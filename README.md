# TD Snap Page Builder

Add vocabulary pages to a [TD Snap](https://us.tobiidynavox.com/pages/td-snap)
page set without clicking through Edit mode button by button. Export your page
set from TD Snap, build pages here (with optional local-AI word suggestions),
and re-import the edited copy.

Runs entirely on your computer. Your original file is never modified, and
nothing is uploaded to the internet.

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
app in your browser at `http://127.0.0.1:8765`. Then:

1. **Export** your page set from TD Snap
   (*Edit mode → Page Set → Import/Export → Export to file*).
2. **Open** the `.sps`/`.spb` file in the app.
3. **Build** a page: title, words (type them, paste a comma-separated list, or
   let a local [Ollama](https://ollama.com) model suggest them), and the page
   that should get the link button. The preview shows the grid exactly as TD
   Snap will lay it out.
4. **Download** the `.edited` copy and import it into TD Snap — **into a test
   user first**: read [docs/IMPORT_SAFETY.md](docs/IMPORT_SAFETY.md).

### Optional: AI word suggestions

Install [Ollama](https://ollama.com/download), run `ollama pull llama3.2`, and
the "Suggest words with AI" section in the app comes alive. Everything stays
on your machine.

## Command line

Everything the web app does is scriptable:

```bash
python -m tdsnap list "My Page Set.sps"              # show pages
python -m tdsnap add  "My Page Set.sps" \
    --title Snacks --items "Chips,Apple,Banana" \
    --parent-name "My Things"                        # build + validate + save
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
