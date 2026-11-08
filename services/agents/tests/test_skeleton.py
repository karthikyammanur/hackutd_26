"""L1-3 walking skeleton: both phases + runner, all stub nodes, no LLM."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from contracts.events import EvalCase
from contracts.state import Level, PlanStep, SessionState
from services.agents.graph import stubs
from services.agents.graph.deps import Tools
from services.agents.graph.runner import replay, replay_case
from services.agents.graph.state import PUBLIC_FIELDS, GraphState
from services.agents.nodes import after
from services.agents.nodes.during import keyword_guardian

ROOT = Path(__file__).resolve().parents[3]
FIX = ROOT / "evals" / "fixtures"


def _run(name: str) -> tuple[SessionState, Any, list[tuple[str, dict[str, Any]]]]:
    tools = stubs.fake_tools()
    updates: list[tuple[str, dict[str, Any]]] = []
    final = replay(
        FIX / name,
        on_update=lambda n, u: updates.append((n, u)),
        tools=tools,
        guardian=keyword_guardian,
        structured=stubs.offline_structured,
    )
    return final, tools, updates


def _max_level(s: SessionState) -> Level:
    return max((a.level for a in s.alerts), default=Level.none)


def test_hero1_reaches_alert_with_three_buttons() -> None:
    final, _, _ = _run("hero1_fake_bank.json")
    top = [a for a in final.alerts if a.level == Level.alert]
    assert len(top) == 1 and top[0].t >= 92
    assert top[0].buttons == ["call_bank", "ask_trusted_contact", "continue"]
    assert all(a.buttons == [] for a in final.alerts if a.level < Level.alert)
    assert final.ended and final.user_choice == "call_bank"


def test_hero1_after_phase_plans_and_traces_every_step() -> None:
    final, tools, _ = _run("hero1_fake_bank.json")
    assert [p.name for p in final.plan] == ["lock_account", "callback", "recovery", "evidence"]
    assert all(p.status == "done" for p in final.plan)
    traced = [x.node for x in final.trace]
    assert (
        traced.index("planner")
        < traced.index("lock_account")
        < traced.index("callback")
        < traced.index("evidence")
    )
    assert final.evidence_id == "ev-fx_hero1_fake_bank"
    # call_bank -> warm transfer to the verified bank number
    after_calls = [c for c in tools.comms.calls if c[0] != "notify"]
    assert [c[0] for c in after_calls[:2]] == ["call", "transfer"]
    assert after_calls[1][2] == "+18005550199"  # Store.official_number("Lone Star Bank")
    # lock_account goes through the Account protocol
    assert tools.account.holds == [
        ("fx_hero1_fake_bank", ("sim_change", "port_out", "call_forwarding_on"), 60)
    ]


def test_continue_skips_lock_account_but_keeps_evidence() -> None:
    final, tools, _ = _run("fake_tmobile_support.json")
    status = {p.name: p.status for p in final.plan}
    assert status["lock_account"] == "skipped" and status["evidence"] == "done"
    assert "lock_account" not in [x.node for x in final.trace]
    assert tools.account.holds == []


def test_real_bank_callback_stays_quiet() -> None:
    final, tools, _ = _run("real_bank_callback.json")
    assert _max_level(final) <= Level.nudge  # R7
    assert final.plan == [] and "planner" not in [x.node for x in final.trace]
    assert tools.comms.calls == []


def test_no_duplicate_list_items() -> None:
    final, _, _ = _run("hero1_fake_bank.json")
    for field in ("flags", "signals", "alerts", "trace"):
        items = [x.model_dump_json() for x in getattr(final, field)]
        assert len(items) == len(set(items)), f"duplicate {field}"
    assert len(final.signals) == 2 and len(final.alerts) == 3


def test_streamed_updates_carry_no_transcript() -> None:
    _, _, updates = _run("hero1_fake_bank.json")
    assert updates
    for _, u in updates:
        assert set(u) <= PUBLIC_FIELDS
        assert "transcript_window" not in u and "event" not in u


def test_emergency_number_does_nothing() -> None:
    case = json.loads((FIX / "hero1_fake_bank.json").read_text())
    case["session_id"] = "fx_emergency"
    for e in case["events"]:
        e["session_id"] = "fx_emergency"
    case["events"][0]["number"] = "911"
    comms, voice = stubs.FakeComms(), stubs.FakeVoice()
    tools = Tools(
        decider=stubs.decide, comms=comms, voice=voice, store=stubs.FakeStore(), account=stubs.FakeAccount()
    )
    final, pred = replay_case(
        EvalCase.model_validate(case), tools, guardian=keyword_guardian, structured=stubs.offline_structured
    )
    assert final.alerts == [] and final.signals == [] and final.flags == [] and final.plan == []
    assert comms.calls == [] and voice.calls == []
    assert [x.node for x in final.trace] == ["emergency"]
    assert pred["alerts"] == []


def test_decide_flags_only_add_risk() -> None:
    state = SessionState(session_id="s", signals=[stubs.Signal(kind="otp_during_call", t=1, weight=0.35)])
    base = stubs.decide(state).score
    state.flags.append(stubs.Flag(kind="read_code", quote="q", t=2, confidence=0.1))
    assert stubs.decide(state).score >= base  # R6


def test_router_hard_cap() -> None:
    s = GraphState(session_id="s", plan=[PlanStep(name="callback")], after_iterations=after.MAX_ITERATIONS)
    update = after.router(s)
    assert [p.status for p in update["plan"]] == ["skipped"]
    assert after.route_after(s.model_copy(update=update)) == "__end__"


def test_predictions_pass_the_eval_gate(tmp_path: Path) -> None:
    preds = tmp_path / "preds.jsonl"
    for f in sorted(FIX.glob("*.json")):
        replay(f, preds_path=preds, guardian=keyword_guardian, structured=stubs.offline_structured)
    rows = [json.loads(line) for line in preds.read_text().splitlines()]
    assert {r["session_id"] for r in rows} == {
        "fx_hero1_fake_bank",
        "fx_real_bank_callback",
        "fx_fake_tmobile_support",
    }
    out = subprocess.run(
        [
            sys.executable,
            str(ROOT / "evals" / "run_eval.py"),
            "--cases",
            str(FIX),
            "--preds",
            str(preds),
            "--gate",
        ],
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stdout + out.stderr
