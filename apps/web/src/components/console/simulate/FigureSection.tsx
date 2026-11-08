import { useId, useState } from "react";
import { SectionTitle, Tag, Tile } from "../ui";
import { ArchitectureFigure, type ArchitectureFigureProps } from "./architecture/ArchitectureFigure";
import { figureView } from "./architecture/model";
import { usePreviewRun } from "./architecture/usePreviewRun";

const STORAGE_KEY = "safe-signal:simulate:figure";

function readOpen(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) !== "closed";
  } catch {
    return true;
  }
}

function saveOpen(open: boolean) {
  try {
    window.localStorage.setItem(STORAGE_KEY, open ? "open" : "closed");
  } catch {
    // The choice just won't be remembered.
  }
}

/**
 * The architecture figure with its preview controls. Hidden, it renders one line instead of the
 * figure, so no SVG animates and no preview timer runs. The toggle stays the same element in both
 * states, so keyboard focus survives the switch.
 */
export function FigureSection({ running, ...figure }: ArchitectureFigureProps & { running: boolean }) {
  const [open, setOpen] = useState(readOpen);
  const [toggled, setToggled] = useState(false);
  const preview = usePreviewRun();
  const panelId = useId();
  const collapsed = open ? null : figureView(figure);

  const toggle = () => {
    setOpen(!open);
    setToggled(true);
    saveOpen(!open);
    if (open) preview.stop();
  };

  return (
    <section className="mt-8">
      <div
        className={
          collapsed
            ? "relative flex items-center gap-3 overflow-hidden rounded-[18px] bg-card px-[22px] py-3.5 shadow-soft"
            : "mb-3 flex flex-wrap items-center gap-3"
        }
      >
        {collapsed && (
          <div
            className="absolute top-0 left-0 h-[3px] bg-mag transition-[width] duration-500 ease-slide"
            style={{ width: `${(collapsed.progress ?? 0) * 100}%` }}
          />
        )}
        {collapsed && <Tile icon="nodes" tint="grey" />}
        <div className="min-w-0 flex-1 basis-40">
          {collapsed ? (
            <p className="truncate" title={collapsed.summary}>
              <b className="font-semibold">{collapsed.headline}</b>
              <span className="ml-2 text-ink-2">{collapsed.detail}</span>
            </p>
          ) : (
            <SectionTitle>How it works</SectionTitle>
          )}
        </div>
        {!collapsed && preview.data && <Tag>Preview with sample data, no models are running</Tag>}
        {!collapsed && preview.data && (
          <button onClick={preview.stop} className="h-10 rounded-full border border-line bg-white px-4 font-medium hover:bg-sunk">
            Back to the latest run
          </button>
        )}
        {!collapsed && !running && (
          <button onClick={preview.start} className="h-10 rounded-full bg-mag px-5 font-semibold text-white hover:bg-mag-deep">
            {preview.data ? "Play again" : "Preview a run"}
          </button>
        )}
        <button
          onClick={toggle}
          aria-expanded={open}
          aria-controls={panelId}
          aria-label={open ? "Hide how it works" : "Show how it works"}
          className="flex h-10 flex-none items-center gap-1.5 rounded-full border border-line bg-white px-4 font-medium hover:bg-sunk"
        >
          {open ? "Hide" : "Show how it works"}
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={`transition-transform duration-200 ${open ? "rotate-180" : ""}`}>
            <path d="M2.5 4.5 6 8l3.5-3.5" />
          </svg>
        </button>
      </div>
      <div id={panelId}>
        {open && (
          <div className={toggled ? "animate-rise" : undefined}>
            <ArchitectureFigure {...(preview.data ? { ...preview.data, paused: false } : figure)} />
          </div>
        )}
      </div>
    </section>
  );
}
