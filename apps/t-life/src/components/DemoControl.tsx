import { DEMO_SEQUENCE, LEVEL_LABELS } from "../lib/notices";

/** Presenter control. Hidden during full-screen states so they keep their exact actions. */
export function DemoControl({
  step,
  pushed,
  visible,
  onFire,
}: {
  step: number;
  pushed: boolean;
  visible: boolean;
  onFire: () => void;
}) {
  const next = DEMO_SEQUENCE[step];
  const label = next ? `Next ${step + 1}/${DEMO_SEQUENCE.length}` : "Restart";
  return (
    <div
      className={`column-fixed pointer-events-none z-30 justify-end pr-2 ${visible ? "flex" : "hidden"} ${
        pushed ? "bottom-[calc(env(safe-area-inset-bottom)+6px)]" : "bottom-[calc(env(safe-area-inset-bottom)+60px)]"
      }`}
    >
      <button
        type="button"
        onClick={onFire}
        aria-label={next ? `Demo control. Send next notice: ${LEVEL_LABELS[next.level]}` : "Demo control. Restart demo"}
        className="pointer-events-auto flex min-h-11 min-w-11 items-center rounded-full px-1"
      >
        <span className="rounded-full border border-line bg-white/90 px-2.5 py-1 text-[11px] font-medium leading-4 text-muted backdrop-blur-sm">
          {label}
        </span>
      </button>
    </div>
  );
}
