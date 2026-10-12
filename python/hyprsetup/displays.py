"""Keeping the nwg-displays monitor layout across profiles.

nwg-displays writes the layout to ~/.config/hypr/monitors.conf (+ workspaces.conf,
and their Lua equivalents). When a profile (rice.py) replaced ~/.config/hypr with
the author's, these files were moved into the backup, and the author's main file
never loaded them anyway: every profile switch reset the displays to
"preferred, auto". Changes made in nwg-displays while a profile was installed were
also deleted together with the author's folder on uninstall.

Fix: the files nwg-displays generates are stored separately (``save``), put back into
~/.config/hypr after every install/uninstall (``restore``), and load lines are
appended to the author's main file (rice._hook_keybind_overlay).
"""

from __future__ import annotations

import shutil
from pathlib import Path

#: Relative to ~/.config/hypr; what nwg-displays writes (in conf and Lua mode).
FILES: tuple[str, ...] = (
    "monitors.conf", "workspaces.conf",
    "monitors.lua", "workspaces.lua",
    "hyprland/monitors.lua", "hyprland/workspaces.lua",
)


def store_dir(home: Path) -> Path:
    return home / ".config" / "hyprsetup" / "displays"


def _is_nwg(path: Path) -> bool:
    from .apply import foreign_owner      # apply → rice → displays import cycle

    owner = foreign_owner(path) if path.is_file() else None
    return bool(owner) and owner.lower().startswith("nwg")


def save(home: Path) -> list[str]:
    """Stores the nwg-displays files from ~/.config/hypr (newer overwrites older)."""
    hypr, store = home / ".config" / "hypr", store_dir(home)
    saved = []
    for rel in FILES:
        src = hypr / rel
        if not _is_nwg(src):
            continue
        dest = store / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        saved.append(rel)
    return saved


def saved(home: Path) -> list[str]:
    return [rel for rel in FILES if (store_dir(home) / rel).is_file()]


def restore(home: Path) -> list[str]:
    """Puts the stored layout back into ~/.config/hypr."""
    hypr, store = home / ".config" / "hypr", store_dir(home)
    if not hypr.is_dir():
        return []
    restored = []
    for rel in saved(home):
        dest = hypr / rel
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.is_symlink():
                dest.unlink()
            shutil.copyfile(store / rel, dest)
        except OSError:
            continue
        restored.append(str(dest))
    return restored


def conf_lines(home: Path) -> list[str]:
    """source lines to append to the author's hyprland.conf."""
    return [f"source = ~/.config/hypr/{rel}" for rel in saved(home)
            if rel.endswith(".conf")]


def lua_lines(home: Path) -> list[str]:
    """require lines to append to the author's hyprland.lua."""
    names = [rel.removesuffix(".lua").replace("/", ".") for rel in saved(home)
             if rel.endswith(".lua")]
    return [f'pcall(require, "{name}")' for name in names]


def _hyprctl_json(*args: str):
    import json
    import subprocess

    try:
        out = subprocess.run(["hyprctl", *args, "-j"], capture_output=True,
                             text=True, timeout=5).stdout
        return json.loads(out)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def focused_monitor() -> str:
    monitors = _hyprctl_json("monitors") or []
    return next((m["name"] for m in monitors if m.get("focused")), "")


def primary_monitor() -> str:
    """Primary display: the display of workspace 1 (the one focused at login).

    Layer programs that do not specify a display (e.g. a quickshell PanelWindow
    without ``screen``) land on whichever display is focused when they start. At
    login that is always the primary display; on a profile switch, however, the
    bar ended up on whatever display the cursor was on.
    """
    monitors = _hyprctl_json("monitors") or []
    names = {m.get("name") for m in monitors}
    for rule in _hyprctl_json("workspacerules") or []:
        if rule.get("workspaceString") == "1" and rule.get("monitor") in names:
            return rule["monitor"]
    for ws in _hyprctl_json("workspaces") or []:
        if ws.get("id") == 1 and ws.get("monitor") in names:
            return ws["monitor"]
    return min(monitors, key=lambda m: m.get("id", 0))["name"] if monitors else ""


def focus_monitor(name: str) -> None:
    import subprocess

    if name:
        subprocess.run(["hyprctl", "dispatch", "focusmonitor", name],
                       capture_output=True)
