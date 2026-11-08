import { useRef, useState, type PointerEvent } from "react";
import type { NoticeLevel } from "../lib/notices";
import { CloseIcon, SafeSignalMark, WarningIcon } from "./icons";

export interface BannerContent {
  key: string;
  level: NoticeLevel;
  title: string;
  body: string;
}

const DISMISS_DISTANCE = 44;
const TAP_SLOP = 6;

const ICON_TONE: Partial<Record<NoticeLevel, string>> = {
  warning: "bg-gradient-to-br from-[#ffb648] to-[#ee8a12] text-white",
};

function BannerIcon({ level }: { level: NoticeLevel }) {
  if (level === "warning") {
    return (
      <span className={`flex size-11 shrink-0 items-center justify-center rounded-[13px] ${ICON_TONE.warning}`}>
        <WarningIcon size={24} />
      </span>
    );
  }
  return (
    <span className="flex size-11 shrink-0 items-center justify-center overflow-hidden rounded-[13px]">
      <SafeSignalMark size={44} />
    </span>
  );
}

interface BannerProps {
  content: BannerContent;
  /** How many more notices are waiting behind this one. */
  behind: number;
  /** Set for a banner that leaves by itself. Drives the thin countdown line. */
  autoDismissMs: number | null;
  onOpen: () => void;
  onDismiss: () => void;
}

/** A floating card. Swipe it up to dismiss, tap it to open the inbox. */
export function Banner({ content, behind, autoDismissMs, onOpen, onDismiss }: BannerProps) {
  const [offset, setOffset] = useState(0);
  const [leaving, setLeaving] = useState(false);
  const [dragging, setDragging] = useState(false);
  const start = useRef<number | null>(null);
  const moved = useRef(false);

  function onPointerDown(event: PointerEvent<HTMLButtonElement>) {
    start.current = event.clientY;
    moved.current = false;
    setDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event: PointerEvent<HTMLButtonElement>) {
    if (start.current === null) return;
    const distance = event.clientY - start.current;
    if (Math.abs(distance) > TAP_SLOP) moved.current = true;
    // Downward drags resist, so the card feels attached to the top of the screen.
    setOffset(distance < 0 ? distance : distance * 0.15);
  }

  function onPointerUp() {
    start.current = null;
    setDragging(false);
    if (offset < -DISMISS_DISTANCE) {
      setLeaving(true);
      window.setTimeout(onDismiss, 180);
    } else {
      setOffset(0);
    }
  }

  return (
    <div className="column-fixed top-[calc(env(safe-area-inset-top)+38px)] z-40 px-2.5">
      <div
        key={content.key}
        className="banner-spring relative"
        style={{
          transform: leaving ? "translateY(-140%)" : `translateY(${offset}px)`,
          opacity: leaving ? 0 : 1,
          transition: dragging ? "none" : "transform 220ms cubic-bezier(0.2, 0.8, 0.2, 1), opacity 180ms ease-out",
        }}
      >
        {behind > 0 && (
          <div aria-hidden="true" className="absolute inset-x-3 -bottom-2 h-10 rounded-[22px] bg-white/70 shadow-[0_6px_18px_rgb(0_0_0/0.14)] backdrop-blur-xl" />
        )}
        {behind > 1 && (
          <div aria-hidden="true" className="absolute inset-x-6 -bottom-4 h-10 -z-10 rounded-[22px] bg-white/50 shadow-[0_6px_18px_rgb(0_0_0/0.1)] backdrop-blur-xl" />
        )}

        <div
          role={content.level === "quiet" ? "status" : "alert"}
          className="relative flex items-start overflow-hidden rounded-[24px] bg-white/88 shadow-[0_14px_44px_rgb(0_0_0/0.24),0_0_0_0.5px_rgb(0_0_0/0.08)] backdrop-blur-2xl backdrop-saturate-150"
        >
          <button
            type="button"
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
            onClick={() => {
              if (!moved.current) onOpen();
            }}
            className="flex min-w-0 flex-1 touch-none items-start gap-3 rounded-[24px] py-3 pr-1 pl-3 text-left"
          >
            <BannerIcon level={content.level} />
            <span className="min-w-0 flex-1">
              <span className="flex items-baseline gap-1.5 text-[12.5px] leading-4 font-medium text-muted">
                Safe Signal
                <span className="font-normal text-[#8b8b8b]">now</span>
                {behind > 0 && <span className="ml-auto pr-1 font-normal text-[#8b8b8b]">{behind} more</span>}
              </span>
              <span className="mt-0.5 block text-[15.5px] leading-5 font-semibold tracking-[-0.01em] text-ink">{content.title}</span>
              <span className="mt-px line-clamp-2 block text-pretty text-[14px] leading-[19px] text-[#4a4a4a]">{content.body}</span>
            </span>
          </button>
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Dismiss"
            className="flex size-11 shrink-0 items-center justify-center rounded-full text-[#8b8b8b]"
          >
            <CloseIcon size={17} />
          </button>
          {autoDismissMs !== null && (
            <span aria-hidden="true" className="banner-timer absolute inset-x-0 bottom-0 h-[2.5px] bg-magenta/70" style={{ animationDuration: `${autoDismissMs}ms` }} />
          )}
        </div>
      </div>
    </div>
  );
}
