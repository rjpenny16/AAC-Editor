/* The Settings disclosure: what's stored, in plain language, and one button
 * to clear all of it. This is the "Clear all saved data" control and the
 * honest listing the README's Private by design section promises.
 */

import { $ } from "./dom.js";
import { clearAll, getDraft, getPreferences } from "./settings.js";

const PREFERENCE_LABELS = {
  provider: "Last AAC app used",
  ai_engine: "Preferred AI engine",
  ollama_host: "Ollama server address",
  ollama_model: "Ollama model name",
  ai_grounding: "Wikipedia lookup preference",
};

function renderEntry(list, term, description) {
  const dt = document.createElement("dt");
  dt.textContent = term;
  const dd = document.createElement("dd");
  dd.textContent = description;
  list.append(dt, dd);
}

async function renderPanel() {
  const list = $("settings-panel-list");
  list.innerHTML = "";
  const [preferences, draft] = await Promise.all([getPreferences(), getDraft()]);
  const preferenceEntries = Object.entries(preferences).filter(
    ([, value]) => value !== "" && value !== null,
  );

  if (!preferenceEntries.length && !draft) {
    renderEntry(
      list,
      "Nothing saved yet",
      "AAC Editor hasn't written anything to disk on this computer.",
    );
    return;
  }
  preferenceEntries.forEach(([key, value]) => {
    renderEntry(list, PREFERENCE_LABELS[key] || key, String(value));
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
}

$("settings-panel-btn").addEventListener("click", async () => {
  const status = $("settings-panel-status");
  status.textContent = "";
  status.className = "status-line";
  await renderPanel();
  $("settings-panel").showModal();
});

$("settings-clear-btn").addEventListener("click", async () => {
  const button = $("settings-clear-btn");
  const status = $("settings-panel-status");
  button.disabled = true;
  try {
    await clearAll();
    await renderPanel();
    status.textContent = "Cleared. Nothing is saved on this computer anymore.";
    status.className = "status-line success";
  } catch {
    status.textContent = "Couldn’t clear saved data. Try again.";
    status.className = "status-line error";
  } finally {
    button.disabled = false;
  }
});
