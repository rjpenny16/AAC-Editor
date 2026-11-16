# Privacy and security

AAC Editor runs on your computer and works on files on your computer. It has no
server, no account, and no analytics. Nothing in it reports back to anyone, so
neither its author nor anyone else can see your page sets or the words you type
through the app.

This page says exactly what the app keeps, exactly what can leave your computer,
how to check both for yourself, and how to remove everything. The statements that
can be checked are backed by the source code or by an automated test, and the
section called "Check it yourself" shows how to look.

*Last reviewed against the source on 2 October 2026. The full technical review is
in [docs/SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md).*

## The short version

- **Your page sets, button labels, spoken messages, and the words you type are
  never sent anywhere.**
- There are no accounts, no analytics, no crash reports, and no update checks.
- The app only listens on your own computer (`127.0.0.1`). Nothing else on your
  network, or the internet, can connect to it.
- It uses the internet in two situations, and you start both: downloading the
  optional suggestion model once, and the optional Wikipedia lookup. Everything
  else works with no connection at all.
- It keeps very little on disk, shows you what it keeps, and deletes it when you
  ask.

## What it keeps on your computer

| What | Why | Where | When it goes |
| --- | --- | --- | --- |
| **Settings**: your last AAC app, your answer to the welcome question, your AI choices | So the app opens the way you left it | `settings.json` in `%LOCALAPPDATA%\tdsnap-editor` | **Clear all saved data** |
| **Templates** you choose to save | Reuse one topic page for the next person | The same file | When you delete one, or **Clear all saved data** |
| **An unfinished page** | Resume after a crash or reload | The same file | **Only kept if you turn on "Keep an unfinished page". It is off until you do.** Turning it off deletes it |
| **A working copy of an exported file** (`.sps`, `.spb`, or a Grid 3 `.gridset`) | Edits are made on a copy, so your original is never changed | Your temporary folder, in `tdsnap-editor` | When you close the file or quit, including if the app is told to stop or its terminal is closed. **One exception:** if it holds edits you never saved, it is kept so the next start can offer it back ("Open it" or "Discard it"), for at most a week. After a forced kill or a crash, the next start after a day removes any copy without unsaved edits, and **Clear all saved data** removes them all at once |
| **An activity log**: one line per edit, save or check, saying when, how long it took, whether it worked, and a short code (such as `VERIFY_MISMATCH`) if it did not | So a problem that comes and goes can be traced from one support report | `logs` inside the folder above, at most five files of 1 MB | Oldest lines are dropped as it fills; **Clear all saved data** deletes it. **It never contains button labels, spoken messages, page or grid names, file names, paths, AI prompts or anything you typed.** Where it needs to say "the same page as before" it uses a scrambled code that means nothing after the app closes |
| **Grid 3 backups**: a copy of the grid set taken just before each live Grid 3 edit | So a grid can be put back by hand if an edit and its rollback both go wrong | `backups\grid3` inside the folder above; the newest 20 are kept | Older ones are deleted automatically; **Clear all saved data** deletes them all |
| **Diagnostic mode** step records, only if you turn it on | Finer timings for tracking down a fault | The same log | Turns itself off after 24 hours or 50 MB. A note at the bottom of the window shows while it is on |
| **The suggestion model**, only if you set up suggestions | On-device suggestions | `models` inside the folder above | When you delete the file. It is a public model with nothing about you in it |
| **Files you save**: edited copies and `.obz` exports | They are your files | Wherever you choose | When you delete them |

On macOS and Linux the settings folder is `~/.local/share/tdsnap-editor` (or
`$XDG_DATA_HOME`), and the working copies are in a folder named for your user in
the system temp directory. Both are readable only by your account.

**See it on your own computer.** Choose **What AAC Editor saves** at the bottom of
the window. It lists what is stored right now, shows the real folder names, lets
you turn the unfinished-page option on or off, and has the **Clear all saved
data** button. That button removes your settings, templates, any unfinished page,
the activity log, and any leftover working copies. A page set you have open at that moment stays
until you close it, and the app says so.

**The window itself keeps nothing.** The installed app's window runs in private
mode: no cookies, no local storage, and its temporary browser profile is deleted
when the window closes. If you use browser mode instead (`launch.bat` or
`python -m tdsnap.web`), your own browser's history will show the local address
`http://127.0.0.1:8765`, and AAC Editor tells the browser not to cache anything it
returns.

## What can leave your computer

This is the complete list.

1. **Downloading the suggestion model.** Only when you choose **Set up
   suggestions** or download another model. It connects to `huggingface.co`, which
   serves the file itself or hands you on to its own download servers. Hugging
   Face can see your internet address and which model file you asked for. Nothing
   from your pages is sent. The file is checked against a fixed size and SHA-256
   before it is used, and a file that does not match is thrown away.
2. **The Wikipedia lookup.** Off by default, and off again each time you open the
   app. If you tick it, or give a Wikipedia link, AAC Editor sends the page title
   (or the article you named) to `en.wikipedia.org`, and nothing else. Not your
   button labels, not your page set, not what you asked the AI for. Wikipedia can
   see your internet address, as any site you visit can. An administrator can
   switch it off completely by setting `TDSNAP_WEB_GROUNDING=0`.
3. **Links you click.** The Ollama download page and the Wikipedia article link
   open in your normal browser, and only when you click them.

If you use **Ollama**, AAC Editor talks to it only at `localhost` or another
loopback address, never through a proxy, and it will not follow a redirect to
anywhere else. The app refuses to use an Ollama address that is not on your own
computer.

Where to look: the only files that can reach the network are listed in
`tests/test_privacy_contract.py`, and that test fails if a new one appears.

**Asking an assistant yourself.** When the built-in suggestions are not set up,
the suggestions panel offers a request you can copy into a chat assistant you
already use, then paste its answer into the word box. AAC Editor itself sends
nothing: the request leaves your computer only when you paste it somewhere,
under that service's own privacy terms. It contains the page title and how many
words you asked for; do not add a client's name or details to it.

## How the AI works

- The model runs on your computer, either inside AAC Editor or in your own Ollama.
- **Match the wording style** sends a sample of your own button labels to that
  model on your computer, and no further.
- Suggestions are only candidates. Nothing reaches your page until you keep a
  suggestion and then confirm the change.

## How the app protects you

- **Only this computer can reach it.** The server binds to `127.0.0.1`. Requests
  addressed to any other name are refused, which blocks "DNS rebinding" attacks
  from web pages.
- **A web page you visit cannot drive it.** Every request that changes anything,
  and every request that could move or click something in TD Snap or Grid 3, must
  carry a secret token generated fresh each time the app starts. A web page on
  another site can neither read that token nor send it.
- **The page cannot send your data elsewhere.** The app's page is served with a
  policy that makes your browser refuse any connection to a different site. It
  loads no third-party code, fonts, or images.
- **Your data is not cached.** Everything the app's API returns, which is where
  your vocabulary, drafts, and templates travel, is marked so that your browser
  does not store it.
- **You review every change.** In the app, nothing touches TD Snap, Grid 3, or your
  files until you have seen exactly what will change and confirmed it. Exported
  files are edited as a copy.
- **Your real TD Snap file is only read.** When reading the page set TD Snap has
  open, AAC Editor opens it read-only.
- **Files from other people are treated with care.** Board files (`.obz`) are
  size-limited and read in memory, never unpacked onto your disk. Page sets are
  checked before and after every edit, and opened with SQLite's safety settings
  for files made by somebody else.
- **Grid 3 needs your approval each time.** Because the app is not code-signed,
  Windows asks for administrator approval, and the app says why.

## Check it yourself

You do not have to take any of this on trust.

1. **Disconnect from the internet and use the app.** Everything except the model
   download and the Wikipedia lookup keeps working.
2. **See what is listening.** In a terminal, run `netstat -ano | findstr :8765`
   (the app uses 8765 unless something else already has it). You will see
   `127.0.0.1` and no other address.
3. **See what is on disk.** Open the folders named in **What AAC Editor saves**.
   `settings.json` is plain text you can read.
4. **Block it at the firewall.** Add a Windows Defender Firewall outbound rule that
   blocks `AAC Editor.exe`, then use the app. Only the model download and the
   Wikipedia lookup should stop working, because nothing else needs the network.
5. **Read the code, or run the checks.** `python -m pytest tests/test_privacy_contract.py`
   runs the automated checks behind this page.
6. **Check what you downloaded.** Releases are not code-signed, so Windows shows a
   warning the first time. Compare the file's hash with the `.sha256` attached to
   the release (`Get-FileHash <installer>`), or run
   `gh attestation verify <installer> --repo rjpenny16/AAC-Editor` to confirm it was
   built from this repository by its public workflow. If either check fails, do not
   run the file.

## Remove everything

1. In the app, open **What AAC Editor saves** and choose **Clear all saved data**.
2. Uninstall AAC Editor from Windows **Settings > Apps**.
3. Delete the folder `%LOCALAPPDATA%\tdsnap-editor`. Uninstalling does not remove
   it, so do this if you want everything gone. It holds your settings, any
   templates, the activity log, and the suggestion model.

## What this does not promise

- If your computer is compromised, anything on it, including this app's files, is
  readable by whoever compromised it.
- Files you save or export are as private as the place you put them.
- Hugging Face and Wikipedia have their own privacy policies for the two
  connections described above.
- The release is not code-signed, which is why step 6 of "Check it yourself" matters.

## Report a problem

Please report a security or privacy problem privately, through
[GitHub's private vulnerability report](https://github.com/rjpenny16/AAC-Editor/security/advisories/new),
and do not attach real page sets or AAC vocabulary. See [SECURITY.md](SECURITY.md).
