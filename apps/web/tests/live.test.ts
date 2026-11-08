import { describe, expect, test } from "bun:test";
import { handleLiveProxy } from "../worker/live-proxy";
import { findNotice } from "../worker/tlife";
import { traceAt } from "../src/lib/console/call-model";
import { liveNoticeMoments, liveNow, liveScenario, placingScenario, type LiveView } from "../src/lib/console/live";
import { LIVE_CARD_FRAUD, SCENARIOS } from "../src/lib/console/scenarios";
import views from "./fixtures/live-views.json";

// Written by services/api/tests/test_view.py from the card-fraud call: S1 declined, S2 hung up, S3 read the card out.
const { s1, s2, s3 } = views as unknown as Record<"s1" | "s2" | "s3", LiveView>;

const env = { LIVE_API_URL: "https://api.test/", LIVE_API_TOKEN: "secret" };
const request = (path: string, init?: RequestInit) => new Request(`https://safe-signal.test/live-api${path}`, init);

function recording(status = 200, body = "{}", type = "application/json") {
  const calls: { url: string; init: RequestInit }[] = [];
  const upstream = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return new Response(body, { status, headers: { "content-type": type, "set-cookie": "leak=1" } });
  }) as unknown as typeof fetch;
  return { calls, upstream };
}

describe("live proxy", () => {
  test("adds the token and never forwards the visitor's headers or body", async () => {
    const { calls, upstream } = recording(202, '{"session_id":"live-abc"}');
    const response = await handleLiveProxy(
      request("/calls/start", { method: "POST", headers: { authorization: "Bearer attacker" }, body: '{"to":"+19998887777"}' }),
      env,
      upstream,
    );
    expect(response.status).toBe(202);
    expect(calls[0].url).toBe("https://api.test/calls/start");
    expect((calls[0].init.headers as Record<string, string>).authorization).toBe("Bearer secret");
    expect(calls[0].init.body).toBeUndefined();
    expect(response.headers.get("set-cookie")).toBeNull();
  });

  test.each(["/sessions/live-abc", "/sessions/live-abc/events", "/sessions/x/choice", "/live/sms", "/ws/live-abc", "/sessions/a/b/view", "/"])(
    "route %s is not exposed",
    async (path) => {
      const { calls, upstream } = recording();
      expect((await handleLiveProxy(request(path), env, upstream)).status).toBe(404);
      expect(calls).toHaveLength(0);
    },
  );

  test("the wrong method is refused", async () => {
    const { calls, upstream } = recording();
    expect((await handleLiveProxy(request("/calls/start"), env, upstream)).status).toBe(405);
    expect((await handleLiveProxy(request("/calls/current", { method: "POST" }), env, upstream)).status).toBe(405);
    expect(calls).toHaveLength(0);
  });

  test("503 when not configured, 502 when the tunnel answers with a page", async () => {
    const { upstream } = recording(200, "<html>tunnel not found</html>", "text/html");
    expect((await handleLiveProxy(request("/health"), { LIVE_API_URL: "", LIVE_API_TOKEN: "" }, upstream)).status).toBe(503);
    expect((await handleLiveProxy(request("/health"), env, upstream)).status).toBe(502);
  });
});

describe("live call beats", () => {
  test("a placed call starts ringing", () => {
    const trace = traceAt(placingScenario("live-abc"), 0);
    expect(trace.phase).toBe("connecting");
    expect(trace.nodes.customer.status).toBe("Ringing");
  });

  test("S1: declined, so nothing ran and it is erased", () => {
    const scenario = liveScenario(s1);
    expect(scenario.beats.map((beat) => beat.phase)).toEqual(["connecting", "checking", "deleted"]);
    expect(scenario.beats[1].marker).toBe("Call not answered");
    expect(traceAt(scenario, liveNow(s1, scenario)).notices).toHaveLength(0);
  });

  test("S2: card ask alerts the phone, then recovery but no callback", () => {
    const scenario = liveScenario(s2);
    const trace = traceAt(scenario, liveNow(s2, scenario));
    expect(trace.raisedFlags.has("asks_for_card_details")).toBe(true);
    const alert = scenario.beats.find((beat) => beat.notice?.title === "Stop: this call is a scam");
    expect(alert?.t).toBe(40);
    expect(alert?.phase).toBe("live");
    expect(trace.notices.map((notice) => notice.channel)).not.toContain("urgent-callback");
    expect(trace.phase).toBe("deleted");
    expect(trace.tier).toBe(3);
  });

  test("S3: the customer read the card out, so we call back", () => {
    const scenario = liveScenario(s3);
    const trace = traceAt(scenario, liveNow(s3, scenario));
    expect(trace.notices.map((notice) => notice.channel)).toContain("urgent-callback");
    expect(scenario.beats.find((beat) => beat.marker === "After-call plan ready")?.detail).toContain("gave details away");
  });

  test("beats run in order, risk never drops, and the call fits on the timeline", () => {
    for (const view of [s1, s2, s3]) {
      const scenario = liveScenario(view);
      for (let i = 1; i < scenario.beats.length; i += 1) {
        expect(scenario.beats[i].t).toBeGreaterThanOrEqual(scenario.beats[i - 1].t);
        expect(scenario.beats[i].danger).toBeGreaterThanOrEqual(scenario.beats[i - 1].danger);
      }
      expect(scenario.duration).toBeGreaterThan(liveNow(view, scenario));
    }
  });

  test("a quiet call that is still going is never mistaken for a finished one", () => {
    const quiet: LiveView = { ...s2, t: 300, ended: false, erased: false, alerts: [], flags: [], plan: [], timeline: [] };
    const scenario = liveScenario(quiet);
    expect(scenario.duration).toBeGreaterThan(liveNow(quiet, scenario));
    expect(scenario.beats.some((beat) => beat.phase === "deleted")).toBe(false);
  });
});

describe("real-call notices to T-Life", () => {
  const levels = (view: LiveView) =>
    liveNoticeMoments(liveScenario(view)).map(({ noticeT }) => findNotice({ scenarioId: LIVE_CARD_FRAUD.id, beatT: noticeT })?.level);

  test("the pre-written live notices reach T-Life at the right loudness", () => {
    const sent = LIVE_CARD_FRAUD.beats.map((beat) => findNotice({ scenarioId: "live-card-fraud", beatT: beat.t }));
    expect(sent.map((item) => item?.level)).toEqual(["warning", "urgent", "summary", "callback"]);
    expect(sent.map((item) => item?.notice.title)).toEqual([
      "Be careful on this call",
      "Stop: this call is a scam",
      "After your call: what to do now",
      "Safe Signal is calling you",
    ]);
  });

  test("never offered as a test call or played as an ambient call", () => {
    expect(SCENARIOS.map((scenario) => scenario.id)).not.toContain("live-card-fraud");
  });

  test("S1 sends nothing; S2 alert and recovery; S3 adds the callback. Nudges send nothing", () => {
    expect(levels(s1)).toEqual([]);
    expect(levels(s2)).toEqual(["urgent", "summary"]);
    expect(levels(s3)).toEqual(["urgent", "callback", "summary"]); // the plan calls back before it texts the steps
    const nudge = liveScenario({ ...s2, alerts: s2.alerts.filter((alert) => alert.level < 2) });
    expect(liveNoticeMoments(nudge).map(({ noticeT }) => noticeT)).not.toContain(2);
  });

  test("a whisper alert sends the warning", () => {
    const whisper: LiveView = { ...s2, alerts: [{ t: 30, level: 2, reason: "x" }] };
    expect(levels(whisper)[0]).toBe("warning");
  });

  test("the console shows the same text the phone gets", () => {
    const scenario = liveScenario(s3);
    const titles = LIVE_CARD_FRAUD.beats.map((beat) => beat.notice?.body);
    for (const beat of scenario.beats.filter((item) => item.notice)) expect(titles).toContain(beat.notice?.body);
  });
});
