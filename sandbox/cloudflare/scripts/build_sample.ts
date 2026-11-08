// Picks an equal, repeatable sample per call type from the full dataset and writes src/sample.json.
//   bun scripts/build_sample.ts <path to sessions.jsonl> [per type, default 20]
// Keeps only what the pipeline may use. `caller` and `number` are dropped because `caller` leaks the label.
import { readFileSync, writeFileSync } from "node:fs";

const [input, perTypeArg] = process.argv.slice(2);
if (!input) throw new Error("usage: build_sample.ts <sessions.jsonl> [per type]");
const perType = Number(perTypeArg ?? 20);

function rng(seed: number) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const KEEP = new Set(["turn", "sms_otp", "bank_app_open", "bank_transfer", "account"]);
const byType = new Map<string, any[]>();
for (const line of readFileSync(input, "utf8").split("\n")) {
  if (!line.trim()) continue;
  const row = JSON.parse(line);
  const group = byType.get(row.label.type) ?? [];
  group.push(row);
  byType.set(row.label.type, group);
}

const random = rng(20261108);
const output: Record<string, unknown[]> = {};
for (const type of [...byType.keys()].sort()) {
  const rows = byType.get(type)!.sort((a, b) => (a.session_id < b.session_id ? -1 : 1));
  for (let i = rows.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [rows[i], rows[j]] = [rows[j], rows[i]];
  }
  output[type] = rows.slice(0, perType).map((row) => ({
    session_id: row.session_id,
    scam: row.label.scam,
    scam_type: row.label.type,
    money_moment_t: row.label.money_moment_t ?? null,
    direction: row.events.find((e: any) => e.kind === "call_start")?.direction ?? "unknown",
    events: row.events.filter((e: any) => KEEP.has(e.kind)),
  }));
}

const path = new URL("../src/sample.json", import.meta.url).pathname;
writeFileSync(path, JSON.stringify(output));
console.log(`${Object.keys(output).length} types, ${perType} each, ${readFileSync(path).length} bytes`);
