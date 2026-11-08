// Photon sidecar (Node port of spikes/tsafe_ref/src/photon-sidecar.ts). The Python API calls it over HTTP.
//
//   POST /notify   {to, text, session_id?, choices?, buttons?}  -> direct message to `to` (dm.ts)
//   POST /message  {to, text, session_id?}                      -> same, without changing the reply menu
//   GET  /health
//
// Replies: polls Photon for inbound messages from the last number we messaged, on ANY platform (iMessage,
// or SMS/RCS), maps a bare "1"/"2"/"3" to the button id from the last /notify, and POSTs
// {"choice": "call_bank", "digit": "1"} to API_URL/sessions/{id}/choice.
// Never logs message text (R8): only lengths, choice digits and channel hints.
// Run: npm run sidecar
import { createServer } from "node:http";
import { e164, known, mask, parseChoice, photon, project, sameNumber, sendDm, serviceHints } from "./dm.ts";

const sidecarUrl = new URL(process.env.PHOTON_SIDECAR_URL ?? "http://localhost:8787");
const port = Number(process.env.SIDECAR_PORT ?? (sidecarUrl.port || 8787));
const apiUrl = (process.env.API_URL ?? "").replace(/\/+$/, "");

const target = {
  to: process.env.DEMO_CUSTOMER_NUMBER ? e164(process.env.DEMO_CUSTOMER_NUMBER) : "",
  session: process.env.SESSION_ID ?? "",
  choices: ["1", "2", "3"],
  // Button ids from the last /notify, in menu order: reply "1" means buttons[0].
  buttons: ["call_bank", "ask_trusted_contact", "continue"] as string[],
};

const seen = new Set<string>();
const createdSince = new Date().toISOString();

/** POST {choice: <button id>, digit} to the API, e.g. {"choice": "call_bank", "digit": "1"}. */
async function forward(digit: string) {
  const choice = target.buttons[Number(digit) - 1] ?? digit;
  if (!target.session) return console.log(`[choice] ${digit}=${choice} (no session set)`);
  if (!apiUrl) return console.log(`[choice] ${digit}=${choice} (API_URL unset, not posted)`);
  const res = await fetch(`${apiUrl}/sessions/${encodeURIComponent(target.session)}/choice`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ choice, digit }),
  });
  console.log(`[choice] ${digit}=${choice} -> ${res.status}`);
}

async function poll() {
  if (!target.to) return;
  // No platform filter: SMS/RCS replies may arrive on a platform other than "imessage".
  const page = await photon.projects.listMessages({
    path: { id: project },
    query: { createdSince, order: "asc", pageSize: 100 },
  });
  for (const m of page.items.filter(known)) {
    if (seen.has(m.id)) continue;
    seen.add(m.id);
    const from = m.sentBy;
    if (m.status !== "received" || !known(from) || from.kind !== "human") continue;
    const handle = "handle" in from && typeof from.handle === "string" ? from.handle : "";
    if (!sameNumber(handle, target.to)) continue;
    if (m.content.type !== "text") continue;
    const hints = serviceHints(m);
    const via = `platform=${m.platform}${hints.length ? ` ${hints.join(" ")}` : ""}`;
    const choice = parseChoice(m.content.text, target.choices);
    if (!choice) {
      console.log(`[reply] from ${mask(handle)} ${via} len=${m.content.text.length} (not a choice)`);
      continue;
    }
    console.log(`[reply] from ${mask(handle)} ${via} choice=${choice}`);
    await forward(choice);
  }
}

setInterval(() => void poll().catch((err) => console.error("[poll]", err)), 2_000);

createServer(async (req, res) => {
  const reply = (status: number, body: unknown) => {
    res.writeHead(status, { "content-type": "application/json" });
    res.end(JSON.stringify(body));
  };
  const url = new URL(req.url ?? "/", "http://localhost");
  if (req.method === "GET" && url.pathname === "/health") {
    return reply(200, { ok: true, session: target.session || null, to: target.to ? mask(target.to) : null, api: !!apiUrl });
  }
  if (req.method !== "POST" || (url.pathname !== "/notify" && url.pathname !== "/message")) {
    return reply(404, { error: "not found" });
  }
  let body: Record<string, unknown>;
  try {
    let raw = "";
    for await (const chunk of req) raw += chunk;
    body = JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return reply(400, { error: "invalid json" });
  }
  const text = typeof body.text === "string" ? body.text : "";
  let to: string;
  try {
    to = e164(typeof body.to === "string" ? body.to : "");
  } catch {
    return reply(400, { error: "to must be a phone number" });
  }
  if (!text) return reply(400, { error: "text is required" });
  const session = typeof body.session_id === "string" && body.session_id ? body.session_id : target.session;
  if (!session) return reply(400, { error: "no session: pass session_id or set SESSION_ID" });

  target.to = to;
  target.session = session;
  if (url.pathname === "/notify") {
    // Only an alert changes what "1/2/3" mean; a plain /message (whisper, follow-up) keeps the last menu.
    const buttons = Array.isArray(body.buttons) ? body.buttons.map(String) : [];
    if (buttons.length) target.buttons = buttons;
    target.choices = Array.isArray(body.choices) && body.choices.length ? body.choices.map(String) : ["1", "2", "3"];
  }
  try {
    const sent = await sendDm(to, text, `sidecar:${session}:${crypto.randomUUID()}`);
    console.log(`[${url.pathname.slice(1)}] ${mask(to)} session=${session} len=${text.length} msg=${sent.messageId}`);
    return reply(200, { ok: true, message_id: sent.messageId, space_id: sent.spaceId });
  } catch (err) {
    return reply(502, { error: err instanceof Error ? err.message : String(err) });
  }
}).listen(port, "127.0.0.1", () => {
  console.log(`photon sidecar on http://127.0.0.1:${port} api=${apiUrl || "unset"} to=${target.to ? mask(target.to) : "unset"}`);
});
