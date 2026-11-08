import type { ReactNode } from "react";
import { formatPercent } from "@/lib/console/format";
import { ms } from "@/lib/simulate/labels";
import { CATCH_RATE, CORPUS, count, FALSE_ALARM_RATE, LOSS_FACTS, LOSS_HEADLINE, NETWORK_FACTS, TIMINGS, WARNING_RESEARCH } from "@/lib/home/stats";
import { Card } from "../ui";
import { HomeHero } from "./HomeHero";
import { Figures, HomeResults } from "./HomeResults";

function Source({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="text-[12.5px] text-ink-3 underline decoration-wire underline-offset-2 hover:text-ink-2">
      {children}
    </a>
  );
}

function Heading({ children }: { children: ReactNode }) {
  return <h2 className="max-w-[24ch] text-[clamp(30px,3.2vw,42px)] leading-[1.08] font-semibold tracking-[-0.03em] text-balance">{children}</h2>;
}

function TheProblem() {
  return (
    <section className="mt-20">
      <Heading>A phone call is the most expensive way to get scammed</Heading>
      <div className="mt-8 grid grid-cols-[minmax(0,1fr)] items-end gap-x-16 gap-y-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <div>
          <p className="text-[clamp(84px,11.5vw,160px)] leading-[0.9] font-semibold tracking-[-0.055em] text-mag">{LOSS_HEADLINE.value}</p>
          <p className="mt-4 max-w-[34ch] text-[19px] leading-[1.3] tracking-[-0.012em]">{LOSS_HEADLINE.claim}</p>
          <p className="mt-2">
            <Source href={LOSS_HEADLINE.href}>{LOSS_HEADLINE.source}</Source>
          </p>
        </div>
        <ul className="divide-y divide-line border-y border-line">
          {LOSS_FACTS.map((fact) => (
            <li key={fact.value} className="grid grid-cols-[minmax(0,1fr)] gap-x-6 gap-y-1 py-4 sm:grid-cols-[136px_minmax(0,1fr)]">
              <p className="text-[28px] leading-[1.1] font-semibold tracking-[-0.028em]">{fact.value}</p>
              <div>
                <p className="text-[15px] leading-[1.4]">{fact.claim}</p>
                <Source href={fact.href}>{fact.source}</Source>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

const MOMENTS = [
  {
    name: "Before it rings",
    body: "Known scam numbers get a Scam Likely label. Those calls are already handled, so Safe Signal adds no agent to them.",
  },
  {
    name: "During the call",
    body: "Jev, our risk model, rates the conversation on each caller turn against 12 red-flag questions. If a bank code arrives or the caller asks for one, the customer gets a reason and three choices.",
  },
  {
    name: "After the call",
    body: "A checking agent rereads the whole call and can raise the risk. It sends a summary or places an urgent callback, then the call data is deleted.",
  },
];

function TheGap() {
  return (
    <section className="mt-24">
      <Heading>Safe Signal starts where the label stops</Heading>
      <p className="mt-3 max-w-[66ch] text-[16px] leading-[1.45] text-ink-2">
        A label can only warn someone before they answer. It can't help once the call is under way, on calls that were never labeled, or on calls the customer placed themselves.
      </p>

      <Card className="mt-7 p-6 sm:p-8">
        <div className="grid grid-cols-[minmax(0,1fr)] gap-x-2 gap-y-2 md:grid-cols-3">
          {MOMENTS.map((moment) => (
            <p key={moment.name} className="hidden text-[15px] font-semibold md:block">
              {moment.name}
            </p>
          ))}
          <div className="flex h-12 items-center rounded-xl bg-[#1b1b1b] md:rounded-l-xl md:rounded-r-[3px] px-4 text-[14px] font-semibold text-white">Scam Likely label today</div>
          <div className="flex h-12 items-center rounded-xl bg-alert md:rounded-l-[3px] md:rounded-r-xl px-4 text-[14px] font-semibold text-white md:col-span-2">Safe Signal</div>
          {MOMENTS.map((moment) => (
            <div key={moment.name} className="mt-3 md:pr-7">
              <p className="text-[15px] font-semibold md:hidden">{moment.name}</p>
              <p className="text-[14.5px] leading-[1.45] text-ink-2">{moment.body}</p>
            </div>
          ))}
        </div>
      </Card>

      <ul className="mt-8 grid grid-cols-[minmax(0,1fr)] gap-x-10 gap-y-6 px-1 lg:grid-cols-3">
        {NETWORK_FACTS.map((fact) => (
          <li key={fact.title}>
            <p className="text-[15px] font-semibold tracking-[-0.008em]">{fact.title}</p>
            <p className="mt-1 text-[14px] leading-[1.45] text-ink-2">{fact.body}</p>
            <Source href={fact.href}>{fact.source}</Source>
          </li>
        ))}
      </ul>
    </section>
  );
}

function WarningBar({ label, percent, shown, strong }: { label: string; percent: number; shown: string; strong: boolean }) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] items-end gap-x-3 gap-y-1.5">
      <span className="text-[14px] text-ink-2">{label}</span>
      <span className="text-[30px] leading-none font-semibold tracking-[-0.03em]">{shown}</span>
      <span className="col-span-2 block h-2 rounded-r bg-sunk">
        <i className="block h-full rounded-r" style={{ width: `${(percent / 18) * 100}%`, minWidth: 4, background: strong ? "var(--color-mag)" : "#a8a8a8" }} />
      </span>
    </div>
  );
}

const PROMISES: [string, string][] = [
  ["It never hangs up", "The customer decides, and Continue is always one tap."],
  ["It leaves emergency calls alone", "Calls to 911, 988 and local emergency numbers are never touched."],
  ["It doesn't keep the call", "No audio or transcript is saved. Only anonymous indicators stay, as evidence."],
  ["AI can only raise a warning", "A model can push a call's risk up, never below what the rules found."],
];

function TheAlert() {
  return (
    <section className="mt-24">
      <div className="grid grid-cols-[minmax(0,1fr)] gap-x-16 gap-y-8 lg:grid-cols-2">
        <div>
          <Heading>A warning only works if people can act on it</Heading>
          <p className="mt-4 max-w-[52ch] text-[16px] leading-[1.45] text-ink-2">
            Revolut's models caught over 90% of payment scams, and 85% of the customers it warned ignored the warning anyway. So a Safe Signal alert gives a reason and three things to do.
          </p>
          <p className="mt-2">
            <Source href={WARNING_RESEARCH.ignored.href}>{WARNING_RESEARCH.ignored.source}</Source>
          </p>
        </div>
        <Card className="self-start p-6 sm:p-7">
          <p className="text-[15px] font-semibold">Fraud rate in a UK experiment</p>
          <div className="mt-5 grid gap-5">
            <WarningBar label="No risk-gated warning" percent={18} shown="18%" strong={false} />
            <WarningBar label="Risk-gated warnings with action buttons" percent={1} shown="About 1%" strong />
          </div>
          <p className="mt-4 text-[13px] text-ink-2">A 94% reduction. Plain text warnings faded with repeat exposure.</p>
          <Source href={WARNING_RESEARCH.buttons.href}>{WARNING_RESEARCH.buttons.source}</Source>
        </Card>
      </div>

      <ul className="mt-12 grid grid-cols-[minmax(0,1fr)] gap-x-10 gap-y-6 border-t border-line pt-8 sm:grid-cols-2 lg:grid-cols-4">
        {PROMISES.map(([title, body]) => (
          <li key={title}>
            <p className="text-[15px] font-semibold tracking-[-0.008em]">{title}</p>
            <p className="mt-1 text-[14px] leading-[1.45] text-ink-2">{body}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function HomeView({ active }: { active: boolean }) {
  return (
    <div className="mx-auto max-w-[1360px]">
      <HomeHero active={active} />
      <div className="mt-9 border-t border-line pt-6">
        <Figures
          items={[
            ["of scams rated dangerous in testing", formatPercent(CATCH_RATE)],
            ["of legitimate conversations falsely flagged", formatPercent(FALSE_ALARM_RATE)],
            ["median time for Jev to rate the conversation", ms(TIMINGS[0].stat.p50 ?? 0)],
            ["labeled conversations in the test library", count(CORPUS.total)],
          ]}
        />
      </div>
      <TheProblem />
      <TheGap />
      <HomeResults active={active} />
      <TheAlert />
    </div>
  );
}
