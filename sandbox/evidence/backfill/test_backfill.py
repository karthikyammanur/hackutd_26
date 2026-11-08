"""Offline tests against a mock evidence store."""

from datetime import UTC, datetime

import backfill as b
import pytest
from pii_scan import CorpusScanner, TextLeak

ANCHOR = datetime(2026, 11, 8, tzinfo=UTC)
LINE = "this is the bank fraud team please read me the code from your phone"


def result(case="gen-call-1", outcome="caught", tier="dangerous", method="bank_fraud_department", **extra):
    row = {
        "outcome": outcome,
        "tier": tier,
        "max_p_dangerous": 0.913,
        "first_dangerous_t": 47,
        "caught_before_money": True,
        "peak_flags": {"asks_for_code": 0.98, "threatens": 0.1, "claims_authority": 0.7},
    }
    return {"case_id": case, "model": "jev-latest", "method": method, "channel": "call", "weak": False, "predicted_method": "phantom_hacker", "row": row, **extra}


def state(tmp_path, today="2026-11-08"):
    return b.State(tmp_path / "state.json", today, ANCHOR)


class Store:
    def __init__(self, rows_written=None):
        self.bodies, self.rows_written = [], rows_written

    def __call__(self, body):
        self.bodies.append(body)
        return {} if self.rows_written is None else {"rows_written": self.rows_written * len(body["incidents"])}

    @property
    def ids(self):
        return [i["incident_id"] for body in self.bodies for i in body["incidents"]]


def many(count):
    return [result(case=f"gen-call-{i}") for i in range(count)]


def test_maps_fields_buckets_time_and_filters_flags():
    incident = b.to_incident(result(), "r1", ANCHOR)
    assert incident["source"] == "sandbox_synthetic" and incident["caller_cluster"] is None
    assert incident["family"] == "impersonation" and incident["first_alert_bucket_s"] == 45
    assert [s["signal"] for s in incident["signals"]] == ["asks_for_code", "claims_authority"]
    assert incident["money_moved_before_alert"] == 0 and incident["max_risk"] == 0.91
    assert incident["timeline"] == [{"seq": 0, "t_bucket_s": 45, "tier": "dangerous", "risk": 0.91}]
    assert incident["occurred_hour"].endswith(":00:00Z")


def test_hours_are_stable_and_within_ninety_days():
    first = b.to_incident(result(), "r1", ANCHOR)
    assert first == b.to_incident(result(), "r1", ANCHOR)
    moment = datetime.strptime(first["occurred_hour"], "%Y-%m-%dT%H:00:00Z").replace(tzinfo=UTC)
    assert 0 < (ANCHOR - moment).days + 1 <= 90


@pytest.mark.parametrize(
    "bad",
    [result(outcome="clear", tier="safe"), result(outcome="no_verdict", tier=None), result(weak=True), result(method="not_a_method"), result(channel="fax")],
)
def test_non_incidents_are_skipped(bad):
    assert b.to_incident(bad, "r1", ANCHOR) is None


def test_no_client_written_summary():
    assert "summary" not in b.to_incident(result(), "r1", ANCHOR)


@pytest.mark.parametrize("text", ["call 2145550147", "214-555-0147", "a@b.com", "go to https://x", "visit evil.click now"])
def test_privacy_guard_blocks_sensitive_text(text):
    incident = b.to_incident(result(), "r1", ANCHOR) | {"model": text}
    with pytest.raises(b.PrivacyError):
        b.assert_safe(incident)


def test_privacy_guard_blocks_extra_fields_and_clusters():
    incident = b.to_incident(result(), "r1", ANCHOR)
    with pytest.raises(b.PrivacyError):
        b.assert_safe(incident | {"transcript": "hello"})
    with pytest.raises(b.PrivacyError):
        b.assert_safe(incident | {"caller_cluster": "abc"})


def test_corpus_scan_catches_leaked_text_only():
    scanner = CorpusScanner([LINE])
    clean = b.to_incident(result(), "r1", ANCHOR)
    scanner.check_batch([clean])
    with pytest.raises(TextLeak):
        scanner.check_batch([clean | {"model": f"Note: {LINE}"}])


def test_incident_ids_are_not_flagged_as_sensitive():
    b.assert_safe(b.to_incident(result(), "r1", ANCHOR) | {"incident_id": "12345678-1234-5234-9234-123456789012"})


def test_batches_are_capped_at_100(tmp_path):
    store = Store(10)
    report = b.run_backfill(many(250), "r1", store, state(tmp_path))
    assert [len(body["incidents"]) for body in store.bodies] == [100, 100, 50]
    assert report["sent"] == 250 and report["stopped"] == "finished"


def test_budget_stops_before_overspending_and_uses_measured_cost(tmp_path):
    store = Store(10)
    s = state(tmp_path)
    s.rows_per_incident = 10
    report = b.run_backfill(many(500), "r1", store, s, budget=2500)
    assert report["stopped"] == "daily_row_budget" and report["sent"] == 200
    assert s.rows_today <= 2500 and s.rows_per_incident == 10


def test_conservative_cost_when_backend_does_not_report(tmp_path):
    store = Store()
    s = state(tmp_path)
    report = b.run_backfill(many(300), "r1", store, s, budget=8000)
    assert report["sent"] == 200 and s.rows_today == 8000


def test_resumes_next_day_without_repeats(tmp_path):
    results = many(300)
    first, second = Store(10), Store(10)
    today = state(tmp_path)
    today.rows_per_incident = 10
    b.run_backfill(results, "r1", first, today, budget=1000)
    assert len(first.ids) == 100
    assert state(tmp_path, "2026-11-08").rows_today == 1000
    tomorrow = state(tmp_path, "2026-11-09")
    assert tomorrow.rows_today == 0
    b.run_backfill(results, "r1", second, tomorrow, budget=1000)
    assert len(second.ids) == 100 and not set(first.ids) & set(second.ids)


def test_anchor_stays_fixed_across_days(tmp_path):
    s = state(tmp_path)
    b.run_backfill(many(1), "r1", Store(10), s)
    later = b.State(tmp_path / "state.json", "2026-12-25", datetime(2026, 12, 25, tzinfo=UTC))
    assert later.anchor_time() == ANCHOR


def test_max_incidents_limits_first_load(tmp_path):
    store = Store(10)
    report = b.run_backfill(many(500), "r1", store, state(tmp_path), max_incidents=200)
    assert len(store.ids) == 200 and report["stopped"] == "max_incidents"


def test_markers_never_pass_model_text_through():
    marker = {
        "session_id": "dg-sms-X1",
        "model": "jev-latest",
        "call_type": "delivery_fee",
        "got": "safe",
        "outcome": "missed",
        "max_p_dangerous": 0.1,
        "top_flags": "asks_to_move_money;threatens",
        "feedback": "SECRET FEEDBACK",
        "improvement": "SECRET IMPROVEMENT",
    }
    incident = b.to_incident(next(b.results_from_markers([marker])), "markers", ANCHOR)
    assert incident["channel"] == "sms" and {s["strength"] for s in incident["signals"]} == {0.5}
    assert "SECRET" not in str(incident)
