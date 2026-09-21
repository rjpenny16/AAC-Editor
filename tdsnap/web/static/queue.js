/* Multi-page batch: queue several pages, review them as one list, apply once.
 *
 * A caseload session is rarely one page. What makes queueing safe is that a
 * batch is not a second write path: each queued page was already frozen by the
 * ordinary review step, and the server applies them by calling the same
 * single-page write path once per page — same fingerprint guard, same
 * edit-mode session, same rollback. Nothing here reaches past one page.
 *
 * What the batch adds is sequencing and an honest account of it. Every queued
 * page comes back with what actually happened to it, including the ones never
 * attempted, because a run that stops after page two must not read as though
 * pages three and four were fine.
 *
 * Two limits are stated up front rather than discovered:
 *   - Undo is single-level, so it reaches the last page applied and no further.
 *   - A page can be queued once. A second entry's fingerprint was captured
 *     before the first one landed, so it is stale by construction.
 *
 * The queue deliberately does *not* join the draft autosave, unlike the chip
 * box. Every entry holds the fingerprint of a live TD Snap page as it was when
 * that page was reviewed; restoring a queue on the next launch would restore
 * fingerprints that no longer match, so each page would be refused on sight.
 * Offering work back that cannot be applied is worse than not offering it, so
 * the queue is guarded against loss instead — see hasUnsavedWork in support.js
 * and the quit warning in app.js.
 */

import { state } from "./state.js";
import { $, appendNamedList } from "./dom.js";
import { countEdits, editSummary, emptyEdits } from "./edits.js";
import { clearUndoHistory, renderWords } from "./chips.js";
import { titleOf } from "./parents.js";
import { show } from "./wizard.js";

/* The server refuses more than this too; the browser says so first, while the
   user still has the page in front of them. */
const MAX_QUEUED_PAGES = 10;

/* Batching is TD Snap live editing an existing page. An exported file writes
   to one session copy and needs no queue; Grid 3's write path has no batch
   endpoint behind it. Offering the button anywhere else would promise
   something that does not exist. */
function batchable() {
  return state.mode === "live"
    && state.provider === "tdsnap"
    && state.operation === "existing";
}

function queuedPages() {
  return state.queue.map((entry) => entry.page.toLocaleLowerCase());
}

function alreadyQueued(page) {
  return queuedPages().includes(String(page || "").toLocaleLowerCase());
}

/* ---------- queueing ---------- */

/* Why this page cannot join the queue, or "" when it can. Checked before the
   button is offered rather than after it is pressed — a reason the user can
   read while the page is still in front of them beats an error afterwards. */
function blockedReason() {
  const pending = state.pendingEdit;
  if (!pending) return "";
  if (state.queue.length >= MAX_QUEUED_PAGES) {
    return `${MAX_QUEUED_PAGES} pages are already queued, which is the most that `
      + "can be applied in one go. Apply these first.";
  }
  if (alreadyQueued(pending.parentTitle)) {
    return `“${pending.parentTitle}” is already in the queue. A page can be queued `
      + "once, because a second edit to it would be reviewed against the page as "
      + "it is now rather than as the first edit will leave it.";
  }
  return "";
}

/* Takes the *frozen* payload the review step already built, so a queued page
   is reviewed material and never a re-derivation of live state. */
function queueCurrentPage() {
  const pending = state.pendingEdit;
  if (!pending || pending.kind === "undo" || pending.kind === "batch") return null;
  if (blockedReason()) return null;
  const { payload } = pending;
  state.queue.push({
    page: pending.parentTitle,
    summary: editSummary({
      added: payload.items.length,
      changed: payload.changes.length,
      removed: payload.removals.length,
      moved: payload.moves.length,
      page: pending.parentTitle,
    }),
    labels: payload.items.map((item) => item.label),
    counts: {
      added: payload.items.length,
      changed: payload.changes.length,
      removed: payload.removals.length,
      moved: payload.moves.length,
    },
    entry: {
      page: pending.parentTitle,
      items: payload.items,
      changes: payload.changes,
      removals: payload.removals,
      moves: payload.moves,
      fingerprint: payload.fingerprint,
    },
  });
  return pending.parentTitle;
}

function clearQueue() {
  state.queue = [];
  renderQueue();
}

function removeFromQueue(page) {
  const folded = String(page || "").toLocaleLowerCase();
  state.queue = state.queue.filter(
    (entry) => entry.page.toLocaleLowerCase() !== folded,
  );
  renderQueue();
}

/* ---------- the banner on the items step ---------- */

function renderQueue() {
  const banner = $("queue-banner");
  const list = $("queue-list");
  if (!banner) return;
  banner.hidden = state.queue.length === 0;
  list.innerHTML = "";
  state.queue.forEach((queued) => {
    const row = document.createElement("li");
    const name = document.createElement("strong");
    name.textContent = queued.page;
    const detail = document.createElement("span");
    detail.textContent = queued.summary;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "btn btn-ghost btn-compact";
    remove.textContent = "Remove";
    remove.setAttribute("aria-label", `Remove ${queued.page} from the queue`);
    remove.addEventListener("click", () => removeFromQueue(queued.page));
    row.append(name, detail, remove);
    list.append(row);
  });
  $("queue-review-btn").textContent =
    `Review and apply ${state.queue.length} page${state.queue.length === 1 ? "" : "s"}`;
}

/* ---------- the batch review ---------- */

/* Populates the ordinary review screen rather than a second one, so a batch
   goes through the same freeze, the same confirm, and the same error handling
   as a single page. Returns the note the caller renders about work that is
   composed but not queued — naming it is the point, since applying the batch
   will not write it. */
function prepareBatchReview() {
  const entries = state.queue.map((queued) => queued.entry);
  const pages = state.queue.length;
  const totals = state.queue.reduce((sum, queued) => ({
    added: sum.added + queued.counts.added,
    changed: sum.changed + queued.counts.changed,
    removed: sum.removed + queued.counts.removed,
    moved: sum.moved + queued.counts.moved,
  }), { added: 0, changed: 0, removed: 0, moved: 0 });

  state.pendingEdit = Object.freeze({
    kind: "batch",
    operation: "existing",
    path: "/api/tdsnap/batch",
    payload: Object.freeze({ entries: Object.freeze(entries) }),
    title: "",
    parentTitle: state.queue[0].page,
    displayTitle: `${pages} page${pages === 1 ? "" : "s"}`,
    knownPageTitles: Object.freeze([]),
  });

  $("result-eyebrow").textContent = "Review";
  $("result-heading").textContent = `Check all ${pages} page${pages === 1 ? "" : "s"} before they are applied`;
  $("result-sub").textContent =
    "Every page this batch touches is named below, in the order it will be applied. "
    + "Nothing changes until you confirm.";
  $("review-state").hidden = false;
  $("success-state").hidden = true;
  $("review-action").textContent =
    `Apply ${pages} queued page${pages === 1 ? "" : "s"} in TD Snap`;
  $("review-target").textContent = state.queue.map((queued) => queued.page).join(", ");
  $("review-count").textContent = [
    totals.added ? `${totals.added} added` : "",
    totals.changed ? `${totals.changed} changed` : "",
    totals.moved ? `${totals.moved} moved` : "",
    totals.removed ? `${totals.removed} removed` : "",
  ].filter(Boolean).join(" · ");
  $("review-placement").textContent = "As reviewed on each page";
  $("confirm-update-label").textContent =
    `Apply ${pages} page${pages === 1 ? "" : "s"}`;
  $("review-error").hidden = true;
  $("review-error").innerHTML = "";

  // The per-page lists belong to a single-page review; the batch has its own.
  ["review-items-wrap", "review-changes-wrap", "review-moves-wrap",
    "review-removals-wrap", "review-placement-section"].forEach((id) => {
    $(id).hidden = true;
  });
  $("adjust-placement-btn").hidden = true;
  $("queue-add-btn").hidden = true;
  $("review-queue-wrap").hidden = false;

  const list = $("review-queue");
  list.innerHTML = "";
  state.queue.forEach((queued) => {
    const row = document.createElement("li");
    const name = document.createElement("strong");
    name.textContent = queued.summary;
    row.append(name);
    if (queued.labels.length) {
      const detail = document.createElement("span");
      detail.textContent = queued.labels.join(", ");
      row.append(detail);
    }
    list.append(row);
  });

  // Undo is single-level and always has been; a batch is the one place that
  // could be mistaken for "take the whole thing back", so it is said here.
  const note = $("review-undo-note");
  const lastPage = state.queue[pages - 1].page;
  const unqueued = state.words.length || countEdits(state.pageEdits)
    ? titleOf(state.parentId)
    : null;
  note.innerHTML = "";
  const lead = document.createElement("strong");
  lead.textContent = pages > 1
    ? `Undo reaches back one page only — “${lastPage}”, if it is the last one applied.`
    : `Undo reaches back to “${lastPage}” only.`;
  note.append(lead);
  if (unqueued) {
    appendNamedList(
      note,
      "Not in this batch, and not applied by it:",
      [`the buttons you have open for ${unqueued}`],
    );
  }
  note.hidden = false;
  return unqueued;
}

/* ---------- the result ---------- */

const OUTCOME_TEXT = {
  applied: "Applied",
  refused: "Not applied — nothing was changed on this page",
  failed: "Failed — this page was put back the way it was",
  skipped: "Not attempted, because an earlier page could not be applied",
};

function renderBatchOutcome(data) {
  const wrap = $("batch-outcome-wrap");
  const list = $("batch-outcome");
  const results = data.results || [];
  wrap.hidden = results.length === 0;
  list.innerHTML = "";
  results.forEach((result) => {
    const row = document.createElement("li");
    row.className = `batch-outcome-${result.status}`;
    const name = document.createElement("strong");
    name.textContent = result.page;
    const status = document.createElement("span");
    const report = result.report;
    status.textContent = result.status === "applied" && report
      ? `${OUTCOME_TEXT.applied} — ${[
        report.buttons ? `${report.buttons} added` : "",
        report.changed ? `${report.changed} changed` : "",
        report.moved ? `${report.moved} moved` : "",
        report.removed ? `${report.removed} removed` : "",
      ].filter(Boolean).join(", ") || "nothing to do"}`
      : OUTCOME_TEXT[result.status] || result.status;
    row.append(name, status);
    if (result.error) {
      const why = document.createElement("span");
      why.className = "batch-outcome-why";
      why.textContent = result.error;
      row.append(why);
    }
    list.append(row);
  });
}

/* ---------- wiring ---------- */

/* Shown on a single-page review, and only where a batch can actually be
   applied. Called by the review step, which owns that screen. */
function syncQueueControls() {
  const button = $("queue-add-btn");
  const note = $("queue-add-note");
  const offered = batchable();
  const blocked = offered ? blockedReason() : "";
  button.hidden = !offered || Boolean(blocked);
  note.hidden = !blocked;
  note.textContent = blocked;
}

$("queue-add-btn").addEventListener("click", () => {
  const page = queueCurrentPage();
  if (!page) return;
  // The queued payload is frozen and independent of live state, so the
  // composition can be cleared for the next page without disturbing it.
  state.words = [];
  clearUndoHistory();
  state.pageEdits = emptyEdits();
  state.pendingEdit = null;
  state.placementAdjusted = false;
  renderWords();
  renderQueue();
  show("items");
});

$("queue-review-btn").addEventListener("click", () => {
  if (!state.queue.length) return;
  prepareBatchReview();
  show("review");
});

export {
  MAX_QUEUED_PAGES, batchable, clearQueue, prepareBatchReview, queueCurrentPage,
  removeFromQueue, renderBatchOutcome, renderQueue, syncQueueControls,
};
