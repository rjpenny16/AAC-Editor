"""Color encoding for TD Snap page sets.

TD Snap stores colors as signed 32-bit ARGB integers (e.g. the gray border on
its own toolbar buttons is -7828852 == 0xFF888A8C). Bordered buttons in real
files use BorderThickness 3.0.
"""

from .errors import PagesetError

BORDER_THICKNESS = 3.0


def argb_from_hex(value: str) -> int:
    """Convert '#RRGGBB' (or '#AARRGGBB') to TD Snap's signed ARGB int."""
    text = (value or "").strip().lstrip("#")
    if len(text) == 6:
        text = "FF" + text
    if len(text) != 8:
        raise PagesetError(f"Not a color: {value!r} (expected #RRGGBB)")
    try:
        number = int(text, 16)
    except ValueError:
        raise PagesetError(f"Not a color: {value!r} (expected #RRGGBB)")
    return number - 0x1_0000_0000 if number > 0x7FFF_FFFF else number


def hex_from_argb(value: int) -> str:
    """Convert a signed ARGB int back to '#RRGGBB' (drops alpha)."""
    return f"#{value & 0xFFFFFF:06X}"
