import type { ReactNode } from "react";
import type { LinkId, NodeId } from "@/lib/console/call-model";
import { circle, line, planPath, prism, rect, route, type V2, type V3 } from "./iso";

/** The bench: where every part stands and how each trace runs between them. */

export const COL = [130, 320, 510, 700, 890] as const;
export const ROW = [96, 356, 634] as const;

export const HATCH_ID = "ss-pipeline-hatch";

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

const Hatch = ({ plan, z }: { plan: Plan; z: number }) => (
  <path className="hatch" d={planPath(plan, z)} fill={`url(#${HATCH_ID})`} />
);

const Rule = ({ points, className = "rule" }: { points: V3[]; className?: string }) => (
  <path className={className} d={line(points)} />
);

/** Short slits across a front face, the vents of a housing. */
const vents = (x0: number, x1: number, y: number, z: number, count: number, gap = 7): ReactNode =>
  Array.from({ length: count }, (_, i) => {
    const x = x0 + ((x1 - x0) * i) / Math.max(1, count - 1);
    return <Rule key={i} points={[[x, y, z], [x, y, z + gap]]} />;
  });

const screws = (points: V2[], z: number): ReactNode =>
  points.map(([x, y], i) => <Inset key={i} plan={circle(x, y, 2.1, 8)} z={z} className="screw" />);

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

function phoneFlat(cx: number, cy: number, dark = false): ReactNode {
  const h = 9;
  return (
    <g className={dark ? "dark" : undefined}>
      <Solid plan={rect(cx, cy, 46, 84, 10)} z0={0} z1={h} />
      <Inset plan={rect(cx, cy - 1, 37, 66, 6)} z={h + 0.2} className="scr" />
      <Inset plan={rect(cx, cy - 37, 12, 3, 1.5)} z={h + 0.2} className="screw" />
      <Inset plan={circle(cx, cy + 36, 3, 12)} z={h + 0.2} className="seam" />
      <Rule points={[[cx - 12, cy - 16, h + 0.3], [cx + 12, cy - 16, h + 0.3]]} className="scr-line" />
      <Rule points={[[cx - 12, cy - 6, h + 0.3], [cx + 8, cy - 6, h + 0.3]]} className="scr-line" />
      <Rule points={[[cx - 12, cy + 4, h + 0.3], [cx + 12, cy + 4, h + 0.3]]} className="scr-line" />
    </g>
  );
}

const trigger = (cx: number, cy: number): ReactNode => (
  <>
    <Solid plan={rect(cx, cy, 84, 62, 10)} z0={0} z1={8} />
    <Hatch plan={rect(cx, cy, 84, 62, 10)} z={8.2} />
    <Inset plan={circle(cx, cy, 24, 28)} z={8.3} className="seam" />
    <g className="press">
      <Solid plan={circle(cx, cy, 19, 28)} z0={8} z1={18} top="acc" />
      <Inset plan={circle(cx, cy, 13, 24)} z={18.2} className="acc-rim" />
    </g>
  </>
);

const mcp = (cx: number, cy: number): ReactNode => (
  <>
    <Solid plan={rect(cx, cy, 96, 62, 8)} z0={0} z1={24} />
    <Hatch plan={rect(cx, cy, 96, 62, 8)} z={24.2} />
    <Solid plan={rect(cx - 22, cy, 26, 20, 3)} z0={24} z1={30} top="acc" />
    <Solid plan={rect(cx + 22, cy, 26, 20, 3)} z0={24} z1={30} top="acc" />
    {vents(cx - 34, cx + 34, cy + 31, 9, 9)}
  </>
);

const base = (cx: number, cy: number): ReactNode => (
  <>
    {housing(cx, cy, 146, 74, 38)}
    <Inset plan={rect(cx - 30, cy, 58, 24, 4)} z={38.3} className="acc" />
    {[0, 1, 2, 3, 4, 5].map((i) => (
      <Inset key={i} plan={rect(cx + 8 + i * 9, cy, 5, 22, 1.5)} z={38.3} className="seam-fill" />
    ))}
    {vents(cx - 60, cx + 60, cy + 37, 13, 21, 10)}
  </>
);

const windowBack = (cx: number, cy: number): ReactNode => (
  <>
    <Solid plan={rect(cx, cy, 142, 96, 10)} z0={0} z1={4} top="foot" />
    <Inset plan={rect(cx, cy, 124, 78, 6)} z={4.2} className="tray" />
    <Solid plan={rect(cx, cy - 42, 134, 10, 4)} z0={4} z1={30} />
    <Solid plan={rect(cx - 62, cy, 10, 88, 4)} z0={4} z1={30} />
  </>
);

const windowFront = (cx: number, cy: number): ReactNode => (
  <>
    <Solid plan={rect(cx + 62, cy, 10, 88, 4)} z0={4} z1={30} />
    <Solid plan={rect(cx, cy + 42, 134, 10, 4)} z0={4} z1={15} />
    {[-48, -16, 16, 48].map((dx) => (
      <Inset key={dx} plan={circle(cx + dx, cy + 42, 1.6, 8)} z={15.2} className="screw" />
    ))}
  </>
);

export const TILE_SLOTS: V2[] = [
  [-42, -22],
  [-14, -22],
  [14, -22],
  [42, -22],
  [-42, 12],
  [-14, 12],
  [14, 12],
  [42, 12],
];

export function Tile({ cx, cy, slot }: { cx: number; cy: number; slot: number }) {
  const [dx, dy] = TILE_SLOTS[slot];
  return <Solid plan={rect(cx + dx, cy + dy, 24, 28, 4)} z0={5} z1={14} top="tile-top" />;
}

const jev = (cx: number, cy: number): ReactNode => (
  <>
    {housing(cx, cy, 104, 72, 40)}
    {vents(cx - 40, cx + 40, cy + 36, 15, 13, 9)}
  </>
);

export function JevScale({ cx, cy, tier, lit }: { cx: number; cy: number; tier: number; lit: boolean }) {
  return (
    <>
      {[0, 1, 2, 3].map((i) => (
        <path
          key={i}
          className="gauge"
          data-on={lit && tier >= i}
          data-level={i}
          d={planPath(rect(cx - 27 + i * 18, cy, 14, 20 + i * 6, 2.5), 40.4)}
        />
      ))}
    </>
  );
}

const alerting = (cx: number, cy: number): ReactNode => (
  <>
    {housing(cx, cy, 96, 72, 34)}
    {vents(cx - 36, cx + 36, cy + 36, 12, 11, 9)}
    <Solid plan={circle(cx, cy, 20, 28)} z0={34} z1={38} top="foot" />
    <Solid plan={circle(cx, cy, 13, 28)} z0={38} z1={52} top="beacon" />
    <Inset plan={circle(cx, cy, 7, 20)} z={52.2} className="beacon-core" />
  </>
);

function tlife(cx: number, cy: number): ReactNode {
  const x0 = cx - 25;
  const x1 = cx + 25;
  const y = cy + 6;
  const z0 = 6;
  const z1 = 92;
  return (
    <>
      <Solid plan={rect(cx, cy, 74, 34, 8)} z0={0} z1={6} top="foot" />
      <Solid plan={rect(cx, cy, 50, 12, 3)} z0={z0} z1={z1} />
      <path className="scr" d={line([[x0 + 4, y, z0 + 4], [x1 - 4, y, z0 + 4], [x1 - 4, y, z1 - 4], [x0 + 4, y, z1 - 4]], true)} />
      <path className="msg" d={line([[x0 + 9, y, z1 - 26], [x1 - 9, y, z1 - 26], [x1 - 9, y, z1 - 12], [x0 + 9, y, z1 - 12]], true)} />
      <Rule points={[[x0 + 10, y, z1 - 36], [x1 - 10, y, z1 - 36]]} className="scr-line" />
      <Rule points={[[x0 + 10, y, z1 - 44], [x1 - 16, y, z1 - 44]]} className="scr-line" />
    </>
  );
}

const check = (cx: number, cy: number): ReactNode => (
  <>
    {housing(cx, cy, 104, 72, 34)}
    {vents(cx - 40, cx + 40, cy + 36, 12, 13, 9)}
    <Solid plan={circle(cx - 16, cy, 17, 28)} z0={34} z1={42} />
    <Inset plan={circle(cx - 16, cy, 12, 24)} z={42.2} className="lens" />
    <Rule
      points={[[cx - 21, cy, 42.4], [cx - 17, cy + 5, 42.4], [cx - 10, cy - 6, 42.4]]}
      className="tick"
    />
    <Solid plan={rect(cx + 26, cy, 28, 16, 3)} z0={34} z1={37} />
  </>
);

const lessons = (cx: number, cy: number): ReactNode => (
  <>
    <Solid plan={rect(cx + 2, cy + 2, 92, 66, 6)} z0={0} z1={7} />
    <Solid plan={rect(cx - 2, cy - 1, 92, 66, 6)} z0={7} z1={14} />
    <Solid plan={rect(cx, cy, 92, 66, 6)} z0={14} z1={21} />
    <Rule points={[[cx - 32, cy - 14, 21.3], [cx + 32, cy - 14, 21.3]]} />
    <Rule points={[[cx - 32, cy - 2, 21.3], [cx + 18, cy - 2, 21.3]]} />
    <Rule points={[[cx - 32, cy + 10, 21.3], [cx + 26, cy + 10, 21.3]]} />
  </>
);

const callback = (cx: number, cy: number): ReactNode => (
  <>
    <Solid plan={rect(cx, cy, 88, 66, 12)} z0={0} z1={20} />
    <Inset plan={rect(cx, cy + 12, 42, 28, 3)} z={20.2} className="seam" />
    {[-12, 0, 12].flatMap((dx) =>
      [-1, 1].map((row) => <Inset key={`${dx}${row}`} plan={circle(cx + dx, cy + 12 + row * 7, 2.3, 8)} z={20.3} className="acc" />),
    )}
    <Solid plan={rect(cx, cy - 18, 72, 15, 7)} z0={20} z1={30} />
    <Solid plan={circle(cx - 28, cy - 18, 10, 18)} z0={30} z1={35} top="acc" />
    <Solid plan={circle(cx + 28, cy - 18, 10, 18)} z0={30} z1={35} top="acc" />
  </>
);

const purge = (cx: number, cy: number): ReactNode => (
  <>
    {housing(cx, cy, 104, 72, 36)}
    <Inset plan={rect(cx, cy - 4, 72, 12, 3)} z={36.4} className="slot" />
    {vents(cx - 40, cx + 40, cy + 36, 10, 11, 14)}
  </>
);

export interface Part {
  cx: number;
  cy: number;
  /** Half extents of the footprint, used for the selection outline and hit area. */
  w: number;
  d: number;
  /** Height of the tallest piece, used for the hit area. */
  h: number;
  /** Where the caption sits relative to the part. */
  caption?: "below" | "right";
  /** Nudges a caption sideways, in view units, to clear a neighbouring trace. */
  captionShift?: number;
  /** Caption width in view units, for parts with longer status lines. */
  captionWidth?: number;
  art?: ReactNode;
}

export const PARTS: Record<NodeId, Part> = {
  trigger: { cx: COL[1], cy: ROW[0], w: 92, d: 70, h: 18, caption: "right", art: trigger(COL[1], ROW[0]) },
  mcp: { cx: COL[0], cy: ROW[0], w: 104, d: 70, h: 30, art: mcp(COL[0], ROW[0]) },
  customer: { cx: COL[0], cy: ROW[1], w: 54, d: 92, h: 9, art: phoneFlat(COL[0], ROW[1]) },
  caller: { cx: COL[0], cy: ROW[2], w: 54, d: 92, h: 9, art: phoneFlat(COL[0], ROW[2], true) },
  base: { cx: COL[1], cy: ROW[1], w: 154, d: 82, h: 38, captionShift: -34, art: base(COL[1], ROW[1]) },
  window: { cx: COL[2], cy: ROW[1], w: 150, d: 104, h: 30, captionShift: -24, captionWidth: 262 },
  jev: { cx: COL[3], cy: ROW[1], w: 112, d: 80, h: 40, art: jev(COL[3], ROW[1]) },
  alerting: { cx: COL[4], cy: ROW[1], w: 104, d: 80, h: 52, art: alerting(COL[4], ROW[1]) },
  tlife: { cx: COL[4], cy: ROW[0], w: 82, d: 42, h: 92, captionShift: -32, art: tlife(COL[4], ROW[0]) },
  purge: { cx: COL[1], cy: ROW[2], w: 112, d: 80, h: 36, art: purge(COL[1], ROW[2]) },
  lessons: { cx: COL[2], cy: ROW[2], w: 100, d: 74, h: 21, art: lessons(COL[2], ROW[2]) },
  check: { cx: COL[3], cy: ROW[2], w: 112, d: 80, h: 42, art: check(COL[3], ROW[2]) },
  callback: { cx: COL[4], cy: ROW[2], w: 96, d: 74, h: 35, art: callback(COL[4], ROW[2]) },
};

export const WindowBack = () => <>{windowBack(COL[2], ROW[1])}</>;
export const WindowFront = () => <>{windowFront(COL[2], ROW[1])}</>;

const [c0, c1, c2, c3, c4] = COL;
const [r0, r1, r2] = ROW;
const gutter = { outerA: 30, outerB: 54, g0: 226, g1: 416, g2: 606, g3: 796, g4: 975 };

/** Every trace runs on the bench from its source to its target, so dashes travel the right way. */
const ROUTES: Record<LinkId, V2[]> = {
  "trigger>base": [[c1, r0 + 34], [c1, r1 - 40]],
  "base>mcp": [[c1 - 58, r1 - 40], [c1 - 58, r0], [c0 + 52, r0]],
  "mcp>customer": [[c0 - 48, r0 + 9], [gutter.outerB, r0 + 9], [gutter.outerB, r1], [c0 - 27, r1]],
  "mcp>caller": [[c0 - 48, r0 - 9], [gutter.outerA, r0 - 9], [gutter.outerA, r2], [c0 - 27, r2]],
  "customer>base": [[c0 + 27, r1 - 14], [c1 - 77, r1 - 14]],
  "caller>base": [[c0 + 27, r2], [gutter.g0, r2], [gutter.g0, r1 + 16], [c1 - 77, r1 + 16]],
  "base>window": [[c1 + 77, r1 - 14], [c2 - 72, r1 - 14]],
  "window>jev": [[c2 + 72, r1 - 14], [c3 - 57, r1 - 14]],
  "jev>alerting": [[c3 + 57, r1 - 14], [c4 - 53, r1 - 14]],
  "alerting>tlife": [[c4 + 53, r1 - 14], [gutter.g4, r1 - 14], [gutter.g4, r0], [c4 + 28, r0]],
  "window>check": [[c2 + 72, r1 + 24], [gutter.g2, r1 + 24], [gutter.g2, r2 - 14], [c3 - 57, r2 - 14]],
  "lessons>check": [[c2 + 50, r2 + 14], [c3 - 57, r2 + 14]],
  "check>alerting": [[c3 + 57, r2], [gutter.g3, r2], [gutter.g3, r1 + 16], [c4 - 53, r1 + 16]],
  "alerting>callback": [[c4 + 53, r1 + 14], [gutter.g4, r1 + 14], [gutter.g4, r2], [c4 + 48, r2]],
  "window>purge": [[c2 - 72, r1 + 24], [gutter.g1, r1 + 24], [gutter.g1, r2], [c1 + 57, r2]],
};

export const WIRES = (Object.keys(ROUTES) as LinkId[]).map((id) => ({ id, ...route(ROUTES[id]) }));

export const footprint = (part: Part) => planPath(rect(part.cx, part.cy, part.w + 14, part.d + 14, 12), 0.4);

export const shadowOf = (part: Part) => planPath(rect(part.cx + 4, part.cy + 10, part.w, part.d, 12), 0.2);
