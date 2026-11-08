"""ElevenLabsVoice: the bank callback call and the whisper.

callback() places an outbound call from the BANK agent (ELEVENLABS_BANK_AGENT_ID) to the customer over the
SIP trunk (ELEVENLABS_PHONE_NUMBER_ID). It never uses the scammer agent: if the bank agent ID is unset or equals
SCAMMER_AGENT_ID, it raises ToolConfigError and places nothing.

whisper(): we cannot inject audio into a live call we didn't place (F8), so the whisper goes to the customer
as a text through `send_text` (the sidecar). Nothing is synthesised or written to disk (R8).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

import httpx

from services.agents.tools.errors import ToolConfigError, ToolError, guard_not_emergency, mask

log = logging.getLogger(__name__)

OUTBOUND_URL = "https://api.elevenlabs.io/v1/convai/sip-trunk/outbound-call"


class ElevenLabsVoice:
    def __init__(
        self,
        *,
        api_key: str,
        bank_agent_id: str,
        scammer_agent_id: str,
        phone_number_id: str,
        customer_number: str,
        send_text: Callable[[str, str], str],
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._bank_agent_id = bank_agent_id
        self._scammer_agent_id = scammer_agent_id
        self._phone_number_id = phone_number_id
        self._customer = customer_number
        self._send_text = send_text
        self._http = client or httpx.Client(timeout=30)

    @classmethod
    def from_env(
        cls, send_text: Callable[[str, str], str], client: httpx.Client | None = None
    ) -> ElevenLabsVoice:
        env = lambda n: os.environ.get(n, "").strip()  # noqa: E731
        return cls(
            api_key=env("ELEVENLABS_API_KEY"),
            bank_agent_id=env("ELEVENLABS_BANK_AGENT_ID"),
            scammer_agent_id=env("SCAMMER_AGENT_ID"),
            phone_number_id=env("ELEVENLABS_PHONE_NUMBER_ID"),
            customer_number=env("DEMO_CUSTOMER_NUMBER"),
            send_text=send_text,
            client=client,
        )

    def _check_callback_config(self) -> None:
        missing = [
            name
            for name, value in (
                ("ELEVENLABS_API_KEY", self._api_key),
                ("ELEVENLABS_BANK_AGENT_ID", self._bank_agent_id),
                ("ELEVENLABS_PHONE_NUMBER_ID", self._phone_number_id),
                ("DEMO_CUSTOMER_NUMBER", self._customer),
            )
            if not value
        ]
        if missing:
            raise ToolConfigError(f"callback not placed: set {', '.join(missing)}")
        if self._bank_agent_id == self._scammer_agent_id:
            raise ToolConfigError(
                "callback not placed: ELEVENLABS_BANK_AGENT_ID is the scammer agent; set it to the bank agent"
            )

    def callback(self, session_id: str, script: str) -> str:
        """Call the customer from the bank agent. Returns the ElevenLabs conversation id."""
        self._check_callback_config()
        guard_not_emergency(self._customer)
        r = self._http.post(
            OUTBOUND_URL,
            headers={"xi-api-key": self._api_key},
            json={
                "agent_id": self._bank_agent_id,
                "agent_phone_number_id": self._phone_number_id,
                "to_number": self._customer,
                # The bank agent's prompt reads {{callback_script}}; session_id ties the call to the session.
                "conversation_initiation_client_data": {
                    "dynamic_variables": {"callback_script": script, "session_id": session_id}
                },
            },
        )
        if r.status_code != 200:
            raise ToolError(f"ElevenLabs outbound call failed: HTTP {r.status_code}")
        body = r.json()
        call_id = body.get("conversation_id") or body.get("callSid") or ""
        if not call_id:
            raise ToolError("ElevenLabs accepted the call but returned no conversation id")
        log.info(
            "callback placed session=%s to=%s conversation=%s", session_id, mask(self._customer), call_id
        )
        return str(call_id)

    def whisper(self, session_id: str, text: str) -> str:
        return self._send_text(session_id, text)
