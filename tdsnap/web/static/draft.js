/* Draft autosave and recovery.
 *
 * The in-progress item list is the one thing this app holds that nothing
 * else has a copy of until an edit lands (see support.js's hasUnsavedWork).
 * This module autosaves that composition to the opt-in settings file and
 * offers it back on the next launch — "resume or discard" — so a crash, a
 * killed tab, or an accidental reload doesn't have to mean starting over.
 *
 * Saving is polled (mirrors the live TD Snap poll in connect.js) rather than
 * hooked into every place a chip can change, and it never writes over a
 * stored draft until either the recovery banner is answered or the user has
 * visibly moved on by composing something new of their own.
 */

import { state } from "./state.js";
import { $ } from "./dom.js";
import { titleOf } from "./parents.js";
import { clearDraft as clearStoredDraft, getDraft, saveDraft } from "./settings.js";

const AUTOSAVE_INTERVAL_MS = 2000;
const BUILD_STEPS = new Set(["items", "layout", "placement"]);

let pendingResume = null; // a draft the user chose to resume; applied once "items" shows
let recoveryResolved = false; // true once the banner is answered, or the user composed anyway
let lastSignature = "";

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
  if (document.hidden) return;
  const draft = currentComposition();
  if (!recoveryResolved) {
    // Still waiting on the banner: don't overwrite the offered draft with
    // nothing, but a user who started composing anyway has answered it in
    // effect — don't hold their new work hostage to an unclicked button.
    if (!draft) return;
    recoveryResolved = true;
  }
  const signature = draft ? JSON.stringify(draft) : "";
  if (signature === lastSignature) return;
  lastSignature = signature;
  await saveDraft(draft);
}

function startAutosave() {
  window.setInterval(autosaveTick, AUTOSAVE_INTERVAL_MS);
}

async function clearDraft() {
  lastSignature = "";
  await clearStoredDraft();
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

export { clearDraft, takePendingResume };
