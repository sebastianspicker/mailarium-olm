#!/usr/bin/env python3
"""Regenerate synthetic Streamlit documentation screenshots at 1440x900.

Headless Streamlit browser captures are unreliable in many environments
(blank first paint). This script captures the maintained HTML sources under
docs/screenshots/_capture_html/ with Chrome and verifies the documented PNG
dimensions.

Requires Google Chrome (or CHROME_BIN).
"""

from __future__ import annotations

import os
import struct
import subprocess  # nosec B404
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "screenshots"
HTML_DIR = OUT / "_capture_html"
WIDTH, HEIGHT = 1440, 900
DEFAULT_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

TARGETS = (
    ("empty.html", "streamlit-empty-archive.png"),
    ("search.html", "streamlit-search-ui.png"),
    ("dashboard.html", "streamlit-dashboard-ui.png"),
)


def main() -> int:
    """Regenerate every synthetic documentation PNG from its maintained HTML source."""
    chrome = os.environ.get("CHROME_BIN", DEFAULT_CHROME)
    if not Path(chrome).exists():
        print(f"Chrome not found at {chrome}. Set CHROME_BIN.", file=sys.stderr)
        return 1

    for source_name, dest_name in TARGETS:
        source = HTML_DIR / source_name
        dest = OUT / dest_name
        if not source.exists():
            print(f"Missing HTML source: {source}", file=sys.stderr)
            return 1
        print(f"Capturing {source.name} -> {dest}")
        shot = subprocess.run(  # nosec B603
            [
                chrome,
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                "--force-device-scale-factor=1",
                f"--window-size={WIDTH},{HEIGHT}",
                f"--screenshot={dest}",
                source.resolve().as_uri(),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if shot.returncode != 0 or not dest.exists():
            print(shot.stderr or shot.stdout, file=sys.stderr)
            return 1
        _normalize_png(dest)
        _assert_png(dest)
        print(f"  wrote {dest.stat().st_size} bytes")
    print("All documentation screenshots updated.")
    return 0


def _normalize_png(path: Path) -> None:
    from PIL import Image

    image = Image.open(path).convert("RGB")
    if image.size != (WIDTH, HEIGHT):
        image = image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    image.save(path, format="PNG", optimize=True)


def _assert_png(path: Path) -> None:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError(f"{path} is not a PNG")
    width, height = struct.unpack(">II", data[16:24])
    if (width, height) != (WIDTH, HEIGHT):
        raise RuntimeError(f"{path} is {width}x{height}, expected {WIDTH}x{HEIGHT}")
    from PIL import Image

    image = Image.open(path).convert("RGB")
    dark = 0
    for x in range(0, WIDTH, 8):
        for y in range(0, HEIGHT, 8):
            if sum(image.getpixel((x, y))) < 500:
                dark += 1
    if dark < 50:
        raise RuntimeError(f"{path} appears blank (dark samples={dark})")


if __name__ == "__main__":
    raise SystemExit(main())
