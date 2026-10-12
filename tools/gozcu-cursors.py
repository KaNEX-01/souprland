#!/usr/bin/env python3
"""Builds the cursor theme of the Gozcu (st-gozcu) profile (assets/cursors/Gozcu-Cursors).

Shapes come from Bibata Modern (https://github.com/ful1e5/Bibata_Cursor, GPL-3.0):
the SVG sources come with Bibata's own color placeholders (#00FF00 body,
#0000FF outline, #FF0000 busy dial) and are painted in the theme's palette
here. Instead of Bibata's spinning four-color dial, the busy cursors
(wait, left_ptr_watch) play a mint-green moon phase going from new moon to
full moon and back.

Output comes in two formats:
    cursors/      XCursor (GTK, Qt, XWayland) — written directly by this script,
                  no xcursorgen/clickgen needed
    hyprcursors/  hyprcursor (Hyprland, SVG-based crisp scaling) —
                  generated if hyprcursor-util is installed

Requirements: rsvg-convert (librsvg), magick (ImageMagick), git; optionally
hyprcursor-util.

    ./tools/gozcu-cursors.py                    # clones Bibata into the cache
    ./tools/gozcu-cursors.py --bibata ~/src/Bibata_Cursor
"""

from __future__ import annotations

import argparse
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
THEME = "Gozcu-Cursors"
BIBATA_URL = "https://github.com/ful1e5/Bibata_Cursor.git"

# The palette's source is python/hyprsetup/themes.py → "st-gozcu".
BODY = "#1C1C1D"        # BG: charcoal body
GLOW = "#1DF5A4"        # ACCENT: neon mint outline, the moon's lit face
DIM = "#5FA889"         # ACCENT2
SHADE = "#0F3A2B"       # the moon's dark face (greenish earthshine)
CRATER = "#14C98A"      # crater spots on the lit face

COLORS = {
    "#00FF00": BODY,
    "#0000FF": GLOW,
    "#FF0000": BODY,
    # Bibata's small accents — their palette counterparts
    "#FE0000": "#E0686C",   # forbidden / cross
    "#06B231": GLOW,        # copy plus
    "#F1613A": DIM,         # slices of the corner cursors
    "#4FADDF": DIM,
    "#FDBE2A": DIM,
    "#96C865": DIM,
    "#179DD8": "#1DD8C0",
    "#0A6857": DIM,
    "#5F3BE4": DIM,
    "#F27400": "#D6C27C",
    "#606060": "#7C8582",
    "#2C2C2C": "#2A2C2B",
}
# Slices of Bibata's spinning dial: replaced with the moon phase.
PIE = ("#F05024", "#FCB813", "#7EBA41", "#32A0DA")

SIZES = [24, 28, 32, 40, 48, 56, 64, 72, 96]
ANIM_SIZES = [24, 28, 32, 40, 48, 64]   # frame count × size bloats the file
FRAMES = 24
DELAY_MS = 60                           # 24 × 60 ms ≈ one moon cycle every 1.4 s

# Where the moon goes in busy cursors: center and inner radius of Bibata's dial.
MOON_AT = {"wait": (128.0, 128.0, 64.0), "left_ptr_watch": (118.0, 162.0, 50.0)}


# --- moon phase -----------------------------------------------------------

def _lit_path(cx: float, cy: float, r: float, phase: float) -> str:
    """The lit part of the moon. phase 0 → new moon, 0.5 → full moon, 1 → new moon.

    The lit edge is always a semicircle; the shadow boundary (terminator) is a
    half ellipse with horizontal semi-axis r·|cos φ|. While waxing the right
    face is lit, while waning the left (as seen from the northern hemisphere).
    """
    phi = 2 * math.pi * phase
    k = math.cos(phi)
    rx = abs(k) * r
    top, bottom = f"{cx:.3f} {cy - r:.3f}", f"{cx:.3f} {cy + r:.3f}"
    if phi <= math.pi:          # waxing moon: right half
        outer, inner = 1, (0 if k > 0 else 1)
    else:                       # waning moon: left half
        outer, inner = 0, (1 if k > 0 else 0)
    return (f"M {top} A {r:.3f} {r:.3f} 0 0 {outer} {bottom} "
            f"A {rx:.3f} {r:.3f} 0 0 {inner} {top} Z")


def _moon(cx: float, cy: float, r: float, phase: float, uid: str) -> str:
    lit = _lit_path(cx, cy, r, phase)
    # Crater spots in the moon's own coordinates; visible only on the lit face.
    craters = "".join(
        f'<circle cx="{cx + dx * r:.2f}" cy="{cy + dy * r:.2f}" r="{rr * r:.2f}"/>'
        for dx, dy, rr in ((-0.30, -0.28, 0.20), (0.32, 0.18, 0.15),
                           (-0.12, 0.42, 0.12), (0.18, -0.48, 0.09),
                           (0.52, -0.12, 0.08)))
    return (
        f'<g transform="rotate(-25 {cx} {cy})">'
        f'<clipPath id="lit{uid}"><path d="{lit}"/></clipPath>'
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{SHADE}"/>'
        f'<path d="{lit}" fill="{GLOW}"/>'
        f'<g clip-path="url(#lit{uid})" fill="{CRATER}" fill-opacity="0.75">{craters}</g>'
        f'</g>')


def _moon_frames(template: str, name: str) -> list[str]:
    """Strips the dial from Bibata's first frame and puts the moon phases in its place."""
    base = re.sub(r'<path[^>]*fill="(?:%s)"[^>]*/>\s*' % "|".join(PIE), "",
                  template, flags=re.I)
    cx, cy, r = MOON_AT[name]
    return [base.replace("</svg>", _moon(cx, cy, r, i / FRAMES, f"{i}") + "\n</svg>")
            for i in range(FRAMES)]


# --- sources --------------------------------------------------------------

def _recolor(svg: str) -> str:
    for src, dst in COLORS.items():
        svg = re.sub(re.escape(src), dst, svg, flags=re.I)
    return svg


def _load_bibata(path: Path | None) -> Path:
    if path:
        return path
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "souprland/Bibata_Cursor"
    if not (cache / "svg/modern").is_dir():
        cache.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", BIBATA_URL, str(cache)], check=True)
    return cache


def _cursor_specs(bibata: Path) -> list[dict]:
    """configs/normal/x.build.toml: name, hotspot, aliases, frames."""
    cfg = tomllib.loads((bibata / "configs/normal/x.build.toml").read_text())
    cursors = cfg["cursors"]
    fb = cursors.get("fallback_settings", {})
    specs = []
    for key, c in cursors.items():
        if key == "fallback_settings":
            continue
        specs.append({
            "name": c.get("x11_name", key),
            "src": c["png"].removesuffix(".png").removesuffix("-*"),
            "animated": c["png"].endswith("-*.png"),
            "hot": (c.get("x_hotspot", fb.get("x_hotspot", 128)),
                    c.get("y_hotspot", fb.get("y_hotspot", 128))),
            "links": c.get("x11_symlinks", []),
        })
    return specs


# --- XCursor ---------------------------------------------------------------

def _rgba(svg: Path, size: int) -> bytes:
    png = subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size), str(svg)],
                         check=True, capture_output=True).stdout
    return subprocess.run(["magick", "png:-", "-depth", "8", "rgba:-"], input=png,
                          check=True, capture_output=True).stdout


def _argb_premul(rgba: bytes) -> bytes:
    out = bytearray(len(rgba))
    for i in range(0, len(rgba), 4):
        r, g, b, a = rgba[i:i + 4]
        out[i:i + 4] = struct.pack("<I", (a << 24) | ((r * a // 255) << 16)
                                   | ((g * a // 255) << 8) | (b * a // 255))
    return bytes(out)


def _write_xcursor(dest: Path, images: list[tuple[int, int, int, int, bytes]]) -> None:
    """images: (size, hot_x, hot_y, delay_ms, ARGB) — same sizes consecutive."""
    header = struct.pack("<4sIII", b"Xcur", 16, 0x10000, len(images))
    pos = 16 + 12 * len(images)
    toc, chunks = b"", b""
    for size, hx, hy, delay, pixels in images:
        toc += struct.pack("<III", 0xFFFD0002, size, pos)
        chunk = struct.pack("<9I", 36, 0xFFFD0002, size, 1, size, size, hx, hy, delay) + pixels
        chunks += chunk
        pos += len(chunk)
    dest.write_bytes(header + toc + chunks)


def _build_xcursor(spec: dict, svgs: list[Path], out: Path) -> None:
    sizes = ANIM_SIZES if spec["animated"] else SIZES
    images = []
    for size in sizes:
        hx = min(size - 1, round(spec["hot"][0] * size / 256))
        hy = min(size - 1, round(spec["hot"][1] * size / 256))
        for svg in svgs:
            delay = DELAY_MS if spec["animated"] else 0
            images.append((size, hx, hy, delay, _argb_premul(_rgba(svg, size))))
    _write_xcursor(out / spec["name"], images)
    for link in spec["links"]:
        target = out / link
        if target.exists() or target.is_symlink():
            target.unlink()
        target.symlink_to(spec["name"])


# --- hyprcursor ------------------------------------------------------------

def _build_hyprcursor(specs: list[dict], sources: dict[str, list[Path]], theme_dir: Path) -> None:
    if shutil.which("hyprcursor-util") is None:
        print("hyprcursor-util missing: only XCursor was generated", file=sys.stderr)
        return
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src"
        (src / "hyprcursors").mkdir(parents=True)
        (src / "manifest.hl").write_text(
            f"name = {THEME}\ndescription = {_DESC}\nversion = 1.0\n"
            "cursors_directory = hyprcursors\n")
        for spec in specs:
            shape = src / "hyprcursors" / spec["name"]
            shape.mkdir()
            lines = ["resize_algorithm = bilinear",
                     f"hotspot_x = {spec['hot'][0] / 256:.4f}",
                     f"hotspot_y = {spec['hot'][1] / 256:.4f}"]
            lines += [f"define_override = {link}" for link in spec["links"]]
            for svg in sources[spec["name"]]:
                shutil.copy(svg, shape / svg.name)
                delay = f", {DELAY_MS}" if spec["animated"] else ""
                lines.append(f"define_size = 0, {svg.name}{delay}")
            (shape / "meta.hl").write_text("\n".join(lines) + "\n")
        subprocess.run(["hyprcursor-util", "--create", str(src), "--output", tmp],
                       check=True, capture_output=True)
        built = Path(tmp) / f"theme_{THEME}"
        shutil.copytree(built / "hyprcursors", theme_dir / "hyprcursors")
        shutil.copy(built / "manifest.hl", theme_dir / "manifest.hl")


_DESC = ("Gozcu (Sentinel) — charcoal body, neon mint outline, moon-phase busy cursor "
         "(based on Bibata Modern)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bibata", type=Path, help="Bibata_Cursor deposunun yolu")
    ap.add_argument("--out", type=Path, default=ROOT / "assets/cursors" / THEME)
    args = ap.parse_args()

    for tool in ("rsvg-convert", "magick"):
        if shutil.which(tool) is None:
            sys.exit(f"{tool} not found")

    bibata = _load_bibata(args.bibata)
    specs = _cursor_specs(bibata)
    svg_root = bibata / "svg/modern"

    if args.out.exists():
        shutil.rmtree(args.out)
    (args.out / "cursors").mkdir(parents=True)

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        sources: dict[str, list[Path]] = {}
        for spec in specs:
            if spec["animated"]:
                first = sorted((svg_root / spec["src"]).glob("*.svg"))[0]
                frames = _moon_frames(_recolor(first.read_text()), spec["src"])
                paths = []
                for i, svg in enumerate(frames, 1):
                    p = work / f"{spec['name']}-{i:02d}.svg"
                    p.write_text(svg)
                    paths.append(p)
            else:
                p = work / f"{spec['name']}.svg"
                p.write_text(_recolor((svg_root / f"{spec['src']}.svg").read_text()))
                paths = [p]
            sources[spec["name"]] = paths

        with ThreadPoolExecutor(os.cpu_count()) as pool:
            for f in [pool.submit(_build_xcursor, s, sources[s["name"]], args.out / "cursors")
                      for s in specs]:
                f.result()
        _build_hyprcursor(specs, sources, args.out)

    theme = f"[Icon Theme]\nName={THEME}\nComment={_DESC}\n"
    (args.out / "index.theme").write_text(theme)
    (args.out / "cursor.theme").write_text(f"[Icon Theme]\nName={THEME}\nInherits={THEME}\n")
    shutil.copy(bibata / "LICENSE", args.out / "LICENSE")
    print(f"{args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out}: "
          f"{len(specs)} cursors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
