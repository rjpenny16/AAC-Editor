/* Wrapper around GET/PUT/DELETE /api/settings: remembered preferences and a
 * recoverable draft. Both live in one small local file the user can inspect
 * and clear from the Settings disclosure at any time.
 *
 * Nothing is written until something here is actually called to save — a
 * fresh install never triggers a PUT, so it never creates the file. Every
 * ordinary save is best-effort: a failed save is swallowed rather than surfaced,
 * because losing the *ability to resume later* must never block the work
 * happening right now.
 */

import { api } from "./api.js";

let cache = null; // { preferences, draft, templates } once the first load resolves
let loading = null; // in-flight GET, so concurrent first callers issue only one
let lastWrite = Promise.resolve(); // preserve the order of autosaves and clears

function orderedWrite(operation) {
  const current = lastWrite.then(operation);
  lastWrite = current.catch(() => {});
  return current;
}

/* A write that lands while the first GET is still in flight wins: what the
   user just chose is newer than what the file said when the page opened. */
function settle(loaded) {
  if (!cache) cache = loaded;
  return cache;
}

/* Reads go through the cache object, not the load promise: a write replaces
   `cache`, and a reader handed the settled promise would still be looking at
   what the GET returned — which is how a just-saved template would fail to
   appear in the list it was saved into. */
function loadSettings() {
  if (cache) return Promise.resolve(cache);
  if (!loading) {
    loading = api("/api/settings")
      .then((data) => settle({
        preferences: data.preferences || {},
        draft: data.draft || null,
        templates: data.templates || [],
      }))
      .catch(() => settle({ preferences: {}, draft: null, templates: [] }));
  }
  return loading;
}

async function getPreferences() {
  return (await loadSettings()).preferences;
}

async function getDraft() {
  return (await loadSettings()).draft;
}

async function getTemplates() {
  return (await loadSettings()).templates;
}

/* `templates` undefined means "leave the stored ones alone" — the server
   treats an absent key that way too, so the draft autosave running every few
   seconds can never wipe work the user deliberately saved. */
async function writeSettings(preferences, draft, templates, background = false) {
  const previous = cache;
  const updated = {
    preferences,
    draft,
    templates: templates === undefined ? (previous?.templates || []) : templates,
  };
  cache = updated;
  const body = JSON.stringify(
    templates === undefined
      ? { preferences, draft }
      : { preferences, draft, templates },
  );
  try {
    await orderedWrite(() => api("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      background,
      body,
    }));
    return true;
  } catch {
    if (cache === updated) cache = previous;
    return false;
  }
}

async function savePreference(key, value) {
  const data = await loadSettings();
  return writeSettings({ ...data.preferences, [key]: value }, data.draft);
}

async function saveDraft(draft) {
  const data = await loadSettings();
  return writeSettings(data.preferences, draft, undefined, true);
}

/* Save under *name*, replacing a template of the same name rather than
   silently keeping two — the user named it, and naming it again is how they
   say "this one, updated". */
async function saveTemplate(template) {
  const data = await loadSettings();
  const folded = template.name.toLocaleLowerCase();
  const rest = data.templates.filter(
    (saved) => saved.name.toLocaleLowerCase() !== folded,
  );
  return writeSettings(data.preferences, data.draft, [...rest, template]);
}

async function deleteTemplate(name) {
  const data = await loadSettings();
  const folded = String(name || "").toLocaleLowerCase();
  return writeSettings(
    data.preferences,
    data.draft,
    data.templates.filter((saved) => saved.name.toLocaleLowerCase() !== folded),
  );
}

async function clearDraft() {
  return saveDraft(null);
}

async function clearAll() {
  await loadSettings();
  const previous = cache;
  const cleared = { preferences: {}, draft: null, templates: [] };
  cache = cleared;
  try {
    await orderedWrite(() => api("/api/settings", { method: "DELETE" }));
    return true;
  } catch (error) {
    if (cache === cleared) cache = previous;
    throw error;
  }
}

export {
  clearAll, clearDraft, deleteTemplate, getDraft, getPreferences, getTemplates,
  saveDraft, savePreference, saveTemplate,
};
