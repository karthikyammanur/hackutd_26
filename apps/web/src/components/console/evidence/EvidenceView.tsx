import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useEvidence } from "@/hooks/useEvidence";
import { evidenceApi, exportCsvUrl } from "@/lib/evidence/api";
import { CATEGORICAL, FAMILY_COLORS, formatDay, formatHour, label, risk, TIER_COLORS, TIER_ORDER } from "@/lib/evidence/labels";
import {
  countValue,
  EMPTY_FILTERS,
  formatCount,
  parseIncidentPage,
  parseMethods,
  parseOverview,
  parseSignalStats,
  parseTimeseries,
  toQuery,
  type Filters,
  type Incident,
} from "@/lib/evidence/parse";
import { familyLabel, flagLabel, humanize } from "@/lib/simulate/labels";
import { Card, Columns, PanelTitle, SectionTitle, SideCard, StatGrid, Tag } from "../ui";
import { Empty, MethodLeaderboard, SignalBars, SignalHeatmap, StackedDays, TierMix, type HeatRow, type Series } from "./EvidenceCharts";
import { IncidentDrawer } from "./IncidentDrawer";

const SEARCH_DELAY_MS = 300;
const PAGE_SIZE = 25;
const HEATMAP_ROWS = 8;
const HEATMAP_COLUMNS = 8;

type GroupBy = "family" | "method" | "tier";
type View = "search" | "charts";

const CONTROL = "w-full min-w-0 rounded-[10px] border border-line bg-white px-2.5 py-2 text-[13px]";

function Select({ name, value, options, onChange, format = humanize }: {
  name: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
  format?: (value: string) => string;
}) {
  return (
    <label className="min-w-0 text-[12.5px] text-ink-2">
      {name}
      <select value={value} onChange={(event) => onChange(event.target.value)} className={`mt-1 ${CONTROL} text-ink`}>
        <option value="">All</option>
        {options.map((option) => (
          <option key={option} value={option}>{format(option)}</option>
        ))}
      </select>
    </label>
  );
}

function Segment<T extends string>({ label: name, value, options, onChange }: {
  label: string;
  value: T;
  options: [T, string][];
  onChange: (value: T) => void;
}) {
  return (
    <div role="group" aria-label={name} className="inline-flex rounded-full bg-sunk p-1">
      {options.map(([id, text]) => (
        <button
          key={id}
          type="button"
          aria-pressed={id === value}
          onClick={() => onChange(id)}
          className={`rounded-full px-3.5 py-1 text-[13px] font-medium transition-colors duration-300 ${id === value ? "bg-white text-ink" : "text-ink-2"}`}
        >
          {text}
        </button>
      ))}
    </div>
  );
}

function ChartCard({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <Card className="min-w-0 p-[22px]">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <PanelTitle>{title}</PanelTitle>
        {action}
      </div>
      {children}
    </Card>
  );
}

function ResultRow({ incident, onOpen }: { incident: Incident; onOpen: () => void }) {
  return (
    <button type="button" onClick={onOpen} className="-mx-2.5 block w-[calc(100%+20px)] animate-rise rounded-xl px-2.5 py-3 text-left hover:bg-canvas">
      <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <b className="min-w-0 font-semibold">{label(incident.method)}</b>
        {incident.tier && (
          <span className="flex items-center gap-1 text-[12.5px] font-medium">
            <i aria-hidden="true" className="size-2 rounded-[2px]" style={{ background: TIER_COLORS[incident.tier] ?? "#a8a8a8" }} />
            {humanize(incident.tier)}
          </span>
        )}
        {incident.source === "sandbox_synthetic" && <Tag>Synthetic test data</Tag>}
      </span>
      <small className="mt-0.5 block text-[13px] text-ink-2">
        {[incident.channel && humanize(incident.channel), incident.family && familyLabel(incident.family), formatHour(incident.occurredHour), `Peak risk ${risk(incident.maxRisk)}`]
          .filter(Boolean)
          .join(" · ")}
      </small>
      {incident.summary && <span className="mt-1 line-clamp-2 block text-[13px]">{incident.summary}</span>}
      {incident.signals.length > 0 && (
        <span className="mt-1.5 flex flex-wrap gap-1">
          {incident.signals.slice(0, 4).map((signal) => (
            <Tag key={signal.signal}>{flagLabel(signal.signal)}</Tag>
          ))}
        </span>
      )}
    </button>
  );
}

function useHeatmap(enabled: boolean, methods: string[], range: string) {
  const key = enabled && methods.length ? `${methods.join(",")}|${range}` : null;
  const [loaded, setLoaded] = useState<{ key: string; rows: Map<string, ReturnType<typeof parseSignalStats>> } | null>(null);

  useEffect(() => {
    if (!key) return;
    const controller = new AbortController();
    const separator = range ? `${range}&` : "?";
    Promise.all(
      methods.map((method) =>
        evidenceApi(`/stats/signals${separator}method=${encodeURIComponent(method)}`, controller.signal).then(
          (value) => [method, parseSignalStats(value)] as const,
        ),
      ),
    ).then(
      (rows) => setLoaded({ key, rows: new Map(rows) }),
      () => undefined,
    );
    return () => controller.abort();
    // `key` already covers the methods and range.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return loaded?.rows ?? null;
}

export function EvidenceView({ active }: { active: boolean }) {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [query, setQuery] = useState("");
  const [view, setView] = useState<View>("search");
  const [groupBy, setGroupBy] = useState<GroupBy>("family");
  const [opened, setOpened] = useState<string | null>(null);
  const [visited, setVisited] = useState(active);
  const [more, setMore] = useState<{ base: string; items: Incident[]; cursor: string | null } | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState<string | null>(null);

  if (active && !visited) setVisited(true);

  useEffect(() => {
    const timer = setTimeout(() => setQuery(filters.q.trim()), SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [filters.q]);

  const set = (key: keyof Filters) => (value: string) => setFilters((current) => ({ ...current, [key]: value }));

  const search = toQuery({ ...filters, q: query });
  const range = toQuery({ from: filters.from, to: filters.to, source: filters.source });
  const base = `/incidents${toQuery({ ...filters, q: query, limit: String(PAGE_SIZE) })}`;

  const allMethods = useEvidence(visited ? "/stats/methods" : null, parseMethods);
  const overview = useEvidence(visited ? `/stats/overview${range}` : null, parseOverview);
  const methods = useEvidence(visited ? `/stats/methods${range}` : null, parseMethods);
  const signals = useEvidence(visited ? `/stats/signals${range}` : null, parseSignalStats);
  const page = useEvidence(visited ? base : null, parseIncidentPage);
  const series = useEvidence(
    visited && view === "charts" ? `/stats/timeseries${toQuery({ bucket: "day", by: groupBy, from: filters.from, to: filters.to, source: filters.source })}` : null,
    parseTimeseries,
  );

  const topMethods = useMemo(() => (methods.data ?? []).slice(0, HEATMAP_ROWS).map((row) => row.method), [methods.data]);
  const heat = useHeatmap(visited && view === "charts", topMethods, range);

  // Colours come from the all-time ranking, so changing a filter can't repaint a method.
  const methodSeries = useMemo<Series[]>(
    () => (allMethods.data ?? []).slice(0, CATEGORICAL.length).map((row, index) => ({ key: row.method, label: humanize(row.method), color: CATEGORICAL[index] })),
    [allMethods.data],
  );

  const chartSeries: Series[] =
    groupBy === "family"
      ? Object.entries(FAMILY_COLORS).map(([key, color]) => ({ key, label: familyLabel(key), color }))
      : groupBy === "tier"
        ? TIER_ORDER.map((key) => ({ key, label: humanize(key), color: TIER_COLORS[key] }))
        : methodSeries;

  const extra = more?.base === base ? more : null;
  const items = [...(page.data?.items ?? []), ...(extra?.items ?? [])];
  const nextCursor = extra ? extra.cursor : (page.data?.nextCursor ?? null);

  const loadMore = async () => {
    if (!nextCursor) return;
    setLoadingMore(true);
    setMoreError(null);
    try {
      const next = parseIncidentPage(await evidenceApi(`/incidents${toQuery({ ...filters, q: query, limit: String(PAGE_SIZE), cursor: nextCursor })}`));
      setMore({ base, items: [...(extra?.items ?? []), ...next.items], cursor: next.nextCursor });
    } catch (error) {
      setMoreError(error instanceof Error ? error.message : "More results couldn't load");
    } finally {
      setLoadingMore(false);
    }
  };

  const heatRows: HeatRow[] = (methods.data ?? [])
    .filter((row) => heat?.has(row.method))
    .slice(0, HEATMAP_ROWS)
    .map((row) => ({ method: row.method, total: row.total, signals: heat?.get(row.method) ?? [] }));
  const heatColumns = (signals.data ?? []).slice(0, HEATMAP_COLUMNS).map((bucket) => bucket.key);

  const data = overview.data;
  const dangerous = data?.byTier.find((bucket) => bucket.key === "dangerous")?.count ?? null;
  const familyOptions = [...new Set((allMethods.data ?? []).flatMap((row) => row.family ?? []))].sort();
  const methodOptions = (allMethods.data ?? []).map((row) => row.method).sort();
  const signalOptions = (signals.data ?? []).map((bucket) => bucket.key).sort();
  const hasSynthetic = data?.bySource.some((bucket) => bucket.key === "sandbox_synthetic" && countValue(bucket.count) > 0) ?? false;
  const filtersActive = Object.values(filters).some(Boolean);
  const unavailable = overview.error && page.error;
  const suppressed = (series.data ?? []).some((point) => Object.values(point.values).includes("<5"));

  const pickMethod = (method: string) => {
    setFilters((current) => ({ ...current, method }));
    setView("search");
  };

  return (
    <Columns>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <SectionTitle>Incident evidence</SectionTitle>
          {hasSynthetic && <Tag hot>Synthetic test data</Tag>}
        </div>
        <p className="mt-1 text-ink-2">Anonymous indicators from past incidents. No transcript, audio or personal data is stored.</p>

        {unavailable && (
          <Card className="mt-4 p-5">
            <p className="font-medium">The evidence store is unavailable</p>
            <p className="mt-1 text-[13px] text-ink-2">{overview.error}</p>
          </Card>
        )}

        <Card className="mt-4 p-4 sm:p-5">
          <label className="block text-[12.5px] text-ink-2">
            Search indicators
            <input
              type="search"
              value={filters.q}
              maxLength={200}
              onChange={(event) => {
                set("q")(event.target.value);
                setView("search");
              }}
              placeholder="Try gift cards, bank fraud, remote access"
              className={`mt-1 ${CONTROL} py-2.5 text-[14px] text-ink`}
            />
          </label>
          <div className="mt-3 grid grid-cols-2 gap-2.5 lg:grid-cols-4">
            <Select name="Method" value={filters.method} options={methodOptions} onChange={set("method")} />
            <Select name="Family" value={filters.family} options={familyOptions} onChange={set("family")} format={familyLabel} />
            <Select name="Channel" value={filters.channel} options={["call", "sms"]} onChange={set("channel")} format={(value) => (value === "sms" ? "Text" : "Call")} />
            <Select name="Tier" value={filters.tier} options={[...TIER_ORDER]} onChange={set("tier")} />
            <Select name="Test outcome" value={filters.outcome} options={["caught", "soft_miss", "missed", "clear", "soft_false_alarm", "false_alarm"]} onChange={set("outcome")} />
            <Select name="Signal" value={filters.signal} options={signalOptions} onChange={set("signal")} format={flagLabel} />
            <Select name="Source" value={filters.source} options={["sandbox_synthetic", "live"]} onChange={set("source")} format={(value) => (value === "live" ? "Live" : "Synthetic test data")} />
            <div className="col-span-2 grid grid-cols-2 gap-2.5 lg:col-span-1">
              <label className="min-w-0 text-[12.5px] text-ink-2">
                From
                <input type="date" value={filters.from} onChange={(event) => set("from")(event.target.value)} className={`mt-1 ${CONTROL} text-ink`} />
              </label>
              <label className="min-w-0 text-[12.5px] text-ink-2">
                To
                <input type="date" value={filters.to} onChange={(event) => set("to")(event.target.value)} className={`mt-1 ${CONTROL} text-ink`} />
              </label>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <Segment label="View" value={view} options={[["search", "Search"], ["charts", "Charts"]]} onChange={setView} />
            <div className="flex items-center gap-2">
              {filtersActive && (
                <button type="button" onClick={() => setFilters(EMPTY_FILTERS)} className="rounded-full px-3 py-1.5 text-[13px] font-medium text-ink-2 hover:bg-sunk">
                  Clear
                </button>
              )}
              <a href={exportCsvUrl(search)} download className="rounded-full bg-sunk px-3.5 py-1.5 text-[13px] font-medium">
                Export CSV
              </a>
            </div>
          </div>
        </Card>

        {view === "search" ? (
          <Card className="mt-4 p-4 sm:p-5">
            <div className="flex items-baseline justify-between gap-3">
              <PanelTitle>Matching incidents</PanelTitle>
              {page.data?.totalEstimate != null && <span className="text-[13px] text-ink-2">About {page.data.totalEstimate.toLocaleString("en-US")}</span>}
            </div>
            {page.error ? (
              <p className="mt-3 text-[13px] text-mag-deep">Results are unavailable: {page.error}</p>
            ) : page.loading && !items.length ? (
              <Empty>Searching</Empty>
            ) : !items.length ? (
              <Empty>No incidents match these filters</Empty>
            ) : (
              <div className={`mt-1 divide-y divide-line transition-opacity duration-300 ${page.loading ? "opacity-50" : ""}`}>
                {items.map((incident) => (
                  <ResultRow key={incident.id} incident={incident} onOpen={() => setOpened(incident.id)} />
                ))}
              </div>
            )}
            {moreError && <p className="mt-2 text-[13px] text-mag-deep">{moreError}</p>}
            {nextCursor && !page.loading && (
              <button type="button" onClick={() => void loadMore()} disabled={loadingMore} className="mt-3 w-full rounded-full bg-sunk py-2 font-medium disabled:opacity-60">
                {loadingMore ? "Loading" : "Load more"}
              </button>
            )}
          </Card>
        ) : (
          <div className="mt-4 grid min-w-0 gap-4">
            <p className="text-[13px] text-ink-2">Charts follow the date and source filters.</p>
            <ChartCard
              title="Incidents over time"
              action={<Segment label="Group by" value={groupBy} options={[["family", "Family"], ["method", "Method"], ["tier", "Tier"]]} onChange={setGroupBy} />}
            >
              <div className="mt-4">
                {series.error ? (
                  <Empty>{`Unavailable: ${series.error}`}</Empty>
                ) : (
                  <StackedDays points={series.data ?? []} series={chartSeries} suppressedNote={suppressed} />
                )}
              </div>
            </ChartCard>
            <ChartCard title="Signals by method">
              <SignalHeatmap rows={heatRows} signals={heatColumns} />
            </ChartCard>
            <ChartCard title="Method leaderboard">
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12.5px] text-ink-2">
                {TIER_ORDER.map((tier) => (
                  <span key={tier} className="flex items-center gap-1.5">
                    <i aria-hidden="true" className="size-2.5 rounded-[3px]" style={{ background: TIER_COLORS[tier] }} />
                    {humanize(tier)}
                  </span>
                ))}
              </div>
              <MethodLeaderboard methods={methods.data ?? []} onPick={pickMethod} />
            </ChartCard>
          </div>
        )}
      </div>

      <aside className="min-w-0">
        <SideCard className="min-[1241px]:mt-0">
          <PanelTitle>Overview</PanelTitle>
          <StatGrid
            items={[
              ["Incidents", data ? formatCount(data.total) : "Unavailable"],
              ["Dangerous", data ? formatCount(dangerous) : "Unavailable"],
              ["First day", data?.from ? formatDay(data.from) : "Unavailable"],
              ["Last day", data?.to ? formatDay(data.to) : "Unavailable"],
            ]}
          />
        </SideCard>
        <SideCard>
          <PanelTitle>Tier mix</PanelTitle>
          <TierMix buckets={data?.byTier ?? []} />
        </SideCard>
        <SideCard>
          <PanelTitle>Top signals</PanelTitle>
          <SignalBars buckets={signals.data ?? []} />
        </SideCard>
      </aside>

      {opened && <IncidentDrawer id={opened} onClose={() => setOpened(null)} />}
    </Columns>
  );
}
