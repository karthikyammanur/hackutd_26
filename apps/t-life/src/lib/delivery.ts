import type { DeliveredNotice, NoticeDelivery, WireNotice } from "./notices";

type NoticeListener = (notice: DeliveredNotice) => void;
type OpenListener = (notice: DeliveredNotice) => void;

/** An interrupting notice older than this goes to the inbox instead of taking over the screen. */
const STILL_URGENT_MS = 90 * 1000;

const listeners = new Set<NoticeListener>();
const openListeners = new Set<OpenListener>();
const seen = new Set<string>();
let nextId = 0;

/** The one way a notice reaches the app, whether from the demo control or the live feed. */
export function deliverNotice(delivery: NoticeDelivery): void {
  const delivered: DeliveredNotice = { ...delivery, id: `local-${Date.now()}-${(nextId += 1)}`, receivedAt: Date.now() };
  seen.add(delivered.id);
  listeners.forEach((listener) => listener(delivered));
}

function fromWire(wire: WireNotice, muted: boolean): DeliveredNotice {
  return { level: wire.level, notice: wire.notice, id: wire.id, receivedAt: wire.at, muted: muted || undefined };
}

/** Takes a notice from the live feed. The same notice can arrive by socket and by push. */
export function receiveWire(wire: WireNotice, { backlog = false } = {}): void {
  if (seen.has(wire.id)) return;
  seen.add(wire.id);
  const stale = Date.now() - wire.at > STILL_URGENT_MS;
  const delivered = fromWire(wire, backlog && (stale || (wire.level !== "urgent" && wire.level !== "callback")));
  listeners.forEach((listener) => listener(delivered));
}

/** The customer tapped a system notification. */
export function openWire(wire: WireNotice): void {
  receiveWire(wire);
  const delivered = fromWire(wire, false);
  openListeners.forEach((listener) => listener(delivered));
}

export function rememberSeen(ids: string[]): void {
  ids.forEach((id) => seen.add(id));
}

export function subscribeToNotices(listener: NoticeListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function subscribeToOpens(listener: OpenListener): () => void {
  openListeners.add(listener);
  return () => {
    openListeners.delete(listener);
  };
}

export const isStillUrgent = (receivedAt: number, now: number) => now - receivedAt <= STILL_URGENT_MS;
