"""Jev can only raise risk, can't override the hard rules, and any failure falls back to the rules."""

from __future__ import annotations

import json

import pytest

from contracts.events import Direction
from contracts.state import CallerInfo, Flag, Level, Risk, SessionState, Signal
from services.agents.decision import jev_adapter
from services.agents.decision.decide import decide


def state(number="+12145550147", direction=Direction.inbound, verified_org=None, **kw):
    who = CallerInfo(number=number, direction=direction, verified_org=verified_org)
    signals = [Signal(kind="otp_during_call", t=5, weight=0.55)]
    return SessionState(session_id="s", caller=who, signals=signals, **kw)


@pytest.fixture
def jev(monkeypatch):
    monkeypatch.setenv("JEV_URL", "https://jev.invalid/decide")
    calls: list[SessionState] = []

    def install(reply):
        def fake(_url, s):
            calls.append(s)
            if isinstance(reply, Exception):
                raise reply
            return reply

        monkeypatch.setattr(jev_adapter, "_call_jev", fake)
        return calls

    return install


def test_without_url_it_is_exactly_the_rules(monkeypatch):
    monkeypatch.delenv("JEV_URL", raising=False)
    s = state()
    assert jev_adapter.decide_with_jev(s) == decide(s)


def test_jev_can_raise(jev):
    jev(Risk(score=0.95, level=Level.alert, reasons=["jev"]))
    risk = jev_adapter.decide_with_jev(state())
    assert risk.level == Level.alert and "jev" in risk.reasons


def test_r6_jev_cannot_lower(jev):
    jev(Risk(score=0.0, level=Level.none, reasons=["looks safe"]))
    s = state()
    risk = jev_adapter.decide_with_jev(s)
    assert risk.score >= decide(s).score and risk.level >= decide(s).level


@pytest.mark.parametrize("failure", [TimeoutError("slow"), ValueError("bad json"), OSError("refused")])
def test_r4_any_failure_falls_back_to_rules(jev, failure):
    jev(failure)
    s = state()
    assert jev_adapter.decide_with_jev(s) == decide(s)


def test_r1_never_consults_jev_on_emergency(jev):
    calls = jev(Risk(score=1.0, level=Level.alert))
    assert jev_adapter.decide_with_jev(state(number="911")).level == Level.none
    assert calls == []


def test_r4_never_consults_jev_when_paused(jev):
    calls = jev(Risk(score=1.0, level=Level.alert))
    previous = Risk(score=0.2)
    assert jev_adapter.decide_with_jev(state(guard_paused=True, risk=previous)) == previous
    assert calls == []


def test_r7_jev_cannot_alert_on_a_real_bank_call(jev):
    calls = jev(Risk(score=1.0, level=Level.alert))
    s = state("+18005550199", Direction.outbound, "Lone Star Bank")
    assert jev_adapter.decide_with_jev(s).level <= Level.nudge
    assert calls == []


def test_r9_payload_has_no_quotes_and_no_number():
    s = state(flags=[Flag(kind="read_code", quote="read me the code", t=9, confidence=0.9)])
    body = json.dumps(jev_adapter._payload(s))
    assert "read me the code" not in body
    assert "+12145550147" not in body
