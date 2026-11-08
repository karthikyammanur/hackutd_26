"""Alerts to the Intercept APK (com.guardian.guardian) by Firebase Cloud Messaging, HTTP v1.

The APK subscribes every install to topic `tlife` and reads `data.level` for the look of each notice
(quiet, warning, urgent, summary, callback), on channel `guardian_notices`. See the APK's notification doc.

FcmComms and FcmVoice wrap the existing adapters: every customer-facing alert also goes to the APK, and a
failure on one route never blocks the other. Messages to the trusted contact stay off FCM: the topic reaches the
customer's phone, not theirs. Nothing here can hang up a call (R2).

Env: FCM_SERVICE_ACCOUNT_FILE (a Firebase service-account JSON for the project) or FCM_ACCESS_TOKEN (a
short-lived OAuth token, about an hour), FCM_PROJECT_ID (default guardian-push-2026), and FCM_DEVICE_TOKEN to
target one phone instead of FCM_TOPIC (default tlife).
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from typing import Literal

import httpx

from contracts.interfaces import Comms, Voice
from services.agents.tools.errors import ToolConfigError, ToolError

log = logging.getLogger(__name__)

Level = Literal["quiet", "warning", "urgent", "summary", "callback"]
Timing = Literal["during-call", "after-call"]

SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
CHANNEL_ID = "guardian_notices"
CUSTOMER = "customer"
MAX_BODY = 900  # FCM caps the whole message at 4 KB; the APK shows two lines in the banner anyway


def service_account_token(path: str) -> Callable[[], str]:
    """Access tokens from a service-account file, refreshed when they expire."""
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_file(path, scopes=[SCOPE])  # type: ignore[no-untyped-call]
    lock = threading.Lock()

    def token() -> str:
        with lock:
            if not creds.valid:
                creds.refresh(Request())
            return str(creds.token)

    return token


class Fcm:
    def __init__(
        self,
        *,
        project_id: str,
        token: Callable[[], str],
        topic: str = "tlife",
        device_token: str = "",
        client: httpx.Client | None = None,
    ) -> None:
        self._url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
        self._token = token
        self._target = {"token": device_token} if device_token else {"topic": topic}
        self._client = client or httpx.Client(timeout=5)

    @classmethod
    def from_env(cls, client: httpx.Client | None = None) -> Fcm | None:
        """None when FCM is not configured, so the API still runs on the other routes."""
        path = os.environ.get("FCM_SERVICE_ACCOUNT_FILE", "").strip()
        static = os.environ.get("FCM_ACCESS_TOKEN", "").strip()
        if not path and not static:
            return None
        if path and not os.path.isfile(path):
            raise ToolConfigError("FCM_SERVICE_ACCOUNT_FILE does not point to a file")
        return cls(
            project_id=os.environ.get("FCM_PROJECT_ID", "").strip() or "guardian-push-2026",
            token=service_account_token(path) if path else (lambda: static),
            topic=os.environ.get("FCM_TOPIC", "").strip() or "tlife",
            device_token=os.environ.get("FCM_DEVICE_TOKEN", "").strip(),
            client=client,
        )

    def message(self, level: Level, title: str, body: str, timing: Timing) -> dict:
        body = body[:MAX_BODY]
        channel = "urgent-callback" if level == "callback" else "t-life"
        return {
            "message": {
                **self._target,
                "notification": {"title": title, "body": body},
                "data": {"level": level, "channel": channel, "timing": timing, "title": title, "body": body},
                "android": {"priority": "high", "notification": {"channel_id": CHANNEL_ID}},
            }
        }

    def send(self, level: Level, title: str, body: str, timing: Timing) -> str:
        try:
            r = self._client.post(
                self._url,
                headers={"Authorization": f"Bearer {self._token()}"},
                json=self.message(level, title, body, timing),
            )
        except httpx.HTTPError as e:
            raise ToolError(f"FCM unreachable: {type(e).__name__}") from e
        if r.status_code >= 300:
            raise ToolError(f"FCM returned {r.status_code}: {r.text[:200]}")
        name = str(r.json().get("name", ""))
        log.info("fcm %s sent (%s)", level, name.rsplit("/", 1)[-1])
        return f"fcm:{name.rsplit('/', 1)[-1]}"


def both(fcm_send: Callable[[], str], inner: Callable[[], str]) -> str:
    """Send on both routes. Succeeds if either does; raises the inner route's error if both fail."""
    ids: list[str] = []
    errors: list[Exception] = []
    for send in (fcm_send, inner):
        try:
            ids.append(send())
        except Exception as e:
            log.warning("one alert route failed: %s", e)
            errors.append(e)
    if not ids:
        raise errors[-1]
    return " + ".join(ids)


class FcmComms:
    """Comms that also alerts the APK. The phone call and transfer go only through the inner adapter."""

    def __init__(self, inner: Comms, fcm: Fcm) -> None:
        self._inner = inner
        self._fcm = fcm

    def notify(self, session_id: str, to: str, text: str, buttons: list[str]) -> str:
        if to != CUSTOMER:
            return self._inner.notify(session_id, to, text, buttons)
        return both(
            lambda: self._fcm.send("urgent", "Stop: this call is a scam", text, "during-call"),
            lambda: self._inner.notify(session_id, to, text, buttons),
        )

    def message(self, session_id: str, to: str, text: str) -> str:
        if to != CUSTOMER:
            return self._inner.message(session_id, to, text)
        return both(
            lambda: self._fcm.send("summary", "After your call: what to do now", text, "after-call"),
            lambda: self._inner.message(session_id, to, text),
        )

    def call(self, session_id: str, to: str, script: str) -> str:
        call_id = self._inner.call(
            session_id, to, script
        )  # a failed call raises; no notice for a call not placed
        try:
            self._fcm.send(
                "callback",
                "Safe Signal is calling you",
                "Answer to be connected to your bank on its real number. We will never ask for your card or a code.",
                "after-call",
            )
        except Exception as e:
            log.warning("callback notice failed: %s", e)
        return call_id

    def transfer(self, session_id: str, call_id: str, to_number: str) -> str:
        return self._inner.transfer(session_id, call_id, to_number)


class FcmVoice:
    """Voice whose whisper also reaches the APK as a warning. The callback call is unchanged."""

    def __init__(self, inner: Voice, fcm: Fcm) -> None:
        self._inner = inner
        self._fcm = fcm

    def whisper(self, session_id: str, text: str) -> str:
        return both(
            lambda: self._fcm.send("warning", "Be careful on this call", text, "during-call"),
            lambda: self._inner.whisper(session_id, text),
        )

    def __getattr__(self, name: str) -> object:  # callback() and the rest of the inner voice
        return getattr(self._inner, name)
