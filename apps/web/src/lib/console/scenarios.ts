import { FAKE_BANK_SCENARIO, type Beat, type CustomerNotice, type NodeId, type Scenario } from "./call-model";

/** Synthetic scripts for test calls. Danger only rises within a scenario (rule R5). */

const LINES_UP: Partial<Record<NodeId, string>> = {
  customer: "Streaming",
  caller: "Streaming",
  base: "Listening",
  window: "Holding this call",
};

const LINES_ENDED: Partial<Record<NodeId, string>> = {
  customer: "Ended",
  caller: "Ended",
  base: "Handed off",
  jev: "Finished",
  window: "Sent to Checking agent",
};
const LINES_ENDED_SETTLED: NodeId[] = ["customer", "caller", "base", "jev"];

function connectingBeats(): Beat[] {
  return [
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
  ];
}

const ORDINARY_CALL: Scenario = {
  id: "ordinary-call",
  name: "Ordinary call that stays low",
  duration: 92,
  beats: [
    ...connectingBeats(),
    {
      t: 5, phase: "live", danger: 0.06, tier: 0,
      marker: "Call connected", detail: "Both lines streaming to the Base agent",
      links: ["customer>base", "caller>base", "base>window"],
      status: { ...LINES_UP, mcp: "Finished" }, settled: ["mcp"],
    },
    {
      t: 18, phase: "live", danger: 0.08, tier: 0,
      marker: "Routine conversation", detail: "Jev rated the first window",
      links: ["customer>base", "caller>base", "window>jev"],
      status: { ...LINES_UP, window: "Sent a small block", jev: "Rating: low" },
    },
    {
      t: 41, phase: "live", danger: 0.09, tier: 0,
      marker: "Caller pointed to safe verification", detail: "Points to safe verification",
      flag: "verifies_safely",
      links: ["customer>base", "caller>base", "window>jev"],
      status: { ...LINES_UP, window: "Sent a small block", jev: "Rating: low" },
    },
    {
      t: 62, phase: "checking", danger: 0.09, tier: 0,
      marker: "Call ended", detail: "Checking agent started on the whole window",
      links: ["window>check", "lessons>check"],
      status: { ...LINES_ENDED, check: "Rereading the call", lessons: "Applied" },
      settled: LINES_ENDED_SETTLED,
    },
    {
      t: 73, phase: "checking", danger: 0.09, tier: 0,
      marker: "Double check found nothing", detail: "Cleared, so no notice was sent",
      links: ["window>check"],
      status: { check: "Cleared", window: "Sent to Checking agent" }, settled: ["check"],
    },
    {
      t: 81, phase: "deleted", danger: 0.09, tier: 0,
      marker: "Call data deleted", detail: "Window and markers erased",
      links: ["window>purge"],
      status: { window: "Erased", purge: "Complete", lessons: "Finished" },
      settled: ["window", "purge", "lessons"],
    },
  ],
};

const FRIENDLY_STRANGER: Scenario = {
  id: "friendly-stranger",
  name: "Stranger far away wants to be friends",
  duration: 158,
  beats: [
    ...connectingBeats(),
    {
      t: 5, phase: "live", danger: 0.1, tier: 0,
      marker: "Call connected", detail: "Both lines streaming to the Base agent",
      links: ["customer>base", "caller>base", "base>window"],
      status: { ...LINES_UP, mcp: "Finished" }, settled: ["mcp"],
    },
    {
      t: 16, phase: "live", danger: 0.16, tier: 0,
      marker: "Unknown caller from far away", detail: "Unfamiliar region, not on a verified list",
      links: ["customer>base", "caller>base", "window>jev"],
      status: { ...LINES_UP, window: "Sent a small block", jev: "Rating: low" },
    },
    {
      t: 38, phase: "live", danger: 0.22, tier: 0,
      marker: "Long friendly opening", detail: "Nothing has been requested",
      links: ["customer>base", "caller>base", "window>jev"],
      status: { ...LINES_UP, window: "Sent a small block", jev: "Rating: low" },
    },
    {
      t: 63, phase: "live", danger: 0.33, tier: 1,
      marker: "Asked to keep the contact private", detail: "Tier raised, nothing sent yet",
      flag: "asks_secrecy",
      links: ["window>jev", "jev>alerting"],
      status: { ...LINES_UP, window: "Sent a small block", jev: "Rating: suspicious", alerting: "Holding, too early to warn" },
      settled: ["alerting"],
    },
    {
      t: 91, phase: "live", danger: 0.38, tier: 1,
      marker: "Pushed to keep talking elsewhere", detail: "Jev stayed at suspicious",
      links: ["customer>base", "caller>base", "window>jev"],
      status: { ...LINES_UP, window: "Sent a small block", jev: "Rating: suspicious" },
    },
    {
      t: 114, phase: "checking", danger: 0.38, tier: 1,
      marker: "Call ended", detail: "Checking agent started on the whole window",
      links: ["window>check", "lessons>check"],
      status: { ...LINES_ENDED, check: "Rereading the call", lessons: "Applied", alerting: "Standing by" },
      settled: [...LINES_ENDED_SETTLED, "alerting"],
    },
    {
      t: 126, phase: "checking", danger: 0.57, tier: 2,
      marker: "Sandbox lessons matched this pattern", detail: "Checking agent raised the tier after the call",
      links: ["window>check", "lessons>check"],
      status: { check: "Flagged: high", lessons: "Pattern matched", window: "Sent to Checking agent" },
    },
    {
      t: 136, phase: "responding", danger: 0.57, tier: 2,
      marker: "Notice sent after the call", detail: "T-Life notice from the Alerting agent",
      links: ["check>alerting", "alerting>tlife"],
      status: { check: "Flagged", alerting: "Sending notice", tlife: "Notice delivered" },
      settled: ["check"],
      notice: {
        channel: "t-life", timing: "after-call",
        title: "About your last call",
        body: "It looked like the start of a friendship scam. Take care before sharing anything.",
      },
    },
    {
      t: 148, phase: "deleted", danger: 0.57, tier: 2,
      marker: "Call data deleted", detail: "Window and markers erased",
      links: ["window>purge"],
      status: { window: "Erased", purge: "Complete", alerting: "Finished", lessons: "Finished", tlife: "Delivered" },
      settled: ["window", "purge", "alerting", "lessons", "tlife"],
    },
  ],
};

const ID_DISCLOSED: Scenario = {
  id: "id-disclosed",
  name: "Customer shared a government ID number",
  duration: 144,
  beats: [
    ...connectingBeats(),
    {
      t: 5, phase: "live", danger: 0.08, tier: 0,
      marker: "Call connected", detail: "Both lines streaming to the Base agent",
      links: ["customer>base", "caller>base", "base>window"],
      status: { ...LINES_UP, mcp: "Finished" }, settled: ["mcp"],
    },
    {
      t: 21, phase: "live", danger: 0.12, tier: 0,
      marker: "Ordinary sounding conversation", detail: "Jev rated the first window",
      links: ["customer>base", "caller>base", "window>jev"],
      status: { ...LINES_UP, window: "Sent a small block", jev: "Rating: low" },
    },
    {
      t: 47, phase: "live", danger: 0.17, tier: 0,
      marker: "No pressure from the caller", detail: "No red flags raised live",
      links: ["customer>base", "caller>base", "window>jev"],
      status: { ...LINES_UP, window: "Sent a small block", jev: "Rating: low" },
    },
    {
      t: 74, phase: "live", danger: 0.21, tier: 0,
      marker: "Caller stayed polite and calm", detail: "Jev stayed at low",
      links: ["customer>base", "caller>base", "window>jev"],
      status: { ...LINES_UP, window: "Sent a small block", jev: "Rating: low" },
    },
    {
      t: 96, phase: "checking", danger: 0.21, tier: 0,
      marker: "Call ended", detail: "Checking agent started on the whole window",
      links: ["window>check", "lessons>check"],
      status: { ...LINES_ENDED, check: "Rereading the call", lessons: "Applied" },
      settled: LINES_ENDED_SETTLED,
    },
    {
      t: 108, phase: "checking", danger: 0.9, tier: 3,
      marker: "Government ID number given to the caller", detail: "Found on the reread. Only the type of number is kept, never the digits",
      links: ["window>check", "lessons>check"],
      status: { check: "Flagged: severe", lessons: "Pattern matched", window: "Sent to Checking agent" },
    },
    {
      t: 116, phase: "responding", danger: 0.9, tier: 3,
      marker: "Urgent callback placed", detail: "Alerting agent phones the customer, not emergency services",
      links: ["check>alerting", "alerting>callback"],
      status: { check: "Flagged", alerting: "Placing callback", callback: "Calling the customer" },
      settled: ["check"],
      notice: {
        channel: "urgent-callback", timing: "after-call",
        title: "We need to check something with you",
        body: "Sensitive details may have been shared on your last call.",
      },
    },
    {
      t: 126, phase: "responding", danger: 0.9, tier: 3,
      marker: "Callback reached the customer", detail: "Customer decides what to do next",
      links: ["alerting>callback"],
      status: { alerting: "Standing by", callback: "Customer reached" },
      settled: ["alerting", "callback"],
    },
    {
      t: 135, phase: "deleted", danger: 0.9, tier: 3,
      marker: "Call data deleted", detail: "Window and markers erased",
      links: ["window>purge"],
      status: { window: "Erased", purge: "Complete", alerting: "Finished", lessons: "Finished", callback: "Finished" },
      settled: ["window", "purge", "alerting", "lessons", "callback"],
    },
  ],
};

export const SCENARIOS: Scenario[] = [FAKE_BANK_SCENARIO, ORDINARY_CALL, FRIENDLY_STRANGER, ID_DISCLOSED];

export type LiveMoment = "warning" | "urgent" | "summary" | "callback";

/** What a real call sends to T-Life. Written in advance, so the public /tlife-api route still carries no free text. */
export const LIVE_NOTICES: Record<LiveMoment, CustomerNotice> = {
  warning: {
    channel: "t-life", timing: "during-call",
    title: "Be careful on this call", body: "Don't share codes, card numbers or passwords with this caller.",
  },
  urgent: {
    channel: "t-life", timing: "during-call",
    title: "Stop: this call is a scam", body: "Your bank will never ask for your card number, security code or a one-time code on a call.",
  },
  summary: {
    channel: "t-life", timing: "after-call",
    title: "After your call: what to do now", body: "Here's how to protect your account. We've also texted you the steps.",
  },
  callback: {
    channel: "urgent-callback", timing: "after-call",
    title: "Safe Signal is calling you", body: "We'll offer to connect you to your bank's verified number.",
  },
};

/**
 * The real-call notices as beats, so T-Life looks them up like any test call's. Never played, never offered as a
 * test call or an ambient call: only the T-Life route and live calls read it. Tier sets the loudness (tlife.ts).
 */
export const LIVE_CARD_FRAUD: Scenario = {
  id: "live-card-fraud",
  name: "Real call: card fraud",
  duration: 10,
  beats: (["warning", "urgent", "summary", "callback"] as const).map((moment, i) => ({
    t: i + 1,
    phase: moment === "warning" || moment === "urgent" ? "live" : "responding",
    danger: moment === "warning" ? 0.6 : 0.9,
    tier: moment === "warning" ? 2 : 3,
    marker: LIVE_NOTICES[moment].title, detail: "Sent to T-Life during a real call",
    links: [], status: {},
    notice: LIVE_NOTICES[moment],
  })),
};

/** The beat of LIVE_CARD_FRAUD that carries this moment's notice. */
export const liveNoticeBeat = (moment: LiveMoment) => LIVE_CARD_FRAUD.beats.find((beat) => beat.notice === LIVE_NOTICES[moment])!;

/** Every scenario T-Life may send a notice from. */
export const NOTICE_SCENARIOS: Scenario[] = [...SCENARIOS, LIVE_CARD_FRAUD];

/** No call open: every node waiting, nothing lit. Never offered as a test call. */
export const IDLE_SCENARIO: Scenario = {
  id: "idle",
  name: "No call open",
  duration: 1,
  beats: [{ t: 0, phase: "connecting", danger: 0, tier: 0, marker: "No call open", detail: "", links: [], status: {} }],
};
