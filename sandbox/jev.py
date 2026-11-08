"""TypeSafe Jev client: one request per microframe, three danger tiers plus narrow red-flag questions.

The red-flag questions come from test/jev-lab/scam.ts. The tier is Jev's own answer; the flags are recorded
so the review step can explain which signals were missing when a call was scored wrong.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

API = "https://api.typesafe.ai/v1"
Tier = Literal["safe", "uncertain", "dangerous"]
TIER_RANK: dict[str, int] = {"safe": 0, "uncertain": 1, "dangerous": 2}

FLAGS: dict[str, tuple[str, str, str]] = {
    "asks_for_code": (
        "Is the CALLER asking the customer to read out, type, or share a one-time code, verification "
        "number, or digits that were just sent to their phone?",
        "Any request to read back or share a code or digits that arrived by text, even if worded vaguely",
        "No such request, or the caller says they will never ask for a code",
    ),
    "asks_for_pin_or_password": (
        "Is the CALLER asking for an account PIN, passcode, password, or security answer?",
        "Asks for a PIN, passcode, password, the last digits of an account number, or a secret answer",
        "No such request",
    ),
    "asks_to_move_money": (
        "Is the CALLER asking the customer to move, transfer, wire, or withdraw money to a 'safe', "
        "'secure', 'holding', or new account, or to hand cash to a courier?",
        "Any instruction to move money somewhere for protection or to a new recipient",
        "No request to move money",
    ),
    "asks_for_gift_cards": (
        "Is the CALLER asking for payment with gift cards, store cards, or prepaid vouchers, or to read "
        "numbers off the back of a card?",
        "Gift cards, store vouchers, prepaid cards, or reading card numbers aloud",
        "No gift card or voucher payment",
    ),
    "asks_for_crypto_or_wire": (
        "Is the CALLER asking for payment by cryptocurrency, a crypto ATM, a wire transfer, or a payment app?",
        "Crypto, bitcoin ATM, wire, Zelle, Cash App, or similar",
        "No such payment request",
    ),
    "asks_remote_access": (
        "Is the CALLER asking the customer to install an app or give remote access to their phone or "
        "computer?",
        "Install a remote-support app, share their screen, or let the caller control the device",
        "No such request",
    ),
    "asks_secrecy": (
        "Is the CALLER asking the customer to keep this secret, not tell family or the bank, or stay on "
        "the line and not hang up?",
        "Any instruction to hide it from others or not to hang up",
        "No secrecy request",
    ),
    "creates_urgency": (
        "Is the CALLER pressuring the customer to act immediately?",
        "Deadlines in minutes or hours, 'right now', 'before it's too late'",
        "No time pressure",
    ),
    "threatens": (
        "Is the CALLER threatening arrest, legal action, fines, frozen accounts, or cut-off service?",
        "Any threat of a bad consequence if the customer doesn't comply",
        "No threats",
    ),
    "claims_authority": (
        "Does the CALLER claim to be from a bank, the phone carrier, a government agency, a tech company, "
        "or the police?",
        "Claims to represent such an organization",
        "No such claim",
    ),
    "emotional_family_emergency": (
        "Does the CALLER claim to be a family member in an emergency (accident, arrest, hospital, "
        "stranded) who needs money?",
        "A relative in trouble asking for money",
        "No family emergency story",
    ),
    "verifies_safely": (
        "Does the CALLER tell the customer to hang up and call the official number on their card or the "
        "company's website, or say they will never ask for codes or PINs?",
        "Points the customer to an independent, official way to verify",
        "Does not",
    ),
}

DANGER_TIER = {
    "type": "choice",
    "instructions": "Based only on the call so far, which tier best describes the scam danger to the customer?",
    "criteria": {
        "safe": "A normal, legitimate conversation. Nothing is being asked that a real business, friend or "
        "relative would not ask",
        "uncertain": "Something is slightly off or could go either way, but there is no clear attempt yet to "
        "get money, codes, credentials or device access",
        "dangerous": "The caller is manipulating the customer toward losing money, codes, credentials or "
        "device access, including impersonating an organization or a relative",
    },
}


def build_questions() -> dict[str, dict]:
    questions: dict[str, dict] = {
        flag: {"type": "noul", "instructions": q, "criteria": {"true": yes, "false": no}}
        for flag, (q, yes, no) in FLAGS.items()
    }
    questions["danger_tier"] = DANGER_TIER
    return questions


class TierAnswer(BaseModel):
    choice: Tier
    confidence: float | None = None
    probabilities: dict[Tier, float]


class FlagAnswer(BaseModel):
    noul: float


@dataclass(frozen=True)
class JevResult:
    tier: Tier
    probabilities: dict[str, float]
    flags: dict[str, float]
    input_tokens: int
    output_tokens: int
    latency_ms: int


def parse_answer(body: dict, latency_ms: int) -> JevResult:
    answers = body["answers"]
    tier = TierAnswer.model_validate(answers["danger_tier"])
    flags = {name: FlagAnswer.model_validate(answers[name]).noul for name in FLAGS}
    usage = body.get("usage", {})
    return JevResult(
        tier=tier.choice,
        probabilities=dict(tier.probabilities),
        flags=flags,
        input_tokens=int(usage.get("input_tokens", 0)),
        output_tokens=int(usage.get("output_tokens", 0)),
        latency_ms=latency_ms,
    )


class JevError(RuntimeError):
    pass


class Jev:
    def __init__(self, api_key: str, model: str = "jev-latest", timeout_s: float = 15.0, attempts: int = 5):
        self._headers = {
            "authorization": f"Bearer {api_key}",
            "content-type": "application/json",
            "user-agent": "safe-signal-sandbox/0.1",
        }
        self._model = model
        self._timeout = timeout_s
        self._attempts = attempts
        self._questions = build_questions()

    def ping(self) -> None:
        request = urllib.request.Request(f"{API}/models", headers=self._headers)
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            names = [m["name"] for m in json.loads(response.read())["models"]]
        if self._model not in names:
            raise JevError(f"{self._model} not offered (found {names})")

    def classify(self, state: str) -> JevResult:
        payload = json.dumps({"model": self._model, "state": state, "questions": self._questions}).encode()
        last = "no attempts"
        for attempt in range(self._attempts):
            request = urllib.request.Request(
                f"{API}/systemone", data=payload, headers=self._headers, method="POST"
            )
            started = time.perf_counter()
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:
                    body = json.loads(response.read())
                return parse_answer(body, round((time.perf_counter() - started) * 1000))
            except urllib.error.HTTPError as exc:
                last = f"HTTP {exc.code}"
                if exc.code != 429 and exc.code < 500:
                    raise JevError(last) from exc
                retry_after = exc.headers.get("retry-after", "")
                delay = float(retry_after) if retry_after.isdigit() else 2**attempt
            except (urllib.error.URLError, TimeoutError) as exc:
                last = type(exc).__name__
                delay = 2**attempt
            except (KeyError, ValueError) as exc:  # includes Pydantic validation errors
                raise JevError(f"bad response: {type(exc).__name__}") from exc
            time.sleep(min(delay, 30))
        raise JevError(last)
