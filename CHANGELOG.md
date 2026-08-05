# Changelog

All notable changes to AAC Editor are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entries for 2.1.0 and earlier are summarized from the
[published releases](https://github.com/rjpenny16/AAC-Editor/releases); this
file starts tracking changes in detail from 2.2.0 onward.

## [Unreleased]

### Added

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

### Changed

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
