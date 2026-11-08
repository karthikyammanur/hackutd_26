import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent, type PointerEvent } from "react";
import { useElementWidth } from "@/hooks/useElementWidth";
import { TIERS, type Beat, type CallTrace } from "@/lib/console/call-model";
import { RED_FLAGS } from "@/lib/console/flags";
import { formatClock } from "@/lib/console/format";
import { useTooltip } from "../../Tooltip";
import { firstBeatOf, PHASE_NAMES, phaseSpans, tierFloors, tierReachedAt, useReducedMotion, type PhaseSpan } from "./derive";
import { TierGlyph } from "./TierGlyph";
import "./danger.css";

export interface DangerTimelineProps {
  /** The moment under the play head. */
  trace: CallTrace;
  /** The furthest moment the call has reached. Everything up to it stays drawn. */
  extent: CallTrace;
  /** Moves the demo play head. Null when the view is following a live call. */
  onSeek: ((t: number) => void) | null;
}

const PLOT_HEIGHT = 232;
const AXIS_HEIGHT = 30;
const LEFT = 12;
const LANE_HEIGHT = 30;
const TICK_EVERY = 30;
const MARKER_GAP = 18;
const HALFTONE_STEP = 6;
const AHEAD_OPACITY = 0.3;
const TIER_FILLS = ["#F6B8D7", "#EE72AE", "#E20074", "#B8005E"];

/** One point at a time, the head eases up to the new score instead of teleporting. */
function useEasedValue(target: number, snap: boolean): number {
  const [value, setValue] = useState(target);
  const current = useRef(target);

  useEffect(() => {
    let handle = 0;
    let previous = performance.now();
    const step = (now: number) => {
      const eased = snap ? target : current.current + (target - current.current) * (1 - Math.exp(-(now - previous) / 120));
      previous = now;
      current.current = Math.abs(target - eased) < 0.002 ? target : eased;
      setValue(current.current);
      if (current.current !== target) handle = requestAnimationFrame(step);
    };
    handle = requestAnimationFrame(step);
    return () => cancelAnimationFrame(handle);
  }, [target, snap]);

  return snap ? target : value;
}

/** A rising step line with softened corners. Danger holds between beats, then climbs. */
function stepLine(points: { x: number; y: number }[], endX: number): string {
  let path = `M${points[0].x} ${points[0].y}`;
  let previous = points[0];
  for (const point of points.slice(1)) {
    const rise = point.y - previous.y;
    if (Math.abs(rise) < 0.5) continue;
    const direction = Math.sign(rise);
    const inCorner = Math.min(5, Math.abs(rise) / 2, (point.x - previous.x) / 2);
    const outCorner = Math.min(5, Math.abs(rise) / 2, Math.max(0, endX - point.x));
    path += `H${point.x - inCorner}Q${point.x} ${previous.y} ${point.x} ${previous.y + direction * inCorner}`;
    path += `V${point.y - direction * outCorner}Q${point.x} ${point.y} ${point.x + outCorner} ${point.y}`;
    previous = point;
  }
  return `${path}H${endX}`;
}

const LABEL_CHAR_WIDTH = 6.7;

/** A phase name that fits its span sits above the plot. Otherwise it runs up inside the band. */
function fitsSpan(span: PhaseSpan, x: (t: number) => number): boolean {
  return PHASE_NAMES[span.phase].length * LABEL_CHAR_WIDTH + 10 <= x(span.end) - x(span.start);
}

interface MarkerGroup {
  beat: Beat;
  earlier: Beat[];
}

/** Beats too close to tell apart share the later beat's marker. */
function groupBeats(beats: Beat[], x: (t: number) => number): MarkerGroup[] {
  const groups: MarkerGroup[] = [];
  for (const beat of beats) {
    const last = groups[groups.length - 1];
    if (last && x(beat.t) - x(last.beat.t) < MARKER_GAP) {
      groups[groups.length - 1] = { beat, earlier: [...last.earlier, last.beat] };
    } else {
      groups.push({ beat, earlier: [] });
    }
  }
  return groups;
}

function MarkerShape({ beat }: { beat: Beat }) {
  if (beat.flag) {
    return (
      <>
        {beat.notice && <circle cx="11" cy="11" r="9.5" fill="var(--color-card)" stroke="var(--color-mag)" strokeWidth="1.5" />}
        <path d="M11 4.5 17.5 11 11 17.5 4.5 11Z" fill="var(--color-mag)" stroke="var(--color-card)" strokeWidth="2" />
      </>
    );
  }
  if (beat.notice) return <circle cx="11" cy="11" r="5.5" fill="var(--color-card)" stroke="var(--color-mag)" strokeWidth="2.25" />;
  return <circle cx="11" cy="11" r="4.5" fill="var(--color-ink-2)" stroke="var(--color-card)" strokeWidth="2" />;
}

function describe(beat: Beat): string {
  const parts = [`${formatClock(beat.t)}, ${beat.marker}`];
  if (beat.flag) parts.push(`red flag: ${RED_FLAGS[beat.flag]}`);
  if (beat.notice) parts.push("customer told");
  parts.push(`${TIERS[beat.tier]} tier`);
  return parts.join(", ");
}

function inspectorNotes(beat: Beat): string {
  const notes = [beat.flag ? `Red flag: ${RED_FLAGS[beat.flag]}` : beat.detail];
  if (beat.notice) {
    const channel = beat.notice.channel === "t-life" ? "in T-Life" : "by urgent callback";
    const timing = beat.notice.timing === "during-call" ? "during the call" : "after the call";
    notes.push(`Customer told ${channel} ${timing}`);
  }
  return notes.join(". ");
}

function LegendItem({ beat, label }: { beat: Beat; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <svg width="16" height="16" viewBox="0 0 22 22" aria-hidden="true">
        <MarkerShape beat={beat} />
      </svg>
      {label}
    </span>
  );
}

const LEGEND_SAMPLE = {
  flag: { flag: "asks_for_code" } as Beat,
  notice: { notice: {} } as Beat,
  step: {} as Beat,
};

/**
 * How much danger the customer is in, drawn as the call happens. The area is a halftone: dots swell
 * as danger climbs, so the height reads without color. It works like a video editor's timeline:
 * everything the call has reached stays drawn, and the play head scrubs across it when onSeek is given.
 */
export function DangerTimeline({ trace, extent, onSeek }: DangerTimelineProps) {
  const { ref, width } = useElementWidth<HTMLDivElement>();
  const tooltip = useTooltip();
  const rawId = useId();
  const id = rawId.replace(/[^a-zA-Z0-9]/g, "");
  const reducedMotion = useReducedMotion();

  const [dragging, setDragging] = useState(false);
  const [crosshair, setCrosshair] = useState<number | null>(null);
  const [peek, setPeek] = useState<number | null>(null);
  const [pinned, setPinned] = useState<number | null>(null);

  const { scenario, t, now, tier, tierSince, phase } = trace;
  const reachedBeats = extent.past;
  const shownDanger = useEasedValue(extent.danger, reducedMotion || dragging);

  const spans = useMemo(() => phaseSpans(scenario), [scenario]);
  const floors = useMemo(() => tierFloors(scenario), [scenario]);
  const reached = tierReachedAt(extent);
  const endedAt = firstBeatOf(scenario, "checking")?.t ?? scenario.duration;
  const erasedAt = firstBeatOf(scenario, "deleted")?.t ?? scenario.duration;

  const compact = width > 0 && width < 560;
  const railWidth = compact ? 106 : 132;
  const right = width - railWidth;
  const plotWidth = Math.max(1, right - LEFT);
  const x = (time: number) => LEFT + (time / scenario.duration) * plotWidth;
  const laneHeight = LANE_HEIGHT;
  const plotBottom = laneHeight + PLOT_HEIGHT;
  const y = (danger: number) => laneHeight + (1 - danger) * PLOT_HEIGHT;
  const totalHeight = plotBottom + AXIS_HEIGHT;

  const points = reachedBeats.map((beat, index) => ({
    x: x(beat.t),
    y: y(index === reachedBeats.length - 1 ? shownDanger : beat.danger),
  }));
  const headX = x(t);
  const atEdge = t >= extent.t;
  const headY = y(atEdge ? shownDanger : trace.danger);
  const extentX = x(extent.t);
  const line = stepLine(points, extentX);
  const area = `${line}V${plotBottom}H${points[0].x}Z`;

  const callOver = extent.t >= endedAt;
  const erased = t >= erasedAt;
  const isLive = phase === "connecting" || phase === "live";

  const reachedSpans = spans
    .filter((span) => span.start <= extent.t)
    .map((span) => ({ ...span, end: Math.min(span.end, extent.t) }));
  const groups = groupBeats(reachedBeats, x);
  const pinnedBeat = reachedBeats.find((beat) => beat.t === pinned) ?? null;
  const peekBeat = reachedBeats.find((beat) => beat.t === peek) ?? null;
  const inspected = peekBeat ?? pinnedBeat ?? now;
  const inspectedIndex = reachedBeats.indexOf(inspected);

  const ticks: number[] = [];
  for (let tick = 0; tick <= scenario.duration; tick += TICK_EVERY) ticks.push(tick);

  /** The play head can only go where the call has already been. */
  const clampTime = (value: number) => Math.min(extent.t, Math.round(Math.max(0, value) * 10) / 10);
  const timeAtClientX = (clientX: number, element: HTMLElement) => {
    const box = element.getBoundingClientRect();
    return clampTime(((clientX - box.left - LEFT) / plotWidth) * scenario.duration);
  };

  const hide = () => {
    setCrosshair(null);
    tooltip.hide();
  };

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (!onSeek || event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragging(true);
    tooltip.hide();
    onSeek(timeAtClientX(event.clientX, event.currentTarget));
  };

  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const rawTime = ((event.clientX - box.left - LEFT) / plotWidth) * scenario.duration;
    const time = clampTime(rawTime);
    if (dragging) {
      onSeek?.(time);
      return;
    }
    if (rawTime > extent.t) {
      hide();
      return;
    }
    const beat = [...reachedBeats].reverse().find((item) => item.t <= time) ?? now;
    setCrosshair(x(time));
    tooltip.show(event, { primary: `${TIERS[beat.tier]} at ${formatClock(time)}`, secondary: beat.marker });
  };

  const endDrag = () => setDragging(false);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!onSeek) return;
    const stops = reachedBeats.map((beat) => beat.t);
    let next: number | undefined;
    if (event.key === "ArrowRight" || event.key === "ArrowUp") next = t + (event.shiftKey ? 10 : 1);
    else if (event.key === "ArrowLeft" || event.key === "ArrowDown") next = t - (event.shiftKey ? 10 : 1);
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = extent.t;
    else if (event.key === "PageUp") next = stops.find((stop) => stop > t) ?? extent.t;
    else if (event.key === "PageDown") next = [...stops].reverse().find((stop) => stop < t) ?? 0;
    if (next === undefined) return;
    event.preventDefault();
    onSeek(clampTime(next));
  };

  const inspectStep = (direction: -1 | 1) => {
    const beat = reachedBeats[inspectedIndex + direction];
    if (!beat) return;
    if (onSeek) onSeek(beat.t);
    else setPinned(beat.t);
  };

  const onMarkerClick = (beat: Beat) => {
    if (onSeek) onSeek(beat.t);
    else setPinned(pinned === beat.t ? null : beat.t);
  };

  const onMarkerEnter = (event: MouseEvent<HTMLButtonElement>, group: MarkerGroup) => {
    setPeek(group.beat.t);
    setCrosshair(null);
    tooltip.show(event, {
      primary: group.beat.marker,
      secondary: group.earlier.length
        ? `${formatClock(group.beat.t)}. Just before: ${group.earlier.map((beat) => beat.marker).join(", ")}`
        : `${formatClock(group.beat.t)}, ${TIERS[group.beat.tier]}`,
    });
  };

  const onMarkerLeave = () => {
    setPeek(null);
    tooltip.hide();
  };

  const dangerShape = (
    <>
      <path d={area} fill={`url(#${id}halftone)`} clipPath={`url(#${id}during)`} />
      <path d={area} fill={`url(#${id}halftone)`} clipPath={`url(#${id}after)`} opacity="0.34" />
      <path d={line} fill="none" stroke="var(--color-mag)" strokeWidth="2.25" strokeLinejoin="round" clipPath={`url(#${id}during)`} />
      {callOver && (
        <path d={line} fill="none" stroke="var(--color-ink-2)" strokeWidth="2" strokeDasharray="2 5" strokeLinecap="round" clipPath={`url(#${id}afterAll)`} />
      )}
    </>
  );

  const summary = `Danger over the call, currently ${TIERS[tier]} at ${formatClock(t)}. Danger only ever rises.`;
  const pillWidth = 44;
  const pillLeft = Math.max(0, Math.min(right - pillWidth + 8, headX - pillWidth / 2));

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1">
        <p className="flex items-center gap-2 text-[17px] font-semibold tracking-[-0.012em]">
          <TierGlyph tier={tier} />
          <span>
            {TIERS[tier]}
            <span className="font-normal text-ink-2"> since {formatClock(tierSince)}</span>
          </span>
        </p>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-ink-2">
          <LegendItem beat={LEGEND_SAMPLE.flag} label="Red flag" />
          <LegendItem beat={LEGEND_SAMPLE.notice} label="Customer told" />
          <LegendItem beat={LEGEND_SAMPLE.step} label="Call step" />
          <span className="ml-1 font-medium text-ink">{onSeek ? "Drag to scrub" : "Following live"}</span>
        </div>
      </div>
      <p className="sr-only" role="status">
        Danger tier {TIERS[tier]}
      </p>

      <div ref={ref} className="relative mt-3" style={{ height: totalHeight }}>
        {width > 0 && (
          <>
            <svg width={width} height={totalHeight} className="absolute inset-0 overflow-visible" aria-hidden="true">
              <defs>
                <pattern id={`${id}halftone`} width={HALFTONE_STEP * 2} height={PLOT_HEIGHT} y={laneHeight} patternUnits="userSpaceOnUse">
                  {Array.from({ length: Math.floor(PLOT_HEIGHT / HALFTONE_STEP) }, (_, row) => {
                    const level = 1 - (row + 0.5) / (PLOT_HEIGHT / HALFTONE_STEP);
                    const offset = row % 2 === 0 ? 1 : 2;
                    return (
                      <g key={row} fill="var(--color-mag)" opacity={0.42 + level * 0.5}>
                        <circle cx={offset * HALFTONE_STEP - HALFTONE_STEP / 2} cy={row * HALFTONE_STEP + HALFTONE_STEP / 2} r={0.65 + level * level * 1.95} />
                      </g>
                    );
                  })}
                </pattern>
                <radialGradient id={`${id}glow`}>
                  <stop offset="0" stopColor="#E20074" stopOpacity="0.5" />
                  <stop offset="0.45" stopColor="#E20074" stopOpacity="0.2" />
                  <stop offset="1" stopColor="#E20074" stopOpacity="0" />
                </radialGradient>
                <clipPath id={`${id}during`}>
                  <rect x="0" y="0" width={x(endedAt)} height={totalHeight} />
                </clipPath>
                <clipPath id={`${id}after`}>
                  <rect x={x(endedAt)} y="0" width={Math.max(0, x(erasedAt) - x(endedAt))} height={totalHeight} />
                </clipPath>
                <clipPath id={`${id}afterAll`}>
                  <rect x={x(endedAt)} y="-40" width={width} height={totalHeight + 80} />
                </clipPath>
                <clipPath id={`${id}played`}>
                  <rect x="0" y="-40" width={headX} height={totalHeight + 80} />
                </clipPath>
                <clipPath id={`${id}ahead`}>
                  <rect x={headX} y="-40" width={Math.max(0, width - headX)} height={totalHeight + 80} />
                </clipPath>
              </defs>

              {reachedSpans
                .filter((span) => span.phase !== "live")
                .map((span) => (
                  <rect key={span.phase} x={x(span.start)} y={laneHeight} width={x(span.end) - x(span.start)} height={PLOT_HEIGHT} fill="var(--color-sunk)" opacity={span.phase === "connecting" ? 0.45 : 0.6} />
                ))}

              {floors.slice(1).map((floor) => (
                <line key={floor} x1={LEFT} x2={right} y1={y(floor)} y2={y(floor)} stroke="var(--color-line)" />
              ))}

              {reachedSpans.map((span) => {
                const isCurrent = span.phase === phase;
                const isPast = span.end <= t;
                const fullSpan = spans.find((item) => item.phase === span.phase) ?? span;
                const fits = fitsSpan(fullSpan, x);
                const labelWidth = PHASE_NAMES[span.phase].length * LABEL_CHAR_WIDTH;
                const labelX = Math.max((x(span.start) + x(span.end)) / 2, x(span.start) + labelWidth / 2);
                const dangerThere = scenario.beats.find((beat) => beat.t >= span.start)?.danger ?? 0;
                const runsFromBottom = dangerThere > 0.5;
                const inside = {
                  x: (x(span.start) + x(span.end)) / 2 + 4.5,
                  y: runsFromBottom ? plotBottom - 10 : laneHeight + 10,
                };
                return (
                  <g key={span.phase}>
                    <rect
                      x={x(span.start) + (span.start === 0 ? 0 : 1)}
                      y={laneHeight - 7}
                      width={Math.max(2, x(span.end) - x(span.start) - 2)}
                      height="3"
                      rx="1.5"
                      fill={isCurrent ? "var(--color-ink)" : isPast ? "var(--color-wire-used)" : "var(--color-wire)"}
                    />
                    <text
                      {...(fits
                        ? { x: labelX, y: laneHeight - 13, textAnchor: "middle" as const }
                        : {
                            transform: `rotate(-90 ${inside.x} ${inside.y})`,
                            ...inside,
                            textAnchor: runsFromBottom ? ("start" as const) : ("end" as const),
                          })}
                      fontSize="13"
                      fontWeight={isCurrent ? 600 : 400}
                      fill={isCurrent ? "var(--color-ink)" : "var(--color-ink-2)"}
                    >
                      {PHASE_NAMES[span.phase]}
                    </text>
                  </g>
                );
              })}

              {reachedSpans.slice(1).map((span) => (
                <line
                  key={span.phase}
                  x1={x(span.start)}
                  x2={x(span.start)}
                  y1={laneHeight}
                  y2={plotBottom}
                  stroke={span.phase === "checking" ? "var(--color-ink)" : "var(--color-wire)"}
                  strokeWidth={span.phase === "checking" ? 1.5 : 1}
                />
              ))}

              <g clipPath={`url(#${id}played)`}>
                {dangerShape}
              </g>
              <g clipPath={`url(#${id}ahead)`} opacity={AHEAD_OPACITY}>
                {dangerShape}
              </g>

              <line x1={LEFT} x2={right} y1={plotBottom} y2={plotBottom} stroke="var(--color-wire)" />
              {ticks.filter((tick) => Math.abs(x(tick) - headX) > 38).map((tick) => (
                <text key={tick} x={x(tick)} y={plotBottom + 19} fontSize="13" fill="var(--color-ink-2)" textAnchor={tick === 0 ? "start" : "middle"}>
                  {formatClock(tick)}
                </text>
              ))}

              <line x1={headX} x2={right + 12} y1={headY} y2={headY} stroke="var(--color-mag)" strokeOpacity="0.4" strokeDasharray="2 3" />
              {atEdge && <line key={`sweep-${tier}`} className="danger-sweep" x1={headX} x2={right + 12} y1={y(trace.danger)} y2={y(trace.danger)} stroke="var(--color-mag)" strokeWidth="1.5" />}

              {onSeek ? (
                <g>
                  <line x1={headX} x2={headX} y1={laneHeight} y2={plotBottom + 5} stroke="var(--color-ink)" strokeWidth="2" />
                  <path d={`M${headX - 6} ${laneHeight - 9}H${headX + 6}V${laneHeight - 2}L${headX} ${laneHeight + 5}L${headX - 6} ${laneHeight - 2}Z`} fill="var(--color-ink)" stroke="var(--color-card)" strokeWidth="1.5" strokeLinejoin="round" />
                </g>
              ) : (
                <line x1={headX} x2={headX} y1={laneHeight} y2={plotBottom} stroke="var(--color-mag)" strokeOpacity="0.45" />
              )}

              {isLive && atEdge && <circle className="danger-glow" cx={headX} cy={headY} r="20" fill={`url(#${id}glow)`} />}
              <circle
                cx={headX}
                cy={headY}
                r={erased ? 4.5 : 5.5}
                fill={erased ? "var(--color-card)" : isLive ? "var(--color-mag)" : "var(--color-ink-2)"}
                stroke={erased ? "var(--color-ink-3)" : "var(--color-card)"}
                strokeWidth="2"
              />

              {TIERS.map((name, index) => {
                const bottom = y(floors[index]);
                const top = y(floors[index + 1] ?? 1);
                const railX = right + 12;
                const segmentTop = top + 1;
                const segmentHeight = Math.max(0, bottom - top - 2);
                const isReached = reached[index] !== undefined;
                const isCurrent = index === tier;
                return (
                  <g key={name}>
                    <rect
                      x={railX}
                      y={segmentTop}
                      width="8"
                      height={segmentHeight}
                      rx="2.5"
                      fill={isReached ? TIER_FILLS[index] : "var(--color-sunk)"}
                      opacity={isReached && index > tier ? AHEAD_OPACITY + 0.15 : 1}
                      style={{ transition: "fill 0.3s ease-out" }}
                    />
                    <text
                      key={isCurrent ? "current" : "other"}
                      className={isCurrent ? "danger-pop" : undefined}
                      x={railX + 16}
                      y={Math.max(top + 14, (top + bottom) / 2 + 4.5)}
                      fontSize="13"
                      fontWeight={isCurrent ? 600 : 400}
                      fill={isCurrent ? "var(--color-ink)" : "var(--color-ink-2)"}
                    >
                      {name}
                    </text>
                    {!compact && reached[index] !== undefined && (
                      <text x={width} y={Math.max(top + 14, (top + bottom) / 2 + 4.5)} fontSize="13" textAnchor="end" fill="var(--color-ink-2)">
                        {formatClock(reached[index])}
                      </text>
                    )}
                  </g>
                );
              })}
            </svg>

            {crosshair !== null && (
              <div className="pointer-events-none absolute w-0 border-l border-dashed border-ink-3" style={{ left: crosshair, top: laneHeight, height: PLOT_HEIGHT }} />
            )}

            {callOver && (
              <div
                className="pointer-events-none absolute -translate-x-full animate-rise rounded-md bg-card px-2.5 py-1 text-[13px] leading-[1.3] whitespace-nowrap text-ink shadow-soft"
                style={{ left: x(endedAt) - 8, top: y(0.28), opacity: t < endedAt ? 0.6 : 1 }}
              >
                <span className="block font-medium">Call ended</span>
                <span className="block text-ink-2">Checking agent takes over</span>
              </div>
            )}

            <div
              {...(onSeek
                ? {
                    role: "slider",
                    tabIndex: 0,
                    "aria-label": "Call position",
                    "aria-valuemin": 0,
                    "aria-valuemax": Math.round(extent.t),
                    "aria-valuenow": Math.round(t),
                    "aria-valuetext": `${formatClock(t)}, ${PHASE_NAMES[phase]}, ${TIERS[tier]} tier`,
                  }
                : { role: "img", "aria-label": summary })}
              className={`absolute inset-x-0 rounded-md ${onSeek ? (dragging ? "cursor-grabbing" : "cursor-pointer") : ""}`}
              style={{ top: laneHeight, height: PLOT_HEIGHT + AXIS_HEIGHT, width: right, touchAction: onSeek ? "none" : undefined }}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={endDrag}
              onPointerCancel={endDrag}
              onPointerLeave={hide}
              onKeyDown={onKeyDown}
            />

            {groups.map((group) => {
              const { beat } = group;
              const isActive = inspected === beat || group.earlier.includes(inspected);
              const atHead = beat === now || group.earlier.includes(now);
              return (
                <button
                  key={beat.t}
                  type="button"
                  aria-label={describe(beat)}
                  aria-pressed={onSeek ? atHead : pinned === beat.t}
                  className="absolute grid size-[26px] -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full"
                  style={{ left: x(beat.t), top: y(beat.danger), opacity: beat.t > t ? 0.5 : 1 }}
                  onClick={() => onMarkerClick(beat)}
                  onMouseEnter={(event) => onMarkerEnter(event, group)}
                  onMouseLeave={onMarkerLeave}
                  onFocus={() => setPeek(beat.t)}
                  onBlur={() => setPeek(null)}
                >
                  <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true" className="danger-marker animate-pop overflow-visible" data-active={isActive}>
                    <MarkerShape beat={beat} />
                  </svg>
                </button>
              );
            })}

            <div
              className="pointer-events-none absolute rounded-full bg-ink px-2 py-px text-center text-[13px] font-medium text-white"
              style={{ left: pillLeft, top: plotBottom + 5, width: pillWidth }}
            >
              {formatClock(t)}
            </div>
          </>
        )}
      </div>

      <div className="mt-2 flex min-h-[46px] items-start gap-3 border-t border-line pt-2.5">
        <span className="pt-px text-[13px] text-ink-2">
          {formatClock(inspected.t)}
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-medium">{inspected.marker}</p>
          <p className="text-[13px] text-ink-2">
            {inspectorNotes(inspected)}. {TIERS[inspected.tier]} tier, illustrative score {inspected.danger.toFixed(2)}.
          </p>
        </div>
        <div className="flex flex-none items-center gap-1">
          {pinnedBeat && (
            <button type="button" className="mr-1 rounded-full px-2 py-[3px] text-[13px] text-ink-2 hover:bg-sunk" onClick={() => setPinned(null)}>
              Back to now
            </button>
          )}
          <button type="button" aria-label="Previous step" disabled={inspectedIndex <= 0} className="grid size-7 place-items-center rounded-full text-ink-2 hover:bg-sunk disabled:opacity-35" onClick={() => inspectStep(-1)}>
            <Chevron direction={-1} />
          </button>
          <button type="button" aria-label="Next step" disabled={inspectedIndex >= reachedBeats.length - 1} className="grid size-7 place-items-center rounded-full text-ink-2 hover:bg-sunk disabled:opacity-35" onClick={() => inspectStep(1)}>
            <Chevron direction={1} />
          </button>
        </div>
      </div>
    </div>
  );
}

function Chevron({ direction }: { direction: -1 | 1 }) {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={direction === -1 ? "M8.5 3 4.5 7l4 4" : "M5.5 3l4 4-4 4"} />
    </svg>
  );
}
