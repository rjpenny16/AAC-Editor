/* Pending changes, moves, and removals to buttons that already exist.
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
  assert.deepEqual(planned, { changes: [], removals: [], moves: [] });
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
  assert.equal(summary({ moved: 2 }), "Move 2 buttons on Snacks");
  assert.equal(
    summary({ added: 1, changed: 1, moved: 1, removed: 1 }),
    "Add 1, change 1, move 1 and remove 1 button on Snacks",
  );
  assert.equal(summary({ removed: 1 }), "Remove 1 button on Snacks");
  assert.equal(summary({}), "");
});

/* ---------- moves ---------- */

const page = [
  button({ slot: 0, label: "apple" }),
  button({ slot: 1, label: "pear" }),
  button({ slot: 2, label: "Games", editable: false, locked_reason: "It opens a page." }),
];

test("a move into an empty cell is one move, described by row and column", () => {
  const planned = edits.planMove(edits.emptyEdits(), page, 0, 5);

  assert.deepEqual(planned.moves, [{ slot: 0, to: 5, from: { label: "apple" } }]);
  assert.equal(edits.pendingKind(planned, 0), "moved");
  assert.equal(edits.describeMove(planned.moves[0], 4), "row 1, column 1 → row 2, column 2");
  assert.deepEqual(edits.movePayload(planned), [{ slot: 0, to: 5 }]);
});

test("dropping one button on another has the two trade places", () => {
  const planned = edits.planMove(edits.emptyEdits(), page, 0, 1);

  assert.deepEqual(edits.movePayload(planned), [
    { slot: 0, to: 1 },
    { slot: 1, to: 0 },
  ]);
});

test("a locked button is never moved, and nothing is ever dropped onto one", () => {
  const onto = edits.planMove(edits.emptyEdits(), page, 0, 2);
  const from = edits.planMove(edits.emptyEdits(), page, 2, 5);
  const claimed = edits.planMove(edits.emptyEdits(), page, 0, 6, [6]);

  assert.equal(edits.countEdits(onto), 0);
  assert.equal(edits.countEdits(from), 0);
  assert.equal(edits.countEdits(claimed), 0);
});

test("moving a button again replaces its move rather than stacking one", () => {
  let planned = edits.planMove(edits.emptyEdits(), page, 0, 5);
  planned = edits.planMove(planned, page, 0, 6);

  assert.deepEqual(edits.movePayload(planned), [{ slot: 0, to: 6 }]);
});

test("a second move follows the first into the cell it is vacating", () => {
  let planned = edits.planMove(edits.emptyEdits(), page, 0, 5);
  planned = edits.planMove(planned, page, 1, 0);

  // "apple" still leaves cell 0 for cell 5, and "pear" takes the space it left.
  assert.deepEqual(edits.movePayload(planned), [
    { slot: 0, to: 5 },
    { slot: 1, to: 0 },
  ]);
});

test("re-aiming half of a swap keeps the other half wherever it is still valid", () => {
  let planned = edits.planMove(edits.emptyEdits(), page, 0, 1);
  // Sending "apple" to cell 5 instead of cell 1 ends the swap, but "pear" is
  // still headed for a cell "apple" is still leaving, so it keeps going.
  planned = edits.planMove(planned, page, 0, 5);

  assert.deepEqual(edits.movePayload(planned), [
    { slot: 0, to: 5 },
    { slot: 1, to: 0 },
  ]);

  // Retiring "apple" instead is what leaves that half nowhere to be: cell 0 is
  // freed, so "pear" may still take it, while cell 1 is nobody's target now.
  const retired = edits.planRemoval(planned, page[0]);
  assert.deepEqual(edits.movePayload(retired), [{ slot: 1, to: 0 }]);
});

test("moving and changing the same button are independent decisions", () => {
  let planned = edits.planMove(edits.emptyEdits(), page, 0, 5);
  planned = edits.planChange(planned, page[0], { label: "apples", message: "" });

  assert.equal(planned.changes.length, 1);
  assert.deepEqual(edits.movePayload(planned), [{ slot: 0, to: 5 }]);

  // "Keep as it is" answers the change, not the move.
  planned = edits.keepButton(planned, 0);
  assert.deepEqual(planned.changes, []);
  assert.deepEqual(edits.movePayload(planned), [{ slot: 0, to: 5 }]);
});

test("retiring a button drops the move it no longer needs", () => {
  let planned = edits.planMove(edits.emptyEdits(), page, 0, 5);
  planned = edits.planRemoval(planned, page[0]);

  assert.deepEqual(planned.removals, [0]);
  assert.deepEqual(planned.moves, []);
});

test("half a swap is never left behind when the page changes under it", () => {
  const swap = edits.planMove(edits.emptyEdits(), page, 0, 1);
  // "pear" was renamed in TD Snap, so its half of the swap is stale — and with
  // it gone, the other half would drop "apple" onto a button that is staying.
  const settled = edits.reconcile(swap, [
    button({ slot: 0, label: "apple" }),
    button({ slot: 1, label: "pears" }),
  ]);

  assert.deepEqual(settled.moves, []);
});

test("a move survives when the cell it is aimed at is freed by a removal", () => {
  let planned = edits.planRemoval(edits.emptyEdits(), page[1]);
  planned = edits.planMove(planned, page, 0, 1);

  assert.deepEqual(edits.reconcile(planned, page).moves, [
    { slot: 0, to: 1, from: { label: "apple" } },
  ]);
});

test("a new button may use a cell this edit frees, but never one it fills", () => {
  const removed = edits.planRemoval(edits.emptyEdits(), page[0]);
  assert.deepEqual(edits.placeableSlots(removed, page, [3]), [0, 3]);

  const moved = edits.planMove(edits.emptyEdits(), page, 0, 3);
  assert.deepEqual(edits.placeableSlots(moved, page, [3, 4]), [0, 4]);
  assert.deepEqual([...edits.occupiedAfter(moved, page)].sort(), [1, 2, 3]);
});

/* ---------- undo ---------- */

test("undo is offered only for a live TD Snap session that has something to undo", () => {
  const undo = { page: "Snacks" };
  assert.equal(edits.undoAvailable({ lastEdit: undo, provider: "tdsnap", mode: "live" }), true);
  assert.equal(edits.undoAvailable({ lastEdit: null, provider: "tdsnap", mode: "live" }), false);
  assert.equal(edits.undoAvailable({ lastEdit: undo, provider: "tdsnap", mode: "file" }), false);
  assert.equal(edits.undoAvailable({ lastEdit: undo, provider: "grid3", mode: "live" }), false);
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
