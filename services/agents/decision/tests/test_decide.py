"""Proves R1, R4, R5, R6, R7 on the rules and on the fixtures."""

import json
import random
import time
from pathlib import Path

import pytest

from contracts.events import EMERGENCY_NUMBERS, Direction, EvalCase, Turn
from contracts.state import CallerInfo, Flag, FlagKind, Level, Risk, SessionState, Signal
from evals.replay import replay_case
from services.agents.decision import config
from services.agents.decision.decide import decide, deterministic_score, is_emergency

FIXTURES = Path(__file__).resolve().parents[4] / "evals" / "fixtures"
FLAG_KINDS = list(config.FLAG_WEIGHTS)
SIGNAL_KINDS = list(config.SIGNAL_REASONS) + ["verified_caller"]


def caller(number="+12145550147", direction=Direction.inbound, verified_org=None):
    return CallerInfo(number=number, direction=direction, verified_org=verified_org)


def otp(weight=0.55, t=10.0):
    return Signal(kind="otp_during_call", t=t, weight=weight)


def flag(kind: FlagKind = "read_code", confidence=0.95, t=20.0):
    return Flag(kind=kind, quote="x", t=t, confidence=confidence)


def trusted_state(**kw):
    return SessionState(
        session_id="s", caller=caller("+18005550199", Direction.outbound, "Lone Star Bank"), **kw
    )


def fixture(name: str) -> EvalCase:
    return EvalCase.model_validate(json.loads((FIXTURES / f"{name}.json").read_text()))


# ---- R1: emergency numbers ----


@pytest.mark.parametrize("number", sorted(EMERGENCY_NUMBERS) + ["+1911", "1-911", "+1 (988)", " 911 "])
def test_r1_emergency_is_always_none(number):
    state = SessionState(
        session_id="s",
        caller=caller(number),
        signals=[otp(), Signal(kind="scam_list_hit", t=0, weight=1.0)],
        flags=[flag("gift_cards", 1.0), flag("read_code", 1.0)],
    )
    risk = decide(state)
    assert risk.level == Level.none and risk.score == 0.0


def test_r1_beats_previous_risk_and_paused_guard():
    state = SessionState(
        session_id="s", caller=caller("911"), risk=Risk(score=0.9, level=Level.alert), guard_paused=True
    )
    assert decide(state).level == Level.none


def test_r1_ordinary_numbers_are_not_emergency():
    assert not is_emergency("+12145550147")
    assert not is_emergency("9110")


# ---- R4: failures leave the call alone ----


def test_r4_paused_guard_returns_previous_unchanged():
    previous = Risk(score=0.4, level=Level.nudge, reasons=["earlier"])
    state = SessionState(
        session_id="s", caller=caller(), risk=previous, guard_paused=True, signals=[otp(1.0)], flags=[flag()]
    )
    assert decide(state) == previous


def test_r4_internal_error_returns_previous(monkeypatch):
    from services.agents.decision import decide as module

    def boom(_state):
        raise RuntimeError("bad state")

    monkeypatch.setattr(module, "rule_risk", boom)
    previous = Risk(score=0.3, level=Level.nudge)
    assert decide(SessionState(session_id="s", caller=caller(), risk=previous)) == previous


def test_r4_no_caller_info_does_nothing():
    risk = decide(SessionState(session_id="s", signals=[otp(1.0)], flags=[flag()]))
    assert risk.level == Level.none and risk.score == 0.0


# ---- R5: risk only goes up ----


def test_r5_risk_never_falls_across_a_random_call():
    rng = random.Random(5)
    for _ in range(200):
        state = SessionState(session_id="s", caller=caller())
        last = Risk(score=0.0)
        for step in range(25):
            if rng.random() < 0.5:
                state.signals.append(Signal(kind=rng.choice(SIGNAL_KINDS), t=step, weight=rng.random()))  # type: ignore[arg-type]
            else:
                state.flags.append(
                    Flag(kind=rng.choice(FLAG_KINDS), quote="", t=step, confidence=rng.random())
                )
            state.risk = decide(state)
            assert state.risk.score >= last.score and state.risk.level >= last.level
            last = state.risk


def test_r5_high_risk_survives_weaker_evidence():
    state = SessionState(
        session_id="s", caller=caller(), risk=Risk(score=0.9, level=Level.alert, reasons=["otp"])
    )
    risk = decide(state)
    assert risk.score == 0.9 and risk.level == Level.alert and "otp" in risk.reasons


# ---- R6: flags never lower the deterministic score ----


def test_r6_flags_only_add_risk():
    rng = random.Random(6)
    for _ in range(500):
        signals = [
            Signal(kind=rng.choice(SIGNAL_KINDS), t=0, weight=rng.random())  # type: ignore[arg-type]
            for _ in range(rng.randint(0, 5))
        ]
        flags = [
            Flag(kind=rng.choice(FLAG_KINDS), quote="", t=0, confidence=rng.random())
            for _ in range(rng.randint(0, 5))
        ]
        who = caller() if rng.random() < 0.5 else caller("+18005550199", Direction.outbound, "Bank")
        without = decide(SessionState(session_id="s", caller=who, signals=signals))
        with_flags = decide(SessionState(session_id="s", caller=who, signals=signals, flags=flags))
        assert with_flags.score >= without.score
        assert with_flags.level >= without.level


def test_r6_reassuring_low_confidence_flag_cannot_reduce_score():
    state = SessionState(session_id="s", caller=caller(), signals=[otp()])
    base, _ = deterministic_score(state)
    state.flags.append(flag("other", 0.0))
    assert decide(state).score >= base


# ---- R7: real bank stays quiet ----


def test_r7_config_keeps_the_cap_below_whisper():
    assert config.TRUSTED_CAP < config.WHISPER


def test_r7_verified_outbound_with_code_stays_at_or_below_nudge():
    state = trusted_state(signals=[otp(1.0), Signal(kind="bank_app_during_call", t=11, weight=1.0)])
    assert decide(state).level <= Level.nudge


def test_r7_read_code_flag_alone_does_not_lift_cap():
    state = trusted_state(signals=[otp(1.0)], flags=[flag("read_code", 1.0), flag("urgency_secrecy", 1.0)])
    assert decide(state).level <= Level.nudge


def test_r7_weak_hard_flag_does_not_lift_cap():
    state = trusted_state(signals=[otp(1.0)], flags=[flag("gift_cards", 0.2)])
    assert decide(state).level <= Level.nudge


@pytest.mark.parametrize("kind", sorted(config.UNCAP_FLAGS))
def test_r7_confident_hard_flag_lifts_cap(kind):
    state = trusted_state(flags=[flag(kind, 1.0)])
    assert decide(state).level == Level.alert


def test_r7_inbound_verified_number_is_not_trusted_by_the_cap():
    state = SessionState(
        session_id="s",
        caller=caller("+18005550199", Direction.inbound, "Lone Star Bank"),
        signals=[otp(1.0)],
        flags=[flag("read_code", 1.0)],
    )
    assert decide(state).level == Level.alert


# ---- Fixtures end to end, with the flags Call Guardian is expected to raise (L1-2) ----

GUARDIAN_FLAGS: dict[str, dict[float, tuple[FlagKind, float]]] = {
    "fx_hero1_fake_bank": {
        40: ("urgency_secrecy", 0.9),
        101: ("read_code", 0.95),
        118: ("safe_account", 0.95),
    },
    "fx_fake_tmobile_support": {
        30: ("policy_contradiction", 0.9),
        64: ("gift_cards", 0.95),
        80: ("read_code", 0.9),
    },
}


def guardian_for(session_id: str):
    table = GUARDIAN_FLAGS.get(session_id, {})

    def flagger(event):
        if isinstance(event, Turn) and event.t in table:
            kind, confidence = table[event.t]
            return [Flag(kind=kind, quote="", t=event.t, confidence=confidence)]
        return []

    return flagger


@pytest.mark.parametrize("name", ["hero1_fake_bank", "fake_tmobile_support"])
def test_scam_fixtures_reach_alert(name):
    case = fixture(name)
    risk = replay_case(case, flagger=guardian_for(case.session_id)).state.risk
    assert risk is not None and risk.level == Level.alert


def test_hero1_escalates_up_the_ladder_and_alerts_at_the_ask():
    result = replay_case(fixture("hero1_fake_bank"), flagger=guardian_for("fx_hero1_fake_bank"))
    first = {
        name: next(a["t"] for a in result.alerts if a["level"] == name)
        for name in ("nudge", "whisper", "alert")
    }
    assert first["nudge"] < first["whisper"] <= 92 < first["alert"] <= 101


@pytest.mark.parametrize("name", ["real_bank_callback", "real_tmobile_care", "doctor_office_first_seen"])
def test_hard_negative_fixtures_stay_at_or_below_nudge(name):
    case = fixture(name)
    risk = replay_case(case, flagger=guardian_for(case.session_id)).state.risk
    assert risk is not None and risk.level <= Level.nudge


# ---- Repeated evidence counts once, at its strongest ----


def test_repeated_signals_do_not_stack():
    one = decide(SessionState(session_id="s", caller=caller(), signals=[otp(0.5)]))
    many = decide(
        SessionState(session_id="s", caller=caller(), signals=[otp(0.1), otp(0.5), otp(0.2), otp(0.5)])
    )
    assert many.score == one.score


def test_repeated_flags_do_not_stack():
    one = decide(SessionState(session_id="s", caller=caller(), flags=[flag("other", 0.8)]))
    many = decide(
        SessionState(
            session_id="s",
            caller=caller(),
            flags=[flag("other", 0.1), flag("other", 0.8), flag("other", 0.3)],
        )
    )
    assert many.score == one.score


# ---- Interface promises ----


def test_decide_is_deterministic():
    state = SessionState(
        session_id="s",
        caller=caller(),
        signals=[otp(), Signal(kind="anomaly", t=1, weight=0.2)],
        flags=[flag()],
    )
    assert decide(state) == decide(state.model_copy(deep=True))


def test_decide_is_fast():
    state = SessionState(
        session_id="s",
        caller=caller(),
        signals=[otp(t=float(i)) for i in range(200)],
        flags=[flag(t=float(i)) for i in range(200)],
    )
    started = time.perf_counter()
    decide(state)
    assert (time.perf_counter() - started) * 1000 < 100
