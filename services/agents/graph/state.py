"""Graph state: the shared SessionState plus fields only the graph sees.

`event`, `transcript_window` and `transcript_full` hold transcript text. They live in the in-memory checkpointer
only and are never streamed or persisted (R8). `public_state()` is the only view that leaves the graph.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from contracts.events import Event, Turn
from contracts.state import SessionState

WINDOW_TURNS = 8  # turns kept for Call Guardian


class GraphState(SessionState):
    event: Event | None = None  # the event being processed in this invocation
    transcript_window: list[Turn] = Field(default_factory=list)  # last WINDOW_TURNS turns, memory only (R8)
    # Every turn of the call, memory only (R8). The after-call planner reads it to judge whether the customer
    # handed over details; it is erased as soon as the after-call work ends (or at call_end if none runs).
    transcript_full: list[Turn] = Field(default_factory=list)
    turns_seen: int = 0
    guardian_checked_t: float = -1.0  # turns up to this t have been checked
    guardian_ok_t: float = -1.0  # turns up to this t were judged by a successful Nemotron check
    after_iterations: int = 0  # router visits in the after phase (hard cap in nodes/after.py)
    cancel_request: str = ""  # Recovery's message to the bank, carried into the evidence packet


PUBLIC_FIELDS = frozenset(SessionState.model_fields)


def public_update(update: dict[str, Any]) -> dict[str, Any]:
    """Drop graph-only fields from a node's update before it leaves the graph."""
    return {k: v for k, v in update.items() if k in PUBLIC_FIELDS}


def public_state(values: dict[str, Any]) -> SessionState:
    return SessionState.model_validate(public_update(values))
