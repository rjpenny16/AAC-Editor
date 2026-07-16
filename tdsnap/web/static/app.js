/* AAC Editor frontend. Plain JS, no build step.
   One-question wizard with a separate, explicit review and confirmation. */

"use strict";

const $ = (id) => document.getElementById(id);

/* Communicative-function color coding used on topic pages: each function
   gets the same colored border TD Snap renders around the button. */
const FUNCTIONS = {
  question: { name: "Question", color: "#1E88E5" },
  comment: { name: "Comment", color: "#F57C00" },
  positive: { name: "Positive", color: "#43A047" },
  negative: { name: "Negative", color: "#E53935" },
  personal: { name: "Personal", color: "#8E24AA" },
};

const QUESTION_PHRASE = /^(who|what|when|where|why|how|which|whose|is|are|am|was|were|do|does|did|can|could|would|will|should|may|have|has)\b/i;
const NEGATIVE_PHRASE = /\b(no|not|never|don't|doesn't|didn't|can't|cannot|won't|hate|dislike|stop|bad|boring|scary|wrong|upset|angry|sad|too loud|too busy)\b/i;
const OWNERSHIP_PHRASE = /\b(my|mine|our|ours)\b/i;
const PERSONAL_PHRASE = /^i\s+(am|was|have|had|went|saw|read|live|remember|tried|visited|played|watched|ate)\b/i;
const POSITIVE_PHRASE = /\b(love|like|enjoy|favorite|great|good|fun|awesome|amazing|excited|happy|delicious|beautiful|cool|yes|agree|please|want|best)\b/i;

function inferPhraseFunction(label, suggested = "") {
  const text = String(label || "").trim().replaceAll("’", "'");
  if (text.endsWith("?") || QUESTION_PHRASE.test(text)) return "question";
  if (NEGATIVE_PHRASE.test(text)) return "negative";
  if (OWNERSHIP_PHRASE.test(text)) return "personal";
  if (POSITIVE_PHRASE.test(text)) return "positive";
  if (PERSONAL_PHRASE.test(text)) return "personal";
  return suggested && suggested !== "question" ? suggested : "comment";
}

const state = {
  mode: "live",
  connected: false,
  operation: "existing", // "existing" | "new"
  wizardStep: "connect",
  pendingEdit: null,
  placementAdjusted: false,
  grid: { cols: 8, rows: 5 },
  existingButtons: [],
  layoutFingerprint: null,
  pages: [],
  words: [], // [{label, message|null, fn|"", slot, symbol}]
  pageStyle: "words", // "words" | "topic"
  activeFn: "",
  autoTopicRows: false,
  parentId: null,
  parentFree: null,
  parentTouched: false,
  recommendedParent: null,
  currentPage: "",
  edits: 0,
  native: false, // running inside the app's own window (pywebview)?
  apiToken: "",
  targetLoading: false,
};

let liveMonitor = null;
let liveSyncing = false;

/* ---------- helpers ---------- */

/* Fetch the per-run token (and native flag) once. Every POST awaits this so
   a fast first click can't race the config request and get a 403. */
const configReady = (async () => {
  try {
    const response = await fetch("/api/config");
    const config = await response.json();
    state.apiToken = config.token || "";
    state.native = Boolean(config.native);
  } catch {
    /* keep going; the server will reject protected POSTs if it is older */
  }
})();

async function api(path, options) {
  await configReady;
  options = options || {};
  options.headers = Object.assign(
    {},
    options.headers,
    state.apiToken ? { "X-TDSnap-Token": state.apiToken } : {}
  );
  const response = await fetch(path, options).catch(() => {
    throw new Error("The local editor isn’t responding. Try again; if it continues, restart the app.");
  });
  let data = null;
  try {
    data = await response.json();
  } catch {
    throw new Error(`Unexpected response from the app (${response.status}).`);
  }
  if (!response.ok || data.ok === false) {
    const error = new Error(data.error || `Request failed (${response.status}).`);
    error.problems = data.problems || null;
    throw error;
  }
  return data;
}

function stepsFor(operation = state.operation) {
  return operation === "new"
    ? ["connect", "operation", "title", "destination", "items", "review"]
    : ["connect", "operation", "destination", "items", "review"];
}

function stepName(step) {
  if (step === "connect") return "Connect";
  if (step === "operation") return "Choose a task";
  if (step === "title") return "Name the page";
  if (step === "destination") {
    return state.operation === "existing" ? "Choose a page" : "Choose where it belongs";
  }
  if (step === "items") return "Add words or phrases";
  if (step === "review") return "Review";
  return "Adjust placement";
}

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
  const steps = stepsFor();
  const complete = step === "result";
  const shownStep = step === "placement" ? "review" : step === "layout" ? "items" : step;
  const index = Math.max(0, steps.indexOf(shownStep));
  const value = complete ? steps.length : index + 1;
  const label = complete
    ? "Complete"
    : step === "placement" || step === "layout"
      ? `Optional · ${step === "placement" ? "Adjust placement" : "Change page layout"}`
      : `Step ${value} of ${steps.length} · ${stepName(step)}`;
  const progress = $("wizard-progress");
  progress.max = steps.length;
  progress.value = value;
  progress.textContent = `${value} of ${steps.length}`;
  $("wizard-progress-label").textContent = label;
  $("wizard-progress-percent").textContent = `${Math.round((value / steps.length) * 100)}%`;
  $("wizard-announcer").textContent = label;
}

function show(step, focus = true) {
  if (step === "load") step = "connect";
  state.wizardStep = step;
  document.body.dataset.step = step;

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
    const compactReflow = window.matchMedia(
      "(max-height: 40rem), (min-resolution: 1.75dppx)"
    ).matches;
    const scrollTarget = compactReflow
      ? document.querySelector(".wizard-progress")
      : active;
    scrollTarget.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  if (focus) {
    const heading = $(headingFor(step));
    if (heading) {
      heading.tabIndex = -1;
      requestAnimationFrame(() => heading.focus({ preventScroll: true }));
    }
  }
}

function setBusy(button, busy, busyLabel = "") {
  const label = button.querySelector(".btn-label") || button;
  if (busy && !label.dataset.idleLabel) label.dataset.idleLabel = label.textContent;
  if (busy && busyLabel) label.textContent = busyLabel;
  if (!busy && label.dataset.idleLabel) {
    label.textContent = label.dataset.idleLabel;
    delete label.dataset.idleLabel;
  }
  button.classList.toggle("loading", busy);
  button.disabled = busy;
  button.setAttribute("aria-busy", String(busy));
}

function setActivity(message = "") {
  const activity = $("app-activity");
  $("app-activity-text").textContent = message;
  activity.hidden = !message;
  document.body.setAttribute("aria-busy", String(Boolean(message)));
}

function setPreviewBusy(busy, message = "Loading the page layout…") {
  const workspace = document.querySelector(".preview-frame");
  const loading = $("preview-loading");
  workspace.classList.toggle("is-loading", busy);
  workspace.setAttribute("aria-busy", String(busy));
  $("preview-loading-text").textContent = message;
  loading.hidden = !busy;
}

/* ---------- step 1: connect to live TD Snap ---------- */

function rememberDetectedPages(data) {
  const detected = Array.isArray(data.pages) && data.pages.length
    ? data.pages
    : [data.page, "Topics Menu Page"];
  state.pages = [...new Set(detected.filter(Boolean))].map((title) => ({
    id: title,
    title,
  }));
}

async function refreshDetectedPages() {
  const data = await api("/api/tdsnap/status");
  rememberDetectedPages(data);
  renderParents(parentFilter.value);
  return data;
}

$("live-connect-btn").addEventListener("click", async () => {
  const button = $("live-connect-btn");
  const status = $("live-status");
  if (state.connected) {
    show("operation");
    return;
  }
  status.classList.remove("error");
  status.textContent = "Checking TD Snap...";
  setActivity("Checking for TD Snap…");
  setBusy(button, true, "Connecting…");
  try {
    let data = await api("/api/tdsnap/status");
    if (!data.available) throw new Error("Direct editing is available on Windows only.");
    if (!data.running) {
      status.textContent = "Opening TD Snap…";
      setActivity("Opening TD Snap…");
      await api("/api/tdsnap/launch", { method: "POST" });
      for (let attempt = 0; attempt < 60 && !data.running; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 500));
        data = await api("/api/tdsnap/status");
      }
    }
    if (!data.running) throw new Error(data.error || "TD Snap did not finish opening. Try again.");
    if (!data.unlocked) throw new Error("Unlock Windows, then try again.");

    state.mode = "live";
    state.connected = true;
    state.grid = data.grid;
    state.currentPage = data.page;
    rememberDetectedPages(data);
    state.words = [];
    state.parentId = data.page;
    state.parentFree = 1;
    state.parentTouched = false;
    state.recommendedParent = data.page;
    state.edits = 0;
    state.pendingEdit = null;
    state.placementAdjusted = false;

    $("file-badge").textContent = "Connected to TD Snap";
    $("file-badge").hidden = false;
    $("build-sub").textContent =
      `Connected to “${data.page}” · ${data.grid.cols}×${data.grid.rows} grid · ` +
      `${state.pages.length} pages in this page set`;
    $("preview-live-text").textContent = `Live · ${data.page}`;
    $("build-btn-label").textContent = "Review changes";
    status.textContent = "";
    button.querySelector(".btn-label").dataset.idleLabel = "Continue";
    renderParents("");
    setOperation("existing");
    setActivity("Reading the current TD Snap page…");
    await loadTargetLayout(data.page);
    show("operation");
    startLiveMonitor();
  } catch (error) {
    status.classList.add("error");
    status.textContent = `Couldn’t connect to TD Snap. ${error.message}`;
  } finally {
    setActivity();
    setBusy(button, false);
  }
});

async function loadTargetLayout(pageName, currentOnly = false) {
  if (state.operation !== "existing" || (!pageName && !currentOnly)) return null;
  clearBuildError();
  state.targetLoading = true;
  state.parentFree = null;
  parentSelect.disabled = true;
  $("parent-capacity").textContent = "Loading the existing layout…";
  setPreviewBusy(true, currentOnly
    ? "Refreshing the live TD Snap page…"
    : `Loading “${pageName}”…`);
  try {
    const data = await api(currentOnly
      ? "/api/tdsnap/page-layout"
      : `/api/tdsnap/page-layout?page=${encodeURIComponent(pageName)}`);
    state.grid = data.grid;
    state.existingButtons = data.buttons || [];
    state.layoutFingerprint = data.fingerprint;
    state.parentFree = data.free_slots.length;
    const occupied = new Set(state.existingButtons.map((button) => button.slot));
    state.words.forEach((item) => {
      if (occupied.has(item.slot)) item.slot = firstAvailableSlot(item.fn);
    });
    $("parent-capacity").classList.remove("error");
    $("parent-capacity").textContent =
      `${data.free_slots.length} empty cell${data.free_slots.length === 1 ? "" : "s"} on “${data.page}”.`;
    renderWords();
    return data;
  } catch (error) {
    state.existingButtons = [];
    state.layoutFingerprint = null;
    $("parent-capacity").classList.add("error");
    $("parent-capacity").textContent = "The layout could not be loaded.";
    renderWords();
    throw error;
  } finally {
    state.targetLoading = false;
    parentSelect.disabled = false;
    setPreviewBusy(false);
  }
}

function startLiveMonitor() {
  clearInterval(liveMonitor);
  liveMonitor = setInterval(syncLivePreview, 750);
}

async function syncLivePreview() {
  // Only mirror TD Snap while editing an existing page. In new-page mode the
  // builder owns the grid, parent, and word layout — following the live page
  // would overwrite the design (e.g. collapse a topic page onto a smaller grid).
  if (liveSyncing || state.targetLoading || state.mode !== "live" ||
      state.operation !== "existing" || $("step-build").hidden) return;
  liveSyncing = true;
  try {
    const selectedPage = state.parentId;
    const status = await api("/api/tdsnap/status", {
      headers: { "X-TDSnap-Brief": "1" },
    });
    if (state.targetLoading || state.parentId !== selectedPage) return;
    if (!status.running || !status.page || status.page === state.currentPage) return;
    const layout = await loadTargetLayout("", true);
    state.currentPage = layout.page;
    state.parentId = layout.page;
    state.parentTouched = false;
    state.grid = layout.grid;
    $("build-sub").textContent =
      `Following “${layout.page}” · ${layout.grid.cols}×${layout.grid.rows} grid · ` +
      `${state.pages.length} pages in this page set`;
    $("preview-live-text").textContent = `Live · ${layout.page}`;
    renderParents(parentFilter.value);
  } catch {
    // TD Snap briefly has no page grid while navigating; the next poll retries.
  } finally {
    liveSyncing = false;
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
    ? "The page open in TD Snap is selected. Choose another page if this vocabulary belongs elsewhere."
    : "Choose the existing page where the new page's link belongs.";
  $("operation-hint").textContent = existing
    ? "Start by choosing the page where this vocabulary belongs."
    : "Name the new page, then choose where its link belongs.";
  $("preview-hint").textContent = "Drag buttons to move them, or use the arrow keys.";
  $("build-btn-label").textContent = "Review changes";
  state.existingButtons = existing ? state.existingButtons : [];
  state.layoutFingerprint = existing ? state.layoutFingerprint : null;
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
    updatePlacementRecommendation();
    show("destination");
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
    if (state.operation === "new" && state.parentFree === 0) {
      showStepError("destination", "That page is full. Choose a page with an open space.");
      return;
    }
    show("items");
  }
}

function backWizard() {
  clearStepError(state.wizardStep);
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

/* ---------- step 2: words (chip editor) ---------- */

const chipbox = $("chipbox");
const wordInput = $("word-input");

const TOPIC_FUNCTIONS = ["question", "comment", "positive", "negative", "personal"];

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
    if (!used.has(slot)) available.push(slot);
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
  const capacity = state.grid.cols * state.grid.rows - state.existingButtons.length;
  let duplicates = 0;
  let overflow = 0;
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
        duplicates += 1;
      } else if (state.words.length >= capacity) {
        overflow += 1;
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
  // Say when something was silently dropped, or a pasted list quietly
  // loses words and the user only finds out inside TD Snap.
  const skipped = [];
  if (overflow) {
    skipped.push(
      `${overflow} word${overflow === 1 ? "" : "s"} didn't fit — the ` +
      `${state.grid.cols}×${state.grid.rows} grid is full`
    );
  }
  if (duplicates) {
    skipped.push(
      `${duplicates} duplicate${duplicates === 1 ? "" : "s"} skipped`
    );
  }
  $("chip-note").textContent = skipped.length ? skipped.join(" · ") + "." : "";
  renderWords();
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

  const capacity = state.grid.cols * state.grid.rows - state.existingButtons.length;
  const meter = $("capacity");
  meter.textContent = `${state.words.length} of ${capacity} cells`;
  meter.classList.toggle("full", state.words.length >= capacity);
  wordInput.disabled = state.words.length >= capacity;
  wordInput.placeholder = state.pageStyle === "topic"
    ? "+"
    : state.words.length
      ? ""
      : "Type a word, press Enter — or paste a comma-separated list";
  updateTopicInputRow();
  renderPreview();
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

/* ---------- step 2: parent picker ---------- */

const parentSelect = $("parent-select");
const parentFilter = $("parent-filter");

parentFilter.addEventListener("input", () => renderParents(parentFilter.value));
$("parent-filter-clear").addEventListener("click", () => {
  parentFilter.value = "";
  renderParents("");
  parentFilter.focus();
});

parentSelect.addEventListener("change", async () => {
  state.parentId = parentSelect.value;
  state.parentTouched = true;
  state.parentFree = 1;
  if (state.operation === "existing") {
    try {
      await loadTargetLayout(titleOf(state.parentId));
    } catch (error) {
      showBuildError("Couldn’t load the selected TD Snap page.", [error.message]);
    }
  } else {
    $("parent-capacity").classList.remove("error");
    $("parent-capacity").textContent =
      `The link will use the first free cell on “${titleOf(state.parentId)}”.`;
  }
});

function titleOf(pageId) {
  const page = state.pages.find((p) => p.id === pageId);
  return page ? page.title : `Page ${pageId}`;
}

const AAC_PAGE_GROUPS = [
  { words: ["food", "snack", "drink", "meal", "eat"], pages: ["eating", "cooking", "restaurant"] },
  { words: ["game", "play", "toy", "minecraft"], pages: ["games", "toy play", "minecraft"] },
  { words: ["family", "mom", "dad", "sister", "brother", "friend", "people"], pages: ["my family", "about me"] },
  { words: ["school", "class", "teacher", "lesson", "learn"], pages: ["classroom", "reading"] },
  { words: ["feel", "body", "health", "doctor", "appointment"], pages: ["self care", "body safety", "appointment"] },
  { words: ["music", "song", "sing", "instrument"], pages: ["music"] },
  { words: ["sport", "ball", "team", "exercise"], pages: ["sports"] },
  { words: ["shop", "buy", "store", "money"], pages: ["shopping"] },
  { words: ["car", "bus", "train", "travel", "ride"], pages: ["transportation", "community"] },
  { words: ["art", "draw", "paint", "craft", "create"], pages: ["art"] },
  { words: ["book", "story", "read"], pages: ["reading"] },
  { words: ["joke", "funny", "laugh"], pages: ["jokes"] },
];

function tokens(text) {
  const found = String(text || "").toLowerCase().match(/[a-z0-9]+/g) || [];
  const normalized = new Set(found);
  found.forEach((word) => {
    if (word.length > 3 && word.endsWith("s")) normalized.add(word.slice(0, -1));
  });
  return normalized;
}

function recommendParent(title) {
  const wanted = tokens(title);
  if (!wanted.size || !state.pages.length) return state.currentPage || state.pages[0].id;
  let best = null;
  state.pages.forEach((page) => {
    const pageTokens = tokens(page.title);
    let score = [...wanted].filter((token) => pageTokens.has(token)).length * 8;
    AAC_PAGE_GROUPS.forEach((group) => {
      const queryMatches = group.words.some((word) => wanted.has(word));
      const pageMatch = group.pages.findIndex((name) =>
        page.title.toLowerCase().includes(name)
      );
      if (queryMatches && pageMatch >= 0) score += 6 + group.pages.length - pageMatch;
    });
    if (page.id === state.currentPage && page.title !== "Topics Menu Page") score += 2;
    if (/^your topic \d+$/i.test(page.title)) score -= 4;
    if (!best || score > best.score) best = { id: page.id, title: page.title, score };
  });
  if (best && best.score > 0) return best.id;
  return (state.pages.find((page) => page.id === state.currentPage) || state.pages[0]).id;
}

function updatePlacementRecommendation() {
  const recommendation = recommendParent($("title-input").value);
  state.recommendedParent = recommendation;
  let title = titleOf(recommendation);
  const hasName = Boolean($("title-input").value.trim());
  $("placement-title").textContent = hasName ? `Suggested location: ${title}` : "AAC-friendly placement";
  $("placement-copy").textContent = hasName
    ? `This is the closest existing category the app can detect. Keeping related fringe vocabulary together makes it easier to find without moving established words.`
    : "Name the page above and the app will suggest an existing location, keeping related vocabulary together.";
  if (!state.parentTouched && recommendation) {
    state.parentId = recommendation;
    renderParents(parentFilter.value);
    title = titleOf(state.parentId);
    $("parent-capacity").textContent =
      `The link will use the first free cell on “${title}”.`;
  }
  $("use-placement").hidden = !hasName || state.parentId === recommendation;
}

$("title-input").addEventListener("input", () => {
  updatePlacementRecommendation();
  renderPreview();
});
$("use-placement").addEventListener("click", () => {
  state.parentId = state.recommendedParent;
  state.parentTouched = false;
  parentFilter.value = "";
  renderParents("");
  updatePlacementRecommendation();
});

function renderParents(filter) {
  const query = filter.trim().toLowerCase();
  parentSelect.innerHTML = "";
  const matches = state.pages.filter(
    (page) => !query || page.title.toLowerCase().includes(query)
  );
  const selected = state.pages.find((page) => page.id === state.parentId);
  if (selected && !matches.includes(selected)) matches.unshift(selected);
  matches
    .forEach((page) => {
      const option = document.createElement("option");
      option.value = page.id;
      option.textContent = page.title;
      if (page.id === state.parentId) option.selected = true;
      parentSelect.append(option);
    });
  if (!parentSelect.options.length) {
    const option = document.createElement("option");
    option.disabled = true;
    option.textContent = "No pages match";
    parentSelect.append(option);
  }
}

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

function renderPreview() {
  const preview = $("preview");
  const previewTitle = state.operation === "existing"
    ? titleOf(state.parentId)
    : $("title-input").value.trim();
  $("preview-page-title").textContent = previewTitle || "AAC page preview";
  preview.style.setProperty("--cols", state.grid.cols);
  preview.style.setProperty("--rows", state.grid.rows);
  preview.classList.toggle("topic-preview", state.pageStyle === "topic");
  preview.innerHTML = "";
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
    if (existing) {
      cell.classList.add("existing");
      addPreviewCellContent(cell, existing.label || "Existing button", "", state.pageStyle !== "topic");
      cell.title = "Existing TD Snap button — position preserved";
      cell.setAttribute("aria-label", `${existing.label || "Existing button"}, existing and locked`);
    }
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

function movePreviewItem(index, targetSlot) {
  const item = state.words[index];
  if (!item || item.slot === targetSlot) return;
  if (state.existingButtons.some((button) => button.slot === targetSlot)) return;
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

/* ---------- step 2: AI engines ---------- */

let aiReady = false;

$("ai-suggest").addEventListener("toggle", () => {
  if ($("ai-suggest").open && !aiReady) checkAi();
});

async function checkAi() {
  const label = $("ai-engine-state");
  const card = $("ai-download-card");
  try {
    const data = await api(
      `/api/ai/status?host=${encodeURIComponent($("ai-host").value)}`
    );
    const local = data.local;
    $("ai-model-name").textContent = local.model.name;
    $("ai-model-size").textContent = local.model.size;
    $("ai-model-license").textContent = local.model.license;

    const installed = data.ollama.models;
    if (data.ollama.reachable && installed.length) {
      aiReady = true;
      card.hidden = true;
      // Point the model box at a model that's actually installed, unless the
      // user typed one themselves — otherwise the default "llama3.2" fails
      // on servers that only have other models.
      const modelInput = $("ai-model");
      const known = installed.some(
        (name) => name === modelInput.value || name.split(":")[0] === modelInput.value
      );
      if (!known && !modelInput.dataset.userEdited) {
        modelInput.value = installed[0];
      }
      label.textContent =
        `Using your Ollama server (${installed.length} model${installed.length === 1 ? "" : "s"}).`;
    } else if (local.engine_available && local.downloaded) {
      aiReady = true;
      card.hidden = true;
      label.textContent = `Built-in model ready (${local.model.name}).`;
    } else if (local.engine_available) {
      aiReady = false;
      card.hidden = false;
      label.textContent = data.ollama.reachable
        ? "Ollama is connected, but no model is installed. Run the command in the Ollama steps below, or download the built-in model."
        : "No AI model is ready yet. Follow the built-in setup below, or use the Ollama instructions.";
      if (local.download.status === "downloading") trackDownload();
    } else {
      aiReady = false;
      card.hidden = true;
      label.textContent = data.ollama.reachable
        ? "Ollama is connected, but no model is installed. Run ollama pull llama3.2, then click Check connection."
        : "No AI model is ready. This install needs Ollama; follow the setup steps below.";
    }
    $("ai-go").disabled = !aiReady;
  } catch {
    aiReady = false;
    $("ai-go").disabled = true;
    label.textContent = "Could not check the local AI status. Check that the app is still connected, then try again.";
  }
}

async function checkAiWithFeedback() {
  const button = $("ai-check-btn");
  $("ai-engine-state").textContent = "Checking the Ollama connection…";
  setActivity("Checking your AI connection…");
  setBusy(button, true, "Checking…");
  try {
    await checkAi();
  } finally {
    setBusy(button, false);
    setActivity();
  }
}

$("ai-host").addEventListener("change", checkAiWithFeedback);
$("ai-check-btn").addEventListener("click", checkAiWithFeedback);
$("ai-model").addEventListener("input", () => {
  $("ai-model").dataset.userEdited = "1";
});

$("ai-download-btn").addEventListener("click", async () => {
  const button = $("ai-download-btn");
  const status = $("ai-download-status");
  status.classList.remove("error", "success");
  setBusy(button, true, "Starting download…");
  setActivity("Starting the model download…");
  try {
    await api("/api/ai/download", { method: "POST" });
    trackDownload();
  } catch (error) {
    setBusy(button, false);
    status.classList.add("error");
    status.textContent = `The model download couldn’t start. ${error.message}`;
  } finally {
    setActivity();
  }
});

let downloadTimer = null;

function trackDownload() {
  if (downloadTimer) return; // a poll is already running
  const button = $("ai-download-btn");
  const bar = $("ai-progress");
  const fill = $("ai-progress-fill");
  const status = $("ai-download-status");
  setBusy(button, true, "Downloading…");
  bar.hidden = false;

  downloadTimer = setInterval(async () => {
    try {
      const data = await api("/api/ai/download");
      const dl = data.download;
      if (dl.status === "downloading") {
        if (dl.total > 0) {
          const pct = Math.round((dl.done / dl.total) * 100);
          fill.style.width = `${pct}%`;
          bar.setAttribute("aria-valuenow", pct);
          status.textContent =
            `Downloading… ${(dl.done / 1e9).toFixed(2)} of ${(dl.total / 1e9).toFixed(2)} GB (${pct}%)`;
        } else {
          status.textContent = `Downloading… ${(dl.done / 1e9).toFixed(2)} GB`;
        }
        return;
      }
      clearInterval(downloadTimer);
      downloadTimer = null;
      setBusy(button, false);
      if (dl.status === "ready") {
        fill.style.width = "100%";
        status.classList.add("success");
        status.textContent = "Done — suggestions are ready.";
        checkAi();
      } else if (dl.status === "error") {
        status.classList.remove("success");
        status.classList.add("error");
        status.textContent = `Download failed: ${dl.error}. Click to retry.`;
        bar.hidden = true;
      }
    } catch {
      /* transient poll failure; keep trying */
    }
  }, 1000);
}

$("ai-go").addEventListener("click", async () => {
  const button = $("ai-go");
  const status = $("ai-status");
  const category = state.operation === "existing"
    ? titleOf(state.parentId)
    : $("title-input").value.trim();
  status.classList.remove("error", "success");
  if (!category) {
    status.classList.add("error");
    status.textContent = state.operation === "existing"
      ? "Choose an existing page first."
      : "Give the page a title first — it's used as the category.";
    return;
  }
  const topic = state.pageStyle === "topic";
  const what = topic
    ? state.activeFn
      ? `${FUNCTIONS[state.activeFn].name.toLowerCase()} phrases`
      : "phrases"
    : "words";
  setBusy(button, true, "Generating…");
  setActivity(`Generating ${what} for “${category}”…`);
  status.textContent = `Asking ${$("ai-model").value} for ${$("ai-count").value} “${category}” ${what}…`;
  try {
    const data = await api("/api/ai/words", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        category,
        count: Number($("ai-count").value) || 10,
        host: $("ai-host").value,
        model: $("ai-model").value,
        kind: topic ? "phrases" : "words",
        function: topic && state.activeFn ? state.activeFn : null,
        existing: [...new Set(state.existingButtons
          .map((item) => item.label.trim())
          .filter((label) => label && label.toLocaleLowerCase() !== "existing button"))],
      }),
    });
    // Phrases arrive comma-prone; add them one by one instead of splitting.
    const capacity = state.grid.cols * state.grid.rows - state.existingButtons.length;
    let added = 0;
    data.words.forEach((suggestion) => {
      const label = (typeof suggestion === "string"
        ? suggestion
        : String(suggestion.label || "")).trim();
      const suggestedFn = typeof suggestion === "object" && suggestion &&
        FUNCTIONS[suggestion.function] ? suggestion.function : "";
      const exists = [...state.existingButtons, ...state.words].some(
        (item) => item.label.toLocaleLowerCase() === label.toLocaleLowerCase()
      );
      if (label && !exists && state.words.length < capacity) {
        let fn = topic
          ? state.activeFn || inferPhraseFunction(label, suggestedFn)
          : "";
        const slot = firstAvailableSlot(topic && state.autoTopicRows ? fn : "");
        if (topic && !fn && state.autoTopicRows) fn = functionForSlot(slot);
        state.words.push({ label, message: null, fn, slot, symbol: true });
        added += 1;
      }
    });
    renderWords();
    status.classList.add("success");
    status.textContent = `Added ${added} suggestions — remove any you don't want.`;
  } catch (error) {
    status.classList.add("error");
    status.textContent = `Suggestions couldn’t be generated. ${error.message}`;
  } finally {
    setActivity();
    setBusy(button, false);
  }
});

/* ---------- step 2 → 3: build ---------- */

function clearBuildError() {
  const errorBox = $("build-error");
  errorBox.hidden = true;
  errorBox.innerHTML = "";
}

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

function prepareReview() {
  const title = $("title-input").value.trim();
  const parentTitle = titleOf(state.parentId);
  const operation = state.operation;
  const payload = freezePayload({
    operation: operation === "existing" ? "add_to_existing_page" : "create_page",
    title,
    items: state.words.map((item) => ({
      label: item.label,
      message: item.message,
      border_color: item.fn ? FUNCTIONS[item.fn].color : null,
      slot: item.slot,
      symbol: item.symbol !== false,
    })),
    parent: parentTitle,
    page: parentTitle,
    fingerprint: state.layoutFingerprint,
  });
  state.pendingEdit = Object.freeze({
    operation,
    path: operation === "existing" ? "/api/tdsnap/edit-plan" : "/api/tdsnap/page",
    payload,
    title,
    parentTitle,
    displayTitle: operation === "existing" ? parentTitle : title,
  });

  $("result-eyebrow").textContent = "Review";
  $("result-heading").textContent = operation === "existing"
    ? "Ready to update TD Snap?"
    : "Ready to create this page?";
  $("result-sub").textContent = "Check the details below. Nothing changes until you confirm.";
  $("review-state").hidden = false;
  $("success-state").hidden = true;
  $("review-action").textContent = operation === "existing"
    ? "Add buttons to an existing page"
    : "Create a new page";
  $("review-target").textContent = operation === "existing"
    ? parentTitle
    : `${title}, found from ${parentTitle}`;
  $("review-count").textContent = `${payload.items.length} button${payload.items.length === 1 ? "" : "s"}`;
  $("review-placement").textContent = state.placementAdjusted
    ? "The positions you chose"
    : "Automatic — the first open spaces";
  $("confirm-update-label").textContent = operation === "existing"
    ? "Update TD Snap"
    : "Create page in TD Snap";
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
    ? "Updating and checking…"
    : "Creating and checking…");
  $("step-result").setAttribute("aria-busy", "true");
  setActivity(pending.operation === "existing"
    ? "Updating TD Snap and checking the result…"
    : "Creating the page in TD Snap and checking the result…");
  try {
    const data = await api(pending.path, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-TDSnap-Editor": "1",
      },
      body: JSON.stringify(pending.payload),
    });
    state.edits = data.edits || state.edits + 1;
    try {
      await refreshDetectedPages();
    } catch {
      // The requested edit is already verified. A later reconnect can refresh the list.
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
    if (pending.operation === "new" && pending.title) {
      try {
        await refreshDetectedPages();
        const created = state.pages.find(
          (page) => page.title.toLocaleLowerCase() === pending.title.toLocaleLowerCase()
        );
        if (created) {
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
    showReviewError("TD Snap couldn't complete the edit.", [
      error.message,
      ...(error.problems || []),
    ]);
  } finally {
    setActivity();
    $("step-result").setAttribute("aria-busy", "false");
    setBusy(button, false);
  }
});

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

/* ---------- step 3: result ---------- */

const CHECK_LABELS = {
  sqlite_integrity: "The TD Snap page set is healthy",
  linkage_chains: "Every new button and page link is complete",
  roundtrip_diff: "Everything else stayed unchanged",
  td_snap_edit: "TD Snap saved the change",
  navigation: "The new page opens from the chosen page",
  target_page: "The chosen page was updated",
  content: "Every requested speaking button is present",
  positions: "Every new button is in the reviewed space",
  symbols: "Matching symbols were added when available",
  topic_format: "Topic-page row colors were applied in TD Snap",
};

const CHECK_SVG =
  '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
  'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<path d="M20 6 9 17l-5-5"/></svg>';

function renderResult(title, data, operation = state.operation, parentTitle = titleOf(state.parentId)) {
  $("review-state").hidden = true;
  $("success-state").hidden = false;
  $("result-eyebrow").textContent = "Complete";
  $("result-heading").textContent = "Done — TD Snap was updated";
  $("edit-count").textContent =
    state.edits > 1 ? `· ${state.edits} edits this session` : "";
  $("another-btn").textContent = "Make another edit";
  $("result-sub").textContent = operation === "existing"
    ? `${data.buttons} speaking button${data.buttons === 1 ? " was" : "s were"} added to “${title}” without moving its existing vocabulary.`
    : `“${title}” has ${data.buttons} speaking button${data.buttons === 1 ? "" : "s"}, and “${parentTitle}” now links to it.`;

  const checks = $("checks");
  checks.innerHTML = "";
  Object.entries(CHECK_LABELS).forEach(([key, label]) => {
    const status = data.checks && data.checks[key];
    if (!status) return;
    const item = document.createElement("li");
    item.classList.toggle("warning", status !== "pass");
    const icon = document.createElement("span");
    icon.className = "check-icon";
    if (status === "pass") icon.innerHTML = CHECK_SVG;
    else icon.textContent = "!";
    const text = document.createElement("span");
    text.textContent = status === "pass" ? label : `${label} — needs review`;
    item.append(icon, text);
    checks.append(item);
  });

  const warningBox = $("result-warnings");
  warningBox.innerHTML = "";
  const warnings = data.warnings || [];
  warningBox.hidden = warnings.length === 0;
  if (warnings.length) {
    const lead = document.createElement("strong");
    lead.textContent = "TD Snap finished with a note:";
    warningBox.append(lead);
    const list = document.createElement("ul");
    warnings.forEach((warning) => {
      const item = document.createElement("li");
      item.textContent = warning;
      list.append(item);
    });
    warningBox.append(list);
  }

}

$("another-btn").addEventListener("click", () => {
  state.words = [];
  state.parentId = state.currentPage;
  state.parentFree = 1;
  state.parentTouched = false;
  state.existingButtons = [];
  state.layoutFingerprint = null;
  state.pendingEdit = null;
  state.placementAdjusted = false;
  $("title-input").value = "";
  $("parent-capacity").textContent = "";
  $("chip-note").textContent = "";
  parentFilter.value = "";
  setOperation("existing");
  setPageStyle("words");
  renderParents("");
  renderWords();
  $("build-error").hidden = true;
  $("result-warnings").hidden = true;
  show("operation");
});

function resetConnection() {
  clearInterval(liveMonitor);
  state.mode = "live";
  state.connected = false;
  state.words = [];
  state.parentId = null;
  state.parentFree = null;
  state.pendingEdit = null;
  state.placementAdjusted = false;
  $("file-badge").hidden = true;
  $("title-input").value = "";
  $("live-status").textContent = "";
  $("live-connect-btn").querySelector(".btn-label").textContent = "Connect to TD Snap";
  $("parent-capacity").textContent = "";
  $("chip-note").textContent = "";
  $("build-error").hidden = true;
  renderWords();
  show("load");
}

$("reset-btn").addEventListener("click", resetConnection);
$("file-badge").addEventListener("click", resetConnection);

/* ---------- quit (browser mode) ---------- */

$("quit-btn").addEventListener("click", async () => {
  if (!window.confirm("Quit AAC Editor?")) return;
  setBusy($("quit-btn"), true, "Closing…");
  setActivity("Closing the local editor…");
  try {
    await api("/api/quit", { method: "POST" });
  } catch {
    /* the server may stop before the response arrives */
  }
  setActivity();
  setBusy($("quit-btn"), false);
  document.querySelector("main").hidden = true;
  document.querySelector("footer").hidden = true;
  $("quit-screen").hidden = false;
});

/* ---------- init ---------- */

configReady.then(() => {
  // In the native window the OS window close button quits the app;
  // in browser mode the Quit button is the only clean way to stop it.
  $("quit-btn").hidden = state.native;
});

/* Radio-style button groups use one tab stop and arrow-key navigation. */
document.querySelectorAll('[role="radiogroup"]').forEach((group) => {
  const selected = group.querySelector('[role="radio"][aria-checked="true"]');
  group.querySelectorAll('[role="radio"]').forEach((radio) => {
    radio.tabIndex = radio === selected ? 0 : -1;
  });
  group.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) {
      return;
    }
    const radios = [...group.querySelectorAll('[role="radio"]')].filter(
      (radio) => !radio.disabled
    );
    if (!radios.length) return;
    event.preventDefault();
    const current = Math.max(0, radios.indexOf(document.activeElement));
    let next = current;
    if (event.key === "Home") next = 0;
    else if (event.key === "End") next = radios.length - 1;
    else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      next = (current - 1 + radios.length) % radios.length;
    } else {
      next = (current + 1) % radios.length;
    }
    radios[next].click();
    radios[next].focus();
  });
});

renderWords();
renderPreview();
show("load");
