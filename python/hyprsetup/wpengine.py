"""Installed Wallpaper Engine (Steam Workshop) wallpapers.

Feeds the settings app's "Wallpaper Engine" gallery. Workshop items live under
``steamapps/workshop/content/431960/<id>`` in every Steam library; libraries are
listed in ``libraryfolders.vdf`` (a library on a second disk that is not mounted
is silently skipped).

``WPENGINE_PER_SCREEN`` ("DP-1=123;HDMI-A-2=456") picks a separate scene per
display; displays not in the list play ``WPENGINE_ID``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

APP_ID = "431960"
_STEAM_ROOTS = (".local/share/Steam", ".steam/steam",
                ".var/app/com.valvesoftware.Steam/.local/share/Steam")
_PREVIEWS = ("preview.gif", "preview.jpg", "preview.png", "preview.jpeg")


@dataclass
class Item:
    ident: str
    title: str
    kind: str          # scene | video | web | ""
    folder: Path
    preview: Path | None
    edited: bool       # has an edited copy made by wpedit.py


def library_roots(home: Path | None = None) -> list[Path]:
    """Existing Steam libraries (main install + libraryfolders.vdf)."""
    home = home or Path.home()
    roots: list[Path] = []
    for rel in _STEAM_ROOTS:
        steam = home / rel
        if not steam.is_dir():
            continue
        roots.append(steam)
        vdf = steam / "steamapps/libraryfolders.vdf"
        try:
            text = vdf.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        roots += [Path(p) for p in re.findall(r'"path"\s+"([^"]+)"', text)]
    seen: set[Path] = set()
    unique = []
    for root in roots:
        try:
            resolved = root.resolve()
        except OSError:
            continue
        if resolved not in seen and resolved.is_dir():
            seen.add(resolved)
            unique.append(root)
    return unique


def items(home: Path | None = None) -> list[Item]:
    """Installed Workshop wallpapers, sorted by title."""
    home = home or Path.home()
    edited_base = home / ".local/share/hyprsetup-wallpapers"
    found: dict[str, Item] = {}
    for root in library_roots(home):
        base = root / "steamapps/workshop/content" / APP_ID
        if not base.is_dir():
            continue
        for folder in sorted(base.iterdir()):
            project = folder / "project.json"
            if folder.name in found or not project.is_file():
                continue
            try:
                meta = json.loads(project.read_text(encoding="utf-8", errors="ignore"))
            except ValueError:
                meta = {}
            preview = folder / str(meta.get("preview") or "")
            if not preview.is_file():
                preview = next((folder / p for p in _PREVIEWS if (folder / p).is_file()), None)
            found[folder.name] = Item(
                ident=folder.name,
                title=str(meta.get("title") or folder.name).strip(),
                kind=str(meta.get("type") or "").lower(),
                folder=folder,
                preview=preview,
                edited=(edited_base / folder.name / "project.json").is_file())
    return sorted(found.values(), key=lambda i: i.title.casefold())


def parse_per_screen(text: str) -> dict[str, str]:
    """"DP-1=123;HDMI-A-2=456" → {"DP-1": "123", "HDMI-A-2": "456"}."""
    mapping: dict[str, str] = {}
    for part in re.split(r"[;,]", text or ""):
        screen, sep, ident = part.partition("=")
        if sep and screen.strip() and ident.strip():
            mapping[screen.strip()] = ident.strip()
    return mapping


def format_per_screen(mapping: dict[str, str]) -> str:
    return ";".join(f"{screen}={ident}" for screen, ident in sorted(mapping.items()) if ident)
