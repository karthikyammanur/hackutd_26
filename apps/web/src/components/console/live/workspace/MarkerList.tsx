import type { Beat, CallTrace } from "@/lib/console/call-model";
import { formatClock } from "@/lib/console/format";
import type { IconName } from "../../icons";
import { Card, SectionTitle, Tile, type Tint } from "../../ui";

function markerLook(beat: Beat): { icon: IconName; tint: Tint } {
  if (beat.notice) return { icon: "bell", tint: "pink" };
  if (beat.flag) return { icon: "shield", tint: "sand" };
  if (beat.phase === "checking") return { icon: "check", tint: "lilac" };
  return { icon: "call", tint: "grey" };
}

interface MarkerListProps {
  trace: CallTrace;
  extent: CallTrace;
  /** Moves the play head. Null when the view is following a live call. */
  onSeek: ((t: number) => void) | null;
}

/** Markers only: plain descriptions from the beats, never anything said on the call. */
export function MarkerList({ trace, extent, onSeek }: MarkerListProps) {
  return (
    <section>
      <SectionTitle>What happened</SectionTitle>
      <Card className="mt-3.5 px-[22px] py-1.5">
        {[...extent.past].reverse().map((beat) => {
          const atHead = onSeek !== null && beat === trace.now;
          const body = (
            <>
              <Tile {...markerLook(beat)} />
              <div className="min-w-0 flex-1">
                <b className="block font-semibold">{beat.marker}</b>
                <small className="block text-[13px] text-ink-2">{beat.detail}</small>
              </div>
              {atHead && <span className="flex-none rounded-full bg-ink px-2 py-px text-[13px] font-medium text-white">Play head</span>}
              <span className="font-medium text-ink-3 tabular-nums">{formatClock(beat.t)}</span>
            </>
          );
          const look = `flex w-full items-center gap-3.5 border-t border-line py-[13px] text-left first:border-t-0 ${beat.t > trace.t ? "opacity-50" : ""}`;
          return onSeek ? (
            <button key={beat.t} type="button" aria-current={atHead ? "step" : undefined} className={`${look} hover:bg-sunk/55`} onClick={() => onSeek(beat.t)}>
              {body}
            </button>
          ) : (
            <div key={beat.t} className={look}>
              {body}
            </div>
          );
        })}
      </Card>
    </section>
  );
}
