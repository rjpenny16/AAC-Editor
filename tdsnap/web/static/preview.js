/* The grid preview and placement editor.
 *
 * Shows the target page as it will look after the edit: existing buttons
 * locked, new ones movable. Drag works, and so does the keyboard — arrow keys
 * move a button between cells, which is not a nicety here, since many of the
 * people configuring an AAC device navigate this way themselves.
 */

import { state, FUNCTIONS } from "./state.js";
import { $ } from "./dom.js";
import { functionForSlot, openExistingEditor, renderWords } from "./chips.js";
import { changeFor, isRemoved } from "./edits.js";
import { titleOf } from "./parents.js";
import { setOperation, show } from "./wizard.js";

/* ---------- step 2: preview ---------- */

const PREVIEW_ICONS = {
  question: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="8.5" stroke="currentColor" stroke-width="1.8"/><path d="M9.7 9.4a2.45 2.45 0 0 1 4.6 1.2c0 1.8-2.3 2-2.3 3.45" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="17.1" r="1" fill="currentColor"/></svg>',
  comment: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4.5 5.5h15v10.3h-9.2L5 19.2V5.5Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M8 9h8M8 12h5.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  positive: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M8.8 10.2 11.5 4c.45-1 1.9-.7 1.9.4v4.1h4.15c1.35 0 2.3 1.3 1.9 2.6l-1.7 5.7a2 2 0 0 1-1.9 1.45H8.8V10.2ZM5 10.2h3.8v8.05H5z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>',
  negative: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m8.8 13.8 2.7 6.2c.45 1 1.9.7 1.9-.4v-4.1h4.15c1.35 0 2.3-1.3 1.9-2.6l-1.7-5.7a2 2 0 0 0-1.9-1.45H8.8v8.05ZM5 5.75h3.8v8.05H5z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>',
  personal: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="8.25" r="3.25" stroke="currentColor" stroke-width="1.8"/><path d="M5.8 19c.55-3.25 2.65-5 6.2-5s5.65 1.75 6.2 5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  default: '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="5" y="5" width="5.5" height="5.5" rx="1" stroke="currentColor" stroke-width="1.7"/><rect x="13.5" y="5" width="5.5" height="5.5" rx="1" stroke="currentColor" stroke-width="1.7"/><rect x="5" y="13.5" width="5.5" height="5.5" rx="1" stroke="currentColor" stroke-width="1.7"/><rect x="13.5" y="13.5" width="5.5" height="5.5" rx="1" stroke="currentColor" stroke-width="1.7"/></svg>',
};

function addPreviewCellContent(cell, label, fn = "", showSymbol = true) {
  if (showSymbol) {
    const symbol = document.createElement("span");
    symbol.className = "cell-symbol";
    symbol.innerHTML = PREVIEW_ICONS[fn] || PREVIEW_ICONS.default;
    cell.append(symbol);
  } else {
    cell.classList.add("no-symbol");
  }
  const text = document.createElement("span");
  text.className = "cell-label";
  text.textContent = label;
  cell.append(text);
}

function renderGrid3Preview(preview) {
  preview.classList.add("grid3-preview");
  preview.classList.remove("topic-preview");
  preview.style.aspectRatio = state.previewAspect ? String(state.previewAspect) : "1.4";
  preview.style.setProperty("--grid3-background", state.gridBackground || "#f4f6f8");
  state.grid3Cells.filter((item) => item.rect).forEach((model) => {
    const cell = document.createElement("div");
    const rect = model.rect;
    const style = model.style || {};
    cell.className = "cell";
    cell.dataset.slot = model.slot;
    cell.style.left = `${rect.left * 100}%`;
    cell.style.top = `${rect.top * 100}%`;
    cell.style.width = `${rect.width * 100}%`;
    cell.style.height = `${rect.height * 100}%`;
    if (style.background) cell.style.backgroundColor = style.background;
    if (style.border) cell.style.borderColor = style.border;
    if (style.foreground) cell.style.color = style.foreground;

    const wordIndex = state.words.findIndex((item) => item.slot === model.slot);
    if (!model.safe_blank) {
      cell.classList.add("existing");
      if (model.label) addPreviewCellContent(cell, model.label, "", false);
      cell.title = "Existing or special Grid 3 cell — locked";
      cell.setAttribute("aria-label", `${model.label || "Special cell"}, existing and locked`);
    } else if (wordIndex >= 0) {
      const item = state.words[wordIndex];
      cell.classList.add("used");
      addPreviewCellContent(cell, item.label, "", item.symbol !== false);
      cell.draggable = true;
      cell.tabIndex = 0;
      cell.setAttribute("role", "button");
      cell.setAttribute(
        "aria-label",
        `${item.label}, row ${model.y + 1}, column ${model.x + 1}. ` +
        "Drag or use arrow keys to move. This button retains the existing Grid 3 cell style."
      );
      cell.title = item.message
        ? `Speaks: “${item.message}” · retains ${style.key || "existing"} style`
        : `Retains ${style.key || "existing"} style`;
      cell.addEventListener("dragstart", (event) => {
        event.dataTransfer.setData("text/plain", String(wordIndex));
        event.dataTransfer.effectAllowed = "move";
      });
      cell.addEventListener("keydown", (event) => {
        const moves = { ArrowLeft: -1, ArrowRight: 1,
          ArrowUp: -state.grid.cols, ArrowDown: state.grid.cols };
        if (!(event.key in moves)) return;
        event.preventDefault();
        const target = model.slot + moves[event.key];
        movePreviewItem(wordIndex, target);
        preview.querySelector(`[data-slot="${target}"]`)?.focus();
      });
    } else {
      cell.setAttribute(
        "aria-label",
        `Empty space AAC Editor can update safely, row ${model.y + 1}, column ${model.x + 1}, ` +
        `${style.key || "existing"} style`
      );
    }
    if (model.safe_blank) {
      cell.addEventListener("dragover", (event) => {
        event.preventDefault();
        cell.classList.add("drop-target");
      });
      cell.addEventListener("dragleave", () => cell.classList.remove("drop-target"));
      cell.addEventListener("drop", (event) => {
        event.preventDefault();
        cell.classList.remove("drop-target");
        const index = Number(event.dataTransfer.getData("text/plain"));
        if (Number.isInteger(index)) movePreviewItem(index, model.slot);
      });
    }
    preview.append(cell);
  });
}

/* An existing button, in whichever of its four states applies: locked (the
   only state before change and remove existed), eligible, marked for a
   change, or marked for removal. A locked one always says *why* — on hover
   and on focus — because "you can't touch this" without a reason is the kind
   of dead end this app exists to remove. */
function renderExistingCell(cell, existing) {
  const change = changeFor(state.pageEdits, existing.slot);
  const removed = isRemoved(state.pageEdits, existing.slot);
  const label = change ? change.label : existing.label || "Existing button";
  cell.classList.add("existing");
  addPreviewCellContent(cell, label, "", state.pageStyle !== "topic");
  const position =
    `row ${Math.floor(existing.slot / state.grid.cols) + 1}, ` +
    `column ${(existing.slot % state.grid.cols) + 1}`;
  if (removed) {
    cell.classList.add("marked-removed");
    cell.title = `“${existing.label}” will be removed`;
    cell.setAttribute("aria-label", `${existing.label}, ${position}, marked for removal. Select to keep it.`);
  } else if (change) {
    cell.classList.add("marked-changed");
    cell.title = `“${existing.label}” becomes “${change.label}”`;
    cell.setAttribute("aria-label", `${existing.label}, ${position}, will be changed to ${change.label}. Select to edit again.`);
  } else if (existing.editable) {
    cell.classList.add("editable");
    cell.title = existing.message
      ? `Speaks: “${existing.message}” · select to change or remove`
      : "Select to change or remove this button";
    cell.setAttribute("aria-label", `${label}, ${position}, existing. Select to change or remove it.`);
  } else {
    cell.title = existing.locked_reason || "Existing TD Snap button — position preserved";
    cell.setAttribute(
      "aria-label",
      `${label}, ${position}, existing and locked. ${existing.locked_reason || ""}`.trim()
    );
    return;
  }
  if (!state.canEditExisting) {
    cell.classList.remove("editable");
    return;
  }
  cell.tabIndex = 0;
  cell.setAttribute("role", "button");
  cell.addEventListener("click", () => openExistingEditor(existing.slot));
  cell.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    openExistingEditor(existing.slot);
  });
}

function renderPreview() {
  const preview = $("preview");
  const previewTitle = state.operation === "existing"
    ? titleOf(state.parentId)
    : $("title-input").value.trim();
  $("preview-page-title").textContent = previewTitle || "AAC page preview";
  preview.style.setProperty("--cols", state.grid.cols);
  preview.style.setProperty("--rows", state.grid.rows);
  preview.classList.toggle("topic-preview", state.pageStyle === "topic");
  preview.classList.remove("grid3-preview");
  preview.style.removeProperty("aspect-ratio");
  preview.innerHTML = "";
  if (state.provider === "grid3" && state.grid3Cells.length) {
    renderGrid3Preview(preview);
    return;
  }
  if (state.pageStyle !== "topic" && !state.words.length && !state.existingButtons.length) {
    const note = document.createElement("div");
    note.className = "cell empty-note";
    note.textContent = "Your words appear here in an original AAC-style layout. TD Snap may render symbols and spacing differently.";
    preview.append(note);
    return;
  }
  const total = state.grid.cols * state.grid.rows;
  for (let slot = 0; slot < total; slot += 1) {
    if (state.pageStyle === "topic" && slot % state.grid.cols === 0) {
      const fn = functionForSlot(slot);
      const marker = document.createElement("div");
      marker.className = "preview-row-marker";
      marker.style.setProperty("--fn-color", FUNCTIONS[fn].color);
      marker.innerHTML = PREVIEW_ICONS[fn];
      marker.setAttribute("aria-label", `${FUNCTIONS[fn].name} row`);
      preview.append(marker);
    }
    const cell = document.createElement("div");
    cell.className = "cell";
    cell.dataset.slot = slot;
    if (state.pageStyle === "topic") {
      const rowFn = functionForSlot(slot);
      cell.classList.add("topic-row");
      cell.style.setProperty("--row-color", FUNCTIONS[rowFn].color);
    }
    const existing = state.existingButtons.find((item) => item.slot === slot);
    if (existing) renderExistingCell(cell, existing);
    const index = state.words.findIndex((item) => item.slot === slot);
    if (index >= 0) {
      const item = state.words[index];
      cell.classList.add("used");
      addPreviewCellContent(
        cell,
        item.label,
        item.fn,
        state.pageStyle !== "topic" && item.symbol !== false
      );
      cell.draggable = true;
      cell.tabIndex = 0;
      cell.setAttribute("role", "button");
      cell.setAttribute(
        "aria-label",
        `${item.label}, row ${Math.floor(slot / state.grid.cols) + 1}, ` +
        `column ${(slot % state.grid.cols) + 1}. Drag or use arrow keys to move.`
      );
      if (item.fn) {
        cell.classList.add("coded");
        cell.style.setProperty("--fn-color", FUNCTIONS[item.fn].color);
      }
      if (item.message) cell.title = `Speaks: “${item.message}”`;
      cell.addEventListener("dragstart", (event) => {
        event.dataTransfer.setData("text/plain", String(index));
        event.dataTransfer.effectAllowed = "move";
        cell.classList.add("dragging");
      });
      cell.addEventListener("dragend", () => cell.classList.remove("dragging"));
      cell.addEventListener("keydown", (event) => {
        const moves = {
          ArrowLeft: -1,
          ArrowRight: 1,
          ArrowUp: -state.grid.cols,
          ArrowDown: state.grid.cols,
        };
        if (!(event.key in moves)) return;
        event.preventDefault();
        const target = Math.max(0, Math.min(total - 1, slot + moves[event.key]));
        movePreviewItem(index, target);
        const moved = preview.querySelector(`[data-slot="${target}"]`);
        if (moved) moved.focus();
      });
    }
    if (state.pageStyle === "topic" && !existing && index < 0) {
      cell.classList.add("empty-topic");
      cell.setAttribute("aria-label", `Empty cell ${slot + 1}`);
    }
    cell.addEventListener("dragover", (event) => {
      if (existing) return;
      event.preventDefault();
      cell.classList.add("drop-target");
    });
    cell.addEventListener("dragleave", () => cell.classList.remove("drop-target"));
    cell.addEventListener("drop", (event) => {
      if (existing) return;
      event.preventDefault();
      cell.classList.remove("drop-target");
      const index = Number(event.dataTransfer.getData("text/plain"));
      if (Number.isInteger(index)) movePreviewItem(index, slot);
    });
    preview.append(cell);
  }
}

function placementSlots() {
  if (state.provider === "grid3" && state.grid3Cells.length) {
    return state.grid3Cells
      .filter((cell) => cell.safe_blank)
      .sort((left, right) => left.y - right.y || left.x - right.x)
      .map((cell) => cell.slot);
  }
  if (state.availableSlots) return [...state.availableSlots].sort((a, b) => a - b);
  const occupied = new Set(state.existingButtons.map((button) => button.slot));
  return Array.from({ length: state.grid.cols * state.grid.rows }, (_, slot) => slot)
    .filter((slot) => !occupied.has(slot));
}

function renderPlacementOrder() {
  const wrap = $("placement-order-wrap");
  const list = $("placement-order");
  list.innerHTML = "";
  wrap.hidden = state.provider !== "grid3" || !state.words.length;
  if (wrap.hidden) return;
  const slots = placementSlots();
  [...state.words]
    .sort((left, right) => slots.indexOf(left.slot) - slots.indexOf(right.slot))
    .forEach((item) => {
      const index = state.words.indexOf(item);
      const position = slots.indexOf(item.slot);
      const row = document.createElement("li");
      const label = document.createElement("strong");
      label.textContent = item.label;
      row.append(label);
      [-1, 1].forEach((direction) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-ghost";
        button.textContent = direction < 0 ? "Move earlier" : "Move later";
        button.dataset.index = index;
        button.dataset.direction = direction;
        button.disabled = position + direction < 0 || position + direction >= slots.length;
        button.setAttribute("aria-label", `${button.textContent}: ${item.label}`);
        button.addEventListener("click", () => {
          movePreviewItem(index, slots[position + direction]);
          $("placement-order").querySelector(
            `[data-index="${index}"][data-direction="${direction}"]`
          )?.focus();
        });
        row.append(button);
      });
      list.append(row);
    });
}

function movePreviewItem(index, targetSlot) {
  const item = state.words[index];
  if (!item || item.slot === targetSlot) return;
  if (state.existingButtons.some((button) => button.slot === targetSlot) ||
      (state.availableSlots && !state.availableSlots.includes(targetSlot))) return;
  const previousSlot = item.slot;
  const occupant = state.words.find((candidate, candidateIndex) =>
    candidateIndex !== index && candidate.slot === targetSlot
  );
  item.slot = targetSlot;
  if (occupant) occupant.slot = previousSlot;
  if (state.pageStyle === "topic" && state.autoTopicRows) {
    item.fn = functionForSlot(item.slot);
    if (occupant) occupant.fn = functionForSlot(occupant.slot);
  }
  state.placementAdjusted = true;
  state.pendingEdit = null;
  renderWords();
}

$("choose-page-btn").addEventListener("click", () => {
  setOperation("existing");
  show("destination");
});
$("create-page-btn").addEventListener("click", () => {
  setOperation("new");
  show("title");
});

/* The placement grid is the one screen that shows the page as it really is, so
   it is where an existing button is changed or removed. It is reachable from
   the word list as well as from review; the Back button follows whichever
   route the user took rather than always landing on review. */
function showPlacement(from) {
  state.placementReturn = from;
  const editing = from === "items";
  $("placement-heading").textContent = editing
    ? "Change or remove existing buttons"
    : "Adjust button placement";
  $("placement-lead").textContent = editing
    ? "Select a button to change what it says or remove it. Buttons that open a page or run " +
      "an action stay locked, and say why."
    : "Drag buttons to the exact cells you want, or focus one and use the arrow keys. " +
      "Existing buttons stay locked.";
  $("placement-back-btn").textContent = editing
    ? "Back to words and phrases"
    : "Back to review";
  renderPreview();
  show("placement");
}

$("edit-existing-btn").addEventListener("click", () => showPlacement("items"));

export { placementSlots, renderPlacementOrder, renderPreview, showPlacement };
