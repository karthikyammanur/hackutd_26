"""Live sessions for the API: one ordered worker per session, fanned out to WebSocket subscribers.

Events go into a session's inbox and are processed strictly in order, each in a worker thread (the graph blocks on
Nemotron, so it never runs on the event loop). Every result goes out as UIMessage JSON.

R8: turn text is sent only live, as it happens. It is never buffered for late subscribers, never sent after
call_end, and graph-only fields (transcript_window, event) never leave the graph.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from typing import Any

from contracts.events import CallEnd, Event, Source, UserChoice
from contracts.state import SessionState, UIMessage
from services.agents import llm
from services.agents.graph.deps import Tools
from services.agents.graph.runner import Session
from services.agents.graph.stubs import offline_structured
from services.agents.nodes.during import keyword_guardian
from services.agents.tools import real_tools
from services.agents.tools.mock import mock_tools

log = logging.getLogger(__name__)

CHOICES: dict[str, str] = {"1": "call_bank", "2": "ask_trusted_contact", "3": "continue"}
VALID_CHOICES = frozenset({*CHOICES.values(), "dismiss"})


def tools_mode() -> str:
    """TOOLS=real in .env wires Lane 4's live adapters (Photon, ElevenLabs); anything else uses the mocks."""
    return "real" if os.environ.get("TOOLS", "").strip().lower() == "real" else "mock"


def session_tools() -> Tools:
    """Raises ToolConfigError (it names the env var) when TOOLS=real but the adapters are not configured."""
    return real_tools() if tools_mode() == "real" else mock_tools()


def parse_choice(raw: str) -> str | None:
    """Accept the digit from the iMessage reply (1/2/3) or the name."""
    raw = raw.strip().lower()
    choice = CHOICES.get(raw, raw)
    return choice if choice in VALID_CHOICES else None


class LiveSession:
    def __init__(self, session_id: str, offline: bool, tools: Tools) -> None:
        self.session_id = session_id
        self.offline = offline
        self.session = (
            Session(session_id, tools, guardian=keyword_guardian, structured=offline_structured)
            if offline
            else Session(session_id, tools, structured=llm.structured)
        )
        self.loop = asyncio.get_running_loop()
        self.inbox: asyncio.Queue[Event] = asyncio.Queue()
        self.subscribers: set[asyncio.Queue[str]] = set()
        self.last_t = 0.0  # call time of the newest accepted event
        self.ended = False  # set when call_end is accepted
        self.after_done = asyncio.Event()  # set once call_end has been fully processed
        self.worker = asyncio.create_task(self._work(), name=f"session-{session_id}")
        self.replay_task: asyncio.Task[None] | None = None

    # ---- input --------------------------------------------------------------------------------------------

    def submit(self, event: Event) -> bool:
        """Queue an event. Returns False if it is dropped (anything after call_end)."""
        if self.ended:
            return False
        self.last_t = max(self.last_t, event.t)
        if isinstance(event, CallEnd):
            self.ended = True
        self.inbox.put_nowait(event)
        return True

    def choice_event(self, choice: str) -> UserChoice:
        return UserChoice(session_id=self.session_id, t=self.last_t, source=Source.phone, choice=choice)  # type: ignore[arg-type]

    # ---- processing (worker thread) -----------------------------------------------------------------------

    async def _work(self) -> None:
        while True:
            event = await self.inbox.get()
            try:
                await asyncio.to_thread(self._process, event)
            except Exception:  # R4: a failing graph never takes the API down; the session just stops updating
                log.exception("session %s failed on %s", self.session_id, event.kind)
            if isinstance(event, CallEnd):
                self.after_done.set()

    def _process(self, event: Event) -> None:
        self._publish(UIMessage(type="event", session_id=self.session_id, event=event))

        def on_update(node: str, update: dict[str, Any]) -> None:
            for item in update.get("trace", []):
                self._publish(UIMessage(type="trace", session_id=self.session_id, trace=item))
            self._publish(UIMessage(type="state", session_id=self.session_id, state=self.session.snapshot))

        self.session.feed(event, on_update)

    def _publish(self, msg: UIMessage) -> None:
        # R8: submit() drops every event after call_end, so no turn text is ever sent after it.
        self.loop.call_soon_threadsafe(self._fan_out, msg.model_dump_json())

    def _fan_out(self, data: str) -> None:
        for q in list(self.subscribers):
            q.put_nowait(data)

    # ---- output -------------------------------------------------------------------------------------------

    def state(self) -> SessionState:
        return self.session.state()

    def subscribe(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue()
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[str]) -> None:
        self.subscribers.discard(q)

    async def close(self) -> None:
        for task in (self.replay_task, self.worker):
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task


class Hub:
    def __init__(self) -> None:
        self.sessions: dict[str, LiveSession] = {}
        self.waiting: dict[str, set[asyncio.Queue[str]]] = {}  # sockets opened before the session exists

    def get(self, session_id: str) -> LiveSession | None:
        return self.sessions.get(session_id)

    async def start(self, session_id: str, offline: bool) -> LiveSession:
        """A fresh session (an old one with the same id is closed). Sockets already waiting are attached."""
        tools = session_tools()  # before touching the old session, so a config error leaves it running
        old = self.sessions.pop(session_id, None)
        live = LiveSession(session_id, offline, tools)
        if old:
            live.subscribers |= old.subscribers
            await old.close()
        live.subscribers |= self.waiting.pop(session_id, set())
        self.sessions[session_id] = live
        return live

    def subscribe(self, session_id: str) -> asyncio.Queue[str]:
        live = self.sessions.get(session_id)
        if live:
            return live.subscribe()
        q: asyncio.Queue[str] = asyncio.Queue()
        self.waiting.setdefault(session_id, set()).add(q)
        return q

    def unsubscribe(self, session_id: str, q: asyncio.Queue[str]) -> None:
        live = self.sessions.get(session_id)
        if live:
            live.unsubscribe(q)
        self.waiting.get(session_id, set()).discard(q)

    async def close(self) -> None:
        for live in list(self.sessions.values()):
            await live.close()
        self.sessions.clear()
