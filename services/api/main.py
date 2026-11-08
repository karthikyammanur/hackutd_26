"""Safe Signal API: live events in, UIMessage stream out.

    uvicorn services.api.main:app --reload --port 8000

Live (the demo): the bridge POSTs each Event to /sessions/{id}/events; the phone reply goes to /sessions/{id}/choice.
Replay (lane 3 dev): POST /sessions/{fixture}/replay?speed=4. Either way, the console listens on WS /ws/{id}.
Offline (no Brev): ?offline=true on call_start or replay, or SAFE_SIGNAL_OFFLINE=1.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any, Literal

from dotenv import load_dotenv
from fastapi import Body, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, TypeAdapter, ValidationError

from contracts.events import CallStart, EvalCase, Event
from contracts.state import SessionState, UIMessage
from services.api.hub import Hub, LiveSession, parse_choice

load_dotenv()  # so /health and offline defaults see .env before the first LLM call

FIXTURES = Path(__file__).resolve().parents[2] / "evals" / "fixtures"
CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]  # Vite dev server, Next.js


def _env_offline() -> bool:
    return os.environ.get("SAFE_SIGNAL_OFFLINE", "").strip().lower() in ("1", "true", "yes")


hub = Hub()
EVENT: TypeAdapter[Event] = TypeAdapter(Event)  # the contracts union, discriminated by `kind`


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await hub.close()


app = FastAPI(title="Safe Signal API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "offline_default": _env_offline(),
        "nemotron_fast": bool(os.environ.get("NEMOTRON_BASE_URL")),
        "nemotron_deep": bool(os.environ.get("NEMOTRON_DEEP_BASE_URL")),
        "sessions": len(hub.sessions),
    }


# ---- live: one Event at a time -----------------------------------------------------------------------------


@app.post("/sessions/{session_id}/events", status_code=202)
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
        live = await hub.start(session_id, offline=_env_offline() if offline is None else offline)
    elif live is None:
        raise HTTPException(404, f"no session {session_id!r}; send call_start first")
    if not live.submit(event):
        raise HTTPException(409, "call already ended")
    return {"session_id": session_id, "accepted": event.kind, "t": event.t}


class ChoiceIn(BaseModel):
    choice: str  # "1" | "2" | "3" | "call_bank" | "ask_trusted_contact" | "continue" | "dismiss"


@app.post("/sessions/{session_id}/choice", status_code=202)
async def post_choice(session_id: str, body: ChoiceIn) -> dict[str, Any]:
    """The customer's button tap or iMessage reply (1=call_bank, 2=ask_trusted_contact, 3=continue)."""
    live = hub.get(session_id)
    if live is None:
        raise HTTPException(404, f"no session {session_id!r}")
    choice = parse_choice(body.choice)
    if choice is None:
        raise HTTPException(422, f"unknown choice {body.choice!r}; use 1, 2, 3 or a choice name")
    event = live.choice_event(choice)
    if not live.submit(event):
        raise HTTPException(409, "call already ended; the choice came too late for aftercare")
    return {"session_id": session_id, "choice": choice, "t": event.t}


@app.get("/sessions/{session_id}")
async def get_session(session_id: str) -> SessionState:
    live = hub.get(session_id)
    if live is None:
        raise HTTPException(404, f"no session {session_id!r}")
    return await asyncio.to_thread(live.state)


# ---- replay: a fixture paced like a real call --------------------------------------------------------------

_FIXTURE_NAME = re.compile(r"[a-z0-9_]+")


@app.post("/sessions/{fixture_name}/replay", status_code=202)
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
    live = await hub.start(case.session_id, offline=_env_offline() if offline is None else offline)
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
