/* AAC Editor frontend: wiring plus the workflow not yet extracted.
   Native ES modules, no bundler and no build step. */

import { state } from "./state.js";
import { $, setBusy, setActivity } from "./dom.js";
import { configReady, api } from "./api.js";
import { wireRadioGroups } from "./a11y.js";
import { renderWords } from "./chips.js";
import {
  checkLiveAgain, rememberFileSession, resumeFileSession, selectProvider,
} from "./connect.js";
import { renderPreview } from "./preview.js";
import { hasUnsavedWork } from "./support.js";
import { getPreferences } from "./settings.js";
import { show } from "./wizard.js";
import { startOnboarding } from "./onboarding.js";
// Side-effect imports: these wire their own listeners and export nothing
// anyone else calls, so without this they would never load.
import "./ai.js";
import "./review.js";
import "./draft.js";
import "./importer.js";
import "./boards.js";
import "./queue.js";
import "./templates.js";
import "./settings-panel.js";


/* ---------- live connection ---------- */

$("live-lost-retry").addEventListener("click", checkLiveAgain);


/* ---------- quit (browser mode) ---------- */

$("quit-btn").addEventListener("click", async () => {
  const warning = state.queue.length
    ? `Quit AAC Editor? ${state.queue.length} page${state.queue.length === 1 ? "" : "s"} `
      + "queued but not yet applied will be lost."
    : hasUnsavedWork()
      ? "Quit AAC Editor? The buttons you have planned but not yet added will be lost."
      : "Quit AAC Editor?";
  if (!window.confirm(warning)) return;
  setBusy($("quit-btn"), true, "Closing…");
  setActivity("Closing the local editor…");
  const quit = (force) => api("/api/quit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ force }),
  });
  try {
    await quit(false);
  } catch (error) {
    // REL-007: the server refuses to stop mid-edit, and asks first when an
    // exported file has edits that were never saved.
    if (error.code === "BUSY") {
      setActivity();
      setBusy($("quit-btn"), false);
      window.alert(error.message);
      return;
    }
    if (error.code === "UNSAVED") {
      if (!window.confirm(`${error.message} Quit anyway?`)) {
        setActivity();
        setBusy($("quit-btn"), false);
        return;
      }
      try {
        await quit(true);
      } catch {
        /* the server may stop before the response arrives */
      }
    }
    /* otherwise the server may have stopped before the response arrived */
  }
  state.leaving = true;
  setActivity();
  setBusy($("quit-btn"), false);
  document.querySelector("main").hidden = true;
  document.querySelector("footer").hidden = true;
  $("quit-screen").hidden = false;
});

/* ---------- init ---------- */

configReady.then(async () => {
  // In the native window the OS window close button quits the app;
  // in browser mode the Quit button is the only clean way to stop it.
  $("quit-btn").hidden = state.native;

  // An explicit ?provider= link always wins; a remembered choice only fills
  // in when nothing in the URL asked for a specific app.
  const linkedProvider = new URLSearchParams(window.location.search).get("provider");
  const preferences = await getPreferences();
  if (!linkedProvider && preferences.provider) state.provider = preferences.provider;
  if (preferences.ollama_host) $("ai-host").value = preferences.ollama_host;
  if (preferences.ollama_model) {
    $("ai-model").value = preferences.ollama_model;
    $("ai-model").dataset.userEdited = "1";
  }
  // Not restored: the Wikipedia lookup starts off every launch. See ai.js.
  // Style matching is on unless the user turned it off: it costs nothing, goes
  // no further than the local model, and a suggestion that reads like the rest
  // of the page set is the better default.
  if (typeof preferences.ai_style === "boolean") {
    $("ai-style").checked = preferences.ai_style;
  }
  if (preferences.ai_model) $("ai-model-choice").dataset.preferred = preferences.ai_model;
  // "local" was its own choice before the built-in model became the default
  // (REL-028); it now means the default. "ollama" is kept as chosen.
  if (preferences.ai_engine === "ollama") $("ai-engine").value = "ollama";
  else if (["auto", "local"].includes(preferences.ai_engine)) $("ai-engine").value = "auto";

  selectProvider(state.provider);
  show("load");
  // First run asks one question before anything else; a returning user goes
  // straight to connecting.
  if (await startOnboarding({ linked: Boolean(linkedProvider) })) return;
  // A reload in the middle of an exported file picks the same edited copy
  // back up. An explicit link to another app means the user has moved on.
  if (!linkedProvider || linkedProvider === "file") await resumeFileSession();
  if (!state.connected) await offerRecoverableCopy();
});

/* ---------- a live edit a previous run never finished (doc 04, L15) ---------- */

const APP_NAMES = { tdsnap: "TD Snap", grid3: "Grid 3" };

async function reportInterruptedEdits() {
  let edits = [];
  try {
    ({ edits } = await api("/api/interrupted", { background: true }));
  } catch {
    return;
  }
  if (!edits.length) return;
  $("interrupted-text").textContent = edits.map((edit) => {
    const when = edit.at ? new Date(edit.at * 1000).toLocaleString() : "an earlier session";
    const app = APP_NAMES[edit.app] || "the AAC app";
    return `A ${app} edit started at ${when} did not finish (reference ${edit.op}).`;
  }).join(" ");
  $("interrupted-banner").hidden = false;
  $("interrupted-banner").focus();
}

$("interrupted-ack-btn").addEventListener("click", async () => {
  $("interrupted-banner").hidden = true;
  try {
    await api("/api/interrupted/ack", { method: "POST" });
  } catch {
    // Shown again at the next start; that is the safe direction to fail.
  }
});

configReady.then(reportInterruptedEdits);

/* ---------- the app restarted under this page (REL-009) ---------- */

window.addEventListener("aac-app-restarted", () => {
  $("restart-banner").hidden = false;
  $("restart-banner").focus();
});

$("restart-reload-btn").addEventListener("click", () => {
  // The leave warning still applies: planned words live only in this tab.
  window.location.reload();
});

/* ---------- edited copies a previous run left unsaved (REL-007, REL-021) ---------- */

let recoverable = null;

async function offerRecoverableCopy() {
  let sessions = [];
  try {
    ({ sessions } = await api("/api/pageset/recoverable", { background: true }));
  } catch {
    return;
  }
  recoverable = sessions[0] || null;
  if (!recoverable) return;
  const when = new Date(recoverable.modified * 1000).toLocaleString();
  $("recover-banner-text").textContent =
    `An edited copy of “${recoverable.filename}” from ${when} was never saved.`;
  $("recover-banner").hidden = false;
}

$("recover-open-btn").addEventListener("click", async () => {
  if (!recoverable) return;
  $("recover-banner").hidden = true;
  rememberFileSession(recoverable.session_id);
  if (!(await resumeFileSession())) {
    $("live-status").textContent =
      "That edited copy could not be opened. The original file is unchanged.";
  }
});

$("recover-discard-btn").addEventListener("click", async () => {
  if (!recoverable) return;
  if (!window.confirm(`Discard the unsaved edits to “${recoverable.filename}”? The original file is not affected.`)) return;
  $("recover-banner").hidden = true;
  try {
    await api(`/api/pageset/${encodeURIComponent(recoverable.session_id)}/close`, { method: "POST" });
  } catch {
    // Whatever is left is swept with other leftovers after a week.
  }
  recoverable = null;
});

/* The native window refuses to close mid-edit and calls this to say why. */
window.aacCloseBlocked = (reason) => {
  $("app-error-text").textContent = reason;
  $("app-error").hidden = false;
  $("app-error").focus();
};


renderWords();
renderPreview();

wireRadioGroups();
