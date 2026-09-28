/* One Open Board board, turned into words for the page already open.
 *
 * Pure (see openboard.js), so the decisions that matter are pinned here: a
 * board that fits keeps its layout, a link is named rather than turned into a
 * word, a clinical border becomes its function and nothing else does, and a
 * word without a preferred cell can never take the one another word's board
 * put it in.
 */

const test = require("node:test");
const assert = require("node:assert/strict");

let openboard;

test.before(async () => {
  openboard = await import("../../tdsnap/web/static/openboard.js");
});

const FUNCTIONS = {
  question: { name: "Question", color: "#1E88E5" },
  positive: { name: "Positive", color: "#43A047" },
};

function cell(row, col, label, extra = {}) {
  return { row, col, label, message: null, border: null, link: null, ...extra };
}

const BOARD = {
  id: "b",
  name: "Snacks",
  rows: 2,
  columns: 2,
  cells: [
    cell(1, 0, "more", { message: "I want more", border: "#1e88e5" }),
    cell(0, 1, "drinks", { link: "d" }),
    cell(0, 0, "chips", { border: "#FFFFFF" }),
  ],
};

test("a board that fits keeps each word in its own cell, in reading order", () => {
  const { items, links, fits } = openboard.boardWords(BOARD, {
    cols: 3, rows: 2, functions: FUNCTIONS,
  });
  assert.equal(fits, true);
  assert.deepEqual(items.map((item) => [item.label, item.preferredSlot]), [
    ["chips", 0], ["more", 3],
  ]);
  assert.equal(items[1].message, "I want more");
  assert.deepEqual(links, ["drinks"]);
});

test("only a clinical border colour becomes a function", () => {
  const { items } = openboard.boardWords(BOARD, { cols: 3, rows: 2, functions: FUNCTIONS });
  assert.equal(items[0].fn, "");
  assert.equal(items[1].fn, "question");
  assert.equal(openboard.functionForBorder(null, FUNCTIONS), "");
  assert.equal(openboard.functionForBorder("#43a047", FUNCTIONS), "positive");
});

test("a board larger than the page has no preferred cells", () => {
  const { items, fits } = openboard.boardWords(BOARD, { cols: 1, rows: 4, functions: {} });
  assert.equal(fits, false);
  assert.deepEqual(items.map((item) => item.preferredSlot), [null, null]);
});

test("preferred cells are honoured first, then the rest fill what is left", () => {
  const items = [
    { label: "a", fn: "", preferredSlot: null },
    { label: "b", fn: "", preferredSlot: 0 },
    { label: "c", fn: "", preferredSlot: 5 },
    { label: "d", fn: "", preferredSlot: 2 },
  ];
  const slots = openboard.assignSlots(items, {
    open: [0, 1, 2, 3],
    taken: [2],
    firstOpen: (fn, used) => [0, 1, 2, 3].find((slot) => !used.has(slot)) ?? null,
  });
  // b keeps 0; c's cell is not open and d's is already taken, so a, c, and d
  // take the free cells in order, and a never lands on b's cell.
  assert.deepEqual(slots, [1, 0, 3, null]);
});

test("skipped buttons and planned pages read as plain sentences", () => {
  assert.equal(
    openboard.describeSkipped({ board: "Snacks", label: "web", reason: "opens a web link" }),
    "“web” on Snacks — opens a web link",
  );
  assert.equal(
    openboard.describeSkipped({ board: "gone.obf", label: "", reason: "is missing" }),
    "gone.obf — is missing",
  );
  const page = {
    title: "Food (2)", name: "Food", renamed: true, rearranged: true,
    source_grid: { cols: 6, rows: 4 },
    cells: [{ link: null }, { link: "x" }, { link: null }],
  };
  assert.equal(
    openboard.describePlannedPage(page),
    "2 speaking buttons · 1 link to other imported pages · renamed from “Food”, "
      + "which is already taken · was a 6 by 4 board, so its buttons are in reading order",
  );
  assert.equal(
    openboard.describePlannedPage({ ...page, renamed: false, rearranged: false,
      cells: [{ link: null }] }),
    "1 speaking button",
  );
});
