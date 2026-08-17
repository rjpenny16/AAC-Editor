/* Composing the word list: the chip box and the per-chip editor dialog.
 *
 * state.words is the only copy of this work until an edit is applied, which is
 * why leaving the page while it is non-empty prompts a warning.
 */

import { state, FUNCTIONS, TOPIC_FUNCTIONS } from "./state.js";
import { $, appendNamedList } from "./dom.js";
import {
  changeFor, editSummary, isRemoved, keepButton, moveFrom, planChange, planRemoval,
  undoAvailable,
} from "./edits.js";
import { inferPhraseFunction } from "./phrases.js";
import { titleOf } from "./parents.js";
import { openSlots, renderPlacementOrder, renderPreview } from "./preview.js";
import { createUndoStack } from "./undo.js";
import { clearStepError, setActiveFn } from "./wizard.js";

/* ---------- step 2: words (chip editor) ---------- */

const chipbox = $("chipbox");
const wordInput = $("word-input");

/* Removing a chip and "Arrange automatically" are the two actions here that
   discard something — a label, a message, a function assignment — with no
   other way back. Everything else (typing, editing a chip's text) is either
   non-destructive or already reversible by typing again. */
const undoStack = createUndoStack();

function snapshotWords() {
  return state.words.map((item) => ({ ...item }));
}

function undoLastRemoval() {
  if (!undoStack.canUndo()) return false;
  state.words = undoStack.pop();
  renderWords();
  return true;
}

const undoBtn = $("undo-remove-btn");
if (undoBtn) {
  undoBtn.addEventListener("click", undoLastRemoval);
  chipbox.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
      event.preventDefault();
      undoLastRemoval();
    }
  });
}

function updateTopicInputRow() {
  if (!chipbox || !wordInput) return;
  if (!chipbox.classList.contains("topic-mode")) {
    if (wordInput.parentElement !== chipbox) chipbox.append(wordInput);
    return;
  }
  const fn = TOPIC_FUNCTIONS.includes(state.activeFn) ? state.activeFn : "question";
  wordInput.dataset.fn = fn;
  const row = chipbox.querySelector(`[data-row-phrases="${fn}"]`);
  if (row) row.append(wordInput);
  document.querySelectorAll(".topic-row-add").forEach((button) => {
    button.classList.toggle("active", button.dataset.addFn === fn);
  });
}

document.querySelectorAll(".topic-row-add").forEach((button) => {
  button.addEventListener("click", () => {
    wordInput.dataset.forced = button.dataset.addFn;
    setActiveFn(button.dataset.addFn);
    wordInput.focus();
  });
});
wordInput.addEventListener("focus", () => chipbox.classList.add("input-active"));
wordInput.addEventListener("blur", () => chipbox.classList.remove("input-active"));

chipbox.addEventListener("click", (event) => {
  if (event.target === chipbox) wordInput.focus();
});

/* Clear the input BEFORE processing: when a batch fills the grid,
   renderWords() disables the still-focused input, which fires blur
   synchronously — with the value still set, the batch would be
   processed a second time. */
function takeWordInput() {
  const value = wordInput.value;
  wordInput.value = "";
  if (value.trim()) {
    addWords(value, wordInput.dataset.forced || null);
    if (state.pageStyle === "topic") wordInput.blur();
  }
}

wordInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === ",") {
    event.preventDefault();
    takeWordInput();
  } else if (event.key === "Backspace" && !wordInput.value && state.words.length) {
    undoStack.push(snapshotWords());
    state.words.pop();
    renderWords();
  }
});
wordInput.addEventListener("blur", takeWordInput);
$("word-add-btn").addEventListener("click", () => {
  takeWordInput();
  wordInput.focus();
});
wordInput.addEventListener("paste", (event) => {
  const text = (event.clipboardData || window.clipboardData).getData("text");
  if (text && text.includes(",")) {
    event.preventDefault();
    addWords(text);
  }
});

function firstAvailableSlot(preferredFn = "") {
  const used = new Set(state.words.map((item) => item.slot).filter(Number.isInteger));
  const available = openSlots().filter((slot) => !used.has(slot));
  return available.find((slot) => !preferredFn || functionForSlot(slot) === preferredFn)
    ?? available[0]
    ?? state.grid.cols * state.grid.rows - 1;
}

/* How many new buttons fit in total, pending edits to existing buttons
   included — retiring or moving one makes room in the same edit. Counts the
   cells planned buttons already sit in, since those are the same space. */
function pageCapacity() {
  return openSlots().length;
}

function topicRowFunctions(rows) {
  const base = ["question", "comment", "positive", "negative", "personal"];
  if (rows <= 1) return ["question"];
  if (rows < base.length) return [...base.slice(0, rows - 1), "personal"];
  const layout = [...base];
  if (rows > 5) layout.splice(2, 0, "comment");
  while (layout.length < rows) layout.push("personal");
  return layout.slice(0, rows);
}

function functionForSlot(slot) {
  const row = Math.floor((Number(slot) || 0) / state.grid.cols);
  return topicRowFunctions(state.grid.rows)[Math.min(row, state.grid.rows - 1)];
}

function autoFormatTopicRows() {
  if (state.words.length) undoStack.push(snapshotWords());
  state.words.forEach((item) => {
    item.fn = inferPhraseFunction(item.message || item.label, item.fn);
    item.slot = null;
  });
  state.words.forEach((item) => {
    item.slot = firstAvailableSlot(item.fn);
  });
  renderWords();
}

function addWords(raw, forcedFn = null) {
  clearStepError("items");
  state.pendingEdit = null;
  const capacity = pageCapacity();
  const duplicates = [];
  const overflow = [];
  raw
    .split(",")
    .map((word) => word.trim())
    .filter(Boolean)
    .forEach((word) => {
      const normalized = word.toLocaleLowerCase();
      const alreadyPlanned = state.words.some(
        (item) => item.label.toLocaleLowerCase() === normalized
      );
      const alreadyPresent = state.existingButtons.some(
        (item) => String(item.label || "").toLocaleLowerCase() === normalized
      );
      if (alreadyPlanned || alreadyPresent) {
        duplicates.push(word);
      } else if (state.words.length >= capacity) {
        overflow.push(word);
      } else {
        const fn = state.pageStyle === "topic"
          ? forcedFn || (state.autoTopicRows
            ? inferPhraseFunction(word)
            : state.activeFn)
          : "";
        const slot = firstAvailableSlot(fn);
        state.words.push({
          label: word, message: null, fn, slot, symbol: true, symbolQuery: null,
        });
      }
    });
  renderSkippedFeedback(duplicates, overflow);
  renderWords();
}


function renderSkippedFeedback(duplicates, overflow) {
  const note = $("chip-note");
  note.innerHTML = "";
  const destination = titleOf(state.parentId);
  if (duplicates.length === 1) {
    const text = document.createElement("span");
    text.textContent = `${duplicates[0]} is already on ${destination}, so it wasn’t added.`;
    note.append(text);
  } else if (duplicates.length) {
    appendNamedList(note, `These buttons are already on ${destination}, so they weren’t added:`, duplicates);
  }
  if (overflow.length) {
    if (note.childNodes.length) note.append(document.createElement("br"));
    appendNamedList(
      note,
      `${destination} is full. Remove a planned button or choose another page before adding:`,
      overflow
    );
  }
}

const PHRASE_MARK_SVG =
  '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
  'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<path d="M12 6v12M7 9v6M2.5 11v2M17 9v6M21.5 11v2"/></svg>';

function renderWords() {
  chipbox.querySelectorAll(".chip").forEach((chip) => chip.remove());
  state.words.forEach((item, index) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    if (item.fn) {
      chip.dataset.fn = item.fn;
      chip.style.setProperty("--fn-color", FUNCTIONS[item.fn].color);
    }

    const body = document.createElement("button");
    body.type = "button";
    body.className = "chip-body";
    const spoken = item.message || item.label;
    const symbolNote = item.symbol === false
      ? ", no symbol"
      : item.symbolQuery ? `, symbol search “${item.symbolQuery}”` : "";
    body.setAttribute(
      "aria-label",
      `Edit ${item.label}${item.fn ? `, ${FUNCTIONS[item.fn].name}` : ""}` +
        (item.message ? `, speaks “${spoken}”` : "") + symbolNote
    );
    body.title = [
      item.message ? `Speaks: “${item.message}”` : "",
      item.symbol === false ? "No symbol" : item.symbolQuery ? `Symbol: “${item.symbolQuery}”` : "",
    ].filter(Boolean).join(" · ") || "Click to edit";
    if (item.fn) {
      const dot = document.createElement("span");
      dot.className = "chip-dot";
      body.append(dot);
    }
    const label = document.createElement("span");
    label.textContent = item.label;
    body.append(label);
    if (item.message) {
      const mark = document.createElement("span");
      mark.className = "chip-phrase-mark";
      mark.innerHTML = PHRASE_MARK_SVG;
      body.append(mark);
    }
    body.addEventListener("click", () => openChipEditor(index));

    const remove = document.createElement("button");
    remove.type = "button";
    remove.setAttribute("aria-label", `Remove ${item.label}`);
    remove.textContent = "×";
    remove.addEventListener("click", () => {
      undoStack.push(snapshotWords());
      state.words.splice(index, 1);
      $("chip-note").textContent = "";
      renderWords();
    });
    chip.append(body, remove);
    if (state.pageStyle === "topic" && item.fn) {
      const row = chipbox.querySelector(`[data-row-phrases="${item.fn}"]`);
      (row || chipbox).append(chip);
    } else {
      chipbox.insertBefore(chip, wordInput);
    }
  });

  const capacity = pageCapacity();
  const meter = $("capacity");
  const left = Math.max(0, capacity - state.words.length);
  meter.textContent = capacity === 0
    ? "Page is full"
    : state.words.length === 0
      ? `${capacity} space${capacity === 1 ? "" : "s"} available`
      : `${state.words.length} added · ${left} space${left === 1 ? "" : "s"} left`;
  meter.classList.toggle("full", state.words.length >= capacity);
  wordInput.disabled = state.words.length >= capacity;
  $("word-add-btn").disabled = state.words.length >= capacity;
  wordInput.placeholder = state.pageStyle === "topic"
    ? "+"
    : state.words.length
      ? ""
      : "Type a word, press Enter — or paste a comma-separated list";
  updateTopicInputRow();
  if (undoBtn) undoBtn.hidden = !undoStack.canUndo();
  renderExistingEditControls();
  renderPreview();
  renderPlacementOrder();
}

/* The way in to changing what is already on the page, plus a running summary
   of what is pending — so a change made two screens ago is still visible from
   the word list, rather than only resurfacing at review. The undo sits here too
   because this is the screen somebody carries on to after an edit, and it is
   where they notice the mistake they want back.

   Both controls are rendered from state rather than toggled at the call sites,
   so no path through the wizard can leave a stale one on screen. */
function renderExistingEditControls() {
  const button = $("edit-existing-btn");
  const summary = $("edit-existing-summary");
  const undo = $("undo-last-btn");
  if (undo) undo.hidden = !undoAvailable(state);
  if (!button || !summary) return;
  button.hidden = !state.canEditExisting ||
    !state.existingButtons.some((item) => item.editable);
  const line = editSummary({
    changed: state.pageEdits.changes.length,
    removed: state.pageEdits.removals.length,
    moved: state.pageEdits.moves.length,
    page: titleOf(state.parentId),
  });
  summary.hidden = !line;
  summary.textContent = line ? `Pending: ${line.toLocaleLowerCase()}.` : "";
}

/* Called when a session/connection resets and the old undo history no
   longer applies to anything on screen (see resetConnection in connect.js). */
function clearUndoHistory() {
  undoStack.clear();
  if (undoBtn) undoBtn.hidden = true;
}

/* ---------- step 2: chip editor dialog ---------- */

/* The same dialog serves a planned button and an existing one. They differ in
   what a mistake costs: a planned button only exists here, while an existing
   one is vocabulary somebody already uses — so the existing mode says what the
   button holds today, offers a way back to it, and never touches the
   topic-page row, which the change operation deliberately leaves alone. */
const chipDialog = $("chip-editor");
let editingIndex = null;
let editingSlot = null;

function editingExisting() {
  return editingSlot !== null;
}

function existingButton(slot) {
  return state.existingButtons.find((button) => button.slot === slot) || null;
}

function setEditorFn(fn) {
  document.querySelectorAll("#edit-fn-row .fn-pill").forEach((pill) => {
    const selected = pill.dataset.fn === fn;
    pill.classList.toggle("selected", selected);
    pill.setAttribute("aria-checked", selected);
    pill.tabIndex = selected ? 0 : -1;
  });
  chipDialog.dataset.fn = fn;
}

document.querySelectorAll("#edit-fn-row .fn-pill").forEach((pill) =>
  pill.addEventListener("click", () => setEditorFn(pill.dataset.fn))
);

function showEditorFor(mode, {
  label, message, fn = "", note = "", canRevert = false,
  symbol = true, symbolQuery = "",
}) {
  $("edit-label").value = label;
  $("edit-label").setCustomValidity("");
  $("edit-message").value = message;
  setEditorFn(fn);
  const existing = mode === "existing";
  $("chip-editor-title").textContent = existing ? "Change this button" : "Edit button";
  $("chip-editor-note").textContent = note;
  $("chip-editor-note").hidden = !note;
  $("edit-fn-field").hidden = existing;
  // TD Snap owns symbol search, and it only ever runs while a button is being
  // created — so the choice is offered where it can still be honoured, on a
  // planned button, and hidden on one that already has its symbol.
  $("edit-symbol-field").hidden = existing || state.mode === "file";
  $("edit-symbol").checked = symbol !== false;
  $("edit-symbol-query").value = symbolQuery;
  syncSymbolQuery();
  $("edit-revert").hidden = !canRevert;
  $("edit-remove").textContent = existing ? "Remove from the page" : "Remove button";
  chipDialog.showModal();
}

/* The search words only mean anything while a symbol is wanted at all. */
function syncSymbolQuery() {
  const wanted = $("edit-symbol").checked;
  $("edit-symbol-query").disabled = !wanted;
  $("edit-symbol-query-row").hidden = !wanted;
}

$("edit-symbol").addEventListener("change", syncSymbolQuery);

function openChipEditor(index) {
  editingIndex = index;
  editingSlot = null;
  const item = state.words[index];
  showEditorFor("word", {
    label: item.label,
    message: item.message || "",
    fn: item.fn || "",
    symbol: item.symbol !== false,
    symbolQuery: item.symbolQuery || "",
  });
}

/* Opened from the placement grid, on a button that is already on the page. */
function openExistingEditor(slot) {
  const button = existingButton(slot);
  if (!button || !button.editable || !state.canEditExisting) return;
  editingIndex = null;
  editingSlot = slot;
  const change = changeFor(state.pageEdits, slot);
  const removed = isRemoved(state.pageEdits, slot);
  const move = moveFrom(state.pageEdits, slot);
  showEditorFor("existing", {
    label: change ? change.label : button.label,
    message: change ? change.message : button.message || "",
    note: removed
      ? `“${button.label}” is marked for removal. Save to keep it with these details instead.`
      : `On the page now: “${button.label}”` +
        (button.message ? ` · speaks “${button.message}”` : " · speaks its label") +
        (move ? " · already being moved to another cell" : ""),
    canRevert: Boolean(change) || removed,
  });
}

$("edit-label").addEventListener("input", () => {
  $("edit-label").setCustomValidity("");
});

/* A label already in use on this page, whether it is planned, already there,
   or about to be renamed onto. The server refuses these too; catching it here
   means the user finds out while typing rather than at the confirm step. */
function labelTaken(label) {
  const folded = label.toLocaleLowerCase();
  const planned = state.words.some(
    (item, index) => index !== editingIndex && item.label.toLocaleLowerCase() === folded
  );
  const present = state.existingButtons.some((button) => {
    if (button.slot === editingSlot || isRemoved(state.pageEdits, button.slot)) return false;
    const change = changeFor(state.pageEdits, button.slot);
    return (change ? change.label : button.label || "").toLocaleLowerCase() === folded;
  });
  return planned || present;
}

$("chip-editor-form").addEventListener("submit", (event) => {
  if (!event.submitter || event.submitter.value !== "save") return;
  const input = $("edit-label");
  const label = input.value.trim();
  input.setCustomValidity(labelTaken(label) ? "Each button needs a unique label." : "");
  if (!label || !input.checkValidity()) {
    event.preventDefault();
    input.reportValidity();
  }
});

function closeExistingEditor(action) {
  const button = existingButton(editingSlot);
  if (!button) return;
  if (action === "remove") {
    state.pageEdits = planRemoval(state.pageEdits, button);
  } else if (action === "keep") {
    state.pageEdits = keepButton(state.pageEdits, button.slot);
  } else if (action === "save") {
    state.pageEdits = planChange(state.pageEdits, button, {
      label: $("edit-label").value.trim(),
      message: $("edit-message").value.trim(),
    });
  }
  state.pendingEdit = null;
}

chipDialog.addEventListener("close", () => {
  const action = chipDialog.returnValue;
  if (editingExisting()) {
    closeExistingEditor(action);
    editingSlot = null;
    renderWords();
    return;
  }
  if (editingIndex === null) return;
  if (action === "remove") {
    undoStack.push(snapshotWords());
    state.words.splice(editingIndex, 1);
  } else if (action === "save") {
    const label = $("edit-label").value.trim();
    const message = $("edit-message").value.trim();
    if (label) {
      const wantsSymbol = $("edit-symbol").checked;
      const query = $("edit-symbol-query").value.trim();
      state.words[editingIndex] = {
        label,
        message: message && message !== label ? message : null,
        fn: chipDialog.dataset.fn || "",
        slot: state.words[editingIndex].slot,
        symbol: wantsSymbol,
        // The label is already the default search, so only a different query is
        // worth carrying — that keeps the draft and the request free of noise.
        symbolQuery: wantsSymbol && query && query !== label ? query : null,
      };
      if (state.pageStyle === "topic" && state.words[editingIndex].fn) {
        state.words[editingIndex].slot = null;
        state.words[editingIndex].slot = firstAvailableSlot(state.words[editingIndex].fn);
      }
    }
  }
  editingIndex = null;
  renderWords();
});

export {
  autoFormatTopicRows, clearUndoHistory, firstAvailableSlot, functionForSlot,
  openExistingEditor, pageCapacity, renderWords, takeWordInput, undoLastRemoval,
  updateTopicInputRow,
};
