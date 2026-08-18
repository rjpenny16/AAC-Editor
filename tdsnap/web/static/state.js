/* Shared editor state.
 *
 * One object, mutated in place. Modules import it and read or write fields
 * directly; that is deliberate for an app this size, but it means a field's
 * lifecycle is only as clear as the code that resets it — see resetConnection
 * in connect.js, which must clear everything a session owns.
 *
 * Module-level `let` bindings cannot be reassigned across an ES module
 * boundary, so any scalar more than one module writes to lives here instead.
 */

import { emptyEdits } from "./edits.js";

/* Communicative-function color coding used on topic pages: each function
   gets the same colored border TD Snap renders around the button. */
const FUNCTIONS = {
  question: { name: "Question", color: "#1E88E5" },
  comment: { name: "Comment", color: "#F57C00" },
  positive: { name: "Positive", color: "#43A047" },
  negative: { name: "Negative", color: "#E53935" },
  personal: { name: "Personal", color: "#8E24AA" },
};

/* The five rows of a topic page, in the order TD Snap renders them. */
const TOPIC_FUNCTIONS = ["question", "comment", "positive", "negative", "personal"];

/* Requests that touch TD Snap or Grid 3 are given no deadline; everything
   else gives up rather than leaving the user with a dead button. */
const API_TIMEOUT_MS = 10_000;

const requestedProvider = new URLSearchParams(window.location.search).get("provider");
const state = {
  provider: ["tdsnap", "grid3", "file"].includes(requestedProvider)
    ? requestedProvider : "tdsnap",
  mode: "live",
  connected: false,
  operation: "existing", // "existing" | "new"
  wizardStep: "connect",
  pendingEdit: null,
  placementAdjusted: false,
  grid: { cols: 8, rows: 5 },
  existingButtons: [], // [{slot, label, message, function, symbol, editable, locked_reason}]
  // Pending edits to buttons that already exist on the page, kept apart from
  // state.words because they reach into vocabulary somebody already uses.
  // Built by edits.js rather than written out here, so a new kind of edit can
  // never be missing from the one copy nothing resets.
  pageEdits: emptyEdits(),
  // Whether this connection can change, move, or remove what is already on the
  // page: TD Snap live, on an existing page, whose stored content AAC Editor
  // could actually read. Anything less and existing buttons stay locked.
  canEditExisting: false,
  // What "Undo my last change" would do, as described by the server that is
  // holding the snapshot — or null when there is nothing to undo. The snapshot
  // itself never comes here: the browser only ever renders the description and
  // asks the server to replay it. See the undo section in live.py.
  lastEdit: null,
  placementReturn: "review", // which step the placement editor returns to
  availableSlots: null,
  grid3Cells: [],
  previewAspect: null,
  gridBackground: null,
  layoutFingerprint: null,
  pages: [],
  words: [], // [{label, message|null, fn|"", slot, symbol}]
  pageStyle: "words", // "words" | "topic"
  activeFn: "",
  autoTopicRows: false,
  parentId: null,
  parentFree: null,
  parentTouched: false,
  recommendedParent: null,
  currentPage: "",
  sessionId: null,
  filename: "",
  edits: 0,
  applied: false, // has the current word list already been written to the page set?
  native: false, // running inside the app's own window (pywebview)?
  elevated: false,
  apiToken: "",
  targetLoading: false,
  // Set while the user is deliberately leaving, so the unsaved-work guard
  // doesn't nag on the way out of a quit they just confirmed.
  leaving: false,
};

export { API_TIMEOUT_MS, FUNCTIONS, TOPIC_FUNCTIONS, state };
