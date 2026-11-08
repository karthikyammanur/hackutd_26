"""Safe Signal API: live events in, UIMessage stream out.

    uvicorn services.api.main:app --reload --port 8000

Live (the demo): POST /calls/start places the Scammer Simulator call and feeds it in as it happens (live_call.py).
Other sources POST each Event to /sessions/{id}/events; the phone reply goes to /sessions/{id}/choice.
Replay (lane 3 dev): POST /sessions/{fixture}/replay?speed=4. Either way, the console listens on WS /ws/{id}.
Offline (no Brev): ?offline=true on call_start or replay, or SAFE_SIGNAL_OFFLINE=1.
On a public tunnel, set API_TOKEN: the console's routes then need "Authorization: Bearer <API_TOKEN>" (the WebSocket
takes ?token=). The hosted console reaches this API through its Worker, which adds the token (apps/web/worker).
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import os
import re
import secrets
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any, Literal

from dotenv import load_dotenv
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from contracts.events import CallStart, EvalCase, Event, SmsOtp, Source
from contracts.state import SessionState, UIMessage
from services.agents.tools.errors import ToolConfigError
from services.api import live_call
from services.api.hub import Hub, LiveSession, parse_choice, tools_mode
from services.api.view import session_view

load_dotenv()  # so /health and offline defaults see .env before the first LLM call

FIXTURES = Path(__file__).resolve().parents[2] / "evals" / "fixtures"
# Vite dev server, Next.js, the hosted console on Cloudflare, plus any extra origins in CORS_ORIGINS (comma-separated).
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "https://safe-signal.berenis-fopa.workers.dev",
    *[o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()],
]


def _env_offline() -> bool:
    return os.environ.get("SAFE_SIGNAL_OFFLINE", "").strip().lower() in ("1", "true", "yes")


def _token_ok(given: str | None) -> bool:
    token = os.environ.get("API_TOKEN", "").strip()
    return not token or hmac.compare_digest((given or "").encode(), token.encode())


def require_token(authorization: Annotated[str | None, Header()] = None) -> None:
    """With API_TOKEN set, the console's routes need it. Open: /health, and the two routes that carry only a choice
    or a sender type (the iMessage reply via the sidecar, the phone's code report), which have no token to send."""
    given = authorization.removeprefix("Bearer ").strip() if authorization else None
    if not _token_ok(given):
        raise HTTPException(401, "missing or wrong API token")


GUARD = [Depends(require_token)]
hub = Hub()
EVENT: TypeAdapter[Event] = TypeAdapter(Event)  # the contracts union, discriminated by `kind`


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await hub.close()


app = FastAPI(title="Safe Signal API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


async def _start(session_id: str, offline: bool | None) -> LiveSession:
    try:
        return await hub.start(session_id, offline=_env_offline() if offline is None else offline)
    except ToolConfigError as e:  # TOOLS=real but an adapter env var is missing; the message names it
        raise HTTPException(503, f"TOOLS=real: {e}") from e


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "offline_default": _env_offline(),
        "tools": tools_mode(),
        "nemotron_fast": bool(os.environ.get("NEMOTRON_BASE_URL")),
        "nemotron_deep": bool(os.environ.get("NEMOTRON_DEEP_BASE_URL")),
        "sessions": len(hub.sessions),
    }


# ---- a real call: the console's "start call" button ---------------------------------------------------------


@app.post("/calls/start", status_code=202, dependencies=GUARD)
async def start_call() -> dict[str, Any]:
    """Place one Scammer Simulator call to DEMO_CUSTOMER_NUMBER and follow it live. Takes no body: the number
    always comes from .env, so this route can never dial anyone else (R10). One call at a time."""
    current = hub.active()
    if current and current.call_task and not current.call_task.done():
        raise HTTPException(409, f"a call is already running: {current.session_id}")
    try:
        env = live_call.config()
    except ToolConfigError as e:
        raise HTTPException(503, str(e)) from e
    session_id = f"live-{secrets.token_hex(6)}"  # unguessable: the id is all /choice needs
    live = await _start(session_id, None)  # checks the adapters before anything is dialed
    el = live_call.client(env)
    try:
        number = await live_call.caller_number(el, env)
        conv = await live_call.place_call(el, env)
    except Exception as e:
        await el.aclose()
        hub.sessions.pop(session_id, None)
        await live.close()
        raise HTTPException(502, f"ElevenLabs could not place the call: {type(e).__name__}") from e
    live.submit(live_call.call_start(session_id, number))
    live.call_task = asyncio.create_task(live_call.follow(live.submit, session_id, el, conv))
    return {"session_id": session_id, "conversation_id": conv, "ws": f"/ws/{session_id}"}


@app.get("/calls/current", dependencies=GUARD)
def current_call() -> dict[str, Any]:
    """The live call's session id, so a console that did not start it can still open /ws/{id}."""
    live = hub.active()
    return {"session_id": live.session_id if live else None}


# ---- live: one Event at a time -----------------------------------------------------------------------------


@app.post("/sessions/{session_id}/events", status_code=202, dependencies=GUARD)
async def post_event(
    session_id: str,
    body: Annotated[dict[str, Any], Body()],
    offline: Annotated[bool | None, Query()] = None,
) -> dict[str, Any]:
    """Queue one Event. call_start creates the session; anything else needs one. Returns at once (202)."""
    try:
        event = EVENT.validate_python(body)
    except ValidationError as e:
        raise HTTPException(422, [{"loc": err["loc"], "msg": err["msg"]} for err in e.errors()]) from e
    if event.session_id != session_id:
        raise HTTPException(422, f"event.session_id {event.session_id!r} does not match the URL")
    live = hub.get(session_id)
    if isinstance(event, CallStart):
        if live and not live.ended:
            raise HTTPException(409, "a call is already running for this session_id")
        live = await _start(session_id, offline)
    elif live is None:
        raise HTTPException(404, f"no session {session_id!r}; send call_start first")
    if not live.submit(event):
        raise HTTPException(409, "call already ended")
    return {"session_id": session_id, "accepted": event.kind, "t": event.t}


class ChoiceIn(BaseModel):
    """The Photon sidecar sends {"choice": "call_bank", "digit": "1"}; the web UI may send just {"choice": "1"}."""

    model_config = ConfigDict(extra="ignore")
    choice: str  # "1" | "2" | "3" | "call_bank" | "ask_trusted_contact" | "continue" | "dismiss"
    digit: str | None = None  # used only when choice itself is not recognised


@app.post("/sessions/{session_id}/choice", status_code=202)
async def post_choice(session_id: str, body: ChoiceIn) -> dict[str, Any]:
    """The customer's button tap or iMessage reply (1=call_bank, 2=ask_trusted_contact, 3=continue)."""
    live = hub.get(session_id)
    if live is None:
        raise HTTPException(404, f"no session {session_id!r}")
    choice = parse_choice(body.choice) or (parse_choice(body.digit) if body.digit else None)
    if choice is None:
        raise HTTPException(422, f"unknown choice {body.choice!r}; use 1, 2, 3 or a choice name")
    event = live.choice_event(choice)
    if not live.submit(event):
        raise HTTPException(409, "call already ended; the choice came too late for aftercare")
    return {"session_id": session_id, "choice": choice, "t": event.t}


class SmsIn(BaseModel):
    """From the call-screener app on the customer's phone. Never the code or the message text: the phone only
    says what kind of sender a one-time code came from, and which bank its text named."""

    model_config = ConfigDict(extra="forbid")
    sender_type: Literal["bank_shortcode", "other_shortcode", "longcode"]
    org: str | None = None


@app.post("/live/sms", status_code=202)
async def post_live_sms(body: SmsIn) -> dict[str, Any]:
    """A one-time code just arrived on the customer's phone: an sms_otp event on the live call, if there is one."""
    live = hub.active()
    if live is None:
        return {"accepted": False, "reason": "no live call"}  # a code with no call running is not a signal
    event = SmsOtp(
        session_id=live.session_id,
        t=live.last_t,
        source=Source.phone,
        sender_type=body.sender_type,
        org=body.org,
    )
    live.submit(event)
    return {"accepted": True, "session_id": live.session_id, "t": event.t}


@app.get("/sessions/{session_id}", dependencies=GUARD)
async def get_session(session_id: str) -> SessionState:
    live = hub.get(session_id)
    if live is None:
        raise HTTPException(404, f"no session {session_id!r}")
    return await asyncio.to_thread(live.state)


@app.get("/sessions/{session_id}/view", dependencies=GUARD)
async def get_view(session_id: str) -> dict[str, Any]:
    """Markers only, for the hosted console (view.py): no turn text, quotes or numbers."""
    live = hub.get(session_id)
    if live is None:
        raise HTTPException(404, f"no session {session_id!r}")
    state = await asyncio.to_thread(live.state)
    running = live.call_task is not None and not live.call_task.done()
    return session_view(state, t=live.last_t, answered_t=live.answered_t, call_running=running)


# ---- replay: a fixture paced like a real call --------------------------------------------------------------

_FIXTURE_NAME = re.compile(r"[a-z0-9_]+")


@app.post("/sessions/{fixture_name}/replay", status_code=202, dependencies=GUARD)
async def replay(
    fixture_name: str,
    speed: Annotated[float, Query(gt=0, le=1000)] = 4.0,
    offline: Annotated[bool | None, Query()] = None,
    choices: Annotated[Literal["fixture", "live"], Query()] = "fixture",
) -> dict[str, Any]:
    """Replay evals/fixtures/<fixture_name>.json. choices=live skips the scripted user_choice so a tap drives it."""
    path = FIXTURES / f"{fixture_name}.json"
    if not _FIXTURE_NAME.fullmatch(fixture_name) or not path.is_file():
        raise HTTPException(404, f"no fixture {fixture_name!r}")
    case = EvalCase.model_validate_json(path.read_text(encoding="utf-8"))
    live = await _start(case.session_id, offline)
    events = [e for e in case.events if not (choices == "live" and e.kind == "user_choice")]
    live.replay_task = asyncio.create_task(_pace(live, events, speed))
    return {
        "session_id": case.session_id,
        "events": len(events),
        "speed": speed,
        "ws": f"/ws/{case.session_id}",
    }


async def _pace(live: LiveSession, events: list[Any], speed: float) -> None:
    prev = 0.0
    for e in events:
        await asyncio.sleep(max(0.0, (e.t - prev) / speed))
        prev = e.t
        live.submit(e)


# ---- stream ------------------------------------------------------------------------------------------------


@app.websocket("/ws/{session_id}")
async def ws(websocket: WebSocket, session_id: str) -> None:
    """UIMessage JSON: the current state on connect (if the session exists), then event / trace / state live."""
    if not _token_ok(websocket.query_params.get("token")):
        await websocket.close(code=1008)  # policy violation: this stream carries live turn text
        return
    await websocket.accept()
    q = hub.subscribe(session_id)
    try:
        live = hub.get(session_id)
        if live:
            state = await asyncio.to_thread(live.state)
            await websocket.send_text(
                UIMessage(type="state", session_id=session_id, state=state).model_dump_json()
            )
        while True:
            await websocket.send_text(await q.get())
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe(session_id, q)
