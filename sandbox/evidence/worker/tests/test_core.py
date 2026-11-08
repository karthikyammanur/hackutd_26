"""Runs the same SQL as production against SQLite, including FTS5 and query plans."""

import hashlib
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

WORKER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKER / "src"))

import core  # noqa: E402

CREATED = "2026-11-08T05:00:00Z"
TODAY = date(2026, 11, 8)


def incident(**overrides):
    base = {
        "incident_id": "a" * 32,
        "occurred_hour": "2026-11-07T14:00:00Z",
        "channel": "call",
        "source": "sandbox_synthetic",
        "method": "bank_fraud_department",
        "family": "impersonation",
        "predicted_method": "tech_support",
        "tier": "dangerous",
        "outcome": "caught",
        "max_risk": 0.92,
        "first_alert_bucket_s": 45,
        "duration_bucket_s": 180,
        "money_moved_before_alert": 0,
        "model": "jev-latest",
        "caller_cluster": "ab12" * 8,
        "signals": [
            {"signal": "asks_for_code", "strength": 0.98},
            {"signal": "claims_authority", "strength": 0.8},
        ],
        "timeline": [
            {"seq": 0, "t_bucket_s": 15, "tier": "safe", "risk": 0.1},
            {"seq": 1, "t_bucket_s": 45, "tier": "dangerous", "risk": 0.92},
        ],
    }
    base.update(overrides)
    return base


@pytest.fixture
def db():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript((WORKER / "migrations" / "0001_init.sql").read_text())
    return connection


def store(db, raw_list):
    incidents = core.validate_batch({"incidents": raw_list})
    for sql, param in core.insert_statements(incidents, CREATED):
        db.execute(sql, (param,))
    db.commit()


def rows(db, sql, args=()):
    return [dict(r) for r in db.execute(sql, args).fetchall()]


def many(n, **overrides):
    return [
        incident(incident_id=hashlib.sha256(str(i).encode()).hexdigest()[:32], **overrides) for i in range(n)
    ]


@pytest.mark.parametrize(
    ("patch", "field"),
    [
        ({"method": "call 214-555-0147"}, "method"),
        ({"method": "bob@example.com"}, "method"),
        ({"model": "https://evil.example/x"}, "model"),
        ({"channel": "2145550147"}, "channel"),
        ({"incident_id": "caller-2145550147"}, "incident_id"),
        ({"occurred_hour": "2026-11-07T14:37:00Z"}, "occurred_hour"),
        ({"occurred_hour": "2026-13-07T14:00:00Z"}, "occurred_hour"),
        ({"first_alert_bucket_s": 47}, "first_alert_bucket_s"),
        ({"caller_cluster": "2145550147214555"}, "caller_cluster"),
        ({"caller_cluster": "+1 214 555 0147"}, "caller_cluster"),
        ({"family": "none"}, "family"),
        ({"max_risk": float("nan")}, "max_risk"),
        ({"max_risk": True}, "max_risk"),
        ({"source": "live", "outcome": "caught"}, "outcome"),
        ({"signals": [{"signal": "my name is Rosa", "strength": 1}]}, "signals.signal"),
        ({"signals": [{"signal": "asks_for_code", "strength": 1, "quote": "read me the code"}]}, "signals"),
        (
            {"timeline": [{"seq": 0, "t_bucket_s": 15, "tier": "safe", "risk": 0.1, "text": "hello"}]},
            "timeline",
        ),
        ({"timeline": [{"seq": 0, "t_bucket_s": 16, "tier": "safe", "risk": 0.1}]}, "timeline.t_bucket_s"),
    ],
)
def test_rejects_private_or_malformed_values(patch, field):
    with pytest.raises(core.ValidationError) as caught:
        core.validate_batch({"incidents": [incident(**patch)]})
    assert caught.value.field == field or caught.value.reason == "contains_pii"


@pytest.mark.parametrize("extra", ["customer_id", "transcript", "text", "quote", "phone", "summary", "name"])
def test_rejects_every_field_outside_the_schema(extra):
    with pytest.raises(core.ValidationError) as caught:
        core.validate_batch({"incidents": [incident(**{extra: "x"})]})
    assert caught.value.reason == "unknown_field"


def test_error_never_echoes_the_rejected_value():
    secret = "bob@example.com"
    with pytest.raises(core.ValidationError) as caught:
        core.validate_batch({"incidents": [incident(method=secret)]})
    assert secret not in json.dumps(caught.value.body())


def test_batch_is_all_or_nothing(db):
    with pytest.raises(core.ValidationError) as caught:
        store(db, [incident(), incident(incident_id="b" * 32, method="call 2145550147")])
    assert caught.value.index == 1
    assert rows(db, "SELECT COUNT(*) AS n FROM incidents")[0]["n"] == 0


def test_batch_limits_and_duplicates():
    with pytest.raises(core.ValidationError):
        core.validate_batch({"incidents": many(core.MAX_BATCH + 1)})
    with pytest.raises(core.ValidationError):
        core.validate_batch({"incidents": [incident(), incident()]})
    with pytest.raises(core.ValidationError):
        core.validate_batch({"incidents": [incident()], "extra": 1})


def test_summary_comes_only_from_indicators():
    item = core.validate_incident(incident())
    assert item["summary"].startswith("Dangerous call incident classified as bank fraud department")
    assert "asks for code" in item["summary"]
    assert not core.contains_pii(item["summary"])


def test_store_populates_every_table_and_is_idempotent(db):
    store(db, [incident()])
    store(db, [incident()])
    assert rows(db, "SELECT COUNT(*) AS n FROM incidents")[0]["n"] == 1
    assert rows(db, "SELECT COUNT(*) AS n FROM incident_signals")[0]["n"] == 2
    assert rows(db, "SELECT COUNT(*) AS n FROM incident_timeline")[0]["n"] == 2
    assert rows(db, "SELECT COUNT(*) AS n FROM incidents_fts")[0]["n"] == 1
    assert rows(db, "SELECT n FROM rollup_daily")[0]["n"] == 1
    assert rows(db, "SELECT SUM(n) AS n FROM rollup_signal_daily")[0]["n"] == 2


def test_null_outcome_rolls_up_as_one_group(db):
    store(db, [incident(incident_id="a" * 32, outcome=None), incident(incident_id="b" * 32, outcome=None)])
    assert [r["n"] for r in rows(db, "SELECT n FROM rollup_daily WHERE outcome=''")] == [2]


def run_list(db, query, limit=25):
    filters = core.parse_filters({k: [v] for k, v in query.items()}, core.LIST_PARAMS)
    sql, args, mode = core.build_list_query(filters, limit + 1)
    found = rows(db, sql, args)
    return found, core.next_cursor(found, mode, limit)


@pytest.mark.parametrize(
    "query",
    [{}, {"signal": "asks_for_code"}, {"q": "bank fraud"}, {"method": "bank_fraud_department"}],
)
def test_keyset_pagination_visits_each_row_once(db, query):
    store(db, many(23))
    seen, cursor = [], None
    for _ in range(10):
        params = {**query, **({"cursor": cursor} if cursor else {})}
        page, cursor = run_list(db, params, limit=10)
        seen.extend(r["incident_id"] for r in page[:10])
        if not cursor:
            break
    assert len(seen) == 23 == len(set(seen))


def test_search_is_safe_against_fts_syntax(db):
    store(db, [incident()])
    assert run_list(db, {"q": 'bank" OR tier:* NEAR('})[0] == []
    assert len(run_list(db, {"q": "bank fraud"})[0]) == 1
    assert len(run_list(db, {"q": "asks_for_code"})[0]) == 1
    with pytest.raises(core.ValidationError):
        run_list(db, {"q": "!!!"})


@pytest.mark.parametrize(
    ("params", "reason"),
    [
        ({"limit": ["101"]}, "out_of_range"),
        ({"limit": ["-1"]}, "out_of_range"),
        ({"method": ["nope"]}, "not_allowed"),
        ({"from": ["2026-02-31"]}, "bad_date"),
        ({"evil": ["1"]}, "unknown_parameter"),
        ({"tier": ["safe", "dangerous"]}, "repeated_parameter"),
    ],
)
def test_bad_filters(params, reason):
    with pytest.raises(core.ValidationError) as caught:
        core.parse_filters(params, core.LIST_PARAMS)
    assert caught.value.reason == reason


def test_bad_cursor_is_rejected(db):
    with pytest.raises(core.ValidationError):
        run_list(db, {"cursor": "not-a-real-cursor"})


def plan(db, sql, args):
    return " | ".join(r["detail"] for r in db.execute("EXPLAIN QUERY PLAN " + sql, args).fetchall())


def assert_indexed(text):
    assert "SCAN i\n" not in text + "\n" and not text.endswith("SCAN i")
    for marker in (
        "SCAN incidents",
        "SCAN rollup_daily",
        "SCAN rollup_signal_daily",
        "SCAN incident_signals",
        "SCAN s",
    ):
        for part in text.split(" | "):
            if part.strip() == marker:
                pytest.fail(f"full scan: {text}")
    assert "USE TEMP B-TREE FOR ORDER BY" not in text


@pytest.mark.parametrize(
    "query",
    [
        {},
        {"method": "tech_support"},
        {"family": "impersonation"},
        {"outcome": "missed"},
        {"source": "live"},
        {"channel": "sms"},
        {"tier": "dangerous"},
        {"from": "2026-11-01", "to": "2026-11-08"},
        {"method": "tech_support", "tier": "safe", "channel": "sms"},
        {"signal": "asks_for_code"},
        {"signal": "asks_for_code", "method": "tech_support"},
        {"q": "bank"},
        {"q": "bank", "method": "tech_support", "signal": "threatens"},
    ],
)
def test_list_queries_use_indexes(db, query):
    store(db, many(5))
    filters = core.parse_filters({k: [v] for k, v in query.items()}, core.LIST_PARAMS)
    sql, args, _ = core.build_list_query(filters, 26)
    text = plan(db, sql, args)
    print(query, "=>", text)
    assert_indexed(text)


def test_stats_queries_use_primary_keys(db):
    store(db, many(5))
    for sql, args in (
        core.group_query(["tier", "family"], "rollup_daily", "2025-11-08", "2026-11-08", None),
        core.group_query(["day", "method"], "rollup_daily", "2025-11-08", "2026-11-08", "sandbox_synthetic"),
        core.group_query(
            ["signal"], "rollup_signal_daily", "2025-11-08", "2026-11-08", None, ("method", "tech_support")
        ),
        core.rollup_estimate_query({"method": "tech_support"}, TODAY),
        core.rollup_estimate_query({"signal": "threatens"}, TODAY),
    ):
        text = plan(db, sql, args)
        print(text)
        assert "USING PRIMARY KEY" in text or "USING INDEX" in text
        assert_indexed(text)


def test_detail_lookups_use_primary_keys(db):
    store(db, many(2))
    for sql, args in (
        (core.SQL_SIGNALS_FOR, (json.dumps(["a"]),)),
        ("SELECT * FROM incidents WHERE incident_id=?", ("a",)),
        ("SELECT * FROM incident_timeline WHERE incident_id=? ORDER BY seq", ("a",)),
        (core.SQL_EXPIRED, ("2026-01-01", 10)),
    ):
        text = plan(db, sql, args)
        print(text)
        assert "PRIMARY KEY" in text or "USING INDEX" in text or "COVERING INDEX" in text


def test_rollup_estimate_matches_stored_count(db):
    store(db, many(7))
    filters = {"method": "bank_fraud_department"}
    sql, args = core.rollup_estimate_query(filters, TODAY)
    assert rows(db, sql, args)[0]["n"] == 7
    assert core.rollup_estimate_query({"q": '"x"'}, TODAY) is None


def test_write_budget_is_atomic_and_refuses_over_limit(db):
    def reserve(amount):
        return db.execute(core.SQL_RESERVE, ("2026-11-08", amount, 100, 500)).fetchall()

    assert len(reserve(60)) == 1
    assert len(reserve(40)) == 1
    assert reserve(1) == []
    assert db.execute("SELECT rows FROM write_budget").fetchone()["rows"] == 100
    db.execute(core.SQL_RECONCILE, ("2026-11-08", -50, 600))
    assert reserve(1) == [], "over the size limit must refuse even with rows left"
    assert db.execute(core.SQL_RESERVE, ("2026-11-09", 101, 100, 500)).fetchall() == []


def test_small_live_groups_are_suppressed_even_when_mixed():
    data = [
        {"tier": "safe", "source": "live", "n": 3},
        {"tier": "safe", "source": "sandbox_synthetic", "n": 100},
        {"tier": "dangerous", "source": "live", "n": 9},
    ]
    merged = {r["tier"]: r["n"] for r in core.suppress(data, ["tier"], None)}
    assert merged == {"safe": "<5", "dangerous": 9}
    only_live = {r["tier"]: r["n"] for r in core.suppress(data[:1], ["tier"], "live")}
    assert only_live == {"safe": "<5"}


def test_synthetic_groups_are_not_suppressed():
    data = [{"tier": "safe", "source": "sandbox_synthetic", "n": 1}]
    assert core.suppress(data, ["tier"], "sandbox_synthetic")[0]["n"] == 1
    assert core.suppress(data, ["tier"], None)[0]["n"] == 1


def test_overview_excludes_suppressed_from_total():
    data = [
        {"tier": "safe", "family": "none", "source_label": "live", "source": "live", "n": 2},
        {"tier": "dangerous", "family": "impersonation", "source_label": "live", "source": "live", "n": 8},
    ]
    body = core.overview_body(data, "live", {"first_day": "a", "last_day": "b"}, "x", "y")
    assert body["total"] == 8 and body["suppressed_groups"] == 1


def test_csv_blocks_formulas_and_has_no_private_columns():
    text = core.to_csv([{"incident_id": "=cmd()", "summary": "+1", "max_risk": 0.5}])
    assert "'=cmd()" in text and "'+1" in text
    header = text.splitlines()[0]
    for private in ("customer", "phone", "transcript", "quote", "name"):
        assert private not in header


def test_retention_deletes_all_traces(db):
    store(
        db,
        [incident(incident_id="c" * 32, source="live", outcome=None, occurred_hour="2024-01-01T00:00:00Z")],
    )
    store(db, [incident(incident_id="d" * 32, occurred_hour="2024-01-01T00:00:00Z")])
    expired = rows(db, core.SQL_EXPIRED, (core.retention_cutoff(TODAY), 10))
    assert [r["incident_id"] for r in expired] == ["c" * 32], "only live incidents expire"
    for sql, param in core.delete_statements(expired):
        db.execute(sql, (param,))
    for table in ("incident_signals", "incident_timeline"):
        assert rows(db, f"SELECT COUNT(*) AS n FROM {table} WHERE incident_id=?", ("c" * 32,))[0]["n"] == 0
    assert rows(db, "SELECT COUNT(*) AS n FROM incidents")[0]["n"] == 1
    assert rows(db, "SELECT COUNT(*) AS n FROM incidents_fts")[0]["n"] == 1
    assert rows(db, "SELECT COUNT(*) AS n FROM incidents_fts WHERE incident_id=?", ("c" * 32,))[0]["n"] == 0


def test_fts_rowids_sort_by_time_and_stay_in_range():
    earlier = core.fts_rowid("a" * 32, "2026-11-07T14:00:00Z")
    later = core.fts_rowid("b" * 32, "2026-11-07T15:00:00Z")
    assert later > earlier and later < 2**62
