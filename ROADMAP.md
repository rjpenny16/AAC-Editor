# AAC Editor — Roadmap (post-2.2.0)

## Why this document exists

AAC Editor 2.2.0 is a Windows-first tool that edits AAC page sets **in place** —
through TD Snap's and Grid 3's own accessibility surfaces — so a page set keeps its sharing and sync
identity instead of being round-tripped through an export.

Until now, all product intent lived in one negative-space paragraph of the README's Grid 3 section.
This document replaces that with an explicit, ordered plan. Each phase is independently shippable
and unblocks the next.

## Where the project stands

The foundations are solid and should not be re-litigated: three write paths behind one canonical
item model, review-before-write, layout fingerprinting, automatic rollback, 437 Python tests, 111
Playwright tests and 53 frontend unit tests, a five-job CI matrix, axe-checked end-to-end coverage,
and a release pipeline that installs, health-checks, and attests every build. There are no TODO/FIXME markers in the tree.

The gaps are elsewhere. Three were serious; one still is:

1. ~~**A browser refresh silently destroys unsaved work.**~~ *Closed in Phase 2. A `beforeunload`
   guard covers anything composed but not applied, and the in-progress item list is autosaved to the
   opt-in settings file and offered back on the next launch.* One thing is deliberately excluded: the
   Phase 5 multi-page queue is guarded but not autosaved, because its entries hold live TD Snap
   fingerprints that a relaunch invalidates — see Phase 5.
2. ~~**The app is add-only.**~~ *Closed across Phase 4. TD Snap live can change, move, swap, and
   remove a speaking button; an applied edit can be undone once, through the same review step; and
   exported files add to an existing page rather than only creating one. Symbol control landed as
   control over the search rather than the pick — see 4c for why the accessibility surface stops it
   there.*
3. **`live.py` and `grid3.py` each carry their own copy of the UI-Automation helper layer.** Twelve
   identically-named functions exist in both files and have already diverged in behaviour. Building
   Grid 3 parity on top of that multiplies the divergence.

Alongside those, three items on this list have since been dealt with: the orphaned installer images
were removed, and ESLint, Stylelint, a Prettier config, and a `node --test` unit suite now cover the
frontend. The app is still English-only, in a field where bilingual families are the norm.

## Direction

| Question | Decision |
|---|---|
| Priority | Editing depth first, then AI control, onboarding, and reach |
| Persistence | Opt-in local JSON file, user-visible, with a clear-all control |
| Primary audience | SLPs and other professionals working at caseload scale |
| `app.js` (2474 lines) | Split into native ES modules first; no build step added |

---

# Track A — Stabilize

## Phase 0 — Stop the bleeding *(~1 week)*

Cheap, high-impact, largely independent of everything else.

1. **`beforeunload` guard.** Warn before unload when the item list is non-empty or an edit is
   mid-review. Removes the worst failure mode in the product.
2. **Global JS error surface.** There is no `window.onerror`, no `unhandledrejection` handler, and
   no logging anywhere in the frontend — an unexpected exception mid-wizard produces total silence
   for a user who is a clinician, not an engineer. Add both handlers feeding a visible in-app
   message. Audit the nine empty `catch {}` blocks while there; most are deliberate, but the one
   around session close silently leaks a temp directory until the 24-hour sweep.
3. **Delete orphaned assets.** `static/assets/walkthrough-guide.png` (748 KB) and
   `walkthrough-lead.png` (734 KB) have been unreferenced since the walkthrough redesign but still
   ship in the wheel, the PyInstaller bundle, and the installer. Also replace `aac-editor-logo.png`
   — a 291 KB PNG rendered at 32 px — with an SVG or small WebP.
4. **Support diagnostics.** A "Copy a support report" action: app version, OS build, detected
   TD Snap/Grid 3 version, AI engine state, last error, UIA probe result. Show the text before
   copying; clipboard only, never a network call. `grid3._file_version` and `live._process_app_id`
   already gather most of it.
5. **README truth-up.** Remove the guided/compact setup claim; Phase 7 earns it back.
6. **Add `CHANGELOG.md`.** The release workflow already requires a version-matched tag; the
   changelog is the missing half.
7. **Merge the open Dependabot PRs.**

**Exit:** a refresh can no longer silently destroy work · a JS exception produces a visible message ·
the installer sheds ~1.7 MB · the README matches reality · users can paste a diagnostic block into
an issue.

---

## Phase 1 — Quality gates and front-end decomposition *(~2 weeks)*

`app.js` is 2474 lines with no static analysis and one global object that all 54 of its functions can
read and write. `resetConnection()` manually nulls 13 fields and 8 DOM nodes; forgetting one is a
silent bug class. Every phase below pays a tax against this.

**Tooling that does not exist yet:** ESLint, Prettier, `.editorconfig`, Stylelint, a Python type
checker, and pre-commit hooks. Ruff currently runs only its minimal default rule set — add `I`, `B`,
`UP`, `SIM`, `RUF`, and `S`; `B` and `S` are the high-value pair for a file-mutating application. The
codebase is half-annotated with nothing verifying it, so add mypy or pyright in non-strict mode over
the annotated modules first.

**Decide on Python 3.9.** `requires-python` is `>=3.9` while CI tests through 3.14. Dropping 3.9
unlocks PEP 604 unions and `match`, and lets ruff's `UP` rules do real work. The packaged executable
bundles its own interpreter, so this only affects `pip install` users.

**Split `app.js` into native ES modules** (`<script type="module">`, no bundler, no framework — the
zero-JS-build property is worth keeping and PyInstaller packaging stays untouched):

`state.js` · `api.js` · `wizard.js` · `chips.js` · `preview.js` · `ai.js` · `review.js` · `a11y.js` ·
`strings.js` · `app.js` (wiring only).

Break up the five largest functions while splitting: `uploadPageset()` at 178 lines,
`showReviewError()` 152, `renderResult()` 149, `trackDownload()` 122, `renderPreview()` 114.

> **`strings.js` matters more than it looks.** Centralizing user-facing copy now makes Phase 8's
> internationalization mechanical instead of a full-app sweep, at almost no extra cost during a split
> that already touches every string.

**A packaging trap that hides itself.** `pyproject.toml` declares package data as
`["static/*", "static/assets/*"]`. Flat modules in `static/` are covered; a `static/js/`
subdirectory is not — `pip install .` would 404 them, while a source checkout works *and* the
PyInstaller spec copies the whole `static` tree so the packaged executable also works. That
combination hides the break from every local test. Keep modules flat or widen the glob, and add a
test asserting every import target resolves in the *installed* package.

**JavaScript unit tests** under `tests/js/`, run in the existing `browser` CI job. All pure, all
currently untested: `inferPhraseFunction`, `topicRowFunctions`, `firstAvailableSlot`, `tokens`, and
the parent-suggestion scorer.

**Accessibility and performance, while these files are already open:**

- **Dark mode.** `color-scheme: light` is hardcoded and `prefers-color-scheme` is never queried.
  Light sensitivity is common in this user population and TD Snap itself ships dark themes. Add
  `prefers-contrast` handling too.
- **Extend axe past the first screen.** Only the initial wizard is scanned. The chip-editor
  `<dialog>` — a modal containing a destructive "Remove button" — is never scanned and its focus trap
  is never asserted. Add the placement grid, review screen, and result screen.
- **Stop rebuilding the whole preview on every interaction.** `renderWords()` is called from 16 sites
  and unconditionally rebuilds every preview cell, reattaching roughly four listeners per cell. Key
  the cells and diff, or at minimum use event delegation.
- **Pause the 750 ms live poll when the document is hidden.** It currently runs indefinitely with no
  backoff.
- **Raise coverage floors.** Global 55 → 65, *plus per-module floors on the write path*
  (`builder.py`, `validate.py`, `templates.py`, `schema.py`). A single global number lets
  safety-critical code hide behind well-tested helpers.
- **Add a WebView2/Edge Playwright project.** The suite runs chromium-only on Linux; the product
  ships Windows-first inside WebView2.

**Exit:** no source file over ~400 lines · all linters, formatters, and the type checker green in CI
and pre-commit · JS unit tests running · axe covers every screen and the dialog · both `pip install .`
and the packaged executable serve every module · coverage floor 65.

---

# Track B — Don't lose work, and stop the divergence

## Phase 2 — Never lose work *(~2 weeks)*

Phase 0 added the guard rail; this phase adds the safety net. It also delivers the opt-in storage
that Phases 5 and 7 depend on.

- **Opt-in settings store.** One `settings.json` in the app-data directory the model downloader
  already uses, carrying a `version` field. **Written only when the user saves something** — a fresh
  install has no file. `GET`/`PUT`/`DELETE /api/settings` behind the same API-token, loopback-host,
  and custom-header guards as every other mutation. Atomic temp-then-`os.replace`, mirroring
  `Pageset.save_as`. A corrupt file is renamed aside and the app starts clean.
- **Draft autosave and recovery.** Persist the in-progress item list, layout, and placements; on
  launch offer *"You have an unfinished page for Snacks — resume or discard?"*
- **Remember preferences.** Provider choice, Ollama host and model, AI preference — currently
  re-entered every launch.
- **In-composition undo.** Removing a chip has no restore path, and "Arrange automatically" re-flows
  every phrase irreversibly. Add an undo stack for the composition step.
- **Session survivability.** Server sessions live in a process-memory dict, so a Flask restart —
  crash, port conflict, or a launcher killing a stale instance — turns every open exported-file
  session into "Unknown or expired session; re-upload the file." Reconstruct from the on-disk session
  directory instead.
- **A Settings disclosure** listing everything stored in plain language, plus **Clear all saved
  data**. The README's "Private by design" section gains one honest paragraph.

**Exit:** a fresh install writes nothing until the user saves · an interrupted session is recoverable
· stored contents are viewable and deletable in-app · a corrupt file never blocks startup · a server
restart does not orphan an upload.

---

## Phase 3 — Shared UIA core *(~1–2 weeks)*

A pure refactor with no new user-facing behaviour, and a hard prerequisite for Phases 4 and 10.

`grid3.py` imports only two helpers from `live.py` and reimplements the rest. Twelve identically-named
functions exist in both files — `_activate`, `_automation`, `_clusters`, `_fingerprint`, `_grid`,
`_verify_process`, `_wait_for`, `_walk`, `_window`, `add_to_existing_page`, `inspect_page`, `status`
— and they have already diverged:

| Helper | `live.py` | `grid3.py` |
|---|---|---|
| `_walk` | `max_depth=9` | `max_depth=10`, plus try/except around `GetChildren()` |
| `_clusters` | `tolerance=8`, `statistics.mean` | `tolerance=6`, hand-rolled `sum()/len()` |
| `_activate` | retries `Invoke()` for 30 s against transient `UIA_E_ELEMENTNOTENABLED` | single `Invoke()`, `Click()` fallback, **no retry** |

Extract `tdsnap/uia.py` and **reconcile each divergence deliberately** — choose the correct depth,
tolerance, and retry policy, write a test pinning each choice, and record the reasoning in the module
docstring. Do not merge by taking whichever came first.

Two further single-source-of-truth fixes belong here:

- **The phrase classifier is implemented twice, in two languages, line for line.** The Python and
  JavaScript versions mirror five regexes and identical branch ordering, with nothing asserting they
  agree — any vocabulary change must be made twice by hand. Serve one word list from a single place,
  or add a golden-case test run against both implementations.
- **The clinical colour convention is browser-controlled.** The five function colours live in the
  frontend, are POSTed as `border_color`, and the server converts whatever arrives. Add a server-side
  allowlist: question/comment/positive/negative/personal colour coding is a clinical convention, not
  a UI preference.

**Exit:** one UIA helper module · every reconciled divergence has a test pinning the choice · the
phrase classifier has one source of truth · function colours are validated server-side · live and
Grid 3 end-to-end suites pass unchanged on real hardware.

---

# Track C — Capability

## Phase 4 — Editing depth *(~5–7 weeks, three milestones)*

The largest gap between what users need and what the app does. It reuses the safety machinery already
built; the server currently answers anything but `add_to_existing_page` with *"This edit operation is
not supported yet."*

### 4a — Change and remove (TD Snap live) — **shipped**

Landed as one `apply_page_edits(page, items, changes, removals, fingerprint)` spine rather than two
separate operations, so a single review, fingerprint guard, edit-mode session, and rollback covers an
edit that adds, changes, and removes at once — removals first, since they free the cells an addition
may have been placed in. `_verify_added_buttons` became `_verify_page_state` (added, changed,
removed, *and* the cells the edit never named), and `_restore_page_fingerprint` became a thin wrapper
over the content-aware `_restore_page_state`. Eligibility and prior content are read from the page
set's stored command sequences, because the accessibility tree renders a page link and a speaking
button identically. Still outstanding for this milestone: the `TDSNAP_LIVE_E2E=1` run on real
hardware, which is the only thing that can confirm the delete-action discovery against a live TD Snap
editing panel.

> **The new danger.** Every operation to date has been additive, so rollback could mean *"undo until
> the page matches the pre-edit fingerprint."* Destructive edits need the **content** captured too:
> snapshot the label, message, symbol, and border of every touched cell before the edit so rollback
> can restore it — and refuse the edit outright if that snapshot cannot be read. This is the single
> most important correctness requirement in this roadmap.

Guardrails: never touch the excluded groups (Message Bar, Tool Bar); never touch a button whose
command sequence is not a plain speak. Navigation, action, and system buttons stay locked and say why
on hover and focus.

The preview already renders existing buttons as locked. Make eligible ones selectable, open the
existing chip-editor dialog pre-filled, and give removals their own review card naming every button,
so the confirm button reads e.g. *"Change 2 and remove 1 button on Snacks."* New verification checks:
changed buttons say what was asked · removed buttons are gone · nothing else on the page changed.

### 4b — Undo my last change — **shipped**

The edit that would reverse the last applied one is retained for the session and offered as a
single-level **"Undo my last change"** that replays through the same `apply_page_edits` spine — the
same review, fingerprint guard, edit-mode session, verification, and rollback as any other edit. The
fingerprint recorded is the page's token *after* the edit, so the ordinary guard refuses the replay the
moment anything else touches the page, a TD Snap sync included.

Three limits, each stated in the UI rather than discovered: this process and this session only (never
persisted — a snapshot that outlived a restart could not know whether TD Snap had synced); one level
(undoing does not become undoable); and a re-created button is a new button, so its symbol comes from a
fresh search and a border color outside the five clinical colors cannot be written back. The last two
are named on the review screen before the undo runs.

One deliberate departure from the plan above: the snapshot lives in the server process rather than the
browser, because `_prior_content` is what has to trust it. The frontend renders the description the
server hands it and asks for the replay; it never holds the restoration data itself.

### 4c — Move, reorder, and symbol control — **shipped**

- **Move and swap existing buttons.** Unlocked existing buttons are movable in the placement editor by
  drag and by arrow key, and dropping one on another trades their places. Moves travel as
  `moves: [{slot, to}]` in the same reviewed edit, verified in both cells.

  TD Snap exposes no "put this button in that cell" command, so a move is a real drag — and only ever
  onto a cell that is empty, because what TD Snap does when a button is dropped onto an occupied one is
  not predictable from its accessibility surface. A swap is therefore built from that one primitive:
  park one button in a spare cell, move the other, collect the first (`_move_order`, which breaks
  longer rings the same way). A page with no spare cell refuses the swap by name.
- **Symbol control** — *partially delivered; the gap is the accessibility surface, not the work.*
  Per-button **skip** and per-button **search words** shipped (a phrase button labelled "more please"
  can search "more"), and the result now names which buttons ended up without a symbol and which used a
  web image instead of TD Snap's own library.

  **Picking from the candidates did not ship.** TD Snap's symbol-search results expose neither readable
  names nor images through UI Automation — the result list is matched on a control-type string alone —
  and the search only opens inside the button editor, on a button that already exists. Rendering
  thumbnails in the browser would mean screenshotting TD Snap, and offering an unlabelled "first /
  second / third" is a lottery rather than control. Consistent with the rule this project holds
  elsewhere, the feature stops at what the app exposes: control over the *query*, not the pick.
  Revisit if a future TD Snap release names its results.
- **Close the file-mode gap.** Exported files add to an existing page as well as creating one, through
  `builder.add_buttons_to_page`, with a fingerprint guard, whole-file validation before and after, and
  `validate.validate_added_buttons`. Existing buttons there are listed and locked: changing and
  removing on the file path needs its own prior-content snapshot and rollback, and saying so beats
  offering a control that would do something else.

**Exit:** a user can fix a typo, retire a word, move a button, choose its symbol, and undo the last
change — each with a review step and working rollback · destructive failures restore exact prior
content, not merely prior shape · write-path coverage ≥75% (`builder.py` 95%, `validate.py` 88%;
`live.py` sits at 63%, bounded by the Windows-only automation a Linux CI box cannot execute — its pure
planning and verification logic is covered against fakes).

Still outstanding for this phase, as for 4a: the `TDSNAP_LIVE_E2E=1` run on real hardware, the only
thing that can confirm drag-to-move and the delete-action discovery against a live TD Snap editing
panel.

---

## Phase 5 — Caseload-scale vocabulary work *(~2–3 weeks)* — **shipped**

Where "saves hours" becomes literal for the primary audience.

- **List import** — *shipped.* **Import a word list** takes a paste or a CSV/TSV file, detects the
  delimiter and whether there is a header, guesses which column is the label, the message, the
  function, and the symbol hint, and lets any guess be corrected. The parse is a pure module
  (`static/csv.js`) with its own `node --test` suite, so RFC4180 quoting — a comma inside a phrase
  staying inside the phrase — is pinned away from the DOM. Everything that will not fit is named
  before a single button is added: rows already on the page, rows repeated within the list, rows the
  page has no room for, and rows that cannot become a button at all, each identified by row number
  *and* by what it does hold, so it can be found in the file.
- **Reusable topic templates** — *shipped.* A template is labels, spoken messages, topic-page rows,
  symbol search words, and the page style they were composed for, saved by name in the Phase 2
  settings file. What it deliberately does not carry is anything tied to one page set: no page ids, no
  fingerprints, no client's name. Applying one fills the same `state.words` the chip box fills, so it
  goes through the same capacity check, the same review, and the same confirm step as anything typed
  by hand — a template can never write to a page set. It adds to what is there rather than replacing
  it, and names what would not fit. Saved cells are a preference, not a promise: a template built on
  an 8×5 grid keeps its words on a 4×3 page and takes whatever cells are free.

  `settings.save(preferences, draft, templates=None)` leaves stored templates alone, so the draft
  autosave running every few seconds cannot wipe work the user deliberately named; an explicit empty
  list is how they are cleared. The Settings disclosure names saved templates, because **Clear all**
  throws them away and that listing is where a user finds that out.
- **Page-set-wide duplicate detection** — *shipped.* `GET /api/tdsnap/vocabulary` and
  `GET /api/pageset/<id>/vocabulary` return every label in the page set by page, read once per
  connection. Advisory throughout: a word already elsewhere is noted with the pages it is on and never
  blocked, because two pages deliberately carrying "more" is a normal thing for a page set to do. The
  blocking per-page check is unchanged. A page set whose labels cannot be read reports
  `available: false` and nothing downstream is affected.
- **Multi-page batch** — *shipped.* Pages are queued from the ordinary review screen, reviewed as one
  list, and applied by `live.apply_batch` calling the single-page `apply_page_edits` once per page —
  same fingerprint guard, same edit-mode session, same rollback. Nothing in the batch path reaches
  past one page.

  Every queued page is reported on afterwards — `applied`, `refused`, `failed`, or `skipped` — because
  a run that stops after page two must not read as though pages three and four were fine. Warnings
  stay attached to the page that raised them, and a check counts as passed only where every applied
  page passed it.

  Whether a failure stops the run turns on a distinction the write path already made but did not
  expose: `PagesetError.page_touched`. A refusal wrote nothing and is local to that page, so the rest
  of the queue still runs; a page that was written to and restored means the automation lost its
  footing, and the next thing it would do is drive a *different* page in that state, so it stops.

  Two limits are said up front rather than discovered: undo is single-level, so it reaches the last
  page applied and no further; and a page can be queued once, because a second entry's fingerprint was
  captured before the first one landed and is stale by construction.

  **The queue is deliberately not autosaved,** unlike the chip box. Its entries hold live TD Snap
  fingerprints that a relaunch invalidates, so restoring a queue would offer back work that could only
  be refused. It is guarded against loss instead — `hasUnsavedWork` and the quit warning both count it.
- **The item cap was not raised.** Doing so was conditional on the live path being *measured* to hold
  up, and no such measurement exists yet; the 200-item cap stands, and the O(n²) placement-order
  renderer is untouched. The import path respects the cap and reports the overflow by name.

**Exit:** a clinician takes a 60-word spreadsheet, maps its columns, previews placement across three
pages, applies once, and reuses the same set as a template later. — *met, with the queue applied per
page rather than as one atomic write; per-page rollback is what the automation can actually promise.*

---

## Phase 6 — AI you can steer *(~2–3 weeks)* — **shipped**

It was one shot, N items, take it or leave it.

- **Per-item controls** — *shipped.* Opening a suggested button offers **Suggest a different one** and
  **More like this**; removing one records it as a rejection. All three go through one request shape
  in `ai.js`, differing only in `count` and `like`.

  Rejections did **not** simply extend the `existing` list as this plan assumed. A button already on
  the page is a fact about the page; a rejected suggestion is a judgement the user made; a kept one is
  the direction they want more of. Feeding rejections in as "already on the page" tells the model
  something untrue, and shows up as suggestions drifting towards vocabulary that is not there — so
  `build_prompt` gained `avoid`, `like`, and `style` as separate lines.

  Only suggestions are steerable, and provenance decides that: a word somebody typed is theirs, so
  deleting it is never recorded as a rejection, and renaming a suggestion makes it theirs too.

- **Style-matching** — *shipped.* A bounded sample of the page set's real labels rides along with the
  vocabulary index that Phase 5 already read once per connection, and the page being edited leads it.
  It could not reuse the index keys: those are casefolded, because "chips" and "Chips" are the same
  concept for duplicate checking, and capitalization is half of what "style" means.

  Excluded from the grounding request as required, and pinned by two tests rather than by a comment:
  one asserts the lookup receives the page title and none of `existing`, `avoid`, `like`, or `style`;
  the browser suite asserts the same about the request that carries them.

- **Model path** — *shipped as machinery; the second pin is not yet filled in.* `localai` is a
  registry of `ModelChoice` entries, each with its own publisher, immutable commit, size, SHA-256,
  file on disk, and memory bar. Downloads, verification, `Llama` loading, and the picker are all
  per-choice, and a second model never disturbs the first. The gate is measured — `GlobalMemoryStatusEx`
  on Windows, `sysconf` elsewhere — and an unmeasurable machine is offered the default and nothing
  larger, because "assume it's fine" is the guess this bullet ruled out. The small model stays the
  default.

  The larger entry (Qwen2.5 7B Instruct, Apache-2.0) is declared but **not offered**: its exact size
  and SHA-256 have not been confirmed against the publisher, and `pinned` being False keeps it out of
  the UI and out of the download path entirely. Inventing those numbers would ship a download that
  can only ever fail its own integrity check. `scripts/verify_model_pins.py` resolves and prints them
  from Hugging Face's metadata API — one small request, no multi-gigabyte download — and also checks
  the existing pin, so a pin nobody ever verified stops being possible.

- **Quality harness** — *shipped.* `tests/fixtures/ai_eval_set.json` is 20 cases; `tests/ai_eval.py`
  scores them; `test_ai_eval.py` runs them against the real model and records the rate.

  One check was added that this plan did not call for, and it is the one that makes the number mean
  anything. Forbidding *"wand"* passes any answer that avoids the forbidden words — including eight
  capitalised words with no relation to the category. So every word case also names members a person
  would recognise, and one hit is enough: the question is whether the model knows the subject, not
  whether it picked a particular answer.

  The scorer is pure and its rules are tested offline on every CI run, each with an answer that must
  pass and one that must fail. A check that accepts everything passes every release and says nothing.

  It records rather than gates, and the first CI run is why. The file shipped asserting a 0.3 pass
  rate — a guess, which is the exact thing this bullet exists to replace — and CI measured 0.15. That
  number is honest: the job runs Qwen2.5 **0.5B**, the cheapest model that exercises the real code
  path and a third the size of the one that ships, and at that size it mostly echoes the page title
  back (*"farm animals"* for Farm animals, *"Hogwarts"* for Harry Potter characters). Gating on a
  stochastic number from a model nobody uses buys a red build, not information. A collapse is still
  caught on every build, by the smoke test and by the offline rule tests; `TDSNAP_AI_EVAL_FLOOR` gates
  deliberately where that is wanted.

- **Grounding transparency** — *shipped.* `grounding.lookup` returns the article used, its URL, and
  the runners-up; the response names it and the panel shows it with a link. Rejecting one, or choosing
  another, applies to the next round rather than discarding suggestions already on screen that the
  user may have edited. Candidates are now tried in order rather than only the first, so an article
  with no extract no longer means no grounding at all.

**Exit:** a user accepts most suggestions and regenerates the rest without losing work · suggestions
visibly match the page set's existing style · the eval set runs in CI with a recorded pass rate. —
*met. The larger model is the one carried-forward item: the plumbing and its tests are in place, and
the entry becomes available the moment its pin is verified, with no other change.*

---

## Phase 7 — Onboarding and experience tailoring *(~1–2 weeks)*

Deliberately placed after the UI churn of Phases 4–6, so it tailors a stable interface instead of
being built twice. Phase 0 removed the premature README claim; this phase earns it back.

A short first-run assessment that reshapes the editor to fit the person: a novice sees a calmer,
guided interface; an experienced builder sees everything, uncluttered by hand-holding.

- Three dimensions — editing knowledge (guided/standard/expert), comfort with local AI setup
  (none/assist/power), and familiarity with the app layout (new/familiar) — applied through **one
  auditable `applyProfile()`** that skips missing elements silently rather than throwing.
- Store the profile in the Phase 2 opt-in settings file so a returning clinician is not
  re-interviewed every launch, with the answer visible and clearable in Settings.
- **Guardrails, without exception:** never hide a safety or confirmation step; defaults are starting
  points and never locks; tailoring never changes what gets written to the page set; no telemetry, no
  network call, no external font or script. Skipping the assessment lands the user in the full UI.
- Keyboard-operable radiogroups reusing the existing roving-tabindex helper; focus moves to the
  welcome heading; axe assertions extended to the new panel.

Any pre-existing design notes for this feature predate the current wizard UI and reference element
IDs and CSS classes that no longer exist. Re-derive the element map from the live DOM before building.

**Exit:** first-run users are asked once and can skip, landing in a working editor either way ·
guided and expert produce visibly different but equally capable UIs · the README claim is true again.

---

# Track D — Reach

## Phase 8 — Multilingual *(~3–4 weeks)*

Every string is hardcoded in `index.html` and `app.js`; there is no i18n scaffolding of any kind. In
AAC, bilingual and multilingual families are the norm and Spanish-language page sets are common in US
practice — this is arguably the largest single product gap in the project.

It sits here, not earlier, for one reason: extracting strings before Phases 4–7 stop moving the UI
would mean re-translating repeatedly. Phase 1's `strings.js` makes this mostly mechanical by now.

- Message catalogues with a `t()` accessor, extracted from `strings.js` and `index.html`.
- **Spanish first**, reviewed by a bilingual SLP rather than machine-translated — this is clinical
  vocabulary, not UI chrome.
- AI prompts are English-only today. Add per-language prompt variants, and verify the packaged
  model's quality in the target language before claiming support. If it is not good enough, say so in
  the UI rather than shipping poor suggestions into someone's communication system.
- The phrase classifier's five regexes are English-specific and need per-language word lists — which
  is exactly what Phase 3's single-source-of-truth refactor enables.
- Symbol search terms pass through to TD Snap and Grid 3; confirm behaviour with non-English labels.
- Locale-aware comparison for duplicate detection.

**Exit:** the full wizard runs end to end in Spanish · AI suggestions are either good in Spanish or
honestly labelled English-only · duplicate detection and phrase classification work per-language.

---

## Phase 9 — Interchange: OBF / OBZ *(~3–4 weeks)*

The highest-leverage reach work, and the only major feature in this roadmap that is pure Python,
cross-platform, and fully testable without a Windows VM.

- Open Board Format (`.obf` single board, `.obz` board set) is the AAC interoperability standard,
  covering CoughDrop and an import path from several other tools.
- **Import.** Read an `.obz` into the canonical item model, map board grid to TD Snap grid and
  buttons to speak/navigate commands, and drive it through the *existing* review, placement, and
  confirm flow. A multi-board `.obz` becomes a set of linked pages.
- **Export.** Emit `.obf`/`.obz` from a page set so a clinician's work is portable rather than
  vendor-locked. Symbols are the hard part: OBF references images by URL or embedded data, while
  TD Snap symbols are licensed content. Export labels, messages, layout, and linking faithfully; omit
  proprietary symbol images and state that plainly in both the UI and the README.
- This phase should carry the highest test coverage in the project — deterministic, file in and file
  out, no UI automation. Round-trip property tests (import → export → import) belong here.

**Exit:** a CoughDrop `.obz` imports into a TD Snap page set through the normal review flow · a page
set exports to `.obz` and re-imports without losing labels, messages, layout, or links.

---

## Phase 10 — Grid 3 parity *(~3–4 weeks)* — **shipped**

Grid 3 is capability-gated to adding vocabulary into safe blank cells on unprotected `.gridset`
format-1 grids; the server answers anything else with *"This Grid 3 edit operation is not supported
yet."* The UI hides page creation, linking, topic-row layout, and the layout screen behind
TD Snap-only attribute sweeps. Depends on Phase 3.

- Create a new grid and link it from a cell on the open grid — the Grid 3 analogue of adding a topic
  page.
- Extend Phase 4's change, remove, move, and undo to Grid 3 wherever the accessibility surface allows,
  holding the line the project already holds: **no coordinate guessing, no OCR, no computer vision,
  no direct grid-set mutation.** If Grid 3 does not expose it accessibly, the feature stops. That
  discipline is why this tool is trustworthy and it must not bend for the sake of parity.
- **Give `.gridsetx`/WordPower a definite answer.** They are rejected outright today, and WordPower is
  one of the most widely deployed vocabularies in the field. Investigate only far enough to state in
  the README whether support is impossible or merely unbuilt. Users deserve to know which.
- Retire the icon-coordinate calibration environment variables if the shared UIA layer makes them
  unnecessary — they are a standing fragility signal.

**Exit:** Grid 3 creates and links a topic grid · every unsupported case fails with a specific,
actionable message naming exactly what Grid 3 did not expose · the README states a definite position
on `.gridsetx`/WordPower.

**Shipped (2026-09-21), measured on Grid 3 3.0.93.10 against a disposable copy.** Change, move,
remove, undo, and create-and-link all run through Grid 3's own Edit Mode and verify against the
saved file: a 2-cell addition with symbols in 12 s, a change + move + add in 17 s, a 3-cell linked
grid in 27 s. The `.gridsetx` answer is *impossible by design* — every entry is encrypted
(16-byte-aligned ciphertext, no plaintext anywhere in the archive) — and the README says so.

What the investigation found, which the phase had to absorb: the shipped locator never reached
Grid 3's cells on this build (see the CHANGELOG), so the phase began by making the read side work;
Grid 3's New-grid Rows/Columns pickers are not usable through any input path (the result depends on
whether the picker was driven by keyboard, mouse, or not at all — 6, 8, or the parent's rows), so a
new grid is always the parent's size; and "Same as cell label" copies text *onto* the label when
switched on, so spoken text is always written out explicitly. The icon-coordinate calibration
variables are TD Snap's (`TDSNAP_LINK_ICON_*`, `TDSNAP_ADD_ICON_*`) and are untouched here — retiring
them needs the same kind of live TD Snap session this phase had for Grid 3.

Not built, and said so: Remote Editing, word-list cells, symbol choice beyond an exact caption match,
and anything on a `.gridsetx`. `grid3.py` sits at ~59% coverage for the same reason `live.py` does —
the automation half only runs on Windows against Grid 3; its planning, verification, rollback, and
undo logic is covered against a fake Edit Mode that rewrites the grid-set package the way Grid 3
does, and `GRID3_LIVE_E2E=1` runs the real matrix.

---

## Rules that apply to every phase

1. Every new write operation ships with all four: a review step naming the exact change, a fingerprint
   guard, a rollback path, and at least one named check in the result list.
2. Destructive operations additionally snapshot prior **content**, not just prior shape, and refuse to
   run if that snapshot cannot be read.
3. Coverage floors rise per phase; write-path modules carry their own floors.
4. No new network calls. Wikipedia grounding remains the single, named, opt-in exception.
5. No new runtime dependency without passing the packaging smoke test.
6. README and CHANGELOG update in the same PR as the change — this is precisely what went wrong with
   the guided-setup claim and the orphaned walkthrough assets.
7. Tailoring, defaults, and profiles never gate a safety step and never lock a choice.

---

## Verification

Per PR:

```bash
python -m pytest
ruff check tdsnap tests packaging scripts
coverage run -m pytest && python scripts/check_coverage.py      # per-module floors
npm run lint                                    # from Phase 1 on: eslint + stylelint
npm run test:unit                               # from Phase 1 on
npm ci && npx playwright install chromium && npm run test:e2e   # includes axe
```

Two commands this list carried until Phase 4c have been corrected to what CI actually runs, because
neither passed as written: `node --test tests/js` resolves the path as a module on current Node (the
`test:unit` script globs the files), and `coverage report` alone checks the global floor rather than
the per-module ones that matter on the write path. `mypy tdsnap` is dropped from the per-PR list — it
has never been wired into CI and reports ~125 pre-existing errors, most of them the `Item = Union[str,
dict[str, object]]` weakness in `builder.py`. Typing the item model properly is worth a phase entry of
its own; a command in this list that nobody can pass is worth less than no command.

`npx prettier --check .` is also not a gate: the repo has never been prettier-clean (`npm run format`
would rewrite 300+ files). Formatting is applied to the frontend as it is split into modules — see
`.prettierignore`.

End to end, per phase:

- `python -m tdsnap.web`, then walk the full wizard for each of the three providers.
- `python scripts/fetch_fixture.py`, then `python -m tdsnap inspect|list|verify` against the fixture.
- **Live paths (Windows, disposable content only):** `TDSNAP_LIVE_E2E=1` and `GRID3_LIVE_E2E=1`.
  Never a real client page set — see [CONTRIBUTING.md](CONTRIBUTING.md).
- **Any file-path change:** run the quarantine-user procedure in
  [docs/IMPORT_SAFETY.md](docs/IMPORT_SAFETY.md) — new throwaway TD Snap user, import, exercise the
  page, restart TD Snap, re-open.
- **Packaging:** `./packaging/build.ps1 -Version X.Y.Z`, then `packaging/smoke_test.ps1`, plus a
  `pip install .` check that every static asset resolves.
- **Data loss (Phases 0 and 2):** compose a page, reload, and confirm the guard fires; kill the server
  mid-session and confirm recovery.
- **Rollback (Phase 4 onward):** deliberately interrupt an edit mid-flight and confirm the page
  returns to its exact prior *content*, not merely its prior shape.
