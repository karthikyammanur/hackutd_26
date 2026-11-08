import { useCallback, useEffect, useRef, useState } from "react";
import type { Decision, Lessons, LiveState, Marker, MethodRow, StepStat } from "@/lib/simulate/parse";
import type { ArchitectureFigureProps } from "./ArchitectureFigure";

/**
 * A scripted run for showing the figure without spending model credits. It never calls the backend,
 * and the screen labels it as sample data while it plays.
 */

const TOTAL_CALLS = 240;
const LANES = 12;
const TICK_MS = 300;
const STARTING_S = 1.5;
const REPLAY_S = 16;
const REVIEW_S = 5;
const FRAMES_PER_CALL = 6;
const FAILURES_TO_REVIEW = 24;
const LEDGER_SIZE = 40;

const METHODS = [
  { method: "bank_fraud_department", family: "impersonation", scam: true },
  { method: "carrier_impersonation", family: "impersonation", scam: true },
  { method: "delivery_fee", family: "payment", scam: true },
  { method: "prize_lottery", family: "relationship_or_opportunity", scam: true },
  { method: "legitimate", family: "legitimate", scam: false },
];

const emptyRow = ({ method, family }: (typeof METHODS)[number]): MethodRow => ({
  method, family, n: 0, right: 0, soft: 0, wrong: 0, noVerdict: 0, counts: {}, score: null, methodAccuracy: null,
});

const step = (name: string, count: number, p50: number, p95: number): StepStat => ({ name, count, p50, p95, errors: 0 });

const SAMPLE_MARKERS: Marker[] = [
  { id: "sample-1", model: "jev-latest", type: "late_or_soft_detection", outcome: "soft_miss", marker: "Sample: the request came late in the call", feedback: null, improvement: null },
  { id: "sample-2", model: "jev-latest", type: "false_alarm", outcome: "false_alarm", marker: "Sample: a real bank notice looked urgent", feedback: null, improvement: null },
];

const SAMPLE_LESSONS: Lessons = {
  consistent: [],
  lessons: [
    { title: "Sample lesson", detail: "Shown only in the preview.", status: "proposed", method: "prize_lottery", seen: 1 },
    { title: "Sample lesson", detail: "Shown only in the preview.", status: "proposed", method: "delivery_fee", seen: 1 },
  ],
};

function decide(index: number, row: MethodRow, scam: boolean): Decision {
  const roll = Math.random();
  const kind = roll < 0.8 ? "right" : roll < 0.92 ? "soft" : "wrong";
  const outcome = scam
    ? { right: "caught", soft: "soft_miss", wrong: "missed" }[kind]
    : { right: "clear", soft: "soft_false_alarm", wrong: "false_alarm" }[kind];
  const tier = kind === "soft" ? "uncertain" : (kind === "right") === scam ? "dangerous" : "safe";
  row.n += 1;
  row[kind] += 1;
  row.counts[outcome] = (row.counts[outcome] ?? 0) + 1;
  row.score = (row.right + row.soft / 2) / row.n;
  return {
    key: `preview-${index}`, caseId: `sample-${index}`, channel: "call", method: row.method, predictedMethod: null,
    tier, outcome, model: "jev-latest", flags: [], ms: 300 + Math.round(Math.random() * 500),
  };
}

type FigureData = Omit<ArchitectureFigureProps, "paused">;

export function usePreviewRun() {
  const [data, setData] = useState<FigureData | null>(null);
  const timer = useRef(0);

  const stop = useCallback(() => {
    window.clearInterval(timer.current);
    setData(null);
  }, []);

  useEffect(() => () => window.clearInterval(timer.current), []);

  const start = useCallback(() => {
    window.clearInterval(timer.current);
    const startedAt = performance.now();
    const rows = METHODS.map(emptyRow);
    let seen: Decision[] = [];
    let processed = 0;

    const advance = () => {
      const elapsed = (performance.now() - startedAt) / 1000;
      const replayed = Math.min(1, Math.max(0, (elapsed - STARTING_S) / REPLAY_S));
      const target = Math.round(replayed * TOTAL_CALLS);
      while (processed < target) {
        const pick = Math.floor(Math.random() * METHODS.length);
        seen = [decide(processed + 1, rows[pick], METHODS[pick].scam), ...seen].slice(0, LEDGER_SIZE);
        processed += 1;
      }

      const reviewed = Math.min(1, Math.max(0, (elapsed - STARTING_S - REPLAY_S) / REVIEW_S));
      const finished = reviewed >= 1;
      const status = finished ? "done" : replayed >= 1 ? "checking" : "running";
      const frames = processed * FRAMES_PER_CALL;
      const n = rows.reduce((sum, row) => sum + row.n, 0);
      const points = rows.reduce((sum, row) => sum + row.right + row.soft / 2, 0);
      const score = n ? points / n : null;
      const byMethod = rows.filter((row) => row.n > 0).map((row) => ({ ...row, counts: { ...row.counts } }));

      const live: LiveState = {
        id: "preview", status, error: null, elapsedS: elapsed, total: TOTAL_CALLS, processed,
        decisionsPerS: status === "running" ? frames / Math.max(elapsed, 1) : 0,
        framesPerS: status === "running" ? frames / Math.max(elapsed, 1) : 0,
        lanesConfigured: LANES,
        lanesActive: status === "running" ? (replayed === 0 ? Math.min(LANES, Math.ceil(elapsed * 8)) : LANES - Math.floor(Math.random() * 3)) : 0,
        brevInstances: null, endpoints: null,
        steps: [
          step("frames", processed, 2, 5),
          step("agent", frames, 180, 420),
          step("jev", frames, 410, 980),
          step("score", processed, 1, 2),
          step("check", Math.round(reviewed * FAILURES_TO_REVIEW), 900, 1600),
        ],
        byMethod, byModel: null, recent: seen,
        timeline: [{ t: elapsed, processed, decisions: frames, score }],
        weakLabels: null,
      };

      setData({
        live, seen, byMethod, score,
        active: status === "running" ? ["frames", "agent", "jev", "score"] : status === "checking" ? ["check"] : [],
        markers: finished ? SAMPLE_MARKERS : null,
        lessons: finished ? SAMPLE_LESSONS : null,
      });
      if (finished) window.clearInterval(timer.current);
    };

    advance();
    timer.current = window.setInterval(advance, TICK_MS);
  }, []);

  return { data, playing: data !== null && data.live?.status !== "done", start, stop };
}
