"""Resolve bundled wallpapers and recognize copies from older installs."""

from __future__ import annotations

import hashlib
from pathlib import Path


RETIRED_VARIANTS = frozenset({"photo", "uretilmis", "wallhaven"})
_PROFILE_DIR = Path("wallpapers/profile")
_LEGACY_DIRS = {Path("wallpapers/photo"), Path("wallpapers/wallhaven")}


def resolve(root: Path, image: str) -> Path | None:
    """Use an existing file, or map an archived path to the profile artwork."""
    root = Path(root)
    rel = Path(image)
    target = root / rel
    if target.is_file():
        return target
    if rel.parent in _LEGACY_DIRS or (rel.parent == Path("wallpapers") and rel.suffix == ".png"):
        matched = root / _PROFILE_DIR / f"{rel.stem}.jpg"
        if matched.is_file():
            return matched
    if rel.parent == Path("wallpapers/wallhaven"):
        original = root / "wallpapers" / f"{rel.stem}.png"
        if original.is_file():
            return original
    return None


def is_archived_wallpaper(root: Path, target: Path, size: int) -> bool:
    """Recognize exact copies of bundled artwork removed from the install."""
    try:
        index = (root / _PROFILE_DIR / "legacy-wallpapers.txt").read_text(encoding="ascii")
        prefix = f"{size} "
        hashes = {line.removeprefix(prefix) for line in index.splitlines() if line.startswith(prefix)}
        return bool(hashes) and hashlib.sha256(target.read_bytes()).hexdigest() in hashes
    except OSError:
        return False
