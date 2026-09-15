/* Reading a spreadsheet's worth of vocabulary.
 *
 * The chip box already accepts a comma-separated paste, which is fine for six
 * words and useless for the way this work actually arrives: a column of labels
 * next to a column of full sentences, exported from a spreadsheet somebody
 * spent an hour on. That paste path splits on every comma, so "I want more,
 * please" becomes two buttons — exactly the content this phase is for.
 *
 * So this module reads delimited text properly: quoted fields, embedded
 * delimiters and newlines, doubled quotes. It is pure — no DOM, no app state,
 * no fetch — because what a clinician's file turns into has to be checkable
 * without a browser, and because the answer must never depend on which screen
 * the wizard is showing.
 *
 * Nothing here decides what gets written. It produces rows and a reading of
 * them; capacity, duplicates, and the review step stay where they already are.
 */

/* Tab first: a spreadsheet copied to the clipboard is tab-separated, and it is
   the one delimiter that never appears inside ordinary AAC vocabulary. Comma
   and semicolon both do ("I want more, please"), so they are only chosen when
   they actually structure the text — the same count on every line. */
const DELIMITERS = ["\t", ",", ";"];

/* A spreadsheet's own quoting rules (RFC 4180): fields may be wrapped in
   double quotes, a doubled quote inside one is a literal quote, and a quoted
   field may contain the delimiter or a line break. */
function parseDelimited(text, delimiter) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  let index = 0;
  const source = String(text || "").replace(/\r\n?/g, "\n");

  const endField = () => {
    row.push(field);
    field = "";
  };
  const endRow = () => {
    endField();
    rows.push(row);
    row = [];
  };

  while (index < source.length) {
    const char = source[index];
    if (quoted) {
      if (char === '"') {
        if (source[index + 1] === '"') {
          field += '"';
          index += 2;
          continue;
        }
        quoted = false;
        index += 1;
        continue;
      }
      field += char;
      index += 1;
      continue;
    }
    if (char === '"' && field === "") {
      quoted = true;
      index += 1;
      continue;
    }
    if (char === delimiter) {
      endField();
      index += 1;
      continue;
    }
    if (char === "\n") {
      endRow();
      index += 1;
      continue;
    }
    field += char;
    index += 1;
  }
  // A trailing newline ends the last row; anything else still holds a field.
  if (field !== "" || row.length) endRow();
  return rows.filter((entry) => entry.some((value) => value.trim()));
}

/* Which delimiter structures this text: the one that splits every line into
   the same number of fields, most columns winning. A single column of words
   has no delimiter at all, and saying so beats guessing one and splitting a
   phrase in half. */
function detectDelimiter(text) {
  let best = null;
  for (const delimiter of DELIMITERS) {
    const rows = parseDelimited(text, delimiter);
    if (!rows.length) continue;
    const widths = rows.map((row) => row.length);
    const columns = widths[0];
    if (columns < 2 || !widths.every((width) => width === columns)) continue;
    if (!best || columns > best.columns) best = { delimiter, columns };
  }
  return best ? best.delimiter : null;
}

/* Column headings a spreadsheet is likely to carry, in the words people
   actually use. Matching is loose on purpose — "Spoken message", "message",
   and "What it says" all mean the same column — but it only ever *suggests* a
   mapping, which the user then sees and can change. */
const HEADINGS = {
  label: ["label", "button", "word", "text", "name", "title", "vocab", "vocabulary"],
  message: ["message", "says", "speaks", "spoken", "phrase", "sentence", "speech"],
  fn: ["function", "type", "row", "category", "kind", "communicative"],
  symbolQuery: ["symbol", "icon", "picture", "image", "pcs"],
};

const FUNCTION_NAMES = ["question", "comment", "positive", "negative", "personal"];

function normalize(value) {
  return String(value || "").trim().toLocaleLowerCase();
}

/* A cell naming one of the five clinical functions, or "" for none. Anything
   unrecognized is "" rather than a guess: putting a phrase in the wrong
   communicative row is a clinical error, not a formatting one. */
function readFunction(value) {
  const text = normalize(value);
  if (!text) return "";
  const exact = FUNCTION_NAMES.find((name) => name === text);
  if (exact) return exact;
  // "Questions", "question row", "q" — common shorthands for the same thing.
  return FUNCTION_NAMES.find(
    (name) => text.startsWith(name) || (text.length === 1 && name.startsWith(text)),
  ) || "";
}

/* Does the first row name the columns, or is it already vocabulary? A header
   is assumed only when a cell actually matches a known heading — otherwise the
   first word of somebody's list would silently disappear. */
function looksLikeHeader(row) {
  const cells = row.map(normalize);
  return cells.some((cell) =>
    Object.values(HEADINGS).some((names) => names.includes(cell)),
  );
}

/* Suggest which column is which. Returns an index per field, or null when
   nothing matched — the caller shows these as the starting point of a mapping
   the user confirms, never as a decision already made. */
function guessColumns(header) {
  const cells = (header || []).map(normalize);
  const taken = new Set();
  const pick = (names) => {
    const index = cells.findIndex(
      (cell, position) =>
        !taken.has(position) && names.some((name) => cell.includes(name)),
    );
    if (index >= 0) taken.add(index);
    return index >= 0 ? index : null;
  };
  // Label last: "message" contains no label word, but a bare "text" heading
  // would match both, and the more specific columns should claim theirs first.
  const message = pick(HEADINGS.message);
  const fn = pick(HEADINGS.fn);
  const symbolQuery = pick(HEADINGS.symbolQuery);
  const label = pick(HEADINGS.label);
  return { label, message, fn, symbolQuery };
}

/* Read *text* far enough to show the user what it holds: the delimiter, the
   rows, whether the first names the columns, and a suggested mapping. */
function readTable(text) {
  const delimiter = detectDelimiter(text);
  // With no delimiter this is one column — every line is a label, which is the
  // single most common shape a word list arrives in.
  const rows = delimiter
    ? parseDelimited(text, delimiter)
    : String(text || "")
      .replace(/\r\n?/g, "\n")
      .split("\n")
      .map((line) => [line])
      .filter(([line]) => line.trim());
  const hasHeader = rows.length > 1 && looksLikeHeader(rows[0]);
  const columns = hasHeader
    ? guessColumns(rows[0])
    : { label: rows.length ? 0 : null, message: null, fn: null, symbolQuery: null };
  return { delimiter, rows, hasHeader, columns };
}

/* Turn the rows into buttons, under the mapping the user confirmed.
 *
 * Every row is accounted for: one that yields a button is in `items`, one that
 * cannot is in `skipped` with the reason in plain words. A row is never
 * silently dropped, because "I pasted 60 and got 54" with no explanation is
 * exactly the kind of quiet loss this app exists to avoid.
 *
 * `limits` carries the caps the request will be held to anyway — the label and
 * message lengths the server enforces — so an over-long cell is reported here,
 * while the user can still fix it, rather than at the confirm step.
 */
function mapRows(rows, { hasHeader = false, columns = {}, limits = {} } = {}) {
  const { maxLabel = 60, maxMessage = 200 } = limits;
  const body = hasHeader ? rows.slice(1) : rows;
  const items = [];
  const skipped = [];
  const seen = new Set();

  body.forEach((row, index) => {
    const line = index + (hasHeader ? 2 : 1);
    const cell = (position) =>
      typeof position === "number" ? String(row[position] ?? "").trim() : "";
    const label = cell(columns.label);
    if (!label) {
      skipped.push({ line, label: cell(columns.message) || "", reason: "no label" });
      return;
    }
    if (label.length > maxLabel) {
      skipped.push({ line, label, reason: `label is longer than ${maxLabel} characters` });
      return;
    }
    const folded = label.toLocaleLowerCase();
    if (seen.has(folded)) {
      skipped.push({ line, label, reason: "repeated in this list" });
      return;
    }
    const message = cell(columns.message);
    if (message.length > maxMessage) {
      skipped.push({
        line, label, reason: `spoken message is longer than ${maxMessage} characters`,
      });
      return;
    }
    seen.add(folded);
    items.push({
      label,
      // A message identical to the label is how the app already represents
      // "just speak the label", so it is not stored twice.
      message: message && message !== label ? message : null,
      fn: readFunction(cell(columns.fn)),
      symbolQuery: cell(columns.symbolQuery) || null,
    });
  });

  return { items, skipped };
}

/* What the import will actually do, given the room available.
 *
 * Splitting this out from `mapRows` keeps the reading of the file separate
 * from the state of the page: the same file imported onto a fuller page fits
 * fewer buttons, and the user is told that before confirming rather than after.
 */
function planImport(items, { capacity = 0, existing = [], maxItems = 200 } = {}) {
  const present = new Set(existing.map((label) => String(label || "").toLocaleLowerCase()));
  const duplicates = [];
  const candidates = [];
  items.forEach((item) => {
    if (present.has(item.label.toLocaleLowerCase())) duplicates.push(item);
    else candidates.push(item);
  });
  const room = Math.max(0, Math.min(capacity, maxItems));
  return {
    accepted: candidates.slice(0, room),
    overflow: candidates.slice(room),
    duplicates,
  };
}

export {
  detectDelimiter,
  guessColumns,
  mapRows,
  parseDelimited,
  planImport,
  readFunction,
  readTable,
};
