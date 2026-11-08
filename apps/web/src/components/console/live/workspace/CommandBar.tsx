import { useState, type FormEvent } from "react";
import type { LiveLink, SearchResult, TLifeStatus } from "@/hooks/useCallSessions";
import { SCENARIOS } from "@/lib/console/scenarios";
import { SectionTitle } from "../../ui";

const HINT = "Exact full number only. Nothing is saved.";

interface CommandBarProps {
  count: number;
  tlife: TLifeStatus | null;
  live: LiveLink;
  onSearch: (raw: string) => SearchResult;
  onPlace: (scenarioId: string) => void;
  onPlaceLive: () => void;
}

function liveNote(live: LiveLink): string {
  if (live.placing) return "Ringing the demo phone…";
  if (live.note) return live.note;
  if (live.api === "ready") return "Rings the demo phone from the scammer line.";
  if (live.api === "offline") return "The live API is offline.";
  return "Checking the live API…";
}

export function CommandBar({ count, tlife, live, onSearch, onPlace, onPlaceLive }: CommandBarProps) {
  const [number, setNumber] = useState("");
  const [note, setNote] = useState(HINT);
  const [scenarioId, setScenarioId] = useState(SCENARIOS[0].id);

  function submit(event: FormEvent) {
    event.preventDefault();
    const result = onSearch(number);
    if (result.ok) {
      setNumber("");
      setNote(`Opened the call on the number ending in ${result.mask}.`);
    } else if (result.reason === "incomplete") {
      setNote("Enter all 10 digits of the number.");
    } else {
      setNote("No call in progress on that number.");
    }
  }

  return (
    <div className="flex flex-wrap items-start gap-x-4 gap-y-2">
      <div className="flex h-11 flex-1 basis-[200px] items-center gap-2">
        <SectionTitle>Calls in progress</SectionTitle>
        <span className="text-ink-3 tabular-nums">{count}</span>
        {tlife && tlife.phones > 0 && (
          <span className="ml-3 inline-flex items-center gap-1.5 text-[13px] text-ink-2">
            <i className="size-2 rounded-full bg-[#3C9A5F]" aria-hidden="true" />
            {`Lock-screen notices on ${tlife.phones} phone${tlife.phones === 1 ? "" : "s"}`}
          </span>
        )}
      </div>

      <form onSubmit={submit} className="w-[276px]" autoComplete="off" role="search">
        <label htmlFor="console-call-search" className="sr-only">
          Full phone number
        </label>
        <input
          id="console-call-search"
          type="text"
          inputMode="tel"
          autoComplete="off"
          spellCheck={false}
          maxLength={20}
          value={number}
          onChange={(event) => setNumber(event.target.value)}
          placeholder="Search a full phone number"
          className="h-11 w-full rounded-full border border-line bg-card px-4 outline-none placeholder:text-ink-3 focus:border-mag"
        />
        <p role="status" className="mt-1 pl-4 text-[12.5px] text-ink-2">
          {note}
        </p>
      </form>

      <div className="flex items-center gap-2">
        <label htmlFor="console-scenario" className="sr-only">
          Test call scenario
        </label>
        <select
          id="console-scenario"
          value={scenarioId}
          onChange={(event) => setScenarioId(event.target.value)}
          className="h-11 w-[300px] rounded-full border border-line bg-card pr-3 pl-4 text-ink"
        >
          {SCENARIOS.map((scenario) => (
            <option key={scenario.id} value={scenario.id}>
              {scenario.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => onPlace(scenarioId)}
          className="h-11 rounded-full bg-mag px-6 font-semibold whitespace-nowrap text-white transition-colors hover:bg-mag-deep"
        >
          Place test call
        </button>
      </div>

      <div className="w-[236px]">
        <button
          type="button"
          onClick={onPlaceLive}
          disabled={live.placing || live.api === "offline"}
          className="h-11 w-full rounded-full border-2 border-mag px-5 font-semibold whitespace-nowrap text-mag transition-colors hover:bg-mag hover:text-white disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:bg-transparent disabled:hover:text-mag"
        >
          {live.placing ? "Placing real call…" : "Place real call"}
        </button>
        <p role="status" className="mt-1 pl-4 text-[12.5px] text-ink-2">
          {liveNote(live)}
        </p>
      </div>
    </div>
  );
}
