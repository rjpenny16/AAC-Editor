# 07. Release readiness checklist

The gate for calling AAC-Editor stable enough for routine use with clients' communication systems. Every item needs evidence (a CI run, a log archive, a signed session record), not a statement. Items are split by how they can be proven.

**Status on the audited commit `69ffa9d`: not ready.** Unmet items are marked with the issue that blocks them. See [06](06-RELIABILITY-RECOVERY-ROADMAP.md) for the plan.

A release must not be described as production-ready on the strength of section 1 alone. Section 1 shows the app's own logic is right. Only section 2 shows it works with TD Snap and Grid 3.

## 1. Provable automatically (CI)

### Build and checks

- [ ] All jobs in the Tests workflow pass on the release commit, with no test skipped, weakened or retried to achieve it. *Blocked: REL-026.*
- [ ] Required status checks are enabled on `main`, confirmed at release time.
- [ ] Browser suite passes on Linux Chromium and on Windows Edge.
- [ ] Failed browser runs upload traces.
- [ ] `pip-audit` and `npm audit` report no known high or critical vulnerabilities.
- [ ] Packaging smoke test passes on the release commit.

### Data integrity

- [ ] No open issue of severity Critical or High in the "could damage or mislead about vocabulary data" group. *Open today: REL-001, REL-002, REL-003, REL-004, REL-005, REL-006, REL-007.*
- [ ] Every row of both failure-point tables in [04](04-DATA-INTEGRITY-AND-SAFETY.md) has a passing automated test asserting the required outcome class.
- [ ] Single-fault sweep passes for add, change, move, remove, new page, undo and batch, on both apps' fakes.
- [ ] In the sweep: Undo presses never exceed actions performed; no input is sent after a failed precondition; a batch never continues after an outcome other than `verified` or `refused`.
- [ ] Round trip passes for `.sps`, `.spb`, `.gridset`, `.obf`, `.obz`: open, edit, save, re-open, compare.
- [ ] Saving over the source file is refused. *Blocked: REL-006.*
- [ ] A saved copy is re-opened and validated before success is shown.
- [ ] Unsaved working copies survive exit and restart. *Blocked: REL-007.*
- [ ] No code path shows a success heading unless the outcome is `verified` or `verified_with_gaps`. *Blocked: REL-014.*

### Regression protection

- [ ] Every confirmed issue in [02](02-CONFIRMED-BUGS-AND-ROOT-CAUSES.md) is closed with a test that failed before its fix.
- [ ] Seeded random-timing suite: 500 seeds per operation, zero failures.

### Lifecycle and connection

- [ ] A second launch, by either `launch.bat` or the installed app, never starts a second server and never ends the first. *Blocked: REL-010, REL-007.*
- [ ] Quit is refused during a live edit.
- [ ] After a server restart the open page shows an "app restarted" state, not a TD Snap error. *Blocked: REL-009.*
- [ ] An automation call that hangs ends in `unknown` within its deadline and does not block other requests. *Blocked: REL-011.*

### AI isolation

- [ ] With the AI extra not installed, with Ollama absent, with a corrupt model file, and with the inference process killed mid-generation, every editing test still passes.
- [ ] First AI status after a cold start returns in under 2 seconds with the shipped model installed. *Blocked: REL-008.*
- [ ] No AI state disables an editing control.
- [ ] With Ollama absent, neither launch path shows an Ollama error unless the user selected Ollama. *Blocked: REL-028.*
- [ ] When local AI is not ready, the manual fallback (compose prompt, paste list) is offered and makes no network request.

### Errors and diagnostics

- [ ] Every error code has one message answering: what happened, was anything changed, is the original safe, what next, is retry safe, reference.
- [ ] No user-facing message is generic ("Something unexpected went wrong") without those answers.
- [ ] Operation log exists in the packaged app. *Blocked: REL-025.*
- [ ] Seeded-label privacy test: no label, message, page name, file name or path appears in the log or the support report.
- [ ] "Clear saved data" removes the log.

### Security

- [ ] `/api/diagnostics` requires the token. *Blocked: REL-024.*
- [ ] Oversized spans and coordinates in a grid set are refused. *Blocked: REL-012.*
- [ ] Items S-7 and P-4 of [SECURITY_AUDIT.md](../SECURITY_AUDIT.md) fully applied.

## 2. Requires Windows with real TD Snap and Grid 3

All sessions use a disposable TD Snap user and a copy of a stock grid set, with a backup taken first and diagnostic mode on. Session definitions are in [05](05-TESTING-AND-DIAGNOSTICS.md). Each session record states: date, machine, Windows build, display scaling, TD Snap version, Grid 3 version, app version, who ran it, and where the log archive is.

### Behaviour discovery (T3-1)

- [ ] Each VERIFICATION GAP question in [03](03-INTERMITTENT-FAILURE-INVESTIGATION.md) has a recorded answer: Undo timing; Undo after Done; behaviour when the AAC app is already in edit mode; whether a delete confirmation exists; foreground rules from a browser-originated request; page-set database locking; COM error type.
- [ ] The scripted fake UI tree has been updated to match those answers.

### Functional (T3-2)

- [ ] `TDSNAP_LIVE_E2E=1` suite passes.
- [ ] `GRID3_LIVE_E2E=1` suite passes.
- [ ] Each of: add, rename, change spoken message, move, remove, create page, link page, batch of three pages, undo, performed by hand on each app and checked by eye against the result screen.

### Repeated workflow targets (T3-3)

Per app, 100 consecutive scripted cycles (add 3, change 1, move 1, remove 1, undo):

| Measure | Target |
|---|---|
| Outcome `verified` | at least 98 of 100 |
| Outcome `refused` or `rolled_back` (with the real page confirmed unchanged) | at most 2 of 100, each explained from the log |
| Outcome `partial` or `unknown` | 0 |
| **Result screen claim differs from the real page** | **0. A single case fails the gate** |
| AAC app left in edit mode after any cycle | 0 |
| Median duration variation between first and last 10 cycles | under 25% (no slow degradation) |

A failure restarts the count only after its root cause is found and fixed.

### Disturbance (T3-4)

For each of: focus taken by another window; AAC app minimised; AAC app moved to a second monitor between review and apply; unexpected dialog opened; editor process killed mid-edit; AAC app closed mid-edit; CPU throttled to simulate a slow PC:

- [ ] The outcome class reported matches the real page, checked by eye, in 10 of 10 trials each.
- [ ] No input reached any window other than the AAC app (screen recording reviewed).
- [ ] After "editor killed mid-edit", the next start reports the interrupted edit.

### Lifecycle (T3-5)

- [ ] 50 cold starts: 50 reach a connected state; time to ready recorded.
- [ ] Relaunch while running, 10 times: one instance, no lost work.
- [ ] Elevated restart for Grid 3 under the same account and under a different administrator account: both connect, or the second is refused with a clear message.

### Installation (T3-6)

On clean Windows 10 and Windows 11, as a standard user and as an administrator:

- [ ] Install from the release installer; first launch reaches the welcome screen.
- [ ] Upgrade from the previous release keeps settings, drafts and templates.
- [ ] Uninstall removes the program; documented user data location is as described in [PRIVACY.md](../../PRIVACY.md).
- [ ] Reinstall works.
- [ ] The unsigned-installer warning seen by the user matches what the README says to expect.

### Environment spread (T3-7)

- [ ] Display scaling 100%, 125%, 150%.
- [ ] Two monitors.
- [ ] A second TD Snap version, if one can be obtained; otherwise the supported-version statement below names exactly one.
- [ ] AI on a machine with 8 GB RAM: loads or refuses cleanly; never crashes the editor.

### Soak (F4)

- [ ] Two weeks of use by the owner on disposable content with diagnostic mode on; every failure traced to a root cause and either fixed or documented as a known limitation.

## 3. Release statement

Each release publishes, in the changelog:

- [ ] **Supported environments**: exactly the Windows builds, TD Snap versions, Grid 3 versions and display scalings tested in section 2. Anything else is "untested" and the app says so at connect.
- [ ] **Known limitations**, including, permanently: live editing is not transactional; language other than English is unsupported for live editing; live editing relies on the AAC app's own Undo.
- [ ] Links to the CI run and the session records.

## 4. Conditions for routine use with a client's system

Even after the gate is met:

1. Take a backup in TD Snap or Grid 3 before the first live edit of a session. The app prompts for this.
2. Prefer file mode (edit an exported copy, import it back) when a change is large; it has the strongest guarantees.
3. Keep the AAC app in front and do not use the mouse or keyboard during a live edit.
4. After any outcome other than "Done, verified", look at the named page in the AAC app before doing anything else.
5. Stay on the versions named in the release statement.

## 5. Recommended, not gating

- A self-hosted Windows runner with TD Snap and Grid 3 installed, so the opt-in live suites run on every change to `live.py`, `grid3.py` or `uia.py`.
- Code signing for the installer.
- A second person performing T3-2 by hand before each release.
