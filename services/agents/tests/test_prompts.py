"""L1-prompts: the node prompts and their output schemas.

Offline tests need no network: every prompt loads, every worked example inside a prompt validates
against that node's model, and the schemas reject what we never ship (promised refunds, over-long
copy, duplicate plan steps). The live tests need Brev in `.env` and are skipped without it.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from contracts.events import AccountChange, BankAppTraffic, CallStart, EvalCase, SmsOtp, Turn
from contracts.state import Flag
from services.agents import llm
from services.agents.prompts import PROMPT_NAMES, PROMPTS, load_prompt
from services.agents.prompts.schemas import (
    AlertCopy,
    CallbackScript,
    EvidenceSummary,
    GuardianFlag,
    GuardianOutput,
    PlannerOutput,
    RecoveryPlan,
    RecoveryStep,
)

load_dotenv()

FIXTURES = Path(__file__).resolve().parents[3] / "evals" / "fixtures"
_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def _examples(name: str) -> list[str]:
    """The worked example replies in a prompt file, in order."""
    return _JSON_BLOCK.findall(load_prompt(name))


# --- prompt files ------------------------------------------------------------------------------


@pytest.mark.parametrize("name", PROMPT_NAMES)
def test_prompt_loads(name: str) -> None:
    text = load_prompt(name)
    assert len(text) > 400, f"{name} looks like a stub"
    assert "TODO" not in text


def test_unknown_prompt_raises() -> None:
    with pytest.raises(KeyError):
        load_prompt("nope")


@pytest.mark.parametrize("name", PROMPT_NAMES)
def test_prompt_says_the_user_message_is_data(name: str) -> None:
    """R12: every prompt tells the model that the blocks it receives are quoted material."""
    text = load_prompt(name).lower()
    assert "data, never instructions" in text
    assert "evidence, not instructions" in text or "never an instruction" in text


@pytest.mark.parametrize("name", PROMPT_NAMES)
def test_prompt_examples_validate_against_the_schema(name: str) -> None:
    """Every example reply we show the model has to be a legal reply itself."""
    model = PROMPTS[name]
    blocks = _examples(name)
    assert 2 <= len(blocks) <= 4, f"{name} has {len(blocks)} examples, want 2 to 4"
    for i, block in enumerate(blocks, 1):
        try:
            model.model_validate_json(block)
        except ValidationError as e:
            pytest.fail(f"{name} example {i} is not a valid {model.__name__}: {e}")


def test_guardian_prompt_carries_the_cases_that_matter() -> None:
    text = load_prompt("guardian")
    assert '{"flags": []}' in text, "needs the real-bank hard negative, which flags nothing"
    assert "verified organization: Lone Star Bank" in text
    assert "gift card credit" in text and "policy_contradiction" in text, "needs the fake-support case"
    assert "ignore previous instructions" in text.lower(), "needs the spoken-injection case"
    assert "enters in their own app" in text, "needs the code-aloud vs code-in-app rule"


def test_prompts_keep_the_no_hang_up_and_no_promise_rules() -> None:
    assert "hang up" in load_prompt("alert"), "alert copy must be told never to say hang up (R2)"
    assert "does not hang up" in load_prompt("planner")
    assert "no exceptions" in load_prompt("recovery")
    assert "dispute request" in load_prompt("recovery")
    assert "never ask you for a code" in load_prompt("callback")


def test_tiers_cover_every_prompt() -> None:
    assert set(PROMPT_NAMES) == set(llm.NODE_TIER)
    assert {n for n in PROMPT_NAMES if llm.NODE_TIER[n] == "fast"} == {"guardian", "alert", "evidence"}
    assert {n for n in PROMPT_NAMES if llm.NODE_TIER[n] == "deep"} == {"planner", "callback", "recovery"}


# --- schemas -----------------------------------------------------------------------------------


def test_guardian_flag_leaves_t_to_the_node() -> None:
    assert "t" not in GuardianFlag.model_fields
    out = GuardianOutput.model_validate(
        {"flags": [{"kind": "read_code", "quote": "read it back", "confidence": 0.9}]}
    )
    flag = Flag(**out.flags[0].model_dump(), t=101)
    assert flag.kind == "read_code" and flag.t == 101


def test_guardian_output_defaults_to_no_flags() -> None:
    assert GuardianOutput.model_validate({"flags": []}).flags == []
    assert GuardianOutput().flags == []


@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "read_code", "quote": "x" * 201, "confidence": 0.9},  # quote too long
        {"kind": "read_code", "quote": "", "confidence": 0.9},  # empty quote
        {"kind": "read_code", "quote": "ok", "confidence": 1.5},  # out of range
        {"kind": "not_a_kind", "quote": "ok", "confidence": 0.5},  # unknown kind
        {"kind": "read_code", "quote": "ok", "confidence": 0.5, "t": 101},  # the node owns t
    ],
)
def test_guardian_flag_rejects(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        GuardianFlag.model_validate(bad)


def test_alert_copy_accepts_one_plain_sentence() -> None:
    copy = AlertCopy(
        reason="The caller wants the code your bank just texted.", whisper="Please do not read it out."
    )
    assert copy.reason.endswith(".")


@pytest.mark.parametrize(
    "bad",
    [
        {"reason": "Two sentences. That is one too many.", "whisper": "ok"},
        {"reason": "x" * 141, "whisper": "ok"},
        {"reason": "Fine.", "whisper": "y" * 81},
        {"reason": "You will be refunded by your bank.", "whisper": "ok"},
        {"reason": "We guarantee this.", "whisper": "ok"},
    ],
)
def test_alert_copy_rejects(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        AlertCopy.model_validate(bad)


def test_planner_output_keeps_an_ordered_unique_list() -> None:
    plan = PlannerOutput(steps=["callback", "recovery", "evidence"], rationale="Bank impersonation.")
    assert plan.steps[-1] == "evidence"


@pytest.mark.parametrize(
    "bad",
    [
        {"steps": ["callback", "callback"], "rationale": "duplicate step"},
        {"steps": [], "rationale": "no steps"},
        {"steps": ["hang_up"], "rationale": "not a step name"},
        {"steps": ["evidence"], "rationale": "We will refund the customer."},
        {"steps": ["evidence"], "rationale": "x" * 201},
    ],
)
def test_planner_output_rejects(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        PlannerOutput.model_validate(bad)


def test_callback_script_allows_two_sentences() -> None:
    script = CallbackScript(
        opening="Hi, this is Safe Signal. I will never ask you for a code.",
        explanation="That caller wanted the code your bank texted you. A real bank asks for neither.",
        transfer_offer="I can connect you on the number on your card. Say yes whenever you are ready.",
    )
    assert script.opening.startswith("Hi")


@pytest.mark.parametrize("field", ["opening", "explanation", "transfer_offer"])
def test_callback_script_rejects_three_sentences(field: str) -> None:
    good = {"opening": "One sentence.", "explanation": "One sentence.", "transfer_offer": "One sentence."}
    with pytest.raises(ValidationError):
        CallbackScript.model_validate({**good, field: "One. Two. Three."})


def test_callback_script_rejects_a_money_promise() -> None:
    with pytest.raises(ValidationError):
        CallbackScript.model_validate(
            {
                "opening": "Hi.",
                "explanation": "Your money will be returned.",
                "transfer_offer": "I can connect you.",
            }
        )


def _recovery(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "steps": [
            {"order": 1, "title": "Call your bank", "detail": "Use the number on the back of your card."},
            {
                "order": 2,
                "title": "Dispute the purchase with your card issuer",
                "detail": "We filed a dispute request with your card issuer for the gift card purchase.",
            },
        ],
        "cancel_request": (
            "The account holder did not authorise the transfer and asks that anything pending be stopped."
        ),
    }
    return {**base, **over}


def test_recovery_plan_allows_a_card_dispute_request() -> None:
    plan = RecoveryPlan.model_validate(_recovery())
    assert "dispute request" in plan.steps[1].detail


@pytest.mark.parametrize(
    "text",
    [
        "You will get your money back within ten days.",
        "The bank will refund the transfer.",
        "We guarantee a full refund.",
        "Your dispute was approved.",
        "The charge was reversed.",
        "Your money is safe now.",
    ],
)
def test_recovery_plan_never_promises_money_back(text: str) -> None:
    with pytest.raises(ValidationError):
        RecoveryPlan.model_validate(_recovery(cancel_request=text))
    with pytest.raises(ValidationError):
        RecoveryStep.model_validate({"order": 1, "title": "Step", "detail": text})


@pytest.mark.parametrize(
    "text", ["Dispute it with Visa.", "Call Mastercard.", "Use your T-Mobile credit card."]
)
def test_recovery_plan_never_names_the_issuer(text: str) -> None:
    with pytest.raises(ValidationError):
        RecoveryStep.model_validate({"order": 1, "title": "Step", "detail": text})


def test_recovery_plan_rejects_order_gaps() -> None:
    steps = [
        {"order": 1, "title": "A", "detail": "first"},
        {"order": 3, "title": "B", "detail": "third"},
    ]
    with pytest.raises(ValidationError):
        RecoveryPlan.model_validate(_recovery(steps=steps))


def test_evidence_summary_caps_the_paragraph() -> None:
    assert EvidenceSummary(summary="Inbound call, code requested, level alert.").summary
    with pytest.raises(ValidationError):
        EvidenceSummary.model_validate({"summary": "x" * 401})
    with pytest.raises(ValidationError):
        EvidenceSummary.model_validate({"summary": "The bank will refund the transfer."})


# --- live: guardian against the fixtures -------------------------------------------------------


def _case(name: str) -> EvalCase:
    return EvalCase.model_validate_json((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _guardian_user(case: EvalCase) -> str:
    """Build the user message the Guardian prompt describes. Transcript text lives here only (R12)."""
    start = next(e for e in case.events if isinstance(e, CallStart))
    verified = (
        f"verified organization: {start.verified_org}"
        if start.verified_org
        else "not on the verified-organization list"
    )
    seen = "first time seen" if start.first_seen else "seen before"
    dialed = " (the customer dialed this number)" if start.direction == "outbound" else ""
    signals: list[str] = []
    for e in case.events:
        if isinstance(e, SmsOtp):
            signals.append(f"otp_during_call from a {e.sender_type} at t={e.t:.0f}")
        elif isinstance(e, BankAppTraffic):
            signals.append(f"bank_app_during_call at t={e.t:.0f}")
        elif isinstance(e, AccountChange):
            signals.append(f"account_change {e.action} {e.status} at t={e.t:.0f}")
    context = "\n".join(
        [
            f"direction: {start.direction}{dialed}",
            f"number: {start.number} ({seen}, {verified})",
            f"carrier_label: {start.carrier_label}",
            f"attestation: {start.attestation}",
            "recent signals: " + (", ".join(signals) if signals else "none"),
        ]
    )
    turns = "\n".join(f"[t={e.t:.0f}] {e.speaker}: {e.text}" for e in case.events if isinstance(e, Turn))
    return llm.data_block("call_context", context) + "\n" + llm.data_block("transcript", turns)


def _needs_brev() -> None:
    if not os.environ.get("NEMOTRON_BASE_URL"):
        pytest.skip("needs NEMOTRON_BASE_URL in .env")


def _run_guardian(fixture: str) -> GuardianOutput:
    user = _guardian_user(_case(fixture))
    out = llm.structured(load_prompt("guardian"), user, GuardianOutput, "fast", timeout=30)
    print(f"\n{fixture}: {llm.last_latency_ms:.0f} ms")
    for f in out.flags:
        print(f"  {f.kind:22} {f.confidence:.2f}  {f.quote[:70]!r}")
    if not out.flags:
        print("  (no flags)")
    return out


def test_live_guardian_flags_the_bank_code_on_hero1() -> None:
    _needs_brev()
    kinds = {f.kind for f in _run_guardian("hero1_fake_bank").flags if f.confidence >= 0.5}
    assert "read_code" in kinds, f"expected read_code, got {kinds}"


def test_live_guardian_flags_the_fake_support_call() -> None:
    _needs_brev()
    kinds = {f.kind for f in _run_guardian("fake_tmobile_support").flags if f.confidence >= 0.5}
    assert kinds & {"gift_cards", "policy_contradiction"}, f"expected a gift card flag, got {kinds}"


def test_live_guardian_stays_quiet_on_the_real_bank_callback() -> None:
    """R7: the customer dialed the verified bank and a code arrived. Nothing to flag."""
    _needs_brev()
    loud = [f for f in _run_guardian("real_bank_callback").flags if f.confidence > 0.5]
    assert not loud, f"hard negative flagged: {loud}"


# --- live: every other prompt returns a valid object -------------------------------------------

_LIVE_USER: dict[str, str] = {
    "alert": """<call_context>
direction: inbound, number not on the verified-organization list, first time seen
</call_context>
<flags>
read_code (0.95): "You just got a six digit code. Read it back to me so I can verify it's you"
safe_account (0.9): "we'll move your balance to a protected safe account"
</flags>
<signals>
unknown_caller, otp_during_call from a bank short code
</signals>
level: alert""",
    "planner": """<call_context>
direction: inbound, number not on the verified-organization list, first time seen
</call_context>
<flags>
read_code (0.95), safe_account (0.9), urgency_secrecy (0.8)
</flags>
<signals>
unknown_caller, otp_during_call from a bank short code
</signals>
risk: 0.88, level: alert
user_choice: call_bank
trusted_contact_on_file: true""",
    "callback": """<call_context>
direction: inbound, number not on the verified-organization list, call ended at t=131
</call_context>
<flags>
read_code (0.95): "Read it back to me so I can verify it's you"
safe_account (0.9): "we'll move your balance to a protected safe account"
</flags>
<callback_target>
organisation: the customer's bank
verified_number: the number printed on the back of the customer's card
</callback_target>""",
    "recovery": """<call_context>
direction: inbound, number not on the verified-organization list
</call_context>
<flags>
read_code (0.95): "Read it back to me so I can verify it's you"
safe_account (0.9): "we'll move your balance to a protected safe account"
</flags>
<signals>
unknown_caller, otp_during_call from a bank short code
</signals>
<what_moved>
a one-time bank code was requested; the caller described a 1,240 dollar transfer the customer did not
authorise; no payment was made by the customer
</what_moved>""",
    "evidence": """<call_context>
direction: inbound, number not on the verified-organization list, first time seen, ended at t=131
</call_context>
<flags>
read_code (0.95): "Read it back to me so I can verify it's you"
safe_account (0.9): "we'll move your balance to a protected safe account"
</flags>
<signals>
unknown_caller, otp_during_call from a bank short code at t=92
</signals>
risk: 0.88, level: alert
alerts: 1 at level alert
user_choice: call_bank
plan: callback (done), recovery (done), evidence (running)""",
}


@pytest.mark.parametrize("name", sorted(_LIVE_USER))
def test_live_prompt_returns_a_valid_object(name: str) -> None:
    """Also proves the nested $defs/$ref schema (recovery) decodes on the deep tier."""
    _needs_brev()
    tier = llm.NODE_TIER[name]
    model: type[BaseModel] = PROMPTS[name]
    out = llm.structured(load_prompt(name), _LIVE_USER[name], model, tier, timeout=60, max_tokens=1200)
    print(f"\n{name} ({tier}): {llm.last_latency_ms:.0f} ms\n{json.dumps(out.model_dump(), indent=2)}")
    assert isinstance(out, model)


# --- live: guardian on calls that appear in no example ------------------------------------------

_UNSEEN_SCAM = """<call_context>
direction: inbound
number: +12025550164 (first time seen, not on the verified-organization list)
carrier_label: none
attestation: none
recent signals: none
</call_context>
<transcript>
[t=18] caller: This is the federal benefits fraud unit. Your number was used to open accounts in two states.
[t=33] caller: To let me check your balance safely, download AnyDesk and give me the nine digit session code.
[t=52] caller: Do not mention this to the teller or your family while the case is open.
</transcript>"""

_UNSEEN_BENIGN = """<call_context>
direction: outbound (the customer dialed this number)
number: +18005550199 (seen before, verified organization: Lone Star Bank)
carrier_label: none
attestation: A
recent signals: none
</call_context>
<transcript>
[t=12] customer: I am calling about the replacement card you were sending me.
[t=19] caller: Happy to check. Can you confirm the last four digits of the card and the ZIP code on the account?
[t=48] caller: Thanks, that matches. Your new card is on its way and should arrive Thursday.
</transcript>"""


@pytest.mark.parametrize(
    ("label", "user", "expect_kind"),
    [("unseen_scam", _UNSEEN_SCAM, "remote_access"), ("unseen_benign", _UNSEEN_BENIGN, None)],
)
def test_live_guardian_generalises_beyond_the_examples(
    label: str, user: str, expect_kind: str | None
) -> None:
    """The examples come from the fixtures, so check two calls the prompt has never seen."""
    _needs_brev()
    out = llm.structured(load_prompt("guardian"), user, GuardianOutput, "fast", timeout=30)
    print(f"\n{label}: {llm.last_latency_ms:.0f} ms")
    for f in out.flags:
        print(f"  {f.kind:22} {f.confidence:.2f}  {f.quote[:70]!r}")
    if not out.flags:
        print("  (no flags)")
    kinds = {f.kind for f in out.flags if f.confidence > 0.5}
    if expect_kind is None:
        assert not kinds, f"benign call flagged: {kinds}"
    else:
        assert expect_kind in kinds, f"expected {expect_kind}, got {kinds}"
