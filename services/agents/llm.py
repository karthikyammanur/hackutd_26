"""The one Nemotron client (R13). Every reply comes back as a validated Pydantic model, or not at all (R11).

Two tiers, each its own Brev vLLM server, with a hosted-NIM fallback per tier:
  fast  NEMOTRON_BASE_URL       + NEMOTRON_MODEL_FAST      (Nemotron 3 Nano 4B)   fallback NEMOTRON_FALLBACK_MODEL_FAST
  deep  NEMOTRON_DEEP_BASE_URL  + NEMOTRON_MODEL_PLANNER   (Nemotron Nano 9B v2)  fallback NEMOTRON_FALLBACK_MODEL_PLANNER
Brev uses custom served names; NIM needs real model IDs, hence the separate fallback model vars.

Thinking is off at the source by default: fast via chat_template_kwargs, deep via "/no_think" in the system
prompt. Stripping <think> blocks is only a safety net.

Transcripts and web text are data (R12): put them in the `user` message through `data_block()`, never in `system`.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from functools import cache
from typing import Any, Literal, TypeVar

import openai
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

M = TypeVar("M", bound=BaseModel)
Tier = Literal["fast", "deep"]

# Which tier each node uses. Nodes read their tier from here so the mapping lives in one place.
NODE_TIER: dict[str, Tier] = {
    "guardian": "fast",
    "alert": "fast",
    "evidence": "fast",
    "planner": "deep",
    "callback": "deep",
    "recovery": "deep",
}

DEFAULT_TIMEOUT_S = 10.0

# Latency of the most recent successful `structured()` call, in ms. Read it right after the call.
last_latency_ms: float = 0.0


class LLMError(Exception):
    """Base class. Callers catch this, take no action and set guard_paused (R4, R11)."""


class LLMUnavailable(LLMError):
    """Brev and the fallback both failed at the transport level."""


class LLMInvalidOutput(LLMError):
    """The model's reply did not validate, even after one retry."""


@dataclass(frozen=True)
class Endpoint:
    name: str  # "brev-fast", "nim-deep", ...
    client: openai.OpenAI
    model: str
    tier: Tier


_TIER_ENV: dict[Tier, tuple[str, str, str]] = {
    # tier: (brev url var, brev model var, nim model var)
    "fast": ("NEMOTRON_BASE_URL", "NEMOTRON_MODEL_FAST", "NEMOTRON_FALLBACK_MODEL_FAST"),
    "deep": ("NEMOTRON_DEEP_BASE_URL", "NEMOTRON_MODEL_PLANNER", "NEMOTRON_FALLBACK_MODEL_PLANNER"),
}


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


@cache
def _client(base_url: str, api_key: str) -> openai.OpenAI:
    # max_retries=0 so a failure moves on to the fallback at once instead of retrying Brev.
    return openai.OpenAI(base_url=base_url, api_key=api_key or "none", max_retries=0)


@cache
def _endpoints(tier: Tier) -> list[Endpoint]:
    """Endpoints to try for a tier, in order. An endpoint with a missing URL or model is skipped."""
    load_dotenv()
    url_var, model_var, nim_model_var = _TIER_ENV[tier]
    out: list[Endpoint] = []
    for name, url, key, model in (
        (f"brev-{tier}", _env(url_var), _env("NEMOTRON_API_KEY"), _env(model_var)),
        (
            f"nim-{tier}",
            _env("NEMOTRON_FALLBACK_BASE_URL"),
            _env("NEMOTRON_FALLBACK_API_KEY"),
            _env(nim_model_var),
        ),
    ):
        if url and model:
            out.append(Endpoint(name, _client(url, key), model, tier))
    if not out:
        raise LLMError(f"no endpoint configured for tier {tier!r}: set {url_var} and {model_var}")
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
    """Safety net only: thinking is switched off at the source."""
    text = _THINK.sub("", raw).strip()
    return _FENCE.sub("", text).strip()


def _transport_error(e: Exception) -> bool:
    """Errors worth trying the fallback for. A 400 would fail on NIM too."""
    if isinstance(e, openai.APITimeoutError | openai.APIConnectionError | openai.RateLimitError):
        return True
    return isinstance(e, openai.APIStatusError) and e.status_code >= 500


def _thinking_args(tier: Tier, thinking: bool, messages: list[dict[str, str]]) -> dict[str, Any]:
    """Turn thinking on or off the way each model expects. Returns extra kwargs for create()."""
    if tier == "fast":
        return {"extra_body": {"chat_template_kwargs": {"enable_thinking": thinking}}}
    if not thinking:  # deep: Nemotron Nano 9B v2 reads /no_think from the system prompt
        messages[0] = {"role": "system", "content": "/no_think\n" + messages[0]["content"]}
    return {}


def _complete(
    tier: Tier,
    thinking: bool,
    messages: list[dict[str, str]],
    model_cls: type[BaseModel],
    timeout: float,
    max_tokens: int,
) -> str:
    last: Exception | None = None
    for ep in _endpoints(tier):
        msgs = list(messages)
        extra = _thinking_args(tier, thinking, msgs)
        try:
            resp = ep.client.chat.completions.create(
                model=ep.model,
                messages=msgs,  # type: ignore[arg-type]
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": model_cls.__name__, "schema": model_cls.model_json_schema()},
                },
                temperature=0,
                max_tokens=max_tokens,
                timeout=timeout,
                **extra,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            if not _transport_error(e):
                raise LLMError(f"{ep.name}: {e}") from e
            log.warning("llm %s failed (%s), trying next", ep.name, type(e).__name__)
            last = e
    raise LLMUnavailable(f"all endpoints failed for tier {tier!r}: {last}") from last


def structured(
    system: str,
    user: str,
    model_cls: type[M],
    tier: Tier,
    *,
    thinking: bool = False,
    timeout: float = DEFAULT_TIMEOUT_S,
    max_tokens: int = 1024,
) -> M:
    """Ask Nemotron for JSON matching `model_cls`, validate it, retry once with the error, then raise.

    `system` holds instructions only. Any transcript or web text goes in `user`, wrapped with `data_block()`.
    `thinking=True` lets the model reason first (deep tier, when latency allows); raise max_tokens with it.
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
        raw = _complete(tier, thinking, messages, model_cls, timeout, max_tokens)
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
