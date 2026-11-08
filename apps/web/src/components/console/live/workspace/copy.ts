import { TIERS, type CallPhase, type CallTrace, type Tier } from "@/lib/console/call-model";
import { formatClock } from "@/lib/console/format";

export const PHASE_LABEL: Record<CallPhase, string> = {
  connecting: "Connecting",
  live: "On the call",
  checking: "Rereading",
  responding: "Reaching out",
  deleted: "Erased",
};

export const TIER_DOT: Record<Tier, string> = {
  0: "bg-ink-3",
  1: "bg-[#C8953A]",
  2: "bg-[#EE5CA6]",
  3: "bg-mag",
};

const LIVE_HEADLINE: Record<Tier, string> = {
  0: "Nothing worrying so far",
  1: "Something on this call needs watching",
  2: "This caller looks risky",
  3: "The customer is in danger right now",
};

function headline(trace: CallTrace): string {
  switch (trace.phase) {
    case "connecting":
      return "Connecting the call";
    case "live":
      return LIVE_HEADLINE[trace.tier];
    case "checking":
      return trace.tier >= 2 ? "The reread found something serious" : "Rereading the call for anything missed";
    case "responding":
      return trace.notices.at(-1)?.channel === "urgent-callback" ? "Phoning the customer back" : "Telling the customer what the check found";
    case "deleted":
      return "This call has been erased";
  }
}

/** The headline and risk line. Says what is going on, never the word for the label it replaced. */
export function describeCall(trace: CallTrace): { title: string; detail: string; hot: boolean } {
  const tierName = TIERS[trace.tier];
  const standing = trace.tier === 0 ? `${tierName}, watching` : `${tierName} since ${formatClock(trace.tierSince)}`;
  return {
    title: headline(trace),
    detail: `${standing}, risk ${trace.danger.toFixed(2)}. ${trace.now.marker}.`,
    hot: trace.tier >= 2,
  };
}
