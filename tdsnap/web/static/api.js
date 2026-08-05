/* Every call to the local server goes through here.
 *
 * The per-run API token is fetched once and awaited by every request, so a
 * fast first click cannot race the config response and get a 403. Errors are
 * normalized into something a clinician can act on rather than a status code.
 */

import { state, API_TIMEOUT_MS } from "./state.js";

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

const configReady = (async () => {
  try {
    const response = await fetchWithDeadline("/api/config");
    const config = await response.json();
    state.apiToken = config.token || "";
    state.native = Boolean(config.native);
    state.elevated = Boolean(config.elevated);
  } catch {
    /* keep going; the server will reject protected POSTs if it is older */
  }
})();

async function api(path, options, timeoutMs = API_TIMEOUT_MS) {
  await configReady;
  options = options || {};
  options.headers = Object.assign(
    {},
    options.headers,
    state.apiToken ? { "X-TDSnap-Token": state.apiToken } : {}
  );
  const response = await fetchWithDeadline(path, options, timeoutMs).catch((error) => {
    if (error.name === "AbortError") {
      const timeout = new Error("The request took too long and was stopped.");
      timeout.name = "TimeoutError";
      throw timeout;
    }
    throw new Error("The local editor isn’t responding. Try again; if it continues, restart the app.");
  });
  let data = null;
  try {
    data = await response.json();
  } catch {
    throw new Error(`Unexpected response from the app (${response.status}).`);
  }
  if (!response.ok || data.ok === false) {
    const error = new Error(data.error || `Request failed (${response.status}).`);
    error.problems = data.problems || null;
    throw error;
  }
  return data;
}

export { fetchWithDeadline, configReady, api };
