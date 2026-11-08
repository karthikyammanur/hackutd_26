import { useSyncExternalStore } from "react";
import { traceAt, type Beat, type CallPhase, type Scenario, type Tier } from "@/lib/console/call-model";
import { liveNow, liveScenario, placingScenario, type LiveView } from "@/lib/console/live";
import { SCENARIOS } from "@/lib/console/scenarios";

/**
 * Calls in progress, held in this tab's memory only. Nothing here is written to storage or sent
 * anywhere. A session leaves the roster the moment it reaches "deleted", so the roster can never
 * become a call log. The one call open at that moment stays reviewable until the viewer moves on.
 */

export interface CallSession {
  id: string;
  /** "live" is a real call placed by the Safe Signal API. Its beats come from the API, not a script. */
  kind: "test" | "ambient" | "live";
  /** Live only: the API's session id. */
  remoteId?: string;
  scenario: Scenario;
  /** Where the play head is. */
  t: number;
  /** How far the call has actually reached. Scrubbing back leaves this where it was. */
  furthest: number;
  /** Ambient only: call seconds per real second. */
  rate: number;
}

export interface DeletionReceipt {
  sessionId: string;
  heldSeconds: number;
  sentNotices: boolean;
  scenario: Scenario;
  /** Where the review is scrubbed to. */
  t: number;
  tier: Tier;
}

/** How far one of a test call's notices got on its way to T-Life. */
export type NoticeDelivery =
  | { state: "sending" }
  | { state: "sent"; phones: number }
  | { state: "failed" };

export type TLifeStatus = { phones: number };

/** The link to the Safe Signal API, through the Worker's /live-api proxy. */
export interface LiveLink {
  api: "unknown" | "ready" | "offline";
  placing: boolean;
  /** Why it's offline, or what the last attempt said. */
  note: string | null;
}

export type SearchResult = { ok: true; mask: string } | { ok: false; reason: "incomplete" | "not-found" };

interface SessionsState {
  sessions: CallSession[];
  openId: string | null;
  /** Last two digits, only when the call was opened by number. */
  openMask: string | null;
  receipt: DeletionReceipt | null;
  playing: boolean;
  speed: number;
  deliveries: Record<string, NoticeDelivery>;
  tlife: TLifeStatus | null;
  live: LiveLink;
}

export const DEMO_SPEEDS = [1, 6, 12];

const TICK_MS = 100;
const TLIFE_STATUS_MS = 6000;
const AMBIENT_MIN = 4;
const AMBIENT_MAX = 6;
const AMBIENT_RATE_MIN = 3;
const AMBIENT_RATE_MAX = 7;
const SPAWN_GAP_MIN_MS = 6000;
const SPAWN_GAP_MAX_MS = 14000;
const LIVE_POLL_MS = 1000;
const LIVE_CURRENT_MS = 5000;

/** Fixed synthetic numbers so a presenter can search a test call. 555-01XX is reserved for fiction. */
const TEST_NUMBERS: Record<string, string> = {
  "code-request": "2025550142",
  "ordinary-call": "2025550143",
  "friendly-stranger": "2025550144",
  "id-disclosed": "2025550145",
};

const ID_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ";

let state: SessionsState = {
  sessions: [], openId: null, openMask: null, receipt: null, playing: true, speed: 6, deliveries: {}, tlife: null,
  live: { api: "unknown", placing: false, note: null },
};
const numbers = new Map<string, string>();
/** API session ids already shown, so a finished call is never picked up again. */
const seenRemote = new Set<string>();
const polling = new Set<string>();
let checkingCurrent = false;
let nextLivePollAt = 0;
let nextCurrentAt = 0;
const listeners = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | null = null;
let lastTick = 0;
let nextSpawnAt = 0;
let nextStatusAt = 0;

function publish(next: SessionsState) {
  state = next;
  for (const listener of listeners) listener();
}

function randomBetween(min: number, max: number) {
  return min + Math.random() * (max - min);
}

function pickFrom<T>(items: T[]): T {
  return items[Math.floor(Math.random() * items.length)];
}

function newSessionId(): string {
  const taken = new Set(state.sessions.map((session) => session.id));
  for (;;) {
    const bytes = crypto.getRandomValues(new Uint8Array(4));
    const id = Array.from(bytes, (byte) => ID_ALPHABET[byte % ID_ALPHABET.length]).join("");
    if (!taken.has(id)) return id;
  }
}

function deletionTime(scenario: Scenario): number {
  return scenario.beats.find((beat) => beat.phase === "deleted")?.t ?? scenario.duration;
}

/** Ambient calls are mostly ordinary, as real traffic would be. */
function pickAmbientScenario(): Scenario {
  const ordinary = SCENARIOS.find((scenario) => scenario.id === "ordinary-call");
  return ordinary && Math.random() < 0.5 ? ordinary : pickFrom(SCENARIOS);
}

function newAmbientSession(startPartWay: boolean): CallSession {
  const scenario = pickAmbientScenario();
  const id = newSessionId();
  const lastDigits = String(Math.floor(randomBetween(0, 100))).padStart(2, "0");
  numbers.set(id, `31255501${lastDigits}`);
  const t = startPartWay ? randomBetween(0, deletionTime(scenario) * 0.7) : 0;
  return {
    id,
    kind: "ambient",
    scenario,
    t,
    furthest: t,
    rate: randomBetween(AMBIENT_RATE_MIN, AMBIENT_RATE_MAX),
  };
}

function scheduleSpawn(now: number) {
  nextSpawnAt = now + randomBetween(SPAWN_GAP_MIN_MS, SPAWN_GAP_MAX_MS);
}

function buildReceipt(session: CallSession): DeletionReceipt {
  const deletedAt = deletionTime(session.scenario);
  const final = traceAt(session.scenario, deletedAt);
  return {
    sessionId: session.id,
    heldSeconds: deletedAt,
    sentNotices: final.notices.length > 0,
    scenario: session.scenario,
    t: deletedAt,
    tier: final.tier,
  };
}

export const deliveryKey = (sessionId: string, beatT: number) => `${sessionId}:${beatT}`;

function setDelivery(key: string, delivery: NoticeDelivery) {
  publish({ ...state, deliveries: { ...state.deliveries, [key]: delivery } });
}

/** Sends the id of a scripted notice. The Worker looks up the text itself. */
function sendToTLife(key: string, scenarioId: string, beatT: number) {
  fetch("/tlife-api/notices", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ scenarioId, beatT }),
  })
    .then(async (response) => {
      if (!response.ok) throw new Error(String(response.status));
      const { phones, relay } = (await response.json()) as TLifeStatus & { relay?: { url: string; body: string } };
      setDelivery(key, { state: "sent", phones });
      // Posted from here because the relay rate-limits Cloudflare's shared addresses. Already signed.
      if (relay) void fetch(relay.url, { method: "POST", body: relay.body }).catch(() => undefined);
    })
    .catch(() => setDelivery(key, { state: "failed" }));
}

function refreshTLifeStatus() {
  fetch("/tlife-api/status")
    .then((response) => (response.ok ? (response.json() as Promise<TLifeStatus>) : null))
    .then((tlife) => publish({ ...state, tlife }))
    .catch(() => publish({ ...state, tlife: null }));
}

function tick() {
  const now = performance.now();
  const elapsed = (now - lastTick) / 1000;
  lastTick = now;

  let { openId, openMask, receipt } = state;
  let { deliveries } = state;
  const outgoing: { key: string; scenarioId: string; beatT: number }[] = [];
  const sessions: CallSession[] = [];
  for (const session of state.sessions) {
    const rate = session.kind === "test" ? (state.playing ? state.speed : 0) : session.kind === "live" ? 0 : session.rate;
    const t = session.t + elapsed * rate;
    if (session.kind === "test") {
      for (const beat of session.scenario.beats) {
        const key = deliveryKey(session.id, beat.t);
        // Only beats the call plays through, and only once, even if the presenter scrubs back.
        if (beat.notice && beat.t > session.t && beat.t <= t && !deliveries[key]) {
          deliveries = { ...deliveries, [key]: { state: "sending" } };
          outgoing.push({ key, scenarioId: session.scenario.id, beatT: beat.t });
        }
      }
    }
    if (t >= deletionTime(session.scenario)) {
      numbers.delete(session.id);
      if (session.id === openId) {
        receipt = buildReceipt(session);
        openId = null;
        openMask = null;
      }
      continue;
    }
    sessions.push(rate === 0 ? session : { ...session, t, furthest: Math.max(session.furthest, t) });
  }

  const ambientCount = sessions.filter((session) => session.kind === "ambient").length;
  if (ambientCount < AMBIENT_MAX && (ambientCount < AMBIENT_MIN || now >= nextSpawnAt)) {
    sessions.push(newAmbientSession(false));
    scheduleSpawn(now);
  }

  publish({ ...state, sessions, openId, openMask, receipt, deliveries });
  for (const { key, scenarioId, beatT } of outgoing) sendToTLife(key, scenarioId, beatT);

  if (now >= nextStatusAt && document.visibilityState === "visible") {
    nextStatusAt = now + TLIFE_STATUS_MS;
    refreshTLifeStatus();
  }

  if (now >= nextLivePollAt) {
    nextLivePollAt = now + LIVE_POLL_MS;
    for (const session of state.sessions) if (session.kind === "live") pollLive(session);
  }
  if (now >= nextCurrentAt && document.visibilityState === "visible" && !state.sessions.some((s) => s.kind === "live")) {
    nextCurrentAt = now + LIVE_CURRENT_MS;
    checkCurrent();
  }
}

// ---- real calls, through the Worker's /live-api proxy to the Safe Signal API --------------------------------

function setLive(change: Partial<LiveLink>) {
  publish({ ...state, live: { ...state.live, ...change } });
}

async function errorText(response: Response): Promise<string> {
  const body = (await response.json().catch(() => ({}))) as { error?: string; detail?: unknown };
  if (response.status === 401) return "The console's token doesn't match the API's";
  return body.error ?? (typeof body.detail === "string" ? body.detail : `The live API answered ${response.status}`);
}

/** Adds the API's call to the roster. Opens it when asked, or when nothing else is open. */
function addLiveSession(remoteId: string, open: boolean) {
  if (seenRemote.has(remoteId)) return;
  seenRemote.add(remoteId);
  const id = newSessionId();
  const session: CallSession = { id, kind: "live", remoteId, scenario: placingScenario(remoteId), t: 0, furthest: 0, rate: 0 };
  const takeView = open || (state.openId === null && state.receipt === null);
  publish({
    ...state,
    sessions: [session, ...state.sessions],
    ...(takeView ? { openId: id, openMask: null, receipt: null } : {}),
    live: { api: "ready", placing: false, note: null },
  });
  pollLive(session);
}

function pollLive(session: CallSession) {
  const remoteId = session.remoteId;
  if (!remoteId || polling.has(remoteId)) return;
  polling.add(remoteId);
  fetch(`/live-api/sessions/${encodeURIComponent(remoteId)}/view`, { cache: "no-store" })
    .then(async (response) => {
      if (response.status === 404) {
        // The API restarted and forgot the call. Nothing left to show.
        publish({
          ...state,
          sessions: state.sessions.filter((s) => s.id !== session.id),
          openId: state.openId === session.id ? null : state.openId,
          live: { ...state.live, note: "The API no longer has that call" },
        });
        return;
      }
      if (!response.ok) throw new Error(await errorText(response));
      const view = (await response.json()) as LiveView;
      const scenario = liveScenario(view);
      const t = liveNow(view, scenario);
      updateSession(session.id, (current) => ({ ...current, scenario, t, furthest: Math.max(current.furthest, t) }));
      if (state.live.api !== "ready") setLive({ api: "ready", note: null });
    })
    .catch((error: unknown) => setLive({ api: "offline", note: error instanceof Error ? error.message : "Lost the live API" }))
    .finally(() => polling.delete(remoteId));
}

/** Finds a real call started elsewhere (another console, or spikes/live_bridge.py). Also tells if the API is up. */
function checkCurrent(open = false) {
  if (checkingCurrent) return;
  checkingCurrent = true;
  fetch("/live-api/calls/current", { cache: "no-store" })
    .then(async (response) => {
      if (!response.ok) return setLive({ api: "offline", note: await errorText(response) });
      const { session_id } = (await response.json()) as { session_id: string | null };
      if (state.live.api !== "ready") setLive({ api: "ready", note: null });
      if (session_id) addLiveSession(session_id, open);
    })
    .catch(() => setLive({ api: "offline", note: "Couldn't reach the console's server" }))
    .finally(() => {
      checkingCurrent = false;
    });
}

/** Asks the API to ring the demo phone from the ElevenLabs scammer line. The API picks the number (rule R10). */
function placeLiveCall() {
  if (state.live.placing) return;
  setLive({ placing: true, note: null });
  fetch("/live-api/calls/start", { method: "POST" })
    .then(async (response) => {
      if (response.status === 409) {
        setLive({ placing: false, note: "A real call is already running. Opening it." });
        return checkCurrent(true);
      }
      if (!response.ok) throw new Error(await errorText(response));
      const { session_id } = (await response.json()) as { session_id: string };
      addLiveSession(session_id, true);
    })
    .catch((error: unknown) => setLive({ placing: false, note: error instanceof Error ? error.message : "Couldn't place the call" }));
}

/** Leaving the Live window counts as moving on, so the review goes with it. */
function dropReviewOnLeave() {
  const onLive = window.location.hash === "" || window.location.hash === "#live";
  if (!onLive && state.receipt) publish({ ...state, receipt: null });
}

function subscribe(listener: () => void) {
  if (listeners.size === 0) {
    window.addEventListener("hashchange", dropReviewOnLeave);
    const now = performance.now();
    if (!state.sessions.some((session) => session.kind === "ambient")) {
      // One at a time, because newSessionId reads the sessions already placed.
      for (let i = 0; i <= AMBIENT_MIN; i += 1) {
        state = { ...state, sessions: [...state.sessions, newAmbientSession(true)] };
      }
      scheduleSpawn(now);
    }
    lastTick = now;
    timer = setInterval(tick, TICK_MS);
  }
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) window.removeEventListener("hashchange", dropReviewOnLeave);
    if (listeners.size === 0 && timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  };
}

function getSnapshot() {
  return state;
}

/** Starts the scenario's test call and opens it. A repeat replaces the one already running. */
function placeTestCall(scenarioId: string) {
  const scenario = SCENARIOS.find((candidate) => candidate.id === scenarioId);
  const number = TEST_NUMBERS[scenarioId];
  if (!scenario || !number) return;

  let sessions = state.sessions;
  for (const [id, held] of numbers) {
    if (held === number) {
      numbers.delete(id);
      sessions = sessions.filter((session) => session.id !== id);
    }
  }

  const id = newSessionId();
  numbers.set(id, number);
  const session: CallSession = { id, kind: "test", scenario, t: 0, furthest: 0, rate: 0 };
  publish({ ...state, sessions: [session, ...sessions], openId: id, openMask: null, receipt: null, playing: true, deliveries: sessions.some((item) => item.kind === "test") ? state.deliveries : {} });
}

/** Opens one call by its exact, complete number. There is no partial match by design. */
function openByNumber(raw: string): SearchResult {
  const cleaned = raw.replace(/[\s().+-]/g, "");
  const digits = /^1\d{10}$/.test(cleaned) ? cleaned.slice(1) : cleaned;
  if (!/^\d{10}$/.test(digits)) return { ok: false, reason: "incomplete" };

  for (const [id, held] of numbers) {
    if (held === digits) {
      const mask = digits.slice(-2);
      publish({ ...state, openId: id, openMask: mask, receipt: null });
      return { ok: true, mask };
    }
  }
  return { ok: false, reason: "not-found" };
}

function openTestSession(id: string) {
  const session = state.sessions.find((candidate) => candidate.id === id);
  if (!session || session.kind === "ambient") return;
  publish({ ...state, openId: id, openMask: null, receipt: null });
}

function closeView() {
  publish({ ...state, openId: null, openMask: null, receipt: null });
}

/** Scrubs the review of an erased call. */
function seekReview(t: number) {
  if (!state.receipt) return;
  publish({ ...state, receipt: { ...state.receipt, t: Math.max(0, Math.min(t, state.receipt.heldSeconds)) } });
}

function togglePlaying() {
  publish({ ...state, playing: !state.playing });
}

function setSpeed(speed: number) {
  publish({ ...state, speed });
}

function updateSession(id: string, change: (session: CallSession) => CallSession) {
  publish({
    ...state,
    sessions: state.sessions.map((session) => (session.id === id ? change(session) : session)),
  });
}

/** Moves a test call's play head within what it has reached. Deletion is never reached by seeking, only by playing. */
function seek(id: string, t: number) {
  updateSession(id, (session) => ({
    ...session,
    t: Math.max(0, Math.min(t, session.furthest, deletionTime(session.scenario) - 0.01)),
  }));
  publish({ ...state, playing: false });
}

/** Demo only: jumps a test call to the moment it ends. The console can't end a real call. */
function skipToAfterCall(id: string) {
  updateSession(id, (session) => {
    const ended = session.scenario.beats.find((beat) => beat.phase === "checking");
    if (!ended) return session;
    const t = Math.max(session.t, ended.t);
    return { ...session, t, furthest: Math.max(session.furthest, t) };
  });
}

const actions = { placeTestCall, placeLiveCall, openByNumber, openTestSession, closeView, togglePlaying, setSpeed, seek, seekReview, skipToAfterCall };

export function useCallSessions() {
  const snapshot = useSyncExternalStore(subscribe, getSnapshot);
  return { ...snapshot, ...actions };
}

/** The most recent beat at a session's time. Enough for a roster row: tier and phase. */
export function latestBeat(session: CallSession): { phase: CallPhase; tier: Tier } {
  const beats: Beat[] = session.scenario.beats;
  return [...beats].reverse().find((beat) => beat.t <= session.t) ?? beats[0];
}
