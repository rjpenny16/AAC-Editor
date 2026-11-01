/* The live monitor's backoff and "lost TD Snap" decision (livewatch.js). */

const test = require("node:test");
const assert = require("node:assert/strict");

let createLiveWatch, BASE_DELAY_MS, MAX_DELAY_MS, LOST_AFTER;

test.before(async () => {
  ({ createLiveWatch, BASE_DELAY_MS, MAX_DELAY_MS, LOST_AFTER } =
    await import("../../tdsnap/web/static/livewatch.js"));
});

test("a fresh watch polls at the base rate and is not lost", () => {
  const watch = createLiveWatch();
  assert.equal(watch.nextDelay(), BASE_DELAY_MS);
  assert.equal(watch.isLost(), false);
});

test("a couple of misses while TD Snap navigates do not count as lost", () => {
  const watch = createLiveWatch();
  for (let i = 1; i < LOST_AFTER; i += 1) assert.equal(watch.miss(), false);
  assert.equal(watch.isLost(), false);
  assert.equal(watch.nextDelay(), BASE_DELAY_MS);
});

test("the miss that crosses the threshold is reported once", () => {
  const watch = createLiveWatch({ lostAfter: 3 });
  assert.equal(watch.miss(), false);
  assert.equal(watch.miss(), false);
  assert.equal(watch.miss(), true);
  assert.equal(watch.isLost(), true);
  assert.equal(watch.miss(), false, "later misses must not re-announce");
});

test("once lost, the delay doubles and stops at the ceiling", () => {
  const watch = createLiveWatch({ base: 1000, max: 5000, lostAfter: 1 });
  watch.miss();
  assert.equal(watch.nextDelay(), 1000);
  watch.miss();
  assert.equal(watch.nextDelay(), 2000);
  watch.miss();
  assert.equal(watch.nextDelay(), 4000);
  watch.miss();
  assert.equal(watch.nextDelay(), 5000);
  watch.miss();
  assert.equal(watch.nextDelay(), 5000);
});

test("a good poll after a lost spell resets the rate and says it recovered", () => {
  const watch = createLiveWatch({ lostAfter: 2 });
  watch.miss();
  watch.miss();
  watch.miss();
  assert.ok(watch.nextDelay() > BASE_DELAY_MS);
  assert.equal(watch.ok(), true);
  assert.equal(watch.isLost(), false);
  assert.equal(watch.nextDelay(), BASE_DELAY_MS);
  assert.equal(watch.ok(), false, "a second good poll is not a recovery");
});

test("a good poll before the threshold is not reported as a recovery", () => {
  const watch = createLiveWatch({ lostAfter: 3 });
  watch.miss();
  assert.equal(watch.ok(), false);
});

test("reset returns to full speed without waiting for a good poll", () => {
  const watch = createLiveWatch({ lostAfter: 1 });
  watch.miss();
  watch.miss();
  watch.reset();
  assert.equal(watch.isLost(), false);
  assert.equal(watch.nextDelay(), BASE_DELAY_MS);
});

test("hurry polls at full speed but still reports the recovery", () => {
  const watch = createLiveWatch({ lostAfter: 1 });
  watch.miss();
  watch.miss();
  watch.hurry();
  assert.equal(watch.nextDelay(), BASE_DELAY_MS);
  assert.equal(watch.isLost(), true);
  assert.equal(watch.ok(), true);
});

test("a miss after hurry backs off again from the base rate", () => {
  const watch = createLiveWatch({ base: 1000, max: 8000, lostAfter: 1 });
  watch.miss();
  watch.miss();
  watch.miss();
  watch.hurry();
  watch.miss();
  assert.equal(watch.nextDelay(), 2000);
});

test("the ceiling is well above the base rate", () => {
  assert.ok(MAX_DELAY_MS >= BASE_DELAY_MS * 4);
});
