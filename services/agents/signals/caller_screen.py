"""Caller Screen: scores a number before it rings (scam list + anomaly features).

Calls the carrier already labeled, and emergency calls, are out of scope and get no agent at all.
"""

from __future__ import annotations

import json
from collections.abc import Collection
from dataclasses import dataclass, field
from pathlib import Path

from contracts.events import CallStart, Direction
from contracts.state import CallerInfo, Risk, Signal
from services.agents.decision import config
from services.agents.decision.decide import is_emergency, level_for, noisy_or, normalize_number

SCAM_LIST_PATH = Path(__file__).resolve().parents[3] / "data" / "scam_list.json"


def load_scam_numbers(path: Path = SCAM_LIST_PATH) -> frozenset[str]:
    """Normalized numbers from the scam list file, ready to pass to screen_call."""
    numbers = json.loads(path.read_text(encoding="utf-8"))["numbers"]
    return frozenset(normalize_number(n) for n in numbers)


@dataclass(frozen=True)
class ScreenResult:
    in_scope: bool
    caller: CallerInfo
    signals: list[Signal] = field(default_factory=list)
    prior_risk: Risk = field(default_factory=lambda: Risk(score=0.0))


def _identity_signals(start: CallStart) -> tuple[list[Signal], bool]:
    """Returns the identity signals and whether the verified-org claim can be believed."""
    org = (start.verified_org or "").strip() or None
    t = start.t
    if org is not None and (start.direction == Direction.outbound or start.attestation == "A"):
        return [Signal(kind="verified_caller", t=t, weight=0.0, detail=org)], True
    if (
        org is not None
    ):  # caller ID shows a verified number but the network won't vouch for it: likely spoofed
        detail = f"shows {org}'s number, attestation {start.attestation}"
        return [
            Signal(kind="unverified_caller", t=t, weight=config.WEIGHT_SPOOF_SUSPECT, detail=detail)
        ], False
    if start.first_seen:
        return [
            Signal(kind="unknown_caller", t=t, weight=config.WEIGHT_UNKNOWN_CALLER, detail="first seen")
        ], False
    return [
        Signal(kind="unverified_caller", t=t, weight=config.WEIGHT_UNVERIFIED_CALLER, detail="not on list")
    ], False


def _anomaly_signal(start: CallStart, burst_count: int) -> Signal | None:
    """Attestation only says something about who's calling, so it counts on inbound calls only."""
    parts: list[tuple[float, str]] = []
    if start.direction == Direction.inbound and config.ATTESTATION_ANOMALY[start.attestation] > 0:
        parts.append((config.ATTESTATION_ANOMALY[start.attestation], f"attestation {start.attestation}"))
    if burst_count >= config.BURST_THRESHOLD:
        parts.append((config.WEIGHT_BURST_ANOMALY, f"{burst_count} subscribers called in the last hour"))
    if not parts:
        return None
    return Signal(
        kind="anomaly", t=start.t, weight=noisy_or(w for w, _ in parts), detail="; ".join(d for _, d in parts)
    )


def screen_call(
    start: CallStart, scam_numbers: Collection[str] = frozenset(), burst_count: int = 0
) -> ScreenResult:
    """scam_numbers should be normalized digit strings; burst_count comes from network stats."""
    caller = CallerInfo(
        number=start.number,
        direction=start.direction,
        verified_org=start.verified_org,
        first_seen=start.first_seen,
        attestation=start.attestation,
    )
    if start.carrier_label != "none" or is_emergency(start.number):
        return ScreenResult(in_scope=False, caller=caller)

    signals, believed = _identity_signals(start)
    if not believed:  # nothing downstream (Watcher, R7) may trust an unbelieved claim
        caller = caller.model_copy(update={"verified_org": None})
    if normalize_number(start.number) in scam_numbers:
        signals.append(Signal(kind="scam_list_hit", t=start.t, weight=config.WEIGHT_SCAM_LIST_HIT))
    if anomaly := _anomaly_signal(start, burst_count):
        signals.append(anomaly)

    score = noisy_or(s.weight for s in signals)
    reasons = [
        config.SIGNAL_REASONS[s.kind] for s in signals if s.weight > 0 and s.kind in config.SIGNAL_REASONS
    ]
    return ScreenResult(
        in_scope=True,
        caller=caller,
        signals=signals,
        prior_risk=Risk(score=score, level=level_for(score), reasons=reasons),
    )
