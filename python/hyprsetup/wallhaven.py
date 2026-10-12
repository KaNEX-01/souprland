"""Wallhaven wallpapers for the Script Test profiles.

The images are other people's uploads, so they are not committed (``wallpapers/wallhaven/``
is in .gitignore). Only the source list lives in the repo:
``wallpapers/wallhaven/sources.json`` → {profile: {id, url, page, file}}.
An image is downloaded on first use (when the profile is applied); if the download
fails, the wallpaper we generated for the profile (``wallpapers/<profile>.png``) is used.
Each profile's "generated (old)" appearance variant selects that old image.

Downloaded images are scaled to 1920×1080 (if Pillow is available).
To download them all manually: ``python3 -m hyprsetup.wallhaven``.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

DIR = Path("wallpapers/wallhaven")
#: Images are scaled to this size (16:9, center-cropped).
SIZE = (1920, 1080)
SOURCES = DIR / "sources.json"
_MAX = 40 * 1024 * 1024


def sources(root: Path) -> dict[str, dict]:
    try:
        return json.loads((Path(root) / SOURCES).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _to_1080p(path: Path, suffix: str) -> None:
    """Fits the image to SIZE (left as-is without Pillow)."""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return
    try:
        with Image.open(path) as image:
            if image.size == SIZE:
                return
            fitted = ImageOps.fit(image if suffix == ".png" else image.convert("RGB"),
                                  SIZE, Image.LANCZOS)
        fitted.save(path, "PNG" if suffix == ".png" else "JPEG",
                    **({"optimize": True} if suffix == ".png" else {"quality": 92}))
    except OSError:
        pass


def ensure(root: Path, image: str) -> Path | None:
    """Downloads ``wallpapers/wallhaven/<file>`` from the source list if missing.

    Returns the existing image; if it could not be downloaded, the old generated
    image, or None.
    """
    root = Path(root)
    target = root / image
    if target.is_file():
        return target
    entry = next((e for e in sources(root).values() if e.get("file") == Path(image).name), None)
    if entry and str(entry.get("url", "")).startswith("https://w.wallhaven.cc/"):
        try:
            request = urllib.request.Request(entry["url"], headers={"User-Agent": "souprland"})
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read(_MAX + 1)
            if 0 < len(data) <= _MAX:
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_suffix(target.suffix + ".part")
                tmp.write_bytes(data)
                _to_1080p(tmp, target.suffix)
                tmp.replace(target)
                return target
        except OSError:
            pass
    fallback = root / "wallpapers" / f"{Path(image).stem}.png"
    return fallback if fallback.is_file() else None


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    for name, entry in sorted(sources(root).items()):
        path = ensure(root, str(DIR / entry["file"]))
        ok = path is not None and path.parent.name == "wallhaven"
        print(f"{'ok ' if ok else '!! '} {name}: {entry['page']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
