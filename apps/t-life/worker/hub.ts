import { DEMO_SEQUENCE, type NoticeDelivery, type NoticeLevel, type WireNotice } from "../src/lib/notices";
import { relayMessage, type RealtimeEnv, type RelayMessage } from "./realtime";
import { sendPush, type PushSubscriptionRecord, type VapidKeys } from "./webpush";

export interface HubEnv extends RealtimeEnv {
  STORE: KVNamespace;
  VAPID_PUBLIC_KEY: string;
  VAPID_PRIVATE_JWK: string;
  VAPID_SUBJECT: string;
}

export interface DeliverResult {
  /** Phones whose push service accepted the notice. */
  phones: number;
  limited: boolean;
  /** Signed copy for the caller to post to the live stream. */
  relay?: RelayMessage;
}

interface StoredNotice {
  kind: "room" | "self";
  wire: WireNotice;
}

const SUBSCRIPTIONS_KEY = "subscriptions";
const NOTICES_KEY = "notices";
const MAX_SUBSCRIPTIONS = 100;
const MAX_STORED = 40;
const MAX_RECENT = 12;
const RECENT_LIFETIME_S = 20 * 60;
const PUSH_TTL_S = 300;
const RATE_WINDOW_MS = 60 * 1000;
const MAX_PER_WINDOW = 40;
const SELF_TEST_DELAY_MS = 5000;
// The shortest edge cache KV allows, so a phone that just signed up is seen quickly.
const READ_FRESHEST = { type: "json", cacheTtl: 30 } as const;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** The one shared demo room: opted-in devices and a short-lived list of recent notices. */
export class NoticeHub {
  constructor(private readonly env: HubEnv) {}

  private get vapid(): VapidKeys {
    return { publicKey: this.env.VAPID_PUBLIC_KEY, privateJwk: this.env.VAPID_PRIVATE_JWK, subject: this.env.VAPID_SUBJECT };
  }

  private async subscriptions(): Promise<PushSubscriptionRecord[]> {
    return (await this.env.STORE.get<PushSubscriptionRecord[]>(SUBSCRIPTIONS_KEY, READ_FRESHEST)) ?? [];
  }

  private saveSubscriptions(list: PushSubscriptionRecord[]) {
    return this.env.STORE.put(SUBSCRIPTIONS_KEY, JSON.stringify(list));
  }

  private async notices(): Promise<StoredNotice[]> {
    const stored = (await this.env.STORE.get<StoredNotice[]>(NOTICES_KEY, READ_FRESHEST)) ?? [];
    const oldest = Date.now() - RECENT_LIFETIME_S * 1000;
    return stored.filter((item) => item.wire.at >= oldest);
  }

  async recent(since: number): Promise<WireNotice[]> {
    return (await this.notices())
      .filter((item) => item.kind === "room" && item.wire.at > since)
      .map((item) => item.wire)
      .slice(-MAX_RECENT);
  }

  /** Records a notice unless the room has hit its rate limit. */
  private async record(wire: WireNotice, kind: StoredNotice["kind"]): Promise<boolean> {
    const stored = await this.notices();
    const windowStart = Date.now() - RATE_WINDOW_MS;
    if (stored.filter((item) => item.wire.at > windowStart).length >= MAX_PER_WINDOW) return false;
    const next = [...stored, { kind, wire }].slice(-MAX_STORED);
    await this.env.STORE.put(NOTICES_KEY, JSON.stringify(next), { expirationTtl: RECENT_LIFETIME_S });
    return true;
  }

  async subscribe(subscription: PushSubscriptionRecord): Promise<boolean> {
    const list = await this.subscriptions();
    const known = list.find((item) => item.endpoint === subscription.endpoint);
    // The app re-registers on every launch. KV has a low daily write allowance, so skip no-ops.
    if (known?.p256dh === subscription.p256dh && known.auth === subscription.auth) return true;
    if (!known && list.length >= MAX_SUBSCRIPTIONS) return false;
    await this.saveSubscriptions([...list.filter((item) => item.endpoint !== subscription.endpoint), subscription]);
    return true;
  }

  async unsubscribe(endpoints: string[]): Promise<void> {
    const list = await this.subscriptions();
    const kept = list.filter((item) => !endpoints.includes(item.endpoint));
    if (kept.length !== list.length) await this.saveSubscriptions(kept);
  }

  async status(): Promise<{ phones: number }> {
    return { phones: (await this.subscriptions()).length };
  }

  /** Pushes to one device. Reports whether it was accepted and whether the subscription is dead. */
  private async pushTo(subscription: PushSubscriptionRecord, notice: WireNotice): Promise<{ ok: boolean; gone: boolean }> {
    try {
      const status = await sendPush(subscription, notice, this.vapid, PUSH_TTL_S);
      return { ok: status >= 200 && status < 300, gone: status === 404 || status === 410 };
    } catch {
      return { ok: false, gone: false };
    }
  }

  private wire(delivery: NoticeDelivery): WireNotice {
    return { id: crypto.randomUUID(), level: delivery.level, notice: delivery.notice, at: Date.now() };
  }

  /** Called through the private service binding from the console's Worker. */
  async deliver(delivery: NoticeDelivery): Promise<DeliverResult> {
    const notice = this.wire(delivery);
    if (!(await this.record(notice, "room"))) return { phones: 0, limited: true };
    const list = await this.subscriptions();
    const [results, relay] = await Promise.all([
      Promise.all(list.map((subscription) => this.pushTo(subscription, notice))),
      relayMessage(this.env, notice),
    ]);
    const gone = list.filter((_, index) => results[index].gone).map((item) => item.endpoint);
    if (gone.length > 0) await this.unsubscribe(gone);
    return { phones: results.filter((result) => result.ok).length, limited: false, relay };
  }

  /** Sends one fixed sample to the device that asked, after a pause so it can leave the app. */
  async selfTest(endpoint: string, level: NoticeLevel): Promise<void> {
    const subscription = (await this.subscriptions()).find((item) => item.endpoint === endpoint);
    const sample = DEMO_SEQUENCE.find((item) => item.level === level);
    if (!subscription || !sample) return;
    const notice = this.wire(sample);
    if (!(await this.record(notice, "self"))) return;
    await sleep(SELF_TEST_DELAY_MS);
    await this.pushTo(subscription, notice);
  }
}
