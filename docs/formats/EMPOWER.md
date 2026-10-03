# Empower (PRC-Saltillo): discovery checklist

AAC Editor does not open Empower vocabularies yet. Less is known about
Empower's files than about Chat Editor's, so this starts one step earlier:
finding out what Empower saves at all.

**Use disposable content only.** Never a client's vocabulary.

## 1. Find the files

Answer these first:

- Where does Empower run for editing (Windows, iPad, the device itself)?
- How is a vocabulary saved, backed up, or moved between devices? Is there a
  file a person can pick, and what is it called (extension)?
- Is there a desktop editor, and does it read and write that same file?

## 2. Collect files

As for Chat Editor: a small stock vocabulary unchanged; the same after adding
one button labelled `zzqx test`; the same after adding one linked page; and
an unchanged copy of a licensed vocabulary if one is installed.

## 3. Run the structure report

```bash
python -m tdsnap inspect-format "Empower backup.xyz"
```

Use the real file name. AAC Editor recognises a file whose name contains
"empower" and says Empower is not supported yet; the report works on any
file regardless of name.

## 4. Go or no-go

- **Encrypted or signed** (the report shows zip-encrypted entries, or entries
  that look encrypted): Empower gets a definite README position, the same as
  `.gridsetx`. AAC Editor will not work around a licence protection. If Empower
  imports Open Board (`.obz`), that becomes the supported route instead.
- **Open** (a readable database, XML, or JSON): Empower follows the Chat Editor
  plan in [CHAT_EDITOR.md](CHAT_EDITOR.md#what-happens-next), read first, then
  write, then a device round trip.

## 5. Results

- Empower version and platform:
- File type and how it is moved to a device:
- Container:
- Encrypted or signed?
- Does Empower import or export Open Board?
