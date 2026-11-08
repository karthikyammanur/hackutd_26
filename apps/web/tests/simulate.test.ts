import { describe, expect, test } from "bun:test";
import { budgetProblem, DAILY_CASES, DAILY_RUNS, type Ledger, type Usage } from "../worker/ledger";
import { handleProxy, validateRescore, validateRun } from "../worker/proxy";
import { activeSteps, decisionRates, drillIn, familyRows, headline, mergeDecisions, overallScore, parseLessons, parseLive, parseMarkers } from "../src/lib/simulate/parse";

const env = { SANDBOX_API_URL: "https://backend.test", SANDBOX_PASSWORD: "secret" };
const ORIGIN = "https://safe-signal.test";
const request = (path: string, init?: RequestInit) => new Request(`${ORIGIN}/sandbox-api${path}`, init);
const post = (path: string, body: unknown, headers: Record<string, string> = {}) =>
  request(path, { method: "POST", body: JSON.stringify(body), headers });
const validRun = { limit: 100, lanes: 4, channels: ["call"], methods: [], sources: [], models: [], window_turns: 6 };
const billedRun = { ...validRun, models: ["jev-latest"] };

function memoryLedger(start: Usage = { runs: 0, cases: 0 }) {
  const usage = { ...start };
  const owners = new Map<string, string>();
  const ledger: Ledger = {
    async reserve(cases) {
      const message = budgetProblem(usage, cases);
      if (message) return { ok: false, message };
      usage.runs += 1;
      usage.cases += cases;
      return { ok: true, day: "d" };
    },
    async release(_day, cases) {
      usage.runs -= 1;
      usage.cases -= cases;
    },
    async setOwner(runId, owner) {
      owners.set(runId, owner);
    },
    async ownerOf(runId) {
      return owners.get(runId) ?? null;
    },
  };
  return { ledger, usage };
}
const ledger = () => memoryLedger().ledger;

function recording(status = 200, body = "{}") {
  const calls: { url: string; init: RequestInit }[] = [];
  const upstream = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return new Response(body, { status, headers: { "content-type": "application/json", "set-cookie": "leak=1" } });
  }) as unknown as typeof fetch;
  return { calls, upstream };
}

describe("proxy", () => {
  test("injects the password and replaces any client auth", async () => {
    const { calls, upstream } = recording();
    await handleProxy(request("/runs", { headers: { authorization: "Bearer attacker" } }), env, ledger(), upstream);
    expect(calls[0].url).toBe("https://backend.test/runs");
    expect((calls[0].init.headers as Record<string, string>).authorization).toBe("Bearer secret");
  });

  test("never echoes upstream cookies or the password", async () => {
    const { upstream } = recording();
    const response = await handleProxy(request("/runs"), env, ledger(), upstream);
    expect(response.headers.get("set-cookie")).toBeNull();
    expect(await response.text()).not.toContain("secret");
  });

  test.each([
    ["GET", "/admin"],
    ["DELETE", "/runs"],
    ["GET", "/runs/a/b"],
    ["POST", "/corpus"],
    ["GET", "/runs/../secrets"],
  ])("blocks %s %s", async (method, path) => {
    const { calls, upstream } = recording();
    const response = await handleProxy(request(path, { method }), env, ledger(), upstream);
    expect(response.status).toBe(404);
    expect(calls).toHaveLength(0);
  });

  test.each([
    { ...validRun, limit: 20001 },
    { ...validRun, limit: 0 },
    { ...validRun, limit: 1.5 },
    { ...validRun, lanes: 129 },
    { ...validRun, window_turns: 50 },
    { lanes: 2 },
    { limit: 10 },
    { ...validRun, methods: "all" },
    { ...validRun, models: Array(65).fill("m") },
  ])("rejects run %#", async (body) => {
    const { calls, upstream } = recording();
    expect((await handleProxy(post("/runs", body), env, ledger(), upstream)).status).toBe(400);
    expect(calls).toHaveLength(0);
  });

  test("forwards only known run fields", async () => {
    const { calls, upstream } = recording(201);
    await handleProxy(post("/runs", { ...validRun, admin: true }), env, ledger(), upstream);
    expect(JSON.parse(calls[0].init.body as string)).toEqual(validRun);
  });

  test("blocks POSTs from another site", async () => {
    const { calls, upstream } = recording();
    const response = await handleProxy(post("/runs", validRun, { origin: "https://evil.test" }), env, ledger(), upstream);
    expect(response.status).toBe(403);
    expect(calls).toHaveLength(0);
  });

  test("passes upstream errors such as a run already active", async () => {
    const { upstream } = recording(409, '{"error":"active","id":"r"}');
    expect((await handleProxy(post("/runs", validRun), env, ledger(), upstream)).status).toBe(409);
  });

  test("reports a missing secret and a dead backend", async () => {
    expect((await handleProxy(request("/runs"), { ...env, SANDBOX_PASSWORD: "" }, ledger())).status).toBe(503);
    const dead = (async () => {
      throw new Error("down");
    }) as unknown as typeof fetch;
    expect((await handleProxy(request("/runs"), env, ledger(), dead)).status).toBe(502);
  });

  test("limits runs that use Jev to the billed cap", async () => {
    const { upstream } = recording(201);
    const jev = { ...validRun, models: ["jev-latest"], limit: 2001 };
    expect((await handleProxy(post("/runs", jev), env, ledger(), upstream)).status).toBe(400);
  });

  test("allows 20,000 cases on local models without using the daily budget", async () => {
    const { upstream } = recording(201);
    const { ledger: full } = memoryLedger({ runs: DAILY_RUNS, cases: DAILY_CASES });
    const local = { ...validRun, models: ["safe-signal-guard"], limit: 20000 };
    expect((await handleProxy(post("/runs", local), env, full, upstream)).status).toBe(201);
  });

  test("allows 128 lanes", async () => {
    const { calls, upstream } = recording(201);
    expect((await handleProxy(post("/runs", { ...validRun, lanes: 128 }), env, ledger(), upstream)).status).toBe(201);
    expect(calls).toHaveLength(1);
  });

  test("stops at the daily run budget without calling the backend", async () => {
    const { calls, upstream } = recording(201);
    const { ledger: full } = memoryLedger({ runs: DAILY_RUNS, cases: 0 });
    const response = await handleProxy(post("/runs", billedRun), env, full, upstream);
    expect(response.status).toBe(429);
    expect(((await response.json()) as { error: string }).error).toContain("Daily limit");
    expect(calls).toHaveLength(0);
  });

  test("stops at the daily case budget", async () => {
    const { upstream } = recording(201);
    const { ledger: nearly } = memoryLedger({ runs: 1, cases: DAILY_CASES - 50 });
    expect((await handleProxy(post("/runs", billedRun), env, nearly, upstream)).status).toBe(429);
    expect((await handleProxy(post("/runs", { ...billedRun, limit: 50 }), env, nearly, upstream)).status).toBe(201);
  });

  test("counts a started run and refunds one the backend refused", async () => {
    const started = memoryLedger();
    await handleProxy(post("/runs", billedRun), env, started.ledger, recording(201, '{"id":"r1"}').upstream);
    expect(started.usage).toEqual({ runs: 1, cases: 100 });
    const refused = memoryLedger();
    const response = await handleProxy(post("/runs", billedRun), env, refused.ledger, recording(409, '{"error":"active","id":"r"}').upstream);
    expect(response.status).toBe(409);
    expect(refused.usage).toEqual({ runs: 0, cases: 0 });
    const dead = memoryLedger();
    const down = (async () => {
      throw new Error("down");
    }) as unknown as typeof fetch;
    expect((await handleProxy(post("/runs", billedRun), env, dead.ledger, down)).status).toBe(502);
    expect(dead.usage).toEqual({ runs: 0, cases: 0 });
  });

  test("leaves the daily budget to the backend when the budget store is down", async () => {
    const { calls, upstream } = recording(201);
    const broken = { ...ledger(), reserve: () => Promise.reject(new Error("down")) } as Ledger;
    expect((await handleProxy(post("/runs", billedRun), env, broken, upstream)).status).toBe(201);
    expect(calls).toHaveLength(1);
  });

  test("only the browser that started a run can cancel it", async () => {
    const { ledger: shared } = memoryLedger();
    const { calls, upstream } = recording(201, '{"id":"r1"}');
    const started = await handleProxy(post("/runs", validRun), env, shared, upstream);
    const setCookie = started.headers.get("set-cookie") ?? "";
    expect(setCookie).toContain("HttpOnly");
    expect(setCookie).toContain("SameSite=Strict");
    const cookie = setCookie.split(";")[0];
    calls.length = 0;

    const cancel = (headers: Record<string, string>, id = "r1") => request(`/runs/${id}/cancel`, { method: "POST", headers });
    expect((await handleProxy(cancel({}), env, shared, upstream)).status).toBe(403);
    const other = `ss_owner=${"a".repeat(64)}`;
    expect((await handleProxy(cancel({ cookie: other }), env, shared, upstream)).status).toBe(403);
    expect((await handleProxy(cancel({ cookie }, "someone-elses-run"), env, shared, upstream)).status).toBe(403);
    expect(calls).toHaveLength(0);

    expect((await handleProxy(cancel({ cookie }), env, shared, upstream)).status).toBe(201);
    expect(calls[0].url).toBe("https://backend.test/runs/r1/cancel");
  });

  test("validates rescore", () => {
    const good = { dangerous_threshold: 0.5, uncertain_threshold: 0.2, require_hard_flag: false };
    expect("body" in validateRescore(good)).toBe(true);
    expect("error" in validateRescore({ ...good, dangerous_threshold: 2 })).toBe(true);
    expect("error" in validateRescore({ ...good, uncertain_threshold: 0.9 })).toBe(true);
    expect("error" in validateRescore({ ...good, require_hard_flag: "yes" })).toBe(true);
    expect("error" in validateRun(null)).toBe(true);
  });
});

const CONTRACT_LIVE = {
  id: "run-x",
  status: "running",
  elapsed_s: 12.3,
  total: 500,
  processed: 120,
  decisions_per_s: 42.1,
  frames_per_s: 40.2,
  lanes: { configured: 8, active: 6 },
  brev: { instances_reported: 1, endpoints: [{ name: "fast", healthy: true }, { name: "deep", healthy: false }] },
  steps: [{ name: "jev", count: 10, p50_ms: 93, p95_ms: 135, errors: 1 }],
  by_method: [
    { method: "family_emergency_voice_clone", family: "impersonation", n: 10, caught: 6, soft_miss: 1, missed: 2, clear: 0, soft_false_alarm: 0, false_alarm: 0, no_verdict: 1, score: 0.65, method_accuracy: 0.5 },
    { method: "legitimate", family: "none", n: 30, caught: 0, soft_miss: 0, missed: 0, clear: 27, soft_false_alarm: 2, false_alarm: 1, no_verdict: 0, score: 0.93, method_accuracy: 1 },
  ],
  by_model: [{ model: "jev-latest", n: 40, score: 0.8, catch_rate: 0.9, false_alarm_rate: 0.03, p50_ms: 90 }],
  recent: [{ case_id: "c1", channel: "call", method: "family_emergency_voice_clone", predicted_method: "bank_fraud_department", tier: "dangerous", outcome: "caught", model: "jev-latest", flags: ["asks_secrecy"], ms: 93 }],
  timeline: [
    { t: 1, processed: 3, decisions: 10, score: 0.8 },
    { t: 3, processed: 8, decisions: 40, score: 0.8 },
  ],
};

describe("parse", () => {
  test("reads the contract", () => {
    const live = parseLive(CONTRACT_LIVE);
    expect(live.brevInstances).toBe(1);
    expect(live.lanesActive).toBe(6);
    expect(live.endpoints?.[1]).toEqual({ name: "deep", healthy: false });
    expect(live.byMethod?.[0]).toMatchObject({ right: 6, soft: 1, wrong: 2, noVerdict: 1 });
    expect(live.steps.find((step) => step.name === "jev")?.p50).toBe(93);
    expect(decisionRates(live.timeline)).toEqual([15]);
  });

  test("missing fields stay null and are never invented", () => {
    const live = parseLive({});
    expect(live.brevInstances).toBeNull();
    expect(live.decisionsPerS).toBeNull();
    expect(live.byMethod).toBeNull();
    expect(live.endpoints).toBeNull();
    expect(live.steps.every((step) => step.count === null)).toBe(true);
    expect(overallScore(live.byMethod)).toBeNull();
    expect(parseLive(null).status).toBeNull();
  });

  test("weights overall score by cases and groups families", () => {
    const live = parseLive(CONTRACT_LIVE);
    expect(overallScore(live.byMethod)).toBeCloseTo(0.86, 5);
    expect(familyRows(live.byMethod).find((row) => row.family === "impersonation")).toEqual({ family: "impersonation", n: 10, wrong: 3, soft: 1 });
  });

  test("keeps every decision once, newest first", () => {
    const live = parseLive(CONTRACT_LIVE);
    const once = mergeDecisions([], live.recent);
    expect(mergeDecisions(once, live.recent)).toBe(once);
    const later = { ...live.recent[0], caseId: "c2", key: "c2:jev-latest" };
    expect(mergeDecisions(once, [later]).map((item) => item.caseId)).toEqual(["c2", "c1"]);
  });

  test("drill-in tallies flags and wrong methods", () => {
    const seen = parseLive(CONTRACT_LIVE).recent;
    const detail = drillIn(seen, "family_emergency_voice_clone");
    expect(detail.observed).toBe(1);
    expect(detail.flags).toEqual([{ label: "asks_secrecy", count: 1 }]);
    expect(detail.misclassifiedAs).toEqual([{ label: "bank_fraud_department", count: 1 }]);
  });

  test("reads the deployed backend's shapes", () => {
    const live = parseLive({ ...CONTRACT_LIVE, steps: [{ name: "frames", count: 1 }, { name: "nemotron_classifier", count: 2 }], weak_labels: { n: 4, score: 0.6 } });
    expect(live.steps.map((step) => step.name)).toEqual(["frames", "nemotron_classifier"]);
    expect(live.weakLabels).toEqual({ n: 4, score: 0.6 });
    expect(parseLive({ ...CONTRACT_LIVE, weak_labels: { n: 0 } }).weakLabels).toBeNull();

    const lessons = parseLessons({
      repeat_failures: [{ model: "a", method: "x", runs_failing: 2, mean_error_rate: 0.5 }, { model: "b", method: "x", runs_failing: 2, mean_error_rate: 0.25 }],
      lessons: [{ marker: "bad_label", method: "x", count: 15, improvement: "fix it" }],
    });
    expect(new Set(lessons.consistent.map((item) => item.key)).size).toBe(2);
    expect(lessons.consistent[0].detail).toBe("a, failing in 2 runs, 50.0% mean error");
    expect(lessons.lessons[0]).toMatchObject({ title: "Bad label", detail: "fix it", seen: 15, method: "x" });

    const markers = parseMarkers([{ session_id: "s", model: "a" }, { session_id: "s", model: "b" }]);
    expect(new Set(markers.map((item) => item.id)).size).toBe(2);
  });

  test("the headline never averages a yardstick model into Jev", () => {
    const models = [{ model: "baseline-rules", n: 10, score: 0.2, catchRate: 0, falseAlarmRate: 0, p50: 0 }, { model: "jev-latest", n: 10, score: 0.9, catchRate: 0, falseAlarmRate: 0, p50: 0 }];
    expect(headline(models, null)).toEqual({ score: 0.9, note: "overall score, jev-latest" });
    expect(headline([models[0]], null).note).toBe("overall score, baseline-rules");
    expect(headline([models[0], { ...models[0], model: "other" }], null).note).toContain("averaged across 2 models");
    expect(headline(null, null).score).toBeNull();
  });

  test("a step is active only while its count rises", () => {
    const first = parseLive(CONTRACT_LIVE);
    const raised = parseLive({ ...CONTRACT_LIVE, steps: [{ name: "jev", count: 20 }] });
    expect(activeSteps(first, raised)).toEqual(["jev"]);
    expect(activeSteps(raised, raised)).toEqual([]);
    expect(activeSteps(first, parseLive({ ...CONTRACT_LIVE, status: "done", steps: [{ name: "jev", count: 20 }] }))).toEqual([]);
  });
});
