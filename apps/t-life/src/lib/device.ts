import { useSyncExternalStore } from "react";
import { openWire, receiveWire } from "./delivery";
import type { NoticeLevel, WireNotice } from "./notices";

/** What this device can do: install state, notification permission and the live connection. */

export type PushState = "unsupported" | "off" | "denied" | "on";

interface InstallPromptEvent extends Event {
  prompt(): Promise<void>;
}

interface DeviceState {
  push: PushState;
  standalone: boolean;
  canInstall: boolean;
  live: boolean;
}

const POLL_MS = 4000;
/** The live stream carries notices, so polling only has to catch what it missed. */
const POLL_WITH_STREAM_MS = 20000;
const RELAY_URL = "https://ntfy.sh";
/** A signed notice older than this is ignored, so an old one can't be replayed as new. */
const STREAM_MAX_AGE_MS = 2 * 60 * 1000;
/** About once a minute while on screen, so a phone can't silently fall off the server's list. */
const RESYNC_EVERY_POLLS = 15;

let state: DeviceState = {
  push: "off",
  standalone: window.matchMedia("(display-mode: standalone)").matches,
  canInstall: false,
  live: false,
};
let installEvent: InstallPromptEvent | null = null;
let registration: ServiceWorkerRegistration | null = null;
let streamOpen = false;
const listeners = new Set<() => void>();

function update(change: Partial<DeviceState>) {
  state = { ...state, ...change };
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useDevice(): DeviceState {
  return useSyncExternalStore(subscribe, () => state);
}

// These fire once and early, so they are attached when the module loads.
window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  installEvent = event as InstallPromptEvent;
  update({ canInstall: true });
});
window.addEventListener("appinstalled", () => {
  installEvent = null;
  update({ canInstall: false, standalone: true });
});

export async function promptInstall(): Promise<void> {
  await installEvent?.prompt();
  installEvent = null;
  update({ canInstall: false });
}

function pushSupported(): boolean {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

function base64UrlToBytes(value: string): Uint8Array<ArrayBuffer> {
  const binary = atob(value.replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

const post = (path: string, body: object) =>
  fetch(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

async function saveSubscription(subscription: PushSubscription): Promise<void> {
  const { endpoint, keys } = subscription.toJSON();
  const response = await post("/api/subscribe", { endpoint, p256dh: keys?.p256dh, auth: keys?.auth });
  if (!response.ok) throw new Error(`The notification service refused this device (${response.status})`);
}

/** Asks for permission and registers this device. Must run from a tap. */
export async function enableNotifications(): Promise<void> {
  if (!pushSupported() || !registration) {
    update({ push: "unsupported" });
    return;
  }
  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    update({ push: permission === "denied" ? "denied" : "off" });
    return;
  }
  const { publicKey } = (await (await fetch("/api/vapid")).json()) as { publicKey: string };
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: base64UrlToBytes(publicKey),
  });
  await saveSubscription(subscription);
  update({ push: "on" });
}

export async function disableNotifications(): Promise<void> {
  const subscription = await registration?.pushManager.getSubscription();
  if (subscription) {
    await post("/api/unsubscribe", { endpoint: subscription.endpoint });
    await subscription.unsubscribe();
  }
  update({ push: "off" });
}

/** Asks the server to send one sample to this phone in five seconds. */
export async function sendSampleToPhone(level: NoticeLevel): Promise<boolean> {
  const subscription = await registration?.pushManager.getSubscription();
  if (!subscription) return false;
  const response = await post("/api/self-test", { endpoint: subscription.endpoint, level });
  return response.ok;
}

async function resyncSubscription() {
  const subscription = await registration?.pushManager.getSubscription();
  if (subscription && Notification.permission === "granted") await saveSubscription(subscription).catch(() => undefined);
}

/** While the app is on screen, checks for new notices. Push brings them when it isn't. */
function pollLive(): () => void {
  let since = 0;
  let timer = 0;
  let firstPoll = true;
  let stopped = false;
  let polls = 0;

  async function poll() {
    if (stopped) return;
    if (document.visibilityState === "visible") {
      try {
        const response = await fetch(`/api/recent?since=${since}`, { cache: "no-store" });
        if (!response.ok) throw new Error(String(response.status));
        const { notices } = (await response.json()) as { notices: WireNotice[] };
        notices.forEach((notice) => {
          receiveWire(notice, { backlog: firstPoll });
          since = Math.max(since, notice.at);
        });
        firstPoll = false;
        update({ live: true });
        polls += 1;
        if (polls % RESYNC_EVERY_POLLS === 0) void resyncSubscription();
      } catch {
        update({ live: false });
      }
    }
    timer = window.setTimeout(() => void poll(), streamOpen ? POLL_WITH_STREAM_MS : POLL_MS);
  }

  const onVisible = () => {
    if (document.visibilityState === "visible") void resyncSubscription();
  };
  document.addEventListener("visibilitychange", onVisible);

  void poll();
  return () => {
    stopped = true;
    document.removeEventListener("visibilitychange", onVisible);
    window.clearTimeout(timer);
  };
}

/** Opens the live stream. Every message must carry the server's signature to be shown. */
function connectStream(): () => void {
  let source: EventSource | null = null;
  let stopped = false;

  async function open() {
    const response = await fetch("/api/realtime", { cache: "no-store" });
    if (!response.ok) throw new Error(String(response.status));
    const { topic, publicKey } = (await response.json()) as { topic: string; publicKey: string };
    const key = await crypto.subtle.importKey("raw", base64UrlToBytes(publicKey), { name: "ECDSA", namedCurve: "P-256" }, false, ["verify"]);
    if (stopped) return;

    source = new EventSource(`${RELAY_URL}/${topic}/sse`);
    source.onopen = () => {
      streamOpen = true;
      update({ live: true });
    };
    source.onerror = () => {
      streamOpen = false;
    };
    source.onmessage = (event: MessageEvent<string>) => void accept(event.data, key);
  }

  async function accept(data: string, key: CryptoKey) {
    try {
      const { n, s } = JSON.parse((JSON.parse(data) as { message: string }).message) as { n: string; s: string };
      const valid = await crypto.subtle.verify({ name: "ECDSA", hash: "SHA-256" }, key, base64UrlToBytes(s), new TextEncoder().encode(n));
      if (!valid) return;
      const wire = JSON.parse(n) as WireNotice;
      if (Date.now() - wire.at <= STREAM_MAX_AGE_MS) receiveWire(wire);
    } catch {
      // Anything that isn't a well-formed signed notice is dropped.
    }
  }

  // A browser that gave up on the stream gets a new one when the app returns to the screen.
  const onVisible = () => {
    if (document.visibilityState === "visible" && source?.readyState === EventSource.CLOSED) void open().catch(() => undefined);
  };
  document.addEventListener("visibilitychange", onVisible);
  void open().catch(() => undefined);

  return () => {
    stopped = true;
    streamOpen = false;
    document.removeEventListener("visibilitychange", onVisible);
    source?.close();
  };
}

function onWorkerMessage(event: MessageEvent<{ type: "notice" | "open"; notice: WireNotice }>) {
  if (event.data.type === "notice") receiveWire(event.data.notice);
  if (event.data.type === "open") openWire(event.data.notice);
}

/** A cold start from a tapped notification carries the notice in the URL. */
function readLaunchNotice() {
  const params = new URLSearchParams(location.search);
  const raw = params.get("notice");
  if (!raw) return;
  history.replaceState(null, "", "/");
  try {
    openWire(JSON.parse(raw) as WireNotice);
  } catch {
    // A malformed link just opens the app normally.
  }
}

async function registerWorker() {
  if (!pushSupported()) {
    update({ push: "unsupported" });
    return;
  }
  registration = await navigator.serviceWorker.register("/sw.js");
  const subscription = await registration.pushManager.getSubscription();
  if (Notification.permission === "denied") {
    update({ push: "denied" });
  } else if (subscription && Notification.permission === "granted") {
    update({ push: "on" });
    // Keeps the server's list right if it was cleared or this device's keys rotated.
    await saveSubscription(subscription).catch(() => undefined);
  }
}

/** Starts every incoming route. Call after the app is listening for notices. */
export function startDevice(): () => void {
  void registerWorker();
  navigator.serviceWorker?.addEventListener("message", onWorkerMessage);
  const stopLive = pollLive();
  const stopStream = connectStream();
  readLaunchNotice();
  return () => {
    navigator.serviceWorker?.removeEventListener("message", onWorkerMessage);
    stopLive();
    stopStream();
  };
}
