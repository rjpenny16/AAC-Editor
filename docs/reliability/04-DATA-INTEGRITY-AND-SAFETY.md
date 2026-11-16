# 04. Data integrity and safety

Audited commit `69ffa9d`. The question here is narrow: **can AAC-Editor damage a communication system, and would the user know?** Issue IDs refer to [02](02-CONFIRMED-BUGS-AND-ROOT-CAUSES.md) and [03](03-INTERMITTENT-FAILURE-INVESTIGATION.md). See also [IMPORT_SAFETY.md](../IMPORT_SAFETY.md).

## Verdict

| Path | Can it corrupt data silently? | Basis |
|---|---|---|
| Exported TD Snap file (`.sps`/`.spb`) | **No evidence that it can.** Strongest path in the app | Scratch copy, validation, atomic replace, fault injection on every SQLite write |
| Grid 3 file (`.gridset`) | Unlikely; less evidence | Same save mechanics; no fault-injection tests; never run against a real Grid 3 file in CI |
| Open Board import/export | Unlikely | Bounded reads, same save path |
| Saving the edited copy (desktop) | **Yes, by overwriting the original**, if the user picks it | REL-006 |
| Live TD Snap | **Cannot be ruled out.** Risk is in failure and rollback, not in the normal path | REL-002, REL-003, REL-004, REL-005 |
| Live Grid 3 | **Cannot be ruled out.** Rollback writes to disk repeatedly | REL-001 |

"Silently" matters. In every live scenario identified, verification would probably detect that something is wrong. The risk is in what happens next: a rollback that goes too far, an error message that hides it, or a batch that keeps going.

## How writes work today

### File mode

1. Upload or native open copies the file into a private session folder as `original` and `current`. The user's file is not touched again until save.
2. An edit copies `current` to a scratch file, applies changes in one SQLite transaction (or rebuilds the zip for a grid set), runs `validate` (table snapshot comparison for TD Snap files), then `replace_durably` over `current`.
3. Save: `atomic_copy(current, destination)`.

Strengths: the original is preserved in the session; every replace is temp file, fsync, rename; `tests/test_fault_injection.py` rejects the Nth write for every N in three builder paths and asserts nothing changed and no transaction is left open.

Gaps:

- No guard against choosing the original as the destination (REL-006).
- The saved copy is not re-opened and checked before "saved" is shown.
- No undo in file mode, although `original` is kept and could provide "revert all".
- `original` and `current` are deleted on clean exit even if edits were never saved (REL-007).
- Fingerprint check outside the session lock on the TD Snap file path allows a double apply of the same plan (doc 02 minor).
- No fault injection for `.gridset` writes, for `atomic.py` itself, or for the save step.
- On Windows, `os.replace` over a file that is open fails (REL-020); the temp file is cleaned up, so this is a failed save, not corruption.

### Live TD Snap

The app does not write TD Snap's files. It drives TD Snap's interface, and reads TD Snap's page set read-only to verify. Safety therefore depends entirely on four things: acting on the right window, acting on the right button, detecting a wrong result, and undoing it.

- Right window: checked once at the start by name and package identity; not checked before each input (REL-005).
- Right button: slot arithmetic from measured geometry, with a review fingerprint as the guard. The guard is strict on content but also sensitive to window position (REL-018).
- Detection: labels, messages, removals and every untouched button are compared after the edit. Symbols and borders are not (REL-014).
- Undo: TD Snap's own Undo button, pressed in a loop with a fixed short wait (REL-002).

### Live Grid 3

Grid 3 must be in normal mode at the start (good). The edit is typed with the keyboard, **saved**, and then verified by reading the saved file. Verification is thorough. But because saving comes first, a wrong result is already on disk when it is detected, and recovery is "undo, save, check" in a loop (REL-001).

## Transaction boundaries

| Operation | Atomic today? | Notes |
|---|---|---|
| One file edit | Yes | Scratch copy plus replace |
| One live page edit | No, by nature | Many UI actions; relies on rollback |
| New page plus link plus buttons (live) | No | Rollback must delete the page and undo the link; orphan page possible (REL-002 A3) |
| Batch of pages (live) | No, and not intended | Each page independent; stop rule is defective (REL-003) |
| Board import into a file | Yes | One transaction; fault injection covers `add_linked_pages` |
| Undo of last live edit | No | Implemented as a reverse edit through the same path |

## Outcome classes

Today the server returns either a report or an error string. The UI cannot tell "nothing happened" from "something happened and I do not know what". Every operation should end in exactly one of these, carried as a field, never inferred from text:

| Outcome | Meaning | What the user is told | Automatic retry? |
|---|---|---|---|
| `refused` | Preconditions failed; nothing was sent to the AAC app or file | What to fix; "nothing was changed" | Safe |
| `verified` | Applied and every checked property matched | "Done", with what was checked | n/a |
| `verified_with_gaps` | Core content verified; listed extras (symbols, borders) could not be | "Done, but check these" | No |
| `rolled_back` | Failed after writing; restoration verified against the baseline | "Not applied. The page is as it was" | Only after the user re-reviews |
| `partial` | Failed after writing; restoration failed or was not attempted; current state was read and is known | Exactly which buttons differ from before | Never |
| `unknown` | The app could not read the final state (hung call, lost window, process killed) | "Check this page in TD Snap before doing anything else", page name, time, what was attempted | Never; live editing locks until the user reconnects and confirms |

Rule: **anything other than `refused` or `verified` stops a batch.**

## Failure-point table

Required end state for a failure injected at each step. "Today" is from reading the code; the live rows are unverified on hardware.

### Live edit (TD Snap and Grid 3)

| # | Failure injected | Required end state | Required outcome | Today |
|---|---|---|---|---|
| L1 | Window not found, wrong app, not foreground | AAC app untouched | `refused` | TD Snap: foreground not checked (REL-005) |
| L2 | Page fingerprint differs from review | Untouched | `refused` | Correct; false positives (REL-018) |
| L3 | AAC app already in edit mode | Untouched | `refused` | Grid 3 correct; TD Snap proceeds (REL-002) |
| L4 | Failure entering edit mode | Untouched, left in normal mode | `refused` | Believed correct |
| L5 | Failure on first write | Baseline restored, verified, normal mode | `rolled_back` | Depends on Undo (REL-002) |
| L6 | Failure mid multi-button edit (button k of n) | Baseline restored | `rolled_back`, else `partial` listing differences | As L5; `partial` not expressible |
| L7 | All writes done, verification read fails (cannot read) | No further writes | `unknown` | Treated as mismatch, triggers rollback; Grid 3 may over-undo (REL-001) |
| L8 | All writes done, verification mismatch | Baseline restored | `rolled_back` or `partial` | As L5 |
| L9 | Failure during rollback | Stop immediately; no more Undo | `partial` or `unknown` | Error text combined; can be masked (REL-003) |
| L10 | Failure leaving edit mode | State described truthfully | Outcome of the edit preserved, plus "still in edit mode" | Replaces the real error (REL-003, REL-015) |
| L11 | Focus stolen mid-edit | Stop before next input | `partial` | TD Snap: input goes to the other window (REL-005) |
| L12 | Unexpected dialog | Stop; do not press anything | `unknown` | Not handled |
| L13 | AAC app closes or crashes mid-edit | n/a | `unknown` | Raw error or timeout |
| L14 | Automation call hangs | n/a | `unknown` after deadline; live editing locked | Hangs for ever (REL-011) |
| L15 | Editor closed or killed mid-edit | On next start: "an edit to page X was interrupted at HH:MM" | `unknown`, from a journal | Nothing recorded (REL-007) |
| L16 | Failure during user-requested Undo | As L5 to L9 | Same classes | Same code path |
| L17 | Batch: page k ends in anything but `verified`/`refused` | Pages after k not attempted; results for 1..k returned | Per-page outcomes | Can continue (REL-003); results lost on non-`PagesetError` |

### File edit and save

| # | Failure injected | Required end state | Today |
|---|---|---|---|
| F1 | Error before the transaction | `current` unchanged | Correct, tested |
| F2 | Error on Nth SQLite write | `current` unchanged, no open transaction | Correct, tested for 3 paths |
| F3 | Validation fails after writing scratch | `current` unchanged, scratch removed | Correct by design; add test |
| F4 | Crash between fsync and rename | `current` is old or new, never mixed | Correct by design (rename is atomic) |
| F5 | `os.replace` refused (locked) | `current` unchanged; clear message; retry safe | Unchanged yes; message misleading (REL-020) |
| F6 | Disk full | `current` unchanged | Correct; clear message for grid sets only |
| F7 | Grid-set rebuild fails mid-zip | `current` unchanged | Believed correct; **no test** |
| F8 | Save to read-only or locked destination | Destination unchanged; working copy kept | Unchanged yes; raw OS text shown |
| F9 | Save destination equals source | Refused | **Overwrites** (REL-006) |
| F10 | Saved file unreadable afterwards | Detected before "saved" is shown | Not checked |
| F11 | Editor exits with unsaved edits | Working copy kept and offered next start | **Deleted** (REL-007) |
| F12 | Editor crashes with unsaved edits | Working copy rebuilt from disk | Works; "saved" flag wrong; cap accounting wrong (REL-021) |
| F13 | Malformed or hostile input file | Refused with a clear message; server stays up | Mostly; memory blow-up (REL-012) |

## Plan for the strongest practical protection

In priority order. Details and acceptance criteria are in [06](06-RELIABILITY-RECOVERY-ROADMAP.md), Phase B.

1. **Introduce the outcome type** above, end to end (server, API, result screen, batch).
2. **Intent journal for live edits.** Before the first input, append one record to a local file: operation ID, app, page identity (hashed), counts of actions, time. Append `done` with the outcome at the end. A record without `done` at startup means L15 happened; tell the user. No labels or vocabulary are stored.
3. **Bounded, honest rollback.** Never press Undo more times than actions were performed. Stop at the first step where state cannot be read. Never save inside a rollback loop. If restoration is not verified, report `partial` with the exact differences, or `unknown`.
4. **Refuse to start in a dirty state.** TD Snap already in edit mode, Grid 3 with unsaved changes, any dialog open, not foreground: all `refused`.
5. **Verify before commit where the app allows it.** TD Snap: final check before Done. Grid 3: investigate on hardware whether the in-memory grid can be read through UI Automation before Ctrl+S; if not, keep save-then-verify but with rule 3.
6. **Backup before live edits.** Grid 3: copy the `.gridset` to a timestamped file in the app's data folder before the first key. TD Snap: the page set cannot be restored by file copy while TD Snap runs, so prompt the user to make a TD Snap backup on first use and at most once a day, and record that they did.
7. **File mode:** refuse source as destination; re-open and validate the saved copy; keep unsaved working copies across exit; add "revert all edits" from `original`.
8. **Fault injection for every row in the two tables above**, using the scripted fake UI tree described in [05](05-TESTING-AND-DIAGNOSTICS.md).

## What can and cannot be guaranteed

- File mode can be made to guarantee "the original is never modified and the working copy is never half-written". Most of this is already true.
- Live mode cannot be made transactional, because the AAC apps offer no transaction. The achievable guarantee is weaker and should be stated to users in these words: **"After any live edit, AAC-Editor will tell you truthfully whether the page is changed, unchanged, or needs checking, and it will never continue on to another page unless the last one was verified."**
- Whether rollback itself is trustworthy depends on TD Snap and Grid 3 behaviour that has not yet been observed. Until the experiments in doc 03 are done, live editing of a client's real system should be preceded by a backup made in the AAC app.
