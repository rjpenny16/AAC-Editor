/* Open Board Format: bring a board in, take a page set out.
 *
 * Importing reads an .obf or .obz on the server and hands back boards as
 * pages; the chosen board's buttons land in the chip box exactly as typed
 * words would, so they go through the same review, placement and confirm.
 * A board set with more than one board asks which board to bring in — each
 * one becomes its own page through the ordinary flow, and the buttons that
 * open other boards are named so they can be linked once those pages exist.
 *
 * Exporting is a plain download: every page of the open page set as one
 * .obz, labels, spoken text, layout, function colours and links included,
 * symbols not — they are licensed content and never leave the page set.
 */

import { state, FUNCTIONS } from "./state.js";
import { $ } from "./dom.js";
import { api } from "./api.js";
import { firstAvailableSlot, pageCapacity, renderWords } from "./chips.js";
import { planImport } from "./csv.js";

const MAX_ITEMS = 200;
let imported = null;

const dialog = $("board-dialog");
const picker = $("board-picker");
const summary = $("board-summary");
const errorBox = $("board-error");

function setError(message) {
  errorBox.textContent = message;
  errorBox.hidden = !message;
}

/* ---------- import ---------- */

$("import-board-btn").addEventListener("click", () => $("import-board-file").click());

$("import-board-file").addEventListener("change", async (event) => {
  const [file] = event.target.files || [];
  event.target.value = "";
  if (!file) return;
  const body = new FormData();
  body.append("file", file, file.name);
  imported = null;
  setError("");
  try {
    imported = await api("/api/obf/import", { method: "POST", body }, 0);
  } catch (error) {
    imported = null;
    summary.innerHTML = "";
    setError(`That board could not be read. ${error.message}`);
    dialog.showModal();
    return;
  }
  renderPicker();
  dialog.showModal();
});

function renderPicker() {
  picker.innerHTML = "";
  imported.pages.forEach((page, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    const count = page.items.length;
    option.textContent = `${page.title} — ${count} button${count === 1 ? "" : "s"}` +
      (index === imported.root && imported.pages.length > 1 ? " (start board)" : "");
    picker.append(option);
  });
  picker.value = String(imported.root || 0);
  $("board-picker-field").hidden = imported.pages.length < 2;
  $("board-dialog-title").textContent = imported.pages.length > 1
    ? `Which board from ${imported.filename}?`
    : `Import ${imported.pages[0].title}`;
  renderSummary();
}

function chosenPage() {
  return imported.pages[Number(picker.value) || 0];
}

function plan(page) {
  return planImport(page.items, {
    capacity: pageCapacity() - state.words.length,
    existing: [
      ...state.existingButtons.map((button) => button.label),
      ...state.words.map((item) => item.label),
    ],
    maxItems: MAX_ITEMS - state.words.length,
  });
}

function renderSummary() {
  const page = chosenPage();
  const { accepted, overflow, duplicates } = plan(page);
  summary.innerHTML = "";
  const lines = [
    `${accepted.length} button${accepted.length === 1 ? "" : "s"} will be added` +
      (accepted.length ? ` from “${page.title}”.` : "."),
  ];
  if (page.grid.cols && page.grid.rows
    && (page.grid.cols !== state.grid.cols || page.grid.rows !== state.grid.rows)) {
    lines.push(
      `The board is ${page.grid.cols}×${page.grid.rows} and this page is ` +
      `${state.grid.cols}×${state.grid.rows}, so buttons take the first open spaces here.`,
    );
  }
  if (duplicates.length) {
    lines.push(`Already here, so skipped: ${duplicates.map((item) => item.label).join(", ")}.`);
  }
  if (overflow.length) {
    lines.push(`No room for ${overflow.length} more: ${overflow.map((item) => item.label).join(", ")}.`);
  }
  if (page.links.length) {
    const named = page.links.map((link) => link.label).join(", ");
    lines.push(
      `${page.links.length} button${page.links.length === 1 ? " opens" : "s open"} other boards ` +
      `(${named}). Import each of those as its own page, then link it from this one.`,
    );
  }
  imported.warnings.forEach((warning) => lines.push(warning));
  lines.forEach((text) => {
    const line = document.createElement("span");
    line.textContent = text;
    summary.append(line);
  });
  $("board-add-btn").disabled = !accepted.length;
}

picker.addEventListener("change", renderSummary);

$("board-add-btn").addEventListener("click", () => {
  if (!imported) return;
  const page = chosenPage();
  const { accepted } = plan(page);
  if (!accepted.length) return;
  const sameGrid = page.grid.cols === state.grid.cols && page.grid.rows === state.grid.rows;
  const open = new Set(state.availableSlots || []);
  state.words.forEach((item) => open.delete(item.slot));
  accepted.forEach((item) => {
    const fn = state.pageStyle === "topic" && item.function in FUNCTIONS ? item.function : "";
    // A board the same size as this page keeps its layout where the cell is
    // free; anything else takes the first open space, like a typed word.
    const keep = sameGrid && Number.isInteger(item.slot) && open.has(item.slot);
    const slot = keep ? item.slot : firstAvailableSlot(fn);
    open.delete(slot);
    state.words.push({
      label: item.label,
      message: item.message || null,
      fn,
      slot,
      symbol: true,
      symbolQuery: null,
    });
  });
  state.pendingEdit = null;
  renderWords();
  dialog.close("imported");
});

/* ---------- export ---------- */

/* Where the whole open page set can be downloaded as an .obz, or nothing when
   the provider cannot offer one (Grid 3 has no page set file to read). */
function exportHref() {
  if (state.mode === "file" && state.sessionId) {
    return `/api/pageset/${encodeURIComponent(state.sessionId)}/obz`;
  }
  if (state.mode === "live" && state.provider === "tdsnap" && state.connected) {
    return `/api/tdsnap/obz?page=${encodeURIComponent(state.currentPage || "")}`;
  }
  return "";
}

function syncExportLink() {
  const link = $("export-obz-link");
  const href = exportHref();
  link.hidden = !href;
  if (href) link.href = href;
  else link.removeAttribute("href");
}

// Read the state at the moment the menu opens: whichever provider or session
// is current then is the one the download would cover.
document.querySelectorAll(".more-options").forEach((menu) => {
  menu.addEventListener("toggle", syncExportLink);
});

export { syncExportLink };
