# 06. Reliability recovery roadmap

Audited commit `69ffa9d`. This is the implementation plan. **Nothing in it has been started; it needs the owner's approval first.** Issue IDs refer to [02](02-CONFIRMED-BUGS-AND-ROOT-CAUSES.md) and [03](03-INTERMITTENT-FAILURE-INVESTIGATION.md). It supersedes the ordering of Track E (Phases 16 to 20) in [ROADMAP.md](../../ROADMAP.md) until the release gate in [07](07-RELEASE-READINESS-CHECKLIST.md) is met; Phases 17, 18 and most of 20 (fewer steps, design system, polish) are paused.

## Rules for the whole programme

1. No new features until the release gate is met.
2. One issue or one tightly related group per pull request. No pull request mixes a live-automation change with anything else.
3. Every fix lands with a test that failed before it.
4. No merge with a red check. No test is weakened, skipped or retried to get green.
5. Live-automation changes are not considered done until exercised in a Tier 3 session (doc [05](05-TESTING-AND-DIAGNOSTICS.md)).
6. Refactoring only where listed below, each justified by a defect it removes.

Complexity: S = under a day, M = one to three days, L = about a week. These are estimates of engineering effort including tests, not calendar promises, and hardware sessions are extra.

## Phase A. Trustworthy baseline

Goal: a green, gated CI that keeps its evidence, and a log on the owner's machine.

| # | Work | Issues | Files | Size |
|---|---|---|---|---|
| A1 | Fix the badge's accessible name; update the assertion that pins the wrong one; add scans of each connected state with no modal | REL-026 | `web/static/connect.js`, `web/static/index.html`, `tests/test_live_edit.spec.js` | S |
| A2 | Upload Playwright `test-results/` on failure; require all Tests jobs to pass before merging to `main` (repository setting, owner action) | REL-026 | `.github/workflows/tests.yml` | S |
| A3 | Replace the wait-then-assert-nothing tests with request counting | REL-026 | `tests/test_live_edit.spec.js` | S |
| A4 | Operation log, summary level; operation IDs through `_drive` and the file-edit routes; error-code catalogue (first version) | REL-025 | new `web/oplog.py`; `web/server.py`, `uia.py`, `live.py`, `grid3.py` (instrumentation only, no behaviour change); `packaging/launcher.py` | M |
| A5 | Diagnostic mode (step records) and support-report changes; token on `/api/diagnostics`; privacy test | REL-025, REL-024 | `web/diagnostics.py`, `web/static/support.js`, `web/static/settings-panel.js`, `tests/test_privacy_contract.py`, `PRIVACY.md` | M |
| A6 | Correct the docs that overstate verification | doc 02 minor | `README.md`, `docs/QA_PLAN.md`, `ROADMAP.md` | S |
| A7 | Write and run Tier 3 session T3-1 (behaviour discovery) on disposable content; record answers in doc 03 | REL-001, 002, 004, 005, 017, 019 | docs only | hardware, about half a day |

- **Depends on:** nothing. A7 needs A4 and A5 and a Windows machine.
- **Regression risk:** low. A4 touches the live modules but only adds calls that record; guard with a test that logging failures never affect an operation.
- **Acceptance:** `main` green for legitimate reasons; a deliberately failing pull request cannot be merged; a failed browser test has a downloadable trace; a live edit on the owner's machine produces log records with no vocabulary in them (checked by the seeded-label test); T3-1 answers recorded.

## Phase B. Protect user data

Goal: no operation can leave data changed without saying so; no path overwrites or discards the user's work.

| # | Work | Issues | Files | Size |
|---|---|---|---|---|
| B1 | Outcome type (`refused`, `verified`, `verified_with_gaps`, `rolled_back`, `partial`, `unknown`) from the live modules through the API to the result screen; stop rule in `apply_batch` uses it and catches every exception; cleanup failures never replace the primary error | REL-003, REL-014, REL-015 | `errors.py`, `live.py`, `grid3.py`, `web/server.py`, `web/static/result.js`, `review.js` | M |
| B2 | Save safety: refuse source as destination, default to `.edited`, re-open and validate the saved copy | REL-006 | `web/server.py`, `web/desktop.py` | S |
| B3 | Shutdown safety: quit refuses while a live edit runs and warns on unsaved file edits; unsaved working copies survive exit and are offered at next start; launch scripts focus the running instance instead of quitting it | REL-007, REL-021 | `web/server.py`, `web/desktop.py`, `launch.bat`, `launch.sh`, `web/static/connect.js` | M |
| B4 | Intent journal for live edits; "an edit was interrupted" notice at startup | L15 in doc 04 | `web/oplog.py`, `web/server.py`, frontend notice | S |
| B5 | Dirty-state refusals: TD Snap already in edit mode, any dialog present | REL-002 | `live.py` | S |
| B6 | Bounded rollback for TD Snap: condition-based waits, Undo presses capped at actions performed, stop on unreadable state, final verification before Done | REL-002 | `live.py` | M to L |
| B7 | Bounded rollback for Grid 3: no save inside the loop, unreadable file is `unknown`, single rollback attempt; timestamped `.gridset` backup before the first key | REL-001 | `grid3.py` | M |
| B8 | Removal confirmation waits on one combined condition and only activates controls inside a dialog | REL-004 | `live.py` | S |
| B9 | Shared verification for `apply_page_edits` and `add_topic_page` | REL-016 | `live.py` | M |
| B10 | Scripted fake UI tree with fault schedule; single-fault sweep for all operations | REL-027 | `tests/` only | L |
| B11 | Fault injection for `.gridset` writes, `atomic.py`, save; round-trip tests; move the file-edit fingerprint check inside the session lock | doc 04 F-rows | `tests/`, `web/server.py` | M |

- **Order inside the phase:** B10 first (it is the safety net for B5 to B9), then B1, then the rest. B2, B3, B4 and B11 are independent and can go in parallel.
- **Depends on:** Phase A. B6, B7 and B8 depend on the answers from A7; if hardware is not yet available, implement the conservative version (refuse, cap, stop) and leave "verify before commit" for later.
- **Regression risks:** B5 to B8 make the app refuse or stop in situations where it used to carry on. Some edits that succeeded by luck will now be refused with an explanation. That is intended, but the messages must be right, and Tier 3 must confirm normal edits are not refused.
- **Acceptance:** every row of both failure-point tables in doc 04 has a passing test asserting the required outcome; in the sweep, Undo presses never exceed actions performed and no input is sent after a failed precondition; a batch stops on anything but `verified` or `refused`; the three scratch reproductions from this audit are permanent tests; T3-4 disturbance session shows outcome claims matching the real page every time.

## Phase C. Eliminate intermittent failures

Goal: the same action in the same situation gives the same result.

| # | Work | Issues | Files | Size |
|---|---|---|---|---|
| C1 | Shared `require_foreground` (window-level) before every input in both apps; restore minimised window; integrity-level check at connect | REL-005, REL-023 | `uia.py`, `live.py`, `grid3.py` | M |
| C2 | Robust reads: vanished element means poll again; one poll after the deadline; settle-wait after selecting a button; timeouts expressed as minimum polls and minimum time | REL-017 | `uia.py`, `live.py` | M |
| C3 | Position-independent page fingerprint | REL-018 | `live.py`, tests | M |
| C4 | Database reads: distinguish locked from absent, brief bounded wait on lock, refuse instead of guessing when content is unreadable; URI helper | REL-019, REL-013 | `live.py`, `web/server.py`, `formats.py`, `cli.py` | M |
| C5 | Deadlines and cancellation for automation jobs; `unknown` outcome and locked state after a write deadline; reads abandoned on client timeout | REL-011 | `uia.py`, `web/server.py`, frontend | M |
| C6 | Single-instance lock; second launch shows the first | REL-010 | `web/server.py`, `web/desktop.py`, `packaging/launcher.py` | M |
| C7 | Typed API errors; token re-fetch on 403; "app restarted" state; live poll no longer treats every error as "TD Snap missing" | REL-009 | `web/static/api.js`, `connect.js`, `livewatch.js` | S |
| C8 | Session read/replace locking; brief retry on `PermissionError`; correct message | REL-020 | `web/server.py`, `atomic.py` | S to M |
| C9 | Block navigation away from an in-flight apply; reconcile a lost response for existing-page edits using the operation ID | H-14, doc 03 | `web/static/review.js`, `web/server.py` | M |
| C10 | Version awareness: record TD Snap and Grid 3 versions; warn on untested versions; one module holding every selector and UI string | H-04, H-05 | `live.py`, `grid3.py`, new selectors module | M |

- **Depends on:** Phase B (the fake UI tree and outcome type). C1 to C4 are ordered by expected impact; reorder using the first real logs.
- **Regression risks:** C3 changes a safety guard; keep the old fingerprint in parallel for one release and log disagreements before removing it. C5 changes threading; keep the single-thread rule.
- **Acceptance:** seeded random-timing suite passes for 500 seeds per operation; T3-3 meets the targets in doc 07; T3-5 shows 50 of 50 cold starts connect; moving the TD Snap window between review and apply no longer refuses the edit.

## Phase D. Stabilise AI and secondary workflows

Goal: AI can fail in any way without affecting editing, and says what state it is in.

| # | Work | Issues | Files | Size |
|---|---|---|---|---|
| D1 | Status without hashing on the request path: verify at install, sidecar record, background re-verify | REL-008 | `web/localai.py` | S |
| D2 | AI state machine (below), one source of truth on the server, request IDs, server-side deadline and cancel; frontend renders from state; download poll with in-flight guard and bounded errors | REL-022 | `web/localai.py`, `web/engines.py`, `web/server.py`, `web/static/ai.js` | M |
| D3 | Run built-in inference in a child process; memory gate on available RAM | REL-022 | `web/localai.py`, packaging | L |
| D4 | Suggestions carry the page and request they were made for; stale ones are discarded | doc 03 | `web/static/ai.js` | S |
| D5 | Grid-set bounds; `zlib.error`; native-dialog exception mapping; settings load errors | REL-012, doc 02 minor | `grid3.py`, `gridset.py`, `obf.py`, `web/desktop.py`, `web/settings.py` | S |
| D6 | Stale `.part` cleanup at startup, guarded by the single-instance lock | REL-022 | `web/localai.py` | S |

AI state model. One state at a time; every transition is logged with its code.

```
not_configured -> checking -> { ready | needs_model | engine_unreachable | unsupported_hardware }
needs_model -> downloading(progress) -> verifying -> ready
downloading -> download_failed(code) -> needs_model
verifying -> corrupt -> needs_model          (file removed)
ready -> loading -> { loaded | load_failed(code) }
loaded -> generating(request_id) -> { loaded + result | loaded + failed(code) | loaded + cancelled }
any -> engine_crashed -> not_configured      (child process exit; editor unaffected)
```

Rules: one download and one generation at a time, enforced on the server; a new generation request cancels the previous one; every state has a user-facing sentence and a next step; no AI state can disable an editing control.

- **Depends on:** C6 (single instance) for D6; otherwise independent of B and C and can run in parallel with C if capacity allows.
- **Regression risk:** D3 changes packaging; verify in the installer smoke test.
- **Acceptance:** killing the inference process during generation leaves the editor fully usable and shows a clear AI error; first status check after a cold start returns in under 2 seconds with a multi-gigabyte model installed; with AI disabled or absent, every editing test passes unchanged.

## Phase E. UX and maintainability

Goal: every failure is understandable, and the duplicated code that caused repeat bugs is gone.

| # | Work | Files | Size |
|---|---|---|---|
| E1 | Error copy pass against the six questions, driven by the error-code catalogue; technical detail only in the report | `web/static/*`, `web/server.py` | M |
| E2 | Result screen: heading from outcome class; "what was checked" list | `web/static/result.js` | S |
| E3 | Extract the three validate, snapshot, save blocks into one function | `web/server.py` | S |
| E4 | Split `apply_page_edits` into plan, execute, verify, restore, each testable against the fake tree | `live.py` | M |
| E5 | Public interface between `live.py`, `grid3.py`, `gridset.py` instead of private imports | those modules | S |
| E6 | Accessibility: scans for every screen state including behind-modal content; NVDA and Narrator pass | tests, manual | M |
| E7 | User guide page: what each outcome means and what to do | docs | S |

- **Depends on:** B1 and A4. E4 must come after B10 so it is refactored under the sweep.
- **Not included:** design-system work, logo, new menus (ROADMAP Phases 17 and 18). Deferred.
- **Acceptance:** no user-facing string matches "something went wrong" or "try again" without the other five answers; every error code has a browser test.

## Phase F. End-to-end validation

Goal: evidence, on real machines, that the gate in doc 07 is met.

| # | Work | Size |
|---|---|---|
| F1 | Tier 3 sessions T3-2 to T3-7 on disposable content, logs archived with the release | 2 to 3 days of hands-on time |
| F2 | Full regression: all CI jobs, Windows Edge browser job, packaging smoke | CI |
| F3 | Clean-install matrix: Windows 10 and 11, standard user and administrator, install, upgrade, uninstall | half a day |
| F4 | Two-week soak: the owner uses the release candidate on disposable content, diagnostic mode on; every failure investigated to root cause | elapsed time |
| F5 | Release-readiness review against doc 07; sign-off recorded in the changelog | S |

- **Acceptance:** doc 07 complete with evidence links.

## Dependencies at a glance

```
A1-A3 ──┐
A4-A5 ──┼─> A7 (hardware) ──> B6, B7, B8
        └─> B10 ──> B1 ──> B5..B9 ──> C1..C5 ──> E4
            B2, B3, B4, B11 (parallel)     C6 ──> D6
            D1, D2, D4, D5 (parallel with C)      D3
                                   all ──> E1..E7 ──> F
```

## Independent review of this plan

### 1. Senior debugging engineer: causes or symptoms?

- *Critique:* The four roots are sound, but most live findings are unobserved. The plan risks fixing imagined problems while the real one stays hidden.
- *Critique:* Previous fixes missed duplicated twins. Nothing in the first draft prevented that recurring.
- *Revision:* Logging and the T3-1 discovery session were moved into Phase A, ahead of all live-code changes. Phase C's order is explicitly provisional until real logs exist.
- *Revision:* Added B9, E3 and E4 (shared verification, shared save block, split of `apply_page_edits`) as reliability items, and rule 6 to stop wider refactoring.

### 2. Windows automation engineer: timing, focus, permissions, state?

- *Critique:* Foreground checks at process level are not enough; a dialog in the same process still receives keys. Coordinate clicks are fragile under display scaling and multi-monitor setups.
- *Critique:* Windows may refuse `SetForegroundWindow` from a background process; the plan must define what happens then, not assume it can be forced.
- *Critique:* An unsigned build without UIAccess cannot drive an elevated app; "restart as administrator" for Grid 3 changes the user profile.
- *Revision:* C1 specifies window-level checks and a refusal path that asks the user to click the AAC app, with no attempt to force focus. Scaling and second-monitor cases were added to T3-7. REL-023 covers the profile problem. C10 puts every selector in one module and records app versions.
- *Open:* prefer UI Automation patterns (Invoke, Value) over coordinate clicks wherever TD Snap exposes them. This needs T3-1 to know what TD Snap exposes; added as a question there, not as committed work.

### 3. AAC-focused SLP: are my clients' systems safe?

- *Critique:* "Rollback" is not something I can rely on if it depends on Undo. I need a backup I control, and plain words about what happened.
- *Critique:* A message that says "state unknown" is alarming unless it tells me exactly which page to look at and what to compare.
- *Critique:* I work on a client's device in a session. I cannot have the tool half-finish and leave the device in edit mode when I hand it back.
- *Revision:* B7 adds an automatic Grid 3 file backup; doc 04 adds a prompted TD Snap backup; doc 07 makes "backup taken" part of routine-use conditions. E7 adds a user guide to outcomes. B1 and E1 require the page name (shown locally, never logged) and the list of affected buttons in `partial` and `unknown` messages. L10 in doc 04 requires "still in edit mode" to be reported.
- *Stated limit:* live editing cannot be made transactional. Doc 04 gives the exact guarantee that can be offered.

### 4. QA and release engineer: can we demonstrate it?

- *Critique:* The fake UI tree could become a second fiction, like today's mocks.
- *Critique:* "100 cycles" on one machine is one environment.
- *Critique:* A required-checks setting is outside the repository and can be switched off.
- *Revision:* T3-1 results are used to correct the fake, and any Tier 3 failure the sweep did not predict must be added to the fake as a new fault before the fix is accepted. T3-7 adds environment spread, and doc 07 states the supported-environment list as exactly the environments tested. Doc 07 includes "branch protection on" as a checked item at each release.
- *Open:* there is no continuous real-hardware testing. A self-hosted Windows runner with both apps licensed would close this; it is listed in doc 07 as a recommendation, not a gate.

## Estimated total

| Phase | Engineering | Hardware time |
|---|---|---|
| A | about 1 week | half a day |
| B | about 3 weeks | 1 day |
| C | about 3 weeks | 1 day |
| D | about 1.5 weeks (2.5 with D3) | half a day |
| E | about 1.5 weeks | half a day |
| F | a few days | 3 days plus a two-week soak |

Roughly ten to twelve weeks of focused work before the gate can be attempted. Phases A and B alone, about four weeks, remove the confirmed data risks and make every later failure diagnosable.
