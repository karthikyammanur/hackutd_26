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


def demo_number(name: str, value: str) -> str:
    """A DEMO_* number from .env: empty stays empty; anything else must be E.164 and not an emergency number.

    Catches placeholders like "+1XXXXXXXXXX", which would otherwise be read aloud as a verified number.
    """
    value = value.strip()
    if value and not re.fullmatch(r"\+\d{10,15}", value):
        raise ToolConfigError(f"{name} is not a phone number; use E.164, e.g. +12145550100")
    if value:
        guard_not_emergency(value)
    return value


def mask(number: str) -> str:
    digits = re.sub(r"\D", "", number)
    return f"...{digits[-4:]}"
