/* Composing the word list: the chip box and the per-chip editor dialog.
 *
 * state.words is the only copy of this work until an edit is applied, which is
 * why leaving the page while it is non-empty prompts a warning.
 */

import { state, FUNCTIONS, TOPIC_FUNCTIONS } from "./state.js";
import { $, appendNamedList } from "./dom.js";
import { inferPhraseFunction } from "./phrases.js";
import { titleOf } from "./parents.js";
import { renderPlacementOrder, renderPreview } from "./preview.js";
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
  state.existingButtons.forEach((button) => used.add(button.slot));
  const capacity = state.grid.cols * state.grid.rows;
  const available = [];
  for (let slot = 0; slot < capacity; slot += 1) {
    if (!used.has(slot) && (!state.availableSlots || state.availableSlots.includes(slot))) {
      available.push(slot);
    }
  }
  return available.find((slot) => !preferredFn || functionForSlot(slot) === preferredFn)
    ?? available[0]
    ?? capacity - 1;
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
  const capacity = state.availableSlots
    ? state.availableSlots.length : state.grid.cols * state.grid.rows - state.existingButtons.length;
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
        state.words.push({ label: word, message: null, fn, slot, symbol: true });
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
    body.setAttribute(
      "aria-label",
      `Edit ${item.label}${item.fn ? `, ${FUNCTIONS[item.fn].name}` : ""}` +
        (item.message ? `, speaks “${spoken}”` : "")
    );
    body.title = item.message ? `Speaks: “${item.message}”` : "Click to edit";
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

  const capacity = state.availableSlots
    ? state.availableSlots.length : state.grid.cols * state.grid.rows - state.existingButtons.length;
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
  renderPreview();
  renderPlacementOrder();
}

/* Called when a session/connection resets and the old undo history no
   longer applies to anything on screen (see resetConnection in connect.js). */
function clearUndoHistory() {
  undoStack.clear();
  if (undoBtn) undoBtn.hidden = true;
}

/* ---------- step 2: chip editor dialog ---------- */

const chipDialog = $("chip-editor");
let editingIndex = null;

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

function openChipEditor(index) {
  editingIndex = index;
  const item = state.words[index];
  $("edit-label").value = item.label;
  $("edit-label").setCustomValidity("");
  $("edit-message").value = item.message || "";
  setEditorFn(item.fn || "");
  chipDialog.showModal();
}

$("edit-label").addEventListener("input", () => {
  $("edit-label").setCustomValidity("");
});

$("chip-editor-form").addEventListener("submit", (event) => {
  if (!event.submitter || event.submitter.value !== "save") return;
  const input = $("edit-label");
  const label = input.value.trim();
  const duplicate = state.words.some(
    (item, index) => index !== editingIndex &&
      item.label.toLocaleLowerCase() === label.toLocaleLowerCase()
  );
  input.setCustomValidity(duplicate ? "Each button needs a unique label." : "");
  if (!label || !input.checkValidity()) {
    event.preventDefault();
    input.reportValidity();
  }
});

chipDialog.addEventListener("close", () => {
  const action = chipDialog.returnValue;
  if (editingIndex === null) return;
  if (action === "remove") {
    undoStack.push(snapshotWords());
    state.words.splice(editingIndex, 1);
  } else if (action === "save") {
    const label = $("edit-label").value.trim();
    const message = $("edit-message").value.trim();
    if (label) {
      state.words[editingIndex] = {
        label,
        message: message && message !== label ? message : null,
        fn: chipDialog.dataset.fn || "",
        slot: state.words[editingIndex].slot,
        symbol: state.words[editingIndex].symbol !== false,
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
  renderWords, takeWordInput, undoLastRemoval, updateTopicInputRow,
};
