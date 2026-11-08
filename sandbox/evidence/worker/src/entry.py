"""Safe Signal evidence store: anonymous incident indicators on D1. See sandbox/evidence/CONTRACT.md."""

import hashlib
import hmac
import json
import re
import time
from datetime import UTC, date, datetime
from urllib.parse import parse_qs, urlparse

import core
import js
from pyodide.ffi import to_js
from workers import Response, WorkerEntrypoint

STATS_TTL_S = 60
_stats_cache: dict[str, tuple[float, str]] = {}


def json_response(body, status: int = 200, headers: dict | None = None) -> Response:
    return Response(
        json.dumps(body), status=status, headers={"content-type": "application/json", **(headers or {})}
    )


def today_utc() -> date:
    return datetime.now(UTC).date()


async def d1_all(db, sql: str, *args) -> list[dict]:
    statement = db.prepare(sql)
    if args:
        statement = statement.bind(*args)
    result = await statement.all()
    # Through JSON because null must arrive as None; a direct to_py conversion can keep JS null objects.
    return json.loads(js.JSON.stringify(result.results))


async def d1_batch(db, pairs: list[tuple[str, str]]) -> list[dict]:
    statements = [db.prepare(sql).bind(param) for sql, param in pairs]
    results = await db.batch(to_js(statements))
    return json.loads(js.JSON.stringify(results))


def int_var(env, name: str) -> int:
    return int(str(getattr(env, name)))


async def reserve(env, rows: int) -> bool:
    found = await d1_all(
        env.DB,
        core.SQL_RESERVE,
        today_utc().isoformat(),
        rows,
        int_var(env, "DAILY_WRITE_LIMIT"),
        int_var(env, "MAX_DB_BYTES"),
    )
    return bool(found)


async def reconcile(env, delta: int, size_bytes: int) -> None:
    await env.DB.prepare(core.SQL_RECONCILE).bind(today_utc().isoformat(), delta, size_bytes).run()


async def write_batch(env, pairs: list[tuple[str, str]], reserved: int) -> dict:
    """Runs under a reservation, then swaps the estimate for what D1 reports it wrote."""
    try:
        results = await d1_batch(env.DB, pairs)
    except Exception:
        await reconcile(env, -reserved, 0)
        raise
    written = sum(int(r["meta"].get("rows_written", 0)) for r in results)
    size = max(int(r["meta"].get("size_after", 0) or 0) for r in results)
    # The reserve and reconcile statements each also write one row.
    await reconcile(env, written + 2 - reserved, size)
    return {"rows_written": written, "size_after": size}


async def post_incidents(env, request) -> Response:
    text = await request.text()
    if len(text) > core.MAX_BODY_CHARS:
        return json_response({"error": "invalid request", "reason": "body_too_large"}, 413)
    try:
        body = json.loads(text)
    except ValueError:
        return json_response({"error": "invalid request", "reason": "not_json"}, 400)
    incidents = core.validate_batch(body)
    reservation = core.estimate_rows(incidents)
    if not await reserve(env, reservation):
        return json_response({"error": "daily free-tier write budget reached", "reason": "write_budget"}, 429)
    pairs = core.insert_statements(incidents, datetime.now(UTC).strftime("%Y-%m-%dT%H:00:00Z"))
    measured = await write_batch(env, pairs, reservation)
    return json_response({"received": len(incidents), **measured})


async def attach_signals(env, items: list[dict]) -> None:
    if not items:
        return
    rows = await d1_all(env.DB, core.SQL_SIGNALS_FOR, json.dumps([i["incident_id"] for i in items]))
    by_id: dict[str, list] = {}
    for row in rows:
        by_id.setdefault(row["incident_id"], []).append(
            {"signal": row["signal"], "strength": row["strength"]}
        )
    for item in items:
        item["signals"] = by_id.get(item["incident_id"], [])


async def get_incidents(env, params) -> Response:
    filters = core.parse_filters(params, core.LIST_PARAMS)
    limit = filters.get("limit", core.DEFAULT_PAGE)
    sql, args, mode = core.build_list_query(filters, limit + 1)
    rows = await d1_all(env.DB, sql, *args)
    cursor = core.next_cursor(rows, mode, limit)
    items = [core.clean_item(row) for row in rows[:limit]]
    await attach_signals(env, items)
    estimate = None
    query = core.rollup_estimate_query(filters, today_utc())
    if query:
        counted = await d1_all(env.DB, query[0], *query[1])
        estimate = counted[0]["n"]
    return json_response({"items": items, "next_cursor": cursor, "total_estimate": estimate})


async def get_incident(env, incident_id: str) -> Response:
    if not (core.HASH_ID_RE.match(incident_id) or core.READABLE_ID_RE.match(incident_id)):
        return json_response({"error": "Not found"}, 404)
    columns = core.SELECT_COLUMNS.replace("i.", "")
    rows = await d1_all(env.DB, f"SELECT {columns} FROM incidents WHERE incident_id=?", incident_id)
    if not rows:
        return json_response({"error": "Not found"}, 404)
    packet = rows[0]
    await attach_signals(env, [packet])
    packet["timeline"] = await d1_all(
        env.DB,
        "SELECT seq,t_bucket_s,tier,risk FROM incident_timeline WHERE incident_id=? ORDER BY seq",
        incident_id,
    )
    return json_response(packet)


async def get_export(env, params) -> Response:
    filters = core.parse_filters(params, core.EXPORT_PARAMS)
    sql, args, _ = core.build_list_query(filters, core.MAX_EXPORT)
    rows = await d1_all(env.DB, sql, *args)
    return Response(
        core.to_csv(rows),
        headers={
            "content-type": "text/csv",
            "content-disposition": 'attachment; filename="safe-signal-incidents.csv"',
        },
    )


def stats_params(params, allowed: set[str]) -> tuple[dict, str | None]:
    query = core._single(params, allowed)
    source = query.get("source")
    if source is not None:
        core._enum(source, core.SOURCES, "source")
    return query, source


async def build_stats(env, path: str, params) -> dict | None:
    today = today_utc()
    if path == "/stats/overview":
        query, source = stats_params(params, {"from", "to", "source"})
        from_day, to_day = core.stats_range(query, today)
        sql, args = core.group_query(["tier", "family"], "rollup_daily", from_day, to_day, source)
        rows = await d1_all(env.DB, sql, *args)
        bounds = await d1_all(
            env.DB,
            "SELECT (SELECT day FROM rollup_daily ORDER BY day LIMIT 1) AS first_day,"
            "(SELECT day FROM rollup_daily ORDER BY day DESC LIMIT 1) AS last_day",
        )
        return core.overview_body(rows, source, bounds[0], from_day, to_day)
    if path == "/stats/timeseries":
        query, source = stats_params(params, {"bucket", "by", "from", "to", "source"})
        if query.get("bucket", "day") != "day":
            raise core.ValidationError("not_allowed", "bucket")
        by = core._enum(query.get("by", "family"), {"method", "family", "tier"}, "by")
        from_day, to_day = core.stats_range(query, today)
        sql, args = core.group_query(["day", by], "rollup_daily", from_day, to_day, source)
        return core.timeseries_body(await d1_all(env.DB, sql, *args), by, source, from_day, to_day)
    if path == "/stats/signals":
        query, source = stats_params(params, {"from", "to", "source", "method"})
        from_day, to_day = core.stats_range(query, today)
        extra = None
        if "method" in query:
            extra = ("method", core._enum(query["method"], core.METHOD_FAMILY, "method"))
        sql, args = core.group_query(["signal"], "rollup_signal_daily", from_day, to_day, source, extra)
        return core.signals_body(await d1_all(env.DB, sql, *args), source)
    if path == "/stats/methods":
        query, source = stats_params(params, {"from", "to", "source"})
        from_day, to_day = core.stats_range(query, today)
        sql, args = core.group_query(["method", "family", "tier"], "rollup_daily", from_day, to_day, source)
        return core.methods_body(await d1_all(env.DB, sql, *args), source)
    return None


async def cached_stats(env, path: str, raw_query: str, params) -> Response:
    key = f"https://evidence-cache.invalid{path}?{raw_query}"
    now = time.monotonic()
    hit = _stats_cache.get(key)
    if hit and now - hit[0] < STATS_TTL_S:
        return Response(hit[1], headers={"content-type": "application/json", "x-evidence-cache": "isolate"})
    try:
        match = await js.caches.default.match(key)
        if match is not None and getattr(match, "ok", False):
            text = await match.text()
            _stats_cache[key] = (now, text)
            return Response(text, headers={"content-type": "application/json", "x-evidence-cache": "edge"})
    except Exception as error:
        print(f"cache read failed: {type(error).__name__}")

    body = await build_stats(env, path, params)
    if body is None:
        return json_response({"error": "Not found"}, 404)
    text = json.dumps(body)
    _stats_cache[key] = (now, text)
    try:
        headers = to_js(
            {"headers": {"content-type": "application/json", "cache-control": f"max-age={STATS_TTL_S}"}},
            dict_converter=js.Object.fromEntries,
        )
        await js.caches.default.put(key, js.Response.new(text, headers))
    except Exception as error:
        print(f"cache write failed: {type(error).__name__}")
    return Response(text, headers={"content-type": "application/json", "x-evidence-cache": "miss"})


async def run_retention(env) -> None:
    rows = await d1_all(env.DB, core.SQL_EXPIRED, core.retention_cutoff(today_utc()), core.RETENTION_BATCH)
    if not rows:
        return
    reservation = 30 * len(rows) + 8
    if not await reserve(env, reservation):
        print("retention skipped: write budget")
        return
    measured = await write_batch(env, core.delete_statements(rows), reservation)
    print(f"retention removed {len(rows)} incidents, wrote {measured['rows_written']} rows")


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        header = str(request.headers.get("authorization") or "")
        given = header.removeprefix("Bearer ")
        digest = hashlib.sha256(given.encode()).hexdigest()
        if not given or not hmac.compare_digest(digest, str(self.env.ADMIN_PASSWORD_HASH)):
            return json_response({"error": "Unauthorized"}, 401)
        url = urlparse(str(request.url))
        path = url.path.rstrip("/")
        method = str(request.method)
        params = parse_qs(url.query, keep_blank_values=True)
        try:
            if path == "/incidents" and method == "POST":
                return await post_incidents(self.env, request)
            if method != "GET":
                return json_response({"error": "Not found"}, 404)
            if path == "/incidents":
                return await get_incidents(self.env, params)
            match = re.fullmatch(r"/incidents/([^/]+)", path)
            if match:
                return await get_incident(self.env, match.group(1))
            if path == "/export.csv":
                return await get_export(self.env, params)
            if path.startswith("/stats/"):
                return await cached_stats(self.env, path, url.query, params)
            return json_response({"error": "Not found"}, 404)
        except core.ValidationError as error:
            return json_response(error.body(), 400)
        except Exception as error:
            print(f"request failed: {type(error).__name__}")
            return json_response({"error": "Internal error"}, 500)

    async def scheduled(self, controller, env, ctx):
        await run_retention(env)
