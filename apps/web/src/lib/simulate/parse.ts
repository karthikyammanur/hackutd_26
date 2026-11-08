import { humanize } from "./labels";

/** Reads sandbox API responses. A missing or malformed field becomes null, so the UI can say it's unavailable. */

export const STEP_NAMES = ["frames", "agent", "jev", "score", "check"] as const;
export const TERMINAL = new Set(["done", "failed", "cancelled"]);

export interface StepStat {
  name: string;
  count: number | null;
  p50: number | null;
  p95: number | null;
  errors: number | null;
}

export interface MethodRow {
  method: string;
  family: string;
  n: number;
  right: number;
  soft: number;
  wrong: number;
  noVerdict: number;
  counts: Record<string, number>;
  score: number | null;
  methodAccuracy: number | null;
}

export interface ModelRow {
  model: string;
  n: number | null;
  score: number | null;
  catchRate: number | null;
  falseAlarmRate: number | null;
  p50: number | null;
}

export interface Decision {
  key: string;
  caseId: string;
  channel: string | null;
  method: string;
  predictedMethod: string | null;
  tier: string | null;
  outcome: string | null;
  model: string | null;
  flags: string[];
  ms: number | null;
}

export interface TimelinePoint {
  t: number;
  processed: number | null;
  decisions: number | null;
  score: number | null;
}

export interface Endpoint {
  name: string;
  healthy: boolean | null;
}

export interface LiveState {
  id: string | null;
  status: string | null;
  /** Why a run stopped, from the coordinator. Only set on failed runs. */
  error: string | null;
  elapsedS: number | null;
  total: number | null;
  processed: number | null;
  decisionsPerS: number | null;
  framesPerS: number | null;
  lanesConfigured: number | null;
  lanesActive: number | null;
  brevInstances: number | null;
  endpoints: Endpoint[] | null;
  steps: StepStat[];
  byMethod: MethodRow[] | null;
  byModel: ModelRow[] | null;
  recent: Decision[];
  timeline: TimelinePoint[];
  weakLabels: { n: number; score: number | null } | null;
}

type Raw = Record<string, unknown>;

const object = (value: unknown): Raw | null =>
  typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Raw) : null;
const number = (value: unknown): number | null => (typeof value === "number" && Number.isFinite(value) ? value : null);
const text = (value: unknown): string | null => (typeof value === "string" && value ? value : null);
const rows = (value: unknown): Raw[] => (Array.isArray(value) ? value.map(object).filter((row) => row !== null) : []);
const optionalRows = (value: unknown): Raw[] | null => (Array.isArray(value) ? rows(value) : null);
const count = (row: Raw, key: string) => number(row[key]) ?? 0;

function parseMethod(row: Raw): MethodRow | null {
  const method = text(row.method);
  if (!method) return null;
  const right = count(row, "caught") + count(row, "clear");
  const soft = count(row, "soft_miss") + count(row, "soft_false_alarm");
  const wrong = count(row, "missed") + count(row, "false_alarm");
  const noVerdict = count(row, "no_verdict");
  const counts = Object.fromEntries(
    ["caught", "clear", "soft_miss", "soft_false_alarm", "missed", "false_alarm", "no_verdict"].map((key) => [key, count(row, key)]),
  );
  return {
    method,
    family: text(row.family) ?? "unknown",
    n: number(row.n) ?? right + soft + wrong + noVerdict,
    right,
    soft,
    wrong,
    noVerdict,
    counts,
    score: number(row.score),
    methodAccuracy: number(row.method_accuracy),
  };
}

export function parseMethods(value: unknown): MethodRow[] | null {
  const raw = optionalRows(value);
  return raw && raw.map(parseMethod).filter((row) => row !== null);
}

export function parseModels(value: unknown): ModelRow[] | null {
  const raw = optionalRows(value);
  if (!raw) return null;
  return raw.flatMap((row) => {
    const model = text(row.model);
    if (!model) return [];
    return [
      {
        model,
        n: number(row.n),
        score: number(row.score),
        catchRate: number(row.catch_rate),
        falseAlarmRate: number(row.false_alarm_rate),
        p50: number(row.p50_ms),
      },
    ];
  });
}

function parseDecision(row: Raw): Decision | null {
  const caseId = text(row.case_id);
  if (!caseId) return null;
  const model = text(row.model);
  return {
    key: `${caseId}:${model ?? ""}`,
    caseId,
    channel: text(row.channel),
    method: text(row.method) ?? "unknown",
    predictedMethod: text(row.predicted_method),
    tier: text(row.tier),
    outcome: text(row.outcome),
    model,
    flags: Array.isArray(row.flags) ? row.flags.filter((flag): flag is string => typeof flag === "string") : [],
    ms: number(row.ms),
  };
}

function parseWeak(value: unknown): LiveState["weakLabels"] {
  const raw = object(value);
  const n = raw && number(raw.n);
  return raw && n ? { n, score: number(raw.score) } : null;
}

export function parseLive(value: unknown): LiveState {
  const raw = object(value) ?? {};
  const lanes = object(raw.lanes);
  const brev = object(raw.brev);
  const stepRows = rows(raw.steps);
  return {
    id: text(raw.id),
    status: text(raw.status),
    error: text(raw.error),
    elapsedS: number(raw.elapsed_s),
    total: number(raw.total),
    processed: number(raw.processed),
    decisionsPerS: number(raw.decisions_per_s),
    framesPerS: number(raw.frames_per_s),
    lanesConfigured: lanes && number(lanes.configured),
    lanesActive: lanes && number(lanes.active),
    brevInstances: brev && number(brev.instances_reported),
    endpoints:
      brev && Array.isArray(brev.endpoints)
        ? rows(brev.endpoints).map((row) => ({
            name: text(row.name) ?? "unnamed",
            healthy: typeof row.healthy === "boolean" ? row.healthy : null,
          }))
        : null,
    // Real runs can report extra steps, one per classifier, so show whatever came back.
    steps: stepRows.length
      ? stepRows.flatMap((row) => {
          const name = text(row.name);
          return name ? [{ name, count: number(row.count), p50: number(row.p50_ms), p95: number(row.p95_ms), errors: number(row.errors) }] : [];
        })
      : STEP_NAMES.map((name) => ({ name, count: null, p50: null, p95: null, errors: null })),
    byMethod: parseMethods(raw.by_method),
    byModel: parseModels(raw.by_model),
    recent: rows(raw.recent).map(parseDecision).filter((row) => row !== null),
    timeline: rows(raw.timeline).flatMap((row) => {
      const t = number(row.t);
      return t === null ? [] : [{ t, processed: number(row.processed), decisions: number(row.decisions), score: number(row.score) }];
    }),
    weakLabels: parseWeak(raw.weak_labels),
  };
}

const SEEN_LIMIT = 5000;

/** `/live` only returns recent decisions, so keep each one seen. Newest first, one entry per case and model. */
export function mergeDecisions(seen: Decision[], incoming: Decision[]): Decision[] {
  const known = new Set(seen.map((item) => item.key));
  const fresh = incoming.filter((item) => !known.has(item.key));
  return fresh.length ? [...fresh, ...seen].slice(0, SEEN_LIMIT) : seen;
}

export function activeSteps(previous: LiveState | null, next: LiveState): string[] {
  if (!previous || next.status === null || TERMINAL.has(next.status)) return [];
  const before = new Map(previous.steps.map((step) => [step.name, step.count ?? 0]));
  return next.steps.filter((step) => step.count !== null && step.count > (before.get(step.name) ?? 0)).map((step) => step.name);
}

export function overallScore(methods: MethodRow[] | null): number | null {
  if (!methods) return null;
  const scored = methods.filter((row) => row.score !== null && row.n > 0);
  const total = scored.reduce((sum, row) => sum + row.n, 0);
  return total ? scored.reduce((sum, row) => sum + row.n * (row.score as number), 0) / total : null;
}

const PRIMARY_MODELS = ["safe-signal-guard", "jev-latest"];

/** One model's score for the headline. Other models are yardsticks, so they aren't averaged into it. */
export function headline(models: ModelRow[] | null, methods: MethodRow[] | null): { score: number | null; note: string } {
  const primary = PRIMARY_MODELS.map((name) => models?.find((model) => model.model === name)).find(Boolean) ?? (models?.length === 1 ? models[0] : null);
  if (primary) return { score: primary.score, note: `overall score, ${primary.model}` };
  if (models && models.length > 1) return { score: overallScore(methods), note: `overall score, averaged across ${models.length} models` };
  return { score: overallScore(methods), note: "overall score" };
}

export interface FamilyRow {
  family: string;
  n: number;
  wrong: number;
  soft: number;
}

export function familyRows(methods: MethodRow[] | null): FamilyRow[] {
  const families = new Map<string, FamilyRow>();
  for (const row of methods ?? []) {
    const entry = families.get(row.family) ?? { family: row.family, n: 0, wrong: 0, soft: 0 };
    entry.n += row.n;
    entry.wrong += row.wrong + row.noVerdict;
    entry.soft += row.soft;
    families.set(row.family, entry);
  }
  return [...families.values()].sort((a, b) => a.family.localeCompare(b.family));
}

export interface FamilySummary {
  family: string;
  n: number;
  right: number;
  soft: number;
  wrong: number;
  noVerdict: number;
  score: number | null;
}

/** Families with the lowest score first. Compares what the screen shows, so tiny changes in a live run don't reshuffle the list. */
export function familySummaries(methods: MethodRow[] | null): FamilySummary[] {
  const shownScore = ({ score }: FamilySummary) => (score === null ? Infinity : Math.round(score * 1000));
  return familyRows(methods)
    .map(({ family, n, soft, wrong }) => {
      const members = (methods ?? []).filter((row) => row.family === family);
      const noVerdict = members.reduce((sum, row) => sum + row.noVerdict, 0);
      const right = members.reduce((sum, row) => sum + row.right, 0);
      return { family, n, right, soft, wrong: wrong - noVerdict, noVerdict, score: overallScore(members) };
    })
    .sort((a, b) => (shownScore(a) === shownScore(b) ? b.wrong + b.noVerdict - (a.wrong + a.noVerdict) : shownScore(a) - shownScore(b)));
}

export interface Tally {
  label: string;
  count: number;
}

const tally = (labels: string[]): Tally[] => {
  const counts = new Map<string, number>();
  for (const label of labels) counts.set(label, (counts.get(label) ?? 0) + 1);
  return [...counts].map(([label, value]) => ({ label, count: value })).sort((a, b) => b.count - a.count);
};

export function drillIn(seen: Decision[], method: string) {
  const decisions = seen.filter((item) => item.method === method);
  return {
    observed: decisions.length,
    flags: tally(decisions.flatMap((item) => item.flags)),
    misclassifiedAs: tally(
      decisions.flatMap((item) => (item.predictedMethod && item.predictedMethod !== method ? [item.predictedMethod] : [])),
    ),
  };
}

/** Turns cumulative decision counts into a rate per second between points. */
export function decisionRates(timeline: TimelinePoint[]): number[] {
  const rates: number[] = [];
  for (let index = 1; index < timeline.length; index++) {
    const [before, after] = [timeline[index - 1], timeline[index]];
    const seconds = after.t - before.t;
    if (before.decisions !== null && after.decisions !== null && seconds > 0) {
      rates.push(Math.max(0, (after.decisions - before.decisions) / seconds));
    }
  }
  return rates;
}

export interface Named {
  name: string;
  count: number | null;
}

/** Accepts either `{name: count}` or `[{name, count}]`, because `/corpus` only specifies "counts by". */
function namedCounts(value: unknown, field: string): Named[] {
  const map = object(value);
  if (map) return Object.entries(map).map(([name, entry]) => ({ name, count: number(entry) }));
  return rows(value).flatMap((row) => {
    const name = text(row[field]) ?? text(row.name);
    return name ? [{ name, count: number(row.count) ?? number(row.n) }] : [];
  });
}

export interface Corpus {
  channels: Named[];
  sources: Named[];
  methods: Named[];
}

export function parseCorpus(value: unknown): Corpus {
  const raw = object(value) ?? {};
  const pick = (field: string) => namedCounts(raw[`by_${field}`] ?? raw[`${field}s`] ?? raw[field], field);
  return { channels: pick("channel"), sources: pick("source"), methods: pick("method") };
}

export interface ModelOption {
  name: string;
  healthy: boolean | null;
}

export function parseModelOptions(value: unknown): ModelOption[] {
  const raw = object(value);
  return rows(raw ? raw.models : value).flatMap((row) => {
    const name = text(row.model) ?? text(row.id) ?? text(row.name);
    if (!name) return [];
    const status = row.healthy ?? row.status;
    return [{ name, healthy: typeof status === "boolean" ? status : status === "ok" ? true : null }];
  });
}

export interface RunSummary {
  id: string;
  createdAt: string | null;
  total: number | null;
  status: string | null;
}

export function parseRuns(value: unknown): RunSummary[] {
  return rows(value).flatMap((row) => {
    const id = text(row.id);
    return id ? [{ id, createdAt: text(row.created_at), total: number(row.total), status: text(row.status) }] : [];
  });
}

export interface Marker {
  id: string;
  model: string | null;
  type: string | null;
  outcome: string | null;
  marker: string | null;
  feedback: string | null;
  improvement: string | null;
}

export function parseMarkers(value: unknown): Marker[] {
  return rows(value).map((row, index) => ({
    id: `${text(row.case_id) ?? text(row.session_id) ?? index}:${text(row.model) ?? ""}`,
    model: text(row.model),
    type: text(row.method) ?? text(row.call_type),
    outcome: text(row.outcome),
    marker: text(row.marker),
    feedback: text(row.feedback),
    improvement: text(row.improvement),
  }));
}

export interface ConsistentFailure {
  key: string;
  name: string;
  detail: string;
}

export interface Lessons {
  consistent: ConsistentFailure[];
  lessons: { title: string; detail: string | null; status: string | null; method: string | null; seen: number | null }[];
}

export function parseLessons(value: unknown): Lessons {
  const raw = object(value) ?? {};
  return {
    consistent: rows(raw.repeat_failures ?? raw.consistent_failures).flatMap((row) => {
      const name = text(row.method) ?? text(row.type);
      if (!name) return [];
      const model = text(row.model);
      const failing = number(row.runs_failing);
      const seen = number(row.runs_seen);
      const rate = number(row.mean_error_rate);
      const detail = [
        model,
        failing === null ? null : seen === null ? `failing in ${failing} runs` : `failing in ${failing} of ${seen} runs`,
        rate === null ? null : `${(rate * 100).toFixed(1)}% mean error`,
      ].filter(Boolean);
      return [{ key: `${model ?? ""}:${name}`, name, detail: detail.join(", ") }];
    }),
    lessons: rows(raw.lessons).flatMap((row) => {
      const marker = text(row.marker);
      const title = text(row.pattern) ?? (marker && humanize(marker)) ?? text(row.lesson);
      return title
        ? [{ title, detail: text(row.fix) ?? text(row.improvement), status: text(row.status), method: text(row.method), seen: number(row.count) }]
        : [];
    }),
  };
}
