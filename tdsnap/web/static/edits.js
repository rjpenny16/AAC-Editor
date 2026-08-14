/* Pending changes and removals to buttons that already exist on the page.
 *
 * state.words holds buttons that don't exist yet; this holds edits to ones
 * that do. They are kept apart deliberately: adding a button is reversible by
 * deleting a chip, while changing or removing one reaches into vocabulary
 * somebody already relies on. Nothing here touches the page — it only
 * describes what the review screen will name and what the confirm request
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
  return { changes: [], removals: [] };
}

function changeFor(edits, slot) {
  return edits.changes.find((change) => change.slot === slot) || null;
}

function isRemoved(edits, slot) {
  return edits.removals.includes(slot);
}

function pendingKind(edits, slot) {
  if (isRemoved(edits, slot)) return "removed";
  return changeFor(edits, slot) ? "changed" : null;
}

function countEdits(edits) {
  return edits.changes.length + edits.removals.length;
}

/* Drop every pending edit whose button is no longer where it was, so a page
   that changed under us can never carry a stale slot into a write request. */
function reconcile(edits, buttons) {
  const bySlot = new Map(buttons.map((button) => [button.slot, button]));
  return {
    changes: edits.changes.filter((change) => {
      const button = bySlot.get(change.slot);
      return button && button.editable && button.label === change.from.label;
    }),
    removals: edits.removals.filter((slot) => {
      const button = bySlot.get(slot);
      return button && button.editable;
    }),
  };
}

function planChange(edits, button, next) {
  const rest = {
    changes: edits.changes.filter((change) => change.slot !== button.slot),
    removals: edits.removals.filter((slot) => slot !== button.slot),
  };
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
  return {
    changes: edits.changes.filter((change) => change.slot !== button.slot),
    removals: [...edits.removals.filter((slot) => slot !== button.slot), button.slot].sort(
      (left, right) => left - right,
    ),
  };
}

function keepButton(edits, slot) {
  return {
    changes: edits.changes.filter((change) => change.slot !== slot),
    removals: edits.removals.filter((candidate) => candidate !== slot),
  };
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

/* "Change 2 and remove 1 button on Snacks" — the sentence the confirm button
   carries, so what is written is named in full before anything is written.
   The trailing noun agrees with the last count, which is the one it reads
   next to. */
function editSummary({ added = 0, changed = 0, removed = 0, page = "" }) {
  const parts = [];
  if (added) parts.push([`add ${added}`, added]);
  if (changed) parts.push([`change ${changed}`, changed]);
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

export {
  changeFor,
  changePayload,
  countEdits,
  describeChange,
  describeRemoval,
  differs,
  editSummary,
  effectiveLabel,
  emptyEdits,
  isRemoved,
  keepButton,
  pendingKind,
  planChange,
  planRemoval,
  reconcile,
};
