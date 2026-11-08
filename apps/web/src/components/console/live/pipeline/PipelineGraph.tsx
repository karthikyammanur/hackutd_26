import { useState, type CSSProperties } from "react";
import { PIPELINE_NODES, type CallPhase, type CallTrace, type NodeId } from "@/lib/console/call-model";
import {
  COL,
  footprint,
  HATCH_ID,
  JevScale,
  PARTS,
  ROW,
  shadowOf,
  Tile,
  TILE_SLOTS,
  WindowBack,
  WindowFront,
  WIRES,
  type Part,
} from "./bench";
import { depthOf, planPath, prism, project, roundPlan, VIEW, WORLD, type V2 } from "./iso";
import "./pipeline.css";

export interface PipelineGraphProps {
  trace: CallTrace;
  selected: NodeId | null;
  onSelect: (node: NodeId) => void;
}

type StageId = "setup" | "live" | "after";

const STAGE_OF: Record<CallPhase, StageId> = {
  connecting: "setup",
  live: "live",
  checking: "after",
  responding: "after",
  deleted: "after",
};

const { width: W, depth: D } = WORLD;
const [r0, r1, r2] = ROW;
const seamA = (r0 + r1) / 2 + 22;
const seamB = (r1 + r2) / 2 + 30;
const liveLeft = COL[0] + 112;
const tabLeft = COL[3] + 72;

const PLATES: { id: StageId; plan: V2[] }[] = [
  {
    id: "setup",
    plan: [
      [0, 0],
      [COL[1] + 180, 0],
      [COL[1] + 180, seamA - 6],
      [0, seamA - 6],
    ],
  },
  {
    id: "live",
    plan: [
      [0, seamA + 6],
      [tabLeft, seamA + 6],
      [tabLeft, 0],
      [W, 0],
      [W, seamB - 6],
      [liveLeft, seamB - 6],
      [liveLeft, D],
      [0, D],
    ],
  },
  {
    id: "after",
    plan: [
      [liveLeft + 12, seamB + 6],
      [W, seamB + 6],
      [W, D],
      [liveLeft + 12, D],
    ],
  },
];

const pct = (value: number, total: number) => `${(value / total) * 100}%`;

const CAPTION_W = 214;

function placement(part: Part) {
  const halfW = part.w / 2;
  const halfD = part.d / 2;
  const top = project(part.cx, part.cy - halfD, part.h)[1] - 6;
  const [frontX, frontY] = project(part.cx, part.cy + halfD, 0);

  if (part.caption === "right") {
    const [rightX, rightY] = project(part.cx + halfW, part.cy, 0);
    const left = project(part.cx - halfW, part.cy, 0)[0] - 4;
    const captionLeft = rightX + 12;
    const bottom = frontY + 6;
    const width = captionLeft + CAPTION_W - left;
    return {
      style: { left: pct(left, VIEW.width), top: pct(top, VIEW.height), width: pct(width, VIEW.width), height: pct(bottom - top, VIEW.height) },
      caption: {
        left: pct(captionLeft - left, width),
        top: pct(rightY - 30 - top, bottom - top),
        width: pct(CAPTION_W, width),
      },
    };
  }

  const captionTop = frontY + 10;
  const bottom = captionTop + 92;
  const captionW = part.captionWidth ?? CAPTION_W;
  const left = frontX - captionW / 2 + (part.captionShift ?? 0);
  return {
    style: { left: pct(left, VIEW.width), top: pct(top, VIEW.height), width: pct(captionW, VIEW.width), height: pct(bottom - top, VIEW.height) },
    caption: {
      left: "0%",
      top: pct(captionTop - top, bottom - top),
      width: "100%",
      textAlign: "center" as const,
    },
  };
}

const PLACEMENTS = Object.fromEntries(
  PIPELINE_NODES.map((node) => [node.id, placement(PARTS[node.id])]),
) as Record<NodeId, ReturnType<typeof placement>>;

const DRAW_ORDER = [...PIPELINE_NODES]
  .map((node) => node.id)
  .sort((a, b) => depthOf(PARTS[a].cx, PARTS[a].cy) - depthOf(PARTS[b].cx, PARTS[b].cy));

const anchor = (x: number, y: number): CSSProperties => {
  const [sx, sy] = project(x, y);
  return { left: pct(sx, VIEW.width), top: pct(sy, VIEW.height) };
};

function Plates({ now }: { now: StageId }) {
  return (
    <>
      {PLATES.map(({ id, plan }) => {
        const rounded = roundPlan(plan, 16, 5);
        const { sides, top } = prism(rounded, -15, 0);
        return (
          <g key={id} className="ss-plate" data-now={id === now}>
            {sides.map((side, i) => (
              <path key={i} className={`s ${side.tone}`} d={side.d} />
            ))}
            <path className="top" d={top} />
            {id === "setup" ? (
              <path d={planPath(rounded, 0.3)} fill={`url(#${HATCH_ID})`} opacity={0.16} />
            ) : null}
          </g>
        );
      })}
    </>
  );
}

export function PipelineGraph({ trace, selected, onSelect }: PipelineGraphProps) {
  const [hot, setHot] = useState<NodeId | null>(null);
  const stage = STAGE_OF[trace.phase];
  const erased = trace.phase === "deleted";
  const held = trace.past.filter((beat) => beat.links.includes("base>window") || beat.links.includes("window>jev")).length;
  const tiles = Math.min(TILE_SLOTS.length, held);
  const jevLit = trace.nodes.jev.state !== "idle";
  const windowPart = PARTS.window;

  return (
    <div
      className="ss-pipe"
      data-tier={trace.tier}
      role="group"
      aria-label="How this call moves through Safe Signal"
      style={{ aspectRatio: `${VIEW.width} / ${VIEW.height}` }}
    >
      <svg viewBox={`0 0 ${VIEW.width} ${VIEW.height}`} aria-hidden="true" focusable="false">
        <defs>
          <pattern id={HATCH_ID} width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(-38)">
            <rect width="1" height="7" fill="#8a8a8a" />
          </pattern>
          <filter id="ss-pipeline-soft" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="8" />
          </filter>
        </defs>

        <Plates now={stage} />

        <g filter="url(#ss-pipeline-soft)" opacity="0.14">
          {PIPELINE_NODES.map((node) => (
            <path key={node.id} d={shadowOf(PARTS[node.id])} fill="#000" />
          ))}
        </g>

        {WIRES.map((wire) => {
          const state = trace.links[wire.id];
          return (
            <g key={wire.id} className="ss-wire" data-state={state}>
              <path className="bed" d={wire.d} />
              {state === "active" ? <path className="halo" d={wire.d} /> : null}
              <path className="trace" d={wire.d} />
              <circle className="tail" cx={wire.tail[0]} cy={wire.tail[1]} r="3.2" />
              <path className="head" d={wire.head} />
              {state === "active" ? (
                <>
                  <path className="packet-drop" d={wire.d} />
                  <path className="packet" d={wire.d} />
                </>
              ) : null}
            </g>
          );
        })}

        {DRAW_ORDER.map((id) => {
          const part = PARTS[id];
          return (
            <g
              key={id}
              className="ss-node"
              data-state={trace.nodes[id].state}
              data-selected={selected === id}
              data-hot={hot === id}
            >
              <path className="ss-foot" d={footprint(part)} />
              {id === "window" ? (
                <>
                  <WindowBack />
                  {TILE_SLOTS.map((_, i) => (
                    <g
                      key={i}
                      className="ss-tile"
                      data-held={i < tiles && !erased}
                      style={{ "--i": i } as CSSProperties}
                    >
                      <Tile cx={windowPart.cx} cy={windowPart.cy} slot={i} />
                    </g>
                  ))}
                  <WindowFront />
                </>
              ) : (
                part.art
              )}
              {id === "jev" ? <JevScale cx={part.cx} cy={part.cy} tier={trace.tier} lit={jevLit} /> : null}
            </g>
          );
        })}
      </svg>

      <div className="ss-stage" data-now={stage === "setup"} style={anchor(196, 14)}>
        Setup
        <small>Simulated</small>
      </div>
      <div className="ss-stage" data-now={stage === "live"} style={anchor(84, seamA + 22)}>
        Live
      </div>
      <div className="ss-stage" data-now={stage === "after"} style={anchor(COL[1] + 122, seamB + 26)}>
        After the call
      </div>

      <div
        className="ss-now"
        style={{
          ...anchor(COL[1] + 194, 34),
          width: pct(tabLeft - COL[1] - 204, VIEW.width),
        }}
      >
        <div className="ss-now-mark">{trace.now.marker}</div>
        <div className="ss-legend">
          <span>
            <i className="ss-key" data-kind="now" /> Moving now
          </span>
          <span>
            <i className="ss-key" /> Already used
          </span>
        </div>
      </div>

      {PIPELINE_NODES.map((node) => {
        const { state, status } = trace.nodes[node.id];
        const place = PLACEMENTS[node.id];
        return (
          <button
            key={node.id}
            type="button"
            className="ss-hit"
            data-state={state}
            data-erased={node.id === "window" && erased}
            style={place.style}
            aria-pressed={selected === node.id}
            aria-label={`${node.name}${node.kind === "simulated" ? ", simulated" : ""}: ${status}`}
            onClick={() => onSelect(node.id)}
            onPointerEnter={() => setHot(node.id)}
            onPointerLeave={() => setHot((cur) => (cur === node.id ? null : cur))}
            onFocus={() => setHot(node.id)}
            onBlur={() => setHot((cur) => (cur === node.id ? null : cur))}
          >
            <span className="ss-cap" style={place.caption}>
              <span className="ss-name">{node.name}</span>
              <span className="ss-status">{status}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
