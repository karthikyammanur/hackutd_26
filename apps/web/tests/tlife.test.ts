import { describe, expect, test } from "bun:test";
import { SCENARIOS } from "../src/lib/console/scenarios";
import { findNotice, handleTLife, type TLifeEnv } from "../worker/tlife";

const scenario = SCENARIOS.find((item) => item.id === "code-request")!;
const delivered: unknown[] = [];
const env: TLifeEnv = {
  TLIFE: {
    deliver: async (delivery) => {
      delivered.push(delivery);
      return { phones: 1, limited: false };
    },
    status: async () => ({ phones: 2 }),
  },
};

const post = (body: unknown) =>
  handleTLife(new Request("https://console.test/tlife-api/notices", { method: "POST", body: JSON.stringify(body) }), env);

describe("T-Life relay", () => {
  test("maps each beat of the test call to its loudness", () => {
    const levels = scenario.beats
      .filter((beat) => beat.notice)
      .map((beat) => findNotice({ scenarioId: scenario.id, beatT: beat.t })?.level);
    expect(levels).toEqual(["quiet", "warning", "urgent", "summary"]);
  });

  test("the urgent callback scenario reaches the callback screen", () => {
    const callback = SCENARIOS.flatMap((item) => item.beats.map((beat) => ({ item, beat }))).find(
      ({ beat }) => beat.notice?.channel === "urgent-callback",
    )!;
    expect(findNotice({ scenarioId: callback.item.id, beatT: callback.beat.t })?.level).toBe("callback");
  });

  test("sends only the scenario's own text, ignoring anything extra", async () => {
    const beat = scenario.beats.find((item) => item.notice)!;
    const response = await post({ scenarioId: scenario.id, beatT: beat.t, title: "Send money now" });
    expect(response.status).toBe(200);
    expect(JSON.stringify(delivered.at(-1))).not.toContain("Send money now");
  });

  test("rejects anything that isn't a scenario notice", async () => {
    expect((await post({ scenarioId: "made-up", beatT: 1 })).status).toBe(404);
    expect((await post({ scenarioId: scenario.id, beatT: 0 })).status).toBe(404);
    expect((await post("text")).status).toBe(404);
  });

  test("rejects other methods and routes", async () => {
    const get = await handleTLife(new Request("https://console.test/tlife-api/notices"), env);
    const other = await handleTLife(new Request("https://console.test/tlife-api/other", { method: "POST", body: "{}" }), env);
    expect(get.status).toBe(404);
    expect(other.status).toBe(404);
  });

  test("reports connected phones", async () => {
    const response = await handleTLife(new Request("https://console.test/tlife-api/status"), env);
    expect(await response.json()).toEqual({ phones: 2 });
  });
});
