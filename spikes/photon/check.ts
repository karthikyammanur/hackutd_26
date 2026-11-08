// L4-1 read-only Photon check: auth works and the demo space is visible. Sends nothing.
// Prints message metadata only, never message text (R8). Run: npm run check
import { Photon } from "@photon-ai/api";
import { known } from "./dm.ts";

const project = process.env.PHOTON_PROJECT_ID;
const key = process.env.PHOTON_API_KEY;
const spaceId = process.env.PHOTON_SPACE_ID;
if (!project || !key || !spaceId) throw new Error("Set PHOTON_PROJECT_ID, PHOTON_API_KEY, PHOTON_SPACE_ID");

const photon = new Photon({ headers: { Authorization: `Bearer ${key}` } });
const page = await photon.projects.listMessages({
  path: { id: project },
  query: { order: "desc", pageSize: 20, platform: "imessage" },
});
const inSpace = page.items.filter(known).filter((m) => known(m.space) && m.space.id === spaceId);
console.log(`auth ok: ${page.items.length} recent iMessages in project, ${inSpace.length} in PHOTON_SPACE_ID`);
for (const m of inSpace.slice(0, 5)) {
  console.log(`  ${m.id} status=${m.status} from=${known(m.sentBy) ? m.sentBy.kind : "?"} type=${m.content.type}`);
}
