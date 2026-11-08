"""Call Guardian on Nemotron fast: flags caller asks that go against the customer's interest.

Transcript text goes only in the user message, inside data_block() (R12). Flags only add risk; decide() owns the
score (R6). Any failure: no flags, guard_paused=True, nothing done to the call (R4).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any

from contracts.events import Turn
from contracts.state import Flag, SessionState
from services.agents import llm
from services.agents.graph import stubs
from services.agents.graph.state import GraphState
from services.agents.nodes.during import Node, Update, ingest_turn, trace
from services.agents.prompts import GuardianOutput, load_prompt

log = logging.getLogger(__name__)

TIMEOUT_S = 3.0
KEYWORD_FALLBACK = False  # Lead decision: keyword flags while paused stay off unless switched on
MIN_OVERLAP = 0.6  # share of quote words that must appear in a turn when there is no exact match

Structured = Callable[..., Any]  # llm.structured, or a fake in tests


def call_context(state: SessionState) -> str:
    c = state.caller
    lines: list[str] = []
    if c:
        dialed = " (the customer dialed this number)" if c.direction == "outbound" else ""
        seen = "first time seen" if c.first_seen else "seen before"
        verified = (
            f"verified organization: {c.verified_org}"
            if c.verified_org
            else "not on the verified-organization list"
        )
        lines += [
            f"direction: {c.direction}{dialed}",
            f"number: {c.number} ({seen}, {verified})",
            f"attestation: {c.attestation}",
        ]
    sigs = [
        f"{s.kind} at t={s.t:.0f}" + (f" ({s.detail})" if s.detail else "")
        for s in state.signals
        if s.kind not in ("unknown_caller", "unverified_caller", "verified_caller")
    ]
    lines.append("recent signals: " + (", ".join(sigs) if sigs else "none"))
    return "\n".join(lines)


def transcript(state: GraphState) -> str:
    return "\n".join(f"[t={x.t:.0f}] {x.speaker}: {x.text}" for x in state.transcript_window)


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9']+", " ", text.lower()).split())


def match_turn(quote: str, state: GraphState) -> Turn | None:
    """The window turn the quote came from: exact (normalized) substring first, else best word overlap."""
    q = _norm(quote)
    if not q:
        return None
    for turn in reversed(state.transcript_window):
        if q in _norm(turn.text):
            return turn
    words = set(q.split())
    best: Turn | None = None
    best_score = 0.0
    for turn in reversed(state.transcript_window):
        score = len(words & set(_norm(turn.text).split())) / len(words)
        if score > best_score:
            best, best_score = turn, score
    return best if best_score >= MIN_OVERLAP else None


def to_flags(out: GuardianOutput, state: GraphState) -> tuple[list[Flag], int]:
    """Attach t from the matched turn; drop customer quotes, unmatched quotes, repeats, and hindsight flags.

    Hindsight: a turn already judged by an earlier successful check is not re-flagged because later turns make
    the call look worse (a real fraud alert opens with the same story). Turns from a failed check stay open.
    Returns (flags, dropped).
    """
    seen = {(f.kind, f.t) for f in state.flags}
    flags: list[Flag] = []
    dropped = 0
    for g in out.flags:
        turn = match_turn(g.quote, state)
        if (
            turn is None
            or turn.speaker != "caller"
            or turn.t <= state.guardian_ok_t
            or (g.kind, turn.t) in seen
        ):
            dropped += 1
            continue
        seen.add((g.kind, turn.t))
        flags.append(Flag(kind=g.kind, quote=g.quote, t=turn.t, confidence=g.confidence))
    return flags, dropped


def make_guardian(
    structured: Structured = llm.structured, *, keyword_fallback: bool = KEYWORD_FALLBACK
) -> Node:
    def guardian(state: GraphState) -> Update:
        update, check = ingest_turn(state)
        if not check:
            return update
        view = state.model_copy(update=update)  # window including this turn
        user = (
            llm.data_block("call_context", call_context(view))
            + "\n"
            + llm.data_block("transcript", transcript(view))
        )
        try:
            out = structured(
                load_prompt("guardian"), user, GuardianOutput, llm.NODE_TIER["guardian"], timeout=TIMEOUT_S
            )
        except Exception as exc:  # R4: the guard pauses, the call is untouched
            log.warning("guardian failed: %s", type(exc).__name__)
            update["guard_paused"] = True
            result = type(exc).__name__
            if keyword_fallback:
                kw = [
                    f
                    for f in stubs.guardian_check(view.transcript_window, since_t=state.guardian_checked_t)
                    if (f.kind, f.t) not in {(x.kind, x.t) for x in state.flags}
                ]
                if kw:
                    update["flags"] = kw
                    result += "; keyword fallback: " + ", ".join(f.kind for f in kw)
            update["trace"] = trace(state, "guardian", "guard paused", result)
            return update
        if state.guard_paused:
            update["guard_paused"] = False
        flags, dropped = to_flags(out, view)
        update["guardian_ok_t"] = view.transcript_window[-1].t
        if flags:
            update["flags"] = flags
            note = f" (dropped {dropped})" if dropped else ""
            update["trace"] = trace(
                state, "guardian", "nemotron check", ", ".join(f"{f.kind}@{f.t:.0f}" for f in flags) + note
            )
        return update

    return guardian
