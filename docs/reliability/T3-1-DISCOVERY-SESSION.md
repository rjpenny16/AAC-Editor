# T3-1. Behaviour discovery session (script for the owner)

Roadmap item A7a. This is the first real-hardware session from [05](05-TESTING-AND-DIAGNOSTICS.md). Its job is to answer the open questions in [03](03-INTERMITTENT-FAILURE-INVESTIGATION.md) by watching what TD Snap and Grid 3 actually do. Nothing here needs programming. It takes about half a day.

Everything happens on **disposable content**. Nothing in this session touches a client's vocabulary.

## What you need

- The Windows computer with TD Snap and Grid 3 installed.
- AAC Editor, **the installed app** (not `launch.bat`), at the version built from the branch that contains this file or later.
- About 4 hours, a notepad (or the recording sheet at the end), and a phone to take the occasional photo of the screen.
- Optional but useful: Windows' built-in screen recorder (Win+Alt+R in the Game Bar) so a surprising moment can be watched again.

## Part 0. Set up (30 minutes)

Do every step. A session without them does not count.

### 0.1 Make a disposable TD Snap user

1. Open TD Snap.
2. Open the menu, choose **Users**, then **New user**. Name it `T3 Test`.
3. When TD Snap asks for a page set, pick a **stock** page set (for example *Core First*). Do not import or copy a client's page set.
4. Make sure `T3 Test` is the active user. TD Snap's title area or menu shows the user name.
5. Do not sign this user into myTobiiDynavox or any sync account.

### 0.2 Back up the TD Snap test page set

1. In TD Snap, open the menu, choose **Backup**, and back up `T3 Test` to a file on the desktop named `T3-before.sps` (or the backup name TD Snap suggests). If TD Snap offers only cloud backup, use **Export page set** to a file instead.
2. Write down the time.

### 0.3 Make a disposable Grid 3 grid set

1. Open Grid 3. Create a new user named `T3 Test`, or use an existing test user that holds no client content.
2. Add a stock grid set (for example *Super Core 30*) to that user. Use **Copy** if Grid 3 offers it so the original stays untouched.
3. Close Grid 3's editing screens so it is in normal (user) mode.
4. Find the grid set's file. In Grid 3 choose **Grid Explorer**, right-click the grid set, **Export** it to the desktop as `T3-before.gridset`.

### 0.4 Turn on AAC Editor's diagnostic mode

1. Start AAC Editor from the Start menu (the installed app).
2. At the bottom of the window choose **What AAC Editor saves**.
3. Tick **Record each step of every edit in the activity log**. A note "Diagnostic mode is on" appears at the bottom of the window. Leave it on for the whole session.

### 0.5 Note the versions

Write down on the recording sheet:

- Windows version (Start, type `winver`, press Enter).
- Display scaling (Settings, System, Display, Scale).
- TD Snap version (TD Snap menu, **About**).
- Grid 3 version (Grid 3 menu, **About**).
- AAC Editor version (footer, **Copy a support report**: the first lines show it).

## Part 1. TD Snap (about 2 hours)

For every experiment: do the steps, then write what you saw in the matching row of the recording sheet. "What I expected" does not matter; write what happened. If something unexpected happens, stop, take a photo, and write the time.

Use a page in the `T3 Test` page set with a few empty cells, for example a topic page you create for this session called `T3 Page`.

### Experiment 1. Is there a confirmation when a button is deleted? (REL-004)

1. In TD Snap, enter edit mode by hand (the pencil or **Edit** button).
2. Select any button on `T3 Page`.
3. Delete it with TD Snap's own delete control.
4. **Note:** did TD Snap show a question such as "Are you sure?" with **Delete**/**Yes**/**OK**? Write the exact words on the buttons of that question, if there was one.
5. After the delete, **note** what is selected: nothing, the next button, or something else.
6. Press **Undo** once to bring the button back. Press **Done**.

### Experiment 2. Does Undo still work after Done? (REL-002, question A3)

1. Enter edit mode. Add one button with the label `undo-test` in an empty cell. Press **Done**.
2. Enter edit mode again.
3. **Note:** is the **Undo** button enabled (not greyed out)?
4. If it is enabled, press it once. **Note:** did `undo-test` disappear?
5. Press **Done**. If `undo-test` is still there, delete it.

### Experiment 3. What if TD Snap is already in edit mode? (REL-002)

1. Enter edit mode by hand. Change one existing button's label to `manual-change`. **Do not press Done.**
2. Switch to AAC Editor. Connect to TD Snap, choose `T3 Page`, add one word `app-word`, review, and apply.
3. **Note** exactly what AAC Editor says (a photo is best). With the version this script was written for, AAC Editor should refuse and tell you TD Snap is already in edit mode. If it went ahead instead, note whether `manual-change` is still there afterwards and whether TD Snap is still in edit mode.
4. Back in TD Snap, press **Undo** until `manual-change` is gone, then **Done**.

### Experiment 4. How fast does TD Snap redraw after Undo? (REL-002, REL-017)

This one is measured by AAC Editor's log; you only need to make it happen.

1. In AAC Editor, add 5 words to `T3 Page` and apply. Wait for the result screen.
2. Choose **Undo my last change** and apply it.
3. Repeat steps 1 and 2 four more times (five rounds).
4. **Note** on the sheet whether any round said anything other than "Done" or "undone".

### Experiment 5. Window not in front (REL-005, H-01)

Do each of these three times.

1. **Behind another window.** In AAC Editor, plan 2 words for `T3 Page` and go to the review screen. Now click on another program (for example Notepad) so it covers TD Snap. Click **Apply** in AAC Editor. **Note** what happened: did the words arrive in TD Snap, did anything get typed into Notepad, and what did AAC Editor say?
2. **Minimised.** Same, but minimise TD Snap before pressing **Apply**.
3. **Moved.** Same, but drag the TD Snap window to a different position (or to a second monitor, if you have one) between the review screen and **Apply**.

After each, put `T3 Page` back the way it was (Undo in TD Snap, or **Undo my last change** in AAC Editor).

### Experiment 6. Is TD Snap's page set locked while it saves? (REL-019)

Measured by the log; you only need to make it happen.

1. Apply an edit of 10 words to `T3 Page` from AAC Editor.
2. Apply an edit that changes 3 existing labels.
3. Apply an edit that removes 3 buttons.

The log records whether any read of TD Snap's page set hit a lock. Nothing to note unless AAC Editor reports a failure.

### Experiment 7. The repeated set (doc 03, "What must be measured")

On disposable pages only, over the rest of the TD Snap time:

- 20 additions (any mix of 1 to 5 words per edit),
- 10 label changes,
- 10 removals,
- 5 uses of **Undo my last change**.

**Note** every result that is not "Done" with the time and AAC Editor's reference (the short code shown next to the message).

### Experiment 8. Different administrator (REL-023)

Skip unless the computer has a second administrator account.

1. Close TD Snap. Start TD Snap with right-click, **Run as administrator**.
2. Try to connect AAC Editor. **Note** what it says.
3. Close TD Snap and start it normally again.

## Part 2. Grid 3 (about 1 hour)

AAC Editor needs to run as administrator for Grid 3; it asks when you choose Grid 3. Approve with **your own** account.

### Experiment 9. Undo history deeper than one edit (REL-001)

1. In Grid 3, enter Edit Mode by hand and make **three** small manual changes on one grid (for example rename three cells to `m1`, `m2`, `m3`). Save (Ctrl+S) and leave Edit Mode.
2. In AAC Editor, connect to Grid 3 and add one word `g-word` to the same grid. Apply.
3. **Note** the result.
4. Now choose **Undo my last change** in AAC Editor.
5. **Note:** are `m1`, `m2`, `m3` all still there? Only `g-word` should be gone. If any of `m1` to `m3` disappeared, that is the over-undo problem: take a photo and write the time.

### Experiment 10. A file held open (REL-001)

1. Open the Grid 3 grid set's folder in File Explorer (Grid 3, Grid Explorer, right-click the grid set, **Open file location**, if your version offers it). Leave File Explorer showing the folder.
2. Apply one addition from AAC Editor, then **Undo my last change**.
3. **Note** both results.

### Experiment 11. Grid 3 already in Edit Mode (L3)

1. Put Grid 3 in Edit Mode by hand. Do not change anything.
2. Try to apply an edit from AAC Editor.
3. **Note** what AAC Editor says. It should refuse and say Grid 3 is in Edit Mode.

## Part 3. Finish (15 minutes)

1. In AAC Editor choose **Copy a support report** and paste it into an email or a text file named `T3-1-report.txt`.
2. Open the log folder: **What AAC Editor saves** shows the folder; open the `logs` folder inside it. Copy every file named `operations.jsonl*` next to the report. These files contain codes and timings only; you can open them in Notepad to check that no labels or page names are in them.
3. Turn diagnostic mode off (**What AAC Editor saves**, untick).
4. Restore TD Snap: restore the `T3-before` backup, or simply delete the `T3 Test` user.
5. Restore Grid 3: delete the `T3 Test` grid set or user.
6. Send the report, the log files and the recording sheet. The answers go into doc 03, and the simulated TD Snap and Grid 3 used by the automated tests are corrected to match.

## Recording sheet

Copy this table into a document and fill in the right-hand column.

| # | Question | What happened |
|---|---|---|
| 0 | Windows version, display scaling, TD Snap version, Grid 3 version, AAC Editor version | |
| 1a | Delete confirmation shown? Exact button words | |
| 1b | What is selected after a delete | |
| 2 | Undo enabled after Done and re-entering edit mode? Did it undo `undo-test`? | |
| 3 | AAC Editor's message when TD Snap was already in edit mode; `manual-change` kept? | |
| 4 | Any undo round not "Done"/"undone"? Reference codes | |
| 5a | Behind another window: what arrived where, message (x3) | |
| 5b | Minimised: what happened, message (x3) | |
| 5c | Moved between review and apply: what happened, message (x3) | |
| 6 | Any failure while editing 10/3/3 | |
| 7 | Every non-"Done" result in the repeated set, with time and reference | |
| 8 | Elevated TD Snap: message | |
| 9 | Grid 3: `m1` to `m3` still there after undo? | |
| 10 | Grid 3 with the folder open: both results | |
| 11 | Grid 3 already in Edit Mode: message | |
| — | Anything else surprising, with time | |
