"""Anonymous incident indicators in one SQLite file on this machine. See sandbox/evidence/CONTRACT.md.

Validation, privacy checks and SQL are shared with the original store (sandbox/evidence/worker/src/core.py).
Finished runs are logged here automatically. Only ids, labels, tiers, scores and flag names are read from them.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import parse_qs

import backfill
import core

log = logging.getLogger("evidence")

SCHEMA_NAME = "0001_init.sql"
SCHEMA_PATHS = (
    Path(__file__).with_name(SCHEMA_NAME),
    Path(__file__).parent.parent / "evidence" / "worker" / "migrations" / SCHEMA_NAME,
)
INGEST_TABLE = (
    "CREATE TABLE IF NOT EXISTS ingested_runs (run_id TEXT PRIMARY KEY, ingested_at TEXT NOT NULL,"
    " model TEXT, incidents_new INTEGER NOT NULL, skipped INTEGER NOT NULL)"
)
# One verdict per run, so a run that compares several models doesn't log the same call several times.
MODEL_PRIORITY = ("safe-signal-guard", "jev-latest", "jev-preview", "nemotron-deep", "nemotron-fast", "baseline-rules")
# With this fixed namespace, a test case seen in many runs is still one incident.
SANDBOX_NAMESPACE = "sandbox"
PAGE = 1000
WRITE_CHUNK = 500

JSON_TYPE = {"content-type": "application/json"}
Reply = tuple[int, str, dict[str, str]]


def dict_row(cursor: sqlite3.Cursor, row: tuple) -> dict:
    return {column[0]: row[index] for index, column in enumerate(cursor.description)}


def open_db(path: str, readonly: bool = False) -> sqlite3.Connection:
    uri = f"file:{path}?mode=ro" if readonly else f"file:{path}"
    connection = sqlite3.connect(uri, uri=True, check_same_thread=False, isolation_level=None, timeout=30)
    connection.row_factory = dict_row
    if not readonly:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
    return connection


def reply(body: object, status: int = 200) -> Reply:
    return status, json.dumps(body), JSON_TYPE


def pick_model(models: list[str]) -> str | None:
    return next((model for model in MODEL_PRIORITY if model in models), None)


def to_stored_incident(item: dict, anchor: datetime) -> dict | None:
    """Maps one per-case result to a validated incident. Returns None when it isn't an incident."""
    incident = backfill.to_incident(item, SANDBOX_NAMESPACE, anchor)
    if incident is None:
        return None
    # The model is left out of the id so that one test case stays one incident across model comparisons.
    incident["incident_id"] = backfill.incident_id_for(SANDBOX_NAMESPACE, item["case_id"], "any-model")
    incident["occurred_hour"] = backfill.occurred_hour_for(incident["incident_id"], anchor)
    backfill.assert_safe(incident)
    return core.validate_incident(incident)


class EvidenceStore:
    def __init__(self, path: str):
        self.path = path
        self.write_lock = threading.Lock()
        self.writer = open_db(path)
        self.ensure_schema()
        self.reader = open_db(path, readonly=True)

    def ensure_schema(self) -> None:
        exists = self.writer.execute("SELECT 1 FROM sqlite_master WHERE name='incidents'").fetchone()
        if not exists:
            schema = next(path for path in SCHEMA_PATHS if path.exists()).read_text()
            self.writer.executescript(f"BEGIN;{schema};COMMIT;")
        self.writer.execute(INGEST_TABLE)

    def all(self, sql: str, *args) -> list[dict]:
        return self.reader.execute(sql, args).fetchall()

    # Writing ---------------------------------------------------------------------------------------------------

    def write(self, incidents: list[dict]) -> int:
        """Stores a batch in one transaction and returns how many incidents were new."""
        if not incidents:
            return 0
        created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:00:00Z")
        statements = core.insert_statements(incidents, created_at)
        with self.write_lock:
            self.writer.execute("BEGIN IMMEDIATE")
            try:
                # The incidents insert is last, and earlier statements use its absence to skip repeats.
                new = 0
                for sql, parameter in statements:
                    new = self.writer.execute(sql, (parameter,)).rowcount
                self.writer.execute("COMMIT")
            except Exception:
                self.writer.execute("ROLLBACK")
                raise
        return new

    def expire(self, today: date) -> int:
        """Removes live incidents past the retention period. Synthetic data and rollups stay."""
        rows = self.all(core.SQL_EXPIRED, core.retention_cutoff(today), core.RETENTION_BATCH)
        if not rows:
            return 0
        with self.write_lock:
            self.writer.execute("BEGIN IMMEDIATE")
            try:
                for sql, parameter in core.delete_statements(rows):
                    self.writer.execute(sql, (parameter,))
                self.writer.execute("COMMIT")
            except Exception:
                self.writer.execute("ROLLBACK")
                raise
        return len(rows)

    def ingest_run(self, state: sqlite3.Connection, run: dict) -> dict:
        models = json.loads(run["config"]).get("models") or []
        model = pick_model(models)
        anchor = datetime.fromisoformat(run["created_at"]).replace(minute=0, second=0, microsecond=0)
        new = skipped = 0
        after = ""
        batch: list[dict] = []
        while model:
            rows = state.execute(
                "SELECT case_id, model, method, channel, weak, predicted_method, row FROM results"
                " WHERE run_id=? AND model=? AND case_id>? ORDER BY case_id LIMIT ?",
                (run["id"], model, after, PAGE),
            ).fetchall()
            if not rows:
                break
            after = rows[-1]["case_id"]
            for row in rows:
                try:
                    incident = to_stored_incident(
                        {**row, "weak": bool(row["weak"]), "row": json.loads(row["row"])}, anchor
                    )
                except (core.ValidationError, backfill.PrivacyError, ValueError, KeyError, TypeError) as error:
                    log.warning("incident skipped: %s", getattr(error, "reason", type(error).__name__))
                    skipped += 1
                    continue
                if incident is not None:
                    batch.append(incident)
                if len(batch) >= WRITE_CHUNK:
                    new += self.write(batch)
                    batch = []
        new += self.write(batch)
        with self.write_lock:
            self.writer.execute(
                "INSERT OR REPLACE INTO ingested_runs (run_id, ingested_at, model, incidents_new, skipped) VALUES (?,?,?,?,?)",
                (run["id"], datetime.now(UTC).isoformat(), model, new, skipped),
            )
        return {"run_id": run["id"], "model": model, "incidents_new": new, "skipped": skipped}

    def ingest_pending(self, state_path: str) -> list[dict]:
        """Logs every finished run not logged yet. Safe to repeat and safe after a restart."""
        state = open_db(state_path, readonly=True)
        try:
            done_already = {row["run_id"] for row in self.all("SELECT run_id FROM ingested_runs")}
            runs = state.execute(
                "SELECT id, created_at, config FROM runs WHERE status='done' ORDER BY created_at"
            ).fetchall()
            reports = [self.ingest_run(state, run) for run in runs if run["id"] not in done_already]
        finally:
            state.close()
        expired = self.expire(datetime.now(UTC).date())
        if expired:
            log.info("retention removed %d incidents", expired)
        return reports

    # API, same routes and bodies as CONTRACT.md -------------------------------------------------------------------

    def respond(self, method: str, path: str, query: str, body: bytes = b"") -> Reply:
        params = parse_qs(query, keep_blank_values=True)
        try:
            if path == "/incidents" and method == "POST":
                return self.post_incidents(body)
            if method != "GET":
                return reply({"error": "Not found"}, 404)
            if path == "/incidents":
                return self.list_incidents(params)
            match = re.fullmatch(r"/incidents/([^/]+)", path)
            if match:
                return self.packet(match.group(1))
            if path == "/export.csv":
                return self.export(params)
            if path.startswith("/stats/"):
                result = self.stats(path, params)
                return reply(result) if result is not None else reply({"error": "Not found"}, 404)
            return reply({"error": "Not found"}, 404)
        except core.ValidationError as error:
            return reply(error.body(), 400)

    def post_incidents(self, body: bytes) -> Reply:
        if len(body) > core.MAX_BODY_CHARS:
            return reply({"error": "invalid request", "reason": "body_too_large"}, 413)
        try:
            parsed = json.loads(body)
        except ValueError:
            return reply({"error": "invalid request", "reason": "not_json"}, 400)
        incidents = core.validate_batch(parsed)
        return reply({"received": len(incidents), "new": self.write(incidents)})

    def attach_signals(self, items: list[dict]) -> None:
        if not items:
            return
        ids = json.dumps([item["incident_id"] for item in items])
        by_id: dict[str, list] = {}
        for row in self.all(core.SQL_SIGNALS_FOR, ids):
            by_id.setdefault(row["incident_id"], []).append({"signal": row["signal"], "strength": row["strength"]})
        for item in items:
            item["signals"] = by_id.get(item["incident_id"], [])

    def list_incidents(self, params: dict) -> Reply:
        filters = core.parse_filters(params, core.LIST_PARAMS)
        limit = filters.get("limit", core.DEFAULT_PAGE)
        sql, args, mode = core.build_list_query(filters, limit + 1)
        rows = self.all(sql, *args)
        cursor = core.next_cursor(rows, mode, limit)
        items = [core.clean_item(row) for row in rows[:limit]]
        self.attach_signals(items)
        estimate = None
        count = core.rollup_estimate_query(filters, datetime.now(UTC).date())
        if count:
            estimate = self.all(count[0], *count[1])[0]["n"]
        return reply({"items": items, "next_cursor": cursor, "total_estimate": estimate})

    def packet(self, incident_id: str) -> Reply:
        if not (core.HASH_ID_RE.match(incident_id) or core.READABLE_ID_RE.match(incident_id)):
            return reply({"error": "Not found"}, 404)
        columns = core.SELECT_COLUMNS.replace("i.", "")
        rows = self.all(f"SELECT {columns} FROM incidents WHERE incident_id=?", incident_id)
        if not rows:
            return reply({"error": "Not found"}, 404)
        found = rows[0]
        self.attach_signals([found])
        found["timeline"] = self.all(
            "SELECT seq,t_bucket_s,tier,risk FROM incident_timeline WHERE incident_id=? ORDER BY seq", incident_id
        )
        return reply(found)

    def export(self, params: dict) -> Reply:
        filters = core.parse_filters(params, core.EXPORT_PARAMS)
        sql, args, _ = core.build_list_query(filters, core.MAX_EXPORT)
        return (
            200,
            core.to_csv(self.all(sql, *args)),
            {"content-type": "text/csv", "content-disposition": 'attachment; filename="safe-signal-incidents.csv"'},
        )

    @staticmethod
    def stats_params(params: dict, allowed: set[str]) -> tuple[dict, str | None]:
        query = core._single(params, allowed)
        source = query.get("source")
        if source is not None:
            core._enum(source, core.SOURCES, "source")
        return query, source

    def stats(self, path: str, params: dict) -> dict | None:
        today = datetime.now(UTC).date()
        if path == "/stats/overview":
            query, source = self.stats_params(params, {"from", "to", "source"})
            from_day, to_day = core.stats_range(query, today)
            sql, args = core.group_query(["tier", "family"], "rollup_daily", from_day, to_day, source)
            bounds = self.all(
                "SELECT (SELECT day FROM rollup_daily ORDER BY day LIMIT 1) AS first_day,"
                "(SELECT day FROM rollup_daily ORDER BY day DESC LIMIT 1) AS last_day"
            )
            return core.overview_body(self.all(sql, *args), source, bounds[0], from_day, to_day)
        if path == "/stats/timeseries":
            query, source = self.stats_params(params, {"bucket", "by", "from", "to", "source"})
            if query.get("bucket", "day") != "day":
                raise core.ValidationError("not_allowed", "bucket")
            by = core._enum(query.get("by", "family"), {"method", "family", "tier"}, "by")
            from_day, to_day = core.stats_range(query, today)
            sql, args = core.group_query(["day", by], "rollup_daily", from_day, to_day, source)
            return core.timeseries_body(self.all(sql, *args), by, source, from_day, to_day)
        if path == "/stats/signals":
            query, source = self.stats_params(params, {"from", "to", "source", "method"})
            from_day, to_day = core.stats_range(query, today)
            extra = ("method", core._enum(query["method"], core.METHOD_FAMILY, "method")) if "method" in query else None
            sql, args = core.group_query(["signal"], "rollup_signal_daily", from_day, to_day, source, extra)
            return core.signals_body(self.all(sql, *args), source)
        if path == "/stats/methods":
            query, source = self.stats_params(params, {"from", "to", "source"})
            from_day, to_day = core.stats_range(query, today)
            sql, args = core.group_query(["method", "family", "tier"], "rollup_daily", from_day, to_day, source)
            return core.methods_body(self.all(sql, *args), source)
        return None
