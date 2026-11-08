"""Keyword stand-in for Call Guardian, so the rules can be evaluated before Lane 1's graph exists.

This is NOT Call Guardian. It's a deliberately simple baseline: regexes on the caller's turns, tuned on
data/train and the fixtures only. Numbers produced with it are labeled as a keyword baseline in the report.
Quotes are clipped to the Flag limit and stay in memory (R8).
"""

from __future__ import annotations

import re

from contracts.events import Turn
from contracts.state import Flag, FlagKind

_NEGATION = re.compile(
    r"\b(never|don'?t|do not|won'?t|will not|would not|wouldn'?t|no need|not need)\b", re.I
)
_REASSURANCE = re.compile(r"\b(don'?t worry|don'?t be (scared|afraid|alarmed)|never mind|no worries)\b", re.I)
_CLAUSE_BREAK = re.compile(r"[,;:]|\b(but|however)\b", re.I)
_SHARE = r"(?:read|tell|give|say|share|provide|confirm|send me)"  # bare "send" is what a real sender says
_SECRET = r"(?:code|pin|passcode|password|otp|digits|verification)"

# (kind, pattern, confidence, negation cancels the match)
_RULES: list[tuple[FlagKind, re.Pattern[str], float, bool]] = [
    (
        "gift_cards",
        re.compile(r"\b(gift ?cards?|prepaid cards?|reload(able)? cards?|vouchers?)\b", re.I),
        0.9,
        True,
    ),
    ("read_code", re.compile(rf"\b{_SHARE}\b.{{0,40}}\b{_SECRET}\b", re.I), 0.9, True),
    ("read_code", re.compile(rf"\bwhat(?:'s| is| are)\b.{{0,20}}\b{_SECRET}\b", re.I), 0.85, True),
    (
        "safe_account",
        re.compile(r"\b(safe|secure|protected|holding)\s+(vault\s+)?account\b", re.I),
        0.9,
        True,
    ),
    (
        "safe_account",
        re.compile(r"\b(move|transfer|send)\b.{0,30}\b(balance|savings|funds|all of it)\b", re.I),
        0.7,
        True,
    ),
    (
        "remote_access",
        re.compile(r"\b(anydesk|teamviewer|quick ?assist|remote access|screen ?share)\b", re.I),
        0.9,
        True,
    ),
    (
        "remote_access",
        re.compile(r"\b(control of|access to|into) your (computer|pc|device|phone|screen)\b", re.I),
        0.8,
        True,
    ),
    ("policy_contradiction", re.compile(r"\brefunds?\b.{0,60}\bgift ?cards?\b", re.I), 0.85, True),
    ("urgency_secrecy", re.compile(r"\b(don'?t|do not) (hang up|tell|call)\b", re.I), 0.7, False),
    (
        "urgency_secrecy",
        re.compile(r"\b(warrant|arrest(ed)?|deported|shut ?off|disconnected)\b", re.I),
        0.6,
        True,
    ),
    ("urgency_secrecy", re.compile(r"\b(confidential|keep this|stay on the line)\b", re.I), 0.6, False),
]

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _negated(text_before_match: str) -> bool:
    """True if a negation governs the match: same clause, and not a reassurance like "don't worry"."""
    clause = _CLAUSE_BREAK.split(text_before_match)[-1]
    return bool(_NEGATION.search(_REASSURANCE.sub("", clause)))


def flag_turn(event: object) -> list[Flag]:
    """Flags raised by one caller turn. Customer turns and non-turn events produce nothing."""
    if not isinstance(event, Turn) or event.speaker != "caller":
        return []
    flags: list[Flag] = []
    seen: set[FlagKind] = set()
    for sentence in _SENTENCE.split(event.text):
        for kind, pattern, confidence, negatable in _RULES:
            match = pattern.search(sentence)
            if kind in seen or match is None:
                continue
            if negatable and _negated(sentence[: match.start()]):
                continue
            seen.add(kind)
            flags.append(Flag(kind=kind, quote=sentence[:200], t=event.t, confidence=confidence))
    return flags
