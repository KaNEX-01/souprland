"""MOD + I panel: the floating, slide-down form of the settings app.

The panel has NO separate UI. It used to: its own window, its own sliders
and only part of the schema. The result was that half of the settings users
looked for were missing from the panel, and the panel turned into one
endlessly long list. Now MOD + I opens the full app itself
(``gui/app.py``): tabs on the left (Home, Profiles, Appearance,
Bar Presets, Status Bar, Terminal, Launcher, Widgets, Behavior,
Session, Keybindings, Applications, Components, Displays, System), the
selected page on the right; profiles/presets, color editor, shortcut
capture, display detection and live previews included.

The only difference is how it appears: because its window class is
``dev.hyprsetup.Quick``, the Hyprland rules (templates/hypr/windowrules.conf.tmpl)
make it a floating, centered panel that slides down from the top; its size
is proportional to the screen (render.py:QUICK_PANEL_*) and Esc closes it.
The window opened from the menu or the command line (``hyprsetup``) has
class ``dev.hyprsetup.Gui``; it floats and slides by the same rules, but it
only opens on the Home page and Esc does not close it.

This module only starts that mode; constants are not kept here but taken
from ``gui/app.py`` so there is no second source of truth.
"""

from __future__ import annotations

from pathlib import Path

from .app import QUICK_APP_ID, run as run_app  # noqa: F401

__all__ = ["QUICK_APP_ID", "run"]


def run(root: Path, catalog_path: Path, templates: Path,
        daemon: bool = False, show: bool = False) -> int:
    """MOD + I: open the settings app in panel mode."""
    return run_app(root, catalog_path, templates, panel=True,
                   daemon=daemon, show=show)
