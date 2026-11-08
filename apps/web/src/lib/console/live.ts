import type { Beat, CallPhase, CustomerNotice, NodeId, Scenario, Tier } from "./call-model";
import { TIERS } from "./call-model";
import type { RedFlag } from "./flags";

/**
 * A real call, as the Safe Signal API reports it (GET /sessions/{id}/view, services/api/view.py), turned into
 * the same beats a scripted call plays. Markers only: the API never sends turn text, quotes or numbers.
 */

export interface LiveView {
  session_id: string;
  /** Call time of the newest event the API took in. */
  t: number;
  /** When the customer picked up. Null while it rings, and for a declined call. */
  answered_t: number | null;
  call_running: boolean;
  ended: boolean;
  /** The transcript is gone from the API's memory, so the call is finished. */
  erased: boolean;
  guard_paused: boolean;
  risk: { score: number; level: number } | null;
  signals: { kind: string; t: number }[];
  flags: { kind: string; t: number }[];
  alerts: { t: number; level: number; reason: string }[];
  choice: string | null;
  /** The after-call planner's call on whether the customer handed anything over. */
  disclosed: boolean | null;
  plan: { name: string; status: string }[];
  timeline: TimelineItem[];
}

export interface TimelineItem {
  t: number;
  node: string;
  score?: number;
  level?: number;
  status?: string;
  steps?: string[];
  disclosed?: boolean | null;
  choice?: string | null;
}

const FLAG: Record<string, { marker: string; flag?: RedFlag }> = {
  gift_cards: { marker: "Caller asked for gift cards", flag: "asks_for_gift_cards" },
  read_code: { marker: "Caller asked for the one-time code", flag: "asks_for_code" },
  card_details: { marker: "Caller asked for card details", flag: "asks_for_card_details" },
  safe_account: { marker: "Caller asked to move money", flag: "asks_to_move_money" },
  remote_access: { marker: "Caller asked for remote access", flag: "asks_remote_access" },
  policy_contradiction: { marker: "Caller said something a bank never would" },
  urgency_secrecy: { marker: "Pressure to act now and keep quiet", flag: "creates_urgency" },
  other: { marker: "Something else on the call looked wrong" },
};

const SIGNAL: Record<string, string> = {
  otp_during_call: "One-time code arrived during the call",
  bank_app_during_call: "Bank app opened during the call",
  account_change_during_call: "Account change during the call",
  scam_list_hit: "Number is on a scam list",
  anomaly: "Unusual activity on the account",
};

const SCREEN: Record<string, string> = {
  unknown_caller: "Unknown number",
  unverified_caller: "Not on the verified list",
  verified_caller: "Verified organization",
};

const STEP: Record<string, string> = {
  lock_account: "Hold account changes",
  callback: "Call the customer back",
  recovery: "Send recovery steps",
  evidence: "Save evidence",
  notify_trusted_contact: "Tell the trusted contact",
};

const CHOICE: Record<string, string> = {
  call_bank: "Call my bank",
  ask_trusted_contact: "Ask someone I trust",
  continue: "Continue the call",
  dismiss: "Dismissed the alert",
};

/** Alert ladder (none, nudge, whisper, alert) to the console's tiers. */
const tierOf = (level: number): Tier => Math.max(0, Math.min(3, Math.round(level))) as Tier;
const rating = (tier: Tier) => `Rating: ${TIERS[tier].toLowerCase()}`;

type Draft = Omit<Beat, "danger" | "tier" | "phase"> & { phase?: CallPhase };

/** The first beat, before the API has said anything. */
export function placingScenario(remoteId: string): Scenario {
  return liveScenario({
    session_id: remoteId, t: 0, answered_t: null, call_running: true, ended: false, erased: false, guard_paused: false,
    risk: null, signals: [], flags: [], alerts: [], choice: null, disclosed: null, plan: [], timeline: [],
  });
}

export function liveScenario(view: LiveView): Scenario {
  const scores = view.timeline.filter((x) => x.node === "decide" && x.score !== undefined);
  const dangerAt = (t: number) => Math.max(0, ...scores.filter((x) => x.t <= t).map((x) => x.score ?? 0));
  const tierAt = (t: number) => tierOf(Math.max(0, ...scores.filter((x) => x.t <= t).map((x) => x.level ?? 0)));
  const answered = view.answered_t;
  const phaseAt = (t: number): CallPhase => (answered !== null && t >= answered ? "live" : "connecting");

  const screen = view.signals.filter((s) => s.kind in SCREEN).map((s) => SCREEN[s.kind]);
  const during: Draft[] = [
    {
      t: 0, phase: "connecting",
      marker: "Real call placed", detail: screen.length ? `ElevenLabs is ringing the demo phone. ${screen.join(", ")}` : "ElevenLabs is ringing the demo phone",
      links: ["trigger>base", "base>mcp", "mcp>customer", "mcp>caller"],
      status: { trigger: "Pressed", base: "Starting call", mcp: "Placing call", customer: "Ringing", caller: "Ringing" },
      settled: ["trigger"],
    },
  ];
  if (answered !== null) {
    during.push({
      t: answered, phase: "live",
      marker: "Call answered", detail: "Both sides streaming to the Base agent",
      links: ["customer>base", "caller>base", "base>window"],
      status: { mcp: "Finished", customer: "Streaming", caller: "Streaming", base: "Listening", window: "Holding this call" },
      settled: ["mcp"],
    });
  }
  for (const s of view.signals) {
    if (!(s.kind in SIGNAL)) continue;
    during.push({
      t: s.t, marker: SIGNAL[s.kind], detail: "Signal from the customer's phone, without its contents",
      links: ["customer>base", "window>jev"],
      status: { base: "Signal received", jev: rating(tierAt(s.t)) },
    });
  }
  for (const f of view.flags) {
    const known = FLAG[f.kind] ?? FLAG.other;
    during.push({
      t: f.t, marker: known.marker, detail: "Flagged by the Call Guardian", flag: known.flag,
      links: ["customer>base", "caller>base", "window>jev"],
      status: { window: "Sent a small block", jev: rating(tierAt(f.t)) },
    });
  }
  for (const a of view.alerts) {
    const tier = tierOf(a.level);
    if (tier >= 3) {
      during.push({
        t: a.t, marker: "Customer alerted", detail: a.reason,
        links: ["window>jev", "jev>alerting", "alerting>tlife"],
        status: { jev: rating(tier), alerting: "Alerting the customer", tlife: "Alert sent to the phone" },
        notice: { channel: "t-life", timing: "during-call", title: "Stop: this call is a scam", body: a.reason },
      });
    } else if (tier === 2) {
      during.push({
        t: a.t, marker: "Customer warned", detail: a.reason,
        links: ["window>jev", "jev>alerting", "alerting>tlife"],
        status: { jev: rating(tier), alerting: "Sending a warning", tlife: "Warning sent to the phone" },
        notice: { channel: "t-life", timing: "during-call", title: "Be careful on this call", body: a.reason },
      });
    } else if (tier === 1) {
      during.push({
        t: a.t, marker: "Watching more closely", detail: a.reason,
        links: ["window>jev", "jev>alerting"],
        status: { jev: rating(tier), alerting: "Watching, nothing sent yet" },
      });
    }
  }
  for (const x of view.timeline) {
    if (x.node !== "user_choice") continue;
    during.push({
      t: x.t, marker: `Customer pressed "${CHOICE[x.choice ?? ""] ?? "a button"}"`, detail: "From the alert on the phone",
      links: ["customer>base"], status: { base: "Choice received" },
    });
  }
  // Stable sort: at the same second, signals and flags come before the alert they caused.
  during.sort((a, b) => a.t - b.t);

  const after: Draft[] = [];
  const end = view.timeline.find((x) => x.node === "call_end");
  if (end) {
    const aftercare = view.timeline.some((x) => x.node === "planner") || (view.ended && !view.erased);
    const ended: NodeId[] = ["customer", "caller", "base", "jev", "alerting", "tlife"];
    after.push({
      t: end.t, phase: "checking",
      marker: answered === null ? "Call not answered" : "Call ended",
      detail: answered === null
        ? "Nothing was heard, so nothing ran"
        : aftercare ? "The after-call planner is rereading the whole call" : "Nothing worrying, so no after-call work",
      links: aftercare ? ["window>check"] : [],
      status: {
        customer: "Ended", caller: "Ended", base: "Handed off", jev: "Finished", alerting: "Standing by", tlife: "Delivered",
        ...(aftercare ? { window: "Sent to the planner", check: "Rereading the call" } : {}),
      },
      settled: ended,
    });
    let t = end.t;
    for (const x of view.timeline) {
      if (x.node === "planner") {
        t += 1;
        const steps = (x.steps ?? []).map((name) => STEP[name] ?? name).join(", ");
        const gave = x.disclosed ? "The customer gave details away" : "The customer gave nothing away";
        after.push({
          t, phase: "responding", marker: "After-call plan ready", detail: `${gave}. ${steps}`,
          links: ["check>alerting"], status: { check: "Plan ready", alerting: "Working the plan" }, settled: ["check"],
        });
      } else if (x.node in STEP) {
        t += 1;
        after.push({ t, phase: "responding", ...stepBeat(x.node, x.status ?? "done") });
      } else if (x.node === "router" && view.erased) {
        t += 1;
        after.push(erasedBeat(t, aftercare));
      }
    }
    if (view.erased && !after.some((beat) => beat.phase === "deleted")) after.push(erasedBeat(t + 1, aftercare));
  }

  const beats: Beat[] = [...during, ...after].map((draft) => {
    const tier = tierAt(draft.t);
    return { ...draft, phase: draft.phase ?? phaseAt(draft.t), danger: dangerAt(draft.t), tier };
  });
  // Risk never drops (rule R5), and the after-call beats keep the call's final level.
  for (let i = 1; i < beats.length; i += 1) {
    beats[i] = { ...beats[i], danger: Math.max(beats[i].danger, beats[i - 1].danger), tier: Math.max(beats[i].tier, beats[i - 1].tier) as Tier };
  }
  // Past both the last beat and the API's clock, so a quiet call is never mistaken for a finished one.
  const reached = Math.max(view.t, beats[beats.length - 1].t);
  return { id: `live-${view.session_id}`, name: "Real call to the demo phone", duration: Math.max(60, Math.ceil((reached + 15) / 30) * 30), beats };
}

function stepBeat(name: string, status: string): Pick<Beat, "marker" | "detail" | "links" | "status"> & { notice?: CustomerNotice } {
  const failed = status === "failed";
  const label = STEP[name] ?? name;
  if (failed) return { marker: `${label}: failed`, detail: "The step failed. The call itself was never touched", links: [], status: { alerting: `${label} failed` } };
  if (status === "skipped") return { marker: `${label}: skipped`, detail: "Not needed after all", links: [], status: {} };
  switch (name) {
    case "callback":
      return {
        marker: "Urgent callback placed", detail: "The follow-up agent offers to connect the bank's verified number",
        links: ["check>alerting", "alerting>callback"],
        status: { alerting: "Calling the customer", callback: "Calling now" },
        notice: { channel: "urgent-callback", timing: "after-call", title: "Safe Signal is calling you", body: "To connect you with your bank's verified number." },
      };
    case "recovery":
      return {
        marker: "Recovery steps sent", detail: "What to do now, sent to the phone",
        links: ["check>alerting", "alerting>tlife"],
        status: { alerting: "Sending recovery steps", tlife: "Summary sent to the phone" },
        notice: { channel: "t-life", timing: "after-call", title: "After your call: what to do now", body: "Steps to protect your account." },
      };
    case "lock_account":
      return { marker: "Account changes held", detail: "Simulated hold on the demo account", links: ["check>alerting"], status: { alerting: "Holding account changes" } };
    case "evidence":
      return { marker: "Evidence saved", detail: "Markers only, never the recording or the words", links: [], status: { check: "Evidence saved" } };
    default:
      return { marker: label, detail: "Done", links: ["check>alerting"], status: { alerting: label } };
  }
}

function erasedBeat(t: number, aftercare: boolean): Draft {
  const done: NodeId[] = aftercare ? ["window", "purge", "alerting", "check"] : ["window", "purge"];
  return {
    t, phase: "deleted", marker: "Call data deleted", detail: "Transcript and markers erased from memory",
    links: ["window>purge"],
    status: { window: "Erased", purge: "Complete", ...(aftercare ? { alerting: "Finished", check: "Finished" } : {}) },
    settled: done,
  };
}

/** The play head for a live call: wherever the API has reached. */
export function liveNow(view: LiveView, scenario: Scenario): number {
  return Math.max(view.t, scenario.beats[scenario.beats.length - 1].t);
}
