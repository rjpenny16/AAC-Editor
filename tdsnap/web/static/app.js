/* TD Snap Page Builder frontend. Plain JS, no build step.
   State machine: load → build → result (result keeps the session so more
   pages can be added before downloading). */

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

const state = {
  mode: "live",
  operation: "existing", // "existing" | "new"
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
  const response = await fetch(path, options);
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

function show(step) {
  $("step-load").hidden = step !== "load";
  $("step-build").hidden = step !== "build";
  $("step-result").hidden = step !== "result";
  const active = $(`step-${step}`);
  if (active && typeof active.scrollIntoView === "function") {
    active.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  if (step === "result") {
    const heading = active && active.querySelector("h2");
    if (heading) {
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
    }
  }
}

function setBusy(button, busy) {
  button.classList.toggle("loading", busy);
  button.disabled = busy;
}

/* ---------- step 1: connect to live TD Snap ---------- */

$("live-connect-btn").addEventListener("click", async () => {
  const button = $("live-connect-btn");
  const status = $("live-status");
  status.classList.remove("error");
  status.textContent = "Checking TD Snap...";
  setBusy(button, true);
  try {
    const data = await api("/api/tdsnap/status");
    if (!data.available) throw new Error("Direct editing is available on Windows only.");
    if (!data.running) throw new Error(data.error || "Open TD Snap, then try again.");
    if (!data.unlocked) throw new Error("Unlock Windows, then try again.");

    state.mode = "live";
    state.grid = data.grid;
    state.currentPage = data.page;
    const detected = Array.isArray(data.pages) && data.pages.length
      ? data.pages
      : [data.page, "Topics Menu Page"];
    state.pages = [...new Set(detected.filter(Boolean))].map((title) => ({
      id: title,
      title,
    }));
    state.words = [];
    state.parentId = data.page;
    state.parentFree = 1;
    state.parentTouched = false;
    state.recommendedParent = data.page;
    state.edits = 0;

    $("file-badge").textContent = "Live TD Snap";
    $("file-badge").hidden = false;
    $("build-sub").textContent =
      `Connected to “${data.page}” · ${data.grid.cols}×${data.grid.rows} grid · ` +
      `${state.pages.length} possible locations detected`;
    $("build-btn-label").textContent = "Update TD Snap";
    status.textContent = "";
    renderParents("");
    setOperation("existing");
    await loadTargetLayout(data.page);
    show("build");
    $("word-input").focus();
    checkAi();
  } catch (error) {
    status.classList.add("error");
    status.textContent = error.message;
  } finally {
    setBusy(button, false);
  }
});

async function loadTargetLayout(pageName) {
  if (state.operation !== "existing" || !pageName) return;
  clearBuildError();
  state.targetLoading = true;
  state.parentFree = null;
  parentSelect.disabled = true;
  $("parent-capacity").textContent = "Loading the existing layout…";
  try {
    const data = await api(`/api/tdsnap/page-layout?page=${encodeURIComponent(pageName)}`);
    state.grid = data.grid;
    state.existingButtons = data.buttons || [];
    state.layoutFingerprint = data.fingerprint;
    state.parentFree = data.free_slots.length;
    const occupied = new Set(state.existingButtons.map((button) => button.slot));
    state.words.forEach((item) => {
      if (occupied.has(item.slot)) item.slot = firstAvailableSlot();
    });
    $("parent-capacity").classList.remove("error");
    $("parent-capacity").textContent =
      `${data.free_slots.length} empty cell${data.free_slots.length === 1 ? "" : "s"} on “${data.page}”.`;
    renderWords();
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
  }
}

function setOperation(operation) {
  state.operation = operation;
  const existing = operation === "existing";
  $("operation-existing").classList.toggle("selected", existing);
  $("operation-existing").setAttribute("aria-checked", existing);
  $("operation-new").classList.toggle("selected", !existing);
  $("operation-new").setAttribute("aria-checked", !existing);
  $("operation-existing").tabIndex = existing ? 0 : -1;
  $("operation-new").tabIndex = existing ? -1 : 0;
  $("title-field").hidden = existing;
  $("placement-advice").hidden = existing;
  $("target-label").textContent = existing
    ? "Which existing page should receive the buttons?"
    : "Where should the new folder button go?";
  $("operation-hint").textContent = existing
    ? "Choose the category first, then add words without creating another folder."
    : "Create a separate vocabulary page and link it from an existing page.";
  $("preview-hint").textContent = existing
    ? "Existing buttons are locked. Drag new buttons to exact empty cells, or focus one and use the arrow keys."
    : "Drag buttons to the exact cells you want, or focus one and use the arrow keys.";
  $("build-btn-label").textContent = "Update TD Snap";
  state.existingButtons = existing ? state.existingButtons : [];
  state.layoutFingerprint = existing ? state.layoutFingerprint : null;
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
  $("title-input").focus();
});

/* ---------- step 2: page style + function palette ---------- */

function setPageStyle(style) {
  state.pageStyle = style;
  state.autoTopicRows = style === "topic";
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
}

$("style-words").addEventListener("click", () => setPageStyle("words"));
$("style-topic").addEventListener("click", () => setPageStyle("topic"));
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
  if (value.trim()) addWords(value);
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
wordInput.addEventListener("paste", (event) => {
  const text = (event.clipboardData || window.clipboardData).getData("text");
  if (text && text.includes(",")) {
    event.preventDefault();
    addWords(text);
  }
});

function firstAvailableSlot() {
  const used = new Set(state.words.map((item) => item.slot));
  state.existingButtons.forEach((button) => used.add(button.slot));
  const capacity = state.grid.cols * state.grid.rows;
  for (let slot = 0; slot < capacity; slot += 1) {
    if (!used.has(slot)) return slot;
  }
  return capacity - 1;
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
  state.words.forEach((item, index) => {
    if (!Number.isInteger(item.slot)) item.slot = index;
    item.fn = functionForSlot(item.slot);
  });
  renderWords();
}

function addWords(raw) {
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
        const slot = firstAvailableSlot();
        const fn = state.pageStyle === "topic" && state.autoTopicRows
          ? functionForSlot(slot)
          : state.activeFn;
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
    chipbox.insertBefore(chip, wordInput);
  });

  const capacity = state.grid.cols * state.grid.rows - state.existingButtons.length;
  const meter = $("capacity");
  meter.textContent = `${state.words.length} of ${capacity} cells`;
  meter.classList.toggle("full", state.words.length >= capacity);
  wordInput.disabled = state.words.length >= capacity;
  wordInput.placeholder = state.words.length
    ? ""
    : state.pageStyle === "topic"
      ? "Type a phrase, press Enter — click it after to set color or spoken text"
      : "Type a word, press Enter — or paste a comma-separated list";
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
  const topics = state.pages.find((page) => page.title === "Topics Menu Page");
  return (topics || state.pages.find((page) => page.id === state.currentPage) || state.pages[0]).id;
}

function updatePlacementRecommendation() {
  const recommendation = recommendParent($("title-input").value);
  state.recommendedParent = recommendation;
  const title = titleOf(recommendation);
  const hasName = Boolean($("title-input").value.trim());
  $("placement-title").textContent = hasName ? `Suggested location: ${title}` : "AAC-friendly placement";
  $("placement-copy").textContent = hasName
    ? `This is the closest existing category the app can detect. Keeping related fringe vocabulary together makes it easier to find without moving established words.`
    : "Name the page above and the app will suggest an existing location, keeping related vocabulary together.";
  if (!state.parentTouched && recommendation) {
    state.parentId = recommendation;
    renderParents(parentFilter.value);
    $("parent-capacity").textContent =
      `The link will use the first free cell on “${title}”.`;
  }
  $("use-placement").hidden = !hasName || state.parentId === recommendation;
}

$("title-input").addEventListener("input", updatePlacementRecommendation);
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
  state.pages
    .filter((page) => !query || page.title.toLowerCase().includes(query))
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
  } else if (query && parentSelect.options.length === 1 &&
             parentSelect.options[0].value !== String(state.parentId)) {
    // Filter narrowed to a single page: select it without an extra click.
    parentSelect.options[0].selected = true;
    parentSelect.dispatchEvent(new Event("change"));
  }
}

/* ---------- step 2: preview ---------- */

function renderPreview() {
  const preview = $("preview");
  preview.style.setProperty("--cols", state.grid.cols);
  preview.innerHTML = "";
  if (!state.words.length && !state.existingButtons.length) {
    const note = document.createElement("div");
    note.className = "cell empty-note";
    note.textContent = "Your words appear here, laid out exactly as TD Snap will show them.";
    preview.append(note);
    return;
  }
  const total = state.grid.cols * state.grid.rows;
  for (let slot = 0; slot < total; slot += 1) {
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
      cell.textContent = existing.label || "Existing button";
      cell.title = "Existing TD Snap button — position preserved";
      cell.setAttribute("aria-label", `${existing.label || "Existing button"}, existing and locked`);
    }
    const index = state.words.findIndex((item) => item.slot === slot);
    if (index >= 0) {
      const item = state.words[index];
      cell.classList.add("used");
      cell.textContent = item.label;
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
  renderWords();
}

/* ---------- step 2: AI engines ---------- */

let aiReady = false;

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

$("ai-host").addEventListener("change", checkAi);
$("ai-check-btn").addEventListener("click", async () => {
  $("ai-engine-state").textContent = "Checking the Ollama connection…";
  await checkAi();
});
$("ai-model").addEventListener("input", () => {
  $("ai-model").dataset.userEdited = "1";
});

$("ai-download-btn").addEventListener("click", async () => {
  const status = $("ai-download-status");
  status.classList.remove("error");
  try {
    await api("/api/ai/download", { method: "POST" });
    trackDownload();
  } catch (error) {
    status.classList.add("error");
    status.textContent = error.message;
  }
});

let downloadTimer = null;

function trackDownload() {
  if (downloadTimer) return; // a poll is already running
  const button = $("ai-download-btn");
  const bar = $("ai-progress");
  const fill = $("ai-progress-fill");
  const status = $("ai-download-status");
  setBusy(button, true);
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
        status.textContent = "Done — suggestions are ready.";
        checkAi();
      } else if (dl.status === "error") {
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
  const category = $("title-input").value.trim();
  status.classList.remove("error");
  if (!category) {
    status.classList.add("error");
    status.textContent = "Give the page a title first — it's used as the category.";
    return;
  }
  const topic = state.pageStyle === "topic";
  const what = topic
    ? state.activeFn
      ? `${FUNCTIONS[state.activeFn].name.toLowerCase()} phrases`
      : "phrases"
    : "words";
  setBusy(button, true);
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
      }),
    });
    // Phrases arrive comma-prone; add them one by one instead of splitting.
    const capacity = state.grid.cols * state.grid.rows - state.existingButtons.length;
    let added = 0;
    data.words.forEach((text) => {
      const label = text.trim();
      const exists = state.words.some((item) => item.label === label);
      if (label && !exists && state.words.length < capacity) {
        const slot = firstAvailableSlot();
        const fn = topic && state.autoTopicRows ? functionForSlot(slot) : state.activeFn;
        state.words.push({ label, message: null, fn, slot, symbol: true });
        added += 1;
      }
    });
    renderWords();
    status.textContent = `Added ${added} suggestions — remove any you don't want.`;
  } catch (error) {
    status.classList.add("error");
    status.textContent = error.message;
  } finally {
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
buildForm.addEventListener("input", clearBuildError);
buildForm.addEventListener("change", clearBuildError);

buildForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearBuildError();

  takeWordInput();

  const title = $("title-input").value.trim();
  const failures = [];
  if (state.operation === "new" && !title) failures.push("Give the new page a title.");
  if (!state.words.length) failures.push("Add at least one word.");
  if (state.parentId == null) failures.push("Choose a target page.");
  if (state.operation === "existing" && state.targetLoading) {
    failures.push("Wait for the selected page layout to finish loading.");
  }
  if (state.operation === "existing" && !state.layoutFingerprint) {
    failures.push("Reload the selected page layout before editing.");
  }
  if (state.operation === "new" && state.parentFree === 0) {
    failures.push("The selected page is full; pick one with a free cell.");
  }
  if (failures.length) {
    showBuildError("Almost there:", failures);
    return;
  }

  const button = $("build-btn");
  setBusy(button, true);
  try {
    const path = state.operation === "existing" ? "/api/tdsnap/edit-plan" : "/api/tdsnap/page";
    const payload = {
      operation: state.operation === "existing" ? "add_to_existing_page" : "create_page",
      title,
      items: state.words.map((item) => ({
        label: item.label,
        message: item.message,
        border_color: item.fn ? FUNCTIONS[item.fn].color : null,
        slot: item.slot,
        symbol: item.symbol !== false,
      })),
      parent: titleOf(state.parentId),
      page: titleOf(state.parentId),
      fingerprint: state.layoutFingerprint,
    };
    const data = await api(path, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-TDSnap-Editor": "1",
      },
      body: JSON.stringify(payload),
    });
    state.edits = data.edits || state.edits + 1;
    renderResult(state.operation === "existing" ? titleOf(state.parentId) : title, data);
    show("result");
  } catch (error) {
    showBuildError(error.message, error.problems || []);
  } finally {
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
  sqlite_integrity: "Database integrity and foreign keys",
  linkage_chains: "Every button, layout, link and sync record is complete",
  roundtrip_diff: "Everything else in your page set is untouched, byte for byte",
  td_snap_edit: "TD Snap saved the page in the open page set",
  navigation: "The chosen folder button opens the new page",
  target_page: "The requested existing page was edited",
  content: "Every requested speaking button is present",
  positions: "Every new button is in its reviewed empty cell",
  symbols: "Matching symbols were added to the buttons",
  topic_format: "Topic-page row colors were applied in TD Snap",
};

const CHECK_SVG =
  '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
  'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<path d="M20 6 9 17l-5-5"/></svg>';

function renderResult(title, data) {
  $("result-heading").childNodes[0].textContent = "TD Snap updated ";
  $("edit-count").textContent =
    state.edits > 1 ? `· ${state.edits} edits this session` : "";
  $("another-btn").textContent = state.operation === "existing"
    ? "Add more buttons"
    : "Create another page";
  $("result-sub").textContent = state.operation === "existing"
    ? `${data.buttons} speaking button${data.buttons === 1 ? " was" : "s were"} added to “${title}” without moving its existing vocabulary.`
    : `“${title}” has ${data.buttons} speaking button${data.buttons === 1 ? "" : "s"}, and “${titleOf(state.parentId)}” now links to it.`;

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

$("another-btn").addEventListener("click", async () => {
  const previousParent = state.parentId;
  state.words = [];
  state.parentId = previousParent || state.currentPage;
  state.parentFree = 1;
  state.parentTouched = state.operation === "existing";
  state.existingButtons = [];
  state.layoutFingerprint = null;
  $("title-input").value = "";
  $("parent-capacity").textContent =
    `The link will use the first free cell on “${titleOf(state.parentId)}”.`;
  $("chip-note").textContent = "";
  parentFilter.value = "";
  renderParents("");
  renderWords();
  if (state.operation === "new") updatePlacementRecommendation();
  $("build-error").hidden = true;
  $("result-warnings").hidden = true;
  show("build");
  if (state.operation === "existing") {
    try {
      await loadTargetLayout(titleOf(state.parentId));
      $("word-input").focus();
    } catch (error) {
      showBuildError("Couldn’t refresh the selected TD Snap page.", [error.message]);
    }
  } else {
    $("title-input").focus();
  }
});

$("reset-btn").addEventListener("click", () => {
  state.mode = "live";
  state.words = [];
  state.parentId = null;
  state.parentFree = null;
  $("file-badge").hidden = true;
  $("title-input").value = "";
  $("live-status").textContent = "";
  $("parent-capacity").textContent = "";
  $("chip-note").textContent = "";
  $("build-error").hidden = true;
  renderWords();
  show("load");
});

/* ---------- quit (browser mode) ---------- */

$("quit-btn").addEventListener("click", async () => {
  if (!window.confirm("Quit TD Snap Page Builder?")) return;
  try {
    await api("/api/quit", { method: "POST" });
  } catch {
    /* the server may stop before the response arrives */
  }
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
