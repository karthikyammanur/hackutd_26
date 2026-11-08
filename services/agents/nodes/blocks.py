"""User-message blocks for the Alert and aftercare prompts. Data only, always in the user message (R12).

Built from state (flags with their short quotes, signals, risk, plan). The alert, callback, recovery and evidence
prompts see signals, not conversations. Only the after-call planner also gets the full transcript (after.py),
to judge whether the customer handed anything over; it is erased from memory when the after-call work ends.
"""

from __future__ import annotations

from collections.abc import Iterable

from contracts.state import Level, SessionState
from services.agents import llm

_CALLER_SIGNALS = ("unknown_caller", "unverified_caller", "verified_caller")


def context_line(state: SessionState, ended_at: float | None = None) -> str:
    c = state.caller
    if c is None:
        return "direction: unknown"
    parts = [
        f"direction: {c.direction}"
        + (" (the customer dialed this number)" if c.direction == "outbound" else "")
    ]
    parts.append(
        f"verified organization: {c.verified_org}"
        if c.verified_org
        else "number not on the verified-organization list"
    )
    parts.append("first time seen" if c.first_seen else "seen before")
    if ended_at is not None:
        parts.append(f"call ended at t={ended_at:.0f}")
    return ", ".join(parts)


def flags_lines(state: SessionState, quotes: bool = True) -> str:
    if not state.flags:
        return "none"
    if not quotes:
        best: dict[str, float] = {}
        for f in state.flags:
            best[f.kind] = max(best.get(f.kind, 0.0), f.confidence)
        return ", ".join(f"{k} ({c:.2f})" for k, c in best.items())
    return "\n".join(f'{f.kind} ({f.confidence:.2f}) at t={f.t:.0f}: "{f.quote}"' for f in state.flags)


def signals_line(state: SessionState) -> str:
    out = [s.kind for s in state.signals if s.kind in _CALLER_SIGNALS and s.weight > 0]
    out += [
        f"{s.kind} at t={s.t:.0f}" + (f" ({s.detail})" if s.detail else "")
        for s in state.signals
        if s.kind not in _CALLER_SIGNALS
    ]
    return ", ".join(out) or "none"


def top_level(state: SessionState) -> Level:
    return max((a.level for a in state.alerts), default=Level.none)


def blocks(*pairs: tuple[str, str], tail: Iterable[str] = ()) -> str:
    """data_block() each (label, text) pair, then plain `key: value` lines (no free text in those)."""
    return "\n".join([llm.data_block(label, text) for label, text in pairs] + list(tail))
