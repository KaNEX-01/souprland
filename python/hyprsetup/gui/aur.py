"""AUR badge: everything that comes from the AUR gets the same colored marker in the UI.

AUR packages are unsigned community packages; before picking a setting or a
profile the user should be able to see whether it needs the AUR (README
"Security"). Plain "AUR" text got lost inside the surrounding text; the badge is
a pill filled with the theme's accent color and looks the same on every page.
Always use this badge instead of a colored word inside a sentence.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from .util import ensure_css  # noqa: E402

TOOLTIP = ("Installed from the AUR: unsigned community package. Review the "
           "PKGBUILD before installing.")

_CSS = """
.hs-aur {
    background-color: @accent_bg_color;
    color: @accent_fg_color;
    font-weight: 800;
    font-size: 0.72em;
    letter-spacing: 0.06em;
    border-radius: 999px;
    padding: 1px 7px;
}
"""


def badge(packages: list[str] | None = None) -> Gtk.Label:
    """Small "AUR" pill; its tooltip lists which packages come from the AUR."""
    ensure_css(_CSS)
    label = Gtk.Label(label="AUR", valign=Gtk.Align.CENTER,
                      halign=Gtk.Align.START)
    label.add_css_class("hs-aur")
    tip = TOOLTIP
    if packages:
        tip += "\n\n" + ", ".join(packages)
    label.set_tooltip_text(tip)
    return label


def titled(title: Gtk.Widget, packages: list[str] | None) -> Gtk.Widget:
    """Title + badge next to it (if AUR). Otherwise the title itself."""
    if not packages:
        return title
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6,
                  hexpand=title.get_hexpand())
    title.set_hexpand(False)
    box.append(title)
    box.append(badge(packages))
    return box


def stacked(text: Gtk.Widget, packages: list[str] | None) -> Gtk.Widget:
    """Badge on top, text (e.g. package list) below. Otherwise just the text."""
    if not packages:
        return text
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                  hexpand=text.get_hexpand(), valign=text.get_valign())
    box.append(badge(packages))
    box.append(text)
    return box
