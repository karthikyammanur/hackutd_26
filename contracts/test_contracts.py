"""Contract checks: fixtures stay valid, and the ladder rules hold."""

import json
from pathlib import Path

from contracts.events import EMERGENCY_NUMBERS, EvalCase
from contracts.state import Level, Risk, merge_risk

FIXTURES = Path(__file__).resolve().parent.parent / "evals" / "fixtures"


def test_fixtures_validate():
    files = sorted(FIXTURES.glob("*.json"))
    assert files, "no fixtures found"
    for f in files:
        case = EvalCase.model_validate(json.loads(f.read_text()))
        assert case.events[0].kind == "call_start", f.name
        assert case.events[-1].kind == "call_end", f.name
        ts = [e.t for e in case.events]
        assert ts == sorted(ts), f"{f.name}: events out of order"


def test_fixtures_have_a_hard_negative():
    cases = [EvalCase.model_validate(json.loads(f.read_text())) for f in FIXTURES.glob("*.json")]
    assert any(c.label.hard_negative and not c.label.scam for c in cases)


def test_risk_never_goes_down():
    high = Risk(score=0.9, level=Level.alert, reasons=["otp during call"])
    low = Risk(score=0.2, level=Level.nudge, reasons=["llm says safe"])
    merged = merge_risk(high, low)
    assert merged.score == 0.9 and merged.level == Level.alert
    assert "otp during call" in merged.reasons


def test_levels_are_ordered():
    assert Level.none < Level.nudge < Level.whisper < Level.alert


def test_tool_protocols_expose_agreed_methods():
    from contracts.interfaces import Account, Comms, Store, Voice

    expected = {
        Comms: {"notify", "call", "transfer", "message"},
        Voice: {"whisper"},
        Store: {"append_event", "save_evidence", "lookup_verified", "official_number", "search_policy"},
        Account: {"hold_changes"},
    }
    for proto, methods in expected.items():
        assert methods <= set(vars(proto)), proto.__name__
    assert "hang_up" not in vars(Comms)  # R2


def test_emergency_numbers_listed():
    assert {"911", "988"} <= EMERGENCY_NUMBERS
