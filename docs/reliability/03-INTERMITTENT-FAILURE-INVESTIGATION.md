# 03. Intermittent failure investigation

Audited commit `69ffa9d`. This document answers "why does it work sometimes and not others?". It separates what the evidence supports from what is still a hypothesis, and for each open item names the experiment that would settle it.

Labels: **CONFIRMED** (in doc [02](02-CONFIRMED-BUGS-AND-ROOT-CAUSES.md)), **PROBABLE** (strong technical evidence, not reproduced), **POSSIBLE** (plausible, needs investigation), **VERIFICATION GAP** (cannot currently be tested).

## The short answer

There is no single cause. The code contains at least four families of timing- and state-dependent behaviour, each of which would look like "random" failure from the user's seat. None of them has been observed on a real machine, because the app keeps no log and no test drives the real AAC apps. That absence is itself the most important finding: **until logging exists and one real-hardware session has been recorded, the ranking below is informed judgement, not measurement.**

One thing the investigation did rule out: the red CI is not intermittent. It is one deterministic defect (REL-026).

## Owner input received after the first draft

| Question | Answer | Effect |
|---|---|---|
| Is Windows hardware with TD Snap and Grid 3 available? | Yes | The discovery session (T3-1) can run in Phase A. Every VERIFICATION GAP item can now be closed |
| Which failures are seen most? | Edits failing; failing to connect to Ollama | R1 (readiness) moves to the front of Phase C. The Ollama failure is explained by REL-028 in doc 02, a new confirmed finding |
| How is the app started? | Both `launch.bat` and the installed app | Confirms exposure to REL-007 (the launch script quits the running copy) and REL-028 (the two modes have different AI engines). Mixing the two is itself a source of run-to-run difference |
| Current workaround when AI fails | Asks a web assistant for a comma-separated list and pastes it into the word box | The paste path already works (`web/static/chips.js:151, 214`). A guided version is added to Phase D |

"Edits failing" is still a symptom, not a cause. The candidates, in the order the code makes most likely, are: input sent while TD Snap is not in front (REL-005); the editor panel read before it updates, so a correct edit fails verification and is rolled back (REL-017); "page changed after preview" because the window moved (REL-018); TD Snap's database being locked at verification time (REL-019). The Phase A log will show which, usually from one failed edit.

## Shared root causes

| Root | What it is | Symptoms it would produce | Issues |
|---|---|---|---|
| **R1. Readiness is assumed, not checked** | Live automation acts on TD Snap without confirming it is in front, settled, and showing what was last read | Edits that time out, fail verification although correct, or are refused as "page changed" | REL-005, REL-017, REL-018, REL-019, REL-016, REL-004 |
| **R2. Recovery depends on unobserved Undo behaviour** | Rollback presses Undo and trusts short fixed waits; Grid 3 saves before verifying | "Could not verify restoration", pages left changed, in the worst case more undone than was done | REL-001, REL-002, REL-003, REL-015 |
| **R3. Process and session lifecycle is unmanaged** | No single instance, token per process, no job deadline, working copies deleted on exit | Works after a reload, fails after a relaunch; "can't see TD Snap" when TD Snap is fine; lost file edits; everything hangs | REL-007, REL-009, REL-010, REL-011, REL-020, REL-021, REL-008 |
| **R4. Nothing is recorded** | No log, no operation IDs, errors collapsed into generic strings | Every failure is unrepeatable and unexplainable | REL-025 |

R4 does not cause failures, but it is why R1 to R3 have survived several rounds of fixes: each previous fix (see "History" below) addressed the one symptom that happened to be visible.

## Hypotheses from the brief, with verdicts

| # | Hypothesis | Verdict | Basis |
|---|---|---|---|
| H-01 | Window focus / foreground state | **Supported (code), unverified in the field** | REL-005: no foreground check on the TD Snap path |
| H-02 | Timing and race conditions with the AAC app | **Supported (code)** | REL-017, REL-004, REL-016; `wait_for` gives short timeouts one or two polls |
| H-03 | Fixed delays | **Supported** | `time.sleep(0.12)` per Undo (`live.py:1468-1475`); `wait=0.35` after Ctrl+S (`grid3.py:1161`) |
| H-04 | Fragile UI selectors | **Supported; fails closed** | About 40 hard-coded English names and AutomationIds, plus pixel heuristics (toggle 35 to 75 px, within 140 px of the left edge). A different version or language fails at the first lookup, which is safe but total |
| H-05 | TD Snap / Grid 3 version differences | **VERIFICATION GAP** | Only Grid 3 3.0.93 is recognised, and only as a warning; no TD Snap version is checked at all |
| H-06 | Administrator elevation / permissions | **Supported for one case** | REL-023 |
| H-07 | Swallowed exceptions | **Supported** | Silent SQLite fallbacks (REL-019), swallowed symbol failures (REL-014), `_leave_edit_mode` fully suppressed (`grid3.py:1049-1057`), frontend catch-alls |
| H-08 | Retries without checking current state | **Refuted** for edits | There are no edit-level retries; `uia.activate` retries only when the first try provably did nothing. One exception: `_open_button_editor` clicks twice and the second click can deselect (`live.py:1342-1352`) |
| H-09 | Continuing after partial failure | **Confirmed** | REL-003 |
| H-10 | Unsafe shared mutable state / threading | **Mostly refuted** | One automation thread, one lock. Session dict fields are written unlocked but harmlessly. Exception: fingerprint check outside the session lock for TD Snap file edits (doc 02 minor) |
| H-11 | Resources not released / file locks | **Supported on Windows, unverified** | REL-020 |
| H-12 | Temporary files and previous incomplete sessions | **Confirmed** | REL-021; stale `.part` files persist until the next download starts |
| H-13 | Local server lifecycle, background processes | **Supported** | REL-010, REL-007 |
| H-14 | Browser / session state | **Confirmed** | REL-009; `#review-back-btn` and `#file-badge` stay clickable during an apply with no deadline, and the result screen is shown regardless (`review.js:428-450`) |
| H-15 | Model availability and AI engine startup | **Supported** | REL-008 |
| H-16 | Network conditions | **Limited** | Only affects optional Wikipedia grounding (errors are swallowed and the request proceeds without a reference) and model download |
| H-17 | Installation paths / user profile | **Confirmed for special characters** | REL-013 |
| H-18 | Packaging differences | **VERIFICATION GAP** | The packaged app discards all output; desktop mode differs from browser mode in save path (REL-006), signal handling and shutdown (REL-007) |
| H-19 | Execution-order dependence | **Possible in tests only** | One long-lived server serves the whole browser suite; undo snapshot and file sessions are shared between tests |
| H-20 | Success reported before verification | **Confirmed in presentation** | REL-014 |

## Probable and possible defects

Each entry gives the reasoning, the competing explanation, and the experiment.

### REL-001. Grid 3 rollback can undo too far and save each step (PROBABLE, VERIFICATION GAP) - Critical

- **Where:** `tdsnap/grid3.py:1157-1170` (`_rollback_saved`), `1672` (save before verification), `1724-1738` (caller, second rollback in the `except`).
- **Mechanism:** each loop iteration presses Undo, presses Ctrl+S, waits until the title bar loses its `*`, then reads the saved file once. If the read fails (file still being written, or locked by Grid 3 or a sync client), the exception is swallowed and treated as "not yet restored", and the loop undoes another step and saves again. The loop can run `max(undo_steps, n*4)+8` times. If the first rollback raises, a second full rollback runs from the `except` block.
- **Why it matters:** Grid 3's undo history is not limited to this app's edit. Undoing past the baseline removes earlier work by the user, and each step is saved to disk (and possibly to Smartbox's online sync).
- **Competing explanation:** Grid 3 may always finish writing before clearing the `*`, in which case the read never fails and the loop stops exactly at the baseline.
- **Experiment:** on a throwaway grid set with three prior manual edits in the undo history, force a verification failure (edit the file between save and verify using a test hook), and record how many undo steps occur. Repeat with the file held open by another process.
- **Proposed direction:** never undo more steps than this edit performed; treat an unreadable file as "unknown" and stop; do not save inside the loop.
- **Complexity:** M, plus hardware time.

### REL-002. TD Snap rollback can undo too far, and edits start inside an existing edit session (POSSIBLE, VERIFICATION GAP) - Critical

- **Where:** `tdsnap/live.py:1161-1163` (`_enter_edit_mode` returns immediately if a Done button exists), `1468-1475` (Undo loop with `time.sleep(0.12)`), `2526` (`finally` presses Done).
- **Mechanism:** if the user already has TD Snap in edit mode with unfinished changes, the app proceeds on top of them. On failure it presses Undo up to `steps*6+8` times, checking after 0.12 s each time whether the page matches the baseline. If the UI has not repainted in 0.12 s the check reads stale state and another Undo is sent. Then Done commits whatever remains.
- **Related unknown (A3):** `apply_page_edits` and `add_topic_page` press Done before their final check, then rely on Undo still working after re-entering edit mode. If TD Snap clears its undo history on Done, rollback at that stage cannot work, the edit stays applied, and for a new page a retry is refused as a duplicate title.
- **Competing explanation:** TD Snap may repaint synchronously and keep undo history; then the loop is exact.
- **Experiments:** (a) measure time from Undo to UI tree change over 100 presses on the slowest supported machine; (b) apply an edit, press Done, re-enter edit mode, check whether Undo is enabled; (c) start an app edit while TD Snap is in edit mode with one manual change, force a failure, see whether the manual change survives.
- **Proposed direction:** refuse to start if TD Snap is already in edit mode (as Grid 3's `_require_normal_mode` does); wait on a condition, not a sleep; cap undo presses at the number of actions performed; do the final verification before Done.
- **Complexity:** M to L.

### REL-004. Removal confirmation can fire the delete action twice (POSSIBLE, VERIFICATION GAP) - High

- **Where:** `tdsnap/live.py:1791-1792` (name lists), `1814-1840` (`_confirm_removal`).
- **Mechanism:** after pressing delete, the code checks once whether the button is still on the page. If it is, it activates `PrimaryButton`, or failing that the first enabled button named "Delete", "Remove", "Yes" or "OK". If no dialog was shown and TD Snap simply has not repainted yet, "Delete" can be the editor's own delete button, now applying to whatever is selected. If a real dialog appears late, nothing answers it and the next step clicks into it.
- **Mitigation already present:** post-edit verification compares untouched buttons, so a second deletion should be detected, then rolled back (subject to REL-002).
- **Experiment:** on a disposable page, remove a button 50 times with an injected 0 to 500 ms delay before `_confirm_removal`; record whether a confirmation dialog exists in this TD Snap version at all, and what is selected after a delete.
- **Proposed direction:** wait for either "button gone" or "dialog present" as a single condition; only activate a control that is inside a dialog element.
- **Complexity:** S once the real behaviour is known.

### REL-008. AI shows "unavailable" on the first check after launch (PROBABLE) - High

- **Where:** `tdsnap/web/localai.py:330-348` (SHA-256 of every installed model on the status path, cached afterwards), `444` (same hash under `_download_lock`), `tdsnap/web/ollama.py:92` (5 s probe), `tdsnap/web/static/state.js:31` (10 s deadline), `static/ai.js:103-106` (disables Suggest on failure).
- **Mechanism:** hashing a multi-gigabyte model from a cold disk plus a 5 s wait for an absent Ollama can exceed 10 s. The browser reports that it could not check and disables suggestions. The server finishes anyway and caches the hash, so a reload works. That is exactly the "works the second time" pattern.
- **Measured during this audit:** SHA-256 alone runs at about 1.6 GB/s on the audit machine (a server CPU with hashing instructions), so pure hashing of the three shipped models (1.1, 2.5 and 4.7 GB) costs 0.7, 1.5 and 2.9 s. That is not enough by itself to pass 10 s. The time that matters is the cold disk read: at 150 MB/s (hard disk, or a busy laptop SSD just after boot) the same files take roughly 7, 17 and 31 s, and all installed models are hashed in one request. An older CPU without hashing instructions is three to five times slower again. So this is probable with the larger models or more than one model installed, and unlikely with only the small model on a fast SSD. It stays PROBABLE until timed on the owner's machine.
- **Experiment:** time the first `/api/ai/status` after boot on the owner's machine with the shipped model installed (the diagnostic log from Phase A will show this without any manual timing).
- **Proposed direction:** verify the hash at install time and store a sidecar record (size, mtime, hash); status reads the sidecar; re-verify in the background.
- **Complexity:** S.

### REL-010. Two instances can run at once (mechanism CONFIRMED, frequency unknown) - High

- **Where:** `tdsnap/web/server.py:2228-2252` (1 s HTTP probe, fallback to a random port), `541-558` (`clear_leftover_sessions` spares only this process's sessions); `tdsnap/web/localhttp.py:65-81`.
- **Mechanism:** there is no mutex or lock file. If the running instance takes more than a second to answer (busy hashing a model, or in a long automation call), a second launch decides the port is taken by something else and starts on a random port. Now two servers share `settings.json`, the session folder and the model `.part` file. "Clear all saved data" in one deletes the other's working copies. On Windows two processes may also both bind 8765 because the server socket allows address reuse; requests then reach either process, giving token mismatches and "unknown or expired session".
- **Experiments run during this audit (Linux):**
  - Two launches started at the same instant, three trials: the second always printed "Already running at http://127.0.0.1:8765" and exited. The simultaneous-start race did **not** reproduce on Linux.
  - First instance made unresponsive (process suspended) while a second was launched: the second started its own server, `AAC Editor running at http://127.0.0.1:44909`, and both processes then ran side by side sharing one session folder (`tdsnap-editor-<uid>`) and one settings file. So the mechanism is **confirmed**: any time the running copy takes more than one second to answer its health check, a second copy starts.
- **Still unknown:** how often a real instance is that slow (candidates: Windows under load at login, antivirus scanning the packaged executable, a long in-process AI generation), and the Windows same-port case, which needs Windows socket semantics.
- **Experiment:** on Windows, start the app, begin a model download or a generation, start the app again; list processes and ports. The Phase A log records an instance ID and port on every line, so a single user report will show it.
- **Proposed direction:** a named mutex on Windows and a lock file elsewhere, taken before anything else; a second launch asks the first to show its window and exits.
- **Complexity:** M.

### REL-017. TD Snap reads are not robust to the UI changing under them (PROBABLE, VERIFICATION GAP) - High

- **Where:** `tdsnap/uia.py:162-201` (`_matches` and `walk` guard only `GetChildren`), `278-287` (`wait_for`: deadline checked before each poll, no final poll); `tdsnap/live.py:151` (`ignore=()`), `1333-1364`, `1416-1421`.
- **Mechanisms:**
  1. Any property read on an element that disappears mid-walk raises a COM error, and on the TD Snap path nothing is ignored, so one repaint during a tree walk aborts the operation.
  2. Each poll is a full cross-process tree walk to depth 10 to 12. With a 2 s timeout ("Link to new page", `live.py:1270-1274`) a slow PC gets one or two polls.
  3. After clicking a button, the editor panel is read immediately. It can still show the previous button's label and message, so a correct edit fails verification and is rolled back. `_verify_page_state` does this click-and-read for every untouched button whose accessible name differs from its label, so pages with many phrase buttons multiply the chance.
- **Note:** `grid3._rect` catches `(OSError, AttributeError)` on the assumption that a COM error is an `OSError`. That assumption needs checking on Windows; if it is wrong the handler does nothing.
- **Experiment:** fake UIA tree with injectable vanish and stale-read faults (doc 05) proves the code's behaviour; a real run on a slow machine with the diagnostic log proves the frequency.
- **Proposed direction:** treat "element vanished" as "poll again"; always poll once after the deadline; after selecting a button, wait until the editor's label field equals that button's expected label before reading anything else.
- **Complexity:** M.

### REL-019. Reads of TD Snap's own database fail silently (PROBABLE, VERIFICATION GAP) - Medium

- **Where:** `tdsnap/live.py:371, 400, 430, 453, 523, 612, 787, 934` (every read: `mode=ro`, 1 to 2 s timeout, any error becomes `None` or `[]`), fallbacks at `588-702`.
- **Mechanism:** when a read fails, the grid is guessed from visible button positions, hidden cells are no longer reserved, and names are not resolved to labels. TD Snap writes this file around edit and Done, which is when verification reads it. With more than one TD Snap user, identifying the active page set requires every visible button name to be in the database, so a button added a moment ago can make the page set unidentifiable.
- **Experiment:** the diagnostic log records every fallback with its error code; one real session will show whether this happens.
- **Proposed direction:** distinguish "locked, retry briefly" from "not found"; if content cannot be read, refuse the edit instead of guessing.
- **Complexity:** M.

### REL-020. Save fails because the app is reading its own working copy (PROBABLE, Windows only) - Medium

- **Where:** read endpoints open `current` without the session lock (`tdsnap/web/server.py:1451-1478, 1731`); edits replace it with `os.replace` (`tdsnap/atomic.py:36`); grid-set edits map the failure to "another program is using the file" (`server.py:1663`).
- **Mechanism:** on Windows, replacing a file that any handle has open without delete-sharing fails. The vocabulary and layout reads run in the background while the user works, so they can overlap a save.
- **Experiment:** Windows CI test: hold `current` open in one thread and apply an edit in another.
- **Proposed direction:** take the session lock (shared for reads, exclusive for replace); retry the replace briefly on `PermissionError`.
- **Complexity:** S to M.

### Lower-priority possibilities

| Item | Where | Status | Note |
|---|---|---|---|
| Grid measurement differs between preview and edit mode | `live.py:670-701, 743, 1038` | POSSIBLE | Trailing empty rows or columns are not inferred; slot numbers could point at different cells. Mostly causes false verification failures |
| Grid 3 window match takes the first title starting "Grid 3 - " | `grid3.py:215-235` | CONFIRMED in code, low impact | A browser tab with that title above Grid 3 breaks connect |
| Grid 3 foreground check is per process, not per window | `grid3.py:901-925` | POSSIBLE | An unexpected Grid 3 dialog would receive keys, including Enter |
| Unexpected dialogs in either app | both | VERIFICATION GAP | No general handling exists |
| Grid 3 move uses the clipboard | `grid3.py:1651-1653` | CONFIRMED, cosmetic | User's clipboard is overwritten |
| Suggestions land on a page the user has left | `static/ai.js:826-846`, `static/connect.js:756-770` | PROBABLE | Reply is not checked against current page |
| Live preview silently re-targets the plan to whatever page TD Snap shows | `static/connect.js:756-770` | CONFIRMED | By design, but only a small note tells the user |
| Lost response after a successful write | `static/review.js:450-516` | PROBABLE | User sees "isn't responding, try again"; only new-page creation is reconciled. The fingerprint guard prevents a duplicate apply, but the user is not told the edit succeeded |
| llama.cpp out-of-memory kills the editor | `localai.py:298` | PROBABLE | Memory gate uses total RAM |

## History: fixes that addressed symptoms

| Commit | What it fixed | What it left |
|---|---|---|
| `6cc8b57`, `576d12c` (spoken names vs labels) | `apply_page_edits` verification | The same comparison in `add_topic_page` (REL-016) |
| `479fe56` (leave Grid 3 edit mode after failed rollback) | `apply` path | The probe path (REL-015) |
| `09301fc` (polling and saved-settings races) | Live poll sequencing | Download poll overlap, `checkAi` dropping newer requests (REL-022) |
| `ef6e703` (stale `.part`, bounded probes) | Single-process download hygiene | Two-instance case; cleanup only at next download (REL-010, REL-022) |
| `9741587` (say once when TD Snap goes away) | Lost-connection banner | The banner also fires for an expired token (REL-009) |
| `0ea79be`, `f3356e5` (browser regressions) | Tests green at the time | No merge gate, so the next red merge went in (REL-026) |

The pattern: the fix is applied where the symptom was seen, and the duplicated twin of that code is missed. That is why doc 06 includes a small number of targeted de-duplications; they are reliability work, not tidying.

## What must be measured before ranking can be trusted

1. One recorded session per app on the owner's machine with the Phase A diagnostic log enabled: 20 adds, 10 changes, 10 removals, 5 undos on disposable content.
2. The three Undo experiments under REL-002.
3. The foreground experiment: apply an edit from the browser tab with TD Snap behind another window, minimised, and on a second monitor.
4. Cold-start timing of `/api/ai/status` and of server start itself.
5. The owner's own description of which failures occur most. This should reorder Phase C.
