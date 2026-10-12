"""Finds the cursor (Xcursor) themes installed on the system and renders preview surfaces.

Why this exists: until now the user could only type the cursor theme by hand —
there was no list to pick from and no way to see "what it looks like". The Xcursor
file format is documented and simple (see ``_parse``), so the real image can be read
straight from the installed theme without needing a cursor PNG. Packages like Bibata
come from the AUR during install; since this tool usually runs on the machine it
configures, scanning what is "installed" here is both correct and sufficient.
"""

from __future__ import annotations

import struct
from pathlib import Path

#: The installer brings these with the "cursor-theme" component (see
#: config/components.json → repo/aur lists); they show up as suggestions in the
#: quick pick even when not installed. The names are real Xcursor directory names —
#: not to be confused with package names (e.g. package "vimix-cursors", directory
#: "Vimix-cursors").
SUGGESTED = (
    "Bibata-Modern-Ice", "Bibata-Modern-Classic", "Bibata-Modern-Amber",
    "Bibata-Original-Ice", "Bibata-Original-Classic", "Bibata-Original-Amber",
    "capitaine-cursors", "capitaine-cursors-light",
    "Vimix-cursors", "Vimix-white-cursors",
    "Qogir-cursors", "Qogir-white-cursors",
    "Layan-cursors", "Layan-white-cursors",
    "Numix-Cursor", "Numix-Cursor-Light",
    "Adwaita", "breeze_cursors",
)

_IMAGE_CHUNK = 0xFFFD0002
_MAGIC = b"Xcur"


#: Themes bundled with the repo that have no package (e.g. Gozcu-Cursors generated
#: by tools/gozcu-cursors.py). They are copied to ~/.local/share/icons when applied
#: (see apply.py:_apply_cursor); until then the preview is read from here.
BUNDLED_DIR = Path(__file__).resolve().parents[2] / "assets" / "cursors"


def _search_dirs() -> list[Path]:
    return [
        Path.home() / ".icons",
        Path.home() / ".local/share/icons",
        Path("/usr/share/icons"),
        Path("/usr/local/share/icons"),
        BUNDLED_DIR,
    ]


def _pointer_file(theme_dir: Path) -> Path | None:
    cursors = theme_dir / "cursors"
    for name in ("left_ptr", "default"):
        candidate = cursors / name
        if candidate.is_file():
            return candidate
    return None


def available() -> list[str]:
    """Names of installed themes that have ``cursors/left_ptr`` (or ``default``)."""
    found: dict[str, str] = {}   # lowercase key → real name to display
    for base in _search_dirs():
        if not base.is_dir():
            continue
        try:
            entries = sorted(base.iterdir())
        except OSError:
            continue
        for entry in entries:
            if not entry.is_dir():
                continue
            if _pointer_file(entry) is None:
                continue
            found.setdefault(entry.name.lower(), entry.name)
    return sorted(found.values(), key=str.lower)


def find_theme_dir(theme: str) -> Path | None:
    """Returns the first theme directory whose name matches (case-insensitive)."""
    wanted = theme.strip().lower()
    if not wanted:
        return None
    for base in _search_dirs():
        candidate = base / theme
        if candidate.is_dir() and _pointer_file(candidate) is not None:
            return candidate
        if not base.is_dir():
            continue
        try:
            entries = base.iterdir()
        except OSError:
            continue
        for entry in entries:
            if entry.name.lower() == wanted and _pointer_file(entry) is not None:
                return entry
    return None


def _parse(path: Path, target_size: int = 32):
    """Reads an Xcursor file and returns the image closest in size.

    Format: a 4-byte "Xcur" magic, then a table of contents (type, subtype =
    "nominal" size, file position). Each image chunk carries width, height,
    hotspot and then 4 bytes per pixel (B, G, R, A — premultiplied alpha). On a
    little-endian machine this byte order matches cairo's ARGB32 format, so no
    conversion is needed.

    Returns: (width, height, pixel bytes), or None if not found.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) < 16 or data[:4] != _MAGIC:
        return None

    _header_size, _version, ntoc = struct.unpack_from("<III", data, 4)
    best = None    # (difference, position)
    toc_offset = 16
    for i in range(ntoc):
        try:
            chunk_type, subtype, position = struct.unpack_from(
                "<III", data, toc_offset + i * 12)
        except struct.error:
            break
        if chunk_type != _IMAGE_CHUNK:
            continue
        diff = abs(subtype - target_size)
        if best is None or diff < best[0]:
            best = (diff, position)
    if best is None:
        return None

    position = best[1]
    try:
        (_chdr, _ctype, _csub, _cver, width, height,
         _xhot, _yhot, _delay) = struct.unpack_from("<IIIIIIIII", data, position)
    except struct.error:
        return None
    if width <= 0 or height <= 0 or width > 512 or height > 512:
        return None

    pixel_offset = position + 36
    needed = width * height * 4
    pixels = data[pixel_offset:pixel_offset + needed]
    if len(pixels) < needed:
        return None
    return width, height, pixels


_surface_cache: dict[tuple[str, int], object] = {}


def pointer_surface(theme: str, size: int = 32):
    """Returns the given theme's pointer image as a cairo surface.

    ``None`` if the theme is not found or cannot be parsed — the caller should
    draw a built-in placeholder.
    """
    key = (theme, size)
    if key in _surface_cache:
        return _surface_cache[key]

    surface = None
    theme_dir = find_theme_dir(theme)
    pointer = _pointer_file(theme_dir) if theme_dir else None
    if pointer is not None:
        parsed = _parse(pointer, size)
        if parsed is not None:
            import cairo
            width, height, pixels = parsed
            stride = width * 4
            try:
                surface = cairo.ImageSurface.create_for_data(
                    bytearray(pixels), cairo.FORMAT_ARGB32, width, height, stride)
            except Exception:
                surface = None
    _surface_cache[key] = surface
    return surface


def quick_list() -> list[str]:
    """Names shown in the quick pick: installed ones + suggestions.

    Installed ones first (they have real previews), then suggestions that are not
    installed yet but can come with this tool (they work after installation).
    """
    installed = available()
    installed_lower = {n.lower() for n in installed}
    extra = [n for n in SUGGESTED if n.lower() not in installed_lower]
    return installed + extra
