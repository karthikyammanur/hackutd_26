"""Interfaces between lanes. Implementations live in the owning lane; mocks in services/agents/tools/mock.py."""

from __future__ import annotations

from typing import Protocol

from contracts.state import Risk, SessionState


class Decider(Protocol):
    """Lane 2 implements (Jev adapter or rule fallback). Deterministic, < 100 ms, no LLM inside."""

    def __call__(self, state: SessionState) -> Risk: ...


class Comms(Protocol):
    """Lane 4 implements with Photon (MCP). Never hangs up a call (R2)."""

    def notify(self, session_id: str, to: str, text: str, buttons: list[str]) -> str: ...
    def call(self, session_id: str, to: str, script: str) -> str: ...
    def transfer(self, session_id: str, call_id: str, to_number: str) -> str: ...
    def message(self, session_id: str, to: str, text: str) -> str: ...


class Voice(Protocol):
    """Lane 4 implements with ElevenLabs."""

    def whisper(self, session_id: str, text: str) -> str: ...


class Store(Protocol):
    """Lane 4 implements with Tiger Data. Must drop `turn` events (R8)."""

    def append_event(self, session_id: str, event: dict) -> None: ...
    def save_evidence(self, session_id: str, packet: dict) -> str: ...
    def lookup_verified(self, number: str) -> str | None: ...
    def search_policy(self, query: str, k: int = 3) -> list[str]: ...
