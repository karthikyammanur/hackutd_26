import { formatPercent } from "@/lib/console/format";
import { humanize } from "@/lib/simulate/labels";
import { TERMINAL, type Decision, type Lessons, type LiveState, type Marker, type MethodRow, type StepStat } from "@/lib/simulate/parse";

/**
 * Turns the run monitor into what the figure shows. Pure, and every number here comes from `/live`,
 * `/runs/<id>/markers.json` or `/lessons`. Nothing is estimated.
 */

export type Phase = "idle" | "starting" | "replay" | "review" | "done" | "stopped";
export type Light = "idle" | "active" | "done";
export type Tier = "safe" | "uncertain" | "dangerous" | null;
export type Result = "right" | "soft" | "wrong" | "none";
export type StationId = "deck" | "cut" | "note" | "jev" | "peak" | "log" | "board" | "deep" | "lessons" | "checker";
export type WireId =
  | "deck>cut" | "cut>rack" | "loop" | "rack>peak" | "peak>log" | "log>board" | "labels" | "board>deep" | "deep>lessons" | "lessons>checker";

export const TIER_NAMES: Record<Exclude<Tier, null>, string> = { safe: "Safe", uncertain: "Uncertain", dangerous: "Dangerous" };

const CORE_STEPS = new Set(["frames", "agent", "score", "check"]);
const STEP_NAMES: Record<string, string> = {
  jev: "Jev",
  guard: "Safe Signal Guard",
  baseline: "Baseline rules",
  nemotron_classifier: "Nemotron classifier",
};

export const stepName = (name: string) => STEP_NAMES[name] ?? humanize(name);
const count = (value: number) => value.toLocaleString();
const plural = (value: number, word: string, many = `${word}s`) => `${count(value)} ${value === 1 ? word : many}`;

export function phaseOf(live: LiveState | null): Phase {
  const status = live?.status ?? null;
  if (status === null || live === null) return "idle";
  if (status === "done") return "done";
  if (TERMINAL.has(status)) return "stopped";
  if (status === "checking") return "review";
  if (status !== "running") return "idle";
  const moved = (live.processed ?? 0) > 0 || live.steps.some((step) => (step.count ?? 0) > 0);
  return moved ? "replay" : "starting";
}

/* The decision ledger ------------------------------------------------------------------------- */

/** `/live` keeps the newest 40 results, so the tray has one slot for each. */
export const LEDGER_SLOTS = 40;

export interface LedgerTile {
  key: string;
  label: string;
  tier: Tier;
  result: Result;
  batch: number;
}

export interface Ledger {
  slots: (LedgerTile | null)[];
  written: number;
  batch: number;
  newest: string | null;
}

export const EMPTY_LEDGER: Ledger = { slots: Array.from({ length: LEDGER_SLOTS }, () => null), written: 0, batch: 0, newest: null };

const TIERS = new Set(["safe", "uncertain", "dangerous"]);
const RIGHT = new Set(["caught", "clear"]);
const SOFT = new Set(["soft_miss", "soft_false_alarm"]);
const WRONG = new Set(["missed", "false_alarm"]);

export function resultOf(outcome: string | null): Result {
  if (outcome === null) return "none";
  if (RIGHT.has(outcome)) return "right";
  if (SOFT.has(outcome)) return "soft";
  return WRONG.has(outcome) ? "wrong" : "none";
}

const tierOf = (decision: Decision): Tier => (decision.tier && TIERS.has(decision.tier) ? (decision.tier as Tier) : null);

const tileLabel = (decision: Decision, tier: Tier) =>
  `${decision.caseId}${decision.model ? `, ${decision.model}` : ""}: ${tier ? TIER_NAMES[tier] : "No answer"}${decision.outcome ? `, ${humanize(decision.outcome).toLowerCase()}` : ""}`;

/** Writes decisions seen since the last call into the tray, oldest first, so tiles keep their slots until they're overwritten. */
export function advanceLedger(ledger: Ledger, seen: Decision[]): Ledger {
  if (!seen.length || seen[0].key === ledger.newest) return ledger;
  const known = ledger.newest === null ? -1 : seen.findIndex((decision) => decision.key === ledger.newest);
  const fresh = (known === -1 ? seen : seen.slice(0, known)).slice().reverse();
  const slots = [...ledger.slots];
  const batch = ledger.batch + 1;
  let written = ledger.written;
  for (const decision of fresh) {
    const tier = tierOf(decision);
    slots[written % LEDGER_SLOTS] = { key: decision.key, label: tileLabel(decision, tier), tier, result: resultOf(decision.outcome), batch };
    written += 1;
  }
  return { slots, written, batch, newest: seen[0].key };
}

/* What each part of the figure says ----------------------------------------------------------- */

export interface StationView {
  name: string;
  status: string;
  state: Light;
}

export interface BoardShare {
  right: number;
  soft: number;
  wrong: number;
  none: number;
  n: number;
}

export interface FigureInput {
  live: LiveState | null;
  active: string[];
  seen: Decision[];
  markers: Marker[] | null;
  lessons: Lessons | null;
  byMethod: MethodRow[] | null;
  score: number | null;
  paused: boolean;
}

export interface FigureView {
  phase: Phase;
  headline: string;
  detail: string;
  /** Share of calls replayed, 0 to 1. */
  progress: number | null;
  /** Lanes the backend says exist and how many it says are running. */
  lanes: { configured: number | null; running: number | null };
  latestTier: Tier;
  board: BoardShare | null;
  stations: Record<StationId, StationView>;
  wires: Record<WireId, Light>;
  now: { replay: boolean; log: boolean; after: boolean };
  moving: boolean;
  summary: string;
}

function stepOf(live: LiveState | null, name: string): StepStat | null {
  return live?.steps.find((step) => step.name === name) ?? null;
}

const quantity = (step: StepStat | null) => step?.count ?? null;
const said = (value: number | null, words: (n: number) => string, fallback: string) => (value === null ? fallback : words(value));

function decisionsLogged(live: LiveState | null): number | null {
  const last = live?.timeline.at(-1);
  return last?.decisions ?? null;
}

function resultsLogged(live: LiveState | null, byMethod: MethodRow[] | null, seen: Decision[]): number {
  const tallied = (byMethod ?? live?.byMethod ?? []).reduce((sum, row) => sum + row.n, 0) + (live?.weakLabels?.n ?? 0);
  return Math.max(tallied, seen.length);
}

function boardShare(rows: MethodRow[] | null): BoardShare | null {
  if (!rows?.length) return null;
  const total = rows.reduce(
    (sum, row) => ({
      right: sum.right + row.right,
      soft: sum.soft + row.soft,
      wrong: sum.wrong + row.wrong,
      none: sum.none + row.noVerdict,
      n: sum.n + row.n,
    }),
    { right: 0, soft: 0, wrong: 0, none: 0, n: 0 },
  );
  return total.n ? total : null;
}

function classifiers(live: LiveState | null) {
  const steps = (live?.steps ?? []).filter((step) => !CORE_STEPS.has(step.name));
  const primary = steps.find((step) => step.name === "jev" && (step.count ?? 0) > 0) ?? steps.find((step) => (step.count ?? 0) > 0) ?? null;
  return { primary, others: primary ? steps.filter((step) => step !== primary && (step.count ?? 0) > 0).length : 0 };
}

const lit = (on: boolean, phase: Phase, finished: boolean): Light => {
  if (on) return "active";
  return finished && phase !== "idle" ? "done" : "idle";
};

function words(phase: Phase, input: FigureInput, frameDecisions: number | null, active: number | null, configured: number | null) {
  const { live, score } = input;
  const processed = live?.processed ?? null;
  const total = live?.total ?? null;
  const callsLine = processed !== null && total !== null ? `${count(processed)} of ${count(total)} calls finished` : null;
  const lanesLine = active !== null && configured !== null ? `${active} of ${configured} lanes running` : null;

  switch (phase) {
    case "idle":
      return { headline: "Nothing is running", detail: "Start a simulation and the lanes on this bench light up as it works." };
    case "starting":
      return { headline: lanesLine ?? "Starting lanes", detail: "Lanes are up and claiming calls. No call has finished yet." };
    case "replay":
      return {
        headline: lanesLine ?? "Replaying calls",
        detail: [callsLine, frameDecisions === null ? null : `${plural(frameDecisions, "frame decision")} logged`].filter(Boolean).join(", "),
      };
    case "review":
      return {
        headline: "Reviewing failures",
        detail: `Every call is replayed. Nemotron deep has reviewed ${plural(quantity(stepOf(live, "check")) ?? 0, "failure")} so far.`,
      };
    case "done":
      return {
        headline: "Run finished",
        detail: [
          callsLine,
          live?.elapsedS != null ? `${live.elapsedS.toFixed(1)} s` : null,
          score !== null ? `score ${formatPercent(score)}` : null,
        ]
          .filter(Boolean)
          .join(", "),
      };
    case "stopped":
      return {
        headline: live?.status === "cancelled" ? "Run cancelled" : "Run stopped",
        detail: live?.error ?? (callsLine ? `Stopped with ${callsLine}.` : "No results were recorded."),
      };
  }
}

export function figureView(input: FigureInput): FigureView {
  const { live, active, seen, markers, lessons, byMethod, score, paused } = input;
  const phase = phaseOf(live);
  const replaying = phase === "replay" && !paused;
  const reviewing = phase === "review" && !paused;
  const running = phase === "replay" || phase === "starting";
  const finished = phase === "done" || phase === "stopped";
  const has = (step: string) => active.includes(step);

  const configured = live?.lanesConfigured ?? null;
  const reported = live?.lanesActive ?? null;
  const running_ = running ? reported : phase === "idle" ? null : 0;
  const frameDecisions = decisionsLogged(live);
  const { headline, detail } = words(phase, input, frameDecisions, running_, configured);

  const frames = stepOf(live, "frames");
  const agent = stepOf(live, "agent");
  const check = stepOf(live, "check");
  const { primary, others } = classifiers(live);
  const latestTier = seen[0] ? tierOf(seen[0]) : null;
  const results = resultsLogged(live, byMethod, seen);
  const shown = Math.min(seen.length, LEDGER_SLOTS);
  const proposed = lessons?.lessons.filter((lesson) => lesson.status === "proposed").length ?? null;

  const isIdle = phase === "idle";
  const stations: Record<StationId, StationView> = {
    deck: {
      name: "Fake calls",
      status: said(live?.total ?? null, (n) => `${count(n)} with known answers`, "Labeled, with known answers"),
      state: lit(replaying, phase, finished),
    },
    cut: {
      name: "Microframes",
      status: isIdle ? "A new frame on each caller turn" : said(quantity(frames), (n) => `${plural(n, "call")} cut`, "Not reported"),
      state: lit(replaying && has("frames"), phase, finished),
    },
    note: {
      name: "Nemotron fast",
      status: isIdle ? "Keeps a short note, never scores" : said(quantity(agent), (n) => plural(n, "note"), "Not reported"),
      state: lit(replaying && has("agent"), phase, finished),
    },
    jev: {
      name: primary && primary.name !== "jev" ? stepName(primary.name) : "Jev",
      status: isIdle
        ? "Picks the tier, answers 12 red-flag questions"
        : primary
          ? `${plural(primary.count ?? 0, "frame")} answered${others ? `, ${others} more ${others === 1 ? "model" : "models"}` : ""}`
          : "0 frames answered",
      state: lit(replaying && Boolean(primary && has(primary.name)), phase, finished),
    },
    peak: {
      name: "Highest tier wins",
      status: latestTier ? `Latest call: ${TIER_NAMES[latestTier].toLowerCase()}` : "A call keeps its highest tier",
      state: lit(replaying, phase, finished),
    },
    log: {
      name: "Decision log",
      status: seen.length ? `${plural(results, "call result")}, newest ${shown} shown` : "Each tile is one finished call",
      state: lit(replaying && has("score"), phase, finished),
    },
    board: {
      name: "Scoreboard",
      status: isIdle ? "Built in code against the labels" : score === null ? "No scores yet" : phase === "replay" ? "So far, against the labels" : "Against the labels",
      state: lit(replaying, phase, finished),
    },
    deep: {
      name: "Nemotron deep",
      status: isIdle
        ? "Reviews the failures, writes markers"
        : phase === "starting" || phase === "replay"
          ? "Waits for the last call"
          : said(quantity(check), (n) => `${plural(n, "failure")} reviewed`, "Not reported"),
      state: reviewing ? "active" : (check?.count ?? 0) > 0 ? "done" : "idle",
    },
    lessons: {
      name: "Proposed lessons",
      status:
        markers === null && proposed === null
          ? "Written once a run is reviewed"
          : [markers ? plural(markers.length, "marker") : null, proposed === null ? null : `${plural(proposed, "lesson")} proposed`].filter(Boolean).join(", "),
      state: phase === "done" && (markers?.length ?? 0) > 0 ? "done" : "idle",
    },
    checker: { name: "Checking agent", status: "Its knowledge, on the Live page", state: "idle" },
  };

  const flowing = lit(replaying, phase, finished);
  const wires: Record<WireId, Light> = {
    "deck>cut": flowing,
    "cut>rack": flowing,
    loop: flowing,
    "rack>peak": flowing,
    "peak>log": flowing,
    "log>board": flowing,
    labels: flowing,
    "board>deep": reviewing ? "active" : finished && (check?.count ?? 0) > 0 ? "done" : "idle",
    "deep>lessons": reviewing ? "active" : finished && (markers?.length ?? 0) > 0 ? "done" : "idle",
    "lessons>checker": "idle",
  };

  const tally = boardShare(byMethod);
  const processed = live?.processed ?? null;
  const total = live?.total ?? null;
  const progress = processed !== null && total ? Math.min(1, processed / total) : null;

  return {
    phase,
    headline,
    detail,
    progress,
    lanes: { configured, running: running_ },
    latestTier,
    board: tally,
    stations,
    wires,
    now: { replay: running, log: running, after: phase === "review" || phase === "done" },
    moving: replaying || reviewing,
    summary: `${headline}. ${detail}`,
  };
}

/** Names the worker reports for steps beyond the core ones are shown as they come. */
export const STEP_LABELS: Record<string, string> = {
  frames: "Microframes",
  agent: "Nemotron fast",
  jev: "Jev",
  guard: "Safe Signal Guard",
  score: "Scoreboard",
  check: "Nemotron deep",
  baseline: "Baseline rules",
  nemotron_classifier: "Nemotron classifier",
};
