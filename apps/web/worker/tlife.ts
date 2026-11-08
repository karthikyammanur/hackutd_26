/** Carries a test call's notices to the T-Life demo, over a private binding between the two Workers. */

import { SCENARIOS } from "../src/lib/console/scenarios";
import type { Beat, CustomerNotice } from "../src/lib/console/call-model";

export const TLIFE_PREFIX = "/tlife-api";

type NoticeLevel = "quiet" | "warning" | "urgent" | "summary" | "callback";

interface DeliverResult {
  phones: number;
  limited: boolean;
  relay?: { url: string; body: string };
}

export interface TLifeEnv {
  TLIFE: {
    deliver(delivery: { level: NoticeLevel; notice: CustomerNotice }): Promise<DeliverResult>;
    status(): Promise<{ phones: number }>;
  };
}

const MAX_BODY_BYTES = 256;

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });

export function levelOf(beat: Beat & { notice: CustomerNotice }): NoticeLevel {
  if (beat.notice.channel === "urgent-callback") return "callback";
  if (beat.notice.timing === "after-call") return "summary";
  if (beat.tier >= 3) return "urgent";
  return beat.tier === 2 ? "warning" : "quiet";
}

/** Only a notice written into a scenario can be sent, so this public route can't carry free text. */
export function findNotice(body: unknown): { level: NoticeLevel; notice: CustomerNotice } | null {
  if (typeof body !== "object" || body === null) return null;
  const { scenarioId, beatT } = body as { scenarioId?: unknown; beatT?: unknown };
  const beat = SCENARIOS.find((scenario) => scenario.id === scenarioId)?.beats.find((item) => item.t === beatT);
  return beat?.notice ? { level: levelOf(beat as Beat & { notice: CustomerNotice }), notice: beat.notice } : null;
}

export async function handleTLife(request: Request, env: TLifeEnv): Promise<Response> {
  const path = new URL(request.url).pathname.slice(TLIFE_PREFIX.length);

  if (path === "/status" && request.method === "GET") return json(await env.TLIFE.status());

  if (path === "/notices" && request.method === "POST") {
    const raw = await request.text();
    if (raw.length > MAX_BODY_BYTES) return json({ error: "Request too large" }, 413);
    let parsed: unknown = null;
    try {
      parsed = JSON.parse(raw);
    } catch {
      return json({ error: "Expected JSON" }, 400);
    }
    const delivery = findNotice(parsed);
    if (!delivery) return json({ error: "No such notice" }, 404);
    const result = await env.TLIFE.deliver(delivery);
    return json(result, result.limited ? 429 : 200);
  }

  return json({ error: "Not found" }, 404);
}
