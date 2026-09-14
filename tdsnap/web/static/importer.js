/* The import dialog: a spreadsheet's worth of vocabulary, reviewed before it
 * lands in the word list.
 *
 * csv.js does the reading and knows nothing about the app; this module is the
 * other half — it holds the dialog together, maps columns to state.words, and
 * above all it *reports what will not fit before anything is added*. A
 * clinician pasting 60 words onto a page with room for 12 finds that out here,
 * with the 48 named, rather than discovering a silently truncated list later.
 *
 * Nothing here writes to a page set. The imported buttons land in the same
 * state.words the chip box fills, and go through the same review and confirm
 * step as anything typed by hand.
 */

import { state, FUNCTIONS } from "./state.js";
import { $, appendNamedList } from "./dom.js";
import { firstAvailableSlot, pageCapacity, renderWords } from "./chips.js";
import { mapRows, planImport, readTable } from "./csv.js";
import { titleOf } from "./parents.js";
import { elsewhereNote } from "./vocabulary.js";

/* Mirrors the server's own bounds (MAX_ITEMS, MAX_LABEL_CHARS,
   MAX_MESSAGE_CHARS in web/server.py). Checking them here means an over-long
   row is named while the user can still fix it, instead of failing the whole
   request at the confirm step. */
const MAX_ITEMS = 200;
const LIMITS = { maxLabel: 60, maxMessage: 200 };

const COLUMN_FIELDS = [
  ["label", "Button label"],
  ["message", "What it says"],
  ["fn", "Topic-page row"],
  ["symbolQuery", "Symbol search words"],
];

const dialog = $("import-dialog");
const textarea = $("import-text");

/* The reading of whatever is currently in the box, or null when there is
   nothing to read. Held so the column pickers and the summary agree. */
let table = null;

function setError(message) {
  const box = $("import-error");
  box.textContent = message || "";
  box.hidden = !message;
}

/* ---------- opening ---------- */

function openImport() {
  textarea.value = "";
  $("import-file").value = "";
  $("import-file-name").textContent = "";
  $("import-mapping").hidden = true;
  $("import-summary").hidden = true;
  $("import-add-btn").disabled = true;
  table = null;
  setError("");
  dialog.showModal();
  textarea.focus();
}

$("import-list-btn").addEventListener("click", openImport);
$("import-file-btn").addEventListener("click", () => $("import-file").click());

$("import-file").addEventListener("change", async () => {
  const file = $("import-file").files?.[0];
  if (!file) return;
  try {
    // Read in the browser: a word list is page-set content, and there is no
    // reason for it to reach even the local server before the user has seen
    // what it holds.
    textarea.value = await file.text();
    $("import-file-name").textContent = file.name;
    readInput();
  } catch (error) {
    setError(`That file could not be read. ${error.message}`);
  }
});

textarea.addEventListener("input", readInput);

/* ---------- reading and mapping ---------- */

function readInput() {
  setError("");
  const text = textarea.value;
  if (!text.trim()) {
    table = null;
    $("import-mapping").hidden = true;
    $("import-summary").hidden = true;
    $("import-add-btn").disabled = true;
    return;
  }
  table = readTable(text);
  $("import-has-header").checked = table.hasHeader;
  renderColumnPickers();
  $("import-mapping").hidden = false;
  refresh();
}

/* One picker per column in the file, each naming what that column is for.
   Built from the file rather than from a fixed list, because a spreadsheet
   with six columns should show six — including the ones being ignored. */
function renderColumnPickers() {
  const wrap = $("import-columns");
  wrap.innerHTML = "";
  const width = Math.max(...table.rows.map((row) => row.length));
  const header = table.hasHeader ? table.rows[0] : null;

  for (let index = 0; index < width; index += 1) {
    const field = document.createElement("div");
    field.className = "field import-column";
    const select = document.createElement("select");
    select.id = `import-column-${index}`;
    const label = document.createElement("label");
    label.htmlFor = select.id;
    label.textContent = header?.[index]?.trim() || `Column ${index + 1}`;

    const ignore = document.createElement("option");
    ignore.value = "";
    ignore.textContent = "Ignore this column";
    select.append(ignore);
    COLUMN_FIELDS.forEach(([key, name]) => {
      const option = document.createElement("option");
      option.value = key;
      option.textContent = name;
      option.selected = table.columns[key] === index;
      select.append(option);
    });
    select.addEventListener("change", () => {
      // One column per field: choosing a field takes it from whichever column
      // had it, so two columns can never both claim to be the label.
      const chosen = select.value;
      if (chosen) {
        wrap.querySelectorAll("select").forEach((other) => {
          if (other !== select && other.value === chosen) other.value = "";
        });
      }
      refresh();
    });
    field.append(label, select);
    wrap.append(field);
  }
}

function chosenColumns() {
  const columns = { label: null, message: null, fn: null, symbolQuery: null };
  $("import-columns").querySelectorAll("select").forEach((select, index) => {
    if (select.value) columns[select.value] = index;
  });
  return columns;
}

/* ---------- what will happen ---------- */

/* Recomputed on every change, so the summary under the dialog always describes
   the mapping currently on screen. */
function refresh() {
  if (!table) return;
  const columns = chosenColumns();
  const summary = $("import-summary");
  summary.innerHTML = "";
  summary.hidden = false;

  if (columns.label === null) {
    $("import-add-btn").disabled = true;
    const note = document.createElement("strong");
    note.textContent = "Choose which column holds the button label.";
    summary.append(note);
    renderPreview(columns);
    return;
  }

  const { items, skipped } = mapRows(table.rows, {
    hasHeader: $("import-has-header").checked,
    columns,
    limits: LIMITS,
  });
  const plan = planImport(items, {
    capacity: pageCapacity() - state.words.length,
    existing: [
      ...state.existingButtons.map((button) => button.label),
      ...state.words.map((item) => item.label),
    ],
    maxItems: MAX_ITEMS - state.words.length,
  });

  renderPreview(columns);
  renderSummary(plan, skipped, columns);
  $("import-add-btn").disabled = plan.accepted.length === 0;
  $("import-add-btn").textContent = plan.accepted.length === 1
    ? "Add 1 button"
    : `Add ${plan.accepted.length} buttons`;
}

/* The first rows as the mapping reads them — the check that the columns line
   up, made before anything is added rather than after. */
function renderPreview(columns) {
  const preview = $("import-preview");
  preview.innerHTML = "";
  const named = COLUMN_FIELDS.filter(([key]) => columns[key] !== null);
  if (!named.length) return;

  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  named.forEach(([, name]) => {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = name;
    headRow.append(cell);
  });
  head.append(headRow);

  const body = document.createElement("tbody");
  const rows = table.rows.slice($("import-has-header").checked ? 1 : 0,
    ($("import-has-header").checked ? 1 : 0) + 4);
  rows.forEach((row) => {
    const line = document.createElement("tr");
    named.forEach(([key]) => {
      const cell = document.createElement("td");
      cell.textContent = String(row[columns[key]] ?? "").trim();
      line.append(cell);
    });
    body.append(line);
  });
  preview.append(head, body);
}

/* Everything the import will and will not do, in one place and in plain
   words. Each group names its buttons rather than counting them: "48 didn't
   fit" sends somebody hunting, "these 48 didn't fit" does not. */
function renderSummary(plan, skipped, columns) {
  const summary = $("import-summary");
  const page = titleOf(state.parentId);
  const lead = document.createElement("strong");
  lead.textContent = plan.accepted.length
    ? `${plan.accepted.length} button${plan.accepted.length === 1 ? "" : "s"} ready to add.`
    : "Nothing in this list can be added yet.";
  summary.append(lead);

  // A function column only means something on a topic page. Saying so beats
  // importing the file and leaving the user to wonder where their rows went.
  if (columns.fn !== null && state.pageStyle !== "topic") {
    const note = document.createElement("span");
    note.textContent =
      "Topic-page rows are ignored on a standard page. Switch the layout to " +
      "topic-page rows under More options if you want them used.";
    summary.append(note);
  }

  if (plan.duplicates.length) {
    appendNamedList(
      summary,
      `Already on ${page}, so ${plan.duplicates.length === 1 ? "it is" : "they are"} not imported:`,
      plan.duplicates.map((item) => item.label),
    );
  }
  if (plan.overflow.length) {
    appendNamedList(
      summary,
      `${page} does not have room for ${plan.overflow.length} of these. ` +
      "Free some space, or import them onto another page afterwards:",
      plan.overflow.map((item) => item.label),
    );
  }
  // Not a reason to skip anything — just worth knowing before a 60-word import
  // quietly doubles vocabulary that already exists somewhere else.
  const elsewhere = elsewhereNote(plan.accepted.map((item) => item.label), page);
  if (elsewhere) {
    const note = document.createElement("span");
    note.textContent = elsewhere;
    summary.append(note);
  }
  if (skipped.length) {
    const list = document.createElement("ul");
    skipped.forEach((row) => {
      const entry = document.createElement("li");
      entry.textContent = row.label
        ? `Row ${row.line}, “${row.label}” — ${row.reason}`
        : `Row ${row.line} — ${row.reason}`;
      list.append(entry);
    });
    const note = document.createElement("span");
    note.textContent = `${skipped.length} row${skipped.length === 1 ? "" : "s"} could not become a button:`;
    summary.append(note, list);
  }
}

$("import-has-header").addEventListener("change", () => {
  if (!table) return;
  renderColumnPickers();
  refresh();
});

/* ---------- adding ---------- */

$("import-add-btn").addEventListener("click", () => {
  if (!table) return;
  const columns = chosenColumns();
  const { items } = mapRows(table.rows, {
    hasHeader: $("import-has-header").checked,
    columns,
    limits: LIMITS,
  });
  const plan = planImport(items, {
    capacity: pageCapacity() - state.words.length,
    existing: [
      ...state.existingButtons.map((button) => button.label),
      ...state.words.map((item) => item.label),
    ],
    maxItems: MAX_ITEMS - state.words.length,
  });
  if (!plan.accepted.length) return;

  plan.accepted.forEach((item) => {
    const fn = state.pageStyle === "topic" && item.fn in FUNCTIONS ? item.fn : "";
    state.words.push({
      label: item.label,
      message: item.message,
      fn,
      slot: firstAvailableSlot(fn),
      symbol: true,
      symbolQuery: item.symbolQuery,
    });
  });
  // The imported list is unsaved work like anything else typed here, so the
  // review step and the leave-warning both apply from now on.
  state.pendingEdit = null;
  renderWords();
  dialog.close("imported");
});

export { openImport };
