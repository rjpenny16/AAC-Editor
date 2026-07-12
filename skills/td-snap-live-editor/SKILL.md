---
name: td-snap-live-editor
description: Add locally generated word or phrase pages directly to the page set open in the Windows TD Snap app through accessibility controls. Use when a user wants to edit their original or synced TD Snap page set without exporting, importing, downloading a replacement file, or using a cloud agent.
---

# TD Snap Live Editor

Use the repository's local runner. It connects word-list output to a deterministic TD Snap editing workflow and requires no API key or subscription.

## Workflow

1. Require Windows to be unlocked and TD Snap to be open on a populated page.
2. From the repository root, inspect without changing anything:

   ```powershell
   python -m tdsnap.live status
   ```

3. Generate or collect the requested button text. Let the user review it before editing their live page set.
4. Apply the approved page. Repeat `--item` for every button:

   ```powershell
   python -m tdsnap.live add --yes --title "Snacks" --parent "Topics Menu Page" --item "chips" --item "apple"
   ```

5. Require all returned checks to be `pass`. Report any returned warnings.

## Guardrails

- Never run `add` without a user-authorized page title and button list.
- Never automate TD Snap Sync, sharing, account, user, or deletion controls.
- Stop when the runner reports a locked desktop or changed control layout.
- Keep `Topics Menu Page` as the automatic parent. For another parent, have the user open that page first.
- Use the `TDSNAP_LINK_ICON_X/Y` or `TDSNAP_ADD_ICON_X/Y` environment values only to calibrate a confirmed TD Snap layout change.
- Do not add a vision model unless the accessibility runner fails on a real workflow.
