import { describe, expect, test } from "bun:test";
import { FINAL_FRAME, frameAt } from "../src/lib/home/replay";
import { CATCH_RATE, FALSE_ALARM_RATE, LEGIT_TOTAL, OUTCOMES, OVERALL_SCORE, RUN, SCAM_TOTAL, STEP_ERRORS, STEP_TOTAL } from "../src/lib/home/stats";

describe("home page figures", () => {
  test("match what the run itself reported", () => {
    const reported = RUN.byModel?.[0];
    expect(SCAM_TOTAL).toBe(113);
    expect(LEGIT_TOTAL).toBe(82);
    expect(OUTCOMES.caught).toBe(112);
    expect(OUTCOMES.falseAlarm).toBe(12);
    expect(CATCH_RATE).toBeCloseTo(reported?.catchRate ?? 0, 4);
    expect(FALSE_ALARM_RATE).toBeCloseTo(reported?.falseAlarmRate ?? 0, 4);
    expect(OVERALL_SCORE).toBeCloseTo(reported?.score ?? 0, 4);
    expect(STEP_TOTAL).toBe(968);
    expect(STEP_ERRORS).toBe(0);
  });
});

describe("run replay", () => {
  test("ends on the run's real totals", () => {
    const totals = FINAL_FRAME.byMethod.reduce((sum, row) => ({ n: sum.n + row.n, right: sum.right + row.right, soft: sum.soft + row.soft, wrong: sum.wrong + row.wrong }), { n: 0, right: 0, soft: 0, wrong: 0 });
    expect(FINAL_FRAME.live.status).toBe("done");
    expect(FINAL_FRAME.live.processed).toBe(200);
    expect(FINAL_FRAME.live.weakLabels?.n).toBe(5);
    expect(totals).toEqual({ n: 195, right: 165, soft: 18, wrong: 12 });
    expect(FINAL_FRAME.score).toBeCloseTo(OVERALL_SCORE, 6);
    expect(FINAL_FRAME.live.elapsedS).toBeCloseTo(RUN.elapsedS ?? 0, 6);
    expect(FINAL_FRAME.live.steps).toEqual(RUN.steps);
  });

  test("moves through the same phases as a real run", () => {
    expect(frameAt(0).live.processed).toBe(0);
    expect(frameAt(6).live.status).toBe("running");
    expect(frameAt(6).live.processed).toBeGreaterThan(0);
    expect(frameAt(13).live.status).toBe("checking");
    expect(frameAt(13).active).toEqual(["check"]);
  });

  test("never repeats a decision key, so the ledger stays stable", () => {
    const keys = frameAt(8).seen.map((decision) => decision.key);
    expect(new Set(keys).size).toBe(keys.length);
    expect(keys.length).toBe(40);
  });
});
