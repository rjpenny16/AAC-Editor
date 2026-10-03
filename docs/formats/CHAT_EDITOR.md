# Chat Editor (TouchChat, NovaChat, ChatFusion): discovery checklist

AAC Editor does not open Chat Editor vocabularies yet. This page is how the
format gets documented well enough to build a reader and a writer that can
check their own work. Nothing below is assumed until a real file confirms it.

**Use disposable content only.** Make a copy of a stock vocabulary (or a new,
nearly empty one) in Chat Editor and work on that. Never use a client's
vocabulary for any of these steps.

## 1. Collect files

Export or save, from Chat Editor:

- a copy of a small stock vocabulary, unchanged;
- the same vocabulary after adding **one** button with a known label (for
  example `zzqx test`) to an existing page;
- the same vocabulary after adding one new page linked from the home page;
- a copy of any stock vocabulary that is licensed (for example WordPower or
  LAMP Words for Life, if installed), unchanged. This one decides whether
  those can ever be supported.

Note the Chat Editor version and which device family each file is for.

## 2. Run the structure report on each file

```bash
python -m tdsnap inspect-format "Copy of vocabulary.ce" > report-1.txt
python -m tdsnap inspect-format "Copy of vocabulary.ce" --json > report-1.json
```

The report never prints labels or messages, and generalises folder and file
names inside the file. Read it before sharing; it is short.

What it answers:

| Question | Where in the report |
|---|---|
| Is a `.ce` a zip, a database, or something else? | `Container:` |
| Is there a SQLite database inside, and what are its tables and columns? | `table ...` lines |
| How many rows changed between the stock copy and the one-button copy? | row counts |
| Is anything encrypted? | `zip-encrypted`, `look encrypted` |

## 3. Device round trip (decides whether hashes or sync fields matter)

1. Open the one-button copy in Chat Editor. Does the button show?
2. Transfer it to the PRC device (USB, or however that device takes a
   vocabulary). Does it load? Does the button speak?
3. Restart the device app and check again.

If an edit made by hand (a single label changed in the database with a
SQLite tool) is refused by Chat Editor or the device while an edit made in
Chat Editor is not, there is a checksum or sync field to understand first,
the same lesson TD Snap's `SyncHash` taught.

## 4. Results

Fill this in, or paste the reports into an issue.

- Chat Editor version:
- Device family and app version:
- Container:
- Database tables of interest (pages, buttons, layout, actions, resources):
- Rows that change when one button is added:
- Encrypted stock vocabularies:
- Hand-edited file accepted by Chat Editor? By the device?

## What happens next

With the reports, AAC Editor gets `tdsnap/formats` support for `.ce` in this
order: read (pages, buttons, layout, links, `.obz` export); then write (add to
empty cells, new linked pages, change/move/remove speaking buttons, `.obz`
import), each with the same review, before-and-after verification, and
"nothing saved unless it all checks" rule the TD Snap and Grid 3 file paths
have; then a device round trip documented in
[IMPORT_SAFETY.md](../IMPORT_SAFETY.md). Live editing through Chat Editor's
own window comes last, and only if its controls are reachable through Windows
accessibility without screen coordinates.
