import { latestBeat, type CallSession, type DeletionReceipt } from "@/hooks/useCallSessions";
import { TIERS } from "@/lib/console/call-model";
import { Tag } from "../../ui";
import { useTooltip } from "../../Tooltip";
import { PHASE_LABEL, TIER_DOT } from "./copy";

interface RosterProps {
  sessions: CallSession[];
  openId: string | null;
  /** The erased call under review. Its ticket disappears the moment the viewer moves on. */
  erased: DeletionReceipt | null;
  onOpen: (id: string) => void;
}

/** One fixed size, so a card never changes shape as a call changes tier or phase. */
const CARD = "flex h-[66px] w-[188px] flex-col justify-center gap-1 rounded-[14px] px-3.5 text-left";

/** Only a random id, tier and phase per call. Numbers never reach this component. */
export function SessionRoster({ sessions, openId, erased, onOpen }: RosterProps) {
  const tooltip = useTooltip();

  if (sessions.length === 0 && !erased) {
    return <p className="mt-3 py-3 text-ink-2">No calls in progress. Place a test call to start one.</p>;
  }

  return (
    <ul className="-mx-1 mt-3 flex gap-2.5 overflow-x-auto px-1 pt-0.5 pb-2" aria-label="Calls in progress">
      {erased && (
        <li className="flex-none">
          <div className={`${CARD} border border-dashed border-wire ring-2 ring-mag`}>
            <span className="flex h-5 items-center justify-between gap-2">
              <span className="font-semibold tracking-[0.02em]">{erased.sessionId}</span>
              <Tag>Review</Tag>
            </span>
            <span className="flex h-5 items-center gap-1.5 text-[13px] whitespace-nowrap text-ink-2">
              <i className={`size-2 flex-none rounded-full ${TIER_DOT[erased.tier]}`} aria-hidden />
              <span className="font-medium text-ink">{TIERS[erased.tier]}</span>
              <span className="ml-auto text-ink-3">{PHASE_LABEL.deleted}</span>
            </span>
          </div>
        </li>
      )}
      {sessions.map((session) => {
        const { phase, tier } = latestBeat(session);
        const open = session.id === openId;
        const body = (
          <>
            <span className="flex h-5 items-center justify-between gap-2">
              <span className="font-semibold tracking-[0.02em]">{session.id}</span>
              {session.kind === "test" && <Tag hot={open}>Test</Tag>}
              {session.kind === "live" && <Tag hot>Live</Tag>}
            </span>
            <span className="flex h-5 items-center gap-1.5 text-[13px] whitespace-nowrap text-ink-2">
              <i className={`size-2 flex-none rounded-full ${TIER_DOT[tier]}`} aria-hidden />
              <span className="font-medium text-ink">{TIERS[tier]}</span>
              <span className="ml-auto text-ink-3">{PHASE_LABEL[phase]}</span>
            </span>
          </>
        );

        return (
          <li key={session.id} className="flex-none">
            {session.kind !== "ambient" ? (
              <button
                type="button"
                onClick={() => onOpen(session.id)}
                aria-pressed={open}
                aria-label={`Open ${session.kind === "live" ? "real" : "test"} call, session ${session.id}`}
                className={`${CARD} bg-card shadow-soft ${open ? "ring-2 ring-mag" : "hover:ring-1 hover:ring-wire"}`}
              >
                {body}
              </button>
            ) : (
              <div
                onMouseEnter={(event) =>
                  tooltip.show(event, { primary: `Session ${session.id}`, secondary: "Search this call's full number to open it" })
                }
                onMouseLeave={tooltip.hide}
                className={`${CARD} bg-card/70 ${open ? "ring-2 ring-mag" : ""}`}
              >
                {body}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
