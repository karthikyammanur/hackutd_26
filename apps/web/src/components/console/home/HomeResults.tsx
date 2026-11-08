import type { MouseEvent, ReactNode } from "react";
import { useInView, useRunReplay } from "@/hooks/useHomeMotion";
import { formatPercent } from "@/lib/console/format";
import { familyLabel, ms } from "@/lib/simulate/labels";
import {
  BASELINE,
  BASELINE_CATCH_RATE,
  BASELINE_FALSE_ALARM_RATE,
  CATCH_RATE,
  CORPUS,
  count,
  FALSE_ALARM_RATE,
  FAMILIES,
  LEGIT_TOTAL,
  METHOD_ACCURACY,
  OUTCOMES,
  OVERALL_SCORE,
  RUN,
  RUN_ID,
  SCAM_TOTAL,
  SCAM_TYPES_TESTED,
  SCORED_TOTAL,
  STEP_ERRORS,
  STEP_TOTAL,
  TIMINGS,
  WEAK_TOTAL,
} from "@/lib/home/stats";
import { ArchitectureFigure } from "../simulate/architecture/ArchitectureFigure";
import { useTooltip } from "../Tooltip";
import { Card, PanelTitle } from "../ui";
import "./home.css";

type Result = "right" | "soft" | "wrong";

interface TileGroup {
  result: Result;
  label: string;
  n: number;
}

function Waffle({ groups, of, noun }: { groups: TileGroup[]; of: number; noun: string }) {
  const tip = useTooltip();

  const onMove = (event: MouseEvent<HTMLDivElement>) => {
    const index = (event.target as HTMLElement).dataset.group;
    if (index === undefined) return tip.hide();
    const group = groups[Number(index)];
    tip.show(event, { primary: group.label, secondary: `${group.n} of ${of} ${noun}` });
  };

  return (
    <div
      className="hm-tiles mt-4"
      role="img"
      aria-label={groups.map((group) => `${group.n} ${group.label.toLowerCase()}`).join(", ")}
      onMouseMove={onMove}
      onMouseLeave={tip.hide}
    >
      {groups.flatMap((group, index) =>
        Array.from({ length: group.n }, (_, tile) => <i key={`${group.result}-${tile}`} className="hm-tile" data-result={group.result} data-group={index} />),
      )}
    </div>
  );
}

function OutcomeColumn({ rate, statement, title, groups, of, noun }: { rate: number; statement: string; title: string; groups: TileGroup[]; of: number; noun: string }) {
  return (
    <div className="min-w-0">
      <PanelTitle>{title}</PanelTitle>
      <p className="mt-3 text-[clamp(46px,5.4vw,68px)] leading-none font-semibold tracking-[-0.04em]">{formatPercent(rate)}</p>
      <p className="mt-1.5 text-[15px] text-ink-2">{statement}</p>
      <Waffle groups={groups} of={of} noun={noun} />
      <dl className="mt-4 grid grid-cols-3 gap-3">
        {groups.map((group) => (
          <div key={group.label}>
            <dd className="text-[19px] font-semibold tracking-[-0.015em]">{group.n}</dd>
            <dt className="text-[13px] leading-[1.25] text-ink-2">{group.label}</dt>
          </div>
        ))}
      </dl>
    </div>
  );
}

function Key() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[13px] text-ink-2">
      <span>Each square is one conversation.</span>
      {(
        [
          ["right", "Right tier"],
          ["soft", "Uncertain"],
          ["wrong", "Wrong tier"],
        ] as const
      ).map(([result, label]) => (
        <span key={result} className="flex items-center gap-1.5">
          <i className="hm-tile" data-result={result} />
          {label}
        </span>
      ))}
    </div>
  );
}

export function Figures({ items }: { items: [string, string][] }) {
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-5 lg:grid-cols-4">
      {items.map(([label, value]) => (
        <div key={label}>
          <dd className="text-[26px] leading-[1.1] font-semibold tracking-[-0.025em]">{value}</dd>
          <dt className="mt-1 text-[13.5px] leading-[1.3] text-ink-2">{label}</dt>
        </div>
      ))}
    </dl>
  );
}

function FamilyBars() {
  const tip = useTooltip();
  return (
    <ul className="mt-4 grid gap-3.5">
      {FAMILIES.map((family) => {
        const segments: [string, number, string][] = [
          ["Right tier", family.right, "#1b1b1b"],
          ["Uncertain", family.soft, "#a8a8a8"],
          ["Wrong tier", family.wrong, "var(--color-mag)"],
        ];
        return (
          <li key={family.family}>
            <div className="flex items-baseline justify-between gap-3 text-[13.5px]">
              <span className="font-medium">{familyLabel(family.family)}</span>
              <span className="flex-none text-ink-2">
                {family.right} of {family.n} right
              </span>
            </div>
            <div className="mt-1.5 flex h-2 gap-0.5">
              {segments
                .filter(([, n]) => n > 0)
                .map(([label, n, color]) => (
                  <i
                    key={label}
                    className="block h-full first:rounded-l last:rounded-r"
                    style={{ flexGrow: n, background: color }}
                    onMouseMove={(event) => tip.show(event, { primary: familyLabel(family.family), secondary: `${label}: ${n} of ${family.n}` })}
                    onMouseLeave={tip.hide}
                  />
                ))}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

const TIMING_MAX = Math.max(...TIMINGS.map(({ stat }) => stat.p95 ?? 0));

function TimingRanges() {
  const tip = useTooltip();
  return (
    <ul className="mt-4 grid gap-4">
      {TIMINGS.map(({ label, detail, stat }) => {
        const p50 = stat.p50 ?? 0;
        const p95 = stat.p95 ?? 0;
        const from = (p50 / TIMING_MAX) * 100;
        const to = (p95 / TIMING_MAX) * 100;
        return (
          <li key={label}>
            <div className="flex items-baseline justify-between gap-3 text-[13.5px]">
              <span className="min-w-0 font-medium">{label}</span>
              <span className="flex-none font-semibold">{ms(p50)}</span>
            </div>
            <div
              className="relative mt-2 h-2.5"
              role="img"
              aria-label={`${label}: median ${ms(p50)}, 95th percentile ${ms(p95)}`}
              onMouseMove={(event) => tip.show(event, { primary: label, secondary: `Median ${ms(p50)}, 95th percentile ${ms(p95)}` })}
              onMouseLeave={tip.hide}
            >
              <i className="absolute inset-x-0 top-1/2 h-px bg-line" />
              <i className="absolute top-1/2 h-1 -translate-y-1/2 rounded-full bg-[#a8a8a8]" style={{ left: `${from}%`, width: `${to - from}%` }} />
              <i className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-card bg-[#1b1b1b]" style={{ left: `${from}%` }} />
            </div>
            <p className="mt-1 text-[12.5px] text-ink-3">
              {detail}. 95% finished within {ms(p95)}.
            </p>
          </li>
        );
      })}
    </ul>
  );
}

function CompareBar({ name, value, dark }: { name: string; value: number; dark: boolean }) {
  return (
    <div className="grid grid-cols-[104px_minmax(0,1fr)_52px] items-center gap-3 text-[13.5px]">
      <span className={dark ? "font-medium" : "text-ink-2"}>{name}</span>
      <span className="block h-2 rounded-r bg-sunk">
        <i className="block h-full rounded-r" style={{ width: `${value * 100}%`, background: dark ? "#1b1b1b" : "#a8a8a8" }} />
      </span>
      <span className={`text-right ${dark ? "font-semibold" : "text-ink-2"}`}>{formatPercent(value)}</span>
    </div>
  );
}

function CompareGroup({ title, jev, baseline }: { title: string; jev: number; baseline: number }) {
  return (
    <div className="min-w-0">
      <p className="text-[13.5px] font-medium">{title}</p>
      <div className="mt-2.5 grid gap-2">
        <CompareBar name="Jev" value={jev} dark />
        <CompareBar name="Baseline rules" value={baseline} dark={false} />
      </div>
    </div>
  );
}

function RunBench({ active }: { active: boolean }) {
  const [ref, inView] = useInView<HTMLDivElement>();
  const replay = useRunReplay(active && inView);

  return (
    <div ref={ref} className="mt-14 grid grid-cols-[minmax(0,1fr)] items-start gap-x-12 gap-y-5 min-[1180px]:grid-cols-[minmax(280px,320px)_minmax(0,1fr)]">
      <div className="min-[1180px]:pt-6">
        <h3 className="text-[26px] leading-[1.15] font-semibold tracking-[-0.024em] text-balance">Watch that run play back</h3>
        <p className="mt-2 max-w-[56ch] text-[15px] leading-[1.45] text-ink-2">
          Each conversation is replayed one caller turn at a time and scored against its known answer. Then every failure gets reviewed, and what it teaches is proposed as a lesson.
        </p>
        <button type="button" onClick={replay.play} disabled={replay.playing} className="mt-5 h-11 rounded-full bg-mag px-5 text-[15px] font-semibold text-white hover:bg-mag-deep disabled:bg-sunk disabled:text-ink-2">
          {replay.playing ? "Replaying" : "Replay the run"}
        </button>
        <p className="mt-4 text-[13px] text-ink-2">Sped up. The totals are the run's real ones, and only the finishing order is reconstructed.</p>
      </div>
      <div className="min-w-0 overflow-x-auto rounded-[18px]">
        <div className="min-w-[760px]">
          <ArchitectureFigure key={replay.playId} {...replay.frame} paused={false} />
        </div>
      </div>
    </div>
  );
}

function SectionHead({ title, children }: { title: string; children: ReactNode }) {
  return (
    <>
      <h2 className="max-w-[24ch] text-[clamp(30px,3.2vw,42px)] leading-[1.08] font-semibold tracking-[-0.03em] text-balance">{title}</h2>
      <p className="mt-3 max-w-[68ch] text-[16px] leading-[1.45] text-ink-2">{children}</p>
    </>
  );
}

export function HomeResults({ active }: { active: boolean }) {
  return (
    <section className="mt-24">
      <SectionHead title="Tested against conversations with known answers">
        Results from one complete run of {SCORED_TOTAL + WEAK_TOTAL} calls and texts. It includes every miss and false alarm, and contains no T-Mobile customer data.
      </SectionHead>

      <Card className="mt-7 p-6 sm:p-8">
        <div className="grid grid-cols-[minmax(0,1fr)] gap-x-14 gap-y-9 lg:grid-cols-2">
          <OutcomeColumn
            title={`${SCAM_TOTAL} scam conversations`}
            rate={CATCH_RATE}
            statement="rated dangerous"
            of={SCAM_TOTAL}
            noun="scams"
            groups={[
              { result: "right", label: "Caught", n: OUTCOMES.caught },
              { result: "soft", label: "Rated uncertain", n: OUTCOMES.softMiss },
              { result: "wrong", label: "Missed", n: OUTCOMES.missed },
            ]}
          />
          <OutcomeColumn
            title={`${LEGIT_TOTAL} legitimate conversations`}
            rate={FALSE_ALARM_RATE}
            statement="wrongly rated dangerous. The customer can carry on with one tap."
            of={LEGIT_TOTAL}
            noun="legitimate conversations"
            groups={[
              { result: "right", label: "Cleared", n: OUTCOMES.clear },
              { result: "soft", label: "Rated uncertain", n: OUTCOMES.softFalseAlarm },
              { result: "wrong", label: "False alarms", n: OUTCOMES.falseAlarm },
            ]}
          />
        </div>
        <div className="mt-6 border-t border-line pt-4">
          <Key />
        </div>
      </Card>

      <div className="mt-8 px-1">
        <Figures
          items={[
            [`overall score across ${SCORED_TOTAL} scored conversations`, formatPercent(OVERALL_SCORE)],
            ["named the right scam type", formatPercent(METHOD_ACCURACY)],
            [`scam types in this run, out of ${CORPUS.scamMethods} in the library`, String(SCAM_TYPES_TESTED)],
            [`errors in ${count(STEP_TOTAL)} pipeline steps`, String(STEP_ERRORS)],
          ]}
        />
      </div>

      <div className="mt-8 grid grid-cols-[minmax(0,1fr)] gap-5 lg:grid-cols-2">
        <Card className="min-w-0 p-6">
          <PanelTitle>Results by scam family</PanelTitle>
          <FamilyBars />
        </Card>
        <Card className="min-w-0 p-6">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4">
            <PanelTitle>Median time per step</PanelTitle>
            <span className="text-[13px] text-ink-2">
              {RUN.decisionsPerS?.toFixed(1)} decisions a second on {RUN.lanesConfigured} lanes
            </span>
          </div>
          <TimingRanges />
        </Card>
      </div>

      <Card className="mt-5 p-6">
        <PanelTitle>Compared with simple rules</PanelTitle>
        <div className="mt-4 grid grid-cols-[minmax(0,1fr)] gap-x-14 gap-y-5 lg:grid-cols-2">
          <CompareGroup title="Scams rated dangerous" jev={CATCH_RATE} baseline={BASELINE_CATCH_RATE} />
          <CompareGroup title="Legitimate conversations wrongly rated dangerous" jev={FALSE_ALARM_RATE} baseline={BASELINE_FALSE_ALARM_RATE} />
        </div>
        <p className="mt-4 max-w-[86ch] text-[13px] text-ink-2">
          Baseline rules are our own yardstick, not a T-Mobile product. They ran on a separate set of {BASELINE.n} generated conversations, so read this as a direction and not a head-to-head.
        </p>
      </Card>

      <RunBench active={active} />

      <div className="mt-14">
        <h3 className="text-[26px] leading-[1.15] font-semibold tracking-[-0.024em]">The test library</h3>
        <div className="mt-4">
          <Figures
            items={[
              ["labeled conversations", count(CORPUS.total)],
              ["phone calls", count(CORPUS.calls)],
              ["texts", count(CORPUS.texts)],
              ["legitimate conversations, so false alarms get tested too", count(CORPUS.legitimate)],
            ]}
          />
        </div>
        <p className="mt-5 max-w-[86ch] text-[13px] text-ink-2">
          {count(CORPUS.exactLabels)} have exact labels. {count(CORPUS.inferredLabels)} have inferred labels, come from public robocall and text datasets, and are reported separately. Figures on this page come from sandbox run {RUN_ID.replace("run-", "")} on 8 November 2026, using {RUN.byModel?.[0].model}. It is one run, so scam types with few examples can move between runs. {WEAK_TOTAL} conversations with inferred labels were caught and left out of the score.
        </p>
      </div>
    </section>
  );
}
