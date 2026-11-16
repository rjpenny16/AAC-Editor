# 01. Architecture and current state

Part of the reliability audit of November 2026. Audited commit: `69ffa9d` (`main`). This document describes what exists; the defects are in [02](02-CONFIRMED-BUGS-AND-ROOT-CAUSES.md) and [03](03-INTERMITTENT-FAILURE-INVESTIGATION.md). Existing documents are linked, not replaced: [QA plan](../QA_PLAN.md), [security audit](../SECURITY_AUDIT.md), [import safety](../IMPORT_SAFETY.md), [AI quality](../AI_QUALITY.md).

## How this audit was done, and its limits

- Read the repository, 191 commits of history, the last 224 runs of the Tests workflow and the failing job log.
- Ran the Python suite, the frontend unit tests and the browser suite locally on Linux, plus scratch reproductions (results quoted in doc 02).
- **Not done, because it cannot be done here:** nothing was run on Windows, and neither TD Snap nor Grid 3 was available. Every statement about how those two apps behave is read from code and labelled as unverified. No production code was changed.

## Components

```
 Browser tab or pywebview window
   tdsnap/web/static/*.js  (ES modules, no bundler, one global `state` object)
        |  fetch, per-run token in X-TDSnap-Token
        v
 Local HTTP server  tdsnap/web/server.py  (Flask on werkzeug, threaded, 127.0.0.1:8765)
   |            |                 |                    |
   |            |                 |                    +-- settings.json, drafts, templates (web/settings.py)
   |            |                 +-- AI: web/engines.py -> web/localai.py (llama.cpp in-process)
   |            |                                        -> web/ollama.py  (HTTP to localhost:11434)
   |            |                         web/grounding.py (Wikipedia, optional), web/prompts.py
   |            +-- File sessions: temp working copies of .sps / .spb / .gridset / .obf / .obz
   |                  builder.py, pageset.py, gridset.py, obf.py, formats.py, validate.py, atomic.py
   +-- Live editing: one automation thread (uia.AutomationThread) behind _LIVE_LOCK
          live.py  -> TD Snap window, mouse/keyboard input, UI Automation reads,
                      read-only SQLite reads of TD Snap's own page set
          grid3.py -> Grid 3 window, keyboard input, read-only reads of the saved .gridset
```

| Part | Files | Size | Notes |
|---|---|---|---|
| Frontend | `tdsnap/web/static/` | about 10,300 lines | Native ES modules. One mutable global in `state.js`. `api.js` is the only fetch wrapper. |
| Server | `tdsnap/web/server.py` | 2,374 lines | 46 routes. Threaded werkzeug server with daemon threads. |
| Desktop shell | `tdsnap/web/desktop.py`, `packaging/launcher.py` | 219 + small | pywebview window; native open/save dialogs; UAC restart for Grid 3. |
| TD Snap live | `tdsnap/live.py` | 3,074 lines | Largest module. `apply_page_edits` alone is about 316 lines. |
| Grid 3 live | `tdsnap/grid3.py` | 1,966 lines | Shares helpers with `live.py` through `uia.py` and some private imports. |
| UIA core | `tdsnap/uia.py` | 350 lines | Automation thread, `walk`, `wait_for`, `activate`. |
| File editors | `builder.py`, `pageset.py`, `gridset.py`, `obf.py`, `formats.py` | about 3,400 lines | SQLite for TD Snap, zip of XML for Grid 3, JSON/zip for Open Board. |
| Validation | `tdsnap/validate.py` | 636 lines | Table snapshots and structural checks for TD Snap files. |
| AI | `web/localai.py`, `ollama.py`, `engines.py`, `prompts.py`, `grounding.py` | about 2,000 lines | Optional. |
| Packaging | `packaging/` | | PyInstaller spec, Inno Setup script, unsigned installer, smoke test script. |

Runtime dependencies are small: `flask`, and `uiautomation` on Windows; `llama-cpp-python` and `pywebview` are optional extras. Python 3.9 or newer.

## Lifecycle

1. **Start.** `launch.bat` / `launch.sh` (source checkout) or the installed launcher. The launch scripts first try to quit any copy already serving port 8765, then start `python -m tdsnap.web`. The server probes the port with a 1 second HTTP request; if something else answers, it picks a random free port. A new random API token is generated for every process (`server.py:90`).
2. **Page load.** The frontend fetches `/api/config` once to get the token and whether it is running in the native window and elevated.
3. **Connect.** The user picks TD Snap, Grid 3 or a file. Live modes start a status poll (1.5 s backing off to 15 s).
4. **Plan, review, apply.** Words are placed on a preview; a review screen shows the plan; applying sends one request with no client deadline.
5. **Result and undo.** Live modes keep the last edit in memory on the automation thread so it can be undone once.
6. **Exit.** Closing the window or `/api/quit` shuts the server down; `cleanup_sessions()` deletes all file-session working copies.

## Workflows, end to end

### Live TD Snap edit (`POST /api/tdsnap/edit-plan`)

`server._drive` takes `_LIVE_LOCK` and runs on the automation thread: find the window named "TD Snap" and check its package identity; call `SetFocus`; navigate to the page; compare the page fingerprint with the one from the review; enter edit mode (pressing the settings button, unless a Done button already exists); remove, move, change, then add buttons by clicking coordinates and typing into the editor panel; verify labels, messages, removals and untouched buttons by reading the UI tree and TD Snap's SQLite page set (opened read-only); press Done; re-read; build the report. Any exception after the first write triggers `_restore_page_state`, which presses Undo repeatedly until the page matches the baseline.

The app never writes TD Snap's files. All changes go through TD Snap's own interface.

### Live Grid 3 edit (`POST /api/grid3/edit-plan`)

Same lock and thread. Requires the editor to be elevated. Finds the first top-level window whose title starts with "Grid 3 - " and checks the executable path. Refuses unless Grid 3 is in normal (not edit) mode. Presses F11, drives cells with the keyboard, presses Ctrl+S, then verifies by re-reading the saved `.gridset` and diffing every cell against the expected result. A mismatch triggers `_rollback_saved`: undo one step, save, re-read, repeat.

### File edit (`.sps`, `.spb`, `.gridset`, Open Board)

Upload or native open creates a session folder under the user's temp directory holding `original`, `current` and `meta.json`. Each edit is built in a scratch copy, validated, then atomically replaces `current`. The user saves `current` out through a download (browser mode) or a native save dialog (desktop mode).

### AI suggestions (`POST /api/ai/words`)

Optional Wikipedia lookup for grounding, then either Ollama over HTTP or the built-in llama.cpp model in the server process, then cleaning and filtering of the output. Suggestions land in a tray and only become buttons through the same review as typed words.

## Reliability matrix

Status meanings: **Tested (mock)** means automated tests pass against fakes. **Verified** is reserved for behaviour observed against the real thing; almost nothing involving TD Snap or Grid 3 qualifies. **Unverified** means no evidence either way. Issue IDs refer to doc 02 and doc 03.

### Startup and connection

| Workflow | Expected | Observed / evidence | Coverage | Status | Issues |
|---|---|---|---|---|---|
| Fresh install | Installer runs, app starts | `package-smoke` workflow builds and launches on a runner when packaging paths change | CI, conditional | Partial; no clean-machine run recorded | REL-027 |
| First launch | Window opens, token loaded | Works in browser tests | Playwright | Tested (mock) | REL-009 |
| Subsequent launch | Reuses or replaces old copy safely | Launch scripts quit the old copy without asking; working copies deleted | None | **Unreliable** | REL-007, REL-010 |
| Local server startup | One instance, known port | No single-instance lock; port can silently change | None | **Unreliable** | REL-010 |
| TD Snap connection | Finds the running app | Depends on exact window name, package id and English UI | Mocked | Unverified on hardware | REL-017, REL-019, REL-023 |
| Grid 3 connection | Finds the running app, elevated | First title match wins; only version 3.0.93 known | 3 opt-in tests, never run in CI | Unverified on hardware | REL-023 |
| Reconnect after failure | Banner, then recovery | Poll backs off correctly; wrong diagnosis after a server restart | Playwright for the banner only | Partial | REL-009 |
| Switching modes | State fully reset | `resetConnection` centralises this; apply in flight is not blocked | Playwright | Partial | doc 03 H-14 |

### Vocabulary editing (live)

| Workflow | Expected | Evidence | Status | Issues |
|---|---|---|---|---|
| Add button | Added to the reviewed cell and verified | Mocked tests pass | Tested (mock); unverified on hardware | REL-005, REL-017 |
| Rename / change message | Changed and verified | Mocked | Tested (mock); read-after-click race suspected | REL-017 |
| Move button | Drag verified | Mocked; project docs say drag has never been confirmed on hardware | **Unverified** | REL-027 |
| Remove button | Removed once, verified | Mocked; delete-action discovery never confirmed on hardware | **Unverified, risk of double action** | REL-004 |
| Create page | Page created and linked | Mocked; verification step depends on write timing | **Unreliable** | REL-016 |
| Link pages | Link button created | Mocked | Unverified | REL-016 |
| Batch edit | Stops after any page it touched and could not finish | Reproduced continuing past a damaged page | **Defective** | REL-003 |
| Preview / confirm | Refuses if the page changed since review | Works in mocks; false refusals when the window moves | Partial | REL-018 |
| Undo and rollback | Page restored or user told clearly | Mocked with the undo stubbed out | **Unverified, highest risk** | REL-001, REL-002 |
| Import CSV/TSV, templates | Feed the same review | Unit and browser tests | Tested (mock) | none found |

### File operations

| Workflow | Expected | Evidence | Status | Issues |
|---|---|---|---|---|
| Read exported page set | Opens real exports | Integration job uses a real TD Snap export | Verified for that fixture | REL-013 |
| Write edited copy | Original never overwritten | Desktop save dialog can overwrite the original | **Defective** | REL-006 |
| Validate integrity | Structural checks before replace | Fault injection for every SQLite write in three builder paths | Verified (Linux) | none |
| Open Board import/export | Round trip | Unit tests, bounded archive reading | Tested | corrupt-deflate generic error (doc 02 minor) |
| Grid 3 file editing | Edit `.gridset` safely | Unit tests on constructed files; security audit notes no real Grid 3 files were available | Partial | REL-012, REL-020 |
| Malformed files | Clear refusal | Mostly; some escape as generic 500 or native-dialog errors | Partial | REL-012 |
| Read-only / locked files | Clear message | Raw OS text; wrong blame on Windows | Partial, Windows unverified | REL-020 |

### AI

| Workflow | Evidence | Status | Issues |
|---|---|---|---|
| Model discovery / status | First check can exceed the browser deadline; built-in engine absent when started from `launch.bat` | **Unreliable** | REL-008, REL-028 |
| Download and verification | Size cap, magic bytes, SHA-256, durable replace | Sound in one process; unsafe with two instances | REL-010, REL-022 |
| Load and inference | In-process, no deadline, no cancel | Partial | REL-022 |
| Ollama | 5 s probe, clear errors | Tested (unit) | none |
| Malformed output | Parsed defensively, 502 with a clear message | Tested | none |
| Cancellation, repeated requests, stale suggestions | Server keeps generating after the browser gives up; replies are not checked against the current page | Partial | REL-022 |
| Editing without AI | AI never takes the automation or session locks | Sound, with two exceptions | REL-022, REL-024 |

### Application lifecycle

| Workflow | Evidence | Status | Issues |
|---|---|---|---|
| Close and reopen | Working copies deleted on clean exit | By design, but silent | REL-007 |
| Cancel an operation | No server-side cancel for live edits or AI | Missing | REL-011, REL-022 |
| Interrupt an edit (close window) | Automation thread dies mid-sequence, no rollback | **Unsafe** | REL-007 |
| Lose connection | Banner for TD Snap going away (shipped in Phase 16) | Tested (mock) | REL-009 |
| Recover a saved draft | Drafts autosave to settings | Tested | none |
| Unexpected termination | File sessions are rebuilt from disk; live edit state is lost | Partial | REL-021 |
| Clear local data | Deletes other instances' sessions too | Partial | REL-010 |
| Upgrade / uninstall / reinstall | No tests, no record of a manual run | **Unverified** | REL-027 |

## What was reviewed and found sound

Recorded so that later work does not re-investigate these.

- One automation thread with COM initialised once; every live call goes through one lock; the status poll never blocks behind it.
- Server binds to loopback only, checks the Host header, requires a per-run token (constant-time compare) on every mutation and every automation route, sets security headers, caps uploads at 512 MB.
- No HTTP endpoint accepts a filesystem path. No `eval`, `pickle`, `yaml` or `shell=True`.
- Archives are read with entry, per-entry and total size limits and are never extracted to disk, so there is no zip-slip path.
- `atomic.py`: temp file in the destination directory, fsync, `os.replace`, cleanup in `finally`.
- Grid 3 verification compares the saved file cell by cell, including untouched cells. This is the strongest verification in the code base.
- There are no edit-level retries, so retry logic cannot duplicate an add. `uia.activate` retries only when the first attempt provably did nothing.
- Security-audit fixes P-1, P-2, P-3, P-6, S-1 to S-6, S-8 and S-10 are still present. S-7 and P-4 are only partly applied (doc 02, minor findings).

## Areas of uncertainty

1. How TD Snap's Undo behaves after Done, and how quickly its UI tree settles after a click. Everything in the rollback design rests on this and none of it has been observed.
2. Whether TD Snap locks its page-set database while saving, and for how long.
3. Whether Windows grants foreground to TD Snap when the request originates from a browser tab.
4. Behaviour on any TD Snap or Grid 3 version other than the one the code was written against, and on any non-English installation.
5. Installer behaviour on a clean machine, on upgrade and on uninstall.
