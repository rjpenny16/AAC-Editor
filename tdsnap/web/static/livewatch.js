/* When to poll TD Snap, and when to tell the person it has gone quiet.
 *
 * The live monitor in connect.js asks TD Snap which page is open every
 * 1.5 s. Before this module, a failed or "not running" answer was swallowed
 * and the next poll tried again at the same rate, forever: if TD Snap was
 * closed or the laptop slept, the person saw nothing at all, and AAC Editor
 * kept walking an accessibility tree that was not there.
 *
 * This keeps the decision in one small, DOM-free state machine so it can be
 * tested directly (tests/js/livewatch.test.js):
 *
 * - A few misses in a row are normal (TD Snap has no page grid while it
 *   navigates), so nothing is shown until LOST_AFTER consecutive misses.
 * - Once lost, the interval doubles on each further miss up to MAX_DELAY_MS,
 *   so a closed TD Snap is not probed every 1.5 s indefinitely.
 * - The first good answer resets everything and says the connection is back.
 */

const BASE_DELAY_MS = 1500;
const MAX_DELAY_MS = 15000;
const LOST_AFTER = 3;

function createLiveWatch({ base = BASE_DELAY_MS, max = MAX_DELAY_MS, lostAfter = LOST_AFTER } = {}) {
  let misses = 0;
  let delay = base;

  return {
    /* A poll reached TD Snap and it has a page open. Returns true when this
       ends a lost spell, so the caller can hide its banner. */
    ok() {
      const wasLost = misses >= lostAfter;
      misses = 0;
      delay = base;
      return wasLost;
    },
    /* A poll failed, or TD Snap answered that it is not running. Returns true
       on the miss that first crosses into "lost", so the banner is announced
       once rather than on every poll. */
    miss() {
      misses += 1;
      if (misses > lostAfter) delay = Math.min(delay * 2, max);
      return misses === lostAfter;
    },
    /* Start over at full speed, as when the monitor starts on a new page. */
    reset() {
      misses = 0;
      delay = base;
    },
    /* Poll at full speed again without forgetting that TD Snap was lost, as
       when the person selects Check again: the next good poll still has to
       report the recovery so the banner can close. */
    hurry() {
      delay = base;
    },
    isLost() {
      return misses >= lostAfter;
    },
    nextDelay() {
      return delay;
    },
  };
}

export { BASE_DELAY_MS, createLiveWatch, LOST_AFTER, MAX_DELAY_MS };
