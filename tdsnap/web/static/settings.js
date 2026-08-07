/* Wrapper around GET/PUT/DELETE /api/settings: remembered preferences and a
 * recoverable draft. Both live in one small local file the user can inspect
 * and clear from the Settings disclosure at any time.
 *
 * Nothing is written until something here is actually called to save — a
 * fresh install never triggers a PUT, so it never creates the file. Every
 * write is best-effort: a failed save is swallowed rather than surfaced,
 * because losing the *ability to resume later* must never block the work
 * happening right now.
 */

import { api } from "./api.js";

let cache = null; // { preferences, draft } once the first load resolves
let loading = null; // shared in-flight/resolved load, so concurrent callers issue one GET

function loadSettings() {
  if (!loading) {
    loading = api("/api/settings")
      .then((data) => {
        cache = { preferences: data.preferences || {}, draft: data.draft || null };
        return cache;
      })
      .catch(() => {
        cache = { preferences: {}, draft: null };
        return cache;
      });
  }
  return loading;
}

async function getPreferences() {
  return (await loadSettings()).preferences;
}

async function getDraft() {
  return (await loadSettings()).draft;
}

async function writeSettings(preferences, draft) {
  cache = { preferences, draft };
  try {
    await api("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ preferences, draft }),
    });
    return true;
  } catch {
    return false;
  }
}

async function savePreference(key, value) {
  const data = await loadSettings();
  return writeSettings({ ...data.preferences, [key]: value }, data.draft);
}

async function saveDraft(draft) {
  const data = await loadSettings();
  return writeSettings(data.preferences, draft);
}

async function clearDraft() {
  return saveDraft(null);
}

async function clearAll() {
  cache = { preferences: {}, draft: null };
  loading = Promise.resolve(cache);
  try {
    await api("/api/settings", { method: "DELETE" });
    return true;
  } catch {
    return false;
  }
}

export { clearAll, clearDraft, getDraft, getPreferences, saveDraft, savePreference };
