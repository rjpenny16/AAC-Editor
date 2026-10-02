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

let cache = null; // { preferences, draft, templates, folders } once the first load resolves
let loading = null; // in-flight GET, so concurrent first callers issue only one
let loaded = false; // a failed GET is not proof that nothing was saved
let lastWrite = Promise.resolve(); // preserve the order of autosaves and clears

function orderedWrite(operation) {
  const current = lastWrite.then(operation);
  lastWrite = current.catch(() => {});
  return current;
}

function loadSettings() {
  if (cache && loaded) return Promise.resolve(cache);
  if (!loading) {
    loading = api("/api/settings")
      .then((data) => {
        loaded = true;
        cache = {
          preferences: data.preferences || {},
          draft: data.draft || null,
          templates: data.templates || [],
          // Where the files are, so the panel can say so and a person can look.
          folders: { settings: data.folder || "", workingCopies: data.working_copies_folder || "" },
        };
        return cache;
      })
      .catch(() => {
        loading = null;
        if (!cache) cache = { preferences: {}, draft: null, templates: [], folders: {} };
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

async function getTemplates() {
  return (await loadSettings()).templates;
}

async function getFolders() {
  return (await loadSettings()).folders || {};
}

/* An unfinished page is somebody's own vocabulary, so it is kept on disk only if
   they asked for that. Anything but an explicit true means no. */
async function draftAutosaveOn() {
  return (await getPreferences()).draft_autosave === true;
}

/* Draft and preference writes omit templates so an autosave cannot erase a
   saved word list. */
async function writeSettings(update, includeTemplates = false, background = false) {
  await loadSettings();
  if (!loaded) return false;
  return orderedWrite(async () => {
    const next = update(cache);
    try {
      await api("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        background,
        body: JSON.stringify(includeTemplates
          ? { preferences: next.preferences, draft: next.draft, templates: next.templates }
          : { preferences: next.preferences, draft: next.draft }),
      });
      cache = next;
      return true;
    } catch {
      return false;
    }
  });
}

async function savePreference(key, value) {
  return writeSettings((data) => ({
    ...data, preferences: { ...data.preferences, [key]: value },
  }));
}

async function saveDraft(draft) {
  return writeSettings((data) => ({ ...data, draft }), false, true);
}

/* Save under *name*, replacing a template of the same name rather than
   silently keeping two — the user named it, and naming it again is how they
   say "this one, updated". */
async function saveTemplate(template) {
  const folded = template.name.toLocaleLowerCase();
  return writeSettings((data) => ({
    ...data,
    templates: [
      ...data.templates.filter((saved) => saved.name.toLocaleLowerCase() !== folded),
      template,
    ],
  }), true);
}

async function deleteTemplate(name) {
  const folded = String(name || "").toLocaleLowerCase();
  return writeSettings((data) => ({
    ...data,
    templates: data.templates.filter((saved) => saved.name.toLocaleLowerCase() !== folded),
  }), true);
}

async function clearDraft() {
  return saveDraft(null);
}

/* Resolves with what the server removed beyond the settings file: leftover
   working copies of page sets, and how many are still in use by an open one. */
async function clearAll() {
  await loadSettings();
  return orderedWrite(async () => {
    const reply = await api("/api/settings", { method: "DELETE" });
    cache = { preferences: {}, draft: null, templates: [], folders: cache ? cache.folders : {} };
    loaded = true;
    return {
      workingCopiesRemoved: Number(reply.working_copies_removed) || 0,
      workingCopiesOpen: Number(reply.working_copies_open) || 0,
    };
  });
}

function settingsReadSucceeded() {
  return loaded;
}

export {
  clearAll, clearDraft, deleteTemplate, draftAutosaveOn, getDraft, getFolders,
  getPreferences, getTemplates, saveDraft, savePreference, saveTemplate,
  settingsReadSucceeded,
};
