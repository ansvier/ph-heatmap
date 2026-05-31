"""Generate public/og.png — the default 1200×630 Open Graph image.

Run once: `./venv/bin/python scripts/build_og.py`. Output is committed to the
repo. Re-run only if HotMap branding changes (logo, tagline, color).

Layout:
  - Black background (#0a0a0a, matches site)
  - HotMap orange wordmark centered horizontally, upper-third
  - Tagline below, centered
  - Optional accent block in HotMap orange (#ff9000) along bottom
"""
from __future__ import annotations
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_PATH = Path(__file__).resolve().parent.parent / "public" / "og.png"
SIZE = (1200, 630)
BG = (10, 10, 10)             # #0a0a0a, matches --bg
FG = (245, 245, 245)          # #f5f5f5, matches --fg
ORANGE = (255, 144, 0)        # #ff9000, brand

WORDMARK = "HotMap"
TAGLINE = "Live treemap of view-growth momentum on Pornhub"


def _load_font(preferred_paths: list[Path], size: int) -> ImageFont.FreeTypeFont:
    """Try a list of font paths; fall back to PIL's default if all fail."""
    for p in preferred_paths:
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def main() -> None:
    img = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(img)

    # System fonts on macOS / Linux GitHub runners. Helvetica/Arial fallbacks
    # for macOS; DejaVu/Liberation for Linux.
    bold_candidates = [
        Path("/System/Library/Fonts/Helvetica.ttc"),
        Path("/Library/Fonts/Arial Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ]
    regular_candidates = [
        Path("/System/Library/Fonts/Helvetica.ttc"),
        Path("/Library/Fonts/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ]
    wordmark_font = _load_font(bold_candidates, size=180)
    tagline_font = _load_font(regular_candidates, size=42)

    # Wordmark — "Hot" white, "Map" orange (matches site logo treatment).
    hot_w = draw.textlength("Hot", font=wordmark_font)
    map_w = draw.textlength("Map", font=wordmark_font)
    total_w = hot_w + map_w
    wm_x = (SIZE[0] - total_w) / 2
    wm_y = 180
    draw.text((wm_x, wm_y), "Hot", font=wordmark_font, fill=FG)
    draw.text((wm_x + hot_w, wm_y), "Map", font=wordmark_font, fill=ORANGE)

    # Tagline
    tag_w = draw.textlength(TAGLINE, font=tagline_font)
    draw.text(((SIZE[0] - tag_w) / 2, 420), TAGLINE, font=tagline_font, fill=FG)

    # Orange accent bar along bottom, like the .top-perf border-left.
    draw.rectangle([(0, 610), (SIZE[0], 630)], fill=ORANGE)

    img.save(OUT_PATH, "PNG", optimize=True)
    print(f"wrote {OUT_PATH} ({OUT_PATH.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
