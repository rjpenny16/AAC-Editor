/* The wizard: which step is showing, how the user moves between them, and
 * where step-level errors appear.
 *
 * One question per screen, with review and confirmation kept separate and
 * explicit. Nothing here may skip a confirmation step — every path to a write
 * goes through review.
 */

import { state } from "./state.js";
import { $ } from "./dom.js";
import { autoFormatTopicRows, renderWords, updateTopicInputRow } from "./chips.js";
import { loadTargetLayout } from "./connect.js";
import { clearDraft, takePendingResume } from "./draft.js";
import { loadParentCapacity, titleOf, updatePlacementRecommendation } from "./parents.js";

/* ---------- helpers ---------- */

/* Fetch the per-run token (and native flag) once. Every POST awaits this so
   a fast first click can't race the config request and get a 403. */

function headingFor(step) {
  return {
    connect: "load-heading",
    operation: "operation-heading",
    title: "title-heading",
    destination: "destination-heading",
    items: "items-heading",
    layout: "layout-heading",
    placement: "placement-heading",
    review: "result-heading",
    result: "result-heading",
  }[step];
}

function updateProgress(step) {
  const stage = step === "result" ? "done"
    : ["review", "placement"].includes(step) ? "review"
      : ["items", "layout"].includes(step) ? "add" : "setup";
  const labels = { setup: "Setup", add: "Add", review: "Review", done: "Done" };
  const stages = ["add", "review", "done"];
  const index = stages.indexOf(stage);
  document.querySelectorAll("#wizard-progress [data-stage]").forEach((item) => {
    const itemIndex = stages.indexOf(item.dataset.stage);
    item.classList.toggle("complete", index > itemIndex);
    if (item.dataset.stage === stage) item.setAttribute("aria-current", "step");
    else item.removeAttribute("aria-current");
  });
  const label = labels[stage];
  $("wizard-progress-label").textContent = label;
  $("wizard-announcer").textContent = label;
}

/* Every provider reaches the items step by a different path (tdsnap: live
   connect → operation → destination; grid3: straight from connect; file:
   connect → title → destination) so this is the one place robust to all of
   them — applied once, the moment a resumed draft has somewhere to land. */
function applyPendingDraftResume() {
  const draft = takePendingResume();
  if (!draft) return;
  // The stored draft uses the request-shaped `symbol_query`; state.words uses
  // the camel-cased field the editor reads and writes.
  state.words = draft.items.map(({ symbol_query: query, ...item }) => ({
    ...item,
    symbolQuery: query || null,
  }));
  if (draft.page_style) setPageStyle(draft.page_style);
  if (draft.active_fn) setActiveFn(draft.active_fn, false);
  renderWords();
  void clearDraft();
}

function show(step, focus = true) {
  if (step === "load") step = "connect";
  state.wizardStep = step;
  document.body.dataset.step = step;
  if (step === "items") applyPendingDraftResume();

  const buildSteps = ["operation", "title", "destination", "items", "layout", "placement"];
  $("step-load").hidden = step !== "connect";
  $("step-build").hidden = !buildSteps.includes(step);
  $("step-result").hidden = !["review", "result"].includes(step);
  document.querySelectorAll("[data-wizard-step]").forEach((section) => {
    section.hidden = section.dataset.wizardStep !== step;
  });
  updateProgress(step);

  const active = step === "connect"
    ? $("step-load")
    : ["review", "result"].includes(step)
      ? $("step-result")
      : $(`wizard-${step}`);
  if (active && typeof active.scrollIntoView === "function") {
    active.scrollIntoView({ behavior: "auto", block: "start" });
  }
  if (focus) {
    const heading = $(headingFor(step));
    if (heading) {
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
    }
  }
}

function setOperation(operation) {
  state.operation = operation;
  state.pendingEdit = null;
  const existing = operation === "existing";
  $("operation-existing").classList.toggle("selected", existing);
  $("operation-existing").setAttribute("aria-checked", existing);
  $("operation-new").classList.toggle("selected", !existing);
  $("operation-new").setAttribute("aria-checked", !existing);
  $("operation-existing").tabIndex = existing ? 0 : -1;
  $("operation-new").tabIndex = existing ? -1 : 0;
  $("title-field").hidden = existing;
  $("destination-heading").textContent = existing
    ? "Which page would you like to change?"
    : "Where should people find this page?";
  $("placement-advice").hidden = false;
  if (existing) {
    $("placement-title").textContent = "Start with a familiar page";
    $("placement-copy").textContent =
      "Choose the page where these words already belong. You can create a separate page later.";
    $("use-placement").hidden = true;
  }
  $("target-label").textContent = existing ? "Page to change" : "Find it from";
  $("destination-intro").textContent = existing
    ? state.mode === "file"
      ? "Choose the page in this exported copy that the new buttons belong on."
      : "The page open in TD Snap is selected. Choose another page if this vocabulary belongs elsewhere."
    : "Choose the existing page where the new page's link belongs.";
  $("operation-hint").textContent = existing
    ? "Start by choosing the page where this vocabulary belongs."
    : "Name the new page, then choose where its link belongs.";
  $("preview-hint").textContent = "Drag buttons to move them, or use the arrow keys.";
  $("build-btn-label").textContent = "Review changes";
  $("current-page-label").textContent = existing
    ? `Adding to ${titleOf(state.parentId)}`
    : `Creating ${$("title-input").value.trim() || "a new page"}`;
  state.existingButtons = existing ? state.existingButtons : [];
  state.layoutFingerprint = existing ? state.layoutFingerprint : null;
  if (!existing) state.parentFree = null;
  updateProgress(state.wizardStep);
  renderWords();
}

$("operation-existing").addEventListener("click", async () => {
  setOperation("existing");
  try {
    await loadTargetLayout(titleOf(state.parentId));
  } catch (error) {
    showBuildError("Couldn’t load the selected TD Snap page.", [error.message]);
  }
});
$("operation-new").addEventListener("click", () => {
  setOperation("new");
  updatePlacementRecommendation();
});

function clearStepError(step) {
  const error = document.querySelector(`[data-error-for="${step}"]`);
  if (!error) return;
  error.textContent = "";
  error.hidden = true;
}

function showStepError(step, message) {
  const error = document.querySelector(`[data-error-for="${step}"]`);
  if (!error) return;
  error.textContent = message;
  error.hidden = false;
  error.focus({ preventScroll: true });
}

async function continueWizard() {
  clearStepError(state.wizardStep);
  if (state.wizardStep === "operation") {
    if (state.operation === "new") {
      show("title");
      return;
    }
    if (!state.layoutFingerprint && state.parentId) {
      try {
        await loadTargetLayout(titleOf(state.parentId));
      } catch (error) {
        showStepError("operation", `We couldn't read that page. ${error.message}`);
        return;
      }
    }
    show("destination");
    return;
  }

  if (state.wizardStep === "title") {
    const title = $("title-input").value.trim();
    if (!title) {
      showStepError("title", "Enter a name for the new page.");
      return;
    }
    if (state.pages.some(
      (page) => page.title.trim().toLocaleLowerCase() === title.toLocaleLowerCase()
    )) {
      showStepError("title", `A page named “${title}” already exists. Choose a different name.`);
      return;
    }
    updatePlacementRecommendation();
    show("destination");
    try {
      await loadParentCapacity();
    } catch (error) {
      showStepError("destination", `We couldn't check that page. ${error.message}`);
    }
    return;
  }

  if (state.wizardStep === "destination") {
    if (!state.parentId) {
      showStepError("destination", "Choose a page before continuing.");
      return;
    }
    if (state.operation === "existing" && state.targetLoading) {
      showStepError("destination", "Please wait while the page finishes loading.");
      return;
    }
    if (state.operation === "existing" && !state.layoutFingerprint) {
      try {
        await loadTargetLayout(titleOf(state.parentId));
      } catch (error) {
        showStepError("destination", `We couldn't read that page. ${error.message}`);
        return;
      }
    }
    if (state.operation === "new" && state.parentFree === null) {
      try {
        await loadParentCapacity();
      } catch (error) {
        showStepError("destination", `We couldn't check that page. ${error.message}`);
        return;
      }
    }
    if (state.operation === "new" && state.parentFree === 0) {
      showStepError("destination", "That page is full. Choose a page with an open space.");
      return;
    }
    show("items");
  }
}

function backWizard() {
  clearStepError(state.wizardStep);
  if (state.provider === "grid3") {
    show("connect");
    return;
  }
  // Exported files walk the same two routes as TD Snap live now that they can
  // add to an existing page, so one map serves both.
  const previous = state.operation === "new"
    ? { operation: "connect", title: "operation", destination: "title", items: "destination" }
    : { operation: "connect", destination: "operation", items: "destination" };
  show(previous[state.wizardStep] || "operation");
}

document.querySelectorAll(".wizard-next").forEach((button) => {
  button.addEventListener("click", continueWizard);
});
document.querySelectorAll(".wizard-back").forEach((button) => {
  button.addEventListener("click", backWizard);
});

/* ---------- step 2: page style + function palette ---------- */

function setPageStyle(style) {
  state.pageStyle = style;
  state.autoTopicRows = style === "topic";
  $("chipbox").classList.toggle("topic-mode", style === "topic");
  delete $("word-input").dataset.forced;
  $("style-words").classList.toggle("selected", style === "words");
  $("style-words").setAttribute("aria-checked", style === "words");
  $("style-topic").classList.toggle("selected", style === "topic");
  $("style-topic").setAttribute("aria-checked", style === "topic");
  $("style-words").tabIndex = style === "words" ? 0 : -1;
  $("style-topic").tabIndex = style === "topic" ? 0 : -1;
  $("fn-palette").hidden = style !== "topic";
  $("style-hint").textContent =
    style === "topic"
      ? "Quick-fire phrases and color-coded buttons for talking about one topic."
      : "Single words — each button speaks its label.";
  document.querySelector(".buttons-hint").textContent = style === "topic"
    ? "Add phrases across the communication functions below."
    : "Add one word per button.";
  $("preview-legend").hidden = style !== "topic";
  $("ai-go").textContent = style === "topic" ? "Suggest phrases" : "Suggest words";
  $("ai-summary-text").textContent =
    style === "topic" ? "Suggest phrases with AI" : "Suggest words with AI";
  if (style !== "topic") setActiveFn("", false);
  else autoFormatTopicRows();
}

function setActiveFn(fn, manual = true) {
  state.activeFn = fn;
  if (manual) state.autoTopicRows = false;
  document.querySelectorAll("#fn-palette .fn-pill").forEach((pill) => {
    const selected = pill.dataset.fn === fn;
    pill.classList.toggle("selected", selected);
    pill.setAttribute("aria-checked", selected);
    pill.tabIndex = selected ? 0 : -1;
  });
  updateTopicInputRow();
}

$("style-words").addEventListener("click", () => setPageStyle("words"));
$("style-topic").addEventListener("click", () => {
  setPageStyle("topic");
  if (state.operation === "new") updatePlacementRecommendation();
  if (state.wizardStep === "items") $("word-input").focus();
});
$("layout-options-btn").addEventListener("click", () => show("layout"));
$("layout-back-btn").addEventListener("click", () => show("items"));
$("auto-topic-layout").addEventListener("click", () => {
  state.autoTopicRows = true;
  autoFormatTopicRows();
});
document.querySelectorAll("#fn-palette .fn-pill").forEach((pill) =>
  pill.addEventListener("click", () => setActiveFn(pill.dataset.fn))
);

function clearBuildError() {
  const errorBox = $("build-error");
  errorBox.hidden = true;
  errorBox.innerHTML = "";
}

function showBuildError(message, details) {
  const errorBox = $("build-error");
  errorBox.innerHTML = "";
  const lead = document.createElement("strong");
  lead.textContent = message;
  errorBox.append(lead);
  if (details.length) {
    const list = document.createElement("ul");
    details.forEach((detail) => {
      const item = document.createElement("li");
      item.textContent = detail;
      list.append(item);
    });
    errorBox.append(list);
  }
  errorBox.hidden = false;
}

export { clearBuildError, clearStepError, continueWizard, setActiveFn, setOperation, setPageStyle, show, showBuildError, showStepError };
