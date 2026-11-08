/** Same-origin proxy to the sandbox backend. The password stays here, and the site is public, so runs that cost money are capped. */

import type { Ledger } from "./ledger";

export interface ProxyEnv {
  SANDBOX_API_URL: string;
  SANDBOX_PASSWORD: string;
}

export const PREFIX = "/sandbox-api";
export const MAX_LIMIT = 20000;
export const MAX_LANES = 128;
/** Jev is the only model billed per call. Everything else runs on the machine that is already paid for. */
export const MAX_JEV_LIMIT = 2000;
const MAX_BODY_BYTES = 8192;
const MAX_LIST = 64;
const MAX_LABEL = 64;
const WINDOW_RANGE = [2, 12] as const;
const UPSTREAM_TIMEOUT_MS = 30000;

const RUN = "[\\w-]{1,64}";
const ROUTES: [string, RegExp][] = [
  ["GET", /^\/corpus$/],
  ["GET", /^\/models$/],
  ["GET", /^\/lessons$/],
  ["GET", /^\/runs$/],
  ["POST", /^\/runs$/],
  ["GET", new RegExp(`^/runs/${RUN}$`)],
  ["GET", new RegExp(`^/runs/${RUN}/live$`)],
  ["GET", new RegExp(`^/runs/${RUN}/markers\\.(json|csv)$`)],
  ["POST", new RegExp(`^/runs/${RUN}/rescore$`)],
  ["POST", new RegExp(`^/runs/${RUN}/cancel$`)],
];

const json = (body: unknown, status: number) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });

const usesJev = (models: string[]) => models.some((model) => model.startsWith("jev"));

const isInt = (value: unknown, min: number, max: number): value is number =>
  Number.isInteger(value) && (value as number) >= min && (value as number) <= max;

function labelList(value: unknown): string[] | null {
  if (value === undefined) return [];
  if (!Array.isArray(value) || value.length > MAX_LIST) return null;
  return value.every((item) => typeof item === "string" && item.length <= MAX_LABEL) ? (value as string[]) : null;
}

/** Returns the exact body to send upstream, or an error message. Unknown fields are dropped. */
export function validateRun(body: unknown): { body: object } | { error: string } {
  if (typeof body !== "object" || body === null) return { error: "Expected a JSON object" };
  const input = body as Record<string, unknown>;
  if (!isInt(input.limit, 1, MAX_LIMIT)) return { error: `limit must be a whole number from 1 to ${MAX_LIMIT}` };
  if (!isInt(input.lanes, 1, MAX_LANES)) return { error: `lanes must be a whole number from 1 to ${MAX_LANES}` };
  const windowTurns = input.window_turns ?? 6;
  if (!isInt(windowTurns, WINDOW_RANGE[0], WINDOW_RANGE[1])) {
    return { error: `window_turns must be from ${WINDOW_RANGE[0]} to ${WINDOW_RANGE[1]}` };
  }
  const channels = labelList(input.channels);
  const methods = labelList(input.methods);
  const sources = labelList(input.sources);
  const models = labelList(input.models);
  if (!channels || !methods || !sources || !models) return { error: "Filters must be short lists of text" };
  if (usesJev(models) && (input.limit as number) > MAX_JEV_LIMIT) {
    return { error: `Runs that use Jev are limited to ${MAX_JEV_LIMIT.toLocaleString("en-US")} cases` };
  }
  return { body: { limit: input.limit, lanes: input.lanes, window_turns: windowTurns, channels, methods, sources, models } };
}

export function validateRescore(body: unknown): { body: object } | { error: string } {
  if (typeof body !== "object" || body === null) return { error: "Expected a JSON object" };
  const { dangerous_threshold: dangerous, uncertain_threshold: uncertain, require_hard_flag: hardFlag } =
    body as Record<string, unknown>;
  const ratio = (value: unknown) => typeof value === "number" && value >= 0 && value <= 1;
  if (!ratio(dangerous) || !ratio(uncertain)) return { error: "Thresholds must be between 0 and 1" };
  if ((uncertain as number) > (dangerous as number)) return { error: "uncertain_threshold can't exceed dangerous_threshold" };
  if (typeof hardFlag !== "boolean") return { error: "require_hard_flag must be true or false" };
  return { body: { dangerous_threshold: dangerous, uncertain_threshold: uncertain, require_hard_flag: hardFlag } };
}

type ReadResult = { payload: string; limit?: number } | { error: string };

async function readBody(request: Request, path: string): Promise<ReadResult> {
  if (path.endsWith("/cancel")) return { payload: "{}" };
  const text = await request.text();
  if (new TextEncoder().encode(text).length > MAX_BODY_BYTES) return { error: "Request body is too large" };
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return { error: "Request body must be JSON" };
  }
  if (path === "/runs") {
    const checked = validateRun(parsed);
    return "error" in checked ? checked : { payload: JSON.stringify(checked.body), limit: (checked.body as { limit: number }).limit };
  }
  const checked = validateRescore(parsed);
  return "error" in checked ? checked : { payload: JSON.stringify(checked.body) };
}

const OWNER_COOKIE = "ss_owner";
const OWNER_MAX_AGE_S = 30 * 24 * 60 * 60;
const CANCEL_ROUTE = new RegExp(`^/runs/(${RUN})/cancel$`);

function readOwnerToken(request: Request): string | null {
  const match = (request.headers.get("cookie") ?? "").match(new RegExp(`(?:^|;\\s*)${OWNER_COOKIE}=([0-9a-f]{64})(?:;|$)`));
  return match ? match[1] : null;
}

function newOwnerToken(): string {
  return [...crypto.getRandomValues(new Uint8Array(32))].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function hashToken(token: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(token));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

/** Reserves budget, starts the run, and records which browser started it so only that browser can cancel it. */
async function startRun(request: Request, env: ProxyEnv, ledger: Ledger, upstream: typeof fetch, payload: string, limit: number) {
  let reservation: Awaited<ReturnType<Ledger["reserve"]>> | null = null;
  const billed = usesJev((JSON.parse(payload) as { models: string[] }).models);
  try {
    if (billed) reservation = await ledger.reserve(limit);
  } catch {
    // The backend enforces the same daily budget, so a run can still start safely without this store.
  }
  if (reservation && !reservation.ok) return json({ error: reservation.message }, 429);

  const held = reservation;
  const release = async () => {
    if (held) await ledger.release(held.day, limit).catch(() => undefined);
  };
  let response: Response;
  let text: string;
  try {
    response = await send(env, upstream, "/runs", "POST", payload, true);
    text = await response.text();
  } catch {
    await release();
    return json({ error: "The sandbox didn't respond" }, 502);
  }
  if (!response.ok) {
    await release();
    return passThrough(response, text);
  }

  const token = readOwnerToken(request) ?? newOwnerToken();
  let runId: unknown;
  try {
    runId = (JSON.parse(text) as { id?: unknown }).id;
  } catch {
    runId = undefined;
  }
  const result = passThrough(response, text);
  if (typeof runId === "string") {
    await ledger.setOwner(runId, await hashToken(token)).catch(() => undefined);
    result.headers.append(
      "set-cookie",
      `${OWNER_COOKIE}=${token}; HttpOnly; Secure; SameSite=Strict; Path=${PREFIX}; Max-Age=${OWNER_MAX_AGE_S}`,
    );
  }
  return result;
}

async function ownsRun(request: Request, ledger: Ledger, runId: string): Promise<boolean> {
  const token = readOwnerToken(request);
  if (!token) return false;
  try {
    return (await ledger.ownerOf(runId)) === (await hashToken(token));
  } catch {
    return false;
  }
}

function send(env: ProxyEnv, upstream: typeof fetch, path: string, method: string, body: string | undefined, publicRun = false) {
  return upstream(`${env.SANDBOX_API_URL}${path}`, {
    method,
    headers: {
      authorization: `Bearer ${env.SANDBOX_PASSWORD}`,
      "content-type": "application/json",
      ...(publicRun ? { "x-safe-signal-public": "1" } : {}),
    },
    body,
    signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
  });
}

function passThrough(response: Response, body: BodyInit | null) {
  const headers = new Headers({ "cache-control": "no-store" });
  for (const name of ["content-type", "content-disposition"]) {
    const value = response.headers.get(name);
    if (value) headers.set(name, value);
  }
  return new Response(body, { status: response.status, headers });
}

export async function handleProxy(request: Request, env: ProxyEnv, ledger: Ledger, upstream: typeof fetch = fetch): Promise<Response> {
  const url = new URL(request.url);
  const path = url.pathname.slice(PREFIX.length).replace(/\/$/, "");
  if (!ROUTES.some(([method, route]) => method === request.method && route.test(path))) {
    return json({ error: "Not found" }, 404);
  }

  let body: string | undefined;
  let limit: number | undefined;
  if (request.method === "POST") {
    // Stops another website from starting runs through a visitor's browser.
    const origin = request.headers.get("origin");
    if (origin && origin !== url.origin) return json({ error: "Forbidden" }, 403);
    const read = await readBody(request, path);
    if ("error" in read) return json({ error: read.error }, 400);
    body = read.payload;
    limit = read.limit;
  }

  if (!env.SANDBOX_PASSWORD || !env.SANDBOX_API_URL) return json({ error: "The sandbox isn't configured" }, 503);

  const cancel = request.method === "POST" ? path.match(CANCEL_ROUTE) : null;
  if (cancel && !(await ownsRun(request, ledger, cancel[1]))) {
    return json({ error: "Only the browser that started this run can cancel it" }, 403);
  }
  if (request.method === "POST" && path === "/runs") {
    return startRun(request, env, ledger, upstream, body as string, limit as number);
  }

  try {
    const response = await send(env, upstream, path, request.method, body);
    return passThrough(response, response.body);
  } catch {
    return json({ error: "The sandbox didn't respond" }, 502);
  }
}
