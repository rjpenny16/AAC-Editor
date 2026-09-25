/* Step 1: choosing an AAC app and connecting to it.
 *
 * Three providers with different capabilities — TD Snap live, Grid 3 live, and
 * an exported file — behind one connect button. Also owns the live monitor
 * that follows whatever page the user navigates to in TD Snap.
 */

import { state } from "./state.js";
import { $, setBusy, setActivity, setPreviewBusy } from "./dom.js";
import { api, userRequestInFlight } from "./api.js";
import { renderWords } from "./chips.js";
import { emptyEdits, reconcile } from "./edits.js";
import { parentFilter, parentSelect, renderParents, titleOf } from "./parents.js";
import { savePreference } from "./settings.js";
import { loadVocabulary } from "./vocabulary.js";
import { clearBuildError, setOperation, setPageStyle, show, showBuildError } from "./wizard.js";

/* Owned here because connect.js is the only writer, and a module-level `let`
   cannot be reassigned across an ES module boundary. */
let liveMonitor = null;
let liveSyncing = false;
let layoutRequest = 0;

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
  $("connection-detail").hidden = true;
  $("connection-detail").textContent = "";
}

/* *detail* is the sentence that turns a refusal into something a user can act
   on: why administrator approval is being asked for, what it is a property of,
   and what still works without it. A bare "Administrator restart was
   cancelled." told a clinician who is not a local administrator nothing they
   could use. */
function showConnectionError(product, message = "", detail = "") {
  const box = $("connection-error");
  if (product === "TD Snap") {
    box.querySelector("strong").textContent =
      "AAC Editor couldn’t reach TD Snap. Nothing was changed.";
  } else {
    box.querySelector("strong").textContent = `AAC Editor couldn’t reach ${product}. Nothing was changed.`;
  }
  $("live-status").textContent = message;
  const note = $("connection-detail");
  note.textContent = detail;
  note.hidden = !detail;
  box.hidden = false;
  box.focus({ preventScroll: true });
}

/* The last guidance block /api/grid3/status returned, so a failure thrown
   further down the connect flow can still explain the gate it hit. */
let grid3Guidance = null;

/* What live Grid 3 editing can and cannot do, listed before the user commits
   rather than after. Rendered from the server's own list so the screen and the
   code that enforces it cannot drift apart. */
function renderGrid3Limits(guidance) {
  const box = $("grid3-limits");
  const limits = guidance && guidance.limits;
  if (!limits) {
    box.hidden = true;
    return;
  }
  [["grid3-can", limits.can], ["grid3-cannot", limits.cannot]].forEach(
    ([id, entries]) => {
      const list = $(id);
      list.innerHTML = "";
      (entries || []).forEach((entry) => {
        const item = document.createElement("li");
        item.textContent = entry;
        list.append(item);
      });
    },
  );
  box.hidden = state.provider !== "grid3" || state.connected;
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
  // Grid 3 has no page picker (the open grid is the page); everything else
  // on the live items step — creating a page, changing or undoing — it shares.
  document.querySelectorAll("[data-tdsnap-only]").forEach((element) => {
    element.hidden = grid3;
  });
  document.querySelectorAll("[data-live-only]").forEach((element) => {
    element.hidden = file;
  });
  $("layout-options-btn").hidden = grid3;
  $("grid3-limits").hidden = !grid3;
  if (grid3) void loadGrid3Guidance();
  $("connect-task-copy").textContent = file
    ? "Choose an .sps or .spb file exported from TD Snap. Your original file stays unchanged."
    : grid3
      ? "Open Grid 3 to the grid you want to change (not in Edit Mode), then connect."
      : "Open TD Snap to the page you want to change, then connect.";
  $("live-connect-btn").querySelector(".btn-label").textContent = file
    ? "Choose a file"
    : grid3
      ? (state.elevated ? "Connect to Grid 3" : "Enable Grid 3 editing")
      : "Connect to TD Snap";
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
        "<li>Return here and select <strong>Connect to TD Snap</strong>.</li>";
  $("connection-help-note").textContent = file
    ? "The editor works on a temporary copy and never overwrites your export."
    : "Direct editing follows the page open in the selected AAC app.";
  $("live-status").textContent = "";
}

/* Ask what Grid 3 can do the moment somebody looks at it, rather than after
   they have committed to it and been stopped. One cheap call, only for the
   people actually considering Grid 3, and a failure costs the panel and
   nothing else — the connect attempt itself re-reads the same endpoint. */
async function loadGrid3Guidance() {
  if (grid3Guidance) {
    renderGrid3Limits(grid3Guidance);
    return;
  }
  try {
    const data = await api("/api/grid3/status");
    grid3Guidance = data.guidance || null;
  } catch {
    grid3Guidance = null;
  }
  if (state.provider === "grid3") renderGrid3Limits(grid3Guidance);
}

/* The explanation that belongs with whatever gate Grid 3 stopped at, or "" for
   every other provider and for a Grid 3 failure the server never described. */
function grid3Detail() {
  if (state.provider !== "grid3" || !grid3Guidance) return "";
  return grid3Guidance.ready ? "" : grid3Guidance.detail || "";
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

/* After a Grid 3 edit, the grid on screen is the only page the app can offer —
   and after creating a grid, that is the new grid. Re-read it and its layout. */
async function followGrid3Page() {
  const data = await api("/api/grid3/status");
  if (!data.running || !data.page) return null;
  state.currentPage = data.page;
  state.parentId = data.page;
  state.pages = [{ id: data.page, title: data.page }];
  state.grid = data.grid;
  $("build-sub").textContent =
    `Connected to “${data.page}” in ${data.grid_set} · ${data.grid.cols}×${data.grid.rows} grid`;
  $("preview-live-text").textContent = `Grid 3 · ${data.page}`;
  setOperation("existing");
  state.pageEdits = emptyEdits();
  return loadTargetLayout(data.page);
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

/* Which exported-file session this tab is working in, kept for this tab only,
   so a reload picks the same temporary copy back up — edits included — rather
   than stranding it. */
const FILE_SESSION_KEY = "aac-editor-file-session";

function rememberFileSession(sessionId) {
  try {
    if (sessionId) window.sessionStorage.setItem(FILE_SESSION_KEY, sessionId);
    else window.sessionStorage.removeItem(FILE_SESSION_KEY);
  } catch {
    /* storage can be unavailable; a reload then simply starts over */
  }
}

function rememberedFileSession() {
  try {
    return window.sessionStorage.getItem(FILE_SESSION_KEY) || "";
  } catch {
    return "";
  }
}

/* After a reload: reopen the exported copy this tab was working in, if the
   app still has it. Quietly does nothing when it does not. */
async function resumeFileSession() {
  const sessionId = rememberedFileSession();
  if (!sessionId || state.connected) return false;
  try {
    const data = await api(`/api/pageset/${encodeURIComponent(sessionId)}`);
    selectProvider("file");
    await useFileSession(data);
    state.edits = data.edits || 0;
    state.fileUnsaved = Boolean(data.unsaved);
    $("live-status").textContent = "";
    showFileResumeNote(data);
    return true;
  } catch {
    rememberFileSession("");
    return false;
  }
}

/* The edited copy can be saved from the header at any point, not only from the
   result screen — which a reload, or simply moving on to the next page, used
   to leave with no way back to. */
function syncFileSave() {
  const link = $("header-save-btn");
  const available = state.mode === "file" && state.connected && state.edits > 0;
  link.hidden = !available;
  if (!available) {
    link.removeAttribute("href");
    return;
  }
  link.href = `/api/pageset/${encodeURIComponent(state.sessionId)}/download`;
  link.download = state.filename.replace(/(\.[^.]+)?$/, ".edited$1");
  link.classList.toggle("btn-primary", state.fileUnsaved);
  link.classList.toggle("btn-secondary", !state.fileUnsaved);
  link.textContent = state.fileUnsaved ? "Save edited copy" : "Save again";
}

$("header-save-btn").addEventListener("click", (event) => {
  if (state.native && window.pywebview?.api?.save_pageset) {
    // The native window saves through its own dialog, as the result screen does.
    event.preventDefault();
    $("file-save-btn").click();
    return;
  }
  state.fileUnsaved = false;
  syncFileSave();
});

function showFileResumeNote(data) {
  syncFileSave();
  const note = $("destination-intro");
  note.textContent = data.unsaved
    ? `Picked up where you left off in ${data.filename}. Your earlier changes are ` +
      "still here — save the edited copy when you're done."
    : `Picked up where you left off in ${data.filename}.`;
}

async function useFileSession(data) {
  if (!data || data.ok === false) throw new Error(data?.error || "The page set could not be opened.");
  if (data.cancelled) return false;
  if (!data.session_id || !Array.isArray(data.pages) || !data.pages.length) {
    throw new Error("The page set does not contain any editable pages.");
  }
  clearInterval(liveMonitor);
  rememberFileSession(data.session_id);
  state.fileUnsaved = false;
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
  // Adding to a page that already exists is the shorter, more common path, so
  // an exported file opens on the page picker; creating a page is a link there.
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
  show("destination");
  try {
    await loadTargetLayout(titleOf(state.parentId));
  } catch (error) {
    showBuildError("Couldn’t load that page. Choose another one.", [error.message]);
  }
  await loadVocabulary();
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
      grid3Guidance = data.guidance || null;
      renderGrid3Limits(grid3Guidance);
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
          throw new Error(restarted?.error || "Administrator approval was not given.");
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
      setOperation("existing");
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
    // Advisory duplicate checking across the whole page set; a failure here
    // costs the advisory and nothing else, so it is never awaited for success.
    await loadVocabulary();
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
    showConnectionError(product, error.message, grid3Detail());
  } finally {
    setActivity();
    setBusy(button, false);
  }
});

/* A live app is sometimes caught between pages — TD Snap has no page grid for
   a moment while it navigates or redraws — and a read at that instant fails
   although nothing is wrong. Try again briefly before calling it a failure;
   an exported file is a file, and fails the first time for real. A timeout is
   never retried: the app has already been given a minute. */
const LAYOUT_RETRIES = 2;
const LAYOUT_RETRY_DELAY_MS = 700;

async function readLayout(path, stillWanted) {
  for (let attempt = 0; ; attempt += 1) {
    try {
      return await api(path);
    } catch (error) {
      const retry = state.mode === "live" && error.name !== "TimeoutError" &&
        attempt < LAYOUT_RETRIES && stillWanted();
      if (!retry) throw error;
      await new Promise((resolve) => setTimeout(resolve, LAYOUT_RETRY_DELAY_MS));
    }
  }
}

/* Resolves once no page layout is loading, so Continue can wait for the page
   the user just picked rather than asking them to click again. */
async function layoutSettled() {
  while (state.targetLoading) {
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
}

async function loadTargetLayout(pageName, currentOnly = false) {
  if (state.operation !== "existing" || (!pageName && !currentOnly)) return null;
  const request = ++layoutRequest;
  const target = state.parentId;
  const session = state.sessionId;
  const provider = state.provider;
  clearBuildError();
  state.targetLoading = true;
  state.layoutFingerprint = null;
  state.parentFree = null;
  parentSelect.disabled = true;
  $("parent-capacity").textContent = "Loading the existing layout…";
  setPreviewBusy(true, currentOnly
    ? "Refreshing the live TD Snap page…"
    : `Loading “${pageName}”…`);
  try {
    const path = state.mode === "file"
      ? `/api/pageset/${encodeURIComponent(state.sessionId)}` +
        `/page/${encodeURIComponent(state.parentId)}/layout`
      : state.provider === "grid3"
        ? "/api/grid3/page-layout"
        : currentOnly
          ? "/api/tdsnap/page-layout"
          : `/api/tdsnap/page-layout?page=${encodeURIComponent(pageName)}`;
    const data = await readLayout(path, () => request === layoutRequest);
    if (request !== layoutRequest || state.operation !== "existing" ||
        state.parentId !== target || state.sessionId !== session || state.provider !== provider) {
      return null;
    }
    if (state.layoutPage !== data.page) state.pageEdits = emptyEdits();
    state.layoutPage = data.page;
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
    state.canEditExisting = ["tdsnap", "grid3"].includes(state.provider) && state.mode === "live" &&
      state.operation === "existing" && data.content_readable === true;
    // A Grid 3 layout carries the retained undo; TD Snap reports it separately.
    if (state.provider === "grid3" && "undo" in data) state.lastEdit = data.undo;
    // Drop any pending edit whose button moved, was renamed, or stopped being
    // eligible while the live page was being followed.
    state.pageEdits = state.canEditExisting
      ? reconcile(state.pageEdits, state.existingButtons)
      : emptyEdits();
    $("parent-capacity").classList.remove("error");
    $("parent-capacity").textContent = data.free_slots.length
      ? `${data.free_slots.length} empty space${data.free_slots.length === 1 ? "" : "s"} ` +
        `AAC Editor can update safely on “${data.page}”.`
      : `“${data.page}” is full. Choose another page or remove existing vocabulary in ${state.provider === "grid3" ? "Grid 3" : "TD Snap"}.`;
    state.currentPage = state.mode === "file" ? state.parentId : data.page;
    $("current-page-label").textContent = `Adding to ${data.page}`;
    renderWords();
    return data;
  } catch (error) {
    if (request !== layoutRequest || state.operation !== "existing" || state.parentId !== target) {
      return null;
    }
    state.existingButtons = [];
    state.availableSlots = [];
    state.grid3Cells = [];
    state.layoutFingerprint = null;
    state.canEditExisting = false;
    state.pageEdits = emptyEdits();
    $("parent-capacity").classList.add("error");
    $("parent-capacity").textContent = "The layout could not be loaded.";
    renderWords();
    throw error;
  } finally {
    if (request === layoutRequest) {
      state.targetLoading = false;
      parentSelect.disabled = false;
      setPreviewBusy(false);
    }
  }
}

/* Every poll walks TD Snap's accessibility tree, which is not free for TD Snap
   either; once every 1.5 s still follows a page change well within the time
   it takes somebody to look back at this window. */
const LIVE_MONITOR_MS = 1500;

function startLiveMonitor() {
  clearInterval(liveMonitor);
  liveMonitor = setInterval(syncLivePreview, LIVE_MONITOR_MS);
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
      state.provider !== "tdsnap" || state.operation !== "existing" ||
      $("step-build").hidden || userRequestInFlight()) return;
  liveSyncing = true;
  try {
    const selectedPage = state.parentId;
    const status = await api("/api/tdsnap/status", {
      headers: { "X-TDSnap-Brief": "1" },
      background: true,
    }, 10_000);
    if (state.targetLoading || state.parentId !== selectedPage || state.operation !== "existing") return;
    // "busy": AAC Editor is already driving TD Snap for something the user
    // asked for. The next poll will look again.
    if (status.busy || !status.running || !status.page || status.page === state.currentPage) return;
    const previousPage = state.currentPage;
    const layout = await loadTargetLayout("", true);
    if (!layout) return;
    // Planned words follow the page open in TD Snap. Say so, rather than
    // letting words meant for one page quietly land on another.
    if (state.words.length && layout.page !== previousPage) {
      const count = state.words.length;
      $("chip-note").textContent =
        `TD Snap is now showing “${layout.page}”, so your ${count} planned ` +
        `button${count === 1 ? "" : "s"} will go there. Go back to ` +
        `“${previousPage}” in TD Snap to add them to that page instead.`;
    }
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

export {
  followGrid3Page, layoutSettled, loadTargetLayout, refreshDetectedPages, rememberFileSession,
  resumeFileSession, selectProvider, stopLiveMonitor, syncFileSave,
};
