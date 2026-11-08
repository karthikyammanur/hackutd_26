import { useState } from "react";
import { countValue, foldSeries, formatCount, OTHER, type Bucket, type Count, type MethodStat, type TimePoint } from "@/lib/evidence/parse";
import { formatDay, OTHER_COLOR, TIER_COLORS, TIER_ORDER } from "@/lib/evidence/labels";
import { familyLabel, flagLabel, humanize } from "@/lib/simulate/labels";

const GROW = "transition-[width,height] duration-500 ease-slide";
const CHART_HEIGHT = 200;

function Swatch({ color }: { color: string }) {
  return <i aria-hidden="true" className="size-2.5 flex-none rounded-[3px]" style={{ background: color }} />;
}

export function Empty({ children }: { children: string }) {
  return <p className="py-6 text-center text-[13px] text-ink-3">{children}</p>;
}

export interface Series {
  key: string;
  label: string;
  color: string;
}

function niceMax(value: number): number {
  if (value <= 5) return 5;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((candidate) => candidate * magnitude >= value) ?? 10;
  return step * magnitude;
}

export function StackedDays({ points, series, suppressedNote }: { points: TimePoint[]; series: Series[]; suppressedNote: boolean }) {
  const [hover, setHover] = useState<number | null>(null);
  const days = foldSeries(points, series.map((item) => item.key));
  const all = days.some((day) => day.values[OTHER]) ? [...series, { key: OTHER, label: "Other", color: OTHER_COLOR }] : series;
  const top = niceMax(Math.max(0, ...days.map((day) => day.total)));

  if (!days.length) return <Empty>No incidents in this range</Empty>;
  const hovered = hover === null ? null : days[hover];
  const edgeStyle =
    hover === null
      ? undefined
      : hover > days.length / 2
        ? { right: `${((days.length - 1 - hover) / days.length) * 100}%` }
        : { left: `${(hover / days.length) * 100}%` };
  const midDay = days[Math.floor(days.length / 2)];

  return (
    <div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12.5px] text-ink-2">
        {all.map((item) => (
          <span key={item.key} className="flex items-center gap-1.5">
            <Swatch color={item.color} />
            {item.label}
          </span>
        ))}
      </div>

      <div className="mt-4 grid grid-cols-[auto_minmax(0,1fr)] gap-x-2">
        <div className="flex flex-col justify-between text-right text-[12px] text-ink-3" style={{ height: CHART_HEIGHT }}>
          <span>{top.toLocaleString("en-US")}</span>
          <span>{(top / 2).toLocaleString("en-US")}</span>
          <span>0</span>
        </div>
        <div className="relative" style={{ height: CHART_HEIGHT }} onPointerLeave={() => setHover(null)}>
          <i className="absolute inset-x-0 top-0 border-t border-line" />
          <i className="absolute inset-x-0 top-1/2 border-t border-line" />
          <i className="absolute inset-x-0 bottom-0 border-t border-wire" />
          <div className="absolute inset-0 flex items-end gap-[2px]">
            {days.map((day, index) => (
              <button
                key={day.day}
                type="button"
                onPointerEnter={() => setHover(index)}
                onFocus={() => setHover(index)}
                onBlur={() => setHover(null)}
                onClick={() => setHover(index)}
                aria-label={`${formatDay(day.day)}: ${day.total.toLocaleString("en-US")} incidents`}
                className={`flex h-full max-w-14 min-w-0 flex-1 flex-col-reverse gap-[2px] rounded-t-[4px] ${hover === index ? "bg-sunk/70" : ""}`}
              >
                {all.map((item) => {
                  const value = day.values[item.key] ?? 0;
                  return value ? (
                    <i
                      key={item.key}
                      className={`block w-full rounded-[2px] ${GROW}`}
                      style={{ height: `${(value / top) * 100}%`, background: item.color }}
                    />
                  ) : null;
                })}
              </button>
            ))}
          </div>
          {hovered && (
            <div role="status" className="pointer-events-none absolute top-1 z-10 w-48 rounded-lg bg-white p-2.5 text-[12.5px] shadow-soft" style={edgeStyle}>
              <b className="font-semibold">{formatDay(hovered.day)}</b>
              <ul className="mt-1 space-y-0.5">
                {all
                  .filter((item) => hovered.values[item.key])
                  .map((item) => (
                    <li key={item.key} className="flex items-center gap-1.5">
                      <Swatch color={item.color} />
                      <span className="min-w-0 flex-1 truncate">{item.label}</span>
                      <span className="font-medium">{hovered.values[item.key].toLocaleString("en-US")}</span>
                    </li>
                  ))}
              </ul>
              <div className="mt-1 flex justify-between border-t border-line pt-1 font-medium">
                <span>Total</span>
                <span>{hovered.total.toLocaleString("en-US")}</span>
              </div>
            </div>
          )}
        </div>
        <span />
        <div className="mt-1 flex justify-between text-[12px] text-ink-3">
          <span>{formatDay(days[0].day)}</span>
          {days.length > 2 && <span>{formatDay(midDay.day)}</span>}
          {days.length > 1 && <span>{formatDay(days[days.length - 1].day)}</span>}
        </div>
      </div>

      {suppressedNote && <p className="mt-2 text-[12.5px] text-ink-3">Groups under 5 live incidents are hidden for privacy and chart as zero.</p>}

      <details className="mt-3 text-[13px]">
        <summary className="cursor-pointer text-ink-2">View as table</summary>
        <div className="mt-2 max-h-64 overflow-auto">
          <table className="w-full text-left text-[12.5px]">
            <thead className="text-ink-2">
              <tr>
                <th scope="col" className="py-1 pr-3 font-medium">Day</th>
                {all.map((item) => (
                  <th key={item.key} scope="col" className="py-1 pr-3 font-medium whitespace-nowrap">{item.label}</th>
                ))}
                <th scope="col" className="py-1 font-medium">Total</th>
              </tr>
            </thead>
            <tbody>
              {days.map((day) => (
                <tr key={day.day} className="border-t border-line">
                  <td className="py-1 pr-3 whitespace-nowrap">{formatDay(day.day)}</td>
                  {all.map((item) => (
                    <td key={item.key} className="py-1 pr-3">{(day.values[item.key] ?? 0).toLocaleString("en-US")}</td>
                  ))}
                  <td className="py-1 font-medium">{day.total.toLocaleString("en-US")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

export function TierMix({ buckets }: { buckets: Bucket[] }) {
  const find = (tier: string) => buckets.find((bucket) => bucket.key === tier)?.count ?? null;
  const total = TIER_ORDER.reduce((sum, tier) => sum + countValue(find(tier)), 0);
  if (!total) return <Empty>No tier data yet</Empty>;

  return (
    <div className="mt-3">
      <div className="flex h-3 gap-[2px]" role="img" aria-label={TIER_ORDER.map((tier) => `${tier} ${formatCount(find(tier))}`).join(", ")}>
        {TIER_ORDER.map((tier) => {
          const value = countValue(find(tier));
          return value ? (
            <i key={tier} className={`block rounded-[3px] ${GROW}`} style={{ width: `${(value / total) * 100}%`, background: TIER_COLORS[tier] }} />
          ) : null;
        })}
      </div>
      <ul className="mt-3 space-y-1.5 text-[13px]">
        {TIER_ORDER.map((tier) => {
          const count = find(tier);
          return (
            <li key={tier} className="flex items-center gap-2">
              <Swatch color={TIER_COLORS[tier]} />
              <span className="flex-1">{humanize(tier)}</span>
              <span className="font-medium">{formatCount(count)}</span>
              <span className="w-12 text-right text-ink-2">{typeof count === "number" ? `${((count / total) * 100).toFixed(1)}%` : ""}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function SignalBars({ buckets, limit = 8 }: { buckets: Bucket[]; limit?: number }) {
  if (!buckets.length) return <Empty>No signals recorded yet</Empty>;
  const largest = Math.max(1, ...buckets.map((bucket) => countValue(bucket.count)));
  return (
    <ul className="mt-3 space-y-2.5">
      {buckets.slice(0, limit).map((bucket) => (
        <li key={bucket.key}>
          <div className="flex justify-between gap-3 text-[13px]">
            <span className="min-w-0 truncate">{flagLabel(bucket.key)}</span>
            <span className="font-medium">{formatCount(bucket.count)}</span>
          </div>
          <div className="mt-1 h-1.5 rounded-[3px] bg-sunk">
            <i className={`block h-full rounded-[3px] bg-mag ${GROW}`} style={{ width: `${(countValue(bucket.count) / largest) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

export function MethodLeaderboard({ methods, onPick }: { methods: MethodStat[]; onPick: (method: string) => void }) {
  if (!methods.length) return <Empty>No methods recorded yet</Empty>;
  const largest = Math.max(1, ...methods.map((row) => countValue(row.total)));
  return (
    <div className="mt-2">
      {methods.slice(0, 15).map((row, index) => {
        const total = countValue(row.total);
        return (
          <button
            key={row.method}
            type="button"
            onClick={() => onPick(row.method)}
            title="Search this method"
            className="-mx-2.5 grid w-[calc(100%+20px)] grid-cols-[22px_minmax(0,1fr)_auto] items-center gap-x-2.5 gap-y-1 rounded-lg px-2.5 py-2 text-left hover:bg-canvas"
          >
            <span className="text-[12.5px] text-ink-3">{index + 1}</span>
            <span className="min-w-0">
              <b className="block truncate font-semibold">{humanize(row.method)}</b>
              <small className="text-[12.5px] text-ink-2">{row.family ? familyLabel(row.family) : "Family unavailable"}</small>
            </span>
            <span className="font-semibold">{formatCount(row.total)}</span>
            <span />
            <span className={`col-span-2 flex h-2 gap-[2px] ${GROW}`} style={{ width: `${(total / largest) * 100}%` }}>
              {TIER_ORDER.map((tier) => {
                const value = countValue(row.tiers[tier] ?? null);
                return value ? (
                  <i key={tier} className={`block rounded-[2px] ${GROW}`} style={{ width: `${(value / total) * 100}%`, background: TIER_COLORS[tier] }} />
                ) : null;
              })}
            </span>
          </button>
        );
      })}
    </div>
  );
}

export interface HeatRow {
  method: string;
  total: Count | null;
  signals: Bucket[];
}

function cellColor(share: number): string {
  return `color-mix(in oklab, var(--color-mag) ${Math.round(8 + share * 92)}%, var(--color-card))`;
}

export function SignalHeatmap({ rows, signals }: { rows: HeatRow[]; signals: string[] }) {
  if (!rows.length || !signals.length) return <Empty>Not enough signal data for a heatmap yet</Empty>;
  return (
    <div className="mt-3 overflow-x-auto" tabIndex={0} role="region" aria-label="Signals fired, by scam method">
      <table className="w-full min-w-[640px] border-separate border-spacing-[2px] text-[12.5px]">
        <thead>
          <tr>
            <th scope="col" className="w-40 text-left font-medium text-ink-2">Method</th>
            {signals.map((signal) => (
              <th key={signal} scope="col" className="px-1 pb-1 align-bottom text-[12px] leading-tight font-medium text-ink-2">
                {flagLabel(signal)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const total = countValue(row.total);
            return (
              <tr key={row.method}>
                <th scope="row" className="max-w-40 truncate pr-2 text-left font-medium" title={humanize(row.method)}>
                  {humanize(row.method)}
                </th>
                {signals.map((signal) => {
                  const count = row.signals.find((bucket) => bucket.key === signal)?.count ?? null;
                  const share = total ? Math.min(countValue(count) / total, 1) : 0;
                  return (
                    <td
                      key={signal}
                      title={`${humanize(row.method)}, ${flagLabel(signal)}: ${formatCount(count ?? 0)}`}
                      className="h-9 rounded-[4px] text-center transition-colors duration-500"
                      style={{ background: count === null ? "var(--color-canvas)" : cellColor(share), color: share > 0.55 ? "#fff" : "var(--color-ink)" }}
                    >
                      {count === "<5" ? "<5" : count === null || !total ? "" : `${Math.round(share * 100)}%`}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-2 text-[12.5px] text-ink-3">Each cell is the share of that method's incidents where the signal fired.</p>
    </div>
  );
}
