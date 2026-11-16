/* Every failure message answers the six questions in doc 05 (roadmap E1):
 * what happened, was anything changed, is the original safe, what next, is
 * retrying safe, and a reference. Pure module, so checked without a browser.
 */

const test = require("node:test");
const assert = require("node:assert/strict");

let outcomes;

test.before(async () => {
  outcomes = await import("../../tdsnap/web/static/outcomes.js");
});

const FAILURES = ["refused", "rolled_back", "partial", "unknown"];

test("every failure outcome gives all six answers", () => {
  for (const outcome of FAILURES) {
    const lines = outcomes.failureLines(
      { message: "TD Snap did not save the button.", outcome, code: "VERIFY_MISMATCH", op: "ab12" },
      "TD Snap",
    );
    const facts = outcomes.OUTCOME[outcome];
    assert.equal(lines[0], "TD Snap did not save the button.", outcome); // what happened
    assert.ok(lines.includes(facts.changed), `${outcome}: was anything changed`);
    assert.ok(lines.includes(facts.safe), `${outcome}: is the original safe`);
    assert.ok(lines.includes(facts.retry), `${outcome}: is retrying safe`);
    assert.ok(lines.some((line) => line.includes("Reference ab12")), `${outcome}: reference`);
    assert.ok(lines.length >= 5, `${outcome}: what next`);
  }
});

test("an error with no outcome is treated as unknown, never as safe", () => {
  const lines = outcomes.failureLines({ message: "The local editor isn’t responding." });
  assert.ok(lines.includes(outcomes.OUTCOME.unknown.changed));
  assert.ok(!lines.includes(outcomes.OUTCOME.refused.changed));
});

test("headings follow the outcome, and only partial or unknown say to check", () => {
  assert.match(outcomes.failureHeading({ outcome: "refused" }), /not started/);
  assert.match(outcomes.failureHeading({ outcome: "rolled_back" }), /put back/);
  assert.match(outcomes.failureHeading({ outcome: "partial" }, "Grid 3"), /Check it in Grid 3/);
  assert.match(outcomes.failureHeading({ outcome: "unknown" }), /Check the page/);
});

test("no message is a bare 'something went wrong, try again'", () => {
  for (const outcome of FAILURES) {
    const text = outcomes.failureLines({ message: "x", outcome }).join(" ");
    assert.doesNotMatch(text, /something (unexpected )?went wrong/i);
  }
});
