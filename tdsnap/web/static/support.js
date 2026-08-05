/* Unsaved work, unexpected failures, and the support report.
 *
 * The composed word list is the one thing this app holds that nothing else has
 * a copy of, so leaving with it unsaved asks first. An uncaught exception used
 * to leave the wizard frozen and silent; now it says so and offers the report.
 */

import { state } from "./state.js";
import { $ } from "./dom.js";
import { api } from "./api.js";

/* The last few unexpected failures, appended to the support report. Bounded so
   a repeating error can't grow without limit. */
const recentErrors = [];
const MAX_RECENT_ERRORS = 5;

/* ---------- unsaved work, unexpected errors, support report ---------- */

/* Composing a page is the one thing the app holds that nothing else has a
   copy of: it lives in state.words until an edit is applied. A reload would
   drop it silently, so ask first.

   state.words survives a successful edit — it is only cleared when the user
   starts another one — so state.applied, not emptiness, is what says the work
   is safely in the page set. */
function hasUnsavedWork() {
  return !state.applied && Boolean(state.words.length || state.pendingEdit);
}

window.addEventListener("beforeunload", (event) => {
  if (state.leaving || !hasUnsavedWork()) return;
  // Browsers show their own wording; returnValue just opts into the prompt.
  event.preventDefault();
  event.returnValue = "";
  return "";
});

function recordError(source, detail) {
  const entry = `${new Date().toISOString()} · ${source}: ${detail}`;
  recentErrors.push(entry);
  if (recentErrors.length > MAX_RECENT_ERRORS) recentErrors.shift();
}

/* An uncaught exception used to leave the wizard frozen and completely
   silent. Say so instead: the work is still in memory, and the support
   report is one click away. */
function showAppError(source, detail) {
  recordError(source, detail);
  const banner = $("app-error");
  $("app-error-text").textContent = detail;
  const wasHidden = banner.hidden;
  banner.hidden = false;
  if (wasHidden) banner.focus();
}

window.addEventListener("error", (event) => {
  const detail = event.error?.message || event.message || "Unknown error";
  showAppError("error", detail);
});

window.addEventListener("unhandledrejection", (event) => {
  const reason = event.reason;
  const detail = reason?.message || String(reason || "Unknown error");
  showAppError("unhandledrejection", detail);
});

$("app-error-dismiss").addEventListener("click", () => {
  $("app-error").hidden = true;
});

async function showSupportReport() {
  const dialog = $("support-dialog");
  const output = $("support-report-text");
  const status = $("support-copy-status");
  status.textContent = "";
  status.className = "status-line";
  output.textContent = "Collecting…";
  dialog.showModal();
  let text;
  try {
    ({ text } = await api("/api/diagnostics"));
  } catch (error) {
    // The report is most valuable when the app is unwell, so a failed
    // collection still has to produce something pasteable.
    text = `AAC Editor support report\n\n[app]\n  collection_failed: ${error.message}`;
  }
  if (recentErrors.length) {
    text += `\n\n[recent app errors]\n${recentErrors.map((line) => `  ${line}`).join("\n")}`;
  }
  output.textContent = text;
}

$("support-report-btn").addEventListener("click", showSupportReport);
$("app-error-report").addEventListener("click", showSupportReport);

$("support-copy").addEventListener("click", async () => {
  const status = $("support-copy-status");
  try {
    await navigator.clipboard.writeText($("support-report-text").textContent);
    status.textContent = "Copied. Paste it into your bug report.";
    status.className = "status-line success";
  } catch {
    // Clipboard access can be refused; the text is selectable either way.
    const range = document.createRange();
    range.selectNodeContents($("support-report-text"));
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    status.textContent = "Couldn’t copy automatically — the report is selected, so press Ctrl+C.";
    status.className = "status-line error";
  }
});

export { hasUnsavedWork, recordError };
