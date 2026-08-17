/* Pending changes and removals to buttons that already exist on the page.
 *
 * Pure by design (see edits.js) so the sentence a user is asked to confirm,
 * and the request body behind it, can both be checked without a browser.
 */

const test = require("node:test");
const assert = require("node:assert/strict");

let edits;

test.before(async () => {
  edits = await import("../../tdsnap/web/static/edits.js");
});

function button(overrides = {}) {
  return {
    slot: 3,
    label: "aple",
    message: "",
    function: null,
    symbol: true,
    editable: true,
    locked_reason: null,
    ...overrides,
  };
}

test("a change that changes nothing is not recorded", () => {
  const target = button({ message: "I want an apple" });
  const planned = edits.planChange(edits.emptyEdits(), target, {
    label: "aple",
    message: "I want an apple",
  });
  assert.deepEqual(planned, { changes: [], removals: [] });
});

test("a change records what the button held before it", () => {
  const target = button({ message: "I want an aple" });
  const planned = edits.planChange(edits.emptyEdits(), target, {
    label: "apple",
    message: "I want an apple",
  });
  assert.equal(planned.changes.length, 1);
  assert.deepEqual(planned.changes[0].from, {
    label: "aple",
    message: "I want an aple",
    fn: "",
  });
  assert.equal(edits.effectiveLabel(planned, target), "apple");
  assert.equal(edits.pendingKind(planned, 3), "changed");
});

test("only the fields that actually move are sent", () => {
  const target = button({ message: "I want an apple" });
  const planned = edits.planChange(edits.emptyEdits(), target, {
    label: "apple",
    message: "I want an apple",
  });
  assert.deepEqual(edits.changePayload(planned), [{ slot: 3, label: "apple" }]);
});

test("clearing a message is sent as an empty message, not as nothing", () => {
  const target = button({ message: "I want an apple" });
  const planned = edits.planChange(edits.emptyEdits(), target, {
    label: "aple",
    message: "",
  });
  assert.deepEqual(edits.changePayload(planned), [{ slot: 3, message: "" }]);
});

test("removing a button drops any pending change to it, and keeping undoes both", () => {
  const target = button();
  let planned = edits.planChange(edits.emptyEdits(), target, { label: "apple", message: "" });
  planned = edits.planRemoval(planned, target);
  assert.deepEqual(planned.changes, []);
  assert.deepEqual(planned.removals, [3]);
  assert.equal(edits.pendingKind(planned, 3), "removed");

  planned = edits.keepButton(planned, 3);
  assert.equal(edits.countEdits(planned), 0);
  assert.equal(edits.pendingKind(planned, 3), null);
});

test("an edit is dropped when its button moved, was renamed, or became locked", () => {
  const target = button();
  let planned = edits.planChange(edits.emptyEdits(), target, { label: "apple", message: "" });
  planned = edits.planRemoval(planned, button({ slot: 4, label: "pear" }));

  assert.equal(edits.countEdits(edits.reconcile(planned, [])), 0);
  assert.equal(
    edits.countEdits(
      edits.reconcile(planned, [button({ slot: 3, label: "banana" }), button({ slot: 4, label: "pear" })]),
    ),
    1,
  );
  assert.equal(
    edits.countEdits(
      edits.reconcile(planned, [
        button({ slot: 3, label: "aple" }),
        button({ slot: 4, label: "pear", editable: false }),
      ]),
    ),
    1,
  );
});

test("the confirm sentence names every kind of change, and agrees with its last count", () => {
  const summary = (counts) => edits.editSummary({ page: "Snacks", ...counts });
  assert.equal(summary({ changed: 2, removed: 1 }), "Change 2 and remove 1 button on Snacks");
  assert.equal(summary({ changed: 1, removed: 2 }), "Change 1 and remove 2 buttons on Snacks");
  assert.equal(
    summary({ added: 3, changed: 2, removed: 1 }),
    "Add 3, change 2 and remove 1 button on Snacks",
  );
  assert.equal(summary({ removed: 1 }), "Remove 1 button on Snacks");
  assert.equal(summary({}), "");
});

test("each edit reads as a plain sentence on the review screen", () => {
  const target = button({ message: "I want an aple" });
  const renamed = edits.planChange(edits.emptyEdits(), target, {
    label: "apple",
    message: "I want an apple",
  });
  assert.equal(
    edits.describeChange(renamed.changes[0]),
    "“aple” becomes “apple” · speaks “I want an apple”",
  );

  const cleared = edits.planChange(edits.emptyEdits(), target, {
    label: "aple",
    message: "",
  });
  assert.equal(
    edits.describeChange(cleared.changes[0]),
    "speaks its label instead of “I want an aple”",
  );
  assert.equal(
    edits.describeRemoval(button({ label: "aple", message: "I want an aple" })),
    "aple — speaks “I want an aple”",
  );
  assert.equal(edits.describeRemoval(button({ label: "aple" })), "aple");
});
