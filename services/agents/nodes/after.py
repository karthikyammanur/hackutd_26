"""After-call nodes: planner -> router -> one node per step -> router ... (hard cap MAX_ITERATIONS).

Planner, Callback and Recovery run on Nemotron deep; Evidence summary on fast. Every LLM output is checked by its
schema (R11), and rules the LLM must not break are enforced here in code. Any LLM failure falls back to a
template: the call is over, so a slow or bad reply never sets guard_paused.

"customer" and "trusted_contact" are logical recipients; lane 4's Comms maps them to the demo numbers.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any, Literal

from contracts.state import Level, PlanStep, StepName
from services.agents import llm
from services.agents.graph.deps import Tools
from services.agents.graph.state import GraphState
from services.agents.nodes.blocks import blocks, context_line, flags_lines, signals_line, top_level
from services.agents.nodes.during import CUSTOMER, Node, Update, trace
from services.agents.prompts import (
    CallbackScript,
    EvidenceSummary,
    PlannerOutput,
    RecoveryPlan,
    load_prompt,
)

log = logging.getLogger(__name__)

MAX_ITERATIONS = 8
TRUSTED_CONTACT = "trusted_contact"
ORDER: tuple[StepName, ...] = ("lock_account", "callback", "recovery", "notify_trusted_contact", "evidence")
TIMEOUT_S: dict[str, float] = {"planner": 25.0, "callback": 25.0, "recovery": 25.0, "evidence": 10.0}

Status = Literal["done", "failed", "skipped"]
StepResult = tuple[Status, str, str, Update]  # status, tool/action, detail, extra state update
Structured = Callable[..., Any]  # llm.structured, or a fake in tests


def _ask(structured: Structured, node: str, user: str, model: type) -> Any:
    """One Nemotron call for an after-call node. Returns None on any failure (caller uses its template)."""
    try:
        return structured(load_prompt(node), user, model, llm.NODE_TIER[node], timeout=TIMEOUT_S[node])
    except Exception as exc:
        log.warning("%s llm failed: %s", node, type(exc).__name__)
        return None


# ---- planner ------------------------------------------------------------------------------------------------


def fallback_steps(state: GraphState) -> list[StepName]:
    """Deterministic plan used when the planner LLM fails."""
    steps: list[StepName] = ["lock_account", "callback", "recovery", "evidence"]
    if state.user_choice == "ask_trusted_contact":
        steps.append("notify_trusted_contact")
    return steps


def enforce_plan(steps: list[StepName], state: GraphState) -> list[PlanStep]:
    """Rules the planner cannot break. Steps added by a rule say so in their detail."""
    chosen = dict.fromkeys(steps)
    required: dict[StepName, str] = {}
    choice = state.user_choice
    if choice == "ask_trusted_contact":
        required["notify_trusted_contact"] = "customer chose ask_trusted_contact"
    else:
        chosen.pop("notify_trusted_contact", None)  # only on the customer's choice
    if choice == "call_bank":
        required["callback"] = "customer chose call_bank"
    if top_level(state) >= Level.alert and choice != "continue":
        required["lock_account"] = "session reached alert"  # a code-read scam leads to a SIM swap next
    required["evidence"] = "always recorded"
    plan: list[PlanStep] = []
    for name in ORDER:
        if name == "lock_account" and choice == "continue":
            plan.append(PlanStep(name=name, status="skipped", detail="customer chose continue"))
        elif name in chosen:
            plan.append(PlanStep(name=name))
        elif name in required:
            plan.append(PlanStep(name=name, detail=f"required: {required[name]}"))
    return plan


def planner_user(state: GraphState) -> str:
    risk = state.risk
    return blocks(
        ("call_context", context_line(state)),
        ("flags", flags_lines(state, quotes=False)),
        ("signals", signals_line(state)),
        tail=[
            f"risk: {risk.score:.2f}, level: {top_level(state).name}" if risk else "risk: none",
            f"user_choice: {state.user_choice or 'none'}",
            "trusted_contact_on_file: true",
        ],
    )


def make_planner(structured: Structured) -> Node:
    def planner(state: GraphState) -> Update:
        out = _ask(structured, "planner", planner_user(state), PlannerOutput)
        steps = list(out.steps) if out else fallback_steps(state)
        plan = enforce_plan(steps, state)

        def tag(p: PlanStep) -> str:
            if p.status == "skipped":
                return f"{p.name} (skipped)"
            return f"{p.name} (required)" if p.detail.startswith("required") else p.name

        summary = ", ".join(tag(p) for p in plan)
        why = out.rationale if out else "planner fallback (LLM unavailable)"
        return {
            "plan": plan,
            "after_iterations": 0,
            "trace": trace(state, "planner", "plan", f"{summary} | {why}"),
        }

    return planner


# ---- router -------------------------------------------------------------------------------------------------


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


# ---- steps --------------------------------------------------------------------------------------------------


def _bank(state: GraphState) -> str | None:
    for sig in state.signals:
        if sig.kind in ("otp_during_call", "bank_app_during_call") and sig.detail:
            return sig.detail
    return state.caller.verified_org if state.caller else None


HOLD_ACTIONS = ["sim_change", "port_out", "call_forwarding_on"]
HOLD_MINUTES = 60


def lock_account(state: GraphState, tools: Tools, structured: Structured) -> StepResult:
    hold_id = tools.account.hold_changes(state.session_id, HOLD_ACTIONS, HOLD_MINUTES)
    return (
        "done",
        "account.hold_changes",
        f"{', '.join(HOLD_ACTIONS)} held {HOLD_MINUTES} min ({hold_id})",
        {},
    )


_PHONE = re.compile(r"\+?\d[\d\s().-]{5,}\d")


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def unknown_numbers(script: str, allowed: str | None) -> list[str]:
    """Phone-like numbers in the script other than the official one (the prompt forbids them)."""
    ok = _digits(allowed or "")
    return [m for m in _PHONE.findall(script) if len(_digits(m)) >= 7 and _digits(m)[-10:] != ok[-10:]]


# The customer chose this callback, so it never verifies them: no question about anything personal or account.
_PERSONAL = re.compile(
    r"\b(?:(?:home |mailing |billing |street )?address|zip(?: code)?|postal code|last (?:four|4)|digits?"
    r"|card number|account number|routing number|member number|date of birth|birth ?date|birthday|dob"
    r"|social security|ssn|pin|passcode|password|code|security question|maiden name|full name)\b",
    re.I,
)
_REQUEST = re.compile(
    r"\b(?:can|could|would|will) you\b|\bplease\b|\bwhat(?:'s| is| are) (?:your|the)\b|\b(?:i|we)(?:'ll| will)? need\b"
    r"|\b(?:may|can|could) (?:i|we) (?:have|get|take)\b"
    r"|\b(?:tell|give|confirm|provide|share|read|say|enter|type|spell|verify|repeat) (?:me |us )?(?:your|the)\b",
    re.I,
)
_IDENTITY = re.compile(
    r"\b(?:verify|verifying|confirm|confirming|authenticate)\w* (?:your |the customer's )?(?:identity|who you are)\b"
    r"|\bidentity (?:check|verification)\b|\bsecurity (?:check|questions?)\b",
    re.I,
)
# Only a negated ask counts ("I will never ask you for a code"); "Don't worry, can you confirm..." does not.
_NEGATION = re.compile(
    r"\b(?:never|won't|will not|don't|do not|not)(?: \w+)?? (?:ask|need|request)\b|\bno need to\b", re.I
)
# "The caller asked you to read back a code to verify your identity" reports the scam; it asks nothing.
_REPORTED = re.compile(
    r"\b(?:the|that) (?:caller|person)\b|\b(?:they|he|she) (?:asked|wanted|said|told|tried|pushed)\b", re.I
)


def asks_personal_info(script: str) -> list[str]:
    """Sentences that ask the customer for personal or account details, or verify who they are.

    Fine: "I will never ask you for a code" (a negation) and "The caller asked you to verify your identity"
    (a statement about the scam call). Any sentence ending in "?" that asks for something is still caught.
    """
    hits: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", script):
        reported = _REPORTED.search(sentence) and not sentence.rstrip().endswith("?")
        if _NEGATION.search(sentence) or reported:
            continue
        if _IDENTITY.search(sentence) or (_REQUEST.search(sentence) and _PERSONAL.search(sentence)):
            hits.append(sentence.strip())
    return hits


def callback_template(org: str | None, number: str | None) -> str:
    who = org or "the organisation"
    where = "on its official number" if number else "on the number printed on your card or bill"
    return (
        "Hi, this is Safe Signal, your T-Mobile call protection, about the call that just ended. "
        "I will never ask you for a code. "
        f"If you'd like, I can connect you to {who} {where}, or you can dial it yourself whenever you're ready."
    )


def make_callback(structured: Structured) -> Callable[[GraphState, Tools, Structured], StepResult]:
    def callback(state: GraphState, tools: Tools, _: Structured) -> StepResult:
        org = _bank(state)
        number = tools.store.official_number(org) if org else None
        target = "\n".join(
            [
                f"organisation: {org or 'the organisation the caller claimed to be'}",
                f"verified_number: {number}"
                if number
                else "verified_number: the number printed on the back of the customer's card or bill",
            ]
        )
        user = blocks(
            ("call_context", context_line(state, ended_at=state.event.t if state.event else None)),
            ("flags", flags_lines(state)),
            ("callback_target", target),
        )
        out = _ask(structured, "callback", user, CallbackScript)
        script = " ".join([out.opening, out.explanation, out.transfer_offer]) if out else ""
        source = "nemotron"
        if not out or unknown_numbers(script, number):
            script, source = callback_template(org, number), "template"
        elif asks_personal_info(script):  # never ask for address, card digits, codes... or verify identity
            log.warning("callback script asked for personal info; using the template")
            script, source = callback_template(org, number), "template (script asked for personal info)"
        sid = state.session_id
        call_id = tools.comms.call(sid, CUSTOMER, script)
        if state.user_choice == "call_bank" and org and number:
            tid = tools.comms.transfer(sid, call_id, number)
            return (
                "done",
                f"{source} script + comms.call + comms.transfer",
                f"warm transfer to {org} {number} ({tid})",
                {},
            )
        return "done", f"{source} script + comms.call", f"callback placed, transfer offered ({call_id})", {}

    return callback


def what_moved(state: GraphState) -> str:
    kinds = {f.kind for f in state.flags if f.confidence >= 0.5}
    parts: list[str] = []
    if "read_code" in kinds:
        parts.append("a one-time code was requested")
    if "safe_account" in kinds:
        parts.append("the caller asked to move money to another account")
    if "gift_cards" in kinds:
        parts.append("the caller asked for payment by gift card")
    if "remote_access" in kinds:
        parts.append("the caller asked for remote access to a device")
    for s in state.signals:
        if s.kind == "account_change_during_call":
            parts.append(f"a {s.detail or 'account'} change was attempted during the call and held")
    parts.append("whether the customer complied is not known")
    return "; ".join(parts)


_RECOVERY_TEMPLATE: dict[str, str] = {
    "read_code": "Change your online banking password and tell your bank a code was requested.",
    "safe_account": "Don't move money to any account a caller gave you.",
    "gift_cards": "Keep any gift card receipts and contact the card's seller.",
    "remote_access": "Uninstall any remote access app the caller asked for.",
}


def make_recovery(structured: Structured) -> Callable[[GraphState, Tools, Structured], StepResult]:
    def recovery(state: GraphState, tools: Tools, _: Structured) -> StepResult:
        user = blocks(
            ("call_context", context_line(state)),
            ("flags", flags_lines(state)),
            ("signals", signals_line(state)),
            ("what_moved", what_moved(state)),
        )
        out = _ask(structured, "recovery", user, RecoveryPlan)
        if out:
            text = " ".join(f"{s.order}. {s.title}: {s.detail}" for s in out.steps)
            n, cancel, source = len(out.steps), out.cancel_request, "nemotron"
        else:
            kinds = dict.fromkeys(f.kind for f in state.flags)
            lines = [_RECOVERY_TEMPLATE[k] for k in kinds if k in _RECOVERY_TEMPLATE] or [
                "Call your bank at the number on your card."
            ]
            text, n, cancel, source = " ".join(lines), len(lines), "", "template"
        tools.comms.message(state.session_id, CUSTOMER, text)
        return (
            "done",
            f"{source} plan + comms.message",
            f"sent {n} recovery steps",
            {"cancel_request": cancel},
        )

    return recovery


def evidence_summary_template(state: GraphState) -> str:
    kinds = ", ".join(dict.fromkeys(f.kind for f in state.flags)) or "no flags"
    return (
        f"Call {context_line(state)}. Flags: {kinds}. Signals: {signals_line(state)}. "
        f"Level reached {top_level(state).name}; customer choice: {state.user_choice or 'none'}."
    )[:400]


def make_evidence(structured: Structured) -> Callable[[GraphState, Tools, Structured], StepResult]:
    def evidence(state: GraphState, tools: Tools, _: Structured) -> StepResult:
        """Signals, not conversations (R9): flag kind + short quote, scores, timestamps. No transcript."""
        plan_line = ", ".join(
            f"{p.name} ({'running' if p.name == 'evidence' else p.status})" for p in state.plan
        )
        user = blocks(
            ("call_context", context_line(state, ended_at=state.event.t if state.event else None)),
            ("flags", flags_lines(state)),
            ("signals", signals_line(state)),
            tail=[
                f"risk: {state.risk.score:.2f}, level: {top_level(state).name}"
                if state.risk
                else "risk: none",
                f"alerts: {len(state.alerts)} up to level {top_level(state).name}",
                f"user_choice: {state.user_choice or 'none'}",
                f"plan: {plan_line}",
            ],
        )
        out = _ask(structured, "evidence", user, EvidenceSummary)
        summary, source = (out.summary, "nemotron") if out else (evidence_summary_template(state), "template")
        packet = {
            "session_id": state.session_id,
            "caller_number": state.caller.number if state.caller else None,
            "summary": summary,
            "signals": [x.model_dump(mode="json") for x in state.signals],
            "flags": [f.model_dump(mode="json") for f in state.flags],
            "alerts": [a.model_dump(mode="json") for a in state.alerts],
            "risk": state.risk.model_dump(mode="json") if state.risk else None,
            "user_choice": state.user_choice,
            "plan": [p.model_dump(mode="json") for p in state.plan],
            "cancel_request": state.cancel_request or None,
        }
        eid = tools.store.save_evidence(state.session_id, packet)
        return "done", f"{source} summary + store.save_evidence", eid, {"evidence_id": eid}

    return evidence


def notify_trusted_contact(state: GraphState, tools: Tools, structured: Structured) -> StepResult:
    tools.comms.message(
        state.session_id,
        TRUSTED_CONTACT,
        "Safe Signal: someone you know may have been on a scam call. Please check in with them.",
    )
    return "done", "comms.message", "trusted contact notified", {}


STEP_NAMES: tuple[StepName, ...] = ORDER


def make_step(name: StepName, tools: Tools, structured: Structured) -> Node:
    fn: Callable[[GraphState, Tools, Structured], StepResult] = {
        "lock_account": lock_account,
        "callback": make_callback(structured),
        "recovery": make_recovery(structured),
        "evidence": make_evidence(structured),
        "notify_trusted_contact": notify_trusted_contact,
    }[name]

    def step(state: GraphState) -> Update:
        try:
            status, action, detail, extra = fn(state, tools, structured)
        except Exception as exc:  # a failed tool marks the step failed; the call itself is untouched (R4)
            status, action, detail, extra = "failed", "error", type(exc).__name__, {}
        plan = [
            p.model_copy(update={"status": status, "detail": detail}) if p.name == name else p
            for p in state.plan
        ]
        out: dict[str, Any] = {"plan": plan, "trace": trace(state, name, action, detail)}
        return out | extra

    return step
