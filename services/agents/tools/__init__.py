"""Lane 4 tools. `real_tools()` wires the live adapters; `mock.mock_tools()` gives in-memory fakes."""

from __future__ import annotations

import os

import httpx
from dotenv import load_dotenv

from services.agents.graph import stubs
from services.agents.graph.deps import Tools
from services.agents.tools.demo import DemoStore, SimAccount
from services.agents.tools.elevenlabs import ElevenLabsVoice
from services.agents.tools.photon import PhotonComms, Sidecar


def real_tools(client: httpx.Client | None = None) -> Tools:
    """Live Photon (via the sidecar) + ElevenLabs, with the in-memory DemoStore and SimAccount.

    Missing env fails here for the sidecar URL and customer number; the bank agent is checked when a callback
    is placed, so alerts still work without it. The decider is Lane 1's stand-in until Lane 2's lands.
    """
    load_dotenv()
    sidecar = Sidecar(os.environ.get("PHOTON_SIDECAR_URL", "").strip(), client)
    customer = os.environ.get("DEMO_CUSTOMER_NUMBER", "").strip()
    voice = ElevenLabsVoice.from_env(
        send_text=lambda sid, text: sidecar.post(
            "/message", {"to": customer, "text": text, "session_id": sid}
        ),
        client=client,
    )
    return Tools(
        decider=stubs.decide,
        comms=PhotonComms.from_env(sidecar, voice),
        voice=voice,
        store=DemoStore.from_env(),
        account=SimAccount(),
    )
