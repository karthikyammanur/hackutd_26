import type { CSSProperties, ReactNode } from "react";
import { circle, line, planPath, prism, project, rect, type V2, type V3 } from "../../live/pipeline/iso";
import { BOARD, BRIDGE_X, CHECKER, CUTTER, DECK, DEEP, LEDGER, LESSONS, PEAK, RACK, RULER } from "./layout";
import { LEDGER_SLOTS, type BoardShare, type Result, type Tier } from "./model";

/** The machine, drawn with the Live page's camera. Static parts are built once at module load. */

export const HATCH_ID = "sa-hatch";

type Plan = V2[];

function Solid({ plan, z0, z1, top = "top" }: { plan: Plan; z0: number; z1: number; top?: string }) {
  const { sides, top: topPath } = prism(plan, z0, z1);
  return (
    <>
      {sides.map((side, i) => (
        <path key={i} className={`s ${side.tone}`} d={side.d} />
      ))}
      <path className={top} d={topPath} />
    </>
  );
}

const Inset = ({ plan, z, className }: { plan: Plan; z: number; className: string }) => (
  <path className={className} d={planPath(plan, z)} />
);

const Rule = ({ points, className = "rule" }: { points: V3[]; className?: string }) => (
  <path className={className} d={line(points)} />
);

const Hatch = ({ plan, z }: { plan: Plan; z: number }) => (
  <path className="hatch" d={planPath(plan, z)} fill={`url(#${HATCH_ID})`} />
);

const screws = (points: V2[], z: number): ReactNode =>
  points.map(([x, y], i) => <Inset key={i} plan={circle(x, y, 2.1, 8)} z={z} className="screw" />);

const vents = (x0: number, x1: number, y: number, z: number, count: number, gap = 7): ReactNode =>
  Array.from({ length: count }, (_, i) => {
    const x = x0 + ((x1 - x0) * i) / Math.max(1, count - 1);
    return <Rule key={i} points={[[x, y, z], [x, y, z + gap]]} />;
  });

function housing(cx: number, cy: number, w: number, d: number, h: number): ReactNode {
  return (
    <>
      <Solid plan={rect(cx, cy, w + 8, d + 8, 8)} z0={0} z1={3} top="foot" />
      <Solid plan={rect(cx, cy, w, d, 9)} z0={3} z1={h} />
      <Inset plan={rect(cx, cy, w - 14, d - 14, 6)} z={h + 0.2} className="seam" />
      {screws(
        [
          [cx - w / 2 + 8, cy - d / 2 + 8],
          [cx + w / 2 - 8, cy - d / 2 + 8],
          [cx - w / 2 + 8, cy + d / 2 - 8],
          [cx + w / 2 - 8, cy + d / 2 - 8],
        ],
        h + 0.3,
      )}
    </>
  );
}

/* Call deck: labeled cards, hatched because they're synthetic. */
const CARDS = [0, 1, 2, 3, 4, 5, 6];
export const DECK_ART: ReactNode = (() => {
  const { cx, cy } = DECK;
  return (
    <>
      <Solid plan={rect(cx, cy, 110, 136, 10)} z0={0} z1={3} top="foot" />
      {CARDS.map((i) => (
        <Solid key={i} plan={rect(cx - 2 + i * 0.7, cy + 3 - i, 92, 118, 7)} z0={3 + i * 3.4} z1={6 + i * 3.4} />
      ))}
      <Hatch plan={rect(cx + 2, cy - 3, 92, 118, 7)} z={27.6} />
      <Inset plan={rect(cx + 2, cy - 40, 64, 18, 3)} z={27.8} className="acc" />
      <Rule points={[[cx - 30, cy - 12, 27.8], [cx + 34, cy - 12, 27.8]]} className="scr-line" />
      <Rule points={[[cx - 30, cy + 2, 27.8], [cx + 26, cy + 2, 27.8]]} className="scr-line" />
      <Rule points={[[cx - 30, cy + 16, 27.8], [cx + 18, cy + 16, 27.8]]} className="scr-line" />
      <Rule points={[[cx - 30, cy + 34, 27.8], [cx - 8, cy + 34, 27.8]]} className="scr-line" />
    </>
  );
})();

/* Cutter: a blade over a throat, with the microframes fanned out at the exit. */
export const CUTTER_ART: ReactNode = (() => {
  const { cx, cy } = CUTTER;
  return (
    <>
      {housing(cx, cy, 96, 104, 40)}
      <Inset plan={rect(cx - 4, cy, 56, 74, 4)} z={40.3} className="tray" />
      <Inset plan={rect(cx - 4, cy, 4, 70, 1)} z={40.4} className="slot" />
      <Solid plan={rect(cx - 4, cy - 44, 44, 12, 3)} z0={40} z1={50} />
      <Solid plan={rect(cx - 4, cy + 44, 44, 12, 3)} z0={40} z1={50} />
      <Solid plan={rect(cx - 4, cy, 9, 92, 2)} z0={50} z1={58} top="acc" />
      {[-30, -20, -10, 0, 10, 20, 30].map((dy) => (
        <Rule key={dy} points={[[cx + 26, cy + dy, 40.4], [cx + 40, cy + dy, 40.4]]} className="scr-line" />
      ))}
      {vents(cx - 38, cx + 38, cy + 52, 12, 11, 9)}
    </>
  );
})();

/* Lane rack -------------------------------------------------------------------------------------- */

export const railY = (index: number, total: number) => RACK.y0 + ((index + 0.5) * (RACK.y1 - RACK.y0)) / total;

export const RACK_BASE: ReactNode = (() => {
  const { x0, x1, y0, y1 } = RACK;
  const cx = (x0 + x1) / 2;
  const cy = (y0 + y1) / 2;
  const w = x1 - x0;
  const d = y1 - y0;
  return (
    <>
      <Solid plan={rect(cx, cy, w + 12, d + 12, 8)} z0={0} z1={3} top="foot" />
      <Solid plan={rect(cx, cy, w, d, 6)} z0={3} z1={7} />
      <Inset plan={rect(cx, cy, w - 10, d - 10, 4)} z={7.2} className="tray" />
      {screws([[x0 + 7, y0 + 7], [x1 - 7, y0 + 7], [x0 + 7, y1 - 7], [x1 - 7, y1 - 7]], 7.4)}
    </>
  );
})();

/** One lane: a rail with its status lamp and a shuttle that carries frames between the two bridges. */
export function laneArt(y: number, pitch: number): { rail: ReactNode; lamp: string; shuttle: ReactNode; travel: V2 } {
  const { railX0, railX1 } = RACK;
  const railDepth = Math.max(1.6, Math.min(8, pitch * 0.42));
  const lampR = Math.max(0.9, Math.min(3.2, pitch * 0.28));
  const shuttleDepth = Math.max(1.6, Math.min(20, pitch * 0.74));
  const cx = (railX0 + railX1) / 2;
  const startX = BRIDGE_X.note - 56;
  const rail = (
    <>
      <Solid plan={rect(cx, y, railX1 - railX0, railDepth, 1)} z0={7.2} z1={9.6} top="rail-top" />
      <Rule points={[[railX0 + 14, y, 10], [railX1 - 14, y, 10]]} className="rail-mark" />
    </>
  );
  const shuttle = (
    <Solid plan={rect(startX, y, 30, shuttleDepth, 1.5)} z0={9.6} z1={Math.min(9.6 + Math.max(3, pitch * 0.34), 16.6)} top="chip-top" />
  );
  const [ax, ay] = project(startX, y);
  const [bx, by] = project(BRIDGE_X.jev + 50, y);
  return { rail, lamp: planPath(circle(railX0 + 8, y, lampR, 10), 10.2), shuttle, travel: [bx - ax, by - ay] };
}

function bridge(x: number, topArt: ReactNode) {
  const { y0, y1 } = RACK;
  const beamHeight = 40;
  const cy = (y0 + y1) / 2;
  const depth = y1 - y0 + 22;
  const back = (
    <>
      <Solid plan={rect(x, y0 - 6, 30, 16, 3)} z0={0} z1={beamHeight} />
      <Inset plan={circle(x, y0 - 6, 4, 10)} z={beamHeight + 0.2} className="seam" />
    </>
  );
  const front = (
    <>
      <Solid plan={rect(x, y1 + 6, 30, 16, 3)} z0={0} z1={beamHeight} />
      <Solid plan={rect(x, cy, 46, depth, 4)} z0={beamHeight} z1={beamHeight + 11} />
      <Inset plan={rect(x, cy, 34, depth - 12, 3)} z={beamHeight + 11.2} className="seam" />
      {topArt}
      {screws([[x - 16, y0 - 2], [x + 16, y0 - 2], [x - 16, y1 + 2], [x + 16, y1 + 2]], beamHeight + 11.3)}
    </>
  );
  return { back, front };
}

const BEAM_TOP = 51.4;

const NOTE_BRIDGE = bridge(
  BRIDGE_X.note,
  <>
    <Inset plan={rect(BRIDGE_X.note, RACK.y0 + 58, 26, 60, 2)} z={BEAM_TOP} className="scr" />
    {[-22, -12, -2, 8, 18].map((dy, i) => (
      <Rule key={dy} points={[[BRIDGE_X.note - 8, RACK.y0 + 58 + dy, BEAM_TOP + 0.2], [BRIDGE_X.note + (i % 2 ? 4 : 8), RACK.y0 + 58 + dy, BEAM_TOP + 0.2]]} className="scr-line" />
    ))}
    <Solid plan={rect(BRIDGE_X.note, RACK.y1 - 54, 22, 44, 3)} z0={BEAM_TOP - 0.2} z1={BEAM_TOP + 7} top="acc" />
  </>,
);

const QUESTIONS = Array.from({ length: 12 }, (_, i) => i);

const JEV_BRIDGE = bridge(
  BRIDGE_X.jev,
  <>
    {QUESTIONS.map((i) => (
      <Inset
        key={i}
        plan={circle(BRIDGE_X.jev + (i % 2 ? 8 : -8), RACK.y0 + 22 + Math.floor(i / 2) * 16, 2.4, 10)}
        z={BEAM_TOP}
        className="seam-fill"
      />
    ))}
  </>,
);

export const NoteBridgeBack = () => <>{NOTE_BRIDGE.back}</>;
export const NoteBridgeFront = () => <>{NOTE_BRIDGE.front}</>;
export const JevBridgeBack = () => <>{JEV_BRIDGE.back}</>;
export const JevBridgeFront = () => <>{JEV_BRIDGE.front}</>;

const TIER_LEVEL: Record<Exclude<Tier, null>, number> = { safe: 1, uncertain: 2, dangerous: 3 };
const TIER_STEP_Z = [3.5, 8, 13];

/** The three-tier scale on the Jev bridge. Filled up to the latest call's tier. */
export function JevScale({ tier }: { tier: Tier }) {
  const level = tier ? TIER_LEVEL[tier] : 0;
  const yBase = RACK.y1 - 72;
  return (
    <>
      {[0, 1, 2].map((i) => (
        <path
          key={i}
          className="gauge"
          data-on={level > i}
          data-level={i}
          d={planPath(rect(BRIDGE_X.jev, yBase + i * 24, 26, 18, 2), BEAM_TOP + 0.1)}
        />
      ))}
    </>
  );
}

/* Ruler that shows how much of the run is replayed. */
const RULER_MARKS = Array.from({ length: 21 }, (_, i) => i);
export const RULER_ART: ReactNode = (() => {
  const { x0, x1, cy, d } = RULER;
  return (
    <>
      <Solid plan={rect((x0 + x1) / 2, cy, x1 - x0 + 8, d, 2)} z0={0} z1={4} top="top" />
      {RULER_MARKS.map((i) => {
        const x = x0 + ((x1 - x0) * i) / 20;
        return <Rule key={i} points={[[x, cy - d / 2 + 1, 4.2], [x, cy - (i % 5 ? 0 : -3), 4.2]]} className={i % 5 ? "tick-minor" : "tick-major"} />;
      })}
    </>
  );
})();

export function progressPath(progress: number): string {
  const { x0, x1, cy, d } = RULER;
  const end = x0 + (x1 - x0) * progress;
  const y0 = cy + 0.5;
  const y1 = cy + d / 2 - 1;
  return line([[x0, y0, 4.3], [end, y0, 4.3], [end, y1, 4.3], [x0, y1, 4.3]], true);
}

/* Peak hold: the ratchet that remembers the highest tier any frame reached. */
export function PeakArt({ tier }: { tier: Tier }) {
  const { cx, cy } = PEAK;
  const level = tier ? TIER_LEVEL[tier] : 0;
  return (
    <>
      {housing(cx, cy, 76, 118, 26)}
      {[0, 1, 2].map((i) => (
        <g key={i} className="stair" data-on={level > i}>
          <Solid plan={rect(cx, cy - 34 + i * 34, 48, 26, 3)} z0={26} z1={26 + TIER_STEP_Z[i]} />
        </g>
      ))}
      <Solid plan={rect(cx - 32, cy, 8, 96, 1.5)} z0={26} z1={30} />
      {[-30, -15, 0, 15, 30].map((dy) => (
        <Inset key={dy} plan={rect(cx - 32, cy + dy, 6, 2, 0.5)} z={30.2} className="screw" />
      ))}
      {vents(cx - 28, cx + 28, cy + 59, 8, 9, 9)}
    </>
  );
}

/* Ledger: a tray with a recessed slot for every recent result, so a tile lands where it's kept. */
const COLS = 8;
const ROWS = LEDGER_SLOTS / COLS;
const cellW = (LEDGER.x1 - LEDGER.x0 - 24) / COLS;
const cellD = (LEDGER.y1 - LEDGER.y0 - 24) / ROWS;
const TILE_W = cellW - 7;
const TILE_D = cellD - 9;

export const slotCenter = (slot: number): V2 => {
  const col = slot % COLS;
  const row = Math.floor(slot / COLS);
  return [LEDGER.x0 + 12 + cellW * (col + 0.5), LEDGER.y0 + 12 + cellD * (row + 0.5)];
};

const LEDGER_CX = (LEDGER.x0 + LEDGER.x1) / 2;
const LEDGER_CY = (LEDGER.y0 + LEDGER.y1) / 2;
const TRAY_W = LEDGER.x1 - LEDGER.x0;
const TRAY_D = LEDGER.y1 - LEDGER.y0;

export const LEDGER_BACK: ReactNode = (
  <>
    <Solid plan={rect(LEDGER_CX, LEDGER_CY, TRAY_W + 8, TRAY_D + 8, 10)} z0={0} z1={3} top="foot" />
    <Inset plan={rect(LEDGER_CX, LEDGER_CY, TRAY_W - 6, TRAY_D - 6, 6)} z={3.2} className="tray" />
    {Array.from({ length: LEDGER_SLOTS }, (_, slot) => {
      const [x, y] = slotCenter(slot);
      return <Inset key={slot} plan={rect(x, y, TILE_W + 3, TILE_D + 3, 2.5)} z={3.3} className="slot-bed" />;
    })}
    <Solid plan={rect(LEDGER_CX, LEDGER.y0 + 2, TRAY_W, 8, 3)} z0={3} z1={21} />
    <Solid plan={rect(LEDGER.x0 + 2, LEDGER_CY, 8, TRAY_D - 4, 3)} z0={3} z1={21} />
  </>
);

export const LEDGER_FRONT: ReactNode = (
  <>
    <Solid plan={rect(LEDGER.x1 - 2, LEDGER_CY, 8, TRAY_D - 4, 3)} z0={3} z1={21} />
    <Solid plan={rect(LEDGER_CX, LEDGER.y1 - 2, TRAY_W, 8, 3)} z0={3} z1={9} />
    {[-108, -36, 36, 108].map((dx) => (
      <Inset key={dx} plan={circle(LEDGER_CX + dx, LEDGER.y1 - 2, 1.5, 8)} z={9.2} className="screw" />
    ))}
  </>
);

const TILE_RISE: Record<string, number> = { safe: 7, uncertain: 13, dangerous: 21, none: 4 };

interface TileProps {
  slot: number;
  tier: Tier;
  result: Result;
  label: string;
  dropping: boolean;
  delay: number;
}

/** Height is the tier, the mark on top is the result, so neither depends on colour alone. */
export function LedgerTile({ slot, tier, result, label, dropping, delay }: TileProps) {
  const [x, y] = slotCenter(slot);
  const z1 = 4 + TILE_RISE[tier ?? "none"];
  const plan = rect(x, y, TILE_W, TILE_D, 3);
  const [fx0, fy0] = [x - TILE_W * 0.24, y - TILE_D * 0.24];
  const [fx1, fy1] = [x + TILE_W * 0.24, y + TILE_D * 0.24];
  return (
    <g className="sa-tile" data-result={result} data-drop={dropping} style={{ "--d": `${delay}ms` } as CSSProperties}>
      <title>{label}</title>
      <Solid plan={plan} z0={3.4} z1={z1} top="tile-top" />
      {result === "wrong" && (
        <>
          <Rule points={[[fx0, fy0, z1 + 0.2], [fx1, fy1, z1 + 0.2]]} className="tile-mark" />
          <Rule points={[[fx1, fy0, z1 + 0.2], [fx0, fy1, z1 + 0.2]]} className="tile-mark" />
        </>
      )}
      {result === "soft" && <Inset plan={circle(x, y, Math.min(TILE_W, TILE_D) * 0.22, 14)} z={z1 + 0.2} className="tile-ring" />}
    </g>
  );
}

/* Scoreboard: an upright board fed by the ledger and by the labels. */
const face = (x0: number, x1: number, z0: number, z1: number) => {
  const y = BOARD.cy + 5.3;
  return line([[x0, y, z0], [x1, y, z0], [x1, y, z1], [x0, y, z1]], true);
};

export const BOARD_ART: ReactNode = (() => {
  const { cx, cy, w, h } = BOARD;
  return (
    <>
      <Solid plan={rect(cx, cy + 1, w + 16, 72, 8)} z0={0} z1={5} top="foot" />
      <Inset plan={rect(cx, cy + 1, w, 58, 5)} z={5.2} className="seam" />
      <Solid plan={rect(cx, cy, w, 10, 3)} z0={5} z1={h} />
      <path className="board-face" d={face(cx - w / 2 + 6, cx + w / 2 - 6, 11, h - 6)} />
      <Rule points={[[cx - w / 2 + 16, cy + 5.4, 40], [cx + w / 2 - 16, cy + 5.4, 40]]} className="scr-line" />
      {screws([[cx - w / 2 + 12, cy + 28], [cx + w / 2 - 12, cy + 28]], 5.4)}
    </>
  );
})();

const SEGMENTS = [
  ["right", "seg-right"],
  ["soft", "seg-soft"],
  ["wrong", "seg-wrong"],
  ["none", "seg-none"],
] as const;

export function BoardBars({ board }: { board: BoardShare | null }) {
  const { cx, w } = BOARD;
  const x0 = cx - w / 2 + 16;
  const x1 = cx + w / 2 - 16;
  const full = x1 - x0;
  const z0 = 19;
  const z1 = 32;
  if (!board) return <path className="seg-empty" d={face(x0, x1, z0, z1)} />;
  const widths = SEGMENTS.map(([key]) => (board[key] / board.n) * full);
  return (
    <>
      {SEGMENTS.map(([key, className], index) => {
        if (widths[index] <= 0) return null;
        const left = x0 + widths.slice(0, index).reduce((sum, width) => sum + width, 0);
        const right = left + widths[index];
        return <path key={key} className={className} d={face(left, right - (right < x1 - 0.5 ? 1.4 : 0), z0, z1)} />;
      })}
    </>
  );
}

/* Review row */
export const DEEP_ART: ReactNode = (() => {
  const { cx, cy } = DEEP;
  return (
    <>
      {housing(cx, cy, 116, 84, 36)}
      {vents(cx - 44, cx + 44, cy + 42, 12, 15, 9)}
      <Solid plan={circle(cx - 20, cy, 20, 28)} z0={36} z1={44} />
      <Inset plan={circle(cx - 20, cy, 14, 24)} z={44.2} className="lens" />
      <Rule points={[[cx - 26, cy, 44.4], [cx - 21, cy + 6, 44.4], [cx - 13, cy - 7, 44.4]]} className="tick" />
      <Solid plan={rect(cx + 28, cy - 8, 34, 18, 3)} z0={36} z1={40} />
      <Solid plan={rect(cx + 28, cy + 16, 34, 12, 3)} z0={36} z1={39} top="acc" />
    </>
  );
})();

export const LESSONS_ART: ReactNode = (() => {
  const { cx, cy } = LESSONS;
  return (
    <>
      <Solid plan={rect(cx + 2, cy + 2, 96, 70, 6)} z0={0} z1={7} />
      <Solid plan={rect(cx - 2, cy - 1, 96, 70, 6)} z0={7} z1={14} />
      <Solid plan={rect(cx, cy, 96, 70, 6)} z0={14} z1={21} />
      <Rule points={[[cx - 34, cy - 16, 21.3], [cx + 34, cy - 16, 21.3]]} />
      <Rule points={[[cx - 34, cy - 3, 21.3], [cx + 20, cy - 3, 21.3]]} />
      <Rule points={[[cx - 34, cy + 10, 21.3], [cx + 28, cy + 10, 21.3]]} />
      <Rule points={[[cx - 34, cy + 22, 21.3], [cx + 8, cy + 22, 21.3]]} />
    </>
  );
})();

export const CHECKER_ART: ReactNode = (() => {
  const { cx, cy } = CHECKER;
  return (
    <>
      {housing(cx, cy, 108, 78, 32)}
      <Solid plan={circle(cx - 18, cy, 16, 24)} z0={32} z1={39} />
      <Inset plan={circle(cx - 18, cy, 11, 20)} z={39.2} className="lens" />
      <Solid plan={rect(cx + 26, cy, 30, 16, 3)} z0={32} z1={35} />
      {vents(cx - 40, cx + 40, cy + 39, 10, 13, 9)}
    </>
  );
})();
