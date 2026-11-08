import { DEMO_CALLER, URGENT_ACTIONS, type CustomerNotice, type UrgentAction } from "../lib/notices";
import { SafeSignalMark } from "./icons";
import { useTakeoverFocus } from "./useTakeoverFocus";

const BUTTON_STYLES: Record<UrgentAction, string> = {
  "Call my bank": "bg-white text-ink",
  "Ask my trusted contact": "border border-white/70 text-white",
  Continue: "border border-white/70 text-white",
};

export function UrgentScreen({
  notice,
  onAction,
}: {
  notice: CustomerNotice;
  onAction: (action: UrgentAction) => void;
}) {
  const headingRef = useTakeoverFocus<HTMLHeadingElement>();
  return (
    <div
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="urgent-title"
      aria-describedby="urgent-reason"
      className="on-dark screen-in column-fixed inset-y-0 z-50 flex flex-col bg-berry px-6 pt-[calc(var(--top-clear)+12px)] pb-[calc(env(safe-area-inset-bottom)+20px)] text-white"
    >
      {/* The reason scrolls if it must. The actions never leave the screen, so Continue stays one tap. */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <SafeSignalMark size={44} tone="light" />
        <p className="mt-5 text-[15px] text-white/80">On your call with {DEMO_CALLER}</p>
        <h1
          id="urgent-title"
          ref={headingRef}
          tabIndex={-1}
          className="mt-2 text-balance text-[clamp(32px,10vw,40px)] font-bold leading-[1.08] tracking-[-0.01em] outline-none"
        >
          {notice.title}
        </h1>
        <p id="urgent-reason" className="mt-4 text-pretty text-[22px] font-medium leading-[1.3]">
          {notice.body}
        </p>
        <p className="mt-4 text-[15px] leading-[1.4] text-white/80">
          Your call stays on. You decide what happens next.
        </p>
      </div>
      <div className="flex shrink-0 flex-col gap-3 pt-5">
        {URGENT_ACTIONS.map((action) => (
          <button
            key={action}
            type="button"
            onClick={() => onAction(action)}
            className={`min-h-14 rounded-lg px-4 text-[17px] font-semibold ${BUTTON_STYLES[action]}`}
          >
            {action}
          </button>
        ))}
      </div>
    </div>
  );
}
