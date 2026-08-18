/* Pending changes, moves, and removals to buttons that already exist.
 *
 * state.words holds buttons that don't exist yet; this holds edits to ones
 * that do. They are kept apart deliberately: adding a button is reversible by
 * deleting a chip, while changing, moving, or removing one reaches into
 * vocabulary somebody already relies on. Nothing here touches the page — it
 * only describes what the review screen will name and what the confirm request
 * will carry.
 *
 * Everything in this module is pure so the wording a user is asked to confirm
 * can be tested directly, without a browser.
 */

/* An edit is only pending when it would actually alter something. Recording a
   "change" that changes nothing would put a line on the review screen naming
   an edit that never happens, which is worse than no line at all. */
function differs(button, next) {
  const label = (next.label || "").trim();
  const message = (next.message || "").trim();
  const wasMessage = (button.message || "").trim();
  return label !== (button.label || "").trim() || message !== wasMessage;
}

function emptyEdits() {
  return { changes: [], removals: [], moves: [] };
}

function changeFor(edits, slot) {
  return edits.changes.find((change) => change.slot === slot) || null;
}

function isRemoved(edits, slot) {
  return edits.removals.includes(slot);
}

/* A move is recorded against the cell the button started in, so `slot` is
   where it was when the page was read and `to` is where it is headed. Both
   lookups are needed: the preview draws the button in its destination while
   still knowing which cell it vacated. */
function moveFrom(edits, slot) {
  return edits.moves.find((move) => move.slot === slot) || null;
}

function moveInto(edits, slot) {
  return edits.moves.find((move) => move.to === slot) || null;
}

function pendingKind(edits, slot) {
  if (isRemoved(edits, slot)) return "removed";
  if (changeFor(edits, slot)) return "changed";
  return moveFrom(edits, slot) ? "moved" : null;
}

function countEdits(edits) {
  return edits.changes.length + edits.removals.length + edits.moves.length;
}

/* A move may only land on a cell that will be free by the time it runs: an
   empty one, one a removal frees, or one whose own button is moving out (two
   buttons trading places). Dropping a move can therefore invalidate another,
   so this settles rather than filtering once — half a swap would leave one
   button aimed at the other, which the write path refuses outright. */
function survivingMoves(moves, bySlot, removals) {
  for (;;) {
    const sources = new Set(moves.map((move) => move.slot));
    const kept = moves.filter((move) => {
      const occupant = bySlot.get(move.to);
      return !occupant || removals.includes(move.to) || sources.has(move.to);
    });
    if (kept.length === moves.length) return kept;
    moves = kept;
  }
}

/* Drop every pending edit whose button is no longer where it was, so a page
   that changed under us can never carry a stale slot into a write request. */
function reconcile(edits, buttons) {
  const bySlot = new Map(buttons.map((button) => [button.slot, button]));
  const stillThere = (slot, label) => {
    const button = bySlot.get(slot);
    return Boolean(button && button.editable && (label === undefined || button.label === label));
  };
  const removals = edits.removals.filter((slot) => stillThere(slot));
  return {
    changes: edits.changes.filter((change) => stillThere(change.slot, change.from.label)),
    removals,
    moves: survivingMoves(
      edits.moves.filter((move) => stillThere(move.slot, move.from.label)),
      bySlot,
      removals,
    ),
  };
}

/* Which cells hold an existing button once the edit lands. New buttons have to
   avoid these, and so does the next move: a cell that looks empty in the grid
   today may be where something is already headed. */
function occupiedAfter(edits, buttons) {
  const sources = new Set(edits.moves.map((move) => move.slot));
  const staying = buttons
    .map((button) => button.slot)
    .filter((slot) => !isRemoved(edits, slot) && !sources.has(slot));
  return new Set([...staying, ...edits.moves.map((move) => move.to)]);
}

/* Cells a new button may be placed in once the pending edit lands: the ones the
   page reported empty, plus the ones this edit frees, minus the ones it fills.

   *free* is what the page reported before any of this was planned, which is why
   it is not the whole answer — a cell whose button is being retired or moved
   away is space the same edit creates, and the write path has always accepted
   it. Typing a correction into the space a typo just vacated is the most
   ordinary use of this feature. */
function placeableSlots(edits, buttons, free) {
  const taken = occupiedAfter(edits, buttons);
  const freed = [...edits.removals, ...edits.moves.map((move) => move.slot)];
  return [...new Set([...free, ...freed])]
    .filter((slot) => !taken.has(slot))
    .sort((left, right) => left - right);
}

/* Every planner returns a whole new edit set rather than mutating one, so the
   caller can hand the result straight to state and never half-apply a plan. */
function withoutSlot(edits, slot) {
  return {
    changes: edits.changes.filter((change) => change.slot !== slot),
    removals: edits.removals.filter((candidate) => candidate !== slot),
    moves: edits.moves.filter((move) => move.slot !== slot),
  };
}

function planChange(edits, button, next) {
  const rest = withoutSlot(edits, button.slot);
  // A button that is moving keeps moving when its text is edited: they are
  // independent decisions about the same button.
  const move = moveFrom(edits, button.slot);
  if (move) rest.moves = [...rest.moves, move].sort((left, right) => left.slot - right.slot);
  if (!differs(button, next)) return rest;
  rest.changes.push({
    slot: button.slot,
    label: (next.label || "").trim(),
    message: (next.message || "").trim(),
    from: {
      label: button.label || "",
      message: button.message || "",
      fn: button.function || "",
    },
  });
  rest.changes.sort((left, right) => left.slot - right.slot);
  return rest;
}

function planRemoval(edits, button) {
  const rest = withoutSlot(edits, button.slot);
  return {
    ...rest,
    removals: [...rest.removals, button.slot].sort((left, right) => left - right),
  };
}

/* Move the button reviewed in *slot* to *target*. When another eligible button
   is already there the two trade places, which is one move each — the write
   path routes a swap through a spare cell so neither is ever dropped onto the
   other. Anything not eligible to move leaves the plan untouched, so a drop on
   a locked button is a no-op rather than a silent near-miss.

   *blocked* names cells a new button in this session has claimed: they look
   empty on the page but the same edit is about to fill them. */
function planMove(edits, buttons, slot, target, blocked = []) {
  const bySlot = new Map(buttons.map((button) => [button.slot, button]));
  const button = bySlot.get(slot);
  const occupant = bySlot.get(target);
  const movable = (candidate) =>
    Boolean(candidate && candidate.editable && !isRemoved(edits, candidate.slot));
  // A button already on its way out — retired, or moving somewhere else — is not
  // in the way, so that cell takes a plain move rather than a swap.
  const swapWith =
    occupant && !isRemoved(edits, occupant.slot) && !moveFrom(edits, occupant.slot)
      ? occupant
      : null;
  if (
    !movable(button) ||
    slot === target ||
    blocked.includes(target) ||
    (swapWith && !movable(swapWith))
  ) {
    return edits;
  }

  const rest = withoutSlot(edits, slot);
  // This button now claims the target cell, so nothing else may still be aimed
  // at it. Everything else is left alone and settled by the same rule that
  // reconciles a page which changed underneath: a move whose target stops being
  // free goes, and so does anything that only made sense alongside it.
  const moves = rest.moves.filter((move) => move.to !== target);
  moves.push({ slot, to: target, from: { label: button.label || "" } });
  if (swapWith) {
    moves.push({ slot: target, to: slot, from: { label: swapWith.label || "" } });
  }
  return {
    ...rest,
    moves: survivingMoves(moves, bySlot, rest.removals)
      .sort((left, right) => left.slot - right.slot),
  };
}

function keepButton(edits, slot) {
  const move = moveFrom(edits, slot);
  const rest = withoutSlot(edits, slot);
  // "Keep as it is" answers the change or removal the dialog was opened on; a
  // pending move of the same button is a separate decision and survives.
  if (move) rest.moves = [...rest.moves, move].sort((left, right) => left.slot - right.slot);
  return rest;
}

/* What the button will read once the edit lands — used by the preview so the
   grid shows the page as it will be, not as it is. */
function effectiveLabel(edits, button) {
  const change = changeFor(edits, button.slot);
  return change ? change.label : button.label;
}

/* The request body's change list: only the fields that actually move, so a
   label-only edit never rewrites a spoken message it was not asked to. */
function changePayload(edits) {
  return edits.changes.map((change) => {
    const payload = { slot: change.slot };
    if (change.label !== change.from.label) payload.label = change.label;
    if (change.message !== change.from.message) payload.message = change.message;
    return payload;
  });
}

/* Moves travel as bare cell numbers; the label rides along only in the review
   copy, because the write path reads the label off the page itself. */
function movePayload(edits) {
  return edits.moves.map((move) => ({ slot: move.slot, to: move.to }));
}

/* "Change 2 and remove 1 button on Snacks" — the sentence the confirm button
   carries, so what is written is named in full before anything is written.
   The trailing noun agrees with the last count, which is the one it reads
   next to. */
function editSummary({ added = 0, changed = 0, removed = 0, moved = 0, page = "" }) {
  const parts = [];
  if (added) parts.push([`add ${added}`, added]);
  if (changed) parts.push([`change ${changed}`, changed]);
  if (moved) parts.push([`move ${moved}`, moved]);
  if (removed) parts.push([`remove ${removed}`, removed]);
  if (!parts.length) return "";
  const last = parts[parts.length - 1];
  const noun = `button${last[1] === 1 ? "" : "s"}`;
  const words = parts.map((part) => part[0]);
  const list =
    words.length === 1
      ? words[0]
      : `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}`;
  const sentence = `${list} ${noun} on ${page}`;
  return sentence.charAt(0).toUpperCase() + sentence.slice(1);
}

/* One plain-language line per edit, for the review list. */
function describeChange(change) {
  const parts = [];
  if (change.label !== change.from.label) {
    parts.push(`“${change.from.label}” becomes “${change.label}”`);
  }
  if (change.message !== change.from.message) {
    parts.push(
      change.message
        ? `speaks “${change.message}”`
        : `speaks its label instead of “${change.from.message}”`,
    );
  }
  return parts.join(" · ");
}

function describeRemoval(button) {
  return button.message ? `${button.label} — speaks “${button.message}”` : button.label;
}

/* Undo exists only where the machinery it needs does: a live TD Snap session
   that has actually applied an edit. Exported files and Grid 3 have no retained
   snapshot to replay, so they never offer the control at all. */
function undoAvailable({ lastEdit, provider, mode }) {
  return Boolean(lastEdit && provider === "tdsnap" && mode === "live");
}

/* Row and column, one-based, because that is how somebody looking at a device
   counts cells — never the internal slot number. */
function cellName(slot, cols) {
  return `row ${Math.floor(slot / cols) + 1}, column ${(slot % cols) + 1}`;
}

function describeMove(move, cols) {
  return `${cellName(move.slot, cols)} → ${cellName(move.to, cols)}`;
}

export {
  cellName,
  changeFor,
  changePayload,
  countEdits,
  describeChange,
  describeMove,
  describeRemoval,
  differs,
  editSummary,
  effectiveLabel,
  emptyEdits,
  isRemoved,
  keepButton,
  moveFrom,
  moveInto,
  movePayload,
  occupiedAfter,
  pendingKind,
  placeableSlots,
  planChange,
  planMove,
  planRemoval,
  reconcile,
  undoAvailable,
};
