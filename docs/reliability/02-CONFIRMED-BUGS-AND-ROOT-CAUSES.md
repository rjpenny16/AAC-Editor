# 02. Confirmed bugs and root causes

Audited commit `69ffa9d`. Only defects that are **CONFIRMED** appear here: each one is demonstrated by a CI log, by a local reproduction, or directly by the code as written. Suspected problems that need more evidence are in [03](03-INTERMITTENT-FAILURE-INVESTIGATION.md).

"Confirmed" means the defect exists in the code. It does not mean it has been seen on the owner's machine: where a defect needs Windows or a real AAC app to trigger, that is stated under Confidence.

Complexity: S = under a day, M = one to three days, L = about a week, including tests.

## Index

| ID | Severity | Summary |
|---|---|---|
| REL-003 | High | A batch carries on after a page it damaged and could not restore |
| REL-005 | High | TD Snap input is sent without checking TD Snap is in front |
| REL-006 | High | Desktop "save" can overwrite the original file |
| REL-007 | High | Relaunching or closing the app destroys unsaved work and can abandon a live edit |
| REL-009 | High | After a server restart the open page fails everything and blames TD Snap |
| REL-011 | High | Automation calls have no deadline |
| REL-025 | High | No log exists; the support report can leak vocabulary |
| REL-026 | High | CI is red from one cause, loses its evidence and gates nothing |
| REL-012 | Medium | A crafted grid set can exhaust memory |
| REL-013 | Medium | `#` or `%` in a folder name breaks file reading |
| REL-014 | Medium | The result screen says "Done" regardless of the checks |
| REL-015 | Medium | Grid 3 probe can leave Grid 3 in edit mode |
| REL-016 | Medium | New-page verification is timing-dependent |
| REL-018 | Medium | Moving the TD Snap window invalidates a reviewed edit |
| REL-021 | Medium | Crash leftovers block opening files; reload drops the session |
| REL-022 | Medium | AI generation cannot be cancelled and shares the editor's process |
| REL-024 | Medium | The diagnostics endpoint is unauthenticated and blocks automation |
| REL-023 | Low | No elevation check for TD Snap; wrong profile after an elevated restart |

---

## REL-026. CI is red from one cause, loses its evidence and gates nothing

- **Severity:** High (it removes the project's only automatic safety net).
- **Affected:** every pull request since 5 November 2026.
- **Files:** `tdsnap/web/static/connect.js:352-353, 474-475, 509-510`; `tdsnap/web/static/index.html:32`; `tests/test_live_edit.spec.js:203-208, 911-913`; `.github/workflows/tests.yml` (browser job); `package.json:15`.
- **Symptoms:** browser job reports 175 passed, 11 failed, 1 skipped.
- **Steps to reproduce:** `npm ci && npx playwright install chromium && npm run test:e2e`.
- **Expected:** all scans clean.
- **Actual:** every failing test reports `label-content-name-mismatch` on `#file-badge`.
- **Root cause:** the badge's visible text and its `aria-label` disagree, for example visible "TD Snap · Change app" against label "Change app (currently TD Snap)". axe-core's check ignores text in parentheses and requires the visible words to appear in order inside the accessible name; they do not. The mismatch dates from commit `fb7662d` (July). It only started failing when PR #83 moved `@axe-core/playwright` from 4.13.0 to 4.14.0, because in axe-core 4.14 this rule is no longer tagged experimental and so runs in a default scan.
- **Evidence:**
  - Run 214 on `main` (merge of PR #87, 5 Nov 19:25:59 UTC) succeeded. Run 216 on `main` (merge of PR #83, 19:26:37 UTC) failed. Every run since has failed, including seven unrelated dependency pull requests rebased onto it.
  - Failing job log, run 224: 11 tests listed, error body identical in each.
  - Local reproduction: see "Local runs" below.
  - No other element in the app has this pattern (every `aria-label` on a button was checked).
- **Why exactly 11:** 14 tests scan with the badge visible. Three of them scan while a modal dialog is open, which makes everything behind it inert to axe. So the badge defect is also present on those three screens; they pass by accident.
- **Classification of the 11:** all deterministic; all one genuine application defect (WCAG 2.5.3, Label in Name, which matters to voice-control users); none are test-infrastructure faults; none are intermittent.
- **Second-order problems, also confirmed:**
  1. PR #83 was merged while its own check was failing. Nothing requires checks to pass.
  2. The browser job records traces and screenshots on failure but has no upload step, so they are discarded.
  3. `tests/test_live_edit.spec.js:911-913` asserts the incorrect label, so the fix must change the test. This is a case where the assertion is demonstrably wrong.
  4. Tests that prove less than they claim: line 1352 waits 1200 ms to show that a 1500 ms poll changed nothing; lines 279 and 283 wait 2200 ms against a 2000 ms autosave.
- **Confidence:** very high.
- **Proposed fix:** make the accessible name begin with the visible text (or remove the `aria-label` and rely on the text plus a visually hidden suffix); update the pinned assertion; add `actions/upload-artifact` for `test-results/` on failure; turn on required status checks for `main`; replace the three weak waits with conditions on observed requests.
- **Regression risk:** low. Screen-reader wording changes slightly.
- **Tests:** the existing 11; add one scan of each connected state without a modal.
- **Complexity:** S.

### Local runs

| Suite | Result |
|---|---|
| `pytest` (Python 3.13, Linux) | 978 passed, 16 skipped |
| `npm run test:unit` | 68 passed |
| `npm run test:e2e`, three runs | 175 passed, 11 failed, 1 skipped each time; see the addendum |

---

## REL-003. A batch carries on after a page it damaged and could not restore

- **Severity:** High. Data integrity.
- **Affected:** TD Snap multi-page batch edits; also single edits (wrong message).
- **Files:** `tdsnap/live.py:2510-2527` (the `except` / `finally` pair in `apply_page_edits`), `2610-2622` (`_batch_stop`), `2666-2685` (`apply_batch`), `1155-1158` (`_exit_edit_mode`).
- **Symptoms:** after a failure on one page, the batch continues onto the next page; the message shown says only "TD Snap did not leave edit mode."
- **Expected:** once a page has been written to and not cleanly finished, the batch stops, and the user is told the page may be changed.
- **Actual:** the `finally` block calls `_exit_edit_mode`. If that raises, Python replaces the in-flight exception (the one carrying `page_touched = True` and the rollback result) with the new one, which has `page_touched = False`. `apply_batch` reads that flag to decide whether to stop.
- **Reproduction (scratch test, fakes only):** make an add fail, make the rollback fail, make leaving edit mode fail. Output:
  ```
  REL-003 raised: 'TD Snap did not leave edit mode.'
  REL-003 page_touched: False
  REL-003 batch would stop: False
  ```
- **Related, same code:** `apply_batch` catches only `PagesetError`. Any other exception (a raw COM error, `LookupError`) on page N aborts the whole request, and the results for pages 1 to N-1, which were applied, never reach the user. Reproduced:
  ```
  REL-003b pages attempted before the whole batch call failed: ['One', 'Two']
  ```
- **Root cause:** cleanup that can fail is placed in `finally` without preserving the primary error; the stop decision is carried on an exception attribute that defaults to "safe".
- **Confidence:** high that the defect exists. How often leaving edit mode fails on real TD Snap is unknown, but it is most likely exactly when something else has already gone wrong.
- **Proposed fix:** wrap the `finally` body so a cleanup failure is attached to, not substituted for, the primary error; make "touched" the default once the first write has started; have `apply_batch` catch every exception, mark that page "failed, state unknown", stop, and still return the results so far.
- **Regression risk:** low; behaviour only changes on failure paths.
- **Tests:** the two scratch reproductions become permanent tests; add fault injection at every step of `apply_page_edits` (doc 05).
- **Complexity:** S.

## REL-005. TD Snap input is sent without checking TD Snap is in front

- **Severity:** High.
- **Affected:** every live TD Snap edit.
- **Files:** `tdsnap/live.py:262-268` (`_focus_window`), and every raw input call: `auto.Click` at 1268, 1347, 1748, 1965; `DragDrop` at 1950; `SendKeys("{Esc}")` at 1279, 1491. Compare `tdsnap/grid3.py:901-925` (`_require_grid3_foreground`).
- **Symptoms (expected in the field):** an edit that "does nothing" then times out; clicks landing in another window.
- **Expected:** input is only sent when TD Snap is the foreground window, and the edit is refused with a clear message otherwise.
- **Actual:** `SetFocus()` is called once per edit and its result is ignored. No later check exists. Clicks go to absolute screen coordinates. A minimised TD Snap is not restored. Grid 3's code path has a foreground check before every key; TD Snap's has none.
- **Root cause:** the precondition was implemented for the second app and never back-ported to the first.
- **Evidence:** code as written. Whether Windows refuses the foreground change in practice is a hardware question (doc 03, H-01).
- **Confidence:** certain that the check is absent; probable that it causes real failures, since Windows restricts which process may take the foreground.
- **Proposed fix:** one shared `require_foreground(window)` in `uia.py`, called before every input in both apps; compare window handle, not just process; restore if minimised; on failure raise a refusal that says nothing was changed (if before the first write) or stop and report unknown state (if after).
- **Regression risk:** medium. Stricter checks will refuse some edits that currently succeed by luck; the message must tell the user to click TD Snap and retry.
- **Tests:** fake UIA tree with a "foreground lost at step N" fault (doc 05).
- **Complexity:** M.

## REL-006. Desktop "save" can overwrite the original file

- **Severity:** High. Contradicts a documented safety promise.
- **Affected:** saving an edited file in the desktop window (not browser mode, where saving is a download).
- **Files:** `tdsnap/web/server.py:909-917` (`save_current_as`), `tdsnap/web/desktop.py:66-81`; compare `tdsnap/pageset.py:288-309`, which does refuse. Promise: `docs/IMPORT_SAFETY.md` ("only ever writes a separate file").
- **Steps:** open `client.sps` in the desktop app, make an edit, choose Save, pick `client.sps` in the dialog and accept the operating system's overwrite prompt.
- **Expected:** refused, or at minimum an explicit in-app confirmation plus an automatic backup.
- **Actual:** `atomic_copy(current, dest_path)` runs with no comparison against the source path.
- **Root cause:** the guard lives in the CLI path (`Pageset.save_as`) and was not carried into the session-based web path, which does not record where the file was opened from.
- **Confidence:** high (code).
- **Proposed fix:** record the source path in the session when opened natively; refuse the same path (using the same `samefile` logic); default the dialog to `<name>.edited<ext>`; re-open and validate the saved copy before reporting success.
- **Regression risk:** low.
- **Tests:** unit test on `save_current_as`; round-trip test that the saved file re-opens and matches `current`.
- **Complexity:** S.

## REL-007. Relaunching or closing the app destroys unsaved work and can abandon a live edit

- **Severity:** High.
- **Affected:** anyone who double-clicks the launcher twice, or closes the window while an edit is running.
- **Files:** `launch.bat:31-32`, `launch.sh:27`; `tdsnap/web/server.py:1119-1125` (`/api/quit`), `2368` (`cleanup_sessions` in `finally`); `tdsnap/web/desktop.py:207-217`; `tdsnap/uia.py:140-143` (daemon thread).
- **Actual behaviour, three parts:**
  1. The launch scripts POST `/api/quit` to whatever is on port 8765, silently.
  2. `/api/quit` does not check for unsaved file edits or a running live edit; shutdown then deletes every working copy.
  3. Request threads and the automation thread are daemon threads, so quitting or closing the window during a live edit stops the sequence wherever it is: TD Snap or Grid 3 can be left in edit mode with part of the edit applied and no rollback.
  4. If the running copy is the packaged window, `/api/quit` stops only the server and leaves a dead window open.
- **Root cause:** shutdown has no notion of work in progress.
- **Confidence:** high (code; `packaging/smoke_test.ps1:57-62` works around part 4).
- **Proposed fix:** `/api/quit` refuses while `_LIVE_LOCK` is held, and reports unsaved sessions; launch scripts focus the existing instance instead of killing it; on exit, keep sessions with unsaved edits and offer them on next start; closing the window during an edit asks first and, if confirmed, waits for the current step and runs rollback.
- **Regression risk:** medium (startup flow changes).
- **Tests:** server tests for quit-while-busy and quit-with-unsaved; packaged smoke test for relaunch.
- **Complexity:** M.

## REL-009. After a server restart the open page fails everything and blames TD Snap

- **Severity:** High for trust; no data risk.
- **Files:** `tdsnap/web/static/api.js:25-35`; `tdsnap/web/server.py:90, 1035-1038`; `tdsnap/web/static/connect.js:776`.
- **Steps:** leave the page open; restart the app; use the page.
- **Expected:** "The app restarted. Reload this page."
- **Actual:** the token is fetched once and a failure is swallowed; a restarted server has a new token; every protected call returns 403; the live poll counts 403s as "TD Snap not found" and after three shows the lost-connection banner; the model-download poll retries every second for ever.
- **Root cause:** a single unauthenticated-state condition is not distinguished from every other failure.
- **Confidence:** high.
- **Proposed fix:** on 403, re-fetch `/api/config` once and retry; if the token changed, show a dedicated "app restarted" state. Give `api.js` typed errors (timeout, unreachable, unauthorised, refused, failed) so callers stop guessing.
- **Tests:** Playwright test that swaps the token mid-session.
- **Complexity:** S.

## REL-011. Automation calls have no deadline

- **Severity:** High.
- **Files:** `tdsnap/uia.py:146-156` (`done.wait()` with no timeout); `tdsnap/web/server.py:98-101` (`_drive`), `1062` (diagnostics under the lock); `tdsnap/web/static/state.js:31-32`.
- **Actual:** if one UI Automation call into TD Snap or Grid 3 hangs (a cross-process COM call into an unresponsive app does), the request thread waits for ever holding `_LIVE_LOCK`. Every later live request and the support report queue behind it. Separately, when the browser gives up on a status or layout request after 10 or 60 seconds, the server job is not cancelled and can still navigate TD Snap later, after the user has moved on.
- **Root cause:** no cancellation or deadline model for automation jobs.
- **Confidence:** high that the code has no deadline; frequency of hangs is unknown.
- **Proposed fix:** each job carries a deadline and a cancel flag checked between steps; a read job that passes its deadline is abandoned; a write job that passes its deadline returns "state unknown" and puts the live connection into a locked state that requires the user to check the page and reconnect. Never queue a second write behind a hung one.
- **Regression risk:** medium.
- **Tests:** fake that blocks at step N.
- **Complexity:** M.

## REL-025. No log exists; the support report can leak vocabulary

- **Severity:** High, because it blocks diagnosis of everything in doc 03.
- **Files:** `packaging/launcher.py:18-23` (stdout and stderr to devnull); `tdsnap/web/server.py:932-948`; `tdsnap/web/diagnostics.py:51, 62, 132`; `tdsnap/web/static/support.js:57-60, 104-106`.
- **Actual:** the packaged app writes no log anywhere. The server's `logger.exception` output is discarded. No operation has an ID, a start time or a duration. The support report states that no page-set content is included, but it appends recent client-side error strings as free text, and those strings can contain button labels (for example the "did not verify the removal of: ..." message) and file paths.
- **Root cause:** diagnostics were designed as a one-off snapshot, not a record.
- **Proposed fix:** doc 05, "Diagnostics".
- **Complexity:** M.

## REL-012. A crafted grid set can exhaust memory

- **Severity:** Medium (needs a hostile or corrupt file; takes the whole app down).
- **Files:** `tdsnap/grid3.py:526-531`; `tdsnap/gridset.py:321-328`.
- **Root cause:** `ColumnSpan` and `RowSpan` are accepted as any integer; `covered()` materialises every covered square.
- **Reproduction:**
  ```
  REL-012 spans 3000x3000 -> 9,000,000 squares, 28.7s, peak 1299 MB
  ```
  Larger values scale with the product of the spans. Negative or huge `X`/`Y` are likewise unbounded.
- **Proposed fix:** reject spans and coordinates outside the grid's declared dimensions at parse time; cap dimensions.
- **Tests:** parser test with oversized spans.
- **Complexity:** S.

## REL-013. `#` or `%` in a folder name breaks file reading

- **Severity:** Medium (rare, but total for the affected user, and confusing).
- **Files:** 19 call sites of the form `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`, including `tdsnap/web/server.py:668, 694, 727, 1421, 1462, 1789, 1926`, `tdsnap/live.py:337, 388, 423, 441, 485, 598, 767, 915, 2063`, `tdsnap/formats.py:188`, `tdsnap/cli.py:34`.
- **Reproduction:**
  ```
  REL-013 plain: ok
  REL-013 with#hash: FAILS -> no such table: t
  REL-013 with%41pct: FAILS -> unable to open database file
  ```
- **Why it matters for intermittency:** the session folder lives under the Windows temp directory, which contains the user name. A user name with `#` or `%` breaks every file-mode read; on the live path the same failure is swallowed and silently degrades TD Snap page reading (see REL-019 in doc 03).
- **Proposed fix:** one helper that builds the URI with `pathlib.Path(path).as_uri()` or percent-encoding; replace all call sites.
- **Complexity:** S.

## REL-014. The result screen says "Done" regardless of the checks

- **Severity:** Medium. Directly against "never report success before verification".
- **Files:** `tdsnap/web/static/result.js:103-110`; `tdsnap/live.py:2532-2547`; `tdsnap/live.py:2006-2007, 2996-2997`.
- **Actual:** the heading is always "Complete" / "Done - TD Snap was updated". Checks that did not pass are listed lower down as "needs review". On the TD Snap path the check values are literals: the report is only built if verification passed, which is fine for labels, messages and removals, but symbol and border application failures are swallowed (`except PagesetError: pass`) and are not verified at all.
- **Proposed fix:** an explicit outcome field from the server (`verified`, `verified_with_gaps`, `rolled_back`, `partial`, `unknown`; doc 04) drives the heading; list what was and was not verified.
- **Complexity:** S for the UI, M with the outcome type.

## REL-015. Grid 3 probe can leave Grid 3 in edit mode

- **Severity:** Medium.
- **Files:** `tdsnap/grid3.py:1414-1417`; compare the fixed form at `1730` from commit `479fe56`.
- **Actual:** in the compatibility probe's `except` block, `_restore_unsaved` is called without protection. If it raises, `_leave_edit_mode` never runs and the original error is lost.
- **Root cause:** an incomplete fix; the same pattern was corrected in one place and missed in its twin.
- **Proposed fix:** same try/finally as line 1730; better, a single context manager used by both.
- **Complexity:** S.

## REL-016. New-page verification is timing-dependent

- **Severity:** Medium.
- **Files:** `tdsnap/live.py:2975` against `2406-2419`.
- **Actual:** `add_topic_page` compares each slot's accessible name with the requested label. For a button with a spoken message TD Snap exposes the message as the name; it only maps back to the label if TD Snap has already written its database. `apply_page_edits` was fixed for exactly this in commit `6cc8b57` and later; `add_topic_page` was not. Failure triggers a rollback of a page that was created correctly.
- **Root cause:** duplicated verification logic that drifted.
- **Proposed fix:** one shared verification function used by both entry points.
- **Complexity:** S to M.

## REL-018. Moving the TD Snap window invalidates a reviewed edit

- **Severity:** Medium (no data risk; a frequent-looking false refusal).
- **Files:** `tdsnap/live.py:705-712`.
- **Actual:** the page fingerprint includes each button's absolute `left` and `top` screen coordinates. Moving or resizing TD Snap, a DPI change, or the editing panel opening between preview and apply changes the fingerprint and produces "page changed after preview". Batch entries capture their fingerprint when queued, so they are exposed for longer.
- **Proposed fix:** fingerprint on grid slot, label and stored content identity, not pixels.
- **Regression risk:** medium; the fingerprint is a safety guard, so the replacement must be at least as strict about content.
- **Complexity:** M.

## REL-021. Crash leftovers block opening files; reload drops the session

- **Severity:** Medium.
- **Files:** `tdsnap/web/server.py:474-488, 2255-2274`; `tdsnap/web/static/connect.js:270-274`.
- **Actual:** the 2 GB temporary-storage cap counts every session folder on disk, including ones left by crashes or by another instance, for up to 24 hours. After a few crashes with large page sets, opening a file fails with "would exceed the temporary storage limit". Separately, on page reload any error while resuming a file session, including a transient timeout, makes the frontend forget the session without saying so. The "saved" flag is not persisted, so a rebuilt session always claims unsaved changes.
- **Proposed fix:** on start, list recoverable sessions and offer "restore" or "discard"; count only live sessions against the cap; retry resume once and tell the user if it fails.
- **Complexity:** M.

## REL-022. AI generation cannot be cancelled and shares the editor's process

- **Severity:** Medium.
- **Files:** `tdsnap/web/localai.py:298, 566-628`; `tdsnap/web/server.py:2181-2213`; `tdsnap/web/grounding.py:43, 391-403`; `tdsnap/web/static/ai.js:93, 312, 826-846`.
- **Actual:**
  - Generation runs inside the server process under `_llm_lock`, with no deadline and no cancel. When the browser gives up at 150 seconds the server carries on, and the next request waits behind it.
  - Worst-case server time (grounding up to about 66 s, Ollama probe 5 s, first attempt 45 s, retry up to 120 s) exceeds the browser's 150 s.
  - A native crash or out-of-memory abort in llama.cpp ends the whole editor, including any file session. The memory check uses total, not available, RAM.
  - The download progress poll is a `setInterval` with an async body and no in-flight guard; it overlaps, and it never stops on repeated errors.
  - `checkAi` drops a newer status check if one is already running, so a changed host or engine can show the older answer.
  - Suggestions returning after up to 150 s are not checked against the page the user is now on.
- **On the recent commits:** `ef6e703`, `ed6d6b4` and `bcd9818` are correct for a single process (stale `.part` cleanup, size cap, checksum before replace, durable install). They do not cover two instances (REL-010, doc 03), cleanup only runs when a download starts, and the stored failure `detail` is never shown or included in the support report despite the comment saying so.
- **Proposed fix:** doc 06, Phase D: explicit AI state machine; request IDs; server-side deadline and cancel; inference in a child process.
- **Complexity:** L if inference moves out of process, M otherwise.

## REL-024. The diagnostics endpoint is unauthenticated and blocks automation

- **Severity:** Medium-low.
- **Files:** `tdsnap/web/server.py:1062`; `tdsnap/web/diagnostics.py:73-90`.
- **Actual:** `GET /api/diagnostics` needs no token and runs the whole report, including model hashing and the Ollama probe, on the automation thread under `_LIVE_LOCK`. Any web page can trigger it with an image tag (it cannot read the answer) and stall live editing for seconds.
- **Proposed fix:** require the token; gather AI and environment facts off the automation thread.
- **Complexity:** S.

## REL-023. No elevation check for TD Snap; wrong profile after an elevated restart

- **Severity:** Low.
- **Files:** `tdsnap/live.py:377`; `tdsnap/grid3.py:125-158, 753-758`.
- **Actual:** if TD Snap runs at a higher integrity level than the editor, Windows drops the editor's input without an error and the user sees timeouts such as "TD Snap did not open a button in the empty cell". After "Restart as administrator" approved with a different administrator account, `LOCALAPPDATA` points at that account, so TD Snap's page set is not found.
- **Proposed fix:** compare integrity levels at connect and say so; resolve the TD Snap data folder from the TD Snap process's user, not the editor's.
- **Complexity:** M.

---

## Minor confirmed findings

| Finding | Where | Fix |
|---|---|---|
| Native open/save catch only `PagesetError` and `OSError`; a corrupt SQLite file raises through to the window | `web/desktop.py:61, 80` | Catch `sqlite3.Error` and `zipfile.BadZipFile`; map to a clear message |
| Corrupt deflate data in `.obz` gives a generic 500 | `tdsnap/obf.py:486` | Catch `zlib.error` |
| Read-only hardening (`harden_untrusted`) is not applied to the server's own read-only connections (security audit S-7, partial) | `server.py` read paths | Route through one helper |
| Clean-exit signal handling is browser-mode only (security audit P-4, partial) | `server.py:2362` | Call in `run_desktop` too |
| Fingerprint check for TD Snap file edits happens outside the session lock; two identical submissions can both apply | `server.py:1500` vs `1508`, `1858` | Move inside the lock, as the grid-set path already does |
| Three near-identical validate, snapshot, save blocks | `server.py:1508-1536, 1580-1608, 1879-1907` | Extract one function |
| `README.md:48, 88` describe live verification as established; it is proven only against mocks | README | Reword until hardware runs exist |
| `docs/QA_PLAN.md` quotes 171 browser tests; there are 187 | QA plan | Update |
| `ROADMAP.md` Phase 16 exit criterion "browser suite green on Linux Chromium and Windows Edge" is unmet: no Windows browser job exists and Linux is red | ROADMAP | Correct or implement |

## Addendum: local browser-suite runs

Three consecutive local runs of the full browser suite (Linux, Chromium, one worker, no retries), made to separate deterministic from intermittent failures.

| Run | Passed | Failed | Skipped | Duration |
|---|---|---|---|---|
| 1 | 175 | 11 | 1 | 3.6 min |
| 2 | 175 | 11 | 1 | 3.4 min |
| 3 | 175 | 11 | 1 | 3.4 min |

- The set of failing tests was byte-for-byte identical in all three runs and identical to CI run 224: lines 354, 366, 375, 2492, 2845, 3853, 4425, 4657, 4738, 4889 and 5268 of `tests/test_live_edit.spec.js`.
- The only violation ID in any failure was `label-content-name-mismatch` (11 occurrences per run), always on `#file-badge`.
- No test changed outcome between runs. On this evidence the browser suite has **no intermittent failures**; it has one deterministic defect.
- The skipped test is the real-TD-Snap test at line 3096, which runs only with `TDSNAP_LIVE_E2E=1`.

Other reproductions made during the audit, all with scratch scripts outside the repository:

| Issue | Result |
|---|---|
| REL-003 | Reproduced (output quoted above) |
| REL-006 | Reproduced: calling `save_current_as` with the source path replaced the original file's contents |
| REL-012 | Reproduced (output quoted above) |
| REL-013 | Reproduced (output quoted above) |
| REL-010 (doc 03) | Second instance started on a random port while the first was unresponsive; simultaneous-start race did not reproduce on Linux |
| REL-008 (doc 03) | Hashing speed measured; outcome depends on cold disk speed, so still unconfirmed |

Not reproduced because they need Windows or the real AAC apps: REL-001, REL-002, REL-004, REL-005 (field effect), REL-017, REL-019, REL-020, REL-023.
