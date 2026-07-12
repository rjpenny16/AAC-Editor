"""Generate packaging/icon.ico — the app's window/taskbar/exe icon.

Draws the same mark as the web favicon (four rounded squares on the accent
blue) at every size Windows uses, and writes a multi-resolution .ico.
The result is committed, so this only needs re-running when the mark
changes:  pip install pillow && python scripts/make_icon.py
"""

import os

from PIL import Image, ImageDraw

ACCENT = (0, 113, 227, 255)  # #0071e3, same as the web UI
WHITE = (255, 255, 255)
SIZES = [16, 24, 32, 48, 64, 128, 256]
OUT = os.path.join(os.path.dirname(__file__), "..", "packaging", "icon.ico")

# The favicon's geometry on a 16-unit grid: (x, y, size, opacity).
SQUARES = [
    (2.5, 2.5, 5, 1.0),
    (8.5, 2.5, 5, 0.55),
    (2.5, 8.5, 5, 0.55),
    (8.5, 8.5, 5, 0.3),
]


def render(size: int) -> Image.Image:
    scale = 8  # draw big, downsample for smooth corners at small sizes
    canvas = size * scale
    unit = canvas / 16
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    ImageDraw.Draw(image).rounded_rectangle(
        (0, 0, canvas - 1, canvas - 1), radius=int(4 * unit), fill=ACCENT
    )
    for x, y, side, opacity in SQUARES:
        # Composite each square so its opacity blends over the blue instead
        # of punching a transparent hole (ImageDraw overwrites pixels).
        layer = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
        ImageDraw.Draw(layer).rounded_rectangle(
            (x * unit, y * unit, (x + side) * unit - 1, (y + side) * unit - 1),
            radius=int(1.25 * unit),
            fill=WHITE + (int(255 * opacity),),
        )
        image = Image.alpha_composite(image, layer)
    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    largest = render(SIZES[-1])
    largest.save(
        os.path.abspath(OUT),
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=[render(s) for s in SIZES[:-1]],
    )
    print(f"Wrote {os.path.abspath(OUT)}")


if __name__ == "__main__":
    main()
