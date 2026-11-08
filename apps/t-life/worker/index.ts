import { WorkerEntrypoint } from "cloudflare:workers";
import { DEMO_SEQUENCE, type NoticeDelivery, type NoticeLevel } from "../src/lib/notices";
import { NoticeHub, type HubEnv } from "./hub";
import { isPushEndpoint } from "./hub-endpoints";

interface Env extends HubEnv {
  ASSETS: { fetch(request: Request): Promise<Response> };
}

const MAX_BODY_BYTES = 2048;
const LEVELS = new Set<string>(DEMO_SEQUENCE.map((item) => item.level));

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });

const hubOf = (env: Env) => new NoticeHub(env);

async function readBody(request: Request): Promise<Record<string, unknown> | null> {
  const raw = await request.text();
  if (raw.length > MAX_BODY_BYTES) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    return typeof parsed === "object" && parsed !== null ? (parsed as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

const isShortString = (value: unknown): value is string => typeof value === "string" && value.length > 0 && value.length <= 256;

async function handleApi(request: Request, env: Env, ctx: ExecutionContext, path: string): Promise<Response> {
  if (path === "/api/vapid" && request.method === "GET") return json({ publicKey: env.VAPID_PUBLIC_KEY });

  if (path === "/api/realtime" && request.method === "GET") {
    return json({ topic: env.REALTIME_TOPIC, publicKey: env.REALTIME_PUBLIC_KEY });
  }

  if (path === "/api/recent" && request.method === "GET") {
    const since = Number(new URL(request.url).searchParams.get("since") ?? 0);
    return json({ notices: await hubOf(env).recent(Number.isFinite(since) ? since : 0) });
  }

  if (request.method !== "POST") return json({ error: "Not found" }, 404);
  const body = await readBody(request);
  if (!body || typeof body.endpoint !== "string" || !isPushEndpoint(body.endpoint)) return json({ error: "Invalid request" }, 400);

  if (path === "/api/subscribe") {
    if (!isShortString(body.p256dh) || !isShortString(body.auth)) return json({ error: "Invalid keys" }, 400);
    const saved = await hubOf(env).subscribe({ endpoint: body.endpoint, p256dh: body.p256dh, auth: body.auth });
    return json({ saved }, saved ? 200 : 503);
  }
  if (path === "/api/unsubscribe") {
    await hubOf(env).unsubscribe([body.endpoint]);
    return json({ ok: true });
  }
  if (path === "/api/self-test") {
    if (typeof body.level !== "string" || !LEVELS.has(body.level)) return json({ error: "Unknown level" }, 400);
    ctx.waitUntil(hubOf(env).selfTest(body.endpoint, body.level as NoticeLevel));
    return json({ queued: true }, 202);
  }
  return json({ error: "Not found" }, 404);
}

export default {
  fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const { pathname } = new URL(request.url);
    if (pathname.startsWith("/api/")) return handleApi(request, env, ctx, pathname);
    return env.ASSETS.fetch(request);
  },
};

/** Reachable only through a service binding on this Cloudflare account, never from the internet. */
export class NoticeRelay extends WorkerEntrypoint<Env> {
  deliver(delivery: NoticeDelivery) {
    return hubOf(this.env).deliver(delivery);
  }

  status() {
    return hubOf(this.env).status();
  }
}
