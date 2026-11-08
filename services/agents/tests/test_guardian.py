"""L1-2 Call Guardian. Offline tests use a fake structured(); live tests replay the fixtures against Brev."""

from __future__ import annotations

import os
import statistics
import time
from pathlib import Path
from typing import Any

import pytest
from dotenv import load_dotenv

from contracts.events import EvalCase, Source, Turn
from contracts.state import CallerInfo, Flag, Level, SessionState
from services.agents import llm
from services.agents.graph import stubs
from services.agents.graph.runner import replay, replay_case
from services.agents.graph.state import GraphState
from services.agents.nodes.guardian import make_guardian
from services.agents.prompts import GuardianFlag, GuardianOutput, load_prompt

load_dotenv()
FIX = Path(__file__).resolve().parents[3] / "evals" / "fixtures"

ASK = "You just got a code. Read the digits to me now so I can confirm it's you."


class FakeLLM:
    def __init__(self, *replies: Any):
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, system: str, user: str, model_cls: type, tier: str, **kw: Any) -> Any:
        self.calls.append({"system": system, "user": user, "model": model_cls, "tier": tier, **kw})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _turn(t: float, speaker: str, text: str) -> Turn:
    return Turn(session_id="s", t=t, source=Source.network, speaker=speaker, text=text)  # type: ignore[arg-type]


def _state(event: Turn, window: list[Turn] | None = None, **kw: Any) -> GraphState:
    caller = CallerInfo(number="+15555550100", direction="inbound")  # type: ignore[arg-type]
    return GraphState(session_id="s", caller=caller, event=event, transcript_window=window or [], **kw)


def _out(*flags: tuple[str, str, float]) -> GuardianOutput:
    return GuardianOutput(flags=[GuardianFlag(kind=k, quote=q, confidence=c) for k, q, c in flags])  # type: ignore[arg-type]


def test_flag_gets_t_of_the_matching_caller_turn() -> None:
    earlier = _turn(20, "caller", "Hello, this is the fraud team.")
    fake = FakeLLM(_out(("read_code", "Read the digits to me now", 0.9)))
    update = make_guardian(fake)(_state(_turn(60, "caller", ASK), [earlier]))
    assert update["flags"] == [
        Flag(kind="read_code", quote="Read the digits to me now", t=60, confidence=0.9)
    ]
    assert fake.calls[0]["tier"] == "fast" and fake.calls[0]["timeout"] == 3.0
    assert fake.calls[0]["model"] is GuardianOutput


def test_transcript_only_in_user_message() -> None:
    fake = FakeLLM(_out())
    make_guardian(fake)(_state(_turn(60, "caller", ASK)))
    call = fake.calls[0]
    assert call["system"] == load_prompt("guardian") and ASK not in call["system"]
    assert "<transcript>" in call["user"] and ASK in call["user"] and "<call_context>" in call["user"]


def test_customer_and_unmatched_quotes_are_dropped() -> None:
    window = [_turn(30, "customer", "Sure, read it to you? the code is here")]
    fake = FakeLLM(
        _out(("read_code", "the code is here", 0.9), ("gift_cards", "buy me some gift cards", 0.9))
    )
    update = make_guardian(fake)(_state(_turn(40, "caller", "Okay, go on."), window))
    assert "flags" not in update


def test_repeat_flags_across_checks_are_dropped() -> None:
    first = _turn(60, "caller", ASK)
    prior = Flag(kind="read_code", quote="Read the digits", t=60, confidence=0.9)
    fake = FakeLLM(_out(("read_code", "Read the digits to me now", 0.95)))
    update = make_guardian(fake)(_state(_turn(70, "caller", "Hurry please."), [first], flags=[prior]))
    assert "flags" not in update


def test_customer_turns_wait_for_every_third_turn() -> None:
    fake = FakeLLM(_out())
    guardian = make_guardian(fake)
    update = guardian(_state(_turn(10, "customer", "Hi."), turns_seen=0))
    assert fake.calls == [] and update["turns_seen"] == 1
    guardian(_state(_turn(12, "customer", "Okay."), turns_seen=2))
    assert len(fake.calls) == 1


def test_failure_pauses_guard_and_adds_nothing() -> None:
    fake = FakeLLM(llm.LLMUnavailable("down"), _out())
    guardian = make_guardian(fake)
    update = guardian(_state(_turn(60, "caller", ASK)))
    assert update["guard_paused"] is True and "flags" not in update
    assert update["trace"][0].action == "guard paused"
    update = guardian(_state(_turn(70, "caller", "Still there?"), guard_paused=True))
    assert update["guard_paused"] is False


def test_keyword_fallback_is_off_by_default_and_works_when_on() -> None:
    off = make_guardian(FakeLLM(llm.LLMInvalidOutput("bad")))(_state(_turn(60, "caller", ASK)))
    assert "flags" not in off
    on = make_guardian(FakeLLM(llm.LLMInvalidOutput("bad")), keyword_fallback=True)(
        _state(_turn(60, "caller", ASK))
    )
    assert [f.kind for f in on["flags"]] == ["read_code"] and on["guard_paused"] is True


STORY = "We noticed a large transfer on your account this morning. Did you authorize it?"


def test_hindsight_flag_on_an_already_judged_turn_is_dropped() -> None:
    """t=20 was judged at t=20; a later check can't re-flag it because the call now looks worse."""
    window = [_turn(20, "caller", STORY)]
    fake = FakeLLM(
        _out(
            ("policy_contradiction", "Did you authorize it?", 0.95),
            ("read_code", "Read the digits to me now", 0.9),
        )
    )
    update = make_guardian(fake)(_state(_turn(60, "caller", ASK), window, guardian_ok_t=20))
    assert [(f.kind, f.t) for f in update["flags"]] == [("read_code", 60)]
    assert update["guardian_ok_t"] == 60


def test_turns_from_a_failed_check_stay_open() -> None:
    window = [_turn(20, "caller", STORY)]
    fake = FakeLLM(_out(("policy_contradiction", "Did you authorize it?", 0.95)))
    update = make_guardian(fake)(_state(_turn(60, "caller", ASK), window, guardian_ok_t=-1.0))
    assert [(f.kind, f.t) for f in update["flags"]] == [("policy_contradiction", 20)]


def test_failed_check_does_not_advance_ok_t() -> None:
    update = make_guardian(FakeLLM(llm.LLMUnavailable("down")))(_state(_turn(60, "caller", ASK)))
    assert "guardian_ok_t" not in update


# --- live: replay each fixture with the Nemotron Guardian --------------------------------------------------

LIVE = bool(os.environ.get("NEMOTRON_BASE_URL"))
FIXTURES = ("hero1_fake_bank", "real_bank_callback", "fake_tmobile_support")


@pytest.fixture(scope="module")
def live_runs() -> dict[str, Any]:
    if not LIVE:
        pytest.skip("needs NEMOTRON_BASE_URL in .env")
    latencies: list[float] = []

    def timed(*args: Any, **kw: Any) -> Any:
        start = time.perf_counter()
        try:
            return llm.structured(*args, **kw)
        finally:
            latencies.append((time.perf_counter() - start) * 1000)

    finals: dict[str, SessionState] = {}
    for name in FIXTURES:
        finals[name] = replay(FIX / f"{name}.json", tools=stubs.fake_tools(), guardian=make_guardian(timed))
    print()
    for name, s in finals.items():
        print(f"== {name}  (guard_paused at end: {s.guard_paused})")
        for f in s.flags:
            print(f"   t={f.t:>4.0f}  {f.kind:<22} {f.confidence:.2f}  {f.quote[:80]!r}")
        if not s.flags:
            print("   (no flags)")
        print("   levels: " + ", ".join(f"t={a.t:.0f} {a.level.name}" for a in s.alerts) or "   levels: none")
    xs = sorted(latencies)
    p95 = xs[max(0, round(0.95 * (len(xs) - 1)))]
    print(
        f"guardian checks: n={len(xs)}  p50 {statistics.median(xs):.0f} ms  p95 {p95:.0f} ms  max {xs[-1]:.0f} ms"
    )
    return {"finals": finals, "latencies": xs}


def test_live_hero1_flags_read_code_at_or_after_the_ask(live_runs: dict[str, Any]) -> None:
    s: SessionState = live_runs["finals"]["hero1_fake_bank"]
    hits = [f for f in s.flags if f.kind == "read_code" and f.confidence >= 0.5]
    assert hits and min(f.t for f in hits) >= 101, s.flags
    assert max(a.level for a in s.alerts) == Level.alert


def test_live_real_bank_callback_has_no_flag_above_half(live_runs: dict[str, Any]) -> None:
    s: SessionState = live_runs["finals"]["real_bank_callback"]
    assert not [f for f in s.flags if f.confidence > 0.5], s.flags
    assert max((a.level for a in s.alerts), default=Level.none) <= Level.nudge  # R7


def test_live_guard_never_paused(live_runs: dict[str, Any]) -> None:
    assert not any("guard paused" == x.action for s in live_runs["finals"].values() for x in s.trace)


GENUINE_FRAUD_ALERT = {
    "session_id": "inline_genuine_fraud_alert",
    "label": {"scam": False, "type": "benign_bank_fraud_alert", "hard_negative": True},
    "events": [
        {
            "t": 0,
            "source": "network",
            "kind": "call_start",
            "direction": "inbound",
            "number": "+15125550186",
            "carrier_label": "none",
            "attestation": "A",
            "first_seen": True,
        },
        {
            "t": 7,
            "source": "network",
            "kind": "turn",
            "speaker": "caller",
            "text": "This is the fraud prevention line at Cedar Ridge Bank. We saw a 74 dollar charge at a gas station about an hour ago. Did you make it?",
        },
        {"t": 15, "source": "network", "kind": "turn", "speaker": "customer", "text": "No, I didn't."},
        {
            "t": 22,
            "source": "network",
            "kind": "turn",
            "speaker": "caller",
            "text": "Okay, then we'll block the card right away and send a new one. You can also check your recent activity in your banking app.",
        },
        {"t": 30, "source": "network", "kind": "turn", "speaker": "customer", "text": "Great, thank you."},
        {"t": 36, "source": "network", "kind": "call_end"},
    ],
}


def test_live_genuine_bank_fraud_alert_gets_no_flag_above_half() -> None:
    """A real fraud-alert call opens with a story and a question. That is not policy_contradiction."""
    if not LIVE:
        pytest.skip("needs NEMOTRON_BASE_URL in .env")
    raw = {
        **GENUINE_FRAUD_ALERT,
        "events": [{"session_id": "inline_genuine_fraud_alert", **e} for e in GENUINE_FRAUD_ALERT["events"]],
    }
    final, _ = replay_case(EvalCase.model_validate(raw), stubs.fake_tools(), guardian=make_guardian())
    print("\ngenuine fraud alert flags:", [(f.kind, f.t, f.confidence) for f in final.flags] or "none")
    assert not [f for f in final.flags if f.confidence > 0.5], final.flags
    assert not final.guard_paused
