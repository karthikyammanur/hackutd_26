/** Same-origin, read-only proxy to the evidence store. The password stays here and nothing can be written through it. */

export interface EvidenceEnv {
  EVIDENCE_API_URL: string;
  EVIDENCE_PASSWORD: string;
}

export const EVIDENCE_PREFIX = "/evidence-api";
export const MAX_PAGE_SIZE = 100;
const MAX_VALUE = 200;
const MAX_CURSOR = 512;
const UPSTREAM_TIMEOUT_MS = 30000;

const FILTERS = ["q", "method", "family", "channel", "tier", "outcome", "signal", "source", "from", "to"];
const RANGE = ["from", "to", "source"];

const ROUTES: { route: RegExp; params: string[] }[] = [
  { route: /^\/incidents$/, params: [...FILTERS, "cursor", "limit"] },
  { route: /^\/incidents\/[\w-]{1,64}$/, params: [] },
  { route: /^\/stats\/overview$/, params: RANGE },
  { route: /^\/stats\/timeseries$/, params: ["bucket", "by", ...RANGE] },
  { route: /^\/stats\/signals$/, params: ["method", ...RANGE] },
  { route: /^\/stats\/methods$/, params: RANGE },
  { route: /^\/export\.csv$/, params: FILTERS },
];

const json = (body: unknown, status: number, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store", ...headers },
  });

/** Keeps only this route's parameters. Returns an error message for a value that's too long. */
export function cleanQuery(search: URLSearchParams, params: string[]): URLSearchParams | string {
  const clean = new URLSearchParams();
  for (const name of params) {
    const value = search.get(name);
    if (value === null || value === "") continue;
    if (value.length > (name === "cursor" ? MAX_CURSOR : MAX_VALUE)) return `${name} is too long`;
    if (name === "limit") {
      const limit = Number.parseInt(value, 10);
      if (Number.isNaN(limit)) continue;
      clean.set(name, String(Math.min(Math.max(limit, 1), MAX_PAGE_SIZE)));
    } else {
      clean.set(name, value);
    }
  }
  return clean;
}

export async function handleEvidenceProxy(request: Request, env: EvidenceEnv, upstream: typeof fetch = fetch): Promise<Response> {
  if (request.method !== "GET") return json({ error: "This service is read-only" }, 405, { allow: "GET" });

  const url = new URL(request.url);
  const path = url.pathname.slice(EVIDENCE_PREFIX.length).replace(/\/$/, "");
  const match = ROUTES.find(({ route }) => route.test(path));
  if (!match) return json({ error: "Not found" }, 404);

  const query = cleanQuery(url.searchParams, match.params);
  if (typeof query === "string") return json({ error: query }, 400);
  if (!env.EVIDENCE_PASSWORD || !env.EVIDENCE_API_URL) return json({ error: "The evidence store isn't configured" }, 503);

  const suffix = query.size ? `?${query}` : "";
  let response: Response;
  try {
    response = await upstream(`${env.EVIDENCE_API_URL}${path}${suffix}`, {
      method: "GET",
      headers: { authorization: `Bearer ${env.EVIDENCE_PASSWORD}` },
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
  } catch {
    return json({ error: "The evidence store didn't respond" }, 502);
  }

  const headers = new Headers({ "cache-control": path.startsWith("/stats/") && response.ok ? "private, max-age=60" : "no-store" });
  for (const name of ["content-type", "content-disposition"]) {
    const value = response.headers.get(name);
    if (value) headers.set(name, value);
  }
  return new Response(response.body, { status: response.status, headers });
}
