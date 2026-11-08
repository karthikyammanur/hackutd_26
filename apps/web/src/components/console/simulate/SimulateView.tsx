import { useCallback, useEffect, useState, type ReactNode } from "react";
import { useRunMonitor } from "@/hooks/useRunMonitor";
import { api, ApiError, type RunRequest } from "@/lib/simulate/api";
import { familyLabel, humanize, ms, rate, show, UNAVAILABLE } from "@/lib/simulate/labels";
import {
  familySummaries,
  headline,
  parseCorpus,
  parseModelOptions,
  parseRuns,
  TERMINAL,
  type Corpus,
  type ModelOption,
  type RunSummary,
} from "@/lib/simulate/parse";
import { formatPercent } from "@/lib/console/format";
import { Columns, PanelTitle, SectionTitle, SideCard, StatGrid, Tag, Tile } from "../ui";
import { FamilyList, Legend, MethodBars, RateChart } from "./charts";
import { FigureSection } from "./FigureSection";
import { RescoreLevers } from "./RescoreLevers";
import { DecisionStream, DrillIn, MarkersAndLessons, ModelTable } from "./Results";
import { RunControls } from "./RunControls";

const isActive = (status: string | null) => status === "running" || status === "checking";

export function SimulateView() {
  const [corpus, setCorpus] = useState<Corpus | null>(null);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const refreshRuns = useCallback(async () => {
    const list = await api("/runs").then(parseRuns, () => []);
    setRuns(list);
  }, []);

  useEffect(() => {
    api("/corpus").then((value) => setCorpus(parseCorpus(value)), () => undefined);
    api("/models").then((value) => setModels(parseModelOptions(value)), () => undefined);
    api("/runs").then(
      (value) => {
        const list = parseRuns(value);
        setRuns(list);
        setRunId((current) => current ?? (list.find((run) => isActive(run.status)) ?? list[0])?.id ?? null);
      },
      () => undefined,
    );
  }, []);

  const start = async (request: RunRequest) => {
    setStarting(true);
    setStartError(null);
    try {
      const created = (await api("/runs", { method: "POST", body: request })) as { id?: string };
      if (created.id) setRunId(created.id);
      await refreshRuns();
    } catch (error) {
      const active = error instanceof ApiError ? (error.body as { id?: unknown } | null)?.id : undefined;
      if (typeof active === "string") setRunId(active);
      setStartError(error instanceof Error ? error.message : "The run couldn't start");
    } finally {
      setStarting(false);
    }
  };

  const onFinished = useCallback(() => void refreshRuns(), [refreshRuns]);
  const activeRun = runs.some((run) => run.id === runId && isActive(run.status));

  const controls = (
    <RunControls corpus={corpus} models={models} busy={starting || activeRun} error={startError} onStart={start} />
  );

  return (
    <RunPanel key={runId ?? "none"} runId={runId} runs={runs} onSelect={setRunId} onFinished={onFinished} controls={controls} />
  );
}

function RunPanel({
  runId,
  runs,
  onSelect,
  onFinished,
  controls,
}: {
  runId: string | null;
  runs: RunSummary[];
  onSelect: (id: string) => void;
  onFinished: () => void;
  controls: ReactNode;
}) {
  const monitor = useRunMonitor(runId, onFinished);
  const { live, seen, rescored } = monitor;
  const [family, setFamily] = useState<string | null>(null);
  const [pickedMethod, setPickedMethod] = useState<string | null>(null);
  const [cancelError, setCancelError] = useState<string | null>(null);

  const byMethod = rescored?.byMethod ?? live?.byMethod ?? null;
  const byModel = rescored?.byModel ?? live?.byModel ?? null;
  const families = familySummaries(byMethod);
  const shown = (byMethod ?? [])
    .filter((row) => !family || row.family === family)
    .sort((a, b) => a.family.localeCompare(b.family) || a.method.localeCompare(b.method));
  const picked = byMethod?.find((row) => row.method === pickedMethod) ?? null;
  const { score, note } = headline(byModel, byMethod);
  const finished = live?.status != null && TERMINAL.has(live.status);

  const cancel = async () => {
    setCancelError(null);
    await api(`/runs/${runId}/cancel`, { method: "POST" }).catch((error: unknown) =>
      setCancelError(error instanceof Error ? error.message : "The run couldn't be cancelled"),
    );
  };

  return (
    <Columns>
      <div className="min-w-0">
        <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
          <div>
            <div className="flex flex-wrap items-center gap-2.5 font-semibold">
              <Tile icon="flask" tint="sage" />
              {runId ? "Simulation" : "No simulation yet"}
              {live?.status && <span role="status"><Tag hot={isActive(live.status)}>{humanize(live.status)}</Tag></span>}
              {rescored && <Tag>Rescored</Tag>}
            </div>
            <div className="mt-3.5 text-[44px] leading-[1.1] font-semibold tracking-[-0.03em]">
              {score === null ? "--" : formatPercent(score)}
              <small className="ml-1 text-[17px] font-medium tracking-[-0.01em] text-ink-3">{note}</small>
            </div>
            <div className="mt-2 text-ink-2">
              {show(live?.processed ?? null, (value) => value.toLocaleString())} of {show(live?.total ?? null, (value) => value.toLocaleString())} cases
              {live?.elapsedS != null && `, ${live.elapsedS.toFixed(1)} s`}
            </div>
            {live?.weakLabels && (
              <div className="mt-1 text-[13px] text-ink-3">
                {live.weakLabels.n} cases with inferred labels are scored separately:{" "}
                {live.weakLabels.score === null ? "n/a" : formatPercent(live.weakLabels.score)}
              </div>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {runs.length > 0 && (
              <select
                aria-label="Run"
                value={runId ?? ""}
                onChange={(event) => onSelect(event.target.value)}
                className="h-10 max-w-[240px] rounded-full border border-line bg-white px-3 text-[13px]"
              >
                {runs.map((run) => (
                  <option key={run.id} value={run.id}>
                    {run.id} ({run.status ?? "unknown"})
                  </option>
                ))}
              </select>
            )}
            {live?.status && isActive(live.status) && (
              <button onClick={cancel} className="h-10 rounded-full border border-line bg-white px-4 font-medium hover:bg-sunk">
                Cancel
              </button>
            )}
          </div>
        </div>
        {cancelError && (
          <p role="alert" className="mt-3 font-medium text-mag-deep">
            {cancelError}
          </p>
        )}
        {monitor.error && (
          <p role="alert" className="mt-3 font-medium text-mag-deep">
            Live data is unavailable: {monitor.error}
          </p>
        )}

        <FigureSection
          running={isActive(live?.status ?? null)}
          live={live}
          active={monitor.active}
          seen={seen}
          markers={monitor.markers}
          lessons={monitor.lessons}
          byMethod={byMethod}
          score={score}
          paused={monitor.error !== null}
        />

        <section className="mt-10">
          <div className="mb-3.5 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <SectionTitle>Scam families</SectionTitle>
            {family ? (
              <span className="text-[13px] text-ink-2">
                Showing only {familyLabel(family)}.{" "}
                <button onClick={() => setFamily(null)} className="rounded font-medium text-ink underline">
                  Show all families
                </button>
              </span>
            ) : (
              families.length > 1 && <span className="text-[13px] text-ink-3">Lowest score first</span>
            )}
          </div>
          {byMethod === null ? (
            <Unavailable text={live ? `Method results: ${UNAVAILABLE.toLowerCase()}.` : "Results appear when a run starts."} />
          ) : (
            <FamilyList families={families} unit={byModel?.length === 1 ? "call" : "result"} picked={family} onPick={setFamily} />
          )}
        </section>

        <section className="mt-10">
          <div className="mb-3.5 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <span className="flex items-center gap-2">
              <SectionTitle>By method</SectionTitle>
              {family && <Tag>{familyLabel(family)}</Tag>}
            </span>
            <Legend />
          </div>
          {shown.length ? <MethodBars methods={shown} picked={pickedMethod} onPick={setPickedMethod} /> : <Unavailable text="Methods appear here as results finish." />}
        </section>

        {picked && (
          <section className="mt-10">
            <div className="mb-3.5">
              <SectionTitle>{humanize(picked.method)}</SectionTitle>
            </div>
            <DrillIn row={picked} seen={seen} />
          </section>
        )}

        <section className="mt-10">
          <div className="mb-3.5">
            <SectionTitle>Model comparison</SectionTitle>
          </div>
          <ModelTable models={live ? byModel : []} />
        </section>

        <section className="mt-10">
          <div className="mb-3.5">
            <SectionTitle>Latest decisions</SectionTitle>
          </div>
          <DecisionStream seen={seen} />
        </section>

        <section className="mt-10">
          <div className="mb-3.5 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <SectionTitle>Failure markers and lessons</SectionTitle>
            <span className="text-[13px] text-ink-3">Written by the check agent</span>
          </div>
          <MarkersAndLessons runId={runId} markers={monitor.markers} lessons={monitor.lessons} />
        </section>
      </div>

      <aside className="min-w-0">
        {controls}

        <RescoreLevers
          enabled={finished}
          applied={rescored !== null}
          error={monitor.rescoreError}
          onChange={monitor.rescore}
          onReset={monitor.resetRescore}
        />

        <SideCard>
          <PanelTitle>Throughput</PanelTitle>
          <StatGrid
            items={[
              ["Jev decisions / s", show(live?.decisionsPerS ?? null, rate)],
              ["Frames / s", show(live?.framesPerS ?? null, rate)],
              ["Lanes active", show(live?.lanesActive ?? null)],
              ["Lanes configured", show(live?.lanesConfigured ?? null)],
              ["Jev median", show(live?.steps.find((step) => step.name === "jev")?.p50 ?? null, ms)],
              ["Jev p95", show(live?.steps.find((step) => step.name === "jev")?.p95 ?? null, ms)],
            ]}
          />
          <div className="mt-4">
            <RateChart timeline={live?.timeline ?? []} />
          </div>
        </SideCard>

        <SideCard>
          <PanelTitle>Brev</PanelTitle>
          <p className="mt-1 text-[13px] text-ink-2">Instances reported: <b className="font-medium text-ink">{show(live?.brevInstances ?? null)}</b></p>
          <div className="mt-3">
            {live?.endpoints === null || !live ? (
              <p className="text-[13px] text-ink-3">Endpoint health is unavailable.</p>
            ) : (
              live.endpoints.map((endpoint) => (
                <div key={endpoint.name} className="flex items-center justify-between border-t border-line py-[11px]">
                  <b className="font-semibold">{endpoint.name}</b>
                  <span className="inline-flex items-center gap-[7px] text-[13px] text-ink-2">
                    <i className={`size-2 rounded-full ${endpoint.healthy === true ? "bg-[#1B1B1B]" : endpoint.healthy === false ? "bg-mag" : "bg-ink-3"}`} />
                    {endpoint.healthy === null ? UNAVAILABLE : endpoint.healthy ? "Healthy" : "Down"}
                  </span>
                </div>
              ))
            )}
          </div>
        </SideCard>

        <SideCard>
          <PanelTitle>What gets saved</PanelTitle>
          <p className="mt-1.5 text-ink-2">Only scores, flags, ids and markers. Call and message text is never shown here.</p>
        </SideCard>
      </aside>
    </Columns>
  );
}

function Unavailable({ text }: { text: string }) {
  return <div className="rounded-[18px] bg-card px-[22px] py-5 text-ink-2 shadow-soft">{text}</div>;
}
