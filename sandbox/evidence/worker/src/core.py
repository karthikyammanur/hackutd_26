"""Validation, SQL and response shaping with no Cloudflare dependency, so it tests on plain SQLite."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import math
import re
from datetime import UTC, date, datetime, timedelta

from taxonomy_ids import METHOD_FAMILY

MAX_BATCH = 100
MAX_SIGNALS = 32
MAX_TIMELINE = 64
MAX_BODY_CHARS = 1_000_000
MAX_PAGE = 100
DEFAULT_PAGE = 25
MAX_EXPORT = 5000
BUCKET_S = 15
MAX_BUCKET_S = 86_400
K_ANON = 5
DEFAULT_RANGE_DAYS = 365
RETENTION_DAYS = 365
RETENTION_BATCH = 500

CHANNELS = {"call", "sms"}
SOURCES = {"sandbox_synthetic", "live"}
TIERS = ("safe", "uncertain", "dangerous")
OUTCOMES = {"caught", "soft_miss", "missed", "clear", "soft_false_alarm", "false_alarm"}
MODELS = {
    "safe-signal-guard",
    "jev-latest",
    "jev-preview",
    "nemotron-fast",
    "nemotron-deep",
    "baseline-rules",
    "guardian-pipeline",
}
SIGNALS = {
    # Jev red-flag questions
    "asks_for_code",
    "asks_for_pin_or_password",
    "asks_to_move_money",
    "asks_for_gift_cards",
    "asks_for_crypto_or_wire",
    "asks_remote_access",
    "asks_secrecy",
    "creates_urgency",
    "threatens",
    "claims_authority",
    "emotional_family_emergency",
    "verifies_safely",
    # Events on the phone or network
    "sms_otp",
    "bank_app_open",
    "bank_transfer",
    "account_change",
    "new_domain",
    "blocklisted_domain",
}
FAMILIES = set(METHOD_FAMILY.values())

INCIDENT_FIELDS = {
    "incident_id",
    "occurred_hour",
    "channel",
    "source",
    "method",
    "family",
    "predicted_method",
    "tier",
    "outcome",
    "max_risk",
    "first_alert_bucket_s",
    "duration_bucket_s",
    "money_moved_before_alert",
    "model",
    "caller_cluster",
    "signals",
    "timeline",
}
REQUIRED_FIELDS = {
    "incident_id",
    "occurred_hour",
    "channel",
    "source",
    "method",
    "family",
    "tier",
    "max_risk",
    "model",
}
SIGNAL_FIELDS = {"signal", "strength"}
TIMELINE_FIELDS = {"seq", "t_bucket_s", "tier", "risk"}

HOUR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:00:00Z$")
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HASH_ID_RE = re.compile(r"^[a-f0-9]{32,64}$")
READABLE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
CLUSTER_RE = re.compile(r"^[a-f0-9]{16,64}$")

PII_PATTERNS = (
    ("digit_run", re.compile(r"\d{7,}")),
    ("phone_like", re.compile(r"(?:\d[\s().+\-]{0,2}){7,}")),
    ("email", re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")),
    (
        "url",
        re.compile(
            r"(?:[a-z][a-z0-9+.-]*://|www\.)\S+|\b[\w-]+\.(?:com|net|org|io|co|gov|edu|info|biz|xyz)\b", re.I
        ),
    ),
)


class ValidationError(Exception):
    """Carries only the field name and a fixed reason. Rejected values are never echoed back."""

    def __init__(self, reason: str, field: str = "", index: int | None = None):
        super().__init__(reason)
        self.reason = reason
        self.field = field
        self.index = index

    def body(self) -> dict:
        out = {"error": "invalid request", "reason": self.reason}
        if self.field:
            out["field"] = self.field
        if self.index is not None:
            out["index"] = self.index
        return out


def contains_pii(text: str) -> bool:
    return any(pattern.search(text) for _, pattern in PII_PATTERNS)


def _scan(value, field: str) -> None:
    """Defense in depth: runs on every string before field checks."""
    if isinstance(value, dict):
        for key, item in value.items():
            if contains_pii(str(key)):
                raise ValidationError("contains_pii", field)
            _scan(item, f"{field}.{key}" if field else str(key))
    elif isinstance(value, list):
        for item in value:
            _scan(item, field)
    elif isinstance(value, str):
        leaf = field.rsplit(".", 1)[-1]
        exempt = (leaf == "occurred_hour" and HOUR_RE.match(value)) or (
            leaf in ("incident_id", "caller_cluster") and HASH_ID_RE.match(value)
        )
        if not exempt and leaf != "caller_cluster" and contains_pii(value):
            raise ValidationError("contains_pii", field)


def _check_keys(obj: dict, allowed: set[str], field: str) -> None:
    if not isinstance(obj, dict):
        raise ValidationError("not_an_object", field)
    if set(obj) - allowed:
        raise ValidationError("unknown_field", field)


def _enum(value, allowed, field: str):
    if not isinstance(value, str) or value not in allowed:
        raise ValidationError("not_allowed", field)
    return value


def _fraction(value, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError("not_a_number", field)
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValidationError("out_of_range", field)
    return round(number, 3)


def _bucket(value, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > MAX_BUCKET_S:
        raise ValidationError("out_of_range", field)
    if value % BUCKET_S:
        raise ValidationError("not_bucketed", field)
    return value


def _hour(value) -> str:
    if not isinstance(value, str) or not HOUR_RE.match(value):
        raise ValidationError("not_rounded_to_hour", "occurred_hour")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise ValidationError("not_a_date", "occurred_hour") from error
    return value


def _incident_id(value) -> str:
    if not isinstance(value, str) or not (HASH_ID_RE.match(value) or READABLE_ID_RE.match(value)):
        raise ValidationError("bad_format", "incident_id")
    return value


def _cluster(value):
    if value is None:
        return None
    # A real keyed hash of 16+ hex characters essentially always has a letter; a bare number doesn't.
    if not isinstance(value, str) or not CLUSTER_RE.match(value) or value.isdigit():
        raise ValidationError("bad_format", "caller_cluster")
    return value


def signal_words(signal: str) -> str:
    return signal.replace("_", " ")


def build_summary(incident: dict) -> str:
    """Deterministic and built only from validated indicator fields."""
    parts = [
        f"{incident['tier'].capitalize()} {incident['channel']} incident",
        f"classified as {signal_words(incident['method'])} ({signal_words(incident['family'])})",
        f"peak risk {incident['max_risk']:.2f}",
    ]
    if incident["first_alert_bucket_s"] is not None:
        parts.append(f"first alert near {incident['first_alert_bucket_s']}s")
    if incident["money_moved_before_alert"] == 1:
        parts.append("money moved before the alert")
    top = sorted(incident["signals"], key=lambda s: (-s["strength"], s["signal"]))[:4]
    if top:
        parts.append("top signals: " + ", ".join(signal_words(s["signal"]) for s in top))
    return ". ".join([parts[0] + " " + parts[1], *parts[2:]]) + "."


def validate_incident(raw: dict, field: str = "") -> dict:
    _check_keys(raw, INCIDENT_FIELDS, field)
    missing = REQUIRED_FIELDS - set(raw)
    if missing:
        raise ValidationError("missing_field", sorted(missing)[0])
    _scan(raw, "")

    method = _enum(raw["method"], METHOD_FAMILY, "method")
    family = _enum(raw["family"], FAMILIES, "family")
    if METHOD_FAMILY[method] != family:
        raise ValidationError("family_mismatch", "family")
    predicted = raw.get("predicted_method")
    if predicted is not None:
        _enum(predicted, METHOD_FAMILY, "predicted_method")
    source = _enum(raw["source"], SOURCES, "source")
    outcome = raw.get("outcome")
    if outcome is not None:
        _enum(outcome, OUTCOMES, "outcome")
        if source == "live":
            raise ValidationError("outcome_only_in_testing", "outcome")

    first = raw.get("first_alert_bucket_s")
    duration = raw.get("duration_bucket_s")
    money = raw.get("money_moved_before_alert")
    if isinstance(money, bool):
        money = int(money)
    if money not in (None, 0, 1):
        raise ValidationError("not_allowed", "money_moved_before_alert")

    raw_signals = raw.get("signals", [])
    if not isinstance(raw_signals, list) or len(raw_signals) > MAX_SIGNALS:
        raise ValidationError("too_many", "signals")
    signals, seen = [], set()
    for item in raw_signals:
        _check_keys(item, SIGNAL_FIELDS, "signals")
        if set(item) != SIGNAL_FIELDS:
            raise ValidationError("missing_field", "signals")
        name = _enum(item["signal"], SIGNALS, "signals.signal")
        if name in seen:
            raise ValidationError("duplicate", "signals.signal")
        seen.add(name)
        signals.append({"signal": name, "strength": _fraction(item["strength"], "signals.strength")})

    raw_timeline = raw.get("timeline", [])
    if not isinstance(raw_timeline, list) or len(raw_timeline) > MAX_TIMELINE:
        raise ValidationError("too_many", "timeline")
    timeline, seqs = [], set()
    for item in raw_timeline:
        _check_keys(item, TIMELINE_FIELDS, "timeline")
        if set(item) != TIMELINE_FIELDS:
            raise ValidationError("missing_field", "timeline")
        seq = item["seq"]
        if isinstance(seq, bool) or not isinstance(seq, int) or not 0 <= seq < MAX_TIMELINE or seq in seqs:
            raise ValidationError("not_allowed", "timeline.seq")
        seqs.add(seq)
        timeline.append(
            {
                "seq": seq,
                "t_bucket_s": _bucket(item["t_bucket_s"], "timeline.t_bucket_s"),
                "tier": _enum(item["tier"], TIERS, "timeline.tier"),
                "risk": _fraction(item["risk"], "timeline.risk"),
            }
        )

    incident = {
        "incident_id": _incident_id(raw["incident_id"]),
        "occurred_hour": _hour(raw["occurred_hour"]),
        "channel": _enum(raw["channel"], CHANNELS, "channel"),
        "source": source,
        "method": method,
        "family": family,
        "predicted_method": predicted,
        "tier": _enum(raw["tier"], TIERS, "tier"),
        "outcome": outcome,
        "max_risk": _fraction(raw["max_risk"], "max_risk"),
        "first_alert_bucket_s": None if first is None else _bucket(first, "first_alert_bucket_s"),
        "duration_bucket_s": None if duration is None else _bucket(duration, "duration_bucket_s"),
        "money_moved_before_alert": money,
        "model": _enum(raw["model"], MODELS, "model"),
        "caller_cluster": _cluster(raw.get("caller_cluster")),
        "signals": signals,
        "timeline": timeline,
    }
    incident["summary"] = build_summary(incident)
    return incident


def validate_batch(body) -> list[dict]:
    """All-or-nothing: the first bad incident rejects the whole batch."""
    if not isinstance(body, dict) or set(body) != {"incidents"} or not isinstance(body["incidents"], list):
        raise ValidationError("expected_incidents_list")
    raw = body["incidents"]
    if not raw or len(raw) > MAX_BATCH:
        raise ValidationError("batch_size", "incidents")
    incidents, seen = [], set()
    for index, item in enumerate(raw):
        try:
            incident = validate_incident(item)
        except ValidationError as error:
            error.index = index
            raise
        if incident["incident_id"] in seen:
            raise ValidationError("duplicate", "incident_id", index)
        seen.add(incident["incident_id"])
        incidents.append(incident)
    return incidents


HOUR_EPOCH = datetime(2020, 1, 1, tzinfo=UTC)
HASH_BITS = 42
SAFE_ROWID_BITS = 62


def fts_rowid(incident_id: str, occurred_hour: str) -> int:
    """Newest-first ordering for search, and a value retention can recompute to delete the FTS row."""
    moment = datetime.strptime(occurred_hour, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    hours = max(int((moment - HOUR_EPOCH).total_seconds() // 3600), 0) & (
        (1 << (SAFE_ROWID_BITS - HASH_BITS)) - 1
    )
    digest = int(hashlib.sha256(incident_id.encode()).hexdigest()[:16], 16) & ((1 << HASH_BITS) - 1)
    return (hours << HASH_BITS) | digest


_J = "json_extract(value,'$.{}')"
_NEW = "NOT EXISTS (SELECT 1 FROM incidents i WHERE i.incident_id=json_extract(value,'$.incident_id'))"
_INCIDENT_COLUMNS = [
    "incident_id",
    "occurred_hour",
    "channel",
    "source",
    "method",
    "family",
    "predicted_method",
    "tier",
    "outcome",
    "max_risk",
    "first_alert_bucket_s",
    "duration_bucket_s",
    "money_moved_before_alert",
    "model",
    "caller_cluster",
    "summary",
    "created_at",
]


def _extract(columns: list[str]) -> str:
    return ",".join(_J.format(c) for c in columns)


# Each statement takes one JSON array, because D1 limits both bound parameters and queries per invocation.
# `incidents` runs last in the batch: earlier statements use its absence to skip incidents already stored,
# and the batch is one transaction, so re-sending can't double count.
SQL_ROLLUP_DAILY = f"""
INSERT INTO rollup_daily (day,source,channel,method,family,tier,outcome,n)
SELECT {_extract(["day", "source", "channel", "method", "family", "tier", "rollup_outcome"])},COUNT(*)
FROM json_each(?1) WHERE {_NEW} GROUP BY 1,2,3,4,5,6,7
ON CONFLICT (day,source,channel,method,family,tier,outcome) DO UPDATE SET n=n+excluded.n
"""
SQL_ROLLUP_SIGNAL = f"""
INSERT INTO rollup_signal_daily (day,source,method,signal,n)
SELECT {_extract(["day", "source", "method", "signal"])},COUNT(*)
FROM json_each(?1) WHERE {_NEW} GROUP BY 1,2,3,4
ON CONFLICT (day,source,method,signal) DO UPDATE SET n=n+excluded.n
"""
SQL_INSERT_FTS = f"""
INSERT INTO incidents_fts (rowid,incident_id,method,family,tier,signals,summary)
SELECT {_extract(["fts_rowid", "incident_id", "method", "family", "tier", "signals_text", "summary"])}
FROM json_each(?1) WHERE {_NEW}
"""
SQL_INSERT_SIGNALS = f"""
INSERT OR IGNORE INTO incident_signals (incident_id,signal,strength,occurred_hour)
SELECT {_extract(["incident_id", "signal", "strength", "occurred_hour"])}
FROM json_each(?1) WHERE {_NEW}
"""
SQL_INSERT_TIMELINE = f"""
INSERT OR IGNORE INTO incident_timeline (incident_id,seq,t_bucket_s,tier,risk)
SELECT {_extract(["incident_id", "seq", "t_bucket_s", "tier", "risk"])}
FROM json_each(?1) WHERE {_NEW}
"""
SQL_INSERT_INCIDENTS = f"""
INSERT OR IGNORE INTO incidents ({",".join(_INCIDENT_COLUMNS)})
SELECT {_extract(_INCIDENT_COLUMNS)} FROM json_each(?1)
"""


def insert_statements(incidents: list[dict], created_at: str) -> list[tuple[str, str]]:
    """Ordered (sql, json parameter) pairs for one D1 batch."""
    rollup, signal_rows, fts, timeline, rows = [], [], [], [], []
    for incident in incidents:
        incident_id = incident["incident_id"]
        day = incident["occurred_hour"][:10]
        rollup.append({**incident, "day": day, "rollup_outcome": incident["outcome"] or ""})
        rows.append({**incident, "created_at": created_at})
        fts.append(
            {
                **incident,
                "fts_rowid": fts_rowid(incident_id, incident["occurred_hour"]),
                "signals_text": " ".join(s["signal"] for s in incident["signals"]),
            }
        )
        for signal in incident["signals"]:
            signal_rows.append(
                {
                    "incident_id": incident_id,
                    "day": day,
                    "source": incident["source"],
                    "method": incident["method"],
                    "occurred_hour": incident["occurred_hour"],
                    **signal,
                }
            )
        for point in incident["timeline"]:
            timeline.append({"incident_id": incident_id, **point})
    pairs = [
        (SQL_ROLLUP_DAILY, rollup),
        (SQL_ROLLUP_SIGNAL, signal_rows),
        (SQL_INSERT_FTS, fts),
        (SQL_INSERT_SIGNALS, signal_rows),
        (SQL_INSERT_TIMELINE, timeline),
        (SQL_INSERT_INCIDENTS, rows),
    ]
    return [(sql, json.dumps(data, separators=(",", ":"))) for sql, data in pairs if data]


def estimate_rows(incidents: list[dict]) -> int:
    """Deliberately high reservation. Reconciled to the measured count after the batch."""
    signals = sum(len(i["signals"]) for i in incidents)
    timeline = sum(len(i["timeline"]) for i in incidents)
    return 40 * len(incidents) + 4 * signals + 2 * timeline + 8


SQL_RESERVE = """
INSERT INTO write_budget (day,rows,size_bytes) SELECT ?1,?2,0 WHERE ?2 <= ?3
ON CONFLICT (day) DO UPDATE SET rows=rows+excluded.rows
WHERE write_budget.rows+excluded.rows <= ?3 AND write_budget.size_bytes <= ?4
RETURNING rows
"""
SQL_RECONCILE = "UPDATE write_budget SET rows=MAX(rows+?2,0), size_bytes=MAX(size_bytes,?3) WHERE day=?1"


FILTERS = {
    "method": METHOD_FAMILY,
    "family": FAMILIES,
    "channel": CHANNELS,
    "tier": set(TIERS),
    "outcome": OUTCOMES,
    "source": SOURCES,
}
LIST_PARAMS = {*FILTERS, "q", "signal", "from", "to", "cursor", "limit"}
EXPORT_PARAMS = LIST_PARAMS - {"cursor", "limit"}
SELECT_COLUMNS = ",".join(f"i.{c}" for c in _INCIDENT_COLUMNS if c != "created_at")


def _single(params: dict[str, list[str]], allowed: set[str]) -> dict[str, str]:
    if set(params) - allowed:
        raise ValidationError("unknown_parameter")
    out = {}
    for key, values in params.items():
        if len(values) != 1:
            raise ValidationError("repeated_parameter", key)
        out[key] = values[0]
    return out


def _day(value: str, field: str) -> str:
    if not DAY_RE.match(value):
        raise ValidationError("bad_date", field)
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise ValidationError("bad_date", field) from error
    return value


def fts_query(q: str) -> str:
    """Turns user text into quoted terms so FTS5 query syntax can't be injected."""
    if len(q) > 200:
        raise ValidationError("too_long", "q")
    terms = re.findall(r"[A-Za-z0-9_]+", q)[:8]
    if not terms:
        raise ValidationError("no_search_terms", "q")
    return " ".join(f'"{term}"' for term in terms)


def encode_cursor(values: list[str]) -> str:
    return base64.urlsafe_b64encode(json.dumps(values, separators=(",", ":")).encode()).decode().rstrip("=")


def decode_cursor(cursor: str, size: int) -> list[str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        values = json.loads(base64.urlsafe_b64decode(padded.encode()))
    except (ValueError, TypeError) as error:
        raise ValidationError("bad_cursor", "cursor") from error
    if not isinstance(values, list) or len(values) != size or not all(isinstance(v, str) for v in values):
        raise ValidationError("bad_cursor", "cursor")
    return values


def parse_filters(params: dict[str, list[str]], allowed: set[str]) -> dict:
    query = _single(params, allowed)
    filters = {}
    for key, values in FILTERS.items():
        if key in query:
            filters[key] = _enum(query[key], values, key)
    if "signal" in query:
        filters["signal"] = _enum(query["signal"], SIGNALS, "signal")
    if "from" in query:
        filters["from"] = _day(query["from"], "from")
    if "to" in query:
        filters["to"] = _day(query["to"], "to")
    if "from" in filters and "to" in filters and filters["from"] > filters["to"]:
        raise ValidationError("bad_range", "from")
    if "q" in query:
        filters["q"] = fts_query(query["q"])
    if "limit" in query:
        if not query["limit"].isdigit() or not 1 <= int(query["limit"]) <= MAX_PAGE:
            raise ValidationError("out_of_range", "limit")
        filters["limit"] = int(query["limit"])
    if "cursor" in query:
        filters["cursor"] = query["cursor"]
    return filters


def build_list_query(filters: dict, limit: int) -> tuple[str, list, str]:
    """Returns (sql, params, mode). Modes pick the join and keyset columns that keep the query on an index."""
    where, params = [], []
    for key in FILTERS:
        if key in filters:
            where.append(f"i.{key}=?")
            params.append(filters[key])
    if "from" in filters:
        where.append("i.occurred_hour>=?")
        params.append(filters["from"] + "T00:00:00Z")
    if "to" in filters:
        where.append("i.occurred_hour<=?")
        params.append(filters["to"] + "T23:00:00Z")

    if "q" in filters:
        mode = "fts"
        source = "incidents_fts f JOIN incidents i ON i.incident_id=f.incident_id"
        extra = ["incidents_fts MATCH ?"]
        extra_params = [filters["q"]]
        if "signal" in filters:
            extra.append(
                "EXISTS (SELECT 1 FROM incident_signals s WHERE s.incident_id=i.incident_id AND s.signal=?)"
            )
            extra_params.append(filters["signal"])
        if "cursor" in filters:
            extra.append("f.rowid<CAST(? AS INTEGER)")
            extra_params.append(decode_cursor(filters["cursor"], 1)[0])
        select = f"SELECT {SELECT_COLUMNS},CAST(f.rowid AS TEXT) AS cursor_key FROM {source}"
        order = "ORDER BY f.rowid DESC"
    elif "signal" in filters:
        mode = "signal"
        source = "incident_signals s JOIN incidents i ON i.incident_id=s.incident_id"
        extra = ["s.signal=?"]
        extra_params = [filters["signal"]]
        if "cursor" in filters:
            extra.append("(s.occurred_hour,s.incident_id)<(?,?)")
            extra_params.extend(decode_cursor(filters["cursor"], 2))
        select = f"SELECT {SELECT_COLUMNS} FROM {source}"
        order = "ORDER BY s.occurred_hour DESC,s.incident_id DESC"
    else:
        mode = "time"
        source = "incidents i"
        extra, extra_params = [], []
        if "cursor" in filters:
            extra.append("(i.occurred_hour,i.incident_id)<(?,?)")
            extra_params.extend(decode_cursor(filters["cursor"], 2))
        select = f"SELECT {SELECT_COLUMNS} FROM {source}"
        order = "ORDER BY i.occurred_hour DESC,i.incident_id DESC"

    clauses = extra + where
    sql = f"{select} {'WHERE ' + ' AND '.join(clauses) if clauses else ''} {order} LIMIT ?"
    return sql, extra_params + params + [limit], mode


def next_cursor(rows: list[dict], mode: str, limit: int):
    if len(rows) <= limit:
        return None
    last = rows[limit - 1]
    return encode_cursor(
        [last["cursor_key"]] if mode == "fts" else [last["occurred_hour"], last["incident_id"]]
    )


def clean_item(row: dict) -> dict:
    return {k: v for k, v in row.items() if k != "cursor_key"}


SQL_SIGNALS_FOR = (
    "SELECT incident_id,signal,strength FROM incident_signals "
    "WHERE incident_id IN (SELECT value FROM json_each(?1)) ORDER BY incident_id,strength DESC,signal"
)


def stats_range(params: dict[str, str], today: date) -> tuple[str, str]:
    to_day = _day(params["to"], "to") if "to" in params else today.isoformat()
    from_day = (
        _day(params["from"], "from")
        if "from" in params
        else (date.fromisoformat(to_day) - timedelta(days=DEFAULT_RANGE_DAYS)).isoformat()
    )
    if from_day > to_day:
        raise ValidationError("bad_range", "from")
    return from_day, to_day


def rollup_estimate_query(filters: dict, today: date) -> tuple[str, list] | None:
    """Exact count from rollups when the filters allow it. Free-text search can't be counted this way."""
    if "q" in filters:
        return None
    from_day, to_day = stats_range({k: filters[k] for k in ("from", "to") if k in filters}, today)
    if "signal" in filters:
        if any(k in filters for k in ("family", "channel", "tier", "outcome")):
            return None
        sql = "SELECT COALESCE(SUM(n),0) AS n FROM rollup_signal_daily WHERE day>=? AND day<=? AND signal=?"
        params = [from_day, to_day, filters["signal"]]
        for key in ("source", "method"):
            if key in filters:
                sql += f" AND {key}=?"
                params.append(filters[key])
        return sql, params
    sql = "SELECT COALESCE(SUM(n),0) AS n FROM rollup_daily WHERE day>=? AND day<=?"
    params = [from_day, to_day]
    for key in FILTERS:
        if key in filters:
            sql += f" AND {key}=?"
            params.append(filters[key])
    return sql, params


def _source_clause(source: str | None) -> tuple[str, list]:
    return (" AND source=?", [source]) if source else ("", [])


def group_query(keys: list[str], table: str, from_day: str, to_day: str, source: str | None, extra=None):
    clause, params = _source_clause(source)
    columns = ",".join(keys)
    sql = f"SELECT {columns},source,SUM(n) AS n FROM {table} WHERE day>=? AND day<=?{clause}"
    params = [from_day, to_day, *params]
    if extra:
        sql += f" AND {extra[0]}=?"
        params.append(extra[1])
    return f"{sql} GROUP BY {columns},source", params


def suppress(rows: list[dict], keys: list[str], source: str | None) -> list[dict]:
    """Merges sources per key. Any live part under K_ANON shows the whole cell as '<5'.

    Synthetic-only requests are exempt. Hiding the whole cell, rather than only the live part, stops a mixed
    query being subtracted from a synthetic-only one to recover a small live count.
    """
    groups: dict[tuple, dict] = {}
    for row in rows:
        key = tuple(row[k] for k in keys)
        group = groups.setdefault(key, {"n": 0, "suppressed": False, "values": {k: row[k] for k in keys}})
        group["n"] += row["n"]
        if source != "sandbox_synthetic" and row["source"] == "live" and row["n"] < K_ANON:
            group["suppressed"] = True
    return [{**g["values"], "n": "<5" if g["suppressed"] else g["n"]} for g in groups.values()]


def count_of(value) -> int:
    return value if isinstance(value, int) else 0


def group_rows(rows: list[dict], key: str, source: str | None) -> list[dict]:
    merged = suppress(rows, [key], source)
    return sorted(
        ({"key": r[key] if r[key] != "" else "none", "n": r["n"]} for r in merged),
        key=lambda r: (-count_of(r["n"]), str(r["key"])),
    )


def overview_body(rows: list[dict], source: str | None, bounds: dict, from_day: str, to_day: str) -> dict:
    rows = [{**row, "source_label": row["source"]} for row in rows]
    tier = group_rows(rows, "tier", source)
    return {
        "total": sum(count_of(r["n"]) for r in tier),
        "suppressed_groups": sum(r["n"] == "<5" for r in tier),
        "by_tier": tier,
        "by_family": group_rows(rows, "family", source),
        "by_source": group_rows(rows, "source_label", source),
        "window": {"from": from_day, "to": to_day},
        "date_range": {"from": bounds.get("first_day"), "to": bounds.get("last_day")},
    }


def timeseries_body(rows: list[dict], by: str, source: str | None, from_day: str, to_day: str) -> dict:
    series: dict[str, list] = {}
    for row in suppress(rows, ["day", by], source):
        series.setdefault(row[by], []).append({"day": row["day"], "n": row["n"]})
    return {
        "bucket": "day",
        "by": by,
        "window": {"from": from_day, "to": to_day},
        "series": [
            {"key": key, "points": sorted(points, key=lambda p: p["day"])}
            for key, points in sorted(series.items())
        ],
    }


def methods_body(rows: list[dict], source: str | None) -> dict:
    methods: dict[str, dict] = {}
    for row in suppress(rows, ["method", "family", "tier"], source):
        item = methods.setdefault(
            row["method"],
            {"method": row["method"], "family": row["family"], "n": 0, "tiers": {t: 0 for t in TIERS}},
        )
        item["tiers"][row["tier"]] = row["n"]
        item["n"] += count_of(row["n"])
    return {"methods": sorted(methods.values(), key=lambda m: (-m["n"], m["method"]))}


def signals_body(rows: list[dict], source: str | None) -> dict:
    merged = suppress(rows, ["signal"], source)
    return {"signals": sorted(merged, key=lambda r: (-count_of(r["n"]), r["signal"]))}


CSV_COLUMNS = [c for c in _INCIDENT_COLUMNS if c != "created_at"]


def csv_safe(value):
    """Stops a spreadsheet running a cell as a formula."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return "" if value is None else value


def to_csv(rows: list[dict]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        writer.writerow([csv_safe(row.get(column)) for column in CSV_COLUMNS])
    return out.getvalue()


SQL_EXPIRED = (
    "SELECT incident_id,occurred_hour FROM incidents WHERE source='live' AND occurred_hour<? "
    "ORDER BY occurred_hour LIMIT ?"
)


def retention_cutoff(today: date) -> str:
    return (today - timedelta(days=RETENTION_DAYS)).isoformat() + "T00:00:00Z"


def delete_statements(rows: list[dict]) -> list[tuple[str, str]]:
    """FTS rows go by recomputed rowid: deleting by incident_id would scan the whole FTS table."""
    ids = json.dumps([r["incident_id"] for r in rows])
    rowids = json.dumps([fts_rowid(r["incident_id"], r["occurred_hour"]) for r in rows])
    return [
        (
            "DELETE FROM incidents_fts WHERE rowid IN (SELECT CAST(value AS INTEGER) FROM json_each(?1))",
            rowids,
        ),
        ("DELETE FROM incident_signals WHERE incident_id IN (SELECT value FROM json_each(?1))", ids),
        ("DELETE FROM incident_timeline WHERE incident_id IN (SELECT value FROM json_each(?1))", ids),
        ("DELETE FROM incidents WHERE incident_id IN (SELECT value FROM json_each(?1))", ids),
    ]
