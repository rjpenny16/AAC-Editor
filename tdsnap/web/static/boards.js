/* The Open Board dialog: boards in from CoughDrop and friends, a page set out.
 *
 * Two ways in, both ending at the ordinary review:
 *
 * - One board's speaking buttons join the word list for the page already open,
 *   exactly like an imported word list (importer.js) — so they work on TD Snap,
 *   Grid 3, and an exported file alike, and go through the same capacity check,
 *   review, and confirm as anything typed.
 * - On an exported file, the whole set becomes new pages linked the way the
 *   boards were. The server plans it, the review screen names every page, and
 *   the confirm step writes it through one validated transaction
 *   (builder.add_linked_pages). Nothing is written before that confirm.
 *
 * One way out: the page set as an .obz, labels, messages, layout, and links
 * only. TD Snap's symbols are licensed content and are never exported, and the
 * dialog says so before anyone relies on the file.
 */

import { state, FUNCTIONS } from "./state.js";
import { $, appendNamedList, setActivity, setBusy } from "./dom.js";
import { api } from "./api.js";
import { existingLabels, functionForSlot, pageCapacity, renderWords } from "./chips.js";
import { planImport } from "./csv.js";
import {
  assignSlots, boardWords, describePlannedPage, describeSkipped,
} from "./openboard.js";
import { titleOf } from "./parents.js";
import { openSlots } from "./preview.js";
import { show } from "./wizard.js";

const MAX_ITEMS = 200;
const UPLOAD_TIMEOUT_MS = 120_000;

const dialog = $("boards-dialog");

/* What the server read from the chosen file: {filename, boardset}, or null. */
let reading = null;
let chosenFile = null;

function setError(message) {
  const box = $("boards-error");
  box.textContent = message || "";
  box.hidden = !message;
}

function pageName() {
  return state.provider === "grid3" ? state.currentPage || "this grid" : titleOf(state.parentId);
}

/* ---------- opening ---------- */

function openBoards() {
  reading = null;
  chosenFile = null;
  $("boards-file").value = "";
  $("boards-file-name").textContent = "";
  $("boards-read").hidden = true;
  $("boards-export-summary").hidden = true;
  $("boards-export-link").hidden = true;
  setError("");
  renderExportIntro();
  dialog.showModal();
  $("boards-file-btn").focus();
}

$("boards-btn").addEventListener("click", openBoards);
$("boards-file-btn").addEventListener("click", () => $("boards-file").click());

$("boards-file").addEventListener("change", async () => {
  const file = $("boards-file").files?.[0];
  if (!file) return;
  chosenFile = file;
  $("boards-file-name").textContent = file.name;
  $("boards-read").hidden = true;
  setError("");
  const body = new FormData();
  body.append("file", file, file.name);
  setActivity(`Reading ${file.name}…`);
  try {
    reading = await api("/api/obf/read", { method: "POST", body }, UPLOAD_TIMEOUT_MS);
    renderBoardPicker();
    refresh();
    $("boards-read").hidden = false;
  } catch (error) {
    reading = null;
    setError(`That file could not be read as Open Board Format. ${error.message}`);
  } finally {
    setActivity();
  }
});

/* ---------- one board into the word list ---------- */

function renderBoardPicker() {
  const select = $("boards-pick");
  select.innerHTML = "";
  reading.boardset.boards.forEach((board, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    const words = board.cells.filter((cell) => !cell.link).length;
    option.textContent = `${board.name} (${words} word${words === 1 ? "" : "s"})`;
    select.append(option);
  });
  $("boards-pick-row").hidden = reading.boardset.boards.length < 2;
}

$("boards-pick").addEventListener("change", refresh);

function chosenBoard() {
  return reading.boardset.boards[Number($("boards-pick").value) || 0];
}

/* Recomputed whenever the choice changes, so the summary always describes the
   board on screen and names everything it will not bring. */
function planWords() {
  const board = chosenBoard();
  const { items, links, fits } = boardWords(board, {
    cols: state.grid.cols, rows: state.grid.rows, functions: FUNCTIONS,
  });
  const plan = planImport(items, {
    capacity: pageCapacity() - state.words.length,
    existing: [...existingLabels(), ...state.words.map((item) => item.label)],
    maxItems: MAX_ITEMS - state.words.length,
  });
  return { board, plan, links, fits };
}

function refresh() {
  const { board, plan, links, fits } = planWords();
  const page = pageName();
  const summary = $("boards-summary");
  summary.innerHTML = "";
  const count = reading.boardset.boards.length;
  const lead = document.createElement("strong");
  lead.textContent = count > 1
    ? `${reading.filename} has ${count} boards, starting from “${reading.boardset.boards[0].name}”.`
    : `${reading.filename} has one board, “${board.name}”.`;
  summary.append(lead);

  const ready = document.createElement("span");
  ready.textContent = plan.accepted.length
    ? `${plan.accepted.length} word${plan.accepted.length === 1 ? "" : "s"} from “${board.name}” `
      + `can go on ${page}${fits ? ", in the same places as on the board" : ""}.`
    : `Nothing from “${board.name}” can be added to ${page}.`;
  summary.append(ready);

  if (state.pageStyle !== "topic" && plan.accepted.some((item) => item.fn)) {
    const note = document.createElement("span");
    note.textContent = "Function colours are used on topic-page rows only; switch the "
      + "page layout to topic-page rows to keep them.";
    summary.append(note);
  }
  if (plan.duplicates.length) {
    appendNamedList(summary, `Already on ${page}, so not added:`,
      plan.duplicates.map((item) => item.label));
  }
  if (plan.overflow.length) {
    appendNamedList(summary, `${page} does not have room for:`,
      plan.overflow.map((item) => item.label));
  }
  if (links.length) {
    appendNamedList(summary,
      "These open another board, so they are not added as words:", links);
  }
  const skipped = reading.boardset.skipped.filter((entry) => entry.board === board.name);
  if (skipped.length) {
    appendNamedList(summary, "Not brought across from this board:",
      skipped.map(describeSkipped));
  }
  reading.boardset.notes.forEach((text) => {
    const note = document.createElement("span");
    note.textContent = text;
    summary.append(note);
  });

  const addWords = $("boards-words-btn");
  addWords.disabled = plan.accepted.length === 0;
  addWords.textContent = plan.accepted.length === 1
    ? `Add 1 word to ${page}`
    : `Add ${plan.accepted.length} words to ${page}`;

  const pages = $("boards-pages-btn");
  const pagesNote = $("boards-pages-note");
  if (state.mode === "file") {
    pages.hidden = false;
    pages.textContent = count === 1
      ? `Add “${board.name}” as a new page`
      : `Add all ${count} boards as linked pages`;
    pagesNote.textContent = `The ${count === 1 ? "new page opens" : "first board opens"} from `
      + `${titleOf(state.parentId)}. You review every page before anything is written.`;
  } else {
    pages.hidden = true;
    pagesNote.textContent = count > 1
      ? "To add every board as its own linked page, open an exported copy of the page "
        + "set with Choose a file on the first screen."
      : "";
  }
}

$("boards-words-btn").addEventListener("click", () => {
  if (!reading) return;
  const { plan } = planWords();
  if (!plan.accepted.length) return;
  const open = openSlots();
  const accepted = plan.accepted.map((item) => ({
    ...item, fn: state.pageStyle === "topic" ? item.fn : "",
  }));
  const slots = assignSlots(accepted, {
    open,
    taken: state.words.map((item) => item.slot).filter(Number.isInteger),
    firstOpen: (fn, used) => {
      const free = open.filter((slot) => !used.has(slot));
      return free.find((slot) => !fn || functionForSlot(slot) === fn) ?? free[0] ?? null;
    },
  });
  accepted.forEach((item, index) => {
    state.words.push({
      label: item.label,
      message: item.message,
      fn: item.fn,
      slot: slots[index],
      symbol: true,
      symbolQuery: "",
    });
  });
  // Unsaved work from here on, like anything typed: the review step and the
  // leave-warning both apply.
  state.pendingEdit = null;
  renderWords();
  dialog.close("imported");
});

/* ---------- a whole set as linked pages (exported files) ---------- */

$("boards-pages-btn").addEventListener("click", async () => {
  if (!reading || !chosenFile || state.mode !== "file") return;
  const button = $("boards-pages-btn");
  const body = new FormData();
  body.append("file", chosenFile, chosenFile.name);
  body.append("parent_page_id", String(state.parentId));
  setError("");
  setBusy(button, true, "Planning the pages…");
  try {
    const data = await api(
      `/api/pageset/${encodeURIComponent(state.sessionId)}/boards`,
      { method: "POST", body },
      UPLOAD_TIMEOUT_MS,
    );
    dialog.close("reviewing");
    prepareBoardsReview(data);
  } catch (error) {
    setError(`These boards can’t be added yet. ${error.message}`);
  } finally {
    setBusy(button, false);
  }
});

function appendRow(list, heading, detail) {
  const row = document.createElement("li");
  const label = document.createElement("strong");
  label.textContent = heading;
  row.append(label);
  if (detail) {
    const text = document.createElement("span");
    text.textContent = detail;
    row.append(text);
  }
  list.append(row);
}

/* The ordinary review screen, filled with the plan: every page it will create,
   what each holds, and — in the warning box — everything the file had that the
   page set will not. The confirm button posts only the fingerprint; the server
   re-plans from what it kept and refuses if anything moved since. */
function prepareBoardsReview(data) {
  const { plan } = data;
  const root = plan.pages[0];
  const parentTitle = plan.parent.title;
  const { pages, buttons, links } = plan.counts;
  state.pendingEdit = Object.freeze({
    kind: "boards",
    operation: "new",
    path: `/api/pageset/${encodeURIComponent(state.sessionId)}/boards/apply`,
    payload: Object.freeze({ fingerprint: data.fingerprint }),
    title: root.title,
    parentTitle,
    displayTitle: root.title,
    knownPageTitles: Object.freeze([]),
  });

  const action = pages === 1
    ? `Create ${root.title} from ${data.filename}`
    : `Create ${pages} linked pages from ${data.filename}`;
  $("result-eyebrow").textContent = "Check";
  $("result-heading").textContent = pages === 1
    ? "Check the imported page before it is added"
    : `Check all ${pages} imported pages before they are added`;
  $("result-sub").textContent =
    "Every page this import creates is named below, and so is everything it leaves out. "
    + "Nothing changes until you confirm.";
  $("review-state").hidden = false;
  $("success-state").hidden = true;
  $("review-action").textContent = action;
  $("review-target").textContent = `${root.title}, found from ${parentTitle}`;
  $("review-count").textContent = [
    `${pages} page${pages === 1 ? "" : "s"}`,
    `${buttons} button${buttons === 1 ? "" : "s"}`,
    links ? `${links} link${links === 1 ? "" : "s"}` : "",
  ].filter(Boolean).join(" · ");
  $("review-placement").textContent = plan.pages.some((page) => page.rearranged)
    ? "Each board’s own layout, or reading order where a board is bigger than this page set"
    : "Each board’s own layout";
  $("confirm-update-label").textContent = pages === 1
    ? `Create ${root.title}`
    : `Create ${pages} pages`;
  $("review-error").hidden = true;
  $("review-error").innerHTML = "";

  const list = $("review-items");
  list.innerHTML = "";
  $("review-items-wrap").hidden = false;
  $("review-items-wrap").querySelector("h3").textContent = "Pages to create";
  plan.pages.forEach((page) => appendRow(list, page.title, describePlannedPage(page)));

  ["review-changes-wrap", "review-moves-wrap", "review-removals-wrap",
    "review-placement-section", "review-queue-wrap"].forEach((id) => {
    $(id).hidden = true;
  });

  const note = $("review-undo-note");
  note.innerHTML = "";
  const lead = document.createElement("strong");
  lead.textContent = "What does not come across";
  note.append(lead);
  const lines = [
    ...plan.notes,
    "The new pages are only in AAC Editor's edited copy until you save it; your "
      + "original file is never changed.",
  ];
  const noteList = document.createElement("ul");
  lines.forEach((line) => {
    const row = document.createElement("li");
    row.textContent = line;
    noteList.append(row);
  });
  note.append(noteList);
  if (plan.skipped.length) {
    appendNamedList(note, `${plan.skipped.length} button${plan.skipped.length === 1 ? "" : "s"} `
      + "or boards are not imported:", plan.skipped.map(describeSkipped));
  }
  note.hidden = false;

  // An import is its own kind of edit; it is never queued with page edits.
  $("queue-add-btn").hidden = true;
  $("queue-add-note").hidden = true;
  show("review");
}

/* ---------- a page set out ---------- */

function exportPaths() {
  if (state.mode === "file" && state.sessionId) {
    const session = encodeURIComponent(state.sessionId);
    return {
      summary: `/api/pageset/${session}/export`,
      file: `/api/pageset/${session}/export.obz`,
      name: state.filename.replace(/(\.[^.]+)?$/, ".obz"),
    };
  }
  if (state.provider === "tdsnap" && state.connected) {
    const page = state.currentPage ? `?page=${encodeURIComponent(state.currentPage)}` : "";
    return {
      summary: `/api/tdsnap/export${page}`,
      file: `/api/tdsnap/export.obz${page}`,
      name: "TD Snap page set.obz",
    };
  }
  return null;
}

function renderExportIntro() {
  const paths = exportPaths();
  const lead = $("boards-export-lead");
  $("boards-export-check").hidden = !paths;
  if (!paths) {
    lead.textContent = state.provider === "grid3"
      ? "Exporting from Grid 3 is not built. Grid 3 is edited through its own screen, "
        + "and AAC Editor does not read a grid set’s files to export them."
      : "Connect to TD Snap or open an exported file to save it as Open Board.";
    return;
  }
  lead.textContent = state.mode === "file"
    ? "Every page in this file, including the changes made here: labels, what each "
      + "button says, where it sits, and which pages it opens. Symbols are not included."
    : "Every page in the page set TD Snap has open: labels, what each button says, where "
      + "it sits, and which pages it opens. Symbols are not included. TD Snap is only read.";
}

$("boards-export-check").addEventListener("click", async () => {
  const paths = exportPaths();
  if (!paths) return;
  const button = $("boards-export-check");
  const summary = $("boards-export-summary");
  setBusy(button, true, "Reading the page set…");
  try {
    const data = await api(paths.summary);
    summary.innerHTML = "";
    const lead = document.createElement("strong");
    lead.textContent = `${data.boards} page${data.boards === 1 ? "" : "s"}, `
      + `${data.buttons} button${data.buttons === 1 ? "" : "s"}, and `
      + `${data.links} link${data.links === 1 ? "" : "s"}, starting from “${data.root}”.`;
    summary.append(lead);
    data.notes.forEach((text) => {
      const note = document.createElement("span");
      note.textContent = text;
      summary.append(note);
    });
    if (data.skipped.length) {
      appendNamedList(summary, `${data.skipped.length} not exported:`,
        data.skipped.map(describeSkipped));
    }
    summary.hidden = false;
    const link = $("boards-export-link");
    link.href = paths.file;
    link.download = paths.name;
    link.hidden = false;
  } catch (error) {
    summary.innerHTML = "";
    const lead = document.createElement("strong");
    lead.textContent = `The page set could not be exported. ${error.message}`;
    summary.append(lead);
    summary.hidden = false;
  } finally {
    setBusy(button, false);
  }
});

export { openBoards, prepareBoardsReview };
