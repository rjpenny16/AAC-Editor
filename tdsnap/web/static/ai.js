/* The optional AI suggestion panel.
 *
 * Two interchangeable engines sit behind one button: a bundled model the user
 * downloads once, or an Ollama server they already run. Both are local. The
 * panel is entirely optional — the editor is complete without it, and nothing
 * here may become a step the user has to pass through.
 *
 * Suggestions used to be one shot, N items, take it or leave it. They are now
 * steerable, and every steer is a thing the user did rather than a setting they
 * had to find:
 *
 *   - throwing a suggestion away is remembered and sent back as "not this"
 *     (see rememberRejection in chips.js);
 *   - a suggestion can be regenerated on its own, or used as the example for
 *     more of the same kind;
 *   - a sample of the page set's own button labels goes with the request, so
 *     suggestions read the way this page set already reads.
 *
 * **None of that leaves the computer.** The whole app makes exactly one
 * outbound request — the optional Wikipedia lookup — and it carries the page
 * title and nothing else. Rejected suggestions, kept ones, style samples, and
 * existing button labels are all vocabulary belonging to a person who did not
 * agree to publish it; they go to the model running locally and stop there.
 * The server keeps the two apart by construction (see the grounding call in
 * ai_words), and a test pins it.
 */

import { AI_GENERATION_TIMEOUT_MS, state } from "./state.js";
import { $, setBusy } from "./dom.js";
import { api } from "./api.js";
import {
  editingWordIndex, existingLabels, firstAvailableSlot, functionForSlot, pageCapacity, pushUndoSnapshot,
  rememberRejection, renderWords,
} from "./chips.js";
import { setActivity } from "./dom.js";
import { titleOf } from "./parents.js";
import { inferPhraseFunction } from "./phrases.js";
import { savePreference } from "./settings.js";
import { styleSample } from "./vocabulary.js";
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
    renderModelChoices(local);

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

/* Which built-in model to download and run.
 *
 * Only shown when this build actually offers a choice, and an option the
 * machine cannot run is offered as a disabled row with the measured reason
 * beside it rather than silently missing — "why can't I pick that one?" is a
 * fair question, and the answer is a fact about the computer. */
function renderModelChoices(local) {
  const row = $("ai-model-choice-row");
  const select = $("ai-model-choice");
  const note = $("ai-model-choice-note");
  const offered = local.choices || [];
  row.hidden = offered.length < 2;
  if (row.hidden) {
    select.innerHTML = "";
    note.textContent = "";
    return;
  }
  // A remembered choice only leads until the user picks in this session; a
  // choice this machine cannot run never wins (see the fallback below).
  const wanted = select.value || select.dataset.preferred || local.selected;
  select.innerHTML = "";
  offered.forEach((choice) => {
    const option = document.createElement("option");
    option.value = choice.key;
    option.textContent =
      `${choice.name} · ${choice.size}` + (choice.downloaded ? " · downloaded" : "");
    option.disabled = !choice.supported;
    select.append(option);
  });
  const usable = offered.find((choice) => choice.key === wanted && choice.supported);
  select.value = (usable || offered[0]).key;
  describeModelChoice(offered);
}

function describeModelChoice(offered) {
  const note = $("ai-model-choice-note");
  const picked = offered.find((choice) => choice.key === $("ai-model-choice").value);
  const blocked = offered.filter((choice) => !choice.supported && choice.reason);
  note.textContent = [
    picked ? picked.summary : "",
    ...blocked.map((choice) => `${choice.name}: ${choice.reason}`),
  ].filter(Boolean).join(" ");
}

$("ai-model-choice").addEventListener("change", () => {
  $("ai-model-choice").dataset.preferred = $("ai-model-choice").value;
  void savePreference("ai_model", $("ai-model-choice").value);
  checkAi();
});

$("ai-style").addEventListener("change", () => {
  void savePreference("ai_style", $("ai-style").checked);
});

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

$("ai-host").addEventListener("change", () => {
  checkAiWithFeedback();
  void savePreference("ollama_host", $("ai-host").value);
});
$("ai-check-btn").addEventListener("click", checkAiWithFeedback);
$("ai-model").addEventListener("input", () => {
  $("ai-model").dataset.userEdited = "1";
});
$("ai-model").addEventListener("change", () => {
  void savePreference("ollama_model", $("ai-model").value);
});
$("ai-grounding").addEventListener("change", () => {
  void savePreference("ai_grounding", $("ai-grounding").checked);
});

$("ai-download-btn").addEventListener("click", async () => {
  const button = $("ai-download-btn");
  const status = $("ai-download-status");
  status.classList.remove("error", "success");
  setBusy(button, true, "Starting download…");
  setActivity("Starting the model download…");
  try {
    await api("/api/ai/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_key: $("ai-model-choice").value || null }),
    });
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

/* ---------- steering ---------- */

/* Everything the model is told to stay off: what is on the page already, and
   what is already planned. Bounded at the server's limit, newest last, because
   a long import should not push the page's own vocabulary out of the prompt. */
function knownLabels() {
  const labels = [
    ...state.existingButtons.map((item) => String(item.label || "").trim()),
    ...state.words.map((item) => String(item.label || "").trim()),
  ].filter((label) => label && label.toLocaleLowerCase() !== "existing button");
  return [...new Set(labels)].slice(-100);
}

/* How this page set words a button, as evidence rather than as subject matter.
   The page being edited comes first — it is the closest thing to the register
   the user is working in right now — and the rest of the page set fills in
   behind it. Empty when the box is unticked or the page set could not be read,
   and an empty list simply means the prompt says nothing about style. */
function styleContext() {
  if (!$("ai-style").checked) return [];
  const here = state.existingButtons
    .map((item) => String(item.label || "").trim())
    .filter((label) => label && label.toLocaleLowerCase() !== "existing button");
  const seen = new Set();
  return [...here, ...styleSample()]
    .filter((label) => {
      const folded = label.toLocaleLowerCase();
      if (!label || seen.has(folded)) return false;
      seen.add(folded);
      return true;
    })
    .slice(0, 24);
}

function pageCategory() {
  return state.operation === "existing"
    ? titleOf(state.parentId)
    : $("title-input").value.trim();
}

function describeKind() {
  if (state.pageStyle !== "topic") return "words";
  return state.activeFn
    ? `${FUNCTIONS[state.activeFn].name.toLowerCase()} phrases`
    : "phrases";
}

/* One request shape for all three ways of asking: the whole panel, one item
   regenerated, and "more like this". Only `count` and `like` differ. */
async function askForSuggestions({ count, like = [], alsoAvoid = [] }) {
  const context = suggestionContext();
  if (articleContext !== context) {
    state.aiChosenArticle = "";
    state.aiExcluded = [];
    clearGroundingSource();
    articleContext = context;
  }
  const topic = state.pageStyle === "topic";
  const data = await api(
    "/api/ai/words",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        category: pageCategory(),
        count,
        host: $("ai-host").value,
        model: $("ai-model").value,
        model_key: $("ai-model-choice").value || null,
        kind: topic ? "phrases" : "words",
        function: topic && state.activeFn ? state.activeFn : null,
        grounding: $("ai-grounding").checked,
        grounding_title: state.aiChosenArticle || null,
        grounding_exclude: state.aiExcluded,
        existing: knownLabels(),
        avoid: [...new Set([...state.aiRejected, ...alsoAvoid])],
        like,
        style: styleContext(),
      }),
    },
    AI_GENERATION_TIMEOUT_MS
  );
  if (context !== suggestionContext() || !["items", "layout"].includes(state.wizardStep)) {
    throw new Error("The page changed while suggestions were being generated. Suggest again for this page.");
  }
  renderGroundingSource(data.grounding);
  return data;
}

let articleContext = "";
function suggestionContext() {
  return JSON.stringify([state.provider, state.sessionId, state.operation, pageCategory(), state.pageStyle]);
}

/* A suggestion the user has not already got, in whatever shape the engine
   returned it. Words come back as strings and phrases as {label, function}. */
function asSuggestion(raw) {
  const label = (typeof raw === "string" ? raw : String(raw?.label || "")).trim();
  const suggested = typeof raw === "object" && raw && FUNCTIONS[raw.function]
    ? raw.function : "";
  return { label, suggested };
}

function alreadyHave(label) {
  const folded = label.toLocaleLowerCase();
  return [...existingLabels(), ...state.words.map((item) => item.label)].some(
    (text) => String(text || "").toLocaleLowerCase() === folded
  );
}

function planned(label, suggested) {
  const topic = state.pageStyle === "topic";
  let fn = topic ? state.activeFn || inferPhraseFunction(label, suggested) : "";
  const slot = firstAvailableSlot(topic && state.autoTopicRows ? fn : "");
  if (topic && !fn && state.autoTopicRows) fn = functionForSlot(slot);
  // `source` is what makes a chip steerable: it is what the per-item controls
  // key off, and what a rejection is recorded from.
  return {
    label, message: null, fn, slot, symbol: true, symbolQuery: null, source: "ai",
  };
}

function pageRoom() {
  return pageCapacity();
}

/* Phrases arrive comma-prone; add them one by one instead of splitting. */
function absorb(words) {
  const room = pageRoom();
  let added = 0;
  words.forEach((raw) => {
    const { label, suggested } = asSuggestion(raw);
    if (label && !alreadyHave(label) && state.words.length < room) {
      state.words.push(planned(label, suggested));
      added += 1;
    }
  });
  return added;
}

/* ---------- the grounding source, named and refusable ---------- */

function clearGroundingSource() {
  const box = $("ai-grounding-source");
  if (!box) return;
  box.hidden = true;
  $("ai-grounding-note").textContent = "";
  $("ai-grounding-pick").innerHTML = "";
}

/* Say which Wikipedia article the suggestions were actually built on, and let
   the user say it is the wrong one. Taking the first search result silently is
   the one part of grounding a user cannot argue with: "Mercury" the planet and
   "Mercury" the element look identical in a page title. */
function renderGroundingSource(source) {
  const box = $("ai-grounding-source");
  const link = $("ai-grounding-link");
  const pick = $("ai-grounding-pick");
  if (!box) return;
  state.aiSource = source && source.used ? source : null;
  if (!state.aiSource) {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  link.textContent = source.title;
  link.href = source.url;
  pick.innerHTML = "";
  const keep = document.createElement("option");
  keep.value = "";
  keep.textContent = "Keep using this article";
  pick.append(keep);
  (source.alternatives || []).forEach((title) => {
    const option = document.createElement("option");
    option.value = title;
    option.textContent = `Use “${title}” instead`;
    pick.append(option);
  });
  const none = document.createElement("option");
  none.value = "none";
  none.textContent = "Don’t use an article at all";
  pick.append(none);
  pick.value = "";
}

if ($("ai-grounding-pick")) {
  $("ai-grounding-pick").addEventListener("change", () => {
    const choice = $("ai-grounding-pick").value;
    const note = $("ai-grounding-note");
    const rejected = state.aiSource ? state.aiSource.title : "";
    if (!choice) {
      note.textContent = "";
      return;
    }
    // Rejecting an article only arms the next request: suggestions already in
    // the chip box were composed against the old one, and silently throwing
    // away work the user may have edited is not what "wrong article" means.
    if (rejected && !state.aiExcluded.includes(rejected)) {
      state.aiExcluded.push(rejected);
    }
    if (choice === "none") {
      state.aiChosenArticle = "";
      $("ai-grounding").checked = false;
      void savePreference("ai_grounding", false);
      note.textContent =
        "Reference lookup turned off. Suggest again for suggestions with no article behind them.";
    } else {
      state.aiChosenArticle = choice;
      note.textContent = `Suggest again to use “${choice}” instead.`;
    }
  });
}

/* ---------- asking ---------- */

$("ai-go").addEventListener("click", async () => {
  const button = $("ai-go");
  const status = $("ai-status");
  const category = pageCategory();
  status.classList.remove("error", "success");
  if (!category) {
    status.classList.add("error");
    status.textContent = state.operation === "existing"
      ? "Choose an existing page first."
      : "Give the page a title first — it's used as the category.";
    return;
  }
  if (state.words.length >= pageRoom()) {
    status.classList.add("error");
    status.textContent = "The page is full — remove a planned button or choose another page first.";
    return;
  }
  const what = describeKind();
  setBusy(button, true, "Generating…");
  setActivity(`Generating ${what} for “${category}”…`);
  status.textContent = `Asking ${$("ai-model").value} for ${$("ai-count").value} “${category}” ${what}…`;
  try {
    const data = await askForSuggestions({
      count: Number($("ai-count").value) || 10,
    });
    const added = absorb(data.words);
    renderWords();
    status.classList.add("success");
    status.textContent = added
      ? `Added ${added} suggestions — open one to swap it, ask for more like it, or remove it.`
      : "No new suggestions fit. Try again or make room on the page.";
  } catch (error) {
    status.classList.add("error");
    status.textContent = `Suggestions couldn’t be generated. ${error.message}`;
  } finally {
    setActivity();
    setBusy(button, false);
  }
});

/* ---------- per-item controls ---------- */

/* Both live in the chip editor, on a chip this app suggested. They ask for a
   few candidates rather than exactly one, because the first answer is often
   something already on the page — and a control that silently does nothing is
   worse than one that takes a moment. */
const CANDIDATES = 6;

async function withItemBusy(button, work) {
  const status = $("edit-ai-status");
  const index = editingWordIndex();
  if (index === null) return;
  setBusy(button, true, "Asking…");
  status.textContent = "Asking the model…";
  try {
    await work(index);
  } catch (error) {
    status.textContent = `That didn’t work. ${error.message}`;
  } finally {
    setBusy(button, false);
  }
}

$("edit-ai-regenerate").addEventListener("click", () => {
  const button = $("edit-ai-regenerate");
  void withItemBusy(button, async (index) => {
    const current = state.words[index];
    // The word being replaced is itself a "not this" for this request, before
    // it becomes a remembered one below.
    const data = await askForSuggestions({
      count: CANDIDATES, alsoAvoid: [current.label],
    });
    if (state.words[index] !== current || editingWordIndex() !== index || !$("chip-editor").open) return;
    const replacement = data.words
      .map(asSuggestion)
      .find((candidate) => candidate.label && !alreadyHave(candidate.label));
    if (!replacement) {
      $("edit-ai-status").textContent =
        "Nothing new came back — try again, or change the page title.";
      return;
    }
    // The one it replaces counts as rejected: the user asked for something
    // else, which is the same "not this" as deleting it.
    pushUndoSnapshot();
    rememberRejection(current);
    state.words[index] = {
      ...planned(replacement.label, replacement.suggested),
      // Keep where it sits and which row it is on; only the word changes.
      slot: current.slot,
      fn: state.pageStyle === "topic" ? current.fn : "",
    };
    renderWords();
    $("chip-editor").close("cancel");
  });
});

$("edit-ai-more").addEventListener("click", () => {
  const button = $("edit-ai-more");
  void withItemBusy(button, async (index) => {
    const seed = state.words[index];
    const data = await askForSuggestions({
      count: CANDIDATES,
      like: [seed.message || seed.label],
    });
    if (state.words[index] !== seed || editingWordIndex() !== index || !$("chip-editor").open) return;
    pushUndoSnapshot();
    const added = absorb(data.words);
    renderWords();
    if (!added) {
      $("edit-ai-status").textContent = state.words.length >= pageRoom()
        ? "The page is full — remove a button to make room."
        : "Nothing new came back that isn’t already here.";
      return;
    }
    $("chip-editor").close("cancel");
    const status = $("ai-status");
    status.classList.remove("error");
    status.classList.add("success");
    status.textContent =
      `Added ${added} more like “${seed.label}”. Open ${$("ai-suggest").open ? "any" : "the suggestions panel for any"} of them to steer again.`;
  });
});

export { clearGroundingSource };
