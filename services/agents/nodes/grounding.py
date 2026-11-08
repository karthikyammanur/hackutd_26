"""Keep alert copy grounded: say only what a flag or signal in state supports.

draft_reason() builds the reason deterministically from the newest piece of evidence; Nemotron may only rephrase
it. unsupported_claims() then checks every claim keyword in the generated text against the flags and signals in
state, so the card can never claim an ask that has not happened yet (e.g. "wants the code" when the code has only
arrived).
"""

from __future__ import annotations

import re

from contracts.state import SessionState

FLAG_MIN_CONFIDENCE = 0.5

FLAG_SENTENCE: dict[str, str] = {
    "read_code": "The caller asked you to read back a code, and real bank or carrier staff never ask for that.",
    "safe_account": "The caller wants your money moved to a 'safe' account, and real banks never ask for that.",
    "gift_cards": "The caller asked for payment by gift card, and real companies never ask for that.",
    "remote_access": "The caller asked for remote access to your device.",
    "urgency_secrecy": "The caller is rushing you or asking you to keep this call to yourself.",
    "policy_contradiction": "The caller described a rule that the real company does not have.",
    "other": "The caller asked for something that works against you.",
}


def _signal_sentence(kind: str, verified: bool) -> str | None:
    who = "a caller" if verified else "an unverified number"
    return {
        "otp_during_call": f"A bank code just arrived while you're on a call with {who}.",
        "bank_app_during_call": f"Your bank app opened while you're on a call with {who}.",
        "account_change_during_call": "Someone tried to change your phone account during this call.",
        "scam_list_hit": "This number is on a scam list.",
        "unknown_caller": "This number is new and not on our verified list.",
        "unverified_caller": "This number is not on our verified list.",
    }.get(kind)


def draft_reason(state: SessionState) -> str:
    """One sentence from the newest evidence: a flag (confidence >= 0.5) or a signal with weight > 0.

    Ties at the same t go to the flag, since the caller's ask is the stronger evidence.
    """
    verified = bool(state.caller and state.caller.verified_org)
    items: list[tuple[float, int, str]] = []
    for f in state.flags:
        if f.confidence >= FLAG_MIN_CONFIDENCE:
            items.append((f.t, 1, FLAG_SENTENCE[f.kind]))
    for s in state.signals:
        sentence = _signal_sentence(s.kind, verified)
        if s.weight > 0 and sentence:
            items.append((s.t, 0, sentence))
    if not items:
        return "Something about this call looks unusual."
    return max(items)[2]


# Claim keyword -> the flag kinds or signal kinds that support it. Checked in order; one match is enough.
_ASK_CODE = re.compile(
    r"\b(read|say|tell|give|share|repeat|wants?|asks?|asked|asking|needs?)\b[^.]{0,40}?\b(code|digits|pin|password)",
    re.IGNORECASE,
)
CLAIMS: list[tuple[str, re.Pattern[str], frozenset[str]]] = [
    ("asks for a code", _ASK_CODE, frozenset({"read_code"})),
    (
        "code",
        re.compile(r"\b(code|digits|one-time|pin|password)\b", re.IGNORECASE),
        frozenset({"read_code", "otp_during_call"}),
    ),
    ("read back", re.compile(r"\bread (it |them |that )?back\b", re.IGNORECASE), frozenset({"read_code"})),
    ("gift card", re.compile(r"\b(gift|prepaid) ?cards?\b", re.IGNORECASE), frozenset({"gift_cards"})),
    (
        "safe account",
        re.compile(
            r"\b(safe|protected|secure|holding) account\b|\bmove (your |the )?(money|balance|funds)\b",
            re.IGNORECASE,
        ),
        frozenset({"safe_account"}),
    ),
    (
        "remote access",
        re.compile(r"\bremote\b|\bscreen ?shar|\banydesk\b|\bteamviewer\b", re.IGNORECASE),
        frozenset({"remote_access"}),
    ),
    (
        "transfer",
        re.compile(r"\b(transfer|wire)\w*\b", re.IGNORECASE),
        frozenset({"safe_account", "gift_cards"}),
    ),
    (
        "SIM",
        re.compile(r"\b(sim|port[- ]?out|call forwarding)\b", re.IGNORECASE),
        frozenset({"account_change_during_call"}),
    ),
]


def evidence_kinds(state: SessionState) -> set[str]:
    kinds = {f.kind for f in state.flags if f.confidence >= FLAG_MIN_CONFIDENCE}
    kinds |= {s.kind for s in state.signals if s.weight > 0}
    return kinds


def unsupported_claims(text: str, state: SessionState) -> list[str]:
    """Claim keywords in `text` with no supporting flag or signal in state."""
    have = evidence_kinds(state)
    return [name for name, pat, needs in CLAIMS if pat.search(text) and not (needs & have)]
