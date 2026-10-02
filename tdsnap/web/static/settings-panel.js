/* What AAC Editor saves: what's stored, in plain language, where it is, the one
 * choice about keeping an unfinished page, and a button to clear all of it. This
 * is the "Clear all saved data" control and the honest listing the README's
 * Private by design section promises.
 *
 * The static parts of the dialog (what else is on disk, what can leave this
 * computer) live in index.html, where they can be read without running anything.
 */

import { $ } from "./dom.js";
import { setDraftAutosave, syncDraftAutosave } from "./draft.js";
import {
  clearAll, draftAutosaveOn, getDraft, getFolders, getPreferences, getTemplates,
  settingsReadSucceeded,
} from "./settings.js";

const PREFERENCE_LABELS = {
  provider: "Last AAC app used",
  ai_engine: "Preferred AI engine",
  ollama_host: "Ollama server address",
  ollama_model: "Ollama model name",
  ai_style: "Whether suggestions match this page set's wording",
  ai_model: "Which built-in AI model to use",
  experience: "How much help you asked for",
  tips_seen: "Tips for the Build screen",
  draft_autosave: "Keep an unfinished page",
};

/* Values that mean nothing on their own are described instead of printed. */
const VALUE_LABELS = {
  experience: {
    new: "New to this: tips and hints",
    some: "Edited AAC pages before: hints, no tips",
    expert: "Builds page sets often: fewer hints",
  },
  tips_seen: { true: "Dismissed" },
  ai_style: { true: "On", false: "Off" },
  draft_autosave: { true: "On", false: "Off" },
};

function renderEntry(list, term, description) {
  const dt = document.createElement("dt");
  dt.textContent = term;
  const dd = document.createElement("dd");
  dd.textContent = description;
  list.append(dt, dd);
}

function setFolder(id, folder) {
  const line = $(id);
  line.hidden = !folder;
  line.querySelector("code").textContent = folder || "";
}

async function renderPanel() {
  const list = $("settings-panel-list");
  list.innerHTML = "";
  const [preferences, draft, templates, folders, keepDraft] = await Promise.all([
    getPreferences(), getDraft(), getTemplates(), getFolders(), draftAutosaveOn(),
  ]);
  setFolder("settings-folder-line", folders.settings);
  setFolder("working-copies-folder-line", folders.workingCopies);
  $("draft-autosave-toggle").checked = keepDraft;
  if (!settingsReadSucceeded()) {
    renderEntry(
      list,
      "Couldn’t read saved data",
      "Try again. Saved information may still be on this computer.",
    );
    return;
  }
  const preferenceEntries = Object.entries(preferences).filter(
    ([, value]) => value !== "" && value !== null,
  );

  if (!preferenceEntries.length && !draft && !templates.length) {
    renderEntry(
      list,
      "Nothing saved yet",
      "AAC Editor has not created a settings file on this computer.",
    );
    return;
  }
  preferenceEntries.forEach(([key, value]) => {
    renderEntry(
      list,
      PREFERENCE_LABELS[key] || key,
      VALUE_LABELS[key]?.[String(value)] || String(value),
    );
  });
  if (draft) {
    const count = Array.isArray(draft.items) ? draft.items.length : 0;
    const target =
      draft.operation === "existing" && draft.target_page
        ? draft.target_page
        : draft.title || "an unnamed page";
    renderEntry(
      list,
      "Unfinished page",
      `${count} button${count === 1 ? "" : "s"} planned for “${target}”, saved so you can resume it.`,
    );
  }
  // Clearing wipes these too, so the listing has to name them by name — this
  // is the one place a user finds out what they would be throwing away.
  if (templates.length) {
    const names = [...templates]
      .map((template) => template.name)
      .sort((left, right) => left.localeCompare(right));
    renderEntry(
      list,
      `Saved template${names.length === 1 ? "" : "s"}`,
      `${names.join(", ")} — reusable word lists, kept until you delete them.`,
    );
  }
}

/* What Clear all actually did, said exactly. "Nothing is saved anymore" would be
   untrue while a page set is open or a downloaded model is on disk. */
function clearedMessage({ workingCopiesRemoved, workingCopiesOpen }) {
  const parts = ["Cleared your saved settings, templates, and any unfinished page."];
  if (workingCopiesRemoved) {
    parts.push(
      `Removed ${workingCopiesRemoved} leftover temporary cop${workingCopiesRemoved === 1 ? "y" : "ies"} `
      + "of a page set.",
    );
  }
  if (workingCopiesOpen) {
    parts.push(
      "The page set you have open right now stays until you close it or quit AAC Editor.",
    );
  }
  parts.push(
    "A downloaded suggestion model is not personal data. It stays in the “models” folder "
    + "next to the settings file until you delete it.",
  );
  return parts.join(" ");
}

$("settings-panel-btn").addEventListener("click", async () => {
  const status = $("settings-panel-status");
  status.textContent = "";
  status.className = "status-line";
  await renderPanel();
  $("settings-panel").showModal();
});

$("draft-autosave-toggle").addEventListener("change", async () => {
  const toggle = $("draft-autosave-toggle");
  const status = $("settings-panel-status");
  toggle.disabled = true;
  try {
    const saved = await setDraftAutosave(toggle.checked);
    await renderPanel();
    if (saved) {
      status.textContent = toggle.checked
        ? "AAC Editor will keep an unfinished page on this computer, and nothing else about it."
        : "Stopped keeping unfinished pages, and deleted the one that was kept.";
      status.className = "status-line success";
    } else {
      status.textContent = "Couldn’t change that setting. Try again.";
      status.className = "status-line error";
    }
  } finally {
    toggle.disabled = false;
  }
});

$("settings-clear-btn").addEventListener("click", async () => {
  const button = $("settings-clear-btn");
  const status = $("settings-panel-status");
  button.disabled = true;
  try {
    const result = await clearAll();
    await syncDraftAutosave();
    await renderPanel();
    status.textContent = clearedMessage(result);
    status.className = "status-line success";
  } catch {
    status.textContent = "Couldn’t clear saved data. Try again.";
    status.className = "status-line error";
  } finally {
    button.disabled = false;
  }
});
