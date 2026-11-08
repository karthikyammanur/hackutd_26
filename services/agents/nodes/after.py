"""After-call nodes: planner -> router -> one node per step -> router ... (hard cap MAX_ITERATIONS).

Step 2 uses a deterministic planner; step 5 swaps in Nemotron (deep tier). Customer and trusted-contact
addresses are placeholders that lane 4's Comms resolves to the demo numbers.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from contracts.state import PlanStep, StepName
from services.agents.graph.deps import Tools
from services.agents.graph.state import GraphState
from services.agents.nodes.during import CUSTOMER, Node, Update, trace

MAX_ITERATIONS = 8
TRUSTED_CONTACT = "trusted_contact"

Status = Literal["done", "failed", "skipped"]
StepResult = tuple[Status, str, str, Update]  # status, tool/action, detail, extra state update


def plan_steps(state: GraphState) -> list[PlanStep]:
    """Stand-in planner. 'continue' skips lock_account; 'ask_trusted_contact' adds the notify step."""
    choice = state.user_choice
    bank = _bank(state)
    callback_detail = f"warm transfer to {bank}" if choice == "call_bank" and bank else "send official number"
    steps = [
        PlanStep(name="lock_account", status="skipped", detail="customer chose continue")
        if choice == "continue"
        else PlanStep(name="lock_account"),
        PlanStep(name="callback", detail=callback_detail),
        PlanStep(name="recovery"),
        PlanStep(name="evidence"),
    ]
    if choice == "ask_trusted_contact":
        steps.append(PlanStep(name="notify_trusted_contact"))
    return steps


def planner(state: GraphState) -> Update:
    plan = plan_steps(state)
    summary = ", ".join(f"{p.name}{' (skipped)' if p.status == 'skipped' else ''}" for p in plan)
    return {"plan": plan, "after_iterations": 0, "trace": trace(state, "planner", "plan", summary)}


def _next_pending(state: GraphState) -> StepName | None:
    return next((p.name for p in state.plan if p.status == "pending"), None)


def router(state: GraphState) -> Update:
    n = state.after_iterations + 1
    nxt = _next_pending(state)
    if nxt is None:
        return {"after_iterations": n, "trace": trace(state, "router", "all steps finished")}
    if n > MAX_ITERATIONS:
        plan = [
            p.model_copy(update={"status": "skipped", "detail": "iteration cap"})
            if p.status == "pending"
            else p
            for p in state.plan
        ]
        return {"after_iterations": n, "plan": plan, "trace": trace(state, "router", "iteration cap reached")}
    return {"after_iterations": n, "trace": trace(state, "router", "next", nxt)}


def route_after(state: GraphState) -> str:
    return _next_pending(state) or "__end__"


def _bank(state: GraphState) -> str | None:
    for sig in state.signals:
        if sig.kind in ("otp_during_call", "bank_app_during_call") and sig.detail:
            return sig.detail
    return state.caller.verified_org if state.caller else None


HOLD_ACTIONS = ["sim_change", "port_out", "call_forwarding_on"]
HOLD_MINUTES = 60


def lock_account(state: GraphState, tools: Tools) -> StepResult:
    hold_id = tools.account.hold_changes(state.session_id, HOLD_ACTIONS, HOLD_MINUTES)
    return (
        "done",
        "account.hold_changes",
        f"{', '.join(HOLD_ACTIONS)} held {HOLD_MINUTES} min ({hold_id})",
        {},
    )


def callback(state: GraphState, tools: Tools) -> StepResult:
    bank = _bank(state)
    number = tools.store.official_number(bank) if bank else None
    sid = state.session_id
    if state.user_choice == "call_bank" and bank and number:
        call_id = tools.comms.call(
            sid, CUSTOMER, f"This is Safe Signal. Connecting you to {bank} at their official number."
        )
        tid = tools.comms.transfer(sid, call_id, number)
        return "done", "comms.call + comms.transfer", f"warm transfer to {bank} {number} ({tid})", {}
    if bank and number:
        tools.comms.message(sid, CUSTOMER, f"To check with {bank}, call their official number: {number}.")
        return "done", "comms.message", f"sent {bank} official number", {}
    tools.comms.message(sid, CUSTOMER, "To check with your bank, call the number on the back of your card.")
    return "done", "comms.message", "sent card-number advice", {}


_RECOVERY: dict[str, str] = {
    "read_code": "Change your online banking password and tell your bank a code was shared.",
    "safe_account": "Don't move money to any account a caller gave you.",
    "gift_cards": "Keep the gift card receipts and contact the card's issuer.",
    "remote_access": "Uninstall any remote access app the caller asked for.",
}


def recovery(state: GraphState, tools: Tools) -> StepResult:
    kinds = dict.fromkeys(f.kind for f in state.flags)
    steps = [_RECOVERY[k] for k in kinds if k in _RECOVERY] or ["Call your bank at the number on your card."]
    tools.comms.message(state.session_id, CUSTOMER, " ".join(steps))
    return "done", "comms.message", f"sent {len(steps)} recovery steps", {}


def evidence(state: GraphState, tools: Tools) -> StepResult:
    """Signals, not conversations (R9): flag kind + short quote, scores, timestamps. No transcript."""
    packet = {
        "session_id": state.session_id,
        "caller_number": state.caller.number if state.caller else None,
        "signals": [x.model_dump(mode="json") for x in state.signals],
        "flags": [f.model_dump(mode="json") for f in state.flags],
        "alerts": [a.model_dump(mode="json") for a in state.alerts],
        "risk": state.risk.model_dump(mode="json") if state.risk else None,
        "user_choice": state.user_choice,
    }
    eid = tools.store.save_evidence(state.session_id, packet)
    return "done", "store.save_evidence", eid, {"evidence_id": eid}


def notify_trusted_contact(state: GraphState, tools: Tools) -> StepResult:
    tools.comms.message(
        state.session_id,
        TRUSTED_CONTACT,
        "Safe Signal: someone you know may have been on a scam call. Please check in with them.",
    )
    return "done", "comms.message", "trusted contact notified", {}


STEPS: dict[StepName, Callable[[GraphState, Tools], StepResult]] = {
    "lock_account": lock_account,
    "callback": callback,
    "recovery": recovery,
    "evidence": evidence,
    "notify_trusted_contact": notify_trusted_contact,
}


def make_step(name: StepName, tools: Tools) -> Node:
    fn = STEPS[name]

    def step(state: GraphState) -> Update:
        try:
            status, action, detail, extra = fn(state, tools)
        except Exception as exc:  # a failed tool marks the step failed; the call itself is untouched (R4)
            status, action, detail, extra = "failed", "error", type(exc).__name__, {}
        plan = [
            p.model_copy(update={"status": status, "detail": detail}) if p.name == name else p
            for p in state.plan
        ]
        out: dict[str, Any] = {"plan": plan, "trace": trace(state, name, action, detail)}
        return out | extra

    return step
