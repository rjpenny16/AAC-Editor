/* AAC Editor frontend: wiring plus the workflow not yet extracted.
   Native ES modules, no bundler and no build step. */

import { state } from "./state.js";
import { $, setBusy, setActivity } from "./dom.js";
import { configReady, api } from "./api.js";
import { wireRadioGroups } from "./a11y.js";
import { renderWords } from "./chips.js";
import { selectProvider } from "./connect.js";
import { renderPreview } from "./preview.js";
import { hasUnsavedWork } from "./support.js";
import { show } from "./wizard.js";
// Side-effect imports: these wire their own listeners and export nothing
// anyone else calls, so without this they would never load.
import "./ai.js";
import "./review.js";


/* ---------- quit (browser mode) ---------- */

$("quit-btn").addEventListener("click", async () => {
  const warning = hasUnsavedWork()
    ? "Quit AAC Editor? The buttons you have planned but not yet added will be lost."
    : "Quit AAC Editor?";
  if (!window.confirm(warning)) return;
  state.leaving = true;
  setBusy($("quit-btn"), true, "Closing…");
  setActivity("Closing the local editor…");
  try {
    await api("/api/quit", { method: "POST" });
  } catch {
    /* the server may stop before the response arrives */
  }
  setActivity();
  setBusy($("quit-btn"), false);
  document.querySelector("main").hidden = true;
  document.querySelector("footer").hidden = true;
  $("quit-screen").hidden = false;
});

/* ---------- init ---------- */

configReady.then(() => {
  // In the native window the OS window close button quits the app;
  // in browser mode the Quit button is the only clean way to stop it.
  $("quit-btn").hidden = state.native;
  selectProvider(state.provider);
});


renderWords();
renderPreview();
show("load");

wireRadioGroups();
