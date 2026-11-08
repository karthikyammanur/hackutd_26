"""Tests for the classifier matrix and statistics. No network and no Cloudflare runtime."""

import sys
from pathlib import Path

import pytest

from classify import parse_guard

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import classify as c  # noqa: E402
import pipeline as p  # noqa: E402
from taxonomy import METHODS  # noqa: E402


def report(model="jev-latest", method="bank_fraud_department", scam=True, tier="dangerous", weak=False, limited=0, predicted=None):
    session = {"session_id": "C1", "scam": scam, "scam_type": method, "money_moment_t": None}
    frames = [{"t": 1, "tier": tier, "p_dangerous": 0.9 if tier == "dangerous" else 0.1, "flags": {"asks_for_code": 0.9}, "delivered": True, "agent_called": False, "agent_ok": True}]
    return {
        "frames": 1,
        "decisions": 1,
        "rate_limited": limited,
        "steps": {"jev": {"count": 1, "errors": 0, "hist": {"100": 1}}},
        "results": [
            {
                "model": model,
                "row": p.score_call(session, frames),
                "predicted_method": predicted,
                "hard_flag": 0.9,
                "ms": 90,
                "scam": scam,
                "weak": weak,
                "method": method,
                "family": "impersonation",
                "channel": "call",
                "source": "datagen",
            }
        ],
    }


def test_jev_method_question_covers_taxonomy():
    question = c.jev_questions()["scam_method"]
    assert set(question["criteria"]) == set(METHODS)


def test_jev_matrix_parse():
    answers = {name: {"noul": 0.2} for name in p.FLAGS}
    answers["danger_tier"] = {"choice": "uncertain", "probabilities": {"safe": 0.3, "uncertain": 0.6, "dangerous": 0.1}}
    answers["scam_method"] = {"choice": "tech_support"}
    parsed = c.parse_jev_matrix({"answers": answers})
    assert parsed["method"] == "tech_support" and parsed["p_uncertain"] == 0.6


def test_direct_output_is_validated():
    good = c.parse_direct('{"tier":"dangerous","p_safe":0.1,"p_uncertain":0.1,"p_dangerous":0.8,"method":"tech_support","flags":["threatens","made_up"]}')
    assert good["tier"] == "dangerous" and set(good["flags"]) == {"threatens"}
    assert c.parse_direct('{"tier":"safe","p_safe":1,"p_uncertain":0,"p_dangerous":0,"method":"nope"}')["method"] is None
    for bad in ('{"tier":"maybe"}', '{"tier":"safe","p_safe":2,"p_uncertain":0,"p_dangerous":0}', "not json"):
        with pytest.raises(ValueError):
            c.parse_direct(bad)


def test_baseline_is_deterministic_and_sensible():
    scam = "CALLER: This is the bank fraud department. Read me the code we just sent, right now."
    assert c.baseline_classify(scam) == c.baseline_classify(scam)
    assert c.baseline_classify(scam)["tier"] == "dangerous"
    assert c.baseline_classify("CALLER: Your order is ready for pickup at the deli.")["tier"] == "safe"


def test_validate_run_caps():
    assert c.validate_run({"limit": 10, "lanes": 2})["models"] == ["safe-signal-guard"]
    for bad in ({"limit": 50001}, {"lanes": 129}, {"limit": True}, {"models": ["gpt"]}, {"channels": ["fax"]}):
        with pytest.raises(ValueError):
            c.validate_run(bad)


def test_filter_is_parameterized():
    where, args = c.corpus_filter({"channels": ["sms"], "methods": ["x' OR 1=1"], "sources": []})
    assert "OR 1=1" not in where and args == ["sms", "x' OR 1=1"]


def test_rescore_params():
    assert c.rescore_params({"dangerous_threshold": 0.7, "require_hard_flag": True}) == (0.7, 0.2, 1)
    with pytest.raises(ValueError):
        c.rescore_params({"dangerous_threshold": 3})


def test_weak_labels_stay_out_of_headline():
    live = c.new_live()
    c.absorb_report(live, report(weak=True), 1.0)
    assert live["models"] == {} and live["methods"] == {} and live["weak"]["n"] == 1


def test_absorb_and_view_are_measured():
    live = c.new_live()
    c.absorb_report(live, report(predicted="bank_fraud_department"), 1.0)
    c.absorb_report(live, report(scam=False, method="legitimate", tier="dangerous"), 2.5)
    run = {"id": "r", "status": "running", "total": 10, "lanes": 4, "error": ""}
    view = c.live_view(run, live, 3, {"instances_reported": 1, "endpoints": []}, 2.5)
    assert view["processed"] == 2 and view["lanes"] == {"configured": 4, "active": 3}
    bank = next(m for m in view["by_method"] if m["method"] == "bank_fraud_department")
    assert bank["caught"] == 1 and bank["method_accuracy"] == 1.0
    assert view["by_model"][0]["false_alarm_rate"] == 1.0
    assert {s["name"] for s in view["steps"]} >= {"frames", "agent", "jev", "score", "check"}
    assert view["decisions_per_s"] > 0


def test_rate_limit_streak_resets():
    live = c.new_live()
    c.absorb_report(live, report(limited=1), 1)
    c.absorb_report(live, report(limited=1), 2)
    assert live["rate_streak"] == 2
    c.absorb_report(live, report(), 3)
    assert live["rate_streak"] == 0


def test_rescored_rows():
    rows = [
        {"method": "m", "scam": 1, "tier": "dangerous", "n": 3, "method_ok": 2, "method_seen": 3},
        {"method": "m", "scam": 1, "tier": "safe", "n": 1, "method_ok": 0, "method_seen": 1},
        {"method": "m", "scam": 0, "tier": "none", "n": 1, "method_ok": 0, "method_seen": 0},
    ]
    item = c.rescored_rows(rows, "method")[0]
    assert (item["caught"], item["missed"], item["no_verdict"], item["n"]) == (3, 1, 1, 5)
    assert item["score"] == 0.6 and item["method_accuracy"] == 0.5


def test_histogram_quantile_is_close():
    hist = {}
    for ms in range(1, 1001):
        c.hist_add(hist, ms)
    assert 450 <= c.hist_quantile(hist, 0.5) <= 550


def test_pacer_spaces_concurrent_callers_and_holds_the_global_rate():
    pacer = c.BrevPacer(lanes=8, max_rps=16)
    assert [pacer.reserve(100.0) for _ in range(3)] == [0.0, 0.5, 1.0]
    assert pacer.reserve(200.0) == 0.0


def test_finished_rate_excludes_check_time():
    live = c.new_live()
    c.absorb_report(live, report(), 2.0)
    assert c.decisions_rate(live, 100.0, finished=True) == 0.5


def test_parse_guard_validates_the_reply():
    answer = parse_guard({"tier": "dangerous", "p_dangerous": 0.95, "p_uncertain": 0.0, "flags": {"asks_for_code": 0.8, "made_up": 1.0}})
    assert answer["tier"] == "dangerous" and answer["method"] is None and answer["flags"] == {"asks_for_code": 0.8}
    for bad in ({"tier": "fine"}, {"tier": "safe", "p_dangerous": 2, "p_uncertain": 0, "flags": {}}, {"tier": "safe", "p_dangerous": 0, "p_uncertain": 0}):
        with pytest.raises(ValueError):
            parse_guard(bad)
