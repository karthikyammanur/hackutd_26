/** Same shape as CustomerNotice in apps/web/src/lib/console/call-model.ts. */
export interface CustomerNotice {
  channel: "t-life" | "urgent-callback";
  timing: "during-call" | "after-call";
  title: string;
  body: string;
}

/** How loudly a notice is shown. A real feed would set this from the alert level. */
export type NoticeLevel = "quiet" | "warning" | "urgent" | "summary" | "callback";

export interface NoticeDelivery {
  level: NoticeLevel;
  notice: CustomerNotice;
}

export interface DeliveredNotice extends NoticeDelivery {
  id: string;
  receivedAt: number;
  /** Goes to the inbox without a banner or a takeover. */
  muted?: boolean;
}

/** A notice as it travels from the server to this device. */
export interface WireNotice extends NoticeDelivery {
  id: string;
  at: number;
}

export const URGENT_ACTIONS = ["Call my bank", "Ask my trusted contact", "Continue"] as const;
export type UrgentAction = (typeof URGENT_ACTIONS)[number];

export const DEMO_CALLER = "(214) 555-0142";
export const DEMO_CALLBACK_NUMBER = "(800) 555-0199";
export const DEMO_MEMBER_NUMBER = "(214) 555-0101";

/** The first four lines match the fake bank call in the console scenario. */
export const DEMO_SEQUENCE: readonly NoticeDelivery[] = [
  {
    level: "quiet",
    notice: {
      channel: "t-life",
      timing: "during-call",
      title: "Be careful on this call",
      body: "This caller isn't on our verified list.",
    },
  },
  {
    level: "warning",
    notice: {
      channel: "t-life",
      timing: "during-call",
      title: "A code just arrived",
      body: "Don't share it with anyone on this call.",
    },
  },
  {
    level: "urgent",
    notice: {
      channel: "t-life",
      timing: "during-call",
      title: "This call may be a scam",
      body: "The caller is asking for a code your bank sent.",
    },
  },
  {
    level: "summary",
    notice: {
      channel: "t-life",
      timing: "after-call",
      title: "We checked your last call",
      body: "It showed signs of a scam. Here's what to do next.",
    },
  },
  {
    level: "callback",
    notice: {
      channel: "urgent-callback",
      timing: "after-call",
      title: "Urgent callback from T-Mobile",
      body: "We're calling about your last call. We won't ask for any code or password.",
    },
  },
];

export const LEVEL_LABELS: Record<NoticeLevel, string> = {
  quiet: "Quiet card",
  warning: "Warning",
  urgent: "Urgent screen",
  summary: "After-call summary",
  callback: "Urgent callback",
};

export const SUMMARY_NEXT_STEPS = [
  "Call your bank using the number on your card.",
  "Change any password or code you shared on the call.",
  "Answer our callback if you'd like help with the next steps.",
] as const;
