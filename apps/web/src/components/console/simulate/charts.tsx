import { useElementWidth } from "@/hooks/useElementWidth";
import { decisionRates, type FamilySummary, type MethodRow, type TimelinePoint } from "@/lib/simulate/parse";
import { familyLabel, humanize } from "@/lib/simulate/labels";
import { formatPercent } from "@/lib/console/format";
import { Icon, type IconName } from "../icons";
import { Card, Tile, type Tint } from "../ui";

const RIGHT = "bg-[#1B1B1B]";
const SOFT = "bg-[#8E8E8E]";
const WRONG = "bg-mag";
const NO_VERDICT = "bg-wire";

export function Legend() {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12.5px] text-ink-2">
      {[
        ["Right tier", RIGHT],
        ["Uncertain", SOFT],
        ["Wrong tier", WRONG],
        ["No answer", NO_VERDICT],
      ].map(([label, color]) => (
        <span key={label} className="flex items-center gap-1.5">
          <i className={`size-2.5 rounded-[2px] ${color}`} />
          {label}
        </span>
      ))}
    </div>
  );
}

/** A few results should look like a few, so the shared scale never gets shorter than this. */
const MIN_SCALE = 10;

const FAMILY_ICONS: Record<string, { icon: IconName; tint: Tint }> = {
  impersonation: { icon: "call", tint: "lilac" },
  payment: { icon: "base", tint: "sand" },
  payment_lure: { icon: "base", tint: "sand" },
  credential_theft: { icon: "shield", tint: "blue" },
  relationship_or_opportunity: { icon: "message", tint: "sage" },
  legitimate: { icon: "check", tint: "grey" },
  none: { icon: "check", tint: "grey" },
};

export function FamilyList({
  families,
  unit,
  picked,
  onPick,
}: {
  families: FamilySummary[];
  /** "call" when one model ran. With several, each call counts once per model, so these are results. */
  unit: "call" | "result";
  picked: string | null;
  onPick: (family: string | null) => void;
}) {
  if (!families.length) {
    return <Card className="px-[22px] py-5 text-ink-2">No results yet. Families appear here as {unit}s finish.</Card>;
  }

  const scale = Math.max(MIN_SCALE, ...families.map((family) => family.n));

  return (
    <Card className="px-[22px] py-1.5">
      <ul>
        {families.map((family) => {
          const isPicked = family.family === picked;
          const label = familyLabel(family.family);
          const parts = [
            { name: "right", value: family.right, color: RIGHT },
            { name: "uncertain", value: family.soft, color: SOFT },
            { name: "wrong", value: family.wrong, color: WRONG },
            { name: "no answer", value: family.noVerdict, color: NO_VERDICT },
          ].filter((part) => part.value > 0);
          const { icon, tint } = FAMILY_ICONS[family.family] ?? { icon: "nodes", tint: "grey" };
          return (
            <li key={family.family} className="border-t border-line py-1 first:border-t-0">
              <button
                onClick={() => onPick(isPicked ? null : family.family)}
                aria-pressed={isPicked}
                title={isPicked ? "Show all families" : `Show only ${label} under By method`}
                className={`-mx-2.5 grid w-[calc(100%+20px)] grid-cols-[32px_minmax(0,1fr)_64px] items-center gap-x-3 gap-y-2 rounded-xl px-2.5 py-2 text-left sm:grid-cols-[32px_minmax(0,1.5fr)_minmax(0,1fr)_64px] ${
                  isPicked ? "bg-sunk" : "hover:bg-canvas"
                }`}
              >
                {isPicked ? (
                  <span className="grid size-8 place-items-center rounded-[9px] bg-[#1B1B1B] text-white">
                    <Icon name="tick" />
                  </span>
                ) : (
                  <Tile icon={icon} tint={tint} />
                )}
                <span className="min-w-0">
                  <b className="block truncate font-semibold">{label}</b>
                  <small className="flex flex-wrap items-center gap-x-3 text-[13px] text-ink-2">
                    <span>
                      {family.n ? (
                        <>
                          <Pop value={family.n.toLocaleString()} /> {family.n === 1 ? unit : `${unit}s`}
                        </>
                      ) : (
                        `No ${unit}s yet`
                      )}
                    </span>
                    {parts.map((part) => (
                      <span key={part.name} className="flex items-center gap-1.5">
                        <i className={`size-2 rounded-[2px] ${part.color}`} />
                        {part.value.toLocaleString()} {part.name}
                      </span>
                    ))}
                  </small>
                </span>
                <span className="order-last col-span-full block sm:order-none sm:col-span-1" aria-hidden="true">
                  {family.n > 0 && (
                    <span
                      className={`flex h-2 overflow-hidden rounded-[2px] transition-[width] duration-500 ease-slide ${family.n / scale < 0.08 ? "gap-px" : "gap-0.5"}`}
                      style={{ width: `max(4px, ${(family.n / scale) * 100}%)` }}
                    >
                      {parts.map((part) => (
                        <i
                          key={part.name}
                          className={`block h-full min-w-px basis-0 transition-[flex-grow] duration-500 ease-slide ${part.color}`}
                          style={{ flexGrow: part.value }}
                        />
                      ))}
                    </span>
                  )}
                </span>
                <span className="text-right font-semibold">{family.score === null ? "n/a" : formatPercent(family.score)}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

/** Replays a small pop whenever the value changes. */
function Pop({ value }: { value: number | string }) {
  return (
    <span key={value} className="inline-block animate-pop">
      {value}
    </span>
  );
}

export function MethodBars({
  methods,
  picked,
  onPick,
}: {
  methods: MethodRow[];
  picked: string | null;
  onPick: (method: string) => void;
}) {
  const largest = Math.max(1, ...methods.map((row) => row.n));

  return (
    <Card className="px-[22px] py-2.5">
      {methods.map((row) => {
        const segments = [
          { value: row.right, color: RIGHT },
          { value: row.soft, color: SOFT },
          { value: row.wrong, color: WRONG },
          { value: row.noVerdict, color: NO_VERDICT },
        ];
        return (
          <button
            key={row.method}
            onClick={() => onPick(row.method)}
            aria-pressed={row.method === picked}
            className={`-mx-3.5 grid w-[calc(100%+28px)] grid-cols-[minmax(0,1fr)_56px] items-center gap-x-4 gap-y-1.5 rounded-xl px-3.5 py-2.5 text-left sm:grid-cols-[minmax(0,1.1fr)_minmax(0,1.5fr)_58px] ${
              row.method === picked ? "bg-sunk" : "hover:bg-canvas"
            }`}
          >
            <span className="min-w-0">
              <b className="block truncate font-semibold">{humanize(row.method)}</b>
              <small className="text-[13px] text-ink-2">
                {familyLabel(row.family)}, <Pop value={row.n} /> {row.n === 1 ? "result" : "results"}
              </small>
            </span>
            <span className="order-last col-span-2 block sm:order-none sm:col-span-1">
              <span
                className="flex h-2.5 overflow-hidden rounded-[2px] transition-[width] duration-500 ease-slide"
                style={{ width: `${(row.n / largest) * 100}%` }}
              >
                {segments.map(({ value, color }) => (
                  <i
                    key={color}
                    className={`block h-full transition-[width] duration-500 ease-slide ${color}`}
                    style={{ width: row.n ? `${(value / row.n) * 100}%` : 0 }}
                  />
                ))}
              </span>
            </span>
            <span className="text-right font-semibold">{row.score === null ? "n/a" : formatPercent(row.score)}</span>
          </button>
        );
      })}
    </Card>
  );
}

const HEIGHT = 64;

export function RateChart({ timeline }: { timeline: TimelinePoint[] }) {
  const { ref, width } = useElementWidth<HTMLDivElement>();
  const rates = decisionRates(timeline);

  if (rates.length < 2) {
    return (
      <div ref={ref} className="grid h-16 place-items-center text-[13px] text-ink-3">
        The chart appears once decisions are recorded
      </div>
    );
  }

  const peak = Math.max(...rates, 1);
  const points = rates
    .map((value, index) => `${(index / (rates.length - 1)) * width},${HEIGHT - 2 - (value / peak) * (HEIGHT - 6)}`)
    .join(" ");

  return (
    <div ref={ref}>
      <svg width={width} height={HEIGHT} role="img" aria-label={`Decisions per second over time, peak ${peak.toFixed(1)}`}>
        <polyline points={points} fill="none" stroke="var(--color-mag)" strokeWidth="1.8" strokeLinejoin="round" />
      </svg>
      <div className="flex justify-between text-[12.5px] text-ink-3">
        <span>Decisions per second</span>
        <span>Peak {peak.toFixed(1)}</span>
      </div>
    </div>
  );
}

export function TallyBars({ items, empty }: { items: { label: string; count: number }[]; empty: string }) {
  if (!items.length) return <p className="mt-1.5 text-[13px] text-ink-3">{empty}</p>;
  const largest = items[0].count;
  return (
    <ul className="mt-2 space-y-2">
      {items.slice(0, 8).map((item) => (
        <li key={item.label}>
          <div className="flex justify-between gap-3 text-[13px]">
            <span className="min-w-0 truncate">{item.label}</span>
            <span className="font-medium">{item.count}</span>
          </div>
          <div className="mt-1 h-1.5 rounded-[2px] bg-sunk">
            <i
              className="block h-full rounded-[2px] bg-[#1B1B1B] transition-[width] duration-500 ease-slide"
              style={{ width: `${(item.count / largest) * 100}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}
