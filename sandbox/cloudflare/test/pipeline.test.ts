import { describe, expect, test } from "bun:test";
import { sha256Hex, verifyPassword } from "../src/auth";
import { buildFrames, composeState, type RawEvent, type Session } from "../src/frames";
import { buildQuestions, parseAnswer, type Tier } from "../src/jev";
import { parseJsonObject } from "../src/nemotron";
import { consistentFailures, failureBuckets, validateReview } from "../src/review";
import { buildScoreboard, scoreCall, type FrameResult } from "../src/scoring";

const events: RawEvent[] = [
  { t: 5, kind: "turn", who: "caller", text: "Hello from your bank." },
  { t: 9, kind: "turn", who: "customer", text: "Hi." },
  { t: 20, kind: "sms_otp", sender: "Bank" },
  { t: 25, kind: "turn", who: "caller", text: "read me the code" },
];
const session = (scam: boolean, scam_type = "x"): Session => ({
  session_id: "S-1",
  scam,
  scam_type,
  money_moment_t: scam ? 30 : null,
  direction: "inbound",
  events,
});
const frame = (index: number, tier: Tier | null, t = 5 * index): FrameResult => ({
  index,
  t,
  trigger: "turn",
  tier,
  p_safe: 0.1,
  p_uncertain: 0.1,
  p_dangerous: tier === "dangerous" ? 0.9 : 0.1,
  flags: { asks_for_code: 0.8 },
  jev_ms: 5,
  agent_ms: null,
  input_tokens: 1,
  output_tokens: 1,
  agent_called: false,
  agent_ok: true,
  delivered: tier !== null,
  error: tier === null ? "failed" : null,
});

describe("auth", () => {
  test("accepts only the password matching the stored hash", async () => {
    const hash = await sha256Hex("correct horse");
    expect(await verifyPassword("correct horse", hash)).toBe(true);
    expect(await verifyPassword("wrong", hash)).toBe(false);
    expect(await verifyPassword("", hash)).toBe(false);
    expect(await verifyPassword("correct horse", "")).toBe(false);
  });
});

describe("frames", () => {
  test("each frame sees only the past", () => {
    const frames = buildFrames(events);
    expect(frames.map((f) => f.trigger)).toEqual(["turn", "sms_otp", "turn"]);
    expect(frames[1].window.join()).not.toContain("read me the code");
    expect(frames[2].latest).toContain("read me the code");
  });

  test("the agent is only handed turns that left the window, once each", () => {
    const many: RawEvent[] = Array.from({ length: 9 }, (_, i) => ({ t: i, kind: "turn", who: "caller", text: `line ${i}` }));
    const handed = buildFrames(many).flatMap((f) => f.scrolledOut);
    expect(handed).toEqual(["CALLER: line 0", "CALLER: line 1", "CALLER: line 2"]);
  });

  test("the newest turn always reaches Jev verbatim", () => {
    const f = buildFrames(events)[2];
    expect(composeState(session(true), f, "note")).toContain(f.latest);
  });
});

describe("scoring", () => {
  test.each([
    [true, "dangerous", "caught", 1],
    [true, "uncertain", "soft_miss", 0.5],
    [true, "safe", "missed", 0],
    [false, "safe", "clear", 1],
    [false, "uncertain", "soft_false_alarm", 0.5],
    [false, "dangerous", "false_alarm", 0],
  ] as const)("scam=%p tier=%p", (scam, tier, outcome, points) => {
    const row = scoreCall(session(scam), [frame(0, tier)]);
    expect([row.outcome, row.points]).toEqual([outcome, points]);
  });

  test("risk never goes down across frames", () => {
    const row = scoreCall(session(true), [frame(1, "dangerous"), frame(2, "safe")]);
    expect(row.tier).toBe("dangerous");
    expect(row.first_dangerous_t).toBe(5);
    expect(row.caught_before_money).toBe(true);
  });

  test("a call with no answers is no_verdict, never safe", () => {
    expect(scoreCall(session(false), [frame(0, null)]).outcome).toBe("no_verdict");
  });

  test("failed frames are counted", () => {
    const row = scoreCall(session(true), [frame(0, "uncertain"), frame(1, null)]);
    const board = buildScoreboard([row], {});
    expect(board.delivery.jev_failures).toBe(1);
    expect(board.delivery.delivered).toBe(1);
  });
});

describe("jev", () => {
  test("parses a real-shaped response and rejects a bad one", () => {
    const questions = buildQuestions();
    const answers: Record<string, unknown> = {};
    for (const name of Object.keys(questions)) answers[name] = { noul: 0.2 };
    answers.danger_tier = { choice: "dangerous", probabilities: { safe: 0.1, uncertain: 0.1, dangerous: 0.8 } };
    expect(parseAnswer({ answers }, 1).tier).toBe("dangerous");
    expect(() => parseAnswer({ answers: {} }, 1)).toThrow();
  });
});

describe("review", () => {
  const good = {
    pattern: "p",
    scam_types: ["x"],
    failure_kind: "missed_scam",
    likely_cause: "c",
    fix: "f",
    fix_target: "jev_questions",
    priority: "high",
  };

  test("drops invented evidence and malformed items", () => {
    const review = validateReview(
      {
        overall: "o",
        recommendations: [
          { ...good, evidence_session_ids: ["S-1", "S-FAKE"] },
          { ...good, evidence_session_ids: ["S-FAKE"] },
          { ...good, fix_target: "nonsense", evidence_session_ids: ["S-1"] },
        ],
      },
      new Set(["S-1"]),
    );
    expect(review.recommendations.map((r) => r.evidence_session_ids)).toEqual([["S-1"]]);
    expect(() => validateReview({}, new Set())).toThrow();
  });

  test("only failures are sent to the reviewer", () => {
    const right = scoreCall(session(true), [frame(0, "dangerous")]);
    const wrong = scoreCall(session(true), [frame(0, "safe")]);
    const buckets = failureBuckets([right, wrong], () => "excerpt");
    expect(buckets).toHaveLength(1);
    expect(buckets[0].outcome).toBe("missed");
  });

  test("a consistent failure needs repeat runs", () => {
    const one = [{ run_id: "a", type: "x", error_rate: 0.5 }];
    expect(consistentFailures(one, ["a"])).toEqual([]);
    const two = [...one, { run_id: "b", type: "x", error_rate: 0.3 }];
    expect(consistentFailures(two, ["a", "b"]).map((c) => c.type)).toEqual(["x"]);
  });

  test("model output is parsed safely", () => {
    expect(parseJsonObject('<think>hm</think> {"a": 1}')).toEqual({ a: 1 });
    expect(() => parseJsonObject("nope")).toThrow();
  });
});
