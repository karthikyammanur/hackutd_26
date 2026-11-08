"""Node prompts. One markdown file per node, loaded as the `system` argument of `llm.structured()`.

A prompt file holds instructions and fixed authored examples only. Live transcript text never goes
in a system prompt: the node puts it in the user message through `llm.data_block()` (R12).
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from pydantic import BaseModel

from services.agents.prompts.schemas import (
    AlertCopy,
    CallbackScript,
    EvidenceSummary,
    GuardianFlag,
    GuardianOutput,
    PlannerOutput,
    RecoveryPlan,
    RecoveryStep,
)

_DIR = Path(__file__).parent

# Node name -> (prompt file, output model). Tiers live in `llm.NODE_TIER`.
PROMPTS: dict[str, type[BaseModel]] = {
    "guardian": GuardianOutput,
    "alert": AlertCopy,
    "planner": PlannerOutput,
    "callback": CallbackScript,
    "recovery": RecoveryPlan,
    "evidence": EvidenceSummary,
}

PROMPT_NAMES: tuple[str, ...] = tuple(PROMPTS)

__all__ = [
    "PROMPTS",
    "PROMPT_NAMES",
    "AlertCopy",
    "CallbackScript",
    "EvidenceSummary",
    "GuardianFlag",
    "GuardianOutput",
    "PlannerOutput",
    "RecoveryPlan",
    "RecoveryStep",
    "load_prompt",
]


@cache
def load_prompt(name: str) -> str:
    """The system prompt for a node. Raises KeyError for an unknown node."""
    if name not in PROMPTS:
        raise KeyError(f"unknown prompt {name!r}; known: {', '.join(PROMPT_NAMES)}")
    text = (_DIR / f"{name}.md").read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"prompt {name!r} is empty")
    return text
