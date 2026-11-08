import { useSyncExternalStore } from "react";
import { EvidenceView } from "./evidence/EvidenceView";
import { HomeView } from "./home/HomeView";
import { Icon, type IconName } from "./icons";
import { LiveAgents } from "./live/LiveAgents";
import { SimulateView } from "./simulate/SimulateView";
import { TooltipProvider } from "./Tooltip";

type ConsoleWindow = "home" | "live" | "simulate" | "evidence";

const WINDOWS: { id: ConsoleWindow; label: string; icon: IconName }[] = [
  { id: "home", label: "Home", icon: "home" },
  { id: "live", label: "Live agents", icon: "nodes" },
  { id: "simulate", label: "Simulate", icon: "base" },
  { id: "evidence", label: "Evidence", icon: "search" },
];

const SEGMENT_WIDTH = 112;
const WINDOW_PANE = "h-full flex-1 basis-0 min-w-0 overflow-y-auto pt-2 pr-4 pb-[72px] pl-2 sm:pr-11 sm:pl-5";

function subscribeToHash(onChange: () => void) {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

function readWindow(): ConsoleWindow {
  const hash = window.location.hash.slice(1);
  return WINDOWS.find((w) => w.id === hash)?.id ?? "home";
}

function openWindow(id: ConsoleWindow) {
  window.location.hash = id;
}

export function ConsoleShell() {
  const current = useSyncExternalStore<ConsoleWindow>(subscribeToHash, readWindow);
  const index = WINDOWS.findIndex((w) => w.id === current);

  return (
    <TooltipProvider>
      <div className="flex h-dvh overflow-hidden">
        <nav className="flex w-14 flex-none sm:w-[76px] flex-col items-center gap-2 py-[22px]" aria-label="Main">
          <div
            aria-label="Safe Signal"
            role="img"
            className="mb-6 grid size-9 place-items-center rounded-lg bg-mag text-[21px] font-bold text-white"
          >
            S
          </div>
          {WINDOWS.map((w) => (
            <button
              key={w.id}
              onClick={() => openWindow(w.id)}
              title={w.label}
              aria-label={w.label}
              aria-current={w.id === current ? "page" : undefined}
              className={`grid size-10 place-items-center rounded-[11px] ${
                w.id === current ? "bg-sunk text-ink" : "text-ink-2 hover:bg-sunk"
              }`}
            >
              <Icon name={w.icon} />
            </button>
          ))}
        </nav>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-[76px] flex-none items-center justify-between pr-4 pl-2 sm:pr-11 sm:pl-5">
            <h1 className="text-lg font-semibold tracking-[-0.015em]">{current === "home" ? "Safe Signal" : WINDOWS[index].label}</h1>
            <div role="group" aria-label="Window" className="relative hidden rounded-full border border-line bg-white p-1 md:flex">
              <i
                className="absolute top-1 left-1 h-[34px] rounded-full bg-sunk transition-transform duration-[450ms] ease-slide"
                style={{ width: SEGMENT_WIDTH, transform: `translateX(${SEGMENT_WIDTH * index}px)` }}
              />
              {WINDOWS.map((w) => (
                <button
                  key={w.id}
                  onClick={() => openWindow(w.id)}
                  aria-pressed={w.id === current}
                  style={{ width: SEGMENT_WIDTH }}
                  className={`relative z-10 h-[34px] rounded-full font-medium transition-colors duration-300 ${
                    w.id === current ? "text-ink" : "text-ink-2"
                  }`}
                >
                  {w.label}
                </button>
              ))}
            </div>
          </header>

          <div className="min-h-0 flex-1 overflow-hidden">
            <div
              className="flex h-full transition-transform duration-[550ms] ease-slide"
              style={{ width: `${WINDOWS.length * 100}%`, transform: `translateX(${(-100 / WINDOWS.length) * index}%)` }}
            >
              <main inert={current !== "home"} className={WINDOW_PANE}>
                <HomeView active={current === "home"} />
              </main>
              <main inert={current !== "live"} className={WINDOW_PANE}>
                <LiveAgents />
              </main>
              <main inert={current !== "simulate"} className={WINDOW_PANE}>
                <SimulateView />
              </main>
              <main inert={current !== "evidence"} className={WINDOW_PANE}>
                <EvidenceView active={current === "evidence"} />
              </main>
            </div>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
