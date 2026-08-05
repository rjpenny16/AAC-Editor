/* The optional AI suggestion panel.
 *
 * Two interchangeable engines sit behind one button: a bundled model the user
 * downloads once, or an Ollama server they already run. Both are local. The
 * panel is entirely optional — the editor is complete without it, and nothing
 * here may become a step the user has to pass through.
 */

import { state } from "./state.js";
import { $, setBusy } from "./dom.js";
import { api } from "./api.js";
import { firstAvailableSlot, functionForSlot, renderWords } from "./chips.js";
import { setActivity } from "./dom.js";
import { titleOf } from "./parents.js";
import { inferPhraseFunction } from "./phrases.js";
import { FUNCTIONS } from "./state.js";

/* ---------- step 2: AI engines ---------- */

let aiReady = false;

$("ai-suggest").addEventListener("toggle", () => {
  if ($("ai-suggest").open && !aiReady) checkAi();
});

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

async function checkAiWithFeedback() {
  const button = $("ai-check-btn");
  $("ai-engine-state").textContent = "Checking the Ollama connection…";
  setActivity("Checking your AI connection…");
  setBusy(button, true, "Checking…");
  try {
    await checkAi();
  } finally {
    setBusy(button, false);
    setActivity();
  }
}

$("ai-host").addEventListener("change", checkAiWithFeedback);
$("ai-check-btn").addEventListener("click", checkAiWithFeedback);
$("ai-model").addEventListener("input", () => {
  $("ai-model").dataset.userEdited = "1";
});

$("ai-download-btn").addEventListener("click", async () => {
  const button = $("ai-download-btn");
  const status = $("ai-download-status");
  status.classList.remove("error", "success");
  setBusy(button, true, "Starting download…");
  setActivity("Starting the model download…");
  try {
    await api("/api/ai/download", { method: "POST" });
    trackDownload();
  } catch (error) {
    setBusy(button, false);
    status.classList.add("error");
    status.textContent = `The model download couldn’t start. ${error.message}`;
  } finally {
    setActivity();
  }
});

let downloadTimer = null;

function trackDownload() {
  if (downloadTimer) return; // a poll is already running
  const button = $("ai-download-btn");
  const bar = $("ai-progress");
  const fill = $("ai-progress-fill");
  const status = $("ai-download-status");
  setBusy(button, true, "Downloading…");
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
        status.classList.add("success");
        status.textContent = "Done — suggestions are ready.";
        checkAi();
      } else if (dl.status === "error") {
        status.classList.remove("success");
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
  const category = state.operation === "existing"
    ? titleOf(state.parentId)
    : $("title-input").value.trim();
  status.classList.remove("error", "success");
  if (!category) {
    status.classList.add("error");
    status.textContent = state.operation === "existing"
      ? "Choose an existing page first."
      : "Give the page a title first — it's used as the category.";
    return;
  }
  const topic = state.pageStyle === "topic";
  const what = topic
    ? state.activeFn
      ? `${FUNCTIONS[state.activeFn].name.toLowerCase()} phrases`
      : "phrases"
    : "words";
  setBusy(button, true, "Generating…");
  setActivity(`Generating ${what} for “${category}”…`);
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
        grounding: $("ai-grounding").checked,
        existing: [...new Set(state.existingButtons
          .map((item) => item.label.trim())
          .filter((label) => label && label.toLocaleLowerCase() !== "existing button"))],
      }),
    });
    // Phrases arrive comma-prone; add them one by one instead of splitting.
    const capacity = state.availableSlots
      ? state.availableSlots.length : state.grid.cols * state.grid.rows - state.existingButtons.length;
    let added = 0;
    data.words.forEach((suggestion) => {
      const label = (typeof suggestion === "string"
        ? suggestion
        : String(suggestion.label || "")).trim();
      const suggestedFn = typeof suggestion === "object" && suggestion &&
        FUNCTIONS[suggestion.function] ? suggestion.function : "";
      const exists = [...state.existingButtons, ...state.words].some(
        (item) => item.label.toLocaleLowerCase() === label.toLocaleLowerCase()
      );
      if (label && !exists && state.words.length < capacity) {
        let fn = topic
          ? state.activeFn || inferPhraseFunction(label, suggestedFn)
          : "";
        const slot = firstAvailableSlot(topic && state.autoTopicRows ? fn : "");
        if (topic && !fn && state.autoTopicRows) fn = functionForSlot(slot);
        state.words.push({ label, message: null, fn, slot, symbol: true });
        added += 1;
      }
    });
    renderWords();
    status.classList.add("success");
    status.textContent = `Added ${added} suggestions — remove any you don't want.`;
  } catch (error) {
    status.classList.add("error");
    status.textContent = `Suggestions couldn’t be generated. ${error.message}`;
  } finally {
    setActivity();
    setBusy(button, false);
  }
});
