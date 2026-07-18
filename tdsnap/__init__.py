"""tdsnap — safe editor for TD Snap page-set files (.sps/.spb).

A TD Snap page set is a SQLite database with a rich, versioned schema. This
package edits it the safe way: it discovers the schema at runtime, clones
existing rows as templates instead of inserting hand-built ones, creates every
linkage row the app expects (PageLayout, CommandSequence, ButtonPageLink,
SyncData), and validates the database after every write. The user's original
file is never modified; edits land in a separate ``*.edited`` copy.
"""

from .errors import PagesetError
from .pageset import Pageset
from .builder import add_category_page
from .validate import validate_pageset, validate_new_page

__version__ = "2.2.0"

__all__ = [
    "PagesetError",
    "Pageset",
    "add_category_page",
    "validate_pageset",
    "validate_new_page",
    "__version__",
]
