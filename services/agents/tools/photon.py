"""PhotonComms: alerts and messages through the Photon sidecar (spikes/photon/sidecar.ts), calls through ElevenLabs.

The graph names recipients by role ("customer", "trusted_contact"). In the demo every role goes to
DEMO_CUSTOMER_NUMBER (R10: a teammate's own phone). The customer must have texted the Photon line once first,
or the shared line cannot reach them (docs/integrations.md).

notify() sends the buttons as a numbered list; the sidecar maps a reply of "1"/"2"/"3" back to the button id
and posts it to the API's /sessions/{id}/choice. No method here can hang up a call (R2).
"""

from __future__ import annotations

import logging
import os
import re

import httpx

from services.agents.tools.elevenlabs import ElevenLabsVoice
from services.agents.tools.errors import (
    ToolConfigError,
    ToolError,
    ToolUnsupported,
    demo_number,
    guard_not_emergency,
    mask,
)

log = logging.getLogger(__name__)

BUTTON_LABELS: dict[str, str] = {
    "call_bank": "call your bank for me",
    "ask_trusted_contact": "ask a trusted contact",
    "continue": "continue the call",
}


def button_menu(buttons: list[str]) -> str:
    return "\n".join(
        f"Reply {i} to {BUTTON_LABELS.get(b, b.replace('_', ' '))}" for i, b in enumerate(buttons, 1)
    )


class Sidecar:
    """HTTP client for the Photon sidecar."""

    def __init__(self, base_url: str, client: httpx.Client | None = None) -> None:
        if not base_url:
            raise ToolConfigError("set PHOTON_SIDECAR_URL (e.g. http://localhost:8787)")
        self._base = base_url.rstrip("/")
        self._http = client or httpx.Client(timeout=20)

    def post(self, path: str, body: dict) -> str:
        try:
            r = self._http.post(f"{self._base}{path}", json=body)
        except httpx.HTTPError as exc:
            raise ToolError(f"sidecar unreachable at {self._base}: {type(exc).__name__}") from exc
        if r.status_code != 200:
            raise ToolError(f"sidecar {path} failed: HTTP {r.status_code} {r.text[:200]}")
        return str(r.json().get("message_id", ""))


class PhotonComms:
    def __init__(
        self, *, sidecar: Sidecar, voice: ElevenLabsVoice, customer_number: str, bank_number: str = ""
    ) -> None:
        if not customer_number:
            raise ToolConfigError("set DEMO_CUSTOMER_NUMBER")
        guard_not_emergency(customer_number)
        if bank_number:
            guard_not_emergency(bank_number)
        self._sidecar = sidecar
        self._voice = voice
        self._customer = customer_number
        self._bank = bank_number  # the follow-up agent's transfer_to_number destination (DEMO_BANK_NUMBER)

    @classmethod
    def from_env(cls, sidecar: Sidecar, voice: ElevenLabsVoice) -> PhotonComms:
        return cls(
            sidecar=sidecar,
            voice=voice,
            customer_number=demo_number("DEMO_CUSTOMER_NUMBER", os.environ.get("DEMO_CUSTOMER_NUMBER", "")),
            bank_number=demo_number("DEMO_BANK_NUMBER", os.environ.get("DEMO_BANK_NUMBER", "")),
        )

    def _number_for(self, role: str) -> str:
        """Every role maps to the customer's phone in the demo."""
        return self._customer

    def notify(self, session_id: str, to: str, text: str, buttons: list[str]) -> str:
        number = self._number_for(to)
        body = f"{text}\n\n{button_menu(buttons)}" if buttons else text
        mid = self._sidecar.post(
            "/notify",
            {
                "to": number,
                "text": body,
                "session_id": session_id,
                "choices": [str(i) for i in range(1, len(buttons) + 1)],
                "buttons": buttons,
            },
        )
        log.info("notify session=%s role=%s to=%s msg=%s", session_id, to, mask(number), mid)
        return mid

    def message(self, session_id: str, to: str, text: str) -> str:
        number = self._number_for(to)
        mid = self._sidecar.post("/message", {"to": number, "text": text, "session_id": session_id})
        log.info("message session=%s role=%s to=%s msg=%s", session_id, to, mask(number), mid)
        return mid

    def call(self, session_id: str, to: str, script: str) -> str:
        return self._voice.callback(session_id, script)

    def transfer(self, session_id: str, call_id: str, to_number: str) -> str:
        """Our code cannot transfer a live call (F8). The follow-up agent can: its transfer_to_number tool is
        set to DEMO_BANK_NUMBER and connects the customer only when they say yes. So this just records that."""
        guard_not_emergency(to_number)
        digits = re.sub(r"\D", "", to_number)
        if not self._bank or digits[-10:] != re.sub(r"\D", "", self._bank)[-10:]:
            raise ToolUnsupported("the follow-up agent only transfers to DEMO_BANK_NUMBER (F8)")
        log.info(
            "transfer offered session=%s call=%s to=%s (agent connects on yes)",
            session_id,
            call_id,
            mask(to_number),
        )
        return f"agent-transfer-on-yes:{call_id}"
