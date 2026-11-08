"""Errors the real adapters raise. The graph catches them, marks the step failed and leaves the call alone (R4)."""

from __future__ import annotations

import re

from contracts.events import EMERGENCY_NUMBERS


class ToolError(RuntimeError):
    """A tool could not do what was asked (network, provider error)."""


class ToolConfigError(ToolError):
    """A required env var is missing or unsafe. The message names the variable."""


class ToolUnsupported(ToolError):
    """The provider cannot do this at all (see F8 in context/decisions.md)."""


def guard_not_emergency(number: str) -> None:
    """R1: never dial, message or transfer to an emergency number."""
    if re.sub(r"\D", "", number) in EMERGENCY_NUMBERS:
        raise ToolError("refusing to contact an emergency number (R1)")


def mask(number: str) -> str:
    digits = re.sub(r"\D", "", number)
    return f"...{digits[-4:]}"
