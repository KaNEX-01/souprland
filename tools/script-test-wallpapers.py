#!/usr/bin/env python3
"""Renders the wallpapers of the Script Test profiles (wallpapers/st-*.png).

The images in the reference screenshots belong to other people; here we draw
our own images with the same mood:

    st-yaprak    dark green, overlapping leaves (with depth of field)
    st-gunbatimi a blurry red sun on a black background
    st-kizil     red background, black sunburst
    st-gecegolu  pixel-art night lake: stars, mountains, reflection, a boat
    st-neon      synthwave: banded sun, neon city, perspective grid
    st-sakura    pastel sky, cherry branches, drifting petals
    st-okyanus   underwater: light shafts, caustic pattern, bubbles
    st-kagit     misty ink mountains on sepia paper, a red sun
    st-orman     autumn: layered pine silhouettes, orange mist
    st-kutup     aurora curtains, snowy mountains, stars
    st-crt       green phosphor screen: lines of code, scanlines
    st-cam       frosted glass: blurry color blobs, grain

  adapted from temaornek/ references:
    st-sepya     beige sky, turquoise oil-paint sea (horizontal brush strokes)
    st-vadi      lush green mountain slopes, clouds, a road on the slope
    st-metro     Soviet-punk poster: red background, mustard star, halftone
    st-manga     white page: vertical Japanese text, ensō ring, screentone
    st-lavanta   navy room, lavender neon tubes and their reflections
    st-nane      mint-cyan shards of broken glass, slanted stripes
    st-ay        starry sky, cratered full moon
    st-siyah     charcoal black, faint diagonal light, grain
    st-limon     black background, lime-green comic panels
    st-alacakaranlik  purple-orange clouds, snowy peak, pines, lake reflection
    st-galaksi   pixel-art spiral galaxies
    st-zirve     black-and-white misty snowy peak
    st-karadelik swirling dust cloud, event horizon, thin bright ring
    st-nerv      red grunge brush strokes, faint honeycomb grid
    st-kurbaga   bird's-eye pond, a frog on a lily pad, leaves, rain
    st-doom      rising flames, smoke, sparks
    st-mando     sunset: giant pale sun, clouds, rocks, embers

  personal:
    st-gozcu     green moon: charcoal mist, mountain layers, neon moon, glowing
                 river, pine forest, a sentinel on the cliff (static fallback
                 of Workshop 2363450232)
    st-kule      night line: navy mist, stars, receding power pylons with red
                 warning lights (static fallback of Wallpaper Engine "Dark
                 Transmission Tower" — the lock screen and palette come from
                 this image)

Usage:  python3 tools/script-test-wallpapers.py [--matched] [name ...]
Use --matched for the palette-matched desktop wallpapers in wallpapers/profile/.
Requirements: python-numpy, python-pillow (only this tool; not needed for installing).
Randomness uses a fixed seed: the same command gives the same image.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "wallpapers"
W, H = 2560, 1440


def _hex(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a, b, t: float):
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


# ---------------------------------------------------------------- yaprak ---
def _leaf(size: float, rot: float, cx: float, cy: float,
          slim: float = 1.0) -> list[tuple[float, float]]:
    """Heart-shaped (pothos) leaf: two round lobes at the base, a pointed tip."""
    pts = []
    for i in range(49):
        t = i / 48
        y = -1 + 2 * t                       # -1 tip .. 1 base
        # concave taper toward the tip, round lobe at the base
        width = (math.sin(math.pi * (t ** 0.8)) ** 0.9) * (0.36 + 0.34 * t) * slim
        pts.append((width, y - 0.18 * math.sin(math.pi * t) ** 6 * (t > 0.85)))
    shape = pts + [(-x, y) for x, y in reversed(pts)]
    c, s = math.cos(rot), math.sin(rot)
    return [(cx + size * (x * c - y * s), cy + size * (x * s + y * c)) for x, y in shape]


def yaprak(rng: np.random.Generator) -> Image.Image:
    base = Image.new("RGB", (W, H), _hex("050a05"))
    greens = [_hex(c) for c in ("2f6b2a", "3a7a33", "275c25", "44873a", "336d2e", "1f4d1f")]
    layers = (  # (count, size range, blur, brightness)
        (650, (60, 110), 5, 0.35),
        (520, (80, 140), 2, 0.6),
        (380, (100, 170), 0, 0.95),
    )
    for count, (lo, hi), blur, light in layers:
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw, sdraw = ImageDraw.Draw(layer), ImageDraw.Draw(shade)
        for _ in range(count):
            cx, cy = rng.uniform(-80, W + 80), rng.uniform(-80, H + 80)
            size = rng.uniform(lo, hi)
            rot = rng.uniform(-math.pi, math.pi)
            slim = rng.uniform(0.85, 1.1)
            colour = greens[rng.integers(len(greens))]
            colour = tuple(min(255, int(v * light * rng.uniform(0.8, 1.2))) for v in colour)
            c, s = math.cos(rot), math.sin(rot)

            def at(x, y):
                return (cx + size * (x * c - y * s), cy + size * (x * s + y * c))
            poly = _leaf(size, rot, cx, cy, slim)
            sdraw.polygon([(x + 8, y + 14) for x, y in poly], fill=(0, 0, 0, 170))
            # dark edge, interior lightens layer by layer: soft volume
            draw.polygon(poly, fill=_mix(colour, (0, 0, 0), 0.35) + (255,))
            for k, frac in enumerate((0.9, 0.75, 0.55)):
                inner = _leaf(size * frac, rot, *at(0, 0.06 * (k + 1)), slim)
                draw.polygon(inner, fill=_mix(colour, (200, 235, 170), 0.05 * k) + (255,))
            # glossy highlight: a thin light strip on one side of the midrib
            side = 1 if rng.random() < 0.5 else -1
            gloss = _mix(colour, (225, 245, 205), 0.45)
            draw.line([at(side * 0.1, 0.55), at(side * 0.18, 0.0), at(side * 0.08, -0.6)],
                      fill=gloss + (70,), width=max(2, int(size / 14)), joint="curve")
            vein = _mix(colour, (20, 40, 15), 0.5)
            draw.line([at(0, 0.95), at(0, -0.9)], fill=vein + (220,), width=max(2, int(size / 40)))
            for k in range(4):
                y0 = 0.55 - k * 0.38
                for sd in (-1, 1):
                    draw.line([at(0, y0), at(sd * 0.3 * slim, y0 - 0.3)],
                              fill=vein + (120,), width=max(1, int(size / 90)))
        shade = shade.filter(ImageFilter.GaussianBlur(12))
        base.paste(shade, (0, 0), shade)
        layer = layer.filter(ImageFilter.GaussianBlur(blur or 0.8))
        base.paste(layer, (0, 0), layer)
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    vignette = np.clip(1.05 - 0.3 * d ** 2, 0.5, 1.0)[..., None]
    arr = np.asarray(base, dtype=np.float32) * vignette
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


# ------------------------------------------------------------- gunbatimi ---
def gunbatimi(rng: np.random.Generator) -> Image.Image:
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    top, mid = np.array(_hex("f0b49a"), np.float32), np.array(_hex("e2563a"), np.float32)
    t = np.clip(yy / (H * 0.7), 0, 1)[..., None]
    sky = top * (1 - t) + mid * t
    # giant red sun: bottom center, misty edges
    cx, cy, r = W * 0.5, H * 0.66, H * 0.62
    d = np.sqrt((xx - cx) ** 2 + ((yy - cy) * 1.05) ** 2) / r
    sun = np.array(_hex("ff2a12"), np.float32)
    glow = np.clip(1.25 - d, 0, 1)[..., None] ** 1.4
    img = sky * (1 - glow) + sun * glow
    # core is a darker red-orange
    core = np.clip(0.9 - d, 0, 1)[..., None] ** 2
    img = img * (1 - core * 0.5) + np.array(_hex("ff4a1c"), np.float32) * core * 0.5
    disc = np.clip((0.70 - d) / 0.075, 0, 1)[..., None] * 0.72
    img = img * (1 - disc) + np.array(_hex("ff9057"), np.float32) * disc
    # faint purple-blue haze top left
    haze = np.exp(-(((xx - W * 0.05) / (W * 0.25)) ** 2 + ((yy - H * 0.08) / (H * 0.3)) ** 2))
    img = img * (1 - 0.35 * haze[..., None]) + np.array(_hex("8a4a7a"), np.float32) * 0.35 * haze[..., None]
    # black ground at the bottom (horizon)
    ground = np.clip((yy - H * 0.8) / (H * 0.05), 0, 1)[..., None]
    img = img * (1 - ground) + np.array(_hex("050101"), np.float32) * ground
    # cloudy shadow fading to black at the left and right edges
    edge = np.clip((np.abs(xx - cx) / (W * 0.5) - 0.55) / 0.45, 0, 1)[..., None] * \
        np.clip((yy - H * 0.35) / (H * 0.4), 0, 1)[..., None]
    img = img * (1 - edge * 0.85)
    out = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    out = out.filter(ImageFilter.GaussianBlur(28))
    noise = rng.normal(0, 3.0, (H, W, 1)).astype(np.float32)
    arr = np.asarray(out, np.float32) + noise
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


# ----------------------------------------------------------------- kizil ---
def kizil(rng: np.random.Generator) -> Image.Image:
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    red = np.array(_hex("c4101c"), np.float32)
    dark = np.array(_hex("0a0203"), np.float32)
    cx, cy = W * 0.36, H * 0.24
    angle = np.arctan2(yy - cy, xx - cx)
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    # rays of irregular width
    rays = np.zeros_like(angle)
    count = 46
    widths = rng.uniform(0.15, 0.55, count)
    offsets = rng.uniform(0, 2 * math.pi, count)
    for w, o in zip(widths, offsets):
        delta = np.angle(np.exp(1j * (angle - o)))
        rays = np.maximum(rays, (np.abs(delta) < w * 2 * math.pi / count / 2).astype(np.float32))
    rays *= np.clip((dist - H * 0.12) / (H * 0.2), 0, 1)       # empty center
    img = red * (1 - rays[..., None]) + dark * rays[..., None]
    # black disc in the center (eclipse) and a thin red ring
    ring = np.abs(dist - H * 0.105) < 4
    img[dist < H * 0.1] = dark
    img[ring] = np.array(_hex("ff3b3b"), np.float32)
    # corner fading to black at the bottom right
    corner = np.clip(((xx / W) + (yy / H) - 1.25) / 0.6, 0, 1)[..., None]
    img = img * (1 - corner * 0.9)
    # halftone-like texture
    dots = (np.sin(xx * 0.9) * np.sin(yy * 0.9) > 0.92)[..., None]
    img = np.where(dots, img * 0.82, img)
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


# ------------------------------------------------------------- gecegolu ---
PW, PH = 640, 360            # pixel canvas; scaled up ×4


def _ridge(rng, base: float, peaks: int, height: tuple[int, int]) -> np.ndarray:
    """Jagged mountain silhouette: envelope of random triangular peaks + roughness."""
    x = np.arange(PW, dtype=np.float32)
    ridge = np.full(PW, base, np.float32)
    for _ in range(peaks):
        px = rng.uniform(-60, PW + 60)
        ph = rng.uniform(*height)
        slope = rng.uniform(0.55, 1.1)
        ridge = np.minimum(ridge, base - ph + np.abs(x - px) * slope)
    ridge += np.cumsum(rng.integers(-1, 2, PW)) * 0.15        # rocky roughness
    return np.clip(ridge, 0, base)


def gecegolu(rng: np.random.Generator) -> Image.Image:
    img = np.zeros((PH, PW, 3), np.float32)
    horizon = int(PH * 0.6)
    sky_cols = [_hex(c) for c in ("1b1035", "2a1650", "3b1f66", "55307a", "7a4790", "b06aa8")]
    # sky: gradient banded with ordered (Bayer 4×4) dithering
    bayer = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16
    for y in range(horizon):
        t = (y / horizon) ** 1.6 * (len(sky_cols) - 1)
        for x in range(PW):
            k = min(len(sky_cols) - 2, int(t))
            frac = t - k
            img[y, x] = sky_cols[k + 1] if frac > bayer[y % 4, x % 4] else sky_cols[k]
    # milky way: low-resolution noise clouds in a diagonal belt
    coarse = rng.random((horizon // 12 + 2, PW // 12 + 2))
    noise = np.asarray(Image.fromarray((coarse * 255).astype(np.uint8)).resize(
        (PW, horizon), Image.BICUBIC), np.float32)[:horizon] / 255
    yy, xx = np.mgrid[0:horizon, 0:PW]
    band = np.exp(-((yy - (150 - xx * 0.16)) / 55.0) ** 2)
    cloud = band * noise
    cloud = (cloud > 0.42) * 0.22 + (cloud > 0.62) * 0.2
    img[:horizon] = img[:horizon] * (1 - cloud[..., None]) + np.array(_hex("8a6ab0")) * cloud[..., None]
    # stars: single pixels + bright plus-shaped ones
    for _ in range(420):
        x, y = rng.integers(0, PW), rng.integers(0, horizon - 40)
        img[y, x] = _mix(_hex("d8c8f0"), (255, 255, 255), rng.uniform(0, 1))
    for _ in range(26):
        x, y = rng.integers(3, PW - 3), rng.integers(3, horizon - 60)
        c = np.array(_hex("f0e0ff"))
        img[y, x] = c
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            img[y + dy, x + dx] = c * 0.75
    # shooting star
    for i in range(34):
        x, y = 92 + i, 8 + int(i * 1.4)
        a = i / 34
        img[y, x] = _mix(_hex("6a80d0"), _hex("e0f0ff"), a)
        if i > 26:
            img[y + 1, x] = img[y, x - 1] = _hex("e0f0ff")
    # mountain layers: darker from back to front
    layers = ((horizon - 10, 7, (50, 95), "3d2560"), (horizon - 4, 9, (25, 70), "2b1a46"),
              (horizon, 6, (10, 40), "1c1130"))
    for base, peaks, height, colour in layers:
        ridge = _ridge(rng, base, peaks, height)
        for x in range(PW):
            top = int(max(10, ridge[x]))
            img[top:horizon, x] = _hex(colour)
    # pine trees on the shore
    def pine(x0: int, ground: int, height: int, colour) -> None:
        for dy in range(height):
            half = int((dy / height) * height * 0.28) + (1 if dy % 4 == 3 else 0)
            y = ground - height + dy
            img[y, max(0, x0 - half):min(PW, x0 + half + 1)] = colour
    for x in list(range(4, 150, 7)) + list(range(470, 636, 6)):
        pine(x + int(rng.integers(-2, 3)), horizon + 2, int(rng.integers(16, 40)), _hex("140c20"))
    # lit houses on the right shore
    for hx in (395, 404, 414, 426, 436, 448):
        hy = horizon - 2
        img[hy - 6:hy, hx:hx + 7] = _hex("1a0f26")
        img[hy - 4:hy - 2, hx + 2:hx + 4] = _hex("ffc860")
        img[hy - 8:hy - 6, hx + 1:hx + 6] = _hex("1a0f26")
    for hx in (34, 46, 58):
        img[horizon - 8:horizon - 2, hx:hx + 7] = _hex("1a0f26")
        img[horizon - 6:horizon - 4, hx + 2:hx + 4] = _hex("ffc860")
    # lake: reflection of the upper part, darkened and wavy
    lake = img[:horizon][::-1].copy()
    depth = PH - horizon
    reflect = np.zeros((depth, PW, 3), np.float32)
    for y in range(depth):
        shift = int(round(math.sin(y * 0.9) * (1 + y / 40)))
        src = lake[min(y, horizon - 1)]
        reflect[y] = np.roll(src, shift, axis=0) * (0.55 - 0.25 * y / depth)
        if y % 5 == 2:                                  # glinting wave lines
            reflect[y] *= 1.12
    img[horizon:] = reflect + np.array(_hex("120a24")) * 0.35
    # boat and lantern
    bx, by = 380, horizon + 70
    for dy in range(9):
        inset = dy * 2
        img[by + dy, bx - 42 + inset:bx + 42 - inset] = _hex("1c1118")
    img[by - 1, bx - 44:bx + 44] = _hex("3a2630")
    for px in (bx - 6, bx + 8):
        img[by - 14:by, px - 4:px + 4] = _hex("1a1430")          # two people sitting
        img[by - 19:by - 14, px - 3:px + 3] = _hex("1a1430")
    fy, fx = by - 6, bx - 26
    img[fy - 4:fy + 1, fx - 2:fx + 3] = _hex("ffd27a")
    glow = np.exp(-(((np.arange(PW) - fx) / 14.0) ** 2))[None, :] * \
        np.exp(-(((np.arange(PH) - fy) / 10.0) ** 2))[:, None]
    img += glow[..., None] * np.array([90, 60, 20])
    # pier (bottom left)
    for dy in range(26):
        y = PH - 26 + dy
        img[y, 0:110 - dy] = _hex("2a1a22") if dy % 6 else _hex("1a1016")
    # scale up (nearest neighbor: keep pixels crisp)
    small = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    return small.resize((W, H), Image.NEAREST)


# ------------------------------------------------------- shared helpers ---
def _grid():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    return yy, xx


def _vgrad(stops: list[tuple[float, str]]) -> np.ndarray:
    """Vertical gradient: [(0..1 position, color), ...]"""
    t = np.linspace(0, 1, H, dtype=np.float32)
    pos = [p for p, _ in stops]
    out = np.zeros((H, 3), np.float32)
    for c in range(3):
        out[:, c] = np.interp(t, pos, [_hex(col)[c] for _, col in stops])
    return np.repeat(out[:, None, :], W, axis=1)


def _noise(rng, scale: int, octaves: int = 4) -> np.ndarray:
    """Multi-octave soft noise (0..1), full size."""
    total = np.zeros((H, W), np.float32)
    amp, norm = 1.0, 0.0
    for o in range(octaves):
        step = max(2, scale // (2 ** o))
        small = rng.random((H // step + 2, W // step + 2)).astype(np.float32)
        layer = np.asarray(Image.fromarray((small * 255).astype(np.uint8)).resize(
            (W, H), Image.BICUBIC), np.float32) / 255
        total += layer * amp
        norm += amp
        amp *= 0.5
    return total / norm


def _img(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def _ridge_full(rng, base: float, amp: float, rough: float = 0.5) -> np.ndarray:
    """Soft mountain line at full resolution (y for each x)."""
    x = np.arange(W, dtype=np.float32)
    y = np.full(W, base, np.float32)
    freq, a = 1.5, amp
    for _ in range(6):
        phase = rng.uniform(0, 2 * math.pi)
        y -= a * (0.5 + 0.5 * np.sin(x / W * 2 * math.pi * freq + phase))
        freq *= 2.1
        a *= rough
    return y


# ---------------------------------------------------------------- neon ----
def neon(rng: np.random.Generator) -> Image.Image:
    yy, xx = _grid()
    horizon = H * 0.62
    img = _vgrad([(0, "07040f"), (0.35, "1b0a3a"), (0.6, "5a1067"), (0.62, "ff3fb4"),
                  (0.63, "12061f"), (1, "05030a")])
    # sun: gradient disc cut by horizontal bands
    cx, cy, r = W * 0.5, horizon - H * 0.17, H * 0.24
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    sun = (d < r) & (yy < horizon)
    band = ((yy - (cy - r * 0.1)) / (r * 0.9))
    cut = (band > 0) & (np.mod(yy, 26) < 5 + band * 12)
    sun &= ~cut
    t = np.clip((yy - (cy - r)) / (2 * r), 0, 1)[..., None]
    sun_col = np.array(_hex("ffe14d"), np.float32) * (1 - t) + np.array(_hex("ff2bd6"), np.float32) * t
    img = np.where(sun[..., None], sun_col, img)
    glow = np.exp(-((d - r) / (r * 0.35)) ** 2) * (yy < horizon) * 0.35
    img += glow[..., None] * np.array(_hex("ff2bd6"), np.float32)
    # city silhouette
    x = 0
    while x < W:
        bw = int(rng.integers(40, 140))
        bh = int(rng.integers(60, 260))
        top = int(horizon - bh)
        img[top:int(horizon), x:x + bw] = _hex("0c0618")
        for wy in range(top + 10, int(horizon) - 8, 18):
            for wx in range(x + 8, x + bw - 8, 16):
                if rng.random() < 0.35:
                    img[wy:wy + 6, wx:wx + 6] = _hex("00e5ff" if rng.random() < 0.6 else "ff2bd6")
        x += bw + int(rng.integers(0, 12))
    # perspective grid floor
    below = yy > horizon
    depth = (yy - horizon) / (H - horizon + 1)
    rows = np.abs(np.sin(1.0 / (depth + 0.03) * 3.0)) < 0.06
    cols = np.abs(np.mod((xx - W / 2) / (depth + 0.02) / 90, 1.0) - 0.5) > 0.47
    lines = below & (rows | cols)
    img = np.where(lines[..., None], np.array(_hex("ff2bd6"), np.float32) * (0.4 + depth[..., None]), img)
    return _img(img).filter(ImageFilter.GaussianBlur(0.8))


# -------------------------------------------------------------- sakura ----
def sakura(rng: np.random.Generator) -> Image.Image:
    img = _vgrad([(0, "f6d9e4"), (0.5, "fbeef2"), (1, "e9e2f4")])
    base = _img(img)
    draw = ImageDraw.Draw(base, "RGBA")
    # branch coming in from the top left
    def branch(x, y, angle, length, width, depth):
        if depth == 0 or length < 12:
            return
        x2 = x + math.cos(angle) * length
        y2 = y + math.sin(angle) * length
        draw.line([(x, y), (x2, y2)], fill=(86, 52, 60, 255), width=int(width))
        for _ in range(int(rng.integers(1, 3))):
            branch(x2, y2, angle + rng.uniform(-0.6, 0.6), length * rng.uniform(0.6, 0.8),
                   max(2, width * 0.7), depth - 1)
        if depth < 4:
            for _ in range(int(rng.integers(8, 16))):
                bx, by = x2 + rng.uniform(-45, 45), y2 + rng.uniform(-45, 45)
                rr = rng.uniform(9, 18)
                col = (int(rng.uniform(235, 255)), int(rng.uniform(150, 190)),
                       int(rng.uniform(185, 210)), 235)
                draw.ellipse([bx - rr, by - rr, bx + rr, by + rr], fill=col)
                draw.ellipse([bx - 3, by - 3, bx + 3, by + 3], fill=(200, 90, 120, 255))
    branch(-40, 160, 0.2, 520, 46, 8)
    branch(W + 40, 90, math.pi - 0.3, 480, 40, 8)
    branch(W * 0.2, -40, 1.25, 300, 24, 6)
    # drifting petals
    for _ in range(260):
        px, py = rng.uniform(0, W), rng.uniform(0, H)
        rr = rng.uniform(4, 11)
        rot = rng.uniform(0, math.pi)
        pts = [(px + rr * math.cos(rot + a) * (1 if i % 2 else 0.45),
                py + rr * math.sin(rot + a) * (1 if i % 2 else 0.45))
               for i, a in enumerate(np.linspace(0, 2 * math.pi, 9)[:-1])]
        draw.polygon(pts, fill=(245, int(rng.uniform(160, 200)), 205, int(rng.uniform(120, 220))))
    return base.filter(ImageFilter.GaussianBlur(0.6))


# ------------------------------------------------------------- okyanus ----
def okyanus(rng: np.random.Generator) -> Image.Image:
    yy, xx = _grid()
    img = _vgrad([(0, "1d6b8f"), (0.25, "0f3f62"), (0.7, "081f36"), (1, "040c18")])
    # light shafts coming down from the water surface
    rays = np.zeros((H, W), np.float32)
    for _ in range(14):
        x0 = rng.uniform(0, W)
        slope = rng.uniform(-0.35, 0.15)
        width = rng.uniform(20, 90)
        cx = x0 + yy * slope
        rays += np.exp(-((xx - cx) / width) ** 2) * rng.uniform(0.15, 0.4)
    rays *= np.clip(1 - yy / (H * 0.85), 0, 1) ** 1.5
    img += rays[..., None] * np.array([120, 220, 230], np.float32)
    # caustic pattern on top
    caustic = np.abs(np.sin(xx * 0.03 + _noise(rng, 160) * 9) * np.sin(yy * 0.05 + _noise(rng, 120) * 7))
    img += ((caustic > 0.92) * np.clip(1 - yy / (H * 0.35), 0, 1))[..., None] * 60
    out = _img(img).filter(ImageFilter.GaussianBlur(2))
    draw = ImageDraw.Draw(out, "RGBA")
    # bubbles
    for _ in range(120):
        bx, by = rng.uniform(0, W), rng.uniform(H * 0.2, H)
        rr = rng.uniform(2, 9)
        draw.ellipse([bx - rr, by - rr, bx + rr, by + rr], outline=(190, 240, 255, 150), width=2)
    # rocks / seaweed silhouette at the bottom
    ridge = _ridge_full(rng, H * 0.97, H * 0.16, 0.45)
    arr = np.asarray(out, np.float32).copy()
    arr[yy > ridge[None, :]] = _hex("03101c")
    return _img(arr)


# --------------------------------------------------------------- kagit ----
def kagit(rng: np.random.Generator) -> Image.Image:
    yy, xx = _grid()
    paper = np.array(_hex("efe6d2"), np.float32)
    img = np.ones((H, W, 3), np.float32) * paper
    img *= (0.94 + 0.08 * _noise(rng, 40, 5))[..., None]
    # ink mountains in mist layers (darker from far to near)
    ink = np.array(_hex("2a2622"), np.float32)
    for i, (base, amp, alpha) in enumerate(((0.62, 0.30, 0.22), (0.74, 0.24, 0.38),
                                            (0.86, 0.20, 0.6), (0.98, 0.14, 0.85))):
        ridge = _ridge_full(rng, H * base, H * amp, 0.5)
        below = yy > ridge[None, :]
        fade = np.clip(1 - (yy - ridge[None, :]) / (H * 0.18), 0.15, 1)   # mist toward the bottom
        mask = (below * fade * alpha)[..., None]
        img = img * (1 - mask) + ink * mask
    # red sun (seal)
    cx, cy, r = W * 0.7, H * 0.28, H * 0.09
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    sun = np.clip((r - d) / 3, 0, 1)[..., None] * (0.85 + 0.15 * _noise(rng, 12, 2))[..., None]
    img = img * (1 - sun) + np.array(_hex("b03a2b"), np.float32) * sun
    out = _img(img).filter(ImageFilter.GaussianBlur(1.2))
    # a few birds
    draw = ImageDraw.Draw(out)
    for _ in range(5):
        bx, by, sz = rng.uniform(W * 0.2, W * 0.5), rng.uniform(H * 0.15, H * 0.35), rng.uniform(8, 16)
        draw.line([(bx - sz, by - sz * 0.4), (bx, by), (bx + sz, by - sz * 0.4)],
                  fill=(43, 38, 34), width=3)
    return out


# --------------------------------------------------------------- orman ----
def orman(rng: np.random.Generator) -> Image.Image:
    yy, xx = _grid()
    img = _vgrad([(0, "f4b860"), (0.35, "e07b39"), (0.7, "7a3420"), (1, "2a140c")])
    sun_d = np.sqrt((xx - W * 0.62) ** 2 + (yy - H * 0.42) ** 2)
    img += (np.exp(-(sun_d / (H * 0.25)) ** 2) * 90)[..., None] * np.array([1, 0.8, 0.5])
    layers = (("b8642f", 0.55, 50), ("8a4523", 0.66, 70), ("5c2c18", 0.78, 95),
              ("33180e", 0.92, 130))
    for colour, base, tall in layers:
        mask = np.zeros((H, W), bool)
        ground = _ridge_full(rng, H * base, H * 0.04, 0.5)
        mask |= yy > ground[None, :]
        x = -20
        while x < W + 20:
            h = rng.uniform(tall * 0.7, tall * 1.6) * (H / 1440)
            w = h * rng.uniform(0.22, 0.32)
            gx = int(np.clip(x, 0, W - 1))
            top = ground[gx] - h
            tri = (yy > top) & (yy < ground[gx] + 5) & \
                  (np.abs(xx - x) < (yy - top) / h * w)
            mask |= tri
            x += rng.uniform(w * 0.6, w * 1.4)
        col = np.array(_hex(colour), np.float32)
        img = np.where(mask[..., None], col, img)
        # mist between layers
        img = img * 0.92 + np.array(_hex("f0a060"), np.float32) * 0.08 * (yy < H * base)[..., None]
    # falling leaves
    out = _img(img)
    draw = ImageDraw.Draw(out, "RGBA")
    for _ in range(140):
        lx, ly, rr = rng.uniform(0, W), rng.uniform(0, H), rng.uniform(3, 8)
        draw.ellipse([lx - rr, ly - rr * 0.5, lx + rr, ly + rr * 0.5],
                     fill=(int(rng.uniform(200, 250)), int(rng.uniform(90, 150)), 40, 200))
    return out


# --------------------------------------------------------------- kutup ----
def kutup(rng: np.random.Generator) -> Image.Image:
    yy, xx = _grid()
    img = _vgrad([(0, "050a16"), (0.45, "0e1b30"), (0.7, "1a2c46"), (1, "0b1220")])
    stars = (rng.random((H, W)) > 0.9994) & (yy < H * 0.6)
    img[stars] = 225
    # aurora: soft winding bands; fade upward with vertical rays
    x = xx[0]
    for colour, base, amp, freq, height in (("7fe3b4", 0.30, 0.07, 1.1, 0.16),
                                            ("86c4e8", 0.22, 0.05, 1.7, 0.10),
                                            ("b58cf0", 0.38, 0.04, 0.8, 0.08)):
        phase = rng.uniform(0, 2 * math.pi)
        center = H * base + H * amp * np.sin(x / W * 2 * math.pi * freq + phase)
        dist = yy - center[None, :]
        below = np.exp(-np.clip(dist, 0, None) / (H * 0.012))      # sharp bottom edge
        above = np.exp(-np.clip(-dist, 0, None) / (H * height))   # long fade upward
        curtain = np.where(dist > 0, below, above)
        # irregular rays: random brightness every 25-60 px, smoothed
        knots = np.arange(0, W + 60, 38, dtype=np.float32)
        rays = np.interp(x, knots, rng.uniform(0.15, 1.0, len(knots)))
        rays = (0.35 + 0.65 * rays)[None, :]
        img += (curtain * rays * 0.6)[..., None] * np.array(_hex(colour), np.float32)
    img = np.asarray(_img(img).filter(ImageFilter.GaussianBlur(6)), np.float32).copy()
    # mountains: low, snow-capped
    for colour, base, amp in (("2b3b57", 0.80, 0.16), ("18233a", 0.90, 0.10)):
        ridge = _ridge_full(rng, H * base, H * amp, 0.45)
        below = yy > ridge[None, :]
        peak = ridge.min()
        snow = below & (yy < ridge[None, :] + H * 0.02) & (ridge[None, :] < peak + H * amp * 0.45)
        img = np.where(below[..., None], np.array(_hex(colour), np.float32), img)
        img = np.where(snow[..., None], np.array(_hex("cfdcec"), np.float32), img)
    return _img(img).filter(ImageFilter.GaussianBlur(0.8))


# ----------------------------------------------------------------- crt ----
def crt(rng: np.random.Generator) -> Image.Image:
    yy, xx = _grid()
    img = np.zeros((H, W, 3), np.float32)
    # random "code" lines: clusters of short bright rectangles
    out = _img(img)
    draw = ImageDraw.Draw(out)
    y = 60
    while y < H - 60:
        x = 80 + int(rng.integers(0, 6)) * 28
        for _ in range(int(rng.integers(3, 14))):
            w = int(rng.integers(2, 9)) * 14
            if rng.random() < 0.85:
                shade = int(rng.uniform(40, 120))
                draw.rectangle([x, y, x + w, y + 14], fill=(0, shade, int(shade * 0.45)))
            x += w + 14
            if x > W - 200:
                break
        y += 30
    # big logo box in the middle
    draw.rectangle([W * 0.35, H * 0.38, W * 0.65, H * 0.62], outline=(65, 255, 122), width=6)
    draw.rectangle([W * 0.35 + 18, H * 0.38 + 18, W * 0.65 - 18, H * 0.62 - 18],
                   outline=(31, 154, 69), width=2)
    for i in range(6):
        draw.rectangle([W * 0.39, H * 0.43 + i * 40, W * 0.39 + rng.integers(200, 560),
                        H * 0.43 + i * 40 + 18], fill=(65, 255, 122) if i == 0 else (31, 154, 69))
    arr = np.asarray(out.filter(ImageFilter.GaussianBlur(1.5)), np.float32)
    arr += np.asarray(out.filter(ImageFilter.GaussianBlur(14)), np.float32) * 0.8   # glow
    arr *= (0.75 + 0.25 * (np.mod(yy, 4) < 2))[..., None]                         # scanlines
    d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    arr *= np.clip(1.15 - 0.45 * d ** 2, 0, 1)[..., None]                          # vignette
    arr += np.array([2, 10, 4], np.float32)
    return _img(arr)


# ----------------------------------------------------------------- cam ----
def cam(rng: np.random.Generator) -> Image.Image:
    yy, xx = _grid()
    img = np.ones((H, W, 3), np.float32) * np.array(_hex("140f2a"), np.float32)
    blobs = (("7b4dff", 0.25, 0.30, 0.42), ("ff6ac1", 0.75, 0.25, 0.35),
             ("2ec5ff", 0.65, 0.80, 0.40), ("ffb86b", 0.15, 0.85, 0.28),
             ("a78bfa", 0.5, 0.5, 0.3))
    for colour, bx, by, r in blobs:
        d = np.sqrt(((xx - W * bx) / W) ** 2 + ((yy - H * by) / H) ** 2)
        w = np.exp(-(d / r) ** 2)[..., None]
        img = img * (1 - w * 0.75) + np.array(_hex(colour), np.float32) * w * 0.75
    out = _img(img).filter(ImageFilter.GaussianBlur(40))
    # thin light refraction lines and grain
    arr = np.asarray(out, np.float32)
    arr += (np.sin((xx + yy * 0.6) * 0.004) * 6)[..., None]
    arr += rng.normal(0, 4, (H, W, 1)).astype(np.float32)
    return _img(arr)


# ====================================================== third party ======
# Wallpapers of the profiles adapted from the references under temaornek/.
# The images in the references (anime characters, photos) belong to other
# people; here only the same MOOD is given with our own drawing.

def _streaks(rng, sy: int, sx: int) -> np.ndarray:
    """Horizontally stretched (brush-stroke-like) noise, 0..1."""
    small = rng.random((max(2, H // sy), max(2, W // sx))).astype(np.float32)
    big = Image.fromarray((small * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)
    return np.asarray(big, np.float32) / 255


def _font(spec: str, size: int):
    import subprocess
    from PIL import ImageFont
    try:
        path = subprocess.run(["fc-match", "-f", "%{file}", spec], capture_output=True,
                              text=True, check=True).stdout.strip()
        return ImageFont.truetype(path, size)
    except Exception:  # noqa: BLE001 — default font if none is found
        return ImageFont.load_default()


def _blend(img: np.ndarray, colour, mask: np.ndarray) -> np.ndarray:
    m = np.clip(mask, 0, 1)[..., None]
    return img * (1 - m) + np.array(_hex(colour) if isinstance(colour, str) else colour,
                                    np.float32) * m


# --------------------------------------------------------------- sepya ----
def sepya(rng):
    """Beige sky, turquoise oil-paint sea: horizontal brush strokes."""
    yy, _ = _grid()
    t = yy / H
    sky = _vgrad([(0, "e6dcc0"), (0.45, "ddd0ae"), (1, "c9b98f")])
    stroke = _streaks(rng, 6, 90) * 0.6 + _streaks(rng, 3, 40) * 0.4
    # sea band: shore lines ripple with the brush
    top = 0.40 + (stroke - 0.5) * 0.18
    bottom = 0.86 + (stroke - 0.5) * 0.12
    sea = np.clip((t - top) * 14, 0, 1) * np.clip((bottom - t) * 10, 0, 1)
    sea_col = _vgrad([(0, "6fb2ae"), (0.5, "3e8f8f"), (1, "2a6f72")])
    img = sky * (1 - sea[..., None]) + sea_col * sea[..., None]
    # light foam and dark depth strokes
    foam = (_streaks(rng, 4, 70) > 0.72) * sea
    img = _blend(img, "e8e0c4", foam * 0.55)
    deep = (_streaks(rng, 5, 60) < 0.28) * sea
    img = _blend(img, "24585c", deep * 0.5)
    # brush marks in the sky too
    img += ((stroke - 0.5) * 22)[..., None]
    # canvas texture
    img += (rng.normal(0, 5, (H, W)).astype(np.float32))[..., None]
    return _img(img).filter(ImageFilter.GaussianBlur(1.2))


# ---------------------------------------------------------------- vadi ----
def vadi(rng):
    """Lush green mountain slopes, a cloud top right, soft depth of field."""
    yy, xx = _grid()
    img = _vgrad([(0, "7fa9c9"), (0.25, "b6cfd8"), (0.45, "c9d6c4"), (1, "2f5a2a")])
    cloud = _noise(rng, 220, 5)
    cmask = np.clip((cloud - 0.5) * 6, 0, 1) * np.clip(1 - yy / (H * 0.35), 0, 1) \
        * np.clip((xx - W * 0.55) / (W * 0.2), 0, 1)
    img = _blend(img, "f4f6f2", cmask)
    layers = (("9fb98a", 0.40, 0.12, 0.45), ("6f9a5a", 0.50, 0.18, 0.55),
              ("4f7f3d", 0.58, 0.20, 0.6), ("3a6a2c", 0.78, 0.22, 0.65),
              ("2a5520", 0.97, 0.2, 0.7))
    for i, (colour, base, amp, rough) in enumerate(layers):
        ridge = _ridge_full(rng, H * base, H * amp, rough)
        below = (yy > ridge[None, :]).astype(np.float32)
        canopy = _noise(rng, 18 + 10 * i, 3)
        col = np.array(_hex(colour), np.float32)
        shade = (0.75 + 0.5 * canopy)[..., None]
        light = np.array([1.06, 1.08, 0.9], np.float32) * np.clip(1 - (yy - ridge[None, :]) / (H * 0.4), 0.7, 1)[..., None]
        img = img * (1 - below[..., None]) + (col * shade * light) * below[..., None]
    # light mist on the valley floor
    mist = np.exp(-((yy - H * 0.66) / (H * 0.07)) ** 2) * (0.25 + 0.2 * _noise(rng, 120, 3))
    img = _blend(img, "dfe8dc", mist)
    out = _img(img).filter(ImageFilter.GaussianBlur(3))
    arr = np.asarray(out, np.float32) * 0.92 + 10
    return _img(arr)


# --------------------------------------------------------------- metro ----
def metro(rng):
    """Soviet-punk poster: blood-red background, mustard star, rays, halftone."""
    yy, xx = _grid()
    red, dark, mustard = _hex("7a2b27"), _hex("3d1514"), _hex("e0c66a")
    img = np.ones((H, W, 3), np.float32) * np.array(red, np.float32)
    cx, cy = W * 0.72, H * 0.46
    ang = np.arctan2(yy - cy, xx - cx)
    rays = (np.mod(ang / (2 * math.pi) * 28, 1) < 0.5)
    img = _blend(img, dark, rays * 0.35)
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    # halftone dots: shrink with distance from the center
    cell = 22
    gx, gy = np.mod(xx, cell) - cell / 2, np.mod(yy, cell) - cell / 2
    radius = np.clip(1 - d / (H * 0.95), 0, 1) * cell * 0.48
    dots = np.sqrt(gx ** 2 + gy ** 2) < radius
    img = _blend(img, mustard, dots * 0.55 * (xx > W * 0.35))
    out = _img(img)
    draw = ImageDraw.Draw(out)
    # star
    R, r = H * 0.30, H * 0.12
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rad = R if i % 2 == 0 else r
        pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    draw.polygon(pts, fill=mustard)
    inner = [(cx + (x - cx) * 0.78, cy + (y - cy) * 0.78) for x, y in pts]
    draw.polygon(inner, fill=_hex("5a1d1b"))
    inner2 = [(cx + (x - cx) * 0.62, cy + (y - cy) * 0.62) for x, y in pts]
    draw.polygon(inner2, fill=mustard)
    # stencil stripes and frame
    for i in range(5):
        y0 = H * 0.78 + i * 38
        draw.rectangle([W * 0.06, y0, W * 0.06 + W * (0.12 + 0.05 * (i % 3)), y0 + 18], fill=mustard)
    draw.rectangle([30, 30, W - 30, H - 30], outline=mustard, width=6)
    arr = np.asarray(out, np.float32)
    grunge = _noise(rng, 6, 3)
    arr = arr * (0.82 + 0.25 * grunge)[..., None]
    arr += rng.normal(0, 6, (H, W, 1)).astype(np.float32)
    return _img(arr)


# --------------------------------------------------------------- manga ----
def manga(rng):
    """White manga page: vertical Japanese text, ensō brush ring, screentone."""
    yy, xx = _grid()
    img = np.ones((H, W, 3), np.float32) * 252
    # screentone (dot grid) at the bottom right, diagonal density
    cell = 12
    gx, gy = np.mod(xx + yy * 0.5, cell) - cell / 2, np.mod(yy, cell) - cell / 2
    density = np.clip(((xx / W) + (yy / H) - 1.1) * 1.6, 0, 1)
    tone = np.sqrt(gx ** 2 + gy ** 2) < density * cell * 0.42
    img = _blend(img, "202020", tone * 0.85)
    out = _img(img)
    draw = ImageDraw.Draw(out)
    # ensō: an open brush ring of wavering thickness
    cx, cy, R = W * 0.68, H * 0.48, H * 0.30
    start = rng.uniform(0, 2 * math.pi)
    steps = 900
    for i in range(steps):
        t = i / steps
        a = start + t * 2 * math.pi * 0.92
        w = 34 * (math.sin(t * math.pi) ** 0.6) * (0.75 + 0.25 * math.sin(t * 23)) + 4
        x = cx + R * math.cos(a) * (1 + 0.03 * math.sin(t * 7))
        y = cy + R * math.sin(a)
        draw.ellipse([x - w, y - w, x + w, y + w], fill=(24, 24, 24))
    # dry brush fibers
    for i in range(160):
        a = start + rng.uniform(0.85, 0.95) * 2 * math.pi
        rr = R + rng.uniform(-30, 30)
        x, y = cx + rr * math.cos(a), cy + rr * math.sin(a)
        draw.line([(x, y), (x + rng.uniform(-60, 10), y + rng.uniform(-10, 40))],
                  fill=(40, 40, 40), width=1)
    # vertical text: shadowed, two columns
    font = _font("Noto Serif CJK JP", 92)
    cols = (("静かな午後に", W * 0.27, H * 0.22), ("月を待つふたり", W * 0.18, H * 0.38))
    for text, x, y0 in cols:
        for i, ch in enumerate(text):
            yc = y0 + i * 108
            draw.text((x + 6, yc + 6), ch, font=font, fill=(185, 185, 185))
            draw.text((x, yc), ch, font=font, fill=(20, 20, 20))
    # red seal
    sx, sy = W * 0.27 + 12, H * 0.22 + 6 * 108 + 40
    draw.rectangle([sx, sy, sx + 70, sy + 70], fill=(192, 57, 43))
    small = _font("Noto Serif CJK JP", 46)
    draw.text((sx + 12, sy + 6), "静", font=small, fill=(252, 252, 252))
    return out.filter(ImageFilter.GaussianBlur(0.5))


# ------------------------------------------------------------- lavanta ----
def lavanta(rng):
    """Night-navy room, lavender neon tubes and their reflections on the floor."""
    yy, xx = _grid()
    img = _vgrad([(0, "141522"), (0.7, "1a1b2b"), (1, "0e0f18")])
    floor = H * 0.80
    tubes = ((0.26, 0.30, 0.70), (0.74, 0.29, 0.68), (0.44, 0.18, 0.62), (0.58, 0.22, 0.60))
    glow = np.zeros((H, W), np.float32)
    core = np.zeros((H, W), np.float32)
    for x0, top, bot in tubes:
        x0 *= W
        inside = (yy > H * top) & (yy < H * bot)
        dx = np.abs(xx - x0)
        core = np.maximum(core, (dx < 11) * inside)
        vert = np.clip(np.minimum(yy - H * top, H * bot - yy) / 60 + 1, 0, 1)
        glow += np.exp(-(dx / 120) ** 2) * vert * 0.9
        # reflection on the floor
        refl = (yy > floor) * np.exp(-((yy - floor) / 160)) * np.exp(-(dx / 60) ** 2)
        glow += refl * 0.5
    img += glow[..., None] * np.array(_hex("a98be0"), np.float32) * 0.55
    img = _blend(img, "f4ecff", core)
    # floor line and vignette
    img = _blend(img, "2a2a40", np.exp(-((yy - floor) / 2) ** 2) * 0.8)
    d = np.sqrt(((xx - W / 2) / W) ** 2 + ((yy - H / 2) / H) ** 2)
    img *= np.clip(1.2 - d * 1.1, 0.35, 1)[..., None]
    img += rng.normal(0, 2.5, (H, W, 1)).astype(np.float32)
    return _img(img).filter(ImageFilter.GaussianBlur(1.5))


# ---------------------------------------------------------------- nane ----
def nane(rng):
    """Persona mood: mint-cyan background, diagonal cracks, slanted stripes."""
    yy, xx = _grid()
    img = _vgrad([(0, "2ee6b4"), (1, "17b896")])
    img += (np.sin((xx + yy) / 260) * 8)[..., None]
    out = _img(img)
    draw = ImageDraw.Draw(out, "RGBA")
    # big ring
    cx, cy, R = W * 0.58, H * 0.42, H * 0.46
    draw.ellipse([cx - R, cy - R, cx + R, cy + R], outline=(10, 80, 66, 120), width=34)
    draw.ellipse([cx - R * 0.72, cy - R * 0.72, cx + R * 0.72, cy + R * 0.72],
                 outline=(230, 255, 248, 90), width=6)
    # broken glass shards
    for _ in range(26):
        x, y = rng.uniform(-100, W), rng.uniform(-100, H)
        size = rng.uniform(80, 380)
        pts = [(x, y), (x + size * rng.uniform(0.3, 1.2), y + size * rng.uniform(-0.3, 0.4)),
               (x + size * rng.uniform(-0.2, 0.6), y + size * rng.uniform(0.5, 1.3))]
        shade = rng.choice([(8, 70, 58, 150), (12, 95, 80, 110), (220, 255, 245, 70),
                            (40, 245, 200, 120)])
        draw.polygon(pts, fill=tuple(int(c) for c in shade))
    # slanted white stripes
    for i in range(7):
        x0 = rng.uniform(-200, W)
        w = rng.uniform(6, 40)
        draw.polygon([(x0, 0), (x0 + w, 0), (x0 + w - H * 0.55, H), (x0 - H * 0.55, H)],
                     fill=(235, 255, 250, int(rng.uniform(30, 90))))
    # small triangles
    for _ in range(40):
        x, y, s = rng.uniform(0, W), rng.uniform(0, H), rng.uniform(8, 28)
        draw.polygon([(x, y - s), (x + s * 0.8, y + s * 0.6), (x - s * 0.8, y + s * 0.6)],
                     fill=(6, 50, 42, 170))
    return out.filter(ImageFilter.GaussianBlur(0.8))


# ------------------------------------------------------------------ ay ----
def ay(rng):
    """Starry black sky, cratered full moon; lower-right half in shadow."""
    yy, xx = _grid()
    img = np.zeros((H, W, 3), np.float32) + 6
    star = rng.random((H, W))
    img[star > 0.9993] = 200
    img[star > 0.99985] = 255
    cx, cy, R = W * 0.5, H * 0.5, H * 0.33
    dx, dy = (xx - cx) / R, (yy - cy) / R
    r2 = dx ** 2 + dy ** 2
    disk = r2 < 1
    nz = np.sqrt(np.clip(1 - r2, 0, 1))
    # light from the top left; the night side is still visible (earthshine)
    light = np.clip(-0.55 * dx - 0.45 * dy + 0.7 * nz, 0, 1)
    light = 0.18 + 0.82 * light
    maria = _noise(rng, 260, 4)
    surface = 150 + 70 * _noise(rng, 30, 4) - 80 * np.clip((maria - 0.5) * 4, 0, 1)
    # craters
    for _ in range(140):
        a, rr = rng.uniform(0, 2 * math.pi), math.sqrt(rng.random()) * 0.95
        kx, ky = cx + R * rr * math.cos(a), cy + R * rr * math.sin(a)
        kr = R * rng.uniform(0.008, 0.06)
        d = np.sqrt((xx - kx) ** 2 + (yy - ky) ** 2) / kr
        surface += (np.exp(-((d - 1) / 0.12) ** 2) * 35 - (d < 1) * 18) * (d < 2)
    moon = (surface * light)[..., None] * np.array([1.0, 1.0, 1.03], np.float32)
    edge = np.clip((1 - np.sqrt(r2)) * R / 2, 0, 1)[..., None]
    img = img * (1 - edge) + moon * edge
    halo = np.exp(-np.clip(np.sqrt(r2) - 1, 0, None) * 6) * (~disk) * 45
    img += halo[..., None]
    return _img(img).filter(ImageFilter.GaussianBlur(0.7))


# --------------------------------------------------------------- siyah ----
def siyah(rng):
    """Charcoal black, faint light slanting in from the left, film grain."""
    yy, xx = _grid()
    base = 16 + 10 * np.clip(1 - np.abs((xx - W * 0.45) - (yy - H * 0.2) * 0.6) / (W * 0.35), 0, 1) ** 2
    base += 6 * np.exp(-((xx - W * 0.5) ** 2 + (yy - H * 0.55) ** 2) / (2 * (W * 0.18) ** 2))
    img = np.repeat(base[..., None], 3, axis=2)
    img += rng.normal(0, 2.2, (H, W, 1)).astype(np.float32)
    return _img(img).filter(ImageFilter.GaussianBlur(0.6))


# --------------------------------------------------------------- limon ----
def limon(rng):
    """Pitch-black background, lime-green comic panels in the middle."""
    yy, xx = _grid()
    img = np.zeros((H, W, 3), np.float32)
    # faint sound-wave bars at the bottom
    out = _img(img)
    draw = ImageDraw.Draw(out)
    for i, x in enumerate(range(int(W * 0.2), int(W * 0.8), 14)):
        h = abs(math.sin(i * 0.37) * math.sin(i * 0.11)) * 70 + rng.uniform(0, 25)
        draw.rectangle([x, H - 10 - h, x + 6, H - 10], fill=(46, 48, 42))
    lime, ink, paper = _hex("c8f43c"), (12, 12, 12), (236, 238, 228)
    x0, y0, x1, y1 = W * 0.27, H * 0.37, W * 0.73, H * 0.64
    pw = (x1 - x0) / 3
    for p in range(3):
        px0, px1 = x0 + p * pw + 6, x0 + (p + 1) * pw - 6
        panel = Image.new("RGB", (int(px1 - px0), int(y1 - y0)), paper)
        pd = ImageDraw.Draw(panel)
        w, h = panel.size
        # halftone lime gradient
        for gy in range(0, h, 10):
            for gx in range(0, w, 10):
                k = ((gx / w) * (1 if p != 1 else -1) + gy / h) * 0.5 + (0.5 if p == 1 else 0)
                r = max(0, k) * 5
                if r > 0.6:
                    pd.ellipse([gx - r, gy - r, gx + r, gy + r], fill=lime)
        # big shapes: circle, star, speed lines
        cx, cy = w * rng.uniform(0.35, 0.65), h * rng.uniform(0.35, 0.6)
        if p == 0:
            pd.ellipse([cx - 90, cy - 90, cx + 90, cy + 90], fill=lime, outline=ink, width=6)
            for a in np.linspace(0, 2 * math.pi, 30):
                pd.line([(cx + 110 * math.cos(a), cy + 110 * math.sin(a)),
                         (cx + 260 * math.cos(a), cy + 260 * math.sin(a))], fill=ink, width=2)
        elif p == 1:
            pts = []
            for i in range(10):
                a = -math.pi / 2 + i * math.pi / 5
                rr = 120 if i % 2 == 0 else 50
                pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
            pd.polygon(pts, fill=lime, outline=ink)
            pd.line(pts + [pts[0]], fill=ink, width=6)
        else:
            for i in range(9):
                yv = h * 0.15 + i * h * 0.09
                pd.line([(w * 0.1, yv), (w * 0.9, yv + rng.uniform(-30, 30))], fill=ink, width=5)
            pd.ellipse([cx - 60, cy - 60, cx + 60, cy + 60], fill=ink)
            pd.ellipse([cx - 25, cy - 25, cx + 25, cy + 25], fill=lime)
        pd.rectangle([0, 0, w - 1, h - 1], outline=ink, width=8)
        out.paste(panel, (int(px0), int(y0)))
    return out


# ------------------------------------------------------- alacakaranlik ----
def alacakaranlik(rng):
    """Purple-orange clouds, snowy blue peak, pine silhouettes, lake reflection."""
    yy, xx = _grid()
    horizon = H * 0.72
    sky = _vgrad([(0, "2b2a4a"), (0.25, "4b3b6a"), (0.45, "8a5a7a"), (0.62, "c27a5a"), (0.72, "6a5a6a"), (1, "1a1a22")])
    cloud = _noise(rng, 200, 5)
    glow = np.exp(-(((xx - W * 0.56) / (W * 0.25)) ** 2 + ((yy - H * 0.42) / (H * 0.15)) ** 2))
    cmask = np.clip((cloud - 0.42) * 4, 0, 1) * (yy < H * 0.62)
    img = sky * (1 - cmask[..., None] * 0.5) + (np.array(_hex("f28a4a"), np.float32) * glow[..., None]
                                                + np.array(_hex("5a4a7a"), np.float32) * (1 - glow[..., None])) * cmask[..., None] * 0.5
    img += (glow * 60)[..., None] * np.array([1, 0.5, 0.25], np.float32)
    # mountain: central peak, blue rocks, snow
    x = xx[0]
    peak = H * 0.40 + np.abs(x - W * 0.48) * 0.55 + _ridge_full(rng, 0, H * 0.04, 0.6) * -1
    peak = np.minimum(peak, horizon)
    mountain = (yy > peak[None, :]) & (yy < horizon)
    rock = _noise(rng, 12, 3)
    mcol = np.where((rock > 0.55)[..., None], np.array(_hex("d8dde8"), np.float32),
                    np.array(_hex("3a4a6a"), np.float32))
    img = np.where(mountain[..., None], mcol * (0.6 + 0.4 * np.clip(1 - (yy - peak[None, :]) / (H * 0.3), 0, 1))[..., None], img)
    # pine forest: tall on both sides, low in the middle
    mask = np.zeros((H, W), bool)
    px = -10
    while px < W + 10:
        edge = abs(px - W / 2) / (W / 2)
        hgt = rng.uniform(0.08, 0.14) * H + edge ** 2 * H * 0.42
        wid = hgt * rng.uniform(0.16, 0.24)
        top = horizon - hgt
        tri = (yy > top) & (yy < horizon + 2) & (np.abs(xx - px) < (yy - top) / hgt * wid)
        mask |= tri
        px += rng.uniform(wid * 0.5, wid * 1.1)
    img = np.where(mask[..., None], np.array(_hex("0d1512"), np.float32), img)
    # lake: reflection of the upper half, rippled and darkened
    below = yy > horizon
    ry = np.clip(2 * horizon - yy, 0, H - 1).astype(int)
    ripple = (np.sin(yy * 0.9 + _noise(rng, 30, 2) * 12) * 6).astype(int)
    rx = np.clip(xx.astype(int) + ripple, 0, W - 1)
    refl = img[ry, rx] * 0.55
    img = np.where(below[..., None], refl, img)
    img = _blend(img, "2a3a20", (np.abs(yy - horizon) < 6) * 1.0)
    return _img(img).filter(ImageFilter.GaussianBlur(1.0))


# ------------------------------------------------------------- galaksi ----
def galaksi(rng):
    """Pixel art: a big tilted spiral galaxy, a small second galaxy, stars."""
    s = 4
    h, w = H // s, W // s
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    pal = [_hex(c) for c in ("1d1b2e", "2c2944", "4a4566", "7c7499", "b9a7cc", "f2c6dc", "fff2f6")]

    def spiral(cx, cy, scale, tilt, rot, arms=2, wind=2.6):
        x, y = (xx - cx) / scale, (yy - cy) / scale
        c, sn = math.cos(rot), math.sin(rot)
        xr, yr = x * c - y * sn, (x * sn + y * c) / tilt
        r = np.sqrt(xr ** 2 + yr ** 2) + 1e-3
        th = np.arctan2(yr, xr)
        arm = 0.5 + 0.5 * np.cos(arms * (th - wind * np.log(r)))
        val = arm ** 2.2 * np.exp(-r * 1.4) * 1.6 + np.exp(-(r / 0.16) ** 2) * 1.4
        return val

    noise = rng.random((h, w)).astype(np.float32)
    v = spiral(w * 0.58, h * 0.5, w * 0.30, 0.45, -0.32) + spiral(w * 0.13, h * 0.2, w * 0.07, 0.8, 0.5, wind=3.0)
    v = v * (0.8 + 0.4 * noise)
    idx = np.clip((v * 6).astype(int), 0, len(pal) - 1)
    img = np.array(pal, np.float32)[idx]
    stars = rng.random((h, w))
    img[stars > 0.996] = _hex("e6dcf2")
    img[stars > 0.9993] = _hex("f2b6d6")
    out = _img(img).resize((W, H), Image.NEAREST)
    draw = ImageDraw.Draw(out)
    for _ in range(14):                                  # sparkles (plus-shaped)
        x, y = int(rng.uniform(0, w)) * s, int(rng.uniform(0, h)) * s
        col = tuple(rng.choice([(180, 240, 255), (255, 230, 200), (242, 182, 214)]))
        for k in range(-3, 4):
            a = s if abs(k) < 3 else s
            draw.rectangle([x + k * s, y, x + k * s + a - 1, y + s - 1], fill=col)
            draw.rectangle([x, y + k * s, x + s - 1, y + k * s + a - 1], fill=col)
    # comet
    x, y = W * 0.86, H * 0.66
    for k in range(18):
        draw.rectangle([x - k * s * 2, y + k * s * 0.5, x - k * s * 2 + s * 2, y + k * s * 0.5 + s],
                       fill=(170, 210, 230) if k else (255, 255, 255))
    return out


# --------------------------------------------------------------- zirve ----
def zirve(rng):
    """Black and white: misty gray sky, a single snowy peak, dark forest below."""
    yy, xx = _grid()
    img = _vgrad([(0, "d9d9d9"), (0.5, "e6e6e6"), (1, "cfcfcf")])
    x = xx[0]
    ridge = np.abs(x - W * 0.52) ** 1.05 * 0.62 - _ridge_full(rng, 0, H * 0.05, 0.6)
    ridge = ridge - ridge.min() + H * 0.30
    below = yy > ridge[None, :]
    # snow + rock: gullies running down the slope
    gully = _streaks(rng, 50, 8)                               # stretched vertically
    gully = np.asarray(Image.fromarray((gully * 255).astype(np.uint8)).transpose(Image.FLIP_LEFT_RIGHT), np.float32) / 255
    detail = _noise(rng, 10, 3)
    rockiness = np.clip((gully * 0.6 + detail * 0.6 - 0.55) * 4, 0, 1)
    depth = np.clip((yy - ridge[None, :]) / (H * 0.45), 0, 1)
    snow = 238 - 150 * rockiness * (0.4 + depth) - 40 * depth
    img = np.where(below[..., None], snow[..., None], img)
    # forest at the bottom
    forest = _ridge_full(rng, H * 0.92, H * 0.08, 0.7)
    trees = yy > forest[None, :] - (_noise(rng, 6, 2) * 30)
    img = np.where(trees[..., None], (40 + 25 * detail)[..., None], img)
    # mist
    fog = np.clip(1 - np.abs(yy - H * 0.85) / (H * 0.12), 0, 1) * 0.25
    img = img * (1 - fog[..., None]) + 220 * fog[..., None]
    return _img(img).filter(ImageFilter.GaussianBlur(1.0))


# ----------------------------------------------------------- karadelik ----
def karadelik(rng):
    """Swirling dust cloud, pitch-black event horizon and a thin bright cream ring."""
    yy, xx = _grid()
    cx, cy = W * 0.5, H * 0.42
    dx, dy = xx - cx, yy - cy
    r = np.sqrt(dx ** 2 + dy ** 2)
    th = np.arctan2(dy, dx)
    R = H * 0.20
    # polar noise: the swirl increases inward
    tb, rb = 2048, 512
    small = rng.random((48, 96)).astype(np.float32)
    polar = np.asarray(Image.fromarray((small * 255).astype(np.uint8)).resize((tb, rb), Image.BICUBIC), np.float32) / 255
    small2 = rng.random((160, 320)).astype(np.float32)
    polar = polar * 0.65 + np.asarray(Image.fromarray((small2 * 255).astype(np.uint8)).resize((tb, rb), Image.BICUBIC), np.float32) / 255 * 0.35
    rmax = math.hypot(W, H) * 0.6
    ri = np.clip(r / rmax * (rb - 1), 0, rb - 1).astype(int)
    swirl = th + 2.2 * R / (r + 40)
    ti = (np.mod(swirl / (2 * math.pi), 1) * (tb - 1)).astype(int)
    dust = polar[ri, ti]
    fall = np.exp(-np.clip(r - R, 0, None) / (H * 0.38))
    cloud = np.clip(dust * 1.6 - 0.45, 0, 1) * fall
    img = cloud[..., None] * np.array([205, 195, 182], np.float32)
    ring = np.exp(-((r - R) / 5.5) ** 2) * 255 + np.exp(-((r - R) / 30) ** 2) * 90
    img += ring[..., None] * np.array([1.0, 0.96, 0.88], np.float32)
    img = np.where((r < R - 3)[..., None], 0, img)
    img += rng.normal(0, 2, (H, W, 1)).astype(np.float32)
    return _img(img).filter(ImageFilter.GaussianBlur(1.2))


# ---------------------------------------------------------------- nerv ----
def nerv(rng):
    """Red grunge: brush strokes, splatters, faint honeycomb grid."""
    yy, xx = _grid()
    img = np.ones((H, W, 3), np.float32) * np.array(_hex("3a1010"), np.float32)
    out = _img(img)
    for layer in range(3):
        over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(over)
        for _ in range(40):
            x, y = rng.uniform(-200, W + 200), rng.uniform(-200, H + 200)
            length, width = rng.uniform(300, 1100), rng.uniform(40, 180)
            a = rng.uniform(-0.9, -0.3)
            col = [(176, 32, 32), (122, 16, 16), (210, 58, 42), (20, 8, 8), (90, 10, 14)][int(rng.integers(0, 5))]
            pts = []
            for k in range(12):
                t = k / 11
                off = math.sin(t * math.pi) * width * rng.uniform(0.7, 1.0)
                pts.append((x + math.cos(a) * length * t - math.sin(a) * off,
                            y + math.sin(a) * length * t + math.cos(a) * off))
            for k in range(11, -1, -1):
                t = k / 11
                off = -math.sin(t * math.pi) * width * rng.uniform(0.2, 0.5)
                pts.append((x + math.cos(a) * length * t - math.sin(a) * off,
                            y + math.sin(a) * length * t + math.cos(a) * off))
            draw.polygon(pts, fill=col + (int(rng.uniform(120, 220)),))
        out = Image.alpha_composite(out.convert("RGBA"), over.filter(ImageFilter.GaussianBlur(3 - layer)))
    arr = np.asarray(out.convert("RGB"), np.float32)
    # splatters
    spl = rng.random((H, W)) > 0.9985
    arr[spl] = _hex("d03a2a")
    # honeycomb grid (faint)
    size = 70
    qx = xx / (size * 1.5)
    qy = (yy - (np.floor(qx) % 2) * size * 0.866) / (size * 1.732)
    fx, fy = qx - np.floor(qx), qy - np.floor(qy)
    hexline = (np.minimum.reduce([fx, 1 - fx, np.abs(fy - 0.5) * 2]) < 0.03)
    arr = _blend(arr, "ff7262", hexline * 0.10)
    d = np.sqrt(((xx - W / 2) / W) ** 2 + ((yy - H / 2) / H) ** 2)
    arr *= np.clip(0.55 + d * 0.9, 0.55, 1.05)[..., None]          # darker in the middle
    arr *= (0.85 + 0.25 * _noise(rng, 5, 3))[..., None]
    return _img(arr)


# ------------------------------------------------------------- kurbaga ----
def kurbaga(rng):
    """Bird's-eye pond: turquoise water, a frog on a lily pad, leaves, rain."""
    yy, xx = _grid()
    n1, n2 = _noise(rng, 140, 5), _noise(rng, 50, 4)
    img = _vgrad([(0, "1f7a7e"), (1, "13595e")])
    swirl = np.sin(n1 * 22 + n2 * 6)
    img = _blend(img, "0d3f45", np.clip(swirl, 0, 1) * 0.55)
    img = _blend(img, "3fb3b0", np.clip(-swirl - 0.6, 0, 1) * 0.6)
    out = _img(img)
    draw = ImageDraw.Draw(out, "RGBA")
    # lily pad + ripples
    cx, cy, R = W * 0.53, H * 0.49, H * 0.09
    for k in range(3):
        rr = R * (1.35 + k * 0.3)
        draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(200, 240, 235, 60 - k * 15), width=4)
    draw.pieslice([cx - R, cy - R, cx + R, cy + R], start=20, end=360, fill=(46, 140, 70, 255))
    draw.pieslice([cx - R * 0.9, cy - R * 0.9, cx + R * 0.9, cy + R * 0.9], start=20, end=360,
                  fill=(60, 165, 84, 255))
    for a in np.linspace(math.radians(30), math.radians(350), 9):
        draw.line([(cx, cy), (cx + R * 0.85 * math.cos(a), cy + R * 0.85 * math.sin(a))],
                  fill=(40, 120, 62, 255), width=3)
    # frog (from above): body, legs, eyes
    fx, fy = cx - R * 0.15, cy - R * 0.05
    for sx in (-1, 1):
        draw.ellipse([fx + sx * 52 - 22, fy + 18, fx + sx * 52 + 22, fy + 58], fill=(150, 175, 60, 255))
        draw.ellipse([fx + sx * 40 - 16, fy - 46, fx + sx * 40 + 16, fy - 18], fill=(150, 175, 60, 255))
    draw.ellipse([fx - 50, fy - 55, fx + 50, fy + 50], fill=(178, 200, 72, 255))
    draw.ellipse([fx - 30, fy - 30, fx + 30, fy + 30], fill=(196, 214, 96, 255))
    for sx in (-1, 1):
        draw.ellipse([fx + sx * 26 - 13, fy - 62, fx + sx * 26 + 13, fy - 36], fill=(196, 214, 96, 255))
        draw.ellipse([fx + sx * 26 - 6, fy - 55, fx + sx * 26 + 6, fy - 43], fill=(20, 30, 20, 255))
    # leaf clusters in the corners
    greens = [(52, 120, 40), (70, 150, 52), (96, 178, 66), (40, 100, 36)]
    for (ox, oy, spread) in ((0, 0, 0.32), (W, H, 0.30), (W * 0.2, 0, 0.18)):
        for _ in range(140):
            px = ox + rng.normal(0, W * spread * 0.5)
            py = oy + rng.normal(0, H * spread * 0.6)
            size = rng.uniform(30, 70)
            pts = _leaf(size, rng.uniform(-math.pi, math.pi), px, py, 0.9)
            col = greens[int(rng.integers(0, 4))]
            draw.polygon(pts, fill=col + (255,), outline=(20, 50, 20, 255))
    # pink flowers
    for _ in range(30):
        px, py = rng.uniform(0, W * 0.4), rng.uniform(H * 0.5, H)
        draw.ellipse([px - 5, py - 5, px + 5, py + 5], fill=(230, 140, 170, 200))
    # rain streaks
    rain = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rain)
    for _ in range(260):
        px, py, ln = rng.uniform(0, W), rng.uniform(0, H), rng.uniform(30, 70)
        rd.line([(px, py), (px - ln * 0.6, py + ln)], fill=(220, 245, 245, 70), width=3)
    out = Image.alpha_composite(out.convert("RGBA"), rain.filter(ImageFilter.GaussianBlur(1)))
    return out.convert("RGB").filter(ImageFilter.GaussianBlur(0.8))


# ---------------------------------------------------------------- doom ----
def doom(rng):
    """Flames rising from an ember-black sky downward, smoke and sparks."""
    yy, xx = _grid()
    flame = _streaks(rng, 3, 3)                          # start isotropic
    tall = np.asarray(Image.fromarray((rng.random((H // 90, W // 18)) * 255).astype(np.uint8))
                      .resize((W, H), Image.BICUBIC), np.float32) / 255   # long vertical tongues
    t = yy / H
    heat = np.clip((t - 0.35) * 1.9 + (tall - 0.5) * 1.1 + (flame - 0.5) * 0.35, 0, 1.3)
    heat *= 0.85 + 0.3 * np.exp(-((xx - W * 0.5) / (W * 0.45)) ** 2)
    stops = [(0.0, "080302"), (0.25, "3a0a04"), (0.5, "9a1c06"), (0.75, "ff5a0a"),
             (0.95, "ffa13d"), (1.3, "ffe08a")]
    pos = [p for p, _ in stops]
    img = np.stack([np.interp(heat, pos, [_hex(c)[k] for _, c in stops]) for k in range(3)], -1)
    smoke = _noise(rng, 180, 4) * np.clip(1 - t * 1.6, 0, 1)
    img += (smoke * 28)[..., None] * np.array([1, 0.55, 0.4], np.float32)
    out = _img(img).filter(ImageFilter.GaussianBlur(2))
    glow = Image.new("RGB", (W, H))
    gd = ImageDraw.Draw(glow)
    for _ in range(320):
        px, py = rng.uniform(0, W), rng.uniform(0, H * 0.9)
        rr = rng.uniform(1.5, 4.5)
        col = (255, int(rng.uniform(120, 210)), 40)
        gd.ellipse([px - rr, py - rr, px + rr, py + rr], fill=col)
    arr = np.asarray(out, np.float32) + np.asarray(glow, np.float32) \
        + np.asarray(glow.filter(ImageFilter.GaussianBlur(8)), np.float32) * 1.5
    return _img(arr)


# --------------------------------------------------------------- mando ----
def mando(rng):
    """A pale giant sun in an orange sky, smoky clouds, rocky silhouette, embers."""
    yy, xx = _grid()
    img = _vgrad([(0, "2a4652"), (0.3, "5a6a68"), (0.55, "d88a4a"), (0.8, "e8a060"), (1, "4a2a20")])
    cx, cy, R = W * 0.52, H * 0.40, H * 0.27
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    img = _blend(img, "efd9a6", np.clip((R - d) / 3, 0, 1) * 0.92)
    img += (np.exp(-np.clip(d - R, 0, None) / (H * 0.12)) * 40)[..., None] * np.array([1, 0.8, 0.5], np.float32)
    # cloud layers: round clusters billowing from bottom to top
    for colour, base, scale, alpha in (("f0c890", 0.60, 160, 0.85), ("d9884a", 0.70, 120, 0.95),
                                       ("9a5636", 0.82, 90, 1.0), ("5a3226", 0.92, 70, 1.0)):
        n = _noise(rng, scale, 4)
        edge = H * base - (n - 0.5) * H * 0.35
        mask = np.clip((yy - edge) / 14, 0, 1) * alpha
        shade = (0.85 + 0.3 * _noise(rng, 40, 3))[..., None]
        img = img * (1 - mask[..., None]) + np.array(_hex(colour), np.float32) * shade * mask[..., None]
    # rocky foreground
    for side in (0, 1):
        ridge = _ridge_full(rng, H * 1.02, H * 0.10, 0.6)
        xs = xx / W if side == 0 else 1 - xx / W
        lift = np.clip(0.3 - xs, 0, 1) ** 1.3 * H * 0.9
        rock = yy > (ridge[None, :] - lift)
        img = np.where(rock[..., None], np.array(_hex("21171a"), np.float32), img)
    out = _img(img).filter(ImageFilter.GaussianBlur(1.2))
    draw = ImageDraw.Draw(out)
    for _ in range(160):                                     # flying embers
        px, py = rng.uniform(0, W), rng.uniform(0, H * 0.8)
        ln = rng.uniform(6, 26)
        draw.line([(px, py), (px + ln, py - ln * 0.45)], fill=(255, int(rng.uniform(110, 180)), 60),
                  width=int(rng.integers(2, 5)))
    return out


# ---------------------------------------------------------------- kule ----
def _tower(draw, cx: float, base: float, height: float, colour, lights: list) -> None:
    """Lattice power pylon silhouette: tapering body, three crossarms, cross bracing."""
    top = base - height
    half_base, half_top = height * 0.11, height * 0.025
    width = max(1, int(height / 160))

    def half(y: float) -> float:
        t = (base - y) / height
        return half_base + (half_top - half_base) * t ** 0.8
    # two legs + cross bracing
    draw.line([(cx - half_base, base), (cx - half_top, top)], fill=colour, width=width * 2)
    draw.line([(cx + half_base, base), (cx + half_top, top)], fill=colour, width=width * 2)
    steps = 14
    for k in range(steps):
        y0 = base - height * k / steps
        y1 = base - height * (k + 1) / steps
        draw.line([(cx - half(y0), y0), (cx + half(y1), y1)], fill=colour, width=width)
        draw.line([(cx + half(y0), y0), (cx - half(y1), y1)], fill=colour, width=width)
        draw.line([(cx - half(y1), y1), (cx + half(y1), y1)], fill=colour, width=width)
    # crossarms and the insulator strings at their ends
    for frac, arm in ((0.70, 0.30), (0.80, 0.26), (0.90, 0.21), (1.0, 0.12)):
        y = base - height * frac
        span = height * arm
        draw.polygon([(cx - span, y), (cx + span, y), (cx + half(y), y + height * 0.035),
                      (cx - half(y), y + height * 0.035)], outline=colour)
        draw.line([(cx - span, y), (cx + span, y)], fill=colour, width=width * 2)
        for side in (-1, 1):
            draw.line([(cx + side * span * 0.92, y), (cx + side * span * 0.92, y + height * 0.05)],
                      fill=colour, width=width)
        lights.append((cx - span, y))
        lights.append((cx + span, y))
    lights.append((cx, top - height * 0.01))
    lights.append((cx - half(base - height * 0.4), base - height * 0.4))
    lights.append((cx + half(base - height * 0.4), base - height * 0.4))


def kule(rng):
    """Night line: navy-black sky, low mist, stars, lattice pylons receding in
    perspective, sagging wires, red warning lights."""
    yy, xx = _grid()
    img = _vgrad([(0.0, "0b0f17"), (0.45, "151c29"), (0.80, "1d2533"), (0.88, "1a202b"),
                  (1.0, "07090d")])
    # cloud cover: wide, soft noise
    clouds = _noise(rng, 420, 5)
    img += ((clouds - 0.5) * 26)[..., None] * np.array([0.8, 0.9, 1.1], np.float32)
    # horizon mist
    fog = np.exp(-((yy - H * 0.86) / (H * 0.06)) ** 2) * (0.6 + 0.4 * _noise(rng, 200, 3))
    img += fog[..., None] * np.array([22, 26, 34], np.float32)
    out = _img(img)
    draw = ImageDraw.Draw(out)
    # stars: sparse, dim
    for _ in range(420):
        x, y = rng.uniform(0, W), rng.uniform(0, H * 0.75)
        b = int(rng.uniform(90, 220) * (1 - y / H))
        r = rng.choice([0.8, 1.2, 1.8], p=[0.7, 0.25, 0.05])
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(b, b, min(255, b + 20)))
    # pylons from far to near (the perspective line recedes toward center-right)
    lights: list[tuple[float, float, float]] = []
    horizon = H * 0.90
    vanish_x = W * 0.535
    towers = []
    for i in range(9):
        depth = 0.16 * (1.55 ** i)                 # 0.16 → near ~4.7
        scale = min(1.0, depth / 4.7)
        cx = vanish_x + (W * 0.63 - vanish_x) * scale
        height = H * 0.95 * scale
        base = horizon + (H * 0.995 - horizon) * scale
        towers.append((scale, cx, base, height))
    wires_prev = None
    for scale, cx, base, height in towers:
        shade = int(8 + 30 * (1 - scale))
        colour = (shade, shade + 4, shade + 10)
        pts: list = []
        _tower(draw, cx, base, height, colour, pts)
        lights.extend((x, y, scale) for x, y in pts)
        arms = [p for p in pts[:8]]
        if wires_prev is not None:
            for (x0, y0), (x1, y1) in zip(wires_prev, arms):
                sag = 18 + 120 * scale
                curve = [(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t + sag * 4 * t * (1 - t))
                         for t in np.linspace(0, 1, 40)]
                draw.line(curve, fill=colour, width=max(1, int(scale * 3)))
        wires_prev = arms
    # wires running out of frame from the nearest pylon
    for x0, y0 in wires_prev:
        x1, y1 = x0 + W * 0.5, y0 - H * 0.8
        curve = [(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t + 60 * 4 * t * (1 - t))
                 for t in np.linspace(0, 1, 40)]
        draw.line(curve, fill=(10, 13, 19), width=3)
    # red warning lights: the glow is blurred on a separate layer
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    for x, y, scale in lights:
        if rng.random() < 0.35:
            continue
        r = 2 + 6 * scale
        gdraw.ellipse([x - r * 3, y - r * 3, x + r * 3, y + r * 3], fill=(120, 14, 20))
        draw.ellipse([x - r * 0.5, y - r * 0.5, x + r * 0.5, y + r * 0.5], fill=(255, 70, 70))
    # distant town lights + a single green-red aircraft light in the sky
    for _ in range(26):
        x, y = rng.uniform(0, W), horizon + rng.uniform(-6, 10)
        gdraw.ellipse([x - 5, y - 3, x + 5, y + 3], fill=(70, 58, 40))
    ax, ay = W * 0.36, H * 0.69
    draw.ellipse([ax - 3, ay - 3, ax + 3, ay + 3], fill=(120, 255, 170))
    draw.ellipse([ax + 12, ay - 3, ax + 18, ay + 3], fill=(255, 90, 90))
    gdraw.ellipse([ax - 14, ay - 10, ax + 30, ay + 10], fill=(40, 60, 60))
    glow = glow.filter(ImageFilter.GaussianBlur(14))
    out = Image.fromarray(np.clip(np.asarray(out, np.float32) + np.asarray(glow, np.float32),
                                  0, 255).astype(np.uint8))
    # grain
    arr = np.asarray(out, np.float32) + rng.normal(0, 2.0, (H, W, 1)).astype(np.float32)
    return _img(arr)


def gozcu(rng):
    """Green moon: charcoal mist, layered mountain silhouettes, a neon mint
    moon half sunk into the horizon, glowing river meanders in the valley, a
    pine forest in front and a small sentinel silhouette on the left cliff."""
    yy, xx = _grid()
    img = _vgrad([(0.0, "1d1c1d"), (0.40, "2b2a2b"), (0.62, "2e2e2e"), (1.0, "141414")])
    img += ((_noise(rng, 380, 5) - 0.5) * 18)[..., None]
    moon_x, moon_y, moon_r = W * 0.50, H * 0.34, H * 0.13
    d = np.sqrt((xx - moon_x) ** 2 + (yy - moon_y) ** 2)
    img += (np.exp(-(np.maximum(d - moon_r, 0) / (H * 0.16)) ** 2) * 0.55)[..., None] \
        * np.array([20, 120, 80], np.float32)
    img = _blend(img, "1df5a4", (d < moon_r).astype(np.float32))
    img = _blend(img, "6dffc8", np.clip(1 - d / (moon_r * 0.9), 0, 1) * 0.35 * (d < moon_r))
    # mountain layers: from far (light gray) to near (dark)
    for base, amp, col, rough in ((0.60, 0.20, "353535", 0.45), (0.66, 0.14, "2a2a2a", 0.5),
                                  (0.74, 0.10, "202020", 0.5), (0.84, 0.08, "171717", 0.55)):
        ridge = _ridge_full(rng, H * base, H * amp, rough)
        img = _blend(img, col, (yy > ridge[None, :]).astype(np.float32))
    # river: horizontal meanders in the valley, glow on a separate layer
    out = _img(img)
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    draw = ImageDraw.Draw(out)
    for i in range(7):
        y = H * (0.69 + 0.035 * i) + rng.uniform(-8, 8)
        x0 = W * (0.38 + rng.uniform(-0.12, 0.10))
        length = W * rng.uniform(0.05, 0.16) * (1 + i * 0.25)
        pts = [(x0 + length * t, y + math.sin(t * 6 + i) * 10) for t in np.linspace(0, 1, 30)]
        width = int(4 + i * 3)
        gdraw.line(pts, fill=(8, 90, 60), width=width * 3)
        draw.line(pts, fill=(45, 240, 165), width=width)
    # river glow is composited BEFORE the trees; otherwise it spills over the forest
    glow = glow.filter(ImageFilter.GaussianBlur(12))
    out = Image.fromarray(np.clip(np.asarray(out, np.float32) + np.asarray(glow, np.float32),
                                  0, 255).astype(np.uint8))
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    draw = ImageDraw.Draw(out)
    # pine forest in front
    for layer, (base, size, shade) in enumerate(((0.80, 70, 22), (0.88, 110, 16), (0.97, 170, 11))):
        for _ in range(int(W / size * 1.6)):
            x = rng.uniform(-50, W + 50)
            h = size * rng.uniform(1.4, 2.6)
            yb = H * base + rng.uniform(-20, 30)
            draw.polygon([(x, yb - h), (x - h * 0.26, yb), (x + h * 0.26, yb)],
                         fill=(shade, shade, shade))
    # left cliff and the sentinel
    cliff = [(0, H * 0.42), (W * 0.17, H * 0.40), (W * 0.20, H * 0.47), (W * 0.18, H * 0.62),
             (W * 0.21, H * 0.80), (W * 0.16, H), (0, H)]
    draw.polygon(cliff, fill=(19, 19, 19))
    gx, gy = W * 0.14, H * 0.40
    draw.rectangle([gx - 9, gy - 70, gx + 9, gy - 18], fill=(14, 14, 14))
    draw.ellipse([gx - 9, gy - 92, gx + 9, gy - 72], fill=(14, 14, 14))
    draw.rectangle([gx - 26, gy - 66, gx - 8, gy - 30], fill=(14, 14, 14))
    draw.line([(gx - 4, gy - 18), (gx - 6, gy)], fill=(14, 14, 14), width=7)
    draw.line([(gx + 4, gy - 18), (gx + 6, gy)], fill=(14, 14, 14), width=7)
    # watchtower on the right hill + rising green smoke
    tx, ty = W * 0.84, H * 0.36
    draw.polygon([(W * 0.70, H), (W * 0.80, H * 0.40), (tx, ty), (W * 0.90, H * 0.42), (W, H * 0.55),
                  (W, H)], fill=(30, 30, 30))
    draw.rectangle([tx - 34, ty - 30, tx + 34, ty], fill=(20, 20, 20))
    for k in range(4):
        draw.rectangle([tx - 26 + k * 15, ty - 22, tx - 18 + k * 15, ty - 14], fill=(80, 255, 190))
    for t in np.linspace(0, 1, 120):
        sx = tx + math.sin(t * 7) * 30 * t + t * 20
        sy = ty - 40 - t * H * 0.30
        r = 6 + 10 * t
        gdraw.ellipse([sx - r * 2, sy - r * 2, sx + r * 2, sy + r * 2], fill=(6, 60, 40))
        draw.ellipse([sx - r * 0.6, sy - r * 0.6, sx + r * 0.6, sy + r * 0.6],
                     fill=(30, int(200 - 90 * t), int(140 - 60 * t)))
    # birds and flying ashes
    for _ in range(9):
        bx, by = moon_x + rng.uniform(-W * 0.12, W * 0.15), moon_y + rng.uniform(-H * 0.25, H * 0.02)
        s2 = rng.uniform(6, 12)
        draw.line([(bx - s2, by - s2 * 0.4), (bx, by), (bx + s2, by - s2 * 0.5)], fill=(18, 18, 18), width=3)
    for _ in range(40):
        ax, ay = rng.uniform(0, W), rng.uniform(0, H)
        draw.ellipse([ax - 2, ay - 2, ax + 2, ay + 2], fill=(110, 105, 100))
    glow = glow.filter(ImageFilter.GaussianBlur(18))
    out = Image.fromarray(np.clip(np.asarray(out, np.float32) + np.asarray(glow, np.float32),
                                  0, 255).astype(np.uint8))
    arr = np.asarray(out, np.float32) + rng.normal(0, 2.2, (H, W, 1)).astype(np.float32)
    return _img(arr)


MAKERS = {"st-yaprak": yaprak, "st-gunbatimi": gunbatimi,
          "st-kizil": kizil, "st-gecegolu": gecegolu,
          "st-neon": neon, "st-sakura": sakura, "st-okyanus": okyanus,
          "st-kagit": kagit, "st-orman": orman, "st-kutup": kutup,
          "st-crt": crt, "st-cam": cam,
          "st-sepya": sepya, "st-vadi": vadi, "st-metro": metro,
          "st-manga": manga, "st-lavanta": lavanta, "st-nane": nane,
          "st-ay": ay, "st-siyah": siyah, "st-limon": limon,
          "st-alacakaranlik": alacakaranlik, "st-galaksi": galaksi,
          "st-zirve": zirve, "st-karadelik": karadelik, "st-nerv": nerv,
          "st-kurbaga": kurbaga, "st-doom": doom, "st-mando": mando,
          "st-kule": kule, "st-gozcu": gozcu}


def main(names: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matched", action="store_true",
                        help="render the wallpaper using the profile's bar and palette")
    parser.add_argument("names", nargs="*", metavar="PROFILE")
    args = parser.parse_args(names)
    if args.matched:
        sys.path.insert(0, str(ROOT / "python"))
    for name in args.names or MAKERS:
        if name not in MAKERS:
            parser.error(f"unknown profile: {name}")
        seed = (2000 if args.matched else 1000) + list(MAKERS).index(name)
        image = MAKERS[name](np.random.default_rng(seed))
        if args.matched:
            path = OUT / "profile" / f"{name}.jpg"
            path.parent.mkdir(exist_ok=True)
            _match_profile(image, name).save(path, quality=92, subsampling=0, optimize=True)
        else:
            path = OUT / f"{name}.png"
            image.save(path, optimize=True)
        print(f"written: {path.relative_to(ROOT)}")
    return 0


def _match_profile(image: Image.Image, name: str) -> Image.Image:
    """Color grade an original render and soften the edge behind the bar."""
    from hyprsetup import presets, themes

    values = presets.resolve_chain(ROOT, profile=name)
    palette = themes.resolve(values["THEME"], values.get("CUSTOM_COLORS", ""))
    bg, surface, fg, accent, secondary = (
        np.asarray(_hex(palette[key][:6]), dtype=np.float32)
        for key in ("BG", "SURFACE", "FG", "ACCENT", "ACCENT2")
    )
    source = np.asarray(image.convert("RGB"), dtype=np.float32)
    luma = source @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    low, high = np.percentile(luma[::4, ::4], (3, 98))
    tone = np.clip((luma - low) / max(24, high - low), 0, 1)
    light = themes.is_light(palette)
    if light:
        stops = (fg, _mix(fg, surface, 0.55), surface, bg, _mix(bg, (255, 255, 255), 0.38))
        tone = tone ** 0.72
    else:
        stops = (_mix(bg, (0, 0, 0), 0.38), bg, _mix(surface, secondary, 0.25),
                 _mix(surface, accent, 0.70), _mix(accent, fg, 0.42))
        tone = tone ** 1.18
    ramp = np.asarray(stops)
    grade = np.stack([np.interp(tone, (0, 0.18, 0.48, 0.83, 1), ramp[:, channel])
                      for channel in range(3)], axis=-1).astype(np.float32)

    # Retain small hue differences in the illustration and carry the secondary
    # accent into cool details without introducing unrelated dominant colors.
    cool = np.clip((source[..., 2] - source[..., 0]) / 100, 0, 1)
    grade += (cool * tone * (0.12 if light else 0.32))[..., None] * (secondary - accent)
    chroma = 0 if name in {"st-manga", "st-siyah", "st-sepya"} else 0.13
    grade += (source - luma[..., None]) * chroma
    if name == "st-kagit":
        # The ink landscape stays sepia while the small red sun matches the bar accent.
        seal = np.clip((source[..., 0] - source[..., 1] - 32) / 78, 0, 1)[..., None]
        grade += 0.77 * seal * (accent - grade)

    bar_edge = values.get("BAR_POSITION", "top")
    vertical = bar_edge in {"left", "right"}
    axis = np.linspace(0, 1, image.width if vertical else image.height, dtype=np.float32)
    if bar_edge in {"bottom", "right"}:
        axis = axis[::-1]
    fade = np.clip(1 - axis / 0.19, 0, 1) ** 2
    opacity = float(values.get("BAR_OPACITY", "1"))
    edge = (fade[None, :, None] if vertical else fade[:, None, None]) * (0.8 - 0.28 * opacity)
    return _img(grade * (1 - edge) + bg * edge)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
