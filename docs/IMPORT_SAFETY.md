# Importing edited page sets safely

This tool validates every edit against the rules a working TD Snap file obeys,
but TD Snap's format is proprietary — the only test that fully counts is TD
Snap itself opening the file. Follow this checklist so a bad file can never
cost you your real setup.

## Every time

1. **Never overwrite your original export.** The tool only ever writes a
   separate `<name>.edited.sps` file; keep the original somewhere safe until
   the edited copy has proven itself.

2. **Back up your real TD Snap user first.** In TD Snap:
   *Settings → System → Backup* (or sync to myTobiiDynavox). Do this before
   touching imports.

3. **Quarantine-import first.** Create a brand-new, throwaway TD Snap user
   (e.g. "Import Test") and import the `.edited` file there. If TD Snap
   crashes or misbehaves, delete the test user — your real user was never at
   risk.

4. **Exercise the new page in the test user:**
   - open the page you put the link button on;
   - tap the new link button — the new page should open;
   - tap several word buttons — each should appear in the message bar and speak;
   - navigate back, fully close and restart TD Snap, and open the page again.

5. **Only then** import into your real user, and keep the step-2 backup for a
   few days of normal use.

## Grid 3 grid sets

The same idea, with Grid 3's own tools. AAC Editor writes
`<name>.edited.gridset` and never changes the grid set you chose or the one
Grid 3 has open.

1. **Keep the original `.gridset`** until the edited copy has proven itself.
2. **Back up first.** In Grid 3, back up the user or export the grid set.
3. **Import into a throwaway user.** Create a new Grid 3 user (for example
   "Import Test") and add the `.edited.gridset` to it.
4. **Exercise it:** open each grid the edit touched, tap the new and changed
   cells, follow every new jump and its Back cell, then close and restart
   Grid 3 and open the grids again.
5. **Only then** add it to the real user.

If Grid 3 refuses the file or something looks wrong, send the output of
`python -m tdsnap inspect-format "My Grids.edited.gridset"` with the report. It
describes the package's structure and never prints its words.

## If something goes wrong

Run the built-in checker on the edited file and include its output when
reporting the problem:

```
python -m tdsnap verify "My Page Set.edited.sps" --show-sync
```

`verify` knows the linkage rules that crashed TD Snap in the past (orphaned
placements, buttons without command sequences, broken page links, missing
sync records) and prints exactly what it finds. `--show-sync` adds the
timestamp/hash fields of recently changed pages, which are the first suspects
for any *sync-related* rejection: the one field this tool cannot reproduce
perfectly is TD Snap's proprietary `SyncHash`. Local imports are expected to
work regardless; if you use myTobiiDynavox page-set sync and it complains
after an edit, that hash is why — re-export, re-apply the edit, and sync
before making other changes.
