/* The composition step's undo stack.
 *
 * Standalone by design (see undo.js) so it can be exercised directly,
 * without pulling in state.js/dom.js and the DOM they assume exists.
 */

const test = require("node:test");
const assert = require("node:assert/strict");

let createUndoStack;

test.before(async () => {
  ({ createUndoStack } = await import("../../tdsnap/web/static/undo.js"));
});

test("a fresh stack has nothing to undo", () => {
  const stack = createUndoStack();
  assert.equal(stack.canUndo(), false);
  assert.equal(stack.pop(), undefined);
});

test("push then pop returns the same snapshot, last in first out", () => {
  const stack = createUndoStack();
  stack.push(["apple"]);
  stack.push(["apple", "banana"]);
  assert.equal(stack.canUndo(), true);
  assert.deepEqual(stack.pop(), ["apple", "banana"]);
  assert.deepEqual(stack.pop(), ["apple"]);
  assert.equal(stack.canUndo(), false);
});

test("popping an empty stack is safe and returns undefined", () => {
  const stack = createUndoStack();
  stack.push(["apple"]);
  stack.pop();
  assert.equal(stack.pop(), undefined);
  assert.equal(stack.canUndo(), false);
});

test("the stack is bounded: the oldest snapshot is dropped, not the newest", () => {
  const stack = createUndoStack(2);
  stack.push("a");
  stack.push("b");
  stack.push("c");
  assert.equal(stack.pop(), "c");
  assert.equal(stack.pop(), "b");
  assert.equal(stack.canUndo(), false); // "a" was evicted when "c" pushed past the limit
});

test("clear empties the stack", () => {
  const stack = createUndoStack();
  stack.push("a");
  stack.push("b");
  stack.clear();
  assert.equal(stack.canUndo(), false);
  assert.equal(stack.pop(), undefined);
});

test("stacks are independent of each other", () => {
  const first = createUndoStack();
  const second = createUndoStack();
  first.push("only in first");
  assert.equal(first.canUndo(), true);
  assert.equal(second.canUndo(), false);
});
