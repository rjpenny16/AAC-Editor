/* Every call to the local server goes through here.
 *
 * The per-run API token is fetched once and awaited by every request, so a
 * fast first click cannot race the config response and get a 403. Errors are
 * normalized into something a clinician can act on rather than a status code.
 */

import { state, API_TIMEOUT_MS, LIVE_READ_TIMEOUT_MS } from "./state.js";

async function fetchWithDeadline(path, options = {}, timeoutMs = API_TIMEOUT_MS) {
  if (!timeoutMs) return fetch(path, options);
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  if (options.signal) {
    if (options.signal.aborted) controller.abort();
    else options.signal.addEventListener("abort", () => controller.abort(), { once: true });
  }
  try {
    return await fetch(path, { ...options, signal: controller.signal });
  } finally {
    window.clearTimeout(timeout);
  }
}

async function loadConfig() {
  const response = await fetchWithDeadline("/api/config");
  const config = await response.json();
  state.native = Boolean(config.native);
  state.elevated = Boolean(config.elevated);
  return config.token || "";
}

const configReady = (async () => {
  try {
    state.apiToken = await loadConfig();
  } catch {
    /* keep going; a protected request re-fetches the token (REL-009) */
  }
})();

/* REL-009: the token used to be fetched once. A restarted app has a new
   one, every protected call then failed with 403, and the live poll counted
   those as "TD Snap not found". Now a stale token is re-fetched once: if it
   was never loaded, the request is retried; if it changed, the app
   restarted, which is said plainly (state.appRestarted) instead. */
async function refreshToken() {
  const before = state.apiToken;
  try {
    const token = await loadConfig();
    if (!token) return "failed";
    state.apiToken = token;
    if (before && token !== before) {
      state.appRestarted = true;
      window.dispatchEvent(new CustomEvent("aac-app-restarted"));
      return "restarted";
    }
    return "loaded";
  } catch {
    return "failed";
  }
}

/* What kind of failure an error is, so callers stop guessing from text:
   timeout, unreachable, restarted, unauthorised, refused, failed. */
function typedError(message, kind, extra = {}) {
  const error = new Error(message);
  error.kind = kind;
  Object.assign(error, extra);
  return error;
}

/* Reading a whole page from TD Snap or Grid 3 walks every control on it, and
   a TD Snap page read may navigate to that page first; on a slow computer
   that can take well over ten seconds without anything being wrong. The quick
   "is it running?" checks keep the short deadline, so a hung app still says
   so promptly. */
const SLOW_READS = /^\/api\/(tdsnap\/(page-layout|vocabulary)|grid3\/(page-layout|probe)|diagnostics)\b/;

function defaultTimeout(path) {
  return SLOW_READS.test(path) ? LIVE_READ_TIMEOUT_MS : API_TIMEOUT_MS;
}

/* Requests the user is waiting on, as opposed to the background poll. The poll
   stands aside while any are in flight, so it can never be what a click waits
   behind. */
let foregroundRequests = 0;

function userRequestInFlight() {
  return foregroundRequests > 0;
}

async function api(path, options, timeoutMs = defaultTimeout(path)) {
  options = options || {};
  const background = Boolean(options.background);
  delete options.background;
  if (!background) foregroundRequests += 1;
  try {
    return await request(path, options, timeoutMs);
  } finally {
    if (!background) foregroundRequests -= 1;
  }
}

async function request(path, options, timeoutMs, retried = false) {
  await configReady;
  const headers = Object.assign(
    {},
    options.headers,
    state.apiToken ? { "X-TDSnap-Token": state.apiToken } : {}
  );
  const response = await fetchWithDeadline(path, { ...options, headers }, timeoutMs)
    .catch((error) => {
      if (error.name === "AbortError") {
        const timeout = typedError("The request took too long and was stopped.", "timeout");
        timeout.name = "TimeoutError";
        throw timeout;
      }
      throw typedError(
        "The local editor isn’t responding. Try again; if it continues, restart the app.",
        "unreachable",
      );
    });
  let data = null;
  try {
    data = await response.json();
  } catch {
    throw typedError(`Unexpected response from the app (${response.status}).`, "failed",
      { status: response.status });
  }
  if (response.status === 403 && data && data.code === "TOKEN_STALE" && !retried) {
    const refreshed = await refreshToken();
    const method = String(options.method || "GET").toUpperCase();
    // A read is safe to repeat; a write after a restart is not, because the
    // review it was built from belongs to the app that stopped.
    if (refreshed === "loaded" || (refreshed === "restarted" && method === "GET")) {
      return request(path, options, timeoutMs, true);
    }
    if (refreshed === "restarted") {
      throw typedError("AAC Editor restarted since this page was opened. Reload the page, "
        + "then review the edit again.", "restarted",
      { code: "TOKEN_STALE", outcome: "refused", status: 403 });
    }
  }
  if (!response.ok || data.ok === false) {
    const error = new Error(data.error || `Request failed (${response.status}).`);
    error.problems = data.problems || null;
    // Stable fields from the server (errors.py): what kind of failure, what
    // it means for the page, and the operation ID the user can quote.
    error.code = data.code || null;
    error.outcome = data.outcome || null;
    error.op = data.op || response.headers.get("X-AAC-Op") || null;
    error.status = response.status;
    error.kind = response.status === 403 ? "unauthorised"
      : response.status < 500 ? "refused" : "failed";
    noteFailure(path, error);
    throw error;
  }
  return data;
}

/* The last few failed requests, as codes and operation IDs only, for the
   support report (support.js). Never the message: a message can name a
   button or a page (REL-025). */
const MAX_RECENT_FAILURES = 10;

function noteFailure(path, error) {
  const route = path.split("?")[0].replace(/\/[A-Za-z0-9_-]{16,}(?=\/|$)/g, "/x")
    .replace(/\/\d+(?=\/|$)/g, "/x");
  state.recentFailures.push({
    at: new Date().toISOString(),
    route,
    status: error.status,
    code: error.code || "none",
    op: error.op || "none",
  });
  if (state.recentFailures.length > MAX_RECENT_FAILURES) state.recentFailures.shift();
}

export { api, configReady, fetchWithDeadline, refreshToken, userRequestInFlight };
