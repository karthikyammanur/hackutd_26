"""Tests for the pure pipeline logic. No network and no Cloudflare runtime."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pipeline as p  # noqa: E402

SECRET = "read me the code from your phone"
EVENTS = [
    {"t": 5, "kind": "turn", "who": "caller", "text": "Hello from your bank."},
    {"t": 9, "kind": "turn", "who": "customer", "text": "Hi."},
    {"t": 20, "kind": "sms_otp", "sender": "Bank"},
    {"t": 25, "kind": "turn", "who": "caller", "text": SECRET},
]


def session(scam=True, scam_type="x"):
    return {
        "session_id": "S-1",
        "scam": scam,
        "scam_type": scam_type,
        "money_moment_t": 30 if scam else None,
        "direction": "inbound",
        "events": EVENTS,
    }


def frame(tier, t=5):
    if tier is None:
        return {"t": t, "tier": None, "delivered": False, "agent_called": False, "agent_ok": True}
    return {
        "t": t,
        "tier": tier,
        "p_dangerous": 0.9 if tier == "dangerous" else 0.1,
        "flags": {"asks_for_code": 0.8, "threatens": 0.1},
        "delivered": True,
        "agent_called": False,
        "agent_ok": True,
    }


def test_frames_only_see_the_past():
    frames = p.build_frames(EVENTS)
    assert [f["trigger"] for f in frames] == ["turn", "sms_otp", "turn"]
    assert SECRET not in " ".join(frames[1]["window"])
    assert SECRET in frames[2]["latest"]


def test_agent_gets_each_scrolled_out_turn_once():
    events = [{"t": i, "kind": "turn", "who": "caller", "text": f"line {i}"} for i in range(9)]
    handed = [line for f in p.build_frames(events) for line in f["scrolled_out"]]
    assert handed == ["CALLER: line 0", "CALLER: line 1", "CALLER: line 2"]


def test_state_keeps_newest_turn_and_excludes_labels():
    s = session()
    f = p.build_frames(EVENTS)[2]
    state = p.compose_state(s, f, "note")
    assert f["latest"] in state
    assert "scam" not in state.lower()


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
    row = p.score_call(session(scam), [frame(tier)])
    assert (row["outcome"], row["points"]) == (outcome, points)


def test_risk_never_goes_down_and_timing_is_recorded():
    row = p.score_call(session(True), [frame("dangerous", 5), frame("safe", 10)])
    assert row["tier"] == "dangerous"
    assert row["first_dangerous_t"] == 5
    assert row["caught_before_money"] is True


def test_no_answers_is_no_verdict_not_safe():
    assert p.score_call(session(False), [frame(None)])["outcome"] == "no_verdict"


def test_jev_response_is_validated():
    answers = {name: {"noul": 0.2} for name in p.FLAGS}
    answers["danger_tier"] = {"choice": "dangerous", "probabilities": {"dangerous": 0.8}}
    assert p.parse_jev({"answers": answers})["tier"] == "dangerous"
    with pytest.raises(ValueError):
        p.parse_jev({"answers": {}})


def test_check_output_is_validated_and_cleaned():
    good = p.parse_check('<think>x</think>{"marker": "Bad Label!", "feedback": "why", "improvement": "how"}')
    assert good["marker"] == "bad_label"
    with pytest.raises(ValueError):
        p.parse_check('{"marker": "x"}')
    with pytest.raises(ValueError):
        p.parse_check("not json")


def test_failed_check_still_produces_a_marker():
    row = p.score_call(session(False), [frame("dangerous")])
    marker = p.make_marker(row, None)
    assert marker["marker"] == "check_agent_failed"
    assert marker["outcome"] == "false_alarm"
    assert marker["top_flags"] == "asks_for_code"


def test_csv_neutralizes_formulas():
    row = p.score_call(session(False), [frame("dangerous")])
    marker = p.make_marker(row, {"marker": "m", "feedback": "=HYPERLINK(1)", "improvement": "ok"})
    text = p.markers_csv([marker])
    assert text.splitlines()[0].startswith("session_id,call_type")
    assert "'=HYPERLINK" in text


def test_summary_counts():
    rows = [p.score_call(session(True), [frame("dangerous")]), p.score_call(session(False), [frame("uncertain")])]
    summary = p.summarize(rows)
    assert summary["scam_catch_rate"] == 1.0
    assert summary["benign_uncertain_rate"] == 1.0
    assert summary["benign_false_alarm_rate"] == 0.0
    assert summary["overall_score"] == 0.75


def test_check_input_has_no_private_fields():
    row = p.score_call(session(True), [frame("safe")])
    text = p.check_case_text(row, session(True))
    assert "<case>" in text and SECRET in text


def test_sms_is_a_single_frame_and_labels_stay_out():
    sms = [{"t": 0, "kind": "sms", "from_type": "longcode", "text": "Toll due at pay-x.click", "domain": "pay-x.click", "domain_age_days": 3}]
    frames = p.build_frames(sms)
    assert len(frames) == 1 and frames[0]["sms"]["from_type"] == "longcode"
    state = p.compose_state({"direction": "inbound"}, frames[0], "")
    assert "Toll due" in state and "domain age 3 days" in state


def test_window_turns_is_configurable():
    events = [{"t": i, "kind": "turn", "who": "caller", "text": f"l{i}"} for i in range(5)]
    assert len(p.build_frames(events, window_turns=2)[-1]["window"]) == 2


def test_unlabeled_case_is_not_scored():
    row = p.score_call({**session(True), "scam": None}, [frame("dangerous")])
    assert row["outcome"] == "unlabeled" and row["points"] == 0.0
