"""Step 4 (non-LLM part): Alert node delivery. whisper -> Voice.whisper; alert -> Comms.notify with 3 buttons."""

from __future__ import annotations

import inspect
from pathlib import Path

from contracts.events import SmsOtp, Source
from contracts.state import Alert, Level, Risk
from services.agents.graph import stubs
from services.agents.graph.deps import Tools
from services.agents.graph.runner import replay
from services.agents.graph.state import GraphState
from services.agents.nodes import during
from services.agents.nodes.during import keyword_guardian

FIX = Path(__file__).resolve().parents[3] / "evals" / "fixtures"
BUTTONS = ["call_bank", "ask_trusted_contact", "continue"]


class Fakes:
    def __init__(self) -> None:
        self.comms, self.voice = stubs.FakeComms(), stubs.FakeVoice()
        self.tools = Tools(
            decider=stubs.decide,
            comms=self.comms,
            voice=self.voice,
            store=stubs.FakeStore(),
            account=stubs.FakeAccount(),
        )


def _state(level: Level, prev: list[Alert] | None = None) -> GraphState:
    return GraphState(
        session_id="s",
        event=SmsOtp(session_id="s", t=50, source=Source.network, sender_type="bank_shortcode"),
        risk=Risk(score=0.9, level=level, reasons=["a bank code arrived during this call"]),
        alerts=prev or [],
    )


def test_whisper_level_calls_voice_whisper_only() -> None:
    f = Fakes()
    update = during.make_alert(f.tools, stubs.offline_structured)(_state(Level.whisper))
    assert f.voice.calls == [("whisper", during.WHISPER_TEMPLATE)]  # offline: template whisper
    assert f.comms.calls == []
    assert update["alerts"][0].buttons == []


def test_alert_level_notifies_customer_with_three_buttons() -> None:
    f = Fakes()
    update = during.make_alert(f.tools, stubs.offline_structured)(_state(Level.alert))
    (kind, to, text, buttons), *rest = f.comms.calls
    assert (kind, to, buttons) == ("notify", "customer", ",".join(BUTTONS)) and rest == []
    assert text == update["alerts"][0].reason
    assert update["alerts"][0].buttons == BUTTONS
    assert f.voice.calls == []


def test_nudge_delivers_nothing() -> None:
    f = Fakes()
    update = during.make_alert(f.tools, stubs.offline_structured)(_state(Level.nudge))
    assert update["alerts"][0].level == Level.nudge
    assert f.comms.calls == [] and f.voice.calls == []


def test_same_level_does_not_deliver_again() -> None:
    f = Fakes()
    prev = [Alert(t=40, level=Level.alert, reason="r")]
    assert during.make_alert(f.tools, stubs.offline_structured)(_state(Level.alert, prev)) == {}
    assert f.comms.calls == []


def test_failed_delivery_keeps_alert_in_state() -> None:
    f = Fakes()

    def boom(*_: object) -> str:
        raise TimeoutError

    f.comms.notify = boom  # type: ignore[method-assign]
    update = during.make_alert(f.tools, stubs.offline_structured)(_state(Level.alert))
    assert update["alerts"][0].level == Level.alert
    assert update["trace"][0].action == "alert: template + delivery failed"


def test_hero1_delivers_one_whisper_and_one_notify() -> None:
    f = Fakes()
    replay(
        FIX / "hero1_fake_bank.json",
        tools=f.tools,
        guardian=keyword_guardian,
        structured=stubs.offline_structured,
    )
    assert len(f.voice.calls) == 1
    notifies = [c for c in f.comms.calls if c[0] == "notify"]
    assert len(notifies) == 1 and notifies[0][3] == ",".join(BUTTONS)


def test_real_bank_delivers_nothing() -> None:
    f = Fakes()
    replay(
        FIX / "real_bank_callback.json",
        tools=f.tools,
        guardian=keyword_guardian,
        structured=stubs.offline_structured,
    )
    assert f.comms.calls == [] and f.voice.calls == []


def test_no_hang_up_anywhere() -> None:
    """R2: no tool or node can end a call."""
    assert not [n for n in dir(stubs.FakeComms) if "hang" in n.lower()]
    src = inspect.getsource(during)
    assert "hang_up(" not in src and "end_call(" not in src.replace("def end_call(", "")


# ---- grounding: the copy says only what a flag or signal supports ------------------------------------------

from contracts.state import CallerInfo, Flag, Signal  # noqa: E402
from services.agents.nodes import grounding  # noqa: E402
from services.agents.prompts import AlertCopy  # noqa: E402


def _t92(with_read_code: bool = False) -> GraphState:
    """hero1 at t=92: the bank code has arrived, the caller has not asked for it yet."""
    flags = [Flag(kind="urgency_secrecy", quote="don't call the branch", t=40, confidence=0.9)]
    if with_read_code:
        flags.append(Flag(kind="read_code", quote="Read it back to me", t=101, confidence=0.95))
    return GraphState(
        session_id="s",
        caller=CallerInfo(number="+15555550100", direction="inbound"),  # type: ignore[arg-type]
        event=SmsOtp(session_id="s", t=92, source=Source.network, sender_type="bank_shortcode"),
        signals=[
            Signal(kind="unknown_caller", t=0, weight=0.15),
            Signal(kind="otp_during_call", t=92, weight=0.35, detail="Lone Star Bank"),
        ],
        flags=flags,
        risk=Risk(score=0.62, level=Level.whisper, reasons=["r"]),
    )


class CopyLLM:
    def __init__(self, reason: str, whisper: str) -> None:
        self.out = AlertCopy(reason=reason, whisper=whisper)
        self.users: list[str] = []

    def __call__(self, system: str, user: str, *a: object, **kw: object) -> AlertCopy:
        self.users.append(user)
        return self.out


def test_draft_at_t92_is_the_code_arriving_not_an_ask() -> None:
    draft = grounding.draft_reason(_t92())
    assert draft == "A bank code just arrived while you're on a call with an unverified number."
    assert grounding.unsupported_claims(draft, _t92()) == []


def test_t92_wants_the_code_is_rejected_and_the_draft_is_used() -> None:
    f = Fakes()
    fake = CopyLLM(
        "The caller wants the code your bank just sent, and real staff never ask for it.",
        "Keep that code to yourself.",
    )
    update = during.make_alert(f.tools, fake)(_t92())
    reason = update["alerts"][0].reason
    assert "wants the code" not in reason and reason == grounding.draft_reason(_t92())
    assert f.voice.calls == [("whisper", during.WHISPER_TEMPLATE)]
    assert "ungrounded: asks for a code" in update["trace"][0].action
    assert "<draft>" in fake.users[0]


def test_grounded_rephrase_is_kept() -> None:
    f = Fakes()
    fake = CopyLLM(
        "Your bank just sent a code while an unknown number is on the line.", "Pause before sharing anything."
    )
    update = during.make_alert(f.tools, fake)(_t92())
    assert update["alerts"][0].reason.startswith("Your bank just sent a code")
    assert f.voice.calls == [("whisper", "Pause before sharing anything.")]


def test_once_read_code_is_flagged_the_ask_is_allowed() -> None:
    state = _t92(with_read_code=True)
    assert grounding.draft_reason(state).startswith("The caller asked you to read back a code")
    assert grounding.unsupported_claims("The caller wants the code your bank sent.", state) == []


def test_every_claim_keyword_needs_evidence() -> None:
    state = _t92()
    assert grounding.unsupported_claims("They want a gift card.", state) == ["gift card"]
    assert grounding.unsupported_claims("Don't move your money to a safe account.", state) == ["safe account"]
    assert grounding.unsupported_claims("They may try to swap your SIM.", state) == ["SIM"]
    assert grounding.unsupported_claims("They want remote access.", state) == ["remote access"]
    assert grounding.unsupported_claims("A transfer is being set up.", state) == ["transfer"]


def test_every_draft_sentence_passes_its_own_check_and_the_schema() -> None:
    for kind, sentence in grounding.FLAG_SENTENCE.items():
        state = _t92().model_copy(
            update={"flags": [Flag(kind=kind, quote="q", t=200, confidence=0.9)], "signals": []}
        )  # type: ignore[arg-type]
        assert grounding.draft_reason(state) == sentence
        assert grounding.unsupported_claims(sentence, state) == [], kind
        AlertCopy(reason=sentence, whisper="ok")  # one sentence, <= 140 chars, no promise
