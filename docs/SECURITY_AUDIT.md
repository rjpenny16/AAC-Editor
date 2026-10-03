# Security and privacy review

This is the technical record behind [PRIVACY.md](../PRIVACY.md). It says what was
reviewed, what was found, what was changed, what was left alone and why, and what
this review could not cover.

- **Reviewed:** 2 October 2026, against commit `96e4512` (release 2.3.0 plus
  dependency updates), on a Linux machine.
- **Question asked:** does the app keep or send anything about its users that they
  would not expect, and can it be made to do harm to them or their AAC app?

## Result

AAC Editor has no telemetry, no analytics, no accounts, no crash reporting, and no
update checks, and no code path that could send a person's page sets or vocabulary
to a third party. That held up under review. The only internet connections it can
make are the one-time model download and the optional Wikipedia lookup, and both are
started by the user.

The review did find places where the app did more than it said, or less than it
should: it saved the user's unfinished page to disk without being asked, it could
route "local" requests through a network proxy, it could be made to delete files
outside its own folder, and its own wording overclaimed in two places. All of those
are fixed, each with a test that fails without the fix. Nothing found was being
exploited, and nothing found exposed data to anyone but a local attacker or a
specific network setup, but each was a gap between what a user would reasonably
believe and what the code did.

## How it was reviewed

- Read every Python module in `tdsnap/`, every script and stylesheet the page loads,
  the packaging and installer files, the release and test workflows, and the
  dependency manifests.
- Searched the whole tree for every way data can leave (network libraries, `fetch`,
  sockets, browser storage), every way data is written (files, temp files, SQLite),
  and every dangerous construct (`eval`, `exec`, `pickle`, `shell=True`, unsafe
  XML or zip handling, string-built SQL, disabled TLS verification).
- Reproduced the suspected problems with small programs before changing anything,
  rather than reasoning about them: a real proxy and a real stand-in Ollama server,
  and a real traversal request against the original code.
- Ran `pip-audit` over the app's Python dependency tree and `npm audit` over the
  development tooling.
- After writing the fixes and their tests, put each flaw back one at a time
  (22 deliberate regressions) to confirm the tests catch it. 21 are caught; the
  other removes one of two independent checks, so behavior is unchanged, which
  is the point of having two. This turned up weak tests of my own (one could not
  fail, because the proxy settings were read before the test set them), which were
  rewritten.

## Threat model

What is being protected: the vocabulary and page sets of people who use AAC, which
can be deeply personal (names, medical needs, family), and the working state of
their communication device.

| Who might cause harm | How | Considered |
| --- | --- | --- |
| A web page the user visits while the app runs | Cross-site requests, DNS rebinding, requests to `127.0.0.1` | Yes |
| Another account or process on a shared computer | Reading temp files, planting files, symlinks | Yes |
| A hostile file someone sends the user | A malicious page set, board file, or grid set | Yes |
| A network intermediary | A proxy that receives requests meant for this computer | Yes |
| The supply chain | A compromised dependency, action, or release | Yes |
| The app itself | Keeping or sending more than people expect | Yes |
| An attacker who already controls the user's account or the computer | Anything | No. They can already read everything the app can |

## Findings

Severity: **High** means a person's data could be exposed or lost by ordinary use.
**Medium** needs a specific condition. **Low** is hardening. **Info** is worth
knowing and needs no action.

| ID | Severity | Finding | Status |
| --- | --- | --- | --- |
| P-1 | Medium | An unfinished page was written to disk every 2 seconds by default | Fixed |
| P-2 | Medium | Requests to a local Ollama could go through a network proxy | Fixed |
| P-3 | Medium | The Wikipedia lookup tick was remembered across launches | Fixed |
| P-4 | Medium | Temporary working copies were undisclosed, loosely protected, and not cleared | Fixed |
| P-5 | Medium | Two statements to users overclaimed | Fixed |
| P-6 | Info | Merely checking for the AI model created a folder on a fresh install | Fixed |
| S-1 | Medium | A crafted session id could make the app delete its parent folder | Fixed |
| S-2 | Medium | TD Snap's own page set was opened read-write in one code path | Fixed |
| S-3 | Low | A website could trigger TD Snap navigation with a forged GET | Fixed |
| S-4 | Low | API responses could be cached by the browser | Fixed |
| S-5 | Low | The working-copy folder was shared and predictable on POSIX | Fixed |
| S-6 | Low | Table names from a file's own schema were put into SQL unquoted | Fixed |
| S-7 | Info | SQLite safety settings for untrusted files not set | Fixed (defense in depth) |
| S-8 | Info | The desktop window relied on library defaults for privacy | Fixed |
| S-9 | Info | The reference link was assigned from server data unchecked | Fixed |
| S-10 | Info | The launch scripts' local request could use a proxy | Fixed |
| S-11 | Info | Maintainer's local Windows paths in `design-qa.md` | Fixed |

### P-1. An unfinished page was kept by default (Medium, CWE-312)

`draft.js` ran an autosave timer from the moment the app loaded and wrote the list
of buttons the user was planning, with their spoken messages, the target page
name, and the new page's title, to `settings.json` every two seconds. Nothing asked
the user. The README said "Nothing is written to disk until you save something".

That is the user's own vocabulary, and it was kept without a choice. **Fix:** the
feature is now opt-in. It is off until the user ticks **Keep an unfinished page**
under **What AAC Editor saves**. The browser does not write while it is off, and the
server also refuses to store a draft unless the saved preference says so, so a bug
in the page cannot start keeping one. Turning it off deletes the stored draft. A
draft that an older version already saved is offered once ("resume or discard"),
then deleted when answered unless the option is on, so nobody loses work unseen and
nothing is kept unasked. Tests: `test_web.py` (four server tests) and the
"private by default" group in `test_live_edit.spec.js`.

### P-2. "Local" requests could go through a proxy (Medium, CWE-200)

`urllib` sends a request through `HTTP_PROXY`, or the Windows proxy settings, for
every destination, `127.0.0.1` included, unless `NO_PROXY` exempts it. The request
AAC Editor sends to a local Ollama contains the page title, the labels already on the
page, and a sample of the page set's wording. Reproduced: with `http_proxy` set and
no `no_proxy`, `urllib.request.proxy_bypass("localhost")`, `("127.0.0.1")`, and
`("::1")` are all false, and the stock call delivers the request to the proxy.

This needs Ollama in use (optional) and a proxy configured without a loopback
exemption, which is plausible on a school or clinic network. **Fix:**
`tdsnap/web/localhttp.py` is the one way the app talks to this computer. It never
uses a proxy, refuses any address that is not loopback, and refuses to follow a
redirect. Ollama, the "is it already running" check, and the window-raise request all
use it. The two connections that are meant to leave the computer deliberately do not,
because on a managed network they need the proxy to work at all. Tests use real
sockets: a stand-in proxy and a stand-in Ollama, in `test_privacy_contract.py`.

### P-3. The Wikipedia tick was remembered (Medium)

The one setting that sends anything off the computer was saved and restored, so one
tick became a standing permission. **Fix:** it is not saved and not restored, and the
server drops it as an unknown preference. It starts off every time the app opens.

### P-4. Temporary working copies (Medium, CWE-276, CWE-377)

Opening an exported file copies it to the temp folder, where it stays while the file
is open. Three problems. It was not mentioned in the README or the privacy panel. On
a shared POSIX computer the folder (`/tmp/tdsnap-editor`) and its files were created
with default permissions, readable by other accounts, and a folder or symlink another
user created first would be trusted. And a crash left copies behind, with nothing
the user could do to remove them. **Fix:** the folder is per user
(`tdsnap-editor-<uid>`), created `0700`, checked to be a real directory owned by the
current user, and tightened if it was loose. Copies are removed on any orderly exit:
an unhandled error, the process being told to stop (`SIGTERM`), or its terminal being
closed (`SIGHUP`). Testing a real process showed that `SIGTERM` and `SIGHUP` used to
leave the copy behind, because Python dies on those signals without running cleanup.
Only a forced kill still can, and nothing can catch that. **Clear all saved data** now removes leftovers (and
says if an open file's copy was kept). The panel and the privacy page describe all
of it, with the real folder names. Windows keeps `%TEMP%` private to the user already.

### P-5. Overclaiming (Medium)

The panel said "AAC Editor hasn't written anything to disk on this computer" when a
working copy or a model might be there, and said "Nothing is saved on this computer
anymore" after Clear, while a downloaded model remained. The README said nothing is
written until you save. **Fix:** the wording now says exactly what exists and what
Clear did and did not remove. A test fails if the old phrases return, and another
fails if a document names a host the code does not use, or the code uses one the
documents do not name.

### P-6. Looking created a folder (Info)

`localai._models_dir()` created `tdsnap-editor/models` every time anything asked where
the model would be, which includes the status check behind the suggestions panel. On a
fresh install, opening the panel put an empty folder on disk while the app said it had
saved nothing. **Fix:** the folder is created only when a download is about to write into
it. Two tests fail on the old behavior: one checks that status, install, and path checks
leave the data folder empty, the other that reading the settings, AI status, health,
config, and support-report endpoints writes nothing.

### S-1. A crafted session id could delete the folder above the session root (Medium, CWE-22)

The session id comes from the URL and was joined onto the session folder without
checking. A request for session `..` made the app treat the temp folder itself as a
session when `current` and `meta.json` existed there, and closing that session ran
`rmtree` on it. **Reproduced on the original code:** `GET /api/pageset/..` registered
the session, then `POST /api/pageset/../close` deleted the files in the parent. It
needs the token and the ability to create two files in the temp folder, so it is a
local attack, but it is a deletion primitive. **Fix:** ids must match
`[A-Za-z0-9_-]{1,64}` (so no dot can appear), and the resolved folder must be a direct
child of the session root. The test replays the exploit, and fails without the fix.

### S-2. TD Snap's own page set opened read-write once (Medium)

Every read of TD Snap's page set used `mode=ro` except one (`live.py`, reading saved
placements), which only selected but opened the file for writing. The README
promises TD Snap's file is read only. **Fix:** it opens read-only like the rest. A
test scans every module that reads TD Snap's file and fails on any `sqlite3.connect`
without `mode=ro`.

### S-3. Forged GETs and the two header-only endpoints (Low, CWE-352)

`GET /api/tdsnap/page-layout?page=X` navigates TD Snap to page X when X is not the
visible page. A request for `http://127.0.0.1:8765/...` carries a `Host` the server
accepts whichever page caused it, so any website could move the user's AAC app to a
different page. Separately, the two TD Snap edit endpoints
(`/api/tdsnap/page`, `/api/tdsnap/edit-plan`) required only a custom header, while
their Grid 3 equivalents required the token as well. The header does block
cross-origin browser requests; the token is the second wall. **Fix:** everything under
`/api/tdsnap/` and `/api/grid3/` needs the per-run token, and so does every POST, PUT,
and DELETE except `/api/focus` (a second launch raising the window). The token is
compared with `secrets.compare_digest`. Two things are deliberately exempt and
documented in the source: the live `.obz` download (a plain navigation cannot carry a
header, and the page that starts a download cannot read it) and `/api/diagnostics`
(read-only, returns no page content, and has to keep working when things are broken).
A test enumerates every route in the app and checks each state-changing one.

### S-4. API responses could be cached (Low)

Responses carrying vocabulary, drafts, and templates had no cache header, so a
browser could store them. **Fix:** `Cache-Control: no-store` on everything under
`/api/`. Also added `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy`,
`X-Permitted-Cross-Domain-Policies`, and a `Permissions-Policy` that switches off
browser features the app never uses.

### S-5. The session folder was shared and predictable (Low)

See P-4. Listed on its own because it is a security fix as well as a privacy one.

### S-6. Unquoted SQL identifiers (Low)

Table names read from the file being opened were put into `SELECT COUNT(*) FROM {t}`
and `SELECT * FROM "{t}"` with comments saying they never came from user input. They
come from the file's own schema, so a hostile file chooses them. It is not an
injection in practice: `execute` runs one statement, the connection used to inspect is
read-only or a private copy, and a `SELECT` cannot change anything, so the worst
outcome was an error or a slow query. **Fix:** one `quote_identifier` helper, used
everywhere, with the incorrect comments corrected and a test that opens files with
table names like `a"b` and `Page"; DROP TABLE Page; --`.

### S-7. SQLite safety settings (Info)

Every working copy now sets `trusted_schema=OFF` and `cell_size_check=ON`. Be clear
about how much this does: Python registers no SQL functions of its own, so
`trusted_schema` changes nothing a hostile file can do today. It means a function this
app registers later can never be called from a file's own triggers or views, and
`cell_size_check` turns a crafted page into an error. It cannot affect a genuine file:
the committed schema snapshot, dumped from a real TD Snap 4.13 export, has no
triggers, views, virtual tables, or `CHECK` constraints, and every default is a
constant. A test asserts both of those facts.

### S-8. The desktop window (Info)

The installed window's privacy rested on pywebview defaults. They are right for the
pinned 6.2.1 (`private_mode=True`, which also deletes the embedded browser's profile
when the window closes, and `OPEN_EXTERNAL_LINKS_IN_BROWSER=True`, which keeps any
outside page out of the window that carries the native bridge). **Fix:** both are now
set explicitly, so a library update cannot change them silently.

### S-9. The reference link (Info)

The Wikipedia link under suggestions was assigned from a server field. The server
builds it from a fixed host, but it is followed with a click that leaves the app, so
the page now only assigns it if it starts with `https://en.wikipedia.org/wiki/`. A test
feeds it a `javascript:` URL, a foreign host, and a look-alike host.

### S-10. The launch scripts (Info)

`launch.bat` and `launch.sh` ask a running copy to quit, over loopback, using the
token. That request now bypasses any proxy too.

### S-11. Local paths in `design-qa.md` (Info)

Two lines named the maintainer's Windows username and a local tool's folder. They are
replaced with placeholders. The git history still contains the originals.

## Checked and found sound

- **Network surface.** Six modules import a networking library, and each is named in
  `tests/test_privacy_contract.py` with its reason. The only remote hosts in the source
  are `huggingface.co` and `en.wikipedia.org`. A test fails if a seventh module or a
  third host appears.
- **The page.** No third-party scripts, styles, fonts, or images. No `localStorage`,
  `IndexedDB`, or cookies. One `fetch` helper, same origin. Data reaches the DOM with
  `textContent`; `innerHTML` is only used to clear or with constants. The Content
  Security Policy has no `unsafe-eval`, no inline script, and `connect-src 'self'`, so
  a browser refuses a connection to anywhere else. A browser test proves it by trying.
- **The server.** Binds `127.0.0.1` only, with no option to change it. Rejects any
  other `Host`. No CORS headers. Inputs are bounded in length and count.
- **Wikipedia lookup.** The reference field accepts an article title or an `https`
  link to English Wikipedia and nothing else, so it cannot be pointed at an internal
  address. `lookup()` has no parameter that could carry anything but a title.
- **Model download.** Pinned to an immutable commit, an exact size, and a SHA-256,
  and checked for the GGUF header; a file that fails is deleted. Started only by two
  button clicks.
- **Ollama.** The address must be loopback, enforced in two places.
- **Files from other people.** `.obz` archives are read in memory, member by member,
  with limits on entries, bytes, and total size, and never extracted. The live Grid 3
  connection only reads grid sets from Grid 3's own user folder, after resolving
  symlinks. A `.gridset` someone opens as a file is copied into the private session
  folder first and read there: entry count, total size, and each XML entry are
  bounded, password-protected entries are refused, nothing is extracted, and edits
  stream every untouched entry into a new package rather than unpacking it. XML is
  parsed by the standard library's expat, which resolves no external entities and
  (from expat 2.4) limits entity amplification. `inspect-format` reads a file the
  same bounded way, opens any SQLite inside read-only with `harden_untrusted`, and
  prints names of tables, columns, and elements, never values. There is no
  `eval`, `exec`, `pickle`, `yaml.load`, `shell=True`, or disabled TLS check anywhere.
- **Support report.** Built from an allow-list of keys, so page content cannot get in.
- **Privileges.** The app runs `asInvoker`. Administrator approval is requested only
  for Grid 3, by an explicit UAC prompt, and the build refuses a `uiAccess` manifest
  without a valid signature. Installed under Program Files, so a standard user cannot
  replace what an elevated copy runs.
- **Release.** Built only from an exact version-matched tag by a public workflow,
  tested, smoke-tested after install, checksummed, and attested before upload.
  The test workflows have read-only tokens.
- **Dependencies.** `pip-audit` reports no known vulnerabilities in the app's Python
  dependency tree.

## Not changed, and why

| Item | Why |
| --- | --- |
| Grid 3 XML is parsed with `xml.etree`, which does not resist entity-expansion attacks by itself | The input is a file in Grid 3's own user folder, capped in size, and modern `expat` limits expansion. Rejecting any file with a DTD would be the standard fix, but it could refuse a real Grid 3 file, and this review had no real Grid 3 files to test against. Worth doing with real files on hand |
| `style-src 'unsafe-inline'` in the policy | The page uses inline styles. Script and connection policies are strict, so it does not weaken the privacy claim. Worth tightening in time |
| `/api/config` hands the token to any same-origin caller | That is how a local page gets it. A process running as the user can already drive TD Snap and read these files directly, so the token is a defense against web pages, not against local code |
| The installer does not remove `%LOCALAPPDATA%\tdsnap-editor` | Needs a Windows build to write and test. Documented in the privacy page. A prompt at uninstall is the usual answer |
| Releases are not code-signed | Documented in the README and the privacy page, with the checksum and attestation to verify instead |
| A leftover working copy survives a forced kill or a crash until the next start after 24 hours, or Clear all | A forced kill cannot be caught by any program. The copy is needed for the reload-recovery feature in browser mode, and it is now disclosed and clearable |
| Development tooling reports 3 `npm audit` advisories in `stylelint`'s dependencies (`colord`, `fast-uri`, `nanoid`) | They never ship. Lockfile updated to patched versions |

## Recommendations for the maintainer

None of these change what is promised to users; they make the promise cheaper to keep.

1. **Pin third-party GitHub Actions to commit SHAs** in `release.yml` and the test
   workflows (Dependabot can keep the pins current). This review did not resolve the
   SHAs, because that means reading other repositories.
2. **Hash-pin the release build's dependencies.** `release-constraints.txt` fixes the
   direct inputs but not their dependencies, and the build uses `--extra-index-url`.
   A fully pinned requirements file with hashes (`pip-compile --generate-hashes`)
   would make a rebuild reproducible and close the dependency-confusion gap.
3. **Attach a software bill of materials** to each release.
4. **Offer to remove saved data at uninstall**, and show the choice in the installer.
5. **Seek a code-signing route** when one is available. SmartScreen's warning is the
   single biggest cause of doubt for a new user.
6. **Run the Windows-only paths against real TD Snap and Grid 3** for the changes
   here, once, before release (see the limits below).

## Limits of this review

- The Windows-specific code (UI Automation drivers, the installer, the WebView2
  window) was read, not run. Behavior of pywebview was confirmed from the pinned
  version's source. I could not run TD Snap, Grid 3, or the installer.
- No fuzzing, and no review of the internals of Flask, Werkzeug, llama.cpp, or
  pywebview. For those I relied on `pip-audit` and the pinned versions.
- The browser tests were run against Chromium, not the WebView2 the installed app uses.
- A review is a snapshot. The automated checks are what keep it true.

## Reproducing the checks

```bash
pip install ".[dev]"
python -m pytest tests/test_privacy_contract.py        # the privacy and security contract
python -m pytest                                        # everything
pip-audit .                                             # known vulnerabilities, Python
npm ci && npm audit                                     # development tooling
npm run test:e2e                                        # the browser tests
```
