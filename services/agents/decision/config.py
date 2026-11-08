"""Weights and thresholds for the decision layer.

Tuned on data/train only (evals/tune.py). Never tune on data/eval: those numbers go on the Devpost.
"""

from __future__ import annotations

from typing import Final

from contracts.state import FlagKind

# Score needed to reach each level on the ladder.
NUDGE: Final = 0.25
WHISPER: Final = 0.50
ALERT: Final = 0.75

# R7: on a call the customer dialed to a verified number the score cannot pass this, so the level stays
# at or below nudge. Must stay under WHISPER (a test enforces it).
TRUSTED_CAP: Final = 0.49

# Flags that lift the R7 cap: no real bank or carrier asks for these. A weak LLM guess is not enough.
UNCAP_FLAGS: Final[frozenset[FlagKind]] = frozenset({"gift_cards", "safe_account", "remote_access"})
UNCAP_MIN_CONFIDENCE: Final = 0.8

# Call Guardian flags: contribution = weight x flag.confidence.
FLAG_WEIGHTS: Final[dict[FlagKind, float]] = {
    "gift_cards": 0.90,
    "read_code": 0.90,
    "safe_account": 0.90,
    "remote_access": 0.85,
    "policy_contradiction": 0.60,
    "urgency_secrecy": 0.35,
    "other": 0.20,
}

# Caller Screen.
WEIGHT_UNKNOWN_CALLER: Final = 0.10
WEIGHT_UNVERIFIED_CALLER: Final = 0.05
WEIGHT_SPOOF_SUSPECT: Final = 0.30  # inbound, shows a verified number, but the network doesn't attest it
WEIGHT_SCAM_LIST_HIT: Final = 0.80
ATTESTATION_ANOMALY: Final[dict[str, float]] = {"A": 0.0, "B": 0.05, "C": 0.15, "none": 0.20}
BURST_THRESHOLD: Final = 20  # distinct subscribers called by this number in the last hour
WEIGHT_BURST_ANOMALY: Final = 0.40

# Signal Watcher (Trigger A).
OTP_WEIGHT: Final[dict[str, float]] = {"bank_shortcode": 0.55, "other_shortcode": 0.40, "longcode": 0.15}
WEIGHT_BANK_APP: Final = 0.35
ACCOUNT_CHANGE_WEIGHT: Final[dict[str, float]] = {
    "sim_change": 0.70,
    "port_out": 0.70,
    "call_forwarding_on": 0.60,
}

# Jev adapter: leave room inside the 100 ms decision budget for the rule fallback.
JEV_TIMEOUT_S: Final = 0.08

SIGNAL_REASONS: Final[dict[str, str]] = {
    "unknown_caller": "First call from this number",
    "unverified_caller": "This number is not on the verified list",
    "otp_during_call": "A one-time code arrived during this call",
    "bank_app_during_call": "Your banking app was used during this call",
    "account_change_during_call": "A change to your phone account was attempted during this call",
    "scam_list_hit": "This number is on a scam list",
    "anomaly": "The network sees unusual activity from this number",
}

FLAG_REASONS: Final[dict[FlagKind, str]] = {
    "gift_cards": "The caller asked for gift cards or prepaid cards",
    "read_code": "The caller asked for a one-time code",
    "safe_account": "The caller asked you to move money to a 'safe' account",
    "remote_access": "The caller asked for access to your device",
    "policy_contradiction": "The caller said something that contradicts official policy",
    "urgency_secrecy": "The caller is pressuring you or asking you to keep this secret",
    "other": "The caller made an unusual request",
}
