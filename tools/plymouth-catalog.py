#!/usr/bin/env python3
"""Builds the catalog of community Plymouth themes.

Output:
  presets/login/plymouth.toml            theme list (name, package, preview URL)
  presets/login/plymouth-previews/*.jpg  480x270 card images (a few KB)

Sources:
  * adi1090x/plymouth-themes — 80 themes (from Android boot animations),
    each on the AUR as plymouth-theme-<name>-git; GIF previews live in the
    adi1090x/files repo (in README order, which matches the folder order).
  * catppuccin/plymouth — 4 flavors; WebP previews inside the repo.

Animated previews (~3 MB each) are NOT put in the repo: the settings app
downloads and caches them when selected. Here only the head of the GIF is
downloaded for the card image (Range) and the "fullest" frame (highest
brightness deviation) is picked — the first frames of boot animations are
often black.

Requires Pillow (only for this tool; the app does not use it):
    python3 tools/plymouth-catalog.py
"""

from __future__ import annotations

import io
import json
import re
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageFile, ImageStat

ImageFile.LOAD_TRUNCATED_IMAGES = True

ROOT = Path(__file__).resolve().parent.parent
OUT_TOML = ROOT / "presets/login/plymouth.toml"
OUT_DIR = ROOT / "presets/login/plymouth-previews"
THUMB = (480, 270)
UA = {"User-Agent": "souprland-plymouth-catalog"}

ADI_REPO = "adi1090x/plymouth-themes"
ADI_README = f"https://raw.githubusercontent.com/{ADI_REPO}/master/README.md"
ADI_TREE = f"https://api.github.com/repos/{ADI_REPO}/git/trees/master?recursive=1"
CAT_REPO = "catppuccin/plymouth"
CAT_FLAVORS = {"latte": "light", "frappe": "dark and soft", "macchiato": "dark",
               "mocha": "darkest"}


def fetch(url: str, limit: int | None = None) -> bytes:
    headers = dict(UA)
    if limit:
        headers["Range"] = f"bytes=0-{limit}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers),
                                timeout=60) as resp:
        return resp.read()


def stars(repo: str) -> tuple[int, str]:
    data = json.loads(fetch(f"https://api.github.com/repos/{repo}"))
    return data.get("stargazers_count", 0), (data.get("license") or {}).get("spdx_id", "")


def best_frame(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    best: tuple[float, Image.Image] | None = None
    index = 0
    while True:
        try:
            image.seek(index)
            frame = image.convert("RGB")
        except (EOFError, OSError, ValueError):
            break
        score = ImageStat.Stat(frame.convert("L")).stddev[0]
        if best is None or score > best[0]:
            best = (score, frame.copy())
        index += 1
    if best is None:
        raise ValueError("could not read a frame")
    return best[1]


def save_thumb(frame: Image.Image, name: str) -> None:
    # Fit the 16:9 card, fill the rest with black (boot screens are black).
    # Lanczos: thin bright lines (most themes are wireframes on black) got
    # blurry with the default downscale. subsampling=0 (4:4:4): JPEG chroma
    # subsampling smeared thin colored lines into blotches.
    frame.thumbnail(THUMB, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", THUMB, (0, 0, 0))
    canvas.paste(frame, ((THUMB[0] - frame.width) // 2, (THUMB[1] - frame.height) // 2))
    canvas.save(OUT_DIR / f"{name}.jpg", quality=92, subsampling=0, optimize=True)


def content_crop(path: Path) -> list[float]:
    """Zoom box for the card (x, y, width, height; as fractions).

    Most boot animations are a small logo in the middle of a black screen: on
    a 120 pixel card the logo shrank to 30 pixels and looked blurry. The bounds
    of pixels clearly different from the background (corner pixel) are found,
    a margin is added and the box is widened to 16:9. The large preview is not
    cropped — there it should look as it really will on screen.
    """
    image = Image.open(path).convert("RGB")
    w, h = image.size
    bg = image.getpixel((2, 2))
    mask = Image.new("L", (w, h))
    px, mp = image.load(), mask.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2]) > 60:
                mp[x, y] = 255
    box = mask.getbbox()
    if box is None:
        return [0.0, 0.0, 1.0, 1.0]
    x0, y0, x1, y1 = box
    cw, ch = (x1 - x0) * 1.5, (y1 - y0) * 1.5          # margin
    ch = max(ch, cw * 9 / 16, h * 0.35)                 # 16:9, no extreme zoom
    cw = ch * 16 / 9
    if cw > w:
        cw, ch = w, w * 9 / 16
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    left = min(max(cx - cw / 2, 0), w - cw)
    top = min(max(cy - ch / 2, 0), h - ch)
    return [round(left / w, 4), round(top / h, 4), round(cw / w, 4), round(ch / h, 4)]


def q(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []

    adi_stars, adi_license = stars(ADI_REPO)
    tree = json.loads(fetch(ADI_TREE))["tree"]
    dirs = sorted({p["path"] for p in tree
                   if re.fullmatch(r"pack_\d/[^/]+/[^/]+\.plymouth", p["path"])})
    readme = fetch(ADI_README).decode()
    links = re.findall(r"\+ \[([^\]]+)\]\((https://raw[^)]+/\d+\.gif)\)", readme)
    if len(dirs) != len(links):
        print(f"adi1090x: {len(dirs)} folders but {len(links)} previews", file=sys.stderr)
        return 1
    for path, (title, gif) in zip(dirs, links):
        pack, name = path.split("/")[:2]
        # If the order mapping breaks (a theme added to the README but not as a
        # folder) do not show the wrong preview: the names' first letters must match.
        if re.sub(r"[^a-z]", "", name)[:4] != re.sub(r"[^a-z]", "", title.lower())[:4]:
            print(f"adi1090x: {name} ↔ {title} do not match", file=sys.stderr)
            return 1
        entries.append({
            "id": name, "title": title, "source": "adi1090x",
            "desc": f"Adapted from an Android boot animation (adi1090x, {pack.replace('_', ' ')})",
            "repo": f"https://github.com/{ADI_REPO}", "stars": adi_stars,
            "license": adi_license, "aur": f"plymouth-theme-{name.replace('_', '-')}-git",
            "preview": gif})

    cat_stars, cat_license = stars(CAT_REPO)
    for flavor, tone in CAT_FLAVORS.items():
        entries.append({
            "id": f"catppuccin-{flavor}", "title": f"Catppuccin {flavor.capitalize()}",
            "source": "catppuccin",
            "desc": f"Catppuccin palette, {tone}; matches the project's Catppuccin themes",
            "repo": f"https://github.com/{CAT_REPO}", "stars": cat_stars,
            "license": cat_license, "aur": f"plymouth-theme-catppuccin-{flavor}-git",
            "preview": f"https://raw.githubusercontent.com/{CAT_REPO}/main/assets/{flavor}.webp"})

    for entry in entries:
        thumb = OUT_DIR / f"{entry['id']}.jpg"
        if thumb.is_file():
            continue
        # The first ~1.5 MB of a GIF holds dozens of frames; WebPs are small, take all.
        limit = 1_500_000 if entry["preview"].endswith(".gif") else None
        try:
            save_thumb(best_frame(fetch(entry["preview"], limit)), entry["id"])
            print("  image:", entry["id"])
        except (OSError, ValueError) as exc:
            print(f"  !! {entry['id']}: {exc}", file=sys.stderr)

    lines = [
        "# Community Plymouth (boot animation) themes — generated by tools/plymouth-catalog.py.",
        "#",
        "# The settings app's Login Screen → Boot animation section shows this list.",
        "# Themes that are not installed are installed from the AUR (in a terminal,",
        "# paru/yay); the theme lands in /usr/share/plymouth/themes/<id>"
        " and is enabled with Apply.",
        "#",
        "# Fields:",
        "#   id       theme folder name (the plymouth-set-default-theme name once installed)",
        "#   aur      AUR package",
        "#   preview  animated preview (downloaded and cached when selected)",
        "#   crop     zoom box on the card (x, y, width, height; as fractions) — so the",
        "#            logo doesn't end up tiny; the large preview shows the full frame",
        "#   card image: plymouth-previews/<id>.jpg",
        "",
    ]
    for entry in entries:
        thumb = OUT_DIR / f"{entry['id']}.jpg"
        crop = content_crop(thumb) if thumb.is_file() else [0.0, 0.0, 1.0, 1.0]
        lines.append("[[theme]]")
        for key in ("id", "title", "source", "desc", "repo", "stars", "license",
                    "aur", "preview"):
            value = entry[key]
            lines.append(f"{key} = {value if isinstance(value, int) else q(value)}")
        lines.append(f"crop = [{', '.join(str(v) for v in crop)}]")
        lines.append("")
    OUT_TOML.write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(entries)} tema → {OUT_TOML.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
