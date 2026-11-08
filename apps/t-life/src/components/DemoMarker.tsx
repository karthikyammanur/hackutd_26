/** Always on top, on every screen. Keeps this from passing as the real app. */
export function DemoMarker({ inCall }: { inCall: boolean }) {
  return (
    <div className="column-fixed pointer-events-none top-[calc(env(safe-area-inset-top)+8px)] z-60 flex justify-center gap-1.5">
      <span
        role="note"
        aria-label="Demo. This is not a real T-Mobile app."
        className="rounded-full border border-white/40 bg-tile px-2.5 py-0.5 text-[12px] font-semibold leading-[18px] text-white"
      >
        Demo
      </span>
      {inCall && (
        <span className="flex items-center gap-1 rounded-full bg-ok px-2.5 py-0.5 text-[12px] font-semibold leading-[18px] text-white">
          <span aria-hidden="true" className="size-1.5 rounded-full bg-white" />
          On a call
        </span>
      )}
    </div>
  );
}
