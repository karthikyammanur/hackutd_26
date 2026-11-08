import type { ReactNode } from "react";
import { PIPELINE_NODES, TIERS, type CallTrace } from "@/lib/console/call-model";
import { RED_FLAG_ENTRIES, RED_FLAGS } from "@/lib/console/flags";
import { formatClock } from "@/lib/console/format";
import { useTooltip } from "../../Tooltip";
import { callTiming, memoryStatus, PHASE_NAMES, phaseSpans, sentToJev, type MemoryState } from "./derive";
import { TierGlyph } from "./TierGlyph";

function Stat({ label, value, note, children }: { label: string; value: ReactNode; note: string; children?: ReactNode }) {
  return (
    <div className="border-t border-line pt-2.5">
      <dt className="text-[13px] text-ink-2">{label}</dt>
      <dd>
        <div className="mt-px flex items-center gap-2 text-[22px] leading-[1.25] font-semibold tracking-[-0.016em]">
          {value}
        </div>
        <div className="mt-1 flex h-[9px] items-center">{children}</div>
        <p className="mt-1.5 text-[13px] leading-[1.35] text-ink-2">{note}</p>
      </dd>
    </div>
  );
}

function Pip({ on, label, secondary }: { on: boolean; label: string; secondary?: string }) {
  const tooltip = useTooltip();
  return (
    <span
      className={`inline-block size-[9px] flex-none rounded-[2.5px] ${on ? "bg-mag" : "border border-wire"}`}
      aria-hidden="true"
      onMouseEnter={(event) => tooltip.show(event, { primary: label, secondary })}
      onMouseLeave={tooltip.hide}
    />
  );
}

const STATIONS: { state: MemoryState; label: string }[] = [
  { state: "empty", label: "Empty" },
  { state: "held", label: "In memory" },
  { state: "erased", label: "Erased" },
];

function MemoryTrack({ state, openedAt, erasedAt }: { state: MemoryState; openedAt?: number; erasedAt?: number }) {
  const current = STATIONS.findIndex((station) => station.state === state);
  const times = [undefined, openedAt, erasedAt];
  return (
    <ol className="flex w-full max-w-[320px] items-start">
      {STATIONS.map((station, index) => {
        const reached = index <= current;
        const isCurrent = index === current;
        const time = times[index];
        return (
          <li key={station.state} className="relative flex-1">
            {index > 0 && <span className={`absolute top-[6px] right-1/2 left-[-50%] h-0.5 ${reached ? "bg-ink" : "bg-wire"}`} aria-hidden="true" />}
            <span className="relative flex flex-col items-center gap-1 text-center">
              <span
                className={`block size-3.5 rounded-full border-2 ${isCurrent ? "border-ink bg-ink ring-2 ring-card ring-offset-0" : reached ? "border-ink bg-card" : "border-wire bg-card"}`}
                aria-hidden="true"
              />
              <span className={`text-[13px] leading-tight ${isCurrent ? "font-semibold text-ink" : "text-ink-2"}`}>
                {station.label}
                {time !== undefined && <span className="block font-normal text-ink-2">{formatClock(time)}</span>}
              </span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

/** Live readouts for one call. Every figure is computed from the trace. */
export function CallStats({ trace }: { trace: CallTrace }) {
  const { scenario, past, t, phase, tier, tierSince, raisedFlags, notices } = trace;
  const timing = callTiming(trace);
  const memory = memoryStatus(trace);
  const spans = phaseSpans(scenario);
  const phaseIndex = spans.findIndex((span) => span.phase === phase);
  const phaseSince = spans[phaseIndex]?.start ?? 0;

  const blocks = past.filter(sentToJev);
  const lastBlock = blocks[blocks.length - 1];
  const flagBeats = past.filter((beat) => beat.flag);
  const lastFlag = flagBeats[flagBeats.length - 1];
  const flagTimes = new Map(flagBeats.map((beat) => [beat.flag, beat.t]));
  const during = notices.filter((notice) => notice.timing === "during-call").length;
  const after = notices.length - during;

  const callNote =
    timing.connectedAt === undefined
      ? "Not connected yet"
      : timing.endedAt === undefined
        ? `Connected at ${formatClock(timing.connectedAt)}`
        : `Ended at ${formatClock(timing.endedAt)}`;

  const windowRole = PIPELINE_NODES.find((node) => node.id === "window")?.role ?? "";
  const memoryCopy: Record<MemoryState, { value: string; note: string }> = {
    empty: { value: "Nothing yet", note: "The conversation window opens when the call connects." },
    held: {
      value: "This call's conversation window",
      note: `${windowRole}. Held for ${formatClock(memory.heldFor)}.${phase === "checking" ? " The Checking agent is rereading it." : ""}`,
    },
    erased: {
      value: "Nothing",
      note: `The window and markers were erased at ${formatClock(memory.erasedAt ?? t)}, after ${formatClock(memory.heldFor)} in memory. What remains here is this session's replay.`,
    },
  };

  return (
    <div className="@container">
      <dl className="grid grid-cols-2 gap-x-6 gap-y-4 @min-[480px]:grid-cols-3 @min-[900px]:grid-cols-6">
        <Stat label="Time in call" value={formatClock(timing.inCall)} note={callNote} />

        <Stat label="Phase" value={PHASE_NAMES[phase]} note={`For ${formatClock(t - phaseSince)}, step ${phaseIndex + 1} of ${spans.length}`}>
          <span className="flex w-full max-w-[120px] gap-0.5" aria-hidden="true">
            {spans.map((span, index) => (
              <span key={span.phase} className={`h-1 flex-1 rounded-full ${index <= phaseIndex ? "bg-ink" : "bg-wire"}`} />
            ))}
          </span>
        </Stat>

        <Stat
          label="Tier"
          value={
            <>
              <TierGlyph tier={tier} />
              {TIERS[tier]}
            </>
          }
          note={`At this tier for ${formatClock(t - tierSince)}`}
        />

        <Stat
          label="Red flags raised"
          value={`${raisedFlags.size} of ${RED_FLAG_ENTRIES.length}`}
          note={lastFlag?.flag ? `Latest: ${RED_FLAGS[lastFlag.flag]}` : "None raised yet"}
        >
          <span className="sr-only">Raised: {[...raisedFlags].map((flag) => RED_FLAGS[flag]).join(", ") || "none"}</span>
          <span className="flex gap-[3px]">
            {RED_FLAG_ENTRIES.map(([flag, label]) => {
              const raisedAt = flagTimes.get(flag);
              return <Pip key={flag} on={raisedFlags.has(flag)} label={label} secondary={raisedAt !== undefined ? `Raised at ${formatClock(raisedAt)}` : "Not raised"} />;
            })}
          </span>
        </Stat>

        <Stat label="Small blocks to Jev" value={blocks.length} note={lastBlock ? `Last sent at ${formatClock(lastBlock.t)}` : "None sent yet"}>
          <span className="flex gap-[3px]">
            {blocks.map((beat) => (
              <Pip key={beat.t} on label={`Block sent at ${formatClock(beat.t)}`} secondary={beat.status.jev} />
            ))}
          </span>
        </Stat>

        <Stat
          label="Customer notices"
          value={notices.length}
          note={notices.length ? `${during} during, ${after} after the call` : "None sent yet"}
        >
          <span className="flex gap-[3px]">
            {past
              .filter((beat) => beat.notice)
              .map((beat) => (
                <Pip key={beat.t} on label={beat.notice?.title ?? ""} secondary={`Sent at ${formatClock(beat.t)}`} />
              ))}
          </span>
        </Stat>
      </dl>

      <div className="mt-5 flex flex-col gap-4 rounded-[14px] bg-sunk/55 p-4 @min-[640px]:flex-row @min-[640px]:items-center @min-[640px]:justify-between">
        <div className="min-w-0">
          <p className="text-[13px] text-ink-2">In memory now</p>
          <p className="text-[17px] font-semibold tracking-[-0.012em]">{memoryCopy[memory.state].value}</p>
          <p className="mt-0.5 text-[13px] text-ink-2">{memoryCopy[memory.state].note}{memory.state === "erased" ? "" : " This screen shows markers only."}</p>
        </div>
        <MemoryTrack state={memory.state} openedAt={memory.openedAt} erasedAt={memory.erasedAt} />
      </div>
    </div>
  );
}
