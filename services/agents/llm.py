"""The one Nemotron client (R13). Every reply comes back as a validated Pydantic model, or not at all (R11).

Brev first, hosted NIM fallback, same OpenAI-compatible API. Transcripts and web text are data (R12): put them in
the `user` message through `data_block()`, never in `system`.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from functools import cache
from typing import TypeVar

import openai
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

M = TypeVar("M", bound=BaseModel)

DEFAULT_TIMEOUT_S = 10.0

# Latency of the most recent successful `structured()` call, in ms. Read it right after the call.
last_latency_ms: float = 0.0


class LLMError(Exception):
    """Base class. Callers catch this, take no action and set guard_paused (R4, R11)."""


class LLMUnavailable(LLMError):
    """Brev and the fallback both failed at the transport level."""


class LLMInvalidOutput(LLMError):
    """The model's reply did not validate, even after one retry."""


def fast_model() -> str:
    load_dotenv()
    return _require("NEMOTRON_MODEL_FAST")


def planner_model() -> str:
    load_dotenv()
    return _require("NEMOTRON_MODEL_PLANNER")


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise LLMError(f"{name} is not set (see .env.example)")
    return value


@cache
def _clients() -> list[tuple[str, openai.OpenAI]]:
    """(name, client) in the order to try them. max_retries=0 so a failure moves on to the fallback at once."""
    load_dotenv()
    out: list[tuple[str, openai.OpenAI]] = []
    for name, url_var, key_var in (
        ("brev", "NEMOTRON_BASE_URL", "NEMOTRON_API_KEY"),
        ("nim", "NEMOTRON_FALLBACK_BASE_URL", "NEMOTRON_FALLBACK_API_KEY"),
    ):
        url = os.environ.get(url_var, "").strip()
        if url:
            key = os.environ.get(key_var, "").strip() or "none"
            out.append((name, openai.OpenAI(base_url=url, api_key=key, max_retries=0)))
    if not out:
        raise LLMError("NEMOTRON_BASE_URL is not set (see .env.example)")
    return out


def data_block(label: str, text: str) -> str:
    """Wrap untrusted text (transcript, web page) in tags. The text cannot close the tag early (R12)."""
    if not re.fullmatch(r"[a-z_]+", label):
        raise ValueError("label must be lowercase letters and underscores")
    safe = re.sub(rf"</?\s*{label}\s*>", "[tag removed]", text, flags=re.IGNORECASE)
    return f"<{label}>\n{safe}\n</{label}>"


_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


def _clean(raw: str) -> str:
    text = _THINK.sub("", raw).strip()
    return _FENCE.sub("", text).strip()


def _transport_error(e: Exception) -> bool:
    """Errors worth trying the fallback for. A 400 would fail on NIM too."""
    if isinstance(e, openai.APITimeoutError | openai.APIConnectionError | openai.RateLimitError):
        return True
    return isinstance(e, openai.APIStatusError) and e.status_code >= 500


def _complete(
    messages: list[dict[str, str]],
    model_cls: type[BaseModel],
    model_name: str,
    timeout: float,
    max_tokens: int,
) -> str:
    last: Exception | None = None
    for name, client in _clients():
        try:
            resp = client.chat.completions.create(
                model=model_name,
                messages=messages,  # type: ignore[arg-type]
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": model_cls.__name__, "schema": model_cls.model_json_schema()},
                },
                temperature=0,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            if not _transport_error(e):
                raise LLMError(f"{name}: {e}") from e
            log.warning("llm %s failed (%s), trying next", name, type(e).__name__)
            last = e
    raise LLMUnavailable(f"all endpoints failed: {last}") from last


def structured(
    system: str,
    user: str,
    model_cls: type[M],
    model_name: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_S,
    max_tokens: int = 1024,
) -> M:
    """Ask Nemotron for JSON matching `model_cls`, validate it, retry once with the error, then raise.

    `system` holds instructions only. Any transcript or web text goes in `user`, wrapped with `data_block()`.
    """
    global last_latency_ms
    schema = json.dumps(model_cls.model_json_schema(), separators=(",", ":"))
    messages = [
        {
            "role": "system",
            "content": f"{system}\n\nReply with one JSON object that matches this JSON schema, and nothing else:\n{schema}",
        },
        {"role": "user", "content": user},
    ]
    start = time.perf_counter()
    for attempt in (1, 2):
        raw = _complete(messages, model_cls, model_name, timeout, max_tokens)
        try:
            result = model_cls.model_validate_json(_clean(raw))
        except ValidationError as e:
            if attempt == 2:
                log.error("llm output invalid after retry for %s: %s", model_cls.__name__, e.errors()[:3])
                raise LLMInvalidOutput(str(e)) from e
            messages += [
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": f"That reply did not match the schema. Errors:\n{e}\nReply again with only the corrected JSON object.",
                },
            ]
            continue
        last_latency_ms = (time.perf_counter() - start) * 1000
        return result
    raise AssertionError("unreachable")
