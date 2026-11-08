import assert from "node:assert/strict";
import { test } from "node:test";

process.env.PHOTON_PROJECT_ID ??= "test";
process.env.PHOTON_AGENT_USER_ID ??= "test";
process.env.PHOTON_API_KEY ??= "test";
const { e164, parseChoice, sameNumber } = await import("./dm.ts");

test("bare digits are choices, free text is not", () => {
  const c = ["1", "2", "3"];
  for (const t of ["1", " 2 ", "3.", "3!", "2)"]) assert.equal(parseChoice(t, c), t.trim()[0]);
  for (const t of ["4", "12", "1 please", "", "call 1"]) assert.equal(parseChoice(t, c), undefined);
});

test("numbers match across formats (SMS handles may lack +1)", () => {
  assert.equal(e164("(555) 555-0100"), "+15555550100");
  assert.ok(sameNumber("5555550100", "+15555550100"));
  assert.ok(!sameNumber("+15555550101", "+15555550100"));
});
