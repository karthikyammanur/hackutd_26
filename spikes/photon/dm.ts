// Direct message to a phone number over Photon's REST API (@photon-ai/api 0.5.0). Shared by send.ts and sidecar.ts.
//
// Steps: createOrGetUser(number) -> createOrGetSpace([our agent, that user]) -> sendMessage -> poll getMessage.
// The REST API reports delivered/failed but not WHICH service (iMessage, SMS, RCS) carried it; only the
// Spectrum SDK exposes that (`user.service`, `message.sender.service`). We print any service-like field the
// API sends anyway, since the SDK keeps unknown members.
import { Photon } from "@photon-ai/api";

export const project = need("PHOTON_PROJECT_ID");
export const agentUserId = need("PHOTON_AGENT_USER_ID");
export const photon = new Photon({ headers: { Authorization: `Bearer ${need("PHOTON_API_KEY")}` } });

function need(name: string): string {
  const v = process.env[name]?.trim();
  if (!v) throw new Error(`Set ${name}`);
  return v;
}

/** E.164 for US numbers given as 10 or 11 digits; anything else must already start with +. */
export function e164(raw: string): string {
  const d = raw.replace(/\D/g, "");
  if (raw.trim().startsWith("+")) return `+${d}`;
  if (d.length === 10) return `+1${d}`;
  if (d.length === 11 && d.startsWith("1")) return `+${d}`;
  throw new Error(`Not an E.164 number: ...${d.slice(-4)}`);
}

/** SDK unions include a `{ platform: "UNKNOWN", raw }` branch; this drops it so the real fields type-check. */
export function known<T extends { platform: unknown }>(x: T | undefined): x is Exclude<T, { platform: "UNKNOWN" }> {
  return !!x && x.platform !== "UNKNOWN";
}

export const mask = (n: string) => `...${n.replace(/\D/g, "").slice(-4)}`;
export const sameNumber = (a: string, b: string) => {
  const x = a.replace(/\D/g, "").slice(-10);
  return x.length >= 7 && x === b.replace(/\D/g, "").slice(-10);
};

/** Read-only: is this number already a Photon user in the project, and is there a direct space with it? */
export async function lookupDm(to: string) {
  const users = await photon.projects.listUsers({
    path: { id: project },
    query: { platform: "imessage", pageSize: 100 },
  });
  const items = users.items.filter(known).filter((u) => u.platform === "imessage");
  const peer = items.find((u) => u.platform === "imessage" && sameNumber(u.handle, to));
  const agent = items.find((u) => u.platform === "imessage" && u.id === agentUserId);
  return { peer, agent };
}

/** "1", " 2 ", "3." and "3!" count; anything longer is a free-text reply, not a choice. */
export function parseChoice(text: string, choices: string[]): string | undefined {
  const m = /^\s*([0-9])\s*[.!)]?\s*$/.exec(text);
  return m && choices.includes(m[1]!) ? m[1] : undefined;
}

const spaceCache = new Map<string, string>();

/** Find or create the direct space between our agent line and `to`. Writes a user + space, sends nothing. */
export async function openDm(to: string): Promise<string> {
  const cached = spaceCache.get(to);
  if (cached) return cached;
  const peer = await photon.projects.createOrGetUser({
    path: { id: project },
    body: { platform: "imessage", handle: to },
  });
  if (!known(peer)) throw new Error("createOrGetUser returned an unknown platform");
  const space = await photon.projects.createOrGetSpace({
    path: { id: project },
    headers: { "idempotency-key": `safe-signal-dm:${agentUserId}:${peer.id}` },
    body: { platform: "imessage", participantIds: [agentUserId, peer.id] },
  });
  if (!known(space)) throw new Error("createOrGetSpace returned an unknown platform");
  spaceCache.set(to, space.id);
  return space.id;
}

export async function sendDm(to: string, text: string, key: string) {
  const spaceId = await openDm(to);
  const msg = await photon.projects.sendMessage({
    path: { id: project },
    headers: { "idempotency-key": key },
    body: { spaceId, senderId: agentUserId, content: { type: "text", format: "plain", text } },
  });
  if (!known(msg)) throw new Error("sendMessage returned an unknown platform");
  return { spaceId, messageId: msg.id, status: msg.status };
}

/** Service-like fields anywhere in a message record (iMessage/SMS/RCS), if the API sends them. */
export function serviceHints(record: unknown): string[] {
  const out: string[] = [];
  const walk = (v: unknown, path: string) => {
    if (!v || typeof v !== "object") return;
    for (const [k, val] of Object.entries(v)) {
      if (k === "content" || k === "text" || k === "handle") continue; // never print message text (R8)
      if (/service|channel|transport|network/i.test(k) && typeof val !== "object") out.push(`${path}${k}=${val}`);
      else walk(val, `${path}${k}.`);
    }
  };
  walk(record, "");
  return out;
}

/** Poll until delivered/failed or timeout. Returns the final status, failure reason and any channel hints. */
export async function waitForDelivery(messageId: string, timeoutMs = 60_000) {
  const until = Date.now() + timeoutMs;
  for (;;) {
    const m = await photon.projects.getMessage({ path: { id: project, messageId } });
    if (!known(m)) throw new Error("getMessage returned an unknown platform");
    if (m.status === "delivered" || m.status === "failed" || Date.now() > until) {
      const failure = "failure" in m ? m.failure : undefined;
      return { status: m.status, platform: m.platform, failure, hints: serviceHints(m) };
    }
    await new Promise((r) => setTimeout(r, 2_000));
  }
}
