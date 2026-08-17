/* What happened, after the write.
 *
 * Reports the named checks the backend ran, surfaces any warnings verbatim,
 * and offers the next action. resetConnection lives here because tearing a
 * session down is the other half of finishing one.
 */

import { state } from "./state.js";
import { $, setBusy, setActivity } from "./dom.js";
import { api } from "./api.js";
import { clearUndoHistory, renderWords } from "./chips.js";
import { loadTargetLayout, refreshDetectedPages, selectProvider, stopLiveMonitor } from "./connect.js";
import { clearDraft } from "./draft.js";
import { emptyEdits, undoAvailable } from "./edits.js";
import { parentFilter, renderParents, titleOf } from "./parents.js";
import { recordError } from "./support.js";
import { setOperation, setPageStyle, show, showBuildError } from "./wizard.js";

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
  changed_content: "Every changed button says what you asked for",
  moved_buttons: "Every moved button is in its new cell",
  removed_buttons: "Every removed button is gone",
  untouched_buttons: "Nothing else on the page changed",
  undone: "The previous change was put back",
  symbols: "Matching symbols were added when available",
  topic_format: "Topic-page row colors were applied in TD Snap",
  grid3_edit: "Grid 3 saved the change",
  target_grid: "The reviewed grid was updated",
  style_preserved: "Every new cell retained its existing Grid 3 style",
  save_completed: "Your page set was saved",
};

const CHECK_SVG =
  '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
  'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<path d="M20 6 9 17l-5-5"/></svg>';

function editedCounts(data) {
  return [
    data.buttons ? `${data.buttons} added` : "",
    data.changed ? `${data.changed} changed` : "",
    data.moved ? `${data.moved} moved` : "",
    data.removed ? `${data.removed} removed` : "",
  ].filter(Boolean).join(", ");
}

/* The undo control, and what it can still reach. Rendered from state so the
   button disappears the moment the snapshot behind it is spent — a single-level
   undo that still looks available is worse than no undo at all. */
function renderUndoControl() {
  const button = $("undo-edit-btn");
  const note = $("undo-availability");
  const available = undoAvailable(state);
  if (button) button.hidden = !available;
  if (!note) return;
  note.hidden = !available;
  note.textContent = available
    ? `Undo puts “${state.lastEdit.page}” back the way it was. It reaches back one ` +
      "change, and not past a sync in TD Snap."
    : "";
}

function renderResult(title, data, operation = state.operation, parentTitle = titleOf(state.parentId)) {
  $("review-state").hidden = true;
  $("success-state").hidden = false;
  state.applied = true;
  clearUndoHistory();
  void clearDraft();
  $("result-eyebrow").textContent = "Complete";
  const product = state.provider === "grid3" ? "Grid 3" : "TD Snap";
  $("result-heading").textContent = data.undone
    ? `Done — the last change was undone in ${product}`
    : `Done — ${product} was updated`;
  renderUndoControl();
  $("edit-count").textContent =
    state.edits > 1 ? `· ${state.edits} edits this session` : "";
  $("another-btn").textContent = "Add more buttons";
  const saveButton = $("file-save-btn");
  saveButton.hidden = state.mode !== "file";
  if (state.mode === "file") {
    const editedName = state.filename.replace(/(\.[^.]+)?$/, ".edited$1");
    saveButton.href = `/api/pageset/${encodeURIComponent(state.sessionId)}/download`;
    saveButton.download = editedName;
  } else {
    saveButton.removeAttribute("href");
    saveButton.removeAttribute("download");
  }
  const touched = (data.changed || 0) + (data.removed || 0) + (data.moved || 0);
  $("result-sub").textContent = data.undone
    ? `“${title}” is back the way it was: ${editedCounts(data)}. There is nothing ` +
      "left to undo from this session."
    : operation !== "existing"
      ? `“${title}” has ${data.buttons} speaking button${data.buttons === 1 ? "" : "s"}, and “${parentTitle}” now links to it.`
      : touched
        ? `“${title}” was updated: ${editedCounts(data)}. Nothing else on the page changed.`
        : `${data.buttons} speaking button${data.buttons === 1 ? " was" : "s were"} added to ` +
          `“${title}” without changing its existing ${state.provider === "grid3" ? "cells" : "vocabulary"}.`;

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
    lead.textContent = `${product} finished with a note:`;
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

$("file-save-btn").addEventListener("click", async (event) => {
  if (state.mode !== "file" || !state.native || !window.pywebview?.api?.save_pageset) return;
  event.preventDefault();
  const button = $("file-save-btn");
  setBusy(button, true, "Saving…");
  setActivity("Saving the edited copy…");
  try {
    const result = await window.pywebview.api.save_pageset(state.sessionId);
    if (!result || result.ok === false) throw new Error(result?.error || "The file could not be saved.");
    if (!result.cancelled) {
      $("live-result-note").textContent =
        `The edited copy was saved to ${result.path}. Review it before importing it into TD Snap.`;
    }
  } catch (error) {
    $("live-result-note").textContent = `The edited copy could not be saved. ${error.message}`;
  } finally {
    setActivity();
    setBusy(button, false);
  }
});

$("another-btn").addEventListener("click", async () => {
  state.words = [];
  state.pageEdits = emptyEdits();
  state.applied = false;
  state.parentId = state.currentPage;
  state.parentFree = 1;
  state.parentTouched = false;
  state.pendingEdit = null;
  state.placementAdjusted = false;
  $("title-input").value = "";
  $("parent-capacity").textContent = "";
  $("chip-note").textContent = "";
  parentFilter.value = "";
  if (state.mode === "file") {
    const wasExisting = state.operation === "existing";
    state.existingButtons = [];
    state.availableSlots = null;
    state.layoutFingerprint = null;
    state.parentFree = null;
    setPageStyle("words");
    try {
      await refreshDetectedPages();
      if (!state.pages.some((page) => page.id === state.parentId)) {
        state.parentId = state.pages[0]?.id || null;
      }
      renderParents("");
      // Somebody who just added to a page usually has more to add to it, so
      // stay on that page rather than sending them back to naming a new one.
      if (wasExisting && state.parentId) {
        setOperation("existing");
        await loadTargetLayout(titleOf(state.parentId));
        show("items");
      } else {
        setOperation("new");
        show("title");
      }
    } catch (error) {
      resetConnection();
      $("live-status").classList.add("error");
      $("live-status").textContent = `Open the exported file again. ${error.message}`;
    }
    return;
  }
  if (state.provider === "grid3") {
    setPageStyle("words");
    setActivity("Refreshing the Grid 3 grid…");
    try {
      await loadTargetLayout(state.currentPage);
      renderWords();
      show("items");
    } catch (error) {
      resetConnection();
      $("live-status").classList.add("error");
      $("live-status").textContent = `Reconnect to Grid 3. ${error.message}`;
    } finally {
      setActivity();
    }
    return;
  }
  state.existingButtons = [];
  state.availableSlots = null;
  state.layoutFingerprint = null;
  setOperation("existing");
  setPageStyle("words");
  renderParents("");
  $("build-error").hidden = true;
  $("result-warnings").hidden = true;
  setActivity("Refreshing the page open in TD Snap…");
  try {
    await loadTargetLayout(state.currentPage);
    show("items");
  } catch (error) {
    showBuildError("Choose a page to continue.", [error.message]);
    show("destination");
  } finally {
    setActivity();
  }
});

function resetConnection() {
  stopLiveMonitor();
  clearUndoHistory();
  const sessionId = state.sessionId;
  if (sessionId) {
    // A failure here leaks the session's temp directory until the 24-hour
    // sweep. Not worth interrupting the user for, but worth recording so a
    // support report shows it.
    void api(`/api/pageset/${encodeURIComponent(sessionId)}/close`, { method: "POST" })
      .catch((error) => recordError("session-close", error.message));
  }
  // Starting over may mean a different person's page set, so the retained edit
  // has to go from the server as well as from here. It would be refused by the
  // fingerprint guard anyway; still offering it would be the wrong promise.
  if (undoAvailable(state)) {
    void api("/api/tdsnap/last-edit", { method: "DELETE" })
      .catch((error) => recordError("undo-forget", error.message));
  }
  state.lastEdit = null;
  state.mode = "live";
  state.connected = false;
  state.sessionId = null;
  state.filename = "";
  state.words = [];
  state.pageEdits = emptyEdits();
  state.canEditExisting = false;
  state.applied = false;
  state.parentId = null;
  state.parentFree = null;
  state.availableSlots = null;
  state.grid3Cells = [];
  state.previewAspect = null;
  state.gridBackground = null;
  state.pendingEdit = null;
  state.placementAdjusted = false;
  $("file-badge").hidden = true;
  $("file-save-btn").hidden = true;
  $("file-save-btn").removeAttribute("href");
  $("file-save-btn").removeAttribute("download");
  $("title-input").value = "";
  $("live-status").textContent = "";
  $("parent-capacity").textContent = "";
  $("chip-note").textContent = "";
  $("build-error").hidden = true;
  selectProvider(state.provider);
  renderWords();
  show("load");
}

$("reset-btn").addEventListener("click", resetConnection);
$("file-badge").addEventListener("click", resetConnection);

export { renderResult };
