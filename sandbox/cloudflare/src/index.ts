// Safe Signal sandbox on Cloudflare. The Worker authenticates requests; one Durable Object owns all run state
// and works through calls using alarms, one call per alarm, so a run isn't limited by a single request's lifetime.
//
// Stored: scores, flags, ids. Never stored or returned: transcript text or agent notes (R8). Notes live in local
// variables for the length of one call, and review excerpts are rebuilt from the bundled sample in memory.
import { DurableObject } from "cloudflare:workers";
import { verifyPassword } from "./auth";
import { buildFrames, composeState, type Session } from "./frames";
import { classify } from "./jev";
import { updateNote, type NemotronConfig } from "./nemotron";
import { consistentFailures, failureBuckets, runReview, type Review } from "./review";
import { buildScoreboard, scoreCall, type CallRow, type FrameResult } from "./scoring";
import sampleJson from "./sample.json";

export interface Env {
  RUNNER: DurableObjectNamespace<Runner>;
  ADMIN_PASSWORD_HASH: string;
  TYPESAFE_API_KEY: string;
  NVIDIA_API_KEY: string;
  NEMOTRON_BASE_URL: string;
  NEMOTRON_FAST_MODEL: string;
  NEMOTRON_DEEP_MODEL: string;
  JEV_MODEL: string;
}

const SAMPLE = sampleJson as unknown as Record<string, Session[]>;
const MAX_PER_TYPE = Math.max(...Object.values(SAMPLE).map((group) => group.length));
const BY_ID = new Map(Object.values(SAMPLE).flat().map((session) => [session.session_id, session]));

function selectSessions(perType: number): Session[] {
  return Object.keys(SAMPLE)
    .sort()
    .flatMap((type) => SAMPLE[type].slice(0, perType));
}

function excerptFor(sessionId: string): string {
  const session = BY_ID.get(sessionId);
  if (!session) return "";
  const frames = buildFrames(session.events);
  const last = frames[frames.length - 1];
  return last ? composeState(session, last, "").slice(-900) : "";
}

export async function replayCall(
  session: Session,
  env: Pick<Env, "TYPESAFE_API_KEY" | "NVIDIA_API_KEY" | "NEMOTRON_BASE_URL" | "NEMOTRON_FAST_MODEL" | "JEV_MODEL">,
): Promise<FrameResult[]> {
  const config: NemotronConfig = { baseUrl: env.NEMOTRON_BASE_URL, apiKey: env.NVIDIA_API_KEY };
  const results: FrameResult[] = [];
  let note = "";
  for (const frame of buildFrames(session.events)) {
    let agentMs: number | null = null;
    let agentOk = true;
    const agentCalled = frame.scrolledOut.length > 0;
    if (agentCalled) {
      try {
        const updated = await updateNote(config, env.NEMOTRON_FAST_MODEL, note, frame.scrolledOut);
        note = updated.note;
        agentMs = updated.latencyMs;
      } catch {
        agentOk = false; // keep the previous note; the newest turns still reach Jev verbatim (R4)
      }
    }
    const state = composeState(session, frame, note);
    const result: FrameResult = {
      index: frame.index,
      t: frame.t,
      trigger: frame.trigger,
      tier: null,
      p_safe: null,
      p_uncertain: null,
      p_dangerous: null,
      flags: {},
      jev_ms: null,
      agent_ms: agentMs,
      input_tokens: 0,
      output_tokens: 0,
      agent_called: agentCalled,
      agent_ok: agentOk,
      delivered: false,
      error: null,
    };
    try {
      const answer = await classify(env.TYPESAFE_API_KEY, env.JEV_MODEL, state);
      result.tier = answer.tier;
      result.p_safe = answer.probabilities.safe ?? null;
      result.p_uncertain = answer.probabilities.uncertain ?? null;
      result.p_dangerous = answer.probabilities.dangerous ?? null;
      result.flags = answer.flags;
      result.jev_ms = answer.latencyMs;
      result.input_tokens = answer.inputTokens;
      result.output_tokens = answer.outputTokens;
      result.delivered = state.includes(frame.latest);
    } catch (error) {
      result.error = (error instanceof Error ? error.message : "failed").slice(0, 200);
    }
    results.push(result);
  }
  return results;
}

type Row = Record<string, SqlStorageValue>;

export class Runner extends DurableObject<Env> {
  private sql: SqlStorage;

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    this.sql = ctx.storage.sql;
    this.sql.exec(`
      CREATE TABLE IF NOT EXISTS runs (
        id TEXT PRIMARY KEY, created_at TEXT, per_type INTEGER, total INTEGER, cursor INTEGER DEFAULT 0,
        status TEXT, error TEXT, board TEXT, review TEXT);
      CREATE TABLE IF NOT EXISTS calls (
        run_id TEXT, seq INTEGER, session_id TEXT, row TEXT, PRIMARY KEY (run_id, seq));
      CREATE TABLE IF NOT EXISTS frames (
        run_id TEXT, session_id TEXT, idx INTEGER, jev_ms INTEGER, agent_ms INTEGER, data TEXT,
        PRIMARY KEY (run_id, session_id, idx));
      CREATE TABLE IF NOT EXISTS failure_log (run_id TEXT, ts TEXT, type TEXT, n INTEGER, error_rate REAL, outcomes TEXT);
      CREATE TABLE IF NOT EXISTS lessons (run_id TEXT, ts TEXT, status TEXT, data TEXT);
    `);
  }

  private active(): Row | undefined {
    return this.sql.exec("SELECT * FROM runs WHERE status IN ('running','reviewing') LIMIT 1").toArray()[0];
  }

  async start(perType: number): Promise<{ status: number; body: { id?: string; total?: number; error?: string } }> {
    const running = this.active();
    if (running) return { status: 409, body: { error: "A run is already in progress", id: String(running.id) } };
    const id = `run-${new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14)}`;
    const total = selectSessions(perType).length;
    this.sql.exec(
      "INSERT INTO runs (id, created_at, per_type, total, status) VALUES (?, ?, ?, ?, 'running')",
      id,
      new Date().toISOString(),
      perType,
      total,
    );
    await this.ctx.storage.setAlarm(Date.now() + 10);
    return { status: 201, body: { id, total } };
  }

  async cancel(id: string): Promise<boolean> {
    const changed = this.sql.exec(
      "UPDATE runs SET status='cancelled' WHERE id=? AND status IN ('running','reviewing')",
      id,
    ).rowsWritten;
    if (changed) await this.ctx.storage.deleteAlarm();
    return changed > 0;
  }

  async alarm(): Promise<void> {
    const run = this.active();
    if (!run) return;
    const id = String(run.id);
    if (run.status === "running") {
      const sessions = selectSessions(Number(run.per_type));
      const cursor = Number(run.cursor);
      if (cursor < sessions.length) {
        await this.processCall(id, cursor, sessions[cursor]);
        if (this.abortIfBroken(id, cursor + 1)) return;
        await this.ctx.storage.setAlarm(Date.now() + 25);
        return;
      }
      this.sql.exec("UPDATE runs SET status='reviewing' WHERE id=?", id);
      await this.ctx.storage.setAlarm(Date.now() + 25);
      return;
    }
    await this.finish(id);
  }

  private async processCall(id: string, seq: number, session: Session): Promise<void> {
    const frames = await replayCall(session, this.env);
    const row = scoreCall(session, frames);
    this.ctx.storage.transactionSync(() => {
      for (const frame of frames) {
        this.sql.exec(
          "INSERT OR REPLACE INTO frames (run_id, session_id, idx, jev_ms, agent_ms, data) VALUES (?, ?, ?, ?, ?, ?)",
          id,
          session.session_id,
          frame.index,
          frame.jev_ms,
          frame.agent_ms,
          JSON.stringify(frame),
        );
      }
      this.sql.exec(
        "INSERT OR REPLACE INTO calls (run_id, seq, session_id, row) VALUES (?, ?, ?, ?)",
        id,
        seq,
        session.session_id,
        JSON.stringify(row),
      );
      this.sql.exec("UPDATE runs SET cursor=? WHERE id=?", seq + 1, id);
    });
  }

  // If the first calls all got nothing from Jev, stop instead of spending the rest of the run on errors.
  private abortIfBroken(id: string, done: number): boolean {
    if (done !== 3) return false;
    const rows = this.rows(id);
    if (!rows.every((r) => r.outcome === "no_verdict")) return false;
    const sample = this.sql
      .exec("SELECT data FROM frames WHERE run_id=? LIMIT 1", id)
      .toArray()
      .map((r) => JSON.parse(String(r.data)).error)[0];
    this.sql.exec("UPDATE runs SET status='failed', error=? WHERE id=?", `Jev returned nothing: ${sample}`, id);
    return true;
  }

  private rows(id: string): CallRow[] {
    return this.sql
      .exec("SELECT row FROM calls WHERE run_id=? ORDER BY seq", id)
      .toArray()
      .map((r) => JSON.parse(String(r.row)) as CallRow);
  }

  private percentile(id: string, column: "jev_ms" | "agent_ms", q: number): number | null {
    const where = `run_id=? AND ${column} IS NOT NULL`;
    const count = Number(this.sql.exec(`SELECT COUNT(*) AS n FROM frames WHERE ${where}`, id).one().n);
    if (!count) return null;
    const offset = Math.min(count - 1, Math.round(q * (count - 1)));
    return Number(
      this.sql.exec(`SELECT ${column} AS v FROM frames WHERE ${where} ORDER BY ${column} LIMIT 1 OFFSET ?`, id, offset).one().v,
    );
  }

  private async finish(id: string): Promise<void> {
    const rows = this.rows(id);
    const board = buildScoreboard(rows, {
      jev_ms_p50: this.percentile(id, "jev_ms", 0.5),
      jev_ms_p95: this.percentile(id, "jev_ms", 0.95),
      agent_ms_p50: this.percentile(id, "agent_ms", 0.5),
      agent_ms_p95: this.percentile(id, "agent_ms", 0.95),
    });
    let review: Review;
    try {
      const config = { baseUrl: this.env.NEMOTRON_BASE_URL, apiKey: this.env.NVIDIA_API_KEY };
      review = await runReview(config, this.env.NEMOTRON_DEEP_MODEL, failureBuckets(rows, excerptFor));
    } catch (error) {
      const name = error instanceof Error ? error.message.slice(0, 120) : "error";
      review = { overall: `The review agent failed (${name}). The scoreboard is still valid.`, recommendations: [] };
    }
    const now = new Date().toISOString();
    this.ctx.storage.transactionSync(() => {
      for (const item of board.by_type) {
        this.sql.exec(
          "INSERT INTO failure_log (run_id, ts, type, n, error_rate, outcomes) VALUES (?, ?, ?, ?, ?, ?)",
          id,
          now,
          item.type,
          item.n,
          item.error_rate ?? 0,
          JSON.stringify(item.outcomes),
        );
      }
      for (const rec of review.recommendations) {
        this.sql.exec("INSERT INTO lessons (run_id, ts, status, data) VALUES (?, ?, 'proposed', ?)", id, now, JSON.stringify(rec));
      }
      this.sql.exec(
        "UPDATE runs SET status='done', board=?, review=? WHERE id=?",
        JSON.stringify(board),
        JSON.stringify(review),
        id,
      );
    });
  }

  list(): unknown[] {
    return this.sql
      .exec("SELECT id, created_at, per_type, total, cursor, status, error FROM runs ORDER BY created_at DESC LIMIT 50")
      .toArray();
  }

  get(id: string): unknown | null {
    const run = this.sql.exec("SELECT * FROM runs WHERE id=?", id).toArray()[0];
    if (!run) return null;
    return {
      ...run,
      board: run.board ? JSON.parse(String(run.board)) : null,
      review: run.review ? JSON.parse(String(run.review)) : null,
      calls: this.rows(id),
    };
  }

  insights(): unknown {
    const history = this.sql.exec("SELECT run_id, type, error_rate FROM failure_log ORDER BY ts").toArray() as unknown as {
      run_id: string;
      type: string;
      error_rate: number;
    }[];
    const order = [...new Set(history.map((h) => h.run_id))];
    const lessons = this.sql
      .exec("SELECT run_id, ts, status, data FROM lessons ORDER BY ts DESC LIMIT 100")
      .toArray()
      .map((r) => ({ run_id: r.run_id, ts: r.ts, status: r.status, ...JSON.parse(String(r.data)) }));
    return { runs_logged: order.length, consistent_failures: consistentFailures(history, order), lessons };
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const json = (body: unknown, status = 200) =>
      new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

    const given = request.headers.get("authorization")?.replace(/^Bearer /, "") ?? "";
    if (!(await verifyPassword(given, env.ADMIN_PASSWORD_HASH))) return json({ error: "Unauthorized" }, 401);

    const runner = env.RUNNER.get(env.RUNNER.idFromName("main"));
    const path = new URL(request.url).pathname.replace(/\/$/, "");
    const match = path.match(/^\/api\/runs\/([\w-]+)(\/cancel)?$/);

    if (path === "/api/runs" && request.method === "GET") return json(await runner.list());
    if (path === "/api/runs" && request.method === "POST") {
      const body = (await request.json().catch(() => ({}))) as { perType?: unknown };
      const perType = Number(body.perType);
      if (!Number.isInteger(perType) || perType < 1 || perType > MAX_PER_TYPE) {
        return json({ error: `perType must be a whole number from 1 to ${MAX_PER_TYPE}` }, 400);
      }
      const result = await runner.start(perType);
      return json(result.body, result.status);
    }
    if (path === "/api/insights" && request.method === "GET") return json(await runner.insights());
    if (match && !match[2] && request.method === "GET") {
      const run = await runner.get(match[1]);
      return run ? json(run) : json({ error: "Not found" }, 404);
    }
    if (match?.[2] && request.method === "POST") return json({ cancelled: await runner.cancel(match[1]) });
    return json({ error: "Not found" }, 404);
  },
} satisfies ExportedHandler<Env>;
