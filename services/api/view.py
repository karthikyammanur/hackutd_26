"""What the hosted console sees of a live call: markers only.

The console is a public site, so this never carries turn text, flag quotes, phone numbers, tool details or the
planner's reasoning (R8). Just kinds, times, levels, the alert sentence the customer was shown, and step statuses.
"""

from __future__ import annotations

import re
from typing import Any

from contracts.state import Level, SessionState

_SCORE = re.compile(r"^(\d+(?:\.\d+)?) (none|nudge|whisper|alert)$")
_GAVE = re.compile(r"customer handed over details: (yes|no)")
STEPS = ("lock_account", "callback", "recovery", "evidence", "notify_trusted_contact")
FINISHED = ("all steps finished", "iteration cap reached")  # the router erases the transcript on both


def session_view(
    state: SessionState, *, t: float, answered_t: float | None, call_running: bool
) -> dict[str, Any]:
    status = {p.name: p.status for p in state.plan}
    worst = max((a.level for a in state.alerts), default=Level.none)
    timeline: list[dict[str, Any]] = []
    disclosed: bool | None = None
    erased = state.ended and worst < Level.whisper  # end_call erases it when no after-call work runs
    for x in state.trace:
        item: dict[str, Any] = {"t": x.t, "node": x.node}
        if x.node == "decide":
            m = _SCORE.match(x.result)
            if not m:
                continue
            item |= {"score": float(m[1]), "level": int(Level[m[2]])}
        elif x.node == "planner":
            m = _GAVE.search(x.result)
            disclosed = m[1] == "yes" if m else None
            item |= {"disclosed": disclosed, "steps": list(status)}
        elif x.node in STEPS:
            item["status"] = status.get(x.node, "pending")
        elif x.node == "router" and x.action in FINISHED:
            erased = True
            item["erased"] = True
        elif x.node == "user_choice":
            item["choice"] = state.user_choice
        elif x.node != "call_end":
            continue  # flags, signals and alerts come from their own lists below
        timeline.append(item)
    return {
        "session_id": state.session_id,
        "t": t,
        "answered_t": answered_t,
        "call_running": call_running,
        "ended": state.ended,
        "erased": erased,
        "guard_paused": state.guard_paused,
        "risk": {"score": state.risk.score, "level": int(state.risk.level)} if state.risk else None,
        "signals": [{"kind": s.kind, "t": s.t} for s in state.signals],
        "flags": [{"kind": f.kind, "t": f.t} for f in state.flags],
        "alerts": [{"t": a.t, "level": int(a.level), "reason": a.reason} for a in state.alerts],
        "choice": state.user_choice,
        "disclosed": disclosed,
        "plan": [{"name": p.name, "status": p.status} for p in state.plan],
        "timeline": timeline,
    }
