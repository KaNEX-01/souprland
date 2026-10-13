"""Generates wallpapers from palette colors.

Why we generate them: the real wallpapers of the reference rices are copyrighted
(anime art, game screenshots, purchased illustrations) and cannot be distributed
with the repo. Instead, each profile generates an image derived from its own palette
that evokes the source's *composition*: ambxst's flowing lava bands, cosmic's star
field, lamp's paper texture — no source image is copied directly.

A copy pre-rendered with this generator ships with the repo for all 48 profiles
under `wallpapers/<profile>.png`; `install.sh` copies it directly (via
WALLPAPER_IMAGE) instead of redrawing it. If the file is missing/deleted, this module
falls back to on-the-fly generation according to `WALLPAPER_STYLE` (see
docs/gallery-catalog.md — copyright note).

No dependencies: the PNG is written directly with ``zlib``. Neither Pillow nor
ImageMagick is needed, because python3 is already present wherever this installer runs.

For speed every pattern draws per row/span; the only per-pixel loops are sparse
effects like stars and grain. A 1920x1080 image takes under a second.
"""

from __future__ import annotations

import math
import random
import struct
import zlib
from pathlib import Path

from . import themes

#: Pattern name → description. Profiles pick one of these with WALLPAPER_STYLE.
STYLES: dict[str, str] = {
    "waves": "Flowing horizontal bands — lava/forest layers",
    "stars": "Star field and a faint galaxy band",
    "orb": "Large soft disc in the background — moon or sun",
    "mist": "Misty hill silhouettes and thin slanted rain",
    "grid": "Technical grid and scanlines",
    "paper": "Flat background with light grain — paper feel",
    "solid": "Solid color, slight darkening in the corners",
    "dunes": "Diagonal soft bands — sand dunes",
}

DEFAULT_SIZE = (1920, 1080)


# --------------------------------------------------------------- png ------
def _chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


#: tEXt chunk written right after IHDR. It marks the file as a generated
#: pattern: apply.py/install.sh may then replace it when another pattern is
#: picked (without it the first generated pattern counted as "your own image"
#: and every later pattern choice silently did nothing).
GENERATED_MARK = b"Software\x00souprland-pattern"


def is_generated(path: Path) -> bool:
    """Was the file written by write_png (a generated pattern)?"""
    try:
        with open(path, "rb") as f:
            head = f.read(128)
    except OSError:
        return False
    return GENERATED_MARK in head


def write_png(path: Path, width: int, height: int, pixels: bytearray) -> Path:
    """``pixels`` is given row by row as RGB (without the filter byte)."""
    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)                                   # filter: None
        raw += pixels[y * stride:(y + 1) * stride]
    png = (b"\x89PNG\r\n\x1a\n"
           + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
           + _chunk(b"tEXt", GENERATED_MARK)
           + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
           + _chunk(b"IEND", b""))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    return path


# ------------------------------------------------------------ color ------
def _rgb(value: str) -> tuple[int, int, int]:
    value = (value or "000000").lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a, b, t: float):
    t = max(0.0, min(1.0, t))
    return (round(a[0] + (b[0] - a[0]) * t),
            round(a[1] + (b[1] - a[1]) * t),
            round(a[2] + (b[2] - a[2]) * t))


def _shade(colour, amount: float):
    """amount > 0 lightens, < 0 darkens."""
    target = (255, 255, 255) if amount > 0 else (0, 0, 0)
    return _mix(colour, target, abs(amount))


class Canvas:
    def __init__(self, width: int, height: int):
        self.w, self.h = width, height
        self.buf = bytearray(width * height * 3)

    def row(self, y: int, colour) -> None:
        start = y * self.w * 3
        self.buf[start:start + self.w * 3] = bytes(colour) * self.w

    def span(self, y: int, x0: int, x1: int, colour) -> None:
        x0, x1 = max(0, x0), min(self.w, x1)
        if x1 <= x0:
            return
        start = (y * self.w + x0) * 3
        self.buf[start:start + (x1 - x0) * 3] = bytes(colour) * (x1 - x0)

    def point(self, x: int, y: int, colour) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.buf[i:i + 3] = bytes(colour)

    def vertical_gradient(self, top, bottom) -> None:
        for y in range(self.h):
            self.row(y, _mix(top, bottom, y / max(1, self.h - 1)))


# ----------------------------------------------------------- patterns ----
def _waves(c: Canvas, pal, rnd) -> None:
    """Layered flowing bands (ambxst, green-mango, nixos)."""
    base, dark, accent = _rgb(pal["BG"]), _rgb(pal["BG_DARK"]), _rgb(pal["ACCENT"])
    c.vertical_gradient(_shade(dark, -0.25), base)
    layers = 7
    for i in range(layers):
        t = (i + 1) / layers
        colour = _mix(_shade(dark, -0.15), _mix(base, accent, 0.45), t)
        amp = c.h * (0.045 + 0.02 * (1 - t))
        mid = c.h * (0.30 + 0.62 * t)
        freq = 1.1 + 0.55 * i
        phase = rnd.uniform(0, math.tau)
        for x in range(c.w):
            u = x / c.w
            y0 = int(mid + amp * math.sin(u * math.tau * freq + phase)
                     + amp * 0.35 * math.sin(u * math.tau * freq * 2.3 + phase * 1.7))
            for y in range(max(0, y0), c.h):
                i3 = (y * c.w + x) * 3
                c.buf[i3:i3 + 3] = bytes(colour)


def _stars(c: Canvas, pal, rnd) -> None:
    """Star field (cosmic-void, pixel-cosmos)."""
    dark, base = _rgb(pal["BG_DARK"]), _rgb(pal["BG"])
    fg, accent = _rgb(pal["FG"]), _rgb(pal["ACCENT"])
    c.vertical_gradient(_shade(dark, -0.35), _shade(base, -0.1))
    # Galaxy band: blended over the existing gradient instead of replacing the row,
    # otherwise a sharp seam appears at the band's edge.
    for y in range(c.h):
        d = abs(y - c.h * 0.42) / (c.h * 0.26)
        if d >= 1:
            continue
        i0 = y * c.w * 3
        under = (c.buf[i0], c.buf[i0 + 1], c.buf[i0 + 2])
        c.row(y, _mix(under, _mix(base, accent, 0.4), (1 - d) ** 2 * 0.45))
    for _ in range(int(c.w * c.h / 2600)):
        x, y = rnd.randrange(c.w), rnd.randrange(c.h)
        b = rnd.random()
        colour = _mix(base, fg if b > 0.25 else accent, 0.35 + 0.65 * b)
        c.point(x, y, colour)
        if b > 0.94:                       # halo around a few bright stars
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                c.point(x + dx, y + dy, _mix(base, colour, 0.45))


def _orb(c: Canvas, pal, rnd) -> None:
    """Large soft circle near the horizon (mando-sand, luna-mono, eclipse)."""
    dark, base = _rgb(pal["BG_DARK"]), _rgb(pal["BG"])
    accent = _rgb(pal["ACCENT"])
    c.vertical_gradient(_shade(dark, -0.3), base)
    # The orb is deliberately small, high and faint: the wallpaper should not compete
    # with the UI, it should be a disc in the background as in the source.
    cx, cy = c.w * 0.5, c.h * 0.44
    radius = min(c.w, c.h) * 0.24
    halo = radius * 2.4
    x0, x1 = max(0, int(cx - halo)), min(c.w, int(cx + halo))
    y0, y1 = max(0, int(cy - halo)), min(c.h, int(cy + halo))
    core = _mix(accent, (255, 255, 255), 0.15)
    for y in range(y0, y1):
        for x in range(x0, x1):
            d = math.hypot(x - cx, y - cy)
            if d > halo:
                continue
            i3 = (y * c.w + x) * 3
            under = (c.buf[i3], c.buf[i3 + 1], c.buf[i3 + 2])
            if d <= radius:
                t = 1 - (d / radius) ** 2
                c.buf[i3:i3 + 3] = bytes(_mix(under, core, 0.30 + 0.22 * t))
            else:
                t = 1 - (d - radius) / (halo - radius)
                c.buf[i3:i3 + 3] = bytes(_mix(under, accent, 0.18 * t * t))


def _mist(c: Canvas, pal, rnd) -> None:
    """Misty hill silhouettes + slanted rain (ashen-rain, aqua-split).

    A plain gradient looked nothing like the source; the source has overlapping hill
    silhouettes that get lighter with distance, and thin slanted rain streaks.
    """
    dark, base = _rgb(pal["BG_DARK"]), _rgb(pal["BG"])
    surface, fg = _rgb(pal["SURFACE"]), _rgb(pal["FG"])
    c.vertical_gradient(_shade(base, 0.18), _shade(base, -0.05))

    # Four hill layers from far to near; nearer ones are darker.
    for i in range(4):
        t = i / 3
        colour = _mix(_mix(base, surface, 0.35), _shade(dark, -0.15), t)
        mid = c.h * (0.42 + 0.17 * t)
        amp = c.h * (0.05 + 0.03 * t)
        freq = 0.8 + 0.9 * i
        phase = rnd.uniform(0, math.tau)
        for x in range(c.w):
            u = x / c.w
            y0 = int(mid + amp * math.sin(u * math.tau * freq + phase)
                     + amp * 0.4 * math.sin(u * math.tau * freq * 2.7 + phase))
            for y in range(max(0, y0), c.h):
                i3 = (y * c.w + x) * 3
                c.buf[i3:i3 + 3] = bytes(colour)

    # Slanted rain: sparse, low contrast.
    for _ in range(int(c.w * 0.6)):
        x, y = rnd.randrange(c.w), rnd.randrange(c.h)
        length = rnd.randint(8, int(c.h * 0.045))
        for k in range(length):
            xx, yy = x + k // 3, y + k
            if yy >= c.h:
                break
            i3 = (yy * c.w + (xx % c.w)) * 3
            under = (c.buf[i3], c.buf[i3 + 1], c.buf[i3 + 2])
            c.buf[i3:i3 + 3] = bytes(_mix(under, fg, 0.10))


def _grid(c: Canvas, pal, rnd) -> None:
    """Technical grid + scanlines (cybr-neon, nerv-magi, doom-rip)."""
    dark, base = _rgb(pal["BG_DARK"]), _rgb(pal["BG"])
    accent = _rgb(pal["ACCENT"])
    c.vertical_gradient(_shade(dark, -0.2), _shade(base, 0.05))
    # A glow that fades outward from the center
    for y in range(c.h):
        d = abs(y - c.h * 0.5) / (c.h * 0.5)
        row = _mix(_shade(base, 0.05), _shade(dark, -0.2), d)
        c.row(y, _mix(row, accent, 0.10 * (1 - d) ** 2))
    step = max(24, c.w // 48)
    line = _mix(_shade(dark, -0.05), accent, 0.18)
    for x in range(0, c.w, step):
        for y in range(c.h):
            c.point(x, y, line)
    for y in range(0, c.h, step):
        c.span(y, 0, c.w, line)
    for y in range(0, c.h, 3):            # scanlines
        i0 = y * c.w * 3
        row = tuple(c.buf[i0:i0 + 3])
        c.row(y, _shade(row, -0.10))


def _paper(c: Canvas, pal, rnd) -> None:
    """Flat background with light grain (lamp-paper, paper-mono, blanc-mono)."""
    base, dark = _rgb(pal["BG"]), _rgb(pal["BG_DARK"])
    c.vertical_gradient(_shade(base, 0.04), dark)
    grain = _rgb(pal["SUBTEXT"])
    for _ in range(int(c.w * c.h / 90)):
        x, y = rnd.randrange(c.w), rnd.randrange(c.h)
        i3 = (y * c.w + x) * 3
        under = (c.buf[i3], c.buf[i3 + 1], c.buf[i3 + 2])
        c.buf[i3:i3 + 3] = bytes(_mix(under, grain, rnd.uniform(0.03, 0.10)))


def _solid(c: Canvas, pal, rnd) -> None:
    """Solid color + corner vignette (void-lilac, persona-teal, nothing-mono)."""
    base = _rgb(pal["BG"])
    cx, cy = c.w / 2, c.h / 2
    far = math.hypot(cx, cy)
    for y in range(c.h):
        # The vignette also varies horizontally, so a few spans per row are enough
        segments = 48
        for s in range(segments):
            x0 = s * c.w // segments
            x1 = (s + 1) * c.w // segments
            xm = (x0 + x1) / 2
            d = math.hypot(xm - cx, y - cy) / far
            c.span(y, x0, x1, _shade(base, -0.22 * d * d))


def _dunes(c: Canvas, pal, rnd) -> None:
    """Diagonal soft bands (dune-grey, miasma-khaki, sophos-ukiyo)."""
    dark, base = _rgb(pal["BG_DARK"]), _rgb(pal["BG"])
    accent = _rgb(pal["ACCENT"])
    c.vertical_gradient(_shade(dark, -0.2), _shade(base, 0.06))
    bands = 6
    for i in range(bands):
        t = (i + 1) / bands
        colour = _mix(_shade(dark, -0.1), _mix(base, accent, 0.3), t)
        slope = rnd.uniform(0.18, 0.42) * (1 if i % 2 else -1)
        offset = c.h * (0.28 + 0.66 * t)
        for x in range(c.w):
            y0 = int(offset + slope * (x - c.w / 2)
                     + c.h * 0.03 * math.sin(x / c.w * math.tau * 1.4 + i))
            for y in range(max(0, y0), c.h):
                i3 = (y * c.w + x) * 3
                c.buf[i3:i3 + 3] = bytes(colour)


_RENDERERS = {"waves": _waves, "stars": _stars, "orb": _orb, "mist": _mist,
              "grid": _grid, "paper": _paper, "solid": _solid, "dunes": _dunes}


# --------------------------------------------------------------- api -----
def generate(theme: str, style: str, out: Path,
             size: tuple[int, int] = DEFAULT_SIZE,
             overrides: str = "") -> Path:
    """Generates a wallpaper for a theme + pattern and returns its path."""
    if style not in _RENDERERS:
        raise ValueError(f"unknown pattern: {style} "
                         f"(valid: {', '.join(sorted(STYLES))})")
    palette = themes.resolve(theme, overrides)
    canvas = Canvas(*size)
    # The seed derives from the theme name: the same theme gives the same image on
    # every run, and different themes get different wave/star layouts.
    _RENDERERS[style](canvas, palette, random.Random(theme))
    return write_png(Path(out), canvas.w, canvas.h, canvas.buf)
