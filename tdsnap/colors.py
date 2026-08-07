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
    except ValueError as exc:
        raise PagesetError(f"Not a color: {value!r} (expected #RRGGBB)") from exc
    return number - 0x1_0000_0000 if number > 0x7FFF_FFFF else number


def hex_from_argb(value: int) -> str:
    """Convert a signed ARGB int back to '#RRGGBB' (drops alpha)."""
    return f"#{value & 0xFFFFFF:06X}"


# The five communicative-function border colors used on topic pages —
# question/comment/positive/negative/personal — mirrored from the frontend's
# FUNCTIONS map (tdsnap/web/static/state.js). This is a clinical
# color-coding convention, not a UI preference: a request is free to choose
# which function a button has, never what color that function renders as.
FUNCTION_BORDER_COLORS = {
    "question": "#1E88E5",
    "comment": "#F57C00",
    "positive": "#43A047",
    "negative": "#E53935",
    "personal": "#8E24AA",
}

ALLOWED_BORDER_ARGB = frozenset(
    argb_from_hex(color) for color in FUNCTION_BORDER_COLORS.values()
)


def is_allowed_border_color(value: int) -> bool:
    """True when *value* (a signed ARGB int) is one of the five clinical
    function-border colors — the only button borders the product writes."""
    return value in ALLOWED_BORDER_ARGB
