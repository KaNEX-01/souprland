"""Launcher entry for the settings app (souprland.desktop).

install.sh used to write the entry only on a full install: the ``hyprsetup.desktop``
left over from an old install (old Turkish name, generic icon) stayed in place,
and anyone who deleted the entry or ran from the repo never found the app in the
launcher. Now this module is the only writer: install.sh calls it, and the settings
app checks it with ``ensure()`` on every start (and after self-update) — the file is
left untouched if the content is the same.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

_DATA = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
APPS = _DATA / "applications"
ENTRY = APPS / "souprland.desktop"
#: Old name; removed if present so the launcher does not show two settings apps.
LEGACY = APPS / "hyprsetup.desktop"
ICON_DIR = _DATA / "icons/hicolor/scalable/apps"
#: Installed wrappers; "hyprsetup" is the name used by old installs (it accepts
#: the same subcommands).
BINS = (Path.home() / ".local/bin/souprland", Path.home() / ".local/bin/hyprsetup")


def _exec_path(source: Path | None) -> str | None:
    """The installed wrapper; otherwise hyprsetup-gui in the repo."""
    for wrapper in BINS:
        if wrapper.is_file() and os.access(wrapper, os.X_OK):
            return str(wrapper)
    if source is not None:
        gui = source / "hyprsetup-gui"
        if gui.is_file():
            return str(gui)
    return None


def content(exec_path: str) -> str:
    installed = exec_path in {str(b) for b in BINS}
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Name=Souprland",
        "GenericName=Hyprland Settings",
        "Comment=Theme, bar, icons, keybindings and behavior — "
        "changes apply instantly",
        f"Exec={exec_path}",
        "Icon=souprland",
        "StartupWMClass=dev.hyprsetup.Gui",
        "Terminal=false",
        "Categories=Settings;DesktopSettings;",
        "Keywords=hyprland;hyprsetup;souprland;settings;config;theme;"
        "icon;bar;wayland;",
    ]
    if installed:
        # Right-click / launcher sub-actions; the subcommands exist only in the
        # installed wrapper (install.sh:install_app_step).
        lines.append("Actions=quick;cheatsheet;")
        lines += [
            "", "[Desktop Action quick]", "Name=Quick panel",
            f"Exec={exec_path} --quick",
            "", "[Desktop Action cheatsheet]", "Name=Keybinding cheatsheet",
            f"Exec={exec_path} cheatsheet",
        ]
    return "\n".join(lines) + "\n"


def _install_icon(source: Path | None) -> bool:
    target = ICON_DIR / "souprland.svg"
    if target.is_file():
        return False
    for base in (source, _DATA / "hyprsetup"):
        icon = base / "assets/souprland.svg" if base else None
        if icon is not None and icon.is_file():
            try:
                ICON_DIR.mkdir(parents=True, exist_ok=True)
                shutil.copy2(icon, target)
                return True
            except OSError:
                return False
    return False


def ensure(source: Path | None = None) -> bool:
    """Writes the entry if needed; returns True if anything changed."""
    exec_path = _exec_path(source)
    if exec_path is None:
        return False
    changed = _install_icon(source)
    text = content(exec_path)
    try:
        current = ENTRY.read_text(encoding="utf-8") if ENTRY.is_file() else ""
    except OSError:
        current = ""
    try:
        if current != text:
            APPS.mkdir(parents=True, exist_ok=True)
            ENTRY.write_text(text, encoding="utf-8")
            changed = True
        if LEGACY.is_file():
            LEGACY.unlink()
            changed = True
    except OSError:
        return changed
    if changed:
        for argv in (["update-desktop-database", str(APPS)],
                     ["gtk-update-icon-cache", "-qtf", str(ICON_DIR.parents[1])]):
            if shutil.which(argv[0]):
                subprocess.run(argv, check=False, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    return changed
