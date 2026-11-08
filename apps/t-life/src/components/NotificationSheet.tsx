import { useEffect, useState, type ReactNode } from "react";
import { disableNotifications, enableNotifications, promptInstall, sendSampleToPhone, useDevice } from "../lib/device";
import { DEMO_SEQUENCE, LEVEL_LABELS, type NoticeLevel } from "../lib/notices";
import { CloseIcon } from "./icons";

const COUNTDOWN_SECONDS = 5;

function Check() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path d="M2.5 7.5 5.6 10.5 11.5 3.8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SetupRow({ step, done, title, detail, action }: { step: number; done: boolean; title: string; detail: string; action?: ReactNode }) {
  return (
    <li className="flex items-center gap-3 py-3">
      <span
        className={`flex size-7 shrink-0 items-center justify-center rounded-full text-[13px] font-semibold ${
          done ? "bg-ok text-white" : "bg-[#ececec] text-muted"
        }`}
      >
        {done ? <Check /> : step}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[15px] leading-5 font-semibold">{title}</span>
        <span className="block text-pretty text-[13.5px] leading-[18px] text-muted">{detail}</span>
      </span>
      {action}
    </li>
  );
}

const ACTION = "min-h-10 shrink-0 rounded-full bg-magenta px-4 text-[14px] font-semibold text-white disabled:opacity-60";

export function NotificationSheet({ onClose }: { onClose: () => void }) {
  const { push, standalone, canInstall, live } = useDevice();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<{ level: NoticeLevel; left: number } | null>(null);

  useEffect(() => {
    if (!pending) return;
    const timer = window.setTimeout(
      () => setPending(pending.left <= 1 ? null : { ...pending, left: pending.left - 1 }),
      1000,
    );
    return () => window.clearTimeout(timer);
  }, [pending]);

  async function allow() {
    setBusy(true);
    setError(null);
    try {
      await enableNotifications();
    } catch {
      setError("Couldn't turn on notifications. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  async function sendSample(level: NoticeLevel) {
    setError(null);
    setPending({ level, left: COUNTDOWN_SECONDS });
    const queued = await sendSampleToPhone(level).catch(() => false);
    if (!queued) {
      setPending(null);
      setError("Couldn't send that one. Check your connection and try again.");
    }
  }

  const pushDetail: Record<typeof push, string> = {
    on: "This phone will get warnings, even when the app is closed.",
    off: "So we can reach you during a call.",
    denied: "Blocked. Turn them on for this app in your phone's settings.",
    unsupported: "This browser can't receive them. Use Chrome on Android.",
  };

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-labelledby="notification-sheet-title">
      <button type="button" aria-label="Close" onClick={onClose} className="screen-in absolute inset-0 bg-black/40" />
      <div className="sheet-in column-fixed bottom-0 max-h-[88dvh] overflow-y-auto rounded-t-[26px] bg-white px-5 pt-2 pb-[calc(env(safe-area-inset-bottom)+20px)]">
        <div aria-hidden="true" className="mx-auto h-1 w-9 rounded-full bg-[#d9d9d9]" />
        <div className="mt-3 flex items-center justify-between">
          <h2 id="notification-sheet-title" className="text-[21px] font-bold tracking-[-0.01em]">
            Notifications
          </h2>
          <button type="button" onClick={onClose} aria-label="Close" className="flex size-11 items-center justify-center rounded-full text-muted">
            <CloseIcon size={20} />
          </button>
        </div>

        <ol className="divide-y divide-line">
          <SetupRow
            step={1}
            done={standalone}
            title="Add to home screen"
            detail={standalone ? "Installed on this phone." : canInstall ? "Opens like any other app." : "In your browser menu, choose Add to Home screen."}
            action={
              canInstall && !standalone ? (
                <button type="button" onClick={() => void promptInstall()} className={ACTION}>
                  Add
                </button>
              ) : undefined
            }
          />
          <SetupRow
            step={2}
            done={push === "on"}
            title="Allow notifications"
            detail={pushDetail[push]}
            action={
              push === "off" ? (
                <button type="button" disabled={busy} onClick={() => void allow()} className={ACTION}>
                  {busy ? "Turning on" : "Allow"}
                </button>
              ) : undefined
            }
          />
          <SetupRow
            step={3}
            done={live}
            title="Connected to Safe Signal"
            detail={live ? "Ready for a test call from the console." : "Connecting. Check your internet connection."}
          />
        </ol>

        {error && (
          <p role="alert" className="mt-2 text-[14px] text-danger">
            {error}
          </p>
        )}

        {push === "on" && (
          <section className="mt-5">
            <h3 className="text-[16px] font-semibold">Send one to this phone</h3>
            <p role="status" className="mt-0.5 min-h-[18px] text-[13.5px] leading-[18px] text-muted">
              {pending
                ? `Arriving in ${pending.left}. Leave the app now to see it outside.`
                : "It arrives in 5 seconds, so you can leave the app first."}
            </p>
            <div className="mt-3 grid grid-cols-2 gap-2">
              {DEMO_SEQUENCE.map(({ level }) => (
                <button
                  key={level}
                  type="button"
                  disabled={pending !== null}
                  onClick={() => void sendSample(level)}
                  className={`min-h-12 rounded-2xl border px-3 text-left text-[14.5px] font-medium disabled:opacity-50 ${
                    pending?.level === level ? "border-magenta text-magenta" : "border-line"
                  }`}
                >
                  {LEVEL_LABELS[level]}
                </button>
              ))}
            </div>
            <button type="button" onClick={() => void disableNotifications()} className="mt-4 min-h-11 text-[14px] font-medium text-muted underline underline-offset-2">
              Turn off notifications on this phone
            </button>
          </section>
        )}
      </div>
    </div>
  );
}
