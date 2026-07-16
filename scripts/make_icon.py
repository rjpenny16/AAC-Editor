"""Generate the Windows icon from the AAC Editor logo."""

import os

from PIL import Image

SIZES = [16, 24, 32, 48, 64, 128, 256]
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SOURCE = os.path.join(
    ROOT, "tdsnap", "web", "static", "assets", "aac-editor-logo.png"
)
OUT = os.path.join(ROOT, "packaging", "icon.ico")


def main() -> None:
    with Image.open(SOURCE) as source:
        logo = source.convert("RGBA")
    bounds = logo.getbbox()
    if not bounds:
        raise ValueError("The logo is fully transparent.")
    logo = logo.crop(bounds)
    padding = round(max(logo.size) * 0.08)
    side = max(logo.size) + 2 * padding
    icon = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    icon.alpha_composite(
        logo, ((side - logo.width) // 2, (side - logo.height) // 2)
    )
    icon.save(OUT, format="ICO", sizes=[(size, size) for size in SIZES])
    with Image.open(OUT) as generated:
        assert generated.format == "ICO" and generated.size == (256, 256)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
