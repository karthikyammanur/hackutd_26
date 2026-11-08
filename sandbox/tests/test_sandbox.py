"""Offline tests: no network, fake Nemotron and Jev."""

from __future__ import annotations

import json

import pytest

from sandbox import review as reviewer
from sandbox import scoring
from sandbox.data import parse_session
from sandbox.graph import build_graph, compose_state, run_call
from sandbox.jev import JevResult, build_questions, parse_answer
from sandbox.llm import LLMError, parse_json_model
from sandbox.run import write_outputs

SECRET_LINE = "read me the code from your phone"


def row(scam=True, type_="bank_safe_account", sid="S-1"):
    return {
        "session_id": sid,
        "label": {"scam": scam, "type": type_, "money_moment_t": 30 if scam else None},
        "events": [
            {"t": -50, "kind": "dns", "domain": "x.work", "domainAgeDays": 2},
            {
                "t": 0,
                "kind": "call_start",
                "direction": "inbound",
                "caller": "first_seen",
                "number": "+15555550100",
            },
            {"t": 5, "kind": "turn", "who": "caller", "text": "Hello from your bank."},
            {"t": 9, "kind": "turn", "who": "customer", "text": "Hi."},
            {"t": 20, "kind": "sms_otp", "sender": "Bank"},
            {"t": 25, "kind": "turn", "who": "caller", "text": SECRET_LINE},
            {"t": 40, "kind": "call_end"},
        ],
    }


class FakeAgent:
    def __init__(self, fail=False):
        self.fail = fail

    def brief(self, previous, new_lines):
        if self.fail:
            raise RuntimeError("down")
        return "note", 3


class FakeJev:
    def __init__(self, tiers):
        self.tiers = list(tiers)
        self.states = []

    def classify(self, state):
        self.states.append(state)
        tier = self.tiers.pop(0)
        if tier == "error":
            raise RuntimeError("jev down")
        probs = {"safe": 0.1, "uncertain": 0.1, "dangerous": 0.1, tier: 0.8}
        return JevResult(tier, probs, {"asks_for_code": 0.9}, 10, 5, 7)


def run(tiers, data=None, agent=None):
    session = parse_session(data or row())
    jev = FakeJev(tiers)
    return run_call(build_graph(agent or FakeAgent(), jev), session), jev


def test_frames_only_see_the_past_and_skip_precall_dns():
    frames = parse_session(row()).frames
    assert [f.trigger for f in frames] == ["turn", "sms_otp", "turn"]
    assert all(SECRET_LINE not in " ".join(f.window) for f in frames[:2])
    assert SECRET_LINE in frames[2].latest


def test_label_leaking_caller_field_never_reaches_jev():
    _, jev = run(["safe", "safe", "safe"])
    assert all("first_seen" not in s and "+1555" not in s for s in jev.states)


@pytest.mark.parametrize(
    ("scam", "tier", "outcome", "points"),
    [
        (True, "dangerous", "caught", 1.0),
        (True, "uncertain", "soft_miss", 0.5),
        (True, "safe", "missed", 0.0),
        (False, "safe", "clear", 1.0),
        (False, "uncertain", "soft_false_alarm", 0.5),
        (False, "dangerous", "false_alarm", 0.0),
    ],
)
def test_outcomes(scam, tier, outcome, points):
    result, _ = run([tier] * 3, row(scam=scam, type_="t"))
    scored = scoring.score_call(result)
    assert (scored.outcome, scored.points) == (outcome, points)


def test_risk_never_goes_down_across_frames():
    result, _ = run(["dangerous", "safe", "safe"])
    assert result.tier == "dangerous"
    assert result.first_dangerous_t == 5


def test_jev_failure_leaves_tier_alone_and_is_counted():
    result, _ = run(["uncertain", "error", "safe"])
    assert result.tier == "uncertain"
    board = scoring.build_scoreboard([result], [scoring.score_call(result)])
    assert board["delivery"]["jev_failures"] == 1
    assert board["delivery"]["delivered"] == 2


def test_all_frames_failed_is_no_verdict_not_safe():
    result, _ = run(["error", "error", "error"])
    assert scoring.score_call(result).outcome == "no_verdict"


def test_agent_failure_still_sends_the_verbatim_turn():
    result, jev = run(["safe", "safe", "dangerous"], agent=FakeAgent(fail=True))
    assert all(not f.agent_ok for f in result.frames)
    assert SECRET_LINE in jev.states[-1]
    assert result.frames[-1].delivered


def test_compose_state_keeps_transcript_as_given():
    session = parse_session(row())
    assert session.frames[-1].latest in compose_state(session, session.frames[-1], "note")


def test_jev_payload_and_response_shape():
    questions = build_questions()
    assert set(questions["danger_tier"]["criteria"]) == {"safe", "uncertain", "dangerous"}
    answers = {name: {"type": "noul", "noul": 0.2} for name in questions if name != "danger_tier"}
    answers["danger_tier"] = {
        "type": "choice",
        "choice": "dangerous",
        "confidence": 0.8,
        "probabilities": {"safe": 0.1, "uncertain": 0.1, "dangerous": 0.8},
    }
    parsed = parse_answer({"answers": answers, "usage": {"input_tokens": 1, "output_tokens": 2}}, 9)
    assert parsed.tier == "dangerous" and parsed.input_tokens == 1


def test_llm_output_must_validate():
    good = parse_json_model('<think>hm</think> {"overall": "x"}', reviewer.Review)
    assert good.overall == "x"
    with pytest.raises(LLMError):
        parse_json_model("not json", reviewer.Review)
    with pytest.raises(LLMError):
        parse_json_model('{"wrong": 1}', reviewer.Review)


def test_review_drops_invented_evidence():
    rec = {
        "pattern": "p",
        "scam_types": ["t"],
        "failure_kind": "missed_scam",
        "likely_cause": "c",
        "fix": "f",
        "fix_target": "jev_questions",
        "priority": "high",
    }
    review = reviewer.Review(
        overall="o",
        recommendations=[
            reviewer.Recommendation(**rec, evidence_session_ids=["S-1", "S-FAKE"]),
            reviewer.Recommendation(**rec, evidence_session_ids=["S-FAKE"]),
        ],
    )
    kept = reviewer.keep_supported(review, [{"session_ids": ["S-1"]}])
    assert [r.evidence_session_ids for r in kept.recommendations] == [["S-1"]]


def test_consistent_failure_needs_repeat_runs():
    one = [{"run_id": "a", "type": "x", "error_rate": 0.5}]
    assert reviewer.consistent_failures(one) == []
    two = [
        *one,
        {"run_id": "b", "type": "x", "error_rate": 0.3},
        {"run_id": "b", "type": "y", "error_rate": 0.0},
    ]
    assert [c["type"] for c in reviewer.consistent_failures(two)] == ["x"]


def test_no_transcript_text_reaches_disk(tmp_path):
    result, _ = run(["safe", "uncertain", "safe"])
    rows = [scoring.score_call(result)]
    board = scoring.build_scoreboard([result], rows)
    review = reviewer.Review(overall="ok")
    write_outputs("r1", tmp_path / "out", tmp_path / "logs", [result], rows, board, review)
    written = "".join(p.read_text() for p in tmp_path.rglob("*") if p.is_file())
    assert SECRET_LINE not in written and "Hello from your bank" not in written
    assert json.loads((tmp_path / "out" / "scoreboard.json").read_text())["sessions"] == 1
