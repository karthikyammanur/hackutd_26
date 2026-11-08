"""Safe Signal sandbox backend: Python Worker, a coordinator Durable Object and parallel lane Durable Objects.

The Runner (coordinator) owns run state and hands out cases. Each Lane claims one case at a time from it, runs the
case through the agent and every selected classifier, and reports scores back. See sandbox/CONTRACT.md for the API.

Every request needs `Authorization: Bearer <password>`; the Worker only holds the password's SHA-256 hash.
Stored: scores, flags, ids, markers. Transcript text and agent notes stay in memory (R8).
"""

import asyncio
import hashlib
import hmac
import json
import re
import time
from datetime import UTC, datetime
from urllib.parse import urlparse

from classify import (
    ALL_MODELS,
    BASELINE,
    BREV_MODELS,
    DIRECT_SYSTEM,
    HARD_FLAGS,
    JEV_MODELS,
    RESCORE_TIER_SQL,
    BrevPacer,
    absorb_report,
    baseline_classify,
    case_session,
    corpus_filter,
    hist_add,
    jev_questions,
    live_view,
    new_live,
    parse_direct,
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
from taxonomy import METHODS
from workers import DurableObject, Response, WorkerEntrypoint, fetch

JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MODELS_URL = "https://api.typesafe.ai/v1/models"
QUESTIONS = jev_questions()
CHECK_MAX = 500
CHECK_PER_ALARM = 4
PAGE_SIZE = 200
RATE_STREAK_PAUSE = 12
STALL_SECONDS = 180
HEALTH_TTL_S = 15
CORPUS_TTL_S = 60


class HttpError(RuntimeError):
    def __init__(self, status: int):
        super().__init__(f"HTTP {status}")
        self.status = status


class BudgetExceeded(RuntimeError):
    pass


def now_ms() -> int:
    return int(time.time() * 1000)


def json_response(body, status: int = 200) -> Response:
    return Response(json.dumps(body), status=status, headers={"content-type": "application/json"})


async def post_json(url: str, headers: dict, payload: dict, timeout: float) -> dict:
    async def call():
        response = await fetch(
            url,
            method="POST",
            headers={"content-type": "application/json", **headers},
            body=json.dumps(payload),
        )
        if response.status != 200:
            raise HttpError(int(response.status))
        return json.loads(await response.text())

    return await asyncio.wait_for(call(), timeout)


async def get_ok(url: str, key: str, timeout: float = 6) -> bool:
    async def call():
        response = await fetch(url, headers={"authorization": f"Bearer {key}"})
        return int(response.status) == 200

    try:
        return await asyncio.wait_for(call(), timeout)
    except Exception:
        return False


async def d1_all(env, sql: str, *args) -> list[dict]:
    statement = env.CORPUS.prepare(sql)
    if args:
        statement = statement.bind(*args)
    result = await statement.all()
    return list(result.results.to_py())


def endpoint_for(env, model: str) -> str:
    return env.BREV_FAST_URL if model == "nemotron-fast" else env.BREV_DEEP_URL


class CaseContext:
    """Per-case budget, pacing and measurements for one lane alarm."""

    def __init__(self, env, pacer: BrevPacer):
        self.env = env
        self.remaining = int(env.SUBREQUEST_BUDGET)
        self.pacer = pacer
        self.rate_limited = 0
        self.steps: dict[str, dict] = {}

    def spend(self) -> None:
        if self.remaining <= 0:
            raise BudgetExceeded("subrequest budget")
        self.remaining -= 1

    def step(self, name: str, ms: float | None, error: bool = False) -> None:
        step = self.steps.setdefault(name, {"count": 0, "errors": 0, "hist": {}})
        step["count"] += 1
        step["errors"] += int(error)
        if ms is not None:
            hist_add(step["hist"], ms)

    async def pace_brev(self) -> None:
        """Global bound on the shared A100, held across cases by the lane's pacer."""
        wait = self.pacer.reserve(time.monotonic())
        if wait > 0:
            await asyncio.sleep(wait)


async def brev_complete(ctx: CaseContext, model: str, system: str, user: str, max_tokens: int, timeout: float = 60) -> str:
    await ctx.pace_brev()
    ctx.spend()
    try:
        body = await post_json(
            f"{endpoint_for(ctx.env, model)}/chat/completions",
            {"authorization": f"Bearer {ctx.env.BREV_API_KEY}"},
            {
                "model": model,
                "temperature": 0,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
                "chat_template_kwargs": {"enable_thinking": False},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            },
            timeout,
        )
    except HttpError as error:
        if error.status == 429:
            ctx.rate_limited += 1
        raise
    return body["choices"][0]["message"]["content"] or ""


async def ask_agent(ctx: CaseContext, note: str, lines: list[str]) -> str:
    user = f"<note>{note or '(empty)'}</note>\n<call>\n" + "\n".join(lines) + "\n</call>"
    last = None
    for _ in range(2):
        try:
            return parse_note(await brev_complete(ctx, "nemotron-fast", AGENT_SYSTEM, user, 200))
        except BudgetExceeded:
            raise
        except Exception as error:
            last = error
    raise last


async def ask_jev(ctx: CaseContext, model: str, state: str) -> dict:
    last = None
    for attempt in range(3):
        ctx.spend()
        try:
            body = await post_json(
                JEV_URL,
                {"authorization": f"Bearer {ctx.env.TYPESAFE_API_KEY}"},
                {"model": model, "state": state, "questions": QUESTIONS},
                15,
            )
            return parse_jev_matrix(body)
        except ValueError:
            raise
        except HttpError as error:
            last = error
            if error.status == 429:
                ctx.rate_limited += 1
            elif error.status < 500:
                raise
        except Exception as error:
            last = error
        await asyncio.sleep(2**attempt)
    raise last


async def ask_direct(ctx: CaseContext, model: str, state: str) -> dict:
    last = None
    for _ in range(2):
        try:
            return parse_direct(await brev_complete(ctx, model, DIRECT_SYSTEM, f"<case>\n{state}\n</case>", 220))
        except BudgetExceeded:
            raise
        except Exception as error:
            last = error
    raise last


async def classify_frame(ctx: CaseContext, model: str, state: str, latest: str) -> dict:
    step = "jev" if model in JEV_MODELS else ("baseline" if model == BASELINE else "nemotron_classifier")
    started = time.monotonic()
    try:
        if model in JEV_MODELS:
            answer = await ask_jev(ctx, model, state)
        elif model in BREV_MODELS:
            answer = await ask_direct(ctx, model, state)
        else:
            answer = baseline_classify(state)
        ms = (time.monotonic() - started) * 1000
        ctx.step(step, ms)
        return {**answer, "delivered": latest in state, "ms": ms}
    except Exception as error:
        ctx.step(step, None, error=True)
        return {"tier": None, "delivered": False, "ms": 0.0, "error": type(error).__name__}


async def replay_case(env, case: dict, run: dict, pacer: BrevPacer) -> dict:
    """Run one case through the note agent and every selected classifier."""
    ctx = CaseContext(env, pacer)
    session = case_session(case)
    started = time.monotonic()
    frames = build_frames(session["events"], run["window_turns"])
    ctx.step("frames", (time.monotonic() - started) * 1000)
    per_model = {model: [] for model in run["models"]}
    note = ""
    for frame in frames:
        agent_called = bool(frame["scrolled_out"])
        agent_ok = True
        if agent_called:
            at = time.monotonic()
            try:
                note = await ask_agent(ctx, note, frame["scrolled_out"])
                ctx.step("agent", (time.monotonic() - at) * 1000)
            except Exception:
                agent_ok = False  # keep the old note; the newest turns still reach the classifier verbatim (R4)
                ctx.step("agent", None, error=True)
        state = compose_state(session, frame, note)
        answers = await asyncio.gather(*(classify_frame(ctx, m, state, frame["latest"]) for m in run["models"]))
        for model, answer in zip(run["models"], answers, strict=True):
            per_model[model].append({**answer, "t": frame["t"], "agent_called": agent_called, "agent_ok": agent_ok})

    at = time.monotonic()
    results, decisions = [], 0
    for model, model_frames in per_model.items():
        answered = [f for f in model_frames if f["tier"]]
        decisions += len(answered)
        row = score_call(session, model_frames)
        peak = max(answered, key=lambda f: f["p_dangerous"], default=None)
        predicted = peak.get("method") if peak else None
        hard = max((row["peak_flags"].get(name, 0.0) for name in HARD_FLAGS), default=0.0)
        ms = round(sum(f["ms"] for f in model_frames) / max(len(model_frames), 1))
        results.append(
            {
                "model": model,
                "row": row,
                "predicted_method": predicted,
                "hard_flag": hard,
                "ms": ms,
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
        "results": results,
    }


class Lane(DurableObject):
    """One parallel worker. Claims a case, processes it, reports, repeats on the next alarm."""

    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        self.ctx = ctx
        self.env = env
        self.pacer = None

    def coordinator(self):
        return self.env.RUNNER.getByName("coordinator-v2")

    async def begin(self, payload: str) -> str:
        await self.ctx.storage.put("assignment", payload)
        await self.ctx.storage.delete("inflight")
        await self.ctx.storage.setAlarm(now_ms() + 1)
        return "ok"

    async def alarm(self, alarm_info=None):
        assignment = await self.ctx.storage.get("assignment")
        if not assignment:
            return
        job = json.loads(assignment)
        run = job["run"]
        inflight = await self.ctx.storage.get("inflight")
        if not inflight:
            inflight = await self.coordinator().claim(safe_json({"run_id": run["id"]}))
            inflight = str(inflight)
            if inflight == "stop":
                await self.ctx.storage.delete("assignment")
                await self.coordinator().lane_finished(safe_json({"run_id": run["id"], "lane": job["lane"]}))
                return
            await self.ctx.storage.put("inflight", inflight)

        rows = await d1_all(self.env, "SELECT payload FROM cases WHERE case_id=?", inflight)
        if rows:
            if self.pacer is None:
                self.pacer = BrevPacer(int(run["lanes"]), float(self.env.BREV_MAX_RPS))
            report = await replay_case(self.env, json.loads(rows[0]["payload"]), run, self.pacer)
            await self.coordinator().report(safe_json({"run_id": run["id"], **report}))
        else:
            await self.coordinator().report(safe_json({"run_id": run["id"], "case_id": inflight, "missing": True}))
        await self.ctx.storage.delete("inflight")
        await self.ctx.storage.setAlarm(now_ms() + 1)


class Runner(DurableObject):
    """Coordinator: run records, case queue, results, statistics and the check agent."""

    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        self.ctx = ctx
        self.env = env
        self.sql = ctx.storage.sql
        self.live_cache: dict[str, dict] = {}
        self.persisted_at: dict[str, float] = {}
        self.health: dict = {}
        self.health_at = 0.0
        self.check_pacer = BrevPacer(1, 8.0)
        self.corpus_cache: dict = {}
        self.corpus_at = 0.0
        self.page_lock = asyncio.Lock()
        for statement in (
            "CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created_at TEXT, started_ms INTEGER, finished_ms INTEGER DEFAULT 0,"
            " config TEXT, total INTEGER, lanes INTEGER, claimed INTEGER DEFAULT 0, page TEXT DEFAULT '[]', cursor_rand REAL DEFAULT -1,"
            " cursor_id TEXT DEFAULT '', lanes_done INTEGER DEFAULT 0, check_total INTEGER DEFAULT 0, check_done INTEGER DEFAULT 0,"
            " last_report_ms INTEGER DEFAULT 0, status TEXT, error TEXT DEFAULT '', live TEXT DEFAULT '')",
            "CREATE TABLE IF NOT EXISTS results (run_id TEXT, case_id TEXT, model TEXT, method TEXT, family TEXT, channel TEXT,"
            " scam INTEGER, weak INTEGER, answered INTEGER, outcome TEXT, predicted_method TEXT, p_d REAL, p_ud REAL, hard_flag REAL,"
            " row TEXT, PRIMARY KEY (run_id, case_id, model))",
            "CREATE TABLE IF NOT EXISTS check_queue (run_id TEXT, seq INTEGER, case_id TEXT, model TEXT, PRIMARY KEY (run_id, seq))",
            "CREATE TABLE IF NOT EXISTS markers (run_id TEXT, seq INTEGER, data TEXT, PRIMARY KEY (run_id, seq))",
            "CREATE TABLE IF NOT EXISTS failure_log (run_id TEXT, ts TEXT, model TEXT, method TEXT, n INTEGER, error_rate REAL)",
        ):
            self.sql.exec(statement)

    def query(self, statement: str, *args) -> list[dict]:
        return list(self.sql.exec(statement, *args).toArray().to_py())

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
            self.sql.exec("UPDATE runs SET live=? WHERE id=?", safe_json(self.live_cache[run_id]), run_id)
            self.persisted_at[run_id] = current

    def elapsed(self, run: dict) -> float:
        end = int(run["finished_ms"]) or now_ms()
        return max((end - int(run["started_ms"])) / 1000, 0.001)

    # Lane RPC --------------------------------------------------------------------------------------------------

    async def claim(self, payload: str) -> str:
        run_id = json.loads(payload)["run_id"]
        async with self.page_lock:
            run = self.run(run_id)
            if not run or run["status"] != "running" or int(run["claimed"]) >= int(run["total"]):
                return "stop"
            page = json.loads(run["page"])
            if not page:
                page = await self.next_page(run)
                if not page:
                    return "stop"
            case_id = page.pop(0)
            self.sql.exec("UPDATE runs SET page=?, claimed=claimed+1 WHERE id=?", safe_json(page), run_id)
            return case_id

    async def next_page(self, run: dict) -> list[str]:
        config = json.loads(run["config"])
        where, args = corpus_filter(config)
        rows = await d1_all(
            self.env,
            f"SELECT case_id, rand FROM cases WHERE ({where}) AND (rand > ? OR (rand = ? AND case_id > ?)) ORDER BY rand, case_id LIMIT ?",
            *args,
            float(run["cursor_rand"]),
            float(run["cursor_rand"]),
            run["cursor_id"],
            PAGE_SIZE,
        )
        if not rows:
            return []
        self.sql.exec("UPDATE runs SET cursor_rand=?, cursor_id=? WHERE id=?", float(rows[-1]["rand"]), rows[-1]["case_id"], run["id"])
        return [row["case_id"] for row in rows]

    async def report(self, payload: str) -> str:
        report = json.loads(payload)
        run_id = report["run_id"]
        run = self.run(run_id)
        if not run or report.get("missing"):
            return "ok"
        fresh = 0
        for result in report["results"]:
            row = result["row"]
            cursor = self.sql.exec(
                "INSERT OR IGNORE INTO results (run_id, case_id, model, method, family, channel, scam, weak, answered, outcome,"
                " predicted_method, p_d, p_ud, hard_flag, row) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                run_id,
                report["case_id"],
                result["model"],
                result["method"],
                result["family"],
                result["channel"],
                -1 if result["scam"] is None else int(result["scam"]),
                int(result["weak"]),
                int(row["frames_answered"] > 0),
                row["outcome"],
                result["predicted_method"] or "",
                row["max_p_dangerous"],
                row["max_p_unsafe"],
                result["hard_flag"],
                safe_json(row),
            )
            cursor.toArray()
            fresh += int(cursor.rowsWritten > 0)
        if not fresh:  # a retried alarm reported this case already
            return "ok"
        live = self.live_for(run)
        absorb_report(live, report, self.elapsed(run))
        self.sql.exec("UPDATE runs SET last_report_ms=? WHERE id=?", now_ms(), run_id)
        if live["rate_streak"] >= RATE_STREAK_PAUSE:
            self.fail_run(run_id, f"Auto-paused: {live['rate_streak']} cases in a row hit rate limits. POST /runs/{run_id}/resume to continue.")
        self.persist_live(run_id)
        return "ok"

    def fail_run(self, run_id: str, error: str) -> None:
        self.sql.exec("UPDATE runs SET status='failed', error=?, finished_ms=? WHERE id=? AND status='running'", error, now_ms(), run_id)

    async def lane_finished(self, payload: str) -> str:
        run_id = json.loads(payload)["run_id"]
        self.sql.exec("UPDATE runs SET lanes_done=lanes_done+1 WHERE id=?", run_id)
        run = self.run(run_id)
        if run and run["status"] == "running" and int(run["lanes_done"]) >= int(run["lanes"]):
            if run_id in self.live_cache:
                self.persist_live(run_id, force=True)
            self.queue_checks(run_id)
            self.sql.exec("UPDATE runs SET status='checking' WHERE id=?", run_id)
            await self.ctx.storage.setAlarm(now_ms() + 10)
        return "ok"

    def queue_checks(self, run_id: str) -> None:
        """Queue failures for the check agent, spreading the cap evenly across method, model and outcome."""
        names = ",".join(f"'{name}'" for name in sorted(FAILURES))
        self.sql.exec(
            "INSERT OR REPLACE INTO check_queue (run_id, seq, case_id, model) "
            "SELECT run_id, ROW_NUMBER() OVER (ORDER BY rn, case_id) - 1, case_id, model FROM ("
            " SELECT run_id, case_id, model, ROW_NUMBER() OVER (PARTITION BY model, method, outcome ORDER BY case_id) AS rn"
            f" FROM results WHERE run_id=? AND weak=0 AND scam>=0 AND outcome IN ({names})"
            f") ORDER BY rn, case_id LIMIT {CHECK_MAX}",
            run_id,
        )
        total = int(self.query("SELECT COUNT(*) AS n FROM check_queue WHERE run_id=?", run_id)[0]["n"])
        self.sql.exec("UPDATE runs SET check_total=? WHERE id=?", total, run_id)

    # Coordinator alarm: check agent and stall watchdog -----------------------------------------------------------

    async def alarm(self, alarm_info=None):
        run = self.active()
        if not run:
            return
        run_id = run["id"]
        if run["status"] == "running":
            last = int(run["last_report_ms"]) or int(run["started_ms"])
            if now_ms() - last > STALL_SECONDS * 1000:
                self.fail_run(run_id, f"Stalled: no case finished for {STALL_SECONDS} seconds.")
                return
            await self.ctx.storage.setAlarm(now_ms() + 30000)
            return

        done, total = int(run["check_done"]), int(run["check_total"])
        if done < total:
            batch = self.query("SELECT * FROM check_queue WHERE run_id=? AND seq>=? ORDER BY seq LIMIT ?", run_id, done, CHECK_PER_ALARM)
            await asyncio.gather(*(self.check_one(run_id, item) for item in batch))
            self.sql.exec("UPDATE runs SET check_done=? WHERE id=?", done + len(batch), run_id)
            if run_id in self.live_cache:
                self.persist_live(run_id, force=True)
            await self.ctx.storage.setAlarm(now_ms() + 10)
            return
        self.finish(run)

    async def check_one(self, run_id: str, item: dict) -> None:
        stored = self.query("SELECT row FROM results WHERE run_id=? AND case_id=? AND model=?", run_id, item["case_id"], item["model"])
        row = json.loads(stored[0]["row"])
        started = time.monotonic()
        check = None
        ctx = CaseContext(self.env, self.check_pacer)
        failure = "none"
        try:
            cases = await d1_all(self.env, "SELECT payload FROM cases WHERE case_id=?", item["case_id"])
            text = check_case_text(row, case_session(json.loads(cases[0]["payload"])))
            for _ in range(3):
                try:
                    check = parse_check(await brev_complete(ctx, "nemotron-deep", CHECK_SYSTEM, text, 500))
                    break
                except Exception as error:
                    failure = type(error).__name__
        except Exception as error:
            failure = type(error).__name__
        if check is None:
            print(f"check agent failed: {failure}")
        live = self.live_cache.get(run_id)
        if live is not None:
            hist: dict = {}
            hist_add(hist, (time.monotonic() - started) * 1000)
            step_add(live, "check", 1, int(check is None), hist if check else {})
        marker = {**make_marker(row, check), "model": item["model"]}
        self.sql.exec("INSERT OR REPLACE INTO markers (run_id, seq, data) VALUES (?, ?, ?)", run_id, int(item["seq"]), safe_json(marker))

    def finish(self, run: dict) -> None:
        run_id = run["id"]
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
                self.sql.exec(
                    "INSERT INTO failure_log (run_id, ts, model, method, n, error_rate) VALUES (?,?,?,?,?,?)",
                    run_id,
                    now,
                    model,
                    group["method"],
                    n,
                    round(1 - float(group["points"]) / n, 4),
                )
        self.persist_live(run_id, force=True)
        self.sql.exec("UPDATE runs SET status='done', finished_ms=? WHERE id=?", now_ms(), run_id)

    # HTTP ------------------------------------------------------------------------------------------------------

    async def brev_status(self) -> dict:
        current = time.monotonic()
        if not self.health or current - self.health_at > HEALTH_TTL_S:
            fast, deep = await asyncio.gather(
                get_ok(f"{self.env.BREV_FAST_URL}/models", self.env.BREV_API_KEY),
                get_ok(f"{self.env.BREV_DEEP_URL}/models", self.env.BREV_API_KEY),
            )
            self.health = {
                "instances_reported": int(self.env.BREV_INSTANCES_REPORTED),
                "endpoints": [{"name": "fast", "healthy": fast}, {"name": "deep", "healthy": deep}],
            }
            self.health_at = current
        return self.health

    def lanes_active(self, run: dict) -> int:
        return 0 if run["status"] != "running" else max(int(run["lanes"]) - int(run["lanes_done"]), 0)

    async def fetch(self, request):
        path = urlparse(str(request.url)).path.rstrip("/")
        method = str(request.method)
        if path == "/corpus" and method == "GET":
            return await self.corpus()
        if path == "/models" and method == "GET":
            return await self.models()
        if path == "/lessons" and method == "GET":
            return json_response(self.lessons())
        if path == "/runs" and method == "GET":
            rows = self.query(
                "SELECT id, created_at, total, lanes, claimed, status, error, check_total, check_done FROM runs ORDER BY created_at DESC LIMIT 50"
            )
            return json_response(rows)
        if path == "/runs" and method == "POST":
            return await self.start(request)

        match = re.fullmatch(r"/runs/([\w-]+)(/live|/rescore|/markers\.json|/markers\.csv|/cancel|/resume)?", path)
        if not match:
            return json_response({"error": "Not found"}, 404)
        run_id, action = match.group(1), match.group(2)
        run = self.run(run_id)
        if not run:
            return json_response({"error": "Not found"}, 404)

        if action == "/live" and method == "GET":
            live = self.live_for(run)
            return json_response(live_view(run, live, self.lanes_active(run), await self.brev_status(), self.elapsed(run)))
        if action is None and method == "GET":
            live = self.live_for(run)
            view = live_view(run, live, self.lanes_active(run), await self.brev_status(), self.elapsed(run))
            return json_response({k: v for k, v in view.items() if k not in ("recent", "timeline")} | {"config": json.loads(run["config"])})
        if action == "/rescore" and method == "POST":
            return await self.rescore(run_id, request)
        if action == "/markers.json" and method == "GET":
            return json_response(self.markers(run_id))
        if action == "/markers.csv" and method == "GET":
            return Response(
                markers_csv(self.markers(run_id)),
                headers={"content-type": "text/csv", "content-disposition": f'attachment; filename="{run_id}-markers.csv"'},
            )
        if action == "/cancel" and method == "POST":
            cancelled = run["status"] in ("running", "checking")
            if cancelled:
                self.sql.exec("UPDATE runs SET status='cancelled', finished_ms=? WHERE id=?", now_ms(), run_id)
                if run_id in self.live_cache:
                    self.persist_live(run_id, force=True)
                await self.ctx.storage.deleteAlarm()
            return json_response({"cancelled": cancelled})
        if action == "/resume" and method == "POST":
            return await self.resume(run)
        return json_response({"error": "Not found"}, 404)

    def markers(self, run_id: str) -> list[dict]:
        return [json.loads(r["data"]) for r in self.query("SELECT data FROM markers WHERE run_id=? ORDER BY seq", run_id)]

    async def corpus(self):
        if self.corpus_cache and time.monotonic() - self.corpus_at < CORPUS_TTL_S:
            return json_response(self.corpus_cache)
        out = {"total": 0}
        for key in ("channel", "source", "family", "method", "label_quality"):
            rows = await d1_all(self.env, f"SELECT {key} AS name, COUNT(*) AS n FROM cases GROUP BY {key} ORDER BY n DESC")
            out[f"by_{key}"] = {row["name"]: int(row["n"]) for row in rows}
        out["total"] = sum(out["by_channel"].values())
        self.corpus_cache, self.corpus_at = out, time.monotonic()
        return json_response(out)

    async def models(self):
        brev = await self.brev_status()
        jev_ok = await get_ok(JEV_MODELS_URL, self.env.TYPESAFE_API_KEY)
        health = {entry["name"]: entry["healthy"] for entry in brev["endpoints"]}
        return json_response(
            [
                {
                    "id": model,
                    "kind": "jev" if model in JEV_MODELS else "baseline" if model == BASELINE else "nemotron",
                    "healthy": jev_ok if model in JEV_MODELS else True if model == BASELINE else health["fast" if model == "nemotron-fast" else "deep"],
                }
                for model in ALL_MODELS
            ]
        )

    async def start(self, request):
        running = self.active()
        if running:
            return json_response({"error": "A run is already in progress", "id": running["id"]}, 409)
        try:
            config = validate_run(json.loads(await request.text()))
        except (ValueError, TypeError, AttributeError) as error:
            return json_response({"error": str(error) or "Send a JSON object"}, 400)
        where, args = corpus_filter(config)
        counted = await d1_all(self.env, f"SELECT COUNT(*) AS n FROM cases WHERE {where}", *args)
        available = int(counted[0]["n"]) if counted else 0
        if not available:
            return json_response({"error": "No corpus cases match that selection"}, 400)
        moment = datetime.now(UTC)
        run_id = "run-" + moment.strftime("%Y%m%d%H%M%S%f")[:17]
        total = min(config["limit"], available)
        lanes = min(config["lanes"], total)
        config["lanes"] = lanes
        self.sql.exec(
            "INSERT INTO runs (id, created_at, started_ms, config, total, lanes, status) VALUES (?,?,?,?,?,?,'running')",
            run_id,
            moment.isoformat(),
            now_ms(),
            safe_json(config),
            total,
            lanes,
        )
        await self.launch_lanes(run_id, config, lanes)
        await self.ctx.storage.setAlarm(now_ms() + 30000)
        return json_response({"id": run_id, "total": total, "lanes": lanes, "available": available}, 201)

    async def launch_lanes(self, run_id: str, config: dict, lanes: int) -> None:
        run = {"id": run_id, "models": config["models"], "lanes": lanes, "window_turns": config["window_turns"]}

        async def launch(index: int):
            stub = self.env.LANE.getByName(f"{run_id}:{index}")
            await stub.begin(safe_json({"run": run, "lane": index}))

        await asyncio.gather(*(launch(i) for i in range(lanes)))

    async def resume(self, run: dict):
        if run["status"] != "failed" or "Auto-paused" not in (run["error"] or ""):
            return json_response({"error": "Only an auto-paused run can resume"}, 409)
        if self.active():
            return json_response({"error": "A run is already in progress"}, 409)
        config = json.loads(run["config"])
        live = self.live_for(run)
        live["rate_streak"] = 0
        self.sql.exec("UPDATE runs SET status='running', error='', finished_ms=0, lanes_done=0, last_report_ms=? WHERE id=?", now_ms(), run["id"])
        await self.launch_lanes(run["id"], config, int(run["lanes"]))
        await self.ctx.storage.setAlarm(now_ms() + 30000)
        return json_response({"resumed": True})

    async def rescore(self, run_id: str, request):
        try:
            dangerous, uncertain, hard = rescore_params(json.loads(await request.text()))
        except (ValueError, TypeError, AttributeError) as error:
            return json_response({"error": str(error) or "Send a JSON object"}, 400)

        def grouped(key: str) -> list[dict]:
            return self.query(
                f"SELECT {key}, scam, {RESCORE_TIER_SQL} AS tier, COUNT(*) AS n,"
                " SUM(predicted_method=method) AS method_ok, SUM(predicted_method!='') AS method_seen"
                f" FROM results WHERE run_id=? AND weak=0 AND scam>=0 GROUP BY {key}, scam, tier",
                dangerous,
                hard,
                uncertain,
                run_id,
            )

        families = {r["method"]: r["family"] for r in self.query("SELECT DISTINCT method, family FROM results WHERE run_id=?", run_id)}
        by_method = [{**item, "family": families.get(item["method"], "unknown")} for item in rescored_rows(grouped("method"), "method")]
        return json_response(
            {
                "thresholds": {"dangerous_threshold": dangerous, "uncertain_threshold": uncertain, "require_hard_flag": bool(hard)},
                "by_method": by_method,
                "by_model": rescored_rows(grouped("model"), "model"),
            }
        )

    def lessons(self) -> dict:
        runs = [r["run_id"] for r in self.query("SELECT DISTINCT run_id FROM failure_log ORDER BY ts DESC LIMIT 5")]
        repeat = []
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
                {"marker": key[0], "method": key[1], "outcome": key[2], "count": 0, "improvement": marker["improvement"], "feedback": marker["feedback"]},
            )
            entry["count"] += 1
        return {
            "runs_logged": len(runs),
            "repeat_failures": repeat,
            "lessons": sorted(counts.values(), key=lambda x: -x["count"])[:100],
        }


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        header = str(request.headers.get("authorization") or "")
        given = header.removeprefix("Bearer ")
        digest = hashlib.sha256(given.encode()).hexdigest()
        if not given or not hmac.compare_digest(digest, str(self.env.ADMIN_PASSWORD_HASH)):
            return json_response({"error": "Unauthorized"}, 401)
        stub = self.env.RUNNER.getByName("coordinator-v2")
        return await stub.fetch(request.js_object)
