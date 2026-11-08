import type { CSSProperties } from "react";
import { project, route, type V2 } from "../../live/pipeline/iso";
import type { StationId, WireId } from "./model";

/** Where everything stands on the bench. World units match the Live page: x right, y toward the viewer, z up. */

export const BENCH = { w: 1010, d: 760 };
export const RACK = { x0: 272, x1: 802, y0: 44, y1: 300, railX0: 284, railX1: 792 };
export const BRIDGE_X = { note: 424, jev: 620 };
export const PEAK = { cx: 884, cy: 176 };
export const DECK = { cx: 70, cy: 176 };
export const CUTTER = { cx: 192, cy: 176 };
export const LEDGER = { x0: 652, x1: 996, y0: 402, y1: 736 };
export const RULER = { x0: 284, x1: 792, cy: 322, d: 12 };
export const BOARD = { cx: 500, cy: 488, w: 174, h: 106 };
export const DEEP = { cx: 290, cy: 500 };
export const LESSONS = { cx: 290, cy: 650 };
export const CHECKER = { cx: 90, cy: 650 };

export const PLATES = {
  replay: [[0, 0], [BENCH.w, 0], [BENCH.w, 352], [0, 352]] as V2[],
  log: [[638, 364], [BENCH.w, 364], [BENCH.w, BENCH.d], [638, BENCH.d]] as V2[],
  after: [[0, 364], [626, 364], [626, BENCH.d], [0, BENCH.d]] as V2[],
};

const corners = ([
  [0, 0, 40],
  [BENCH.w, 0, 60],
  [0, BENCH.d, -16],
  [BENCH.w, BENCH.d, -16],
] as const).map(([x, y, z]) => project(x, y, z));
const minX = Math.min(...corners.map((c) => c[0])) - 12;
const minY = Math.min(...corners.map((c) => c[1])) - 14;

export const VB = {
  x: minX,
  y: minY,
  width: Math.round(Math.max(...corners.map((c) => c[0])) - minX + 12),
  height: Math.round(Math.max(...corners.map((c) => c[1])) - minY + 14),
};

const pct = (value: number, total: number) => `${(value / total) * 100}%`;

export function anchor(x: number, y: number, z = 0): CSSProperties {
  const [sx, sy] = project(x, y, z);
  return { left: pct(sx - VB.x, VB.width), top: pct(sy - VB.y, VB.height) };
}

export const ROUTES: Record<WireId, V2[]> = {
  "deck>cut": [[DECK.cx + 56, DECK.cy], [CUTTER.cx - 54, CUTTER.cy]],
  "cut>rack": [[CUTTER.cx + 54, CUTTER.cy], [RACK.x0 - 8, CUTTER.cy]],
  loop: [[BRIDGE_X.jev, RACK.y0 - 18], [BRIDGE_X.note, RACK.y0 - 18]],
  "rack>peak": [[RACK.x1 + 8, PEAK.cy], [PEAK.cx - 42, PEAK.cy]],
  "peak>log": [[PEAK.cx + 42, PEAK.cy], [968, PEAK.cy], [968, LEDGER.y0 - 8]],
  "log>board": [[LEDGER.x0 - 8, 488], [BOARD.cx + BOARD.w / 2 + 12, 488]],
  labels: [[52, DECK.cy + 74], [52, 382], [392, 382], [392, 468], [BOARD.cx - BOARD.w / 2 - 12, 468]],
  "board>deep": [[BOARD.cx - BOARD.w / 2 - 12, DEEP.cy], [DEEP.cx + 64, DEEP.cy]],
  "deep>lessons": [[DEEP.cx, DEEP.cy + 46], [DEEP.cx, LESSONS.cy - 40]],
  "lessons>checker": [[LESSONS.cx - 52, LESSONS.cy], [CHECKER.cx + 60, LESSONS.cy]],
};

export const WIRES = (Object.keys(ROUTES) as WireId[]).map((id) => ({ id, ...route(ROUTES[id], 13, 0.6) }));

type Placement = "below" | "above" | "left";

export const CAPTIONS: Record<StationId, { at: [number, number, number]; width: number; place: Placement }> = {
  deck: { at: [DECK.cx + 8, DECK.cy - 72, 34], width: 170, place: "above" },
  cut: { at: [CUTTER.cx + 8, CUTTER.cy + 62, 0], width: 150, place: "below" },
  note: { at: [BRIDGE_X.note + 26, RACK.y0 - 20, 66], width: 190, place: "above" },
  jev: { at: [BRIDGE_X.jev + 6, RACK.y0 - 20, 66], width: 240, place: "above" },
  peak: { at: [PEAK.cx - 22, PEAK.cy + 66, 0], width: 200, place: "below" },
  log: { at: [846, LEDGER.y0 - 8, 22], width: 270, place: "above" },
  board: { at: [BOARD.cx, BOARD.cy + 42, 0], width: 220, place: "below" },
  deep: { at: [DEEP.cx - 74, DEEP.cy + 4, 0], width: 200, place: "left" },
  lessons: { at: [LESSONS.cx, LESSONS.cy + 44, 0], width: 200, place: "below" },
  checker: { at: [CHECKER.cx + 4, CHECKER.cy + 46, 0], width: 186, place: "below" },
};
