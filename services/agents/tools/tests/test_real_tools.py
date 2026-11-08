"""Real adapters against fake HTTP (httpx.MockTransport). Nothing leaves the process."""

from __future__ import annotations

import json

import httpx
import pytest

from contracts.interfaces import Account, Comms, Store, Voice
from services.agents.tools import real_tools
from services.agents.tools.demo import DemoStore, SimAccount
from services.agents.tools.elevenlabs import OUTBOUND_URL, ElevenLabsVoice
from services.agents.tools.errors import ToolConfigError, ToolError, ToolUnsupported
from services.agents.tools.photon import PhotonComms, Sidecar

CUSTOMER = "+15555550100"  # synthetic (R10)
BANK_AGENT, SCAMMER_AGENT = "agent_bank", "agent_scammer"


class Recorder:
    def __init__(self, status: int = 200, body: dict | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.status, self.body = status, body or {"ok": True, "message_id": "pho_msg_1"}

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        if req.url == OUTBOUND_URL:
            return httpx.Response(self.status, json={"success": True, "conversation_id": "conv_1"})
        return httpx.Response(self.status, json=self.body)

    def json(self, i: int = -1) -> dict:
        return json.loads(self.requests[i].content)


def build(rec: Recorder, bank_agent: str = BANK_AGENT) -> tuple[PhotonComms, ElevenLabsVoice]:
    client = httpx.Client(transport=httpx.MockTransport(rec))
    sidecar = Sidecar("http://sidecar.test", client)
    voice = ElevenLabsVoice(
        api_key="k",
        bank_agent_id=bank_agent,
        scammer_agent_id=SCAMMER_AGENT,
        phone_number_id="phnum_1",
        customer_number=CUSTOMER,
        send_text=lambda sid, text: sidecar.post(
            "/message", {"to": CUSTOMER, "text": text, "session_id": sid}
        ),
        client=client,
    )
    return PhotonComms(sidecar=sidecar, voice=voice, customer_number=CUSTOMER), voice


def test_notify_sends_numbered_buttons_to_customer() -> None:
    rec = Recorder()
    comms, _ = build(rec)
    mid = comms.notify(
        "s1", "customer", "This may be a scam.", ["call_bank", "ask_trusted_contact", "continue"]
    )
    assert mid == "pho_msg_1"
    assert rec.requests[0].url.path == "/notify"
    body = rec.json()
    assert body["to"] == CUSTOMER and body["session_id"] == "s1"
    assert body["choices"] == ["1", "2", "3"]
    assert body["buttons"] == ["call_bank", "ask_trusted_contact", "continue"]
    assert "Reply 1 to call your bank for me" in body["text"]


def test_every_role_goes_to_customer() -> None:
    rec = Recorder()
    comms, _ = build(rec)
    comms.message("s1", "trusted_contact", "check in")
    assert rec.requests[0].url.path == "/message" and rec.json()["to"] == CUSTOMER


def test_sidecar_error_is_a_tool_error() -> None:
    comms, _ = build(Recorder(status=502, body={"error": "x"}))
    with pytest.raises(ToolError):
        comms.message("s1", "customer", "hi")


def test_callback_uses_bank_agent() -> None:
    rec = Recorder()
    comms, _ = build(rec)
    assert comms.call("s1", "customer", "This is Lone Star Bank calling back.") == "conv_1"
    body = rec.json()
    assert str(rec.requests[0].url) == OUTBOUND_URL
    assert body["agent_id"] == BANK_AGENT and body["to_number"] == CUSTOMER
    assert body["conversation_initiation_client_data"]["dynamic_variables"]["session_id"] == "s1"


@pytest.mark.parametrize("bank_agent", ["", SCAMMER_AGENT])
def test_callback_refuses_without_bank_agent(bank_agent: str) -> None:
    rec = Recorder()
    comms, _ = build(rec, bank_agent=bank_agent)
    with pytest.raises(ToolConfigError, match="ELEVENLABS_BANK_AGENT_ID"):
        comms.call("s1", "customer", "script")
    assert rec.requests == []  # nothing placed


def test_whisper_goes_out_as_text() -> None:
    rec = Recorder()
    _, voice = build(rec)
    voice.whisper("s1", "Be careful: a bank code arrived during this call.")
    assert rec.requests[0].url.path == "/message"


def test_transfer_unsupported_and_emergency_refused() -> None:
    comms, _ = build(Recorder())
    with pytest.raises(ToolUnsupported):
        comms.transfer("s1", "conv_1", "+18005550199")
    with pytest.raises(ToolError, match="R1"):
        comms.transfer("s1", "conv_1", "911")
    with pytest.raises(ToolError, match="R1"):
        PhotonComms(sidecar=Sidecar("http://x"), voice=build(Recorder())[1], customer_number="988")


def test_demo_store_and_sim_account() -> None:
    s = DemoStore(bank_number="+15555550199")
    assert s.lookup_verified("+15555550199") == "Lone Star Bank"
    assert s.official_number("Lone Star Bank") == "+15555550199"
    s.append_event("s1", {"kind": "turn", "text": "x"})
    assert s.events == []  # R8
    assert SimAccount().hold_changes("s1", ["sim_change"], 60).startswith("sim-hold-")


def test_real_tools_wires_protocols(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.agents.tools.load_dotenv", lambda: None)
    monkeypatch.setenv("PHOTON_SIDECAR_URL", "http://sidecar.test")
    monkeypatch.setenv("DEMO_CUSTOMER_NUMBER", CUSTOMER)
    t = real_tools(httpx.Client(transport=httpx.MockTransport(Recorder())))
    comms: Comms = t.comms
    voice: Voice = t.voice
    store: Store = t.store
    account: Account = t.account
    assert isinstance(comms, PhotonComms) and isinstance(voice, ElevenLabsVoice)
    assert isinstance(store, DemoStore) and isinstance(account, SimAccount)


def test_real_tools_fails_clearly_without_sidecar(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.agents.tools.load_dotenv", lambda: None)
    monkeypatch.delenv("PHOTON_SIDECAR_URL", raising=False)
    with pytest.raises(ToolConfigError, match="PHOTON_SIDECAR_URL"):
        real_tools()
