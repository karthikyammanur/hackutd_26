"""Shared session state for the LangGraph graph and the web UI.

Each field has one owner (see context/architecture.md). List fields are append-only and use
`operator.add` so parallel LangGraph nodes merge safely.
"""

from __future__ import annotations

import operator
from enum import IntEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from contracts.events import Direction, Event


class Level(IntEnum):
    """Alert ladder. Ordered, so levels compare with < and max()."""

    none = 0
    nudge = 1
    whisper = 2
    alert = 3  # notification + 3 buttons + account changes held. Never a hang-up (R2).


class Risk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: float = Field(ge=0, le=1)
    level: Level = Level.none
    reasons: list[str] = Field(default_factory=list)


def merge_risk(old: Risk | None, new: Risk) -> Risk:
    """Risk only goes up during a call (R5). Reasons accumulate."""
    if old is None:
        return new
    reasons = old.reasons + [r for r in new.reasons if r not in old.reasons]
    return Risk(score=max(old.score, new.score), level=max(old.level, new.level), reasons=reasons)


FlagKind = Literal[
    "gift_cards",
    "read_code",
    "safe_account",
    "remote_access",
    "policy_contradiction",
    "urgency_secrecy",
    "other",
]


class Flag(BaseModel):
    """Produced by Call Guardian (Lane 1)."""

    model_config = ConfigDict(extra="forbid")
    kind: FlagKind
    quote: str = Field(max_length=200)  # short evidence quote, never the full transcript
    t: float
    confidence: float = Field(ge=0, le=1)


class Signal(BaseModel):
    """Produced by Caller Screen and Signal Watcher (Lane 2)."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal[
        "unknown_caller",
        "unverified_caller",
        "verified_caller",
        "otp_during_call",
        "bank_app_during_call",
        "account_change_during_call",
        "scam_list_hit",
        "anomaly",
    ]
    t: float
    weight: float = Field(ge=0, le=1)
    detail: str = ""


class Alert(BaseModel):
    model_config = ConfigDict(extra="forbid")
    t: float
    level: Level
    reason: str  # one plain sentence shown to the customer
    buttons: list[Literal["call_bank", "ask_trusted_contact", "continue"]] = Field(
        default_factory=lambda: ["call_bank", "ask_trusted_contact", "continue"]
    )


StepName = Literal["lock_account", "callback", "recovery", "evidence", "notify_trusted_contact"]


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: StepName
    status: Literal["pending", "running", "done", "failed", "skipped"] = "pending"
    detail: str = ""


class TraceItem(BaseModel):
    """What the Aftercare Planner and its tools did, rendered in the console."""

    model_config = ConfigDict(extra="forbid")
    t: float
    node: str
    action: str
    result: str = ""


class CallerInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    number: str
    direction: Direction
    verified_org: str | None = None
    first_seen: bool = True
    attestation: Literal["A", "B", "C", "none"] = "none"


class SessionState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str
    caller: CallerInfo | None = None  # Caller Screen
    prior_risk: Risk | None = None  # Caller Screen
    flags: Annotated[list[Flag], operator.add] = Field(default_factory=list)  # Call Guardian
    signals: Annotated[list[Signal], operator.add] = Field(default_factory=list)  # Signal Watcher
    risk: Risk | None = None  # Decision only, via merge_risk
    alerts: Annotated[list[Alert], operator.add] = Field(default_factory=list)  # Alert
    user_choice: str | None = None
    plan: list[PlanStep] = Field(default_factory=list)  # Aftercare Planner
    trace: Annotated[list[TraceItem], operator.add] = Field(default_factory=list)
    evidence_id: str | None = None  # Evidence
    guard_paused: bool = False  # R4: set when an agent fails; UI shows "guard paused"
    ended: bool = False


class UIMessage(BaseModel):
    """WebSocket message from the API to the web app."""

    model_config = ConfigDict(extra="forbid")
    type: Literal["event", "state", "trace"]
    session_id: str
    event: Event | None = None  # never a `turn` with full text after the call ends
    state: SessionState | None = None
    trace: TraceItem | None = None
