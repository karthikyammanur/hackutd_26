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
