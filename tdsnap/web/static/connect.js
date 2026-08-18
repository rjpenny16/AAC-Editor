/* Step 1: choosing an AAC app and connecting to it.
 *
 * Three providers with different capabilities — TD Snap live, Grid 3 live, and
 * an exported file — behind one connect button. Also owns the live monitor
 * that follows whatever page the user navigates to in TD Snap.
 */

import { state } from "./state.js";
import { $, setBusy, setActivity, setPreviewBusy } from "./dom.js";
import { api } from "./api.js";
import { firstAvailableSlot, renderWords } from "./chips.js";
import { emptyEdits, reconcile } from "./edits.js";
import { parentFilter, parentSelect, renderParents } from "./parents.js";
import { savePreference } from "./settings.js";
import { clearBuildError, setOperation, setPageStyle, show, showBuildError } from "./wizard.js";

/* Owned here because connect.js is the only writer, and a module-level `let`
   cannot be reassigned across an ES module boundary. */
let liveMonitor = null;
let liveSyncing = false;

/* Stop following the page open in TD Snap (used when a session is torn down). */
function stopLiveMonitor() {
  clearInterval(liveMonitor);
  liveMonitor = null;
}

/* ---------- step 1: choose and connect to an AAC app ---------- */

function setProviderState(provider, label, stateName = "") {
  $(`provider-${provider}-state`).textContent = label;
  $(`provider-${provider}`).dataset.state = stateName;
}

function clearConnectionError() {
  $("connection-error").hidden = true;
}

function showConnectionError(product, message = "") {
  const box = $("connection-error");
  if (product === "TD Snap") {
    box.querySelector("strong").textContent =
      "AAC Editor couldn’t reach TD Snap. Nothing was changed.";
  } else {
    box.querySelector("strong").textContent = `AAC Editor couldn’t reach ${product}. Nothing was changed.`;
  }
  $("live-status").textContent = message;
  box.hidden = false;
  box.focus({ preventScroll: true });
}

function selectProvider(provider) {
  if (state.connected || !["tdsnap", "grid3", "file"].includes(provider)) return;
  state.provider = provider;
  document.body.dataset.provider = provider;
  ["tdsnap", "grid3", "file"].forEach((name) => {
    const selected = name === provider;
    $(`provider-${name}`).classList.toggle("selected", selected);
    $(`provider-${name}`).setAttribute("aria-checked", String(selected));
    $(`provider-${name}`).tabIndex = selected ? 0 : -1;
  });
  const grid3 = provider === "grid3";
  const file = provider === "file";
  clearConnectionError();
  document.querySelectorAll("[data-tdsnap-only]").forEach((element) => {
    element.hidden = grid3;
  });
  document.querySelectorAll("[data-live-tdsnap-only]").forEach((element) => {
    element.hidden = grid3 || file;
  });
  $("layout-options-btn").hidden = grid3;
  $("connect-task-title").textContent = file
    ? "Open a TD Snap exported file"
    : grid3 ? "Use the grid open in Grid 3" : "Use the page open in TD Snap";
  $("connect-task-copy").textContent = file
    ? "Choose an .sps or .spb export. Your original file stays unchanged."
    : grid3
      ? "Open the grid you want in Grid 3. Do not enter Edit Mode."
      : "Open the page you want to change and keep Windows unlocked.";
  $("live-connect-btn").querySelector(".btn-label").textContent = file
    ? "Choose exported page set"
    : grid3
      ? (state.elevated ? "Connect to Grid 3" : "Enable Grid 3 editing")
      : "Use the page open in TD Snap";
  $("connection-help").innerHTML = file
    ? "<li>Export the page set from TD Snap as an .sps or .spb file.</li>" +
      "<li>Choose that exported file here and add the new page.</li>" +
      "<li>Save the edited copy, then import it into TD Snap after reviewing it.</li>"
    : grid3
      ? "<li>Open Grid 3 and the existing grid you want to change.</li>" +
        "<li>Save or discard any unfinished Grid 3 edits.</li>" +
        "<li>Return here and connect. Windows may request administrator approval.</li>"
      : "<li>Open TD Snap and choose the person and page set you want to edit.</li>" +
        "<li>Open the page you want to change.</li>" +
        "<li>Return here and select <strong>Use the page open in TD Snap</strong>.</li>";
  $("connection-help-note").textContent = file
    ? "The editor works on a temporary copy and never overwrites your export."
    : "Direct editing follows the page open in the selected AAC app.";
  $("live-status").textContent = "";
}

function selectProviderAndRemember(provider) {
  selectProvider(provider);
  void savePreference("provider", provider);
}
$("provider-tdsnap").addEventListener("click", () => selectProviderAndRemember("tdsnap"));
$("provider-grid3").addEventListener("click", () => selectProviderAndRemember("grid3"));
$("provider-file").addEventListener("click", () => selectProviderAndRemember("file"));
$("connection-retry").addEventListener("click", () => $("live-connect-btn").click());
$("connection-help-btn").addEventListener("click", () => {
  const details = $("connection-help-details");
  details.open = true;
  details.querySelector("summary").focus();
});

function rememberDetectedPages(data) {
  const detected = Array.isArray(data.pages) && data.pages.length
    ? data.pages
    : [data.page];
  state.pages = [...new Set(detected.filter(Boolean))].map((title) => ({
    id: title,
    title,
  }));
}

async function refreshDetectedPages() {
  if (state.mode === "file") {
    const data = await api(`/api/pageset/${encodeURIComponent(state.sessionId)}/pages`);
    state.pages = (data.pages || []).map((page) => ({
      id: String(page.id),
      title: page.title,
    }));
    renderParents(parentFilter.value);
    return data;
  }
  const data = await api("/api/tdsnap/status");
  rememberDetectedPages(data);
  renderParents(parentFilter.value);
  return data;
}

async function useFileSession(data) {
  if (!data || data.ok === false) throw new Error(data?.error || "The page set could not be opened.");
  if (data.cancelled) return false;
  if (!data.session_id || !Array.isArray(data.pages) || !data.pages.length) {
    throw new Error("The page set does not contain any editable pages.");
  }
  clearInterval(liveMonitor);
  state.mode = "file";
  state.provider = "file";
  state.connected = true;
  state.sessionId = data.session_id;
  state.filename = data.filename || "page-set.sps";
  state.grid = data.grid || state.grid;
  state.pages = data.pages.map((page) => ({ id: String(page.id), title: page.title }));
  state.currentPage = state.pages[0].id;
  state.parentId = state.currentPage;
  state.parentFree = null;
  state.parentTouched = false;
  state.words = [];
  state.existingButtons = [];
  state.pageEdits = emptyEdits();
  state.canEditExisting = false;
  state.availableSlots = null;
  state.layoutFingerprint = null;
  state.edits = 0;
  state.pendingEdit = null;
  state.placementAdjusted = false;
  $("title-input").value = "";
  setPageStyle("words");
  // Exported files can now add to a page that already exists, so they open on
  // the same first question the live providers ask instead of assuming a new
  // page is wanted. Adding to a familiar page is the shorter path, so it leads.
  setOperation("existing");
  renderParents("");
  $("file-badge").textContent = `${state.filename} · Change file`;
  $("file-badge").setAttribute("aria-label", `Change exported file (currently ${state.filename})`);
  $("file-badge").hidden = false;
  $("build-sub").textContent =
    `${state.filename} · ${state.grid.cols}×${state.grid.rows} grid · ${state.pages.length} pages`;
  $("preview-live-text").textContent = `Exported copy · ${state.filename}`;
  $("live-result-note").textContent =
    "Save the edited copy, review it, then import it into TD Snap.";
  setProviderState("file", "Ready", "ready");
  show("operation");
  return true;
}

async function uploadPageset(file) {
  const form = new FormData();
  form.append("file", file);
  return api("/api/pageset", { method: "POST", body: form }, 0);
}

$("file-input").addEventListener("change", async () => {
  const input = $("file-input");
  const file = input.files?.[0];
  if (!file) return;
  const button = $("live-connect-btn");
  clearConnectionError();
  setBusy(button, true, "Opening…");
  setActivity("Opening a temporary copy of the exported page set…");
  try {
    await useFileSession(await uploadPageset(file));
  } catch (error) {
    showConnectionError("the exported file", error.message);
  } finally {
    input.value = "";
    setActivity();
    setBusy(button, false);
  }
});

$("live-connect-btn").addEventListener("click", async () => {
  const button = $("live-connect-btn");
  const status = $("live-status");
  if (state.connected) {
    show("items");
    return;
  }
  clearConnectionError();
  status.classList.remove("error");
  const product = state.provider === "grid3"
    ? "Grid 3" : state.provider === "file" ? "the exported file" : "TD Snap";
  status.textContent = "";
  setActivity(`Checking for ${product}…`);
  setBusy(button, true, "Connecting…");
  try {
    if (state.provider === "file") {
      if (state.native && window.pywebview?.api?.open_pageset) {
        await useFileSession(await window.pywebview.api.open_pageset());
      } else {
        $("file-input").click();
      }
      return;
    }
    if (state.provider === "grid3") {
      const data = await api("/api/grid3/status");
      if (!data.available) throw new Error("Grid 3 editing is available on Windows only.");
      if (!data.installed) {
        setProviderState("grid3", "Not installed", "not-installed");
        throw new Error("Grid 3 was not found in its standard installation folder.");
      }
      if (data.needs_elevation) {
        setProviderState("grid3", "Administrator approval required", "elevation");
        if (!state.native || !window.pywebview?.api?.restart_elevated_for_grid3) {
          throw new Error("Open the AAC Editor desktop app to enable Grid 3 editing.");
        }
        status.textContent = "Windows will ask for administrator approval. AAC Editor will reopen here.";
        const restarted = await window.pywebview.api.restart_elevated_for_grid3();
        if (!restarted || restarted.ok === false) {
          throw new Error(restarted?.error || "Administrator restart was cancelled.");
        }
        return;
      }
      if (!data.running) {
        setProviderState("grid3", "Not running", "not-running");
        throw new Error(data.error || "Open Grid 3 to the grid you want to edit.");
      }
      if (data.dirty) throw new Error("Save or discard the unfinished change in Grid 3 first.");
      if (!data.unlocked) throw new Error("Unlock Windows, then try again.");
      state.mode = "live";
      state.operation = "existing";
      state.grid = data.grid;
      state.currentPage = data.page;
      state.pages = [{ id: data.page, title: data.page }];
      state.words = [];
      state.parentId = data.page;
      state.parentTouched = false;
      state.edits = 0;
      state.pendingEdit = null;
      state.placementAdjusted = false;
      setPageStyle("words");
      $("build-sub").textContent =
        `Connected to “${data.page}” in ${data.grid_set} · ` +
        `${data.grid.cols}×${data.grid.rows} grid`;
      $("preview-live-text").textContent = `Grid 3 · ${data.page}`;
      $("preview-hint").textContent =
        "New buttons use the size, color, and style of each empty Grid 3 space.";
      $("live-result-note").textContent = "Your Grid 3 grid was saved.";
      setActivity("Reading the current Grid 3 grid…");
      await loadTargetLayout(data.page);
      setActivity("Checking Grid 3 Edit Mode compatibility…");
      await api("/api/grid3/probe", {
        method: "POST",
        headers: { "X-AAC-Editor": "grid3" },
      });
      state.connected = true;
      $("file-badge").textContent = "Grid 3 · Change app";
      $("file-badge").setAttribute("aria-label", "Change app (currently Grid 3)");
      $("file-badge").hidden = false;
      setProviderState("grid3", "Ready", "ready");
      status.textContent = data.compatibility_warning || "";
      show("items");
      return;
    }
    let data = await api("/api/tdsnap/status");
    if (!data.available) throw new Error("Direct editing is available on Windows only.");
    if (!data.running) {
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
    state.grid = data.grid;
    state.currentPage = data.page;
    rememberDetectedPages(data);
    state.words = [];
    state.parentId = data.page || state.pages[0]?.id || null;
    state.parentFree = 1;
    state.parentTouched = false;
    state.recommendedParent = data.page;
    state.edits = 0;
    state.pendingEdit = null;
    state.placementAdjusted = false;

    $("file-badge").textContent = "TD Snap · Change app";
    $("file-badge").setAttribute("aria-label", "Change app (currently TD Snap)");
    $("build-sub").textContent =
      `Connected to “${data.page}” · ${data.grid.cols}×${data.grid.rows} grid · ` +
      `${state.pages.length} pages in this page set`;
    $("preview-live-text").textContent = `Live · ${data.page}`;
    $("build-btn-label").textContent = "Review changes";
    status.textContent = "";
    button.querySelector(".btn-label").dataset.idleLabel = "Continue";
    renderParents("");
    setOperation("existing");
    if (data.page) {
      setActivity("Reading the page open in TD Snap…");
      try {
        await loadTargetLayout(data.page);
      } catch (error) {
        if (error.name === "TimeoutError") throw error;
        state.layoutFingerprint = null;
        showBuildError("Choose a page to continue.", ["AAC Editor couldn’t determine the open page."]);
      }
    }
    state.connected = true;
    $("file-badge").hidden = false;
    setProviderState("tdsnap", "Ready", "ready");
    // The retained edit lives in the server process, so reloading the browser
    // after an edit does not cost the undo. Failing to ask simply means not
    // offering it — never a reason to block a connection that otherwise worked.
    try {
      state.lastEdit = (await api("/api/tdsnap/last-edit")).undo;
    } catch {
      state.lastEdit = null;
    }
    renderWords();
    if (state.layoutFingerprint) show("items");
    else show("destination");
    startLiveMonitor();
  } catch (error) {
    state.connected = false;
    $("file-badge").hidden = true;
    if (state.provider === "grid3") {
      if (!["not-installed", "not-running", "elevation"].includes(
        $("provider-grid3").dataset.state
      )) setProviderState("grid3", "Unsupported grid", "unsupported");
    }
    setActivity();
    setBusy(button, false);
    showConnectionError(product, state.provider === "grid3" ? error.message : "");
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
    const data = await api(state.mode === "file"
      ? `/api/pageset/${encodeURIComponent(state.sessionId)}` +
        `/page/${encodeURIComponent(state.parentId)}/layout`
      : state.provider === "grid3"
        ? "/api/grid3/page-layout"
        : currentOnly
          ? "/api/tdsnap/page-layout"
          : `/api/tdsnap/page-layout?page=${encodeURIComponent(pageName)}`);
    state.grid = data.grid;
    state.existingButtons = data.buttons || [];
    state.availableSlots = data.free_slots || [];
    state.grid3Cells = state.provider === "grid3" ? (data.cells || []) : [];
    state.previewAspect = data.preview_aspect || null;
    state.gridBackground = data.background || null;
    state.layoutFingerprint = data.fingerprint;
    state.parentFree = data.free_slots.length;
    // Changing or removing needs the page set's stored content: without it
    // there is nothing to restore from if the edit fails part-way. A page set
    // AAC Editor cannot fully identify keeps working for adding buttons.
    state.canEditExisting = state.provider === "tdsnap" && state.mode === "live" &&
      state.operation === "existing" && data.content_readable === true;
    // Drop any pending edit whose button moved, was renamed, or stopped being
    // eligible while the live page was being followed.
    state.pageEdits = state.canEditExisting
      ? reconcile(state.pageEdits, state.existingButtons)
      : emptyEdits();
    const occupied = new Set(state.existingButtons.map((button) => button.slot));
    state.words.forEach((item) => {
      if (occupied.has(item.slot) || !state.availableSlots.includes(item.slot)) {
        item.slot = firstAvailableSlot(item.fn);
      }
    });
    $("parent-capacity").classList.remove("error");
    $("parent-capacity").textContent = data.free_slots.length
      ? `${data.free_slots.length} empty space${data.free_slots.length === 1 ? "" : "s"} ` +
        `AAC Editor can update safely on “${data.page}”.`
      : `“${data.page}” is full. Choose another page or remove existing vocabulary in ${state.provider === "grid3" ? "Grid 3" : "TD Snap"}.`;
    if (state.mode === "file") state.currentPage = state.parentId;
    $("current-page-label").textContent = `Adding to ${data.page}`;
    renderWords();
    return data;
  } catch (error) {
    state.existingButtons = [];
    state.availableSlots = null;
    state.grid3Cells = [];
    state.layoutFingerprint = null;
    state.canEditExisting = false;
    state.pageEdits = emptyEdits();
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
  // A hidden tab cannot show the result, and this fires every 750 ms for the
  // whole session — no reason to keep walking TD Snap's accessibility tree
  // while nobody is looking at it.
  if (document.hidden) return;
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

export { loadTargetLayout, refreshDetectedPages, selectProvider, stopLiveMonitor };
