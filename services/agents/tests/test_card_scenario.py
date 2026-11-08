"""The live demo script: one card-fraud call, cut at three points.

S1: the customer never picks up -> nothing runs. S2: they hear the card ask, get the alert and hang up ->
no callback. S3: they read the card out -> callback to connect the bank. Offline (keyword Guardian, no LLM).
The planner gets the full transcript, and it is erased from memory when the after-call work ends.
"""

from __future__ import annotations

from typing import Any

from contracts.events import CallEnd, CallStart, Direction, Event, Source, Turn
from contracts.state import Level
from services.agents.graph.runner import Session
from services.agents.graph.state import GraphState
from services.agents.graph.stubs import fake_tools, offline_structured
from services.agents.nodes import after
from services.agents.nodes.during import keyword_guardian
from services.agents.prompts import PlannerOutput

SID = "card"


def _turn(t: float, who: str, text: str) -> Turn:
    return Turn(session_id=SID, t=t, source=Source.network, speaker=who, text=text)  # type: ignore[arg-type]


START = CallStart(
    session_id=SID,
    t=0,
    source=Source.network,
    direction=Direction.inbound,
    number="+15550142",
    first_seen=True,
)
OPENING = [
    _turn(
        2,
        "caller",
        "Hi, this is Daniel from the Lone Star Bank fraud department. Am I speaking with the cardholder?",
    ),
    _turn(8, "customer", "Yes."),
    _turn(14, "caller", "We flagged a 1,240 dollar charge in Ohio on your debit card. Did you make it?"),
    _turn(20, "customer", "No."),
    _turn(
        26, "caller", "I'll block it now. Please don't hang up and don't call the branch, it resets the case."
    ),
    _turn(
        40,
        "caller",
        "To block the card I need to verify it. Please read me the 16-digit card number on the front.",
    ),
]
GAVE_CARD = [
    _turn(52, "customer", "Okay, it's 4 2 4 2, 4 2 4 2, 4 2 4 2, 4 2 4 2."),
    _turn(58, "caller", "Thank you. And the expiration date and the security code on the back?"),
    _turn(66, "customer", "Twelve twenty eight, and the code is one two three."),
]


def _run(events: list[Event]) -> tuple[Session, list[tuple[str, dict[str, Any]]]]:
    s = Session(SID, fake_tools(), guardian=keyword_guardian, structured=offline_structured)
    out: list[tuple[str, dict[str, Any]]] = []
    for e in events:
        out += s.feed(e)
    return s, out


def _graph(s: Session) -> GraphState:
    return GraphState.model_validate(s.graph.get_state(s.config).values)


def test_s1_unanswered_call_does_nothing() -> None:
    s, _ = _run([START, CallEnd(session_id=SID, t=30, source=Source.network)])
    st = s.state()
    assert st.alerts == [] and st.plan == []


def test_s2_card_ask_alerts_and_hanging_up_means_no_callback() -> None:
    s, _ = _run([START, *OPENING, CallEnd(session_id=SID, t=45, source=Source.network)])
    st = s.state()
    assert any(f.kind == "card_details" for f in st.flags)
    alert = next(a for a in st.alerts if a.level == Level.alert)
    assert alert.t == 40 and "card number" in alert.reason
    names = [p.name for p in st.plan]
    assert "callback" not in names and names[-1] == "evidence"
    planner = next(x for x in st.trace if x.node == "planner")
    assert "customer handed over details: no" in planner.result
    assert _graph(s).transcript_full == [] and _graph(s).transcript_window == []  # erased after aftercare


def test_s3_customer_reads_the_card_out_so_we_call_back() -> None:
    s, _ = _run([START, *OPENING, *GAVE_CARD, CallEnd(session_id=SID, t=75, source=Source.network)])
    st = s.state()
    plan = {p.name: p for p in st.plan}
    assert plan["callback"].status == "done" and plan["recovery"].status == "done"
    planner = next(x for x in st.trace if x.node == "planner")
    assert "customer handed over details: yes (customer read out digits)" in planner.result
    assert "4 2 4 2" not in " ".join(x.result for x in st.trace)  # digits never reach the trace
    assert _graph(s).transcript_full == []


def _planner_says_yes(customer_line: str) -> tuple[Session, dict[str, str]]:
    seen: dict[str, str] = {}

    def fake(system: str, user: str, model: type, *a: Any, **k: Any) -> Any:
        if model is PlannerOutput:
            seen["user"] = user
            return PlannerOutput(
                steps=["recovery", "evidence"], rationale="Card read out.", customer_disclosed=True
            )
        raise RuntimeError("offline")

    s = Session(SID, fake_tools(), guardian=keyword_guardian, structured=fake)
    for e in [
        START,
        *OPENING,
        _turn(50, "customer", customer_line),
        CallEnd(session_id=SID, t=60, source=Source.network),
    ]:
        s.feed(e)
    return s, seen


def test_planner_sees_the_transcript_and_its_yes_counts_with_some_digits() -> None:
    s, seen = _planner_says_yes("It starts 4 2 4, hold on.")
    assert "<transcript>" in seen["user"] and "16-digit card number" in seen["user"]
    assert "callback" in [p.name for p in s.state().plan]  # required: the customer started reading it out


def test_planner_yes_without_any_digits_is_ignored() -> None:
    """Live Nemotron once said the card was given when the customer had only been asked for it."""
    s, _ = _planner_says_yes("Hold on, let me think about it.")
    st = s.state()
    assert "callback" not in [p.name for p in st.plan]
    planner = next(x for x in st.trace if x.node == "planner")
    assert "customer handed over details: no" in planner.result and "ignored" in planner.result


def test_card_flag_needs_an_actual_card_ask() -> None:
    from services.agents.nodes.guardian import CARD_ASK

    assert CARD_ASK.search("Can you read me the 16-digit card number on the front?")
    assert CARD_ASK.search("And the three-digit security code on the back?")
    assert not CARD_ASK.search("I'm going to block the card right now. Please don't hang up.")


def test_digit_counter() -> None:
    st = GraphState(session_id="x", transcript_full=[_turn(1, "customer", "It's four one one one, two two")])
    assert after.customer_read_out_digits(st)
    st = GraphState(
        session_id="x", transcript_full=[_turn(1, "customer", "No, I won't give you that, one moment")]
    )
    assert not after.customer_read_out_digits(st)
    st = GraphState(session_id="x", transcript_full=[_turn(1, "caller", "Read me 4242 4242 4242 4242")])
    assert not after.customer_read_out_digits(st)  # only the customer's own words count
