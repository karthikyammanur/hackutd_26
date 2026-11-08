"""A real Scammer Simulator call, followed live inside the API.

POST /calls/start places the call from the Scammer Simulator agent (ElevenLabs, SIP trunk) to
DEMO_CUSTOMER_NUMBER only (R10: never a number from the request), then follow() polls the conversation every
second and feeds call_start, each new transcript line as a `turn`, and call_end into the session.

R8: transcript text only passes through memory into the graph. It is never logged or written anywhere.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx

from contracts.events import CallEnd, CallStart, Direction, Source, Turn
from services.agents.tools.errors import ToolConfigError

log = logging.getLogger(__name__)

EL = "https://api.elevenlabs.io/v1/convai"
DONE = ("done", "failed")
SETTLE_POLLS = 2  # the newest line can still be growing; send it once it is unchanged this many polls
POLL_S = 1.0
MAX_CALL_S = 15 * 60  # stop following a call that never reports an end
NEED = ("ELEVENLABS_API_KEY", "SCAMMER_AGENT_ID", "ELEVENLABS_PHONE_NUMBER_ID", "DEMO_CUSTOMER_NUMBER")


def speaker(role: str) -> str:
    """ElevenLabs 'agent' is the Scammer Simulator (the caller); 'user' is the customer."""
    return "caller" if role == "agent" else "customer"


class Transcript:
    """Turns ElevenLabs transcript snapshots into new, final turns, each sent once."""

    def __init__(self) -> None:
        self.sent = 0  # entries already sent
        self.last_text = ""
        self.stable = 0

    def new_turns(self, entries: list[dict[str, Any]], final: bool) -> list[tuple[float, str, str]]:
        entries = [
            e for e in entries if (e.get("message") or "").strip() and e.get("role") in ("agent", "user")
        ]
        ready = len(entries) if final else max(len(entries) - 1, self.sent)
        if not final and len(entries) > self.sent:
            newest = entries[-1]["message"]
            self.stable = self.stable + 1 if newest == self.last_text else 0
            self.last_text = newest
            if self.stable >= SETTLE_POLLS:
                ready = len(entries)
        out = [
            (float(e.get("time_in_call_secs") or 0), speaker(e["role"]), e["message"].strip())
            for e in entries[self.sent : ready]
        ]
        self.sent = max(self.sent, ready)
        return out


def config() -> dict[str, str]:
    """The env the call needs. Raises ToolConfigError naming the first missing variable."""
    env = {k: os.environ.get(k, "").strip() for k in NEED}
    for k, v in env.items():
        if not v:
            raise ToolConfigError(f"{k} is not set")
    return env


def client(env: dict[str, str]) -> httpx.AsyncClient:
    return httpx.AsyncClient(headers={"xi-api-key": env["ELEVENLABS_API_KEY"]}, timeout=20)


async def caller_number(el: httpx.AsyncClient, env: dict[str, str]) -> str:
    r = await el.get(f"{EL}/phone-numbers/{env['ELEVENLABS_PHONE_NUMBER_ID']}")
    r.raise_for_status()
    return r.json().get("phone_number") or "unknown"


async def place_call(el: httpx.AsyncClient, env: dict[str, str]) -> str:
    """Dial the demo customer from the Scammer Simulator. Returns the ElevenLabs conversation id."""
    r = await el.post(
        f"{EL}/sip-trunk/outbound-call",
        json={
            "agent_id": env["SCAMMER_AGENT_ID"],
            "agent_phone_number_id": env["ELEVENLABS_PHONE_NUMBER_ID"],
            "to_number": env["DEMO_CUSTOMER_NUMBER"],
        },
    )
    r.raise_for_status()
    conv = r.json().get("conversation_id")
    if not conv:
        raise RuntimeError("ElevenLabs placed the call but returned no conversation_id")
    return str(conv)


async def fetch(el: httpx.AsyncClient, conv: str) -> dict[str, Any]:
    r = await el.get(f"{EL}/conversations/{conv}")
    r.raise_for_status()
    return r.json()


def call_start(session_id: str, number: str) -> CallStart:
    return CallStart(
        session_id=session_id,
        t=0,
        source=Source.network,
        direction=Direction.inbound,
        number=number,
        first_seen=True,
    )


async def follow(submit: Any, session_id: str, el: httpx.AsyncClient, conv: str) -> None:
    """Poll the conversation and submit each new turn, then call_end. Always ends the call in the graph."""
    tx = Transcript()
    last_t = 0.0
    duration = 0.0
    loop = asyncio.get_running_loop()
    started = loop.time()
    try:
        while loop.time() - started < MAX_CALL_S:
            try:
                d = await fetch(el, conv)
            except httpx.HTTPError as e:  # a blip: try again next poll
                log.warning("conversation poll failed: %s", type(e).__name__)
                await asyncio.sleep(POLL_S)
                continue
            final = d.get("status") in DONE
            for t, who, text in tx.new_turns(d.get("transcript") or [], final):
                last_t = max(last_t, t)
                submit(Turn(session_id=session_id, t=t, source=Source.network, speaker=who, text=text))  # type: ignore[arg-type]
            if final:
                duration = float((d.get("metadata") or {}).get("call_duration_secs") or 0)
                log.info("call %s ended (%s), %d turns", session_id, d.get("status"), tx.sent)
                break
            await asyncio.sleep(POLL_S)
    finally:
        submit(CallEnd(session_id=session_id, t=max(last_t + 1, duration), source=Source.network))
        await el.aclose()
