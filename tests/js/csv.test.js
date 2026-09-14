/* Reading a clinician's spreadsheet.
 *
 * Pure by design (see csv.js), so what a real file turns into is checked here
 * rather than by pasting into a browser and squinting at the chip box. The
 * cases that matter are the ones that used to lose work: a comma inside a
 * phrase, a quoted field with a line break in it, and a row that cannot become
 * a button having a reason attached rather than vanishing.
 */

const test = require("node:test");
const assert = require("node:assert/strict");

let csv;

test.before(async () => {
  csv = await import("../../tdsnap/web/static/csv.js");
});

/* ---------- parsing ---------- */

test("a comma inside a phrase is not a column break", () => {
  const text = 'Label\tMessage\nmore\t"I want more, please"\nstop\tStop that';

  const { delimiter, rows, hasHeader } = csv.readTable(text);

  assert.equal(delimiter, "\t");
  assert.equal(hasHeader, true);
  assert.deepEqual(rows[1], ["more", "I want more, please"]);
  assert.deepEqual(rows[2], ["stop", "Stop that"]);
});

test("quoted fields carry delimiters, line breaks, and doubled quotes", () => {
  const text = 'a,"one, two","line\nbreak","say ""hi"""';

  assert.deepEqual(csv.parseDelimited(text, ","), [
    ["a", "one, two", "line\nbreak", 'say "hi"'],
  ]);
});

test("windows and old-mac line endings read the same as unix", () => {
  const rows = csv.parseDelimited("a,b\r\nc,d\re,f", ",");
  assert.deepEqual(rows, [["a", "b"], ["c", "d"], ["e", "f"]]);
});

test("a single column of words needs no delimiter and keeps its commas", () => {
  const { delimiter, rows, hasHeader, columns } = csv.readTable(
    "more please\nI want a turn, now\nall done",
  );

  assert.equal(delimiter, null);
  assert.equal(hasHeader, false);
  assert.equal(columns.label, 0);
  assert.deepEqual(rows, [["more please"], ["I want a turn, now"], ["all done"]]);
});

test("a delimiter only counts when it structures every line", () => {
  // Commas here are punctuation, not columns: the lines disagree on width.
  assert.equal(csv.detectDelimiter("hello, there\nyes\nno, not now, thanks"), null);
  // These agree, so the comma is real.
  assert.equal(csv.detectDelimiter("a,b\nc,d\ne,f"), ",");
  assert.equal(csv.detectDelimiter("a;b\nc;d"), ";");
});

test("blank lines are dropped rather than becoming empty buttons", () => {
  const { rows } = csv.readTable("apple\n\n\npear\n");
  assert.deepEqual(rows, [["apple"], ["pear"]]);
});

/* ---------- column mapping ---------- */

test("headings are recognised in the words people actually use", () => {
  assert.deepEqual(
    csv.guessColumns(["Button", "What it says", "Function", "Symbol"]),
    { label: 0, message: 1, fn: 2, symbolQuery: 3 },
  );
  assert.deepEqual(
    csv.guessColumns(["Spoken message", "Vocabulary"]),
    { label: 1, message: 0, fn: null, symbolQuery: null },
  );
  // Nothing recognised: no mapping is invented.
  assert.deepEqual(
    csv.guessColumns(["col1", "col2"]),
    { label: null, message: null, fn: null, symbolQuery: null },
  );
});

test("a first row of vocabulary is never mistaken for a header", () => {
  const { hasHeader, columns } = csv.readTable("apple\tI want an apple\npear\tI want a pear");
  assert.equal(hasHeader, false);
  assert.equal(columns.label, 0);
});

test("function names are read loosely but never guessed", () => {
  assert.equal(csv.readFunction("Question"), "question");
  assert.equal(csv.readFunction("  questions "), "question");
  assert.equal(csv.readFunction("q"), "question");
  assert.equal(csv.readFunction("Positive row"), "positive");
  assert.equal(csv.readFunction(""), "");
  // A word that is not one of the five clinical functions gets none, rather
  // than landing a phrase in the wrong communicative row.
  assert.equal(csv.readFunction("greeting"), "");
  assert.equal(csv.readFunction("misc"), "");
});

/* ---------- rows to buttons ---------- */

test("every row becomes a button or a stated reason", () => {
  const rows = [
    ["Label", "Message", "Function"],
    ["more", "I want more, please", "Question"],
    ["", "orphan message", ""],
    ["more", "duplicate of row 2", ""],
    ["x".repeat(61), "too long", ""],
    ["all done", "", "positive"],
  ];

  const { items, skipped } = csv.mapRows(rows, {
    hasHeader: true,
    columns: { label: 0, message: 1, fn: 2 },
  });

  assert.deepEqual(items, [
    { label: "more", message: "I want more, please", fn: "question", symbolQuery: null },
    { label: "all done", message: null, fn: "positive", symbolQuery: null },
  ]);
  assert.deepEqual(skipped.map((row) => [row.line, row.reason]), [
    [3, "no label"],
    [4, "repeated in this list"],
    [5, "label is longer than 60 characters"],
  ]);
  // Line numbers are the file's own, so a user can go and fix the right row.
  assert.equal(skipped[0].line, 3);
});

test("a message identical to the label is not stored twice", () => {
  const { items } = csv.mapRows([["hello", "hello"]], {
    columns: { label: 0, message: 1 },
  });
  assert.equal(items[0].message, null);
});

test("an over-long spoken message is reported, not truncated", () => {
  const { items, skipped } = csv.mapRows([["hi", "x".repeat(201)]], {
    columns: { label: 0, message: 1 },
  });
  assert.deepEqual(items, []);
  assert.match(skipped[0].reason, /spoken message is longer than 200/);
});

test("unmapped columns simply do not contribute", () => {
  const { items } = csv.mapRows([["apple", "ignored", "also ignored"]], {
    columns: { label: 0 },
  });
  assert.deepEqual(items, [
    { label: "apple", message: null, fn: "", symbolQuery: null },
  ]);
});

/* ---------- what will actually fit ---------- */

test("what will not fit is separated before anything is committed", () => {
  const items = ["a", "b", "c", "d"].map((label) => ({ label }));

  const plan = csv.planImport(items, { capacity: 2, existing: [] });

  assert.deepEqual(plan.accepted.map((item) => item.label), ["a", "b"]);
  assert.deepEqual(plan.overflow.map((item) => item.label), ["c", "d"]);
});

test("buttons already on the page are named, and do not consume the room", () => {
  const items = ["apple", "pear", "plum"].map((label) => ({ label }));

  const plan = csv.planImport(items, { capacity: 2, existing: ["Apple"] });

  assert.deepEqual(plan.duplicates.map((item) => item.label), ["apple"]);
  assert.deepEqual(plan.accepted.map((item) => item.label), ["pear", "plum"]);
  assert.deepEqual(plan.overflow, []);
});

test("the 200-button request cap bounds the import even on an empty page set", () => {
  const items = Array.from({ length: 250 }, (_, index) => ({ label: `w${index}` }));

  const plan = csv.planImport(items, { capacity: 1000, maxItems: 200 });

  assert.equal(plan.accepted.length, 200);
  assert.equal(plan.overflow.length, 50);
});
