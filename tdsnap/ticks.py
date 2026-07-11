"""Timestamps in .NET ticks, the format TD Snap stores everywhere.

A tick is 100 nanoseconds; tick 0 is 0001-01-01T00:00:00 UTC. Real page sets
carry values like 638575603671889890 in ``Page.Timestamp``, ``SyncData`` and
``Synchronization``.
"""

import datetime

# Seconds between 0001-01-01 and 1970-01-01 (the Unix epoch).
_EPOCH_OFFSET_SECONDS = 62_135_596_800
_TICKS_PER_SECOND = 10_000_000


def net_ticks_now() -> int:
    """Return the current UTC time as .NET ticks."""
    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    return int((now + _EPOCH_OFFSET_SECONDS) * _TICKS_PER_SECOND)


def ticks_to_datetime(ticks: int) -> datetime.datetime:
    """Convert .NET ticks to an aware UTC datetime (for display/debugging)."""
    seconds = ticks / _TICKS_PER_SECOND - _EPOCH_OFFSET_SECONDS
    return datetime.datetime.fromtimestamp(seconds, datetime.timezone.utc)
