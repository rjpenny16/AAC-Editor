/* Freezing the plan, reviewing it, and confirming the write.
 *
 * The payload is frozen when the user reaches review, and any later edit
 * invalidates it and sends them back through — so what gets written is always
 * what was on screen when they pressed the button. This step is never skipped
 * and never defaulted past.
 */

import { state } from "./state.js";
import { $, setBusy, setActivity } from "./dom.js";
import { api } from "./api.js";
import { pageCapacity, renderWords, takeWordInput } from "./chips.js";
import { loadTargetLayout, refreshDetectedPages } from "./connect.js";
import {
  changePayload, countEdits, describeChange, describeMove, describeRemoval, editSummary,
  emptyEdits, movePayload,
} from "./edits.js";
import { parentFilter, renderParents, titleOf } from "./parents.js";
import { placementSlots, renderPreview, showPlacement } from "./preview.js";
import { renderResult } from "./result.js";
import { FUNCTIONS } from "./state.js";
import { clearBuildError, clearStepError, continueWizard, setOperation, show, showStepError } from "./wizard.js";

/* ---------- step 2 → 3: build ---------- */


const buildForm = $("build-form");
function handleAnswerChange() {
  clearBuildError();
  clearStepError(state.wizardStep);
  state.pendingEdit = null;
}
buildForm.addEventListener("input", handleAnswerChange);
buildForm.addEventListener("change", handleAnswerChange);

function freezePayload(payload) {
  [payload.items, payload.changes, payload.removals].forEach((list) => {
    if (!list) return;
    list.forEach(Object.freeze);
    Object.freeze(list);
  });
  return Object.freeze(payload);
}

function syncReviewPlacement() {
  renderPreview();
  const source = $("preview");
  const target = $("review-preview");
  target.className = `${source.className} review-preview`;
  target.setAttribute("style", source.getAttribute("style") || "");
  target.replaceChildren(...[...source.children].map((child) => child.cloneNode(true)));
  target.setAttribute("aria-hidden", "true");
  target.querySelectorAll("[tabindex], [role], [draggable]").forEach((element) => {
    element.removeAttribute("tabindex");
    element.removeAttribute("role");
    element.removeAttribute("draggable");
  });
  const slots = placementSlots();
  const list = $("review-placement-order");
  list.innerHTML = "";
  [...state.words]
    .sort((left, right) => slots.indexOf(left.slot) - slots.indexOf(right.slot))
    .forEach((item) => {
      const row = document.createElement("li");
      row.textContent = item.label;
      list.append(row);
    });
}

/* Changes, moves, and removals only ever apply to the page already open, so
   they travel with an existing-page edit and are dropped everywhere else. */
function pendingPageEdits() {
  if (state.mode === "file" || state.provider === "grid3" || state.operation !== "existing") {
    return { changes: [], removals: [], moves: [] };
  }
  return state.pageEdits;
}

function appendReviewRow(list, heading, detail = "") {
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

function renderReviewEdits(edits, cols = state.grid.cols) {
  const changes = $("review-changes");
  const removals = $("review-removals");
  const moves = $("review-moves");
  [changes, removals, moves].forEach((list) => { list.innerHTML = ""; });
  $("review-changes-wrap").hidden = !edits.changes.length;
  $("review-removals-wrap").hidden = !edits.removals.length;
  $("review-moves-wrap").hidden = !edits.moves.length;
  edits.changes.forEach((change) => {
    appendReviewRow(changes, change.from.label, describeChange(change));
  });
  edits.moves.forEach((move) => {
    appendReviewRow(moves, move.from.label, describeMove(move, cols));
  });
  edits.removals.forEach((slot) => {
    const button = state.existingButtons.find((item) => item.slot === slot);
    if (button) appendReviewRow(removals, describeRemoval(button));
  });
}

/* Where the confirmed edit is sent. Exported-file sessions now have both an
   add-to-existing path and a create-a-page path, the same split the live
   providers have always had. */
function editPath(operation) {
  if (state.mode === "file") {
    const session = encodeURIComponent(state.sessionId);
    return operation === "existing"
      ? `/api/pageset/${session}/page/${encodeURIComponent(state.parentId)}/buttons`
      : `/api/pageset/${session}/page`;
  }
  if (state.provider === "grid3") return "/api/grid3/edit-plan";
  return operation === "existing" ? "/api/tdsnap/edit-plan" : "/api/tdsnap/page";
}

function prepareReview() {
  const title = $("title-input").value.trim();
  const parentTitle = titleOf(state.parentId);
  const operation = state.operation;
  const edits = pendingPageEdits();
  const items = state.words.map((item) => ({
      label: item.label,
      message: item.message,
      border_color: item.fn ? FUNCTIONS[item.fn].color : null,
      slot: item.slot,
      symbol: item.symbol !== false,
      symbol_query: item.symbolQuery || null,
    }));
  const payload = freezePayload(state.mode === "file"
    ? operation === "existing"
      ? { items, fingerprint: state.layoutFingerprint }
      : { title, items, parent_page_id: Number(state.parentId) }
    : {
        operation: operation === "existing"
          ? countEdits(edits) ? "edit_page" : "add_to_existing_page"
          : "create_page",
        title,
        items,
        changes: changePayload(edits),
        removals: [...edits.removals],
        moves: movePayload(edits),
        parent: parentTitle,
        page: parentTitle,
        fingerprint: state.layoutFingerprint,
      });
  state.pendingEdit = Object.freeze({
    operation,
    path: editPath(operation),
    payload,
    title,
    parentTitle,
    displayTitle: operation === "existing" ? parentTitle : title,
    knownPageTitles: Object.freeze(
      state.pages.map((page) => page.title.trim().toLocaleLowerCase())
    ),
  });

  const count = payload.items.length;
  const changed = edits.changes.length;
  const removed = edits.removals.length;
  const moved = edits.moves.length;
  const destructive = Boolean(changed || removed || moved);
  $("result-eyebrow").textContent = "Review";
  $("result-heading").textContent = destructive
    ? "Check every change before it is made"
    : "Check positions before adding";
  $("result-sub").textContent = destructive
    ? "Every button this edit touches is named below. Nothing changes until you confirm."
    : "Check the details below. Nothing changes until you confirm.";
  $("review-state").hidden = false;
  $("success-state").hidden = true;
  const buttonWord = `button${count === 1 ? "" : "s"}`;
  const resultLabel = operation !== "existing"
    ? `Create ${title} with ${count} ${buttonWord}`
    : destructive
      ? editSummary({ added: count, changed, removed, moved, page: parentTitle })
      : `Add ${count} ${buttonWord} to ${parentTitle}`;
  $("review-action").textContent = resultLabel;
  $("review-target").textContent = operation === "existing"
    ? parentTitle
    : `${title}, found from ${parentTitle}`;
  $("review-count").textContent = [
    `${count} added`,
    changed ? `${changed} changed` : "",
    moved ? `${moved} moved` : "",
    removed ? `${removed} removed` : "",
  ].filter(Boolean).join(" · ");
  $("review-placement").textContent = state.placementAdjusted
    ? "The positions you chose"
    : "Automatic — the first open spaces";
  $("confirm-update-label").textContent = resultLabel;
  $("review-error").hidden = true;
  $("review-error").innerHTML = "";

  const list = $("review-items");
  list.innerHTML = "";
  $("review-items-wrap").hidden = !count;
  $("review-items-wrap").querySelector("h3").textContent = "Buttons to add";
  payload.items.forEach((item) => {
    const detail = [
      item.message ? `Speaks: ${item.message}` : "",
      item.symbol === false ? "No symbol" : "",
      item.symbol_query ? `Symbol search: ${item.symbol_query}` : "",
    ].filter(Boolean).join(" · ");
    appendReviewRow(list, item.label, detail);
  });
  renderReviewEdits(edits);
  // Both are the undo review's doing, and every other review restores them.
  $("review-undo-note").hidden = true;
  $("review-placement-section").hidden = false;
  $("adjust-placement-btn").hidden = false;
  syncReviewPlacement();
  show("review");
}

/* ---------- undo the last applied edit ---------- */

/* An undo is reviewed exactly like the edit that caused it: same screen, same
   lists, same confirm step, and the server replays it through the same write
   path. What it cannot do is stated up front rather than discovered — it
   reaches back one edit, only within this session, and only while the page is
   still as AAC Editor left it. A TD Snap sync, or anybody editing the page in
   TD Snap, ends that. */
const UNDO_LIMITS = [
  "This reaches back one change only, and only while this window has been open.",
  "It cannot reach back past a sync in TD Snap, or past a change made in TD Snap itself.",
];

function prepareUndoReview() {
  const undo = state.lastEdit;
  if (!undo) return;
  const cols = (undo.grid && undo.grid.cols) || state.grid.cols;
  const restores = undo.restores;
  const counts = {
    added: restores.adds.length,
    changed: restores.changes.length,
    removed: restores.removals.length,
    moved: restores.moves.length,
  };
  state.pendingEdit = Object.freeze({
    kind: "undo",
    operation: "existing",
    path: "/api/tdsnap/undo",
    payload: Object.freeze({}),
    title: undo.page,
    parentTitle: undo.page,
    displayTitle: undo.page,
    knownPageTitles: Object.freeze([]),
  });

  const resultLabel = editSummary({ ...counts, page: undo.page })
    || `Undo the last change on ${undo.page}`;
  $("result-eyebrow").textContent = "Review";
  $("result-heading").textContent = "Check what undoing will put back";
  $("result-sub").textContent =
    "Every button this undo touches is named below. Nothing changes until you confirm.";
  $("review-state").hidden = false;
  $("success-state").hidden = true;
  $("review-action").textContent = resultLabel;
  $("review-target").textContent = undo.page;
  $("review-count").textContent = [
    counts.added ? `${counts.added} put back` : "",
    counts.changed ? `${counts.changed} restored` : "",
    counts.moved ? `${counts.moved} moved back` : "",
    counts.removed ? `${counts.removed} taken away` : "",
  ].filter(Boolean).join(" · ");
  $("review-placement").textContent = "Back to where each button was";
  $("confirm-update-label").textContent = resultLabel;
  $("review-error").hidden = true;
  $("review-error").innerHTML = "";

  const items = $("review-items");
  items.innerHTML = "";
  $("review-items-wrap").hidden = !counts.added;
  $("review-items-wrap").querySelector("h3").textContent = "Buttons to put back";
  restores.adds.forEach((item) => {
    appendReviewRow(items, item.label, item.message ? `Speaks: ${item.message}` : "");
  });
  renderReviewEdits({
    changes: restores.changes,
    removals: [],
    moves: restores.moves.map((move) => ({ ...move, from: { label: move.label } })),
  }, cols);
  const removals = $("review-removals");
  removals.innerHTML = "";
  $("review-removals-wrap").hidden = !counts.removed;
  restores.removals.forEach((button) => appendReviewRow(removals, describeRemoval(button)));

  const note = $("review-undo-note");
  note.innerHTML = "";
  const lead = document.createElement("strong");
  lead.textContent = "What undo can and cannot reach";
  const list = document.createElement("ul");
  [...UNDO_LIMITS, ...(undo.warnings || [])].forEach((line) => {
    const row = document.createElement("li");
    row.textContent = line;
    list.append(row);
  });
  note.append(lead, list);
  note.hidden = false;

  // The placement grid shows the page as an *edit* will leave it; an undo is
  // described by its lists instead of re-deriving a preview of the way back.
  $("review-placement-section").hidden = true;
  $("adjust-placement-btn").hidden = true;
  show("review");
}

["undo-edit-btn", "undo-last-btn"].forEach((id) => {
  const button = $(id);
  if (button) button.addEventListener("click", prepareUndoReview);
});

function showReviewError(message, details = []) {
  const box = $("review-error");
  box.innerHTML = "";
  const lead = document.createElement("strong");
  lead.textContent = message;
  box.append(lead);
  if (details.length) {
    const list = document.createElement("ul");
    details.forEach((detail) => {
      const item = document.createElement("li");
      item.textContent = detail;
      list.append(item);
    });
    box.append(list);
  }
  box.hidden = false;
  box.focus({ preventScroll: true });
}

buildForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (state.wizardStep !== "items") {
    continueWizard();
    return;
  }
  clearBuildError();
  clearStepError("items");

  takeWordInput();

  if (!state.words.length && !countEdits(pendingPageEdits())) {
    showStepError("items", "Add at least one word or phrase before continuing.");
    return;
  }
  if (state.availableSlots && state.words.length > pageCapacity()) {
    showStepError("items", "This page is full. Remove a planned button or choose another page.");
    return;
  }

  prepareReview();
});

$("review-back-btn").addEventListener("click", () => {
  state.pendingEdit = null;
  show("items");
});

$("adjust-placement-btn").addEventListener("click", () => {
  showPlacement("review");
});

$("placement-back-btn").addEventListener("click", () => {
  if (state.placementReturn === "items") {
    state.pendingEdit = null;
    show("items");
    return;
  }
  prepareReview();
});

$("confirm-update-btn").addEventListener("click", async () => {
  const pending = state.pendingEdit;
  if (!pending) {
    showReviewError("The review is out of date.", ["Go back, review your buttons again, then confirm."]);
    return;
  }

  const undoing = pending.kind === "undo";
  const product = state.provider === "grid3" ? "Grid 3" : "TD Snap";
  const busyLabel = undoing
    ? `Undoing the change in ${product} and checking…`
    : pending.operation === "existing"
      ? `Updating ${product} and checking…`
      : "Creating and checking…";
  const button = $("confirm-update-btn");
  $("review-error").hidden = true;
  setBusy(button, true, busyLabel);
  $("step-result").setAttribute("aria-busy", "true");
  setActivity(undoing
    ? `Putting “${pending.displayTitle}” back and checking the result…`
    : pending.operation === "existing"
      ? `Updating ${product} and checking the result…`
      : "Creating the page in TD Snap and checking the result…");
  try {
    const data = await api(pending.path, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(state.mode === "file"
          ? {}
          : state.provider === "grid3"
          ? { "X-AAC-Editor": "grid3" }
          : { "X-TDSnap-Editor": "1" }),
      },
      body: JSON.stringify(pending.payload),
    }, 0);
    state.edits = data.edits || state.edits + 1;
    // `undo` is absent from a Grid 3 or exported-file report; only TD Snap live
    // retains anything, and there it is always present (null when spent).
    if ("undo" in data) state.lastEdit = data.undo;
    if (state.provider === "tdsnap" || state.mode === "file") {
      try {
        await refreshDetectedPages();
      } catch {
        // The requested edit is already verified. A later reconnect can refresh the list.
      }
    }
    // An undo has just rewritten the page it was reviewed against, so the
    // pending edits and the layout behind them are both stale.
    if (undoing) {
      state.pageEdits = emptyEdits();
      try {
        await loadTargetLayout(pending.displayTitle);
      } catch {
        // The undo is already verified; the next poll or reconnect re-reads it.
      }
    }
    renderResult(
      pending.displayTitle,
      data,
      pending.operation,
      pending.parentTitle
    );
    state.pendingEdit = null;
    show("result");
  } catch (error) {
    if (undoing) {
      showReviewError("TD Snap couldn’t undo the last change.", [
        error.message,
        ...(error.problems || []),
        "Nothing was left half-done: the page is as it was before this undo.",
      ]);
      return;
    }
    if (state.mode !== "file" && pending.operation === "new" && pending.title) {
      try {
        await refreshDetectedPages();
        const created = state.pages.find(
          (page) => page.title.toLocaleLowerCase() === pending.title.toLocaleLowerCase()
        );
        if (created && !pending.knownPageTitles.includes(pending.title.toLocaleLowerCase())) {
          setOperation("existing");
          state.parentId = created.id;
          state.parentTouched = true;
          parentFilter.value = "";
          renderParents("");
          const layout = await loadTargetLayout(created.title);
          const present = new Set(
            layout.buttons.map((item) => item.label.trim().toLocaleLowerCase())
          );
          const before = state.words.length;
          state.words = state.words.filter(
            (item) => !present.has(item.label.trim().toLocaleLowerCase())
          );
          const alreadyAdded = before - state.words.length;
          state.pendingEdit = null;
          state.placementAdjusted = false;
          renderWords();
          show("items");
          showStepError(
            "items",
            `TD Snap created the page but stopped before every button was added. ` +
            `${alreadyAdded} button${alreadyAdded === 1 ? " is" : "s are"} already there. ` +
            (state.words.length
              ? `${state.words.length} button${state.words.length === 1 ? " remains" : "s remain"}. Review and try the update again.`
              : "All requested buttons are already there.")
          );
          return;
        }
      } catch {
        // Keep the original error if TD Snap cannot be inspected for recovery.
      }
    }
    showReviewError(`${state.provider === "grid3" ? "Grid 3" : "TD Snap"} couldn't complete the edit.`, [
      error.message,
      ...(error.problems || []),
    ]);
  } finally {
    setActivity();
    $("step-result").setAttribute("aria-busy", "false");
    setBusy(button, false);
  }
});
