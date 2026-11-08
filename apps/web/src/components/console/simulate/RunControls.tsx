import { useState, type ReactNode } from "react";
import type { RunRequest } from "@/lib/simulate/api";
import { humanize } from "@/lib/simulate/labels";
import type { Corpus, ModelOption, Named } from "@/lib/simulate/parse";
import { PanelTitle, SideCard } from "../ui";

const MAX_LIMIT = 20000;
const MAX_LANES = 128;

function toggled(list: string[], value: string) {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
}

export function Lever({
  label,
  value,
  children,
}: {
  label: string;
  value: string | number;
  children: ReactNode;
}) {
  return (
    <label className="mt-3.5 block">
      <span className="flex justify-between text-[13px] text-ink-2">
        {label}
        <b className="font-medium text-ink">{value}</b>
      </span>
      {children}
    </label>
  );
}

function Chips({
  label,
  options,
  selected,
  onChange,
  emptyMeans,
}: {
  label: string;
  options: Named[];
  selected: string[];
  onChange: (next: string[]) => void;
  emptyMeans: string;
}) {
  return (
    <fieldset className="mt-3.5">
      <legend className="text-[13px] text-ink-2">
        {label}
        {selected.length === 0 && <span className="text-ink-3"> ({emptyMeans})</span>}
      </legend>
      {options.length === 0 ? (
        <p className="mt-1 text-[13px] text-ink-3">Options unavailable</p>
      ) : (
        <div className="mt-1.5 flex max-h-40 flex-wrap gap-1.5 overflow-y-auto">
          {options.map((option) => {
            const on = selected.includes(option.name);
            return (
              <button
                key={option.name}
                type="button"
                aria-pressed={on}
                onClick={() => onChange(toggled(selected, option.name))}
                className={`rounded-full px-2.5 py-1 text-xs font-medium ${on ? "bg-ink text-white" : "bg-sunk text-ink-2"}`}
              >
                {humanize(option.name)}
                {option.count !== null && <span className="opacity-60"> {option.count.toLocaleString()}</span>}
              </button>
            );
          })}
        </div>
      )}
    </fieldset>
  );
}

const FALLBACK_CHANNELS: Named[] = [
  { name: "call", count: null },
  { name: "sms", count: null },
];

export function RunControls({
  corpus,
  models,
  busy,
  error,
  onStart,
}: {
  corpus: Corpus | null;
  models: ModelOption[];
  busy: boolean;
  error: string | null;
  onStart: (request: RunRequest) => void;
}) {
  const [limit, setLimit] = useState(MAX_LIMIT);
  const [lanes, setLanes] = useState(32);
  const [windowTurns, setWindowTurns] = useState(6);
  const [channels, setChannels] = useState<string[]>(["call", "sms"]);
  const [methods, setMethods] = useState<string[]>([]);
  const [sources, setSources] = useState<string[]>([]);
  const [picked, setPicked] = useState<string[]>([]);

  return (
    <SideCard className="mt-0!">
      <PanelTitle>Run levers</PanelTitle>

      <Lever label="Cases" value={limit.toLocaleString()}>
        <input className="mt-1 w-full accent-mag" type="range" min={10} max={MAX_LIMIT} step={10} value={limit} onChange={(e) => setLimit(Number(e.target.value))} />
      </Lever>
      <Lever label="Parallel lanes" value={lanes}>
        <input className="mt-1 w-full accent-mag" type="range" min={1} max={MAX_LANES} value={lanes} onChange={(e) => setLanes(Number(e.target.value))} />
      </Lever>
      <Lever label="Verbatim window" value={`${windowTurns} turns`}>
        <input className="mt-1 w-full accent-mag" type="range" min={2} max={12} value={windowTurns} onChange={(e) => setWindowTurns(Number(e.target.value))} />
      </Lever>

      <Chips label="Channels" options={corpus?.channels.length ? corpus.channels : FALLBACK_CHANNELS} selected={channels} onChange={setChannels} emptyMeans="all" />
      <Chips label="Models" options={models.map((model) => ({ name: model.name, count: null }))} selected={picked} onChange={setPicked} emptyMeans="backend default" />
      <Chips label="Sources" options={corpus?.sources ?? []} selected={sources} onChange={setSources} emptyMeans="all" />
      <Chips label="Scam methods" options={corpus?.methods ?? []} selected={methods} onChange={setMethods} emptyMeans="all" />

      <button
        onClick={() => onStart({ limit, lanes, window_turns: windowTurns, channels, methods, sources, models: picked })}
        disabled={busy}
        className="mt-5 inline-flex h-10 w-full items-center justify-center rounded-full bg-mag px-[18px] font-medium text-white hover:bg-mag-deep disabled:opacity-55"
      >
        {busy ? "Run in progress" : "Simulate"}
      </button>
      {error && (
        <p role="alert" className="mt-2.5 text-[13px] font-medium text-mag-deep">
          {error}
        </p>
      )}
      <p className="mt-2.5 text-[12.5px] text-ink-3">
        This site allows up to {MAX_LIMIT.toLocaleString()} cases and {MAX_LANES} lanes per run. Runs that use Jev are limited to 2,000 cases, and to 20 runs or 20,000 cases per UTC day.
      </p>
    </SideCard>
  );
}
