"""Replay fixture sessions through the graph, as if live.

    python -m services.agents.graph.runner evals/fixtures --preds preds.jsonl --show

Each event is sent as {"event": e}; the in-memory checkpointer (thread_id = session_id) holds the rest.
`on_update(node, update)` gets each node's update with graph-only fields removed (no transcript, R8).
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig

from contracts.events import EvalCase
from contracts.state import Risk, SessionState
from services.agents.graph.build import build_graph
from services.agents.graph.deps import Tools
from services.agents.graph.state import public_state, public_update
from services.agents.graph.stubs import fake_tools

OnUpdate = Callable[[str, dict[str, Any]], None]


def replay_case(
    case: EvalCase, tools: Tools | None = None, on_update: OnUpdate | None = None
) -> tuple[SessionState, dict[str, Any]]:
    """Returns the final state and the prediction row for evals/run_eval.py."""
    graph = build_graph(tools or fake_tools())  # swap fake_tools() for lane 4's adapters here
    config: RunnableConfig = {"configurable": {"thread_id": case.session_id}}
    risk = Risk(score=0.0)
    pred_alerts: list[dict[str, Any]] = []
    latency_ms: list[float] = []

    for i, event in enumerate(case.events):
        inp: dict[str, Any] = {"event": event} if i else {"event": event, "session_id": case.session_id}
        start = time.perf_counter()
        for chunk in graph.stream(inp, config, stream_mode="updates"):
            for node, update in chunk.items():
                pub = public_update(update or {})
                if not pub:
                    continue
                risk = pub.get("risk", risk)
                for a in pub.get("alerts", []):
                    pred_alerts.append({"t": a.t, "level": a.level.name, "score": round(risk.score, 3)})
                if on_update:
                    on_update(node, pub)
        if event.kind != "call_end":  # after-call work is not on the live path
            latency_ms.append(round((time.perf_counter() - start) * 1000, 2))

    final = public_state(graph.get_state(config).values)
    return final, {"session_id": case.session_id, "alerts": pred_alerts, "latency_ms": latency_ms}


def replay(
    fixture_path: str | Path,
    on_update: OnUpdate | None = None,
    preds_path: str | Path | None = None,
    tools: Tools | None = None,
) -> SessionState:
    case = EvalCase.model_validate_json(Path(fixture_path).read_text())
    final, pred = replay_case(case, tools, on_update)
    if preds_path:
        with Path(preds_path).open("a") as f:
            f.write(json.dumps(pred) + "\n")
    return final


def _fixture_paths(args: list[str]) -> list[Path]:
    out: list[Path] = []
    for a in args:
        p = Path(a)
        out += sorted(p.glob("*.json")) if p.is_dir() else [p]
    return out


def show(state: SessionState) -> str:
    lines = [f"== {state.session_id}", "levels:"]
    lines += [
        f"  t={a.t:>5.0f}  {a.level.name:<7}  {a.reason}  buttons={a.buttons}" for a in state.alerts
    ] or ["  (none)"]
    lines += [
        f"user_choice: {state.user_choice}",
        "plan: " + ", ".join(f"{p.name}={p.status}" for p in state.plan),
        "trace:",
    ]
    lines += [f"  t={x.t:>5.0f}  {x.node:<22} {x.action:<28} {x.result}" for x in state.trace]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("fixtures", nargs="+")
    ap.add_argument("--preds", type=Path)
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    if args.preds:
        args.preds.write_text("")
    for path in _fixture_paths(args.fixtures):
        final = replay(path, preds_path=args.preds)
        if args.show:
            print(show(final) + "\n")


if __name__ == "__main__":
    main()
