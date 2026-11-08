import { familySummaries, parseLive, type StepStat } from "@/lib/simulate/parse";
import snapshot from "./run-snapshot.json";

/**
 * Every number on the home page, with where it came from. Run figures are computed from the frozen
 * summary of one sandbox run, so nothing here is typed in by hand except the rows marked as copied
 * from the sandbox API. Outside figures come from context/facts.md and link to their source.
 */

export const RUN = parseLive(snapshot);
export const RUN_ID = snapshot.id;
export const RUN_MODEL = snapshot.config.models[0];

const methods = RUN.byMethod ?? [];
const total = (key: string) => methods.reduce((sum, row) => sum + (row.counts[key] ?? 0), 0);

export const OUTCOMES = {
  caught: total("caught"),
  softMiss: total("soft_miss"),
  missed: total("missed"),
  clear: total("clear"),
  softFalseAlarm: total("soft_false_alarm"),
  falseAlarm: total("false_alarm"),
};

export const SCAM_TOTAL = OUTCOMES.caught + OUTCOMES.softMiss + OUTCOMES.missed;
export const LEGIT_TOTAL = OUTCOMES.clear + OUTCOMES.softFalseAlarm + OUTCOMES.falseAlarm;
export const SCORED_TOTAL = SCAM_TOTAL + LEGIT_TOTAL;
export const WEAK_TOTAL = RUN.weakLabels?.n ?? 0;

export const CATCH_RATE = OUTCOMES.caught / SCAM_TOTAL;
export const FALSE_ALARM_RATE = OUTCOMES.falseAlarm / LEGIT_TOTAL;
export const OVERALL_SCORE = (OUTCOMES.caught + OUTCOMES.clear + (OUTCOMES.softMiss + OUTCOMES.softFalseAlarm) / 2) / SCORED_TOTAL;
export const METHOD_ACCURACY = snapshot.by_model[0].method_accuracy;

export const SCAM_TYPES_TESTED = methods.filter((row) => row.method !== "legitimate").length;
export const FAMILIES = familySummaries(RUN.byMethod);

export const STEP_TOTAL = RUN.steps.reduce((sum, step) => sum + (step.count ?? 0), 0);
export const STEP_ERRORS = RUN.steps.reduce((sum, step) => sum + (step.errors ?? 0), 0);

const step = (name: string): StepStat => {
  const found = RUN.steps.find((item) => item.name === name);
  if (!found) throw new Error(`The run snapshot has no ${name} step`);
  return found;
};

export const TIMINGS = [
  { label: "Jev rates the danger", detail: "Once per conversation frame", stat: step("jev") },
  { label: "Nemotron fast updates its note", detail: "Keeps a short running note", stat: step("agent") },
  { label: "Nemotron deep reviews a failure", detail: "After the run has finished", stat: step("check") },
];

/**
 * Baseline rules on a later 600-case run, copied from GET /runs/<id>. The set was generated cases
 * only, so it is a yardstick and not a head-to-head with the mixed set above.
 */
export const BASELINE = {
  runId: "run-20261108122702957",
  n: 600,
  caught: 148,
  scams: 148 + 55 + 103,
  falseAlarm: 42,
  legit: 203 + 49 + 42,
};
export const BASELINE_CATCH_RATE = BASELINE.caught / BASELINE.scams;
export const BASELINE_FALSE_ALARM_RATE = BASELINE.falseAlarm / BASELINE.legit;

/** The test library, copied from GET /corpus on 8 November 2026. */
export const CORPUS = {
  total: 340991,
  calls: 80789,
  texts: 260202,
  legitimate: 156726,
  scamMethods: 36,
  exactLabels: 329215,
  inferredLabels: 11776,
  publicRobocalls: 686,
  publicTexts: 16272,
};

export const count = (value: number) => value.toLocaleString("en-US");

export interface SourcedFact {
  value: string;
  claim: string;
  source: string;
  href: string;
}

const SPOKESMAN = "https://www.spokesman.com/stories/2026/apr/03/americans-lost-a-record-159-billion-to-scams-in-20";

export const LOSS_HEADLINE: SourcedFact = {
  value: "$15.9B",
  claim: "reported lost to fraud by US consumers in 2025, a record.",
  source: "FTC, via Spokesman-Review, April 2026",
  href: SPOKESMAN,
};

export const LOSS_FACTS: SourcedFact[] = [
  {
    value: "$1,835",
    claim: "median loss when the scam came by phone call, the highest of any contact method in 2025.",
    source: "FTC data, via Experian, 2026",
    href: "https://www.experian.com/blogs/ask-experian/survey-findings-are-consumers-making-it-easier-for-identity-thieves/",
  },
  {
    value: "About $3B",
    claim: "reported lost by adults 60 and over in 2025. Six-figure losses were 6% of their reports and 70% of the dollars.",
    source: "FTC report to Congress, via PPC Land, 2026",
    href: "https://ppc.land/older-americans-lost-3-billion-to-fraud-in-2025-ftc-tells-congress/",
  },
  {
    value: "$893M",
    claim: "in 2025 losses tied by the FBI to AI-related scams, including voice cloning.",
    source: "FBI IC3 report, via AARP, 2026",
    href: "https://www.aarp.org/money/scams-fraud/fbi-ftc-report-2025-losses",
  },
];

export const WARNING_RESEARCH = {
  ignored: {
    source: "Revolut, evidence to UK Parliament, March 2022",
    href: "https://committees.parliament.uk/oralevidence/9895/pdf",
  },
  buttons: {
    source: "Nottingham CeDEx, about 9,000 people, 2023",
    href: "https://www.nottingham.ac.uk/cedex/documents/papers/cedex-discussion-paper-2023-08.pdf",
  },
};

export const NETWORK_FACTS = [
  {
    title: "AI in the network is already here",
    body: "T-Mobile's Live Translation runs an AI agent in its network core, and T-Mobile says it stores no recordings or transcripts.",
    source: "The Register, February 2026",
    href: "https://www.theregister.com/2026/02/11/tmobile_network_ai_translate_live_calls/",
  },
  {
    title: "Content filters are losing sight of messages",
    body: "iPhone-to-Android RCS became end-to-end encrypted in iOS 26.5, which makes carrier content filtering harder.",
    source: "Infosecurity Magazine, May 2026",
    href: "https://www.infosecurity-magazine.com/news/apple-google-rcs-end-to-end/",
  },
  {
    title: "Carrier fraud signals are arriving",
    body: "Aduna, backed by AT&T, T-Mobile and Verizon, targets Q4 2026 for KYC, Device Swap and Call Forward Detection APIs.",
    source: "Telco Magazine, October 2026",
    href: "https://telcomagazine.com/news/aduna-unveils-us-fraud-apis-with-at-t-and-verizon",
  },
];
