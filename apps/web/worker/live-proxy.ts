/**
 * Same-origin proxy to the Safe Signal API (services/api), which runs on the demo laptop behind a tunnel.
 * The token stays here. Four routes only: place the one demo call, find the live call, read its markers, health.
 * No route takes a phone number: the API always dials its own demo number (rule R10).
 */

export interface LiveEnv {
  /** The tunnel to the API, e.g. https://name.ngrok-free.app. A var, so it can change without a rebuild. */
  LIVE_API_URL: string;
  /** Same value as API_TOKEN in the API's .env. A secret: `wrangler secret put LIVE_API_TOKEN`. */
  LIVE_API_TOKEN: string;
}

export const LIVE_PREFIX = "/live-api";
const START_TIMEOUT_MS = 40000; // placing the call waits on ElevenLabs
const READ_TIMEOUT_MS = 8000;

const ROUTES: { method: "GET" | "POST"; route: RegExp }[] = [
  { method: "POST", route: /^\/calls\/start$/ },
  { method: "GET", route: /^\/calls\/current$/ },
  { method: "GET", route: /^\/sessions\/[\w-]{1,64}\/view$/ },
  { method: "GET", route: /^\/health$/ },
];

const json = (body: unknown, status: number, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store", ...headers },
  });

export async function handleLiveProxy(request: Request, env: LiveEnv, upstream: typeof fetch = fetch): Promise<Response> {
  const path = new URL(request.url).pathname.slice(LIVE_PREFIX.length).replace(/\/$/, "");
  const match = ROUTES.find(({ route }) => route.test(path));
  if (!match) return json({ error: "Not found" }, 404);
  if (request.method !== match.method) return json({ error: "Method not allowed" }, 405, { allow: match.method });
  if (!env.LIVE_API_URL || !env.LIVE_API_TOKEN) return json({ error: "The live API isn't configured" }, 503);

  let response: Response;
  try {
    response = await upstream(`${env.LIVE_API_URL.replace(/\/+$/, "")}${path}`, {
      method: match.method,
      // Never the visitor's own headers or body. ngrok's header skips its browser warning page.
      headers: { authorization: `Bearer ${env.LIVE_API_TOKEN}`, "ngrok-skip-browser-warning": "1" },
      signal: AbortSignal.timeout(match.method === "POST" ? START_TIMEOUT_MS : READ_TIMEOUT_MS),
    });
  } catch {
    return json({ error: "The live API didn't respond" }, 502);
  }
  const type = response.headers.get("content-type") ?? "";
  if (!type.includes("application/json")) return json({ error: "The live API isn't reachable" }, 502); // a tunnel's error page
  return new Response(response.body, { status: response.status, headers: { "content-type": "application/json", "cache-control": "no-store" } });
}
