/* The client-side phrase classifier.
 *
 * These cases are the contract between this and `phrase_function` in
 * tdsnap/web/prompts.py. The server classifies AI suggestions, the client
 * classifies whatever the user types or pastes, and a disagreement puts the
 * same phrase in a different colored row depending on where it came from.
 */

const test = require("node:test");
const assert = require("node:assert/strict");

let inferPhraseFunction;

test.before(async () => {
  ({ inferPhraseFunction } = await import("../../tdsnap/web/static/phrases.js"));
});

test("a trailing question mark wins", () => {
  assert.equal(inferPhraseFunction("Are we going out?"), "question");
  assert.equal(inferPhraseFunction("This is a statement?"), "question");
});

test("question words are recognized without punctuation", () => {
  for (const phrase of ["what happens next", "how does it work", "can I try"]) {
    assert.equal(inferPhraseFunction(phrase), "question", phrase);
  }
});

test("negation beats a positive word in the same phrase", () => {
  assert.equal(inferPhraseFunction("I do not like this"), "negative");
  assert.equal(inferPhraseFunction("This is not good"), "negative");
});

test("ownership marks a phrase as personal", () => {
  assert.equal(inferPhraseFunction("My turn"), "personal");
  assert.equal(inferPhraseFunction("That is mine"), "personal");
});

test("liking is positive", () => {
  assert.equal(inferPhraseFunction("I love this part"), "positive");
  assert.equal(inferPhraseFunction("This is awesome"), "positive");
});

test("first-person experience is personal", () => {
  assert.equal(inferPhraseFunction("I went there yesterday"), "personal");
  assert.equal(inferPhraseFunction("I watched it twice"), "personal");
});

test("a neutral observation falls back to comment", () => {
  assert.equal(inferPhraseFunction("The sky is grey"), "comment");
});

test("a suggested function is honoured only when nothing else matches", () => {
  assert.equal(inferPhraseFunction("The sky is grey", "personal"), "personal");
  // A statement must never be filed as a question, whatever was suggested.
  assert.equal(inferPhraseFunction("The sky is grey", "question"), "comment");
});

test("a curly apostrophe classifies like a straight one", () => {
  assert.equal(inferPhraseFunction("I don’t like it"), "negative");
  assert.equal(inferPhraseFunction("I don't like it"), "negative");
});

test("empty and non-string input never throws", () => {
  for (const value of ["", null, undefined, 42]) {
    assert.equal(typeof inferPhraseFunction(value), "string");
  }
});
