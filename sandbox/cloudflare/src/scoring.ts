// Compares Jev's tiers against the labels. Every number in the report comes from here, never from an LLM.
import { HARD_NEGATIVE_TYPES, type Session } from "./frames";
import { TIER_RANK, type Tier } from "./jev";

export interface FrameResult {
  index: number;
  t: number;
  trigger: string;
  tier: Tier | null;
  p_safe: number | null;
  p_uncertain: number | null;
  p_dangerous: number | null;
  flags: Record<string, number>;
  jev_ms: number | null;
  agent_ms: number | null;
  input_tokens: number;
  output_tokens: number;
  agent_called: boolean;
  agent_ok: boolean;
  delivered: boolean;
  error: string | null;
}

export interface CallRow {
  session_id: string;
  scam_type: string;
  scam: boolean;
  hard_negative: boolean;
  expected: string;
  tier: Tier | null;
  outcome: string;
  points: number;
  max_p_dangerous: number;
  first_dangerous_t: number | null;
  money_moment_t: number | null;
  caught_before_money: boolean | null;
  frames: number;
  frames_answered: number;
  frames_delivered: number;
  agent_called: number;
  agent_failures: number;
  jev_failures: number;
  input_tokens: number;
  output_tokens: number;
  peak_flags: Record<string, number>;
}

const OUTCOMES: Record<string, [string, number]> = {
  "true:dangerous": ["caught", 1],
  "true:uncertain": ["soft_miss", 0.5],
  "true:safe": ["missed", 0],
  "false:safe": ["clear", 1],
  "false:uncertain": ["soft_false_alarm", 0.5],
  "false:dangerous": ["false_alarm", 0],
};

export const FAILURES = new Set(["soft_miss", "missed", "soft_false_alarm", "false_alarm", "no_verdict"]);

export function scoreCall(session: Session, frames: FrameResult[]): CallRow {
  const answered = frames.filter((f) => f.tier !== null);
  // Risk only goes up during a call (R5): the call's tier is the highest any frame reached.
  let tier: Tier | null = null;
  for (const frame of answered) if (tier === null || TIER_RANK[frame.tier!] > TIER_RANK[tier]) tier = frame.tier;
  const [outcome, points] = tier === null ? ["no_verdict", 0] : OUTCOMES[`${session.scam}:${tier}`];
  const first = answered.find((f) => f.tier === "dangerous")?.t ?? null;
  const money = session.money_moment_t;
  const peak: Record<string, number> = {};
  for (const frame of answered) {
    for (const [name, p] of Object.entries(frame.flags)) peak[name] = Math.max(p, peak[name] ?? 0);
  }
  return {
    session_id: session.session_id,
    scam_type: session.scam_type,
    scam: session.scam,
    hard_negative: HARD_NEGATIVE_TYPES.has(session.scam_type),
    expected: session.scam ? "dangerous" : "safe",
    tier,
    outcome,
    points,
    max_p_dangerous: Math.max(0, ...answered.map((f) => f.p_dangerous ?? 0)),
    first_dangerous_t: first,
    money_moment_t: money,
    caught_before_money: money === null ? null : first !== null && first <= money,
    frames: frames.length,
    frames_answered: answered.length,
    frames_delivered: frames.filter((f) => f.delivered).length,
    agent_called: frames.filter((f) => f.agent_called).length,
    agent_failures: frames.filter((f) => !f.agent_ok).length,
    jev_failures: frames.filter((f) => f.tier === null).length,
    input_tokens: frames.reduce((n, f) => n + f.input_tokens, 0),
    output_tokens: frames.reduce((n, f) => n + f.output_tokens, 0),
    peak_flags: peak,
  };
}

const rate = (n: number, d: number) => (d ? Number((n / d).toFixed(4)) : null);
const median = (xs: number[]) => {
  if (!xs.length) return null;
  const sorted = [...xs].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
};

export function buildScoreboard(rows: CallRow[], latency: Record<string, number | null>) {
  const byType = new Map<string, CallRow[]>();
  for (const row of rows) byType.set(row.scam_type, [...(byType.get(row.scam_type) ?? []), row]);
  const types = [...byType.entries()]
    .sort(([a], [b]) => (a < b ? -1 : 1))
    .map(([type, group]) => {
      const outcomes: Record<string, number> = {};
      for (const row of group) outcomes[row.outcome] = (outcomes[row.outcome] ?? 0) + 1;
      const points = group.reduce((n, r) => n + r.points, 0);
      return {
        type,
        scam: group[0].scam,
        hard_negative: group[0].hard_negative,
        n: group.length,
        points_pct: rate(points, group.length),
        error_rate: rate(group.length - points, group.length),
        outcomes,
        mean_max_p_dangerous: Number((group.reduce((n, r) => n + r.max_p_dangerous, 0) / group.length).toFixed(4)),
        median_first_dangerous_t: median(group.flatMap((r) => (r.first_dangerous_t === null ? [] : [r.first_dangerous_t]))),
      };
    });

  const scams = rows.filter((r) => r.scam);
  const benign = rows.filter((r) => !r.scam);
  const hard = benign.filter((r) => r.hard_negative);
  const withMoney = scams.filter((r) => r.caught_before_money !== null);
  const sum = (key: keyof CallRow) => rows.reduce((n, r) => n + Number(r[key]), 0);
  const count = (list: CallRow[], outcome: string) => list.filter((r) => r.outcome === outcome).length;
  const tiers = (list: CallRow[]) =>
    Object.fromEntries(["dangerous", "uncertain", "safe"].map((t) => [t, list.filter((r) => r.tier === t).length]));

  return {
    sessions: rows.length,
    scams: scams.length,
    benign: benign.length,
    hard_negatives: hard.length,
    overall_points_pct: rate(sum("points"), rows.length),
    catch_rate: rate(count(scams, "caught"), scams.length),
    false_alarm_rate: rate(count(benign, "false_alarm"), benign.length),
    hard_negative_false_alarm_rate: rate(count(hard, "false_alarm"), hard.length),
    caught_before_money: rate(withMoney.filter((r) => r.caught_before_money).length, withMoney.length),
    caught_before_money_n: withMoney.length,
    confusion: { scam: tiers(scams), benign: tiers(benign) },
    by_type: types,
    delivery: {
      frames: sum("frames"),
      delivered: sum("frames_delivered"),
      delivered_rate: rate(sum("frames_delivered"), sum("frames")),
      agent_called: sum("agent_called"),
      agent_failures: sum("agent_failures"),
      jev_failures: sum("jev_failures"),
      jev_input_tokens: sum("input_tokens"),
      jev_output_tokens: sum("output_tokens"),
      ...latency,
    },
  };
}
