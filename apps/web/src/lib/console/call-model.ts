import type { RedFlag } from "./flags";

/**
 * The shared model of one traced call. Screens render a CallTrace and nothing else.
 *
 * Privacy rule for everything in here: markers only. No transcript text, names, organizations or
 * full phone numbers. A finished call is deleted, so a trace never outlives its session.
 */

export const NODE_IDS = [
  "trigger", "base", "mcp", "customer", "caller", "window", "jev",
  "alerting", "tlife", "check", "lessons", "callback", "purge",
] as const;
export type NodeId = (typeof NODE_IDS)[number];

export type NodeKind = "simulated" | "agent" | "model" | "device" | "memory" | "output" | "knowledge";

export interface PipelineNode {
  id: NodeId;
  name: string;
  role: string;
  kind: NodeKind;
}

export const PIPELINE_NODES: PipelineNode[] = [
  { id: "trigger", name: "Test call", role: "Starts a simulated call for the demo", kind: "simulated" },
  { id: "base", name: "Base agent", role: "Listens live and routes the conversation", kind: "agent" },
  { id: "mcp", name: "Call MCP", role: "Tool call that places the test call", kind: "simulated" },
  { id: "customer", name: "Customer line", role: "Live audio from the customer's side", kind: "device" },
  { id: "caller", name: "Caller line", role: "Live audio from the caller's side", kind: "device" },
  { id: "window", name: "Conversation window", role: "Held in memory only, for this call", kind: "memory" },
  { id: "jev", name: "Jev", role: "Rates how much danger the customer is in", kind: "model" },
  { id: "alerting", name: "Alerting agent", role: "Decides how to reach the customer", kind: "agent" },
  { id: "tlife", name: "T-Life notification", role: "Reaches the customer in the app", kind: "output" },
  { id: "check", name: "Checking agent", role: "Rereads the whole call once it ends", kind: "agent" },
  { id: "lessons", name: "Sandbox lessons", role: "What the sandbox learned from past test calls", kind: "knowledge" },
  { id: "callback", name: "Urgent callback", role: "Phones the customer when an alert is not enough", kind: "output" },
  { id: "purge", name: "Delete", role: "Erases the window and every marker", kind: "memory" },
];

export const LINK_IDS = [
  "trigger>base", "base>mcp", "mcp>customer", "mcp>caller", "customer>base", "caller>base",
  "base>window", "window>jev", "jev>alerting", "alerting>tlife", "window>check", "lessons>check",
  "check>alerting", "alerting>callback", "window>purge",
] as const;
export type LinkId = (typeof LINK_IDS)[number];

/** Danger tiers, lowest first. Risk only ever rises during a call (rule R5). */
export const TIERS = ["Low", "Suspicious", "High", "Severe"] as const;
export type Tier = 0 | 1 | 2 | 3;

export type CallPhase = "connecting" | "live" | "checking" | "responding" | "deleted";
export type ActivityState = "idle" | "active" | "done";

export interface CustomerNotice {
  channel: "t-life" | "urgent-callback";
  timing: "during-call" | "after-call";
  title: string;
  body: string;
}

/** One moment in a call. */
export interface Beat {
  t: number;
  phase: CallPhase;
  danger: number;
  tier: Tier;
  /** Plain description of the marker. Never quotes the conversation. */
  marker: string;
  detail: string;
  flag?: RedFlag;
  links: LinkId[];
  status: Partial<Record<NodeId, string>>;
  /** Nodes whose status on this beat means they have stopped working. */
  settled?: NodeId[];
  notice?: CustomerNotice;
}

export interface Scenario {
  id: string;
  name: string;
  /** Seconds. Phases come from the beats. */
  duration: number;
  beats: Beat[];
}

export interface CallTrace {
  scenario: Scenario;
  t: number;
  past: Beat[];
  now: Beat;
  phase: CallPhase;
  danger: number;
  tier: Tier;
  /** Time the current tier was first reached. */
  tierSince: number;
  raisedFlags: Set<RedFlag>;
  notices: CustomerNotice[];
  nodes: Record<NodeId, { state: ActivityState; status: string }>;
  links: Record<LinkId, ActivityState>;
}

/** Everything a screen shows at time t. Derived from the beats, so scrubbing can't drift. */
export function traceAt(scenario: Scenario, t: number): CallTrace {
  const past = scenario.beats.filter((beat) => beat.t <= t);
  const now = past[past.length - 1];
  const earlier = past.slice(0, -1);

  const nodes = {} as CallTrace["nodes"];
  for (const id of NODE_IDS) {
    const latest = [...past].reverse().find((beat) => beat.status[id] !== undefined);
    const working = now.status[id] !== undefined && !now.settled?.includes(id);
    nodes[id] = { state: working ? "active" : latest ? "done" : "idle", status: latest?.status[id] ?? "Waiting" };
  }

  const links = {} as CallTrace["links"];
  for (const id of LINK_IDS) {
    links[id] = now.links.includes(id) ? "active" : earlier.some((beat) => beat.links.includes(id)) ? "done" : "idle";
  }

  return {
    scenario,
    t,
    past,
    now,
    phase: now.phase,
    danger: now.danger,
    tier: now.tier,
    tierSince: past.find((beat) => beat.tier === now.tier)?.t ?? 0,
    raisedFlags: new Set(past.flatMap((beat) => (beat.flag ? [beat.flag] : []))),
    notices: past.flatMap((beat) => (beat.notice ? [beat.notice] : [])),
    nodes,
    links,
  };
}

/** Timing follows evals/fixtures/hero1_fake_bank.json. Danger values are illustrative. */
export const FAKE_BANK_SCENARIO: Scenario = {
  id: "code-request",
  name: "Caller asks for a one-time code",
  duration: 168,
  beats: [
    {
      t: 0, phase: "connecting", danger: 0.04, tier: 0,
      marker: "Test call started", detail: "Simulated from the console",
      links: ["trigger>base"], status: { trigger: "Pressed", base: "Starting call" }, settled: ["trigger"],
    },
    {
      t: 2, phase: "connecting", danger: 0.04, tier: 0,
      marker: "Call placed through the MCP", detail: "Simulated tool call",
      links: ["base>mcp", "mcp>customer", "mcp>caller"],
      status: { base: "Tool call sent", mcp: "Placing call", customer: "Ringing", caller: "Ringing" },
    },
    {
      t: 5, phase: "live", danger: 0.12, tier: 0,
      marker: "Call connected", detail: "Both lines streaming to the Base agent",
      links: ["customer>base", "caller>base", "base>window"],
      status: { mcp: "Finished", customer: "Streaming", caller: "Streaming", base: "Listening", window: "Holding this call" },
      settled: ["mcp"],
    },
    {
      t: 11, phase: "live", danger: 0.24, tier: 0,
      marker: "Caller claimed authority", detail: "Jev rated the first window",
      flag: "claims_authority",
      links: ["customer>base", "caller>base", "window>jev"],
      status: { window: "Sent a small block", jev: "Rating: low" },
    },
    {
      t: 25, phase: "live", danger: 0.34, tier: 1,
      marker: "Unexpected account warning", detail: "Tier raised, quiet card sent",
      links: ["window>jev", "jev>alerting", "alerting>tlife"],
      status: { jev: "Rating: suspicious", alerting: "Sending quiet card", tlife: "Quiet card delivered" },
      notice: { channel: "t-life", timing: "during-call", title: "Be careful on this call", body: "This caller isn't on our verified list." },
    },
    {
      t: 45, phase: "live", danger: 0.46, tier: 1,
      marker: "Pressure to act now", detail: "Creates urgency",
      flag: "creates_urgency",
      links: ["customer>base", "caller>base", "window>jev"],
      status: { window: "Sent a small block", jev: "Rating: suspicious", alerting: "Standing by" },
      settled: ["alerting"],
    },
    {
      t: 97, phase: "live", danger: 0.68, tier: 2,
      marker: "One-time code arrived during the call", detail: "Signal from the customer's phone",
      links: ["customer>base", "window>jev", "jev>alerting", "alerting>tlife"],
      status: { base: "Signal received", jev: "Rating: high", alerting: "Sending warning", tlife: "Warning delivered" },
      notice: { channel: "t-life", timing: "during-call", title: "A code just arrived", body: "Don't share it with anyone on this call." },
    },
    {
      t: 106, phase: "live", danger: 0.91, tier: 3,
      marker: "Caller requested the code", detail: "Asks for a code",
      flag: "asks_for_code",
      links: ["window>jev", "jev>alerting", "alerting>tlife"],
      status: { jev: "Rating: severe", alerting: "Alerting the customer", tlife: "Alert on screen" },
      notice: { channel: "t-life", timing: "during-call", title: "This call may be a scam", body: "The caller is asking for a code your bank sent." },
    },
    {
      t: 123, phase: "live", danger: 0.96, tier: 3,
      marker: "Request to move money", detail: "Asks to move money",
      flag: "asks_to_move_money",
      links: ["customer>base", "caller>base", "window>jev"],
      status: { window: "Sent a small block", jev: "Rating: severe" },
    },
    {
      t: 136, phase: "checking", danger: 0.96, tier: 3,
      marker: "Call ended", detail: "Checking agent started on the whole window",
      links: ["window>check", "lessons>check"],
      status: {
        customer: "Ended", caller: "Ended", base: "Handed off", window: "Sent to Checking agent",
        check: "Rereading the call", lessons: "Applied", jev: "Finished", alerting: "Standing by", tlife: "Delivered",
      },
      settled: ["customer", "caller", "base", "jev", "alerting", "tlife"],
    },
    {
      t: 148, phase: "responding", danger: 0.96, tier: 3,
      marker: "Double check confirmed the danger", detail: "After-call summary sent",
      links: ["check>alerting", "alerting>tlife"],
      status: { check: "Confirmed", alerting: "Sending summary", tlife: "Summary delivered" },
      settled: ["check"],
      notice: { channel: "t-life", timing: "after-call", title: "We checked your last call", body: "It showed signs of a scam. Here's what to do next." },
    },
    {
      t: 158, phase: "deleted", danger: 0.96, tier: 3,
      marker: "Call data deleted", detail: "Window and markers erased",
      links: ["window>purge"],
      status: { window: "Erased", purge: "Complete", alerting: "Finished", lessons: "Finished" },
      settled: ["window", "purge", "alerting", "lessons"],
    },
  ],
};
