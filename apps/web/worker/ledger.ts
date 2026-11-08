/** Daily run budget and run ownership. The rules live here so they can be tested without Cloudflare. */

export const DAILY_RUNS = 20;
export const DAILY_CASES = 20000;

export interface Usage {
  runs: number;
  cases: number;
}

export type Reservation = { ok: true; day: string } | { ok: false; message: string };

export interface Ledger {
  reserve(cases: number): Promise<Reservation>;
  release(day: string, cases: number): Promise<void>;
  setOwner(runId: string, owner: string): Promise<void>;
  ownerOf(runId: string): Promise<string | null>;
}

export const utcDay = (now: Date) => now.toISOString().slice(0, 10);

/** Returns why a run can't start today, or null if it fits. */
export function budgetProblem(usage: Usage, cases: number): string | null {
  if (usage.runs >= DAILY_RUNS) {
    return `Daily limit reached: this site has started ${usage.runs} of ${DAILY_RUNS} runs today. It resets at midnight UTC.`;
  }
  if (usage.cases + cases > DAILY_CASES) {
    const left = Math.max(0, DAILY_CASES - usage.cases);
    return `Daily limit reached: ${left.toLocaleString("en-US")} of ${DAILY_CASES.toLocaleString("en-US")} cases are left today, and this run asks for ${cases.toLocaleString("en-US")}. It resets at midnight UTC.`;
  }
  return null;
}
