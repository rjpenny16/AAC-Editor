# TD Snap Page Builder

Add vocabulary pages to a [TD Snap](https://us.tobiidynavox.com/pages/td-snap)
page set without clicking through Edit mode button by button. Export your page
set from TD Snap, build pages here (with optional on-device AI suggestions),
and re-import the edited copy.

Free and open source (MIT). Runs entirely on your computer: your original
file is never modified, and nothing you edit is uploaded to the internet.
Not affiliated with or endorsed by Tobii Dynavox.

## Download

**Windows app (no Python needed):** grab `TDSnapPageBuilder-windows.zip` from
the [latest release](https://github.com/rjpenny16/AAC-Editor/releases/latest),
unzip it anywhere, and double-click `TD Snap Page Builder.exe`. The app opens
in its own window: opening a page set and saving the edited copy use the
normal Windows file dialogs, closing the window quits the app, and
double-clicking the .exe again brings the existing window to the front
instead of starting a second copy.

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

One honest caveat: TD Snap's `SyncHash` algorithm is proprietary. Edited files
open and work locally; if you use myTobiiDynavox *page-set sync*, see
[docs/IMPORT_SAFETY.md](docs/IMPORT_SAFETY.md).

## Quick start

Requires [Python 3.9+](https://www.python.org/downloads/) (tick **"Add Python
to PATH"** when installing on Windows).

**Windows:** double-click `launch.bat`
**Mac/Linux:** `./launch.sh`

The launcher installs two small dependencies (Flask, Requests) and opens the
app in your browser at `http://127.0.0.1:8765` (when you're done, the *Quit
the app* link in the footer stops it; launching again while it's running
reuses the open copy instead of failing). Prefer a real window over a
browser tab? `pip install .[desktop]` and run `python -m tdsnap.web
--window`. Then:

1. **Export** your page set from TD Snap
   (*Edit mode → Page Set → Import/Export → Export to file*).
2. **Open** the `.sps`/`.spb` file in the app.
3. **Build** a page: title, words (type them, paste a comma-separated list, or
   let a local [Ollama](https://ollama.com) model suggest them), and the page
   that should get the link button. The preview shows the grid exactly as TD
   Snap will lay it out.

   Two page styles:
   - **Word page** — single words; each button speaks its label.
   - **Topic page** — quick-fire phrases with communicative-function
     color-coding: each button gets the same 3px colored border TD Snap
     renders (blue = question, orange = comment, green = positive,
     red = negative, purple = personal). Click any button chip to change its
     color or give it a full spoken phrase while the label stays short
     (label "Lunch?", speaks "What are we having for lunch?").
4. **Download** the `.edited` copy (the windowed app **saves** it wherever
   you choose) and import it into TD Snap — **into a test user first**:
   read [docs/IMPORT_SAFETY.md](docs/IMPORT_SAFETY.md).

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
```

## Development

```bash
pip install -r requirements.txt pytest
python -m pytest                      # unit tests (committed schema snapshot)
python scripts/fetch_fixture.py       # downloads a real page set (not committed)
python -m pytest                      # now includes integration tests
python -m tdsnap.web --no-browser     # run the web app
```

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
