"""Nemotron client. Every output is parsed into a Pydantic model or rejected (R11)."""

from __future__ import annotations

import json
import re
import time
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel, ValidationError

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


def parse_json_model(text: str, schema: type[T]) -> T:
    cleaned = _THINK.sub("", text).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise LLMError("no JSON object in model output")
    try:
        return schema.model_validate(json.loads(cleaned[start : end + 1]))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise LLMError(f"invalid model output: {type(exc).__name__}") from exc


class Nemotron:
    def __init__(self, base_url: str, api_key: str, model: str, timeout_s: float = 120.0):
        self.model = model
        self._client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout_s, max_retries=2)

    def ping(self) -> None:
        served = [m.id for m in self._client.models.list().data]
        if self.model not in served:
            raise LLMError(f"{self.model} is not served here (found {served})")

    def complete(
        self, system: str, user: str, schema: type[T], max_tokens: int, attempts: int = 2
    ) -> tuple[T, int]:
        """Return (validated output, latency in ms). Transcripts only ever go in `user` (R12)."""
        started = time.perf_counter()
        error: LLMError | None = None
        for _ in range(attempts):
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            try:
                parsed = parse_json_model(response.choices[0].message.content or "", schema)
                return parsed, round((time.perf_counter() - started) * 1000)
            except LLMError as exc:
                error = exc
        raise error or LLMError("no attempts made")
