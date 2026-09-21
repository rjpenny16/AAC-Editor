# AAC Editor

[![Tests](https://github.com/rjpenny16/AAC-Editor/actions/workflows/tests.yml/badge.svg)](https://github.com/rjpenny16/AAC-Editor/actions/workflows/tests.yml)
[![Latest release](https://img.shields.io/github/v/release/rjpenny16/AAC-Editor)](https://github.com/rjpenny16/AAC-Editor/releases/latest)
[![MIT license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

AAC Editor helps AAC users, parents, SLPs, and other professionals
spend less time editing buttons and more time communicating. Add many words or
entire topic pages at once, review every change before it runs, and update the
page or grid already open in TD Snap or Grid 3 so it keeps its existing sharing and sync
identity—saving hours of repetitive work.

![AAC Editor setup screen with TD Snap, Grid 3, and exported-file options](docs/screenshot.png)

## Download

Download **`AACEditor-*-windows-x64-setup.exe`** from the
[latest release](https://github.com/rjpenny16/AAC-Editor/releases/latest) and run
the installer. Python is not required. The installer places AAC Editor beneath
Program Files and its shortcuts launch that installed executable.

Releases are not code-signed — no free Authenticode certificate is available
to this project — so Windows SmartScreen shows **Windows protected your PC** on
first run and names the publisher as unknown. Before choosing *More info → Run
anyway*, confirm the download is the one the public workflow built: compare
`Get-FileHash` against the `.sha256` file attached to the release, or run
`gh attestation verify <installer> --repo rjpenny16/AAC-Editor`. A file that
fails either check must not be run.

Live Grid 3 editing needs Windows administrator approval, each time you
connect. That is a consequence of the release being unsigned: an executable can
only reach Grid 3 without elevating if it carries a trusted Authenticode
signature, so AAC Editor asks for approval and reopens itself elevated instead.
If you are not an administrator on the computer, someone who is has to approve
it. TD Snap editing and exported files never need any of this, and the app says
so on the Grid 3 screen rather than leaving you to work it out.

## What it does

- Adds words to exact empty spaces on an existing TD Snap page — live, or in an
  exported copy.
- Fixes a typo or retires a word: changes what an existing TD Snap button says,
  moves it to another cell, or removes it, with the same review, verification,
  and rollback an addition gets. Buttons that open a page or run an action stay
  locked and say why.
- Undoes the last change it made, once, through the same review step — while the
  page is still as AAC Editor left it.
- Does the same on the grid open in Grid 3: adds speaking cells to safe empty
  spaces, changes, moves, or removes existing speaking cells, undoes the last
  change, and creates a new grid linked from the open one — every step
  performed by Grid 3's own Edit Mode and checked against the saved grid-set
  file afterwards. Cells that jump to another grid, run a command, or span
  more than one square stay locked and say why.
- Creates word or color-coded topic pages and links them from an existing page.
- Imports a word list: paste a spreadsheet column or open a CSV/TSV, map which
  column is the label, the message, the function, and the symbol words, and see
  everything that will not fit named before anything is added.
- Saves a page you have built as a named template and reuses it for the next
  person — one topic page built once, used across a caseload.
- Queues several pages, reviews them as one list, and applies them in one go,
  reporting what happened to every page including any it did not attempt.
- Rejects duplicates, checks capacity, and never touches a button the review
  step did not name. A word that already exists elsewhere in the page set is
  pointed out but never blocked.
- Adds matching TD Snap symbols when TD Snap can find them, searching the words
  you choose — or none at all, per button.
- Suggests AAC-friendly placement and optional words or phrases with local AI.
  Suggestions arrive as candidates you keep or discard, so nothing a model
  produced reaches the page unasked, and every one you keep is still steerable:
  swap it for another, ask for more like it, or throw it away and it is not
  offered again.
- Verifies the completed edit and reports anything that still needs review.

If something goes wrong, **Copy a support report** in the footer collects the
versions and capability flags a bug report needs. It never includes page names,
button labels, or file names, so it is safe to paste in full.

## Private by design

The app listens only on your computer. Direct mode edits TD Snap through its
own Windows controls, so the active page set keeps its existing sharing and
sync identity. AAC Editor does not upload page-set files or button vocabulary;
the optional single-topic grounding request is the only exception described
below.

AI is optional and local. It is one button to start: the **Stuck for ideas?**
panel on the vocabulary screen says whether suggestions are **Ready** or need a
one-time **Setup**, and setting them up downloads the model once while you carry
on adding words.

- The packaged app can download Qwen2.5 1.5B Instruct once (~1 GB, Apache-2.0)
  and run it offline. Every built-in model is pinned to an exact URL, byte size
  and SHA-256, and a download that does not match all three is thrown away.
  Where the app offers more than one, the larger ones are unlocked by the
  memory this computer is *measured* to have — a machine whose memory cannot be
  read is offered the small model and nothing bigger.
- If [Ollama](https://ollama.com/download) is already running, the app can use
  one of its installed models instead — picked from a list of what you actually
  have, not typed from memory. **Suggestion settings** chooses which engine
  runs; a choice that cannot run is stood in for, and the panel says which model
  wrote the suggestions.
- Suggestions can be asked to match how your page set already writes a button.
  That sample of your own labels goes to the model on this computer and no
  further; turn it off with **Match the wording style of this page set**.

Online grounding is separate and off by default. If you explicitly enable it
for a suggestion, AAC Editor sends only that page title or category to
Wikipedia; button labels, page sets, style samples, rejected suggestions, and
generated suggestions all remain local. The article it used is named under the
suggestions with a link, and you can send it to a different one — or to none —
if it picked the wrong "Mercury". Administrators can hard-disable grounding
with `TDSNAP_WEB_GROUNDING=0`.

Nothing is written to disk until you save something. Remembering your last
AAC app, your Ollama connection, an unfinished page (so a crash or a
reload can offer to resume it), and any templates you save all live in one
`settings.json` in the same
per-user data folder the built-in AI model uses — never uploaded, never
synced. **What AAC Editor saves**, in the app's footer, lists exactly what's
stored in plain language, and **Clear all saved data** deletes the file.

## Quick start

1. Open TD Snap and the page set you want to edit.
2. Open AAC Editor and select **Use the page open in TD Snap**.
3. Add buttons, review their positions, and confirm the result-specific action.
4. Use **Choose another page** or **Create a new page** only when needed.
5. Review the checks before returning to TD Snap.

To fix, move, or retire something already on the page, select **Change, move, or
remove existing buttons**, then select the button itself — or drag it to another
cell, or move it with the arrow keys. Dropping one button on another has the two
trade places. AAC Editor changes only buttons whose whole job is to speak their
own message; a button that opens a page or runs an action stays locked and says
so on hover and on focus. Before a change, a move, or a removal runs, AAC Editor
reads what every affected button holds today, and refuses the edit outright if it
cannot — a destructive edit it could not undo is one it does not start. If the
edit then fails part-way, TD Snap is undone until each of those buttons holds its
prior label and spoken message again, and the result screen confirms that nothing
else on the page moved.

If an edit lands and turns out to be wrong, **Undo my last change** puts the page
back. It goes through the same review step, naming every button it will restore,
remove, or move home before anything runs. Three things it deliberately cannot
do, all of which it says on that screen: it reaches back one change only, it only
covers a change made while the app has been open, and it cannot reach back past a
sync in TD Snap or a change made in TD Snap itself. A button it re-creates is a
new button, so its symbol comes from a fresh TD Snap search.

Each button's symbol can be steered from the button editor: turn **Let TD Snap
add a symbol** off for one that should stay text-only, or set **Symbol search
words** when the label is a poor query — searching `more` for a button that says
*more please*. The result names the buttons that ended up without a symbol, so
there is no guessing about which ones to look at in TD Snap.

For Grid 3, choose **Grid 3** on the first screen and open the grid you want
to work on. The same two tasks TD Snap offers are then available: add to the
open grid — including changing, moving, or removing the speaking cells already
on it — or create a new grid, which Grid 3 links from the first empty cell of
the open grid. A new grid is always the open grid's size and carries Grid 3's
own **Back** cell in its top-left square; Grid 3's row and column pickers are
left alone because their result depends on how they are driven rather than on
the value chosen. Grid 3 is left showing whichever grid the edit ended on.
Choosing Grid 3 lists what it can and cannot do before you commit, and every
gate it stops at names itself: Grid 3 not installed, a grid not open, an
unfinished change to save first, a locked desktop, or administrator approval.

Grid 3 support is capability-based: AAC Editor reads the grid-set file for the
grid's real content and finds every cell by the ids Grid 3 exposes through UI
Automation, in the viewer and in Edit Mode. Only unprotected `.gridset`
format-1 grids are supported. Anything the accessible surface does not offer is
refused with a message naming what was missing. Not supported: Remote Editing,
word-list population, and cells that are not plain speaking (Write) cells.

**`.gridsetx` grid sets, including WordPower, are not supported, and cannot
be.** Every file inside a `.gridsetx` — the settings, every grid, every
picture — is encrypted by Grid 3. AAC Editor's safety model depends on reading
the grid before an edit and checking the saved file afterwards, neither of
which is possible without the key, and the project will not work around a
licence protection. This is a definite position, not an unbuilt feature: edit
those grid sets in Grid 3 itself.

The Grid 3 connection runs a reversible Edit Mode compatibility check: it adds
a provisional Write command and label to a safe blank, undoes it, and verifies
that nothing was saved. Every edit then happens in one Edit Mode session and one
save; if the saved file does not match what was reviewed, AAC Editor undoes and
re-saves until it does, and the message names the exact cell that differed.
Because every step is typed into Grid 3, AAC Editor refuses to type at all if
another window takes the keyboard mid-edit, rather than send a keystroke into
whatever is in front. Keep the keyboard and mouse alone while an edit runs.

Grid 3 runs with `uiAccess`, which puts its windows at a higher integrity level
than an ordinary app, so reading its accessibility tree needs administrator
rights. Connecting to Grid 3 asks for that approval through a normal UAC prompt
and restarts the app elevated; cancelling leaves the running copy untouched.

Keep Windows unlocked while an edit runs. The live editor is Windows-only and
depends on the current TD Snap interface. The exported-file fallback is
validated against a genuine TD Snap 4.13 export; see
[Importing edited page sets safely](docs/IMPORT_SAFETY.md) before using it.

## Python and command-line use

Requires Python 3.9 or newer:

```bash
pip install .
python -m tdsnap.web
```

Add `.[ai]` to install the built-in AI engine. The launchers are also available:

- Windows: double-click `launch.bat`
- macOS/Linux: run `./launch.sh` for exported-file and command-line work

Common commands:

```bash
python -m tdsnap list "My Page Set.sps"
python -m tdsnap verify "My Page Set.edited.sps"
python -m tdsnap inspect "My Page Set.sps"
python -m tdsnap.live status
python -m tdsnap.live add --yes --title Snacks --item Chips --item Apple
```

Exported-file edits always write a separate `*.edited.sps` copy. They discover
the file's schema at runtime, clone TD Snap's own records as templates, and run
SQLite integrity, foreign-key, linkage, and unexpected-change checks before
saving. TD Snap's proprietary `SyncHash` cannot be reproduced, so direct mode
is preferred when page-set sync matters. Exported files can add buttons to a page
that already exists as well as create one; existing buttons are shown but locked,
because changing and removing them there would need their own prior-content
snapshot and rollback.

## Development

```bash
pip install ".[dev]"
python -m pytest
ruff check tdsnap tests packaging scripts
coverage run -m pytest && coverage report
npm ci
npx playwright install chromium
npm run test:e2e
```

Install `.[ai,desktop]` and PyInstaller, then build the installer with
`./packaging/build.ps1 -Version 2.3.0`. Release builds are unsigned; `-Sign`
with `AAC_EDITOR_SIGNING_THUMBPRINT` set signs with a certificate you supply.

What a model returns is cleaned before it is ever offered: numbering, bullets,
quotation marks, markdown and trailing explanations are stripped, and the page
title restated, an item that is really a sentence, a repeat, anything already on
the page, and anything you rejected are dropped (`tdsnap/web/prompts.py`, pinned
by `tests/test_ai_cleaning.py`). Because that drops items, the request asks for
more than you wanted and a round that comes back nearly empty is asked once
more.

AI suggestion quality also has its own harness. `tests/fixtures/ai_eval_set.json`
holds a fixed set of category prompts and the rules the prompt already states —
*"Harry Potter characters"* must not return *"wand"*, and must return somebody
from the books. The scoring runs offline on every CI build
(`tests/test_ai_eval_rules.py`); the same rules run against the real model, and
record a pass rate, when opted in. The recorded rate is a trend to compare
release to release rather than a bar to clear — CI runs a model a third the
size of the one that ships — so it does not fail a build unless
`TDSNAP_AI_EVAL_FLOOR` is set:

```bash
TDSNAP_AI_SMOKE=1 python -m pytest tests/test_ai_eval.py
python scripts/verify_model_pins.py   # confirm each model pin with its publisher
```

The browser suite mocks TD Snap and Grid 3 accessibility responses. Real TD Snap
and Grid 3 tests are explicit opt-ins (`TDSNAP_LIVE_E2E=1` and
`GRID3_LIVE_E2E=1`) and must use disposable content. A real proprietary page or
grid set must never be committed; `scripts/fetch_fixture.py` downloads the
optional TD Snap integration fixture when needed.

Bug reports and pull requests are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md)
and the [security policy](SECURITY.md) first.

## Release integrity

Releases are not code-signed. Free code signing for open source was applied for
and declined, and a paid certificate is not in this project's budget. Two things
follow from that, and only these two: SmartScreen warns on first run, and live
Grid 3 editing has to ask for administrator approval instead of reaching Grid 3
directly. Everything else in AAC Editor is unaffected. If a certificate ever
becomes available, `./packaging/build.ps1 -Sign` is the whole change: the signed
build embeds the `uiAccess` manifest, and the administrator prompt goes away.

- Committer and reviewer: [Ryan Penny](https://github.com/rjpenny16)
- Releases are built from an existing version-matched tag by the public
  workflow, which installs and health-checks the package before attaching it.
- Every installer ships with a SHA-256 checksum and a
  [build provenance attestation](https://docs.github.com/en/actions/security-for-github-actions/using-artifact-attestations)
  tying it to the exact commit and workflow run that produced it.
- Privacy: AAC Editor will not transfer information to other networked systems
  unless specifically requested by the user or the person installing or
  operating it. The optional Wikipedia grounding control names the single
  topic value it sends before the request is made.

## License and trademarks

[MIT](LICENSE). The optional AI model is downloaded separately under its own
Apache-2.0 license. “TD Snap” is a trademark of Tobii Dynavox. This independent
community project is not affiliated with or endorsed by Tobii Dynavox or
Smartbox Assistive Technology. “Grid 3” is a Smartbox trademark.

---

Built by **Ryan Penny, M.A., CCC-SLP**, owner of
[myVoice Speech Therapy](https://www.myvoicespeechtherapy.com/).
