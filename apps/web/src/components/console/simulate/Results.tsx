import { markersCsvUrl } from "@/lib/simulate/api";
import { flagLabel, humanize, ms, show } from "@/lib/simulate/labels";
import { drillIn, type Decision, type Lessons, type Marker, type MethodRow, type ModelRow } from "@/lib/simulate/parse";
import { formatPercent } from "@/lib/console/format";
import { Card, Tag } from "../ui";
import { TallyBars } from "./charts";

const percent = (value: number | null) => show(value, formatPercent);

export function DrillIn({ row, seen }: { row: MethodRow; seen: Decision[] }) {
  const detail = drillIn(seen, row.method);
  const outcomes = Object.entries(row.counts)
    .filter(([, value]) => value > 0)
    .sort(([, a], [, b]) => b - a)
    .map(([label, value]) => ({ label: humanize(label), count: value }));

  return (
    <Card className="grid gap-6 px-[22px] py-5 sm:grid-cols-3">
      <div>
        <b className="font-semibold">Outcomes</b>
        <TallyBars items={outcomes} empty="No outcomes yet" />
        <p className="mt-3 text-[13px] text-ink-2">Method named correctly: {percent(row.methodAccuracy)}</p>
      </div>
      <div>
        <b className="font-semibold">Flags that popped</b>
        <TallyBars items={detail.flags.map((item) => ({ ...item, label: flagLabel(item.label) }))} empty="No flags in the decisions seen" />
      </div>
      <div>
        <b className="font-semibold">Mistaken for</b>
        <TallyBars items={detail.misclassifiedAs.map((item) => ({ ...item, label: humanize(item.label) }))} empty="No wrong method in the decisions seen" />
      </div>
      <p className="text-[12.5px] text-ink-3 sm:col-span-3">
        Flags and wrong methods come from the {detail.observed} of {row.n} decisions this page received in its live stream.
      </p>
    </Card>
  );
}

export function ModelTable({ models }: { models: ModelRow[] | null }) {
  if (!models) return <Card className="px-[22px] py-5 text-ink-2">Model comparison is unavailable.</Card>;
  if (!models.length) return <Card className="px-[22px] py-5 text-ink-2">No model results yet.</Card>;

  return (
    <Card className="overflow-x-auto px-[22px] py-3">
      <table className="w-full min-w-[520px] text-left">
        <thead>
          <tr className="text-[13px] text-ink-2">
            <th className="py-2 font-medium">Model</th>
            <th className="py-2 font-medium">Cases</th>
            <th className="w-[30%] py-2 font-medium">Score</th>
            <th className="py-2 font-medium">Caught</th>
            <th className="py-2 font-medium">False alarms</th>
            <th className="py-2 font-medium">Median</th>
          </tr>
        </thead>
        <tbody>
          {models.map((model) => (
            <tr key={model.model} className="border-t border-line">
              <td className="py-2.5 pr-3 font-semibold">{model.model}</td>
              <td className="py-2.5">{show(model.n)}</td>
              <td className="py-2.5 pr-4">
                <span className="flex items-center gap-2">
                  <span className="h-2 flex-1 rounded-[2px] bg-sunk">
                    <i className="block h-full rounded-[2px] bg-[#1B1B1B] transition-[width] duration-500 ease-slide" style={{ width: `${(model.score ?? 0) * 100}%` }} />
                  </span>
                  <span className="w-12 text-right">{model.score === null ? "n/a" : formatPercent(model.score)}</span>
                </span>
              </td>
              <td className="py-2.5">{model.catchRate === null ? "n/a" : formatPercent(model.catchRate)}</td>
              <td className="py-2.5">{model.falseAlarmRate === null ? "n/a" : formatPercent(model.falseAlarmRate)}</td>
              <td className="py-2.5">{model.p50 === null ? "n/a" : ms(model.p50)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

const WRONG_OUTCOMES = new Set(["missed", "false_alarm", "no_verdict"]);

export function DecisionStream({ seen }: { seen: Decision[] }) {
  if (!seen.length) return <Card className="px-[22px] py-5 text-ink-2">Decisions appear here as they land.</Card>;

  return (
    <Card className="px-[22px] py-2.5">
      <ul>
        {seen.slice(0, 12).map((item) => (
          <li key={item.key} className="flex animate-rise flex-wrap items-center gap-x-3 gap-y-1 border-t border-line py-2.5 first:border-t-0">
            <span className="min-w-0 flex-1 basis-40">
              <b className="block truncate font-semibold">{humanize(item.method)}</b>
              <small className="block truncate text-[12.5px] text-ink-2">
                {[item.channel, item.model, item.ms === null ? null : ms(item.ms)].filter(Boolean).join(" · ")}
              </small>
            </span>
            <span className="flex flex-wrap gap-1.5">
              {item.tier && <Tag>{humanize(item.tier)}</Tag>}
              {item.outcome && <Tag hot={WRONG_OUTCOMES.has(item.outcome)}>{humanize(item.outcome)}</Tag>}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function MarkersAndLessons({
  runId,
  markers,
  lessons,
}: {
  runId: string | null;
  markers: Marker[] | null;
  lessons: Lessons | null;
}) {
  return (
    <div className="space-y-2.5">
      {markers === null && <p className="text-ink-2">Markers appear when the run finishes.</p>}
      {markers?.length === 0 && <p className="text-ink-2">No failure markers for this run.</p>}
      {markers?.slice(0, 12).map((marker) => (
        <div key={marker.id} className="rounded-2xl border border-line px-[22px] py-4">
          <div className="flex flex-wrap items-center gap-2 font-semibold">
            {humanize(marker.marker ?? "unlabeled")}
            {marker.outcome && <Tag hot>{humanize(marker.outcome)}</Tag>}
            {marker.type && <Tag>{humanize(marker.type)}</Tag>}
            {marker.model && <Tag>{marker.model}</Tag>}
          </div>
          {marker.feedback && <p className="mt-[3px] text-ink-2">{marker.feedback}</p>}
          {marker.improvement && <p className="mt-1 text-ink">Fix: {marker.improvement}</p>}
        </div>
      ))}
      {runId && !!markers?.length && (
        <a className="inline-block text-[13px] font-medium text-mag-deep underline" href={markersCsvUrl(runId)}>
          Download all {markers.length} markers as CSV
        </a>
      )}

      {lessons === null ? (
        <p className="pt-2 text-[13px] text-ink-3">Lessons across runs are unavailable.</p>
      ) : (
        <>
          {lessons.consistent.map((item) => (
            <div key={item.key} className="rounded-2xl bg-mag-wash px-[22px] py-3.5">
              <b className="font-semibold">Keeps failing: {humanize(item.name)}</b>
              <p className="text-ink-2">{item.detail}</p>
            </div>
          ))}
          {lessons.lessons.slice(0, 8).map((lesson, index) => (
            <div key={`${lesson.title}-${index}`} className="rounded-2xl border border-line px-[22px] py-4">
              <div className="flex flex-wrap items-center gap-2 font-semibold">
                {lesson.title}
                {lesson.method && <Tag>{humanize(lesson.method)}</Tag>}
                {lesson.seen !== null && <Tag>Seen {lesson.seen} times</Tag>}
                {lesson.status && <Tag>{humanize(lesson.status)}</Tag>}
              </div>
              {lesson.detail && <p className="mt-[3px] text-ink-2">{lesson.detail}</p>}
            </div>
          ))}
        </>
      )}
    </div>
  );
}
