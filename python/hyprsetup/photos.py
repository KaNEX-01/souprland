"""Photo wallpapers of the Script Test profiles (``wallpapers/photo/``).

Every image there is a real photograph released as **CC0 or public domain**
on Wikimedia Commons, so it can ship inside the repository; author, page and
licence are listed in ``wallpapers/photo/sources.json``. Each profile's
"photo" look variant uses its image, the "generated" variant the drawing from
``tools/script-test-wallpapers.py``.

They replace the former Wallhaven picks, which were downloaded on first use
from other people's uploads: several were game/film/anime art (DOOM,
Evangelion, The Mandalorian…) and none had a licence on record.

Old configs may still name ``wallpapers/wallhaven/<profile>.<ext>`` (that
directory no longer exists) or the ``wallhaven`` variant; ``resolve`` and
``VARIANT_ALIAS`` send them to the photo of the same profile.
"""

from __future__ import annotations

import json
from pathlib import Path

DIR = Path("wallpapers/photo")
SOURCES = DIR / "sources.json"
LEGACY_DIR = "wallpapers/wallhaven/"
#: Renamed look variants: old name → new name.
VARIANT_ALIAS = {"wallhaven": "photo"}


def sources(root: Path) -> dict[str, dict]:
    try:
        return json.loads((Path(root) / SOURCES).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def resolve(root: Path, image: str) -> Path | None:
    """The file to use for a configured ``WALLPAPER_IMAGE``.

    An existing file is used as is. A former Wallhaven path maps to the
    profile's photo, or failing that to its generated wallpaper.
    """
    root = Path(root)
    target = root / image
    if target.is_file():
        return target
    if image.startswith(LEGACY_DIR):
        stem = Path(image).stem
        for candidate in (root / DIR / f"{stem}.jpg", root / "wallpapers" / f"{stem}.png"):
            if candidate.is_file():
                return candidate
    return None
