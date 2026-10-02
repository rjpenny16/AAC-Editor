/* Draft autosave and recovery.
 *
 * The in-progress item list is the one thing this app holds that nothing
 * else has a copy of until an edit lands (see support.js's hasUnsavedWork).
 * It is also somebody's own vocabulary, so it is kept on disk only when the
 * person has turned on "Keep an unfinished page" under What AAC Editor saves.
 * With that off, which is how every install starts, nothing here is ever
 * written: the list lives in the page and nowhere else.
 *
 * With it on, the composition is autosaved to the settings file and offered
 * back on the next launch ("resume or discard") so a crash, a killed tab, or an
 * accidental reload doesn't have to mean starting over.
 *
 * A draft that an older version saved before this was a choice is still offered
 * once, never silently dropped and never silently kept: answering the offer
 * deletes it unless the option is on.
 *
 * Saving is polled (mirrors the live TD Snap poll in connect.js) rather than
 * hooked into every place a chip can change, and it never writes over a
 * stored draft until either the recovery banner is answered or the user has
 * visibly moved on by composing something new of their own.
 */

import { state } from "./state.js";
import { $ } from "./dom.js";
import { titleOf } from "./parents.js";
import {
  clearDraft as clearStoredDraft, draftAutosaveOn, getDraft, saveDraft, savePreference,
} from "./settings.js";
import { applyPendingDraftResume } from "./wizard.js";

const AUTOSAVE_INTERVAL_MS = 2000;
const BUILD_STEPS = new Set(["items", "layout", "placement", "review", "destination", "title", "operation"]);

let pendingResume = null; // a draft the user chose to resume; applied once "items" shows
let recoveryResolved = false; // true once the banner is answered, or the user composed anyway
let lastSignature = "";
let enabled = false; // the person's choice to keep an unfinished page; off until they say so

function draftTargetLabel(draft) {
  if (draft.operation === "existing" && draft.target_page) return draft.target_page;
  if (draft.title) return draft.title;
  return "a page";
}

function currentComposition() {
  if (!state.words.length || state.applied || !BUILD_STEPS.has(state.wizardStep)) return null;
  const titleInput = $("title-input");
  return {
    provider: state.provider,
    operation: state.operation,
    page_style: state.pageStyle,
    active_fn: state.activeFn || "",
    target_page: state.operation === "existing" ? titleOf(state.parentId) : "",
    title: state.operation === "new" && titleInput ? titleInput.value.trim() : "",
    // `source` is deliberately not carried. It marks a suggestion this session
    // made, and the steering it enables — regenerate, more like this — only
    // means anything alongside the rejections and the page-set context that a
    // relaunch has already lost. A resumed draft is vocabulary, the same as a
    // template is.
    items: state.words.map((item) => ({
      label: item.label,
      message: item.message,
      fn: item.fn || "",
      slot: Number.isInteger(item.slot) ? item.slot : null,
      symbol: item.symbol !== false,
      symbol_query: item.symbolQuery || null,
    })),
  };
}

async function autosaveTick() {
  if (document.hidden || !enabled) return;
  const draft = currentComposition();
  if (!recoveryResolved) {
    // Still waiting on the banner: don't overwrite the offered draft with
    // nothing, but a user who started composing anyway has answered it in
    // effect — don't hold their new work hostage to an unclicked button.
    if (!draft) return;
    recoveryResolved = true;
    $("draft-banner").hidden = true;
  }
  const signature = draft ? JSON.stringify(draft) : "";
  if (signature === lastSignature) return;
  if (await saveDraft(draft)) lastSignature = signature;
}

function startAutosave() {
  window.setInterval(autosaveTick, AUTOSAVE_INTERVAL_MS);
}

async function clearDraft() {
  lastSignature = "";
  await clearStoredDraft();
}

/* The checkbox in What AAC Editor saves. Turning it off stops the writing first
   and then deletes whatever was kept; turning it on only counts once it has been
   recorded, so the page never believes it may keep a draft that the saved
   settings do not say it may. */
async function setDraftAutosave(on) {
  const wanted = Boolean(on);
  lastSignature = "";
  if (!wanted) enabled = false;
  const saved = await savePreference("draft_autosave", wanted);
  if (wanted && saved) enabled = true;
  if (!wanted) await clearDraft();
  return saved;
}

/* After Clear all saved data the preference is gone with the rest, so the page
   reads it again rather than going on believing what it knew before. */
async function syncDraftAutosave() {
  enabled = await draftAutosaveOn();
  lastSignature = "";
}

/* Answering the recovery offer settles a draft that exists only because an older
   version kept it by default. Unless the person has asked for drafts to be kept,
   it goes now: its buttons are already back in the page if they chose Resume. */
async function settleOfferedDraft() {
  if (!enabled) await clearDraft();
}

/* Consumed once, by wizard.js's show(), the moment the items step is
   actually on screen — see the comment there for why that's the one place
   robust to every provider's different path back to "items". */
function takePendingResume() {
  const draft = pendingResume;
  pendingResume = null;
  return draft;
}

async function initDraftRecovery() {
  enabled = await draftAutosaveOn();
  const draft = await getDraft();
  if (draft && Array.isArray(draft.items) && draft.items.length) {
    const banner = $("draft-banner");
    $("draft-banner-text").textContent =
      `You have an unfinished page for “${draftTargetLabel(draft)}” — resume or discard it?`;
    banner.hidden = false;
    banner.focus({ preventScroll: true });

    $("draft-resume-btn").addEventListener(
      "click",
      () => {
        pendingResume = draft;
        banner.hidden = true;
        recoveryResolved = true;
        void settleOfferedDraft();
        // Already on the items step (connected before answering the banner):
        // show() won't run again to pick it up, so land it now.
        if (state.wizardStep === "items") {
          applyPendingDraftResume();
          return;
        }
        // Otherwise the words wait for somewhere to land. Say so, or the
        // button looks as though it did nothing.
        const count = draft.items.length;
        const words = `${count} word${count === 1 ? "" : "s"}`;
        const status = $(state.wizardStep === "connect" ? "live-status" : "chip-note");
        status.classList.remove("error");
        status.textContent = state.wizardStep === "connect"
          ? `Your ${words} will be put back as soon as you connect.`
          : `Your ${words} will be put back when you reach the words step.`;
      },
      { once: true },
    );
    $("draft-discard-btn").addEventListener(
      "click",
      async () => {
        banner.hidden = true;
        recoveryResolved = true;
        await clearDraft();
      },
      { once: true },
    );
  } else {
    recoveryResolved = true;
  }
  startAutosave();
}

initDraftRecovery();

export { clearDraft, setDraftAutosave, syncDraftAutosave, takePendingResume };
