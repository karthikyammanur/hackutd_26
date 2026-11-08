/**
 * A small axonometric camera for the pipeline bench. World units: x runs right, y runs toward the
 * viewer, z is up. Everything here is pure and runs once at module load.
 */

export type V2 = [number, number];
export type V3 = [number, number, number];

const AZIMUTH = (17 * Math.PI) / 180;
const ELEVATION = (43 * Math.PI) / 180;
const cosA = Math.cos(AZIMUTH);
const sinA = Math.sin(AZIMUTH);
const sinE = Math.sin(ELEVATION);
const cosE = Math.cos(ELEVATION);

/** World extents of the bench. Labels sit inside it, so this is also the frame of the figure. */
export const WORLD = { width: 1010, depth: 792 };

const rawProject = (x: number, y: number, z: number): V2 => [x * cosA - y * sinA, (x * sinA + y * cosA) * sinE - z * cosE];

const corners: V2[] = [
  rawProject(0, 0, 0),
  rawProject(WORLD.width, 0, 92),
  rawProject(0, WORLD.depth, -16),
  rawProject(WORLD.width, WORLD.depth, -16),
];
const PAD = { left: 10, right: 10, top: 12, bottom: 12 };
const minX = Math.min(...corners.map((c) => c[0])) - PAD.left;
const minY = Math.min(...corners.map((c) => c[1])) - PAD.top;

export const VIEW = {
  width: Math.round(Math.max(...corners.map((c) => c[0])) - minX + PAD.right),
  height: Math.round(Math.max(...corners.map((c) => c[1])) - minY + PAD.bottom),
};

export const project = (x: number, y: number, z = 0): V2 => {
  const [sx, sy] = rawProject(x, y, z);
  return [sx - minX, sy - minY];
};

/** Depth along the view, for back-to-front sorting. */
export const depthOf = (x: number, y: number) => x * sinA + y * cosA;

const n = (v: number) => Number(v.toFixed(1));

export const pathOf = (points: V2[], close = false) =>
  `M${points.map(([x, y]) => `${n(x)} ${n(y)}`).join("L")}${close ? "Z" : ""}`;

/** Projects a list of world points into an SVG path. */
export const line = (points: V3[], close = false) => pathOf(points.map(([x, y, z]) => project(x, y, z)), close);

type Plan = V2[];

function cornerArc(prev: V2, at: V2, next: V2, radius: number, steps: number): V2[] {
  const toPrev: V2 = [prev[0] - at[0], prev[1] - at[1]];
  const toNext: V2 = [next[0] - at[0], next[1] - at[1]];
  const lenPrev = Math.hypot(...toPrev);
  const lenNext = Math.hypot(...toNext);
  const t = Math.min(radius, lenPrev / 2, lenNext / 2);
  const a: V2 = [at[0] + (toPrev[0] / lenPrev) * t, at[1] + (toPrev[1] / lenPrev) * t];
  const b: V2 = [at[0] + (toNext[0] / lenNext) * t, at[1] + (toNext[1] / lenNext) * t];
  const out: V2[] = [];
  for (let i = 0; i <= steps; i += 1) {
    const u = i / steps;
    const v = 1 - u;
    out.push([v * v * a[0] + 2 * v * u * at[0] + u * u * b[0], v * v * a[1] + 2 * v * u * at[1] + u * u * b[1]]);
  }
  return out;
}

/** Rounds every corner of a closed polygon, convex or concave. */
export function roundPlan(points: Plan, radius: number, steps = 4): Plan {
  return points.flatMap((at, i) =>
    cornerArc(points[(i + points.length - 1) % points.length], at, points[(i + 1) % points.length], radius, steps),
  );
}

/** A plan rectangle centred on (cx, cy). */
export const rect = (cx: number, cy: number, w: number, d: number, r = 6): Plan =>
  roundPlan(
    [
      [cx - w / 2, cy - d / 2],
      [cx + w / 2, cy - d / 2],
      [cx + w / 2, cy + d / 2],
      [cx - w / 2, cy + d / 2],
    ],
    r,
  );

export const circle = (cx: number, cy: number, r: number, steps = 24): Plan =>
  Array.from({ length: steps }, (_, i): V2 => {
    const a = (i / steps) * Math.PI * 2;
    return [cx + Math.cos(a) * r, cy + Math.sin(a) * r];
  });

export const planPath = (plan: Plan, z = 0) => line(plan.map(([x, y]): V3 => [x, y, z]), true);

export type Tone = "s1" | "s2" | "s3";

export interface PrismPaths {
  top: string;
  sides: { d: string; tone: Tone }[];
}

/** Extrudes a plan into the side strips the camera can see, shaded by facing. */
export function prism(plan: Plan, z0: number, z1: number): PrismPaths {
  const area = plan.reduce((sum, [x, y], i) => {
    const [nx, ny] = plan[(i + 1) % plan.length];
    return sum + x * ny - nx * y;
  }, 0);
  const flip = area < 0 ? -1 : 1;

  const sides: PrismPaths["sides"] = [];
  let run: { from: number; to: number; tone: Tone } | null = null;

  const flush = () => {
    if (!run) return;
    const upper: V3[] = [];
    const lower: V3[] = [];
    for (let i = run.from; i <= run.to; i += 1) {
      const [x, y] = plan[i % plan.length];
      upper.push([x, y, z1]);
      lower.unshift([x, y, z0]);
    }
    sides.push({ d: line([...upper, ...lower], true), tone: run.tone });
    run = null;
  };

  for (let i = 0; i < plan.length; i += 1) {
    const [x0, y0] = plan[i];
    const [x1, y1] = plan[(i + 1) % plan.length];
    const len = Math.hypot(x1 - x0, y1 - y0) || 1;
    const nx = ((y1 - y0) / len) * flip;
    const ny = (-(x1 - x0) / len) * flip;
    if (nx * sinA + ny * cosA <= 0) {
      flush();
      continue;
    }
    const light = nx * -0.35 + ny * 0.94;
    const tone: Tone = light > 0.72 ? "s1" : light > 0.2 ? "s2" : "s3";
    if (run && run.tone === tone && run.to === i) {
      run.to = i + 1;
    } else {
      flush();
      run = { from: i, to: i + 1, tone };
    }
  }
  flush();
  return { top: planPath(plan, z1), sides };
}

/** Rounds the corners of an open floor route and projects it. Returns the path and its arrowhead. */
export function route(points: V2[], radius = 13, z = 0.6) {
  const rounded: V2[] = [points[0]];
  for (let i = 1; i < points.length - 1; i += 1) {
    rounded.push(...cornerArc(points[i - 1], points[i], points[i + 1], radius, 6));
  }
  rounded.push(points[points.length - 1]);

  const end = points[points.length - 1];
  const before = points[points.length - 2];
  const len = Math.hypot(end[0] - before[0], end[1] - before[1]) || 1;
  const ux = (end[0] - before[0]) / len;
  const uy = (end[1] - before[1]) / len;
  const head: V3[] = [
    [end[0] - ux * 2, end[1] - uy * 2, z],
    [end[0] - ux * 13 - uy * 6.5, end[1] - uy * 13 + ux * 6.5, z],
    [end[0] - ux * 13 + uy * 6.5, end[1] - uy * 13 - ux * 6.5, z],
  ];

  return {
    d: line(rounded.map(([x, y]): V3 => [x, y, z])),
    head: line(head, true),
    tail: project(points[0][0], points[0][1], z),
  };
}
