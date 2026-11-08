"""What the LLM is allowed to return (R11). One model per node; the graph imports these.

Length and shape rules live here, not only in the prompt text: an invalid reply fails validation,
and `llm.structured()` retries once with the exact error, so the schema teaches the model.

Money rule (facts.md: the T-Mobile card is unconfirmed, so nothing here names a card product):
no output may promise a refund, a reversal or money back. A card-payment step may say it filed a
*dispute request* with the customer's card issuer, with no issuer named.
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from contracts.state import FlagKind, StepName

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

# Promises we never make. Each pattern is something the customer could read as "you get your money back".
_PROMISES: tuple[tuple[str, str], ...] = (
    (r"money[-\s]back", "promises money back"),
    (r"\b(get|getting|have)\s+(your|the|their)\s+(money|funds)\s+back\b", "promises money back"),
    (
        r"\b(will|'ll)\s+be\s+(refunded|reimbursed|returned|recovered|restored|made whole)\b",
        "promises a refund",
    ),
    (
        r"\b(we|they|the bank|the issuer)\s*(?:'ll|\s+will)\s+(refund|reimburse|return|recover|restore)\b",
        "promises a refund",
    ),
    (r"\b(refund|funds?|charges?|money|transfer)\s+will\s+be\b", "promises an outcome"),
    (r"\b(full|complete|guaranteed)\s+(refund|recovery|reimbursement)\b", "promises a refund"),
    (r"\bguarantee", "guarantees an outcome"),
    (
        r"\b(dispute|claim)\s+(was\s+|is\s+)?(approved|won|successful|resolved)\b",
        "promises the dispute succeeds",
    ),
    (r"\b(charge|transfer|payment)s?\s+(was|were|is|are|will\s+be)\s+reversed\b", "promises a reversal"),
    (r"\byour\s+(money|funds)\s+(is|are)\s+safe\b", "promises the money is safe"),
)

# Card networks and issuers. Recovery copy says "your card issuer", never a brand (facts.md).
_ISSUERS = re.compile(
    r"\b(visa|mastercard|master\s?card|amex|american\s+express|discover|t-?mobile\s+(credit\s+)?card)\b",
    re.IGNORECASE,
)


def _no_promise(text: str) -> str:
    """Reject refund, reversal and money-back promises anywhere in customer-facing copy."""
    for pattern, why in _PROMISES:
        if re.search(pattern, text, re.IGNORECASE):
            raise ValueError(
                f"{why}: {text!r}. Never promise a refund, a reversal or money back. "
                "Describe only the action taken or requested."
            )
    return text


def _no_issuer_name(text: str) -> str:
    """Card wording stays generic: 'your card issuer', no brand or bank product name."""
    if m := _ISSUERS.search(text):
        raise ValueError(f"names a card issuer or product ({m.group(0)!r}); say 'your card issuer' instead")
    return text


def _sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_END.split(text.strip()) if s]


def _one_sentence(text: str) -> str:
    n = len(_sentences(text))
    if n > 1:
        raise ValueError(f"must be exactly one sentence, got {n}: {text!r}")
    return text


def _two_sentences(text: str) -> str:
    n = len(_sentences(text))
    if n > 2:
        raise ValueError(f"must be at most two sentences, got {n}: {text!r}")
    return text


Plain = Annotated[str, AfterValidator(_no_promise)]
OneSentence = Annotated[str, AfterValidator(_no_promise), AfterValidator(_one_sentence)]
TwoSentences = Annotated[str, AfterValidator(_no_promise), AfterValidator(_two_sentences)]
CardSafe = Annotated[str, AfterValidator(_no_promise), AfterValidator(_no_issuer_name)]


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- guardian (fast) ---------------------------------------------------------------------------


class GuardianFlag(_Out):
    """One scam ask the caller made. The node adds `t` and builds a `contracts.state.Flag`."""

    kind: FlagKind
    quote: Annotated[str, Field(min_length=1, max_length=200)]  # the caller's own words, short
    confidence: Annotated[float, Field(ge=0, le=1)]


class GuardianOutput(_Out):
    flags: Annotated[list[GuardianFlag], Field(max_length=6)] = Field(default_factory=list)


# --- alert (fast) ------------------------------------------------------------------------------


class AlertCopy(_Out):
    """Customer-facing wording. Never mentions hanging up: the customer decides (R2, R3)."""

    reason: Annotated[OneSentence, Field(min_length=1, max_length=140)]
    whisper: Annotated[Plain, Field(min_length=1, max_length=80)]  # spoken aloud, only the customer hears it


# --- planner (deep) ----------------------------------------------------------------------------


def _unique_steps(steps: list[StepName]) -> list[StepName]:
    if len(set(steps)) != len(steps):
        raise ValueError(f"each step may appear once, got {steps}")
    return steps


class PlannerOutput(_Out):
    steps: Annotated[list[StepName], Field(min_length=1, max_length=5), AfterValidator(_unique_steps)]
    rationale: Annotated[Plain, Field(min_length=1, max_length=200)]


# --- callback (deep) ---------------------------------------------------------------------------


class CallbackScript(_Out):
    """Spoken to the customer when Safe Signal calls them back. Calm, short, no new facts."""

    opening: Annotated[TwoSentences, Field(min_length=1, max_length=240)]
    explanation: Annotated[TwoSentences, Field(min_length=1, max_length=240)]
    transfer_offer: Annotated[TwoSentences, Field(min_length=1, max_length=240)]


# --- recovery (deep) ---------------------------------------------------------------------------


class RecoveryStep(_Out):
    order: Annotated[int, Field(ge=1, le=10)]
    title: Annotated[CardSafe, Field(min_length=1, max_length=80)]
    detail: Annotated[CardSafe, Field(min_length=1, max_length=240)]


def _ordered(steps: list[RecoveryStep]) -> list[RecoveryStep]:
    if [s.order for s in steps] != list(range(1, len(steps) + 1)):
        raise ValueError(f"order must run 1..{len(steps)} with no gaps, got {[s.order for s in steps]}")
    return steps


class RecoveryPlan(_Out):
    steps: Annotated[list[RecoveryStep], Field(min_length=1, max_length=6), AfterValidator(_ordered)]
    cancel_request: Annotated[CardSafe, Field(min_length=1, max_length=320)]  # short message to the bank


# --- evidence (fast) ---------------------------------------------------------------------------


class EvidenceSummary(_Out):
    """Goes in the stored packet, so it holds signals, not conversation (R9)."""

    summary: Annotated[Plain, Field(min_length=1, max_length=400)]
