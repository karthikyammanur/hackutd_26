"""Verification sweep: prove or disprove each product claim with evidence. Rerunnable, nothing is sent.

    python scripts/verify_claims.py                  # all claims (claim 1 replays hero1 in real time, ~2.5 min)
    python scripts/verify_claims.py --only 3,4,7     # a subset
    python scripts/verify_claims.py --fast           # claim 1 at speed 20 instead of 1

The API runs in-process (FastAPI TestClient) with TOOLS=mock: every tool is an in-memory fake that records
what it was asked to do, with a timestamp. real_tools() is patched to raise, so nothing can text or dial.
LLM calls go to real Nemotron (from .env). Prints a markdown table and writes the full evidence as JSON.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["TOOLS"] = "mock"  # before the app loads .env (load_dotenv never overrides a set variable)

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from services.agents import llm  # noqa: E402
from services.agents.graph import stubs  # noqa: E402
from services.agents.graph.deps import Tools  # noqa: E402
from services.agents.tools.photon import PhotonComms, Sidecar  # noqa: E402
from services.api import hub as hub_module  # noqa: E402
from services.api.main import app, hub  # noqa: E402

FIX = ROOT / "evals" / "fixtures"
Row = tuple[str, str, str]  # claim, status, evidence


def _refuse_real_tools(*_: Any, **__: Any) -> Tools:
    raise RuntimeError("verify_claims: real tools are disabled (TOOLS=mock only)")


hub_module.real_tools = _refuse_real_tools  # type: ignore[assignment]


# ---- instrumented mocks ---------------------------------------------------------------------------------------


class Recorder:
    """Every tool call with a perf_counter timestamp, per session."""

    def __init__(self, sid: str) -> None:
        self.sid = sid
        self.log: list[dict[str, Any]] = []
        self.decides: list[tuple[float, float, str]] = []  # (event t, wall time, level)
        self.comms, self.voice = stubs.FakeComms(), stubs.FakeVoice()
        self.store, self.account = stubs.FakeStore(), stubs.FakeAccount()

    def _rec(self, tool: str, method: str, **kw: Any) -> None:
        self.log.append({"wall": time.perf_counter(), "tool": tool, "method": method, **kw})

    def tools(self) -> Tools:
        rec = self

        def decider(state: Any) -> Any:
            out = stubs.decide(state)
            rec.decides.append((state.event.t if state.event else -1, time.perf_counter(), out.level.name))
            return out

        class Comms:
            def notify(self, session_id: str, to: str, text: str, buttons: list[str]) -> str:
                rec._rec("comms", "notify", to=to, text=text, buttons=buttons)
                return rec.comms.notify(session_id, to, text, buttons)

            def call(self, session_id: str, to: str, script: str) -> str:
                rec._rec("comms", "call", to=to, text=script)
                return rec.comms.call(session_id, to, script)

            def transfer(self, session_id: str, call_id: str, to_number: str) -> str:
                rec._rec("comms", "transfer", to=to_number, text="")
                return rec.comms.transfer(session_id, call_id, to_number)

            def message(self, session_id: str, to: str, text: str) -> str:
                rec._rec("comms", "message", to=to, text=text)
                return rec.comms.message(session_id, to, text)

        class Voice:
            def whisper(self, session_id: str, text: str) -> str:
                rec._rec("voice", "whisper", to="customer", text=text)
                return rec.voice.whisper(session_id, text)

        class Account:
            def hold_changes(self, session_id: str, actions: list[str], minutes: int) -> str:
                rec._rec("account", "hold_changes", actions=list(actions), minutes=minutes)
                return rec.account.hold_changes(session_id, actions, minutes)

        return Tools(decider=decider, comms=Comms(), voice=Voice(), store=rec.store, account=Account())

    def calls(self) -> list[dict[str, Any]]:
        return [{k: v for k, v in c.items() if k != "wall"} for c in self.log]


RECORDERS: dict[str, list[Recorder]] = {}
_current_sid: list[str] = [""]


def _session_tools() -> Tools:
    rec = Recorder(_current_sid[0])
    RECORDERS.setdefault(rec.sid, []).append(rec)
    return rec.tools()


hub_module.session_tools = _session_tools  # type: ignore[assignment]

# Count Nemotron requests (by output model and tier), so "no flags" can be told apart from "Guardian never ran".
LLM_CALLS: dict[str, int] = {}
_orig_complete = llm._complete


def _counting_complete(tier: Any, thinking: Any, messages: Any, model_cls: Any, *a: Any, **kw: Any) -> Any:
    key = f"{model_cls.__name__}/{tier}"
    LLM_CALLS[key] = LLM_CALLS.get(key, 0) + 1
    return _orig_complete(tier, thinking, messages, model_cls, *a, **kw)


llm._complete = _counting_complete  # type: ignore[assignment]


# ---- helpers --------------------------------------------------------------------------------------------------


def case(name: str, sid: str | None = None) -> dict[str, Any]:
    raw = json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))
    sid = sid or raw["session_id"]
    raw["session_id"] = sid
    for e in raw["events"]:
        e["session_id"] = sid
    return raw


def wait_done(sid: str, timeout: float = 180) -> float:
    start = time.perf_counter()
    while time.perf_counter() - start < timeout:
        live = hub.get(sid)
        if live and live.after_done.is_set():
            return time.perf_counter() - start
        time.sleep(0.05)
    raise TimeoutError(f"{sid} did not finish in {timeout}s")


def drive(
    c: TestClient,
    events: list[dict[str, Any]],
    speed: float | None = None,
    choice: str | None = None,
    offline: bool = False,
) -> dict[str, float]:
    """POST events through /events (paced by t/speed when speed is set). Returns wall time of each POST by t.

    choice: replaces the fixture's user_choice with a POST /choice (as the sidecar does).
    """
    sid = events[0]["session_id"]
    _current_sid[0] = sid
    posted: dict[float, float] = {}
    t0 = time.perf_counter()
    for e in events:
        if speed:
            delay = t0 + e["t"] / speed - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
        if e["kind"] == "user_choice":
            if choice is None:
                continue
            r = c.post(f"/sessions/{sid}/choice", json={"choice": choice})
        else:
            q = "?offline=true" if offline and e["kind"] == "call_start" else ""
            posted[e["t"]] = time.perf_counter()
            r = c.post(f"/sessions/{sid}/events{q}", json=e)
        assert r.status_code == 202, (e["kind"], r.status_code, r.text)
    return posted


def final_state(c: TestClient, sid: str) -> dict[str, Any]:
    return c.get(f"/sessions/{sid}").json()


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def levels(state: dict[str, Any]) -> list[str]:
    return [f"t={a['t']:g} {a['level_name'] if 'level_name' in a else a['level']}" for a in state["alerts"]]


LEVEL_NAMES = {0: "none", 1: "nudge", 2: "whisper", 3: "alert"}


def level_name(v: Any) -> str:
    return LEVEL_NAMES.get(v, str(v)) if isinstance(v, int) else str(v)


def max_level(state: dict[str, Any]) -> str:
    vals = [a["level"] for a in state["alerts"]]
    return level_name(max(vals)) if vals else "none"


def trace_lines(state: dict[str, Any], nodes: tuple[str, ...] | None = None) -> list[str]:
    return [
        f"t={x['t']:g} {x['node']}: {x['action']} -> {x['result']}"[:200]
        for x in state["trace"]
        if nodes is None or x["node"] in nodes
    ]


EVIDENCE: dict[str, Any] = {}


# ---- claims ---------------------------------------------------------------------------------------------------


def claim1(c: TestClient, speed: float) -> Row:
    raw = case("hero1_fake_bank", "vc1_timing")
    posted = drive(c, raw["events"], speed=speed, choice="call_bank")
    wait_done("vc1_timing")
    rec = RECORDERS["vc1_timing"][-1]
    turns = [e["t"] for e in raw["events"] if e["kind"] == "turn"]
    decide_at = {t: wall for t, wall, _ in rec.decides}
    lat = [(decide_at[t] - posted[t]) * 1000 for t in turns if t in decide_at]
    ask_t = next(
        e["t"] for e in raw["events"] if e["kind"] == "turn" and e["speaker"] == "caller" and "code" in e["text"]
    )
    notify = next((x for x in rec.log if x["method"] == "notify"), None)
    st = final_state(c, "vc1_timing")
    alert = next((a for a in st["alerts"] if a["level"] == 3), None)
    ask_to_notify = (notify["wall"] - posted[ask_t]) * 1000 if notify else None
    EVIDENCE["1"] = {
        "speed": speed,
        "turn_to_risk_ms": dict(zip(turns, [round(x, 1) for x in lat], strict=False)),
        "levels": [f"t={a['t']:g} {level_name(a['level'])}" for a in st["alerts"]],
        "code_asked_t": ask_t,
        "ask_to_notify_ms": ask_to_notify,
    }
    ok = alert is not None and ask_to_notify is not None and alert["t"] == ask_t and ask_to_notify < 2000
    return (
        "1 Mid-call timing",
        "PASS" if ok else "FAIL",
        f"speed {speed:g}, {len(lat)} turns: turn->risk p50 {pct(lat, .5):.0f} ms, p95 {pct(lat, .95):.0f} ms "
        f"(max {max(lat):.0f}). Code asked at t={ask_t:g}; alert fired at t={alert['t'] if alert else '-'}; "
        f"ask->notify() {ask_to_notify:.0f} ms. Levels: {', '.join(EVIDENCE['1']['levels'])}",
    )


def claim2(c: TestClient) -> Row:
    hits = subprocess.run(
        ["git", "grep", "-n", "-i", "-E", r"consent|opt[_ -]?in|listening|signals[_ -]only|SAFE_SIGNAL_LISTEN",
         "--", "contracts", "services", ".env.example", "apps", "db", "deploy"],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout.strip().splitlines()
    setting = [h for h in hits if "/tests/" not in h]
    raw = case("hero1_fake_bank", "vc2_signals_only")
    keep = {"call_start", "sms_otp", "account_change", "call_end"}
    events = [e for e in raw["events"] if e["kind"] in keep]
    drive(c, events)
    wait_done("vc2_signals_only")
    st = final_state(c, "vc2_signals_only")
    EVIDENCE["2"] = {"grep_hits": setting, "events": [e["kind"] for e in events], "levels": levels(st),
                     "trace": trace_lines(st, ("caller_screen", "signal_watcher", "decide", "alert"))}
    return (
        "2 Signals-only default",
        "NOT IMPLEMENTED" if not setting else "CHECK",
        f"No consent/listening setting in contracts, services, api or .env.example ({len(setting)} grep hits; "
        f"F11 still 'Open' in context/decisions.md). Turns always go to the Guardian. hero1 with turns removed "
        f"({', '.join(e['kind'] for e in events)}; hero1 has no account_change): max level "
        f"{max_level(st)} ({'; '.join(f'{x}' for x in trace_lines(st, ('decide', 'alert')))})",
    )


def run_choice(c: TestClient, choice: str) -> tuple[dict[str, Any], Recorder]:
    sid = f"vc4_{choice}"
    drive(c, case("hero1_fake_bank", sid)["events"], choice=choice)
    wait_done(sid)
    return final_state(c, sid), RECORDERS[sid][-1]


def claim3(c: TestClient, runs: dict[str, tuple[dict[str, Any], Recorder]]) -> Row:
    st, rec = runs["call_bank"]
    holds = [x for x in rec.log if x["method"] == "hold_changes"]
    notify = next((x for x in rec.log if x["method"] == "notify"), None)
    alert_t = next((a["t"] for a in st["alerts"] if a["level"] == 3), None)
    hold_trace = trace_lines(st, ("lock_account",))
    mentions = bool(notify and re.search(r"freez|hold|lock|block|paus", notify["text"], re.I))
    EVIDENCE["3"] = {"holds": holds, "alert_text": notify and notify["text"], "lock_trace": hold_trace}
    at_alert = holds and notify and holds[0]["wall"] - notify["wall"] < 1.0
    return (
        "3 Freeze at alert",
        "PASS" if at_alert and mentions else "FAIL",
        f"hold_changes called {len(holds)}x: actions={holds[0]['actions'] if holds else '-'}, "
        f"minutes={holds[0]['minutes'] if holds else '-'}, but only AFTER call_end ({'; '.join(hold_trace)}), "
        f"not at the alert (t={alert_t}). Alert text mentions the freeze: {'yes' if mentions else 'no'}. "
        f"Exact alert text: \"{notify['text'] if notify else '-'}\" buttons={notify['buttons'] if notify else '-'}",
    )


def claim4(c: TestClient, runs: dict[str, tuple[dict[str, Any], Recorder]]) -> Row:
    out: dict[str, Any] = {}
    parts: list[str] = []
    for choice, (st, rec) in runs.items():
        calls = rec.calls()
        out[choice] = {
            "plan": [f"{p['name']}={p['status']}" for p in st["plan"]],
            "calls": [{k: (v[:160] if isinstance(v, str) else v) for k, v in x.items()} for x in calls],
            "user_choice": st["user_choice"],
            "levels": [f"t={a['t']:g} {level_name(a['level'])}" for a in st["alerts"]],
        }
        methods = [f"{x['method']}->{x.get('to', '')}" for x in calls]
        parts.append(f"**{choice}**: plan [{', '.join(out[choice]['plan'])}]; calls [{', '.join(methods)}]")
    no_cb = not any(x["method"] == "call" for x in runs["continue"][1].log)
    tc = [x for x in runs["ask_trusted_contact"][1].log if x["method"] == "message" and x["to"] == "trusted_contact"]
    # Where does the real adapter send a "trusted_contact" message? Mock transport: nothing leaves the process.
    seen: list[dict[str, Any]] = []
    sidecar = Sidecar("http://sidecar.invalid", httpx.Client(transport=httpx.MockTransport(
        lambda r: (seen.append(json.loads(r.content)), httpx.Response(200, json={"ok": True}))[1])))
    pc = PhotonComms(sidecar=sidecar, voice=None, customer_number="+12145550100")  # type: ignore[arg-type]
    pc.message("probe", "trusted_contact", "probe")
    real_to = seen[0]["to"] if seen else None
    out["photon_trusted_contact_to"] = real_to
    EVIDENCE["4"] = out
    real_ok = real_to != "+12145550100"
    status = "PASS" if no_cb and tc and real_ok else "FAIL"
    return (
        "4 All 3 choices",
        status,
        " | ".join(parts) + f". continue places no callback: {'yes' if no_cb else 'NO'}. ask_trusted_contact "
        f"messages logical 'trusted_contact': {'yes' if tc else 'NO'}, but PhotonComms sends it to "
        f"{'DEMO_CUSTOMER_NUMBER' if not real_ok else real_to} (photon.py _number_for maps every role to the "
        f"customer); DEMO_TRUSTED_CONTACT_NUMBER is read nowhere in services/.",
    )


TURN_PHRASES = ["protected safe account", "Read it back to me", "don't call the branch", "1,240 dollar transfer"]


def claim5(c: TestClient, runs: dict[str, tuple[dict[str, Any], Recorder]], started: float) -> Row:
    st, rec = runs["call_bank"]
    packet = next(iter(rec.store.evidence.values()), None)
    text = json.dumps(packet) if packet else ""
    turn_texts = [e["text"] for e in case("hero1_fake_bank")["events"] if e["kind"] == "turn"]
    full_turns = [t for t in turn_texts if t in text]
    quotes = [f.get("quote", "") for f in (packet or {}).get("flags", [])]
    stored_events = {e.get("kind") for e in rec.store.events}
    # Disk: any file touched since the sweep started (repo, temp) that holds hero1 caller wording, or audio files.
    roots = [ROOT, Path(tempfile.gettempdir())]
    hits: list[str] = []
    audio: list[str] = []
    skip = ("node_modules", ".git", "__pycache__", ".venv", ".ruff_cache", ".pytest_cache")
    for root in roots:
        for p in root.rglob("*"):
            try:
                if any(s in p.parts for s in skip) or not p.is_file() or p.stat().st_mtime < started:
                    continue
                if p.suffix.lower() in (".wav", ".mp3", ".ogg", ".webm", ".m4a", ".pcm"):
                    audio.append(str(p))
                if p.stat().st_size > 5_000_000 or p == Path(EVIDENCE.get("_out", "")):
                    continue
                body = p.read_text(encoding="utf-8", errors="ignore")
                if any(ph in body for ph in TURN_PHRASES):
                    hits.append(str(p))
            except (OSError, PermissionError):
                continue
    hits = [h for h in hits if not h.endswith("verify_claims.py")]
    EVIDENCE["5"] = {"packet": packet, "full_turns_in_packet": full_turns, "flag_quotes": quotes,
                     "store_event_kinds": sorted(k for k in stored_events if k), "disk_hits": hits,
                     "audio_files": audio}
    ok = packet is not None and not full_turns and not hits and not audio and "turn" not in stored_events
    return (
        "5 Evidence, no transcript",
        "PASS" if ok else "FAIL",
        f"Saved via Store.save_evidence -> FakeStore.evidence (in memory; DemoStore in real mode is the same, "
        f"no DB yet). Keys: {sorted(packet) if packet else '-'}. Whole caller turns in packet: {len(full_turns)}. "
        f"Flag quotes (R9 allows short quotes): {len(quotes)}, longest {max((len(q) for q in quotes), default=0)} "
        f"chars. Store kept event kinds {sorted(k for k in stored_events if k)} (no turn). Files touched since start "
        f"holding hero1 wording: {len(hits)}; audio files: {len(audio)} (repo + {tempfile.gettempdir()}).",
    )


def claim6(c: TestClient) -> Row:
    rows: list[str] = []
    ok = True
    EVIDENCE["6"] = {}
    for name in ("real_bank_callback", "real_tmobile_care", "doctor_office_first_seen"):
        sid = f"vc6_{name}"
        drive(c, case(name, sid)["events"], choice=None)
        wait_done(sid)
        st = final_state(c, sid)
        top = max((a["level"] for a in st["alerts"]), default=0)
        ok &= top <= 1
        why = [f"{f['kind']} {f['confidence']}: \"{f['quote'][:60]}\"" for f in st["flags"]]
        sig = [s["kind"] for s in st["signals"]]
        EVIDENCE["6"][name] = {"levels": [f"t={a['t']:g} {level_name(a['level'])}: {a['reason']}" for a in st["alerts"]],
                               "flags": why, "signals": sig, "risk": st["risk"]}
        rows.append(f"{name}: max {level_name(top)}, risk {st['risk']['score'] if st['risk'] else 0:.2f}, "
                    f"flags [{'; '.join(why) or 'none'}], signals [{', '.join(sig)}]"
                    + (f", alert '{st['alerts'][-1]['reason']}'" if st["alerts"] else ""))
    return ("6 Quiet on legit calls", "PASS" if ok else "FAIL", " | ".join(rows))


def claim7(c: TestClient) -> Row:
    pat = r"hang[_ -]?up|hangup|end_?call|endCall|terminate|disconnect|\.hangup\(|drop_call"
    hits = subprocess.run(["git", "grep", "-n", "-i", "-E", pat], cwd=ROOT, capture_output=True,
                          text=True).stdout.strip().splitlines()
    code = [h for h in hits if re.match(r"[^:]+\.(py|ts|tsx|js)$", h.split(":")[0])]
    # Not call control: tests asserting R2, synthetic scam lines (data/), Guardian keyword patterns, comments,
    # the graph node that RECORDS a call_end event, and FastAPI's WebSocketDisconnect.
    benign = re.compile(
        r"/tests?/|test_contracts|^data/|stand_in_guardian|stubs\.py:\d+:\s+\(\"urgency|#|\"\"\"|"
        r"\"call_end\": \"end_call\"|add_node\(\"end_call\"|add_conditional_edges\(\"end_call\"|"
        r"def end_call\(state|WebSocketDisconnect|No method here can hang up",
    )
    defs = [h for h in code if not benign.search(h)]
    from contracts import interfaces

    proto = {n: [m for m in vars(p) if not m.startswith("_")] for n, p in
             (("Comms", interfaces.Comms), ("Voice", interfaces.Voice))}
    EVIDENCE["7_protocol_methods"] = proto
    defs += [f"{n}.{m}" for n, ms in proto.items() for m in ms if re.search(r"hang|end|terminat|disconn|drop", m)]
    rows: list[str] = []
    EVIDENCE["7"] = {"code_hits": code, "method_defs_or_calls": defs}
    quiet = True
    for number in ("911", "988"):
        sid = f"vc7_{number}"
        ev = case("hero1_fake_bank", sid)["events"]
        ev[0]["number"] = number
        drive(c, ev, choice="call_bank")
        wait_done(sid)
        st = final_state(c, sid)
        rec = RECORDERS[sid][-1]
        nodes = sorted({x["node"] for x in st["trace"]})
        quiet &= not rec.log and not st["alerts"] and nodes == ["emergency"]
        EVIDENCE["7"][number] = {"trace": trace_lines(st), "tool_calls": rec.calls()}
        rows.append(f"{number}: {len(rec.log)} tool calls, {len(st['alerts'])} alerts, trace nodes {nodes}")
    return (
        "7 Never hangs up / emergency",
        "PASS" if quiet and not defs else "FAIL",
        f"git grep hang-up/end-call/terminate/disconnect: {len(code)} code lines, {len(defs)} that control a call "
        f"({'; '.join(defs[:4]) or 'none'}; the rest are comments, R2 tests, synthetic data, keyword patterns, "
        f"the end_call node that records call_end, WebSocketDisconnect). Comms/Voice methods: "
        f"{proto}. Full hero1 replayed as {', '.join(rows)}.",
    )


def claim8(c: TestClient) -> Row:
    rows: list[str] = []
    EVIDENCE["8"] = {}
    saved = os.environ.get("NEMOTRON_BASE_URL", "")
    status = "PASS"
    for label, url in (("refused", "http://127.0.0.1:9/v1"), ("blackhole", "http://10.255.255.1:9/v1")):
        os.environ["NEMOTRON_BASE_URL"] = url
        llm._endpoints.cache_clear()  # type: ignore[attr-defined]
        sid = f"vc8_{label}"
        raw = case("hero1_fake_bank", sid)
        t_start = time.perf_counter()
        posted = drive(c, raw["events"], choice="call_bank")
        done = wait_done(sid, timeout=300)
        st = final_state(c, sid)
        rec = RECORDERS[sid][-1]
        decide_at = {t: w for t, w, _ in rec.decides}
        per = {t: round((decide_at[t] - posted[t]) * 1000) for t in posted if t in decide_at}
        guardian = trace_lines(st, ("guardian",))
        alert_src = [x["action"] for x in st["trace"] if x["node"] == "alert"]
        EVIDENCE["8"][label] = {"levels": [f"t={a['t']:g} {level_name(a['level'])}" for a in st["alerts"]],
                                "guard_paused": st["guard_paused"], "event_ms": per, "guardian": guardian,
                                "alert_actions": alert_src, "plan": [f"{p['name']}={p['status']}" for p in st["plan"]],
                                "total_s": round(time.perf_counter() - t_start, 1)}
        worst = max(per.values()) if per else 0
        rows.append(
            f"{label} ({url}): max level {max_level(st)} ({', '.join(EVIDENCE['8'][label]['levels'])}), "
            f"guard_paused={st['guard_paused']}, slowest event {worst} ms, alert copy [{'; '.join(alert_src)}], "
            f"aftercare [{', '.join(EVIDENCE['8'][label]['plan'])}] done {done:.1f}s after call_end, "
            f"guardian trace: {guardian[:2] or 'none'}"
        )
        if max_level(st) == "none":
            status = "FAIL"
    os.environ["NEMOTRON_BASE_URL"] = saved
    llm._endpoints.cache_clear()  # type: ignore[attr-defined]
    return ("8 Nemotron (fast) down", status, " | ".join(rows) + ". No NIM fallback configured in .env.")


def claim9(c: TestClient) -> Row:
    sid = "fx_hero1_fake_bank"
    _current_sid[0] = sid
    msgs: list[dict[str, Any]] = []
    stop = threading.Event()

    def reader() -> None:
        with c.websocket_connect(f"/ws/{sid}") as ws:
            while not stop.is_set():
                try:
                    msgs.append(json.loads(ws.receive_text()))
                except Exception:
                    return

    th = threading.Thread(target=reader, daemon=True)
    th.start()
    time.sleep(0.3)
    r1 = c.post(f"/sessions/{sid}/replay?speed=40")
    time.sleep(1.5)  # the first replay is mid-call (around t=60) when the second lands
    second_at = time.perf_counter()
    r2 = c.post(f"/sessions/{sid}/replay?speed=40")
    wait_done(sid)
    time.sleep(1.0)
    stop.set()
    first, second = RECORDERS[sid][-2], RECORDERS[sid][-1]
    late_first = [x["method"] for x in first.log if x["wall"] > second_at]
    ev_t = [m["event"]["t"] for m in msgs if m["type"] == "event"]
    backwards = sum(1 for a, b in zip(ev_t, ev_t[1:], strict=False) if b < a)
    st = final_state(c, sid)
    EVIDENCE["9"] = {"r1": [r1.status_code, r1.json()], "r2": [r2.status_code, r2.json()],
                     "event_t_sequence": ev_t, "first_run_tool_calls_after_restart": late_first,
                     "first_run_calls": first.calls(), "levels": levels(st)}
    clean = r2.status_code == 202 and not late_first
    return (
        "9 Duplicate replay",
        "PASS" if clean else "FAIL",
        f"Both POSTs {r1.status_code}/{r2.status_code}; the 2nd closes the 1st (hub.start) and starts fresh. "
        f"WS saw event t sequence going backwards {backwards}x (restart from t=0, same socket). "
        f"First run made {len(first.log)} tool calls, {len(late_first)} after the restart {late_first}. "
        f"Final session: levels {', '.join(f'{x}' for x in [f'''t={a['t']:g} {level_name(a['level'])}''' for a in st['alerts']])}.",
    )


def claim10() -> Row:
    src = (ROOT / "spikes" / "photon" / "sidecar.ts").read_text(encoding="utf-8").splitlines()
    want = [r"const target", r"session: process\.env\.SESSION_ID", r"target\.session = session",
            r"target\.session\)\}/choice", r"if \(!target\.session\)"]
    lines = [f"sidecar.ts:{i + 1} `{ln.strip()[:90]}`" for i, ln in enumerate(src)
             if any(re.search(w, ln) for w in want)]
    EVIDENCE["10"] = {"lines": lines}
    return (
        "10 Sidecar reply mapping",
        "FAIL",
        "Not run live (it would send iMessages). By code: the sidecar keeps ONE global `target` (to, session, "
        "buttons); every /notify AND /message overwrites target.session, and a reply is forwarded to "
        "target.session. So with two sessions, \"1\" goes to whichever session messaged last (a whisper or "
        "recovery text on B after the alert on A steals A's reply). " + "; ".join(lines),
    )


# ---- main -----------------------------------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma list of claim numbers")
    ap.add_argument("--fast", action="store_true", help="claim 1 at speed 20 instead of 1")
    ap.add_argument("--out", default=str(Path(tempfile.gettempdir()) / "safe_signal_verify_claims.json"))
    args = ap.parse_args()
    only = {int(x) for x in args.only.split(",") if x.strip()} or set(range(1, 11))
    EVIDENCE["_out"] = args.out
    started = time.time()
    rows: list[Row] = []
    with TestClient(app) as c:
        h = c.get("/health").json()
        assert h["tools"] == "mock", h
        steps: dict[int, Callable[[], Any]] = {}
        runs: dict[str, tuple[dict[str, Any], Recorder]] = {}

        def need_runs() -> None:
            if not runs:
                for ch in ("call_bank", "ask_trusted_contact", "continue"):
                    runs[ch] = run_choice(c, ch)

        steps[1] = lambda: rows.append(claim1(c, 20.0 if args.fast else 1.0))
        steps[2] = lambda: rows.append(claim2(c))
        steps[3] = lambda: (need_runs(), rows.append(claim3(c, runs)))
        steps[4] = lambda: (need_runs(), rows.append(claim4(c, runs)))
        steps[5] = lambda: (need_runs(), rows.append(claim5(c, runs, started)))
        steps[6] = lambda: rows.append(claim6(c))
        steps[7] = lambda: rows.append(claim7(c))
        steps[8] = lambda: rows.append(claim8(c))
        steps[9] = lambda: rows.append(claim9(c))
        steps[10] = lambda: rows.append(claim10())
        for n in sorted(only):
            t = time.perf_counter()
            before = dict(LLM_CALLS)
            try:
                steps[n]()
            except Exception as exc:  # one broken claim must not hide the others
                rows.append((f"{n}", "ERROR", f"{type(exc).__name__}: {exc}"))
            used = {k: v - before.get(k, 0) for k, v in LLM_CALLS.items() if v - before.get(k, 0)}
            EVIDENCE.setdefault("llm_requests", {})[str(n)] = used
            if rows and rows[-1][0].split()[0] == str(n) and used:
                claim, status, ev = rows[-1]
                rows[-1] = (claim, status, ev + f" [Nemotron requests: {used}]")
            print(f"[claim {n}] {time.perf_counter() - t:.1f}s", file=sys.stderr)
    Path(args.out).write_text(json.dumps(EVIDENCE, indent=2, default=str), encoding="utf-8")
    print("| Claim | Result | Evidence |\n| --- | --- | --- |")
    for claim, status, ev in rows:
        print(f"| {claim} | {status} | {ev.replace('|', '/')} |")
    print(f"\nFull evidence: {args.out}")


if __name__ == "__main__":
    main()
