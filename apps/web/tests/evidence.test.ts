import { describe, expect, test } from "bun:test";
import { cleanQuery, handleEvidenceProxy } from "../worker/evidence-proxy";
import { asCount, foldSeries, formatCount, OTHER, parseBuckets, parseIncident, parseIncidentPage, parseMethods, parseOverview, parseSignalStats, parseTimeseries, toQuery } from "../src/lib/evidence/parse";

const env = { EVIDENCE_API_URL: "https://backend.test", EVIDENCE_PASSWORD: "secret" };
const request = (path: string, init?: RequestInit) => new Request(`https://safe-signal.test/evidence-api${path}`, init);

function recording(status = 200, body = "{}") {
  const calls: { url: string; init: RequestInit }[] = [];
  const upstream = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return new Response(body, { status, headers: { "content-type": "application/json", "set-cookie": "leak=1" } });
  }) as unknown as typeof fetch;
  return { calls, upstream };
}

describe("evidence proxy", () => {
  test("injects the password and replaces any client auth", async () => {
    const { calls, upstream } = recording();
    await handleEvidenceProxy(request("/stats/overview", { headers: { authorization: "Bearer attacker" } }), env, upstream);
    expect((calls[0].init.headers as Record<string, string>).authorization).toBe("Bearer secret");
  });

  test.each(["POST", "PUT", "DELETE", "PATCH"])("%s is refused and never reaches the backend", async (method) => {
    const { calls, upstream } = recording();
    const response = await handleEvidenceProxy(request("/incidents", { method, body: "{}" }), env, upstream);
    expect(response.status).toBe(405);
    expect(calls).toHaveLength(0);
  });

  test.each(["/", "/admin", "/incidents/a/b", "/incidents/..%2fsecret", "/stats/raw", "/export.json"])("unknown route %s is 404", async (path) => {
    const { calls, upstream } = recording();
    expect((await handleEvidenceProxy(request(path), env, upstream)).status).toBe(404);
    expect(calls).toHaveLength(0);
  });

  test.each([["999", "100"], ["0", "1"], ["-4", "1"], ["25", "25"]])("limit %s becomes %s", async (given, expected) => {
    const { calls, upstream } = recording();
    await handleEvidenceProxy(request(`/incidents?limit=${given}`), env, upstream);
    expect(new URL(calls[0].url).searchParams.get("limit")).toBe(expected);
  });

  test("drops parameters a route doesn't allow", async () => {
    const { calls, upstream } = recording();
    await handleEvidenceProxy(request("/stats/overview?source=live&evil=1&limit=9"), env, upstream);
    expect(new URL(calls[0].url).search).toBe("?source=live");
  });

  test("export can't raise its row limit", async () => {
    const { calls, upstream } = recording();
    await handleEvidenceProxy(request("/export.csv?tier=safe&limit=100000"), env, upstream);
    expect(new URL(calls[0].url).search).toBe("?tier=safe");
  });

  test("rejects an oversized value", async () => {
    const { calls, upstream } = recording();
    expect((await handleEvidenceProxy(request(`/incidents?q=${"a".repeat(201)}`), env, upstream)).status).toBe(400);
    expect(calls).toHaveLength(0);
  });

  test("never forwards upstream cookies, and only caches stats", async () => {
    const { upstream } = recording();
    const stats = await handleEvidenceProxy(request("/stats/methods"), env, upstream);
    expect(stats.headers.get("set-cookie")).toBeNull();
    expect(stats.headers.get("cache-control")).toContain("max-age=60");
    expect((await handleEvidenceProxy(request("/incidents"), env, upstream)).headers.get("cache-control")).toBe("no-store");
  });

  test("reports missing configuration and an unreachable backend", async () => {
    const { upstream } = recording();
    expect((await handleEvidenceProxy(request("/incidents"), { ...env, EVIDENCE_PASSWORD: "" }, upstream)).status).toBe(503);
    const down = (async () => {
      throw new Error("down");
    }) as unknown as typeof fetch;
    expect((await handleEvidenceProxy(request("/incidents"), env, down)).status).toBe(502);
  });

  test("cleanQuery ignores a non-numeric limit", () => {
    const clean = cleanQuery(new URLSearchParams("limit=abc"), ["limit"]);
    expect(String(clean)).toBe("");
  });
});

describe("evidence parsing", () => {
  const row = { incident_id: "i1", occurred_hour: "2026-11-08T05:00:00Z", channel: "call", source: "sandbox_synthetic", method: "tech_support", family: "impersonation", tier: "dangerous", max_risk: 0.9, money_moved_before_alert: 0, signals: [{ signal: "asks_remote_access", strength: 0.8 }, "threatens"], timeline: [{ seq: 1, t_bucket_s: 15, tier: "dangerous", risk: 0.9 }, { seq: 0, t_bucket_s: 0, tier: "safe", risk: 0.1 }] };

  test("reads an incident and orders its timeline", () => {
    const incident = parseIncident(row);
    expect(incident?.moneyMovedBeforeAlert).toBe(false);
    expect(incident?.timeline.map((step) => step.seq)).toEqual([0, 1]);
    expect(incident?.signals.map((signal) => signal.signal)).toEqual(["asks_remote_access", "threatens"]);
  });

  test("missing values stay null, never invented", () => {
    const incident = parseIncident({ incident_id: "i2" });
    expect(incident?.maxRisk).toBeNull();
    expect(incident?.tier).toBeNull();
    expect(incident?.moneyMovedBeforeAlert).toBeNull();
    expect(parseIncident({})).toBeNull();
  });

  test("a page without items is empty", () => {
    expect(parseIncidentPage({ items: [row], next_cursor: "c", total_estimate: 4 }).nextCursor).toBe("c");
    expect(parseIncidentPage(null).items).toEqual([]);
  });

  test("keeps the privacy suppression marker", () => {
    expect(asCount("<5")).toBe("<5");
    expect(asCount("7")).toBeNull();
    expect(formatCount("<5")).toBe("<5");
    expect(parseBuckets({ a: "<5", b: 9 }, [])).toEqual([{ key: "b", count: 9 }, { key: "a", count: "<5" }]);
  });

  test("reads overview, signals and methods", () => {
    const overview = parseOverview({ total: 3, by_tier: [{ tier: "safe", n: 3 }], date_range: { from: "2026-11-01", to: "2026-11-08" } });
    expect(overview.byTier[0]).toEqual({ key: "safe", count: 3 });
    expect(overview.to).toBe("2026-11-08");
    expect(parseSignalStats({ signals: [{ signal: "threatens", n: 2 }] })).toEqual([{ key: "threatens", count: 2 }]);
    const methods = parseMethods({ methods: [{ method: "a", n: 1, safe: 1 }, { method: "b", family: "x", n: 5, tiers: { dangerous: 5 } }] });
    expect(methods[0]).toEqual({ method: "b", family: "x", total: 5, tiers: { dangerous: 5 } });
  });

  test("reads both timeseries shapes and folds the rest into Other", () => {
    expect(parseTimeseries({ points: [{ day: "2026-11-02", values: { a: 1 } }, { day: "2026-11-01", values: { a: 2 } }] }).map((p) => p.day)).toEqual(["2026-11-01", "2026-11-02"]);
    expect(parseTimeseries({ series: [{ key: "a", points: [{ day: "2026-11-01", n: 2 }] }, { key: "b", points: [{ day: "2026-11-01", n: "<5" }] }] })).toEqual([{ day: "2026-11-01", values: { a: 2, b: "<5" } }]);
    const points = parseTimeseries([{ day: "2026-11-01", key: "a", n: 2 }, { day: "2026-11-01", key: "b", n: 3 }, { day: "2026-11-01", key: "c", n: "<5" }]);
    const [folded] = foldSeries(points, ["a"]);
    expect(folded).toEqual({ day: "2026-11-01", values: { a: 2, [OTHER]: 3 }, total: 5, suppressed: true });
  });

  test("toQuery skips empty values", () => {
    expect(toQuery({ q: "gift cards", tier: "", method: undefined })).toBe("?q=gift+cards");
    expect(toQuery({})).toBe("");
  });
});
