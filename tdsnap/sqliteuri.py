"""Read-only SQLite URIs that survive awkward folder names (REL-013)."""

import os
import urllib.parse


def sqlite_ro_uri(path) -> str:
    """A ``file:`` URI that opens *path* read-only, whatever its name contains.

    REL-013: the URIs were built as ``f"file:{path}?mode=ro"``, so a folder
    with ``#`` in its name ended the path at the ``#`` and one with ``%`` was
    decoded as an escape; on the live path that silently degraded TD Snap
    page reading. Every character outside the safe set is percent-encoded.
    """
    absolute = os.path.abspath(os.fspath(path))
    if os.name == "nt":
        absolute = "/" + absolute.replace("\\", "/")
    quoted = urllib.parse.quote(absolute, safe="/:")
    # A UNC path (//server/share) needs an empty authority, or SQLite reads
    # "server" as a host name and refuses it.
    if quoted.startswith("//"):
        quoted = "//" + quoted
    return f"file:{quoted}?mode=ro"
