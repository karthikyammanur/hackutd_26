import { useMemo, useState, type CSSProperties, type ReactNode } from "react";
import { formatPercent } from "@/lib/console/format";
import { ms, show } from "@/lib/simulate/labels";
import type { Decision, Lessons, LiveState, Marker, MethodRow } from "@/lib/simulate/parse";
import { prism, roundPlan } from "../../live/pipeline/iso";
import { Card } from "../../ui";
import {
  BoardBars,
  BOARD_ART,
  CHECKER_ART,
  CUTTER_ART,
  DECK_ART,
  DEEP_ART,
  HATCH_ID,
  JevBridgeBack,
  JevBridgeFront,
  JevScale,
  laneArt,
  LedgerTile,
  LEDGER_BACK,
  LEDGER_FRONT,
  LESSONS_ART,
  NoteBridgeBack,
  NoteBridgeFront,
  PeakArt,
  progressPath,
  RACK_BASE,
  railY,
  RULER_ART,
} from "./art";
import { anchor, BOARD, BRIDGE_X, CAPTIONS, PLATES, RACK, RULER, VB, WIRES } from "./layout";
import {
  advanceLedger,
  EMPTY_LEDGER,
  figureView,
  STEP_LABELS,
  stepName,
  type FigureInput,
  type Ledger,
  type Light,
  type StationId,
} from "./model";
import "./architecture.css";

export interface ArchitectureFigureProps {
  live: LiveState | null;
  active: string[];
  seen: Decision[];
  markers: Marker[] | null;
  lessons: Lessons | null;
  byMethod: MethodRow[] | null;
  score: number | null;
  paused: boolean;
}

/** Lanes drawn before a run reports its own count. Matches the run form's default. */
const RESTING_LANES = 8;

/** The machines keep their calm colour while the lanes and tiles carry the motion. */
const quiet = (state: Light): Light => (state === "active" ? "idle" : state);

function useLedger(seen: Decision[]): Ledger {
  const [state, setState] = useState({ seen, ledger: advanceLedger(EMPTY_LEDGER, seen) });
  if (state.seen !== seen) {
    const next = { seen, ledger: advanceLedger(state.ledger, seen) };
    setState(next);
    return next.ledger;
  }
  return state.ledger;
}

function Plates({ now }: { now: { replay: boolean; log: boolean; after: boolean } }) {
  return (
    <>
      {(Object.entries(PLATES) as [keyof typeof PLATES, (typeof PLATES)["replay"]][]).map(([id, plan]) => {
        const rounded = roundPlan(plan, 16, 5);
        const { sides, top } = prism(rounded, -15, 0);
        return (
          <g key={id} className="sa-plate" data-now={now[id]}>
            {sides.map((side, i) => (
              <path key={i} className={`s ${side.tone}`} d={side.d} />
            ))}
            <path className="top" d={top} />
          </g>
        );
      })}
    </>
  );
}

function Lanes({ total, running, settled }: { total: number; running: number; settled: boolean }) {
  const pitch = (RACK.y1 - RACK.y0) / total;
  const lanes = useMemo(() => Array.from({ length: total }, (_, i) => laneArt(railY(i, total), pitch)), [total, pitch]);
  return (
    <>
      {lanes.map((lane, i) => {
        const on = i < running;
        return (
          <g key={i} className="sa-lane" data-state={on ? "run" : settled ? "done" : "off"}>
            {lane.rail}
            {on && (
              <g
                className="sa-shuttle"
                style={{ "--dx": `${lane.travel[0]}px`, "--dy": `${lane.travel[1]}px`, "--delay": `${(i * -0.37) % 2.8}s` } as CSSProperties}
              >
                {lane.shuttle}
              </g>
            )}
            <path className="sa-lamp" d={lane.lamp} />
          </g>
        );
      })}
    </>
  );
}

function Caption({ id, name, status, state }: { id: StationId; name: string; status: string; state: string }) {
  const { at, width, place } = CAPTIONS[id];
  return (
    <div
      className="sa-cap"
      data-place={place}
      data-state={state}
      style={{ ...anchor(at[0], at[1], at[2]), width: `${(width / VB.width) * 100}%` }}
    >
      <span className="sa-name">{name}</span>
      <span className="sa-status">{status}</span>
    </div>
  );
}

const STATION_ART: Partial<Record<StationId, ReactNode>> = {
  deck: DECK_ART,
  cut: CUTTER_ART,
  board: BOARD_ART,
  deep: DEEP_ART,
  lessons: LESSONS_ART,
  checker: CHECKER_ART,
};

export function ArchitectureFigure(props: ArchitectureFigureProps) {
  const ledger = useLedger(props.seen);
  const input: FigureInput = props;
  const view = figureView(input);
  const { phase, stations, wires, lanes } = view;
  const configured = lanes.configured ?? RESTING_LANES;
  const running = Math.min(lanes.running ?? 0, configured);
  const settled = phase === "done";
  const scoreText = props.score === null ? "--" : formatPercent(props.score);

  return (
    <Card className="relative overflow-hidden px-[22px] pt-5 pb-[18px]">
      <div
        className="absolute top-0 left-0 h-[3px] bg-mag transition-[width] duration-500 ease-slide"
        style={{ width: `${(view.progress ?? 0) * 100}%` }}
      />

      <div
        className="sa-fig"
        data-phase={phase}
        data-moving={view.moving}
        role="img"
        aria-label={view.summary}
        style={{ aspectRatio: `${VB.width} / ${VB.height}` }}
      >
        <svg viewBox={`${VB.x} ${VB.y} ${VB.width} ${VB.height}`} aria-hidden="true" focusable="false">
          <defs>
            <pattern id={HATCH_ID} width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(-38)">
              <rect width="1" height="7" fill="#8a8a8a" />
            </pattern>
          </defs>

          <Plates now={view.now} />

          {WIRES.map((wire) => {
            const state = wires[wire.id];
            return (
              <g key={wire.id} className="sa-wire" data-state={state} data-kind={wire.id === "labels" ? "labels" : wire.id === "loop" ? "loop" : wire.id === "lessons>checker" ? "planned" : "flow"}>
                <path className="bed" d={wire.d} />
                <path className="trace" d={wire.d} />
                <circle className="tail" cx={wire.tail[0]} cy={wire.tail[1]} r="3" />
                <path className="head" d={wire.head} />
                {state === "active" && <path className="packet" d={wire.d} />}
              </g>
            );
          })}

          <g className="sa-node" data-state={quiet(stations.deck.state)}>
            {DECK_ART}
          </g>
          <g className="sa-node" data-state={stations.cut.state}>
            {CUTTER_ART}
          </g>

          <g className="sa-node" data-state="idle">
            {RACK_BASE}
          </g>

          <g className="sa-node sa-bridge" data-state={stations.note.state}>
            <NoteBridgeBack />
          </g>
          <g className="sa-node sa-bridge" data-state={stations.jev.state}>
            <JevBridgeBack />
          </g>

          <Lanes total={configured} running={running} settled={settled} />

          <g className="sa-node" data-state="idle">
            {RULER_ART}
            {view.progress !== null && view.progress > 0 && <path className="sa-progress" d={progressPath(view.progress)} />}
          </g>

          <g className="sa-node sa-bridge" data-state={stations.note.state}>
            <NoteBridgeFront />
          </g>
          <g className="sa-node sa-bridge" data-state={stations.jev.state}>
            <JevBridgeFront />
            <JevScale tier={view.latestTier} />
          </g>

          <g className="sa-node" data-state={quiet(stations.peak.state)}>
            <PeakArt tier={view.latestTier} />
          </g>

          <g className="sa-node" data-state={quiet(stations.log.state)}>
            {LEDGER_BACK}
          </g>
          {ledger.slots.map(
            (tile, slot) =>
              tile && (
                <LedgerTile
                  key={`${slot}:${tile.key}`}
                  slot={slot}
                  tier={tile.tier}
                  result={tile.result}
                  label={tile.label}
                  dropping={tile.batch === ledger.batch && ledger.batch > 1}
                  delay={(slot % 8) * 40}
                />
              ),
          )}
          <g className="sa-node" data-state={quiet(stations.log.state)}>
            {LEDGER_FRONT}
          </g>

          <g className="sa-node" data-state={quiet(stations.board.state)}>
            {BOARD_ART}
            <BoardBars board={view.board} />
          </g>
          {(["deep", "lessons", "checker"] as const).map((id) => (
            <g key={id} className="sa-node" data-state={stations[id].state}>
              {STATION_ART[id]}
            </g>
          ))}
        </svg>

        <div className="sa-stage" data-now={view.now.replay} style={anchor(72, 300)}>Replay</div>
        <div className="sa-stage" data-now={view.now.after} style={anchor(400, 733)}>Score and review</div>

        <div className="sa-rack-cap" data-phase={phase} style={anchor(258, RACK.y0 - 8, 8)}>
          <b>Parallel lanes</b>
          <small>{phase === "idle" ? "One call on each" : "Lit while running"}</small>
        </div>
        {view.progress !== null && (
          <div className="sa-prog-cap" style={anchor(712, RULER.cy + 12)}>
            {formatPercent(view.progress)} of calls replayed
          </div>
        )}

        <div className="sa-loop-cap" style={anchor((BRIDGE_X.note + BRIDGE_X.jev) / 2, RACK.y0 - 20)}>Once per frame</div>
        <div className="sa-label-cap" style={anchor(172, 382)}>Known answers skip the models</div>
        <div className="sa-score" style={anchor(BOARD.cx, BOARD.cy + 5, 68)} aria-hidden="true">
          {scoreText}
        </div>

        <div className="sa-now">
          <div className="sa-now-head">{view.headline}</div>
          <p className="sa-now-sub">{view.detail}</p>
        </div>

        {(Object.keys(CAPTIONS) as StationId[]).map((id) => (
          <Caption key={id} id={id} name={stations[id].name} status={stations[id].status} state={stations[id].state} />
        ))}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-line pt-3">
        <span className="flex items-center gap-2 text-[12.5px] text-ink-2">
          <TierKey />
          Height is the tier: safe, uncertain, dangerous
        </span>
        <ResultKey />
      </div>

      <StepStrip live={props.live} active={props.active} finished={settled || phase === "stopped"} />
    </Card>
  );
}

function TierKey() {
  return (
    <svg width="32" height="14" viewBox="0 0 32 14" aria-hidden="true">
      {[
        [1, 4],
        [12, 8],
        [23, 13],
      ].map(([x, height], index) => (
        <rect key={index} x={x} y={14 - height} width="8" height={height} rx="1.2" fill="#1b1b1b" />
      ))}
    </svg>
  );
}

const RESULT_KEYS = [
  ["Right tier", "#1b1b1b", null],
  ["Uncertain", "#8e8e8e", "ring"],
  ["Wrong tier", "var(--color-mag)", "cross"],
  ["No answer", "none", null],
] as const;

function ResultKey() {
  return (
    <span className="flex flex-wrap gap-x-4 gap-y-1 text-[12.5px] text-ink-2">
      {RESULT_KEYS.map(([label, fill, mark]) => (
        <span key={label} className="flex items-center gap-1.5">
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
            <rect x="0.75" y="0.75" width="10.5" height="10.5" rx="2" fill={fill} stroke={fill === "none" ? "#b9b9b9" : fill} strokeWidth="1.2" />
            {mark === "ring" && <circle cx="6" cy="6" r="2.4" fill="none" stroke="#4a4a4a" strokeWidth="1.1" />}
            {mark === "cross" && <path d="M3.6 3.6l4.8 4.8M8.4 3.6l-4.8 4.8" stroke="#fff" strokeWidth="1.5" strokeLinecap="round" />}
          </svg>
          {label}
        </span>
      ))}
    </span>
  );
}

function StepStrip({ live, active, finished }: { live: LiveState | null; active: string[]; finished: boolean }) {
  if (!live) return <p className="mt-3 text-[13px] text-ink-3">Step counts appear when a run starts.</p>;
  return (
    <ul className="mt-3 grid grid-cols-[repeat(auto-fit,minmax(128px,1fr))] gap-x-5 gap-y-3">
      {live.steps.map((step) => {
        const hot = active.includes(step.name);
        return (
          <li key={step.name} className="min-w-0">
            <span className="flex items-center gap-1.5 text-[13px] font-semibold">
              <i className={`size-2 shrink-0 rounded-full ${hot ? "bg-mag" : finished && step.count ? "bg-[#1b1b1b]" : "bg-wire"}`} />
              <span className="truncate">{STEP_LABELS[step.name] ?? stepName(step.name)}</span>
            </span>
            <small className="block text-[12.5px] text-ink-2">
              {show(step.count, (value) => value.toLocaleString())} done, {step.p50 === null ? "no median" : `median ${ms(step.p50)}`}
            </small>
            <small className={`block text-[12.5px] ${step.errors ? "font-medium text-mag-deep" : "text-ink-3"}`}>
              {show(step.errors)} errors
            </small>
          </li>
        );
      })}
    </ul>
  );
}
