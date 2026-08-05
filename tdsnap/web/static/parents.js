/* Choosing which page the new buttons land on.
 *
 * Includes the placement suggestion: a small token-overlap score against a
 * curated set of AAC page groupings. It only ever suggests — the user picks.
 */

import { state } from "./state.js";
import { $ } from "./dom.js";
import { api } from "./api.js";
import { loadTargetLayout } from "./connect.js";
import { renderPreview } from "./preview.js";
import { showBuildError } from "./wizard.js";

/* ---------- step 2: parent picker ---------- */

const parentSelect = $("parent-select");
const parentFilter = $("parent-filter");

parentFilter.addEventListener("input", () => renderParents(parentFilter.value));
$("parent-filter-clear").addEventListener("click", () => {
  parentFilter.value = "";
  renderParents("");
  parentFilter.focus();
});

parentSelect.addEventListener("change", async () => {
  state.parentId = parentSelect.value;
  state.parentTouched = true;
  state.parentFree = null;
  if (state.operation === "existing") {
    try {
      await loadTargetLayout(titleOf(state.parentId));
    } catch (error) {
      showBuildError("Couldn’t load the selected TD Snap page.", [error.message]);
    }
  } else {
    try {
      await loadParentCapacity();
    } catch (error) {
      showBuildError("Couldn’t check the selected parent page.", [error.message]);
    }
  }
});

function titleOf(pageId) {
  const page = state.pages.find((p) => p.id === pageId);
  return page ? page.title : `Page ${pageId}`;
}

async function loadParentCapacity() {
  if (!state.parentId || state.operation !== "new") return null;
  const requestedId = String(state.parentId);
  state.parentFree = null;
  parentSelect.disabled = true;
  $("parent-capacity").classList.remove("error");
  $("parent-capacity").textContent = `Checking space on “${titleOf(state.parentId)}”…`;
  try {
    let free;
    if (state.mode === "file") {
      const data = await api(
        `/api/pageset/${encodeURIComponent(state.sessionId)}/page/` +
        `${encodeURIComponent(state.parentId)}/capacity`
      );
      free = Number(data.free_cells);
    } else {
      const data = await api(
        `/api/tdsnap/page-layout?page=${encodeURIComponent(titleOf(state.parentId))}`
      );
      free = Array.isArray(data.free_slots) ? data.free_slots.length : 0;
    }
    if (String(state.parentId) !== requestedId) return null;
    state.parentFree = Number.isFinite(free) && free >= 0 ? free : 0;
    $("parent-capacity").classList.toggle("error", state.parentFree === 0);
    $("parent-capacity").textContent = state.parentFree
      ? `${state.parentFree} empty space${state.parentFree === 1 ? "" : "s"} on ` +
        `“${titleOf(state.parentId)}” for the new page button.`
      : `“${titleOf(state.parentId)}” is full. Choose another page or remove a button first.`;
    return state.parentFree;
  } catch (error) {
    if (String(state.parentId) === requestedId) {
      state.parentFree = null;
      $("parent-capacity").classList.add("error");
      $("parent-capacity").textContent = "Capacity could not be checked.";
    }
    throw error;
  } finally {
    parentSelect.disabled = false;
  }
}

const AAC_PAGE_GROUPS = [
  { words: ["food", "snack", "drink", "meal", "eat"], pages: ["eating", "cooking", "restaurant"] },
  { words: ["game", "play", "toy", "minecraft"], pages: ["games", "toy play", "minecraft"] },
  { words: ["family", "mom", "dad", "sister", "brother", "friend", "people"], pages: ["my family", "about me"] },
  { words: ["school", "class", "teacher", "lesson", "learn"], pages: ["classroom", "reading"] },
  { words: ["feel", "body", "health", "doctor", "appointment"], pages: ["self care", "body safety", "appointment"] },
  { words: ["music", "song", "sing", "instrument"], pages: ["music"] },
  { words: ["sport", "ball", "team", "exercise"], pages: ["sports"] },
  { words: ["shop", "buy", "store", "money"], pages: ["shopping"] },
  { words: ["car", "bus", "train", "travel", "ride"], pages: ["transportation", "community"] },
  { words: ["art", "draw", "paint", "craft", "create"], pages: ["art"] },
  { words: ["book", "story", "read"], pages: ["reading"] },
  { words: ["joke", "funny", "laugh"], pages: ["jokes"] },
];

function tokens(text) {
  const found = String(text || "").toLowerCase().match(/[a-z0-9]+/g) || [];
  const normalized = new Set(found);
  found.forEach((word) => {
    if (word.length > 3 && word.endsWith("s")) normalized.add(word.slice(0, -1));
  });
  return normalized;
}

function recommendParent(title) {
  const wanted = tokens(title);
  if (!wanted.size || !state.pages.length) return state.currentPage || state.pages[0].id;
  let best = null;
  state.pages.forEach((page) => {
    const pageTokens = tokens(page.title);
    let score = [...wanted].filter((token) => pageTokens.has(token)).length * 8;
    AAC_PAGE_GROUPS.forEach((group) => {
      const queryMatches = group.words.some((word) => wanted.has(word));
      const pageMatch = group.pages.findIndex((name) =>
        page.title.toLowerCase().includes(name)
      );
      if (queryMatches && pageMatch >= 0) score += 6 + group.pages.length - pageMatch;
    });
    if (page.id === state.currentPage && page.title !== "Topics Menu Page") score += 2;
    if (/^your topic \d+$/i.test(page.title)) score -= 4;
    if (!best || score > best.score) best = { id: page.id, title: page.title, score };
  });
  if (best && best.score > 0) return best.id;
  return (state.pages.find((page) => page.id === state.currentPage) || state.pages[0]).id;
}

function updatePlacementRecommendation() {
  const recommendation = recommendParent($("title-input").value);
  state.recommendedParent = recommendation;
  let title = titleOf(recommendation);
  const hasName = Boolean($("title-input").value.trim());
  $("placement-title").textContent = hasName ? `Suggested location: ${title}` : "AAC-friendly placement";
  $("placement-copy").textContent = hasName
    ? `The new ${$("title-input").value.trim()} button will be added to ${title}. ` +
      "Choose another page if that isn’t where you want it."
    : "Name the page above and the app will suggest an existing location, keeping related vocabulary together.";
  if (!state.parentTouched && recommendation) {
    state.parentId = recommendation;
    state.parentFree = null;
    renderParents(parentFilter.value);
    title = titleOf(state.parentId);
    $("parent-capacity").textContent =
      `Space on “${title}” will be checked before continuing.`;
  }
  $("use-placement").hidden = !hasName || state.parentId === recommendation;
}

$("title-input").addEventListener("input", () => {
  updatePlacementRecommendation();
  renderPreview();
});
$("use-placement").addEventListener("click", () => {
  state.parentId = state.recommendedParent;
  state.parentFree = null;
  state.parentTouched = false;
  parentFilter.value = "";
  renderParents("");
  updatePlacementRecommendation();
});

function renderParents(filter) {
  const query = filter.trim().toLowerCase();
  parentSelect.innerHTML = "";
  const matches = state.pages.filter(
    (page) => !query || page.title.toLowerCase().includes(query)
  );
  const selected = state.pages.find((page) => page.id === state.parentId);
  if (selected && !matches.includes(selected)) matches.unshift(selected);
  parentSelect.size = query ? Math.min(Math.max(matches.length, 2), 6) : 1;
  matches
    .forEach((page) => {
      const option = document.createElement("option");
      option.value = page.id;
      option.textContent = page.title;
      if (page.id === state.parentId) option.selected = true;
      parentSelect.append(option);
    });
  if (!parentSelect.options.length) {
    const option = document.createElement("option");
    option.disabled = true;
    option.textContent = "No pages match";
    parentSelect.append(option);
  }
}

export { loadParentCapacity, parentFilter, parentSelect, renderParents, titleOf, updatePlacementRecommendation };
