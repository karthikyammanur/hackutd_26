"""Load labeled fake calls and cut them into microframes, the way a live call would arrive.

A new frame is produced on every caller turn and every in-call signal (code text, banking app, transfer,
account change). Each frame only sees what had happened by that moment.

Deliberately NOT sent to the classifier:
  `caller` (first_seen / known_business): in this dataset it perfectly separates two benign types from
      every scam, so including it would leak the label.
  `number`, `dns`: not part of the conversation. DNS events also happen before the call starts.
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

WINDOW_TURNS = 6
HARD_NEGATIVE_TYPES = frozenset({"benign_real_bank_alert", "benign_real_carrier_care"})


@dataclass(frozen=True)
class Frame:
    index: int
    t: float
    trigger: str  # "turn" or the signal kind
    new_lines: tuple[str, ...]  # what happened since the previous frame
    window: tuple[str, ...]  # the most recent turns, verbatim
    signals: tuple[str, ...]  # every in-call signal so far
    latest: str  # the line that produced this frame


@dataclass(frozen=True)
class Session:
    session_id: str
    scam: bool
    scam_type: str
    money_moment_t: float | None
    direction: str
    frames: tuple[Frame, ...] = field(default_factory=tuple)

    @property
    def hard_negative(self) -> bool:
        return self.scam_type in HARD_NEGATIVE_TYPES


def _signal_line(event: dict) -> str | None:
    t, kind = event["t"], event["kind"]
    if kind == "sms_otp":
        return f"[{t:g}s] A one-time code text arrived from {event.get('sender', 'a sender')}"
    if kind == "bank_app_open":
        return f"[{t:g}s] The customer opened their banking app"
    if kind == "bank_transfer":
        new = "a new payee" if event.get("newPayee") else "an existing payee"
        return f"[{t:g}s] A bank transfer of ${event.get('amount', '?')} started to {new}"
    if kind == "account":
        return f"[{t:g}s] Phone account event: {event.get('action', 'unknown')}"
    return None


def build_frames(events: list[dict]) -> tuple[Frame, ...]:
    turns: list[str] = []
    signals: list[str] = []
    pending: list[str] = []
    frames: list[Frame] = []

    def emit(t: float, trigger: str, latest: str) -> None:
        frames.append(
            Frame(
                index=len(frames),
                t=t,
                trigger=trigger,
                new_lines=tuple(pending),
                window=tuple(turns[-WINDOW_TURNS:]),
                signals=tuple(signals),
                latest=latest,
            )
        )
        pending.clear()

    for event in sorted(events, key=lambda e: e["t"]):
        if event["kind"] == "turn":
            line = f"{event['who'].upper()}: {event['text']}"
            turns.append(line)
            pending.append(line)
            if event["who"] == "caller":
                emit(event["t"], "turn", line)
        elif (line := _signal_line(event)) is not None:
            signals.append(line)
            pending.append(line)
            emit(event["t"], event["kind"], line)
    return tuple(frames)


def parse_session(row: dict) -> Session:
    start = next((e for e in row["events"] if e["kind"] == "call_start"), {})
    label = row["label"]
    return Session(
        session_id=row["session_id"],
        scam=bool(label["scam"]),
        scam_type=label["type"],
        money_moment_t=label.get("money_moment_t"),
        direction=start.get("direction", "unknown"),
        frames=build_frames(row["events"]),
    )


def load_sample(path: Path, per_type: int, seed: int) -> list[Session]:
    """Equal sessions per call type, repeatable for a seed. per_type <= 0 means every session."""
    by_type: dict[str, list[dict]] = defaultdict(list)
    with path.open() as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                by_type[row["label"]["type"]].append(row)

    rng = random.Random(seed)
    chosen: list[dict] = []
    for scam_type in sorted(by_type):
        rows = sorted(by_type[scam_type], key=lambda r: r["session_id"])
        rng.shuffle(rows)
        chosen.extend(rows if per_type <= 0 else rows[:per_type])
    return [parse_session(row) for row in chosen]
