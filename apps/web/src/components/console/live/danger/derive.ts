import { useSyncExternalStore } from "react";
import { TIERS, type Beat, type CallPhase, type CallTrace, type Scenario } from "@/lib/console/call-model";

/** Everything the danger views show is computed here from the trace. */

export const PHASE_NAMES: Record<CallPhase, string> = {
  connecting: "Connecting",
  live: "Live",
  checking: "Checking",
  responding: "Responding",
  deleted: "Deleted",
};

export interface PhaseSpan {
  phase: CallPhase;
  start: number;
  end: number;
}

/** Phases in call order, with the time each one starts and ends. */
export function phaseSpans(scenario: Scenario): PhaseSpan[] {
  const spans: PhaseSpan[] = [];
  for (const beat of scenario.beats) {
    const last = spans[spans.length - 1];
    if (last?.phase === beat.phase) continue;
    if (last) last.end = beat.t;
    spans.push({ phase: beat.phase, start: beat.t, end: scenario.duration });
  }
  return spans;
}

export function firstBeatOf(scenario: Scenario, phase: CallPhase): Beat | undefined {
  return scenario.beats.find((beat) => beat.phase === phase);
}

/**
 * Where each tier begins on the danger scale: the lowest score that ever carried it in this scenario.
 * A tier the scenario never reaches is spaced evenly, so the scale still draws.
 */
export function tierFloors(scenario: Scenario): number[] {
  let floor = 0;
  return TIERS.map((_, tier) => {
    const scores = scenario.beats.filter((beat) => beat.tier === tier).map((beat) => beat.danger);
    const found = tier === 0 ? 0 : scores.length ? Math.min(...scores) : tier / TIERS.length;
    floor = Math.max(floor, found);
    return floor;
  });
}

/** First time each tier was reached so far, undefined if not yet. */
export function tierReachedAt(trace: CallTrace): (number | undefined)[] {
  return TIERS.map((_, tier) => trace.past.find((beat) => beat.tier === tier)?.t);
}

export interface CallTiming {
  connectedAt: number | undefined;
  endedAt: number | undefined;
  /** Seconds the two parties have been connected. Stops counting when the call ends. */
  inCall: number;
}

export function callTiming(trace: CallTrace): CallTiming {
  const connectedAt = trace.past.find((beat) => beat.phase === "live")?.t;
  const endedAt = trace.past.find((beat) => beat.phase === "checking")?.t;
  if (connectedAt === undefined) return { connectedAt, endedAt, inCall: 0 };
  return { connectedAt, endedAt, inCall: Math.max(0, (endedAt ?? trace.t) - connectedAt) };
}

export type MemoryState = "empty" | "held" | "erased";

export interface MemoryStatus {
  state: MemoryState;
  openedAt: number | undefined;
  erasedAt: number | undefined;
  /** Seconds the conversation window has existed, up to now or to when it was erased. */
  heldFor: number;
}

export function memoryStatus(trace: CallTrace): MemoryStatus {
  const openedAt = trace.past.find((beat) => beat.status.window !== undefined)?.t;
  const erasedAt = trace.past.find((beat) => beat.links.includes("window>purge"))?.t;
  const state: MemoryState = erasedAt !== undefined ? "erased" : openedAt !== undefined ? "held" : "empty";
  const heldFor = openedAt === undefined ? 0 : Math.max(0, (erasedAt ?? trace.t) - openedAt);
  return { state, openedAt, erasedAt, heldFor };
}

/** True when the beat sent a block from the conversation window to Jev. */
export function sentToJev(beat: Beat): boolean {
  return beat.links.includes("window>jev");
}

const MOTION_QUERY = "(prefers-reduced-motion: reduce)";

function subscribeToMotion(onChange: () => void) {
  const query = window.matchMedia(MOTION_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

export function useReducedMotion(): boolean {
  return useSyncExternalStore(subscribeToMotion, () => window.matchMedia(MOTION_QUERY).matches, () => false);
}
