"""L4-3 API: replay and live /events both stream UIMessages; same levels as the runner. Offline (no Brev)."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from contracts.events import EvalCase
from contracts.state import Level, SessionState, UIMessage
from services.agents.graph import stubs
from services.agents.graph.runner import replay_case
from services.agents.nodes.during import keyword_guardian
from services.agents.tools.errors import ToolConfigError
from services.agents.tools.mock import mock_tools
from services.api import hub as hub_module
from services.api.main import app

FIX = Path(__file__).resolve().parents[3] / "evals" / "fixtures"
GRAPH_ONLY = (
    "transcript_window",
    "turns_seen",
    "guardian_checked_t",
    "guardian_ok_t",
    "after_iterations",
    "cancel_request",
)


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    old = os.environ.get("TOOLS")
    os.environ["TOOLS"] = "mock"  # a local .env with TOOLS=real must never send real iMessages from tests
    with TestClient(app) as c:
        yield c
    if old is None:
        os.environ.pop("TOOLS", None)
    else:
        os.environ["TOOLS"] = old


def _case(name: str, session_id: str | None = None) -> dict[str, Any]:
    raw = json.loads((FIX / f"{name}.json").read_text())
    if session_id:
        raw["session_id"] = session_id
        for e in raw["events"]:
            e["session_id"] = session_id
    return raw


def _offline_levels(raw: dict[str, Any]) -> list[tuple[float, Level]]:
    final, _ = replay_case(
        EvalCase.model_validate(raw),
        stubs.fake_tools(),
        guardian=keyword_guardian,
        structured=stubs.offline_structured,
    )
    return [(a.t, a.level) for a in final.alerts]


def _read_until_done(ws: Any, limit: int = 400) -> list[str]:
    """Raw messages until the after phase finishes (sessions that reach aftercare only)."""
    out: list[str] = []
    for _ in range(limit):
        raw = ws.receive_text()
        out.append(raw)
        msg = UIMessage.model_validate_json(raw)
        if msg.trace and msg.trace.node == "router" and msg.trace.action == "all steps finished":
            out.append(ws.receive_text())  # the state message that follows the router's trace
            return out
    raise AssertionError("session did not finish")


def _wait_state(client: TestClient, sid: str, done: Any, timeout: float = 20) -> SessionState:
    end = time.time() + timeout
    while time.time() < end:
        state = SessionState.model_validate(client.get(f"/sessions/{sid}").json())
        if done(state):
            return state
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {sid}")


def test_health(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["ok"] is True and "sessions" in body


def test_cors_allows_vite_and_next(client: TestClient) -> None:
    for origin in ("http://localhost:5173", "http://localhost:3000"):
        r = client.options("/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
        assert r.headers.get("access-control-allow-origin") == origin


def test_replay_streams_uimessages_for_hero1(client: TestClient) -> None:
    with client.websocket_connect("/ws/fx_hero1_fake_bank") as ws:
        r = client.post("/sessions/hero1_fake_bank/replay?speed=1000&offline=true")
        assert r.status_code == 202 and r.json()["session_id"] == "fx_hero1_fake_bank"
        raws = _read_until_done(ws)
    msgs = [UIMessage.model_validate_json(x) for x in raws]
    assert {m.type for m in msgs} == {"event", "state", "trace"}
    final = [m.state for m in msgs if m.state][-1]
    assert final and max(a.level for a in final.alerts) == Level.alert
    assert [a for a in final.alerts if a.level == Level.alert][0].buttons == [
        "call_bank",
        "ask_trusted_contact",
        "continue",
    ]
    assert final.ended and [p.name for p in final.plan][-1] == "evidence"
    # R8: no graph-only field ever leaves the API, and no turn is sent after call_end
    assert not any(k in raw for raw in raws for k in GRAPH_ONLY)
    end_i = next(i for i, m in enumerate(msgs) if m.event and m.event.kind == "call_end")
    assert not [m for m in msgs[end_i:] if m.event and m.event.kind == "turn"]


def test_events_drive_hero1_to_the_same_levels_as_replay(client: TestClient) -> None:
    sid = "live_hero1"
    raw = _case("hero1_fake_bank", sid)
    expected = _offline_levels(raw)
    with client.websocket_connect(f"/ws/{sid}") as ws:
        for e in raw["events"]:
            if e["kind"] == "user_choice":  # the phone reply goes through /choice, as in the demo
                r = client.post(f"/sessions/{sid}/choice", json={"choice": "1"})
                assert r.status_code == 202 and r.json()["choice"] == "call_bank"
                continue
            q = "?offline=true" if e["kind"] == "call_start" else ""
            r = client.post(f"/sessions/{sid}/events{q}", json=e)
            assert r.status_code == 202, r.text
        _read_until_done(ws)
    final = _wait_state(client, sid, lambda s: s.ended and any(x.node == "evidence" for x in s.trace))
    assert [(a.t, a.level) for a in final.alerts] == expected
    assert final.user_choice == "call_bank"
    assert [p.name for p in final.plan] == ["lock_account", "callback", "recovery", "evidence"]


def test_real_bank_callback_through_events_stays_quiet(client: TestClient) -> None:
    sid = "live_real_bank"
    for e in _case("real_bank_callback", sid)["events"]:
        q = "?offline=true" if e["kind"] == "call_start" else ""
        assert client.post(f"/sessions/{sid}/events{q}", json=e).status_code == 202
    final = _wait_state(client, sid, lambda s: s.ended)
    assert max((a.level for a in final.alerts), default=Level.none) <= Level.nudge and final.plan == []


def test_event_errors(client: TestClient) -> None:
    turn = {
        "session_id": "nope",
        "t": 1,
        "source": "network",
        "kind": "turn",
        "speaker": "caller",
        "text": "hi",
    }
    assert client.post("/sessions/nope/events", json=turn).status_code == 404  # no call_start yet
    bad_kind = {**turn, "kind": "teleport"}
    assert client.post("/sessions/nope/events", json=bad_kind).status_code == 422
    assert client.post("/sessions/other/events", json=turn).status_code == 422  # id mismatch
    assert client.post("/sessions/nope/choice", json={"choice": "1"}).status_code == 404


def test_choice_mapping_and_late_events(client: TestClient) -> None:
    sid = "live_choices"
    start = {
        "session_id": sid,
        "t": 0,
        "source": "network",
        "kind": "call_start",
        "direction": "inbound",
        "number": "+15555550123",
        "first_seen": True,
    }
    assert client.post(f"/sessions/{sid}/events?offline=true", json=start).status_code == 202
    assert client.post(f"/sessions/{sid}/events", json=start).status_code == 409  # already running
    assert (
        client.post(f"/sessions/{sid}/choice", json={"choice": "2"}).json()["choice"] == "ask_trusted_contact"
    )
    assert client.post(f"/sessions/{sid}/choice", json={"choice": "continue"}).json()["choice"] == "continue"
    assert client.post(f"/sessions/{sid}/choice", json={"choice": "9"}).status_code == 422
    end = {"session_id": sid, "t": 5, "source": "network", "kind": "call_end"}
    assert client.post(f"/sessions/{sid}/events", json=end).status_code == 202
    late = {
        "session_id": sid,
        "t": 6,
        "source": "network",
        "kind": "turn",
        "speaker": "caller",
        "text": "still there?",
    }
    assert client.post(f"/sessions/{sid}/events", json=late).status_code == 409  # nothing after call_end (R8)
    assert client.post(f"/sessions/{sid}/choice", json={"choice": "1"}).status_code == 409
    assert (
        client.post(f"/sessions/{sid}/events?offline=true", json=start).status_code == 202
    )  # a new call may reuse the id


START = {
    "t": 0,
    "source": "network",
    "kind": "call_start",
    "direction": "inbound",
    "number": "+15555550123",
    "first_seen": True,
}


def test_sidecar_choice_body_with_digit(client: TestClient) -> None:
    sid = "sidecar_choice"
    assert (
        client.post(f"/sessions/{sid}/events?offline=true", json={**START, "session_id": sid}).status_code
        == 202
    )
    r = client.post(f"/sessions/{sid}/choice", json={"choice": "call_bank", "digit": "1"})
    assert r.status_code == 202 and r.json()["choice"] == "call_bank"
    r = client.post(f"/sessions/{sid}/choice", json={"choice": "dismiss", "digit": "4", "via": "imessage"})
    assert r.status_code == 202 and r.json()["choice"] == "dismiss"  # choice wins; extra fields are ignored
    r = client.post(f"/sessions/{sid}/choice", json={"choice": "", "digit": "2"})
    assert r.status_code == 202 and r.json()["choice"] == "ask_trusted_contact"  # digit is the fallback
    assert client.post(f"/sessions/{sid}/choice", json={"choice": "x", "digit": "9"}).status_code == 422


def test_tools_switch(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[str] = []

    def fake_real() -> Any:
        built.append("real")
        return mock_tools()

    monkeypatch.setattr(hub_module, "real_tools", fake_real)
    monkeypatch.setenv("TOOLS", "real")
    assert client.get("/health").json()["tools"] == "real"
    sid = "tools_real"
    assert (
        client.post(f"/sessions/{sid}/events?offline=true", json={**START, "session_id": sid}).status_code
        == 202
    )
    assert built == ["real"]

    def broken() -> Any:
        raise ToolConfigError("set PHOTON_SIDECAR_URL (e.g. http://localhost:8787)")

    monkeypatch.setattr(hub_module, "real_tools", broken)
    sid = "tools_broken"
    r = client.post(f"/sessions/{sid}/events?offline=true", json={**START, "session_id": sid})
    assert r.status_code == 503 and "PHOTON_SIDECAR_URL" in r.json()["detail"]
    assert client.post(f"/sessions/{sid}/choice", json={"choice": "1"}).status_code == 404  # no session made

    monkeypatch.setenv("TOOLS", "mock")
    assert client.get("/health").json()["tools"] == "mock"


def test_unknown_fixture_is_404(client: TestClient) -> None:
    assert client.post("/sessions/no_such_fixture/replay").status_code == 404
    assert client.post("/sessions/..%2Fsecrets/replay").status_code == 404


def test_live_sms_reaches_the_live_call_without_the_code(client: TestClient) -> None:
    sid = "live_sms"
    start = {
        "session_id": sid,
        "t": 0,
        "source": "network",
        "kind": "call_start",
        "direction": "inbound",
        "number": "+15550100",
        "first_seen": True,
    }
    assert client.post(f"/sessions/{sid}/events?offline=true", json=start).status_code == 202
    turn = {
        "session_id": sid,
        "t": 30,
        "source": "network",
        "kind": "turn",
        "speaker": "caller",
        "text": "hi",
    }
    assert client.post(f"/sessions/{sid}/events", json=turn).status_code == 202
    # the phone never sends the code or the text: extra fields are refused
    leak = {"sender_type": "bank_shortcode", "org": "Chase", "body": "Your code is 123456"}
    assert client.post("/live/sms", json=leak).status_code == 422
    r = client.post("/live/sms", json={"sender_type": "bank_shortcode", "org": "Chase"})
    assert r.status_code == 202 and r.json() == {"accepted": True, "session_id": sid, "t": 30.0}
    state = _wait_state(client, sid, lambda s: any(x.kind == "otp_during_call" for x in s.signals))
    assert [x.detail for x in state.signals if x.kind == "otp_during_call"] == ["Chase"]
    end = {"session_id": sid, "t": 40, "source": "network", "kind": "call_end"}
    assert client.post(f"/sessions/{sid}/events", json=end).status_code == 202
    after = client.post("/live/sms", json={"sender_type": "bank_shortcode"}).json()
    assert after.get("session_id") != sid  # an ended call never gets a late code
