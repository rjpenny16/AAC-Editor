/* A small bounded undo stack for the composition step.
 *
 * Chip removal and "Arrange automatically" are the two actions in the
 * composition wizard that discard something — a label, a message, a
 * function assignment — with no other way back. This module is deliberately
 * standalone, with no DOM or app-state import, so it stays trivially
 * testable; chips.js wires it to state.words and the Undo button.
 */

const DEFAULT_LIMIT = 20;

function createUndoStack(limit = DEFAULT_LIMIT) {
  const snapshots = [];
  return {
    push(snapshot) {
      snapshots.push(snapshot);
      if (snapshots.length > limit) snapshots.shift();
    },
    pop() {
      return snapshots.pop();
    },
    canUndo() {
      return snapshots.length > 0;
    },
    clear() {
      snapshots.length = 0;
    },
  };
}

export { createUndoStack };
