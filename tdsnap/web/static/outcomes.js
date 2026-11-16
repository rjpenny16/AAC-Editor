/* What an operation's outcome means, in words a clinician can act on.
 *
 * The server ends every edit in one outcome class (tdsnap/errors.py, doc 04
 * of docs/reliability) and a stable code. This module turns those into the
 * message the user sees, answering, in order (doc 05):
 *
 *   1. what happened;
 *   2. was anything changed;
 *   3. is the original safe;
 *   4. what to do next;
 *   5. whether trying again is safe;
 *   6. a reference to quote, and the support report.
 *
 * The first answer is the server's own sentence (it names the button or page,
 * which is fine on this screen and never logged). The rest come from the
 * outcome and code, never from parsing message text.
 */

const OUTCOME = {
  refused: {
    changed: "Nothing was changed.",
    safe: "The page is exactly as it was.",
    retry: "It is safe to try again once that is sorted out.",
  },
  rolled_back: {
    changed: "The edit was started and then undone: the page was checked and matches how it was before.",
    safe: "Nothing you had before was lost.",
    retry: "It is safe to review the edit again and retry.",
  },
  partial: {
    changed: "Part of the edit may still be on the page: AAC Editor could not put everything back.",
    safe: "Check the page before relying on it.",
    retry: "Do not retry until you have checked the page.",
  },
  unknown: {
    changed: "AAC Editor could not tell what is on the page now.",
    safe: "Check the page before relying on it.",
    retry: "Do not retry until you have checked the page.",
  },
};

/* What to do next, by code. Codes not listed fall back to the outcome. */
const NEXT = {
  NOT_FOREGROUND: (app) => `Click on ${app} so it is the window in front, then try again.`,
  WINDOW_NOT_FOUND: (app) => `Open ${app}, then reconnect.`,
  EDIT_MODE_BUSY: (app) => `Finish or cancel the edit that is open in ${app} (press Done), then try again.`,
  DIALOG_OPEN: (app) => `Answer or close the message open in ${app}, then check the page.`,
  FINGERPRINT_CHANGED: () => "Refresh the page and review the edit again.",
  ELEVATION_MISMATCH: (app) => `Restart ${app} normally (not as administrator), then reconnect.`,
  AUTOMATION_DEADLINE: (app) => `${app} stopped responding. Check the page in ${app}, then choose “Change app” at the top and connect again.`,
  LIVE_LOCKED: (app) => `Check the page in ${app}, then choose “Change app” at the top and connect again.`,
  TOKEN_STALE: () => "AAC Editor restarted. Reload this page.",
  SAVE_LOCKED: () => "Close the file in any other program, then save again.",
  SAVE_SAME_AS_SOURCE: () => "Choose a different file name; the original is kept as it is.",
  SESSION_EXPIRED: () => "Open the file again.",
  BUSY: () => "Wait for the current operation to finish, then try again.",
};

function nextStep(code, outcome, app) {
  if (NEXT[code]) return NEXT[code](app);
  if (outcome === "partial" || outcome === "unknown") {
    return `Look at this page in ${app} and compare it with what you reviewed before doing anything else.`;
  }
  if (outcome === "rolled_back") return "Review the edit again, then retry.";
  return "";
}

/* The lines to show under a failure heading. *error* is what api.js threw:
   message, code, outcome, op. */
function failureLines(error, app = "TD Snap") {
  if (["verified", "verified_with_gaps", "ok"].includes(error.outcome)) {
    return [error.message, `Look at the page in ${app} to see it. Do not apply it again.`,
      ...(error.op ? [`Reference ${error.op}`] : [])];
  }
  const outcome = OUTCOME[error.outcome] ? error.outcome : "unknown";
  const facts = OUTCOME[outcome];
  const lines = [error.message];
  lines.push(facts.changed, facts.safe);
  const next = nextStep(error.code, outcome, app);
  if (next) lines.push(next);
  lines.push(facts.retry);
  if (error.op) lines.push(`Reference ${error.op} · Copy a support report from the footer if you need help.`);
  return lines.filter(Boolean);
}

/* A short heading for a failure, from its outcome. */
function failureHeading(error, app = "TD Snap", undoing = false) {
  const what = undoing ? "The undo" : "The edit";
  if (error.outcome === "verified" || error.outcome === "verified_with_gaps"
      || error.outcome === "ok") {
    return `${what} went through, but its answer was lost on the way back.`;
  }
  switch (error.outcome) {
    case "refused": return `${what} was not started.`;
    case "rolled_back": return `${what} did not go through, and the page was put back.`;
    case "partial": return `${what} did not finish, and the page may be partly changed. Check it in ${app}.`;
    case "unknown": return `${what} stopped part-way. Check the page in ${app} before doing anything else.`;
    default: return `${what} did not go through.`;
  }
}

/* Heading and eyebrow for a result screen, from a success outcome. Anything
   other than verified or verified_with_gaps never shows a success heading. */
function successHeading(outcome, fallback) {
  if (outcome === "verified_with_gaps") {
    return { eyebrow: "Done — check the notes", heading: fallback.replace(/^Done/, "Done, with notes") };
  }
  return { eyebrow: "Complete", heading: fallback };
}

const UNVERIFIED_LABELS = {
  symbols: "symbols",
  topic_format: "topic border colours",
};

function unverifiedText(unverified = []) {
  const names = unverified.map((key) => UNVERIFIED_LABELS[key] || key);
  return names.length
    ? `Not checked automatically: ${names.join(" and ")}. Look at them in the app.`
    : "";
}

export { failureHeading, failureLines, OUTCOME, successHeading, unverifiedText };
