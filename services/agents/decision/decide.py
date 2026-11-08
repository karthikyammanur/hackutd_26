"""decide(state) -> Risk. Deterministic, no LLM, no network, well under 100 ms.

The score is a noisy-OR, so evidence can only ever add risk:

    deterministic = OR(caller screen, signal watcher)
    score         = OR(deterministic, Call Guardian flags)      -> flags can't lower the score (R6)

Hard rules, in the order they apply:
    R1  emergency number               -> zero risk, always
    R4  guard paused or internal error -> previous risk, unchanged
    R7  customer dialed a verified org -> score capped below whisper, unless a confident hard flag appears
    R5  every result goes through merge_risk, so risk only rises during a call
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Sequence

from contracts.events import EMERGENCY_NUMBERS, Direction
from contracts.state import CallerInfo, Flag, FlagKind, Level, Risk, SessionState, Signal, merge_risk
from services.agents.decision import config

log = logging.getLogger(__name__)

EMERGENCY_REASON = "Emergency call: Safe Signal stays out of the way"
_CALLER_SCREEN_KINDS = frozenset(
    {"unknown_caller", "unverified_caller", "verified_caller", "scam_list_hit", "anomaly"}
)


# Service codes a customer can dial in front of a number, e.g. *67 (hide caller ID) or #31#.
_DIAL_PREFIX = re.compile(r"^\s*(?:tel:)?(?:\s*(?:\*\d{2}|#\d{2}#))*")


def _digits(number: str) -> str:
    return re.sub(r"\D", "", number)


def normalize_number(number: str) -> str:
    """Canonical national form, so '+1 (214) 555-0147', '12145550147' and '2145550147' compare equal."""
    digits = _digits(number)
    return digits[1:] if len(digits) == 11 and digits.startswith("1") else digits


def is_emergency(number: str) -> bool:
    digits = _digits(_DIAL_PREFIX.sub("", number, count=1))
    return digits in EMERGENCY_NUMBERS or (digits.startswith("1") and digits[1:] in EMERGENCY_NUMBERS)


def noisy_or(weights: Iterable[float]) -> float:
    """Probability at least one independent cause fires. Adding a weight can never lower the result."""
    miss = 1.0
    for w in weights:
        miss *= 1.0 - min(max(w, 0.0), 1.0)
    return 1.0 - miss


def level_for(score: float) -> Level:
    if score >= config.ALERT:
        return Level.alert
    if score >= config.WHISPER:
        return Level.whisper
    if score >= config.NUDGE:
        return Level.nudge
    return Level.none


def has_verified_org(caller: CallerInfo) -> bool:
    """A blank org from a bad lookup is not a verification."""
    return bool(caller.verified_org and caller.verified_org.strip())


def is_trusted_call(caller: CallerInfo) -> bool:
    """R7: the customer dialed a number on the verified list. Caller ID alone is never enough."""
    return caller.direction == Direction.outbound and has_verified_org(caller)


def _strongest_signals(signals: Sequence[Signal]) -> dict[str, Signal]:
    """One entry per kind, so repeated events of the same kind can't stack up to an alert."""
    best: dict[str, Signal] = {}
    for s in signals:
        if s.kind not in best or s.weight > best[s.kind].weight:
            best[s.kind] = s
    return best


def _strongest_flags(flags: Sequence[Flag]) -> dict[FlagKind, Flag]:
    best: dict[FlagKind, Flag] = {}
    for f in flags:
        if f.kind not in best or f.confidence > best[f.kind].confidence:
            best[f.kind] = f
    return best


def deterministic_score(state: SessionState) -> tuple[float, list[str]]:
    """Score from Caller Screen and Signal Watcher only: the floor no LLM output can go below (R6)."""
    best = _strongest_signals(state.signals)
    screen = noisy_or(s.weight for k, s in best.items() if k in _CALLER_SCREEN_KINDS)
    prior = max(screen, state.prior_risk.score if state.prior_risk else 0.0)
    watcher = [s.weight for k, s in best.items() if k not in _CALLER_SCREEN_KINDS]
    reasons = [
        config.SIGNAL_REASONS[k]
        for k, s in sorted(best.items())
        if s.weight > 0 and k in config.SIGNAL_REASONS
    ]
    return noisy_or([prior, *watcher]), reasons


def flag_score(flags: Sequence[Flag]) -> tuple[float, list[str]]:
    best = _strongest_flags(flags)
    score = noisy_or(config.FLAG_WEIGHTS[k] * f.confidence for k, f in best.items())
    return score, [config.FLAG_REASONS[k] for k, f in sorted(best.items()) if f.confidence > 0]


def _cap_lifted(flags: Sequence[Flag]) -> bool:
    return any(f.kind in config.UNCAP_FLAGS and f.confidence >= config.UNCAP_MIN_CONFIDENCE for f in flags)


def trusted_cap_applies(state: SessionState) -> bool:
    return state.caller is not None and is_trusted_call(state.caller) and not _cap_lifted(state.flags)


def rule_risk(state: SessionState) -> Risk:
    """This turn's risk from the rules, before merging with the call's previous risk."""
    det, det_reasons = deterministic_score(state)
    llm, llm_reasons = flag_score(state.flags)
    score = noisy_or([det, llm])
    if trusted_cap_applies(state):
        score = min(score, config.TRUSTED_CAP)
    return Risk(score=score, level=level_for(score), reasons=det_reasons + llm_reasons)


def decide(state: SessionState) -> Risk:
    """Implements contracts.interfaces.Decider. Never raises: a failure leaves the call untouched (R4)."""
    previous = state.risk if state.risk is not None else Risk(score=0.0)
    try:
        if state.caller is None:  # Caller Screen hasn't run, so we can't rule out an emergency call
            return previous
        if is_emergency(state.caller.number):
            return Risk(score=0.0, level=Level.none, reasons=[EMERGENCY_REASON])
        if state.guard_paused:
            return previous
        return merge_risk(state.risk, rule_risk(state))
    except Exception:
        log.exception("decide failed for session %s; leaving risk unchanged (R4)", state.session_id)
        return previous
