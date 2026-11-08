"""Caller Screen and Signal Watcher behave, and emit Signal objects on every fixture (L2-3)."""

import json
from pathlib import Path
from typing import Literal

import pytest

from contracts.events import (
    AccountChange,
    BankAppTraffic,
    CallStart,
    Direction,
    EvalCase,
    SmsOtp,
    Source,
    Turn,
)
from contracts.state import CallerInfo, Signal
from services.agents.decision import config
from services.agents.decision.decide import normalize_number
from services.agents.signals.caller_screen import screen_call
from services.agents.signals.signal_watcher import watch_event

FIXTURES = Path(__file__).resolve().parents[4] / "evals" / "fixtures"
NUMBER = "+12145550147"


def start(**kw) -> CallStart:
    base = {
        "session_id": "s",
        "t": 0,
        "source": Source.network,
        "direction": Direction.inbound,
        "number": NUMBER,
        "first_seen": True,
    }
    return CallStart(**{**base, **kw})


def kinds(signals: list[Signal]) -> set[str]:
    return {s.kind for s in signals}


UNKNOWN = CallerInfo(number=NUMBER, direction=Direction.inbound)
VERIFIED = CallerInfo(number="+18005550199", direction=Direction.outbound, verified_org="Lone Star Bank")


# ---- Caller Screen ----


def test_first_seen_number_is_unknown():
    result = screen_call(start())
    assert result.in_scope and "unknown_caller" in kinds(result.signals)


def test_known_unlisted_number_is_unverified():
    assert "unverified_caller" in kinds(screen_call(start(first_seen=False)).signals)


def test_customer_dialed_verified_number_is_verified():
    result = screen_call(start(direction=Direction.outbound, verified_org="Lone Star Bank", attestation="C"))
    assert "verified_caller" in kinds(result.signals)
    assert result.caller.verified_org == "Lone Star Bank"
    assert result.prior_risk.score == 0.0


def test_inbound_verified_number_with_full_attestation_is_verified():
    result = screen_call(start(verified_org="Lone Star Bank", attestation="A"))
    assert "verified_caller" in kinds(result.signals)


@pytest.mark.parametrize("attestation", ["B", "C", "none"])
def test_inbound_verified_number_without_full_attestation_is_not_believed(attestation):
    result = screen_call(start(verified_org="Lone Star Bank", attestation=attestation))
    assert "verified_caller" not in kinds(result.signals)
    assert result.caller.verified_org is None


def test_scam_list_hit_matches_any_number_format():
    result = screen_call(start(number="+1 (214) 555-0147"), scam_numbers={normalize_number(NUMBER)})
    assert "scam_list_hit" in kinds(result.signals)
    assert result.prior_risk.score >= config.WEIGHT_SCAM_LIST_HIT


@pytest.mark.parametrize(
    ("attestation", "expected"), [("A", False), ("B", True), ("C", True), ("none", True)]
)
def test_attestation_anomaly(attestation, expected):
    assert ("anomaly" in kinds(screen_call(start(attestation=attestation)).signals)) is expected


def test_attestation_is_ignored_when_the_customer_dialed():
    assert "anomaly" not in kinds(
        screen_call(start(direction=Direction.outbound, attestation="none")).signals
    )


def test_call_burst_is_an_anomaly():
    below = screen_call(start(attestation="A"), burst_count=config.BURST_THRESHOLD - 1)
    above = screen_call(start(attestation="A"), burst_count=config.BURST_THRESHOLD)
    assert "anomaly" not in kinds(below.signals)
    assert "anomaly" in kinds(above.signals)


@pytest.mark.parametrize("label", ["scam_likely", "spam"])
def test_carrier_labeled_calls_get_no_agent(label):
    result = screen_call(start(carrier_label=label))
    assert not result.in_scope and result.signals == []


def test_emergency_numbers_get_no_agent():
    result = screen_call(start(number="911"))
    assert not result.in_scope and result.signals == []


# ---- Signal Watcher (Trigger A) ----


def otp(sender: Literal["bank_shortcode", "other_shortcode", "longcode"] = "bank_shortcode") -> SmsOtp:
    return SmsOtp(session_id="s", t=10, source=Source.network, sender_type=sender, org="Lone Star Bank")


def test_trigger_a_fires_on_bank_code_with_unknown_caller():
    signals = watch_event(otp(), UNKNOWN)
    assert kinds(signals) == {"otp_during_call"}
    assert signals[0].weight == config.OTP_WEIGHT["bank_shortcode"]


def test_trigger_a_fires_on_bank_app_traffic_with_unknown_caller():
    event = BankAppTraffic(session_id="s", t=10, source=Source.network)
    assert kinds(watch_event(event, UNKNOWN)) == {"bank_app_during_call"}


def test_trigger_a_is_silent_on_verified_call():
    assert watch_event(otp(), VERIFIED) == []
    assert watch_event(BankAppTraffic(session_id="s", t=10, source=Source.network), VERIFIED) == []


def test_bank_code_outranks_a_longcode_text():
    assert watch_event(otp(), UNKNOWN)[0].weight > watch_event(otp("longcode"), UNKNOWN)[0].weight


def change(status) -> AccountChange:
    return AccountChange(session_id="s", t=10, source=Source.network, action="sim_change", status=status)


@pytest.mark.parametrize("status", ["attempted", "completed"])
def test_account_change_emits_signal(status):
    assert kinds(watch_event(change(status), UNKNOWN)) == {"account_change_during_call"}


def test_our_own_hold_is_not_evidence():
    assert watch_event(change("held"), UNKNOWN) == []


def test_turns_produce_no_signals():
    turn = Turn(session_id="s", t=3, source=Source.network, speaker="caller", text="read me the code")
    assert watch_event(turn, UNKNOWN) == []


# ---- Every fixture ----


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.json")), ids=lambda p: p.stem)
def test_every_fixture_emits_signals(path):
    case = EvalCase.model_validate(json.loads(path.read_text()))
    first = case.events[0]
    assert isinstance(first, CallStart)
    result = screen_call(first)
    signals = list(result.signals)
    for event in case.events[1:]:
        signals += watch_event(event, result.caller)
    assert signals and all(isinstance(s, Signal) for s in signals)
