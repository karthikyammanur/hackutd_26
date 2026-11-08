/** Turns evidence-store responses into typed values. A field that's missing or malformed becomes null, never a made-up value. */

export type Count = number | "<5";

export interface Bucket {
  key: string;
  count: Count;
}

export interface Signal {
  signal: string;
  strength: number | null;
}

export interface TimelineStep {
  seq: number;
  tBucketS: number | null;
  tier: string | null;
  risk: number | null;
}

export interface Incident {
  id: string;
  occurredHour: string | null;
  channel: string | null;
  source: string | null;
  method: string | null;
  family: string | null;
  predictedMethod: string | null;
  tier: string | null;
  outcome: string | null;
  maxRisk: number | null;
  firstAlertBucketS: number | null;
  durationBucketS: number | null;
  moneyMovedBeforeAlert: boolean | null;
  model: string | null;
  callerCluster: string | null;
  summary: string | null;
  signals: Signal[];
  timeline: TimelineStep[];
}

export interface IncidentPage {
  items: Incident[];
  nextCursor: string | null;
  totalEstimate: number | null;
}

export interface Overview {
  total: Count | null;
  byTier: Bucket[];
  byFamily: Bucket[];
  bySource: Bucket[];
  from: string | null;
  to: string | null;
}

export interface TimePoint {
  day: string;
  values: Record<string, Count>;
}

export interface MethodStat {
  method: string;
  family: string | null;
  total: Count | null;
  tiers: Record<string, Count>;
}

type Dict = Record<string, unknown>;

const isDict = (value: unknown): value is Dict => typeof value === "object" && value !== null && !Array.isArray(value);
const str = (value: unknown): string | null => (typeof value === "string" && value !== "" ? value : null);
const num = (value: unknown): number | null => (typeof value === "number" && Number.isFinite(value) ? value : null);
const first = (row: Dict, keys: string[]): unknown => row[keys.find((key) => row[key] !== undefined) ?? ""];

export function asCount(value: unknown): Count | null {
  if (value === "<5") return "<5";
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}

/** Suppressed groups chart as zero. The table and labels still say "<5". */
export const countValue = (count: Count | null): number => (typeof count === "number" ? count : 0);
export const formatCount = (count: Count | null): string =>
  count === null ? "Unavailable" : typeof count === "number" ? count.toLocaleString("en-US") : count;

function flag(value: unknown): boolean | null {
  if (value === true || value === 1) return true;
  if (value === false || value === 0) return false;
  return null;
}

const COUNT_KEYS = ["n", "count", "total"];

/** Reads `{a: 1}` or `[{tier: "a", n: 1}]` into buckets, largest first. */
export function parseBuckets(value: unknown, nameKeys: string[]): Bucket[] {
  const buckets: Bucket[] = [];
  if (Array.isArray(value)) {
    for (const row of value) {
      if (!isDict(row)) continue;
      const key = str(first(row, [...nameKeys, "key", "name"]));
      const count = asCount(first(row, COUNT_KEYS));
      if (key && count !== null) buckets.push({ key, count });
    }
  } else if (isDict(value)) {
    for (const [key, raw] of Object.entries(value)) {
      const count = asCount(raw);
      if (count !== null) buckets.push({ key, count });
    }
  }
  return buckets.sort((a, b) => countValue(b.count) - countValue(a.count));
}

function parseSignals(value: unknown): Signal[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item): Signal[] => {
    if (typeof item === "string") return [{ signal: item, strength: null }];
    if (!isDict(item)) return [];
    const signal = str(item.signal);
    return signal ? [{ signal, strength: num(item.strength) }] : [];
  });
}

function parseTimeline(value: unknown): TimelineStep[] {
  if (!Array.isArray(value)) return [];
  return value
    .flatMap((item, index): TimelineStep[] =>
      isDict(item) ? [{ seq: num(item.seq) ?? index, tBucketS: num(item.t_bucket_s), tier: str(item.tier), risk: num(item.risk) }] : [],
    )
    .sort((a, b) => a.seq - b.seq);
}

export function parseIncident(value: unknown): Incident | null {
  if (!isDict(value)) return null;
  const source = isDict(value.incident) ? { ...value.incident, signals: value.signals ?? value.incident.signals, timeline: value.timeline ?? value.incident.timeline } : value;
  const id = str(source.incident_id);
  if (!id) return null;
  return {
    id,
    occurredHour: str(source.occurred_hour),
    channel: str(source.channel),
    source: str(source.source),
    method: str(source.method),
    family: str(source.family),
    predictedMethod: str(source.predicted_method),
    tier: str(source.tier),
    outcome: str(source.outcome),
    maxRisk: num(source.max_risk),
    firstAlertBucketS: num(source.first_alert_bucket_s),
    durationBucketS: num(source.duration_bucket_s),
    moneyMovedBeforeAlert: flag(source.money_moved_before_alert),
    model: str(source.model),
    callerCluster: str(source.caller_cluster),
    summary: str(source.summary),
    signals: parseSignals(source.signals),
    timeline: parseTimeline(source.timeline),
  };
}

export function parseIncidentPage(value: unknown): IncidentPage {
  const body = isDict(value) ? value : {};
  const items = Array.isArray(body.items) ? body.items.flatMap((item) => parseIncident(item) ?? []) : [];
  return { items, nextCursor: str(body.next_cursor), totalEstimate: num(body.total_estimate) };
}

export function parseOverview(value: unknown): Overview {
  const body = isDict(value) ? value : {};
  const range = isDict(body.date_range) ? body.date_range : body;
  return {
    total: asCount(body.total),
    byTier: parseBuckets(first(body, ["by_tier", "tiers"]), ["tier"]),
    byFamily: parseBuckets(first(body, ["by_family", "families"]), ["family"]),
    bySource: parseBuckets(first(body, ["by_source", "sources"]), ["source"]),
    from: str(first(range, ["from", "min", "first"])),
    to: str(first(range, ["to", "max", "last"])),
  };
}

const DAY_KEYS = ["day", "bucket", "date"];

/** Accepts one series per key, one row per day with a `values` map, or one row per day and key. Days come back in order. */
export function parseTimeseries(value: unknown): TimePoint[] {
  const body = isDict(value) ? value : {};
  const rows = Array.isArray(value) ? value : first(body, ["points", "series", "rows", "items"]);
  if (!Array.isArray(rows)) return [];
  const byDay = new Map<string, Record<string, Count>>();
  for (const row of rows) {
    if (!isDict(row)) continue;
    if (Array.isArray(row.points)) {
      const key = str(row.key);
      if (!key) continue;
      for (const point of row.points) {
        if (!isDict(point)) continue;
        const day = str(first(point, DAY_KEYS));
        const count = asCount(first(point, COUNT_KEYS));
        if (day && count !== null) byDay.set(day, { ...byDay.get(day), [key]: count });
      }
      continue;
    }
    const day = str(first(row, DAY_KEYS));
    if (!day) continue;
    const values = byDay.get(day) ?? {};
    if (isDict(row.values)) {
      for (const [key, raw] of Object.entries(row.values)) {
        const count = asCount(raw);
        if (count !== null) values[key] = count;
      }
    } else {
      const key = str(first(row, ["key", "group", "method", "family", "tier", "name"]));
      const count = asCount(first(row, COUNT_KEYS));
      if (key && count !== null) values[key] = count;
    }
    byDay.set(day, values);
  }
  return [...byDay.entries()].sort(([a], [b]) => (a < b ? -1 : 1)).map(([day, values]) => ({ day, values }));
}

export function parseSignalStats(value: unknown): Bucket[] {
  const body = isDict(value) ? value : {};
  return parseBuckets(Array.isArray(value) ? value : first(body, ["signals", "items", "rows"]), ["signal"]);
}

const TIERS = ["safe", "uncertain", "dangerous"];

export function parseMethods(value: unknown): MethodStat[] {
  const body = isDict(value) ? value : {};
  const rows = Array.isArray(value) ? value : first(body, ["methods", "items", "rows"]);
  if (!Array.isArray(rows)) return [];
  return rows
    .flatMap((row): MethodStat[] => {
      if (!isDict(row)) return [];
      const method = str(row.method);
      if (!method) return [];
      const tierSource = isDict(row.tiers) ? row.tiers : isDict(row.by_tier) ? row.by_tier : row;
      const tiers: Record<string, Count> = {};
      for (const tier of TIERS) {
        const count = asCount(tierSource[tier]);
        if (count !== null) tiers[tier] = count;
      }
      return [{ method, family: str(row.family), total: asCount(first(row, COUNT_KEYS)), tiers }];
    })
    .sort((a, b) => countValue(b.total) - countValue(a.total));
}

export const OTHER = "other";

/** Folds every key that isn't charted into Other, so the stacks always add up to the true daily total. */
export function foldSeries(points: TimePoint[], keys: readonly string[]): { day: string; values: Record<string, number>; total: number; suppressed: boolean }[] {
  const charted = new Set(keys);
  return points.map(({ day, values }) => {
    const folded: Record<string, number> = {};
    let total = 0;
    let suppressed = false;
    for (const [key, count] of Object.entries(values)) {
      if (count === "<5") suppressed = true;
      const n = countValue(count);
      const slot = charted.has(key) ? key : OTHER;
      folded[slot] = (folded[slot] ?? 0) + n;
      total += n;
    }
    return { day, values: folded, total, suppressed };
  });
}

export interface Filters {
  q: string;
  method: string;
  family: string;
  channel: string;
  tier: string;
  outcome: string;
  signal: string;
  source: string;
  from: string;
  to: string;
}

export const EMPTY_FILTERS: Filters = { q: "", method: "", family: "", channel: "", tier: "", outcome: "", signal: "", source: "", from: "", to: "" };

export function toQuery(values: Record<string, string | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) if (value) query.set(key, value);
  const text = query.toString();
  return text ? `?${text}` : "";
}
