# Security policy

## Reporting a vulnerability

Please do not open a public issue for a security or privacy problem. Use
[GitHub's private vulnerability report](https://github.com/rjpenny16/AAC-Editor/security/advisories/new)
and include the affected version, reproduction steps, and impact.

Do not attach real TD Snap page sets, Playwright traces, access tokens, or AAC
vocabulary. Use a minimal synthetic example and redact personal information.

AI generation stays local by default. Online Wikipedia grounding is a separate,
explicit opt-in that sends only the page title or category shown beside the
control; `TDSNAP_WEB_GROUNDING=0` disables it even when requested.

Portable or unsigned development Grid 3 editing may use an explicit
administrator fallback. The installed production app remains `asInvoker` and
uses UIAccess only when its Authenticode signature is trusted. Elevated
endpoints remain loopback-only and require both the
per-process API token and a custom mutation header. They accept no caller-supplied
file path, verify the target process is the installed Grid 3 executable, and
reject dirty, protected, ambiguous, stale, locked, or accessibility-incompatible
targets. Diagnostic data must not include vocabulary or grid contents.

The latest release is the supported version. You should receive an initial
response within seven days. A fix and disclosure timeline will be agreed upon
after the report is reproduced.
