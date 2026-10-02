# Quality and correctness plan

Goal: make every existing feature work as documented. No new features. Multilingual
support (ROADMAP Phase 8) is out of scope.

Rules for every change in this plan:

- Write the failing test first, then the fix.
- Keep each PR to one defect group.
- Update README and CHANGELOG in the same PR.
- Raise a coverage floor in `scripts/check_coverage.py` when a module earns it.
- Run the per-PR checks in ROADMAP "Verification" before pushing.

## Baseline (2026-09-30, Linux sandbox)

| Check | Result |
|---|---|
| `python -m pytest` | 716 passed, 16 skipped |
| `ruff check tdsnap tests packaging scripts` | clean |
| `npm run lint` | clean |
| `npm run test:unit` | 58 passed |
| `python scripts/check_coverage.py` | all per-module floors met |
| `npm run test:e2e` | not run in the sandbox: installed Chromium build differs from the one Playwright 1.62 expects |

Skipped today: AI smoke and eval (`TDSNAP_AI_SMOKE=1`), Grid 3 live (`GRID3_LIVE_E2E=1`),
real TD Snap fixture tests (`scripts/fetch_fixture.py`), packaged exe and Authenticode guard.

## Phase 1: Close the verification gaps

- [x] Browser suite against the installed Chromium: 171 passed, 1 skipped. (The sandbox Chromium
      build differs from the one Playwright pins, so a local config with `executablePath` was used
      and not committed.)
- [x] Real fixture fetched; integration tests: 7 passed. Full Python suite with the fixture:
      723 passed, 9 skipped.
- [ ] Real-model AI smoke and eval: blocked in the sandbox (model download returns 403 from the
      proxy). Needs a machine that can reach the model CDN. `llama-cpp-python` installs fine.
- [x] Baseline recorded: no failing test anywhere we can run.

## Phase 2: Defects where coverage is thinnest

Priority order.

1. [ ] `live.py` (68%) and `grid3.py` (59%): the click, type, and verify paths.
   - [x] Duplicated helpers: checked. The shared UIA layer already lives in `tdsnap/uia.py`; what
         remains in each file (`_automation`, `_activate`, `_window`, `_verify_process`) differs
         only in app-specific messages and process checks. The ROADMAP's "12 diverging helpers"
         note is stale. No fix needed.
   - [ ] Write tests for the uncovered click, type, and verify paths (Windows-only code, so mocked
         at the `uiautomation` boundary).
2. [ ] Rollback and undo (exported files done, live paths still open): fault-injection tests that interrupt an edit midway and assert the page
      returns to its exact prior content, for add, change, move, remove, and undo, on TD Snap,
      Grid 3, and exported files.
3. [ ] `web/ollama.py` (46%) and `web/desktop.py` (31%): timeouts, missing engine, junk responses,
      and what the user is shown.
4. [ ] CLI (71%): untested commands, including `export-obz` and `import-obz`.
5. [ ] Import and interchange (CSV/TSV, OBF/OBZ): malformed input, encodings and BOMs, large files,
      duplicate labels, and accurate "left out" reporting.
6. [ ] Settings persistence: concurrent writes, corrupt file, clear-all.

## Phase 3: Frontend correctness and accessibility

- [ ] Unsaved-work guard, and autosave recovery with **Keep an unfinished page** turned on (it is off
  by default): reload mid-compose, kill the server, relaunch. With it off, confirm that nothing about
  the page being composed is written to `settings.json`.
- [ ] Error messages and empty states on every wizard step: accurate and actionable.
- [ ] Keyboard-only pass through each screen, focus handling when dialogs close, labels, contrast.
- [ ] The review screen names exactly what is written.

## Phase 4: Fixes

Small PRs ordered by risk: data loss or wrong write, then silent wrong result, then confusing
message, then polish.

## Phase 5: Needs a Windows machine (cannot be verified in the sandbox)

- [ ] Live TD Snap and Grid 3 editing on a disposable copy only.
- [ ] Installer build and `packaging/smoke_test.ps1`.
- [ ] Quarantine-user import procedure in `docs/IMPORT_SAFETY.md` for any file-format change.

## Findings log

- Exported-file writes (`add_category_page`, `add_buttons_to_page`, `add_linked_pages`): every
  write statement was failed in turn; each rolled back cleanly. No defect.
  `tests/test_fault_injection.py` keeps it that way. Mutation-checked: removing the rollback in
  `add_buttons_to_page` makes it fail.

Add one line per defect: where, what, test that reproduces it, PR.
