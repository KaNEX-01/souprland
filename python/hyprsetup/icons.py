"""App icon themes: finds the installed ones and knows the suggested sets.

Why this exists: ICON_THEME_NAME used to be just a free-text box, and the system
had no set other than Papirus. This module provides two things:

* ``available()``  icon themes actually installed on the system (folders with an
  index.theme that define at least one icon directory — cursor-only themes like
  Bibata are filtered out),
* ``SUGGESTED``    suggested sets, even if not installed, and the package that
  provides each. Package names were checked one by one on pacman/AUR (2026-10); the
  directory name is the REAL theme folder the package installs, and that is what
  goes into settings.conf.

The UI draws the preview with Gtk.IconTheme (``PREVIEW_ICONS``); the inheritance
chain (Inherits=) and size selection are left to GTK.
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IconSet:
    name: str          # theme directory, the value written to ICON_THEME_NAME
    label: str         # name shown in the UI
    package: str       # package that provides it
    aur: bool = False  # not in the official repos (needs paru/yay)


#: Suggested sets — the variant that fits a dark desktop was picked; the package's
#: light variants show up in the "Installed" list anyway once it is installed.
SUGGESTED: tuple[IconSet, ...] = (
    IconSet("Papirus-Dark", "Papirus", "papirus-icon-theme"),
    IconSet("breeze-dark", "Breeze", "breeze-icons"),
    IconSet("Adwaita", "Adwaita", "adwaita-icon-theme"),
    IconSet("Tela-circle-dark", "Tela Circle", "tela-circle-icon-theme-standard"),
    IconSet("Tela-circle-dracula-dark", "Tela Dracula", "tela-circle-icon-theme-dracula"),
    IconSet("Tela-circle-nord-dark", "Tela Nord", "tela-circle-icon-theme-nord"),
    IconSet("Qogir-Dark", "Qogir", "qogir-icon-theme"),
    IconSet("BeautyLine", "BeautyLine", "beautyline"),
    IconSet("Pop", "Pop", "pop-icon-theme"),
    IconSet("Cosmic", "Cosmic", "cosmic-icon-theme"),
    IconSet("elementary", "elementary", "elementary-icon-theme"),
    IconSet("Obsidian", "Obsidian", "obsidian-icon-theme"),
    IconSet("Colloid-Dark", "Colloid", "colloid-icon-theme-git", aur=True),
    IconSet("Fluent-dark", "Fluent", "fluent-icon-theme-git", aur=True),
    IconSet("WhiteSur-dark", "WhiteSur", "whitesur-icon-theme", aur=True),
    IconSet("McMojave-circle-dark", "McMojave", "mcmojave-circle-icon-theme-git", aur=True),
    IconSet("Reversal-dark", "Reversal", "reversal-icon-theme-git", aur=True),
    IconSet("Numix-Circle", "Numix Circle", "numix-circle-icon-theme-git", aur=True),
    IconSet("kora", "Kora", "kora-icon-theme", aur=True),
    IconSet("candy-icons", "Candy", "candy-icons-git", aur=True),
    IconSet("Gruvbox-Plus-Dark", "Gruvbox Plus", "gruvbox-plus-icon-theme-git", aur=True),
    IconSet("Nordzy-dark", "Nordzy", "nordzy-icon-theme-git", aur=True),
    IconSet("Vimix-dark", "Vimix", "vimix-icon-theme", aur=True),
    IconSet("zafiro-dark", "Zafiro", "zafiro-icon-theme", aur=True),
    IconSet("Flat-Remix-Blue-Dark", "Flat Remix", "flat-remix", aur=True),
    IconSet("Yaru", "Yaru", "yaru-icon-theme", aur=True),
)

#: Sample icons shown on the card: (candidate names…) — the first one found in the
#: theme is drawn. Folder, terminal, browser, settings, editor, music: a set's
#: character shows most in these.
PREVIEW_ICONS: tuple[tuple[str, ...], ...] = (
    ("folder", "inode-directory"),
    ("utilities-terminal", "terminal", "org.gnome.Terminal"),
    ("firefox", "web-browser", "internet-web-browser"),
    ("preferences-system", "systemsettings", "preferences-desktop"),
    ("accessories-text-editor", "text-editor"),
    ("multimedia-audio-player", "audio-x-generic"),
)

#: Folders that look like themes but should not be offered to the user.
_HIDDEN = {"default", "hicolor", "locolor", "highcontrast", "adwaitalegacy"}


def _search_dirs() -> list[Path]:
    return [
        Path.home() / ".icons",
        Path.home() / ".local/share/icons",
        Path("/usr/share/icons"),
        Path("/usr/local/share/icons"),
    ]


def _read_index(theme_dir: Path) -> configparser.ConfigParser | None:
    index = theme_dir / "index.theme"
    if not index.is_file():
        return None
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        parser.read(index, encoding="utf-8")
    except (configparser.Error, OSError, UnicodeDecodeError):
        return None
    return parser if parser.has_section("Icon Theme") else None


def _is_icon_theme(theme_dir: Path) -> bool:
    """Whether the theme defines real icon directories (not just a cursor)."""
    parser = _read_index(theme_dir)
    if parser is None:
        return False
    # Adwaita marks itself Hidden=true (to stay out of the GNOME picker), but it
    # is a valid and commonly chosen set.
    if (parser.get("Icon Theme", "Hidden", fallback="").lower() == "true"
            and theme_dir.name.lower() != "adwaita"):
        return False
    dirs = parser.get("Icon Theme", "Directories", fallback="").strip()
    return bool(dirs.strip(", "))


def available() -> list[str]:
    """Directory names of the icon themes installed on the system (alphabetical)."""
    found: dict[str, str] = {}
    for base in _search_dirs():
        if not base.is_dir():
            continue
        try:
            entries = sorted(base.iterdir())
        except OSError:
            continue
        for entry in entries:
            key = entry.name.lower()
            if key in _HIDDEN or key in found or not entry.is_dir():
                continue
            if _is_icon_theme(entry):
                found[key] = entry.name
    return sorted(found.values(), key=str.lower)


def display_name(theme: str) -> str:
    """Name= from index.theme (or the directory name)."""
    for base in _search_dirs():
        parser = _read_index(base / theme)
        if parser is not None:
            return parser.get("Icon Theme", "Name", fallback=theme) or theme
    return theme


def suggestion(theme: str) -> IconSet | None:
    wanted = theme.lower()
    return next((s for s in SUGGESTED if s.name.lower() == wanted), None)
