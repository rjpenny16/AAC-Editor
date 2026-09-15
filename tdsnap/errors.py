class PagesetError(Exception):
    """Raised when a file is not a usable TD Snap page set or an edit is unsafe.

    ``page_touched`` distinguishes the two kinds of failure a write path can
    have, because they call for different responses. False — the default, and
    the overwhelming majority — means the edit was *refused* before anything
    was written: a fingerprint that no longer matches, a cell that is no longer
    empty, a locked desktop. Nothing changed, and the next edit can proceed.
    True means the page was written to and then restored; the automation lost
    its footing partway, so anything queued behind it is no longer safe to run
    unattended. See ``live.apply_batch``, which is the caller that acts on it.
    """

    page_touched = False
