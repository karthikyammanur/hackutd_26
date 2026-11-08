// L4-1 Photon spike: send ONE direct message to DEMO_CUSTOMER_NUMBER (a teammate's own phone, R10).
// Dry run (default) only reads: it checks the number and our line, and sends nothing.
// Run: npm run send            (dry run)
//      npm run send -- --yes   (real message)
import { e164, lookupDm, mask, photon, project, sendDm, waitForDelivery } from "./dm.ts";

const raw = process.env.DEMO_CUSTOMER_NUMBER?.trim();
if (!raw) throw new Error("Set DEMO_CUSTOMER_NUMBER");
const to = e164(raw);
const live = process.argv.includes("--yes");

const im = await photon.projects.platforms.getImessage({ path: { id: project } });
const { peer, agent } = await lookupDm(to);
console.log(`to=${mask(to)} line mode=${im.mode} agent=${agent ? `found (${agent.details.type ?? "?"})` : "NOT FOUND"}`);
console.log(`recipient: ${peer ? `known user ${peer.id}` : "not yet a Photon user (will be created)"}`);
if (im.mode === "shared") {
  console.log(
    "note: Photon's API docs say a shared iMessage line only sends to someone with an active assignment " +
      "who has texted the line since. If the send fails with that, the teammate texts the line first.",
  );
}
if (!agent) process.exit(1);
if (!live) {
  console.log("Dry run: nothing sent. Re-run with --yes to send one message.");
  process.exit(0);
}

const text = "Safe Signal test: reply 1, 2 or 3.";
const sent = await sendDm(to, text, `l4-1-dm:${to}:${Date.now()}`);
console.log(`accepted: message=${sent.messageId} space=${sent.spaceId} status=${sent.status}`);
const done = await waitForDelivery(sent.messageId);
console.log(`final: status=${done.status} platform=${done.platform}`);
if (done.failure) console.log("failure:", JSON.stringify(done.failure));
console.log(done.hints.length ? `channel: ${done.hints.join(", ")}` : "channel: not reported by the REST API");
console.log(`Set PHOTON_SPACE_ID=${sent.spaceId} if you want check.ts to watch this conversation.`);
