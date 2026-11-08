"""Shared helpers for the corpus scripts: taxonomy loading and Case construction."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

CORPUS = Path(__file__).resolve().parent.parent
REPO = CORPUS.parent.parent
OUT = CORPUS / "out"
TAXONOMY_PATH = REPO / "sandbox" / "worker" / "src" / "taxonomy.py"


def load_taxonomy():
    """Import at run time, because the Research agent may extend METHODS."""
    spec = importlib.util.spec_from_file_location("taxonomy_runtime", TAXONOMY_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_case(
    case_id: str,
    channel: str,
    source: str,
    scam: bool,
    method: str,
    family: str,
    hard_negative: bool,
    money_moment_t,
    direction: str,
    events: list[dict],
    label_quality: str = "exact",
) -> dict:
    return {
        "case_id": case_id,
        "channel": channel,
        "source": source,
        "label_quality": label_quality,
        "scam": scam,
        "method": method,
        "family": family,
        "hard_negative": hard_negative,
        "money_moment_t": money_moment_t,
        "direction": direction,
        "events": events,
    }


def write_jsonl(path: Path, rows) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
            count += 1
    return count
