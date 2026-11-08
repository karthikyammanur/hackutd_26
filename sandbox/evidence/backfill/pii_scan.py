"""Negative check: prove no corpus text appears in incident payloads.

Corpus text is reduced to hashes of 6-word runs on load, so the scanner never holds the text itself.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from pathlib import Path

NGRAM = 6
_WORD = re.compile(r"[a-z0-9']+")


class TextLeak(ValueError):
    pass


def _hashes(text: str) -> Iterable[bytes]:
    words = _WORD.findall(text.lower())
    for i in range(len(words) - NGRAM + 1):
        yield hashlib.blake2b(" ".join(words[i : i + NGRAM]).encode(), digest_size=8).digest()


def _strings(value) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


class CorpusScanner:
    def __init__(self, texts: Iterable[str]):
        self.known: set[bytes] = set()
        for text in texts:
            self.known.update(_hashes(text))

    @classmethod
    def from_files(cls, paths: Iterable[Path], max_lines_per_file: int = 20_000) -> CorpusScanner:
        def texts() -> Iterable[str]:
            for path in paths:
                with path.open() as handle:
                    for number, line in enumerate(handle):
                        if number >= max_lines_per_file:
                            break
                        for event in json.loads(line).get("events", []):
                            if event.get("text"):
                                yield event["text"]

        return cls(texts())

    def check_batch(self, incidents: list[dict]) -> None:
        for incident in incidents:
            for text in _strings(incident):
                if any(digest in self.known for digest in _hashes(text)):
                    raise TextLeak(f"corpus text found in incident {incident.get('incident_id')}")
