"""System tray icon. Icon image generated with Pillow (no asset files)."""
from __future__ import annotations

from PIL import Image, ImageDraw


def _icon_image():
    img = Image.new("RGB", (64, 64), "#0f766e")
    draw = ImageDraw.Draw(img)
    draw.polygon([(32, 10), (52, 32), (32, 54), (12, 32)], fill="#fbbf24")
    return img


def build_tray(on_open, on_fetch, on_quit):
    import pystray
    menu = pystray.Menu(
        pystray.MenuItem("Open Dashboard", lambda *_: on_open(), default=True),
        pystray.MenuItem("Fetch Now", lambda *_: on_fetch()),
        pystray.MenuItem("Quit", lambda *_: on_quit()),
    )
    return pystray.Icon("SupplyChainSparks", _icon_image(), "Supply Chain Sparks", menu)
