# TD Snap AI Assistant

AI-powered tool for TD Snap that builds new vocabulary pages from natural language —
then **edits your page set file directly** instead of automating mouse clicks.

**NEW:** Uses Ollama for local, private AI processing — no internet required.
**NEW:** Edits the TD Snap page set (`.spb`/`.sps`) file itself, so there are no
fragile screen coordinates to record and nothing breaks when a window moves.

## How it works (export → edit → import)

A TD Snap page set is a SQLite database. This tool opens a *copy* of your exported
page set, adds a new page full of word buttons, links to it from a page you choose,
and writes a new `*.edited.spb`/`*.edited.sps` file. You re-import that file into
TD Snap. No clicking, no timing, no coordinates.

1. **Natural language → AI**: your command goes to Ollama running locally.
2. **AI generates items**: Ollama produces appropriate vocabulary for the category.
3. **Direct edit**: the app inserts a new page + buttons into the page set file.
4. **Re-import**: you import the edited file and the new page appears in TD Snap.

## Quick Start

### 1. Install Ollama (one-time)

**Windows:** download from [ollama.com/download](https://ollama.com/download)
**Mac/Linux:** `curl -fsSL https://ollama.com/install.sh | sh`

Then pull a model:
```bash
ollama pull llama3.2
```

### 2. Install and run the app

**Windows:** double-click `launch.bat`
**Mac/Linux:** run `./launch.sh`

The launcher installs the (small) Python dependencies automatically.

### 3. Export your page set from TD Snap

In TD Snap, export the page set you want to extend to a `.spb` or `.sps` file.
Keep your original safe — the tool never modifies it, it writes a new edited copy.

### 4. Load it in the app

1. Go to the **1 · Open File** tab.
2. Click **Choose File…** and pick your exported file.
3. Under **Where should the new button appear?**, choose the page that should get
   the link to your new category.

### 5. Configure Ollama (first time only)

1. Go to the **3 · Settings** tab.
2. Verify the **Server**: `http://localhost:11434`.
3. Select a **Model** (e.g. `llama3.2`) and click **Test Connection**.

### 6. Run a command

On the **2 · Build a Page** tab, type natural language such as:
- "Add a Favorite Places page with Walmart, McDonald's, Taco Bell"
- "Add restaurants category"
- "Create animals with 15 items"

The app generates the items, writes `yourfile.edited.spb`/`.sps`, and logs the path.

### 7. Re-import into TD Snap

Import the edited file into TD Snap to see the new page and its navigation button.

## Verifying the file format (recommended once)

The page-set schema this tool writes is based on the open-source `obf-node` Snap
converter. Production TD Snap versions can differ, so before relying on it, confirm
the format against a real export and discover any fields TD Snap requires on import:

```bash
# Inspect a real export: container type, tables, sample rows
python inspect_pageset.py yourpageset.sps

# Diff two exports — e.g. before vs. after adding a page by hand in TD Snap —
# to see exactly which rows/fields TD Snap expects
python inspect_pageset.py before.sps after.sps
```

If TD Snap rejects an edited file on import, the diff above is what reveals the
missing field; open an issue with what you find.

## Requirements

- **Python 3.8+** (from [python.org](https://www.python.org/downloads/))
- **Ollama** with a model installed (see step 1)
- **TD Snap** with export/import of page sets
- **8GB RAM recommended** for running local AI models

The editor itself uses only the Python standard library (`sqlite3`); `requests` is
used to talk to Ollama.

## Settings

In the **3 · Settings** tab:
- **Buttons per page** — how many words to generate (default: 10)
- **Columns** — width of the new page's button grid (default: 4)
- **Server** — local Ollama server address (default: `http://localhost:11434`)
- **Model** — which model to use (e.g. `llama3.2`)

## Recommended Ollama Models

| Model | Size | Best For |
|-------|------|----------|
| llama3.2 | 2GB | Most users — fast & accurate |
| llama3.1 | 4.7GB | Better quality, slower |
| phi3 | 2.3GB | Low-end hardware |

```bash
ollama pull <model-name>
```

## Current scope & limitations

- **Text buttons only.** Buttons get a label and spoken message; symbols/images are
  not added yet (linking the symbol library is part of ongoing format verification).
- **TD Snap only.** Other AAC apps (Grid 3, TouchChat, …) are out of scope here, but
  the same data-level approach applies — they have their own file formats.
- **Re-import is manual.** The app produces a file; TD Snap's own import brings it in.

## Troubleshooting

**Cannot connect to Ollama:** check it's running (`ollama list`), start it
(`ollama serve`), verify port 11434.

**"Open a file first":** open a `.spb`/`.sps` on the **1 · Open File** tab first.

**"… is not a SQLite database":** the file isn't a recognised page set — confirm you
exported a page set (not a screenshot/PDF) and check it with `inspect_pageset.py`.

**TD Snap won't import the edited file:** run the diff described in *Verifying the
file format* to find the field TD Snap requires that the writer isn't setting yet.

**Ollama too slow:** try a smaller model (phi3), close other apps, ensure enough RAM.

## What's included

- `td_snap_ai_assistant.py` — main app (Tkinter UI + Ollama)
- `td_snap_pageset.py` — page set editor (SQLite, no external deps)
- `inspect_pageset.py` — format inspector / differ for verification
- `test_td_snap_pageset.py` — unit tests (`python -m pytest`)
- `launch.bat` / `launch.sh` — launchers
- `requirements.txt`, `README.md`, `OLLAMA_INTEGRATION.md`

## Privacy

- **100% local** AI processing; no data leaves your computer.
- The tool edits a **copy** of your export and never touches the original file.
- Keep backups of your TD Snap page sets before importing edited files.

## Support

**Ollama:** [github.com/ollama/ollama](https://github.com/ollama/ollama)
**TD Snap:** Tobii Dynavox support

---

**Made for the AAC community to make vocabulary building faster, easier, and more private.**
