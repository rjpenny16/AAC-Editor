# Security policy

## Reporting a vulnerability

Please do not open a public issue for a security or privacy problem. Use
[GitHub's private vulnerability report](https://github.com/rjpenny16/AAC-Editor/security/advisories/new)
and include the affected version, reproduction steps, and impact.

Do not attach real TD Snap page sets, Playwright traces, access tokens, or AAC
vocabulary. Use a minimal synthetic example and redact personal information.

## What AAC Editor protects

The plain-language statement for people using the app is
[PRIVACY.md](PRIVACY.md). The technical review behind it, with findings, evidence,
and what was deliberately left alone, is
[docs/SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md). In short:

- **Nothing you type or open is sent anywhere.** There are no accounts, analytics,
  crash reports, or update checks. The app reaches the internet in two situations,
  both started by the user: the one-time model download from `huggingface.co` and
  the optional Wikipedia lookup, which sends only a page title.
- **Local only.** The server binds to `127.0.0.1`, rejects any other `Host`
  (DNS rebinding), and refuses to talk to an Ollama address that is not loopback.
  Requests to loopback never use a proxy and never follow a redirect.
- **Hardened against web pages.** Every state-changing request, and every request
  that can move or click something in TD Snap or Grid 3, needs a per-run secret
  token, compared in constant time. The page is served with a Content Security
  Policy that has no third-party origins, and API responses are `no-store`.
- **Little on disk.** Settings and templates in one file. An unfinished page is
  kept only if the user turns that on. Working copies of exported files sit in a
  private temporary folder and are removed on exit. **Clear all saved data**
  removes all of it.
- **Hostile files.** Board files are size-limited and read in memory. Page sets are
  validated before and after every edit. TD Snap's own page set is opened read-only.

Releases are not code-signed; verify the SHA-256 checksum and build
attestation attached to each release before installing. The installed app
runs `asInvoker` without UIAccess. Live Grid 3 editing uses an explicit
administrator restart that the user approves through UAC. Elevated
endpoints remain loopback-only and require both the
per-process API token and a custom mutation header. They accept no caller-supplied
file path, verify the target process is the installed Grid 3 executable, and
reject dirty, protected, ambiguous, stale, locked, or accessibility-incompatible
targets. Diagnostic data must not include vocabulary or grid contents.

AI generation stays local by default. Online Wikipedia grounding is a separate,
explicit opt-in that sends only the page title or category shown beside the
control, starts off every time the app opens, and is disabled even when requested
by `TDSNAP_WEB_GROUNDING=0`.

## Keeping the promises true

`tests/test_privacy_contract.py` turns these statements into checks. It uses real
sockets to prove loopback traffic bypasses a configured proxy, scans the source for
every module that can reach the network and every web address it contains, enumerates
every route to prove each state-changing one needs the token, and compares the
documents with the code. Adding a new way for data to leave the computer fails it on
purpose, so the change gets reviewed and documented.

The latest release is the supported version. You should receive an initial
response within seven days. A fix and disclosure timeline will be agreed upon
after the report is reproduced.
