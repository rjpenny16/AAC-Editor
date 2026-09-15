/* Where else in this page set does a word already exist?
 *
 * Duplicate checking has only ever looked at the page being edited. That
 * catches "apple is already on Snacks" and misses the one that matters more —
 * "apple is already on Food" — so a clinician builds a second button for a
 * concept that already had one, in a different place, possibly saying
 * something slightly different. On a device that is two ways to say the same
 * thing, and it is the user who has to reconcile them.
 *
 * This is advisory and stays advisory. It never removes a word, never disables
 * a control, and never blocks a confirm. The page being edited is still the
 * only thing that can refuse a duplicate, because that is the one that would
 * actually collide. Everything here is a sentence the user can act on or
 * ignore — sometimes the same word on two pages is exactly what was wanted.
 *
 * The whole index is fetched once per connection and answered in the browser,
 * so this costs nothing per keystroke and nothing at all when the page set
 * cannot be read.
 */

import { state } from "./state.js";
import { api } from "./api.js";

/* Casefolded label -> page titles carrying it, or null when unavailable. */
let index = null;
/* Labels as the page set actually spells them, for style matching. The index
   above casefolds, because "chips" and "Chips" are the same concept; style is
   the opposite question — how does this page set word a button? — so the
   server sends these separately rather than reusing the index keys. */
let samples = [];

function forget() {
  index = null;
  samples = [];
}

/* Fetch the index for whichever provider is connected. Never throws: this is
   an advisory, and a failure to load one must not disturb a working session. */
async function loadVocabulary() {
  index = null;
  try {
    const path = state.mode === "file"
      ? `/api/pageset/${encodeURIComponent(state.sessionId)}/vocabulary`
      : "/api/tdsnap/vocabulary";
    if (state.provider === "grid3") return;
    const data = await api(path);
    if (data && data.available && data.labels) index = data.labels;
    if (data && Array.isArray(data.samples)) samples = data.samples;
  } catch {
    // Unavailable is the normal outcome for a page set AAC Editor cannot
    // identify; the UI simply says nothing about other pages.
  }
}

/* The pages carrying *label*, excluding the one being edited — that one is
   already handled by the blocking per-page check, and naming it twice would
   read as two different problems. */
function pagesWith(label, exclude = "") {
  if (!index) return [];
  const folded = String(label || "").trim().toLocaleLowerCase();
  const skip = String(exclude || "").trim().toLocaleLowerCase();
  return (index[folded] || []).filter((page) => page.toLocaleLowerCase() !== skip);
}

/* One advisory line for a batch of labels, or "" when there is nothing worth
   saying. Named rather than counted, and capped so pasting a long list cannot
   turn the note into a wall of text. */
function elsewhereNote(labels, exclude = "", limit = 5) {
  const found = [];
  labels.forEach((label) => {
    const pages = pagesWith(label, exclude);
    if (pages.length) found.push({ label, pages });
  });
  if (!found.length) return "";
  const named = found.slice(0, limit).map(
    (entry) => `“${entry.label}” on ${entry.pages.slice(0, 3).join(", ")}`,
  );
  const rest = found.length - named.length;
  const tail = rest ? `, and ${rest} more` : "";
  return `Already elsewhere in this page set: ${named.join("; ")}${tail}. ` +
    "That may be exactly what you want — nothing is skipped.";
}

function isLoaded() {
  return index !== null;
}

/* A bounded sample of real labels for the AI panel to match against. Empty
   whenever the page set could not be read, which is the same thing as having
   no style to match — the caller simply asks for suggestions without it. */
function styleSample(limit = 24) {
  return samples.slice(0, Math.max(0, limit));
}

export {
  elsewhereNote, forget, isLoaded, loadVocabulary, pagesWith, styleSample,
};
