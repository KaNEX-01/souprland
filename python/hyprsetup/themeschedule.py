"""Automatic day/night theme (THEME_SCHEDULE).

THEME_DAY is applied during daytime and THEME_NIGHT at night; the system color
scheme (COLOR_SCHEME, GTK/Qt light/dark) follows the theme's background.

The trigger is a systemd user timer (templates/systemd/user/hyprsetup-theme.*):
``python3 -m hyprsetup theme-schedule`` runs at both switch times and at login.
The command works out which theme should be active right now; if the theme in
settings.conf differs, it writes it and applies the settings (the same path as a
theme change in the settings app).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from . import themes


def _minutes(text: str, fallback: int) -> int:
    try:
        hours, minutes = (int(part) for part in (text or "").strip().split(":", 1))
        if 0 <= hours < 24 and 0 <= minutes < 60:
            return hours * 60 + minutes
    except ValueError:
        pass
    return fallback


def desired(values: dict[str, str], now: dt.datetime | None = None) -> str:
    """The theme that should be active right now; "" if scheduling is off."""
    if (values.get("THEME_SCHEDULE") or "false").lower() not in ("true", "1", "yes", "on"):
        return ""
    now = now or dt.datetime.now()
    current = now.hour * 60 + now.minute
    day = _minutes(values.get("THEME_DAY_START", ""), 7 * 60)
    night = _minutes(values.get("THEME_NIGHT_START", ""), 19 * 60)
    if day <= night:
        daytime = day <= current < night
    else:                                   # e.g. day 20:00, night 06:00
        daytime = current >= day or current < night
    theme = values.get("THEME_DAY" if daytime else "THEME_NIGHT", "")
    return theme if theme in themes.THEMES else ""


def changes(values: dict[str, str], now: dt.datetime | None = None) -> dict[str, str]:
    """Changes to write to settings.conf (empty = theme is already correct)."""
    theme = desired(values, now)
    if not theme:
        return {}
    scheme = "light" if themes.is_light(themes.THEMES[theme]) else "dark"
    out: dict[str, str] = {}
    if values.get("THEME") != theme:
        out["THEME"] = theme
        out["CUSTOM_COLORS"] = ""           # manual colors belonged to the old theme
    if values.get("COLOR_SCHEME") != scheme:
        out["COLOR_SCHEME"] = scheme
    return out


def run(root: Path, catalog_path: Path) -> str:
    """Switches and applies the theme if needed; returns what was done."""
    from .apply import Applier
    from .catalog import Catalog
    from . import keybinds as keybinds_mod
    from .gui.state import SetupState, config_path

    path = config_path()
    if not path.is_file():
        return "no settings file"
    catalog = Catalog.load(catalog_path)
    state = SetupState(catalog)
    state.load_conf(path)
    todo = changes(state.values)
    if not todo:
        return "theme already correct"
    for key, value in todo.items():
        state.values[key] = value
    state.save_conf(path)
    binds = keybinds_mod.load_default(root)
    result = Applier(root, catalog, binds).apply(state.values, sorted(state.selected))
    if result.errors:
        return f"theme {todo.get('THEME', state.values.get('THEME'))}: {result.errors[0]}"
    return f"theme → {state.values.get('THEME')} ({state.values.get('COLOR_SCHEME')})"
