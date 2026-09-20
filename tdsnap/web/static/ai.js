/* The optional AI suggestion panel.
 *
 * Two interchangeable engines sit behind one button: a model the user
 * downloads once, or an Ollama server they already run. Both are local. The
 * panel is entirely optional — the editor is complete without it, and nothing
 * here may become a step the user has to pass through.
 *
 * **One state at a time, and the server decides which.** The panel used to
 * compose its own sentence out of four booleans, which is how it came to say
 * "Ollama is connected, but no model is installed" while the request it would
 * have sent ran the built-in model instead. `/api/ai/status` now returns the
 * decision — a state, a sentence, and the single next thing the user can do
 * (see engines.py) — and everything below renders that.
 *
 * **Nothing lands on the page unasked.** Suggestions arrive in a tray, as
 * candidates. Keeping one puts it on the page; discarding it is remembered
 * and sent back as "not this". That is the difference between a tool that
 * offers ideas and one that edits somebody's communication system on a
 * guess — and it is also where a bad suggestion stops, which matters more
 * here than in most places a model is wrong.
 *
 * Suggestions are steerable, and every steer is a thing the user did rather
 * than a setting they had to find:
 *
 *   - discarding a suggestion is remembered and sent back as "not this"
 *     (see rememberRejection in chips.js);
 *   - a kept suggestion can be regenerated on its own, or used as the example
 *     for more of the same kind;
 *   - a sample of the page set's own button labels goes with the request, so
 *     suggestions read the way this page set already reads.
 *
 * **None of that leaves the computer.** The whole app makes exactly one
 * outbound request — the optional Wikipedia lookup — and it carries the page
 * title and nothing else. Discarded suggestions, kept ones, style samples,
 * and existing button labels are all vocabulary belonging to a person who did
 * not agree to publish it; they go to the model running locally and stop
 * there. The server keeps the two apart by construction (see the grounding
 * call in ai_words), and a test pins it.
 */

import { AI_GENERATION_TIMEOUT_MS, state } from "./state.js";
import { $, setBusy } from "./dom.js";
import { api } from "./api.js";
import {
  editingWordIndex, firstAvailableSlot, functionForSlot, pushUndoSnapshot,
  rememberRejection, renderWords,
} from "./chips.js";
import { setActivity } from "./dom.js";
import { titleOf } from "./parents.js";
import { inferPhraseFunction } from "./phrases.js";
import { savePreference } from "./settings.js";
import { styleSample } from "./vocabulary.js";
import { FUNCTIONS } from "./state.js";

/* ---------- readiness ---------- */

/* The last `ai` block from /api/ai/status: {ready, engine, state, summary,
   detail, action, note, can_download}. Null until the first check answers. */
let readiness = null;
let checking = false;

const STAGES = {
  ready: "ai-stage-ready",
  setup: "ai-stage-setup",
  downloading: "ai-stage-downloading",
  unavailable: "ai-stage-blocked",
};

const PILLS = {
  checking: "Checking…",
  ready: "Ready",
  setup: "Setup needed",
  downloading: "Setting up…",
  unavailable: "Not available",
};

function statusQuery() {
  const parameters = new URLSearchParams({
    host: $("ai-host").value,
    model: $("ai-model").value,
    engine: $("ai-engine").value || "auto",
  });
  const key = $("ai-model-choice").value || $("ai-model-choice").dataset.preferred;
  if (key) parameters.set("model_key", key);
  return parameters.toString();
}

/* Ask the server where things stand and render the answer.

   Runs once on load rather than when the panel is opened: "is this ready?" is
   the first thing somebody wants to know about a feature they have never used,
   and a panel that only finds out after you open it cannot tell you. */
async function checkAi() {
  if (checking) return;
  checking = true;
  try {
    const data = await api(`/api/ai/status?${statusQuery()}`);
    readiness = data.ai || null;
    renderLocalModel(data.local || {});
    renderOllamaModels(data.ollama || {});
    renderState();
    if ((data.local?.download || {}).status === "downloading") trackDownload();
  } catch {
    readiness = null;
    renderState("Couldn’t check whether suggestions are ready. The app may have " +
      "stopped responding — reload it, then try again.");
  } finally {
    checking = false;
  }
}

/* Paint whichever single state the server reported. Everything not in that
   state is hidden rather than disabled: a control that cannot do anything yet
   is one more thing to wonder about. */
function renderState(failure = "") {
  const panel = $("ai-panel");
  const stateName = failure ? "unavailable" : readiness ? readiness.state : "checking";
  panel.dataset.aiState = stateName;
  $("ai-state-pill").textContent = PILLS[stateName] || PILLS.checking;
  $("ai-summary").textContent = failure
    || (readiness ? readiness.summary : "Checking whether suggestions are ready…");
  $("ai-detail").textContent = failure ? "" : readiness ? readiness.detail : "";
  Object.entries(STAGES).forEach(([name, id]) => {
    $(id).hidden = name !== stateName;
  });
  $("ai-go").disabled = !(readiness && readiness.ready);
  renderTray();
}

/* Which built-in model to download and run.
 *
 * Only shown when this build actually offers a choice, and an option the
 * machine cannot run is offered as a disabled row with the measured reason
 * beside it rather than silently missing — "why can't I pick that one?" is a
 * fair question, and the answer is a fact about the computer. */
function renderLocalModel(local) {
  const model = local.model || {};
  $("ai-model-name").textContent = model.name || "";
  $("ai-model-size").textContent = model.size || "";
  $("ai-model-license").textContent = model.license || "";
  const row = $("ai-model-choice-row");
  const select = $("ai-model-choice");
  const offered = local.choices || [];
  row.hidden = offered.length < 2;
  if (row.hidden) {
    select.innerHTML = "";
    $("ai-model-choice-note").textContent = "";
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

/* Offer the models Ollama actually has, instead of asking somebody to type a
   name from memory. Still a text box, so an unlisted model can be named. */
function renderOllamaModels(ollamaState) {
  const installed = ollamaState.models || [];
  const list = $("ai-model-options");
  list.innerHTML = "";
  installed.forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    list.append(option);
  });
  const input = $("ai-model");
  const known = installed.some(
    (name) => name === input.value || name.split(":")[0] === input.value
  );
  // Point the model box at a model that's actually installed, unless the user
  // typed one themselves — otherwise the default "llama3.2" fails on servers
  // that only have other models.
  if (installed.length && !known && !input.dataset.userEdited) {
    input.value = installed[0];
  }
  $("ai-model-hint").textContent = installed.length
    ? `Installed in Ollama: ${installed.slice(0, 6).join(", ")}.`
    : "Models you have installed appear in this list.";
}

/* ---------- setup ---------- */

$("ai-download-btn").addEventListener("click", async () => {
  const button = $("ai-download-btn");
  const status = $("ai-download-status");
  status.classList.remove("error", "success");
  status.textContent = "";
  setBusy(button, true, "Starting…");
  setActivity("Starting the one-time setup…");
  try {
    await api("/api/ai/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_key: $("ai-model-choice").value || null }),
    });
    readiness = { ...(readiness || {}), state: "downloading", ready: false,
      summary: "Setting up suggestions…",
      detail: "You can keep adding words while this finishes." };
    renderState();
    trackDownload();
  } catch (error) {
    status.classList.add("error");
    status.textContent = `Setup couldn’t start. ${error.message}`;
  } finally {
    setBusy(button, false);
    setActivity();
  }
});

/* Both routes into the Ollama steps: the one offered beside the download for
   somebody who already runs it, and the one offered when it is the only
   route this installation has. */
function openOllamaSteps() {
  $("ai-options").open = true;
  $("ai-advanced").open = true;
  $("ai-host").focus();
}

$("ai-ollama-btn").addEventListener("click", openOllamaSteps);
$("ai-ollama-btn-alt").addEventListener("click", openOllamaSteps);

let downloadTimer = null;

/* Poll the download until it settles.

   Survives leaving the panel and reloading the app: checkAi restarts this
   whenever the server says a download is still running, so a setup started
   before a refresh keeps reporting itself instead of looking abandoned. */
function trackDownload() {
  if (downloadTimer) return; // a poll is already running
  const bar = $("ai-progress");
  const fill = $("ai-progress-fill");
  const text = $("ai-progress-text");
  text.textContent = "Starting…";

  downloadTimer = setInterval(async () => {
    try {
      const data = await api("/api/ai/download");
      const download = data.download;
      if (download.status === "downloading") {
        if (download.total > 0) {
          const percent = Math.round((download.done / download.total) * 100);
          fill.style.width = `${percent}%`;
          bar.setAttribute("aria-valuenow", percent);
          text.textContent =
            `${percent}% — ${(download.done / 1e9).toFixed(2)} of ` +
            `${(download.total / 1e9).toFixed(2)} GB. Keep working; ` +
            "AAC Editor will say when suggestions are ready.";
        } else {
          text.textContent = `Downloaded ${(download.done / 1e9).toFixed(2)} GB so far…`;
        }
        return;
      }
      clearInterval(downloadTimer);
      downloadTimer = null;
      if (download.status === "ready") {
        fill.style.width = "100%";
        const status = $("ai-status");
        status.classList.remove("error");
        status.classList.add("success");
        status.textContent = "Suggestions are ready. They run on this computer, offline.";
        checkAi();
      } else if (download.status === "error") {
        const status = $("ai-download-status");
        status.classList.remove("success");
        status.classList.add("error");
        status.textContent = `Setup didn’t finish: ${download.error} Select ` +
          "Set up suggestions to try again — nothing else is affected.";
        readiness = { ...(readiness || {}), state: "setup", ready: false };
        renderState();
      }
    } catch {
      /* transient poll failure; keep trying */
    }
  }, 1000);
}

/* ---------- settings ---------- */

async function checkAiWithFeedback(button) {
  $("ai-summary").textContent = "Checking…";
  setActivity("Checking your AI connection…");
  if (button) setBusy(button, true, "Checking…");
  try {
    await checkAi();
  } finally {
    if (button) setBusy(button, false);
    setActivity();
  }
}

$("ai-model-choice").addEventListener("change", () => {
  $("ai-model-choice").dataset.preferred = $("ai-model-choice").value;
  void savePreference("ai_model", $("ai-model-choice").value);
  checkAi();
});

$("ai-engine").addEventListener("change", () => {
  void savePreference("ai_engine", $("ai-engine").value);
  checkAi();
});

$("ai-style").addEventListener("change", () => {
  void savePreference("ai_style", $("ai-style").checked);
});

$("ai-host").addEventListener("change", () => {
  void savePreference("ollama_host", $("ai-host").value);
  checkAiWithFeedback($("ai-check-btn"));
});
$("ai-check-btn").addEventListener("click", () => checkAiWithFeedback($("ai-check-btn")));
$("ai-recheck-btn").addEventListener("click", () => checkAiWithFeedback($("ai-recheck-btn")));
$("ai-model").addEventListener("input", () => {
  $("ai-model").dataset.userEdited = "1";
});
$("ai-model").addEventListener("change", () => {
  void savePreference("ollama_model", $("ai-model").value);
});
$("ai-grounding").addEventListener("change", () => {
  void savePreference("ai_grounding", $("ai-grounding").checked);
});

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

/* One request shape for all the ways of asking: the whole panel, more for the
   tray, one item regenerated, and "more like this". Only `count`, `like`, and
   `already` differ. */
async function askForSuggestions({ count, like = [], alsoAvoid = [] }) {
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
        engine: $("ai-engine").value || "auto",
        kind: topic ? "phrases" : "words",
        function: topic && state.activeFn ? state.activeFn : null,
        grounding: $("ai-grounding").checked,
        grounding_title: state.aiChosenArticle || null,
        grounding_exclude: state.aiExcluded,
        existing: knownLabels(),
        avoid: [...new Set([...state.aiRejected, ...alsoAvoid])],
        // Candidates already waiting in the tray. Not rejected and not on the
        // page — only used up, which is a different thing to tell a model.
        already: state.aiSuggestions.map((item) => item.label).slice(-60),
        like,
        style: styleContext(),
      }),
    },
    AI_GENERATION_TIMEOUT_MS
  );
  renderGroundingSource(data.grounding);
  return data;
}

/* A suggestion in whatever shape the engine returned it. Words come back as
   strings and phrases as {label, function}. */
function asSuggestion(raw) {
  const label = (typeof raw === "string" ? raw : String(raw?.label || "")).trim();
  const suggested = typeof raw === "object" && raw && FUNCTIONS[raw.function]
    ? raw.function : "";
  return { label, suggested };
}

function alreadyHave(label) {
  const folded = label.toLocaleLowerCase();
  return [...state.existingButtons, ...state.words].some(
    (item) => String(item.label || "").toLocaleLowerCase() === folded
  );
}

function inTray(label) {
  const folded = label.toLocaleLowerCase();
  return state.aiSuggestions.some(
    (item) => item.label.toLocaleLowerCase() === folded
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
  return state.availableSlots
    ? state.availableSlots.length
    : state.grid.cols * state.grid.rows - state.existingButtons.length;
}

function roomLeft() {
  return Math.max(0, pageRoom() - state.words.length);
}

/* ---------- the suggestion tray ---------- */

/* Take what came back and offer it, dropping anything the user would only
   have to reject again: already on the page, already planned, already here. */
function offer(words) {
  let offered = 0;
  let duplicates = 0;
  words.forEach((raw) => {
    const { label, suggested } = asSuggestion(raw);
    if (!label) return;
    if (alreadyHave(label) || inTray(label)) {
      duplicates += 1;
      return;
    }
    state.aiSuggestions.push({ label, suggested });
    offered += 1;
  });
  renderTray();
  return { offered, duplicates };
}

function trayFunction(item) {
  if (state.pageStyle !== "topic") return "";
  return state.activeFn || inferPhraseFunction(item.label, item.suggested);
}

function renderTray() {
  const tray = $("ai-tray");
  const list = $("ai-tray-list");
  // A candidate that has since been typed, imported, or kept from a template
  // is not a candidate any more.
  state.aiSuggestions = state.aiSuggestions.filter((item) => !alreadyHave(item.label));
  const items = state.aiSuggestions;
  list.innerHTML = "";
  tray.hidden = !items.length;
  if (!items.length) return;
  const room = roomLeft();
  items.forEach((item, index) => {
    const chip = document.createElement("span");
    chip.className = "chip suggestion";
    const fn = trayFunction(item);
    if (fn) {
      chip.dataset.fn = fn;
      chip.style.setProperty("--fn-color", FUNCTIONS[fn].color);
    }
    const keep = document.createElement("button");
    keep.type = "button";
    keep.className = "chip-body";
    keep.setAttribute(
      "aria-label",
      `Keep ${item.label}${fn ? `, ${FUNCTIONS[fn].name}` : ""}`
    );
    keep.title = room ? "Add this to the page" : "The page is full";
    keep.disabled = room <= 0;
    if (fn) {
      const dot = document.createElement("span");
      dot.className = "chip-dot";
      keep.append(dot);
    }
    // A plus, because a chip that looks exactly like the ones above it reads
    // as something already added rather than something on offer.
    const mark = document.createElement("span");
    mark.className = "suggestion-mark";
    mark.setAttribute("aria-hidden", "true");
    mark.textContent = "+";
    const label = document.createElement("span");
    label.textContent = item.label;
    keep.append(mark, label);
    keep.addEventListener("click", () => keepSuggestion(index));

    const drop = document.createElement("button");
    drop.type = "button";
    drop.setAttribute("aria-label", `Discard ${item.label}`);
    drop.textContent = "×";
    drop.addEventListener("click", () => discardSuggestion(index));
    chip.append(keep, drop);
    list.append(chip);
  });
  $("ai-tray-note").textContent = room
    ? "Select one to add it to the page. × discards it, and it won’t be offered again."
    : "The page is full. Remove a planned button to make room for these.";
  $("ai-tray-keep-all").disabled = room <= 0;
}

function keepSuggestion(index) {
  const item = state.aiSuggestions[index];
  if (!item || roomLeft() <= 0) return;
  // The tray is not redrawn by everything that can add a word, so a candidate
  // the user has since typed themselves is caught here rather than only when
  // the tray happens to render.
  const duplicate = alreadyHave(item.label);
  if (!duplicate) {
    pushUndoSnapshot();
    state.words.push(planned(item.label, item.suggested));
  }
  state.aiSuggestions.splice(index, 1);
  renderWords();
  renderTray();
  if (duplicate) {
    const status = $("ai-status");
    status.classList.remove("error", "success");
    status.textContent = `“${item.label}” is already here, so it wasn’t added again.`;
  }
}

/* Discarding is the clearest "not that" the user ever gives, so it rides on
   every later request rather than being offered again next round. */
function discardSuggestion(index) {
  const item = state.aiSuggestions[index];
  if (!item) return;
  rememberRejection({ label: item.label, source: "ai" });
  state.aiSuggestions.splice(index, 1);
  renderTray();
}

$("ai-tray-keep-all").addEventListener("click", () => {
  const status = $("ai-status");
  status.classList.remove("error", "success");
  pushUndoSnapshot();
  let kept = 0;
  const waiting = [];
  state.aiSuggestions.forEach((item) => {
    if (alreadyHave(item.label)) return;
    if (roomLeft() <= 0) {
      waiting.push(item);
      return;
    }
    state.words.push(planned(item.label, item.suggested));
    kept += 1;
  });
  state.aiSuggestions = waiting;
  renderWords();
  renderTray();
  status.classList.add("success");
  status.textContent = waiting.length
    ? `Kept ${kept}. The page filled up, so ${waiting.length} are still waiting.`
    : `Kept ${kept} suggestion${kept === 1 ? "" : "s"}. ` +
      "Open any of them to change the wording, or swap it for another.";
});

$("ai-tray-clear").addEventListener("click", () => {
  const discarded = state.aiSuggestions.length;
  state.aiSuggestions.forEach(
    (item) => rememberRejection({ label: item.label, source: "ai" })
  );
  state.aiSuggestions = [];
  renderTray();
  const status = $("ai-status");
  status.classList.remove("error", "success");
  status.textContent =
    `Discarded ${discarded}. The next round won’t offer them again.`;
});

/* Everything the tray forgets when the page being edited changes: candidates
   composed for one page are not candidates for another. */
function clearSuggestions() {
  state.aiSuggestions = [];
  renderTray();
}

/* The four controls that decide what `pageCategory()` answers. Listened to
   directly rather than called from the modules that own them, because those
   modules are upstream of this one and the import would close a cycle. */
["parent-select", "title-input", "operation-existing", "operation-new"].forEach((id) => {
  const control = $(id);
  if (!control) return;
  const event = control.tagName === "BUTTON" ? "click" : "change";
  control.addEventListener(event, () => {
    if (state.aiSuggestions.length) clearSuggestions();
  });
});

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
    // the tray were composed against the old one, and silently throwing away
    // work the user may have kept is not what "wrong article" means.
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

/* What to say about a round that came back thin, in the user's terms rather
   than the model's: how many are on offer, and what to do about the rest. */
function reportRound({ offered, duplicates }, data) {
  const status = $("ai-status");
  status.classList.remove("error", "success");
  const shortfall = data.requested - data.returned;
  const parts = [];
  if (offered) {
    status.classList.add("success");
    parts.push(
      `${offered} suggestion${offered === 1 ? "" : "s"} ready below. ` +
      "Nothing is on your page yet."
    );
    if (duplicates) {
      parts.push(
        `${duplicates} more repeated something already here and ${duplicates === 1 ? "was" : "were"} left out.`
      );
    } else if (shortfall > 0) {
      parts.push(`The model had ${data.returned} good ones this time; select Suggest more for another round.`);
    }
  } else {
    parts.push(
      duplicates
        ? "Everything that came back is already on this page. Select Suggest more for a different round."
        : "Nothing usable came back. Try a more specific page name, or select Suggest more to ask again."
    );
  }
  if (data.note) parts.push(data.note);
  status.textContent = parts.join(" ");
}

async function runSuggestion(button, busyLabel) {
  const status = $("ai-status");
  const category = pageCategory();
  status.classList.remove("error", "success");
  if (!category) {
    status.classList.add("error");
    status.textContent = state.operation === "existing"
      ? "Choose an existing page first."
      : "Give the page a title first — it’s used as the topic.";
    return;
  }
  const what = describeKind();
  setBusy(button, true, busyLabel);
  setActivity(`Thinking of ${what} for “${category}”…`);
  status.textContent = `Thinking of ${what} for “${category}”. This can take a moment on a laptop.`;
  try {
    const data = await askForSuggestions({
      count: Math.max(1, Math.min(40, Number($("ai-count").value) || 10)),
    });
    reportRound(offer(data.words), data);
  } catch (error) {
    status.classList.add("error");
    status.textContent = `Suggestions couldn’t be generated. ${error.message}`;
    // A failure is also the moment the panel's idea of "ready" may be stale —
    // Ollama stopped, the model file went missing — so find out rather than
    // leaving an enabled button that cannot work.
    void checkAi();
  } finally {
    setActivity();
    setBusy(button, false);
  }
}

$("ai-go").addEventListener("click", () => runSuggestion($("ai-go"), "Thinking…"));
$("ai-tray-more").addEventListener("click", () =>
  runSuggestion($("ai-tray-more"), "Thinking…")
);

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
    const result = offer(data.words);
    if (!result.offered) {
      $("edit-ai-status").textContent =
        "Nothing new came back that isn’t already here.";
      return;
    }
    $("chip-editor").close("cancel");
    const status = $("ai-status");
    status.classList.remove("error");
    status.classList.add("success");
    status.textContent =
      `${result.offered} more like “${seed.label}” — keep the ones you want.`;
  });
});

/* One check on start-up rather than one when the panel is opened: somebody
   who has never used this should find out that it needs a one-time setup
   while they are still typing words, not at the moment they want ideas. */
void checkAi();

export { clearGroundingSource, clearSuggestions, renderTray };
