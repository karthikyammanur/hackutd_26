import { useState, type ComponentProps, type ReactNode } from "react";
import { DEMO_CALLBACK_NUMBER, type CustomerNotice } from "../lib/notices";
import { PhoneHandsetIcon, SafeSignalMark } from "./icons";
import { useTakeoverFocus } from "./useTakeoverFocus";

function RoundAction({
  label,
  tone,
  children,
  ...props
}: { label: string; tone: string; children: ReactNode } & ComponentProps<"button">) {
  return (
    <button type="button" className="flex min-w-24 flex-col items-center gap-2 rounded-xl text-[15px] font-medium" {...props}>
      <span className={`flex size-[72px] items-center justify-center rounded-full ${tone}`}>{children}</span>
      {label}
    </button>
  );
}

/** Nothing here ends on a timer. The customer answers, declines or ends the call. */
export function CallbackScreen({
  notice,
  onDone,
}: {
  notice: CustomerNotice;
  onDone: (choice: string) => void;
}) {
  const [answered, setAnswered] = useState(false);
  const headingRef = useTakeoverFocus<HTMLHeadingElement>();
  return (
    <div
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="callback-title"
      aria-describedby="callback-body"
      className="on-dark screen-in column-fixed inset-y-0 z-50 flex flex-col bg-tile px-6 pt-[calc(var(--top-clear)+24px)] pb-[calc(env(safe-area-inset-bottom)+32px)] text-center text-white"
    >
      <div className="flex min-h-0 flex-1 flex-col items-center overflow-y-auto">
        <span className="rounded-full border-[3px] border-magenta p-1.5">
          <span className="block overflow-hidden rounded-full">
            <SafeSignalMark size={72} tone="light" />
          </span>
        </span>
        <p className="mt-6 text-[15px] text-white/80">{answered ? "Connected" : "Incoming call"}</p>
        <h1
          id="callback-title"
          ref={headingRef}
          tabIndex={-1}
          className="mt-1.5 text-balance text-[30px] font-bold leading-[1.15] outline-none"
        >
          {notice.title}
        </h1>
        <p className="mt-2 text-[16px] text-white/80">{DEMO_CALLBACK_NUMBER}</p>
        <p id="callback-body" className="mt-6 max-w-[32ch] text-[17px] leading-[1.4]">
          {notice.body}
        </p>
        <p className="mt-3 max-w-[34ch] text-[14px] leading-[1.4] text-white/70">
          This callback only reaches you. It doesn't contact emergency services.
        </p>
      </div>
      <div className="flex w-full shrink-0 justify-around pt-6">
        {answered ? (
          <RoundAction label="End call" tone="bg-danger" onClick={() => onDone("Answered")}>
            <PhoneHandsetIcon size={32} className="rotate-[135deg]" />
          </RoundAction>
        ) : (
          <>
            <RoundAction label="Not now" tone="bg-danger" onClick={() => onDone("Not now")}>
              <PhoneHandsetIcon size={32} className="rotate-[135deg]" />
            </RoundAction>
            <RoundAction label="Answer" tone="bg-ok" onClick={() => setAnswered(true)}>
              <PhoneHandsetIcon size={32} />
            </RoundAction>
          </>
        )}
      </div>
    </div>
  );
}
