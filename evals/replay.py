"""Replay EvalCase sessions through Caller Screen, Signal Watcher and decide(), and write predictions.

This is the Lane 2 pipeline only. The real graph (Lane 1, L1-3) puts Call Guardian where `flagger` goes.
Predictions hold only t, level and score, never transcript text (R8).

  python evals/replay.py --cases data/eval --flags keyword --out out/preds.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contracts.events import CallEnd, CallStart, EvalCase, UserChoice  # noqa: E402
from contracts.state import Flag, SessionState  # noqa: E402
from services.agents.decision.decide import decide  # noqa: E402
from services.agents.signals.caller_screen import screen_call  # noqa: E402
from services.agents.signals.signal_watcher import watch_event  # noqa: E402

Flagger = Callable[[object], list[Flag]]


def no_flags(_event: object) -> list[Flag]:
    return []


@dataclass
class ReplayResult:
    state: SessionState
    alerts: list[dict] = field(default_factory=list)
    latency_ms: list[float] = field(default_factory=list)

    def prediction(self) -> dict:
        return {"session_id": self.state.session_id, "alerts": self.alerts, "latency_ms": self.latency_ms}


def replay_case(
    case: EvalCase, flagger: Flagger = no_flags, scam_numbers: Collection[str] = frozenset()
) -> ReplayResult:
    """Feed one session through the pipeline event by event, recording every rise in risk."""
    state = SessionState(session_id=case.session_id)
    result = ReplayResult(state=state)
    top = -1.0
    in_scope = True

    for event in case.events:
        if isinstance(event, CallStart):
            screen = screen_call(event, scam_numbers=scam_numbers)
            in_scope = screen.in_scope
            state.caller = screen.caller
            state.prior_risk = screen.prior_risk
            state.signals += screen.signals
        elif isinstance(event, CallEnd):
            state.ended = True
        elif isinstance(event, UserChoice):
            state.user_choice = event.choice
        elif state.caller is not None and in_scope:
            state.signals += watch_event(event, state.caller)
            state.flags += flagger(event)

        if not in_scope:
            continue
        started = time.perf_counter()
        state.risk = decide(state)
        result.latency_ms.append((time.perf_counter() - started) * 1000)
        if state.risk.score > top:
            top = state.risk.score
            result.alerts.append(
                {"t": event.t, "level": state.risk.level.name, "score": round(state.risk.score, 4)}
            )
    return result


def load_eval_cases(path: Path) -> list[EvalCase]:
    """A folder of .json and/or .jsonl files, or one .jsonl file."""
    rows: list[str] = []
    files = sorted(path.glob("*.json*")) if path.is_dir() else [path]
    for f in files:
        text = f.read_text(encoding="utf-8")
        rows += [line for line in text.splitlines() if line.strip()] if f.suffix == ".jsonl" else [text]
    return [EvalCase.model_validate_json(r) for r in rows]


def main() -> int:
    from evals.stand_in_guardian import flag_turn

    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--flags", choices=["none", "keyword"], default="keyword")
    args = ap.parse_args()

    flagger = flag_turn if args.flags == "keyword" else no_flags
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cases = load_eval_cases(args.cases)
    with args.out.open("w", encoding="utf-8") as fh:
        for case in cases:
            fh.write(json.dumps(replay_case(case, flagger=flagger).prediction()) + "\n")
    print(f"{len(cases)} sessions -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
