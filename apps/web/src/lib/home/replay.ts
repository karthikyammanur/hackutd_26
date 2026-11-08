import type { Decision, LiveState, Marker, MethodRow, StepStat } from "@/lib/simulate/parse";
import { RUN, RUN_MODEL } from "./stats";

/**
 * Plays the frozen run back through the architecture figure, sped up. The tallies are the run's
 * real ones: only the order the conversations finish in is reconstructed, because the summary keeps
 * totals and not a sequence. A fixed seed means every replay looks the same.
 */

const STARTING_S = 1;
const REPLAY_S = 11;
const REVIEW_S = 3;
export const REPLAY_DURATION_S = STARTING_S + REPLAY_S + REVIEW_S;

const LEDGER_SIZE = 40;
const SEED = 20261108;
const OUTCOME_KEYS = ["caught", "soft_miss", "missed", "clear", "soft_false_alarm", "false_alarm", "no_verdict"];

const TIER_OF: Record<string, string> = {
  caught: "dangerous",
  soft_miss: "uncertain",
  missed: "safe",
  clear: "safe",
  soft_false_alarm: "uncertain",
  false_alarm: "dangerous",
};

const KIND_OF: Record<string, "right" | "soft" | "wrong" | "noVerdict"> = {
  caught: "right",
  clear: "right",
  soft_miss: "soft",
  soft_false_alarm: "soft",
  missed: "wrong",
  false_alarm: "wrong",
  no_verdict: "noVerdict",
};

interface ReplayCase {
  row: MethodRow | null;
  outcome: string;
}

function shuffled<T>(items: T[], seed: number): T[] {
  const result = [...items];
  let state = seed;
  const next = () => {
    state = (state + 0x6d2b79f5) | 0;
    let mixed = Math.imul(state ^ (state >>> 15), 1 | state);
    mixed = (mixed + Math.imul(mixed ^ (mixed >>> 7), 61 | mixed)) ^ mixed;
    return ((mixed ^ (mixed >>> 14)) >>> 0) / 4294967296;
  };
  for (let index = result.length - 1; index > 0; index--) {
    const pick = Math.floor(next() * (index + 1));
    [result[index], result[pick]] = [result[pick], result[index]];
  }
  return result;
}

const SOURCE_ROWS = RUN.byMethod ?? [];

/** Conversations with inferred labels are caught and logged, but stay out of the score. */
const CASES: ReplayCase[] = shuffled(
  [
    ...SOURCE_ROWS.flatMap((row) =>
      OUTCOME_KEYS.flatMap((outcome) => Array.from({ length: row.counts[outcome] ?? 0 }, (): ReplayCase => ({ row, outcome }))),
    ),
    ...Array.from({ length: RUN.weakLabels?.n ?? 0 }, (): ReplayCase => ({ row: null, outcome: "caught" })),
  ],
  SEED,
);

const TOTAL = CASES.length;

/** One stand-in per failure the review marked. The figure only shows how many there are. */
const MARKERS: Marker[] = Array.from({ length: 30 }, (_, index) => ({
  id: `replay-${index}`,
  model: RUN_MODEL,
  type: null,
  outcome: null,
  marker: null,
  feedback: null,
  improvement: null,
}));

function emptyRow(row: MethodRow): MethodRow {
  return { ...row, n: 0, right: 0, soft: 0, wrong: 0, noVerdict: 0, counts: {}, score: null };
}

function tallyUpTo(processed: number) {
  const rows = new Map<string, MethodRow>();
  let scored = 0;
  let points = 0;
  let weak = 0;
  for (const { row, outcome } of CASES.slice(0, processed)) {
    if (!row) {
      weak += 1;
      continue;
    }
    const entry = rows.get(row.method) ?? emptyRow(row);
    const kind = KIND_OF[outcome];
    entry.n += 1;
    entry[kind] += 1;
    entry.counts[outcome] = (entry.counts[outcome] ?? 0) + 1;
    entry.score = (entry.right + entry.soft / 2) / entry.n;
    rows.set(row.method, entry);
    scored += 1;
    points += kind === "right" ? 1 : kind === "soft" ? 0.5 : 0;
  }
  return { byMethod: [...rows.values()], score: scored ? points / scored : null, weak };
}

function decisionAt(index: number): Decision {
  const { row, outcome } = CASES[index];
  return {
    key: `replay-${index}`,
    caseId: `case ${index + 1}`,
    channel: null,
    method: row?.method ?? "inferred_label",
    predictedMethod: null,
    tier: TIER_OF[outcome] ?? null,
    outcome,
    model: RUN_MODEL,
    flags: [],
    ms: null,
  };
}

export interface ReplayFrame {
  live: LiveState;
  seen: Decision[];
  byMethod: MethodRow[];
  score: number | null;
  active: string[];
  markers: Marker[] | null;
  lessons: null;
}

const clamp = (value: number) => Math.min(1, Math.max(0, value));

/** The figure's input `elapsed` seconds into the replay. Pure, so scrubbing or re-rendering can't drift. */
export function frameAt(elapsed: number): ReplayFrame {
  const replayed = clamp((elapsed - STARTING_S) / REPLAY_S);
  const reviewed = clamp((elapsed - STARTING_S - REPLAY_S) / REVIEW_S);
  const processed = Math.round(replayed * TOTAL);
  const status = reviewed >= 1 ? "done" : replayed >= 1 ? "checking" : "running";
  const { byMethod, score, weak } = tallyUpTo(processed);

  const steps: StepStat[] = RUN.steps.map((step) => {
    const share = step.name === "check" ? reviewed : replayed;
    return { ...step, count: step.count === null ? null : Math.round(step.count * share) };
  });
  const frames = steps.find((step) => step.name === "jev")?.count ?? null;
  const elapsedS = (RUN.elapsedS ?? 0) * (replayed * 0.9 + reviewed * 0.1);

  const seen: Decision[] = [];
  for (let index = processed - 1; index >= 0 && seen.length < LEDGER_SIZE; index--) seen.push(decisionAt(index));

  return {
    live: {
      ...RUN,
      status,
      elapsedS,
      processed,
      total: TOTAL,
      lanesActive: status === "running" ? RUN.lanesConfigured : 0,
      steps,
      byMethod,
      byModel: null,
      recent: seen,
      timeline: [{ t: elapsedS, processed, decisions: frames, score }],
      weakLabels: weak ? { n: weak, score: 1 } : null,
    },
    seen,
    byMethod,
    score,
    active: status === "running" ? ["frames", "agent", "jev", "score"] : status === "checking" ? ["check"] : [],
    markers: status === "done" ? MARKERS : null,
    lessons: null,
  };
}

export const FINAL_FRAME = frameAt(REPLAY_DURATION_S);
