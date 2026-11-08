"""FCM alerts to the Intercept APK: message shape, level per alert, and one route failing never blocks the other."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from services.agents.tools.errors import ToolError
from services.agents.tools.fcm import Fcm, FcmComms, FcmVoice


def _fcm(sent: list[dict[str, Any]], status: int = 200, device_token: str = "") -> Fcm:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.headers["authorization"] == "Bearer tok"
        sent.append(json.loads(req.content))
        return httpx.Response(status, json={"name": "projects/p/messages/0:123"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return Fcm(project_id="p", token=lambda: "tok", device_token=device_token, client=client)


class Inner:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[str] = []

    def _do(self, what: str) -> str:
        self.calls.append(what)
        if self.fail:
            raise ToolError("sidecar down")
        return f"inner-{what}"

    def notify(self, session_id: str, to: str, text: str, buttons: list[str]) -> str:
        return self._do("notify")

    def message(self, session_id: str, to: str, text: str) -> str:
        return self._do(f"message:{to}")

    def call(self, session_id: str, to: str, script: str) -> str:
        return self._do("call")

    def transfer(self, session_id: str, call_id: str, to_number: str) -> str:
        return self._do("transfer")

    def whisper(self, session_id: str, text: str) -> str:
        return self._do("whisper")


def test_message_shape_matches_the_apk() -> None:
    sent: list[dict[str, Any]] = []
    _fcm(sent).send("urgent", "Stop", "The caller asked for your card number.", "during-call")
    m = sent[0]["message"]
    assert m["topic"] == "tlife"
    assert m["notification"] == {"title": "Stop", "body": "The caller asked for your card number."}
    assert m["data"]["level"] == "urgent" and m["data"]["timing"] == "during-call"
    assert m["android"]["notification"]["channel_id"] == "guardian_notices"
    sent.clear()
    _fcm(sent, device_token="dev").send("quiet", "t", "b", "during-call")
    assert sent[0]["message"]["token"] == "dev" and "topic" not in sent[0]["message"]


def test_each_alert_goes_out_at_its_level() -> None:
    sent: list[dict[str, Any]] = []
    fcm = _fcm(sent)
    comms, voice = FcmComms(Inner(), fcm), FcmVoice(Inner(), fcm)
    voice.whisper("s", "Take a moment.")
    comms.notify("s", "customer", "The caller asked for your card number.", ["call_bank"])
    comms.message("s", "customer", "1. Block the card.")
    comms.call("s", "customer", "script")
    comms.message("s", "trusted_contact", "check in")  # not to the customer's phone
    assert [m["message"]["data"]["level"] for m in sent] == ["warning", "urgent", "summary", "callback"]


def test_one_route_down_still_delivers() -> None:
    sent: list[dict[str, Any]] = []
    comms = FcmComms(Inner(fail=True), _fcm(sent))
    assert comms.notify("s", "customer", "x", []).startswith("fcm:")  # sidecar down, APK still alerted
    broken = FcmComms(Inner(), _fcm([], status=500))
    assert broken.notify("s", "customer", "x", []) == "inner-notify"  # FCM down, iMessage still sent
    with pytest.raises(ToolError):
        FcmComms(Inner(fail=True), _fcm([], status=500)).notify("s", "customer", "x", [])


def test_no_callback_notice_when_the_call_was_not_placed() -> None:
    sent: list[dict[str, Any]] = []
    with pytest.raises(ToolError):
        FcmComms(Inner(fail=True), _fcm(sent)).call("s", "customer", "script")
    assert sent == []


def test_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("FCM_SERVICE_ACCOUNT_FILE", "FCM_ACCESS_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    assert Fcm.from_env() is None  # not configured: the API runs without it
    monkeypatch.setenv("FCM_ACCESS_TOKEN", "abc")
    assert Fcm.from_env() is not None
