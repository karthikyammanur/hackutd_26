import { DEMO_SPEEDS } from "@/hooks/useCallSessions";

interface DemoControlsProps {
  playing: boolean;
  speed: number;
  canSkip: boolean;
  onToggle: () => void;
  onSpeed: (speed: number) => void;
  onSkip: () => void;
}

/** Small on purpose. Place test call is the main control; this only paces the simulation. */
export function DemoControls({ playing, speed, canSkip, onToggle, onSpeed, onSkip }: DemoControlsProps) {
  return (
    <div className="flex items-center gap-2 text-[13px]" role="group" aria-label="Demo pace">
      {canSkip && (
        <button type="button" onClick={onSkip} className="mr-1 text-ink-2 underline-offset-2 hover:text-ink hover:underline">
          Skip to after the call
        </button>
      )}
      <button
        type="button"
        onClick={onToggle}
        aria-label={playing ? "Pause demo" : "Play demo"}
        className="grid size-8 place-items-center rounded-full bg-sunk hover:bg-wire"
      >
        <svg viewBox="0 0 16 16" className="size-3.5" fill="currentColor" aria-hidden>
          {playing ? (
            <path d="M4 2.5h3v11H4zM9 2.5h3v11H9z" />
          ) : (
            <path d="M4.5 2.3v11.4c0 .4.4.6.7.4l8.2-5.7c.3-.2.3-.6 0-.8L5.2 1.9c-.3-.2-.7 0-.7.4z" />
          )}
        </svg>
      </button>
      <div className="flex rounded-full bg-sunk p-0.5">
        {DEMO_SPEEDS.map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => onSpeed(option)}
            aria-pressed={speed === option}
            aria-label={`Speed ${option} times`}
            className={`h-7 rounded-full px-2.5 font-medium ${speed === option ? "bg-card text-ink shadow-soft" : "text-ink-2"}`}
          >
            {option}×
          </button>
        ))}
      </div>
    </div>
  );
}
