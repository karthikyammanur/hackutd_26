"""During-call nodes. Each returns only NEW items for list fields (they merge through operator.add)."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from contracts.events import CallStart, Turn, UserChoice
from contracts.state import Alert, CallerInfo, Level, TraceItem, merge_risk
from services.agents.graph import stubs
from services.agents.graph.deps import Tools
from services.agents.graph.state import WINDOW_TURNS, GraphState

log = logging.getLogger(__name__)

Update = dict[str, Any]


class Node(Protocol):
    def __call__(self, state: GraphState) -> Update: ...


def trace(state: GraphState, node: str, action: str, result: str = "") -> list[TraceItem]:
    return [TraceItem(t=state.event.t if state.event else 0.0, node=node, action=action, result=result)]


def emergency(state: GraphState) -> Update:
    """R1: record who the call is with so later events skip the guard, and do nothing else."""
    e = state.event
    assert isinstance(e, CallStart)
    return {
        "caller": CallerInfo(number=e.number, direction=e.direction),
        "trace": trace(state, "emergency", "guard off for emergency number", "no action (R1)"),
    }


def make_caller_screen(tools: Tools) -> Node:
    def caller_screen(state: GraphState) -> Update:
        e = state.event
        assert isinstance(e, CallStart)
        caller, prior, signals = stubs.caller_screen(e, tools.store)
        return {
            "caller": caller,
            "prior_risk": prior,
            "signals": signals,
            "trace": trace(state, "caller_screen", "screen caller", ", ".join(x.kind for x in signals)),
        }

    return caller_screen


def signal_watcher(state: GraphState) -> Update:
    assert state.event is not None
    signals = stubs.signal_watcher(state.event, state)
    if not signals:
        return {}
    return {
        "signals": signals,
        "trace": trace(state, "signal_watcher", state.event.kind, ", ".join(x.kind for x in signals)),
    }


def ingest_turn(state: GraphState) -> tuple[Update, bool]:
    """Add the turn to the in-memory window. Check on every caller turn and every 3rd turn."""
    e = state.event
    assert isinstance(e, Turn)
    seen = state.turns_seen + 1
    update: Update = {
        "transcript_window": (state.transcript_window + [e])[-WINDOW_TURNS:],
        "turns_seen": seen,
    }
    check = e.speaker == "caller" or seen % 3 == 0
    if check:
        update["guardian_checked_t"] = e.t
    return update, check


def keyword_guardian(state: GraphState) -> Update:
    """Offline stand-in for the Nemotron Guardian (nodes/guardian.py). Used by tests and --offline replay."""
    update, check = ingest_turn(state)
    if check:
        flags = stubs.guardian_check(update["transcript_window"], since_t=state.guardian_checked_t)
        if flags:
            update["flags"] = flags
            update["trace"] = trace(state, "guardian", "check window", ", ".join(f.kind for f in flags))
    return update


def make_decide(tools: Tools) -> Node:
    def decide(state: GraphState) -> Update:
        try:
            new = tools.decider(state)
        except Exception:
            log.exception("decider failed")
            return {
                "guard_paused": True,
                "trace": trace(state, "decide", "decider failed", "guard paused (R4)"),
            }
        merged = merge_risk(state.risk, new)  # R5: never goes down
        update: Update = {"risk": merged}
        if state.risk is None or (merged.score, merged.level) != (state.risk.score, state.risk.level):
            update["trace"] = trace(state, "decide", "score", f"{merged.score:.2f} {merged.level.name}")
        return update

    return decide


CUSTOMER = "customer"  # logical recipient; lane 4's adapter maps it to the real number
BUTTONS: list[Any] = ["call_bank", "ask_trusted_contact", "continue"]


def make_alert(tools: Tools) -> Node:
    """New Alert only when the level goes up. There is no hang-up tool here, by design (R2).

    nudge: state only (UI shows it). whisper: Voice.whisper. alert: Comms.notify with the 3 buttons.
    A failed tool call is traced and the alert stays in state; the call itself is never touched (R4).
    """

    def alert(state: GraphState) -> Update:
        r = state.risk
        prev = max((a.level for a in state.alerts), default=Level.none)
        if r is None or r.level <= prev or r.level < Level.nudge:
            return {}
        reason = stubs.alert_reason(r)  # template until AlertCopy (step 4 LLM part) lands
        buttons = list(BUTTONS) if r.level >= Level.alert else []
        sid = state.session_id
        try:
            if r.level >= Level.alert:
                action, result = "comms.notify", tools.comms.notify(sid, CUSTOMER, reason, buttons)
            elif r.level == Level.whisper:
                action, result = "voice.whisper", tools.voice.whisper(sid, reason)
            else:
                action, result = "show nudge", ""
        except Exception as exc:
            log.warning("alert delivery failed: %s", type(exc).__name__)
            action, result = "delivery failed", type(exc).__name__
        return {
            "alerts": [
                Alert(t=state.event.t if state.event else 0.0, level=r.level, reason=reason, buttons=buttons)
            ],
            "trace": trace(state, "alert", f"{r.level.name}: {action}", f"{reason} {result}".strip()),
        }

    return alert


def record_choice(state: GraphState) -> Update:
    e = state.event
    assert isinstance(e, UserChoice)
    return {"user_choice": e.choice, "trace": trace(state, "user_choice", "customer chose", e.choice)}


def end_call(state: GraphState) -> Update:
    return {"ended": True, "trace": trace(state, "call_end", "call ended")}
