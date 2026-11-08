"""One compiled graph with two phases, invoked once per event with only {"event": e}.

During: route by event kind -> caller_screen | signal_watcher | guardian -> decide -> alert -> END.
After (from call_end, when any alert >= whisper): planner -> router -> step -> router ... -> END.

Both phases live in one StateGraph rather than a compiled subgraph node: a same-schema subgraph returns its whole
final state to the parent, which re-appends every operator.add list (checked against langgraph 1.0.10).
"""

from __future__ import annotations

from enum import Enum

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

import contracts.events
import contracts.state
from contracts.state import Level
from services.agents.graph import stubs
from services.agents.graph.deps import Tools
from services.agents.graph.state import GraphState
from services.agents.nodes import after, during

EVENT_NODE = {
    "sms_otp": "signal_watcher",
    "bank_app_traffic": "signal_watcher",
    "account_change": "signal_watcher",
    "turn": "guardian",
    "user_choice": "record_choice",
    "call_end": "end_call",
}


def route_event(state: GraphState) -> str:
    e = state.event
    if e is None:
        return END
    if e.kind == "call_start":
        return "emergency" if stubs.is_emergency(e.number) else "caller_screen"
    if state.caller and stubs.is_emergency(state.caller.number):
        return END  # R1: nothing runs on an emergency call
    return EVENT_NODE[e.kind]


def needs_aftercare(state: GraphState) -> str:
    worst = max((a.level for a in state.alerts), default=Level.none)
    return "planner" if worst >= Level.whisper else END


def _contract_types() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for mod in (contracts.events, contracts.state):
        for name, obj in vars(mod).items():
            if isinstance(obj, type) and obj.__module__ == mod.__name__ and issubclass(obj, BaseModel | Enum):
                out.append((mod.__name__, name))
    return out


def new_checkpointer() -> InMemorySaver:
    """In memory only. The checkpoint holds turn text, so never swap in a persistent saver (R8)."""
    return InMemorySaver(serde=JsonPlusSerializer(allowed_msgpack_modules=_contract_types()))


def build_graph(tools: Tools, checkpointer: InMemorySaver | None = None) -> CompiledStateGraph:
    g = StateGraph(GraphState)

    # during
    g.add_node("emergency", during.emergency)
    g.add_node("caller_screen", during.make_caller_screen(tools))
    g.add_node("signal_watcher", during.signal_watcher)
    g.add_node("guardian", during.guardian)
    g.add_node("decide", during.make_decide(tools))
    g.add_node("alert", during.make_alert(tools))
    g.add_node("record_choice", during.record_choice)
    g.add_node("end_call", during.end_call)

    g.add_conditional_edges(
        START, route_event, ["emergency", "caller_screen", *set(EVENT_NODE.values()), END]
    )
    for n in ("caller_screen", "signal_watcher", "guardian"):
        g.add_edge(n, "decide")
    g.add_edge("decide", "alert")
    for n in ("alert", "emergency", "record_choice"):
        g.add_edge(n, END)
    g.add_conditional_edges("end_call", needs_aftercare, ["planner", END])

    # after
    g.add_node("planner", after.planner)
    g.add_node("router", after.router)
    for name in after.STEPS:
        g.add_node(name, after.make_step(name, tools))
        g.add_edge(name, "router")
    g.add_edge("planner", "router")
    g.add_conditional_edges("router", after.route_after, [*after.STEPS, END])

    return g.compile(checkpointer=checkpointer or new_checkpointer())
