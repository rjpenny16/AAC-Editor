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
import { renderWords, takeWordInput } from "./chips.js";
import { loadTargetLayout, refreshDetectedPages } from "./connect.js";
import { parentFilter, renderParents, titleOf } from "./parents.js";
import { placementSlots, renderPreview } from "./preview.js";
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
  payload.items.forEach(Object.freeze);
  Object.freeze(payload.items);
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

function prepareReview() {
  const title = $("title-input").value.trim();
  const parentTitle = titleOf(state.parentId);
  const operation = state.operation;
  const items = state.words.map((item) => ({
      label: item.label,
      message: item.message,
      border_color: item.fn ? FUNCTIONS[item.fn].color : null,
      slot: item.slot,
      symbol: item.symbol !== false,
    }));
  const payload = freezePayload(state.mode === "file"
    ? {
        title,
        items,
        parent_page_id: Number(state.parentId),
      }
    : {
        operation: operation === "existing" ? "add_to_existing_page" : "create_page",
        title,
        items,
        parent: parentTitle,
        page: parentTitle,
        fingerprint: state.layoutFingerprint,
      });
  state.pendingEdit = Object.freeze({
    operation,
    path: state.mode === "file"
      ? `/api/pageset/${encodeURIComponent(state.sessionId)}/page`
      : state.provider === "grid3"
        ? "/api/grid3/edit-plan"
        : operation === "existing" ? "/api/tdsnap/edit-plan" : "/api/tdsnap/page",
    payload,
    title,
    parentTitle,
    displayTitle: operation === "existing" ? parentTitle : title,
    knownPageTitles: Object.freeze(
      state.pages.map((page) => page.title.trim().toLocaleLowerCase())
    ),
  });

  $("result-eyebrow").textContent = "Review";
  $("result-heading").textContent = "Check positions before adding";
  $("result-sub").textContent = "Check the details below. Nothing changes until you confirm.";
  $("review-state").hidden = false;
  $("success-state").hidden = true;
  const count = payload.items.length;
  const buttonWord = `button${count === 1 ? "" : "s"}`;
  const resultLabel = operation === "existing"
    ? `Add ${count} ${buttonWord} to ${parentTitle}`
    : `Create ${title} with ${count} ${buttonWord}`;
  $("review-action").textContent = resultLabel;
  $("review-target").textContent = operation === "existing"
    ? parentTitle
    : `${title}, found from ${parentTitle}`;
  $("review-count").textContent = `${payload.items.length} button${payload.items.length === 1 ? "" : "s"}`;
  $("review-placement").textContent = state.placementAdjusted
    ? "The positions you chose"
    : "Automatic — the first open spaces";
  $("confirm-update-label").textContent = resultLabel;
  $("review-error").hidden = true;
  $("review-error").innerHTML = "";

  const list = $("review-items");
  list.innerHTML = "";
  payload.items.forEach((item) => {
    const row = document.createElement("li");
    const label = document.createElement("strong");
    label.textContent = item.label;
    row.append(label);
    if (item.message) {
      const message = document.createElement("span");
      message.textContent = `Speaks: ${item.message}`;
      row.append(message);
    }
    list.append(row);
  });
  syncReviewPlacement();
  show("review");
}

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

  if (!state.words.length) {
    showStepError("items", "Add at least one word or phrase before continuing.");
    return;
  }
  if (state.availableSlots && state.words.length > state.availableSlots.length) {
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
  renderPreview();
  show("placement");
});

$("placement-back-btn").addEventListener("click", () => {
  prepareReview();
});

$("confirm-update-btn").addEventListener("click", async () => {
  const pending = state.pendingEdit;
  if (!pending) {
    showReviewError("The review is out of date.", ["Go back, review your buttons again, then confirm."]);
    return;
  }

  const button = $("confirm-update-btn");
  $("review-error").hidden = true;
  setBusy(button, true, pending.operation === "existing"
    ? `Updating ${state.provider === "grid3" ? "Grid 3" : "TD Snap"} and checking…`
    : "Creating and checking…");
  $("step-result").setAttribute("aria-busy", "true");
  setActivity(pending.operation === "existing"
    ? `Updating ${state.provider === "grid3" ? "Grid 3" : "TD Snap"} and checking the result…`
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
    if (state.provider === "tdsnap" || state.mode === "file") {
      try {
        await refreshDetectedPages();
      } catch {
        // The requested edit is already verified. A later reconnect can refresh the list.
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
