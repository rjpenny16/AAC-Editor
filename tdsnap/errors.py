"""Error type, outcome classes and the error-code catalogue.

Every operation that can change a page set ends in exactly one *outcome*
(doc ``docs/reliability/04-DATA-INTEGRITY-AND-SAFETY.md``), carried as a
field rather than inferred from message text:

``refused``
    Preconditions failed; nothing was sent to the AAC app or file.
``verified``
    Applied, and every checked property matched.
``verified_with_gaps``
    Core content verified; listed extras (symbols, borders) could not be.
``rolled_back``
    Failed after writing; restoration verified against the baseline.
``partial``
    Failed after writing; restoration failed or was not attempted, and the
    current state was read and is known.
``unknown``
    The final state could not be read (hung call, lost window, process gone).

Rule: anything other than ``refused`` or ``verified`` stops a batch.

Each failure also carries a stable *code* from :data:`CODES`. Codes, not
message text, go into the operation log and the support report, because
messages can contain button labels and codes cannot.
"""

from typing import Optional

REFUSED = "refused"
VERIFIED = "verified"
VERIFIED_WITH_GAPS = "verified_with_gaps"
ROLLED_BACK = "rolled_back"
PARTIAL = "partial"
UNKNOWN = "unknown"

OUTCOMES = (REFUSED, VERIFIED, VERIFIED_WITH_GAPS, ROLLED_BACK, PARTIAL, UNKNOWN)
# The outcomes after which nothing on the page needs a second look.
CLEAN_OUTCOMES = (REFUSED, VERIFIED)
# The outcomes in which the page may differ from how it was before.
CHANGED_OUTCOMES = (PARTIAL, UNKNOWN)

# The error-code catalogue. Each code names one failure the user can be told
# about in one message (``tdsnap/web/static/errors.js`` holds the wording),
# and each is what the operation log records instead of free text.
CODES = {
    "REFUSED": "A precondition failed before anything was changed.",
    "NOT_FOREGROUND": "The AAC app was not the window in front.",
    "WINDOW_NOT_FOUND": "The AAC app's window could not be found.",
    "WRONG_APP": "The window found was not the expected AAC app.",
    "EDIT_MODE_BUSY": "The AAC app was already in edit mode.",
    "DIALOG_OPEN": "A dialog was open in the AAC app.",
    "FINGERPRINT_CHANGED": "The page changed after it was reviewed.",
    "ELEVATION_MISMATCH": "The AAC app runs with higher permissions than AAC Editor.",
    "VERIFY_MISMATCH": "After the edit the page did not match what was asked.",
    "VERIFY_UNREADABLE": "The page could not be read back to check the edit.",
    "ROLLBACK_INCOMPLETE": "The edit was not fully undone.",
    "EDIT_MODE_STUCK": "The AAC app did not leave edit mode.",
    "AUTOMATION_DEADLINE": "The AAC app stopped responding during the operation.",
    "AUTOMATION_FAILED": "An automation step failed unexpectedly.",
    "LIVE_LOCKED": "Live editing is paused until the last page is checked.",
    "APP_EXITED": "The AAC app closed during the operation.",
    "DB_LOCKED": "The AAC app's page set was busy.",
    "DB_UNREADABLE": "The AAC app's page set could not be read.",
    "TOKEN_STALE": "The app restarted since this page was loaded.",
    "SAVE_LOCKED": "The file is open in another program.",
    "SAVE_SAME_AS_SOURCE": "Saving over the original file is not allowed.",
    "SAVE_INVALID": "The saved copy did not re-open cleanly.",
    "SESSION_EXPIRED": "The working copy is no longer available.",
    "FILE_INVALID": "The file is not a usable page set.",
    "BUSY": "Another operation is running.",
    "AI_DEADLINE": "Suggestions took too long.",
    "AI_UNAVAILABLE": "No suggestion engine is ready.",
    "AI_FAILED": "The suggestion engine failed.",
    "INTERRUPTED": "An earlier edit was interrupted before it finished.",
    "UNEXPECTED": "Something failed that AAC Editor does not recognise.",
}


class PagesetError(Exception):
    """Raised when a file is not a usable TD Snap page set or an edit is unsafe.

    ``page_touched`` distinguishes the two kinds of failure a write path can
    have, because they call for different responses. False — the default, and
    the overwhelming majority — means the edit was *refused* before anything
    was written: a fingerprint that no longer matches, a cell that is no longer
    empty, a locked desktop. Nothing changed, and the next edit can proceed.
    True means the page was written to; anything queued behind it is no longer
    safe to run unattended. See ``live.apply_batch``, which acts on it.

    ``outcome`` is one of :data:`OUTCOMES` when the raiser knows it, and
    ``code`` a key of :data:`CODES`. Both are optional so that the many
    existing refusals stay one-liners; :func:`outcome_of` fills the gaps.
    """

    page_touched = False

    def __init__(self, *args, code: Optional[str] = None, outcome: Optional[str] = None,
                 page_touched: Optional[bool] = None):
        super().__init__(*args)
        if code is not None:
            self.code = code
        if outcome is not None:
            self.outcome = outcome
        if page_touched is not None:
            self.page_touched = page_touched


def outcome_of(error: BaseException) -> str:
    """The outcome class an exception stands for.

    An explicit ``outcome`` wins. Otherwise a :class:`PagesetError` that did
    not touch the page is ``refused``, and anything else, including an error
    that is not a :class:`PagesetError` at all, is ``unknown``: nothing has
    proved the page is unchanged.
    """
    explicit = getattr(error, "outcome", None)
    if explicit in OUTCOMES:
        return explicit
    if isinstance(error, PagesetError) and not getattr(error, "page_touched", False):
        return REFUSED
    return UNKNOWN


def code_of(error: BaseException) -> str:
    """The catalogue code for an exception; never free text."""
    code = getattr(error, "code", None)
    if isinstance(code, str) and code in CODES:
        return code
    if isinstance(error, PagesetError):
        return "REFUSED" if outcome_of(error) == REFUSED else "AUTOMATION_FAILED"
    return "UNEXPECTED"
