import { DurableObject } from "cloudflare:workers";
import { budgetProblem, utcDay, type Reservation } from "./ledger";

const OWNER_RETENTION_MS = 30 * 24 * 60 * 60 * 1000;

/** One instance serializes every reservation, so concurrent requests can't overspend the budget. */
export class ProxyLedger extends DurableObject {
  private sql: SqlStorage;

  constructor(ctx: DurableObjectState, env: unknown) {
    super(ctx, env as never);
    this.sql = ctx.storage.sql;
    this.sql.exec("CREATE TABLE IF NOT EXISTS usage (day TEXT PRIMARY KEY, runs INTEGER NOT NULL, cases INTEGER NOT NULL)");
    this.sql.exec("CREATE TABLE IF NOT EXISTS owners (run_id TEXT PRIMARY KEY, owner TEXT NOT NULL, created_at INTEGER NOT NULL)");
  }

  reserve(cases: number): Reservation {
    const day = utcDay(new Date());
    const row = this.sql.exec("SELECT runs, cases FROM usage WHERE day=?", day).toArray()[0];
    const message = budgetProblem({ runs: Number(row?.runs ?? 0), cases: Number(row?.cases ?? 0) }, cases);
    if (message) return { ok: false, message };
    this.sql.exec(
      "INSERT INTO usage (day, runs, cases) VALUES (?, 1, ?) ON CONFLICT(day) DO UPDATE SET runs = runs + 1, cases = cases + excluded.cases",
      day,
      cases,
    );
    return { ok: true, day };
  }

  /** Gives a reservation back when the backend didn't start the run. */
  release(day: string, cases: number): void {
    this.sql.exec("UPDATE usage SET runs = MAX(runs - 1, 0), cases = MAX(cases - ?, 0) WHERE day=?", cases, day);
  }

  setOwner(runId: string, owner: string): void {
    const now = Date.now();
    this.sql.exec("DELETE FROM owners WHERE created_at < ?", now - OWNER_RETENTION_MS);
    this.sql.exec("INSERT OR REPLACE INTO owners (run_id, owner, created_at) VALUES (?, ?, ?)", runId, owner, now);
  }

  ownerOf(runId: string): string | null {
    const row = this.sql.exec("SELECT owner FROM owners WHERE run_id=?", runId).toArray()[0];
    return row ? String(row.owner) : null;
  }
}
