/* First-run welcome, the one question it asks, and what the answer changes.
 *
 * The answer is a preference like any other: kept in the local settings file,
 * listed in "What AAC Editor saves", and cleared with everything else. It
 * shapes guidance only — which hints show, whether the tips card appears,
 * which optional panels start open. Every control exists at every level, no
 * review or confirmation step is ever skipped, and nothing here changes what
 * gets written to a page.
 */

import { state } from "./state.js";
import { $ } from "./dom.js";
import { getPreferences, savePreference } from "./settings.js";
import { show } from "./wizard.js";

const LEVELS = ["new", "some", "expert"];
const DEFAULT_LEVEL = "some";

let chosen = DEFAULT_LEVEL;
let tipsSeen = false;
// Where to go once the welcome is answered: the connect screen on first run,
// or back to wherever the person was when they reopened it from Help.
let returnTo = "connect";

function selectLevel(level) {
  chosen = LEVELS.includes(level) ? level : DEFAULT_LEVEL;
  document.querySelectorAll("#step-welcome [data-level]").forEach((card) => {
    const selected = card.dataset.level === chosen;
    card.classList.toggle("selected", selected);
    card.setAttribute("aria-checked", selected);
    card.tabIndex = selected ? 0 : -1;
  });
}

function renderTips(force = false) {
  const tips = $("workspace-tips");
  if (!tips) return;
  tips.hidden = !(force || (state.experience === "new" && !tipsSeen));
}

/* All tailoring lives here, so what each level does can be read in one place.
   A missing element is skipped, never an error. */
function applyProfile(level) {
  const experience = LEVELS.includes(level) ? level : DEFAULT_LEVEL;
  state.experience = experience;
  document.body.dataset.experience = experience;

  const connectionHelp = $("connection-help-details");
  if (connectionHelp && experience === "new") connectionHelp.open = true;

  // Suggestions are one click away for everyone; somebody who builds page
  // sets often is spared the click.
  const suggestions = $("ai-panel");
  if (suggestions && experience === "expert") suggestions.open = true;

  renderTips();
}

function openWelcome() {
  returnTo = state.wizardStep === "welcome" ? returnTo : state.wizardStep || "connect";
  selectLevel(state.experience || DEFAULT_LEVEL);
  show("welcome");
}

async function finishWelcome(level) {
  applyProfile(level);
  show(returnTo);
  await savePreference("experience", state.experience);
}

async function dismissTips() {
  tipsSeen = true;
  renderTips();
  $("word-input")?.focus();
  await savePreference("tips_seen", true);
}

/* Called once the saved preferences are known. Returns true when the
   welcome is showing, so start-up leaves the first screen to it. */
async function startOnboarding({ linked = false } = {}) {
  const preferences = await getPreferences();
  tipsSeen = preferences.tips_seen === true;
  const known = LEVELS.includes(preferences.experience);
  applyProfile(known ? preferences.experience : DEFAULT_LEVEL);
  // A link that names an app already knows where it is going.
  if (known || linked) return false;
  returnTo = "connect";
  selectLevel(DEFAULT_LEVEL);
  show("welcome");
  return true;
}

document.querySelectorAll("#step-welcome [data-level]").forEach((card) => {
  card.addEventListener("click", () => selectLevel(card.dataset.level));
});
$("welcome-start-btn").addEventListener("click", () => finishWelcome(chosen));
$("welcome-skip-btn").addEventListener("click", () => finishWelcome(DEFAULT_LEVEL));
$("tips-dismiss").addEventListener("click", dismissTips);

function closeHelpMenu() {
  $("help-menu").open = false;
}

$("help-level-btn").addEventListener("click", () => {
  closeHelpMenu();
  openWelcome();
});
$("help-tour-btn").addEventListener("click", () => {
  closeHelpMenu();
  if (state.wizardStep === "items") {
    renderTips(true);
    $("workspace-tips").scrollIntoView({ block: "nearest" });
    $("tips-heading").tabIndex = -1;
    $("tips-heading").focus();
    return;
  }
  // Before connecting there is no workspace to point at; the connect screen's
  // own help is the relevant part.
  if (state.wizardStep === "connect") {
    $("connection-help-details").open = true;
    $("connection-help-details").querySelector("summary").focus();
    return;
  }
  openWelcome();
});
document.addEventListener("click", (event) => {
  if ($("help-menu").open && !$("help-menu").contains(event.target)) closeHelpMenu();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && $("help-menu").open) {
    closeHelpMenu();
    $("help-menu").querySelector("summary").focus();
  }
});

export { applyProfile, openWelcome, startOnboarding };
