"""Safe Signal sandbox backend for a single Brev GPU machine.

The same API as the Cloudflare Worker in sandbox/worker (see sandbox/CONTRACT.md), with asyncio tasks in place of
Durable Objects and local SQLite in place of D1. Nemotron is only ever reached on localhost.

Stored: scores, flags, ids, markers. Transcript text and agent notes stay in memory (R8).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import logging
import os
import random
import re
import sqlite3
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs

import httpx
from evidence import EvidenceStore
from classify import (
    ALL_MODELS,
    BASELINE,
    BREV_MODELS,
    DIRECT_SYSTEM,
    HARD_FLAGS,
    GUARD_MODEL,
    JEV_MODELS,
    RESCORE_TIER_SQL,
    absorb_report,
    baseline_classify,
    case_session,
    corpus_filter,
    count_row,
    hist_add,
    jev_questions,
    live_view,
    new_live,
    parse_direct,
    parse_guard,
    parse_jev_matrix,
    rescore_params,
    rescored_rows,
    safe_json,
    step_add,
    validate_run,
)
from pipeline import (
    AGENT_SYSTEM,
    CHECK_SYSTEM,
    FAILURES,
    build_frames,
    check_case_text,
    compose_state,
    make_marker,
    markers_csv,
    parse_check,
    parse_note,
    score_call,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from taxonomy import METHODS

log = logging.getLogger("sandbox")

JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MODELS_URL = "https://api.typesafe.ai/v1/models"
QUESTIONS = jev_questions()
CHECK_MAX = 5000
RATE_STREAK_PAUSE = 12
STALL_SECONDS = 180
HEALTH_TTL_S = 15
DEFAULT_DANGEROUS, DEFAULT_UNCERTAIN = 0.5, 0.2
ACTIVE = ("running", "checking")
JEV_FATAL = {401: "invalid API key", 402: "out of credits", 403: "access denied"}

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created_at TEXT, started_ms INTEGER, finished_ms INTEGER DEFAULT 0,"
    " config TEXT, total INTEGER, lanes INTEGER, claimed INTEGER DEFAULT 0, check_total INTEGER DEFAULT 0,"
    " check_done INTEGER DEFAULT 0, last_report_ms INTEGER DEFAULT 0, status TEXT, error TEXT DEFAULT '', live TEXT DEFAULT '')",
    "CREATE TABLE IF NOT EXISTS run_cases (run_id TEXT, seq INTEGER, case_id TEXT, PRIMARY KEY (run_id, seq))",
    "CREATE TABLE IF NOT EXISTS results (run_id TEXT, case_id TEXT, model TEXT, method TEXT, family TEXT, channel TEXT, source TEXT,"
    " scam INTEGER, weak INTEGER, answered INTEGER, tier TEXT, outcome TEXT, predicted_method TEXT, p_d REAL, p_ud REAL,"
    " hard_flag REAL, ms INTEGER, row TEXT, PRIMARY KEY (run_id, case_id, model))",
    "CREATE INDEX IF NOT EXISTS idx_results_case ON results (run_id, case_id)",
    "CREATE TABLE IF NOT EXISTS check_queue (run_id TEXT, seq INTEGER, case_id TEXT, model TEXT, PRIMARY KEY (run_id, seq))",
    "CREATE TABLE IF NOT EXISTS markers (run_id TEXT, seq INTEGER, data TEXT, PRIMARY KEY (run_id, seq))",
    "CREATE TABLE IF NOT EXISTS failure_log (run_id TEXT, ts TEXT, model TEXT, method TEXT, n INTEGER, error_rate REAL)",
    "CREATE TABLE IF NOT EXISTS public_budget (day TEXT PRIMARY KEY, runs INTEGER DEFAULT 0, cases INTEGER DEFAULT 0)",
)
# Runs started through the public site that use Jev, the only model billed per call, per UTC day.
# Direct API use with the password is not limited here.
PUBLIC_DAILY_RUNS = 20
PUBLIC_DAILY_CASES = 20000
EXPORT_ROW_KEYS = (
    "outcome",
    "tier",
    "max_p_dangerous",
    "first_dangerous_t",
    "money_moment_t",
    "caught_before_money",
    "frames",
    "frames_answered",
    "peak_flags",
)


class HttpError(RuntimeError):
    def __init__(self, status: int, retry_after: float | None = None):
        super().__init__(f"HTTP {status}")
        self.status = status
        self.retry_after = retry_after


def now_ms() -> int:
    return int(time.time() * 1000)


def as_dict_factory(cursor: sqlite3.Cursor, row: tuple) -> dict:
    return {column[0]: row[index] for index, column in enumerate(cursor.description)}


def connect(path: str, readonly: bool = False) -> sqlite3.Connection:
    uri = f"file:{path}?mode=ro" if readonly else f"file:{path}"
    connection = sqlite3.connect(uri, uri=True, check_same_thread=False, isolation_level=None)
    connection.row_factory = as_dict_factory
    if not readonly:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
    return connection


@dataclass(frozen=True)
class Settings:
    state_db: str
    corpus_db: str
    password_hash: str
    jev_key: str
    key_file: str = ""
    fast_url: str = "http://localhost:8000/v1"
    deep_url: str = "http://localhost:8001/v1"
    guard_url: str = "http://localhost:8002"
    instances_reported: int = 1
    jev_concurrency: int = 200
    fast_concurrency: int = 64
    deep_concurrency: int = 24
    check_concurrency: int = 16
    evidence_password_hash: str = ""

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        return cls(
            state_db=env["STATE_DB"],
            corpus_db=env["CORPUS_DB"],
            password_hash=env["SANDBOX_PASSWORD_HASH"],
            jev_key=env["TYPESAFE_API_KEY"],
            key_file=env.get("NEMOTRON_KEY_FILE", ""),
            fast_url=env.get("NEMOTRON_FAST_URL", "http://localhost:8000/v1"),
            deep_url=env.get("NEMOTRON_DEEP_URL", "http://localhost:8001/v1"),
            guard_url=env.get("GUARD_URL", "http://localhost:8002"),
            instances_reported=int(env.get("BREV_INSTANCES_REPORTED", "1")),
            jev_concurrency=int(env.get("JEV_CONCURRENCY", "200")),
            fast_concurrency=int(env.get("NEMOTRON_FAST_CONCURRENCY", "64")),
            deep_concurrency=int(env.get("NEMOTRON_DEEP_CONCURRENCY", "24")),
            check_concurrency=int(env.get("CHECK_CONCURRENCY", "16")),
            evidence_password_hash=env.get("EVIDENCE_PASSWORD_HASH", ""),
        )


class Transport:
    """All outbound HTTP. Replaced by a fake in tests."""

    def __init__(self) -> None:
        limits = httpx.Limits(max_connections=500, max_keepalive_connections=300)
        self.client = httpx.AsyncClient(limits=limits, headers={"user-agent": "safe-signal-sandbox/0.2"})

    async def post_json(self, url: str, headers: dict, payload: dict, timeout: float) -> dict:
        response = await self.client.post(url, headers=headers, json=payload, timeout=timeout)
        if response.status_code != 200:
            header = response.headers.get("retry-after", "")
            raise HttpError(response.status_code, float(header) if header.isdigit() else None)
        return response.json()

    async def get_ok(self, url: str, key: str, timeout: float = 6) -> bool:
        try:
            response = await self.client.get(url, headers={"authorization": f"Bearer {key}"}, timeout=timeout)
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def close(self) -> None:
        await self.client.aclose()


class CaseContext:
    """Measurements for one case."""

    def __init__(self) -> None:
        self.rate_limited = 0
        self.jev_fatal: int | None = None
        self.steps: dict[str, dict] = {}

    def step(self, name: str, ms: float | None, error: bool = False) -> None:
        step = self.steps.setdefault(name, {"count": 0, "errors": 0, "hist": {}})
        step["count"] += 1
        step["errors"] += int(error)
        if ms is not None:
            hist_add(step["hist"], ms)


class Service:
    def __init__(self, settings: Settings, transport: Transport | None = None):
        self.settings = settings
        self.transport = transport or Transport()
        self.db = connect(settings.state_db)
        for statement in SCHEMA:
            self.db.execute(statement)
        self.corpus_db = connect(settings.corpus_db, readonly=True)
        self.jev_gate = asyncio.Semaphore(settings.jev_concurrency)
        self.fast_gate = asyncio.Semaphore(settings.fast_concurrency)
        self.deep_gate = asyncio.Semaphore(settings.deep_concurrency)
        self.live_cache: dict[str, dict] = {}
        self.persisted_at: dict[str, float] = {}
        self.queues: dict[str, deque] = {}
        self.lanes: dict[str, list[asyncio.Task]] = {}
        self.drivers: dict[str, asyncio.Task] = {}
        self.halted: set[str] = set()
        self.health: dict = {}
        self.health_at = 0.0
        self.corpus_summary: dict = {}
        self.key_cache = ("", 0.0)
        self.watchdog: asyncio.Task | None = None
        self.evidence = EvidenceStore(str(Path(settings.state_db).with_name("evidence.db")))
        self.evidence_gate = asyncio.Lock()
        self.background: set[asyncio.Task] = set()

    # Lifecycle ---------------------------------------------------------------------------------------------------

    async def startup(self) -> None:
        self.corpus_summary = self.compute_corpus()
        for run in self.query("SELECT * FROM runs WHERE status IN ('running','checking')"):
            log.info("recovering run %s (%s)", run["id"], run["status"])
            self.rebuild_live(run)
            self.drivers[run["id"]] = asyncio.create_task(self.drive(run["id"]))
        self.watchdog = asyncio.create_task(self.watch())
        self.schedule_evidence()

    async def shutdown(self) -> None:
        tasks = [t for group in self.lanes.values() for t in group] + list(self.drivers.values()) + list(self.background)
        if self.watchdog:
            tasks.append(self.watchdog)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for run_id in list(self.live_cache):
            self.persist_live(run_id, force=True)
        await self.transport.close()

    def schedule_evidence(self) -> None:
        task = asyncio.create_task(self.log_evidence())
        self.background.add(task)
        task.add_done_callback(self.background.discard)

    async def log_evidence(self) -> None:
        """Logs finished runs as incidents. A failure here never affects a run; the next pass picks it up."""
        async with self.evidence_gate:
            try:
                reports = await asyncio.to_thread(self.evidence.ingest_pending, self.settings.state_db)
                for report in reports:
                    log.info("evidence logged: %s", report)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("evidence logging failed")

    async def watch(self) -> None:
        while True:
            await asyncio.sleep(15)
            for run in self.query("SELECT * FROM runs WHERE status='running'"):
                last = int(run["last_report_ms"]) or int(run["started_ms"])
                if now_ms() - last > STALL_SECONDS * 1000:
                    self.fail_run(run["id"], f"Stalled: no case finished for {STALL_SECONDS} seconds.")

    # Storage helpers ---------------------------------------------------------------------------------------------

    def query(self, statement: str, *args) -> list[dict]:
        return self.db.execute(statement, args).fetchall()

    def run(self, run_id: str) -> dict | None:
        rows = self.query("SELECT * FROM runs WHERE id=?", run_id)
        return rows[0] if rows else None

    def active(self) -> dict | None:
        rows = self.query("SELECT * FROM runs WHERE status IN ('running','checking') LIMIT 1")
        return rows[0] if rows else None

    def live_for(self, run: dict) -> dict:
        run_id = run["id"]
        if run_id not in self.live_cache:
            self.live_cache[run_id] = json.loads(run["live"]) if run["live"] else new_live()
        return self.live_cache[run_id]

    def persist_live(self, run_id: str, force: bool = False) -> None:
        current = time.monotonic()
        if force or current - self.persisted_at.get(run_id, 0.0) >= 1.0:
            queue = self.queues.get(run_id)
            run = self.run(run_id)
            claimed = (
                int(run["total"]) - len(queue)
                if queue is not None and run
                else (run["claimed"] if run else 0)
            )
            self.db.execute(
                "UPDATE runs SET live=?, claimed=? WHERE id=?",
                (safe_json(self.live_cache[run_id]), claimed, run_id),
            )
            self.persisted_at[run_id] = current

    def elapsed(self, run: dict) -> float:
        end = int(run["finished_ms"]) or now_ms()
        return max((end - int(run["started_ms"])) / 1000, 0.001)

    def rebuild_live(self, run: dict) -> None:
        """After a restart, recount from stored results: live stats saved up to a second ago may be behind."""
        old = json.loads(run["live"]) if run["live"] else new_live()
        live = new_live()
        live["steps"], live["timeline"], live["recent"] = old["steps"], old["timeline"], old["recent"]
        seen: set[str] = set()
        for item in self.query("SELECT * FROM results WHERE run_id=?", run["id"]):
            row = json.loads(item["row"])
            seen.add(item["case_id"])
            live["frames"] += row["frames"]
            live["decisions"] += row["frames_answered"]
            result = {"predicted_method": item["predicted_method"] or None, "method": item["method"]}
            if item["scam"] < 0:
                live["unlabeled"] += 1
            elif item["weak"]:
                count_row(live["weak"], result, item["outcome"], row["points"])
            else:
                method = live["methods"].setdefault(
                    item["method"], {"family": item["family"], **new_live_counts()}
                )
                count_row(method, result, item["outcome"], row["points"])
                model = live["models"].setdefault(item["model"], {**new_live_counts(), "hist": {}})
                count_row(model, result, item["outcome"], row["points"])
                hist_add(model["hist"], item["ms"])
                live["score_points"] += row["points"]
                live["score_n"] += 1
        live["processed"] = len(seen)
        self.live_cache[run["id"]] = live
        self.persist_live(run["id"], force=True)

    # Model calls -------------------------------------------------------------------------------------------------

    def nemotron_key(self) -> str:
        key, read_at = self.key_cache
        if not key or time.monotonic() - read_at > 30:
            key = Path(self.settings.key_file).read_text().strip() if self.settings.key_file else "test-key"
            self.key_cache = (key, time.monotonic())
        return key

    async def nemotron(
        self, ctx: CaseContext, model: str, system: str, user: str, max_tokens: int, timeout: float = 90
    ) -> str:
        fast = model == "nemotron-fast"
        gate = self.fast_gate if fast else self.deep_gate
        url = self.settings.fast_url if fast else self.settings.deep_url
        try:
            async with gate:
                body = await self.transport.post_json(
                    f"{url}/chat/completions",
                    {"authorization": f"Bearer {self.nemotron_key()}"},
                    {
                        "model": model,
                        "temperature": 0,
                        "max_tokens": max_tokens,
                        "response_format": {"type": "json_object"},
                        "chat_template_kwargs": {"enable_thinking": False},
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                    },
                    timeout,
                )
        except HttpError as error:
            if error.status == 429 or error.status >= 500:
                ctx.rate_limited += 1
            raise
        return body["choices"][0]["message"]["content"] or ""

    async def ask_agent(self, ctx: CaseContext, note: str, lines: list[str]) -> str:
        user = f"<note>{note or '(empty)'}</note>\n<call>\n" + "\n".join(lines) + "\n</call>"
        last: Exception | None = None
        for _ in range(2):
            try:
                return parse_note(await self.nemotron(ctx, "nemotron-fast", AGENT_SYSTEM, user, 200))
            except Exception as error:
                last = error
        raise last or RuntimeError("no attempts")

    async def ask_jev(self, ctx: CaseContext, model: str, state: str) -> dict:
        last: Exception | None = None
        for attempt in range(4):
            delay = 2.0**attempt
            try:
                async with self.jev_gate:
                    body = await self.transport.post_json(
                        JEV_URL,
                        {"authorization": f"Bearer {self.settings.jev_key}"},
                        {"model": model, "state": state, "questions": QUESTIONS},
                        20,
                    )
                return parse_jev_matrix(body)
            except ValueError:
                raise
            except HttpError as error:
                last = error
                if error.status in JEV_FATAL:
                    ctx.jev_fatal = error.status
                    raise
                if error.status != 429 and error.status < 500:
                    raise
                ctx.rate_limited += 1
                delay = max(delay, error.retry_after or 0.0)
            except Exception as error:
                last = error
            await asyncio.sleep(min(delay, 30) + random.random())
        raise last or RuntimeError("no attempts")

    async def ask_guard(self, state: str) -> dict:
        body = await self.transport.post_json(f"{self.settings.guard_url}/classify", {}, {"state": state}, 15)
        return parse_guard(body)

    async def ask_direct(self, ctx: CaseContext, model: str, state: str) -> dict:
        last: Exception | None = None
        for _ in range(2):
            try:
                return parse_direct(
                    await self.nemotron(ctx, model, DIRECT_SYSTEM, f"<case>\n{state}\n</case>", 220)
                )
            except Exception as error:
                last = error
        raise last or RuntimeError("no attempts")

    async def classify_frame(self, ctx: CaseContext, model: str, state: str, latest: str) -> dict:
        step = "jev" if model in JEV_MODELS else "guard" if model == GUARD_MODEL else ("baseline" if model == BASELINE else "nemotron_classifier")
        started = time.monotonic()
        try:
            if model == GUARD_MODEL:
                answer = await self.ask_guard(state)
            elif model in JEV_MODELS:
                answer = await self.ask_jev(ctx, model, state)
            elif model in BREV_MODELS:
                answer = await self.ask_direct(ctx, model, state)
            else:
                answer = baseline_classify(state)
            ms = (time.monotonic() - started) * 1000
            ctx.step(step, ms)
            return {**answer, "delivered": latest in state, "ms": ms}
        except Exception as error:
            ctx.step(step, None, error=True)
            return {"tier": None, "delivered": False, "ms": 0.0, "error": type(error).__name__}

    async def replay_case(self, case: dict, run: dict) -> dict:
        ctx = CaseContext()
        session = case_session(case)
        started = time.monotonic()
        frames = build_frames(session["events"], run["window_turns"])
        ctx.step("frames", (time.monotonic() - started) * 1000)
        per_model: dict[str, list] = {model: [] for model in run["models"]}
        note = ""
        for frame in frames:
            agent_called = bool(frame["scrolled_out"])
            agent_ok = True
            if agent_called:
                at = time.monotonic()
                try:
                    note = await self.ask_agent(ctx, note, frame["scrolled_out"])
                    ctx.step("agent", (time.monotonic() - at) * 1000)
                except Exception:
                    agent_ok = (
                        False  # keep the old note; the newest turns still reach the classifier verbatim (R4)
                    )
                    ctx.step("agent", None, error=True)
            state = compose_state(session, frame, note)
            answers = await asyncio.gather(
                *(self.classify_frame(ctx, m, state, frame["latest"]) for m in run["models"])
            )
            for model, answer in zip(run["models"], answers, strict=True):
                per_model[model].append(
                    {**answer, "t": frame["t"], "agent_called": agent_called, "agent_ok": agent_ok}
                )

        at = time.monotonic()
        results, decisions = [], 0
        for model, model_frames in per_model.items():
            answered = [f for f in model_frames if f["tier"]]
            decisions += len(answered)
            row = score_call(session, model_frames)
            peak = max(answered, key=lambda f: f["p_dangerous"], default=None)
            hard = max((row["peak_flags"].get(name, 0.0) for name in HARD_FLAGS), default=0.0)
            results.append(
                {
                    "model": model,
                    "row": row,
                    "predicted_method": peak.get("method") if peak else None,
                    "hard_flag": hard,
                    "ms": round(sum(f["ms"] for f in model_frames) / max(len(model_frames), 1)),
                    "scam": session["scam"],
                    "weak": case.get("label_quality") == "weak",
                    "method": case["method"],
                    "family": case.get("family") or METHODS.get(case["method"], ("unknown",))[0],
                    "channel": session["channel"],
                    "source": case.get("source", ""),
                }
            )
        ctx.step("score", (time.monotonic() - at) * 1000)
        return {
            "case_id": case["case_id"],
            "frames": len(frames) * len(run["models"]),
            "decisions": decisions,
            "steps": ctx.steps,
            "rate_limited": ctx.rate_limited,
            "jev_fatal": ctx.jev_fatal,
            "results": results,
        }

    # Run execution -----------------------------------------------------------------------------------------------

    def load_queue(self, run_id: str) -> deque:
        rows = self.query(
            "SELECT case_id FROM run_cases WHERE run_id=? AND case_id NOT IN (SELECT case_id FROM results WHERE run_id=?) ORDER BY seq",
            run_id,
            run_id,
        )
        queue = deque(row["case_id"] for row in rows)
        self.queues[run_id] = queue
        return queue

    def case_payload(self, case_id: str) -> dict | None:
        row = self.corpus_db.execute("SELECT payload FROM cases WHERE case_id=?", (case_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    async def lane(self, run_id: str, config: dict, queue: deque) -> None:
        run = {"models": config["models"], "window_turns": config["window_turns"]}
        while queue and run_id not in self.halted:
            case_id = queue.popleft()
            case = self.case_payload(case_id)
            if case is None:
                continue
            try:
                report = await self.replay_case(case, run)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                log.warning("case failed: %s", type(error).__name__)
                continue
            self.record(run_id, report)

    def record(self, run_id: str, report: dict) -> None:
        run = self.run(run_id)
        if not run:
            return
        fresh = 0
        self.db.execute("BEGIN")
        try:
            for result in report["results"]:
                row = result["row"]
                cursor = self.db.execute(
                    "INSERT OR IGNORE INTO results (run_id, case_id, model, method, family, channel, source, scam, weak, answered,"
                    " tier, outcome, predicted_method, p_d, p_ud, hard_flag, ms, row) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        report["case_id"],
                        result["model"],
                        result["method"],
                        result["family"],
                        result["channel"],
                        result["source"],
                        -1 if result["scam"] is None else int(result["scam"]),
                        int(result["weak"]),
                        int(row["frames_answered"] > 0),
                        row["tier"],
                        row["outcome"],
                        result["predicted_method"] or "",
                        row["max_p_dangerous"],
                        row["max_p_unsafe"],
                        result["hard_flag"],
                        result["ms"],
                        safe_json(row),
                    ),
                )
                fresh += cursor.rowcount
            self.db.execute("UPDATE runs SET last_report_ms=? WHERE id=?", (now_ms(), run_id))
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        if not fresh:
            return
        live = self.live_for(run)
        absorb_report(live, report, self.elapsed(run))
        if report.get("jev_fatal") and run["status"] == "running":
            self.fail_run(
                run_id,
                f"Auto-paused: Jev returned HTTP {report['jev_fatal']} ({JEV_FATAL[report['jev_fatal']]}). Fix it, then POST /runs/{run_id}/resume.",
            )
        if live["rate_streak"] >= RATE_STREAK_PAUSE and run["status"] == "running":
            self.fail_run(
                run_id,
                f"Auto-paused: {live['rate_streak']} cases in a row hit rate limits or server errors. POST /runs/{run_id}/resume to continue.",
            )
        self.persist_live(run_id)

    def fail_run(self, run_id: str, error: str) -> None:
        self.halted.add(run_id)
        self.db.execute(
            "UPDATE runs SET status='failed', error=?, finished_ms=? WHERE id=? AND status='running'",
            (error, now_ms(), run_id),
        )
        if run_id in self.live_cache:
            self.persist_live(run_id, force=True)

    async def drive(self, run_id: str) -> None:
        """Owns one run: replay with parallel lanes, then the check agent, then the final bookkeeping."""
        try:
            run = self.run(run_id)
            config = json.loads(run["config"])
            if run["status"] == "running":
                queue = self.load_queue(run_id)
                self.lanes[run_id] = [
                    asyncio.create_task(self.lane(run_id, config, queue)) for _ in range(int(run["lanes"]))
                ]
                await asyncio.gather(*self.lanes[run_id])
                self.lanes.pop(run_id, None)
                run = self.run(run_id)
                if run_id in self.halted or run["status"] != "running":
                    return
                self.queue_checks(run_id)
                self.db.execute("UPDATE runs SET status='checking', claimed=total WHERE id=?", (run_id,))
            await self.run_checks(run_id)
            self.finish(run_id)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            log.exception("run driver failed")
            self.fail_run(run_id, f"Run failed: {type(error).__name__}")

    def queue_checks(self, run_id: str) -> None:
        """Queue failures for the check agent, spreading the cap evenly across method, model and outcome."""
        names = ",".join(f"'{name}'" for name in sorted(FAILURES))
        self.db.execute(
            "INSERT OR REPLACE INTO check_queue (run_id, seq, case_id, model) "
            "SELECT run_id, ROW_NUMBER() OVER (ORDER BY rn, case_id) - 1, case_id, model FROM ("
            " SELECT run_id, case_id, model, ROW_NUMBER() OVER (PARTITION BY model, method, outcome ORDER BY case_id) AS rn"
            f" FROM results WHERE run_id=? AND weak=0 AND scam>=0 AND outcome IN ({names})"
            f") ORDER BY rn, case_id LIMIT {CHECK_MAX}",
            (run_id,),
        )
        total = self.query("SELECT COUNT(*) AS n FROM check_queue WHERE run_id=?", run_id)[0]["n"]
        self.db.execute("UPDATE runs SET check_total=? WHERE id=?", (total, run_id))

    async def run_checks(self, run_id: str) -> None:
        # Only runs after replay has finished, and is bounded below the deep model's gate, so it can't starve classifiers.
        items = self.query(
            "SELECT * FROM check_queue WHERE run_id=? AND seq NOT IN (SELECT seq FROM markers WHERE run_id=?) ORDER BY seq",
            run_id,
            run_id,
        )
        gate = asyncio.Semaphore(self.settings.check_concurrency)

        async def one(item: dict) -> None:
            async with gate:
                await self.check_one(run_id, item)

        await asyncio.gather(*(one(item) for item in items))

    async def check_one(self, run_id: str, item: dict) -> None:
        stored = self.query(
            "SELECT row FROM results WHERE run_id=? AND case_id=? AND model=?",
            run_id,
            item["case_id"],
            item["model"],
        )
        row = json.loads(stored[0]["row"])
        started = time.monotonic()
        check = None
        ctx = CaseContext()
        failure = "none"
        case = self.case_payload(item["case_id"])
        if case is not None:
            text = check_case_text(row, case_session(case))
            for _ in range(3):
                try:
                    check = parse_check(await self.nemotron(ctx, "nemotron-deep", CHECK_SYSTEM, text, 500))
                    break
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    failure = type(error).__name__
        if check is None:
            log.warning("check agent failed: %s", failure)
        live = self.live_cache.get(run_id)
        if live is not None:
            hist: dict = {}
            hist_add(hist, (time.monotonic() - started) * 1000)
            step_add(live, "check", 1, int(check is None), hist if check else {})
        marker = {**make_marker(row, check), "model": item["model"]}
        self.db.execute(
            "INSERT OR REPLACE INTO markers (run_id, seq, data) VALUES (?, ?, ?)",
            (run_id, int(item["seq"]), safe_json(marker)),
        )
        self.db.execute(
            "UPDATE runs SET check_done=(SELECT COUNT(*) FROM markers WHERE run_id=?) WHERE id=?",
            (run_id, run_id),
        )
        if live is not None:
            self.persist_live(run_id)

    def finish(self, run_id: str) -> None:
        run = self.run(run_id)
        live = self.live_for(run)
        now = datetime.now(UTC).isoformat()
        for model in live["models"]:
            groups = self.query(
                "SELECT method, COUNT(*) AS n, SUM(CASE WHEN outcome IN ('caught','clear') THEN 1.0"
                " WHEN outcome IN ('soft_miss','soft_false_alarm') THEN 0.5 ELSE 0 END) AS points"
                " FROM results WHERE run_id=? AND model=? AND weak=0 AND scam>=0 GROUP BY method",
                run_id,
                model,
            )
            for group in groups:
                n = int(group["n"])
                self.db.execute(
                    "INSERT INTO failure_log (run_id, ts, model, method, n, error_rate) VALUES (?,?,?,?,?,?)",
                    (run_id, now, model, group["method"], n, round(1 - float(group["points"]) / n, 4)),
                )
        self.persist_live(run_id, force=True)
        self.db.execute("UPDATE runs SET status='done', finished_ms=? WHERE id=?", (now_ms(), run_id))
        self.schedule_evidence()

    # HTTP routes -------------------------------------------------------------------------------------------------

    async def brev_status(self) -> dict:
        current = time.monotonic()
        if not self.health or current - self.health_at > HEALTH_TTL_S:
            try:
                key = self.nemotron_key()
            except OSError:
                key = ""
            fast, deep = await asyncio.gather(
                self.transport.get_ok(f"{self.settings.fast_url}/models", key),
                self.transport.get_ok(f"{self.settings.deep_url}/models", key),
            )
            self.health = {
                "instances_reported": self.settings.instances_reported,
                "endpoints": [{"name": "fast", "healthy": fast}, {"name": "deep", "healthy": deep}],
            }
            self.health_at = current
        return self.health

    def lanes_active(self, run: dict) -> int:
        if run["status"] != "running":
            return 0
        return sum(not task.done() for task in self.lanes.get(run["id"], []))

    def compute_corpus(self) -> dict:
        out: dict = {"total": 0}
        for key in ("channel", "source", "family", "method", "label_quality"):
            rows = self.corpus_db.execute(
                f"SELECT {key} AS name, COUNT(*) AS n FROM cases GROUP BY {key} ORDER BY n DESC"
            ).fetchall()
            out[f"by_{key}"] = {row["name"]: int(row["n"]) for row in rows}
        out["total"] = sum(out["by_channel"].values())
        return out

    def markers(self, run_id: str) -> list[dict]:
        return [
            json.loads(r["data"])
            for r in self.query("SELECT data FROM markers WHERE run_id=? ORDER BY seq", run_id)
        ]

    async def models(self) -> list[dict]:
        brev = await self.brev_status()
        jev_ok = await self.transport.get_ok(JEV_MODELS_URL, self.settings.jev_key)
        guard_ok = await self.transport.get_ok(f"{self.settings.guard_url}/health", "local")
        health = {entry["name"]: entry["healthy"] for entry in brev["endpoints"]}

        def healthy(model: str) -> bool:
            if model == GUARD_MODEL:
                return guard_ok
            if model in JEV_MODELS:
                return jev_ok
            return True if model == BASELINE else health["fast" if model == "nemotron-fast" else "deep"]

        kinds = {
            m: "guard" if m == GUARD_MODEL else "jev" if m in JEV_MODELS else "baseline" if m == BASELINE else "nemotron" for m in ALL_MODELS
        }
        return [{"id": model, "kind": kinds[model], "healthy": healthy(model)} for model in ALL_MODELS]

    def public_budget_problem(self, day: str, cases: int) -> str | None:
        row = self.db.execute("SELECT runs, cases FROM public_budget WHERE day=?", (day,)).fetchone()
        runs_used, cases_used = (row["runs"], row["cases"]) if row else (0, 0)
        if runs_used >= PUBLIC_DAILY_RUNS:
            return f"The site's limit of {PUBLIC_DAILY_RUNS} runs a day has been reached. It resets at midnight UTC."
        if cases_used + cases > PUBLIC_DAILY_CASES:
            left = max(PUBLIC_DAILY_CASES - cases_used, 0)
            return f"The site has {left} cases left today, out of {PUBLIC_DAILY_CASES}. It resets at midnight UTC."
        return None

    def start(self, body: object, public: bool = False) -> tuple[dict, int]:
        running = self.active()
        if running:
            return {"error": "A run is already in progress", "id": running["id"]}, 409
        try:
            config = validate_run(body)  # type: ignore[arg-type]
        except (ValueError, TypeError, AttributeError) as error:
            return {"error": str(error) or "Send a JSON object"}, 400
        where, args = corpus_filter(config)
        available = self.corpus_db.execute(f"SELECT COUNT(*) AS n FROM cases WHERE {where}", args).fetchone()[
            "n"
        ]
        if not available:
            return {"error": "No corpus cases match that selection"}, 400
        moment = datetime.now(UTC)
        run_id = "run-" + moment.strftime("%Y%m%d%H%M%S%f")[:17]
        total = min(config["limit"], available)
        config["lanes"] = lanes = min(config["lanes"], total)
        day = moment.strftime("%Y-%m-%d")
        metered = public and any(model in JEV_MODELS for model in config["models"])
        if metered and (problem := self.public_budget_problem(day, total)):
            return {"error": problem}, 429
        ids = self.corpus_db.execute(
            f"SELECT case_id FROM cases WHERE {where} ORDER BY rand, case_id LIMIT ?", [*args, total]
        ).fetchall()
        self.db.execute("BEGIN")
        self.db.execute(
            "INSERT INTO runs (id, created_at, started_ms, config, total, lanes, status) VALUES (?,?,?,?,?,?,'running')",
            (run_id, moment.isoformat(), now_ms(), safe_json(config), total, lanes),
        )
        self.db.executemany(
            "INSERT INTO run_cases (run_id, seq, case_id) VALUES (?,?,?)",
            [(run_id, i, r["case_id"]) for i, r in enumerate(ids)],
        )
        if metered:
            self.db.execute(
                "INSERT INTO public_budget (day, runs, cases) VALUES (?, 1, ?)"
                " ON CONFLICT(day) DO UPDATE SET runs=runs+1, cases=cases+excluded.cases",
                (day, total),
            )
        self.db.execute("COMMIT")
        self.drivers[run_id] = asyncio.create_task(self.drive(run_id))
        return {"id": run_id, "total": total, "lanes": lanes, "available": available}, 201

    async def cancel(self, run: dict) -> dict:
        run_id = run["id"]
        if run["status"] not in ACTIVE:
            return {"cancelled": False}
        self.halted.add(run_id)
        self.db.execute("UPDATE runs SET status='cancelled', finished_ms=? WHERE id=?", (now_ms(), run_id))
        tasks = [*self.lanes.pop(run_id, []), *([self.drivers.pop(run_id)] if run_id in self.drivers else [])]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if run_id in self.live_cache:
            self.persist_live(run_id, force=True)
        return {"cancelled": True}

    async def resume(self, run: dict) -> tuple[dict, int]:
        run_id = run["id"]
        if run["status"] != "failed" or "Auto-paused" not in (run["error"] or ""):
            return {"error": "Only an auto-paused run can resume"}, 409
        if self.active():
            return {"error": "A run is already in progress"}, 409
        old = self.drivers.pop(run_id, None)
        if old:
            await asyncio.wait([old], timeout=60)
        self.halted.discard(run_id)
        self.live_for(run)["rate_streak"] = 0
        self.db.execute(
            "UPDATE runs SET status='running', error='', finished_ms=0, last_report_ms=? WHERE id=?",
            (now_ms(), run_id),
        )
        self.drivers[run_id] = asyncio.create_task(self.drive(run_id))
        return {"resumed": True}, 200

    def rescore(self, run_id: str, body: object) -> tuple[dict, int]:
        try:
            dangerous, uncertain, hard = rescore_params(body)  # type: ignore[arg-type]
        except (ValueError, TypeError, AttributeError) as error:
            return {"error": str(error) or "Send a JSON object"}, 400
        # At the default settings the score must match the live one, so use each model's own chosen tier. Thresholds
        # on peak probabilities apply only once someone moves a lever.
        model_tier = dangerous == DEFAULT_DANGEROUS and uncertain == DEFAULT_UNCERTAIN and not hard
        tier_sql = "CASE WHEN answered=0 THEN 'none' ELSE tier END" if model_tier else RESCORE_TIER_SQL
        tier_args = [] if model_tier else [dangerous, hard, uncertain]

        def grouped(key: str) -> list[dict]:
            return self.query(
                f"SELECT {key}, scam, {tier_sql} AS tier, COUNT(*) AS n,"
                " SUM(predicted_method=method) AS method_ok, SUM(predicted_method!='') AS method_seen"
                f" FROM results WHERE run_id=? AND weak=0 AND scam>=0 GROUP BY {key}, scam, {tier_sql}",
                *tier_args,
                run_id,
                *tier_args,
            )

        families = {
            r["method"]: r["family"]
            for r in self.query("SELECT DISTINCT method, family FROM results WHERE run_id=?", run_id)
        }
        by_method = [
            {**item, "family": families.get(item["method"], "unknown")}
            for item in rescored_rows(grouped("method"), "method")
        ]
        return {
            "thresholds": {
                "dangerous_threshold": dangerous,
                "uncertain_threshold": uncertain,
                "require_hard_flag": bool(hard),
            },
            "mode": "model_tier" if model_tier else "peak_probability_thresholds",
            "by_method": by_method,
            "by_model": rescored_rows(grouped("model"), "model"),
        }, 200

    def export_results(self, run_id: str, params: dict) -> dict:
        """Keyset-paged per-case results: scores, tiers and flag names only. An allow-list, so no text can leave."""
        limit = max(1, min(int(params.get("limit", ["1000"])[0]), 1000))
        after_case = params.get("after_case", [""])[0]
        after_model = params.get("after_model", [""])[0]
        model = params.get("model", [""])[0]
        rows = self.query(
            "SELECT case_id, model, method, family, channel, source, weak, predicted_method, row FROM results"
            " WHERE run_id=? AND (case_id, model) > (?, ?) AND (?='' OR model=?) ORDER BY case_id, model LIMIT ?",
            run_id,
            after_case,
            after_model,
            model,
            model,
            limit,
        )
        items = []
        for stored in rows:
            row = json.loads(stored["row"])
            items.append(
                {
                    "case_id": stored["case_id"],
                    "model": stored["model"],
                    "method": stored["method"],
                    "family": stored["family"],
                    "channel": stored["channel"],
                    "source": stored["source"],
                    "weak": bool(stored["weak"]),
                    "predicted_method": stored["predicted_method"] or None,
                    "row": {key: row.get(key) for key in EXPORT_ROW_KEYS},
                }
            )
        last = rows[-1] if len(rows) == limit else None
        return {
            "items": items,
            "next": {"after_case": last["case_id"], "after_model": last["model"]} if last else None,
        }

    def lessons(self) -> dict:
        runs = [
            r["run_id"]
            for r in self.query("SELECT DISTINCT run_id FROM failure_log ORDER BY ts DESC LIMIT 5")
        ]
        repeat: list[dict] = []
        if runs:
            marks = ",".join("?" * len(runs))
            repeat = self.query(
                f"SELECT model, method, COUNT(DISTINCT run_id) AS runs_failing, ROUND(AVG(error_rate), 4) AS mean_error_rate, SUM(n) AS calls"
                f" FROM failure_log WHERE run_id IN ({marks}) AND error_rate>=0.2 GROUP BY model, method"
                " HAVING runs_failing>=2 ORDER BY mean_error_rate DESC",
                *runs,
            )
        counts: dict[tuple, dict] = {}
        for row in self.query("SELECT run_id, data FROM markers ORDER BY run_id DESC LIMIT 5000"):
            marker = json.loads(row["data"])
            if marker["marker"] == "check_agent_failed":
                continue
            key = (marker["marker"], marker["call_type"], marker["outcome"])
            entry = counts.setdefault(
                key,
                {
                    "marker": key[0],
                    "method": key[1],
                    "outcome": key[2],
                    "count": 0,
                    "improvement": marker["improvement"],
                    "feedback": marker["feedback"],
                },
            )
            entry["count"] += 1
        return {
            "runs_logged": len(runs),
            "repeat_failures": repeat,
            "lessons": sorted(counts.values(), key=lambda x: -x["count"])[:100],
        }


def new_live_counts() -> dict:
    from classify import new_counts

    return new_counts()


def error(message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


async def read_json(request: Request) -> object:
    try:
        return json.loads(await request.body())
    except ValueError:
        return None


async def dispatch(service: Service, request: Request) -> Response:
    path = request.url.path.rstrip("/")
    method = request.method
    if path == "/corpus" and method == "GET":
        return JSONResponse(service.corpus_summary)
    if path == "/models" and method == "GET":
        return JSONResponse(await service.models())
    if path == "/lessons" and method == "GET":
        return JSONResponse(service.lessons())
    if path == "/runs" and method == "GET":
        return JSONResponse(
            service.query(
                "SELECT id, created_at, total, lanes, claimed, status, error, check_total, check_done FROM runs ORDER BY created_at DESC LIMIT 50"
            )
        )
    if path == "/runs" and method == "POST":
        public = request.headers.get("x-safe-signal-public") == "1"
        body, status = service.start(await read_json(request), public=public)
        return JSONResponse(body, status_code=status)

    match = re.fullmatch(
        r"/runs/([\w-]+)(/live|/rescore|/markers\.json|/markers\.csv|/cancel|/resume|/results)?", path
    )
    if not match:
        return error("Not found", 404)
    run_id, action = match.group(1), match.group(2)
    run = service.run(run_id)
    if not run:
        return error("Not found", 404)

    if action in ("/live", None) and method == "GET":
        view = live_view(
            run,
            service.live_for(run),
            service.lanes_active(run),
            await service.brev_status(),
            service.elapsed(run),
        )
        if action == "/live":
            return JSONResponse(view)
        return JSONResponse(
            {k: v for k, v in view.items() if k not in ("recent", "timeline")}
            | {"config": json.loads(run["config"])}
        )
    if action == "/rescore" and method == "POST":
        body, status = service.rescore(run_id, await read_json(request))
        return JSONResponse(body, status_code=status)
    if action == "/markers.json" and method == "GET":
        return JSONResponse(service.markers(run_id))
    if action == "/markers.csv" and method == "GET":
        return Response(
            markers_csv(service.markers(run_id)),
            media_type="text/csv",
            headers={"content-disposition": f'attachment; filename="{run_id}-markers.csv"'},
        )
    if action == "/results" and method == "GET":
        try:
            return JSONResponse(service.export_results(run_id, parse_qs(request.url.query)))
        except ValueError:
            return error("limit must be a whole number", 400)
    if action == "/cancel" and method == "POST":
        return JSONResponse(await service.cancel(run))
    if action == "/resume" and method == "POST":
        body, status = await service.resume(run)
        return JSONResponse(body, status_code=status)
    return error("Not found", 404)


def build_app(service: Service) -> Starlette:
    async def handler(request: Request) -> Response:
        if request.url.path == "/healthz":
            return JSONResponse({"ok": True})
        given = request.headers.get("authorization", "").removeprefix("Bearer ")
        digest = hashlib.sha256(given.encode()).hexdigest()
        path = request.url.path.rstrip("/")
        is_evidence = path == "/evidence" or path.startswith("/evidence/")
        # The evidence password opens the incident store and nothing else.
        accepted = [service.settings.password_hash]
        if is_evidence and service.settings.evidence_password_hash:
            accepted.append(service.settings.evidence_password_hash)
        if not given or not any(hmac.compare_digest(digest, known) for known in accepted):
            return error("Unauthorized", 401)
        try:
            if is_evidence:
                status, text, headers = service.evidence.respond(
                    request.method, path.removeprefix("/evidence"), request.url.query, await request.body()
                )
                return Response(text, status_code=status, headers=headers)
            return await dispatch(service, request)
        except Exception as caught:
            log.exception("request failed")
            return error(f"Internal error: {type(caught).__name__}", 500)

    @contextlib.asynccontextmanager
    async def lifespan(_app: Starlette):
        await service.startup()
        yield
        await service.shutdown()

    methods = ["GET", "POST", "OPTIONS", "PUT", "DELETE", "HEAD"]
    return Starlette(routes=[Route("/{path:path}", handler, methods=methods)], lifespan=lifespan)
