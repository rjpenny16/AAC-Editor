# AAC Editor — Roadmap (post-2.2.0)

## Why this document exists

AAC Editor 2.2.0 is a shipped, signed, Windows-first tool that edits AAC page sets **in place** —
through TD Snap's and Grid 3's own accessibility surfaces — so a page set keeps its sharing and sync
identity instead of being round-tripped through an export.

Until now, all product intent lived in one negative-space paragraph of the README's Grid 3 section.
This document replaces that with an explicit, ordered plan. Each phase is independently shippable
and unblocks the next.

## Where the project stands

The foundations are solid and should not be re-litigated: three write paths behind one canonical
item model, review-before-write, layout fingerprinting, automatic rollback, 136 Python tests and 29
Playwright tests, a five-job CI matrix, axe-checked end-to-end coverage, and a fail-closed signed
release pipeline. There are no TODO/FIXME markers in the tree.

The gaps are elsewhere, and three of them are serious:

1. **A browser refresh silently destroys unsaved work.** There is no `beforeunload` guard, no draft,
   no autosave, no recovery. Composing a large topic page — labels, spoken messages, function
   assignments, drag placements — and then reloading loses all of it. This is the clearest
   user-facing failure mode in the product and it is small to fix.
2. ~~**The app is add-only.**~~ *Phase 4a closed the first half of this: TD Snap live can now change
   and remove a speaking button.* Moving a button and choosing its symbol are still hand work
   (Phase 4c), and there is still no user-initiated undo once an edit lands in the real page set;
   only failure-path rollback exists (Phase 4b).
3. **`live.py` and `grid3.py` each carry their own copy of the UI-Automation helper layer.** Twelve
   identically-named functions exist in both files and have already diverged in behaviour. Building
   Grid 3 parity on top of that multiplies the divergence.

Alongside those: 1.48 MB of orphaned images ship in every installer, there is no JavaScript linter,
formatter, type checker, or unit test, and the app is English-only in a field where bilingual
families are the norm.

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

### 4b — Undo my last change

Once an edit runs today, the buttons are in the user's real, synced page set with no way back. Only
failure-path rollback exists; the mitigation is procedural documentation, which relies on the user
having read it *before* the mistake.

This lands here because it needs exactly the content-snapshot machinery 4a builds. Retain the
snapshot of the last applied edit for the session and offer a single-level **"Undo my last change"**
that replays it in reverse through the same review-and-verify flow. Be explicit in the UI that it
cannot reach back past a TD Snap sync.

### 4c — Move, reorder, and symbol control

- **Move and swap existing buttons.** The drag and keyboard placement editor already exists for new
  buttons; extend it to unlocked existing ones.
- **Symbol control.** Symbol choice is delegated entirely to TD Snap's own search and surfaces only
  as a warning when it fails. Show the candidates the search already returns, let the user pick, and
  let them skip. No new file format is needed, and it is the control AAC editors are asked for most.
- **Close the file-mode gap.** Exported-file mode can only *create* pages. Add an add-to-existing
  path so all three providers converge on the same operation set.

**Exit:** a user can fix a typo, retire a word, move a button, choose its symbol, and undo the last
change — each with a review step and working rollback · destructive failures restore exact prior
content, not merely prior shape · write-path coverage ≥75%.

---

## Phase 5 — Caseload-scale vocabulary work *(~2–3 weeks)*

Where "saves hours" becomes literal for the primary audience.

- **List import.** Paste or open CSV/TSV with column mapping (label, message, function, symbol hint).
  The chip box already accepts comma-separated paste; this is the structured version. Respect the
  200-item cap and report what will not fit *before* the user commits.
- **Reusable topic templates** (needs Phase 2). Save the current item set, layout, and function
  assignments as a named template, then apply it to any page set. One topic page built once and reused
  across many clients is the core caseload win.
- **Page-set-wide duplicate detection.** Duplicates are checked only against the target page and
  planned items today. Extend across the whole page set — straightforward SQL for the file path, the
  existing page enumeration for live. Advisory (*"'apple' already exists on Food"*), never blocking.
- **Multi-page batch.** Queue several page-and-items edits, review them as one list, and apply
  sequentially with per-page rollback and per-page results. The live lock already serializes the
  automation; the real work is the review UI and honest partial-failure reporting.
- Raise the item cap only if the live path is *measured* to hold up. Note that the placement-order
  renderer is O(n²) — harmless at 200, visible above it.

**Exit:** a clinician takes a 60-word spreadsheet, maps its columns, previews placement across three
pages, applies once, and reuses the same set as a template later.

---

## Phase 6 — AI you can steer *(~2–3 weeks)*

Today it is one shot, N items, take it or leave it.

- **Per-item controls.** Regenerate one suggestion, "more like this", or reject — with rejections fed
  back as negative constraints. The prompt builder already accepts an `existing` list; rejected items
  simply extend it.
- **Style-matching.** Pass a sample of the page set's real button labels as style context so
  suggestions match the user's register and length. The live path already collects them. This is
  local-model-only by construction and must be explicitly excluded from the grounding request, which
  sends the page title alone.
- **Model path.** The built-in model is pinned to Qwen2.5-1.5B Q4_K_M at ~1.1 GB. Add a larger option
  for machines with the RAM, selected by a measured check rather than a guess, keeping the same
  pin-and-verify discipline (size, SHA-256, GGUF magic). **Keep the small model** — clinic laptops
  need it, and installer size already matters for families on metered connections.
- **Quality harness.** Grow the opt-in AI smoke test into a fixed eval set of ~20 category prompts
  asserting the type-matching rules the prompt already states — *"Harry Potter characters"* must not
  return *"wand"*. Track pass rate per release so prompt edits stop being guesswork.
- **Grounding transparency.** It currently takes the first search result. Name the article used and
  let the user reject it.

**Exit:** a user accepts most suggestions and regenerates the rest without losing work · suggestions
visibly match the page set's existing style · the eval set runs in CI with a recorded pass rate.

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

## Phase 10 — Grid 3 parity *(~3–4 weeks)*

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
mypy tdsnap                                     # from Phase 1 on
coverage run -m pytest && coverage report       # must clear the phase's floor
npx eslint . && npx prettier --check .          # from Phase 1 on
npm ci && npx playwright install chromium && npm run test:e2e   # includes axe
node --test tests/js                            # from Phase 1 on
```

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
