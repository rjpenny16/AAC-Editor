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
  sessionId: null,
  filename: "",
  grid: { cols: 8, rows: 5 },
  pages: [],
  words: [], // [{label, message|null, fn|""}]
  pageStyle: "words", // "words" | "topic"
  activeFn: "",
  parentId: null,
  parentFree: null,
  edits: 0,
};

/* ---------- helpers ---------- */

async function api(path, options) {
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
}

function setBusy(button, busy) {
  button.classList.toggle("loading", busy);
  button.disabled = busy;
}

/* ---------- step 1: load ---------- */

const dropzone = $("dropzone");
const fileInput = $("file-input");

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    fileInput.click();
  }
});
["dragover", "dragenter"].forEach((name) =>
  dropzone.addEventListener(name, (event) => {
    event.preventDefault();
    dropzone.classList.add("dragover");
  })
);
["dragleave", "drop"].forEach((name) =>
  dropzone.addEventListener(name, () => dropzone.classList.remove("dragover"))
);
dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  const file = event.dataTransfer.files && event.dataTransfer.files[0];
  if (file) uploadFile(file);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) uploadFile(fileInput.files[0]);
});

async function uploadFile(file) {
  const status = $("upload-status");
  status.classList.remove("error");
  status.textContent = `Checking “${file.name}”…`;
  dropzone.classList.add("busy");
  try {
    const form = new FormData();
    form.append("file", file, file.name);
    const data = await api("/api/pageset", { method: "POST", body: form });

    state.sessionId = data.session_id;
    state.filename = data.filename;
    state.grid = data.grid;
    state.pages = data.pages;
    state.words = [];
    state.parentId = null;
    state.parentFree = null;
    state.edits = 0;

    $("file-badge").textContent = data.filename;
    $("file-badge").hidden = false;
    $("build-sub").textContent =
      `${data.filename} · schema ${data.schema_version || "?"} · ` +
      `${data.grid.cols}×${data.grid.rows} grid · ${data.pages.length} pages`;
    status.textContent = "";
    renderParents("");
    renderWords();
    show("build");
    $("title-input").focus();
    checkOllama();
  } catch (error) {
    status.classList.add("error");
    status.textContent = error.message;
  } finally {
    dropzone.classList.remove("busy");
    fileInput.value = "";
  }
}

/* ---------- step 2: page style + function palette ---------- */

function setPageStyle(style) {
  state.pageStyle = style;
  $("style-words").classList.toggle("selected", style === "words");
  $("style-words").setAttribute("aria-checked", style === "words");
  $("style-topic").classList.toggle("selected", style === "topic");
  $("style-topic").setAttribute("aria-checked", style === "topic");
  $("fn-palette").hidden = style !== "topic";
  $("style-hint").textContent =
    style === "topic"
      ? "Quick-fire phrases and color-coded buttons for talking about one topic."
      : "Single words — each button speaks its label.";
  $("ai-go").textContent = style === "topic" ? "Suggest phrases" : "Suggest words";
  $("ai-summary-text").textContent =
    style === "topic" ? "Suggest phrases with AI" : "Suggest words with AI";
  if (style !== "topic") setActiveFn("");
}

function setActiveFn(fn) {
  state.activeFn = fn;
  document.querySelectorAll("#fn-palette .fn-pill").forEach((pill) => {
    const selected = pill.dataset.fn === fn;
    pill.classList.toggle("selected", selected);
    pill.setAttribute("aria-checked", selected);
  });
}

$("style-words").addEventListener("click", () => setPageStyle("words"));
$("style-topic").addEventListener("click", () => setPageStyle("topic"));
document.querySelectorAll("#fn-palette .fn-pill").forEach((pill) =>
  pill.addEventListener("click", () => setActiveFn(pill.dataset.fn))
);

/* ---------- step 2: words (chip editor) ---------- */

const chipbox = $("chipbox");
const wordInput = $("word-input");

chipbox.addEventListener("click", (event) => {
  if (event.target === chipbox) wordInput.focus();
});

wordInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === ",") {
    event.preventDefault();
    addWords(wordInput.value);
    wordInput.value = "";
  } else if (event.key === "Backspace" && !wordInput.value && state.words.length) {
    state.words.pop();
    renderWords();
  }
});
wordInput.addEventListener("blur", () => {
  if (wordInput.value.trim()) {
    addWords(wordInput.value);
    wordInput.value = "";
  }
});
wordInput.addEventListener("paste", (event) => {
  const text = (event.clipboardData || window.clipboardData).getData("text");
  if (text && text.includes(",")) {
    event.preventDefault();
    addWords(text);
  }
});

function addWords(raw) {
  const capacity = state.grid.cols * state.grid.rows;
  raw
    .split(",")
    .map((word) => word.trim())
    .filter(Boolean)
    .forEach((word) => {
      const exists = state.words.some((item) => item.label === word);
      if (state.words.length < capacity && !exists) {
        state.words.push({ label: word, message: null, fn: state.activeFn });
      }
    });
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
      renderWords();
    });
    chip.append(body, remove);
    chipbox.insertBefore(chip, wordInput);
  });

  const capacity = state.grid.cols * state.grid.rows;
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
  $("edit-message").value = item.message || "";
  setEditorFn(item.fn || "");
  chipDialog.showModal();
}

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

parentSelect.addEventListener("change", async () => {
  state.parentId = Number(parentSelect.value);
  state.parentFree = null;
  const note = $("parent-capacity");
  note.textContent = "…";
  try {
    const data = await api(
      `/api/pageset/${state.sessionId}/page/${state.parentId}/capacity`
    );
    state.parentFree = data.free_cells;
    const title = titleOf(state.parentId);
    note.textContent =
      data.free_cells > 0
        ? `“${title}” has ${data.free_cells} free cell${data.free_cells === 1 ? "" : "s"}.`
        : `“${title}” is full — the link button won't fit; pick another page.`;
  } catch {
    note.textContent = "";
  }
});

function titleOf(pageId) {
  const page = state.pages.find((p) => p.id === pageId);
  return page ? page.title : `Page ${pageId}`;
}

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
             Number(parentSelect.options[0].value) !== state.parentId) {
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
  if (!state.words.length) {
    const note = document.createElement("div");
    note.className = "cell empty-note";
    note.textContent = "Your words appear here, laid out exactly as TD Snap will show them.";
    preview.append(note);
    return;
  }
  const total = state.grid.cols * state.grid.rows;
  for (let index = 0; index < total; index += 1) {
    const cell = document.createElement("div");
    cell.className = "cell";
    if (index < state.words.length) {
      const item = state.words[index];
      cell.classList.add("used");
      cell.textContent = item.label;
      if (item.fn) {
        cell.classList.add("coded");
        cell.style.setProperty("--fn-color", FUNCTIONS[item.fn].color);
      }
      if (item.message) cell.title = `Speaks: “${item.message}”`;
    }
    preview.append(cell);
  }
}

/* ---------- step 2: Ollama ---------- */

async function checkOllama() {
  const label = $("ollama-state");
  try {
    const data = await api(
      `/api/ollama/status?host=${encodeURIComponent($("ai-host").value)}`
    );
    label.textContent = data.reachable
      ? `Ollama detected (${data.models.length} model${data.models.length === 1 ? "" : "s"}).`
      : "Ollama isn't running right now.";
  } catch {
    label.textContent = "";
  }
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
    const data = await api("/api/ollama/words", {
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
    const capacity = state.grid.cols * state.grid.rows;
    let added = 0;
    data.words.forEach((text) => {
      const label = text.trim();
      const exists = state.words.some((item) => item.label === label);
      if (label && !exists && state.words.length < capacity) {
        state.words.push({ label, message: null, fn: state.activeFn });
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

$("build-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const errorBox = $("build-error");
  errorBox.hidden = true;

  if (wordInput.value.trim()) {
    addWords(wordInput.value);
    wordInput.value = "";
  }

  const title = $("title-input").value.trim();
  const failures = [];
  if (!title) failures.push("Give the new page a title.");
  if (!state.words.length) failures.push("Add at least one word.");
  if (state.parentId == null) failures.push("Pick the page that gets the link button.");
  if (state.parentFree === 0) {
    failures.push("The selected page is full; pick one with a free cell.");
  }
  if (failures.length) {
    showBuildError("Almost there:", failures);
    return;
  }

  const button = $("build-btn");
  setBusy(button, true);
  try {
    const data = await api(`/api/pageset/${state.sessionId}/page`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title,
        items: state.words.map((item) => ({
          label: item.label,
          message: item.message,
          border_color: item.fn ? FUNCTIONS[item.fn].color : null,
        })),
        parent_page_id: state.parentId,
      }),
    });
    state.edits = data.edits;
    renderResult(title, data);
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
};

const CHECK_SVG =
  '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
  'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<path d="M20 6 9 17l-5-5"/></svg>';

function renderResult(title, data) {
  $("edit-count").textContent =
    state.edits > 1 ? `· ${state.edits} pages added this session` : "";
  $("result-sub").textContent =
    `“${title}” has ${data.buttons} speaking button${data.buttons === 1 ? "" : "s"}, ` +
    `and “${titleOf(state.parentId)}” now links to it.`;

  const checks = $("checks");
  checks.innerHTML = "";
  Object.entries(CHECK_LABELS).forEach(([key, label]) => {
    if (!data.checks || data.checks[key] !== "pass") return;
    const item = document.createElement("li");
    const icon = document.createElement("span");
    icon.className = "check-icon";
    icon.innerHTML = CHECK_SVG;
    const text = document.createElement("span");
    text.textContent = label;
    item.append(icon, text);
    checks.append(item);
  });

  $("download-btn").href = `/api/pageset/${state.sessionId}/download`;
}

$("another-btn").addEventListener("click", async () => {
  // Refresh the page list so the just-added page can be a parent too.
  try {
    const data = await api(`/api/pageset/${state.sessionId}/pages`);
    state.pages = data.pages;
  } catch {
    /* keep the stale list; building will still validate server-side */
  }
  state.words = [];
  state.parentId = null;
  state.parentFree = null;
  $("title-input").value = "";
  $("parent-capacity").textContent = "";
  parentFilter.value = "";
  renderParents("");
  renderWords();
  $("build-error").hidden = true;
  show("build");
  $("title-input").focus();
});

$("reset-btn").addEventListener("click", () => {
  state.sessionId = null;
  state.words = [];
  state.parentId = null;
  $("file-badge").hidden = true;
  $("title-input").value = "";
  $("upload-status").textContent = "";
  renderWords();
  show("load");
});

/* ---------- init ---------- */

renderWords();
renderPreview();
