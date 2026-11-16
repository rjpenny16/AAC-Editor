# 05. Testing and diagnostics

Audited commit `69ffa9d`. This document says what the current tests prove, what they do not, and what to build so that reliability can be demonstrated instead of assumed. It extends [QA_PLAN.md](../QA_PLAN.md); it does not replace it.

## What exists and what it proves

| Layer | What runs | Result on this commit | What it proves | What it does not prove |
|---|---|---|---|---|
| Python unit | `pytest`, 4 Python versions, Linux | 978 passed, 16 skipped (local, 3.13) | Parsing, building, validation, planning logic, HTTP routes with fakes | Anything about real TD Snap or Grid 3 |
| Fault injection | `tests/test_fault_injection.py`, 3 tests | pass | Every SQLite write in three builder paths rolls back cleanly | Live edits, `.gridset` writes, save step, `atomic.py` |
| Integration | Real TD Snap export fixture, real small model | pass in CI | The file reader handles one real export; the AI code path runs | Other TD Snap versions; shipped model quality (the eval records, never gates) |
| "windows" job | The same `pytest` on `windows-latest` | pass in CI | The code imports and the mocked suite passes on Windows | UI Automation. Every live test patches the window, the waits, `time.sleep`, rollback and undo |
| Frontend unit | `node --test`, 68 tests | pass | Leaf modules | State interactions |
| Browser | Playwright, Chromium, Linux, 187 tests | 175 pass, 11 fail, 1 skip | UI flows against a mocked backend; accessibility scans | Server restart, token expiry, lost responses, Windows, Edge, the desktop window |
| Packaging | `package-smoke` on path triggers; `release` | conditional | Installer builds and the packaged app starts on a runner | Clean machine, upgrade, uninstall, unsigned-installer prompts |
| Real hardware | `TDSNAP_LIVE_E2E=1` (1 browser test), `GRID3_LIVE_E2E=1` (3 tests) | **never run in CI; no recorded run** | nothing yet | everything that matters most |

Coverage floors: global 60%; per-module floors in `scripts/check_coverage.py`. `live.py`, `uia.py` and `desktop.py` have no floor. Line coverage of `live.py` through fakes that stub its waits says little about its correctness.

### The central gap

`tests/test_grid3.py` `FakeGrid3` replaces `_wait_for` with a single attempt and replaces `_rollback_saved`, `_restore_unsaved`, `_save` and `_dirty`. `tests/test_live.py` replaces `_window`, `_restore_page_state` and `time.sleep`. So the code under test in the live suites is the planning and bookkeeping; the timing, focus, rollback and verification code is replaced by the test itself. A green live suite therefore says nothing about the failure modes in doc [03](03-INTERMITTENT-FAILURE-INVESTIGATION.md).

## Strategy

Three tiers, each with a different job. No tier substitutes for another.

| Tier | Runs where | Job | Deterministic? |
|---|---|---|---|
| 1. Logic | Every push, Linux and Windows | Prove the app's own decisions: preconditions, outcome classification, rollback bounds, state machines | Yes |
| 2. Simulated environment | Every push | Prove behaviour under injected faults against a scripted fake of each AAC app's UI tree, and against a real local server | Yes |
| 3. Real environment | Before each release, on a Windows machine with TD Snap and Grid 3 | Prove the fakes are faithful, and measure reliability | No; that is why it is measured over many runs |

### Tier 1 additions (Python)

- Outcome classification: table-driven tests that each failure point in doc [04](04-DATA-INTEGRITY-AND-SAFETY.md) yields the required outcome class.
- `apply_batch` stop rule for every outcome class and for non-`PagesetError` exceptions (REL-003).
- `save_current_as`: source-equals-destination refusal; saved file re-opens and equals `current` (REL-006).
- SQLite URI helper with `#`, `%`, spaces, non-ASCII, UNC paths (REL-013).
- Grid-set parser bounds (REL-012).
- `atomic.py`: failure at write, fsync, replace; temp file removed in each case. On the Windows job, replace over an open file.
- Session lifecycle: quit while busy, quit with unsaved edits, restart recovery, cap accounting (REL-007, REL-021).
- Single-instance lock: second start detects the first (REL-010).
- Round trips: open, edit, save, re-open, compare for `.sps`, `.spb`, `.gridset`, `.obf`, `.obz`; export then import is identity on the supported subset.

### Tier 2: the scripted fake UI tree

One new test-support module, used by both `live.py` and `grid3.py` tests, that implements the small part of the `uiautomation` surface the code uses (`GetChildren`, `Name`, `AutomationId`, `ControlTypeName`, `BoundingRectangle`, `Click`, `SendKeys`, patterns) over an in-memory model of a page.

It differs from today's fakes in two ways: **the real `_wait_for`, `_restore_page_state`, `_rollback_saved`, `_verify_page_state` and `_exit_edit_mode` run against it**, and it has a virtual clock and a fault schedule.

Faults, each addressable by step number so every run is repeatable:

| Fault | Models | Targets |
|---|---|---|
| `delay(step, ms)` | UI repaints late | REL-017, REL-004, REL-002 |
| `vanish(element, step)` | Control destroyed mid-walk (raises the real COM error type on Windows, a stand-in elsewhere) | REL-017 |
| `stale_editor(step)` | Editor panel still shows the previous button | REL-017 |
| `foreground_lost(step)` | Another window takes focus | REL-005 |
| `input_dropped(step)` | UIPI silently discards input | REL-023 |
| `dialog(step, kind)` | Unexpected or late dialog | REL-004, L12 |
| `undo_disabled_after_done` | Undo history cleared by Done | REL-002 |
| `undo_overshoot` | Undo history deeper than this edit | REL-001, REL-002 |
| `db_locked(ms)` / `file_unreadable(n)` | TD Snap database or `.gridset` busy | REL-019, REL-001 |
| `hang(step)` | Call never returns | REL-011 |
| `app_exit(step)` | AAC app closes | L13 |

Two kinds of test use it:

1. **Exhaustive single-fault sweep.** For each operation (add, change, move, remove, new page, undo, batch of two) and each step index, inject each fault once. Assert: the outcome class matches doc 04; the model's final state matches what the outcome claims; Undo was pressed no more times than actions were performed; no input was sent while not foreground. This is the live-edit equivalent of the existing SQLite fault-injection test.
2. **Seeded random timing.** Random valid delays from a seed on every step, a few hundred seeds per run, seed printed on failure. This is the only place randomness is used, and it is reproducible.

The fake is only as good as its model of the real apps. Tier 3 exists to check that.

### Tier 2: server and browser

- Playwright against the real server with a fake automation backend selected by an environment variable (instead of mocking every route in the browser), for the flows where server state matters.
- New browser tests: token changes mid-session (REL-009); response lost after a successful apply; navigating away during an apply; download poll under errors; AI reply arriving after the page changed; two tabs.
- Replace "wait N ms then assert nothing happened" with counting observed requests over a known number of poll cycles (lines 1352, 279, 283 and the five similar cases).
- Add a Windows job running the browser suite in Edge, which is what the desktop window uses. This is already promised by ROADMAP Phase 16.
- Upload `test-results/` on failure.
- Keep `retries: 0`. Retries would hide exactly the class of problem this project has.

### Tier 3: real-hardware runbook

Preconditions, all mandatory:

- A Windows machine that is not used with clients, or a virtual machine snapshot.
- TD Snap with a **newly created disposable user** and a copy of a stock page set. Grid 3 with a **copy** of a stock grid set under a disposable user. Never a client's content, never a synced account that also holds client content.
- A TD Snap backup and a copy of the `.gridset` taken before each session.
- Diagnostic mode on. The log is the evidence; a run without a log does not count.

Sessions:

| Session | Content | Records |
|---|---|---|
| T3-1 Behaviour discovery | The experiments listed in doc 03: Undo timing, Undo after Done, behaviour when already in edit mode, whether a delete confirmation exists, foreground rules, database locking, COM error type | Answers written into doc 03; fake UI tree updated to match |
| T3-2 Opt-in suites | `TDSNAP_LIVE_E2E=1` and `GRID3_LIVE_E2E=1` | Pass or fail, log |
| T3-3 Repeated workflow | Scripted loop: add 3, change 1, move 1, remove 1, undo, on rotating pages; 100 cycles per app | Outcome per cycle, durations |
| T3-4 Disturbance | During T3-3: click another window; minimise the AAC app; move it to a second monitor; open a dialog; kill the editor mid-edit; kill the AAC app mid-edit; run with CPU throttled | Outcome class each time; manual check of the page against the claim |
| T3-5 Lifecycle | 50 cold starts; relaunch while running; restart with unsaved file edits; elevated restart for Grid 3 | Connection success, time to ready |
| T3-6 Install | Clean Windows 10 and 11: install, first run, upgrade from the previous release, uninstall, reinstall; standard (non-admin) user | Checklist in doc 07 |
| T3-7 Environment spread | Second TD Snap version if obtainable; 125% and 150% display scaling; a low-memory machine for AI | Pass or fail per configuration |

Until T3-1 is done, items marked VERIFICATION GAP stay open and doc [07](07-RELEASE-READINESS-CHECKLIST.md) cannot be signed off.

## Intermittency testing rules

- Prefer deterministic fault injection. Use repetition only for Tier 3, where the environment cannot be scripted.
- A repeated run is evidence only with its log. "It passed 100 times" without per-step durations says nothing about margins.
- Any failure in a repeated run is investigated to root cause before the count restarts. No "re-run and move on".
- A test that fails once in CI is never retried to green; it is quarantined visibly, with an issue, for at most one week.

## Diagnostics

### Today

- `tdsnap/web/diagnostics.py` builds a one-off report from an allow-list of environment facts. It is a sound base.
- There is no log file. The packaged launcher sends stdout and stderr to the null device.
- The frontend keeps recent error strings in memory and appends them to the report as free text. These can contain button labels and paths (REL-025).
- Errors reach the user as one of a handful of generic strings; the original cause is lost.

### Design

**One local operation log**, written by the server, as JSON lines in the app's data folder (next to `settings.json`), rotated at 5 files of 1 MB. Always on at "summary" level, because intermittent faults cannot be reproduced on demand; this is safe because of what is and is not written.

Summary level, one record per operation:

```
{"t":"2026-11-16T13:02:11.482Z","op":"a3f9","kind":"live.apply","app":"tdsnap",
 "outcome":"rolled_back","code":"VERIFY_MISMATCH","ms":8421,
 "counts":{"add":3,"change":1,"remove":0,"move":0},
 "undo_presses":4,"fallbacks":["DB_LOCKED"],"instance":"7c1e"}
```

Diagnostic mode (optional, switched on in settings, auto-off after 24 hours or 50 MB, with a visible indicator while on) adds one record per step:

```
{"t":"...","op":"a3f9","step":7,"name":"select_cell","ms":212,"polls":3,
 "result":"ok","foreground":true,"edit_mode":true}
```

**Always recorded:** operation ID; kind; start time and duration; outcome class and a stable error code; counts; number of polls, timeouts and Undo presses; which fallbacks were taken; app version, Python version, Windows build, display scaling, elevation state of the editor and (where readable) of the AAC app; TD Snap package version and Grid 3 executable version; instance ID and port; AI engine and model key (not prompts).

**Never recorded, at any level:** button labels, spoken messages, page or grid names, vocabulary, AI prompts or outputs, file names, full paths, user or client names. Where an identity is needed to correlate records (the same page across steps), use a salted hash with a salt that lives only in memory for that run. Free-text exception messages are not logged; a code and the exception class are.

**Error codes.** A small fixed catalogue (for example `NOT_FOREGROUND`, `EDIT_MODE_BUSY`, `FINGERPRINT_CHANGED`, `VERIFY_MISMATCH`, `VERIFY_UNREADABLE`, `ROLLBACK_INCOMPLETE`, `AUTOMATION_DEADLINE`, `TOKEN_STALE`, `SAVE_LOCKED`, `AI_DEADLINE`). Each maps to one user-facing message that answers the six questions below. ROADMAP Phase 16 already plans a failure catalogue; this is that catalogue.

**Support report.** Keep the existing mechanism and extend it:

- Attach the last N summary records and, if diagnostic mode is on, the step records for the last failed operation.
- Remove free-text client errors; send codes and operation IDs instead. Show the operation ID in the UI error so the user can quote it.
- Require the API token for `/api/diagnostics` and build the report off the automation thread (REL-024).
- Keep the preview-before-copy behaviour; add a test that seeds labels into every error path and asserts none appear in the report (extends `tests/test_privacy_contract.py`).
- Update [PRIVACY.md](../../PRIVACY.md) to describe the log, where it is, and how to delete it. "Clear saved data" must delete it.

**How this helps with intermittent failures.** With step durations and poll counts, a failure stops being "it didn't work": the log shows, for example, that `wait_editor_label` took 1 poll and returned a stale value in 40 ms on the failing run and 3 polls in 300 ms on a good one. That turns a hypothesis in doc 03 into a confirmed cause, or eliminates it, from a single user report.

### User-facing errors

Every failure message must answer, in this order:

1. What happened (one sentence, no jargon).
2. Was anything changed (from the outcome class: nothing / changed and restored / changed, see list / not known).
3. Is the original data safe.
4. What to do next.
5. Whether trying again is safe.
6. A reference: operation ID, and "Copy support report".

Example, replacing "TD Snap did not leave edit mode.":

> **The edit to this page was undone, but TD Snap is still in edit mode.**
> The page matches how it was before. Nothing else was changed.
> Press Done in TD Snap, check the page, then reconnect here. It is safe to try the edit again after that.
> Reference a3f9 · Copy support report

Technical detail (code, exception class, step) lives in the log and the report, not in the message.

## Coverage targets

Line coverage is a weak measure here. Use these instead:

| Measure | Target |
|---|---|
| Rows of the doc 04 failure-point tables with an automated test | 100% |
| Operations x steps x faults covered by the single-fault sweep | 100% of enumerated combinations |
| Confirmed issues in doc 02 with a regression test that failed before the fix | 100% |
| Error codes with a browser test of their message | 100% |
| Branch coverage floor for `live.py`, `uia.py`, `grid3.py` with real waits and rollback in play | 85% |
