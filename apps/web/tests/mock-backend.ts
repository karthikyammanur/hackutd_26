// TEST ONLY. Serves dist/ and a replay of the sandbox API, for checking the page in a browser.
//   npm run build && bun tests/mock-backend.ts
// Never deployed: the Worker entry is worker/index.ts and this file isn't imported by it.

const METHODS = [
  ["family_emergency_voice_clone", "impersonation"],
  ["bank_fraud_department", "impersonation"],
  ["phantom_hacker", "impersonation"],
  ["toll_unpaid", "payment_lure"],
  ["delivery_fee", "payment_lure"],
  ["account_verification_phish", "credential_theft"],
  ["job_task_scam", "relationship_or_opportunity"],
  ["legitimate", "none"],
];
const TOTAL = 160;
let polls = 12;

function byMethod(processed: number, strict = 0) {
  return METHODS.map(([method, family], index) => {
    const n = Math.round((processed / TOTAL) * (20 + index * 3));
    const benign = method === "legitimate";
    const wrong = Math.round(n * (0.05 + index * 0.02 + strict));
    const soft = Math.round(n * 0.12);
    const right = Math.max(0, n - wrong - soft);
    return {
      method, family, n,
      caught: benign ? 0 : right, clear: benign ? right : 0,
      soft_miss: benign ? 0 : soft, soft_false_alarm: benign ? soft : 0,
      missed: benign ? 0 : wrong, false_alarm: benign ? wrong : 0, no_verdict: 0,
      score: n ? (right + soft / 2) / n : null, method_accuracy: 0.7,
    };
  });
}

const models = (strict = 0) => [
  { model: "jev-latest", n: 120, score: 0.88 - strict, catch_rate: 0.95, false_alarm_rate: 0.06, p50_ms: 93 },
  { model: "nemotron-deep", n: 120, score: 0.74 - strict, catch_rate: 0.81, false_alarm_rate: 0.15, p50_ms: 410 },
];

function live() {
  polls += 1;
  const processed = Math.min(TOTAL, polls * 8);
  const running = processed < TOTAL;
  const decisions = processed * 6;
  return {
    id: "run-mock", status: running ? "running" : "done", elapsed_s: polls, total: TOTAL, processed,
    decisions_per_s: 48.2, frames_per_s: 46.1, lanes: { configured: 8, active: running ? 8 : 0 },
    brev: { instances_reported: 1, endpoints: [{ name: "fast", healthy: true }, { name: "deep", healthy: true }] },
    steps: [
      { name: "frames", count: decisions, p50_ms: 1, p95_ms: 2, errors: 0 },
      { name: "agent", count: processed * 2, p50_ms: 270, p95_ms: 410, errors: 3 },
      { name: "jev", count: decisions, p50_ms: 93, p95_ms: 135, errors: 0 },
      { name: "score", count: processed, p50_ms: 1, p95_ms: 2, errors: 0 },
      { name: "check", count: running ? 0 : 18, p50_ms: 320, p95_ms: 500, errors: 0 },
    ],
    by_method: byMethod(processed),
    by_model: models(),
    recent: Array.from({ length: 10 }, (_, index) => ({
      case_id: `case-${processed - index}`, channel: index % 3 ? "call" : "sms",
      method: METHODS[index % 2 === 0 ? 0 : 1 + (index % 6)][0], predicted_method: index % 4 === 0 ? "bank_fraud_department" : null,
      tier: index % 5 === 0 ? "uncertain" : "dangerous", outcome: index % 5 === 0 ? "soft_miss" : "caught",
      model: "jev-latest", flags: ["emotional_family_emergency", "asks_secrecy"].slice(0, 1 + (index % 2)), ms: 90 + index,
    })),
    timeline: Array.from({ length: polls }, (_, index) => ({ t: index + 1, processed: (index + 1) * 8, decisions: ((index + 1) * (index + 2) * 24) / 8, score: 0.85 })),
  };
}

const json = (body: unknown, status = 200) => Response.json(body, { status });

Bun.serve({
  port: Number(process.env.PORT ?? 4173),
  async fetch(request) {
    const { pathname } = new URL(request.url);
    if (pathname.startsWith("/sandbox-api/")) {
      const path = pathname.slice("/sandbox-api".length);
      if (path === "/corpus") {
        return json({ by_channel: { call: 42000, sms: 900000 }, by_source: { datagen: 42000, generated: 9000 }, by_method: Object.fromEntries(METHODS.map(([method], index) => [method, 1000 + index])) });
      }
      if (path === "/models") return json([{ model: "jev-latest", healthy: true }, { model: "nemotron-deep", healthy: true }]);
      if (path === "/runs" && request.method === "GET") return json([{ id: "run-mock", created_at: "2026-11-08T11:00:00Z", total: TOTAL, status: "running" }]);
      if (path === "/runs") return json({ id: "run-mock", total: TOTAL }, 201);
      if (path === "/lessons") return json({ consistent_failures: [{ type: "phantom_hacker", runs_failing: 3, runs_seen: 4, mean_error_rate: 0.31 }], lessons: [{ pattern: "Authority claims over-weighted", fix: "Add verified context", status: "proposed" }] });
      if (path === "/runs/run-mock/live") return json(live());
      if (path === "/runs/run-mock/markers.json") return json([{ case_id: "case-1", call_type: "benign_real_bank_alert", outcome: "soft_false_alarm", marker: "authority_claim_false_positive", feedback: "Over-relied on the authority claim.", improvement: "Add context for verified institutions." }]);
      if (path === "/runs/run-mock/rescore") {
        const body = (await request.json()) as { dangerous_threshold: number };
        const strict = Math.max(0, 0.5 - body.dangerous_threshold) * 0.5;
        return json({ by_method: byMethod(TOTAL, strict), by_model: models(strict) });
      }
      return json({ error: "Not found" }, 404);
    }
    const file = Bun.file(`dist${pathname === "/" ? "/index.html" : pathname}`);
    return (await file.exists()) ? new Response(file) : new Response(Bun.file("dist/index.html"));
  },
});
console.log("mock ready");
