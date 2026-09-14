/* Reusable topic templates: build a page once, use it for anyone.
 *
 * This is the caseload win the roadmap is named for. An SLP who has built a
 * good Swimming topic page — the right phrases, in the right communicative
 * rows, in a layout that works — currently rebuilds it by hand for the next
 * client, and the next. A template is that work, named and kept, applied to
 * any page set afterwards.
 *
 * What a template is: labels, spoken messages, topic-page rows, symbol search
 * words, and the page style they were composed for. What it is deliberately
 * *not*: anything tied to one page set. No page ids, no fingerprints, no
 * client's name — a template is vocabulary, and vocabulary is the part that
 * transfers.
 *
 * Applying one fills the same state.words the chip box fills, so it goes
 * through the same capacity check, the same review, and the same confirm step
 * as anything typed by hand. A template can never write to a page set.
 */

import { state, FUNCTIONS } from "./state.js";
import { $, appendNamedList } from "./dom.js";
import { firstAvailableSlot, pageCapacity, renderWords } from "./chips.js";
import { titleOf } from "./parents.js";
import { deleteTemplate, getTemplates, saveTemplate } from "./settings.js";
import { setPageStyle } from "./wizard.js";

const dialog = $("templates-dialog");

function setHint(message, isError = false) {
  const hint = $("template-save-hint");
  hint.textContent = message || "";
  hint.classList.toggle("error", Boolean(isError));
}

function summarize(node) {
  const summary = $("template-summary");
  summary.innerHTML = "";
  summary.hidden = !node;
  if (node) summary.append(node);
}

/* ---------- opening ---------- */

async function openTemplates() {
  $("template-name").value = "";
  setHint(
    state.words.length
      ? `${state.words.length} button${state.words.length === 1 ? "" : "s"} ready to save.`
      : "Add some words first, then come back to save them as a template.",
  );
  summarize(null);
  await renderTemplateList();
  dialog.showModal();
  $("template-name").focus();
}

$("templates-btn").addEventListener("click", openTemplates);

/* ---------- saving ---------- */

$("template-save-btn").addEventListener("click", async () => {
  const name = $("template-name").value.trim();
  if (!name) {
    setHint("Give the template a name so you can find it later.", true);
    $("template-name").focus();
    return;
  }
  if (!state.words.length) {
    setHint("There are no buttons to save yet.", true);
    return;
  }
  const saved = await saveTemplate({
    name,
    page_style: state.pageStyle,
    saved_at: Math.floor(Date.now() / 1000),
    items: state.words.map((item) => ({
      label: item.label,
      message: item.message,
      fn: item.fn || "",
      slot: Number.isInteger(item.slot) ? item.slot : null,
      symbol: item.symbol !== false,
      symbol_query: item.symbolQuery || null,
    })),
  });
  if (!saved) {
    setHint("That template could not be saved on this computer.", true);
    return;
  }
  $("template-name").value = "";
  setHint(`Saved “${name}”. It is kept on this computer only.`);
  await renderTemplateList();
});

/* ---------- the list ---------- */

async function renderTemplateList() {
  const list = $("template-list");
  list.innerHTML = "";
  const templates = await getTemplates();
  if (!templates.length) {
    const empty = document.createElement("li");
    empty.className = "template-empty";
    empty.textContent = "No templates saved yet.";
    list.append(empty);
    return;
  }
  [...templates]
    .sort((left, right) => left.name.localeCompare(right.name))
    .forEach((template) => {
      const row = document.createElement("li");
      const name = document.createElement("strong");
      name.textContent = template.name;
      const detail = document.createElement("span");
      const count = template.items.length;
      detail.textContent =
        `${count} button${count === 1 ? "" : "s"} · ` +
        (template.page_style === "topic" ? "topic-page rows" : "standard buttons");
      const use = document.createElement("button");
      use.type = "button";
      use.className = "btn btn-secondary btn-compact";
      use.textContent = "Use";
      use.setAttribute("aria-label", `Use template ${template.name}`);
      use.addEventListener("click", () => applyTemplate(template));
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "btn btn-ghost btn-compact";
      remove.textContent = "Delete";
      remove.setAttribute("aria-label", `Delete template ${template.name}`);
      remove.addEventListener("click", async () => {
        await deleteTemplate(template.name);
        setHint(`Deleted “${template.name}”.`);
        await renderTemplateList();
      });
      row.append(name, detail, use, remove);
      list.append(row);
    });
}

/* ---------- applying ---------- */

/* A template is added to what is already there rather than replacing it, and
   what does not fit is named. The slots it was saved with are a preference,
   not a promise: a template built on an 8×5 grid applied to a 4×3 page keeps
   its words and takes whatever cells are actually free. */
function applyTemplate(template) {
  const style = template.page_style === "topic" ? "topic" : "words";
  if (style !== state.pageStyle) setPageStyle(style);

  const present = new Set([
    ...state.existingButtons.map((button) => String(button.label || "").toLocaleLowerCase()),
    ...state.words.map((item) => item.label.toLocaleLowerCase()),
  ]);
  const duplicates = [];
  const overflow = [];
  const added = [];
  const total = state.grid.cols * state.grid.rows;

  template.items.forEach((item) => {
    const folded = item.label.toLocaleLowerCase();
    if (present.has(folded)) {
      duplicates.push(item.label);
      return;
    }
    if (state.words.length >= pageCapacity()) {
      overflow.push(item.label);
      return;
    }
    present.add(folded);
    const fn = state.pageStyle === "topic" && item.fn in FUNCTIONS ? item.fn : "";
    // Keep the saved cell when this page has it free; otherwise take the next
    // one, which is what firstAvailableSlot already decides for a typed word.
    const wanted = Number.isInteger(item.slot) && item.slot < total ? item.slot : null;
    const free = wanted !== null && !state.words.some((word) => word.slot === wanted)
      && !state.existingButtons.some((button) => button.slot === wanted);
    state.words.push({
      label: item.label,
      message: item.message || null,
      fn,
      slot: free ? wanted : firstAvailableSlot(fn),
      symbol: item.symbol !== false,
      symbolQuery: item.symbol_query || null,
    });
    added.push(item.label);
  });

  state.pendingEdit = null;
  renderWords();

  const report = document.createElement("div");
  const lead = document.createElement("strong");
  lead.textContent = added.length
    ? `Added ${added.length} button${added.length === 1 ? "" : "s"} from “${template.name}”.`
    : `Nothing from “${template.name}” could be added.`;
  report.append(lead);
  const page = titleOf(state.parentId);
  if (duplicates.length) {
    appendNamedList(report, `Already on ${page}, so not added:`, duplicates);
  }
  if (overflow.length) {
    appendNamedList(report, `${page} does not have room for:`, overflow);
  }
  summarize(report);
}

export { openTemplates };
