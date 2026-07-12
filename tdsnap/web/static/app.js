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
  mode: "file", // "file" | "live"
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
  native: false, // running inside the app's own window (pywebview)?
  apiToken: "",
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
}

function setBusy(button, busy) {
  button.classList.toggle("loading", busy);
  button.disabled = busy;
}

/* ---------- step 1: load ---------- */

const dropzone = $("dropzone");
const fileInput = $("file-input");

function browse() {
  // In the native window, use the OS open dialog on the file in place;
  // in a browser there's no path access, so fall back to the upload flow.
  if (state.native && window.pywebview) openNative();
  else fileInput.click();
}

dropzone.addEventListener("click", browse);
dropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    browse();
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

function applyLoadedPageset(data) {
  state.mode = "file";
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
  $("build-btn-label").textContent = "Add page to working copy";
  $("build-sub").textContent =
    `${data.filename} · schema ${data.schema_version || "?"} · ` +
    `${data.grid.cols}×${data.grid.rows} grid · ${data.pages.length} pages`;
  $("upload-status").textContent = "";
  $("parent-capacity").textContent = "";
  parentFilter.value = "";
  renderParents("");
  renderWords();
  show("build");
  $("title-input").focus();
  checkAi();
}

async function uploadFile(file) {
  const status = $("upload-status");
  status.classList.remove("error");
  status.textContent = `Checking “${file.name}”…`;
  dropzone.classList.add("busy");
  try {
    const form = new FormData();
    form.append("file", file, file.name);
    const data = await api("/api/pageset", { method: "POST", body: form });
    applyLoadedPageset(data);
  } catch (error) {
    status.classList.add("error");
    status.textContent = error.message;
  } finally {
    dropzone.classList.remove("busy");
    fileInput.value = "";
  }
}

async function openNative() {
  const status = $("upload-status");
  status.classList.remove("error");
  dropzone.classList.add("busy");
  try {
    const data = await window.pywebview.api.open_pageset();
    if (data.cancelled) return;
    if (!data.ok) throw new Error(data.error || "Could not open the file.");
    applyLoadedPageset(data);
  } catch (error) {
    status.classList.add("error");
    status.textContent = error.message;
  } finally {
    dropzone.classList.remove("busy");
  }
}

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
    state.sessionId = null;
    state.filename = "Open TD Snap";
    state.grid = data.grid;
    state.pages = [{ id: 0, title: "Topics Menu Page" }];
    state.words = [];
    state.parentId = 0;
    state.parentFree = 1;
    state.edits = 0;

    $("file-badge").textContent = "Live TD Snap";
    $("file-badge").hidden = false;
    $("build-sub").textContent =
      `Editing the open TD Snap page set directly - ${data.grid.cols}x${data.grid.rows} grid`;
    $("build-btn-label").textContent = "Add directly to TD Snap";
    status.textContent = "";
    renderParents("");
    $("parent-capacity").textContent =
      "The agent will find the next free cell on the Topics Menu Page.";
    renderWords();
    show("build");
    $("title-input").focus();
    checkAi();
  } catch (error) {
    status.classList.add("error");
    status.textContent = error.message;
  } finally {
    setBusy(button, false);
  }
});

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

function addWords(raw) {
  const capacity = state.grid.cols * state.grid.rows;
  let duplicates = 0;
  let overflow = 0;
  raw
    .split(",")
    .map((word) => word.trim())
    .filter(Boolean)
    .forEach((word) => {
      if (state.words.some((item) => item.label === word)) {
        duplicates += 1;
      } else if (state.words.length >= capacity) {
        overflow += 1;
      } else {
        state.words.push({ label: word, message: null, fn: state.activeFn });
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
  if (state.mode === "live") {
    state.parentFree = 1;
    $("parent-capacity").textContent =
      "The agent will find the next free cell on the Topics Menu Page.";
    return;
  }
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
        ? "Ollama is running but has no models installed."
        : "";
      if (local.download.status === "downloading") trackDownload();
    } else {
      aiReady = false;
      card.hidden = true;
      label.textContent = data.ollama.reachable
        ? "Ollama is running but has no models — try: ollama pull llama3.2"
        : "This install has no built-in AI engine — start Ollama to enable suggestions.";
    }
    $("ai-go").disabled = !aiReady;
  } catch {
    label.textContent = "";
  }
}

$("ai-host").addEventListener("change", checkAi);
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

  takeWordInput();

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
    const path = state.mode === "live"
      ? "/api/tdsnap/page"
      : `/api/pageset/${state.sessionId}/page`;
    const payload = {
      title,
      items: state.words.map((item) => ({
        label: item.label,
        message: item.message,
        border_color: item.fn ? FUNCTIONS[item.fn].color : null,
      })),
    };
    if (state.mode === "live") payload.parent = titleOf(state.parentId);
    else payload.parent_page_id = state.parentId;
    const data = await api(path, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(state.mode === "live" ? { "X-TDSnap-Editor": "1" } : {}),
      },
      body: JSON.stringify(payload),
    });
    state.edits = data.edits || state.edits + 1;
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
  td_snap_edit: "TD Snap saved the page in the open page set",
  navigation: "The Topics button opens the new page",
  content: "Every requested speaking button is present",
};

const CHECK_SVG =
  '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
  'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<path d="M20 6 9 17l-5-5"/></svg>';

function renderResult(title, data) {
  $("result-heading").childNodes[0].textContent =
    state.mode === "live" ? "TD Snap updated " : "Page added ";
  $("edit-count").textContent =
    state.edits > 1 ? `· ${state.edits} pages added this session` : "";
  $("result-sub").textContent =
    `“${title}” has ${data.buttons} speaking button${data.buttons === 1 ? "" : "s"}, ` +
    `and “${titleOf(state.parentId)}” now links to it.`;

  if (data.warnings && data.warnings.length) {
    $("result-sub").textContent += ` ${data.warnings.join(" ")}`;
  }

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

  // Live mode edited TD Snap in place — nothing to save. In the native
  // window, the OS save dialog replaces the browser download flow.
  $("download-btn").hidden = state.mode === "live" || state.native;
  $("save-btn").hidden = state.mode === "live" || !state.native;
  $("save-status").textContent = "";
  $("live-result-note").hidden = state.mode !== "live";
  $("file-result-safety").hidden = state.mode === "live";
  if (state.mode === "file") {
    $("download-btn").href = `/api/pageset/${state.sessionId}/download`;
  }
}

$("save-btn").addEventListener("click", async () => {
  // Native window: OS save dialog, written straight to disk — no Downloads
  // folder detour.
  const button = $("save-btn");
  const status = $("save-status");
  status.classList.remove("error");
  setBusy(button, true);
  try {
    const data = await window.pywebview.api.save_pageset(state.sessionId);
    if (data.cancelled) return;
    if (!data.ok) throw new Error(data.error || "Could not save the file.");
    status.textContent = `Saved to ${data.path}`;
  } catch (error) {
    status.classList.add("error");
    status.textContent = error.message;
  } finally {
    setBusy(button, false);
  }
});

$("another-btn").addEventListener("click", async () => {
  // Refresh the page list so the just-added page can be a parent too.
  if (state.mode === "file") {
    try {
      const data = await api(`/api/pageset/${state.sessionId}/pages`);
      state.pages = data.pages;
    } catch {
      /* keep the stale list; building will still validate server-side */
    }
  }
  state.words = [];
  state.parentId = state.mode === "live" ? 0 : null;
  state.parentFree = state.mode === "live" ? 1 : null;
  $("title-input").value = "";
  $("parent-capacity").textContent = state.mode === "live"
    ? "The agent will find the next free cell on the Topics Menu Page."
    : "";
  $("chip-note").textContent = "";
  parentFilter.value = "";
  renderParents("");
  renderWords();
  $("build-error").hidden = true;
  show("build");
  $("title-input").focus();
});

$("reset-btn").addEventListener("click", () => {
  state.mode = "file";
  state.sessionId = null;
  state.words = [];
  state.parentId = null;
  state.parentFree = null;
  $("file-badge").hidden = true;
  $("title-input").value = "";
  $("upload-status").textContent = "";
  $("parent-capacity").textContent = "";
  $("chip-note").textContent = "";
  $("build-error").hidden = true;
  renderWords();
  show("load");
});

/* ---------- quit (browser mode) ---------- */

$("quit-btn").addEventListener("click", async () => {
  const opened = state.sessionId !== null;
  const warning = opened
    ? "Quit TD Snap Page Builder? Anything you haven't downloaded will be discarded."
    : "Quit TD Snap Page Builder?";
  if (!window.confirm(warning)) return;
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

renderWords();
renderPreview();
