"""Render share image, favicon PNGs, and favicon.ico from committed sources.

Run from the repo with the backend venv (Playwright + system Chrome):
  backend/.venv/Scripts/python.exe frontend/scripts/make-assets.py
"""

import struct
from pathlib import Path

from playwright.sync_api import sync_playwright

FRONTEND = Path(__file__).resolve().parent.parent
PUBLIC = FRONTEND / "public"
SCRIPTS = FRONTEND / "scripts"


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"not a PNG: {path}"
    width, height = struct.unpack(">II", data[16:24])
    return width, height


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1200, "height": 630})
    page.goto((SCRIPTS / "og-page.html").as_uri())
    page.screenshot(path=str(PUBLIC / "og-image.png"))
    for name, size in [
        ("favicon-32.png", 32),
        ("apple-touch-icon.png", 180),
        ("icon-192.png", 192),
        ("icon-512.png", 512),
    ]:
        page.set_viewport_size({"width": size, "height": size})
        page.goto((SCRIPTS / "favicon.html").as_uri())
        page.screenshot(path=str(PUBLIC / name))
    browser.close()

assert png_size(PUBLIC / "og-image.png") == (1200, 630)
assert png_size(PUBLIC / "favicon-32.png") == (32, 32)
assert png_size(PUBLIC / "apple-touch-icon.png") == (180, 180)
assert png_size(PUBLIC / "icon-192.png") == (192, 192)
assert png_size(PUBLIC / "icon-512.png") == (512, 512)

png = (PUBLIC / "favicon-32.png").read_bytes()
header = struct.pack("<HHH", 0, 1, 1)
entry = struct.pack("<BBBBHHII", 32, 32, 0, 0, 1, 32, len(png), 6 + 16)
(PUBLIC / "favicon.ico").write_bytes(header + entry + png)
print("assets done")
