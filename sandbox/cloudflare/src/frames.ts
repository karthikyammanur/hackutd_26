// Cuts a call into microframes: one per caller turn or in-call phone signal, each seeing only the past.

export const WINDOW_TURNS = 6;
export const HARD_NEGATIVE_TYPES = new Set(["benign_real_bank_alert", "benign_real_carrier_care"]);

export interface RawEvent {
  t: number;
  kind: string;
  who?: string;
  text?: string;
  sender?: string;
  amount?: number;
  newPayee?: boolean;
  action?: string;
}

export interface Session {
  session_id: string;
  scam: boolean;
  scam_type: string;
  money_moment_t: number | null;
  direction: string;
  events: RawEvent[];
}

export interface Frame {
  index: number;
  t: number;
  trigger: string;
  window: string[];
  signals: string[];
  latest: string;
  scrolledOut: string[]; // turns that left the verbatim window since the previous frame
}

function signalLine(e: RawEvent): string | null {
  if (e.kind === "sms_otp") return `[${e.t}s] A one-time code text arrived from ${e.sender ?? "a sender"}`;
  if (e.kind === "bank_app_open") return `[${e.t}s] The customer opened their banking app`;
  if (e.kind === "bank_transfer") {
    return `[${e.t}s] A bank transfer of $${e.amount ?? "?"} started to ${e.newPayee ? "a new payee" : "an existing payee"}`;
  }
  if (e.kind === "account") return `[${e.t}s] Phone account event: ${e.action ?? "unknown"}`;
  return null;
}

export function buildFrames(events: RawEvent[]): Frame[] {
  const turns: string[] = [];
  const signals: string[] = [];
  const frames: Frame[] = [];
  let noted = 0;

  const emit = (t: number, trigger: string, latest: string) => {
    const older = turns.slice(0, Math.max(0, turns.length - WINDOW_TURNS));
    frames.push({
      index: frames.length,
      t,
      trigger,
      window: turns.slice(-WINDOW_TURNS),
      signals: [...signals],
      latest,
      scrolledOut: older.slice(noted),
    });
    noted = older.length;
  };

  for (const event of [...events].sort((a, b) => a.t - b.t)) {
    if (event.kind === "turn") {
      const line = `${(event.who ?? "unknown").toUpperCase()}: ${event.text ?? ""}`;
      turns.push(line);
      if (event.who === "caller") emit(event.t, "turn", line);
    } else {
      const line = signalLine(event);
      if (line) {
        signals.push(line);
        emit(event.t, event.kind, line);
      }
    }
  }
  return frames;
}

export function composeState(session: Session, frame: Frame, note: string): string {
  const parts = [`PHONE CALL IN PROGRESS. Direction: ${session.direction}. Elapsed: ${frame.t} seconds.`];
  if (note) parts.push(`NOTES ON THE EARLIER PART OF THE CALL:\n${note}`);
  if (frame.signals.length) {
    parts.push(`EVENTS ON THE CUSTOMER'S PHONE DURING THIS CALL:\n${frame.signals.join("\n")}`);
  }
  if (frame.window.length) parts.push(`MOST RECENT CONVERSATION:\n${frame.window.join("\n")}`);
  return parts.join("\n\n");
}
