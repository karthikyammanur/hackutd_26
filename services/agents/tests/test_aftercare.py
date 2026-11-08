"""L1-4 Aftercare: planner rules in code, Nemotron steps with template fallbacks, live hero1 end to end."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import pytest
from dotenv import load_dotenv

from contracts.events import CallEnd, Source
from contracts.state import Alert, CallerInfo, Flag, Level, PlanStep, Risk, Signal, StepName
from services.agents import llm
from services.agents.graph import stubs
from services.agents.graph.deps import Tools
from services.agents.graph.runner import replay
from services.agents.graph.state import GraphState
from services.agents.nodes import after
from services.agents.nodes.guardian import make_guardian
from services.agents.prompts import CallbackScript, EvidenceSummary, PlannerOutput, RecoveryPlan, RecoveryStep

load_dotenv()
FIX = Path(__file__).resolve().parents[3] / "evals" / "fixtures"
BANK, BANK_NUMBER = "Lone Star Bank", "+18005550199"  # FakeStore's synthetic official number


class FakeLLM:
    """Answers by output model; a missing model raises like a dead endpoint."""

    def __init__(self, **by_model: Any):
        self.by_model = by_model
        self.calls: list[dict[str, Any]] = []

    def __call__(self, system: str, user: str, model_cls: type, tier: str, **kw: Any) -> Any:
        self.calls.append({"model": model_cls.__name__, "user": user, "tier": tier, **kw})
        reply = self.by_model.get(model_cls.__name__)
        if reply is None:
            raise llm.LLMUnavailable("fake: no reply")
        return reply


class Fakes:
    def __init__(self) -> None:
        self.comms, self.store, self.account = stubs.FakeComms(), stubs.FakeStore(), stubs.FakeAccount()
        self.tools = Tools(
            decider=stubs.decide,
            comms=self.comms,
            voice=stubs.FakeVoice(),
            store=self.store,
            account=self.account,
        )


def _state(choice: str | None, top: Level = Level.alert, plan: list[PlanStep] | None = None) -> GraphState:
    return GraphState(
        session_id="s",
        caller=CallerInfo(number="+15555550100", direction="inbound"),  # type: ignore[arg-type]
        event=CallEnd(session_id="s", t=131, source=Source.network),
        signals=[Signal(kind="otp_during_call", t=92, weight=0.35, detail=BANK)],
        flags=[Flag(kind="read_code", quote="read the code back to me", t=101, confidence=0.95)],
        risk=Risk(score=0.94, level=top),
        alerts=[Alert(t=92, level=top, reason="r")],
        user_choice=choice,
        plan=plan or [],
    )


def _names(plan: list[PlanStep]) -> list[StepName]:
    return [p.name for p in plan]


# ---- planner rules (enforced in code) -----------------------------------------------------------------------


def test_alert_session_keeps_lock_account_even_if_planner_drops_it() -> None:
    plan = after.enforce_plan(["callback", "recovery", "evidence"], _state("call_bank"))
    assert _names(plan) == ["lock_account", "callback", "recovery", "evidence"]
    assert plan[0].detail == "required: session reached alert"


def test_whisper_session_may_drop_lock_account() -> None:
    plan = after.enforce_plan(["callback", "evidence"], _state(None, top=Level.whisper))
    assert _names(plan) == ["callback", "evidence"]


def test_continue_skips_lock_account_even_if_planner_wants_it() -> None:
    plan = after.enforce_plan(["lock_account", "recovery", "evidence"], _state("continue"))
    assert [(p.name, p.status) for p in plan] == [
        ("lock_account", "skipped"),
        ("recovery", "pending"),
        ("evidence", "pending"),
    ]


def test_trusted_contact_only_on_the_customers_choice() -> None:
    assert "notify_trusted_contact" not in _names(
        after.enforce_plan(["notify_trusted_contact", "evidence"], _state("call_bank"))
    )
    plan = after.enforce_plan(["recovery"], _state("ask_trusted_contact"))
    assert _names(plan) == ["lock_account", "recovery", "notify_trusted_contact", "evidence"]


def test_call_bank_forces_callback_and_evidence_is_always_last() -> None:
    plan = after.enforce_plan(["evidence", "recovery"], _state("call_bank"))
    assert _names(plan) == ["lock_account", "callback", "recovery", "evidence"]


def test_planner_uses_nemotron_then_enforces() -> None:
    fake = FakeLLM(
        PlannerOutput=PlannerOutput(
            steps=["callback", "recovery", "evidence"], rationale="Bank code was requested."
        )
    )
    update = after.make_planner(fake)(_state("call_bank"))
    assert _names(update["plan"]) == ["lock_account", "callback", "recovery", "evidence"]
    assert fake.calls[0]["tier"] == "deep" and fake.calls[0]["timeout"] == 25.0
    assert (
        "lock_account (required)" in update["trace"][0].result
        and "Bank code was requested." in update["trace"][0].result
    )


def test_planner_falls_back_when_llm_fails() -> None:
    update = after.make_planner(FakeLLM())(_state("call_bank"))
    assert _names(update["plan"]) == ["lock_account", "callback", "recovery", "evidence"]
    assert "planner fallback" in update["trace"][0].result


# ---- steps --------------------------------------------------------------------------------------------------

SCRIPT = CallbackScript(
    opening="Hi, this is Safe Signal, your T-Mobile call protection. I will never ask you for a code.",
    explanation="That caller asked you to read back a bank code. Your bank never asks for that.",
    transfer_offer="If you like, I can connect you to Lone Star Bank on its official number. It's your choice.",
)


def _run_step(name: StepName, state: GraphState, fake: FakeLLM, f: Fakes) -> dict[str, Any]:
    return after.make_step(name, f.tools, fake)(state.model_copy(update={"plan": [PlanStep(name=name)]}))


def test_callback_speaks_nemotron_script_then_warm_transfers() -> None:
    f, fake = Fakes(), FakeLLM(CallbackScript=SCRIPT)
    update = _run_step("callback", _state("call_bank"), fake, f)
    assert [c[0] for c in f.comms.calls] == ["call", "transfer"]
    assert f.comms.calls[0][2].startswith("Hi, this is Safe Signal") and f.comms.calls[1][2] == BANK_NUMBER
    assert update["trace"][0].action == "nemotron script + comms.call + comms.transfer"
    assert f"verified_number: {BANK_NUMBER}" in fake.calls[0]["user"] and fake.calls[0]["timeout"] == 25.0


def test_callback_script_with_an_unknown_number_is_replaced() -> None:
    bad = SCRIPT.model_copy(update={"transfer_offer": "Or call us back at 214 555 0147. It's your choice."})
    f = Fakes()
    update = _run_step("callback", _state("call_bank"), FakeLLM(CallbackScript=bad), f)
    assert "214 555 0147" not in f.comms.calls[0][2]
    assert update["trace"][0].action.startswith("template script")


def test_callback_without_call_bank_offers_but_does_not_transfer() -> None:
    f = Fakes()
    _run_step("callback", _state(None), FakeLLM(CallbackScript=SCRIPT), f)
    assert [c[0] for c in f.comms.calls] == ["call"]


def test_recovery_sends_steps_and_keeps_the_cancel_request() -> None:
    plan = RecoveryPlan(
        steps=[
            RecoveryStep(
                order=1,
                title="Call your bank on the number on your card",
                detail="Use the number printed on your card.",
            )
        ],
        cancel_request="The account holder was asked for a one-time code by a caller. They approved no transfer and ask for a review.",
    )
    f, fake = Fakes(), FakeLLM(RecoveryPlan=plan)
    update = _run_step("recovery", _state("call_bank"), fake, f)
    assert f.comms.calls[0][:2] == ("message", "customer") and "1. Call your bank" in f.comms.calls[0][2]
    assert update["cancel_request"] == plan.cancel_request
    assert (
        "<what_moved>" in fake.calls[0]["user"] and "a one-time code was requested" in fake.calls[0]["user"]
    )


def test_recovery_falls_back_to_template() -> None:
    f = Fakes()
    update = _run_step("recovery", _state("call_bank"), FakeLLM(), f)
    assert update["trace"][0].action == "template plan + comms.message" and update["cancel_request"] == ""


def test_evidence_packet_has_summary_and_no_transcript() -> None:
    f = Fakes()
    state = _state("call_bank").model_copy(
        update={"cancel_request": "cancel please", "transcript_window": []}
    )
    fake = FakeLLM(
        EvidenceSummary=EvidenceSummary(
            summary="Inbound unverified call; a bank code was requested at t=101."
        )
    )
    update = _run_step("evidence", state, fake, f)
    packet = f.store.evidence[update["evidence_id"]]
    assert packet["summary"].startswith("Inbound") and packet["cancel_request"] == "cancel please"
    assert "transcript" not in json.dumps(packet).lower()
    assert fake.calls[0]["tier"] == "fast" and fake.calls[0]["timeout"] == 10.0


def test_after_call_llm_failure_never_pauses_the_guard() -> None:
    f = Fakes()
    for name in ("callback", "recovery", "evidence"):
        update = _run_step(name, _state("call_bank"), FakeLLM(), f)
        assert "guard_paused" not in update and update["plan"][0].status == "done"


# ---- live: hero1 end to end on Nemotron (L1-4 done-when) ---------------------------------------------------


@pytest.mark.skipif(
    not (os.environ.get("NEMOTRON_BASE_URL") and os.environ.get("NEMOTRON_DEEP_BASE_URL")),
    reason="needs both Brev servers in .env",
)
def test_live_hero1_aftercare_trace_shows_each_step_in_order() -> None:
    f = Fakes()
    timings: list[tuple[str, float]] = []

    def timed(system: str, user: str, model_cls: type, tier: llm.Tier, **kw: Any) -> Any:
        start = time.perf_counter()
        try:
            return llm.structured(system, user, model_cls, tier, **kw)
        finally:
            timings.append((model_cls.__name__, (time.perf_counter() - start) * 1000))

    final = replay(
        FIX / "hero1_fake_bank.json", tools=f.tools, guardian=make_guardian(timed), structured=timed
    )
    print("\nlevels: " + ", ".join(f"t={a.t:.0f} {a.level.name}" for a in final.alerts))
    for a in final.alerts:
        print(f"  t={a.t:.0f} {a.level.name}: {a.reason}")
    print("after-call trace:")
    for x in final.trace:
        if x.t >= 131:
            print(f"  {x.node:<16} {x.action:<46} {x.result}")
    print("llm calls: " + ", ".join(f"{n} {ms:.0f}ms" for n, ms in timings if n != "GuardianOutput"))
    packet = f.store.evidence.get(final.evidence_id or "", {})
    print("evidence summary:", packet.get("summary"))
    print("cancel request:", packet.get("cancel_request"))

    names = _names(final.plan)
    assert names == [n for n in after.ORDER if n in names], names  # fixed order
    assert names[0] == "lock_account" and "callback" in names and names[-1] == "evidence"
    assert all(p.status == "done" for p in final.plan), final.plan
    traced = [x for x in final.trace if x.node in names]
    assert [x.node for x in traced] == names and all(x.result for x in traced)
    planner = next(x for x in final.trace if x.node == "planner")
    assert "planner fallback" not in planner.result
    for x in traced:
        if x.node in ("callback", "recovery", "evidence"):
            assert x.action.startswith("nemotron"), x
    assert [c[0] for c in f.comms.calls if c[0] in ("call", "transfer")] == ["call", "transfer"]
    assert any(c[0] == "transfer" and c[2] == BANK_NUMBER for c in f.comms.calls)
    assert not final.guard_paused
