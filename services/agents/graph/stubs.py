"""Deterministic stand-ins until lane 2 (signals/, decision/) and lane 4 (tools/) land.

Same signatures the real code will have, so each swap is one line. No LLM in here.
All numbers and names are synthetic (R10).
"""

from __future__ import annotations

import re

from contracts.events import EMERGENCY_NUMBERS, CallStart, Event, Turn
from contracts.interfaces import Comms, Decider, Store, Voice
from contracts.state import CallerInfo, Flag, FlagKind, Level, Risk, SessionState, Signal
from services.agents.graph.deps import Tools

# Synthetic verified list: number -> org (the real one lives in Store / Tiger Data).
VERIFIED_NUMBERS: dict[str, str] = {"+18005550199": "Lone Star Bank"}
ORG_NUMBERS: dict[str, str] = {org: num for num, org in VERIFIED_NUMBERS.items()}


def is_emergency(number: str) -> bool:
    return re.sub(r"\D", "", number) in EMERGENCY_NUMBERS


def verified_number_for(org: str) -> str | None:
    """org -> official number. Not in the Store protocol yet (contract gap, see PR notes)."""
    return ORG_NUMBERS.get(org)


# ---- scoring -----------------------------------------------------------------------------------------------

LEVEL_AT = ((0.75, Level.alert), (0.5, Level.whisper), (0.2, Level.nudge))


def level_for(score: float) -> Level:
    return next((lv for cut, lv in LEVEL_AT if score >= cut), Level.none)


SIGNAL_REASON: dict[str, str] = {
    "unknown_caller": "an unknown number is on the call",
    "unverified_caller": "the number is not on our verified list",
    "otp_during_call": "a bank code arrived during this call",
    "bank_app_during_call": "your bank app was opened during this call",
    "account_change_during_call": "someone tried to change your phone account during this call",
    "scam_list_hit": "this number is on a scam list",
    "anomaly": "this call looks unusual",
}
FLAG_REASON: dict[str, str] = {
    "read_code": "the caller asked you to read back a code",
    "safe_account": "the caller asked you to move money to a 'safe' account",
    "gift_cards": "the caller asked for gift cards",
    "remote_access": "the caller asked for remote access to a device",
    "urgency_secrecy": "the caller is rushing you or asking you to keep quiet",
    "policy_contradiction": "the caller said something the real company never does",
    "other": "the caller asked for something unusual",
}
FLAG_WEIGHT: dict[str, float] = {
    "read_code": 0.4,
    "safe_account": 0.4,
    "gift_cards": 0.4,
    "remote_access": 0.4,
    "policy_contradiction": 0.3,
    "urgency_secrecy": 0.15,
    "other": 0.05,
}
FLAG_MIN_CONFIDENCE = 0.5


def decide(state: SessionState) -> Risk:
    """Stand-in for lane 2's decide(). Signals give the deterministic score; flags can only add to it (R6)."""
    deterministic = min(1.0, sum(s.weight for s in state.signals))
    best: dict[str, float] = {}
    for f in state.flags:
        best[f.kind] = max(best.get(f.kind, 0.0), f.confidence)
    bonus = sum(FLAG_WEIGHT[k] * c for k, c in best.items())
    score = min(1.0, deterministic + bonus)
    assert score >= deterministic  # R6
    reasons = [SIGNAL_REASON[s.kind] for s in state.signals if s.weight > 0]
    reasons += [FLAG_REASON[f.kind] for f in state.flags if f.confidence >= FLAG_MIN_CONFIDENCE]
    return Risk(score=score, level=level_for(score), reasons=list(dict.fromkeys(reasons)))


def caller_screen(event: CallStart, store: Store) -> tuple[CallerInfo, Risk, list[Signal]]:
    """Stand-in for lane 2's Caller Screen."""
    verified = event.verified_org or store.lookup_verified(event.number)
    caller = CallerInfo(
        number=event.number,
        direction=event.direction,
        verified_org=verified,
        first_seen=event.first_seen,
        attestation=event.attestation,
    )
    if event.carrier_label == "scam_likely":
        sig = Signal(kind="scam_list_hit", t=event.t, weight=0.5)
    elif verified:
        sig = Signal(kind="verified_caller", t=event.t, weight=0.0, detail=verified)
    elif event.first_seen:
        sig = Signal(kind="unknown_caller", t=event.t, weight=0.15)
    else:
        sig = Signal(kind="unverified_caller", t=event.t, weight=0.1)
    reasons = [SIGNAL_REASON[sig.kind]] if sig.weight > 0 else []
    prior = Risk(score=sig.weight, level=level_for(sig.weight), reasons=reasons)
    return caller, prior, [sig]


def _safe_context(state: SessionState) -> bool:
    """Customer dialed a verified number (R7)."""
    c = state.caller
    return bool(c and c.verified_org and c.direction == "outbound")


def signal_watcher(event: Event, state: SessionState) -> list[Signal]:
    """Stand-in for lane 2's Signal Watcher."""
    if _safe_context(state):
        return []
    if event.kind == "sms_otp" and event.sender_type == "bank_shortcode":
        return [Signal(kind="otp_during_call", t=event.t, weight=0.35, detail=event.org or "")]
    if event.kind == "bank_app_traffic":
        return [Signal(kind="bank_app_during_call", t=event.t, weight=0.2, detail=event.org or "")]
    if event.kind == "account_change" and event.status == "attempted":
        return [Signal(kind="account_change_during_call", t=event.t, weight=0.4, detail=event.action)]
    return []


# ---- Call Guardian stand-in (step 3 replaces this with Nemotron) --------------------------------------------

_RULES: list[tuple[FlagKind, re.Pattern[str]]] = [
    ("read_code", re.compile(r"\bread\b.*\b(code|number|digits)\b|\b(code|number|digits)\b.*\bread\b")),
    ("safe_account", re.compile(r"safe account|protected account|move your (money|balance)")),
    ("gift_cards", re.compile(r"gift card")),
    ("remote_access", re.compile(r"anydesk|teamviewer|remote access|share your screen")),
    ("urgency_secrecy", re.compile(r"(don't|do not) (hang up|call|tell)|keep this between")),
    ("policy_contradiction", re.compile(r"refund.*gift card|gift card.*refund")),
]


def guardian_check(window: list[Turn], since_t: float) -> list[Flag]:
    """Keyword flags for caller turns newer than since_t."""
    out: list[Flag] = []
    for turn in window:
        if turn.t <= since_t or turn.speaker != "caller":
            continue
        text = turn.text.lower()
        for kind, pat in _RULES:
            if pat.search(text):
                out.append(Flag(kind=kind, quote=turn.text[:120], t=turn.t, confidence=0.8))
    return out


def alert_reason(risk: Risk) -> str:
    """Template wording (step 4 adds Nemotron with this as the fallback)."""
    latest = risk.reasons[-1] if risk.reasons else "this call looks unusual"
    if risk.level >= Level.alert:
        return f"This may be a scam: {latest}."
    if risk.level == Level.whisper:
        return f"Be careful: {latest}."
    return f"Heads up: {latest}."


# ---- fakes for lane 4's tools (same shape as contracts/interfaces.py) ---------------------------------------


class FakeComms:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def _log(self, *entry: str) -> str:
        self.calls.append(entry)
        return f"fake-{entry[0]}-{len(self.calls)}"

    def notify(self, session_id: str, to: str, text: str, buttons: list[str]) -> str:
        return self._log("notify", to, text, ",".join(buttons))

    def call(self, session_id: str, to: str, script: str) -> str:
        return self._log("call", to, script)

    def transfer(self, session_id: str, call_id: str, to_number: str) -> str:
        return self._log("transfer", call_id, to_number)

    def message(self, session_id: str, to: str, text: str) -> str:
        return self._log("message", to, text)


class FakeVoice:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def whisper(self, session_id: str, text: str) -> str:
        self.calls.append(("whisper", text))
        return f"fake-whisper-{len(self.calls)}"


class FakeStore:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.evidence: dict[str, dict] = {}

    def append_event(self, session_id: str, event: dict) -> None:
        if event.get("kind") != "turn":  # R8
            self.events.append(event)

    def save_evidence(self, session_id: str, packet: dict) -> str:
        eid = f"ev-{session_id}"
        self.evidence[eid] = packet
        return eid

    def lookup_verified(self, number: str) -> str | None:
        return VERIFIED_NUMBERS.get(number)

    def search_policy(self, query: str, k: int = 3) -> list[str]:
        return []


# pyright checks these against the protocols, so a drifted fake fails the type check.
_decider: Decider = decide
_comms: Comms = FakeComms()
_voice: Voice = FakeVoice()
_store: Store = FakeStore()


def fake_tools() -> Tools:
    return Tools(decider=decide, comms=FakeComms(), voice=FakeVoice(), store=FakeStore())
