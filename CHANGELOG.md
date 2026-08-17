# Changelog

All notable changes to AAC Editor are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entries for 2.1.0 and earlier are summarized from the
[published releases](https://github.com/rjpenny16/AAC-Editor/releases); this
file starts tracking changes in detail from 2.2.0 onward.

## [Unreleased]

### Added

- **Change and remove existing TD Snap buttons.** Until now the app was
  add-only: fixing a typo, retiring a word, or rewording a phrase was still
  hand work — the exact work this tool exists to eliminate. Selecting **Change
  or remove existing buttons** on the word list opens the page grid, where an
  eligible button can be selected to rewrite its label, rewrite or clear its
  spoken message, or remove it. Additions, changes, and removals travel as one
  reviewed edit through one rollback.

  Three rules hold this open, and none of them are in the UI where they could
  be bypassed:

  - **Only a plain speaking button is ever rewritten.** A button that opens a
    page or runs a TD Snap action stays locked and says why on hover and on
    focus. The accessibility tree cannot tell these apart — a page link and a
    speaking button look identical — so eligibility is read from the page set's
    own stored command sequence.
  - **Prior content is captured before anything is touched, and the edit is
    refused outright when it cannot be read.** Every operation before this was
    additive, so rollback could mean "undo until the page matches its pre-edit
    fingerprint". A fingerprint carries a button's name and position, and
    rewriting a spoken message changes neither — that rollback would have
    stopped on its first check and reported the page restored while the message
    stayed wrong. Rollback now undoes until each touched cell holds its prior
    label *and* spoken message again, read back through TD Snap's own editor.
  - **Nothing else on the page may move.** Verification now checks the cells
    the edit never named, as well as the ones it did, so "these three buttons
    changed" is a checked claim rather than an assumption.

  New endpoint operation `edit_page` on `POST /api/tdsnap/edit-plan`, carrying
  `changes` and `removals` alongside `items`; the older `add_to_existing_page`
  is unchanged and still accepted. `GET /api/tdsnap/page-layout` now reports
  each button's spoken message, whether it can be edited, and why not.

  The Windows UI Automation paths this rides on — selecting an existing button
  and finding TD Snap's delete action — are covered by unit tests against fakes
  but still need the `TDSNAP_LIVE_E2E=1` run on real hardware before release.
  A delete action TD Snap does not expose stops the removal with a message
  naming exactly that, rather than continuing blind.

- **Support report.** A **Copy a support report** action in the footer, and on
  the new error banner, collects app version, OS, Python, packaging mode, and
  the TD Snap, Grid 3, and AI capability flags a bug report needs. It reports
  grid dimensions but never page names, button labels, grid-set names, file
  paths, or user names, so it is safe to paste in full. Backed by a new
  `GET /api/diagnostics` endpoint and `tdsnap.web.diagnostics`.
- **Unexpected-error banner.** `window.onerror` and `unhandledrejection`
  handlers now surface failures that previously left the wizard frozen and
  completely silent, and offer the support report in place.
- **Dark theme.** Follows `prefers-color-scheme`, with a contrast check in CI.
  Light sensitivity is common among AAC users and therapy rooms are often dim.
- **Frontend quality gates.** ESLint, Stylelint, Prettier config, and
  `.editorconfig`, plus JavaScript unit tests (`node --test`) — none of which
  existed for 2474 lines of JS and 700 of CSS. Wired into the browser CI job.
- **Per-module coverage floors** (`scripts/check_coverage.py`) on the code that
  writes to a page set. A single global percentage is bounded by the
  Windows-only automation modules and says little about the write path.
- **Opt-in settings store.** A single `settings.json` in the same per-user data
  folder the built-in AI model already uses, written only the first time
  something is actually saved — a fresh install creates no file. Backed by
  `tdsnap.web.settings` and `GET`/`PUT`/`DELETE /api/settings`, behind the same
  API-token, loopback-host, and custom-header guards as every other mutation.
  Writes are atomic (temp file, then `os.replace`), and a corrupt file is
  renamed aside and the app starts clean rather than failing to launch.
- **Draft autosave and recovery.** The in-progress item list is autosaved
  while composing; on the next launch, a banner offers *"You have an
  unfinished page for X — resume or discard?"* so a crash, a killed tab, or an
  accidental reload doesn't have to mean starting over.
- **Remembered preferences.** The last AAC app chosen, the Ollama host and
  model, and the Wikipedia-grounding checkbox are restored on the next
  launch instead of being re-entered every time.
- **In-composition undo.** Removing a chip and "Arrange automatically" — the
  two composition actions with no other way back — can now be undone with an
  **Undo** button or Ctrl/Cmd+Z while adding buttons.
- **A Settings disclosure.** **What AAC Editor saves**, in the footer, lists
  everything stored in plain language and offers **Clear all saved data**.
- **A server restart no longer orphans an open file-mode session.** Sessions
  used to live only in process memory, so a crash, a port conflict, or a
  launcher killing a stale instance turned every open upload into "Unknown or
  expired session; re-upload the file" even though the edited copy was still
  on disk. The session directory now carries enough metadata to reconstruct
  itself.

### Changed

- **Shared Windows UI Automation helper layer** (`tdsnap/uia.py`). `live.py`
  (TD Snap) and `grid3.py` (Grid 3) each drove the same control tree
  independently and had already diverged: walk depth (9 vs 10), cluster
  tolerance (8 vs 6), and retry policy on activating a busy control (30s
  retry vs none). Each divergence was reconciled deliberately — not by
  keeping whichever file was older — and is pinned by a test; see the new
  module's docstring for the reasoning behind each choice, and for the three
  same-named helpers deliberately *not* merged because the two products
  genuinely do them differently.
- **The phrase-function classifier has one source of truth for its test
  contract.** `tdsnap/web/prompts.py`'s `phrase_function` and
  `static/phrases.js`'s `inferPhraseFunction` mirrored five regexes by hand
  with nothing asserting they agreed. `tests/fixtures/phrase_function_cases.json`
  is now run against both implementations, so an edit to one without the
  other fails CI. Fixed one real disagreement found in the process: the JS
  side accepted any truthy `suggested` value as a fallback function, while
  Python only accepted one of the five known functions — a caller passing
  something else now falls back to "comment" in both, not just Python.
- **Function border colors are validated server-side.** The five clinical
  topic-page colors (question/comment/positive/negative/personal) used to be
  whatever `border_color` a request sent, converted without question. The
  write path now rejects any color that isn't one of
  `colors.FUNCTION_BORDER_COLORS` — this is a clinical convention, not a UI
  preference, so nothing else is accepted regardless of source.
- **A reload no longer silently discards planned buttons.** The browser now
  warns before leaving while words or phrases are composed but not yet applied.
  Quitting deliberately says what will be lost instead of asking twice.
- **The frontend is now native ES modules** — `state`, `dom`, `api`, `phrases`,
  `a11y`, `wizard`, `connect`, `chips`, `parents`, `preview`, `ai`, `review`,
  `result`, `support` — instead of one 2591-line file with a single mutable
  object every function could reach. No bundler and no build step were added.
- Ruff now runs `I`, `B`, `SIM`, `RUF`, `S`, and `UP` rather than its minimal
  default set. Deliberate patterns carry per-line suppressions with reasons.
- Accessibility scanning covers the word list, chip editor, placement editor,
  review screen, and support dialog, not just the connect screen.
- The live TD Snap poll pauses while the tab is hidden.
- The AI smoke test skips on a CDN transport failure rather than failing the
  build, while still failing on a genuine download defect.
- Failing to close an uploaded page-set session is recorded for the support
  report rather than being discarded; it previously leaked the session's temp
  directory until the 24-hour sweep with no trace.
- Removed the README's claim that setup adapts between a guided and a compact
  workspace. No code implemented it. See
  [ROADMAP.md](ROADMAP.md) Phase 7, which builds the feature properly.

### Removed

- `walkthrough-guide.png` and `walkthrough-lead.png`, unreferenced since the
  walkthrough redesign but still shipped in the wheel, the PyInstaller bundle,
  and the installer.

### Fixed

- **`clone_row` could have copied NULL into every column of every cloned row.**
  `sqlite3.Row` implements the sequence protocol, so `name in row` searches
  values rather than column names — an edit that succeeds, validates, and only
  shows as damage when TD Snap opens the page set. Caught by the expanded lint
  rules, and now covered by direct tests.
- The application logo was a 1254×1254 PNG rendered at 32 px. Resized to 128 px,
  preserving the design. With the orphaned images above, this removes about
  1.7 MB from every download.

## [2.2.0]

Prepared and tagged in the source tree; not yet published as a GitHub release.

### Added

- Windows installer packaging: Inno Setup installer, PyInstaller spec, UIAccess
  manifest, build and smoke-test scripts, and manifest verification.
- A packaging smoke-test workflow that self-signs, builds, installs,
  health-checks, and uninstalls on Windows.
- SignPath code-signing policy, and a release workflow that refuses to publish
  unless both the application and installer are signed.
- `docs/UIACCESS_TESTING.md` covering the development-only UIAccess signing
  procedure, with explicit teardown.
- Pinned release build inputs in `packaging/release-constraints.txt`.

### Changed

- Renamed from TD Snap Page Builder to **AAC Editor**, reflecting Grid 3 support
  alongside TD Snap.
- Refactored the editor data flow to reduce duplicated logic across the
  exported-file, TD Snap live, and Grid 3 write paths.
- Made CI checks platform independent.
- Added creator attribution and sharpened the README around time saved on
  repetitive AAC editing.

## [2.1.0] - 2026-07-14

First published release. See the
[release notes](https://github.com/rjpenny16/AAC-Editor/releases/tag/v2.1.0).

[Unreleased]: https://github.com/rjpenny16/AAC-Editor/compare/v2.1.0...HEAD
[2.1.0]: https://github.com/rjpenny16/AAC-Editor/releases/tag/v2.1.0
