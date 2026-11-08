"""Replay fixture sessions through the graph, as if live.

    python -m services.agents.graph.runner evals/fixtures --preds preds.jsonl --show [--offline]

Each event is sent as {"event": e}; the in-memory checkpointer (thread_id = session_id) holds the rest.
`on_update(node, update)` gets each node's update with graph-only fields removed (no transcript, R8).
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig

from contracts.events import EvalCase, Event
from contracts.state import Risk, SessionState
from services.agents import llm
from services.agents.graph.build import build_graph
from services.agents.graph.deps import Tools
from services.agents.graph.state import public_state, public_update
from services.agents.graph.stubs import fake_tools, offline_structured
from services.agents.nodes.during import Node, Structured, keyword_guardian

OnUpdate = Callable[[str, dict[str, Any]], None]


class Session:
    """One call: one graph, one in-memory checkpointer (thread_id = session_id). Feed events in order.

    Used by replay and by the API. Not safe to feed from two threads at once; the API gives each session one worker.
    """

    def __init__(
        self,
        session_id: str,
        tools: Tools | None = None,
        guardian: Node | None = None,
        structured: Structured = llm.structured,
    ) -> None:
        self.session_id = session_id
        self.graph = build_graph(
            tools or fake_tools(), guardian=guardian, structured=structured
        )  # real adapters: here
        self.config: RunnableConfig = {"configurable": {"thread_id": session_id}}
        self._started = False
        self._lock = threading.RLock()  # on_update may call state() while feed() holds it
        self.snapshot = SessionState(session_id=session_id)

    def feed(self, event: Event, on_update: OnUpdate | None = None) -> list[tuple[str, dict[str, Any]]]:
        """Run the graph for one event. Returns each node's public update (no graph-only fields, R8).

        `self.snapshot` is kept current as updates arrive, so on_update can read the state after each node.
        (Checkpoints are written in the background while streaming, so get_state() can lag mid-run.)
        """
        with self._lock:
            inp: dict[str, Any] = {"event": event}
            if not self._started:
                inp["session_id"] = self.session_id
                self._started = True
            out: list[tuple[str, dict[str, Any]]] = []
            for chunk in self.graph.stream(inp, self.config, stream_mode="updates"):
                for node, update in chunk.items():
                    pub = public_update(update or {})
                    if pub:
                        self.snapshot = _apply(self.snapshot, pub)
                        out.append((node, pub))
                        if on_update:
                            on_update(node, pub)
            self.snapshot = self.state()  # settle on the checkpoint once the run is done
            return out

    def state(self) -> SessionState:
        """The checkpointed state. Exact between events; use `snapshot` inside on_update."""
        with self._lock:
            if not self._started:
                return SessionState(session_id=self.session_id)
            return public_state(self.graph.get_state(self.config).values)


_APPEND = ("flags", "signals", "alerts", "trace")  # operator.add fields in SessionState


def _apply(state: SessionState, update: dict[str, Any]) -> SessionState:
    """Apply one node's public update the way the graph's reducers do."""
    changes = {k: (getattr(state, k) + v if k in _APPEND else v) for k, v in update.items()}
    return state.model_copy(update=changes)


def replay_case(
    case: EvalCase,
    tools: Tools | None = None,
    on_update: OnUpdate | None = None,
    guardian: Node | None = None,
    structured: Structured = llm.structured,
) -> tuple[SessionState, dict[str, Any]]:
    """Returns the final state and the prediction row for evals/run_eval.py."""
    session = Session(case.session_id, tools, guardian, structured)
    risk = Risk(score=0.0)
    pred_alerts: list[dict[str, Any]] = []
    latency_ms: list[float] = []

    for event in case.events:
        start = time.perf_counter()
        for _, pub in session.feed(event, on_update):
            risk = pub.get("risk", risk)
            for a in pub.get("alerts", []):
                pred_alerts.append({"t": a.t, "level": a.level.name, "score": round(risk.score, 3)})
        if event.kind != "call_end":  # after-call work is not on the live path
            latency_ms.append(round((time.perf_counter() - start) * 1000, 2))

    return session.state(), {"session_id": case.session_id, "alerts": pred_alerts, "latency_ms": latency_ms}


def replay(
    fixture_path: str | Path,
    on_update: OnUpdate | None = None,
    preds_path: str | Path | None = None,
    tools: Tools | None = None,
    guardian: Node | None = None,
    structured: Structured = llm.structured,
) -> SessionState:
    case = EvalCase.model_validate_json(Path(fixture_path).read_text())
    final, pred = replay_case(case, tools, on_update, guardian, structured)
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
    ap.add_argument(
        "--offline", action="store_true", help="no LLM: keyword Guardian, template wording, fallback planner"
    )
    args = ap.parse_args()
    if args.preds:
        args.preds.write_text("")
    for path in _fixture_paths(args.fixtures):
        final = replay(
            path,
            preds_path=args.preds,
            guardian=keyword_guardian if args.offline else None,
            structured=offline_structured if args.offline else llm.structured,
        )
        if args.show:
            print(show(final) + "\n")


if __name__ == "__main__":
    main()
