# TD Snap Page Builder

Add vocabulary pages to a [TD Snap](https://us.tobiidynavox.com/pages/td-snap)
page set without clicking through Edit mode button by button. On Windows, the
app can edit the page set already open in TD Snap through accessibility
controls, so existing sharing and sync remain attached. Export/edit/import is
still available as a fallback.

Free and open source (MIT). Runs entirely on your computer: direct mode edits
the open TD Snap page set, while exported-file mode keeps its source file
untouched. Nothing is uploaded to the internet. Not affiliated with or
endorsed by Tobii Dynavox.

## Download

**Windows app (no Python needed):** grab `TDSnapPageBuilder-windows.zip` from
the [latest release](https://github.com/rjpenny16/AAC-Editor/releases/latest),
unzip it anywhere, and double-click `TD Snap Page Builder.exe`. The app opens
in your browser.

The packaged app includes a built-in AI engine for word/phrase suggestions.
The first time you use it, the app offers a one-time download of a free,
open-source model (Qwen2.5 1.5B Instruct, Apache-2.0, ~1 GB); after that,
suggestions run completely offline. The AI is optional — everything else
works without it.

Prefer Python? `pip install .` (add `.[ai]` for the built-in engine) or use
the launchers below.

![Web UI: build a page, preview the grid, download the edited page set](docs/screenshot.png)

## Why this is safe now (and wasn't before)

Earlier versions of this project wrote to the page-set database using a
guessed schema, and **TD Snap crashed after every edit**. The editor has been
rebuilt around the real file format, verified against a genuine TD Snap 4.13
export:

- **Template cloning.** New rows are copies of rows TD Snap itself wrote, with
  only the necessary fields changed — never hand-built rows with guessed
  columns.
- **Complete linkage.** Every button gets its `CommandSequence`; every
  placement is tied to a `PageLayout`; navigation uses `ButtonPageLink` plus
  the real serialized navigate command; every new page gets its `SyncData`
  ledger row and .NET-ticks timestamps.
- **Schema discovery at runtime.** Column lists come from the file itself
  (`PRAGMA table_info`), so a TD Snap update that adds columns doesn't break
  the clone.
- **Validation after every edit.** SQLite integrity + foreign keys, chain
  completeness for the new page, and a snapshot diff proving every table the
  edit shouldn't touch is byte-for-byte identical. If any check fails, nothing
  is saved.

One honest caveat for exported-file edits: TD Snap's `SyncHash` algorithm is
proprietary. Edited files open and work locally; if you use myTobiiDynavox
*page-set sync*, see [docs/IMPORT_SAFETY.md](docs/IMPORT_SAFETY.md). Direct
mode uses TD Snap's own editor and does not have this limitation.

## Quick start

Requires [Python 3.9+](https://www.python.org/downloads/) (tick **"Add Python
to PATH"** when installing on Windows).

**Windows:** double-click `launch.bat`
**Mac/Linux:** `./launch.sh`

The launcher opens the live editor in your browser at `http://127.0.0.1:8765`.

**Direct TD Snap editing (Windows):** open TD Snap and unlock Windows, then
select **Connect to TD Snap**. Choose **Add to an existing page** to put a pasted
list of foods, places, people, or other vocabulary into a category that is
already on the device, or choose **Create a new page** for a separate folder.
For existing pages the app loads occupied cells, locks established vocabulary in
place, checks duplicates and capacity, and requires exact empty-cell placement
before editing. It also detects pages from the open Topics menu, applies optional
topic-row colors, adds matching TD Snap symbols, and verifies the result.
Sync normally inside TD Snap when you are ready.

The web app is live-only. Advanced exported-file editing remains available
through the command-line commands below for maintenance and recovery work.

### Optional: AI word suggestions

Two ways, both fully on your machine:

- **Built-in (packaged app):** open "Suggest words with AI" and click
  *Download AI model* — a one-time ~1 GB download of Qwen2.5 1.5B Instruct
  (Apache-2.0). Offline forever after.
- **Ollama:** if [Ollama](https://ollama.com/download) is running (e.g.
  `ollama pull llama3.2`), the app detects and prefers it automatically —
  handy if you want a bigger model.

## Command line

Everything the web app does is scriptable:

```bash
python -m tdsnap list "My Page Set.sps"              # show pages
python -m tdsnap add  "My Page Set.sps" \
    --title Snacks --items "Chips,Apple,Banana" \
    --parent-name "My Things"                        # build + validate + save
python -m tdsnap add  "My Page Set.sps" \
    --title "Lunch Talk" \
    --items "Lunch?|What are we having for lunch?,More|Can I have some more?" \
    --border-color "#1E88E5" \
    --parent-name "My Things"                        # quick-fire phrase buttons
python -m tdsnap verify  "My Page Set.edited.sps"    # safety checks, any file
python -m tdsnap inspect "My Page Set.sps"           # schema version, tables
python -m tdsnap.live status                          # inspect open TD Snap
python -m tdsnap.live add --yes --title Snacks \
    --item Chips --item Apple                         # edit open TD Snap
```

## Development

```bash
pip install -r requirements.txt pytest
python -m pytest                      # unit tests (committed schema snapshot)
python scripts/fetch_fixture.py       # downloads a real page set (not committed)
python -m pytest                      # now includes integration tests
python -m tdsnap.web --no-browser     # run the web app
```

Browser workflow tests use Playwright and start the local Flask app
automatically when it is not already running:

```bash
npm ci
npx playwright install chromium
npm run test:e2e
```

The suite uses mocked TD Snap accessibility responses, so it never changes a
real page set. The one test that can edit the open TD Snap page set is skipped
unless `TDSNAP_LIVE_E2E=1` is explicitly set.

Layout: `tdsnap/` (schema introspection, template cloning, page builder,
validation, CLI), `tdsnap/web/` (Flask backend + single-page frontend),
`tests/` (unit tests run against `tests/fixtures/schema_snapshot.sql`, a
schema-only snapshot of a real export; integration tests run against the real
downloaded file). The real page set is proprietary Tobii content and must
never be committed — `.gitignore` enforces this.

Releases: tagging `vX.Y.Z` triggers `.github/workflows/release.yml`, which
builds the packaged Windows app (PyInstaller + bundled llama.cpp engine) and
attaches it to a draft GitHub Release. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) — free for anyone to use, modify, and share. The optional AI
model is downloaded separately from Hugging Face under its own Apache-2.0
license. "TD Snap" is a trademark of Tobii Dynavox; this community project is
not affiliated with or endorsed by Tobii Dynavox.
