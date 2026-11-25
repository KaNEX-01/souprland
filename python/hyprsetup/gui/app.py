"""hyprsetup graphical interface — GTK4 / libadwaita."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango  # noqa: E402

from ..catalog import Catalog  # noqa: E402
from .. import cursors as cursors_mod  # noqa: E402
from .. import icons as icons_mod  # noqa: E402
from .. import conffile  # noqa: E402
from .. import deps as deps_mod  # noqa: E402
from .. import mix as mix_mod  # noqa: E402
from .. import rice as rice_mod  # noqa: E402
from .. import transition as transition_mod  # noqa: E402
from .. import ricebar as ricebar_mod  # noqa: E402
from .. import keybinds as keybinds_mod  # noqa: E402
from .. import presets as presets_mod  # noqa: E402
from .. import settings as schema  # noqa: E402
from ..apply import Applier  # noqa: E402
from .. import render as render_mod  # noqa: E402
from .. import themes  # noqa: E402
from .login_page import LoginPage  # noqa: E402
from .tone import WallpaperSwatches  # noqa: E402
from . import aur as aur_mod  # noqa: E402
from . import behavior_diagrams  # noqa: E402
from .mix_preview import MixPreview  # noqa: E402
from . import welcome as welcome_mod  # noqa: E402
from .util import PICTURES, ensure_css, pick_file  # noqa: E402
from .wallcolors_page import WallColorsPage  # noqa: E402
from .wizard_page import WizardPage  # noqa: E402
from .preview import (AnimationDiagram, BarPreview, CursorSizeDiagram,  # noqa: E402
                      DesktopPreview, LauncherLayoutPreview,
                      LayoutDiagram, MouseInputDiagram, PaletteStrip, ShotPreview,
                      TerminalPreview,
                      ValuesPreview, WidgetPreview, WidgetSample,
                      rounded_path, _hex_to_rgb)
from .state import (DEFAULT_WIDGET_ENGINE, SetupState,  # noqa: E402
                    config_candidates, config_path)

APP_ID = "dev.hyprsetup.Gui"

#: Display name and icon name. Window classes, directories and the Python package
#: deliberately keep the old "hyprsetup" name: installed profiles' window
#: rules, systemd units and the ~/.config/hyprsetup state depend on it.
APP_NAME = "Souprland"
ICON_NAME = "souprland"

#: Window class of the MOD+I panel. SEPARATE from the full app's, because
#: the Hyprland window rules (templates/hypr/windowrules.*) only float the panel
#: and slide it in from the top; the window opened from the menu tiles normally.
QUICK_APP_ID = "dev.hyprsetup.Quick"

# Bar backends: same order as the "bar" category in config/components.json.
# When a new backend is added it must be added here too — the GUI's choice
# buttons and gallery badges come from this table.
_BAR_BACKENDS = (
    ("waybar", "Waybar"),
    ("hyprpanel", "HyprPanel"),
    ("quickshell-bar", "Quickshell"),
    ("wayle", "Wayle"),
)

# Badge text on the gallery card for non-Waybar backends: lets the user see
# which program will be pulled in before picking the card.
_BAR_BACKEND_BADGE = {
    "hyprpanel": "Requires HyprPanel",
    "quickshell-bar": "Requires Quickshell",
    "wayle": "Requires Wayle",
}

# Terminal and launcher axes: the same comparison as on the bar page.
# Each row asks the same question of all apps; the "Presets" row says which
# settings the presets actually change in that program —
# what the templates wire up (see render.py:_terminal_vars/_launcher_vars).
_APP_AXES = {
    "terminal": {
        "title": "Terminal",
        "category": "terminal",
        "page_title": "Terminal presets",
        "setting_group": "terminal",
        "apps": (("kitty", "kitty"), ("foot", "foot"),
                 ("alacritty", "Alacritty"), ("ghostty", "Ghostty"),
                 ("wezterm", "WezTerm")),
        "summary": {
            "kitty": "GPU-accelerated, most features: tabs/splits, "
                     "ligatures, its own graphics protocol.",
            "foot": "Pure Wayland, the lightest and fastest to open. Server mode "
                    "(footclient) shares memory.",
            "alacritty": "GPU-accelerated and minimal: no tabs/splits, "
                         "used with a multiplexer (tmux/zellij).",
            "ghostty": "Next-gen; GPU, native tabs/splits and the kitty graphics "
                       "protocol in one.",
            "wezterm": "Configured in Lua; has its own multiplexer and "
                       "keeps remote sessions without tmux.",
        },
        "rows": (
            ("Configuration", {"kitty": "kitty.conf", "foot": "foot.ini",
                              "alacritty": "alacritty.toml",
                              "ghostty": "config",
                              "wezterm": "wezterm.lua (Lua script)"}),
            ("Tabs / splits", {"kitty": "yes", "foot": "no",
                               "alacritty": "no", "ghostty": "yes",
                               "wezterm": "yes + its own multiplexer"}),
            ("Ligatures", {"kitty": "yes", "foot": "no",
                          "alacritty": "no", "ghostty": "yes",
                          "wezterm": "yes"}),
            ("Image display", {"kitty": "kitty graphics protocol",
                                 "foot": "sixel",
                                 "alacritty": "no",
                                 "ghostty": "kitty graphics protocol",
                                 "wezterm": "iTerm2 protocol + sixel"}),
            ("Presets", {"kitty": "all six settings apply",
                        "foot": "all six settings apply",
                        "alacritty": "all six settings apply",
                        "ghostty": "scrollback is a BYTE limit, not lines; "
                                   "converted at ~1 KB per line",
                        "wezterm": "all six apply; cursor shape and "
                                   "blinking merge into one key"}),
        ),
    },
    "launcher": {
        "title": "Launcher",
        "category": "launcher",
        "page_title": "Launcher presets",
        "setting_group": "launcher",
        "apps": (("wofi", "wofi"), ("rofi", "rofi"),
                 ("fuzzel", "fuzzel"), ("walker", "walker"),
                 ("tofi", "tofi")),
        "summary": {
            "wofi": "Classic GTK3-based option; themed with CSS, "
                    "the most readable configuration.",
            "rofi": "The most powerful mode system (drun/run/window/ssh) and its own "
                    "theme language (rasi).",
            "fuzzel": "Pure Wayland, the lightest; a single ini file.",
            "walker": "GTK4, modern module-based launcher.",
            "tofi": "Written for startup speed, the most minimal option. No "
                    "icon support.",
        },
        "rows": (
            ("Configuration", {"wofi": "config + style.css",
                              "rofi": "config.rasi + theme (.rasi)",
                              "fuzzel": "fuzzel.ini",
                              "walker": "style.css only (theme)",
                              "tofi": "single file: config"}),
            ("Modes", {"wofi": "drun · dmenu",
                        "rofi": "drun · run · window · ssh · dmenu",
                        "fuzzel": "drun · dmenu",
                        "walker": "module-based (apps, calculator…)",
                        "tofi": "drun · run · dmenu"}),
            ("Icons", {"wofi": "yes", "rofi": "yes", "fuzzel": "yes",
                      "walker": "yes", "tofi": "NO — by design"}),
            ("Presets", {"wofi": "all seven settings apply",
                        "rofi": "all seven apply",
                        "fuzzel": "six, all but icon size — fuzzel derives the icon "
                                  "from the row height",
                        "walker": "only opacity and icons — walker's "
                                  "own configuration isn't generated, only "
                                  "the theme CSS",
                        "tofi": "icon settings have no effect; the other five "
                                "apply"}),
        ),
    },
}


#: Terminal startup screen cards (Terminal page): (title, description,
#: values written together). A card shows as selected when all its values
#: match the state. Two separate questions: WHICH logo (_FETCH_LOGOS) and HOW
#: image logos are drawn (_FETCH_STYLES). Style cards used to switch the logo
#: to Souprland as well; a user who had picked their own image lost it on
#: pressing "Dotted".
_FETCH_LOGOS: tuple[tuple[str, str, dict[str, str]], ...] = (
    ("Off", "Nothing at startup", {"TERM_FETCH": "off"}),
    ("Distro logo", "fastfetch's classic look",
     {"TERM_FETCH": "on", "TERM_LOGO": "distro"}),
    ("Small logo", "Takes little space", {"TERM_FETCH": "on", "TERM_LOGO": "small"}),
    ("Souprland", "The project's logo", {"TERM_FETCH": "on", "TERM_LOGO": "souprland"}),
    ("Your own image", "An image from your computer",
     {"TERM_FETCH": "on", "TERM_LOGO": "image"}),
    ("No logo", "Info lines only", {"TERM_FETCH": "on", "TERM_LOGO": "none"}),
)
#: Drawing style of an image logo (Souprland or your own image).
_FETCH_STYLES: tuple[tuple[str, str, dict[str, str]], ...] = (
    ("Real image", "Pixel-perfect in kitty, Ghostty, WezTerm",
     {"TERM_LOGO_STYLE": "image"}),
    ("Dotted", "Colored dots; comes out full of the photo's colors",
     {"TERM_LOGO_STYLE": "braille", "TERM_LOGO_MONO": "false"}),
    ("Dotted mono", "Turns the photo into a dot pattern",
     {"TERM_LOGO_STYLE": "braille", "TERM_LOGO_MONO": "true"}),
    ("Pixel", "Made of blocks, like an old game",
     {"TERM_LOGO_STYLE": "block", "TERM_LOGO_MONO": "false"}),
    ("Letters", "ASCII art",
     {"TERM_LOGO_STYLE": "ascii", "TERM_LOGO_MONO": "false"}),
)


# Short note under each column title in the preset gallery: says in one line
# which kinds that backend offers (and which it can't).
_BAR_COLUMN_NOTE = {
    "waybar": "Plain, dense, islands, dock, vertical rail, separators, glass… "
              "the widest range. Structural details only show here.",
    "hyprpanel": "Plain, media, bottom dock, counter and menu-heavy presets. "
                 "No vertical layout — HyprPanel only draws top/bottom.",
    "quickshell-bar": "Plain, dense, bottom capsule and vertical rail. Limited "
                      "to eight modules but runs in a single process.",
    "wayle": "Plain, dashboard and vertical rail. Notifications/OSD/wallpaper "
             "come built in, so no separate component is needed.",
}

# One-sentence summary under each backend column's title.
_BAR_BACKEND_SUMMARY = {
    "waybar": "The most common option and the backend the presets were designed "
              "for. Installed from the repos, lightweight.",
    "hyprpanel": "Rich AGS/GTK-based panel: has menus like a dashboard and a "
                 "notification center. Built from source, heavy.",
    "quickshell-bar": "QtQuick-based; draws the bar and desktop widgets in a "
                      "single process. The leanest module set.",
    "wayle": "Full shell written in Rust/GTK4: bar + notifications + OSD + "
             "wallpaper in one. TOML, live reload.",
}


def _bar_backend_rows() -> tuple[tuple[str, dict[str, str]], ...]:
    """Rows of the backend comparison table.

    The counts are read from the real mapping tables in render.py — so the
    table stays current when a module or style is added instead of a
    hand-written number silently going stale.
    """
    waybar_modules = (len(render_mod.BAR_MODULES)
                      - len(render_mod.HYPRPANEL_ONLY_MODULES))
    hyprpanel_modules = len(render_mod._HYPRPANEL_MODULE_MAP)
    quickshell_modules = len(render_mod.QS_BAR_MODULES)
    wayle_modules = len(render_mod._WAYLE_MODULE_MAP)
    ws_styles = len(render_mod.BAR_WS_STYLES)
    theme_keys = len(render_mod._HYPRPANEL_THEME_KEYS)
    return (
        ("Configuration", {
            "waybar": "config.jsonc + style.css",
            "hyprpanel": f"single config.json — {theme_keys} theme keys",
            "quickshell-bar": "single shell.qml (QML)",
            "wayle": "single config.toml — live reload",
        }),
        ("Modules", {
            "waybar": f"{waybar_modules} modules",
            "hyprpanel": f"{hyprpanel_modules} modules",
            "quickshell-bar": f"{quickshell_modules} modules",
            "wayle": f"{wayle_modules} modules",
        }),
        ("Position", {
            "waybar": "top · bottom · left · right",
            "hyprpanel": "top · bottom only (vertical falls back to top)",
            "quickshell-bar": "top · bottom · left · right",
            "wayle": "top · bottom · left · right",
        }),
        ("Workspace style", {
            "waybar": f"all {ws_styles} styles",
            "hyprpanel": "numbered / icons + underline·highlight·color; "
                         "the rest fall back to the closest",
            "quickshell-bar": "fixed dot indicator — style choice is ignored",
            "wayle": "its own indicator — style choice is ignored",
        }),
        ("Bar presets", {
            "waybar": "all come out exactly",
            "hyprpanel": "size and color apply; dock·separator·islands structure "
                         "isn't shown",
            "quickshell-bar": "size and color apply; structural details "
                              "aren't shown",
            "wayle": "size and color apply; corner radius is a five-step "
                     "scale, not pixels",
        }),
        ("Unique to it", {
            "waybar": "separator modules ([ ]) and the widest module/style support",
            "hyprpanel": "dashboard, notification center, media menu, weather "
                         "— no equivalent in Waybar",
            "quickshell-bar": "single process if the widget engine is also Quickshell; "
                              "no system tray",
            "wayle": "built-in notifications/OSD/wallpaper — CONFLICTS with mako, "
                     "swaync, swayosd and swww",
        }),
    )


# --------------------------------------------------------------- widgets -
class SwatchStrip(Gtk.DrawingArea):
    """Shows a theme's colors as a strip."""

    def __init__(self, palette, width: int = 96, height: int = 26):
        super().__init__()
        # palette is a fixed dict or a callable returning the current palette
        self._source = palette
        self.set_content_width(width)
        self.set_content_height(height)
        self.set_valign(Gtk.Align.CENTER)
        self.set_draw_func(self._draw)

    def _draw(self, _area, cr, width, height) -> None:
        palette = self._source() if callable(self._source) else self._source
        keys = ("BG", "SURFACE", "ACCENT", "ACCENT2", "GREEN", "YELLOW", "RED")
        step = width / len(keys)
        for index, key in enumerate(keys):
            cr.set_source_rgb(*_hex_to_rgb(palette[key]))
            first, last = index == 0, index == len(keys) - 1
            radius = height / 2
            if first or last:
                rounded_path(cr, index * step, 0, step, height, radius, 2)
                cr.fill()
                # Fill the inner side of the rounded corner
                cr.rectangle(index * step + (0 if last else radius), 0,
                             step - radius, height)
                cr.fill()
            else:
                cr.rectangle(index * step, 0, step + 0.5, height)
                cr.fill()


class CursorGlyph(Gtk.DrawingArea):
    """Draws the real pointer image of a cursor theme.

    If the theme is installed, ``cursors.pointer_surface`` returns the real
    Xcursor image and it is drawn 1:1 here. If not (e.g. a suggestion that will
    come with the install but hasn't arrived yet) it falls back to a simple arrow
    sketch — at least hinting at the shape instead of leaving it blank.
    """

    def __init__(self, theme_name: str, size: int = 30):
        super().__init__()
        self._theme = theme_name
        self.set_content_width(size)
        self.set_content_height(size)
        self.set_valign(Gtk.Align.CENTER)
        self.set_halign(Gtk.Align.CENTER)
        self.set_draw_func(self._draw)

    def _draw(self, _area, cr, width, height) -> None:
        surface = cursors_mod.pointer_surface(self._theme, max(width, height))
        if surface is not None:
            sw, sh = surface.get_width(), surface.get_height()
            scale = min(width / sw, height / sh, 1.0) or 1.0
            cr.save()
            cr.translate((width - sw * scale) / 2, (height - sh * scale) / 2)
            cr.scale(scale, scale)
            cr.set_source_surface(surface, 0, 0)
            cr.paint()
            cr.restore()
            return
        # Placeholder: a suggested theme that isn't installed — simple arrow sketch.
        cr.save()
        cr.translate(width * 0.32, height * 0.2)
        s = min(width, height) * 0.6
        cr.move_to(0, 0)
        cr.line_to(0, s)
        cr.line_to(s * 0.28, s * 0.78)
        cr.line_to(s * 0.46, s)
        cr.line_to(s * 0.62, s * 0.86)
        cr.line_to(s * 0.42, s * 0.62)
        cr.line_to(s * 0.7, s * 0.52)
        cr.close_path()
        cr.set_source_rgba(0.5, 0.5, 0.5, 0.35)
        cr.fill_preserve()
        cr.set_source_rgba(0.5, 0.5, 0.5, 0.6)
        cr.set_line_width(1.2)
        cr.stroke()
        cr.restore()


def esc(text: str) -> str:
    """Adw row titles are parsed as Pango markup; '&' etc. must be escaped.

    Only used where markup is parsed (Adw.*Row titles/subtitles,
    PreferencesGroup). A plain ``Gtk.Label`` doesn't parse markup —
    escaping there breaks the text: "widget's" shows up on screen as
    "widget&apos;s".
    """
    return GLib.markup_escape_text(text or "")


#: Backend id → short name used in tables/notes.
_BACKEND_LABEL = dict(_BAR_BACKENDS)


#: Fine-tuning for the layout chips. The default button padding makes the
#: chips needlessly large; since a zone can hold 8-10 modules, the row count
#: grew quickly. The provider is installed inside MainWindow (not in the app
#: class): test/preview paths instantiate MainWindow directly without going
#: through do_activate.
_CHIP_CSS = """
.hs-wp-card { padding: 0; }
.hs-wp-thumb { border-radius: 12px 12px 0 0; }
.hs-wp-on { box-shadow: inset 0 0 0 2px @accent_color; }
.hs-search-hit {
    background-color: alpha(@accent_bg_color, 0.22);
    transition: background-color 250ms ease-out;
}
.hs-chip button { padding-top: 2px; padding-bottom: 2px;
                  padding-left: 10px; padding-right: 10px;
                  min-height: 26px; }
.hs-chip button.hs-chip-close { padding-left: 6px; padding-right: 6px;
                                min-width: 22px; }
.hs-chip-unsupported { opacity: 0.55; }
.hs-mix-card { padding: 0; border-radius: 12px; }
.hs-mix-card > box { border-radius: 12px; }
.hs-mix-selected { box-shadow: inset 0 0 0 3px @accent_color; }
.hs-mix-step { padding: 6px 2px; border-radius: 12px; }
.hs-mix-step:checked { background: alpha(@accent_bg_color, 0.16); }
.hs-step-dot { min-width: 26px; min-height: 26px; border-radius: 999px;
               font-weight: 700; background: alpha(currentColor, 0.12); }
.hs-step-dot.hs-step-done { background: @accent_bg_color; color: @accent_fg_color; }
.hs-mix-step:checked .hs-step-dot { background: @window_fg_color;
                                    color: @window_bg_color; }
.hs-mix-own { border: 2px dashed alpha(currentColor, 0.3); border-radius: 8px; }
.hs-hero-pill { padding: 2px 9px; border-radius: 999px; font-weight: 700;
                background: alpha(currentColor, 0.10); }
.hs-hero-pill-on { background: @accent_bg_color; color: @accent_fg_color; }
"""


def _backend_modules(backend: str) -> set[str]:
    """Generic module names a backend ACTUALLY draws.

    All four backends read the same BAR_MODULES_* list but none of them can draw
    all 30 modules: Waybar doesn't know the HyprPanel-specific ones (dashboard,
    weather…), Quickshell knows only 8 modules, Wayle has no equivalent for
    "updates" and "temperature". The source is the real mapping tables in
    render.py — keeping a hand-written list here would silently go stale when
    a table changes.
    """
    if backend == "waybar":
        return set(render_mod.BAR_MODULES) - set(render_mod.HYPRPANEL_ONLY_MODULES)
    if backend == "hyprpanel":
        return set(render_mod._HYPRPANEL_MODULE_MAP)
    if backend == "quickshell-bar":
        return set(render_mod.QS_BAR_MODULES)
    if backend == "wayle":
        return set(render_mod._WAYLE_MODULE_MAP)
    return set(render_mod.BAR_MODULES)


def backend_note(setting: schema.Setting, active: str) -> str:
    """Says in one line whether the setting applies to the selected bar backend.

    All four backends read the same BAR_* settings but can't apply all of them (see
    settings.Setting.backends). Without the note, users turned a slider that did
    nothing, saw no result and assumed the setting was broken.
    """
    if not setting.backends:
        return ""
    names = " · ".join(_BACKEND_LABEL.get(b, b) for b in setting.backends)
    if active and active not in setting.backends:
        return (f"⚠ No effect on the selected backend ({_BACKEND_LABEL.get(active, active)}) "
                f"— only: {names}")
    return f"Applies to: {names}"


def _help_row(setting: schema.Setting, active_backend: str = "") -> str:
    note = backend_note(setting, active_backend)
    if not note:
        return setting.help or ""
    return f"{setting.help}\n{note}" if setting.help else note


def _forward_scroll(_controller, _dx, dy: float, widget: Gtk.Widget) -> bool:
    """Hand the mouse wheel to the PAGE, not the widget.

    Sliders (Gtk.Scale) and spinners (Adw.SpinRow) use the wheel to change their
    own value. Settings pages are long, so users scroll the list with the
    wheel, and when the pointer passed over a slider that setting changed
    WITHOUT THEM NOTICING — and since every change is applied instantly, the
    desktop broke at that moment too.

    The event is consumed in the CAPTURE phase (so it never reaches the widget)
    and the vertical scroll amount is applied by hand to the nearest
    Gtk.ScrolledWindow, so the page keeps scrolling normally.
    """
    scroller = widget.get_ancestor(Gtk.ScrolledWindow)
    if scroller is not None:
        adjustment = scroller.get_vadjustment()
        step = max(adjustment.get_step_increment(), 50)
        top = max(adjustment.get_lower(),
                  adjustment.get_upper() - adjustment.get_page_size())
        adjustment.set_value(
            min(top, max(adjustment.get_lower(),
                         adjustment.get_value() + dy * step)))
    return True                    # the event ends here


def no_scroll_change(widget: Gtk.Widget) -> Gtk.Widget:
    """Stops the wheel from changing this widget's VALUE.

    Must be applied to every value-carrying widget (slider, spinner); tools/test.sh
    builds the UI and checks that every Gtk.Scale/SpinRow carries this guard.
    """
    controller = Gtk.EventControllerScroll.new(
        Gtk.EventControllerScrollFlags.BOTH_AXES)
    controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    controller.connect("scroll", _forward_scroll, widget)
    widget.add_controller(controller)
    return widget


def requirement_note(setting: schema.Setting, catalog: Catalog) -> str:
    """"Requires: …" line — which value needs which program."""
    def title(dep: str) -> str:
        if dep.startswith(deps_mod.PKG_PREFIX):
            return dep[len(deps_mod.PKG_PREFIX):]
        comp = catalog.component(dep)
        return comp.title if comp else dep

    labels = dict(setting.choices)
    parts = []
    for value, needed in setting.requires.items():
        names = ", ".join(title(d) for d in needed)
        if value in (deps_mod.ANY_VALUE, "true") or not labels:
            parts.append(names)
        else:
            parts.append(f"{labels.get(value, value)}: {names}")
    return ("Requires — " + " · ".join(parts)) if parts else ""


def build_setting_row(setting: schema.Setting, state: SetupState,
                      sync: dict | None = None,
                      active_backend: str = "") -> Gtk.Widget:
    """Builds the matching libadwaita row from a setting in the schema.

    If ``sync`` is given, a callback that re-reads the row from the state is
    written to that dict under the setting key. The UI refreshing itself when a
    preset is applied relies on this, since values change in bulk.
    """
    subtitle = _help_row(setting, active_backend)
    requirement = requirement_note(setting, state.catalog)
    if requirement:
        subtitle = f"{subtitle}\n{requirement}" if subtitle else requirement

    def register(callback) -> None:
        if sync is not None:
            sync[setting.key] = callback

    def commit(value: str, revert) -> None:
        """Writes the value; if it needs a program, has that checked first.

        If the checker (MainWindow._require) finds something missing it asks the
        user; if they back out, ``revert`` pulls the row back to the old value in
        the state. The revert fires the same signal, but since the value now
        matches the state it isn't asked a second time.
        """
        if value == state.get(setting.key):
            return
        needed = deps_mod.triggered(setting.requires, value)
        guard = getattr(state, "require", None)
        if not needed or guard is None:
            state.set(setting.key, value)
            return
        guard(needed, setting.label,
              lambda: state.set(setting.key, value), revert)

    if setting.kind == "bool":
        row = Adw.SwitchRow(title=esc(setting.label), subtitle=esc(subtitle))

        def sync_bool() -> None:
            row.set_active(state.get(setting.key).lower() in ("true", "yes", "1"))

        sync_bool()
        row.connect("notify::active",
                    lambda r, _p: commit("true" if r.get_active() else "false",
                                         sync_bool))
        register(sync_bool)
        return row

    if setting.kind == "choice":
        labels = [label for _value, label in setting.choices]
        values = [value for value, _label in setting.choices]
        row = Adw.ComboRow(title=esc(setting.label), subtitle=esc(subtitle))
        # Adw.ComboRow, unlike its siblings, starts with use-markup OFF:
        # text escaped with esc() showed up on screen as "preset &apos;how&apos;".
        # It's brought in line with the other rows.
        row.set_use_markup(True)
        row.set_model(Gtk.StringList.new(labels))

        def sync_choice() -> None:
            current = state.get(setting.key)
            row.set_selected(values.index(current) if current in values else 0)

        sync_choice()
        row.connect("notify::selected",
                    lambda r, _p: commit(values[r.get_selected()], sync_choice))
        register(sync_choice)
        return row

    if setting.kind == "image":
        return _image_setting_row(setting, state, subtitle, register)

    if setting.kind in ("int", "float"):
        row = Adw.ActionRow(title=esc(setting.label), subtitle=esc(subtitle))
        digits = 0 if setting.kind == "int" else 3
        step = setting.step if setting.kind == "float" else max(1, setting.step)
        adjustment = Gtk.Adjustment(lower=setting.minimum, upper=setting.maximum,
                                    step_increment=step, page_increment=step * 5)
        try:
            adjustment.set_value(float(state.get(setting.key) or setting.default))
        except ValueError:
            adjustment.set_value(setting.minimum)

        scale = no_scroll_change(
            Gtk.Scale(adjustment=adjustment, digits=digits, hexpand=True))
        scale.set_draw_value(False)
        # In narrow panes (e.g. the left column the Appearance/Status Bar pages
        # share with the preview) a 210px minimum left no room for the row title
        # and wrapped even short labels like "Height" down to a single letter;
        # 140 still gives a usable slider.
        scale.set_size_request(140, -1)
        scale.set_valign(Gtk.Align.CENTER)

        value_label = Gtk.Label(width_chars=7, xalign=1.0)
        value_label.add_css_class("dim-label")
        value_label.add_css_class("numeric")

        def _format(value: float) -> str:
            text = f"{value:.0f}" if setting.kind == "int" else f"{value:g}"
            return f"{text}{setting.unit}" if setting.unit else text

        def _on_change(adj) -> None:
            value = adj.get_value()
            value_label.set_text(_format(value))
            state.set(setting.key,
                      str(int(value)) if setting.kind == "int" else f"{value:g}")

        adjustment.connect("value-changed", _on_change)
        value_label.set_text(_format(adjustment.get_value()))

        def _sync_number() -> None:
            try:
                adjustment.set_value(float(state.get(setting.key)
                                           or setting.default))
            except ValueError:
                pass

        register(_sync_number)
        row.add_suffix(scale)
        row.add_suffix(value_label)
        return row

    row = Adw.EntryRow(title=esc(setting.label))
    row.set_text(state.get(setting.key))
    if subtitle:
        row.set_tooltip_text(subtitle)
    row.connect("changed", lambda r: state.set(setting.key, r.get_text()))
    # Only write if different: re-assigning the same text emits "changed" and
    # a key missing from the state gets added as "" — this triggered a needless
    # apply round on every page selection at startup.
    register(lambda: row.get_text() != state.get(setting.key)
             and row.set_text(state.get(setting.key)))
    return row


#: Value written together when an image is chosen: picking a logo image also
#: switches the logo to "Your own image" (else the distro logo would stay).
_IMAGE_ALSO_SETS = {"TERM_LOGO_IMAGE": ("TERM_LOGO", "image")}
#: Longest side of the copy: the logo is drawn small, the background at window size.
_IMAGE_MAX_SIDE = {"TERM_LOGO_IMAGE": 1024}


def images_dir() -> Path:
    """PNG copies of images chosen in the UI (~/.config/hyprsetup/images)."""
    return config_path().parent / "images"


def _swatch_strip(colours: list[str], size: int) -> Gtk.Widget:
    """Small squares of palette colors (profile card, showcase)."""
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=max(2, size // 4),
                  valign=Gtk.Align.CENTER)
    for colour in colours:
        dot = Gtk.DrawingArea(content_width=size, content_height=size)
        rgb = tuple(int(colour.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))

        def draw(_a, cr, w, h, rgb=rgb):
            radius = min(w, h) * 0.3
            cr.new_sub_path()
            cr.arc(w - radius, radius, radius, -1.5708, 0)
            cr.arc(w - radius, h - radius, radius, 0, 1.5708)
            cr.arc(radius, h - radius, radius, 1.5708, 3.1416)
            cr.arc(radius, radius, radius, 3.1416, 4.7124)
            cr.close_path()
            cr.set_source_rgb(*rgb)
            cr.fill_preserve()
            cr.set_source_rgba(1, 1, 1, 0.12)
            cr.set_line_width(1)
            cr.stroke()
        dot.set_draw_func(draw)
        box.append(dot)
    return box


def store_image(key: str, source: Path, prefix: str = "") -> Path:
    """Converts the image to PNG in images_dir; deletes the setting's old copy.

    kitty reads both the background image and fastfetch's kitty-direct logo only
    as PNG; even if JPEG/WebP/SVG is picked, it's converted to PNG. The name
    carries a digest of the content: written under the same name, the setting's
    value wouldn't change and the new image wouldn't be applied.
    """
    import hashlib

    side = _IMAGE_MAX_SIDE.get(key, 2560)
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(source))
    scale = min(1.0, side / max(pixbuf.get_width(), pixbuf.get_height()))
    if scale < 1.0:
        pixbuf = pixbuf.scale_simple(max(1, round(pixbuf.get_width() * scale)),
                                     max(1, round(pixbuf.get_height() * scale)),
                                     GdkPixbuf.InterpType.BILINEAR)
    digest = hashlib.sha1(source.read_bytes()).hexdigest()[:10]
    folder = images_dir()
    folder.mkdir(parents=True, exist_ok=True)
    prefix = prefix or key.lower().replace("_", "-")
    family = key.lower().replace("_", "-").rsplit("-", 1)[0]     # term-bg, term-logo
    target = folder / f"{prefix}-{digest}.png"
    if not target.is_file():
        pixbuf.savev(str(target), "png", [], [])
    for old in folder.glob(f"{family}-*.png"):
        if old != target:
            old.unlink(missing_ok=True)
    return target


def _settings_paned(page: Gtk.Widget, preview: Gtk.Widget, position: int) -> Gtk.Paned:
    """Settings on the left (growing), a fixed-width preview column on the right."""
    return Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, wide_handle=True,
                     start_child=page, resize_start_child=True, shrink_start_child=False,
                     end_child=preview, resize_end_child=False, shrink_end_child=False,
                     position=position)


def choose_image(widget: Gtk.Widget, key: str, title: str, state: SetupState,
                 done=None, failed=None) -> None:
    """Lets the user pick a file, writes its PNG copy to the setting (see store_image)."""
    def chosen(path: Path) -> None:
        try:
            stored = store_image(key, path)
        except (GLib.Error, OSError) as exc:
            if failed:
                failed(f"Could not read image: {exc}")
            return
        also = _IMAGE_ALSO_SETS.get(key)
        if also:
            state.set(*also)
        state.set(key, str(stored))
        if done:
            done()

    pick_file(widget.get_root(), title, chosen, filter_name="Images",
              mimes=["image/*"], folder=PICTURES)


def _image_setting_row(setting: schema.Setting, state: SetupState, subtitle: str,
                       register) -> Gtk.Widget:
    """Image setting: small preview + "Choose…" + remove."""
    row = Adw.ActionRow(title=esc(setting.label))
    thumb = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True)
    frame = Gtk.Box(valign=Gtk.Align.CENTER, overflow=Gtk.Overflow.HIDDEN)
    frame.add_css_class("card")
    frame.set_size_request(64, 40)
    thumb.set_size_request(64, 40)
    frame.append(thumb)
    row.add_prefix(frame)
    clear = Gtk.Button(icon_name="edit-clear-symbolic", valign=Gtk.Align.CENTER,
                       tooltip_text="Remove image")
    clear.add_css_class("flat")
    pick = Gtk.Button(label="Choose…", valign=Gtk.Align.CENTER)
    row.add_suffix(clear)
    row.add_suffix(pick)

    def sync() -> None:
        value = state.get(setting.key)
        path = Path(value).expanduser() if value else None
        if path is not None and path.is_file():
            thumb.set_filename(str(path))
            row.set_subtitle(esc(path.name))
        else:
            thumb.set_paintable(None)
            row.set_subtitle(esc(subtitle or "Not chosen"))
        frame.set_visible(path is not None and path.is_file())
        clear.set_sensitive(bool(value))

    def failed(message: str) -> None:
        row.set_subtitle(esc(message))

    pick.connect("clicked", lambda _b: choose_image(row, setting.key, setting.label,
                                                    state, sync, failed))
    clear.connect("clicked", lambda _b: (state.set(setting.key, ""), sync()))
    sync()
    register(sync)
    return row


#: CSS class of widgets hidden in simple mode. The class is only a marker:
#: MainWindow._apply_level walks the tree and hides those carrying it. Rows
#: have no access to the window while being built (group_to_widget is module
#: level), so a marker is left instead of keeping a list.
ADVANCED_CSS = "hs-advanced"

#: Pages NOT shown in the sidebar at all in simple mode. A profile already
#: brings all of these in one click; picking bar/terminal/launcher piece by
#: piece, toggling packages, the login screen (root scripts) and doctor output
#: are for experienced users.
ADVANCED_PAGES: frozenset[str] = frozenset({
    "mix", "bars", "terminal", "launcher", "widgets", "login", "components",
    "system",
})

#: Which schema groups (settings.GROUPS) each page shows.
#: SINGLE SOURCE: pages are built by walking this list, and tools/test.sh checks
#: from here that every group in the schema lands on a page. If a new group is
#: added but not listed here it shows up NOWHERE in the UI and no error is raised.
PAGE_GROUPS: dict[str, tuple[str, ...]] = {
    # "tone" isn't in the loop; it's drawn right below the Theme group.
    "appearance": ("wallpaper", "tone", "theme_schedule", "layout", "decoration",
                   "animation"),
    # The twelve settings of the "bar_custom" group aren't drawn as plain rows
    # but as an expandable editor per slot (see _bar_custom_group).
    "bar": ("bar", "bar_custom", "dock"),
    "terminal": ("terminal", "terminal_look"),
    "launcher": ("launcher",),
    # The single setting of the "widget" group (WIDGETS) isn't a plain text box;
    # it's written by the page's on/off switches (see _page_widgets).
    "widgets": ("widget", "visualizer"),
    "behavior": ("behavior", "switcher", "groups", "plugins", "input", "gestures",
                 "environment"),
    # Mouse cursor has its own page: theme picker (not in the schema, a custom
    # widget) and size/hide settings side by side (see _page_cursor).
    "cursor": ("cursor",),
    # Session page: what happens when the computer is left alone (hypridle), night
    # light and screen recording. All three were working features never shown
    # in the UI; their settings could only be changed by editing settings.conf
    # by hand.
    "session": ("idle", "lock", "power", "notify", "night", "capture", "gamemode",
                "tools"),
}


def profile_backend(root: Path, name: str) -> str:
    """Bar backend in the profile's resolved chain ("" = default waybar).

    The backend is written in the profile's own file as ``BAR=``; if not there,
    it's read from the bar preset it points to (presets.resolve_chain). If
    neither says, the first bar component in the catalog, i.e. Waybar, applies.
    """
    values = presets_mod.resolve_chain(root, profile=name)
    return values.get("BAR", "") or _BAR_BACKENDS[0][0]


def active_bar_backend(state: SetupState) -> str:
    """Component id of the selected bar backend ("" = none).

    The "no effect on this backend" note next to BAR_* settings relies on this
    (see backend_note). Panel mode draws the same pages, so it lives in one place.
    """
    for comp_id, _label in _BAR_BACKENDS:
        if state.is_selected(comp_id):
            return comp_id
    return ""


def group_to_widget(group: schema.Group, state: SetupState,
                    skip: set[str] | None = None,
                    sync: dict | None = None,
                    active_backend: str = "",
                    rows: dict | None = None) -> Adw.PreferencesGroup:
    widget = Adw.PreferencesGroup(title=esc(group.title),
                                  description=esc(group.subtitle))
    if group.advanced:
        widget.add_css_class(ADVANCED_CSS)
    for setting in group.settings:
        if skip and setting.key in skip:
            continue
        row = build_setting_row(setting, state, sync, active_backend)
        if setting.advanced:
            row.add_css_class(ADVANCED_CSS)
        if rows is not None:
            rows[setting.key] = row
        widget.add(row)
    return widget


def fold(text: str) -> str:
    """Normalizes text for case-insensitive comparison in search."""
    return (text or "").casefold()


@dataclass
class SearchHit:
    """Search result: which setting, on which page."""

    label: str
    page_id: str
    page_title: str
    context: str                 # group title (like "Decoration")
    key: str = ""                # schema key (if any)
    haystack: str = ""           # normalized text the match is searched in
    advanced: bool = False       # not shown in results in simple mode


#: Places NOT in the schema but expected to be searchable. These pages draw
#: their settings with their own custom widgets (list, capture, key table);
#: not showing up in search at all would make people think they don't exist.
_EXTRA_SEARCH: tuple[tuple[str, str, str], ...] = (
    ("Theme and colors", "appearance", "palette, color, theme, accent, highlight"),
    ("Wallpaper colors", "appearance",
     "wallpaper, pick color, accent, auto, automatic, background"),
    ("Font", "appearance", "font, size, typeface"),
    ("Cursor theme", "cursor", "cursor, pointer, mouse, size, gozcu"),
    ("Keyboard shortcuts", "keybinds", "shortcut, keybinding, keybind, key, bind"),
    ("Display layout", "monitors", "monitor, display, resolution, refresh, scale, hz"),
    ("Workspace → display", "monitors", "workspace, monitor, display"),
    ("Components (toggle programs)", "components",
     "package, program, install, hyprsunset, swayosd, cava, wlogout, plugin"),
    ("Default applications", "apps", "terminal, browser, file manager"),
    ("Profiles", "profiles", "preset, profile, rice, look"),
    ("Soup Maker", "mix", "soup maker, mix, part, block, combine, wallpaper, color, bar"),
    ("Bar presets", "bars", "bar, status bar, preset"),
    ("System check (doctor)", "system", "diagnostics, doctor, missing package"),
    ("Wallpaper", "appearance", "wallpaper, background, rotation"),
)


def build_search_index(pages: list[tuple[str, str, str]]) -> list[SearchHit]:
    """List of everything searchable: schema settings + custom pages.

    The schema is the single source of truth: whichever group a setting is
    written into, PAGE_GROUPS ties it to a page, and here it's listed under that
    page's name. So adding a new setting automatically makes it searchable —
    tools/test.sh checks this separately.
    """
    titles = {page_id: title for page_id, title, _icon in pages}
    page_of = {gid: page for page, gids in PAGE_GROUPS.items() for gid in gids}

    hits: list[SearchHit] = []
    for group in schema.GROUPS:
        page_id = page_of.get(group.id, "")
        if not page_id:
            continue
        for setting in group.settings:
            hits.append(SearchHit(
                label=setting.label, page_id=page_id,
                page_title=titles.get(page_id, page_id),
                context=group.title, key=setting.key,
                advanced=setting.advanced or page_id in ADVANCED_PAGES,
                haystack=fold(" ".join((setting.label, setting.key,
                                        setting.help, group.title)))))

    for label, page_id, keywords in _EXTRA_SEARCH:
        hits.append(SearchHit(
            label=label, page_id=page_id,
            page_title=titles.get(page_id, page_id),
            context="page", haystack=fold(f"{label} {keywords}"),
            advanced=page_id in ADVANCED_PAGES))
    return hits


def level_path() -> Path:
    """Persistent location of the Simple/Advanced choice (next to settings.conf).

    Not written to settings.conf: that file holds the desktop's settings, this is
    only how the UI looks — install.sh and render don't care about it.
    """
    return config_path().parent / "gui-level"


def load_level() -> bool:
    """True = advanced. If the file doesn't exist, simple: first-time users see less."""
    try:
        return level_path().read_text(encoding="utf-8").strip() == "advanced"
    except OSError:
        return False


def save_level(advanced: bool) -> None:
    path = level_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("advanced\n" if advanced else "simple\n",
                        encoding="utf-8")
    except OSError as exc:
        print(f"hyprsetup: could not save UI mode: {exc}", file=sys.stderr)


# ------------------------------------------------------------------ window -
class MainWindow(Adw.ApplicationWindow):
    """Settings window: tabs on the left, the selected page on the right.

    ``panel=True`` is the mode opened with MOD+I. SAME window, same pages.
    Both modes come in via Hyprland rules (see templates/hypr/windowrules.conf.tmpl)
    as a floating window sliding in from the top, sized relative to the screen; in
    panel mode the Appearance page also opens, no welcome is shown and Esc
    closes it. There is NO separate
    copy of the panel: the "quick" version used to be a separate file and none
    of the full app's pages (keybindings, displays, components,
    colors, presets, live previews) existed there.
    """

    def __init__(self, app, root: Path, catalog: Catalog,
                 panel: bool = False):
        super().__init__(application=app, title=APP_NAME)
        self.panel = panel
        ensure_css(_CHIP_CSS)
        self.root = root
        self.catalog = catalog
        self.state = SetupState(catalog)
        # Component switches/boxes: collected in one dict no matter which page
        # they're drawn on (_refresh_component_rows refreshes them all).
        # Set up in __init__ because two separate pages (Components, Applications)
        # ADD to the same dict; if reset inside a page, the page drawn later would
        # wipe the earlier one's entries and those rows would never update again.
        self._component_widgets: dict[str, Gtk.Widget] = {}
        #: Setting key → that setting's row widget. Needed to open the page and
        #: bring the row into view when a search result is clicked; group_to_widget
        #: fills it while the pages are built.
        self._setting_rows: dict[str, Gtk.Widget] = {}
        # Read back the real settings left from the previous session/install —
        # otherwise the UI starts from schema defaults on every launch, and changing
        # and applying a single setting would reset EVERYTHING else to defaults.
        # First the GUI's own last "Apply" (gui.conf) is tried, else the
        # settings.conf install.sh writes at the end of installation.
        for candidate in self._conf_candidates():
            if self.state.load_conf(candidate):
                break
        # If a tool like nwg-displays generates monitors.conf/workspaces.conf
        # itself, the setting is left to it: otherwise ANY setting changed here
        # (even a slider) would regenerate those files and the user's
        # display layout would be reset completely.
        self._monitor_owners = self.state.adopt_foreign_monitors()
        # Five independent gallery axes — see lib/preset.sh and
        # docs/preset-sources.md. The profile is the top axis: it brings palette +
        # layout + decoration + default bar/terminal/launcher preset together;
        # picking any of the other four individually overrides the profile's.
        self.presets = presets_mod.load_profiles(root)
        self.bar_presets = presets_mod.load_all(presets_mod.default_dir(root, "bar"))
        self.widget_presets = presets_mod.load_all(
            presets_mod.default_dir(root, "widget"))
        # Widget LAYOUT presets (presets/widget-set/): widget list +
        # corner layout + sizes. Not to be confused with presets/widget/.
        self.widget_sets = presets_mod.load_all(
            presets_mod.default_dir(root, "widget-set"))
        # Widget LOOK presets (presets/widget-style/): plate, border, gauges,
        # clock and music layout. Independent of the layout above.
        self.widget_styles = presets_mod.load_all(
            presets_mod.default_dir(root, "widget-style"))
        self.term_presets = presets_mod.load_all(
            presets_mod.default_dir(root, "terminal"))
        self.launcher_presets = presets_mod.load_all(
            presets_mod.default_dir(root, "launcher"))
        # Page state of the terminal/launcher axes (see _page_app_axis)
        self._axis_status: dict[str, Adw.ActionRow] = {}
        self._axis_previews: dict[str, Gtk.Widget] = {}
        self._axis_card_previews: list[Gtk.Widget] = []
        self._axis_app_buttons: dict[str, dict[str, Gtk.ToggleButton]] = {}
        self._app_axis_widgets: dict[str, dict[str, Gtk.ToggleButton]] = {}
        self._app_axis_titles: dict[str, dict[str, Gtk.Label]] = {}
        self.keybinds = keybinds_mod.load_default(root)
        # Live apply engine. Long-lived: remembers the installed package set and the
        # last applied bar/notification/wallpaper backend (when the backend changes,
        # the OLD one must be stopped too, see apply.py).
        self.applier = Applier(root, catalog, self.keybinds)
        # Setting rows call this before writing a value that needs a program
        # (see build_setting_row.commit, deps.py).
        self.state.require = self._require
        #: Packages whose install was started in a terminal but don't show as installed yet.
        self._pending_install: set[str] = set()
        self._install_poll = 0
        #: Profile (name, variant) whose missing programs are installed in a terminal;
        #: when the install finishes those programs get selected (see _after_install).
        self._pending_profile: tuple[str, str] | None = None
        #: Rows on the Applications page (component id → row), so the "not
        #: installed" subtitle refreshes after installing.
        self._app_axis_rows: dict[str, Adw.ActionRow] = {}
        #: GLib source id of the debounce timer (0 = not pending).
        self._apply_source = 0
        #: If a setting changes while applying, repeat the round.
        self._apply_running = False
        self._apply_again = False
        #: Callbacks to run when the round finishes (when the background thread returns).
        self._apply_then: list = []
        #: The wizard's "preview only" mode: changes accumulate in the state and
        #: aren't written to the desktop (see set_apply_hold).
        self._apply_hold = False
        self._apply_held = False
        # Setting key → callback that refreshes the row from the state. When a
        # preset is applied, all widgets update through this.
        self._sync_rows: dict[str, object] = {}
        # Color key → buttons (one each in Appearance and Mix).
        self._colour_buttons: dict[str, list[Gtk.ColorDialogButton]] = {}
        # Both modes open sized relative to the screen via the floating window rule
        # (see windowrules.conf.tmpl); if GTK doesn't start at the same size, the
        # window resizes and jumps right after opening.
        self.set_default_size(*render_mod.quick_panel_pixels(
            _monitor_size(), {key: self.state.get(key)
                              for key in ("QUICK_PANEL_WIDTH", "QUICK_PANEL_HEIGHT")}))

        self.toasts = Adw.ToastOverlay()
        self.set_content(self.toasts)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.pages: list[tuple[str, str, str]] = []   # (id, title, icon)

        sidebar = self._build_sidebar()
        content = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.title_widget = Adw.WindowTitle(title=APP_NAME)
        header.set_title_widget(self.title_widget)
        content.add_top_bar(header)
        content.set_content(self.stack)

        split = Adw.NavigationSplitView(
            sidebar=Adw.NavigationPage(child=sidebar, title="Sections"),
            content=Adw.NavigationPage(child=content, title="Settings"),
        )
        split.set_min_sidebar_width(220)
        split.set_max_sidebar_width(260)
        # A first-run screen may sit in front of the settings screen (soup
        # animation + "wizard or ready-made theme?"); see welcome.py.
        self.root_stack = Gtk.Stack(
            transition_type=Gtk.StackTransitionType.CROSSFADE,
            transition_duration=450)
        self.root_stack.add_named(split, "main")
        self.toasts.set_child(self.root_stack)
        self._welcome: welcome_mod.Welcome | None = None
        self._welcome_keys: Gtk.EventControllerKey | None = None

        self._add_pages()
        self._apply_level()
        # Search index AFTER the pages are built: result rows tell which page
        # they're on by its human-readable name.
        self._search_index = build_search_index(self.pages)
        # The priority fix is only applied when it CHANGES (so no terminal opens
        # at startup): the last seen value is kept here.
        self._priority_seen = self.state.get("SWITCHER_PRIORITY") or "off"
        self.state.connect(self._on_state_changed)
        # A SEPARATE listener: every real setting change triggers the live apply.
        # Not added to _on_state_changed, because that is also called from
        # do_activate — applying there would make the UI write to ~/.config on
        # every launch without the user touching anything.
        self.state.connect(self._schedule_apply)
        # In panel mode the Home page (intro text + a single switch) is a wasted
        # click: someone pressing MOD+I nearly always comes to change the theme,
        # gaps or blur. The window opened from the menu stays on Home — that's
        # the first look after installation.
        opening = 0
        if panel:
            # Looked up by id so it doesn't break if the page order changes.
            opening = next((i for i, (page_id, _t, _i) in enumerate(self.pages)
                            if page_id == "appearance"), 0)
        self.listbox.select_row(self.listbox.get_row_at_index(opening))
        # HYPRSETUP_PAGE=<page id>: the app opens directly on that page
        # (e.g. terminal). If the page is hidden in simple mode, advanced mode is turned on.
        start = os.environ.get("HYPRSETUP_PAGE", "").strip()
        if start and not panel and any(pid == start for pid, _t, _i in self.pages):
            if start in ADVANCED_PAGES and not self.advanced:
                self.set_advanced(True)
            self._goto_page(start)
        # The MOD+I panel is for quick settings; the welcome only shows in the full app.
        if not panel and welcome_mod.should_show():
            self.show_welcome()

        # If settings.conf changes from outside (hand edit, copying from another
        # machine, git checkout) it should take effect while the app is open too:
        # the file is watched, the state is re-read on change and the normal
        # apply chain runs. Only this fulfills the "settings.conf is the single
        # source of truth" promise: before, a user who edited the file had to
        # close and reopen the app.
        self._conf_monitor = None
        self._conf_written = ""
        self._conf_reload_source = 0
        self._watch_conf()

        if panel:
            # Esc closes: the panel is opened and closed with MOD+I; you shouldn't
            # need to reach for the title bar with the mouse to close it.
            keys = Gtk.EventControllerKey()
            keys.connect("key-pressed", self._on_panel_key)
            self.add_controller(keys)

    # --------------------------------------------------------- welcome --
    def show_welcome(self) -> None:
        """Puts the startup animation and the getting-started choice in front of the settings."""
        if self._welcome is not None:
            return
        self._welcome = welcome_mod.Welcome(self.root, self._on_welcome_finish)
        self.root_stack.add_named(self._welcome, "welcome")
        self.root_stack.set_visible_child_name("welcome")
        # Keys are listened to at window level: during the animation focus may be
        # on no widget at all, yet Esc/Enter must still get through.
        self._welcome_keys = Gtk.EventControllerKey()
        self._welcome_keys.connect("key-pressed", self._welcome.on_key)
        self.add_controller(self._welcome_keys)

    def _on_welcome_finish(self, page_id: str) -> None:
        if page_id:
            self._goto_page(page_id)
        self.root_stack.set_visible_child_name("main")
        if self._welcome_keys is not None:
            self.remove_controller(self._welcome_keys)
            self._welcome_keys = None
        welcome, self._welcome = self._welcome, None

        def drop() -> bool:
            if welcome is not None and welcome.get_parent() is self.root_stack:
                self.root_stack.remove(welcome)
            return False
        # Remove once the transition animation ends; removing immediately would flash dark.
        GLib.timeout_add(600, drop)

    def _on_panel_key(self, _controller, keyval, _keycode, _state) -> bool:
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    # ------------------------------------------------------------ sidebar --
    def _build_sidebar(self) -> Gtk.Widget:
        toolbar = Adw.ToolbarView()
        brand = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        logo = self.root / "assets" / "souprland.svg"
        image = (Gtk.Image.new_from_file(str(logo)) if logo.is_file()
                 else Gtk.Image.new_from_icon_name(ICON_NAME))
        image.set_pixel_size(24)
        brand.append(image)
        name = Gtk.Label(label=APP_NAME)
        name.add_css_class("heading")
        brand.append(name)
        toolbar.add_top_bar(Adw.HeaderBar(title_widget=brand))

        # Simple / Advanced: someone who doesn't know computers well sees all 190
        # settings and can't tell what to change. Simple mode hides fine-tuning
        # and expert pages (settings.ADVANCED_KEYS, ADVANCED_PAGES); the values
        # stay, only the rows aren't shown.
        self.advanced = load_level()
        level = Gtk.Box(homogeneous=True, halign=Gtk.Align.FILL)
        level.add_css_class("linked")
        level.set_margin_start(8)
        level.set_margin_end(8)
        level.set_margin_top(6)
        self.simple_button = Gtk.ToggleButton(label="Simple",
                                              active=not self.advanced)
        self.simple_button.set_tooltip_text(
            "Only frequently used settings and pages")
        self.advanced_button = Gtk.ToggleButton(label="Advanced",
                                                active=self.advanced)
        self.advanced_button.set_tooltip_text(
            "All settings: fine-tuning, environment variables, components, "
            "Soup Maker, login screen…")
        self.advanced_button.set_group(self.simple_button)
        self.advanced_button.connect("toggled", self._on_level_toggled)
        level.append(self.simple_button)
        level.append(self.advanced_button)

        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.listbox.add_css_class("navigation-sidebar")
        self.listbox.connect("row-selected", self._on_page_selected)

        # Search: 177 settings are spread over fifteen pages; instead of browsing
        # around wondering "which page was blur on", you type its name and go
        # straight to that row. Results are drawn IN PLACE of the page list, because
        # the two share the same space and the list must come back when search ends.
        self.search = Gtk.SearchEntry(placeholder_text="Search settings…")
        self.search.set_margin_start(8)
        self.search.set_margin_end(8)
        self.search.set_margin_top(6)
        self.search.set_margin_bottom(4)
        self.search.connect("search-changed", self._on_search_changed)
        self.search.connect("stop-search", lambda _e: self.search.set_text(""))
        self.search.connect("activate", self._on_search_activate)

        self.results = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.results.add_css_class("navigation-sidebar")
        self.results.connect("row-activated", self._on_result_activated)
        self._result_hits: list[SearchHit] = []

        self.sidebar_stack = Gtk.Stack()
        self.sidebar_stack.add_named(
            Gtk.ScrolledWindow(child=self.listbox, vexpand=True), "pages")
        self.sidebar_stack.add_named(
            Gtk.ScrolledWindow(child=self.results, vexpand=True), "results")

        scroller = self.sidebar_stack
        scroller.set_vexpand(True)

        self.summary_label = Gtk.Label(xalign=0.0, wrap=True)
        self.summary_label.add_css_class("dim-label")
        self.summary_label.add_css_class("caption")
        self.summary_label.set_margin_start(12)
        self.summary_label.set_margin_end(12)
        self.summary_label.set_margin_top(6)
        self.summary_label.set_margin_bottom(6)

        # There is NO "Apply" button: every change applies by itself
        # (see _schedule_apply). In its place is a status line saying what
        # happened — without seeing that something was really written and which
        # daemon was reloaded, the user hesitates over "did it apply?".
        self.apply_status = Gtk.Label(xalign=0.0, wrap=True, label="Up to date")
        self.apply_status.add_css_class("dim-label")
        self.apply_status.add_css_class("caption")
        self.apply_status.set_margin_start(12)
        self.apply_status.set_margin_end(12)
        self.apply_status.set_margin_bottom(10)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(level)
        box.append(self.search)
        box.append(scroller)
        box.append(Gtk.Separator())
        box.append(self.summary_label)
        box.append(self.apply_status)
        toolbar.set_content(box)
        return toolbar

    def _add_page(self, page_id: str, title: str, icon: str,
                  child: Gtk.Widget) -> None:
        self.stack.add_named(child, page_id)
        self.pages.append((page_id, title, icon))
        row = Adw.ActionRow(title=title)
        row.add_prefix(Gtk.Image.new_from_icon_name(icon))
        row.set_activatable(True)
        self.listbox.append(row)

    def _on_page_selected(self, _box, row) -> None:
        if row is None:
            return
        index = row.get_index()
        page_id, title, _icon = self.pages[index]
        if page_id == "bar" and hasattr(self, "_rice_bar_group"):
            self._refresh_rice_bar()
        self._resync_rows()
        if page_id == "wizard":
            self.wizard.on_shown()
        self.stack.set_visible_child_name(page_id)
        self.title_widget.set_title(title)

    # ---------------------------------------------------- simple / advanced -
    def _on_level_toggled(self, button: Gtk.ToggleButton) -> None:
        advanced = button.get_active()
        if advanced == self.advanced:
            return
        self.advanced = advanced
        save_level(advanced)
        self._apply_level()
        # If a search is open, re-filter the results for the new mode.
        if self.search.get_text().strip():
            self._on_search_changed(self.search)

    def set_advanced(self, advanced: bool) -> None:
        """Change the mode from outside (the search result's "show in advanced")."""
        (self.advanced_button if advanced else self.simple_button).set_active(True)

    def _apply_level(self) -> None:
        """Show/hide advanced rows, groups and pages according to the selected mode.

        Marked widgets (ADVANCED_CSS) are found by walking the tree: since pages
        can be rebuilt later (import, mix), a kept list would go stale. The mode
        rarely changes and the walk is cheap.
        """
        show = self.advanced
        pending = [self.stack]
        while pending:
            widget = pending.pop()
            if widget.has_css_class(ADVANCED_CSS):
                widget.set_visible(show)
            child = widget.get_first_child()
            while child is not None:
                pending.append(child)
                child = child.get_next_sibling()

        selected = self.listbox.get_selected_row()
        for index, (page_id, _title, _icon) in enumerate(self.pages):
            row = self.listbox.get_row_at_index(index)
            if row is not None and page_id in ADVANCED_PAGES:
                row.set_visible(show)
        # If the open page is now hidden, go back to Home; if a hidden row stays
        # selected, the content is shown but nothing is highlighted in the sidebar.
        if selected is not None and not selected.get_visible():
            self.listbox.select_row(self.listbox.get_row_at_index(0))

    # -------------------------------------------------------------- search --
    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        query = fold(entry.get_text().strip())
        if not query:
            self.sidebar_stack.set_visible_child_name("pages")
            return

        # The query is split into words and ALL must match: someone typing "alt tab"
        # should find the setting mentioning "ALT+Tab", and "bar height" should
        # bring up the bar's height directly.
        tokens = [t for t in query.split() if t]
        hits = [hit for hit in self._search_index
                if all(token in hit.haystack for token in tokens)]
        # In simple mode hidden settings don't show in results either — clicking
        # would lead to an invisible row. How many were hidden is still shown.
        hidden = 0
        if not self.advanced:
            hidden = sum(hit.advanced for hit in hits)
            hits = [hit for hit in hits if not hit.advanced]
        # Those whose label STARTS with the query first: typing "bar" puts "Bar height"
        # on top, and some distant help text containing "bar" below. A label that
        # starts with the whole query beats one that only shares its first word
        # ("lock the screen" → "Lock the screen" before "Lock before sleep").
        hits.sort(key=lambda h: (not fold(h.label).startswith(query),
                                 not fold(h.label).startswith(tokens[0]),
                                 h.page_title, h.label))

        while (row := self.results.get_first_child()) is not None:
            self.results.remove(row)
        self._result_hits = hits[:40]
        for hit in self._result_hits:
            row = Adw.ActionRow(title=esc(hit.label),
                                subtitle=esc(f"{hit.page_title} › {hit.context}"))
            row.set_activatable(True)
            self.results.append(row)
        if not hits:
            row = Adw.ActionRow(title="No results",
                                subtitle="Try another word")
            row.set_sensitive(False)
            self.results.append(row)
        if hidden:
            row = Adw.ActionRow(title=f"{hidden} more results in advanced mode",
                                subtitle="Click to show")
            row.add_prefix(Gtk.Image.new_from_icon_name(
                "view-more-horizontal-symbolic"))
            row.set_activatable(True)
            self._level_hint_row = row
            self.results.append(row)
        self.sidebar_stack.set_visible_child_name("results")

    def _on_search_activate(self, _entry: Gtk.SearchEntry) -> None:
        """Enter: go to the first result (no need to reach for the list)."""
        if self._result_hits:
            self._open_hit(self._result_hits[0])

    def _on_result_activated(self, _box, row) -> None:
        if row is getattr(self, "_level_hint_row", None):
            self.set_advanced(True)
            return
        index = row.get_index()
        if 0 <= index < len(self._result_hits):
            self._open_hit(self._result_hits[index])

    def _open_hit(self, hit: SearchHit) -> None:
        """Open the result's page, bring the row into view and highlight it briefly."""
        for index, (page_id, _title, _icon) in enumerate(self.pages):
            if page_id == hit.page_id:
                self.listbox.select_row(self.listbox.get_row_at_index(index))
                break
        row = self._setting_rows.get(hit.key) if hit.key else None
        if row is None:
            return
        # Giving focus brings the row into view in the scroll area; GTK does
        # this by itself, no manual vadjustment math needed.
        row.grab_focus()
        row.add_css_class("hs-search-hit")
        GLib.timeout_add_seconds(2, self._clear_hit, row)

    @staticmethod
    def _clear_hit(row: Gtk.Widget) -> bool:
        row.remove_css_class("hs-search-hit")
        return False

    # ------------------------------------------------------------ pages -
    def _add_pages(self) -> None:
        # The install pages (Components, Profiles, Summary and Install) were
        # removed: this is no longer an installation wizard but the settings app
        # of a running system. Installing packages is install.sh's job.
        self._add_page("start", "Home", "go-home-symbolic",
                       self._page_start())
        # The wizard asks the same settings in order; it doesn't replace the
        # other pages, it links to them (see wizard_page.py).
        self.wizard = WizardPage(self)
        self._add_page("wizard", "Setup Wizard", "starred-symbolic",
                       self.wizard)
        self._add_page("profiles", "Profiles", "view-paged-symbolic",
                       self._page_profiles())
        self._add_page("mix", "Soup Maker", "view-app-grid-symbolic",
                       self._page_mix())
        self._add_page("appearance", "Appearance", "applications-graphics-symbolic",
                       self._page_appearance())
        self._add_page("wallcolors", "Wallpaper Colors", "color-select-symbolic",
                       WallColorsPage(self))
        self._add_page("wpengine", "Wallpaper Engine", "video-display-symbolic",
                       self._page_wpengine())
        self._add_page("bars", "Bar Presets", "view-continuous-symbolic",
                       self._page_bars())
        self._add_page("bar", "Status Bar", "view-continuous-symbolic",
                       self._page_bar())
        self._add_page("terminal", "Terminal", "utilities-terminal-symbolic",
                       self._page_app_axis("terminal"))
        self._add_page("launcher", "Launcher", "system-search-symbolic",
                       self._page_app_axis("launcher"))
        self._add_page("widgets", "Widgets", "view-grid-symbolic",
                       self._page_widgets())
        self._add_page("behavior", "Behavior", "preferences-system-symbolic",
                       self._page_behavior())
        self._add_page("cursor", "Mouse Cursor", "input-mouse-symbolic",
                       self._page_cursor())
        self._add_page("rules", "Window Rules", "window-new-symbolic",
                       self._page_rules())
        self._add_page("session", "Session", "system-lock-screen-symbolic",
                       self._page_session())
        self._add_page("login", "Login Screen", "system-users-symbolic",
                       LoginPage(self))
        self._add_page("keybinds", "Keybindings", "input-keyboard-symbolic",
                       self._page_keybinds())
        self._add_page("apps", "Applications", "preferences-desktop-apps-symbolic",
                       self._page_apps())
        self._add_page("autostart", "Autostart", "system-run-symbolic",
                       self._page_autostart())
        self._add_page("components", "Components",
                       "application-x-addon-symbolic", self._page_components())
        self._add_page("monitors", "Displays", "video-display-symbolic",
                       self._page_monitors())
        self._add_page("system", "System", "emblem-system-symbolic",
                       self._page_system())

    # --- home ---------------------------------------------------------------
    def _page_start(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()

        intro = Adw.PreferencesGroup(
            title=APP_NAME,
            description="Every setting you change is applied instantly: "
                        "configuration files are regenerated and only the "
                        "affected program (Hyprland, status bar, notification "
                        "server…) is reloaded. There is no \"Apply\" button; "
                        "the line at the bottom left says what was done.\n\n"
                        "This app doesn't install packages or ask for your sudo password. "
                        "An option that isn't installed appears dimmed; you can "
                        "copy the pacman command next to it and run it in a "
                        "terminal.")
        page.add(intro)

        scope = Adw.PreferencesGroup(
            title="Scope",
            description="If you have your own Hyprland configuration (hand-written "
                        "or a ready-made rice), keep this tool from touching it at all.")
        row = Adw.SwitchRow(
            title="Let this tool manage the Hyprland configuration",
            subtitle="If off, no files are written under ~/.config/hypr; "
                     "only packages are installed and other apps are configured.")
        # Read from the state: a hard-coded True showed the switch ON to users
        # with MANAGE_HYPR_CONFIGS=0 (see the same bug in _page_monitors).
        row.set_active(self.state.get("MANAGE_HYPR_CONFIGS") != "0")
        row.connect("notify::active", lambda r, _p: self.state.set(
            "MANAGE_HYPR_CONFIGS", "1" if r.get_active() else "0"))
        scope.add(row)
        page.add(scope)

        again = Adw.PreferencesGroup()
        replay = Adw.ActionRow(
            title="Show the welcome screen again",
            subtitle="The soup animation and the \"wizard or ready-made theme?\" choice")
        button = Gtk.Button(label="Show", valign=Gtk.Align.CENTER)
        button.connect("clicked", lambda _b: self.show_welcome())
        replay.add_suffix(button)
        replay.set_activatable_widget(button)
        again.add(replay)
        page.add(again)
        return page

    # ====================================================== gallery pages ==
    # The three axes are independent: the profile sets palette/layout/default bar,
    # a bar preset can be picked separately and overrides the profile's, and
    # widgets are independent of both. Resolution happens in presets.resolve_chain.

    def _gallery_card(self, title: str, subtitle: str, preview: Gtk.Widget,
                      badges: list[str], on_apply, apply_label: str = "Apply",
                      extra: Gtk.Widget | None = None,
                      width: int = 340,
                      aur: list[str] | None = None,
                      swatches: list[str] | None = None) -> Gtk.Widget:
        """Gallery card made of preview + title + details + action button.

        ``swatches`` (hex colors) become small palette dots right of the title.

        ``extra`` is placed right above the button (e.g. the profile's variant picker).
        """
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.add_css_class("card")
        # Used to be 208px — squeezed enough to make the structural differences
        # between bar presets (islands vs. dock vs. bracket) invisible. Since the
        # gallery no longer depends on Adw.PreferencesPage's narrow reading-width
        # limit (see _gallery_page), this width can grow comfortably.
        card.set_size_request(width, -1)

        frame = Gtk.Frame()
        frame.add_css_class("view")
        frame.set_child(preview)
        card.append(frame)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3,
                       vexpand=True)
        body.set_margin_top(8)
        body.set_margin_bottom(8)
        body.set_margin_start(10)
        body.set_margin_end(10)

        # If max_width_chars isn't limited, Gtk.Label's "natural width" is wide
        # enough to fit the whole text on one line; since a homogeneous FlowBox
        # sizes all cells to the widest child, a single long description dropped
        # the whole gallery to one column — the card is kept proportional to its
        # width (340px).
        name = Gtk.Label(label=title, xalign=0, wrap=True,
                         max_width_chars=30)
        name.add_css_class("heading")
        if swatches:
            head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            name.set_hexpand(True)
            head.append(name)
            head.append(_swatch_strip(swatches, 10))
            body.append(head)
        else:
            body.append(name)

        if subtitle:
            desc = Gtk.Label(label=subtitle, xalign=0, wrap=True, lines=3,
                             max_width_chars=30,
                             ellipsize=Pango.EllipsizeMode.END)
            desc.add_css_class("caption")
            desc.add_css_class("dim-label")
            body.append(desc)

        if badges or aur:
            strip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            strip.set_margin_top(2)
            if aur:
                strip.append(aur_mod.badge(aur))
            for text in badges:
                chip = Gtk.Label(label=text, max_width_chars=16,
                                 ellipsize=Pango.EllipsizeMode.END)
                chip.add_css_class("caption")
                chip.add_css_class("dim-label")
                strip.append(chip)
            body.append(strip)

        if extra is not None:
            extra.set_margin_top(4)
            body.append(extra)

        button = Gtk.Button(label=apply_label)
        button.set_margin_top(6)
        # The button sticks to the card's bottom: FlowBox cells are equal height,
        # but on cards with a short description the button stayed higher, so the
        # buttons of side-by-side cards sat "misaligned" at different heights.
        button.set_vexpand(True)
        button.set_valign(Gtk.Align.END)
        button.add_css_class("suggested-action")
        button.connect("clicked", on_apply)
        body.append(button)

        card.append(body)
        return card

    @staticmethod
    def _gallery_flow() -> Gtk.FlowBox:
        flow = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            homogeneous=True, row_spacing=14, column_spacing=14,
            min_children_per_line=1, max_children_per_line=8,
            valign=Gtk.Align.START)
        return flow

    @staticmethod
    def _gallery_page(title: str, description: str,
                      header_extra: list[Gtk.Widget] | None = None,
                      ) -> tuple[Gtk.Widget, Gtk.Box]:
        """Full-width skeleton for gallery pages.

        Adw.PreferencesPage locks its content to ~600px for readability — the
        right choice for settings forms, but in a 48-card gallery it left a lot of
        empty space and forced needless scrolling (more so once the cards
        grew). Here a plain scrollable Gtk.Box is used instead; only narrow text
        items like title/description/filter go into an Adw.Clamp for
        readability, and the card flow stays full
        width.
        """
        scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        outer.set_margin_top(18)
        outer.set_margin_bottom(18)
        outer.set_margin_start(24)
        outer.set_margin_end(24)
        scroller.set_child(outer)

        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        title_label = Gtk.Label(label=title, xalign=0)
        title_label.add_css_class("title-2")
        header_box.append(title_label)
        if description:
            desc_label = Gtk.Label(label=description, xalign=0, wrap=True)
            desc_label.add_css_class("dim-label")
            header_box.append(desc_label)
        for extra in header_extra or []:
            header_box.append(extra)
        header_clamp = Adw.Clamp(maximum_size=800)
        header_clamp.set_child(header_box)
        outer.append(header_clamp)

        return scroller, outer

    # --- mix (mix.py) ------------------------------------------------------
    def _page_mix(self) -> Gtk.Widget:
        """Pick parts from setups piece by piece and assemble your own desktop.

        Choices first collect in a pending list (clicking cards changes nothing
        right away); "Apply mix" applies them all at once — since app parts
        install files, installing on every click would restart the desktop
        over and over.
        """
        description = (
            "Pick parts from ready-made setups: one's wallpaper, "
            "another's colors, a third one's bar. The base is always your own "
            "configuration; your keybindings, keyboard and ALT+Tab stay the "
            "same. Choose the ingredients step by step; the desktop in the middle "
            "shows how your choice will look (clicking a part of it goes to that "
            "ingredient). Then \"Apply mix\". Parts like the bar and launcher are "
            "painted in the color scheme you picked.")
        self._mix_parts = mix_mod.load_parts(self.root)
        self._mix_apps = mix_mod.app_parts(self.root)
        self._mix_pending: dict[str, str] = mix_mod.selection()
        self._mix_cards: dict[str, list[tuple[Gtk.Widget, str]]] = {}
        # Slot → (manual settings box, note); a separate dict per slot for re-reading
        # the rows from the state (_sync_rows is keyed by setting key, so this mustn't
        # override the same setting's row on the Appearance page).
        self._mix_manual: dict[str, tuple[Gtk.Box, Gtk.Label]] = {}
        self._mix_sync: dict[str, dict] = {}

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        apply_button = Gtk.Button(label="Apply mix")
        apply_button.add_css_class("suggested-action")
        apply_button.connect("clicked", lambda _b: self._on_mix_apply())
        self._mix_apply_button = apply_button
        clear_button = Gtk.Button(label="Turn all off")
        clear_button.set_tooltip_text("Empties all slots: your settings return to how they "
                                      "were before the mix, installed parts are removed.")
        clear_button.connect("clicked", lambda _b: self._on_mix_clear())
        save_button = Gtk.Button(label="Save…")
        save_button.set_tooltip_text("Stores this selection under a name.")
        save_button.connect("clicked", lambda _b: self._on_mix_save())
        self._mix_saved_model = Gtk.StringList()
        self._mix_saved = Gtk.DropDown(model=self._mix_saved_model)
        self._mix_saved.set_tooltip_text("Saved mixes")
        load_button = Gtk.Button(label="Load")
        load_button.connect("clicked", lambda _b: self._on_mix_load())
        delete_button = Gtk.Button(icon_name="user-trash-symbolic")
        delete_button.set_tooltip_text("Delete the selected save")
        delete_button.connect("clicked", lambda _b: self._on_mix_delete())
        self._mix_saved_widgets = (self._mix_saved, load_button, delete_button)
        for widget in (apply_button, clear_button, save_button, *self._mix_saved_widgets):
            actions.append(widget)
        self._mix_status = Gtk.Label(xalign=0, wrap=True)
        self._mix_status.add_css_class("dim-label")
        self._mix_status.add_css_class("caption")

        scroller, outer = self._gallery_page(
            "Soup Maker", description, header_extra=[actions, self._mix_status])

        # Ingredients: the slots that have a tab on the page, in recipe order.
        self._mix_steps = [(slot, label) for slot, label in (*mix_mod.SLOTS, *mix_mod.APP_SLOTS)
                           if slot not in mix_mod.APP_SLOT_IDS or self._mix_apps.get(slot)]
        self._mix_step = self._mix_steps[0][0]

        # 1) Steps: numbered ingredient strip at the top.
        steps = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4,
                        homogeneous=True)
        steps.add_css_class("hs-mix-steps")
        self._mix_step_buttons: dict[str, tuple[Gtk.ToggleButton, Gtk.Label, Gtk.Label]] = {}
        group: Gtk.ToggleButton | None = None
        for index, (slot, label) in enumerate(self._mix_steps, start=1):
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            dot = Gtk.Label(label=str(index), halign=Gtk.Align.CENTER)
            dot.add_css_class("hs-step-dot")
            title = Gtk.Label(label=label, max_width_chars=16,
                              ellipsize=Pango.EllipsizeMode.END)
            title.set_tooltip_text(label)
            title.add_css_class("caption-heading")
            value = Gtk.Label(ellipsize=Pango.EllipsizeMode.END, max_width_chars=14)
            value.add_css_class("caption")
            value.add_css_class("dim-label")
            box.append(dot)
            box.append(title)
            box.append(value)
            button = Gtk.ToggleButton(child=box)
            button.add_css_class("flat")
            button.add_css_class("hs-mix-step")
            if group is None:
                group = button
            else:
                button.set_group(group)
            button.connect("toggled", lambda b, s=slot: b.get_active()
                           and self._mix_goto_step(s))
            steps.append(button)
            self._mix_step_buttons[slot] = (button, dot, value)
        step_scroll = Gtk.ScrolledWindow(vscrollbar_policy=Gtk.PolicyType.NEVER,
                                         propagate_natural_height=True)
        step_scroll.set_child(steps)
        outer.append(step_scroll)

        # 2) Live desktop: the selected ingredient's area is highlighted, regions are clickable.
        # If a bar ingredient is chosen it's drawn even if your own bar isn't selected.
        self._mix_preview = MixPreview(
            self.root,
            lambda c: (c == "bar" and bool(self._mix_pending.get("bar")))
            or self.state.category_has_selection(c),
            on_slot=lambda s: self._mix_goto_step(s))
        self._mix_preview.slots = {s for s, _l in self._mix_steps}
        self._mix_preview.set_hexpand(False)
        self._mix_preview.set_size_request(704, 396)
        frame = Gtk.Frame(child=self._mix_preview, halign=Gtk.Align.CENTER)
        frame.add_css_class("view")
        outer.append(frame)

        # 3) Ingredient title + compact option strip.
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._mix_step_title = Gtk.Label(xalign=0, hexpand=True,
                                         ellipsize=Pango.EllipsizeMode.END)
        self._mix_step_title.add_css_class("title-4")
        manual = Gtk.Button(label="Adjust manually", icon_name="document-edit-symbolic")
        manual.set_child(Adw.ButtonContent(icon_name="document-edit-symbolic",
                                           label="Adjust manually"))
        manual.set_tooltip_text("Change this ingredient's settings one by one")
        manual.connect("clicked", lambda _b: self._open_mix_slot(self._mix_step, "manual"))
        self._mix_clear_step = Gtk.Button(label="Keep my own setting")
        self._mix_clear_step.set_tooltip_text("Empties this ingredient")
        self._mix_clear_step.connect("clicked", lambda _b: self._mix_pick_exact(
            self._mix_step, ""))
        head.append(self._mix_step_title)
        head.append(self._mix_clear_step)
        head.append(manual)
        outer.append(head)

        self._mix_strips = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,
                                     vhomogeneous=False)
        for slot, _label in self._mix_steps:
            self._mix_strips.add_named(self._mix_strip(slot), slot)
        outer.append(self._mix_strips)

        # 4) Back / Next.
        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._mix_prev = Gtk.Button()
        self._mix_prev.connect("clicked", lambda _b: self._mix_step_by(-1))
        self._mix_next = Gtk.Button()
        self._mix_next.add_css_class("suggested-action")
        self._mix_next.connect("clicked", lambda _b: self._mix_step_by(1))
        nav.append(self._mix_prev)
        nav.append(Gtk.Box(hexpand=True))
        nav.append(self._mix_next)
        outer.append(nav)

        self._refresh_mix_saved()
        self._mix_step_buttons[self._mix_step][0].set_active(True)
        self._mix_goto_step(self._mix_step)
        # The links show page names; the later pages haven't been added yet.
        GLib.idle_add(lambda: self._refresh_mix_manual() and False)
        return scroller

    def _mix_strip(self, slot: str) -> Gtk.Widget:
        """An ingredient's options: small cards, wrapping to the next line when full.

        Since the preview above is large, the card itself can stay small;
        the page scrolls downward (users found a horizontal strip awkward).
        The first card is "your own setting" (slot empty).
        """
        row = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
                          homogeneous=True, row_spacing=8, column_spacing=8,
                          min_children_per_line=2, max_children_per_line=12,
                          valign=Gtk.Align.START)
        row.set_margin_bottom(6)
        cards: list[tuple[Gtk.Widget, str]] = []
        own_preview = None
        if slot == "wallpaper":
            current = Path(self.state.get("WALLPAPER_PATH") or "").expanduser()
            if current.is_file():
                own_preview = ShotPreview(current, width=140, height=78)
        own = self._mix_compact_card(slot, "", "Your own setting", "no change", own_preview)
        row.append(own)
        cards.append((own, ""))
        row.append(self._mix_add_card(slot))
        if slot == "wallpaper":
            # The user's own folder: images they added themselves are cards too.
            for path in self._mix_own_wallpapers():
                card = self._mix_compact_card(
                    slot, f"file:{path}", path.stem, "your folder",
                    ShotPreview(path, width=140, height=78))
                row.append(card)
                cards.append((card, f"file:{path}"))
        for value, title, subtitle, preview in self._mix_options(slot, compact=True):
            card = self._mix_compact_card(slot, value, title, subtitle, preview,
                                          aur=self._mix_part_aur(slot, value))
            row.append(card)
            cards.append((card, value))
        self._mix_cards[slot] = cards
        return row

    def _mix_compact_card(self, slot: str, value: str, title: str, subtitle: str,
                          preview: Gtk.Widget | None,
                          aur: list[str] | None = None,
                          on_click=None) -> Gtk.Widget:
        button = Gtk.Button()
        button.add_css_class("card")
        button.add_css_class("hs-mix-card")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_size_request(152, -1)
        if preview is None:
            preview = Gtk.Image.new_from_icon_name("user-home-symbolic")
            preview.set_pixel_size(28)
            preview.set_size_request(136, 76)
            preview.add_css_class("hs-mix-own")
        preview.set_margin_top(6)
        preview.set_margin_start(6)
        preview.set_margin_end(6)
        box.append(preview)
        name = Gtk.Label(label=title, xalign=0, ellipsize=Pango.EllipsizeMode.END,
                         max_width_chars=17)
        name.add_css_class("caption-heading")
        name.set_margin_start(8)
        name.set_margin_end(8)
        box.append(name)
        line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        line.set_margin_start(8)
        line.set_margin_end(8)
        line.set_margin_bottom(6)
        sub = Gtk.Label(label=subtitle, xalign=0, hexpand=True,
                        ellipsize=Pango.EllipsizeMode.END, max_width_chars=14)
        sub.add_css_class("caption")
        sub.add_css_class("dim-label")
        line.append(sub)
        if aur:
            line.append(aur_mod.badge(aur))
        box.append(line)
        button.set_child(box)
        button.set_tooltip_text(f"{title} — {subtitle}" if subtitle else title)
        button.connect("clicked", lambda _b: on_click() if on_click
                       else self._mix_pick_exact(slot, value))
        return button

    def _mix_pick_exact(self, slot: str, value: str) -> None:
        """Card in the strip: selects it (pressing the same card again changes nothing;
        the "Your own setting" card is there for emptying)."""
        if value.startswith("file:"):
            self._mix_use_own_wallpaper(Path(value[5:]))
            return
        self._mix_pending[slot] = value
        self._refresh_mix()

    #: "Add your own" card: (title, subtitle, icon) — the wallpaper one opens a
    #: file chooser, the others open that ingredient's manual settings window.
    _MIX_ADD: dict[str, tuple[str, str, str]] = {
        "wallpaper": ("Your own image…", "choose from file", "list-add-symbolic"),
        "colors": ("Your own colors", "palette + single colors", "color-select-symbolic"),
        "look": ("Adjust it yourself", "corners, gaps, animation", "document-edit-symbolic"),
        "bar": ("Your own bar", "modules, position, size", "document-edit-symbolic"),
        "launcher": ("Your own launcher", "program and look", "document-edit-symbolic"),
        "notify": ("Your own notifications", "program and settings", "document-edit-symbolic"),
        "terminal": ("Your own terminal", "program, font, opacity", "document-edit-symbolic"),
        "lock": ("Your own lock", "lock and idle", "document-edit-symbolic"),
        "widget": ("Your own widgets", "which ones, where", "document-edit-symbolic"),
    }

    def _mix_add_card(self, slot: str) -> Gtk.Widget:
        title, subtitle, icon = self._MIX_ADD.get(
            slot, ("Adjust it yourself", "manually", "document-edit-symbolic"))
        preview = Gtk.Image.new_from_icon_name(icon)
        preview.set_pixel_size(28)
        preview.set_size_request(136, 76)
        preview.add_css_class("hs-mix-own")
        preview.add_css_class("accent")
        action = (self._mix_pick_wallpaper_file if slot == "wallpaper"
                  else lambda: self._open_mix_slot(slot, "manual"))
        return self._mix_compact_card(slot, "", title, subtitle, preview,
                                      on_click=action)

    @staticmethod
    def _mix_wallpaper_dir() -> Path:
        return Path.home() / "Pictures" / "wallpapers"

    def _mix_own_wallpapers(self) -> list[Path]:
        """Images in ~/Pictures/wallpapers (newest first, at most 48).
        The mix's own copies (mix-*) duplicate the setup cards and are skipped."""
        folder = self._mix_wallpaper_dir()
        try:
            files = [f for f in folder.iterdir()
                     if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
                     and f.is_file() and not f.name.startswith("mix-")]
        except OSError:
            return []
        files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        return files[:48]

    def _mix_pick_wallpaper_file(self) -> None:
        pick_file(self, "Choose wallpaper",
                  lambda path: self._mix_use_own_wallpaper(path, copy=True),
                  filter_name="Images", mimes=["image/*"], folder=PICTURES)

    def _mix_use_own_wallpaper(self, path: Path, copy: bool = False) -> None:
        """Makes your own image the wallpaper; the slot goes back to "your own setting".

        ``copy``: an image picked from outside the folder is copied to
        ~/Pictures/wallpapers — so it shows as a card and the desktop isn't left
        blank if the source is deleted. If a mix wallpaper was applied, that slot
        and its "before" values are forgotten; otherwise the next "Apply mix"
        would write the old wallpaper back.
        """
        folder = self._mix_wallpaper_dir()
        if copy and path.parent != folder:
            dest = folder / path.name
            try:
                folder.mkdir(parents=True, exist_ok=True)
                if not dest.is_file() or dest.read_bytes() != path.read_bytes():
                    if dest.exists():
                        dest = folder / f"{path.stem}-{int(time.time())}{path.suffix}"
                    shutil.copyfile(path, dest)
            except OSError as exc:
                self._toast(f"Could not copy image: {exc}")
                return
            path = dest
        state = mix_mod.read_state()
        if state["slots"].pop("wallpaper", None) is not None:
            state["before"].pop("wallpaper", None)
            mix_mod.write_state(state)
        self._mix_pending["wallpaper"] = ""
        try:
            value = "~/" + str(path.relative_to(Path.home()))
        except ValueError:
            value = str(path)
        self.state.set("WALLPAPER_IMAGE", "")
        self.state.set("WALLPAPER_STYLE", "")
        self.state.set("WALLPAPER_PATH", value)
        self._mix_rebuild_strip("wallpaper")
        self._refresh_mix()
        self._toast(f"Wallpaper: {path.name}")

    def _mix_rebuild_strip(self, slot: str) -> None:
        old = self._mix_strips.get_child_by_name(slot)
        visible = self._mix_strips.get_visible_child_name()
        if old is not None:
            self._mix_strips.remove(old)
        self._mix_strips.add_named(self._mix_strip(slot), slot)
        if visible:
            self._mix_strips.set_visible_child_name(visible)

    def _mix_goto_step(self, slot: str) -> None:
        if slot not in dict(self._mix_steps):
            return
        self._mix_step = slot
        button = self._mix_step_buttons[slot][0]
        if not button.get_active():
            button.set_active(True)        # toggled → comes back here
            return
        self._mix_strips.set_visible_child_name(slot)
        self._mix_preview.set_current(slot)
        self._refresh_mix()

    def _mix_step_by(self, delta: int) -> None:
        order = [s for s, _l in self._mix_steps]
        index = order.index(self._mix_step) + delta
        if index >= len(order):
            self._on_mix_apply()
            return
        if index >= 0:
            self._mix_goto_step(order[index])

    #: Manual settings for the setting slots: schema groups (the same settings as
    #: on the Appearance page; colors are drawn separately — see _mix_colour_manual).
    _MIX_SETTING_GROUPS: dict[str, tuple[str, ...]] = {
        "wallpaper": ("wallpaper",),
        "look": ("layout", "decoration", "animation"),
    }
    #: When an app slot is empty (your own program): inline groups and the
    #: page with the detailed settings.
    _MIX_OWN_SETTINGS: dict[str, tuple[tuple[str, ...], str]] = {
        "bar": (("bar",), "bar"),
        "launcher": (("launcher",), "launcher"),
        "notify": (("notify",), "session"),
        "terminal": (("terminal",), "terminal"),
        "lock": (("lock", "idle"), "session"),
        "widget": ((), "widgets"),
    }

    #: Program choice shown inline when an app slot is empty (catalog
    #: category; for slots without a setting in the schema).
    _MIX_OWN_AXES: dict[str, str] = {"notify": "notify"}

    def _mix_slot_page(self, slot: str, key: str = "",
                       start: str = "cards") -> Gtk.Widget:
        """Tab: the setups' cards, or adjusting that slot manually.

        The two are separate views: placed below the cards, the manual settings
        ended up behind dozens of cards and couldn't be found. ``key`` separates a
        second copy of the same slot (the window opened from the summary tile) from the tab's.
        """
        key = key or slot
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        views = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,
                          vhomogeneous=False)
        switch = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                         halign=Gtk.Align.CENTER)
        switch.add_css_class("linked")
        first: Gtk.ToggleButton | None = None
        buttons: dict[str, Gtk.ToggleButton] = {}
        for name, label in (("cards", "Pick from setups"), ("manual", "Adjust manually")):
            button = Gtk.ToggleButton(label=label)
            if first is None:
                first = button
            else:
                button.set_group(first)
            button.connect("toggled", lambda b, n=name: b.get_active()
                           and views.set_visible_child_name(n))
            switch.append(button)
            buttons[name] = button
        box.append(switch)
        box.append(views)
        views.add_named(self._mix_slot_flow(slot, key), "cards")
        note = Gtk.Label(xalign=0, wrap=True)
        note.add_css_class("dim-label")
        manual = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        column.append(note)
        column.append(manual)
        clamp = Adw.Clamp(maximum_size=800)
        clamp.set_child(column)
        views.add_named(clamp, "manual")
        buttons[start].set_active(True)
        views.set_visible_child_name(start)
        self._mix_manual[key] = (manual, note)
        # The setting slots' rows are built once; the app slots' rows depend on
        # the installed part, so they're built in _refresh_mix_manual.
        if slot in mix_mod.SLOT_IDS:
            sync = self._mix_sync.setdefault(key, {})
            if slot == "colors":
                manual.append(self._mix_colour_manual(sync))
            for group_id in self._MIX_SETTING_GROUPS.get(slot, ()):
                group = schema.group(group_id)
                manual.append(group_to_widget(group, self.state, sync=sync))
            note.set_text(
                "You can change your current settings here without picking a card; "
                "changes apply immediately. If you pick a card for this slot and press "
                "\"Apply mix\", the card's values overwrite these; "
                "emptying the slot returns to your settings from before the mix.")
        return box

    def _mix_colour_manual(self, sync: dict) -> Gtk.Widget:
        """Color scheme: preset palette + single colors (writes the same settings as
        the editor on Appearance: THEME and CUSTOM_COLORS)."""
        group = Adw.PreferencesGroup(
            title="Color scheme",
            description="Pick a palette, then change any color one by one. "
                        "Mix parts like the bar and launcher are painted in these "
                        "colors too (the parts are repainted on the next \"Apply "
                        "mix\").")
        values = ["auto", *themes.names()]
        labels = ["From wallpaper (auto)", *themes.names()]
        row = Adw.ComboRow(title="Palette", model=Gtk.StringList.new(labels))
        row.set_enable_search(True)

        def sync_theme() -> None:
            theme = self.state.get("THEME")
            index = values.index(theme) if theme in values else Gtk.INVALID_LIST_POSITION
            if row.get_selected() != index:
                row.set_selected(index)

        def picked(r, _param) -> None:
            index = r.get_selected()
            if not 0 <= index < len(values) or values[index] == self.state.get("THEME"):
                return
            # When the theme changes, manual color edits lose their meaning
            self.state.set("CUSTOM_COLORS", "")
            self.state.set("THEME", values[index])
            self._sync_colour_buttons()

        sync_theme()
        row.connect("notify::selected", picked)
        sync["THEME"] = sync_theme
        group.add(row)
        for widget in self._colour_rows():
            group.add(widget)
        return group

    def _refresh_mix_manual(self) -> None:
        """Redraws the app slots' manual settings according to the installed part."""
        installed = (mix_mod.read_state().get("installed") or {}).get("parts") or {}
        for key, (box, note) in list(self._mix_manual.items()):
            slot = key.split("@")[0]
            if slot not in mix_mod.APP_SLOT_IDS:
                continue
            while (child := box.get_first_child()) is not None:
                box.remove(child)
            sync = self._mix_sync[key] = {}
            ref = installed.get(slot, "")
            if ref:
                note.set_text(f"Currently installed: {mix_mod.part_label(self.root, ref)}. "
                              "The part comes with the author's own files; its colors "
                              "are painted in the colors from the Color scheme tab.")
                box.append(self._mix_part_manual(slot, ref))
                continue
            inline, page_id = self._MIX_OWN_SETTINGS[slot]
            note.set_text("This slot is empty: your own program is used. Its settings "
                          "are here; if you pick a card and apply it, that part's "
                          "settings show up here.")
            for group_id in inline:
                group = schema.group(group_id)
                box.append(group_to_widget(group, self.state, sync=sync))
            for category in self.catalog.categories:
                if category.id == self._MIX_OWN_AXES.get(slot):
                    box.append(self._app_axis_group(category, sync=sync))
            box.append(self._mix_page_link(page_id))

    def _mix_page_link(self, page_id: str) -> Gtk.Widget:
        title = next((t for pid, t, _i in self.pages if pid == page_id), page_id)
        group = Adw.PreferencesGroup()
        row = Adw.ActionRow(title=esc(f"All settings: {title}"),
                            subtitle="Opens this section's detailed page")
        row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        row.set_activatable(True)
        row.connect("activated", lambda _r: self._mix_goto(page_id))
        group.add(row)
        return group

    def _mix_goto(self, page_id: str) -> None:
        """From the mix window to a page: if the window is open it closes first,
        otherwise the page would stay behind it."""
        dialog = self.get_visible_dialog()
        if dialog is not None:
            dialog.close()
        self._goto_page(page_id)

    def _mix_part_manual(self, slot: str, ref: str) -> Gtk.Widget:
        """Settings of an installed part: for the bar, the fields are on the Status Bar
        page (ricebar); for every part, opening the author's files."""
        group = Adw.PreferencesGroup()
        if slot == "bar":
            try:
                bar = ricebar_mod.detect(self.root)
            except (OSError, ValueError, KeyError):
                bar = None
            if bar is not None and bar.fields:
                row = Adw.ActionRow(
                    title="Adjust the bar",
                    subtitle=esc(f"{bar.label}: position, height, gaps, font, "
                                 "opacity, modules… (on the Status Bar page)"),
                    subtitle_lines=0)
                row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
                row.set_activatable(True)
                row.connect("activated", lambda _r: self._mix_goto("bar"))
                group.add(row)
            else:
                group.add(Adw.ActionRow(
                    title="This bar has no adjustable fields defined",
                    subtitle="You can change its settings in the author's files.",
                    subtitle_lines=0))
        try:
            _profile, part = mix_mod.find_part(self.root, ref)
            paths = [rice_mod.expand(p, Path.home()) for p in part.paths]
        except (KeyError, OSError, ValueError):
            paths = []
        for path in paths:
            row = Adw.ActionRow(title=esc(path.name),
                                subtitle=esc(str(path).replace(str(Path.home()), "~", 1)))
            button = Gtk.Button(label="Open", valign=Gtk.Align.CENTER)
            button.set_tooltip_text("Opens the file or folder with the default program")
            button.set_sensitive(path.exists())
            button.connect("clicked", lambda _b, p=path: Gio.AppInfo.launch_default_for_uri(
                Gio.File.new_for_path(str(p)).get_uri(), None))
            row.add_suffix(button)
            group.add(row)
        return group

    def _mix_slot_flow(self, slot: str, key: str = "") -> Gtk.Widget:
        flow = self._gallery_flow()
        cards: list[tuple[Gtk.Widget, str]] = []
        for value, title, subtitle, preview in self._mix_options(slot):
            card = self._mix_card(slot, value, title, subtitle, preview,
                                  aur=self._mix_part_aur(slot, value))
            flow.append(card)
            cards.append((card, value))
        self._mix_cards[key or slot] = cards
        return flow

    def _mix_options(self, slot: str, compact: bool = False):
        """(value, title, subtitle, preview) — a slot's cards.

        ``compact``: the small cards of the Soup Maker strip (140×78)."""
        profiles = self._mix_parts.get("profiles", {})
        shots = presets_mod.default_dir(self.root, "profile")
        size = (140, 78) if compact else (220, 124)

        def shot(profile: str) -> Gtk.Widget:
            variant = ""
            if rice_mod.is_rice(self.root, profile):
                variant = rice_mod.load(self.root, profile).default_variant
            path = shots / f"{profile}.variants" / f"{variant}.jpg"
            if mix_mod.is_own(self._mix_parts, profile):
                # Our profiles have no screenshot set; their photo stands in.
                path = mix_mod.thumbnail_path(self.root, profile, mix_mod.OWN_VARIANT)
            # The bar card shows the screen's top strip (bars are at the top).
            return ShotPreview(path, width=size[0], height=size[1],
                               top=0.2 if slot == "bar" else 1.0)

        if slot == "colors":
            yield (mix_mod.COLORS_FROM_WALLPAPER, "From wallpaper",
                   "Colors are extracted from the wallpaper you choose",
                   PaletteStrip(None, width=size[0], height=size[1], label="auto"))
        for value, _text in (mix_mod.options(self._mix_parts, slot)
                            if slot in mix_mod.SLOT_IDS else []):
            if slot == "colors" and value == mix_mod.COLORS_FROM_WALLPAPER:
                continue
            profile, variant = mix_mod.split_ref(value)
            entry = profiles.get(profile, {})
            owner = entry.get("title", profile).split(" — ")[0]
            if slot == "wallpaper":
                info = entry["variants"][variant]
                thumb = mix_mod.thumbnail_path(self.root, profile, variant)
                preview = ShotPreview(thumb, width=size[0], height=size[1])
                note = "video — first frame" if info.get("video") else owner
                yield value, info["title"], note, preview
            elif slot == "colors":
                info = entry["variants"][variant]
                colors = info.get("colors") or {}
                note = colors.get("theme") or "extracted from wallpaper"
                yield (value, f"{owner} — {info['title']}", note,
                       PaletteStrip(mix_mod.palette_of(self._mix_parts, value),
                                    width=size[0], height=size[1]))
            else:                                         # look
                look = (entry.get("look") or {}).get("values", {})
                bits = [f"rounding {look.get('ROUNDING', '?')}",
                        f"gaps {look.get('GAPS_IN', '?')}/{look.get('GAPS_OUT', '?')}",
                        f"border {look.get('BORDER_SIZE', '?')}"]
                if look.get("BLUR") == "true":
                    bits.append("blur")
                if look.get("SHADOW") == "true":
                    bits.append("shadow")
                if look.get("ANIMATION_CUSTOM"):
                    bits.append("author's animations")
                yield value, entry.get("title", profile), " · ".join(bits), shot(profile)
        if slot in mix_mod.APP_SLOT_IDS:
            # Our profiles first: their bar/launcher/… are settings, not files.
            for name, entry in profiles.items():
                if not entry.get("own"):
                    continue
                summary = mix_mod.own_app_summary(self.root, name, slot)
                if summary:
                    yield name, entry.get("title", name), summary, shot(name)
        for value, part in self._mix_apps.get(slot, []):
            profile, _part_id = mix_mod.split_ref(value)
            owner = profiles.get(profile, {}).get("title", profile).split(" — ")[0]
            yield value, part.title or slot, owner, shot(profile)

    def _mix_part_aur(self, slot: str, value: str) -> list[str]:
        for part_value, part in self._mix_apps.get(slot, []):
            if part_value == value:
                return list(part.packages_aur)
        return []

    def _mix_card(self, slot: str, value: str, title: str, subtitle: str,
                  preview: Gtk.Widget, aur: list[str] | None = None) -> Gtk.Widget:
        button = Gtk.Button()
        button.add_css_class("card")
        button.add_css_class("hs-mix-card")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_size_request(236, -1)
        preview.set_margin_top(8)
        preview.set_margin_start(8)
        preview.set_margin_end(8)
        box.append(preview)
        name = Gtk.Label(label=title, xalign=0, wrap=True, max_width_chars=26, lines=2,
                         ellipsize=Pango.EllipsizeMode.END)
        name.add_css_class("heading")
        name.set_margin_start(10)
        name.set_margin_end(10)
        box.append(name)
        if aur:
            mark = aur_mod.badge(aur)
            mark.set_margin_start(10)
            box.append(mark)
        sub = Gtk.Label(label=subtitle, xalign=0, wrap=True, max_width_chars=30, lines=2,
                        ellipsize=Pango.EllipsizeMode.END)
        sub.add_css_class("caption")
        sub.add_css_class("dim-label")
        sub.set_margin_start(10)
        sub.set_margin_end(10)
        sub.set_margin_bottom(8)
        box.append(sub)
        button.set_child(box)
        button.connect("clicked", lambda _b: self._on_mix_pick(slot, value))
        return button

    def _on_mix_pick(self, slot: str, value: str) -> None:
        current = self._mix_pending.get(slot, "")
        self._mix_pending[slot] = "" if current == value else value
        self._refresh_mix()

    def _mix_label(self, slot: str, value: str) -> str:
        """Short name: "Caelestia · Violet" (full details on the cards)."""
        if not value:
            return "your own setting"
        if value == mix_mod.COLORS_FROM_WALLPAPER and slot == "colors":
            return "from wallpaper"
        profile, rest = mix_mod.split_ref(value)
        entry = self._mix_parts.get("profiles", {}).get(profile, {})
        owner = entry.get("title", profile).split(" — ")[0]
        if slot in ("wallpaper", "colors"):
            title = entry.get("variants", {}).get(rest, {}).get("title", rest)
            return f"{owner} · {title.split(' — ')[0]}"
        if slot == "look" or mix_mod.is_own_ref(self._mix_parts, slot, value):
            return owner
        try:
            _profile, part = mix_mod.find_part(self.root, value)
        except (KeyError, OSError, ValueError):
            return value
        return f"{owner} · {(part.title or slot).split(' — ')[0]}"

    def _refresh_mix(self) -> None:
        """Card highlights, step strip, live preview — from the pending selection."""
        current_wall = str(Path(self.state.get("WALLPAPER_PATH") or "").expanduser())
        for key, cards in self._mix_cards.items():
            chosen = self._mix_pending.get(key.split("@")[0], "")
            if not chosen and any(v == f"file:{current_wall}" for _c, v in cards):
                # One from your own folder is selected: it lights up, not "Your own setting".
                chosen = f"file:{current_wall}"
            for card, value in cards:
                if value == chosen:
                    card.add_css_class("hs-mix-selected")
                else:
                    card.remove_css_class("hs-mix-selected")
        applied = mix_mod.selection()
        labels = {}
        for index, (slot, label) in enumerate(getattr(self, "_mix_steps", []), start=1):
            value = self._mix_pending.get(slot, "")
            pending = value != applied.get(slot, "")
            short = self._mix_label(slot, value)
            labels[slot] = (label, short + (" (pending)" if pending else ""))
            _button, dot, caption = self._mix_step_buttons[slot]
            dot.set_label("✓" if value else str(index))
            (dot.add_css_class if value else dot.remove_css_class)("hs-step-done")
            caption.set_label(("• " if pending else "") + short)
            (caption.add_css_class if pending else caption.remove_css_class)("accent")
        if hasattr(self, "_mix_preview"):
            self._mix_preview.labels = labels
            self._mix_preview.update(mix_mod.preview_values(
                self.root, self._mix_parts, self._mix_pending, self.state.values))
            order = [s for s, _l in self._mix_steps]
            index = order.index(self._mix_step)
            label = dict(self._mix_steps)[self._mix_step]
            value = self._mix_pending.get(self._mix_step, "")
            self._mix_step_title.set_label(
                f"{index + 1}. {label} — {self._mix_label(self._mix_step, value)}")
            self._mix_clear_step.set_sensitive(bool(value))
            self._mix_prev.set_visible(index > 0)
            if index > 0:
                self._mix_prev.set_label(f"← {self._mix_steps[index - 1][1]}")
            self._mix_next.set_label(f"{self._mix_steps[index + 1][1]} →"
                                     if index + 1 < len(order) else "Apply mix")
        warnings = (mix_mod.read_state().get("installed") or {}).get("warnings", [])
        self._mix_status.set_text("\n".join(f"• {w}" for w in warnings))
        self._mix_status.set_visible(bool(warnings))

    def _open_mix_slot(self, slot: str, start: str = "") -> None:
        """A slot's separate window: picking from cards or manual settings.

        Same content as the tab, built separately under the "<slot>@dialog" key;
        when the window closes its entries (cards, rows, color buttons) are
        deleted so dead widgets don't keep getting updated.
        """
        key = f"{slot}@dialog"
        label = dict((*mix_mod.SLOTS, *mix_mod.APP_SLOTS)).get(slot, slot)
        if not start:
            # With no card selected the user most likely wants to adjust manually;
            # with a selection the cards (to change it) come first.
            start = "cards" if self._mix_pending.get(slot) else "manual"
        before = {k: list(v) for k, v in self._colour_buttons.items()}
        page = self._mix_slot_page(slot, key, start)
        if slot in mix_mod.APP_SLOT_IDS:
            self._refresh_mix_manual()
        page.set_margin_top(12)
        page.set_margin_bottom(18)
        page.set_margin_start(12)
        page.set_margin_end(12)

        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                      vexpand=True)
        scroller.set_child(page)
        header = Adw.HeaderBar()
        apply_button = Gtk.Button(label="Apply mix")
        apply_button.add_css_class("suggested-action")
        apply_button.set_tooltip_text("Applies the pending card selections "
                                      "(manual settings already apply immediately)")
        header.pack_end(apply_button)
        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.set_content(scroller)
        dialog = Adw.Dialog(title=label, content_width=820, content_height=680)
        dialog.set_child(view)

        def apply(_b) -> None:
            dialog.close()
            self._on_mix_apply()

        def closed(_d) -> None:
            self._mix_cards.pop(key, None)
            self._mix_manual.pop(key, None)
            self._mix_sync.pop(key, None)
            for colour, buttons in self._colour_buttons.items():
                keep = before.get(colour, [])
                buttons[:] = [b for b in buttons if b in keep]
            # Settings changed in the window should show in the tab's rows too.
            self._resync_rows()

        apply_button.connect("clicked", apply)
        dialog.connect("closed", closed)
        self._refresh_mix()
        dialog.present(self)

    def _refresh_mix_saved(self) -> None:
        names = sorted(mix_mod.read_state()["saved"])
        self._mix_saved_names = names
        self._mix_saved_model.splice(0, self._mix_saved_model.get_n_items(), names)
        for widget in self._mix_saved_widgets:
            widget.set_visible(bool(names))

    def _mix_saved_selected(self) -> str:
        index = self._mix_saved.get_selected()
        names = getattr(self, "_mix_saved_names", [])
        return names[index] if 0 <= index < len(names) else ""

    def _on_mix_save(self) -> None:
        if not any(self._mix_pending.values()):
            self._toast("No selection to save")
            return
        entry = Gtk.Entry(placeholder_text="e.g. evening mix")
        dialog = Adw.AlertDialog(heading="Save mix",
                                 body="This selection is stored under a name; later it loads "
                                      "back in one click.")
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Save")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")

        def done(_dialog, response: str) -> None:
            name = entry.get_text().strip()
            if response != "save" or not name:
                return
            mix_mod.save(name, chosen=self._mix_pending)
            self._refresh_mix_saved()
            self._toast(f"Mix saved: {name}")

        dialog.connect("response", done)
        dialog.present(self)

    def _on_mix_load(self) -> None:
        name = self._mix_saved_selected()
        if not name:
            return
        self._mix_pending = mix_mod.saved(name)
        self._refresh_mix()
        self._toast(f"'{name}' loaded — press \"Apply mix\" to apply it")

    def _on_mix_delete(self) -> None:
        name = self._mix_saved_selected()
        if not name:
            return
        mix_mod.delete_saved(name)
        self._refresh_mix_saved()
        self._toast(f"Save deleted: {name}")

    def _on_mix_clear(self) -> None:
        self._mix_pending = {slot: "" for slot in (*mix_mod.SLOT_IDS,
                                                   *mix_mod.APP_SLOT_IDS)}
        self._refresh_mix()
        self._on_mix_apply()

    def _on_mix_apply(self) -> None:
        """Applies the pending selection; asks first if a profile is active."""
        rice_state = rice_mod.read_state()
        if not rice_state:
            self._mix_apply_now()
            return
        dialog = Adw.AlertDialog(
            heading="Remove the installed profile?",
            body=(f"'{rice_state.get('profile')}' is currently installed. The mix's base "
                  "is your configuration; the author's files are removed and "
                  "your old ones come back from the backup. You can reinstall it "
                  "later from Profiles if you like."))
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("go", "Remove and apply")
        dialog.set_response_appearance("go", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _d, r: r == "go" and self._mix_apply_now())
        dialog.present(self)

    def _mix_apply_now(self) -> None:
        import threading

        pending = dict(self._mix_pending)
        try:
            mix_mod.validate_parts(self.root, {k: pending.get(k, "")
                                               for k in mix_mod.APP_SLOT_IDS})
        except ValueError as exc:
            self._toast(f"Could not apply mix: {exc}")
            return
        # Plan first: it fetches the wallpaper and can fail. Removing the
        # active rice before that left the user with neither the rice nor
        # the mix when, e.g., a wallpaper's package was not installed.
        try:
            changes, state = mix_mod.plan(
                self.root, {k: pending.get(k, "") for k in (*mix_mod.SLOT_IDS,
                                                            *mix_mod.APP_SLOT_IDS)},
                self.state.values)
        except (RuntimeError, KeyError, OSError, ValueError) as exc:
            self._toast(f"Could not apply mix: {exc}")
            return
        fade = None
        if rice_mod.read_state():
            fade = transition_mod.begin(label="Your mix is cooking…")
            restored = rice_mod.uninstall()
            self._toast(f"Profile removed ({len(restored)} files restored)")
        for key, value in changes.items():
            self.state.set(key, value)
        # Our profiles' bar/launcher/… pick programs: select them like a profile does.
        for var in ("TERMINAL", "LAUNCHER", "NOTIFIER", "WIDGET_ENGINE"):
            want = changes.get(var, "")
            if (want and self.catalog.component(want) and not self.state.is_selected(want)
                    and self.applier.component_installed(want)):
                self.state.toggle(want, True)
        if changes.get("BAR"):
            self._sync_bar_backend(changes["BAR"])
        state["parts"] = {k: v for k in mix_mod.APP_SLOT_IDS
                          if (v := pending.get(k, ""))
                          and not mix_mod.is_own_ref(self._mix_parts, k, v)}
        self.state.preset, self.state.variant = mix_mod.profile_marker(
            state, self.state.preset, self.state.variant)
        mix_mod.write_state(state)
        self._sync_all_rows()

        had_parts = bool((state.get("installed") or {}).get("owned"))
        if not state["parts"] and not had_parts:
            def applied() -> None:
                if fade:
                    fade.finish()
                self._refresh_mix()
                self._refresh_mix_manual()
                self._toast("Mix applied")
            self._run_apply(then=applied)
            return

        self._mix_apply_button.set_sensitive(False)
        self._mix_status.set_visible(True)
        self._mix_status.set_text("Installing parts… (unpacking the authors' files)")
        values = dict(self.state.values)
        parts = dict(state["parts"])

        def work() -> None:
            try:
                warnings = mix_mod.install_parts(self.root, parts, values)
                error = ""
            except (RuntimeError, KeyError, ValueError, OSError) as exc:
                warnings, error = [], str(exc)
            GLib.idle_add(finished, warnings, error)

        def finished(warnings: list[str], error: str) -> bool:
            def applied() -> None:
                self._mix_apply_button.set_sensitive(True)
                started = mix_mod.launch_parts()
                self.applier.start_missing(self.state.selected)
                if fade:
                    fade.finish()
                self._refresh_mix()
                self._refresh_mix_manual()
                if error:
                    self._toast(f"Could not install parts: {error}")
                else:
                    note = f" · {len(warnings)} notes" if warnings else ""
                    self._toast(f"Mix applied ({len(started)} programs started){note}")
            self._run_apply(then=applied)
            return False

        threading.Thread(target=work, daemon=True).start()

    # --- profiles -----------------------------------------------------------
    def _page_profiles(self) -> Gtk.Widget:
        """Profile gallery: authors' setups and our own designed
        st-* profiles together."""
        description = ("Each profile brings a color palette, window layout, "
                       "decoration and default bar/terminal/launcher "
                       "preset together. The sizes were taken from popular "
                       "Hyprland setups (which one is based on what: "
                       "docs/preset-sources.md); the colors come from this "
                       "project's own palettes. The previews are drawn from "
                       "the real values the setup will produce. "
                       "The first badge on each card says which program "
                       "draws the bar (Waybar · HyprPanel · Quickshell · "
                       "Wayle); applying the profile selects that program too, and "
                       "if it isn't installed the badge says so. After applying, you "
                       "can change any setting from the other pages.")
        if not self.presets:
            scroller, outer = self._gallery_page("Profiles", description)
            outer.append(Adw.ActionRow(
                title="No profiles found",
                subtitle=f"{presets_mod.default_dir(self.root, 'profile')} is empty"))
            return scroller

        resolved = [(p, presets_mod.resolve_chain(self.root, profile=p.name))
                    for p in self.presets if not p.group]
        own_count = sum(1 for p, _v in resolved if not rice_mod.is_rice(self.root, p.name))

        # Showcase design (2026-10-04, the user picked "1 · Showcase" out of 5
        # drafts): a large feature of the profile currently in use at the top,
        # with filter buttons and the card grid below.
        scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        for side in ("top", "bottom", "start", "end"):
            getattr(outer, f"set_margin_{side}")(22 if side in ("top", "bottom") else 26)
        scroller.set_child(outer)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        title = Gtk.Label(label="Profiles", xalign=0)
        title.add_css_class("title-1")
        titles.append(title)
        count = Gtk.Label(
            label=f"{len(resolved)} profiles · {own_count} ours, "
                  f"{len(resolved) - own_count} authors' own setups",
            xalign=0)
        count.add_css_class("dim-label")
        titles.append(count)
        head.append(titles)
        self._profile_search = Gtk.SearchEntry(placeholder_text="Search profiles…",
                                               valign=Gtk.Align.END, width_chars=24)
        self._profile_search.connect("search-changed", lambda _e: self._filter_profiles())
        head.append(self._profile_search)
        outer.append(head)

        self._profile_hero = Adw.Bin()
        self._profile_hero_name = None
        self._profile_resolved = dict((p.name, (p, v)) for p, v in resolved)
        outer.append(self._profile_hero)
        self._refresh_profile_hero()

        chips = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._profile_chip = "all"
        first: Gtk.ToggleButton | None = None
        for chip_id, label in (("all", f"All {len(resolved)}"),
                               ("own", f"Ours {own_count}"),
                               ("author", f"Authors' {len(resolved) - own_count}"),
                               ("light", "Light theme"),
                               ("noaur", "No AUR needed"),
                               ("motion", "Animated wallpaper")):
            button = Gtk.ToggleButton(label=label)
            button.add_css_class("pill")
            if first is None:
                first = button
                button.set_active(True)
            else:
                button.set_group(first)
            button.connect("toggled", lambda b, c=chip_id: b.get_active()
                           and self._set_profile_chip(c))
            chips.append(button)
        outer.append(chips)

        flow = self._gallery_flow()
        self._profile_cards: list[tuple[Gtk.Widget, dict]] = []
        self._fill_profile_flow(flow, resolved, self._profile_cards)
        outer.append(flow)
        self._profile_empty = Gtk.Label(label="No profiles match this filter", visible=False)
        self._profile_empty.add_css_class("dim-label")
        outer.append(self._profile_empty)

        # Import by link (importer.py): the repo is pinned to a fixed commit, its
        # layout is recognized, and a report is shown before installing.
        import_group = Adw.PreferencesGroup(
            title="Add by link",
            description="Paste the GitHub link of a dotfiles repo (e.g. "
                        "github.com/owner/repo). The repo is analyzed, and before "
                        "installing you're shown what will be installed and which "
                        "commands will run at startup. The author's install script "
                        "is not run.")
        self._import_row = Adw.EntryRow(title="Repository link")
        self._import_button = Gtk.Button(label="Inspect", valign=Gtk.Align.CENTER)
        self._import_button.add_css_class("suggested-action")
        self._import_button.connect("clicked", lambda _b: self._on_import_url())
        self._import_row.add_suffix(self._import_button)
        self._import_row.connect("entry-activated", lambda _r: self._on_import_url())
        import_group.add(self._import_row)
        import_group.set_margin_top(12)
        clamp = Adw.Clamp(maximum_size=800)
        clamp.set_child(import_group)
        outer.append(clamp)
        return scroller

    def _set_profile_chip(self, chip: str) -> None:
        self._profile_chip = chip
        self._filter_profiles()

    def _filter_profiles(self) -> None:
        """Filter button + search box (both together)."""
        chip = getattr(self, "_profile_chip", "all")
        query = fold(self._profile_search.get_text().strip()) \
            if hasattr(self, "_profile_search") else ""
        shown = 0
        for child, meta in getattr(self, "_profile_cards", []):
            ok = {"all": True, "own": meta["own"], "author": not meta["own"],
                  "light": meta["light"], "noaur": not meta["aur"],
                  "motion": meta["motion"]}.get(chip, True)
            ok = ok and (not query or query in meta["text"])
            if child is not None:
                child.set_visible(ok)
            shown += ok
        if hasattr(self, "_profile_empty"):
            self._profile_empty.set_visible(shown == 0)

    def _refresh_profile_hero(self) -> None:
        """Showcase: the profile currently in use (else the first one, "featured")."""
        hero = getattr(self, "_profile_hero", None)
        resolved = getattr(self, "_profile_resolved", {})
        if hero is None or not resolved:
            return
        current = self.state.preset if self.state.preset in resolved else ""
        name = current or next(iter(resolved))
        if name == self._profile_hero_name:
            return
        self._profile_hero_name = name
        preset, values = resolved[name]
        is_rice = rice_mod.is_rice(self.root, name)

        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        card.add_css_class("card")
        card.set_overflow(Gtk.Overflow.HIDDEN)
        card.append(self._profile_preview(name, values.get("PROFILE_VARIANT", ""), values,
                                          width=480, height=270))
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, hexpand=True)
        for side in ("top", "bottom", "start", "end"):
            getattr(info, f"set_margin_{side}")(22 if side in ("top", "bottom") else 26)

        pills = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        def pill(text: str, accent: bool = False) -> None:
            label = Gtk.Label(label=text)
            label.add_css_class("caption")
            label.add_css_class("hs-hero-pill")
            if accent:
                label.add_css_class("hs-hero-pill-on")
            pills.append(label)
        pill("Currently in use" if current else "Featured", accent=True)
        if is_rice:
            manifest = rice_mod.load(self.root, name)
            pill("@" + manifest.repo.removeprefix("https://github.com/").split("/")[0])
            if manifest.packages_aur:
                pills.append(aur_mod.badge(manifest.packages_aur))
        else:
            pill("Ours")
            aur = self._values_aur(values)
            if aur:
                pills.append(aur_mod.badge(aur))
        if values.get("WALLPAPER_DAEMON") == "wallpaperengine":
            pill("Wallpaper Engine")
        info.append(pills)

        title, _sep, sub = preset.label.partition(" — ")
        name_label = Gtk.Label(label=title, xalign=0, wrap=True)
        name_label.add_css_class("title-1")
        info.append(name_label)
        if sub:
            sub_label = Gtk.Label(label=sub, xalign=0)
            sub_label.add_css_class("heading")
            sub_label.add_css_class("dim-label")
            info.append(sub_label)
        desc = Gtk.Label(label=" ".join(preset.desc.split()), xalign=0, wrap=True,
                         lines=4, ellipsize=Pango.EllipsizeMode.END, max_width_chars=60)
        desc.add_css_class("dim-label")
        info.append(desc)
        theme_name = values.get("THEME", "")
        if not is_rice and theme_name and theme_name != "auto":
            palette = themes.resolve(theme_name)
            info.append(_swatch_strip(
                [palette[k] for k in ("BG", "SURFACE", "ACCENT", "ACCENT2", "FG") if palette.get(k)],
                26))
        spacer = Gtk.Box(vexpand=True)
        info.append(spacer)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        apply = Gtk.Button(label="Reapply" if current else "Use this profile")
        apply.add_css_class("suggested-action")
        apply.add_css_class("pill")
        apply.connect("clicked", lambda _b, n=name: self._on_profile_preset(n))
        actions.append(apply)
        info.append(actions)
        card.append(info)
        hero.set_child(card)

    def _fill_profile_flow(self, flow, resolved, cards: list) -> None:
        for preset, values in resolved:
            bar_name = values.get("BAR_PRESET", "")
            theme_name = values.get("THEME", themes.DEFAULT)
            palette = themes.resolve(theme_name)
            badges = [theme_name]
            if theme_name == "auto":
                # "auto" isn't a palette: the colors are extracted from the wallpaper,
                # so the card preview may not match the real result exactly.
                badges = ["auto — from wallpaper"]
            # The bar badge is ALWAYS written (not only "if different"):
            # the user should see which program will draw it before applying
            # the card. If it isn't installed, the bar won't open at all once the
            # profile is applied, so the badge says that too.
            backend = values.get("BAR", "") or _BAR_BACKENDS[0][0]
            label = dict(_BAR_BACKENDS).get(backend, backend)
            if self.applier.component_installed(backend):
                badges.append(f"{label} · {bar_name}" if bar_name else label)
            else:
                badges.append(f"{label} required — not installed")
            if themes.is_light(palette):
                badges.append("light")
            # Our own profiles select programs too: show which ones on the card.
            programs = [values.get(k, "") for k in ("TERMINAL", "LAUNCHER", "NOTIFIER")]
            if any(programs):
                badges.append(" · ".join(p for p in programs if p))
            imported = False
            aur = self._values_aur(values)
            own = not rice_mod.is_rice(self.root, preset.name)
            swatches = ([palette.get(k, "") for k in ("BG", "SURFACE", "ACCENT", "ACCENT2", "FG")]
                        if own and theme_name != "auto" else [])
            swatches = [c for c in swatches if c]
            if rice_mod.is_rice(self.root, preset.name):
                # The look is set by the author's own files; palette/bar
                # badges would be misleading on this card.
                manifest = rice_mod.load(self.root, preset.name)
                imported = rice_mod.is_imported(self.root, preset.name)
                badges = ["Added by link" if imported else "Author's files",
                          manifest.repo.removeprefix("https://github.com/")]
                aur = list(manifest.packages_aur)
            preview = self._profile_preview(preset.name,
                                            values.get("PROFILE_VARIANT", ""), values)
            picker = self._variant_picker(preset.name, values, preview)
            if imported:
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                if picker is not None:
                    box.append(picker)
                forget = Gtk.Button(label="Remove from list")
                forget.add_css_class("flat")
                forget.set_tooltip_text("Deletes the imported manifest (if installed, first "
                                        "switch to another profile or uninstall it).")
                forget.connect("clicked", lambda _b, n=preset.name: self._on_forget_import(n))
                box.append(forget)
                extra_widget = box
            else:
                extra_widget = picker
            card = self._gallery_card(
                preset.label, preset.desc, preview, badges,
                lambda _b, name=preset.name, pick=picker:
                    self._on_profile_preset(name, self._picked_variant(pick)),
                apply_label="Use this profile", extra=extra_widget, aur=aur,
                swatches=swatches)
            flow.append(card)
            # FlowBox wraps an added widget in a FlowBoxChild; that wrapper is what
            # must be hidden, not the card itself. The metadata is for the
            # showcase's filter buttons and search box.
            cards.append((card.get_parent(), {
                "own": own, "light": themes.is_light(palette) and own,
                "aur": bool(aur), "motion": values.get("WALLPAPER_DAEMON") == "wallpaperengine",
                "text": fold(" ".join((preset.name, preset.label, preset.desc))),
            }))

    # --- import by link (importer.py) -------------------------------------
    def _on_import_url(self) -> None:
        import threading

        from .. import importer

        url = self._import_row.get_text().strip()
        if not url:
            return
        self._import_button.set_sensitive(False)
        self._import_button.set_label("Analyzing…")

        def work() -> None:
            try:
                report, error = importer.analyze(url), ""
            except (RuntimeError, ValueError, OSError) as exc:
                report, error = None, str(exc)
            GLib.idle_add(done, report, error)

        def done(report, error: str) -> bool:
            self._import_button.set_sensitive(True)
            self._import_button.set_label("Inspect")
            if report is None:
                self._toast(f"Could not import: {error}")
            else:
                self._show_import_report(report)
            return False

        threading.Thread(target=work, daemon=True).start()

    def _show_import_report(self, report) -> None:
        from .. import importer

        if rice_mod.is_rice(self.root, report.name) \
                and not rice_mod.is_imported(self.root, report.name):
            self._toast(f"'{report.name}' is the name of a setup bundled with the project")
            return
        text = Gtk.Label(label="\n".join(importer.describe(report)), xalign=0,
                         selectable=True, wrap=True)
        text.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        text.add_css_class("monospace")
        text.add_css_class("caption")
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                      propagate_natural_height=True,
                                      max_content_height=420, min_content_width=640)
        scroller.set_child(text)
        heading = f"{report.source.owner or report.source.repo}/{report.source.repo}"
        body = ("The following was recognized automatically. Saving adds it to the "
                "profile list and the Soup Maker page; installing needs a separate confirmation.")
        if report.flagged:
            body += (f"\n\nWARNING: {len(report.flagged)} lines look suspicious "
                     "(marked with '!' in the list). If you're not sure, don't save.")
        dialog = Adw.AlertDialog(heading=heading, body=body)
        if hasattr(dialog, "set_prefer_wide_layout"):          # libadwaita 1.6+
            dialog.set_prefer_wide_layout(True)
        dialog.set_extra_child(scroller)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Save")
        dialog.add_response("install", "Save and install…")
        dialog.set_response_appearance(
            "install", Adw.ResponseAppearance.DESTRUCTIVE if report.flagged
            else Adw.ResponseAppearance.SUGGESTED)
        dialog.set_close_response("cancel")

        def chosen(_dialog, response: str) -> None:
            if response in ("save", "install"):
                self._save_import(report, install=response == "install")

        dialog.connect("response", chosen)
        dialog.present(self)

    def _save_import(self, report, install: bool) -> None:
        import threading

        from .. import importer

        importer.write(report)
        self._toast(f"{report.name} saved — scanning parts…")

        def work() -> None:
            try:
                mix_mod.scan_imported(self.root, report.name, log=lambda *_: None)
                error = ""
            except Exception as exc:                              # noqa: BLE001
                error = str(exc)
            GLib.idle_add(done, error)

        def done(error: str) -> bool:
            self._reload_gallery_pages()
            if error:
                self._toast(f"{report.name} added (could not scan parts: {error})")
            else:
                self._toast(f"{report.name} added: Profiles and Soup Maker")
            if install:
                self._apply_rice(report.name, "")
            return False

        threading.Thread(target=work, daemon=True).start()

    def _on_forget_import(self, name: str) -> None:
        from .. import importer

        if rice_mod.read_state().get("profile") == name:
            self._toast(f"{name} is currently installed; switch to another profile first")
            return
        importer.remove(name)
        self._reload_gallery_pages()
        self._toast(f"{name} removed from the list")

    def _reload_gallery_pages(self) -> None:
        """Rebuilds the profile and mix pages (after an import)."""
        self.presets = presets_mod.load_profiles(self.root)
        visible = self.stack.get_visible_child_name()
        for page_id, builder in (("profiles", self._page_profiles),
                                 ("mix", self._page_mix)):
            old = self.stack.get_child_by_name(page_id)
            if old is None:
                continue
            self.stack.remove(old)
            self.stack.add_named(builder(), page_id)
        self._apply_level()
        if visible:
            self.stack.set_visible_child_name(visible)

    def _variant_picker(self, profile: str, values: dict[str, str],
                        preview: Gtk.Widget) -> Gtk.DropDown | None:
        """Dropdown for the profile's look variants (None if there are none).

        A setup often comes as the same layout + several wallpapers/palettes
        (see presets.variants_dir). When the choice changes, the card's preview
        is redrawn with that variant; "Use this profile" applies the selected
        variant.
        """
        variants = presets_mod.load_variants(self.root, profile)
        if not variants:
            return None
        names = [v.name for v in variants]
        picker = Gtk.DropDown.new_from_strings([v.label for v in variants])
        picker.set_tooltip_text("Variant: wallpaper and color palette")
        picker._variant_names = names                 # noqa: SLF001
        current = values.get("PROFILE_VARIANT", "")
        if current in names:
            picker.set_selected(names.index(current))

        # The preview is replaced when the variant changes (screenshot ↔ schematic);
        # this tracks the replaced widget.
        preview_holder = [preview]

        def changed(dropdown, _param) -> None:
            chosen = self._picked_variant(dropdown)
            resolved = presets_mod.resolve_chain(self.root, profile=profile,
                                                 variant=chosen)
            frame = preview_holder[0].get_parent()
            fresh = self._profile_preview(profile, chosen, resolved)
            if isinstance(frame, Gtk.Frame):
                frame.set_child(fresh)
                preview_holder[0] = fresh

        picker.connect("notify::selected", changed)
        return picker

    def _profile_preview(self, profile: str, variant: str,
                         values: dict[str, str], width: int = 300,
                         height: int = 170) -> Gtk.Widget:
        """The variant's real screenshot if there is one, else a schematic preview.

        Screenshots live in ``presets/profile/<profile>.variants/<variant>.jpg``: the
        setups were really installed and captured (author's shell, wallpaper).
        The schematic preview showed none of the details of Quickshell/eww
        shells.
        """
        if not variant and rice_mod.is_rice(self.root, profile):
            variant = rice_mod.load(self.root, profile).default_variant
        shot = (presets_mod.default_dir(self.root, "profile")
                / f"{profile}.variants" / f"{variant}.jpg")
        if variant and shot.is_file():
            return ShotPreview(shot, width=width, height=height)
        return ValuesPreview(values, width=width, height=height, root=self.root)

    @staticmethod
    def _picked_variant(picker: Gtk.DropDown | None) -> str:
        if picker is None:
            return ""
        names = getattr(picker, "_variant_names", [])
        index = picker.get_selected()
        return names[index] if 0 <= index < len(names) else ""

    def _on_profile_preset(self, name: str, variant: str = "") -> None:
        """Applies the profile; if a program is missing, asks about that first.

        If the bar program the profile points to (and a widget engine, if WIDGETS
        is set) isn't installed, the profile is applied but nothing changes on
        screen — since the template condition "HAS_<program>" fails, that program's
        configuration is never generated. Instead, what's missing is shown
        first and installed in a terminal with one button.
        """
        if rice_mod.is_rice(self.root, name):
            self._apply_rice(name, variant)
            return
        missing = self._profile_requirements(name)
        if missing:
            self._ask_install(name, missing, variant)
            return
        self._apply_profile_now(name, variant)

    # ------------------------------------------------- requirements check --
    def _profile_requirements(self, name: str) -> list[tuple[str, list[str]]]:
        """Components the profile needs that are NOT installed.

        The returned list is ``(component id, missing packages)`` pairs. If it's
        empty the profile can be applied as is.
        """
        values = presets_mod.resolve_chain(self.root, profile=name)
        needed = [values.get("BAR", "") or _BAR_BACKENDS[0][0]]
        if presets_mod.split_widgets(values.get("WIDGETS", "")):
            # Widgets aren't drawn without an engine; if an engine is already
            # installed (eww or quickshell) there's no point asking for a new one.
            engines = [c.id for cat in self.catalog.categories
                       if cat.id == "widget" for c in cat.components]
            if not any(self.applier.component_installed(e) for e in engines):
                needed.append(engines[0] if engines else "")
        # Terminal, launcher, notifications, wallpaper: if they weren't installed,
        # sync_profile_components didn't select them and only showed a
        # notification — on a fresh install the profile was applied only halfway.
        for var in self.state.PROFILE_COMPONENT_VARS:
            want = (values.get(var) or "").strip()
            if want and self.catalog.component(want) and want not in needed:
                needed.append(want)
        out = []
        for comp_id in needed:
            if not comp_id or self.applier.component_installed(comp_id):
                continue
            out.append((comp_id, self.applier.missing_packages(comp_id)
                        or self._component_packages(comp_id)))
        return out

    def _component_packages(self, comp_id: str) -> list[str]:
        comp = self.catalog.component(comp_id)
        return list(comp.repo) + list(comp.aur) if comp else []

    def _ask_install(self, profile: str,
                     missing: list[tuple[str, list[str]]],
                     variant: str = "") -> None:
        """Lists the missing programs and offers install / apply anyway."""
        lines = []
        for comp_id, packages in missing:
            comp = self.catalog.component(comp_id)
            title = comp.title if comp else comp_id
            lines.append(f"• {title} — {' '.join(packages)}")
        body = ("This profile is drawn with the programs below and they aren't "
                "installed. If applied without installing, the profile's bar (or "
                "widgets) won't show at all.\n\n" + "\n".join(lines) +
                "\n\n“Install and apply” opens a terminal and runs the command "
                "there — the password is asked in the terminal; this app never asks "
                "for sudo.")
        dialog = Adw.AlertDialog(heading="Missing programs", body=body)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("anyway", "Apply anyway")
        dialog.add_response("install", "Install and apply")
        dialog.set_response_appearance("install",
                                       Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("install")
        dialog.set_close_response("cancel")

        def _chosen(_dialog, response: str) -> None:
            if response == "cancel":
                return
            if response == "install":
                packages = [pkg for _c, pkgs in missing for pkg in pkgs]
                self._pending_profile = (profile, variant)
                self._install_in_terminal(list(dict.fromkeys(packages)),
                                          watch=True)
            self._apply_profile_now(profile, variant)

        dialog.connect("response", _chosen)
        dialog.present(self)

    # --- dependency check ---------------------------------------------------
    def _require(self, needed, what: str, on_ok, on_cancel=None,
                 chosen: str = "") -> None:
        """If ``needed`` is satisfied, ``on_ok``; otherwise ask, install or cancel.

        Rule: the programs a setting/widget/module needs are checked BEFORE it is
        turned on. Components whose packages are installed but which just aren't
        selected (and don't replace anything else) are selected without asking —
        that's what the user wants anyway. If something must be installed or
        would change the current selection, a dialog opens:

        * Install and enable — the missing ones are installed in a terminal (the
          password is asked there), components are selected, the value is written;
          when the install finishes the app notices by itself and re-applies.
        * Enable anyway — the value is written; no effect until the program arrives.
        * Cancel — nothing changes (``on_cancel`` reverts the row).

        ``chosen``: the component the user clicked directly. It replacing another
        selection is exactly what was wanted, so nothing is asked for that.
        """
        items = deps_mod.unmet(needed, self.catalog, self.state.selected,
                               self.applier.installed_packages())
        for item in items:
            if item.dep == chosen:
                item.replaces = ""
        silent = [i for i in items if i.only_unselected and not i.replaces]
        asked = [i for i in items if i not in silent]

        def select_silent() -> None:
            # Only if continuing: "Cancel" must change nothing.
            for item in silent:
                self.state.toggle(item.component, True)
            if silent:
                self._refresh_component_rows()
                self._toast("Selected: " + ", ".join(i.title for i in silent))

        if not asked:
            select_silent()
            on_ok()
            return

        packages = deps_mod.packages_of(asked)
        lines = []
        for item in asked:
            if item.packages:
                line = f"• {item.title} — not installed: {' '.join(item.packages)}"
            else:
                line = f"• {item.title} — installed, but not selected"
            if item.replaces:
                line += f" (if selected, replaces {item.replaces})"
            lines.append(line)
        body = (f"“{what}” needs the following:\n\n" + "\n".join(lines))
        if packages:
            body += ("\n\n“Install and enable” opens a terminal and runs the install "
                     "there — the password is asked in the terminal. When the "
                     "install finishes, the setting applies by itself.")
        dialog = Adw.AlertDialog(heading="Required program missing"
                                 if packages else "Component not selected",
                                 body=body)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("anyway", "Enable anyway")
        dialog.add_response("install", "Install and enable" if packages else "Select and enable")
        dialog.set_response_appearance("install",
                                       Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("install")
        dialog.set_close_response("cancel")

        def chosen(_dialog, response: str) -> None:
            if response == "cancel":
                if on_cancel is not None:
                    on_cancel()
                return
            select_silent()
            if response == "install":
                for item in asked:
                    if item.component:
                        self.state.toggle(item.component, True)
                self._refresh_component_rows()
                self._refresh_widget_engine()
                if packages:
                    self._install_in_terminal(packages, watch=True)
            on_ok()

        dialog.connect("response", chosen)
        dialog.present(self)

    def _watch_install(self, packages: list[str]) -> None:
        """Watches an install started in a terminal; applies when it's done.

        The install runs in a separate terminal with the user's password; we
        can't know when it will finish. pacman is queried every few seconds;
        once all packages show up the UI is refreshed and the settings are re-applied
        — so the user doesn't end up with "I installed it but it still doesn't work".
        """
        self._pending_install.update(packages)
        if self._install_poll:
            return
        deadline = time.monotonic() + 30 * 60

        def poll() -> bool:
            installed = self.applier.installed_packages(refresh=True)
            done = {p for p in self._pending_install if p in installed}
            if done:
                self._pending_install -= done
                self._after_install(sorted(done))
            if not self._pending_install or time.monotonic() > deadline:
                self._pending_install.clear()
                self._pending_profile = None
                self._install_poll = 0
                return False
            return True

        self._install_poll = GLib.timeout_add_seconds(4, poll)

    def _after_install(self, packages: list[str]) -> None:
        self._toast("Installed: " + ", ".join(packages) + " — applying")
        if self._pending_profile and self._pending_profile[0] == self.state.preset:
            # Programs that couldn't be selected while the profile was applied because
            # they weren't installed (terminal, launcher, notifications, wallpaper)
            # are selected now.
            name, _variant = self._pending_profile
            self._sync_bar_backend(profile_backend(self.root, name))
            self.state.sync_profile_components(
                self.root, name, installed=self.applier.component_installed)
        self._refresh_app_axis_rows()
        self._refresh_component_rows()
        self._refresh_widget_engine()
        self._refresh_widget_zones()
        rebuild = getattr(self, "_icon_gallery_rebuild", None)
        if rebuild is not None:               # so the new icon set shows on its card
            rebuild()
        # The render done before the package arrived skipped that section; redo it now.
        self._schedule_apply()

    def _install_in_terminal(self, packages: list[str],
                             watch: bool = False) -> None:
        """Starts the install in the user's terminal.

        The app itself doesn't install packages or ask for the sudo password (the
        README rule): the command runs in a visible terminal, the user sees what
        happens and can cancel. For AUR packages an installed helper
        (paru/yay) is looked for; if there is none the command stays with pacman and
        the terminal says what's missing.
        """
        if not packages:
            return
        commands = self._package_commands(*self._split_aur(packages))
        if not self._open_terminal(" && ".join(commands)):
            return
        if watch:
            self._watch_install(packages)
            self._toast("Install started in a terminal; it will apply by itself "
                        "when done")
        else:
            self._toast("Install started in a terminal; reapply the profile "
                        "when it's done")

    def _sync_priority(self, mode: str) -> None:
        """SWITCHER_PRIORITY → /etc/ananicy.d rule, in the user's terminal.

        If the system rule is already in the requested mode nothing opens (so sudo
        isn't asked every time the profile is reapplied).
        """
        from .. import priority as priority_mod
        if mode not in priority_mod.MODES:
            return
        if not priority_mod.available():
            if mode != "off":
                self._toast("ananicy-cpp isn't installed — no priority fix needed")
            return
        if priority_mod.current_mode() == mode:
            return
        if not self._open_terminal(priority_mod.script(mode), pause=False):
            return
        self._toast("Applying the priority setting in a terminal (sudo password there)")

    def _split_aur(self, packages: list[str]) -> tuple[list[str], list[str]]:
        """(official repo, AUR) — based on what the catalog lists as AUR."""
        known_aur = {pkg for cat in self.catalog.categories
                     for comp in cat.components for pkg in comp.aur}
        repo = [p for p in packages if p not in known_aur]
        return repo, [p for p in packages if p in known_aur]

    def _values_aur(self, values: dict[str, str]) -> list[str]:
        """AUR packages of the programs a profile selects (BAR, LAUNCHER…)."""
        packages: list[str] = []
        for cat in self.catalog.categories:
            if cat.var == "WIDGET_ENGINE" and not values.get("WIDGET_SET"):
                continue              # without widgets the engine doesn't run either
            if cat.var and values.get(cat.var):
                packages += self._comp_aur(values[cat.var])
        return packages

    def _comp_aur(self, comp_id: str) -> list[str]:
        comp = self.catalog.component(comp_id)
        return list(comp.aur) if comp else []

    def _install_command(self, packages: list[str]) -> str:
        """Install command to copy. AUR packages can't be installed with pacman;
        a helper (paru if none is found) is written for them."""
        repo, aur = self._split_aur(packages)
        commands = []
        if repo:
            commands.append("sudo pacman -S --needed " + " ".join(repo))
        if aur:
            helper = next((h for h in ("paru", "yay") if shutil.which(h)), "paru")
            commands.append(f"{helper} -S --needed " + " ".join(aur))
        return " && ".join(commands)

    @staticmethod
    def _package_commands(repo: list[str], aur: list[str]) -> list[str]:
        """Commands to run in the terminal for repo and AUR packages."""
        helper = next((h for h in ("paru", "yay") if shutil.which(h)), "")
        commands = []
        if repo:
            commands.append("sudo pacman -S --needed "
                            + " ".join(shlex.quote(p) for p in repo))
        if aur:
            if helper:
                commands.append(f"{helper} -S --needed "
                                + " ".join(shlex.quote(p) for p in aur))
            else:
                commands.append(
                    "echo 'No AUR helper (paru/yay) installed; these "
                    f"packages must be installed by hand: {' '.join(aur)}'")
        return commands

    # --- profiles from authors (rice.py) ----------------------------------
    def _apply_rice(self, name: str, variant: str = "") -> None:
        """Installs the author's files — first shows what will happen and asks to confirm.

        The install runs in a terminal: missing packages (the sudo password is
        asked there), then ``python3 -m hyprsetup rice install``. The user sees
        every step; this app never asks for sudo.
        """
        manifest = rice_mod.load(self.root, name)
        variant = variant or manifest.default_variant
        installed = self.applier.installed_packages()
        missing_repo = [p for p in manifest.packages_repo
                        if installed and p not in installed]
        missing_aur = [p for p in manifest.packages_aur
                       if installed and p not in installed]
        # A package the manifest calls "repo" but which is in no configured repo
        # (in the repos on CachyOS, AUR on plain Arch: wlogout, mpvpaper…) showed
        # under "Official repo" and broke sudo pacman; it moves to the AUR list.
        found = deps_mod.in_sync_repos(missing_repo)
        if found:                    # left alone if pacman is missing/didn't run
            missing_aur += [p for p in missing_repo if p not in found]
            missing_repo = [p for p in missing_repo if p in found]
        targets =[i.dest for i in manifest.installs if i.group == "core"]
        local = all(rice_mod.vendor_archive(manifest.vendor, url, commit)
                    for url, commit in manifest.sources())
        origin = ("from the archive bundled with the project — no internet needed" if local
                  else "downloaded from GitHub")
        # With the target folders written into the body (end4: 18 lines) the dialog
        # filled up and the package list got squeezed into 3 lines in an inner
        # scroller; most AUR packages and the official repo never showed. Packages
        # come first, folders in an expander row.
        lines = [f"Source: {manifest.repo} ({manifest.commit[:8]}), {origin}"]
        chosen = manifest.variants.get(variant)
        if chosen is not None and not chosen.wallpaper:
            lines.append(f"Note: the wallpaper of the '{chosen.title}' variant "
                         "hasn't been found yet.")
        dialog = Adw.AlertDialog(heading=f"Install {name}?",
                                 body="\n".join(lines))
        if hasattr(dialog, "set_prefer_wide_layout"):          # libadwaita 1.6+
            dialog.set_prefer_wide_layout(True)
        already = (len(manifest.packages_repo) + len(manifest.packages_aur)
                   - len(missing_repo) - len(missing_aur))
        content = self._rice_packages_view(missing_repo, missing_aur, already)
        places = Adw.ExpanderRow(
            title=f"Locations to install to — {len(targets)}",
            subtitle="Existing ones are backed up; revert with 'python3 -m hyprsetup rice "
                     "uninstall'.")
        places.set_subtitle_lines(0)
        for target in targets:
            row = Adw.ActionRow(title=GLib.markup_escape_text(target))
            row.set_title_selectable(True)
            row.add_css_class("monospace")
            places.add_row(row)
        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        listbox.add_css_class("boxed-list")
        listbox.append(places)
        content.append(listbox)
        dialog.set_extra_child(content)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("install", "Install")
        dialog.set_response_appearance("install", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("install")
        dialog.set_close_response("cancel")

        def chosen_response(_dialog, response: str) -> None:
            if response != "install":
                return
            # The profile's .conf values (theme, gaps…) apply to the files this
            # project generates itself (e.g. if the author didn't share a Hyprland
            # config). They're saved; when the install finishes the terminal
            # re-applies this file (python -m hyprsetup rice install → _reapply).
            self.state.apply_profile_preset(self.root, name, variant)
            self._save_conf()
            commands = self._package_commands(missing_repo, missing_aur)
            commands.append(
                f"PYTHONPATH={shlex.quote(str(self.root / 'python'))} "
                f"python3 -m hyprsetup rice install {shlex.quote(name)} "
                f"--variant {shlex.quote(variant)} "
                f"--root {shlex.quote(str(self.root))}")
            if not self._open_terminal(" && ".join(commands)):
                return
            self._sync_all_rows()
            self._toast(f"{name} install started in a terminal")

        dialog.connect("response", chosen_response)
        dialog.present(self)

    @staticmethod
    def _rice_packages_view(repo: list[str], aur: list[str],
                            already: int) -> Gtk.Box:
        """Packages to install, by name: AUR first (each with how it will be installed),
        then the official repo. The confirmation dialog just saying "3 AUR" didn't
        show what was being agreed to."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        if not repo and not aur:
            label = Gtk.Label(label="All required packages are already installed.",
                              xalign=0, wrap=True)
            label.add_css_class("dim-label")
            box.append(label)
            return box

        if aur:
            in_repo = deps_mod.in_sync_repos(aur)
            notes = {pkg: deps_mod.aur_note(pkg, in_repo) for pkg in aur}
            compiled = sum(1 for _n, builds in notes.values() if builds)
            helper = next((h for h in ("paru", "yay") if shutil.which(h)), "")
            if helper:
                how = (f"Installed with {helper}; the PKGBUILD review and confirmation "
                       "are asked in the terminal.")
            else:
                how = ("No AUR helper (paru/yay) installed — these packages "
                       "won't be installed; you'll have to install them by hand.")
            group = Adw.PreferencesGroup(
                title=f"{len(aur)} packages"
                      + (f" ({compiled} of them are compiled on this machine)"
                         if compiled else ""),
                description="Community packages, unsigned. " + how)
            group.set_header_suffix(aur_mod.badge(aur))
            for pkg in aur:
                note, builds = notes[pkg]
                row = Adw.ActionRow(title=GLib.markup_escape_text(pkg),
                                    subtitle=note)
                row.set_title_selectable(True)
                row.set_title_lines(0)
                row.set_subtitle_lines(0)
                if builds:
                    row.add_css_class("warning")
                group.add(row)
            box.append(group)

        if repo:
            group = Adw.PreferencesGroup(
                title=f"Official repo — {len(repo)} packages",
                description="Signed binaries, installed with sudo pacman.")
            names = Gtk.Label(label="  ".join(repo), xalign=0, wrap=True,
                              selectable=True)
            names.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            names.add_css_class("monospace")
            group.add(names)
            box.append(group)

        if already > 0:
            label = Gtk.Label(label=f"{already} packages already installed, "
                                    "won't be reinstalled.", xalign=0)
            label.add_css_class("dim-label")
            label.add_css_class("caption")
            box.append(label)
        # No inner scroller: AlertDialog scrolls the whole content itself;
        # in a nested scroller the list got squeezed into a few lines.
        return box

    def _group_widget(self, group_id: str, **kwargs) -> Gtk.Widget:
        """Turns a schema group into a settings group whose rows sync on change."""
        return group_to_widget(schema.group(group_id), self.state, sync=self._sync_rows,
                               rows=self._setting_rows, **kwargs)

    def _open_terminal(self, script: str, pause: bool = True) -> bool:
        """Starts the script in a visible terminal; if that fails, warns and returns False.

        ``pause``: when done, the window stays open until Enter (so the output can be read).
        """
        if pause:
            script += "\necho; read -p 'Done, press Enter to close...'"
        if self._spawn_floating(self._terminal_argv(script, scope=False)):
            return True
        try:
            subprocess.Popen(self._terminal_argv(script), start_new_session=True)
        except OSError as exc:
            self._toast(f"Could not open terminal: {exc}")
            return False
        return True

    #: Hyprland rules for the install terminal. The settings app is a floating
    #: window; a terminal opened tiled stayed BEHIND it, and the window asking for
    #: the sudo password wasn't visible. A floating, centered terminal comes to
    #: the top and takes focus; the settings app stays where it is.
    _TERMINAL_RULES = "float on; center on; size 60% 60%"

    def _spawn_floating(self, argv: list[str], rules: str = "",
                        window_class: str = "") -> bool:
        """Has Hyprland open it with ``exec [rules] command``; False if that fails.

        Since the rules are passed with the command, nothing needs to be in the
        user's (or a profile's) windowrules.conf. The process becomes a child
        of Hyprland: the install isn't cut short even if the app closes.
        """
        if (not os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
                or not shutil.which("hyprctl") or argv[0] == "bash"):
            return False
        command = f"[{rules or self._TERMINAL_RULES}] {shlex.join(argv)}"
        if self._hyprctl("dispatch", "exec", command) != "ok":
            return False
        # A new window doesn't always take focus (if focus is on another window at
        # that moment Hyprland keeps it): once open it's raised and focused.
        selector = f"class:^({re.escape(window_class or self.TERMINAL_CLASS)})$"
        tries = [0]

        def raise_terminal() -> bool:
            tries[0] += 1
            if self._hyprctl("dispatch", "focuswindow", selector) == "ok":
                self._hyprctl("dispatch", "alterzorder", f"top,{selector}")
                return False
            return tries[0] < 20                     # wait ~5 s
        GLib.timeout_add(250, raise_terminal)
        return True

    @staticmethod
    def _hyprctl(*args: str) -> str:
        try:
            return subprocess.run(["hyprctl", *args], capture_output=True,
                                  text=True, timeout=5, check=False).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""

    #: Window class of the install terminal (selector for raising it).
    TERMINAL_CLASS = "dev.hyprsetup.Terminal"
    #: Flag giving the terminal a window class; unlisted ones (xterm…) open without one.
    _CLASS_FLAGS = {"kitty": ["--class", TERMINAL_CLASS],
                    "alacritty": ["--class", TERMINAL_CLASS],
                    "foot": [f"--app-id={TERMINAL_CLASS}"],
                    "ghostty": [f"--class={TERMINAL_CLASS}"],
                    "wezterm": ["--class", TERMINAL_CLASS]}

    def _terminal_argv(self, script: str, scope: bool = True) -> list[str]:
        """Argument list that runs a shell command in the selected terminal.

        Terminals are similar in their "-e" flag but WezTerm differs
        ("start --"); if no installed terminal is found, bash is tried
        directly (so the command runs even without a desktop session).
        """
        term = self.state.primary("terminal")
        comp = self.catalog.component(term) if term else None
        binary = (comp.exec.split()[0] if comp and comp.exec else "")
        if not binary or not shutil.which(binary):
            binary = next((b for b in ("kitty", "foot", "alacritty", "ghostty",
                                       "wezterm", "xterm") if shutil.which(b)), "")
        if not binary:
            argv = ["bash", "-lc", script]
        elif binary == "wezterm":
            argv = [binary, "start", *self._CLASS_FLAGS["wezterm"],
                    "--", "bash", "-lc", script]
        else:
            argv = [binary, *self._CLASS_FLAGS.get(binary, []),
                    "-e", "bash", "-lc", script]
        # The app runs inside a systemd unit (desktop launcher:
        # app-…hyprsetup-gui@….service, KillMode=control-group): when the app
        # closed, the terminal in the unit was killed too — a half-finished install,
        # a wallpaper never applied. The terminal starts in its own scope.
        if scope and shutil.which("systemd-run"):
            argv = ["systemd-run", "--user", "--scope", "--quiet", "--collect", "--", *argv]
        return argv

    def _apply_profile_now(self, name: str, variant: str = "") -> None:
        # When switching to a template profile while an author profile is active,
        # the author's files are removed first and the old files come back from the
        # backup; otherwise template output would never be written to paths they own.
        fade = None
        if rice_mod.read_state():
            # Don't let the screen go dark until the author's bar/wallpaper close
            # and yours open (transition.py).
            fade = transition_mod.begin(label=f"{name} is cooking…")
            restored = rice_mod.uninstall()
            self._toast(f"Profile removed ({len(restored)} files "
                        "restored from backup)")
            # The profile closed your bar when opening its own; since the files
            # didn't change, applying doesn't restart it. Missing processes are
            # started after the delayed apply (debounce) finishes.
            restart_missing = True
        else:
            restart_missing = False
        self.state.apply_profile_preset(self.root, name, variant)
        note = self._sync_bar_backend(profile_backend(self.root, name))
        extra = self.state.sync_profile_components(
            self.root, name, installed=self.applier.component_installed)
        if extra:
            note += " · " + ", ".join(extra)
        self._sync_all_rows()
        if hasattr(self, "_rice_bar_group"):
            self._refresh_rice_bar()
        self._refresh_bar_status()
        self._refresh_component_rows()
        if restart_missing:
            # Missing processes are started AFTER the round with the new values
            # FINISHES; starting them mid-round could open the bar twice.
            def restarted() -> None:
                self.applier.start_missing(self.state.selected)
                if fade:
                    fade.finish()
            self._after_apply(restarted)
        pinned = self.state.pinned_bar
        if pinned:
            self._toast(f"Profile applied: {name} · bar preset '{pinned}' "
                        f"was kept because it's your choice{note}")
        else:
            self._toast(f"Profile applied: {name}{note}")

    def _sync_bar_backend(self, backend: str) -> str:
        """Selects the bar program the profile wants.

        The condition at the top of the templates is "BAR==<backend> && HAS_<backend>",
        and BAR is derived from the selection (apply.export_vars). So if the selection
        doesn't change, the profile's Quickshell bar is never generated; the user
        applies the profile and the bar stays as it was. _on_bar_preset did this when a
        bar PRESET was picked; there was no equivalent when applying a profile.

        The returned text is appended to the notification ("" = nothing to say).
        """
        if not backend or self.state.is_selected(backend):
            return ""
        label = dict(_BAR_BACKENDS).get(backend, backend)
        self.state.toggle(backend, True)     # single-choice category: the others drop
        if self.applier.component_installed(backend):
            return f" · bar backend changed to {label}"
        # If not installed the bar never opens; name the package so the user
        # isn't left with "I applied it but there's no bar".
        comp = self.catalog.component(backend)
        packages = " ".join((comp.repo if comp else []) + (comp.aur if comp else []))
        return (f" · this profile wants {label} but it isn't installed: "
                f"pacman -S {packages}" if packages else
                f" · this profile wants {label} but it isn't installed")

    # --- bar presets --------------------------------------------------------
    def _page_bars(self) -> Gtk.Widget:
        self._bar_status = Adw.ActionRow(title="Active bar preset")
        clear = Gtk.Button(label="Leave to profile", valign=Gtk.Align.CENTER)
        clear.connect("clicked", lambda _b: self._on_bar_clear())
        self._bar_status.add_suffix(clear)
        status_group = Adw.PreferencesGroup()
        status_group.add(self._bar_status)

        description = ("Pick the program and the look; only matching presets "
                       "are listed. Presets are independent of the profile: if you pick one here "
                       "it overrides the profile's own bar settings, and your choice is kept "
                       "even if you change profiles. Presets don't define "
                       "colors — they're all drawn with the selected theme.")
        scroller, outer = self._gallery_page(
            "Bar presets", description,
            header_extra=[status_group])
        if not self.bar_presets:
            outer.append(Adw.ActionRow(
                title="No bar presets found",
                subtitle=f"{presets_mod.default_dir(self.root, 'bar')} is empty"))
            return scroller

        # Choice first, then examples. All 66 presets used to be stacked in four
        # long columns (the Waybar column alone had 46 cards): the columns drifted
        # apart and reaching the wanted preset meant scrolling the whole
        # page. Now the program + look are chosen, and only the presets
        # matching them are listed in a single grid.
        by_backend: dict[str, list] = {}
        for preset in self.bar_presets:
            by_backend.setdefault(
                preset.values.get("BAR") or "waybar", []).append(preset)
        current_backend = next(
            (c for c, _l in _BAR_BACKENDS if self.state.is_selected(c)),
            _BAR_BACKENDS[0][0])
        current_family = presets_mod.bar_family(self.state.values)
        chosen = {"backend": current_backend, "family": current_family}

        picker = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        backend_row, _backend_buttons = self._choice_row(
            "Which program draws it?",
            [(c, f"{label} · {len(by_backend.get(c, []))}") for c, label in _BAR_BACKENDS],
            current_backend, lambda value: (chosen.update(backend=value),
                                            refill()))
        picker.append(backend_row)
        note = Gtk.Label(xalign=0, wrap=True)
        note.add_css_class("caption")
        note.add_css_class("dim-label")
        picker.append(note)
        family_row, family_buttons = self._choice_row(
            "How should it look?", self._family_options(), current_family,
            lambda value: (chosen.update(family=value), refill()))
        picker.append(family_row)
        outer.append(picker)

        count = Gtk.Label(xalign=0)
        count.add_css_class("title-4")
        outer.append(count)
        flow = self._gallery_flow()
        outer.append(flow)

        # The comparison table is at the bottom and collapsed: it's read once,
        # it doesn't need to take up half the page on every visit.
        compare = Gtk.Expander(label="Compare programs (package, "
                                     "features, switch backend)")
        compare.set_margin_top(10)
        compare.set_child(self._bar_backend_matrix())
        outer.append(compare)

        def family_of(preset) -> str:
            return presets_mod.bar_family(preset.values)

        def refill() -> None:
            backend, family = chosen["backend"], chosen["family"]
            note.set_label(_BAR_COLUMN_NOTE.get(backend, ""))
            here = by_backend.get(backend, [])
            # The counts in the labels follow the selected program.
            for fam, button in family_buttons.items():
                n = (len(here) if fam == "all"
                     else sum(1 for p in here if family_of(p) == fam))
                button.set_label(f"{self._FAMILY_TEXT[fam]} · {n}")
                button.set_sensitive(n > 0 or fam == family)
            shown = [p for p in here
                     if family == "all" or family_of(p) == family]
            child = flow.get_first_child()
            while child is not None:
                flow.remove(child)
                child = flow.get_first_child()
            self._bar_card_previews = []
            for preset in shown:
                values = dict(preset.values)
                position = values.get("BAR_POSITION", "top")
                size = (values.get("BAR_WIDTH", "44")
                        if position in ("left", "right")
                        else values.get("BAR_HEIGHT", "38"))
                badges = [position, f"{size}px",
                          values.get("BAR_WORKSPACE_STYLE", "numbers")]
                preview = self._live_bar_preview(values, preset.name)
                self._bar_card_previews.append(preview)
                flow.append(self._gallery_card(
                    preset.label, preset.desc, preview, badges,
                    lambda _b, name=preset.name, comp=backend:
                        self._on_bar_preset(name, comp),
                    apply_label="Use this bar", width=300))
            label = dict(_BAR_BACKENDS).get(backend, backend)
            count.set_label(
                f"{label} · {self._FAMILY_TEXT[family].lower()} · "
                f"{len(shown)} presets" if shown else
                f"No {label} presets in this look — pick another look")

        refill()
        self._refresh_bar_status()
        return scroller

    # --- choice row (gallery filters) ---------------------------------------
    _FAMILY_TEXT = {
        "all": "All", "sharp": "Sharp", "rounded": "Rounded",
        "soft": "Soft", "glass": "Frosted glass", "bare": "Bare",
    }

    def _family_options(self) -> list[tuple[str, str]]:
        return ([(f, self._FAMILY_TEXT[f]) for f in presets_mod.FAMILY_ORDER]
                + [("all", self._FAMILY_TEXT["all"])])

    @staticmethod
    def _choice_row(title: str, options: list[tuple[str, str]], active: str,
                    on_change) -> tuple[Gtk.Widget, dict[str, Gtk.ToggleButton]]:
        """Title + adjoining choice buttons (single choice).

        Returns: (row, value → button). Labels can be updated later.
        """
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        label = Gtk.Label(label=title, xalign=0)
        label.add_css_class("heading")
        label.set_size_request(170, -1)
        row.append(label)
        group = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        group.add_css_class("linked")
        buttons: dict[str, Gtk.ToggleButton] = {}
        first: Gtk.ToggleButton | None = None
        for value, text in options:
            button = Gtk.ToggleButton(label=text)
            if first is None:
                first = button
            else:
                button.set_group(first)
            button.set_active(value == active)
            button.connect("toggled", lambda b, v=value:
                           b.get_active() and on_change(v))
            buttons[value] = button
            group.append(button)
        row.append(group)
        return row, buttons

    # --- terminal / launcher ------------------------------------------------
    def _page_app_axis(self, kind: str) -> Gtk.Widget:
        """Builds the terminal and launcher pages.

        The same three sections as the bar page: (1) columns comparing the
        programs by the same criteria, (2) the preset gallery, (3) the settings form +
        live preview. Presets are program-independent — unlike bar presets,
        each preset applies to all the programs; which program actually
        applies which setting is written in the table's "Presets" row.

        The order is presets → individual settings: first a preset is roughly picked,
        then fine-tuned from the form below it. The form also shares the page's own
        scrolling (see `_axis_settings`).
        """
        axis = _APP_AXES[kind]
        presets_here = (self.term_presets if kind == "terminal"
                        else self.launcher_presets)

        status = Adw.ActionRow(title=f"Active {axis['title'].lower()} preset")
        clear = Gtk.Button(label="Leave to profile", valign=Gtk.Align.CENTER)
        clear.connect("clicked", lambda _b: self._on_axis_clear(kind))
        status.add_suffix(clear)
        status_group = Adw.PreferencesGroup()
        status_group.add(status)
        self._axis_status[kind] = status

        description = (
            f"Pick the program and the look; only matching presets are listed; "
            f"each preset means the same thing in every program. "
            f"Presets are independent of the profile: if you pick one here "
            f"it overrides the profile's own {'TERM_*' if kind == 'terminal' else 'LAUNCHER_*'} "
            f"settings and is kept even if you change profiles.")
        scroller, outer = self._gallery_page(
            axis["page_title"], description, header_extra=[status_group])

        # Choice first (program + look), then only the matching presets — the
        # same layout as the bar page. The comparison table moved to a collapsed
        # section at the bottom: it took up half the page.
        current_app = next((c for c, _l in axis["apps"]
                            if self.state.is_selected(c)), "")
        app_row, app_buttons = self._choice_row(
            "Program", list(axis["apps"]), current_app,
            lambda comp, _k=kind: self._select_axis_app(_k, comp))
        self._axis_app_buttons[kind] = app_buttons
        outer.append(app_row)

        if not presets_here:
            outer.append(Adw.ActionRow(
                title="No presets found",
                subtitle=f"{presets_mod.default_dir(self.root, kind)} is empty"))
        else:
            current_family = presets_mod.bar_family(self.state.values)
            chosen = {"family": current_family}
            family_row, family_buttons = self._choice_row(
                "How should it look?", self._family_options(), current_family,
                lambda value: (chosen.update(family=value), refill()))
            outer.append(family_row)

            count = Gtk.Label(xalign=0, wrap=True)
            count.add_css_class("title-4")
            outer.append(count)
            flow = self._gallery_flow()
            outer.append(flow)
            by_name = {p.name: p for p in presets_here}

            # First card: the preset isn't picked by hand, it's matched to the bar
            # preset. Its preview asks for the current match on every draw — when the
            # bar changes, the card changes too.
            def auto_get(key: str, _kind=kind) -> str:
                match = by_name.get(presets_mod.match_axis(_kind, self.state.values))
                if match is not None and key in match.values:
                    return str(match.values[key])
                return self.state.get(key)

            def refill() -> None:
                family = chosen["family"]
                for fam, button in family_buttons.items():
                    n = (len(presets_here) if fam == "all" else sum(
                        1 for p in presets_here
                        if fam in presets_mod.axis_families(kind, p.name)))
                    button.set_label(f"{self._FAMILY_TEXT[fam]} · {n}")
                shown = [p for p in presets_here if family == "all"
                         or family in presets_mod.axis_families(kind, p.name)]
                child = flow.get_first_child()
                while child is not None:
                    flow.remove(child)
                    child = flow.get_first_child()
                self._axis_card_previews = [
                    w for w in self._axis_card_previews
                    if w.get_root() is not None]

                auto_preview = self._axis_preview_widget(kind, auto_get)
                auto_preview.set_content_width(280)
                auto_preview.set_content_height(150)
                self._axis_card_previews.append(auto_preview)
                flow.append(self._gallery_card(
                    "Matches the bar preset (recommended)",
                    "No preset is picked by hand: the one matching the active bar preset's "
                    "character is used, and it changes when the bar does.",
                    auto_preview, ["automatic", "follows the bar preset"],
                    lambda _b: self._on_axis_preset(kind, presets_mod.AUTO),
                    apply_label="Use matching", width=300))
                for preset in shown:
                    values = dict(preset.values)
                    card_preview = self._axis_preview_widget(
                        kind, self._preset_getter(values))
                    card_preview.set_content_width(280)
                    card_preview.set_content_height(150)
                    self._axis_card_previews.append(card_preview)
                    flow.append(self._gallery_card(
                        preset.label, preset.desc, card_preview,
                        self._axis_badges(kind, values),
                        lambda _b, name=preset.name:
                            self._on_axis_preset(kind, name),
                        apply_label="Use this preset", width=300))
                count.set_label(
                    f"{self._FAMILY_TEXT[family]} · {len(shown)} presets "
                    f"+ matching the bar preset")

            refill()

        compare = Gtk.Expander(label="Compare programs "
                                     "(package, features, what the presets map to)")
        compare.set_margin_top(10)
        compare.set_child(self._app_matrix(kind))
        outer.append(compare)

        # --- general settings + live preview, below the presets ---------------
        outer.append(self._axis_settings(kind))
        self._refresh_axis_status(kind)
        return scroller

    def _term_look_gallery(self) -> Gtk.Widget:
        """Preset look cards with previews for the startup screen and background."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._term_look_refresh: list = []
        wallpaper = str(Path(self.state.get("WALLPAPER_PATH") or "").expanduser())
        bg_looks = (
            ("No image", "Just the theme's color", {"TERM_BG_IMAGE": ""}, "none"),
            ("Your wallpaper", "The desktop image, darkened",
             {"TERM_BG_IMAGE": wallpaper}, "wallpaper"),
            ("Your own image", "An image you choose", {}, "image"),
        )
        sections = (
            ("1. Startup screen — logo", "The logo and system info shown when "
             "a new terminal window opens.",
             [(t, d, v, "fetch") for t, d, v in _FETCH_LOGOS]),
            ("2. How should the logo be drawn?", "Turns the selected logo (Souprland or "
             "your own image) into dots, blocks or letters.",
             [(t, d, v, "style") for t, d, v in _FETCH_STYLES]),
            ("3. Background", "The image behind the text (kitty, Ghostty, WezTerm).",
             [(t, d, v, f"bg:{src}") for t, d, v, src in bg_looks]),
        )
        for title, intro, looks in sections:
            heading = Gtk.Label(label=title, xalign=0)
            heading.add_css_class("heading")
            box.append(heading)
            note = Gtk.Label(label=intro, xalign=0, wrap=True)
            note.add_css_class("dim-label")
            note.add_css_class("caption")
            box.append(note)
            flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                               min_children_per_line=2, max_children_per_line=6,
                               row_spacing=10, column_spacing=10)
            flow.set_margin_bottom(10)
            for name, desc, values, tag in looks:
                flow.append(self._term_look_card(name, desc, values, tag))
            box.append(flow)
            if looks[0][3] == "style":
                # Style only makes sense for image logos: for the others, a note
                # saying what to do, instead of the cards.
                hint = Gtk.Label(xalign=0, wrap=True)
                hint.add_css_class("dim-label")
                hint.set_margin_bottom(10)
                box.append(hint)

                def update(flow=flow, hint=hint) -> None:
                    on = (self.state.get("TERM_FETCH") == "on"
                          and self.state.get("TERM_LOGO") in ("souprland", "image"))
                    flow.set_visible(on)
                    hint.set_visible(not on)
                    hint.set_text("First pick the \"Souprland\" or \"Your own image\" "
                                  "logo above; the drawing style applies to that image.")
                update()
                self._term_look_refresh.append(update)
        return box

    def _term_look_card(self, name: str, desc: str, values: dict[str, str],
                        tag: str) -> Gtk.Widget:
        state = self.state
        if tag == "bg:image":
            def preview_get(key: str) -> str:
                current = state.get("TERM_BG_IMAGE")
                if key == "TERM_BG_IMAGE":
                    return current if Path(current).name.startswith("term-bg-image") else ""
                return state.get(key)
        elif tag == "style":
            def preview_get(key: str, v=values) -> str:
                if key == "TERM_FETCH":
                    return "on"
                return v[key] if key in v else state.get(key)
        else:
            def preview_get(key: str, v=values) -> str:
                return v[key] if key in v else state.get(key)
        preview = TerminalPreview(preview_get, state.palette)
        preview.legend = False
        preview.set_zoom(0.72)
        preview.set_content_width(230)
        preview.set_content_height(116)
        self._axis_card_previews.append(preview)
        # "Your own image" cards showed an empty terminal while no image was chosen.
        overlay = Gtk.Overlay(child=preview)
        hint = Gtk.Label(label="＋ Choose image", halign=Gtk.Align.CENTER,
                         valign=Gtk.Align.CENTER)
        hint.add_css_class("osd")
        hint.add_css_class("pill")
        hint.set_can_target(False)
        overlay.add_overlay(hint)
        picks_logo = tag == "fetch" and values.get("TERM_LOGO") == "image"

        def update_hint() -> None:
            if picks_logo:
                has = bool(state.get("TERM_LOGO_IMAGE"))
            elif tag == "bg:image":
                has = Path(state.get("TERM_BG_IMAGE") or "").name.startswith("term-bg-image")
            else:
                hint.set_visible(False)
                return
            # With no image it asks for one; clicking the selected card again changes it.
            hint.set_label("＋ Choose image" if not has else "Change image")
            hint.set_visible(not has or active())

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        inner.append(overlay)
        label = Gtk.Label(label=name, xalign=0)
        label.add_css_class("heading")
        label.set_margin_start(8)
        inner.append(label)
        sub = Gtk.Label(label=desc, xalign=0, wrap=True, max_width_chars=28)
        sub.add_css_class("caption")
        sub.add_css_class("dim-label")
        sub.set_margin_start(8)
        sub.set_margin_end(8)
        sub.set_margin_bottom(8)
        inner.append(sub)
        button = Gtk.Button(child=inner)
        button.add_css_class("card")
        button.add_css_class("hs-mix-card")

        def active() -> bool:
            if tag in ("fetch", "style"):
                return all(state.get(k) == v for k, v in values.items())
            current = Path(state.get("TERM_BG_IMAGE") or "").name
            return {"bg:none": current == "",
                    "bg:wallpaper": current.startswith("term-bg-wallpaper"),
                    "bg:image": current.startswith("term-bg-image")}[tag]

        def refresh() -> None:
            (button.add_css_class if active() else button.remove_css_class)(
                "hs-mix-selected")
            update_hint()

        def write(items: dict[str, str]) -> None:
            for key, value in items.items():
                state.set(key, value)
            refresh()

        def clicked(_b) -> None:
            if tag == "style":
                write(values)
                return
            if tag == "fetch":
                # Your own image: if there's no image, or the card is clicked while already
                # selected (to change the image), a file chooser opens.
                if values.get("TERM_LOGO") == "image" and (
                        not state.get("TERM_LOGO_IMAGE") or active()):
                    choose_image(button, "TERM_LOGO_IMAGE", "Logo image", state,
                                 lambda: write(values), self._toast)
                    return
                needed = deps_mod.triggered(
                    schema.by_key()["TERM_FETCH"].requires, values.get("TERM_FETCH", ""))
                if needed and state.require is not None:
                    state.require(needed, "Startup screen", lambda: write(values), refresh)
                else:
                    write(values)
            elif tag == "bg:none":
                write({"TERM_BG_IMAGE": ""})
            elif tag == "bg:wallpaper":
                source = Path(values["TERM_BG_IMAGE"])
                if not source.is_file():
                    self._toast("Wallpaper file not found")
                    return
                try:
                    stored = store_image("TERM_BG_IMAGE", source, "term-bg-wallpaper")
                except (GLib.Error, OSError) as exc:
                    self._toast(f"Could not read image: {exc}")
                    return
                write({"TERM_BG_IMAGE": str(stored)})
            else:
                choose_image(button, "TERM_BG_IMAGE", "Background image", state,
                             refresh, self._toast)

        button.connect("clicked", clicked)
        refresh()
        self._term_look_refresh.append(refresh)
        return button

    def _axis_settings(self, kind: str) -> Gtk.Widget:
        """The axis's individual settings + live preview.

        The form used to be inside an Adw.PreferencesPage; since that widget
        carries its own Gtk.ScrolledWindow it opened a second scroll area inside
        the page — the wheel scrolled either the form or the page depending on
        where the pointer was, and the form got squeezed into itself as the page
        grew. Here an Adw.PreferencesGroup is placed directly in the page's
        box instead: the group doesn't scroll, the whole page scrolls as one.
        """
        axis = _APP_AXES[kind]
        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        section.set_margin_top(10)

        heading = Gtk.Label(label=f"General {axis['title'].lower()} settings",
                            xalign=0)
        heading.add_css_class("title-4")
        section.append(heading)

        if kind == "terminal":
            section.append(self._term_look_gallery())
        columns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24,
                          valign=Gtk.Align.START)
        group = schema.group(axis["setting_group"])
        # LAUNCHER_PROVIDERS is a comma-separated list; asked as a plain text box,
        # the user would have to know the valid names by heart.
        # The switch list below writes the same setting (see the same pattern
        # applied to WIDGETS on the Widgets page).
        form = group_to_widget(group, self.state, sync=self._sync_rows,
                               skip={"LAUNCHER_PROVIDERS"},
                               rows=self._setting_rows)
        form.set_hexpand(True)
        # The axis's extra groups (those after the first in PAGE_GROUPS; e.g.
        # the terminal's startup screen and background) go below the form: the
        # preview stays beside it and visible while changing them.
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18,
                       hexpand=True)
        left.append(form)
        for extra_id in PAGE_GROUPS.get(kind, ())[1:]:
            left.append(self._group_widget(extra_id))
        columns.append(left)

        # The live preview is twice the card preview: cards at 320x170 introduce the
        # preset, this one is the current setting itself, and opacity/padding/
        # cursor differences are only readable at this scale. Enlarging the canvas
        # alone isn't enough — the mockup draws absolute pixels, so the text stayed
        # the same; set_zoom scales everything together (see preview.py).
        preview = self._axis_preview_widget(kind, self.state.get)
        # At 640px the form beside it broke letter by letter in a narrow window.
        preview.set_zoom(1.5)
        preview.set_content_width(440)
        preview.set_content_height(240)
        frame = Gtk.Frame()
        frame.add_css_class("view")
        frame.set_child(preview)
        frame.set_valign(Gtk.Align.START)
        self._axis_previews[kind] = preview
        columns.append(frame)

        section.append(columns)
        if kind == "launcher":
            section.append(self._launcher_provider_group())

        # The whole section (title + form + preview) sits in a single Adw.Clamp.
        # Wrapping only the form centered it on wide screens and threw the
        # preview to the far right edge of the page, leaving a palm-wide gap
        # between them. halign=START aligns it with the card flow's left
        # edge — if the Clamp centered it, the section would drift off the page.
        clamp = Adw.Clamp(maximum_size=1240)
        clamp.set_halign(Gtk.Align.START)
        clamp.set_child(section)
        return clamp

    def _launcher_provider_group(self) -> Adw.PreferencesGroup:
        """walker's extra query sources: calculator, clipboard, emoji…

        walker gets its data from the "elephant" service and each source is a
        separate plugin; the packages are installed together with the walker
        component (config/components.json). The switches here decide which ones
        are written to the configuration.
        """
        active = self.state.primary("launcher")
        note = ("" if active == "walker"
                else f"No effect: the selected launcher is {active or '—'}. "
                     f"This list only applies to walker.")
        group = Adw.PreferencesGroup(
            title="walker providers",
            description="Extra query sources for the app list. Each one is "
                        "called with its own prefix; those without a prefix are "
                        "reached via \";\" (the source list). "
                        + note)
        self._provider_switches: dict[str, Adw.SwitchRow] = {}
        enabled = set(render_mod.split_launcher_providers(
            self.state.get("LAUNCHER_PROVIDERS")))

        for name, (prefix, package, label) in render_mod.LAUNCHER_PROVIDERS.items():
            subtitle = (f"Prefix: {prefix}" if prefix
                        else "No prefix — selected with \";\"")
            row = Adw.SwitchRow(title=esc(label),
                                subtitle=esc(f"{subtitle} · {package}"))
            row.set_active(name in enabled)
            row.connect("notify::active", self._on_provider_toggled, name)
            self._provider_switches[name] = row
            group.add(row)

        self._sync_rows["LAUNCHER_PROVIDERS"] = self._sync_provider_switches
        return group

    def _on_provider_toggled(self, row: Adw.SwitchRow, _param,
                             name: str) -> None:
        # The order is the catalog's order: so the list order doesn't change as
        # the user toggles switches, and the generated config.toml doesn't come out
        # needlessly different.
        current = set(render_mod.split_launcher_providers(
            self.state.get("LAUNCHER_PROVIDERS")))
        if row.get_active():
            current.add(name)
        else:
            current.discard(name)
        ordered = [n for n in render_mod.LAUNCHER_PROVIDERS if n in current]
        self.state.set("LAUNCHER_PROVIDERS", ",".join(ordered))

    def _sync_provider_switches(self) -> None:
        enabled = set(render_mod.split_launcher_providers(
            self.state.get("LAUNCHER_PROVIDERS")))
        for name, row in getattr(self, "_provider_switches", {}).items():
            active = name in enabled
            if row.get_active() != active:
                row.set_active(active)

    def _preset_getter(self, values: dict[str, str]):
        """For card previews: the preset's values, the rest from the live state.

        A preset only defines its own axis; shared settings like font size
        should come from the user's current choice so the card shows the
        combination that will really be seen (the same logic as the bar cards).
        """
        def get(key: str) -> str:
            if key in values:
                return str(values[key])
            return self.state.get(key)
        return get

    @staticmethod
    def _axis_badges(kind: str, values: dict[str, str]) -> list[str]:
        if kind == "terminal":
            return [f"opacity {values.get('TERM_OPACITY', '—')}",
                    f"padding {values.get('TERM_PADDING', '—')}px",
                    values.get("TERM_CURSOR_STYLE", "block")]
        radius = values.get("LAUNCHER_RADIUS", "")
        border = values.get("LAUNCHER_BORDER", "")
        return [f"{values.get('LAUNCHER_WIDTH', '—')}%",
                values.get("LAUNCHER_POSITION", "center"),
                f"rounding {radius}" if radius != "" else "rounding: like windows",
                f"border {border}" if border != "" else "border: like windows"]

    def _axis_preview_widget(self, kind: str, get_setting):
        cls = TerminalPreview if kind == "terminal" else LauncherLayoutPreview
        return cls(get_setting, self.state.palette)

    def _app_matrix(self, kind: str) -> Gtk.Widget:
        """Table comparing an axis's programs side by side.

        Same layout as `_bar_backend_matrix`; the programs here take the place of
        its backend columns, and the rows are read from the `_APP_AXES`
        table.
        """
        axis = _APP_AXES[kind]
        apps = axis["apps"]
        rows: list[tuple[str, dict[str, str]]] = [("Package", {})]
        for comp_id, _label in apps:
            comp = self.catalog.component(comp_id)
            if comp and comp.aur:
                rows[0][1][comp_id] = ", ".join(comp.aur)
            elif comp and comp.repo:
                rows[0][1][comp_id] = "repo: " + ", ".join(comp.repo)
            else:
                rows[0][1][comp_id] = "—"
        rows.extend(axis["rows"])

        grid = Gtk.Grid(row_spacing=8, column_spacing=16)
        grid.set_margin_top(14)
        grid.set_margin_bottom(14)
        grid.set_margin_start(16)
        grid.set_margin_end(16)

        def column(index: int) -> int:
            return 1 + index * 2

        widgets: dict[str, Gtk.ToggleButton] = {}
        titles: dict[str, Gtk.Label] = {}
        radio_root: Gtk.ToggleButton | None = None
        last_row = len(rows) + 2

        # Program columns share the extra space equally. Without hexpand
        # Gtk.Grid left every column at its natural width and didn't use the
        # surplus: the table piled up on the frame's left, leaving a third of the
        # page empty on its right. max_width_chars only stays as a natural
        # width hint; the text wraps at the real column width.
        for index, (comp_id, label) in enumerate(apps):
            col = column(index)
            title = Gtk.Label(label=label, xalign=0, hexpand=True)
            title.add_css_class("heading")
            titles[comp_id] = title
            grid.attach(aur_mod.titled(title, self._comp_aur(comp_id)),
                        col, 0, 1, 1)

            summary = Gtk.Label(label=axis["summary"].get(comp_id, ""),
                                xalign=0, wrap=True, max_width_chars=26,
                                hexpand=True, valign=Gtk.Align.START)
            summary.add_css_class("caption")
            summary.add_css_class("dim-label")
            grid.attach(summary, col, 1, 1, 1)

            button = Gtk.ToggleButton(label="Use this", valign=Gtk.Align.END)
            button.set_margin_top(6)
            if radio_root is None:
                radio_root = button
            else:
                button.set_group(radio_root)
            button.set_active(self.state.is_selected(comp_id))
            button.connect("toggled", self._on_app_toggled, comp_id, kind)
            widgets[comp_id] = button
            grid.attach(button, col, last_row, 1, 1)

            if index:
                sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
                grid.attach(sep, col - 1, 0, 1, last_row + 1)

        for row_index, (criterion, values) in enumerate(rows, start=2):
            name = Gtk.Label(label=criterion, xalign=0, valign=Gtk.Align.START)
            name.add_css_class("caption-heading")
            name.add_css_class("dim-label")
            grid.attach(name, 0, row_index, 1, 1)
            for index, (comp_id, _label) in enumerate(apps):
                value = Gtk.Label(label=values.get(comp_id, "—"), xalign=0,
                                  wrap=True, max_width_chars=26, hexpand=True,
                                  valign=Gtk.Align.START)
                value.add_css_class("caption")
                if row_index == 2:            # the "Package" row
                    value = aur_mod.stacked(value, self._comp_aur(comp_id))
                grid.attach(value, column(index), row_index, 1, 1)

        self._app_axis_widgets[kind] = widgets
        self._app_axis_titles[kind] = titles
        frame = Gtk.Frame()
        frame.add_css_class("view")
        frame.set_child(grid)
        self._refresh_app_axis_columns()
        return frame

    def _refresh_app_axis_columns(self) -> None:
        for _kind, buttons in getattr(self, "_axis_app_buttons", {}).items():
            for comp_id, button in buttons.items():
                active = self.state.is_selected(comp_id)
                if button.get_active() != active and active:
                    button.set_active(True)
        for kind, titles in getattr(self, "_app_axis_titles", {}).items():
            buttons = self._app_axis_widgets.get(kind, {})
            for comp_id, title in titles.items():
                active = self.state.is_selected(comp_id)
                (title.add_css_class if active
                 else title.remove_css_class)("accent")
                button = buttons.get(comp_id)
                if button is None:
                    continue
                if button.get_active() != active:
                    button.set_active(active)
                label = "Selected" if active else "Use this"
                if button.get_label() != label:
                    button.set_label(label)
                (button.add_css_class if active
                 else button.remove_css_class)("suggested-action")

    def _select_axis_app(self, kind: str, comp_id: str) -> None:
        """Selection from the compact program row at the top (same job as the matrix)."""
        if self.state.is_selected(comp_id):
            return
        self.state.toggle(comp_id, True)
        self._refresh_component_rows()
        self._refresh_app_axis_columns()
        label = dict(_APP_AXES[kind]["apps"]).get(comp_id, comp_id)
        self._toast(f"{_APP_AXES[kind]['title']}: {label}")

    def _on_app_toggled(self, button, comp_id: str, kind: str) -> None:
        if not button.get_active():
            return
        self.state.toggle(comp_id, True)
        self._refresh_component_rows()
        label = dict(_APP_AXES[kind]["apps"]).get(comp_id, comp_id)
        self._toast(f"{_APP_AXES[kind]['title']}: {label}")

    def _on_axis_preset(self, kind: str, name: str) -> None:
        self.state.apply_axis_preset(self.root, kind, name)
        self._sync_all_rows()
        self._refresh_axis_status(kind)
        if name == presets_mod.AUTO:
            name = ("matches the bar preset → "
                    + presets_mod.match_axis(kind, self.state.values))
        self._toast(f"{_APP_AXES[kind]['title']} preset applied: {name}")

    def _on_axis_clear(self, kind: str) -> None:
        self.state.clear_axis_preset(self.root, kind)
        self._sync_all_rows()
        self._refresh_axis_status(kind)
        self._toast(f"{_APP_AXES[kind]['title']} preset left to the profile")

    def _refresh_axis_status(self, kind: str) -> None:
        row = getattr(self, "_axis_status", {}).get(kind)
        if row is None:
            return
        pinned = self.state.pinned_axis(kind)
        key = "TERM_PRESET" if kind == "terminal" else "LAUNCHER_PRESET"
        active = self.state.get(key)
        if active == presets_mod.AUTO:
            family = presets_mod.FAMILY_LABELS[
                presets_mod.bar_family(self.state.values)]
            row.set_subtitle(
                f"Matches the bar preset — {self.state.get('BAR_PRESET') or 'bar'} "
                f"has a {family} character, hence the "
                f"{presets_mod.match_axis(kind, self.state.values)} preset")
        elif pinned:
            row.set_subtitle(f"{pinned} — your choice, kept even if the profile "
                             f"changes")
        elif active:
            row.set_subtitle(f"{active} — comes from the profile")
        else:
            row.set_subtitle("No preset selected — individual settings apply")

    def _bar_backend_matrix(self) -> Gtk.Widget:
        """Table comparing the bar backends side by side by the same criteria.

        The choice used to be three small buttons on one row; the difference
        between them was only mentioned in a long paragraph of the page description.
        The columns share a single Gtk.Grid: each criterion lines up on the same
        row for every backend, and the difference is seen by scanning row by row.
        """
        rows: list[tuple[str, dict[str, str]]] = [("Package", {})]
        for comp_id, _label in _BAR_BACKENDS:
            comp = self.catalog.component(comp_id)
            if comp and comp.aur:
                rows[0][1][comp_id] = ", ".join(comp.aur)
            elif comp and comp.repo:
                rows[0][1][comp_id] = "repo: " + ", ".join(comp.repo)
            else:
                rows[0][1][comp_id] = "—"
        rows.extend(_bar_backend_rows())

        grid = Gtk.Grid(row_spacing=8, column_spacing=18)
        grid.set_margin_top(14)
        grid.set_margin_bottom(14)
        grid.set_margin_start(16)
        grid.set_margin_end(16)

        # 0 → criterion name, 1/3/5 → backends, 2/4 → vertical line between them.
        def column(index: int) -> int:
            return 1 + index * 2

        self._bar_backend_widgets: dict[str, Gtk.ToggleButton] = {}
        self._bar_backend_titles: dict[str, Gtk.Label] = {}
        radio_root: Gtk.ToggleButton | None = None
        # Criterion rows start at 2; the profile row goes below them, and the
        # choice buttons at the very bottom.
        profile_row = len(rows) + 2
        last_row = profile_row + 1

        # Backend columns share the extra space equally — see the same hexpand
        # note in _app_matrix.
        for index, (comp_id, label) in enumerate(_BAR_BACKENDS):
            col = column(index)
            title = Gtk.Label(label=label, xalign=0, hexpand=True)
            title.add_css_class("heading")
            self._bar_backend_titles[comp_id] = title
            grid.attach(aur_mod.titled(title, self._comp_aur(comp_id)),
                        col, 0, 1, 1)

            summary = Gtk.Label(label=_BAR_BACKEND_SUMMARY.get(comp_id, ""),
                                xalign=0, wrap=True, max_width_chars=32,
                                hexpand=True, valign=Gtk.Align.START)
            summary.add_css_class("caption")
            summary.add_css_class("dim-label")
            grid.attach(summary, col, 1, 1, 1)

            btn = Gtk.ToggleButton(label="Use this", valign=Gtk.Align.END)
            btn.set_margin_top(6)
            if radio_root is None:
                radio_root = btn
            else:
                btn.set_group(radio_root)
            btn.set_active(self.state.is_selected(comp_id))
            btn.connect("toggled", self._on_bar_backend_toggled, comp_id)
            self._bar_backend_widgets[comp_id] = btn
            grid.attach(btn, col, last_row, 1, 1)

            if index:
                sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
                grid.attach(sep, col - 1, 0, 1, last_row + 1)

        for row_index, (criterion, values) in enumerate(rows, start=2):
            name = Gtk.Label(label=criterion, xalign=0,
                             valign=Gtk.Align.START)
            name.add_css_class("caption-heading")
            name.add_css_class("dim-label")
            grid.attach(name, 0, row_index, 1, 1)
            for index, (comp_id, _label) in enumerate(_BAR_BACKENDS):
                value = Gtk.Label(label=values.get(comp_id, "—"), xalign=0,
                                  wrap=True, max_width_chars=32, hexpand=True,
                                  valign=Gtk.Align.START)
                value.add_css_class("caption")
                if row_index == 2:            # the "Package" row
                    value = aur_mod.stacked(value, self._comp_aur(comp_id))
                grid.attach(value, column(index), row_index, 1, 1)

        # --- install status ------------------------------------------------
        # This used to say "how many profiles use this backend".
        # The profile system was removed; in its place is this settings app's real
        # constraint: we don't install packages, so a backend that isn't installed
        # can't be selected. The user should see this BEFORE trying to select it.
        label = Gtk.Label(label="Install", xalign=0, valign=Gtk.Align.START)
        label.add_css_class("caption-heading")
        label.add_css_class("dim-label")
        grid.attach(label, 0, profile_row, 1, 1)
        for index, (comp_id, _label) in enumerate(_BAR_BACKENDS):
            missing = self.applier.missing_packages(comp_id)
            cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                           hexpand=True, valign=Gtk.Align.START)
            status = Gtk.Label(label="installed" if not missing else "not installed",
                               xalign=0)
            status.add_css_class("caption")
            cell.append(status)
            if missing:
                command = self._install_command(missing)
                hint = Gtk.Label(label=command, xalign=0, wrap=True,
                                 max_width_chars=32, selectable=True)
                hint.add_css_class("caption")
                hint.add_css_class("dim-label")
                cell.append(hint)
                copy = self._copy_button(command)
                copy.set_halign(Gtk.Align.START)
                cell.append(copy)
                # A backend that isn't installed can't be selected: if selected, the
                # rendered config would have no reader and the bar would never open.
                button = self._bar_backend_widgets.get(comp_id)
                if button is not None and not button.get_active():
                    button.set_sensitive(False)
            grid.attach(cell, column(index), profile_row, 1, 1)

        frame = Gtk.Frame()
        frame.add_css_class("view")
        frame.set_child(grid)
        self._refresh_bar_backend_columns()
        self._refresh_app_axis_columns()
        return frame

    def _refresh_bar_backend_columns(self) -> None:
        """Highlights the selected column — so the active backend is read from the
        column itself, without looking at the subtle tint of the pressed button."""
        for comp_id, title in getattr(self, "_bar_backend_titles", {}).items():
            active = self.state.is_selected(comp_id)
            (title.add_css_class if active else title.remove_css_class)("accent")
            button = self._bar_backend_widgets.get(comp_id)
            if button is None:
                continue
            label = "Selected" if active else "Use this"
            if button.get_label() != label:
                button.set_label(label)
            (button.add_css_class if active
             else button.remove_css_class)("suggested-action")

    def _live_bar_preview(self, values: dict[str, str],
                          name: str = "") -> Gtk.Widget:
        """Preview with the bar preset's fixed layout and live colors.

        Bar presets don't define colors; the card is drawn with the currently selected
        theme so the user sees the combination they'll really get. When the theme
        changes, _on_state_changed has these areas redrawn.

        Horizontal bars use ``BarPreview``: it shows where the bar sits on screen
        (inside a small desktop sketch) while drawing the bar itself at 1:1 scale
        with the real module names — the gallery card's previous version shrank
        the whole desktop and the bar was barely visible. For vertical
        (left/right) presets, since BarPreview's module layout wasn't supported yet,
        it fell back to the whole-desktop sketch; at least the position is drawn right.
        """
        base = dict(schema.defaults())
        base.update({k: str(v) for k, v in values.items()})
        # The preset's name decides the preview's SHAPE (preview.BAR_PREVIEW_SHAPES):
        # capsule, bare text or bracketed. The preset file has no BAR_PRESET
        # line — the caller provides the name.
        if name:
            base["BAR_PRESET"] = name

        def get_setting(key: str) -> str:
            return base.get(key, "")

        position = base.get("BAR_POSITION", "top")
        if position in ("left", "right"):
            # BarPreview now draws vertical bars itself too (modules stacked);
            # this used to fall back to the whole-desktop sketch, and the six
            # vertical presets couldn't be told apart.
            view = BarPreview(get_setting, self.state.palette)
            view.set_card_mode(True)
            view.set_content_width(300)
            view.set_content_height(150)
        else:
            # BarPreview's own sensible base size is already 360x170 —
            # 208x100 used to be forced here, which made the structural difference
            # between presets like islands/dock/bracket invisible.
            view = BarPreview(get_setting, self.state.palette)
            # Card mode: an enlarged, readable bar instead of measurement arrows
            # (see BarPreview.set_card_mode).
            view.set_card_mode(True)
            view.set_content_width(300)
            view.set_content_height(110)
        view.set_hexpand(False)
        return view

    def _refresh_bar_preview_widget(self) -> None:
        """Swaps the SINGLE live preview on the "Status Bar" page according to
        BAR_POSITION when needed.

        BarPreview draws a horizontal bar 1:1 but didn't support the vertical
        (left/right) module layout yet — with the position "left"/"right",
        BAR_POSITION was still interpreted as "top" (the fix in _live_bar_preview
        was made for exactly the same problem, but it had only
        been applied to the gallery cards, not to the single widget on this
        page). As long as the category (horizontal↔vertical) doesn't change it's
        just redrawn; when it changes the widget itself is swapped.
        """
        if not hasattr(self, "_bar_preview_frame"):
            return
        # BarPreview now draws vertical bars too (modules stacked,
        # see preview.BarPreview._draw_vertical), so no widget swap by position
        # is needed: a single widget shows both orientations.
        self.bar_preview.queue_draw()

    def _on_bar_preset(self, name: str, backend: str = "") -> None:
        """Applies the bar preset and also selects the backend the preset wants.

        The backend is a separate axis: the program to install is read from
        `COMPONENTS`, not from the preset's `BAR=` value. While the two were
        separate, picking a preset from the HyprPanel column was silently applied
        to Waybar — on the bash side `lib/select.sh:selection_sync_bar_component`
        does this; here there was no equivalent.
        """
        if backend and not self.state.is_selected(backend):
            # A HyprPanel/Wayle preset without that program installed used to
            # switch the backend anyway: waybar was stopped and no bar came up.
            # Ask first, like every other component (install / enable / cancel).
            comp = self.catalog.component(backend)
            self._require([backend], comp.title if comp else backend,
                          lambda: self._apply_bar_preset(name, backend), chosen=backend)
            return
        self._apply_bar_preset(name, backend)

    def _apply_bar_preset(self, name: str, backend: str = "") -> None:
        self.state.apply_bar_preset(self.root, name)
        switched = bool(backend) and not self.state.is_selected(backend)
        if switched:
            self.state.toggle(backend, True)
        self._sync_all_rows()
        self._refresh_bar_status()
        self._refresh_component_rows()
        # The terminal/launcher matching the bar preset may have changed too.
        for kind in ("terminal", "launcher"):
            self._refresh_axis_status(kind)
        for preview in getattr(self, "_axis_card_previews", ()):
            preview.queue_draw()
        if switched:
            label = dict(_BAR_BACKENDS).get(backend, backend)
            self._toast(f"Bar preset applied: {name} · backend changed to "
                        f"{label}")
        else:
            self._toast(f"Bar preset applied: {name}")

    def _on_bar_clear(self) -> None:
        self.state.clear_bar_preset(self.root)
        self._sync_all_rows()
        self._refresh_bar_status()
        self._toast("Bar preset left to the profile")

    def _refresh_bar_status(self) -> None:
        if not hasattr(self, "_bar_status"):
            return
        active = self.state.get("BAR_PRESET")
        if self.state.pinned_bar:
            self._bar_status.set_subtitle(
                f"{self.state.pinned_bar} — your choice, kept even if the "
                f"profile changes")
        elif active:
            self._bar_status.set_subtitle(
                f"{active} — comes from the profile")
        else:
            self._bar_status.set_subtitle(
                "No preset selected; the individual settings on the Status Bar page "
                "apply")

    # --- widgets ------------------------------------------------------------
    # --- widgets ------------------------------------------------------------
    #: Zone id → title. The order is the grid order on the page (3 columns:
    #: top row, bottom row) — the grid reads like the screen itself.
    _WIDGET_ZONE_ORDER = tuple(render_mod.WIDGET_ZONE_LABELS.items())

    def _page_widgets(self) -> Gtk.Widget:
        """Two columns: corner layout + look settings on the left, preview on the right.

        The old page was just 15 on/off switches and never said three
        things: WHERE the widget would land, whether the selected engine can draw
        it, and whether the component it needs is selected. All three produced
        silent failures — the user turned on a switch and nothing happened on the
        desktop.
        """
        page = Adw.PreferencesPage()
        self._widen_page(page, 880)
        preview_page = Adw.PreferencesPage()
        self._widen_page(preview_page, 460)
        preview_page.set_size_request(460, -1)

        preview_group = Adw.PreferencesGroup(
            title="Layout preview",
            description="The boxes are drawn where they'll really sit on screen; "
                        "their positions come from the same calculation that "
                        "generates the configuration. The edge the bar takes is left empty.")
        self.widget_preview = WidgetPreview(
            get_setting=self.state.get,
            get_palette=self.state.palette,
            get_layout=self._widget_layout_items)
        frame = Gtk.Frame()
        frame.set_child(self.widget_preview)
        frame.add_css_class("view")
        frame.set_margin_top(6)
        preview_group.add(frame)
        preview_page.add(preview_group)

        page.add(self._widget_engine_group())
        page.add(self._widget_toggle_group())
        page.add(self._widget_set_group())
        page.add(self._widget_style_group())
        page.add(self._widget_zone_group())

        # Look settings come from the schema; WIDGETS and the zone lists are
        # written by the chip editor above, so they aren't shown as plain rows.
        page.add(self._group_widget("widget", skip={
            "WIDGETS", "WIDGET_OFFSETS",
            *(f"WIDGET_ZONE_{zone}" for zone in render_mod.WIDGET_ZONES)}))

        # Audio visualizer (cava, bottom edge panel).
        page.add(self._group_widget("visualizer"))

        return _settings_paned(page, preview_page, 900)

    # --- widget: engine status ---------------------------------------------
    def _widget_engine_group(self) -> Adw.PreferencesGroup:
        """Says which engine draws the widgets and whether it's installed.

        Turning on a widget with no engine selected produced nothing; with one
        selected but its package not installed there was the same silence (the
        template's require checks the HAS_* flag). Both are spelled out here.
        """
        group = Adw.PreferencesGroup(
            title="Widget engine",
            description="The program that draws the widgets. Independent of the bar: "
                        "it works with any bar preset you like.")
        self._widget_engine_row = Adw.ActionRow(title="Selected engine")
        self._widget_engine_row.set_subtitle_lines(3)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6,
                      valign=Gtk.Align.CENTER)
        self._widget_engine_buttons: dict[str, Gtk.ToggleButton] = {}
        category = next((c for c in self.catalog.categories
                         if c.id == "widget"), None)
        for comp in (category.components if category else ()):
            button = Gtk.ToggleButton(label=comp.title)
            button.connect("toggled", self._on_widget_engine, comp.id)
            self._widget_engine_buttons[comp.id] = button
            box.append(button)
        self._widget_engine_row.add_suffix(box)
        group.add(self._widget_engine_row)
        self._refresh_widget_engine()
        return group

    def _on_widget_engine(self, button: Gtk.ToggleButton, comp_id: str) -> None:
        if getattr(self, "_widget_engine_guard", False):
            return
        def done() -> None:
            if button.get_active():
                # Single choice: the others in the same category turn off.
                for other in self._widget_engine_buttons:
                    if other != comp_id and self.state.is_selected(other):
                        self.state.toggle(other, False)
                self.state.toggle(comp_id, True)
            else:
                self.state.toggle(comp_id, False)
            self._refresh_widget_engine()
            self._refresh_widget_zones()
            self._refresh_component_rows()

        if not button.get_active():
            done()
            return
        comp = self.catalog.component(comp_id)
        self._require([comp_id], comp.title if comp else comp_id, done,
                      self._refresh_widget_engine, chosen=comp_id)

    def _refresh_widget_engine(self) -> None:
        row = getattr(self, "_widget_engine_row", None)
        if row is None:
            return
        guard = self._widget_engine_guard = True     # noqa: F841
        try:
            for comp_id, button in self._widget_engine_buttons.items():
                active = self.state.is_selected(comp_id)
                if button.get_active() != active:
                    button.set_active(active)
        finally:
            self._widget_engine_guard = False

        engine = self.state.primary("widget")
        if not engine:
            row.set_subtitle("No engine selected — the widgets you turn on "
                             "aren't generated. Pick one below.")
            row.add_css_class("error")
            return
        row.remove_css_class("error")
        comp = self.catalog.component(engine)
        title = comp.title if comp else engine
        missing = self.applier.missing_packages(engine)
        if missing:
            row.set_subtitle(
                f"{title} is selected but its package isn't installed: "
                f"{' '.join(missing)} — no widgets are generated until it's installed "
                f"({self._install_command(missing)})")
            row.add_css_class("warning")
        else:
            row.remove_css_class("warning")
            drawn = len(self._widget_layout_items())
            row.set_subtitle(f"{title} · currently drawing {drawn} widgets")

    # --- widget: on/off list ------------------------------------------------
    def _widget_toggle_group(self) -> Adw.PreferencesGroup:
        """One row per widget: how it looks, what it does, on/off.

        The corner editor's "+" menu only showed names; names like "System
        card" or "Workspace" didn't tell what would be drawn. The samples
        here are drawn in the selected theme's colors.
        """
        group = Adw.PreferencesGroup(
            title="Widgets",
            description="Turn them on and off with the switch. A widget you turn "
                        "on lands in its default position; you can change where "
                        "it goes in the Positions section below.")
        self._widget_switches: dict[str, tuple[Adw.ActionRow, Gtk.Switch]] = {}
        self._widget_samples: list[WidgetSample] = []
        descs = {p.name: p.desc for p in self.widget_presets}
        for name, spec in render_mod.WIDGET_CATALOG.items():
            row = Adw.ActionRow(title=esc(spec.label))
            row.set_subtitle_lines(3)
            row.set_tooltip_text(descs.get(name, "") or None)
            sample = WidgetSample(name, self.state.get, self.state.palette)
            sample.set_valign(Gtk.Align.CENTER)
            sample.set_margin_top(6); sample.set_margin_bottom(6)
            self._widget_samples.append(sample)
            row.add_prefix(sample)
            switch = Gtk.Switch(valign=Gtk.Align.CENTER)
            switch.connect("notify::active", self._on_widget_switch, name)
            row.add_suffix(switch)
            row.set_activatable_widget(switch)
            self._widget_switches[name] = (row, switch)
            group.add(row)
        self._refresh_widget_switches()
        return group

    def _widget_needs(self, names) -> list[str]:
        """What's needed to draw the widgets: the engine + their own components."""
        engine = self.state.primary("widget") or DEFAULT_WIDGET_ENGINE
        needed = [engine]
        for name in names:
            spec = render_mod.WIDGET_CATALOG.get(name)
            if spec and spec.requires:
                needed.append(spec.requires)
        return needed

    def _widget_status(self, name: str) -> tuple[str, bool]:
        """Row subtitle: short description + position + why it isn't drawn."""
        spec = render_mod.WIDGET_CATALOG[name]
        desc = next((p.desc for p in self.widget_presets if p.name == name), "")
        # The first sentence of the preset description is enough; the engine note isn't needed here.
        short = re.split(r"\s*\(|\.\s", desc, maxsplit=1)[0].strip()
        parts = [short] if short else []
        broken = False
        on = name in self.state.widgets()
        if on:
            zone = next((z for z in render_mod.WIDGET_ZONES
                         if name in self.state.widget_zone_list(z)), spec.zone)
            parts.append("Position: " + render_mod.WIDGET_ZONE_LABELS[zone])
            engine = self.state.primary("widget")
            if not engine:
                parts.append("⚠ No widget engine selected — not drawn")
                broken = True
            elif engine not in spec.engines:
                comp = self.catalog.component(engine)
                parts.append(f"⚠ {comp.title if comp else engine} doesn't draw this")
                broken = True
        # Requirements that aren't installed / selected should show even before
        # turning it on: so the dialog on pressing the switch isn't a surprise.
        for item in deps_mod.unmet(self._widget_needs([name]), self.catalog,
                                   self.state.selected,
                                   self.applier.installed_packages()):
            if on and item.component == DEFAULT_WIDGET_ENGINE \
                    and not self.state.primary("widget"):
                continue            # "no engine selected" was written above
            if item.packages:
                parts.append(f"{'⚠ ' if on else ''}{item.title} not installed")
            else:
                parts.append(f"{'⚠ ' if on else ''}{item.title} not selected")
            broken = broken or on
        return " · ".join(parts), broken

    def _refresh_widget_switches(self) -> None:
        switches = getattr(self, "_widget_switches", None)
        if not switches:
            return
        active = set(self.state.widgets())
        self._widget_switch_guard = True
        try:
            for name, (row, switch) in switches.items():
                on = name in active
                if switch.get_active() != on:
                    switch.set_active(on)
                subtitle, broken = self._widget_status(name)
                row.set_subtitle(esc(subtitle))
                if broken:
                    row.add_css_class("warning")
                else:
                    row.remove_css_class("warning")
        finally:
            self._widget_switch_guard = False

    def _on_widget_switch(self, switch: Gtk.Switch, _pspec, name: str) -> None:
        if getattr(self, "_widget_switch_guard", False):
            return
        active = switch.get_active()

        def done() -> None:
            self.state.set_widget_enabled(self.root, name, active)
            self._refresh_widget_zones()
            self._refresh_widget_engine()
            self._refresh_component_rows()

        if not active:
            done()
            return
        self._require(self._widget_needs([name]),
                      render_mod.WIDGET_CATALOG[name].label, done,
                      self._refresh_widget_switches)

    # --- widget: corner layout ----------------------------------------------
    def _widget_layout_items(self) -> list[dict]:
        """Common source of the preview and the status texts."""
        engine = self.state.primary("widget")
        if not engine:
            return []
        return render_mod.widget_layout(self.state.values,
                                        sorted(self.state.selected), engine)

    def _widget_set_group(self) -> Adw.PreferencesGroup:
        """Preset layouts: which widgets are on and in which corner.

        The corner editor is powerful but a blank canvas; it left the answer to
        "which widget goes where" to the user. The presets here answer that
        question with the layouts of known setups (see docs/preset-sources.md) and
        apply in one click — afterwards you can change them in the corner editor
        as you like.
        """
        group = Adw.PreferencesGroup(
            title="Preset layouts",
            description="A preset writes the widget list, the corner layout and "
                        "the sizes together. After applying, you can "
                        "change them one by one below.")
        self._widget_set_rows: dict[str, Adw.ActionRow] = {}
        current = self.state.get("WIDGET_SET")

        for preset in self.widget_sets:
            names = presets_mod.split_widgets(preset.values.get("WIDGETS", ""))
            zones = " · ".join(
                f"{label}: {preset.values.get('WIDGET_ZONE_' + zone, '') or '—'}"
                for zone, label in self._WIDGET_ZONE_ORDER
                if preset.values.get("WIDGET_ZONE_" + zone))
            subtitle = preset.desc
            if zones:
                subtitle += f"\n{zones}"
            # A widget whose required component isn't selected is SILENTLY not
            # drawn (render:active_widgets drops it). It's said here so nobody goes
            # searching for "why are two boxes missing" after applying the preset.
            missing = sorted({
                render_mod.WIDGET_CATALOG[name].requires for name in names
                if name in render_mod.WIDGET_CATALOG
                and render_mod.WIDGET_CATALOG[name].requires
                and not self.state.is_selected(
                    render_mod.WIDGET_CATALOG[name].requires)})
            if missing:
                subtitle += ("\nMissing component: " + ", ".join(missing)
                             + " — those widgets aren't drawn (Components page)")
            row = Adw.ActionRow(title=esc(preset.title or preset.name),
                                subtitle=esc(subtitle))
            row.set_subtitle_lines(5)
            count = Gtk.Label(label=f"{len(names)} widgets")
            count.add_css_class("hs-chip")
            count.set_valign(Gtk.Align.CENTER)
            row.add_prefix(count)
            button = Gtk.Button(label="Apply", valign=Gtk.Align.CENTER)
            button.connect("clicked", self._on_widget_set_clicked, preset.name)
            row.add_suffix(button)
            if preset.name == current:
                button.add_css_class("suggested-action")
            self._widget_set_rows[preset.name] = row
            group.add(row)
        return group

    def _on_widget_set_clicked(self, _button, name: str) -> None:
        preset = next((p for p in self.widget_sets if p.name == name), None)
        names = presets_mod.split_widgets(
            preset.values.get("WIDGETS", "") if preset else "")
        self._require(self._widget_needs(names),
                      preset.title if preset and preset.title else name,
                      lambda: self._apply_widget_set_now(name))

    def _apply_widget_set_now(self, name: str) -> None:
        self.state.apply_widget_set(self.root, name)
        self._sync_all_rows()
        self._refresh_widget_zones()       # so the corner chips show the new layout
        self._refresh_widget_engine()      # the preset may have selected the engine too
        self._refresh_component_rows()
        for set_name, row in getattr(self, "_widget_set_rows", {}).items():
            button = row.get_last_child()      # the "Apply" button
            if isinstance(button, Gtk.Button):
                if set_name == name:
                    button.add_css_class("suggested-action")
                else:
                    button.remove_css_class("suggested-action")
        title = next((p.title for p in self.widget_sets if p.name == name), name)
        self._toast(f"Widget layout applied: {title}")

    def _widget_style_group(self) -> Adw.PreferencesGroup:
        """Look presets: how the widgets are drawn, whatever the layout.

        The layouts above only said WHICH widgets go WHERE; every widget still
        had the same dark box with an accent border. A style writes the look
        settings (plate, border, shadow, blur, gauges, clock, music card)
        together; each of them stays editable in "Look and size" below.
        """
        group = Adw.PreferencesGroup(
            title="Widget style",
            description="A style sets how every widget looks — box, border, "
                        "gauges, clock and music layout. The layout above "
                        "stays as it is; after applying, each look setting "
                        "can still be changed below.")
        self._widget_style_rows: dict[str, Adw.ActionRow] = {}
        current = self.state.get("WIDGET_STYLE")
        for preset in self.widget_styles:
            row = Adw.ActionRow(title=esc(preset.title or preset.name),
                                subtitle=esc(preset.desc))
            row.set_subtitle_lines(3)
            button = Gtk.Button(label="Apply", valign=Gtk.Align.CENTER)
            button.connect("clicked", self._on_widget_style_clicked, preset.name)
            row.add_suffix(button)
            if preset.name == current:
                button.add_css_class("suggested-action")
            self._widget_style_rows[preset.name] = row
            group.add(row)
        return group

    def _on_widget_style_clicked(self, _button, name: str) -> None:
        self.state.apply_widget_style(self.root, name)
        self._sync_all_rows()               # the look rows show the new values
        for style_name, row in self._widget_style_rows.items():
            button = row.get_last_child()   # the "Apply" button
            if isinstance(button, Gtk.Button):
                if style_name == name:
                    button.add_css_class("suggested-action")
                else:
                    button.remove_css_class("suggested-action")
        title = next((p.title for p in self.widget_styles if p.name == name), name)
        self._toast(f"Widget style applied: {title}")

    def _widget_zone_group(self) -> Adw.PreferencesGroup:
        """Positions in the same layout as their places on screen: 3 columns × 2 rows."""
        group = Adw.PreferencesGroup(
            title="Positions",
            description="The boxes are laid out like their places on screen: the "
                        "widgets in each position start from the edge and line up "
                        "one after another. Click a chip to set its order, position "
                        "and pixel offset; add a new widget "
                        "with '+'.")
        self._widget_zone_boxes: dict[str, Adw.WrapBox] = {}
        row = Adw.PreferencesRow(activatable=False)
        grid = Gtk.Grid(column_spacing=8, row_spacing=8,
                        column_homogeneous=True)
        grid.set_margin_top(10); grid.set_margin_bottom(10)
        grid.set_margin_start(10); grid.set_margin_end(10)
        for index, (zone, label) in enumerate(self._WIDGET_ZONE_ORDER):
            cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            cell.add_css_class("card")
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            inner.set_margin_top(8); inner.set_margin_bottom(8)
            inner.set_margin_start(10); inner.set_margin_end(6)

            head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            name = Gtk.Label(label=label.upper(), xalign=0, hexpand=True)
            name.add_css_class("caption-heading")
            name.add_css_class("dim-label")
            head.append(name)
            add = Gtk.MenuButton(icon_name="list-add-symbolic",
                                 valign=Gtk.Align.CENTER,
                                 tooltip_text="Add a widget to this position")
            add.add_css_class("flat")
            add.set_popover(self._widget_add_popover(zone))
            head.append(add)
            inner.append(head)

            flow = Adw.WrapBox(child_spacing=6, line_spacing=6,
                               halign=Gtk.Align.START)
            self._widget_zone_boxes[zone] = flow
            inner.append(flow)
            cell.append(inner)
            grid.attach(cell, index % 3, index // 3, 1, 1)
        row.set_child(grid)
        group.add(row)
        self._refresh_widget_zones()
        return group

    def _widget_add_popover(self, zone: str) -> Gtk.Popover:
        popover = Gtk.Popover()
        scroller = Gtk.ScrolledWindow(propagate_natural_height=True,
                                      max_content_height=420, hexpand=False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_top(6); box.set_margin_bottom(6)
        box.set_margin_start(6); box.set_margin_end(6)
        scroller.set_child(box)
        popover.set_child(scroller)
        popover.connect("show", lambda _p: self._fill_widget_popover(
            box, zone, popover))
        return popover

    def _fill_widget_popover(self, box: Gtk.Box, zone: str,
                             popover: Gtk.Popover) -> None:
        child = box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            box.remove(child)
            child = nxt

        engine = self.state.primary("widget")
        placed = set(self.state.widgets())
        for name, spec in render_mod.WIDGET_CATALOG.items():
            if name in placed:
                continue
            btn = Gtk.Button(halign=Gtk.Align.FILL)
            btn.add_css_class("flat")
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            inner.append(Gtk.Label(label=spec.label, xalign=0))
            notes = []
            if spec.requires:
                comp = self.catalog.component(spec.requires)
                notes.append(f"requires {comp.title if comp else spec.requires}")
            if engine and engine not in spec.engines:
                comp = self.catalog.component(engine)
                notes.append(f"{comp.title if comp else engine} can't draw it")
            if notes:
                sub = Gtk.Label(label=" · ".join(notes), xalign=0)
                sub.add_css_class("caption")
                sub.add_css_class("dim-label")
                inner.append(sub)
            btn.set_child(inner)
            btn.connect("clicked", self._on_widget_added, zone, name, popover)
            box.append(btn)

        if box.get_first_child() is None:
            empty = Gtk.Label(label="No widgets left to add")
            empty.add_css_class("dim-label")
            box.append(empty)

    def _widget_chip(self, zone: str, name: str, index: int,
                     count: int) -> Gtk.Widget:
        spec = render_mod.WIDGET_CATALOG[name]
        engine = self.state.primary("widget")
        unsupported = bool(engine) and engine not in spec.engines
        missing_req = bool(spec.requires) and not self.state.is_selected(spec.requires)

        chip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        chip.add_css_class("linked")
        chip.add_css_class("hs-chip")
        broken = unsupported or missing_req
        if broken:
            chip.add_css_class("hs-chip-unsupported")

        dx, dy = self.state.widget_offset(name)
        shifted = " ⇄" if (dx or dy) else ""
        menu = Gtk.MenuButton(label=spec.label + shifted
                              + (" ⚠" if broken else ""))
        menu.add_css_class("pill")
        if broken:
            menu.add_css_class("warning")
            reasons = []
            if unsupported:
                comp = self.catalog.component(engine)
                reasons.append(f"{comp.title if comp else engine} doesn't draw this "
                               f"widget — it isn't included in the generated configuration.")
            if missing_req:
                comp = self.catalog.component(spec.requires)
                reasons.append(f"The {comp.title if comp else spec.requires} "
                               f"component isn't selected; the widget isn't generated.")
            menu.set_tooltip_text(" ".join(reasons))

        menu.set_popover(self._widget_chip_popover(zone, name, index, count))
        chip.append(menu)

        close = Gtk.Button(icon_name="window-close-symbolic",
                           tooltip_text="Remove this widget")
        close.add_css_class("pill")
        close.add_css_class("hs-chip-close")
        close.connect("clicked", self._on_widget_removed, name)
        chip.append(close)
        return chip

    def _widget_chip_popover(self, zone: str, name: str, index: int,
                             count: int) -> Gtk.Popover:
        """Chip menu: order in the stack, position and pixel offset."""
        pop = Gtk.Popover()
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        inner.set_margin_top(8); inner.set_margin_bottom(8)
        inner.set_margin_start(8); inner.set_margin_end(8)

        def heading(text: str) -> Gtk.Label:
            label = Gtk.Label(label=text, xalign=0)
            label.add_css_class("caption-heading")
            label.add_css_class("dim-label")
            return label

        # In the top positions the list runs top to bottom, in the bottom ones
        # bottom to top (the first element is at the edge). The arrow direction
        # should describe the movement ON SCREEN, not in the list.
        bottom = render_mod.WIDGET_ZONE_EDGES[zone][0] == "bottom"
        up, down = ("▲  Up", "▼  Down")
        inner.append(heading("ORDER"))
        order = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4,
                        homogeneous=True)
        for delta in (-1, 1):
            text = (down if delta < 0 else up) if bottom else \
                   (up if delta < 0 else down)
            b = Gtk.Button(label=text)
            b.set_sensitive(0 <= index + delta < count)
            b.connect("clicked", self._on_widget_moved, zone, name, delta, pop)
            order.append(b)
        inner.append(order)

        inner.append(heading("POSITION"))
        zones = Gtk.Grid(column_spacing=4, row_spacing=4,
                         column_homogeneous=True)
        for i, (target, label) in enumerate(self._WIDGET_ZONE_ORDER):
            b = Gtk.Button(label=label)
            if target == zone:
                b.add_css_class("suggested-action")
                b.set_sensitive(False)
            b.connect("clicked", self._on_widget_rezoned, target, name, pop)
            zones.attach(b, i % 3, i // 3, 1, 1)
        inner.append(zones)

        centered = render_mod.WIDGET_ZONE_EDGES[zone][1] == "center"
        inner.append(heading("FINE TUNING (px)"))
        dx, dy = self.state.widget_offset(name)
        limit = render_mod.WIDGET_OFFSET_LIMIT
        spins: list[Gtk.SpinButton] = []
        for axis, label, value, tip in (
                ("x", "Horizontal", dx,
                 "Extra distance from the side edge. Not applied in center positions."
                 if centered else "Extra distance from the side edge; negative moves "
                                  "it closer to the edge."),
                ("y", "Vertical", dy,
                 "Extra distance from the top/bottom edge; also pushes the widgets "
                 "that follow in the same position.")):
            line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            line.append(Gtk.Label(label=label, xalign=0, hexpand=True))
            spin = Gtk.SpinButton.new_with_range(-limit, limit, 1)
            spin.set_value(value)
            spin.set_tooltip_text(tip)
            if axis == "x" and centered:
                spin.set_sensitive(False)
            no_scroll_change(spin)
            line.append(spin)
            inner.append(line)
            spins.append(spin)

        def on_spin(_spin) -> None:
            self.state.set_widget_offset(name, int(spins[0].get_value()),
                                         int(spins[1].get_value()))
        for spin in spins:
            spin.connect("value-changed", on_spin)

        reset = Gtk.Button(label="Reset offset")
        reset.add_css_class("flat")
        reset.connect("clicked", lambda _b: [sp.set_value(0) for sp in spins])
        inner.append(reset)

        # The chip label (the ⇄ mark) shows the offset; rebuilding the chips every
        # time the spinners change would destroy the open menu, so the
        # refresh happens when the menu closes.
        pop.connect("closed", lambda _p: GLib.idle_add(
            self._refresh_widget_zones_once))
        pop.set_child(inner)
        return pop

    def _refresh_widget_zones_once(self) -> bool:
        self._refresh_widget_zones()
        return False

    def _on_widget_rezoned(self, _btn, zone: str, name: str,
                           popover: Gtk.Popover) -> None:
        popover.popdown()
        self.state.add_widget(self.root, zone, name)

    def _refresh_widget_zones(self) -> None:
        self._refresh_widget_switches()
        for zone, _label in self._WIDGET_ZONE_ORDER:
            flow = getattr(self, "_widget_zone_boxes", {}).get(zone)
            if flow is None:
                continue
            child = flow.get_first_child()
            while child:
                nxt = child.get_next_sibling()
                flow.remove(child)
                child = nxt
            names = [n for n in self.state.widget_zone_list(zone)
                     if n in render_mod.WIDGET_CATALOG]
            for index, name in enumerate(names):
                flow.append(self._widget_chip(zone, name, index, len(names)))
            if not names:
                empty = Gtk.Label(label="empty")
                empty.add_css_class("dim-label")
                empty.add_css_class("caption")
                flow.append(empty)

    def _on_widget_added(self, _btn, zone: str, name: str,
                         popover: Gtk.Popover) -> None:
        popover.popdown()

        def done() -> None:
            self.state.add_widget(self.root, zone, name)
            self._refresh_widget_zones()
            self._refresh_widget_engine()

        self._require(self._widget_needs([name]),
                      render_mod.WIDGET_CATALOG[name].label, done)

    def _on_widget_removed(self, _btn, name: str) -> None:
        self.state.remove_widget(self.root, name)
        self._refresh_widget_zones()
        self._refresh_widget_engine()

    def _on_widget_moved(self, _btn, zone: str, name: str, delta: int,
                         popover: Gtk.Popover) -> None:
        popover.popdown()
        self.state.move_widget(zone, name, delta)
        self._refresh_widget_zones()

    def _goto_page(self, page_id: str) -> None:
        """Selects the row in the sidebar — that updates the title too."""
        for index, (pid, _title, _icon) in enumerate(self.pages):
            if pid == page_id:
                row = self.listbox.get_row_at_index(index)
                if row is not None:
                    self.listbox.select_row(row)
                return

    def _resync_rows(self) -> None:
        """Re-reads the rows from the state: the same setting can have two rows
        (Appearance and Mix); when one changes, the other is refreshed as its page opens."""
        callbacks = list(self._sync_rows.values())
        for sync in getattr(self, "_mix_sync", {}).values():
            callbacks += sync.values()
        for callback in callbacks:
            callback()
        self._sync_colour_buttons()

    def _sync_all_rows(self) -> None:
        """Writes the values in the state back to every row in the UI."""
        self._resync_rows()
        self._refresh_bar_status()
        status = getattr(self, "_preset_status", None)
        if status is not None:
            status.set_subtitle(
                f"Active: {self.state.preset}" if self.state.preset
                else "No profile applied yet")
        for name, check in getattr(self, "_theme_buttons", {}).items():
            active = name == self.state.get("THEME")
            if check.get_active() != active:
                check.set_active(active)
        self._update_theme_label()
        for value, check in getattr(self, "_colorscheme_buttons", {}).items():
            active = value == (self.state.get("COLOR_SCHEME") or "dark")
            if check.get_active() != active:
                check.set_active(active)
        # When a preset is applied BAR_MODULES_* change wholesale; the chip list
        # must be redrawn too (in place of the old dropdown editor — see
        # _bar_layout_group).
        if getattr(self, "_zone_boxes", None):
            self._refresh_zone_chips()

        self._on_state_changed()

    # --- applications -------------------------------------------------------
    #: Axes on the "Applications" page. Bar/terminal/launcher have their own rich
    #: pages, so they're not here; the remaining single-choice
    #: categories used to be selectable only from the "Components" page,
    #: and that page was removed.
    _APP_AXES: tuple[str, ...] = ("files", "notify", "wallpaper")

    def _page_apps(self) -> Gtk.Widget:
        """Default applications: which INSTALLED program is used.

        Unlike the "Components" page, no packages are installed here. An option
        that isn't installed is visible but can't be selected; next to it is a
        copyable pacman command saying what to install (see the System page).
        """
        page = Adw.PreferencesPage()

        intro = Adw.PreferencesGroup(
            title="Default applications",
            description="The choice here goes to three places at once: keybindings "
                        "(MOD+E file manager), ~/.config/mimeapps.list "
                        "(which file type opens with what) and "
                        "~/.config/xdg-terminals.list. This is the single source.")
        page.add(intro)

        for category in self.catalog.categories:
            if category.id in self._APP_AXES:
                page.add(self._app_axis_group(category))

        browser = Adw.PreferencesGroup(
            title="Browser",
            description="The MOD+W shortcut and http/https links open this.")
        row = Adw.EntryRow(title="Browser command")
        row.set_text(self.state.get("BROWSER"))
        row.connect("changed", lambda r: self.state.set("BROWSER", r.get_text()))
        self._sync_rows["BROWSER"] = lambda r=row: (
            r.get_text() != self.state.get("BROWSER")
            and r.set_text(self.state.get("BROWSER")))
        browser.add(row)
        page.add(browser)
        return page

    def _app_axis_group(self, category, sync: dict | None = None) -> Adw.PreferencesGroup:
        """A single-choice application axis (notifications, file manager…).

        If ``sync`` is given (the copy in Mix) the buttons aren't written to
        _component_widgets — that keeps a single widget per key, and the real row
        on the Applications page would stop updating.
        """
        group = Adw.PreferencesGroup(title=esc(category.title))
        radio_root: Gtk.CheckButton | None = None

        for comp in category.components:
            missing = self.applier.missing_packages(comp.id)
            subtitle = comp.desc
            if missing:
                subtitle += "  ·  not installed: " + ", ".join(missing)

            row = Adw.ActionRow(title=esc(comp.title), subtitle=esc(subtitle))
            row.set_subtitle_lines(2)
            if sync is None:
                self._app_axis_rows[comp.id] = row

            check = Gtk.CheckButton(valign=Gtk.Align.CENTER)
            if radio_root is None:
                radio_root = check
            else:
                check.set_group(radio_root)
            check.set_active(self.state.is_selected(comp.id))
            check.connect("toggled", self._on_single_toggled, comp.id)
            row.add_prefix(check)
            if sync is None:
                self._component_widgets[comp.id] = check
            else:
                sync[f"component:{comp.id}"] = (
                    lambda c=check, i=comp.id: c.set_active(self.state.is_selected(i)))

            if comp.aur:
                row.add_suffix(aur_mod.badge(comp.aur))
            if missing:
                # Selecting an option that isn't installed makes _require open the
                # "Install and enable" dialog: the install runs in a terminal (sudo password
                # there), and when done the choice applies by itself.
                row.add_suffix(self._copy_button(
                    self._install_command(missing)))
            row.set_activatable_widget(check)

            if comp.url:
                link = Gtk.LinkButton(uri=comp.url, label="")
                link.set_child(Gtk.Image.new_from_icon_name(
                    "adw-external-link-symbolic"))
                link.set_valign(Gtk.Align.CENTER)
                link.set_tooltip_text(comp.url)
                row.add_suffix(link)

            group.add(row)
        return group

    def _refresh_app_axis_rows(self) -> None:
        """Refreshes the "not installed" subtitles on the Applications page."""
        for comp_id, row in self._app_axis_rows.items():
            comp = self.catalog.component(comp_id)
            if comp is None:
                continue
            missing = self.applier.missing_packages(comp_id)
            subtitle = comp.desc
            if missing:
                subtitle += "  ·  not installed: " + ", ".join(missing)
            row.set_subtitle(esc(subtitle))

    def _require_component(self, comp_id: str, on_ok) -> None:
        """Asks whether the packages are installed before selecting a component.

        If cancelled, the buttons are pulled back to the (unchanged) selection in the state.
        """
        comp = self.catalog.component(comp_id)
        self._require([comp_id], comp.title if comp else comp_id, on_ok,
                      self._refresh_component_rows, chosen=comp_id)

    def _on_single_toggled(self, button, comp_id: str) -> None:
        # Programmatic sync (_refresh_component_rows) writes the selection from the
        # state; it's already selected, so nothing is asked again here.
        if button.get_active() and not self.state.is_selected(comp_id):
            self._require_component(
                comp_id, lambda: self.state.toggle(comp_id, True))

    def _on_bar_backend_toggled(self, button, comp_id: str) -> None:
        if not button.get_active() or self.state.is_selected(comp_id):
            return

        def done() -> None:
            self.state.toggle(comp_id, True)
            self._refresh_component_rows()
            # The button label turns into "Selected" once chosen (see
            # _refresh_bar_backend_columns); the backend's name is read from the table.
            title = dict(_BAR_BACKENDS).get(comp_id, comp_id)
            self._toast(f"Bar backend: {title}")

        self._require_component(comp_id, done)

    #: Warnings written under the category title on the Components page.
    #: SELECTING a component makes its configuration get generated; it doesn't
    #: install the package (this app never asks for sudo) or build hyprpm plugins.
    _COMPONENT_NOTES: dict[str, str] = {
        "plugins": "Plugins aren't pacman packages: they're built FROM SOURCE "
                   "with hyprpm. Selecting one here only generates plugins.conf; "
                   "run ./install.sh to build them.",
        "login": "The login manager is a system service; changing it requires "
                 "root and is only done with ./install.sh.",
        "hardware": "Drivers are chosen by hardware during installation. The "
                    "choice here only affects the generated configuration.",
    }

    def _page_components(self) -> Gtk.Widget:
        """Programs this tool configures — on/off.

        Single-choice axes (terminal, bar, launcher, notifications, file
        manager, wallpaper) are selected on their own pages. MULTI-choice
        categories, however, appeared nowhere: hyprsunset, swayosd,
        cava, wlogout, clipboard history, screen recording/instant replay, matugen,
        hyprpm plugins, nwg-displays… All were installed and their configuration
        generated, but there was no trace of them in the settings app — turning one
        off or on later meant editing the COMPONENTS line in settings.conf by
        hand.
        """
        page = Adw.PreferencesPage()
        self._widen_page(page, 940)

        intro = Adw.PreferencesGroup(
            title="Components",
            description="Turning a component off stops its configuration "
                        "from being generated (existing files aren't deleted); "
                        "turning it on configures it right away if the package is installed. "
                        "This app does NOT install packages: copy the pacman command "
                        "on a row that isn't installed and run it in a terminal; "
                        "then the switch becomes available.")
        page.add(intro)

        for category in self.catalog.categories:
            # Single-choice axes have their own pages; showing the same choice in
            # two places raises the question "which one is right".
            if category.single:
                continue
            group = Adw.PreferencesGroup(
                title=esc(category.title),
                description=esc(self._COMPONENT_NOTES.get(category.id, "")))
            for comp in category.components:
                group.add(self._component_row(category, comp))
            page.add(group)
        return page

    def _component_row(self, category, comp) -> Adw.ActionRow:
        """A single row of the Components page: switch + status + pacman command."""
        missing = self.applier.missing_packages(comp.id)
        subtitle = comp.desc
        if category.required:
            subtitle += "  ·  required — can't be turned off"
        elif missing:
            subtitle += "  ·  not installed: " + ", ".join(missing)

        row = Adw.ActionRow(title=esc(comp.title), subtitle=esc(subtitle))
        row.set_subtitle_lines(3)

        switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        switch.set_active(self.state.is_selected(comp.id))
        # A component with missing packages can be turned on too: an install is
        # offered when turning it on (see _require). The switch used to be locked
        # and the only way was to copy the command and run it by hand.
        switch.set_sensitive(not category.required)
        switch.connect("notify::active", self._on_component_toggled, comp.id)
        self._component_widgets[comp.id] = switch

        if comp.aur:
            row.add_suffix(aur_mod.badge(comp.aur))
        if missing and not category.required:
            row.add_suffix(self._copy_button(self._install_command(missing)))
        if comp.url:
            link = Gtk.LinkButton(uri=comp.url, label="")
            link.set_child(Gtk.Image.new_from_icon_name(
                "adw-external-link-symbolic"))
            link.set_valign(Gtk.Align.CENTER)
            link.set_tooltip_text(comp.url)
            row.add_suffix(link)
        row.add_suffix(switch)
        row.set_activatable_widget(switch)
        return row

    def _on_component_toggled(self, switch, _param, comp_id: str) -> None:
        if self.state.is_selected(comp_id) == switch.get_active():
            return          # _refresh_component_rows writing its own value
        if not switch.get_active():
            self.state.toggle(comp_id, False)
            return
        self._require_component(comp_id,
                                lambda: self.state.toggle(comp_id, True))

    def _refresh_component_rows(self) -> None:
        for comp_id, widget in getattr(self, "_component_widgets", {}).items():
            active = self.state.is_selected(comp_id)
            if isinstance(widget, Gtk.Switch):
                if widget.get_active() != active:
                    widget.set_active(active)
            elif widget.get_active() != active:
                widget.set_active(active)
        # The program-choice copies in Mix (see _app_axis_group).
        for sync in getattr(self, "_mix_sync", {}).values():
            for name, callback in list(sync.items()):
                if name.startswith("component:"):
                    callback()
        # The Waybar/HyprPanel buttons on the "Bar Presets" page — the bar
        # backend is drawn as buttons there, so they're kept in a separate dict
        # (the same component appears as two different widget types).
        for comp_id, widget in getattr(self, "_bar_backend_widgets", {}).items():
            active = self.state.is_selected(comp_id)
            if widget.get_active() != active:
                widget.set_active(active)
        self._refresh_bar_backend_columns()
        # The backend changed: the "applies/no effect" notes on the bar settings
        # page and the "not supported" marks on the layout chips must be
        # rewritten too.
        self._refresh_bar_settings_note()
        if getattr(self, "_zone_boxes", None):
            self._refresh_zone_chips()

    # --- appearance ---------------------------------------------------------
    def _page_appearance(self) -> Gtk.Widget:
        """Two columns: scrolling settings on the left, a fixed live preview on the right.

        Since the preview sits in its own pane, there's no need to scroll up
        while changing settings — see preview_page below.

        The live preview showing the whole desktop stays on the right; diagrams
        explaining a particular settings group (sizes, animation) are placed
        next to that group — see `_group_beside_diagram`.
        """
        page = Adw.PreferencesPage()          # left: settings
        self._widen_page(page, 880)
        preview_page = Adw.PreferencesPage()  # right: live preview, fixed

        preview_group = Adw.PreferencesGroup(
            title="Live preview",
            description="This image updates instantly as the settings below "
                        "change. The front window is the focused window.")
        self.preview = DesktopPreview(
            get_setting=self.state.get,
            get_palette=self.state.palette,
            has_component=self.state.category_has_selection,
            root=self.root,
        )
        frame = Gtk.Frame()
        frame.set_child(self.preview)
        frame.add_css_class("view")
        frame.set_margin_top(6)
        preview_group.add(frame)
        preview_page.add(preview_group)

        # The "Sizes" diagram moved from here to beside the Layout group: which
        # slider moves which arrow in the diagram can be seen without reading,
        # since the two sit at the same height (see the group loop below).

        colorscheme_group = Adw.PreferencesGroup(
            title="System color",
            description="Independent of the accent colors of the theme below: decides "
                        "whether GTK/Qt/libadwaita apps open in dark or light "
                        "mode. Even with a dark theme selected, choosing "
                        "'Light' here opens apps in light mode.")
        root_cs: Gtk.CheckButton | None = None
        self._colorscheme_buttons: dict[str, Gtk.CheckButton] = {}
        for value, title, subtitle in (
                ("dark", "Dark", "Apps open in dark mode"),
                ("light", "Light", "Apps open in light mode")):
            row = Adw.ActionRow(title=esc(title), subtitle=esc(subtitle))
            check = Gtk.CheckButton(valign=Gtk.Align.CENTER)
            if root_cs is None:
                root_cs = check
            else:
                check.set_group(root_cs)
            check.set_active(value == (self.state.get("COLOR_SCHEME") or "dark"))
            check.connect("toggled", self._on_colorscheme_toggled, value)
            self._colorscheme_buttons[value] = check
            row.add_prefix(check)
            row.set_activatable_widget(check)
            colorscheme_group.add(row)
        page.add(colorscheme_group)

        theme_group = Adw.PreferencesGroup(
            title="Theme",
            description="The chosen palette is applied to Hyprland borders, the status bar, "
                        "the terminal, the launcher and notifications at once.")
        page.add(theme_group)
        theme_group.add(self._theme_picker())
        # Manual tone + picking colors from the wallpaper: right below the theme,
        # since both mean "tweak this palette a bit".
        page.add(self._group_widget("tone"))
        page.add(WallpaperSwatches(self))

        typo = Adw.PreferencesGroup(title="Font")

        # Font: free text box + quick pick list. Both write the same setting and
        # follow each other; when a family name not in the list is typed, the
        # selection falls to the "Custom" row.
        font_row = Adw.EntryRow(title="Font family")
        font_row.set_text(self.state.get("FONT_FAMILY"))
        font_row.set_tooltip_text(
            "Fontconfig family name. Using a Nerd Font is recommended; the "
            "icons in the status bar need it.")
        typo.add(font_row)

        families = [value for value, _label in schema.FONT_SUGGESTIONS]
        labels = [label for _value, label in schema.FONT_SUGGESTIONS]
        quick = Adw.ComboRow(
            title="Quick pick",
            subtitle="The listed fonts are the ones this setup brings; "
                     "you can also type your own font in the box above.")
        quick.set_model(Gtk.StringList.new([*labels, "Custom"]))
        # Re-entrancy guard: the combo updates the entry, the entry the combo;
        # without the flag the two trigger each other in a loop.
        guard = {"busy": False}

        def _sync_font() -> None:
            current = self.state.get("FONT_FAMILY")
            if font_row.get_text() != current:
                font_row.set_text(current)
            index = families.index(current) if current in families else len(families)
            if quick.get_selected() != index:
                guard["busy"] = True
                quick.set_selected(index)
                guard["busy"] = False

        def _on_font_typed(row) -> None:
            self.state.set("FONT_FAMILY", row.get_text())
            current = row.get_text()
            index = families.index(current) if current in families else len(families)
            if quick.get_selected() != index:
                guard["busy"] = True
                quick.set_selected(index)
                guard["busy"] = False

        def _on_quick_selected(row, _param) -> None:
            if guard["busy"]:
                return
            index = row.get_selected()
            if 0 <= index < len(families):
                self.state.set("FONT_FAMILY", families[index])
                font_row.set_text(families[index])

        font_row.connect("changed", _on_font_typed)
        quick.connect("notify::selected", _on_quick_selected)
        self._sync_rows["FONT_FAMILY"] = _sync_font
        _sync_font()
        typo.add(quick)

        # The terminal font is separate: the family above may be proportional
        # (the default "Noto Sans" is) and kitty/foot/alacritty don't align
        # properly with a proportional font. A simple text box is enough — a quick
        # pick list would be misleading here, since most of the UI fonts in
        # the list aren't monospace.
        mono_row = Adw.EntryRow(title="Terminal font (monospace)")
        mono_row.set_text(self.state.get("FONT_MONO"))
        mono_row.set_tooltip_text(
            "Terminal emulators and the audio visualizer use this. "
            "It must be a monospace family; its Nerd Font version "
            "brings the icons too.")
        mono_row.connect("changed",
                         lambda row: self.state.set("FONT_MONO", row.get_text()))

        def _sync_mono() -> None:
            current = self.state.get("FONT_MONO")
            if mono_row.get_text() != current:
                mono_row.set_text(current)

        self._sync_rows["FONT_MONO"] = _sync_mono
        _sync_mono()
        typo.add(mono_row)

        font_size = no_scroll_change(Adw.SpinRow.new_with_range(6, 24, 1))
        font_size.set_title("Font size")
        font_size.set_value(float(self.state.get("FONT_SIZE") or 11))
        font_size.connect("notify::value", lambda r, _p: self.state.set(
            "FONT_SIZE", str(int(r.get_value()))))
        self._sync_rows["FONT_SIZE"] = lambda: font_size.set_value(
            float(self.state.get("FONT_SIZE") or 11))
        typo.add(font_size)

        mod = Adw.ComboRow(title="Main modifier key (MOD)",
                           subtitle="The base key of all keybindings")
        mod_values = ["SUPER", "ALT", "CTRL"]
        mod.set_model(Gtk.StringList.new(["SUPER (Windows key)", "ALT", "CTRL"]))
        mod.set_selected(mod_values.index(self.state.get("MOD_KEY") or "SUPER"))
        mod.connect("notify::selected", lambda r, _p: self.state.set(
            "MOD_KEY", mod_values[r.get_selected()]))
        self._sync_rows["MOD_KEY"] = lambda: mod.set_selected(
            mod_values.index(self.state.get("MOD_KEY"))
            if self.state.get("MOD_KEY") in mod_values else 0)
        typo.add(mod)
        page.add(typo)
        page.add(self._icon_theme_group())

        page.add(self._colour_editor())

        # Groups with a diagram are laid out side by side; the rest in a single column.
        beside = {
            # Size diagram: sits right across from the gap/border/rounding
            # sliders. The GAPS_OUT/ROUNDING labels are written on the diagram's
            # edges, so they got clipped in a narrow column — 350 is the smallest
            # width those labels fit in.
            "layout": (LayoutDiagram, "diagram", 350,
                       "Shows which gap each slider changes; "
                       "zoomed in so the sizes are readable."),
            # Animation settings can't have a static preview — what they change is
            # the motion itself; the diagram plays the transitions with the real
            # durations and curves.
            "animation": (AnimationDiagram, "anim_diagram", 330,
                          "Window opening, moving, workspace switch and "
                          "closing play in turn."),
        }
        for group_id in PAGE_GROUPS["appearance"]:
            if group_id == "tone":
                continue
            widget = self._group_widget(group_id)
            if group_id in beside:
                diagram_cls, attr, width, note = beside[group_id]
                page.add(self._group_beside_diagram(widget, diagram_cls, attr,
                                                    note, width))
            else:
                page.add(widget)

        # The left column now carries not just the setting rows but the
        # diagrams beside them too; at 620px both were cramped.
        return _settings_paned(page, preview_page, 900)

    # --- theme picker -------------------------------------------------------
    def _theme_picker(self) -> Gtk.Widget:
        """Themes as small color tiles in a searchable grid.

        Each theme used to be a row with a color strip: ~85 rows took up ~5800
        pixels of the page by themselves, and reaching the settings below meant a
        long scroll. Now the tiles sit side by side, the list is narrowed
        with search + a dark/light filter, and it takes at most ~420 pixels
        (the rest scrolls inside).
        """
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        search = Gtk.SearchEntry(placeholder_text="Search themes…", hexpand=True)
        tools.append(search)
        # The selected theme can end up far down the alphabetical list; show its
        # name here too (see _on_theme_toggled).
        self._theme_current_label = Gtk.Label(xalign=1)
        self._theme_current_label.add_css_class("caption")
        self._theme_current_label.add_css_class("dim-label")
        self._update_theme_label()
        tools.append(self._theme_current_label)
        kinds = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        kinds.add_css_class("linked")
        kind = {"value": "all"}
        first: Gtk.ToggleButton | None = None
        for value, text in (("all", "All"), ("dark", "Dark"),
                            ("light", "Light")):
            btn = Gtk.ToggleButton(label=text)
            if first is None:
                first = btn
                btn.set_active(True)
            else:
                btn.set_group(first)
            btn.connect("toggled", lambda b, v=value: b.get_active() and (
                kind.update(value=v), flow.invalidate_filter()))
            kinds.append(btn)
        tools.append(kinds)
        box.append(tools)

        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
                           homogeneous=True, row_spacing=4, column_spacing=4,
                           min_children_per_line=3, max_children_per_line=8,
                           valign=Gtk.Align.START)
        self._theme_buttons: dict[str, Gtk.ToggleButton] = {}
        meta: dict[Gtk.Widget, tuple[str, bool]] = {}
        current = self.state.get("THEME")
        root: list[Gtk.ToggleButton] = []

        def tile(name: str, label: str, source, light: bool) -> None:
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            inner.set_margin_top(4)
            inner.set_margin_bottom(2)
            strip = SwatchStrip(source, width=112, height=16)
            strip.set_halign(Gtk.Align.CENTER)
            inner.append(strip)
            text = Gtk.Label(label=label, max_width_chars=14,
                             ellipsize=Pango.EllipsizeMode.END)
            text.add_css_class("caption")
            inner.append(text)
            button = Gtk.ToggleButton(child=inner, tooltip_text=label)
            button.add_css_class("flat")
            if root:
                button.set_group(root[0])
            else:
                root.append(button)
            button.set_active(name == current)
            button.connect("toggled", self._on_theme_toggled, name)
            self._theme_buttons[name] = button
            flow.append(button)
            meta[button.get_parent()] = (name.lower(), light)

        # "auto": the palette is extracted from the wallpaper; even when not
        # selected it shows the image's palette (the extraction is cached).
        tile("auto", "From wallpaper", lambda: render_mod.effective_palette(
            {**self.state.values, "THEME": "auto",
             "CUSTOM_COLORS": (self.state.get("CUSTOM_COLORS")
                               if self.state.get("THEME") == "auto" else "")})[1],
            False)
        for name in themes.names():
            palette = themes.THEMES[name]
            # The selected theme's tile also shows manual color edits
            # (state.palette).
            source = ((lambda: self.state.palette()) if name == current
                      else palette)
            tile(name, name, source, themes.is_light(palette))

        def visible(child: Gtk.FlowBoxChild) -> bool:
            name, light = meta.get(child, ("", False))
            if name == "auto":
                return not search.get_text()
            if kind["value"] == "dark" and light:
                return False
            if kind["value"] == "light" and not light:
                return False
            return search.get_text().strip().lower() in name

        flow.set_filter_func(visible)
        search.connect("search-changed", lambda _e: flow.invalidate_filter())

        scroller = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            propagate_natural_height=True, min_content_height=300,
            max_content_height=420)
        scroller.set_child(flow)
        frame = Gtk.Frame()
        frame.add_css_class("view")
        frame.set_child(scroller)
        box.append(frame)
        return box

    # --- cursor quick pick ---------------------------------------------------
    def _cursor_quick_group(self, cursor_row: Adw.EntryRow) -> Gtk.Widget:
        """Pick row showing the installed cursor themes with their real images.

        Those found on the system come first with their real Xcursor image;
        suggestions this tool will install but that aren't installed yet (e.g. Bibata
        variants) follow with a faint arrow sketch — none stays blank.
        """
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(2)
        box.set_margin_bottom(10)
        box.set_margin_start(12)
        box.set_margin_end(12)
        label = Gtk.Label(label="Quick pick — shows how the cursor really "
                                "looks", xalign=0, wrap=True)
        label.add_css_class("caption")
        label.add_css_class("dim-label")
        box.append(label)

        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
                           homogeneous=True, row_spacing=6, column_spacing=6,
                           min_children_per_line=3, max_children_per_line=8,
                           valign=Gtk.Align.START)

        installed = {n.lower() for n in cursors_mod.available()}
        current = self.state.get("CURSOR_THEME")
        self._cursor_buttons: dict[str, Gtk.ToggleButton] = {}
        root_button: Gtk.ToggleButton | None = None

        for name in cursors_mod.quick_list():
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            inner.set_margin_top(8)
            inner.set_margin_bottom(6)
            inner.set_margin_start(10)
            inner.set_margin_end(10)
            inner.append(CursorGlyph(name))
            caption = Gtk.Label(label=name, xalign=0.5, wrap=True,
                                justify=Gtk.Justification.CENTER)
            caption.set_max_width_chars(14)
            caption.add_css_class("caption")
            if name.lower() not in installed:
                caption.add_css_class("dim-label")
            inner.append(caption)

            button = Gtk.ToggleButton(child=inner)
            button.add_css_class("flat")
            button.add_css_class("card")
            if root_button is None:
                root_button = button
            else:
                button.set_group(root_button)
            button.set_active(name.lower() == current.lower())
            if name.lower() not in installed:
                button.set_tooltip_text(
                    f"{name} — not installed on this system yet; "
                    "comes with the installation")

            def _on_toggled(btn, _name=name) -> None:
                if not btn.get_active():
                    return
                self.state.set("CURSOR_THEME", _name)
                cursor_row.set_text(_name)

            button.connect("toggled", _on_toggled)
            self._cursor_buttons[name] = button
            flow.append(button)

        box.append(flow)
        return box

    # --- icon theme ---------------------------------------------------------
    def _icon_theme_group(self) -> Adw.PreferencesGroup:
        """App icon themes: installed sets with their real icons, suggested
        (not installed) sets with their package name. Clicking one that isn't installed
        starts the install in a terminal and selects the theme; when the package
        arrives the settings are re-applied (see _watch_install)."""
        group = Adw.PreferencesGroup(
            title="Icon theme",
            description="App, folder and launcher icons — GTK, Qt, "
                        "the launcher, dock and tray use the same set")
        entry = Adw.EntryRow(title="Icon theme (empty = automatic)")
        entry.set_text(self.state.get("ICON_THEME_NAME"))
        entry.connect("changed", lambda r: self.state.set(
            "ICON_THEME_NAME", r.get_text().strip()))
        refresh = Gtk.Button(icon_name="view-refresh-symbolic",
                             valign=Gtk.Align.CENTER,
                             tooltip_text="Rescan installed themes")
        refresh.add_css_class("flat")
        entry.add_suffix(refresh)
        group.add(entry)

        holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        group.add(holder)
        self._icon_buttons: dict[str, Gtk.ToggleButton] = {}

        def build() -> None:
            child = holder.get_first_child()
            while child is not None:
                holder.remove(child)
                child = holder.get_first_child()
            self._icon_buttons = {}
            holder.append(self._icon_theme_flow(entry))

        refresh.connect("clicked", lambda _b: build())
        self._icon_gallery_rebuild = build
        build()

        def _sync() -> None:
            current = self.state.get("ICON_THEME_NAME")
            if entry.get_text().strip() != current:
                entry.set_text(current)
            for name, btn in self._icon_buttons.items():
                active = name.lower() == current.lower()
                if btn.get_active() != active:
                    btn.set_active(active)

        # The ICON_THEME_NAME row in the Environment group registers its own
        # callback under the same key; a separate key so it isn't overwritten.
        self._sync_rows["ICON_THEME_NAME:gallery"] = _sync
        return group

    def _icon_theme_flow(self, entry: Adw.EntryRow) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(10)
        installed = icons_mod.available()
        installed_keys = {n.lower() for n in installed}
        missing = [s for s in icons_mod.SUGGESTED
                   if s.name.lower() not in installed_keys]
        current = self.state.get("ICON_THEME_NAME")
        root_button: list[Gtk.ToggleButton] = []

        def card(name: str, label: str, theme: Gtk.IconTheme | None,
                 suggestion: icons_mod.IconSet | None) -> Gtk.ToggleButton:
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            inner.set_margin_top(8)
            inner.set_margin_bottom(6)
            inner.set_margin_start(8)
            inner.set_margin_end(8)
            grid = Gtk.Grid(row_spacing=4, column_spacing=4,
                            halign=Gtk.Align.CENTER)
            shot = (self.root / "assets" / "icon-previews" / f"{name}.png"
                    if theme is None else None)
            if shot is not None and shot.is_file():
                # Not installed: an image pre-rendered from the package's own icons
                # (tools/icon-previews.py) — so you can see what will be downloaded.
                # Same size as the grid (3×2 × 32 px + 4 px spacing).
                picture = Gtk.Picture.new_for_filename(str(shot))
                picture.set_content_fit(Gtk.ContentFit.CONTAIN)
                picture.set_can_shrink(True)
                picture.set_size_request(104, 68)
                grid.attach(picture, 0, 0, 1, 1)
            for i, names in enumerate(icons_mod.PREVIEW_ICONS):
                if shot is not None and shot.is_file():
                    break
                if theme is not None:
                    paintable = theme.lookup_icon(
                        names[0], list(names[1:]), 32, 1,
                        Gtk.TextDirection.NONE, 0)
                    image = Gtk.Image.new_from_paintable(paintable)
                else:
                    # No preview image either: a single download icon in the middle.
                    image = Gtk.Image()
                    if i == 4:
                        image.set_from_icon_name("folder-download-symbolic")
                    image.add_css_class("dim-label")
                image.set_pixel_size(32)
                grid.attach(image, i % 3, i // 3, 1, 1)
            inner.append(grid)
            caption = Gtk.Label(label=label, xalign=0.5, wrap=True,
                                justify=Gtk.Justification.CENTER)
            caption.set_max_width_chars(16)
            caption.add_css_class("caption")
            inner.append(caption)
            if suggestion is not None:
                pkg = Gtk.Label(label=suggestion.package,
                                xalign=0.5, wrap=True,
                                justify=Gtk.Justification.CENTER)
                pkg.set_max_width_chars(16)
                pkg.add_css_class("caption")
                pkg.add_css_class("dim-label")
                inner.append(pkg)
                if suggestion.aur:
                    mark = aur_mod.badge([suggestion.package])
                    mark.set_halign(Gtk.Align.CENTER)
                    inner.append(mark)

            button = Gtk.ToggleButton(child=inner)
            button.add_css_class("flat")
            button.add_css_class("card")
            if root_button:
                button.set_group(root_button[0])
            else:
                root_button.append(button)
            button.set_active(name.lower() == current.lower())
            button.set_tooltip_text(
                f"{name} — not installed; click to install it in a terminal"
                if suggestion is not None else name)

            def _on_toggled(btn, _name=name, _sug=suggestion) -> None:
                if not btn.get_active():
                    return
                if self.state.get("ICON_THEME_NAME") == _name:
                    return
                self.state.set("ICON_THEME_NAME", _name)
                entry.set_text(_name)
                if _sug is not None:
                    self._install_icon_set(_sug)

            button.connect("toggled", _on_toggled)
            self._icon_buttons[name] = button
            return button

        def flow() -> Gtk.FlowBox:
            return Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
                               homogeneous=True, row_spacing=6,
                               column_spacing=6, min_children_per_line=3,
                               max_children_per_line=8,
                               valign=Gtk.Align.START)

        def heading(text: str) -> Gtk.Label:
            lbl = Gtk.Label(label=text, xalign=0, wrap=True)
            lbl.add_css_class("caption")
            lbl.add_css_class("dim-label")
            return lbl

        box.append(heading(f"Installed ({len(installed)}) — with their real icons"))
        have = flow()
        for name in installed:
            theme = Gtk.IconTheme()
            theme.set_theme_name(name)
            sug = icons_mod.suggestion(name)
            label = sug.label if sug else icons_mod.display_name(name)
            if label.lower() != name.lower():
                label = f"{label}\n{name}"
            have.append(card(name, label, theme, None))
        box.append(have)

        if missing:
            box.append(heading("Suggested — not installed; the icons come from the "
                               "package itself. Selecting one opens the install in a terminal"))
            more = flow()
            for sug in missing:
                more.append(card(sug.name, sug.label, None, sug))
            box.append(more)
        return box

    def _install_icon_set(self, sug: "icons_mod.IconSet") -> None:
        """Installs an icon set that isn't installed, in the user's terminal.

        _install_in_terminal looks at the catalog components' AUR list; icon
        sets aren't in the catalog, so the repo/AUR split is done here.
        """
        repo, aur = ([], [sug.package]) if sug.aur else ([sug.package], [])
        if not self._open_terminal(" && ".join(self._package_commands(repo, aur))):
            return
        self._watch_install([sug.package])
        self._toast(f"Installing {sug.label} in a terminal; the icons change "
                    "by themselves when done")

    # --- color editor -------------------------------------------------------
    COLOUR_LABELS = {
        "BG": ("Background", "Main color wherever the wallpaper isn't visible"),
        "BG_DARK": ("Dark background", "Status bar and shadow color"),
        "SURFACE": ("Surface", "Window body and inactive border"),
        "FG": ("Text", "Main text color"),
        "SUBTEXT": ("Secondary text", "Dim labels, inactive workspaces"),
        "ACCENT": ("Accent 1", "Active border, selection, clock"),
        "ACCENT2": ("Accent 2", "Second color of the border gradient"),
        "RED": ("Red", "Error, critical battery, power button"),
        "GREEN": ("Green", "Success, network connected"),
        "YELLOW": ("Yellow", "Warning, brightness"),
        "CYAN": ("Cyan", "Extra accent"),
    }

    def _colour_editor(self) -> Adw.PreferencesGroup:
        group = Adw.ExpanderRow(
            title="Customize colors",
            subtitle="Change the selected theme's colors one by one — "
                     "changes go into the preview and every generated file")
        for row in self._colour_rows():
            group.add_row(row)
        wrapper = Adw.PreferencesGroup()
        wrapper.add(group)
        return wrapper

    def _colour_rows(self) -> list[Gtk.Widget]:
        """The palette's individual colors + reset. The Appearance page and Mix
        use the same rows; the buttons are kept in a list per key so that
        _sync_colour_buttons syncs both at once."""
        rows: list[Gtk.Widget] = []
        for key in themes.KEYS:
            label, help_text = self.COLOUR_LABELS.get(key, (key, ""))
            row = Adw.ActionRow(title=esc(label), subtitle=esc(help_text))
            button = Gtk.ColorDialogButton(valign=Gtk.Align.CENTER)
            button.set_dialog(Gtk.ColorDialog(with_alpha=False))
            button.connect("notify::rgba", self._on_colour_changed, key)
            self._colour_buttons.setdefault(key, []).append(button)
            row.add_suffix(button)
            rows.append(row)

        reset_row = Adw.ActionRow(
            title="Revert to theme colors",
            subtitle="Deletes all manual color changes")
        reset = Gtk.Button(label="Reset", valign=Gtk.Align.CENTER)
        reset.add_css_class("destructive-action")
        reset.connect("clicked", lambda _b: self._reset_colours())
        reset_row.add_suffix(reset)
        rows.append(reset_row)
        self._sync_colour_buttons()
        return rows

    def _on_colour_changed(self, button, _param, key: str) -> None:
        if getattr(self, "_syncing_colours", False):
            return
        rgba = button.get_rgba()
        hex_value = "{:02x}{:02x}{:02x}".format(
            round(rgba.red * 255), round(rgba.green * 255),
            round(rgba.blue * 255))
        self.state.set_colour(key, hex_value)

    def _sync_colour_buttons(self) -> None:
        """Syncs the color buttons with the active palette (needed when the theme changes)."""
        from gi.repository import Gdk
        palette = self.state.palette()
        self._syncing_colours = True
        try:
            for key, buttons in getattr(self, "_colour_buttons", {}).items():
                rgba = Gdk.RGBA()
                rgba.parse(f"#{palette[key]}")
                for button in buttons:
                    button.set_rgba(rgba)
        finally:
            self._syncing_colours = False

    def _reset_colours(self) -> None:
        self.state.reset_colours()
        self._sync_colour_buttons()
        self._toast("Theme colors reset")

    # --- status bar ---------------------------------------------------------
    def _refresh_bar_settings_note(self) -> None:
        """Rewrites the "applies/no effect" note on the bar setting rows.

        Pages are built once; when the backend changed later the note went stale and
        gave the user wrong information (e.g. after switching from Waybar to Wayle,
        "Height" still looked like it applied).
        """
        active = self._active_bar_backend()
        group = getattr(self, "_bar_settings_group", None)
        rows = getattr(self, "_bar_setting_rows", {})
        if group is None or not rows:
            return
        for setting in group.settings:
            row = rows.get(setting.key)
            if row is None or not hasattr(row, "set_subtitle"):
                continue
            row.set_subtitle(esc(_help_row(setting, active)))

    def _active_bar_backend(self) -> str:
        return active_bar_backend(self.state)

    def _page_bar(self) -> Gtk.Widget:
        """Two columns: settings on the left, bar preview + layout editor on the right.

        See the same pattern in _page_appearance — for the same reason.
        """
        page = Adw.PreferencesPage()          # left: settings
        # The default 600px clamp was too narrow on this page: even with the left
        # pane over 900px, the rows were squeezed into a 600px strip in the middle
        # with empty bands on both sides, and each row's description wrapped to
        # three lines in the narrow column next to the slider.
        self._widen_page(page, 880)
        preview_page = Adw.PreferencesPage()  # right: preview + layout, fixed
        self._widen_page(preview_page, 420)
        preview_page.set_size_request(420, -1)

        preview_group = Adw.PreferencesGroup(
            title="Bar preview",
            description="Modules land in the zone you choose; height, "
                        "gaps, rounding and opacity are drawn at 1:1 "
                        "scale. Every change below shows up instantly.")
        self.bar_preview = BarPreview(get_setting=self.state.get,
                                      get_palette=self.state.palette)
        # Fill the column's width: with the 360px base size fixed, the preview
        # was centered inside its own frame, leaving gaps on both
        # sides.
        self.bar_preview.set_content_width(380)
        self.bar_preview.set_content_height(230)
        self.bar_preview.set_hexpand(True)
        frame = Gtk.Frame()
        frame.set_child(self.bar_preview)
        frame.add_css_class("view")
        frame.set_margin_top(6)
        # A single widget draws both horizontal and vertical bars; when the
        # position changes it's just redrawn (see _refresh_bar_preview_widget).
        self._bar_preview_frame = frame
        preview_group.add(frame)
        preview_page.add(preview_group)

        bar_group = schema.group("bar")
        # The selected backend drops an "applies / no effect" note under each row
        # (see backend_note). Since the page isn't rebuilt when the backend
        # changes, the note is written for the choice at the time the page opened
        # and updated by _refresh_bar_settings_note.
        self._bar_setting_rows: dict[str, Gtk.Widget] = {}
        self._bar_settings_group = bar_group
        # If a profile brought its own bar (waybar, quickshell, eww,
        # skadi…) this page configures THAT: that bar's fields appear at the top,
        # and the project's BAR_* rows are locked since they have no effect then.
        self._rice_bar_group = Adw.PreferencesGroup()
        self._rice_bar_rows: list[Gtk.Widget] = []
        self._rice_bar_pending: dict = {}
        self._rice_bar_timer = 0
        page.add(self._rice_bar_group)
        own_group = group_to_widget(bar_group, self.state, sync=self._sync_rows,
                                    active_backend=self._active_bar_backend(),
                                    rows=self._bar_setting_rows)
        page.add(own_group)
        # The same rows must be findable by search too (the bar page keeps its
        # own dict separately to refresh the "no effect" notes).
        self._setting_rows.update(self._bar_setting_rows)

        # The layout editor sits BELOW the preview, in the right column: which
        # module goes to which zone is read at a glance next to the bar
        # itself. While it was on the left, the right column's whole height
        # after the preview stood empty.
        layout_group = self._bar_layout_group()
        preview_page.add(layout_group)
        custom_group = self._bar_custom_group()
        page.add(custom_group)
        # The dock is independent of the bar backend: it works even if a profile
        # brings its own bar, so it doesn't go into _own_bar_widgets (those are
        # locked while the rice's bar is present).
        page.add(self._group_widget("dock"))
        self._own_bar_widgets = [own_group, custom_group, layout_group,
                                 preview_group]
        self._refresh_rice_bar()

        # The left column now carries full-width rows; the pane leaves the right
        # column only its own size (420px + margins), and the rest goes to the
        # settings (resize_start_child=True).
        return _settings_paned(page, preview_page, 940)

    # --- the profile's own bar (ricebar) ------------------------------------
    _RICE_BAR_REGIONS = {"modules-left": "left", "modules-center": "center",
                         "modules-right": "right"}

    def _refresh_rice_bar(self) -> None:
        """Detects the active setup's bar and redraws its fields.

        Since the install finishes in a terminal, the page is refreshed each time
        it opens (see _on_page_selected).
        """
        group = self._rice_bar_group
        for row in self._rice_bar_rows:
            group.remove(row)
        self._rice_bar_rows = []
        try:
            bar = ricebar_mod.detect(self.root)
        except (OSError, ValueError, KeyError) as exc:
            bar = None
            print(f"hyprsetup: could not detect bar: {exc}", file=sys.stderr)
        self._rice_bar = bar
        for widget in self._own_bar_widgets:
            widget.set_sensitive(bar is None)
        group.set_visible(bar is not None)
        if bar is None:
            return
        group.set_title(esc(f"Active bar: {bar.label}"))
        brought = (f"The mix's bar comes from the '{bar.profile}' setup"
                   if bar.source == "mix"
                   else f"The '{bar.profile}' setup brought its own bar")
        group.set_description(esc(
            f"{brought}; the project settings below don't apply to it. Changes "
            "here are written to the author's file, saved for this setup "
            "and re-applied when you reinstall it."))

        def add(row: Gtk.Widget) -> None:
            group.add(row)
            self._rice_bar_rows.append(row)

        if not bar.fields:
            add(Adw.ActionRow(title="This bar has no adjustable fields",
                              subtitle=esc(bar.note or "The author keeps the bar's "
                                           "settings in their own files."),
                              subtitle_lines=0))
            return
        if bar.config is None or not bar.config.is_file():
            add(Adw.ActionRow(
                title="The bar's settings file doesn't exist yet",
                subtitle=esc(f"{bar.config} — the bar creates it on first launch; "
                             "reopen this page after it has started."),
                subtitle_lines=0))
            return
        try:
            values = ricebar_mod.read(bar)
        except (OSError, ValueError) as exc:
            add(Adw.ActionRow(title="Could not read bar settings",
                              subtitle=esc(str(exc)), subtitle_lines=0))
            return
        for field in bar.fields:
            row = self._rice_bar_row(field, values.get(field.key))
            if row is not None:
                add(row)
        reset = Adw.ActionRow(title="Back to the author's values",
                              subtitle="Reverts what you changed on this page.")
        button = Gtk.Button(label="Revert", valign=Gtk.Align.CENTER)
        button.connect("clicked", lambda _b: self._on_rice_bar_reset())
        reset.add_suffix(button)
        add(reset)
        if bar.note:
            add(Adw.ActionRow(title="Note", subtitle=esc(bar.note), subtitle_lines=0))

    def _rice_bar_row(self, field, value) -> Gtk.Widget | None:
        title = esc(field.title)
        subtitle = esc(field.subtitle)
        if field.type == "choice":
            choices = list(field.choices)
            if value not in (None, "") and str(value) not in choices:
                choices.append(str(value))
            row = Adw.ComboRow(title=title, subtitle=subtitle)
            row.set_use_markup(True)
            row.set_model(Gtk.StringList.new(choices))
            if str(value) in choices:
                row.set_selected(choices.index(str(value)))
            row.connect("notify::selected", lambda r, _p: self._rice_bar_set(
                field.key, choices[r.get_selected()]))
            return row
        if field.type == "int":
            try:
                current = int(value)
            except (TypeError, ValueError):
                current = field.minimum
            row = Adw.SpinRow.new_with_range(field.minimum, field.maximum, 1)
            row.set_title(title)
            row.set_subtitle(" · ".join(x for x in (field.unit, subtitle) if x))
            row.set_value(current)
            row.connect("notify::value", lambda r, _p: self._rice_bar_set(
                field.key, int(r.get_value()), delay=400))
            return no_scroll_change(row)
        if field.type == "bool":
            row = Adw.SwitchRow(title=title, subtitle=subtitle)
            row.set_active(bool(value))
            row.connect("notify::active", lambda r, _p: self._rice_bar_set(
                field.key, r.get_active()))
            return row
        if field.type == "text":
            row = Adw.EntryRow(title=title, show_apply_button=True)
            if subtitle:
                row.set_tooltip_text(field.subtitle)
            row.set_text("" if value is None else str(value))
            row.connect("apply", lambda r: self._rice_bar_set(
                field.key, r.get_text().strip()))
            return row
        if field.type == "modules" and isinstance(value, dict):
            hidden = set(value.get("hidden", []))
            modules = [(m, self._RICE_BAR_REGIONS.get(region, region))
                       for region, names in value.get("all", {}).items()
                       for m in names]
            row = Adw.ExpanderRow(
                title=title,
                subtitle=f"{len(modules) - len(hidden)} / {len(modules)} visible")
            switches: dict[str, Adw.SwitchRow] = {}

            def toggled(*_args) -> None:
                gone = [m for m, sw in switches.items() if not sw.get_active()]
                row.set_subtitle(f"{len(switches) - len(gone)} / "
                                 f"{len(switches)} visible")
                self._rice_bar_set("modules", {"hidden": gone})

            for name, region in modules:
                if name in switches:
                    continue
                switch = Adw.SwitchRow(title=esc(name), subtitle=region)
                switch.set_active(name not in hidden)
                switch.connect("notify::active", toggled)
                switches[name] = switch
                row.add_row(switch)
            return row
        return None

    def _rice_bar_set(self, key: str, value, delay: int = 0) -> None:
        """Collects the change; writes it with a short delay so the bar isn't
        reloaded on every spinner click."""
        self._rice_bar_pending[key] = value
        if self._rice_bar_timer:
            GLib.source_remove(self._rice_bar_timer)
        self._rice_bar_timer = GLib.timeout_add(max(delay, 50),
                                                self._flush_rice_bar)

    def _flush_rice_bar(self) -> bool:
        self._rice_bar_timer = 0
        changes, self._rice_bar_pending = self._rice_bar_pending, {}
        bar = self._rice_bar
        if bar is None or not changes:
            return False
        try:
            ricebar_mod.write(bar, changes)
        except (OSError, ValueError) as exc:
            self._toast(f"Could not write bar setting: {exc}")
        return False

    def _on_rice_bar_reset(self) -> None:
        bar = self._rice_bar
        if bar is None:
            return
        try:
            ricebar_mod.reset(bar)
        except (OSError, ValueError) as exc:
            self._toast(f"Could not revert: {exc}")
            return
        self._refresh_rice_bar()
        self._toast("Bar returned to the author's values")

    # --- bar layout: an ordered chip list per zone --------------------------
    #
    # The previous editor was a dropdown per module (Off/Left/Center/
    # Right) — 30 rows, and although BAR_MODULES_* is an ordered list the
    # ORDER couldn't be edited at all. Here the three zones are three rows; each
    # zone shows its own modules as chips in order, order and removal are done
    # from the chip, adding from the "+" button.
    _ZONE_LABELS = (("LEFT", "LEFT"), ("CENTER", "CENTER"), ("RIGHT", "RIGHT"))

    def _bar_layout_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(
            title="Layout",
            description="The modules in each zone are listed in their left-to-right "
                        "drawing order. Click a chip to move or "
                        "remove it; add a new module with '+'.")
        self._zone_boxes: dict[str, Gtk.FlowBox] = {}
        for zone, label in self._ZONE_LABELS:
            # Adw.ActionRow is NOT used: its suffix area squeezed the chips into a
            # narrow column and the FlowBox shrank to one chip per row (they all
            # stacked up). We build our own row with the title + "+" on top and
            # the chips below at full width.
            row = Adw.PreferencesRow(activatable=False)
            outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            outer.set_margin_top(10)
            outer.set_margin_bottom(10)
            outer.set_margin_start(12)
            outer.set_margin_end(12)

            head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            name = Gtk.Label(label=label, xalign=0, hexpand=True)
            name.add_css_class("caption-heading")
            name.add_css_class("dim-label")
            head.append(name)
            add = Gtk.MenuButton(icon_name="list-add-symbolic",
                                 valign=Gtk.Align.CENTER,
                                 tooltip_text="Add a module to this zone")
            add.add_css_class("flat")
            add.set_popover(self._module_add_popover(zone))
            head.append(add)
            outer.append(head)

            # Adw.WrapBox (libadwaita 1.7+) is the right tool for chips: Gtk.FlowBox
            # makes ALL columns in a row as wide as the widest child, so "Audio"
            # and "System tray" were drawn at the same width and only two chips fit
            # per row. WrapBox leaves each chip at its natural width and wraps
            # at the end of the line.
            flow = Adw.WrapBox(child_spacing=6, line_spacing=6,
                               halign=Gtk.Align.START)
            self._zone_boxes[zone] = flow
            outer.append(flow)

            row.set_child(outer)
            group.add(row)
        self._refresh_zone_chips()
        return group

    def _bar_custom_group(self) -> Adw.PreferencesGroup:
        """Three slots where users put their own command on the bar.

        There are four settings per slot (command, format, interval, click);
        listing twelve rows flat made the page unreadable. Each slot sits in
        its own expander row whose title shows the command itself —
        even collapsed, you can see which slot is filled.
        """
        group = Adw.PreferencesGroup(
            title="Custom modules",
            description="Shows your own command's output on the bar. "
                        "A slot with a command can be added to the list in "
                        "the Layout section as \"Custom module\". "
                        "Only applies to Waybar.")
        custom = self._custom_group()
        if custom.advanced:
            group.add_css_class(ADVANCED_CSS)
        settings = {s.key: s for s in custom.settings}
        self._bar_custom_rows: dict[int, Adw.ExpanderRow] = {}

        for slot in render_mod.BAR_CUSTOM_SLOTS:
            expander = Adw.ExpanderRow(title=f"Slot {slot}")
            self._bar_custom_rows[slot] = expander
            for suffix in ("CMD", "FORMAT", "INTERVAL", "CLICK"):
                setting = settings[f"BAR_CUSTOM{slot}_{suffix}"]
                row = build_setting_row(setting, self.state,
                                        sync=self._sync_rows)
                # The slot title should show the command: "Slot 2" in a collapsed row
                # didn't say which one was filled.
                expander.add_row(row)
            group.add(expander)
        self._refresh_custom_titles()
        return group

    @staticmethod
    def _custom_group() -> schema.Group:
        return schema.group("bar_custom")

    def _refresh_custom_title(self, slot: int) -> None:
        row = getattr(self, "_bar_custom_rows", {}).get(slot)
        if row is None:
            return
        cmd = (self.state.get(f"BAR_CUSTOM{slot}_CMD") or "").strip()
        row.set_subtitle(esc(cmd) if cmd else "empty — no command entered")

    def _refresh_custom_titles(self) -> None:
        for slot in render_mod.BAR_CUSTOM_SLOTS:
            self._refresh_custom_title(slot)

    def _module_add_popover(self, zone: str) -> Gtk.Popover:
        """Module list opened by the '+' button.

        Modules the selected backend can't draw aren't hidden; they're shown with a
        "not supported" note, so the user can see what will be lost when moving a
        profile/preset to another backend.
        """
        popover = Gtk.Popover()
        scroller = Gtk.ScrolledWindow(propagate_natural_height=True,
                                      max_content_height=420, hexpand=False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_top(6); box.set_margin_bottom(6)
        box.set_margin_start(6); box.set_margin_end(6)
        scroller.set_child(box)
        popover.set_child(scroller)
        popover.connect("show", lambda _p: self._fill_module_popover(box, zone,
                                                                     popover))
        return popover

    def _fill_module_popover(self, box: Gtk.Box, zone: str,
                             popover: Gtk.Popover) -> None:
        child = box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            box.remove(child)
            child = nxt

        backend = self._active_bar_backend()
        supported = _backend_modules(backend)
        placed = set(self.state.zone_modules("LEFT")) | \
            set(self.state.zone_modules("CENTER")) | \
            set(self.state.zone_modules("RIGHT"))

        for module, (label, requires) in render_mod.BAR_MODULES.items():
            if module in placed:
                continue
            btn = Gtk.Button(halign=Gtk.Align.FILL)
            btn.add_css_class("flat")
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            title = Gtk.Label(label=label, xalign=0)
            inner.append(title)
            notes = []
            # An empty custom slot can be added to the bar but draws nothing
            # (render.py filters it out of the list); we say why here.
            if module.startswith("custom/user"):
                slot = module[len("custom/user"):]
                cmd = (self.state.get(f"BAR_CUSTOM{slot}_CMD") or "").strip()
                notes.append(cmd if cmd else
                             "no command entered — write one in the Custom modules section")
            if requires:
                comp = self.catalog.component(requires)
                notes.append(f"requires {comp.title if comp else requires}")
            if backend and module not in supported:
                notes.append(f"not supported by {_BACKEND_LABEL.get(backend, backend)}")
            if notes:
                sub = Gtk.Label(label=" · ".join(notes), xalign=0)
                sub.add_css_class("caption")
                sub.add_css_class("dim-label")
                inner.append(sub)
            btn.set_child(inner)
            btn.connect("clicked", self._on_module_added, zone, module, popover)
            box.append(btn)

        if box.get_first_child() is None:
            empty = Gtk.Label(label="No modules left to add")
            empty.add_css_class("dim-label")
            box.append(empty)

    def _zone_chip(self, zone: str, module: str, index: int,
                   count: int) -> Gtk.Widget:
        label, _requires = render_mod.BAR_MODULES[module]
        backend = self._active_bar_backend()
        unsupported = bool(backend) and module not in _backend_modules(backend)

        chip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        chip.add_css_class("linked")
        chip.add_css_class("hs-chip")
        if unsupported:
            chip.add_css_class("hs-chip-unsupported")

        menu = Gtk.MenuButton(label=label if not unsupported else f"{label} ⚠")
        menu.add_css_class("pill")
        if unsupported:
            menu.set_tooltip_text(
                f"{_BACKEND_LABEL.get(backend, backend)} doesn't draw this module — "
                f"it's removed from the generated configuration.")
            menu.add_css_class("warning")
        pop = Gtk.Popover()
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        inner.set_margin_top(6); inner.set_margin_bottom(6)
        inner.set_margin_start(6); inner.set_margin_end(6)
        for text, delta in (("◀  Move left", -1), ("Move right  ▶", 1)):
            b = Gtk.Button(label=text, halign=Gtk.Align.FILL)
            b.add_css_class("flat")
            b.set_sensitive(0 <= index + delta < count)
            b.connect("clicked", self._on_module_moved, zone, module, delta, pop)
            inner.append(b)
        pop.set_child(inner)
        menu.set_popover(pop)
        chip.append(menu)

        close = Gtk.Button(icon_name="window-close-symbolic",
                           tooltip_text="Remove this module from the bar")
        close.add_css_class("pill")
        close.add_css_class("hs-chip-close")
        close.connect("clicked", self._on_module_removed, module)
        chip.append(close)
        return chip

    def _refresh_zone_chips(self) -> None:
        for zone, _label in self._ZONE_LABELS:
            flow = getattr(self, "_zone_boxes", {}).get(zone)
            if flow is None:
                continue
            child = flow.get_first_child()
            while child:
                nxt = child.get_next_sibling()
                flow.remove(child)
                child = nxt
            modules = [m for m in self.state.zone_modules(zone)
                       if m in render_mod.BAR_MODULES]
            for index, module in enumerate(modules):
                flow.append(self._zone_chip(zone, module, index, len(modules)))
            if not modules:
                empty = Gtk.Label(label="empty")
                empty.add_css_class("dim-label")
                empty.add_css_class("caption")
                flow.append(empty)

    def _on_module_added(self, _btn, zone: str, module: str,
                         popover: Gtk.Popover) -> None:
        popover.popdown()
        label, requires = render_mod.BAR_MODULES[module]

        def done() -> None:
            self.state.add_module(zone, module)
            self._refresh_zone_chips()

        self._require([requires] if requires else [], label, done)

    def _on_module_removed(self, _btn, module: str) -> None:
        self.state.remove_module(module)
        self._refresh_zone_chips()

    def _on_module_moved(self, _btn, zone: str, module: str, delta: int,
                         popover: Gtk.Popover) -> None:
        popover.popdown()
        self.state.move_module(zone, module, delta)
        self._refresh_zone_chips()

    def _on_theme_toggled(self, button, name: str) -> None:
        if not button.get_active():
            return
        # When the theme changes, manual color edits lose their meaning
        self.state.set("CUSTOM_COLORS", "")
        self.state.set("THEME", name)
        self._sync_colour_buttons()
        self._update_theme_label()

    def _update_theme_label(self) -> None:
        label = getattr(self, "_theme_current_label", None)
        if label is None:
            return
        name = self.state.get("THEME")
        label.set_label("Selected: " + ("from wallpaper" if name == "auto"
                                      else name or "—"))

    def _on_colorscheme_toggled(self, button, value: str) -> None:
        if not button.get_active():
            return
        self.state.set("COLOR_SCHEME", value)

    # --- behavior -----------------------------------------------------------
    def _page_behavior(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()
        # There are diagrams next to the rows; the default 600px reading width
        # isn't enough for both.
        self._widen_page(page, 940)
        beside = {
            "input": (MouseInputDiagram, "input_diagram", 320,
                      "Shows how sensitivity, acceleration and natural scrolling "
                      "will feel."),
            "behavior": (behavior_diagrams.WindowBehaviorDiagram,
                         "behavior_diagram", 330,
                         "The floating window is drawn with its edge snapping distance "
                         "and the picture-in-picture width; the labels "
                         "below show the state of the switches."),
            "switcher": (behavior_diagrams.SwitcherDiagram,
                         "switcher_diagram", 330,
                         "The picker that opens on ALT+Tab. Scope and "
                         "sorting really filter the sample window list."),
            "groups": (behavior_diagrams.GroupbarDiagram, "groupbar_diagram",
                       330, "The tab bar of a grouped window."),
            "gestures": (behavior_diagrams.GestureDiagram, "gesture_diagram",
                         330, "Switching workspaces by swiping on the "
                              "touchpad."),
            "plugins": (behavior_diagrams.PluginsDiagram, "plugins_diagram",
                        330, "The overview grid and the window title bar."),
        }
        for group_id in PAGE_GROUPS["behavior"]:
            widget = self._group_widget(group_id)
            if group_id in beside:
                diagram_cls, attr, width, note = beside[group_id]
                page.add(self._group_beside_diagram(widget, diagram_cls, attr,
                                                    note, width))
            else:
                page.add(widget)
        return page

    # --- mouse cursor --------------------------------------------------------
    def _page_cursor(self) -> Gtk.Widget:
        """Cursor theme (with real images) and size/hide settings.

        The theme picker used to be on the Appearance page below the font, and size
        and hiding were on Behavior; anyone looking for the cursor found them in two places.
        """
        page = Adw.PreferencesPage()
        self._widen_page(page, 940)

        group = Adw.PreferencesGroup(
            title="Cursor theme",
            description="GTK, Qt, XWayland and Hyprland use the same theme. "
                        "Themes shipped with the repo (e.g. Gozcu's Gozcu-Cursors) "
                        "are installed automatically when applied.")
        cursor_row = Adw.EntryRow(title="Cursor theme")
        cursor_row.set_text(self.state.get("CURSOR_THEME"))
        cursor_row.connect(
            "changed", lambda r: self.state.set("CURSOR_THEME", r.get_text()))
        group.add(cursor_row)
        group.add(self._cursor_quick_group(cursor_row))

        def _sync_cursor() -> None:
            current = self.state.get("CURSOR_THEME")
            if cursor_row.get_text() != current:
                cursor_row.set_text(current)
            for name, btn in self._cursor_buttons.items():
                active = name.lower() == current.lower()
                if btn.get_active() != active:
                    btn.set_active(active)

        self._sync_rows["CURSOR_THEME"] = _sync_cursor
        page.add(group)

        for group_id in PAGE_GROUPS["cursor"]:
            page.add(self._group_beside_diagram(
                self._group_widget(group_id), CursorSizeDiagram,
                "cursor_diagram",
                "The real look of the selected theme and size — if the theme isn't "
                "installed on this system, a placeholder arrow is drawn.", 320))
        return page

    # --- setting + diagram pairing --------------------------------------------
    def _group_beside_diagram(self, group_widget: Adw.PreferencesGroup,
                              diagram_cls, attr: str,
                              note: str = "",
                              width: int = 290) -> Adw.PreferencesGroup:
        """Puts a settings group SIDE BY SIDE with the diagram that explains it.

        The diagrams used to sit above the group as a separate full-width box:
        which diagram explained which settings could only be told by reading
        the title, and in long groups it scrolled off screen after the first
        row. Side by side, a setting and its counterpart stay at the same height
        and move together while scrolling.

        The returned wrapper has no title — the title/description stay inside the
        group itself, and the diagram starts to their right.
        """
        wrapper = Adw.PreferencesGroup()
        # An advanced group's diagram must be hidden with the group in simple mode too.
        if group_widget.has_css_class(ADVANCED_CSS):
            wrapper.add_css_class(ADVANCED_CSS)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        group_widget.set_hexpand(True)
        box.append(group_widget)

        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        column.set_size_request(width, -1)
        column.set_valign(Gtk.Align.START)
        # It starts lower by the height of the group's title row, so the diagram
        # lines up with the first setting row, not with the title.
        column.set_margin_top(30)

        diagram = diagram_cls(get_setting=self.state.get,
                              get_palette=self.state.palette)
        setattr(self, attr, diagram)
        frame = Gtk.Frame()
        frame.set_child(diagram)
        frame.add_css_class("view")
        column.append(frame)
        if note:
            label = Gtk.Label(label=note, xalign=0, wrap=True)
            label.add_css_class("caption")
            label.add_css_class("dim-label")
            column.append(label)

        box.append(column)
        wrapper.add(box)
        return wrapper

    # ------------------------------------------------ autostart -
    def _page_autostart(self) -> Gtk.Widget:
        """Apps that start when the session starts (EXTRA_EXEC_ONCE).

        They're picked from installed apps (.desktop) or the command is typed by hand.
        The lines run in autostart.conf (lua: autostart.lua) AFTER the project's own
        components; they're kept when the profile changes.
        """
        page = Adw.PreferencesPage()
        self._widen_page(page, 900)

        def commandline(app: Gio.AppInfo) -> str:
            # Field codes (%U, %f…) are meaningless at startup: no file/URL is passed.
            return re.sub(r"\s*%[a-zA-Z]", "", app.get_commandline() or "").strip()

        apps = sorted((a for a in Gio.AppInfo.get_all()
                       if a.should_show() and commandline(a)
                       and not (a.get_id() or "").startswith("souprland-")),
                      key=lambda a: (a.get_display_name() or "").casefold())
        by_command = {commandline(a): a for a in apps}

        current = Adw.PreferencesGroup(
            title="Autostart",
            description="Started in order when the session starts. You can choose "
                        "which workspace an app opens on from the Window Rules "
                        "page.")
        page.add(current)
        rows: list[Gtk.Widget] = []

        def entries() -> list[str]:
            return [c.strip() for c in self.state.get("EXTRA_EXEC_ONCE").split(";;")
                    if c.strip()]

        def store(commands: list[str]) -> None:
            self.state.set("EXTRA_EXEC_ONCE", ";;".join(commands))
            redraw()

        def redraw() -> None:
            for row in rows:
                current.remove(row)
            rows.clear()
            commands = entries()
            if not commands:
                row = Adw.ActionRow(title="Nothing added yet")
                current.add(row)
                rows.append(row)
            for index, command in enumerate(commands):
                app = by_command.get(command)
                row = Adw.ActionRow(title=esc(app.get_display_name() if app else command),
                                    subtitle=esc(command) if app else "")
                icon = app.get_icon() if app else None
                image = (Gtk.Image.new_from_gicon(icon) if icon
                         else Gtk.Image.new_from_icon_name("system-run-symbolic"))
                image.set_pixel_size(28)
                row.add_prefix(image)
                remove = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER,
                                    tooltip_text="Remove from autostart")
                remove.add_css_class("flat")
                remove.connect("clicked", lambda _b, i=index: store(
                    [c for n, c in enumerate(entries()) if n != i]))
                row.add_suffix(remove)
                current.add(row)
                rows.append(row)

        def add(command: str, name: str) -> None:
            commands = entries()
            if command in commands:
                self._toast(f"{name} is already in the list.")
                return
            store(commands + [command])
            self._toast(f"{name} will start at login.")

        custom = Adw.EntryRow(title="Command by hand (e.g. discord --start-minimized)",
                              show_apply_button=True)

        def custom_apply(row) -> None:
            text = row.get_text().strip()
            if text:
                add(text, text.split()[0])
                row.set_text("")
        custom.connect("apply", custom_apply)

        picker = Adw.PreferencesGroup(title="Add application")
        search = Gtk.SearchEntry(placeholder_text="Search applications…", margin_bottom=8)
        picker.add(search)
        picker.add(custom)
        listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        listing.add_css_class("boxed-list")
        listing.set_margin_top(8)
        for app in apps:
            row = Adw.ActionRow(title=esc(app.get_display_name() or ""),
                                subtitle=esc(app.get_description() or ""))
            row.set_subtitle_lines(1)
            icon = app.get_icon()
            image = (Gtk.Image.new_from_gicon(icon) if icon
                     else Gtk.Image.new_from_icon_name("application-x-executable"))
            image.set_pixel_size(28)
            row.add_prefix(image)
            button = Gtk.Button(icon_name="list-add-symbolic", valign=Gtk.Align.CENTER,
                                tooltip_text="Add to autostart")
            button.add_css_class("flat")
            button.connect("clicked", lambda _b, a=app: add(commandline(a),
                                                             a.get_display_name()))
            row.add_suffix(button)
            row.hs_text = fold(f"{app.get_display_name()} {app.get_id()} "
                               f"{app.get_description() or ''}")
            listing.append(row)
        listing.set_filter_func(
            lambda row: fold(search.get_text()) in getattr(row, "hs_text", ""))
        search.connect("search-changed", lambda _e: listing.invalidate_filter())
        picker.add(listing)
        page.add(picker)
        redraw()
        return page

    # --------------------------------------------------- window rules -
    def _page_rules(self) -> Gtk.Widget:
        """Window rule wizard: pick an open window, tick the behavior.

        "App → workspace" (Discord always on 3) is also set up here.
        Rules are written to USER_WINDOWRULES; they're kept when the profile changes
        and, since they come after the profile's rules, they override them.
        """
        from .. import winrules

        page = Adw.PreferencesPage()
        self._widen_page(page, 900)

        def clients() -> list[tuple[str, str]]:
            try:
                data = json.loads(subprocess.run(["hyprctl", "clients", "-j"],
                                                 capture_output=True, text=True,
                                                 timeout=3).stdout or "[]")
            except (OSError, ValueError, subprocess.TimeoutExpired):
                return []
            seen: dict[str, str] = {}
            for client in data:
                cls = client.get("class") or client.get("initialClass") or ""
                if cls and cls not in seen:
                    seen[cls] = client.get("title") or ""
            return sorted(seen.items(), key=lambda item: item[0].casefold())

        try:
            monitors = [m["name"] for m in json.loads(
                subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True,
                               text=True, timeout=3).stdout or "[]")]
        except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
            monitors = []

        new = Adw.PreferencesGroup(
            title="New rule",
            description="Pick an open window (or type its class) and tick how it "
                        "should open. Example: Discord always on workspace 3, "
                        "opening in the background.")
        windows = clients()
        pick = Adw.ComboRow(title="Open window")
        pick.set_model(Gtk.StringList.new(
            ["Type manually"] + [f"{cls} — {title[:40]}" for cls, title in windows]))
        new.add(pick)
        class_row = Adw.EntryRow(title="Window class (hyprctl clients → class)")
        new.add(class_row)
        title_row = Adw.EntryRow(title="Also match the title (optional)")
        new.add(title_row)

        def picked(row, _param) -> None:
            index = row.get_selected()
            if 0 < index <= len(windows):
                class_row.set_text(windows[index - 1][0])
        pick.connect("notify::selected", picked)

        switches: dict[str, Adw.SwitchRow] = {}
        for key, label in winrules.TOGGLES:
            switches[key] = Adw.SwitchRow(title=label)
            new.add(switches[key])
        workspace = no_scroll_change(Adw.SpinRow.new_with_range(0, 10, 1))
        workspace.set_title("Workspace")
        workspace.set_subtitle("0 = any")
        new.add(workspace)
        silent = Adw.SwitchRow(title="Open in the background",
                               subtitle="Opens without switching to that workspace")
        new.add(silent)
        monitor = Adw.ComboRow(title="Display")
        monitor.set_model(Gtk.StringList.new(["Any", *monitors]))
        new.add(monitor)
        size_row = Adw.EntryRow(title="Size (e.g. 1200x800, when floating)")
        new.add(size_row)
        opacity = no_scroll_change(Adw.SpinRow.new_with_range(30, 100, 5))
        opacity.set_title("Opacity (%)")
        opacity.set_value(100)
        new.add(opacity)
        add = Gtk.Button(label="Add rule", halign=Gtk.Align.END, margin_top=12)
        add.add_css_class("suggested-action")
        new.add(add)
        page.add(new)

        mine = Adw.PreferencesGroup(title="My rules")
        page.add(mine)
        rows: list[Gtk.Widget] = []

        def redraw() -> None:
            for row in rows:
                mine.remove(row)
            rows.clear()
            rules = winrules.parse(self.state.get("USER_WINDOWRULES"))
            if not rules:
                row = Adw.ActionRow(title="No rules yet")
                mine.add(row)
                rows.append(row)
            for index, rule in enumerate(rules):
                row = Adw.ActionRow(title=esc(rule.describe()),
                                    subtitle=esc(winrules.label_for(rule)
                                                 if rule.match_class else "typed manually"))
                remove = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER,
                                    tooltip_text="Delete rule")
                remove.add_css_class("flat")
                remove.connect("clicked", lambda _b, i=index: delete(i))
                row.add_suffix(remove)
                mine.add(row)
                rows.append(row)

        def delete(index: int) -> None:
            rules = winrules.parse(self.state.get("USER_WINDOWRULES"))
            if 0 <= index < len(rules):
                del rules[index]
                self.state.set("USER_WINDOWRULES", winrules.dump(rules))
                redraw()

        def on_add(_b) -> None:
            cls = class_row.get_text().strip()
            if not cls:
                self._toast("First pick a window or type its class.")
                return
            match_class = cls if cls.startswith("^") else winrules.exact(cls)
            title = title_row.get_text().strip()
            match_title = (title if title.startswith("^") or not title
                           else f".*{winrules.exact(title)[2:-2]}.*")
            size = None
            found = re.fullmatch(r"\s*(\d+)\s*[x×*]\s*(\d+)\s*", size_row.get_text())
            if found:
                size = (int(found.group(1)), int(found.group(2)))
            index = monitor.get_selected()
            new_rules = winrules.build(
                match_class, match_title,
                toggles={k for k, sw in switches.items() if sw.get_active()},
                workspace=int(workspace.get_value()), silent=silent.get_active(),
                monitor=monitors[index - 1] if 0 < index <= len(monitors) else "",
                size=size, opacity=opacity.get_value() / 100)
            if not new_rules:
                self._toast("No behavior selected.")
                return
            rules = winrules.parse(self.state.get("USER_WINDOWRULES"))
            bodies = {r.body() for r in rules}
            rules += [r for r in new_rules if r.body() not in bodies]
            self.state.set("USER_WINDOWRULES", winrules.dump(rules))
            redraw()
            self._toast(f"{len(new_rules)} rules added: {cls}. They apply to newly "
                        "opened windows.")
            for sw in switches.values():
                sw.set_active(False)
            workspace.set_value(0)
            silent.set_active(False)
            monitor.set_selected(0)
            size_row.set_text("")
            opacity.set_value(100)
        add.connect("clicked", on_add)
        redraw()
        return page

    # --------------------------------------------------- Wallpaper Engine -
    def _page_wpengine(self) -> Gtk.Widget:
        """Installed Workshop wallpapers: gallery with previews, choice per display.

        Clicking a card writes the choice to the setting (WPENGINE_ID, or
        WPENGINE_PER_SCREEN if a target display is selected) and, like any setting change, it's
        applied instantly: wallpaperengine.sh is regenerated and the scene restarts.
        """
        from .. import wpengine

        page = Adw.PreferencesPage()
        self._widen_page(page, 1100)

        status = Adw.PreferencesGroup(
            title="Wallpaper Engine",
            description="Wallpaper Engine's Workshop wallpapers from Steam are played "
                        "on the desktop with linux-wallpaperengine. For a new "
                        "wallpaper, subscribe via Steam → Wallpaper Engine → Workshop, "
                        "then press Refresh.")
        use_row = Adw.ActionRow(title="Wallpaper Engine isn't the wallpaper program",
                                subtitle="Only then does the chosen scene play.")
        use_row.add_prefix(Gtk.Image.new_from_icon_name("dialog-warning-symbolic"))
        use = Gtk.Button(label="Use", valign=Gtk.Align.CENTER)
        use.add_css_class("suggested-action")
        use.connect("clicked", lambda _b: self._require_component(
            "wallpaperengine", lambda: self.state.toggle("wallpaperengine", True)))
        use_row.add_suffix(use)
        status.add(use_row)

        try:
            monitors = [m["name"] for m in json.loads(
                subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True,
                               text=True, timeout=3).stdout or "[]")]
        except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
            monitors = []
        target = Adw.ComboRow(title="Target display",
                              subtitle="The display a clicked card's scene goes to")
        target.set_model(Gtk.StringList.new(["All displays", *monitors]))
        status.add(target)
        page.add(status)

        gallery = Adw.PreferencesGroup(title="Wallpapers")
        refresh = Gtk.Button(icon_name="view-refresh-symbolic", valign=Gtk.Align.CENTER,
                             tooltip_text="Refresh")
        refresh.add_css_class("flat")
        gallery.set_header_suffix(refresh)
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                           max_children_per_line=5, min_children_per_line=2,
                           column_spacing=12, row_spacing=12)
        gallery.add(flow)
        page.add(gallery)

        play = schema.Group("wpengine_play", "Playback", "", "", [
            s for s in schema.group("wallpaper").settings
            if s.key in ("WPENGINE_SCALING", "WPENGINE_FPS", "WPENGINE_SILENT")])
        page.add(group_to_widget(play, self.state, sync=self._sync_rows))

        cards: dict[str, tuple[Gtk.Widget, Gtk.Label]] = {}
        kinds = {"scene": "Scene", "video": "Video", "web": "Web"}

        def screen() -> str:
            index = target.get_selected()
            return monitors[index - 1] if 0 < index <= len(monitors) else ""

        def refresh_marks() -> None:
            use_row.set_visible(not self.state.is_selected("wallpaperengine"))
            main = self.state.get("WPENGINE_ID")
            per = wpengine.parse_per_screen(self.state.get("WPENGINE_PER_SCREEN"))
            for ident, (card, badge) in cards.items():
                where = [name for name in monitors if per.get(name, main) == ident]
                if not monitors and ident == main:
                    where = ["selected"]
                badge.set_label(" · ".join(where))
                badge.set_visible(bool(where))
                if where:
                    card.add_css_class("hs-wp-on")
                else:
                    card.remove_css_class("hs-wp-on")

        def choose(ident: str, title: str) -> None:
            name = screen()
            if name:
                per = wpengine.parse_per_screen(self.state.get("WPENGINE_PER_SCREEN"))
                per[name] = ident
                if not self.state.get("WPENGINE_ID"):
                    self.state.set("WPENGINE_ID", ident)
                self.state.set("WPENGINE_PER_SCREEN", wpengine.format_per_screen(per))
            else:
                self.state.set("WPENGINE_PER_SCREEN", "")
                self.state.set("WPENGINE_ID", ident)
            refresh_marks()
            self._toast(f"{title}" + (f" → {name}" if name else ""))

        def thumbnail(picture: Gtk.Picture, path) -> bool:
            try:
                pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), 320, 180, True)
                picture.set_paintable(Gdk.Texture.new_for_pixbuf(pix))
            except GLib.Error:
                pass
            return False

        def fill() -> None:
            child = flow.get_first_child()
            while child:
                flow.remove(child)
                child = flow.get_first_child()
            cards.clear()
            found = wpengine.items()
            if not found:
                empty = Gtk.Label(label="No installed Workshop wallpapers found.",
                                  margin_top=12, margin_bottom=12)
                empty.add_css_class("dim-label")
                flow.append(empty)
            for item in found:
                card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                card.add_css_class("card")
                card.add_css_class("hs-wp-card")
                picture = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True,
                                      height_request=110, width_request=190)
                picture.add_css_class("hs-wp-thumb")
                card.append(picture)
                if item.preview:
                    GLib.idle_add(thumbnail, picture, item.preview)
                title = Gtk.Label(label=item.title, xalign=0, ellipsize=Pango.EllipsizeMode.END,
                                  max_width_chars=1, hexpand=True, margin_start=8,
                                  margin_end=8)
                title.set_tooltip_text(f"{item.title}\n{item.ident}")
                card.append(title)
                info = kinds.get(item.kind, item.kind or "?")
                if item.edited:
                    info += " · edited copy"
                meta = Gtk.Label(label=info, xalign=0, margin_start=8, margin_end=8)
                meta.add_css_class("dim-label")
                meta.add_css_class("caption")
                card.append(meta)
                badge = Gtk.Label(xalign=0, margin_start=8, margin_end=8, margin_bottom=8,
                                  visible=False)
                badge.add_css_class("accent")
                badge.add_css_class("caption-heading")
                card.append(badge)
                click = Gtk.GestureClick()
                click.connect("released", lambda *_a, i=item.ident, t=item.title: choose(i, t))
                card.add_controller(click)
                card.set_cursor_from_name("pointer")
                flow.append(card)
                cards[item.ident] = (card, badge)
            refresh_marks()

        refresh.connect("clicked", lambda _b: fill())
        self.state.connect(lambda: GLib.idle_add(lambda: (refresh_marks(), False)[1]))
        fill()
        return page

    @staticmethod
    def _widen_page(page: Adw.PreferencesPage, maximum: int) -> None:
        """Widens the inner Adw.Clamp of an Adw.PreferencesPage.

        The default 600px is the right size for a single column of settings; on
        pages with diagrams next to the rows, the two shared the same 600px and
        both became unreadable. There's no public API for it; the inner Clamp is
        found by walking the tree — if libadwaita's layout changes and it isn't
        found, the page keeps its old width without an error.
        """
        stack = [page]
        while stack:
            widget = stack.pop()
            if isinstance(widget, Adw.Clamp):
                widget.set_maximum_size(maximum)
                widget.set_tightening_threshold(maximum)
                return
            child = widget.get_first_child()
            while child:
                stack.append(child)
                child = child.get_next_sibling()

    # --- session ------------------------------------------------------------
    def _page_session(self) -> Gtk.Widget:
        """Idle + night light + screen recording + game mode.

        The groups are drawn from the schema; the page's only own job is to say
        whether the related program is installed. While it isn't, the setting is
        still shown (the value is written to settings.conf and takes effect once
        the program is installed later), but the user can see here why nothing
        happens.
        """
        page = Adw.PreferencesPage()
        self._widen_page(page, 940)

        #: group id → (component id, note shown if that component is missing)
        needs = {
            "idle": ("hypridle", "hypridle isn't installed — idle "
                                 "timeouts aren't generated."),
            "lock": ("hyprlock", "hyprlock isn't installed — lock screen "
                                 "settings don't apply."),
            "night": ("hyprland-extras", "hyprshade isn't installed (Hyprland "
                                         "Extras) — night light "
                                         "scheduling won't work."),
            "capture": ("instant-replay", "gpu-screen-recorder isn't installed "
                                          "(Screenshot & Recording → Instant "
                                          "replay) — record.sh isn't generated."),
        }
        for group_id in PAGE_GROUPS["session"]:
            group = schema.group(group_id)
            widget = self._group_widget(group_id)
            comp_id, note = needs.get(group_id, ("", ""))
            if comp_id and deps_mod.unmet([comp_id], self.catalog, self.state.selected,
                              self.applier.installed_packages()):
                row = Adw.ActionRow(title=esc(note))
                row.set_subtitle("These settings have no effect until it's installed "
                                 "and selected.")
                row.add_prefix(Gtk.Image.new_from_icon_name(
                    "dialog-warning-symbolic"))
                fix = Gtk.Button(label="Install", valign=Gtk.Align.CENTER)
                fix.add_css_class("suggested-action")
                fix.connect("clicked", self._on_session_fix, comp_id,
                            group.title, row)
                row.add_suffix(fix)
                widget.add(row)
            page.add(widget)
        return page

    def _on_session_fix(self, _btn, comp_id: str, what: str,
                        row: Adw.ActionRow) -> None:
        def done() -> None:
            self._refresh_component_rows()
            # If selecting was enough the warning goes away right away; if an install
            # is running the row stays until it finishes (the watcher refreshes it).
            if not deps_mod.unmet([comp_id], self.catalog, self.state.selected,
                                  self.applier.installed_packages()):
                row.set_visible(False)

        self._require([comp_id], what, done, chosen=comp_id)

    def _page_keybinds(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()
        # bind id → (row, key button, revert button)
        self._keybind_rows: dict[str, tuple] = {}

        intro = Adw.PreferencesGroup(
            title="Keyboard shortcuts",
            description="Click a shortcut's key and press the new combination. "
                        "Esc cancels, Backspace removes the shortcut entirely. "
                        "MOD is the main modifier key from the Appearance tab.\n"
                        "Changes are written to settings.conf as the KEYBINDS line; "
                        "you don't need to edit keybinds.conf "
                        "by hand.")
        self._keybind_status = Adw.ActionRow(title="All default")
        self._keybind_status.add_prefix(
            Gtk.Image.new_from_icon_name("dialog-information-symbolic"))
        self._keybind_status.set_subtitle_lines(2)
        reset_all = Gtk.Button(label="Reset all", valign=Gtk.Align.CENTER)
        reset_all.connect("clicked", lambda _b: self._reset_keybinds())
        self._keybind_status.add_suffix(reset_all)
        intro.add(self._keybind_status)
        page.add(intro)

        mod_key = self.state.get("MOD_KEY") or "SUPER"
        for category in self.keybinds.categories:
            group = Adw.PreferencesGroup(title=esc(category.title))
            for bind in category.binds:
                row = Adw.ActionRow(title=esc(bind.title),
                                    subtitle=esc(self._bind_action_text(bind)))
                row.set_subtitle_lines(2)

                if not bind.editable:
                    label = Gtk.Label(
                        label=keybinds_mod.display(bind.keys, mod_key))
                    label.add_css_class("dim-label")
                    label.set_valign(Gtk.Align.CENTER)
                    row.add_suffix(label)
                    group.add(row)
                    continue

                button = Gtk.Button(valign=Gtk.Align.CENTER)
                button.set_tooltip_text("Assign a new key")
                button.connect("clicked", self._on_keybind_clicked, bind)
                undo = Gtk.Button(icon_name="edit-undo-symbolic",
                                  valign=Gtk.Align.CENTER)
                undo.add_css_class("flat")
                undo.set_tooltip_text("Revert to default")
                undo.connect("clicked", self._on_keybind_reset, bind)
                row.add_suffix(button)
                row.add_suffix(undo)
                row.set_activatable_widget(button)
                self._keybind_rows[bind.id] = (row, button, undo)
                group.add(row)
            page.add(group)

        self._refresh_keybind_rows()
        return page

    # Pressing only a modifier key doesn't complete the shortcut.
    _MODIFIER_KEYNAMES = {
        "Super_L", "Super_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
        "Shift_L", "Shift_R", "Meta_L", "Meta_R", "ISO_Level3_Shift",
        "Caps_Lock", "Num_Lock",
    }

    def _bind_action_text(self, bind) -> str:
        """Writes what the shortcut does in readable form.

        The commands in keybinds.json contain placeholders like ``{{CMD_TERMINAL}}``;
        they're filled in here according to the selected components.
        """
        values = {
            "CMD_TERMINAL": self.state.primary("terminal"),
            "CMD_LAUNCHER": self.state.primary("launcher"),
            "CMD_DMENU": self.state.primary("launcher"),
            "CMD_FILEMANAGER": self.state.primary("files"),
            "BROWSER": self.state.get("BROWSER"),
            "LOCK_CMD": ("hyprlock" if self.state.is_selected("hyprlock")
                         else "loginctl lock-session"),
            "LOGOUT_CMD": ("wlogout" if self.state.is_selected("wlogout")
                           else "hyprctl dispatch exit"),
            "SCREENSHOT_CMD": "grim + slurp",
            "SCREENSHOT_DIR_SH": (self.state.get("SCREENSHOT_DIR")
                                  or "~/Pictures/Screenshots"),
        }
        text = re.sub(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}",
                      lambda m: values.get(m.group(1)) or m.group(1).lower(),
                      bind.action)
        if bind.require:
            text += f"  ·  only generated if {bind.require} is selected"
        return text

    def _keybind_overrides(self) -> dict[str, str]:
        return keybinds_mod.parse_overrides(self.state.get("KEYBINDS"))

    def _store_overrides(self, overrides: dict[str, str]) -> None:
        self.state.set("KEYBINDS", keybinds_mod.format_overrides(overrides))
        self._refresh_keybind_rows()

    def _set_keybind(self, bind, combo: str) -> None:
        overrides = self._keybind_overrides()
        combo = keybinds_mod.normalize(combo)
        if combo == keybinds_mod.normalize(bind.keys):
            overrides.pop(bind.id, None)       # back to its default
        else:
            overrides[bind.id] = combo
        self._store_overrides(overrides)

    def _on_keybind_reset(self, _button, bind) -> None:
        overrides = self._keybind_overrides()
        if overrides.pop(bind.id, None) is None:
            return
        self._store_overrides(overrides)

    def _reset_keybinds(self) -> None:
        self._store_overrides({})
        self._toast("All shortcuts reverted to default")

    def _on_keybind_clicked(self, _button, bind) -> None:
        mod_key = self.state.get("MOD_KEY") or "SUPER"
        current = keybinds_mod.normalize(
            self._keybind_overrides().get(bind.id, bind.keys))

        dialog = Adw.Window(modal=True, transient_for=self,
                            title=f"Shortcut: {bind.title}")
        dialog.set_default_size(460, 220)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for margin in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{margin}")(24)

        heading = Gtk.Label(label=bind.title)   # plain text: markup isn't parsed
        heading.add_css_class("title-2")
        prompt = Gtk.Label(label="Press the new key combination")
        current_label = Gtk.Label(
            label=f"Current: {keybinds_mod.display(current, mod_key)}")
        current_label.add_css_class("dim-label")
        hint = Gtk.Label(label="Esc — cancel   ·   Backspace — remove shortcut")
        hint.add_css_class("caption")
        hint.add_css_class("dim-label")
        for widget in (heading, prompt, current_label, hint):
            widget.set_wrap(True)
            box.append(widget)
        dialog.set_content(box)

        controller = Gtk.EventControllerKey()
        controller.connect("key-pressed", self._on_keybind_captured,
                           dialog, bind)
        dialog.add_controller(controller)
        dialog.present()

    def _on_keybind_captured(self, _controller, keyval, _keycode, state,
                             dialog, bind) -> bool:
        name = Gdk.keyval_name(keyval) or ""
        if name in self._MODIFIER_KEYNAMES:
            return True
        if name == "Escape":
            dialog.close()
            return True
        if name in ("BackSpace", "Delete"):
            self._set_keybind(bind, "")
            dialog.close()
            self._toast(f"Shortcut '{bind.title}' removed")
            return True

        mods: list[str] = []
        if state & Gdk.ModifierType.SUPER_MASK:
            mods.append("SUPER")
        if state & Gdk.ModifierType.CONTROL_MASK:
            mods.append("CTRL")
        if state & Gdk.ModifierType.ALT_MASK:
            mods.append("ALT")
        if state & Gdk.ModifierType.SHIFT_MASK:
            mods.append("SHIFT")

        # The physical modifier matching MOD_KEY is turned into the abstract MOD, so
        # changing the main key later doesn't break the shortcuts. Other modifiers
        # (SUPER included) are written as they are.
        mod_key = self.state.get("MOD_KEY") or "SUPER"
        mods = ["MOD" if m == mod_key else m for m in mods]

        key = name.upper() if len(name) == 1 and name.isalpha() else name
        combo = "+".join(mods + [key])
        dialog.close()
        if not keybinds_mod.valid_combo(combo):
            self._toast(f"This key can't be used: {name}")
            return True
        self._set_keybind(bind, combo)
        self._toast(f"{bind.title}: "
                    f"{keybinds_mod.display(keybinds_mod.normalize(combo), mod_key)}")
        return True

    def _refresh_keybind_rows(self) -> None:
        if not getattr(self, "_keybind_rows", None):
            return
        overrides = self._keybind_overrides()
        mod_key = self.state.get("MOD_KEY") or "SUPER"

        used: dict[str, list[str]] = {}
        for bind in self.keybinds.all():
            combo = keybinds_mod.normalize(overrides.get(bind.id, bind.keys))
            if combo:
                used.setdefault(combo, []).append(bind.title)

        for bind in self.keybinds.all():
            entry = self._keybind_rows.get(bind.id)
            if entry is None:
                continue
            row, button, undo = entry
            # The description updates too when the terminal/launcher choice changes.
            row.set_subtitle(esc(self._bind_action_text(bind)))
            combo = keybinds_mod.normalize(overrides.get(bind.id, bind.keys))
            changed = bind.id in overrides
            # Shortcuts that come without keys (window groups) aren't removed;
            # they're waiting for the user to assign them.
            button.set_label(keybinds_mod.display(combo, mod_key) if combo
                             else "unassigned" if not bind.keys and not changed
                             else "removed")
            undo.set_sensitive(changed)
            for css in ("suggested-action", "error"):
                button.remove_css_class(css)
            if combo and len(used.get(combo, ())) > 1:
                button.add_css_class("error")
            elif changed:
                button.add_css_class("suggested-action")

        clashes = {combo: titles for combo, titles in used.items()
                   if len(titles) > 1}
        if clashes:
            combo, titles = next(iter(clashes.items()))
            self._keybind_status.set_title("Conflicting shortcuts")
            self._keybind_status.set_subtitle(
                f"{keybinds_mod.display(combo, mod_key)} → " + ", ".join(titles)
                + ("" if len(clashes) == 1 else f"  (+{len(clashes) - 1} more conflicts)"))
        elif overrides:
            self._keybind_status.set_title(f"{len(overrides)} shortcuts changed")
            self._keybind_status.set_subtitle(
                "will be written to settings.conf as the KEYBINDS line")
        else:
            self._keybind_status.set_title("All default")
            self._keybind_status.set_subtitle("")

    # --- displays -----------------------------------------------------------
    def _page_monitors(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()
        page.add(self._nwg_displays_group())

        detected = Adw.PreferencesGroup(
            title="Detected displays",
            description="If Hyprland is running, your current display layout is "
                        "listed here. The 'Use' button copies this layout into the setting.")
        monitors = _detect_monitors()
        if monitors:
            for name, _spec, description in monitors:
                row = Adw.ActionRow(title=esc(name), subtitle=esc(description))
                row.set_subtitle_lines(2)
                detected.add(row)
            button = Gtk.Button(label="Use this layout")
            button.add_css_class("suggested-action")
            button.set_halign(Gtk.Align.START)
            button.set_margin_top(6)
            spec_text = ";".join(spec for _n, spec, _d in monitors)
            button.connect("clicked", lambda _b: self._use_monitor_spec(spec_text))
            detected.add(button)
        else:
            detected.add(Adw.ActionRow(
                title="Could not get display info",
                subtitle="Hyprland may not be running. You can enter it "
                         "manually below."))
        page.add(detected)

        manual = self._monitor_manual = Adw.PreferencesGroup(
            title="Display setup",
            description="Format: name,resolution@refresh,position,scale — "
                        "separate multiple displays with ';'.")
        self._monitor_entry = Adw.EntryRow(title="MONITOR_SPEC")
        self._monitor_entry.set_text(self.state.get("MONITOR_SPEC"))
        self._monitor_entry.connect("changed", lambda r: self.state.set(
            "MONITOR_SPEC", r.get_text()))
        manual.add(self._monitor_entry)

        ws = self._workspace_entry = Adw.EntryRow(title="Workspace → display")
        ws.set_text(self.state.get("WORKSPACE_MONITOR_MAP"))
        ws.set_tooltip_text("E.g.: 1:DP-1:default;2:DP-1;6:HDMI-A-1:default")
        ws.connect("changed", self._on_workspace_map)
        manual.add(ws)
        manual.set_sensitive(self.state.get("MANAGE_MONITORS") != "0")
        page.add(manual)
        return page

    def _nwg_displays_group(self) -> Adw.PreferencesGroup:
        """Switch for leaving the display layout to nwg-displays + open button.

        There used to be only a "let this tool manage monitors.conf" switch:
        there was no way to install or open nwg-displays, and what the switch
        did wasn't clear either. When the switch is turned on and nwg-displays isn't
        installed, _require shows the "Install and enable" dialog (in a terminal, the sudo
        password is asked there).
        """
        group = Adw.PreferencesGroup(
            title="nwg-displays",
            description="A graphical tool for arranging displays by drag and drop. "
                        "While on, it writes monitors.conf and workspaces.conf; "
                        "this app doesn't touch those files.")
        owner = self._monitor_owners.get("hypr/monitors.conf", "")
        switch = self._nwg_switch = Adw.SwitchRow(
            title="Let nwg-displays manage the displays",
            subtitle=(f"monitors.conf is currently managed by '{owner}'. If you turn this "
                      "off, the file is backed up and regenerated from the setting below."
                      if owner else
                      "While off, the displays come from 'Display setup' below."))
        switch.set_subtitle_lines(3)
        # The initial value is read FROM THE STATE (MANAGE_MONITORS=0 → nwg manages).
        switch.set_active(self.state.get("MANAGE_MONITORS") == "0")
        switch.connect("notify::active", self._on_nwg_displays_toggled)
        group.add(switch)

        open_row = Adw.ActionRow(
            title="Open nwg-displays",
            subtitle="If it isn't installed, it's installed first "
                     "(password asked in the terminal).")
        button = Gtk.Button(label="Open", valign=Gtk.Align.CENTER)
        button.connect("clicked", lambda _b: self._open_nwg_displays())
        open_row.add_suffix(button)
        open_row.set_activatable_widget(button)
        group.add(open_row)
        return group

    def _set_monitor_owner(self, nwg: bool) -> None:
        """Changes the owner of the display files (switch and open button)."""
        if nwg:
            self.state.set("MANAGE_MONITORS", "0")
            # nwg-displays writes workspaces.conf too; the two shouldn't both try to
            # manage the same file (see workspaces.conf.tmpl).
            if self.state.get("WORKSPACE_MONITOR_MAP"):
                self.state.set("WORKSPACE_MONITOR_MAP", "")
                entry = getattr(self, "_workspace_entry", None)
                if entry is not None:
                    entry.set_text("")
        else:
            # As long as the foreign file stays in place, no render can change it
            # (apply.py:write_changed protects it). Since the user explicitly said
            # "you manage it", the file is backed up and removed, and on the next
            # apply round the file we generate takes its place.
            released = self.applier.release_foreign("hypr/monitors.conf")
            if released:
                self._monitor_owners.pop("hypr/monitors.conf", None)
                self._toast(f"{released} backed up; monitors.conf "
                            "is now managed by this tool")
            self.state.set("MANAGE_MONITORS", "1")
        switch = getattr(self, "_nwg_switch", None)
        if switch is not None and switch.get_active() != nwg:
            switch.set_active(nwg)
        manual = getattr(self, "_monitor_manual", None)
        if manual is not None:
            manual.set_sensitive(not nwg)

    def _on_nwg_displays_toggled(self, row, _param) -> None:
        nwg = row.get_active()
        if nwg == (self.state.get("MANAGE_MONITORS") == "0"):
            return                         # programmatic sync
        if not nwg:
            self._set_monitor_owner(False)
            return
        self._require(["nwg-displays"], "nwg-displays",
                      lambda: self._set_monitor_owner(True),
                      on_cancel=lambda: row.set_active(False),
                      chosen="nwg-displays")

    def _open_nwg_displays(self) -> None:
        """Opens nwg-displays; if it isn't installed, has it installed first."""
        def launch() -> None:
            self._set_monitor_owner(True)
            if not shutil.which("nwg-displays"):
                # The install is running in a terminal; the button is pressed again
                # when it finishes.
                self._toast("Press 'Open' again once nwg-displays is installed")
                return
            # The settings app floats: nwg-displays also opens floating and in front.
            if self._spawn_floating(["nwg-displays"],
                                    rules="float on; center on; size 75% 75%",
                                    window_class="nwg-displays"):
                return
            try:
                subprocess.Popen(["nwg-displays"], start_new_session=True,
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            except OSError as exc:
                self._toast(f"Could not open nwg-displays: {exc}")
        self._require(["nwg-displays"], "nwg-displays", launch,
                      chosen="nwg-displays")

    def _on_workspace_map(self, row) -> None:
        """The workspace → display mapping field."""
        text = row.get_text()
        # Writing the mapping by hand also means "you manage workspaces.conf";
        # otherwise the written value would be silently ignored.
        if text.strip() and "hypr/workspaces.conf" in self._monitor_owners:
            released = self.applier.release_foreign("hypr/workspaces.conf")
            if released:
                self._monitor_owners.pop("hypr/workspaces.conf", None)
                self._toast(f"{released} backed up; workspaces.conf "
                            "is now managed by this tool")
        self.state.set("WORKSPACE_MONITOR_MAP", text)

    def _use_monitor_spec(self, spec: str) -> None:
        self.state.set("MONITOR_SPEC", spec)
        self._monitor_entry.set_text(spec)
        self._toast("Display layout copied into the setting")

    # --- system -------------------------------------------------------------
    def _page_system(self) -> Gtk.Widget:
        """Read-only system page: settings file, missing packages, diagnostics.

        This app does NOT install packages (a deliberate decision: changing settings
        shouldn't require root). But when a backend that isn't installed can't be
        selected, the user needs a concrete next step — here there's a copyable
        pacman command for each missing component.
        """
        page = Adw.PreferencesPage()

        conf_group = Adw.PreferencesGroup(
            title="Settings",
            description="Changes are applied instantly and written to this file. "
                        "If you edit the file by hand, reopen the app.")
        path_row = Adw.ActionRow(title="Settings file",
                                 subtitle=str(self._conf_path()))
        path_row.add_suffix(self._copy_button(str(self._conf_path())))
        conf_group.add(path_row)
        backup_row = Adw.ActionRow(
            title="Backups",
            subtitle=str(Path.home() / ".config/hyprsetup-backups/") +
                     "\nA copy of every overwritten file is kept here.")
        backup_row.set_subtitle_lines(2)
        conf_group.add(backup_row)
        page.add(conf_group)

        self._missing_group = Adw.PreferencesGroup(
            title="Components that aren't installed",
            description="This app doesn't install packages. After running the "
                        "command below in a terminal, the related option "
                        "becomes selectable in the UI.")
        page.add(self._missing_group)
        self._refresh_missing_rows()

        page.add(self._update_group())
        page.add(self._share_group())

        doctor_group = Adw.PreferencesGroup(
            title="Diagnostics",
            description="Checks the session, configuration files, packages and "
                        "services. Changes nothing.")
        doctor_row = Adw.ActionRow(title="System check")
        doctor_button = Gtk.Button(label="Run", valign=Gtk.Align.CENTER)
        doctor_button.connect("clicked", lambda _b: self._run_doctor())
        doctor_row.add_suffix(doctor_button)
        doctor_group.add(doctor_row)

        self._doctor_view = Gtk.TextView(editable=False, monospace=True)
        self._doctor_view.set_top_margin(8)
        self._doctor_view.set_left_margin(10)
        self._doctor_view.get_buffer().set_text(
            "The check hasn't been run yet.")
        scroller = Gtk.ScrolledWindow(child=self._doctor_view)
        scroller.set_min_content_height(240)
        scroller.add_css_class("card")
        doctor_group.add(scroller)
        page.add(doctor_group)
        return page

    def _share_group(self) -> Adw.PreferencesGroup:
        """Export the desktop to a single file / import a shared file as a profile.

        Settings that can run commands, reveal a location or are machine-specific
        don't go into the file and aren't accepted on import (profileshare.py).
        """
        from .. import profileshare

        group = Adw.PreferencesGroup(
            title="Share my desktop",
            description="The look (theme, bar, terminal, launcher, layout, "
                        "animation) and the wallpaper are written to a single .tar.gz "
                        "file. Custom commands, extra startup commands, the weather "
                        "location and display settings don't go into the file. Only the "
                        "Workshop id of a Wallpaper Engine scene is included.")
        name_row = Adw.EntryRow(title="Profile name")
        name_row.set_text(self.state.get("THEME") or "My desktop")
        group.add(name_row)
        row = Adw.ActionRow(title="File")
        export = Gtk.Button(label="Export…", valign=Gtk.Align.CENTER)
        importer = Gtk.Button(label="Import…", valign=Gtk.Align.CENTER)
        row.add_suffix(importer)
        row.add_suffix(export)
        group.add(row)

        archive = {"filter_name": "Souprland profile (.tar.gz)",
                   "patterns": ["*.tar.gz", "*.tgz"]}

        def do_export(_b) -> None:
            title = name_row.get_text().strip() or "My desktop"

            def chosen(path: Path) -> None:
                values = dict(self.state.values)
                for cat in self.catalog.categories:
                    if cat.var and self.state.primary(cat.id):
                        values[cat.var] = self.state.primary(cat.id)
                wallpaper = self.applier.wallpaper_file(self.state.values)
                try:
                    out = profileshare.export(values, wallpaper, path, title)
                except OSError as exc:
                    self._toast(f"Could not write: {exc}")
                    return
                self._toast(f"Exported: {out.name}")
            pick_file(self, "Export desktop", chosen,
                      save_as=f"{title}.tar.gz", **archive)

        def do_import(_b) -> None:
            def chosen(path: Path) -> None:
                try:
                    name, skipped = profileshare.import_archive(path, root=self.root)
                except Exception as exc:   # noqa: BLE001 — a broken archive can raise anything
                    self._toast(f"Could not import: {exc}")
                    return
                note = f" ({len(skipped)} settings skipped for safety)" if skipped else ""
                self._toast(f"{name} imported{note}. Reopen the app for it to show up "
                            "in Profiles.")
            pick_file(self, "Import shared desktop", chosen, **archive)

        export.connect("clicked", do_export)
        importer.connect("clicked", do_import)
        return group

    def _update_group(self) -> Adw.PreferencesGroup:
        """Refreshing the installed copy from the source repo (selfupdate.py).

        If the repo is a git clone, new remote commits are counted too, and
        "Update" first runs ``git pull --ff-only``. Since the check uses the
        network, it starts from a button, not when the page opens.
        """
        import threading

        from .. import selfupdate

        group = Adw.PreferencesGroup(
            title="Update",
            description="The settings app, bar panel and keybinding card run "
                        f"from the copy under {selfupdate.INSTALL}.")
        src = selfupdate.source_root()
        if src is None and selfupdate.is_source_tree(self.root):
            src = self.root.resolve()
        row = Adw.ActionRow(title="Source repo",
                            subtitle=esc(str(src) if src else
                                         "unknown — reinstall with install.sh"))
        row.set_subtitle_lines(2)
        check = Gtk.Button(label="Check", valign=Gtk.Align.CENTER)
        update = Gtk.Button(label="Update", valign=Gtk.Align.CENTER, sensitive=False)
        update.add_css_class("suggested-action")
        row.add_suffix(check)
        row.add_suffix(update)
        group.add(row)
        if src is None:
            check.set_sensitive(False)
            return group
        state: dict = {}

        def show(info: dict, files: list[str]) -> None:
            state.update(info=info, files=files)
            parts = [f"{len(files)} files differ from the installed copy" if files
                     else "The installed copy matches the repo"]
            if info.get("git"):
                if info.get("behind"):
                    parts.append(f"{info['behind']} new remote commits ({info['upstream']})")
                elif info.get("upstream"):
                    parts.append("repo is up to date")
                if info.get("error"):
                    parts.append(info["error"])
            row.set_subtitle(esc(f"{src}\n" + " · ".join(parts)))
            update.set_sensitive(bool(files or info.get("behind")))
            check.set_sensitive(True)

        def run_check(_b=None) -> None:
            check.set_sensitive(False)
            row.set_subtitle(esc(f"{src}\nchecking…"))

            def work() -> None:
                info = selfupdate.git_status(src)
                files = selfupdate.differs(src)
                GLib.idle_add(lambda: (show(info, files), False)[1])
            threading.Thread(target=work, daemon=True).start()

        def run_update(_b) -> None:
            update.set_sensitive(False)
            check.set_sensitive(False)
            row.set_subtitle(esc(f"{src}\nupdating…"))
            behind = (state.get("info") or {}).get("behind")

            def work() -> None:
                message = ""
                if behind:
                    ok, text = selfupdate.git_pull(src)
                    if not ok:
                        message = f"git pull failed: {text}"
                if not message:
                    try:
                        changed = selfupdate.sync(src)
                        message = (f"{len(changed)} files updated. Reopen the app for "
                                   "all of the changes." if changed
                                   else "Already up to date.")
                    except OSError as exc:
                        message = f"Could not copy: {exc}"

                def done() -> bool:
                    self.toasts.add_toast(Adw.Toast(title=esc(message), timeout=6))
                    run_check()
                    return False
                GLib.idle_add(done)
            threading.Thread(target=work, daemon=True).start()

        check.connect("clicked", run_check)
        update.connect("clicked", run_update)
        return group

    @staticmethod
    def _copy_button(text: str) -> Gtk.Button:
        button = Gtk.Button(icon_name="edit-copy-symbolic",
                            valign=Gtk.Align.CENTER,
                            tooltip_text="Copy to clipboard")
        button.add_css_class("flat")

        def _copy(_b: Gtk.Button) -> None:
            display = Gdk.Display.get_default()
            if display is not None:
                display.get_clipboard().set(text)

        button.connect("clicked", _copy)
        return button

    def _refresh_missing_rows(self) -> None:
        """Redraws the missing-component rows."""
        group = getattr(self, "_missing_group", None)
        if group is None:
            return
        for row in getattr(self, "_missing_rows", []):
            group.remove(row)
        self._missing_rows: list[Gtk.Widget] = []

        for category in self.catalog.categories:
            if not category.single:
                continue          # only the axes selectable from the UI
            for comp in category.components:
                missing = self.applier.missing_packages(comp.id)
                if not missing:
                    continue
                command = self._install_command(missing)
                row = Adw.ActionRow(
                    title=esc(f"{comp.title} — {category.title}"),
                    subtitle=esc(command))
                row.set_subtitle_lines(2)
                if comp.aur:
                    row.add_suffix(aur_mod.badge(comp.aur))
                row.add_suffix(self._copy_button(command))
                group.add(row)
                self._missing_rows.append(row)

        if not self._missing_rows:
            row = Adw.ActionRow(
                title="All installed",
                subtitle="Every option in the UI is available.")
            group.add(row)
            self._missing_rows.append(row)

    def _run_doctor(self) -> None:
        """Writes the install.sh --doctor output to the page (read-only check)."""
        buffer = self._doctor_view.get_buffer()
        installer = self.root / "install.sh"
        if not installer.is_file():
            buffer.set_text(f"install.sh not found: {installer}")
            return
        buffer.set_text("Running…")
        try:
            proc = subprocess.run(
                ["bash", str(installer), "--doctor"], cwd=str(self.root),
                capture_output=True, text=True, timeout=120, check=False,
                env={**os.environ, "NO_COLOR": "1"})
        except (OSError, subprocess.SubprocessError) as exc:
            buffer.set_text(f"Could not run the check: {exc}")
            return
        buffer.set_text((proc.stdout + proc.stderr).strip() or "(no output)")

    # ------------------------------------------------------- state flow ---
    def _on_state_changed(self) -> None:
        # All three drawings are fed from the same state; whichever page we're on,
        # they're all refreshed (queue_draw on an invisible widget is nearly free).
        for widget in ("preview", "diagram", "input_diagram", "cursor_diagram",
                       "anim_diagram", "widget_preview", "behavior_diagram",
                       "switcher_diagram", "groupbar_diagram",
                       "gesture_diagram", "plugins_diagram"):
            area = getattr(self, widget, None)
            if area is not None:
                area.queue_draw()
        # The widget samples use the theme's colors and box settings.
        for area in getattr(self, "_widget_samples", ()):
            area.queue_draw()
        # Soup Maker's live desktop: manual settings should show up too.
        if getattr(self, "_mix_preview", None) is not None:
            self._mix_preview.update(mix_mod.preview_values(
                self.root, self._mix_parts, self._mix_pending, self.state.values))
        # bar_preview doesn't get a plain queue_draw — if the BAR_POSITION
        # horizontal↔vertical category changed, the widget itself may need to change.
        self._refresh_bar_preview_widget()
        wizard = getattr(self, "wizard", None)
        if wizard is not None:
            wizard.refresh()
        # The bar preset cards are fed from the live palette; they follow theme changes too.
        for area in getattr(self, "_bar_card_previews", ()):
            area.queue_draw()
        # The previews on the terminal/launcher pages come from the live settings too.
        for area in list(getattr(self, "_axis_previews", {}).values()) \
                + list(getattr(self, "_axis_card_previews", ())):
            area.queue_draw()
        # The launcher mockups are fed from the live palette the same way.
        for area in getattr(self, "_launcher_previews", ()):
            area.queue_draw()
        # ALT+Tab priority fix (ananicy rule, needs root).
        priority = self.state.get("SWITCHER_PRIORITY") or "off"
        if priority != getattr(self, "_priority_seen", priority):
            self._priority_seen = priority
            GLib.idle_add(lambda m=priority: (self._sync_priority(m), False)[1])
        # Profiles showcase: when the applied profile changes, that one is shown.
        self._refresh_profile_hero()
        # Selected highlight of the terminal startup screen / background cards.
        for refresh in getattr(self, "_term_look_refresh", ()):
            refresh()
        # The custom module slots' titles show the command; keep them current
        # while the user is typing too.
        self._refresh_custom_titles()
        # When MOD_KEY changes the shortcut labels must update too.
        self._refresh_keybind_rows()
        # Sidebar summary: no longer a package count (this app doesn't install
        # packages), but which tools are currently configured.
        if hasattr(self, "summary_label"):
            self.summary_label.set_text(
                f"Theme: {self.state.get('THEME')}\n"
                f"{self.state.primary('bar') or '—'} · "
                f"{self.state.primary('terminal') or '—'} · "
                f"{self.state.primary('launcher') or '—'}")

    # ---------------------------------------------------------- actions ---
    # The settings file location is defined in state.py: panel mode (gui/quick.py)
    # reads and writes the same file too, there must not be two copies.
    def _conf_path(self) -> Path:
        return config_path()

    def _conf_candidates(self) -> list[Path]:
        return config_candidates()

    # --------------------------------------------- external changes ---
    def _watch_conf(self) -> None:
        """Start watching settings.conf."""
        try:
            gfile = Gio.File.new_for_path(str(self._conf_path()))
            monitor = gfile.monitor_file(Gio.FileMonitorFlags.NONE, None)
        except GLib.Error:
            return                      # watching couldn't be set up: old behavior
        monitor.connect("changed", self._on_conf_changed)
        self._conf_monitor = monitor
        self._conf_written = self._conf_digest()

    def _conf_digest(self) -> str:
        try:
            return self._conf_path().read_text(encoding="utf-8")
        except OSError:
            return ""

    def _on_conf_changed(self, _monitor, _file, _other, event) -> None:
        if event not in (Gio.FileMonitorEvent.CHANGES_DONE_HINT,
                         Gio.FileMonitorEvent.CREATED,
                         Gio.FileMonitorEvent.MOVED_IN,
                         Gio.FileMonitorEvent.RENAMED):
            return
        # An editor's save produces several events (truncate + write +
        # close); instead of reloading on each, a single round runs after a
        # short wait.
        if self._conf_reload_source:
            GLib.source_remove(self._conf_reload_source)
        self._conf_reload_source = GLib.timeout_add(250, self._reload_conf)

    def _reload_conf(self) -> bool:
        self._conf_reload_source = 0
        text = self._conf_digest()
        # Our own file: _run_apply saves settings.conf every round, and if we
        # took its event for "changed from outside" and reloaded, it would loop
        # forever.
        if not text or text == self._conf_written:
            return False
        # Changes made here since our last save (still in the debounce or
        # queued behind a running round) are not in the file yet. Loading the
        # file wholesale would silently undo them — e.g. switching
        # THEME_SCHEDULE off right after on: the timer it started rewrote the
        # file with "true" and the reload brought it back. Keys the user
        # touched since the last save keep the in-app value.
        mine: dict[str, str] = {}
        mine_selected: set[str] | None = None
        if self._apply_source or self._apply_running:
            saved = conffile.parse_text(self._conf_written)
            mine = {k: v for k, v in self.state.values.items()
                    if k in saved and saved[k] != v}
            if set(filter(None, saved.get("COMPONENTS", "").split(","))) != self.state.selected:
                mine_selected = set(self.state.selected)
        self._conf_written = text
        if not self.state.load_conf(self._conf_path()):
            return False
        if mine or mine_selected is not None:
            self.state.values.update(mine)
            if mine_selected is not None:
                self.state.selected = mine_selected
            self._schedule_apply()
        # load_conf fires the listeners: the UI refreshes and the change is
        # applied to the desktop through the normal chain. The row widgets are only
        # read from the state by _sync_all_rows, so that must be called separately.
        self._sync_all_rows()
        self._refresh_component_rows()
        self._toast("settings.conf changed outside the app — reloaded")
        return False

    def _save_conf(self) -> Path:
        path = self.state.save_conf(self._conf_path())
        self._toast(f"Saved: {path}")
        return path

    # ------------------------------------------------- live apply ---------
    #: Delay after a setting changes before applying. While dragging a slider
    #: dozens of changes arrive per second; rendering + restarting daemons on
    #: each would lock up both the UI and the desktop. A single round runs
    #: once the user's hand stops.
    APPLY_DEBOUNCE_MS = 300

    def _schedule_apply(self) -> None:
        """A setting changed — schedule an apply round at the end of the debounce delay."""
        if self._apply_hold:
            self._apply_held = True
            self._set_apply_status("Preview mode: changes pending "
                                   "(Setup Wizard → Finish)")
            return
        if self._apply_source:
            GLib.source_remove(self._apply_source)
        self._apply_source = GLib.timeout_add(
            self.APPLY_DEBOUNCE_MS, self._run_apply)

    def set_apply_hold(self, hold: bool) -> None:
        """Hold / release live apply. On release the accumulated changes are
        applied in a single round."""
        if hold == self._apply_hold:
            return
        self._apply_hold = hold
        if hold:
            self._set_apply_status("Preview mode: not applied to the desktop "
                                   "yet")
        elif self._apply_held:
            self._apply_held = False
            self._schedule_apply()
        else:
            self._set_apply_status("Up to date")

    def _run_apply(self, then=None) -> bool:
        """Start an apply round.

        The round runs in the background: render + daemon restarts
        (_RESTART_SETTLE sleeps, pacman/hyprctl/pgrep calls) froze the window on
        every setting change when run on the main loop. If ``then`` is
        given it's called on the main loop after the round with the current values
        finishes (e.g. start_missing must run after the round).
        """
        self._apply_source = 0
        if then is not None:
            self._apply_then.append(then)
        if self._apply_running:
            # A new change arrived while applying: run once more after the round
            # finishes, so the changes in between aren't lost.
            self._apply_again = True
            return False
        try:
            self.state.save_conf(self._conf_path())
            # So the watcher doesn't take this write for an "external change".
            self._conf_written = self._conf_digest()
        except Exception as exc:                          # noqa: BLE001
            self._set_apply_status(f"Could not apply: {exc}", error=True)
            self._flush_apply_then()
            return False
        self._apply_running = True
        self._set_apply_status("Applying…")
        # The thread works on a copy of the state; the main loop may change
        # values meanwhile (that change comes via _apply_again).
        values = dict(self.state.values)
        selected = sorted(self.state.selected)

        def work() -> None:
            try:
                result, error = self.applier.apply(values, selected), None
            except Exception as exc:                      # noqa: BLE001
                result, error = None, exc
            GLib.idle_add(self._apply_finished, result, error)

        import threading
        # daemon=False: if the window closes mid-round the interpreter waits for
        # the round to finish; no half-written configuration is left behind.
        threading.Thread(target=work, daemon=False).start()
        return False   # GLib.timeout_add: don't repeat

    def _apply_finished(self, result, error) -> bool:
        self._apply_running = False
        if error is not None:
            self._set_apply_status(f"Could not apply: {error}", error=True)
        elif result.errors:
            self._set_apply_status(result.errors[0], error=True)
        elif not result.written:
            self._set_apply_status("Up to date")
        else:
            detail = ", ".join(result.actions) if result.actions else "written"
            self._set_apply_status(f"{len(result.written)} files · {detail}")

        if self._apply_again:
            # Pending "then"s wait for the round with the latest values.
            # If the slider is still moving, the debounce timer is already set
            # and the round comes with it.
            self._apply_again = False
            if not self._apply_source:
                self._run_apply()
        else:
            self._flush_apply_then()
        return False   # GLib.idle_add: once

    def _after_apply(self, callback) -> None:
        """Call ``callback`` when the pending/running round finishes; start one if there is none."""
        if self._apply_running or self._apply_source or self._apply_hold:
            self._apply_then.append(callback)
        else:
            self._run_apply(then=callback)

    def _flush_apply_then(self) -> None:
        pending, self._apply_then = self._apply_then, []
        for callback in pending:
            callback()

    def _set_apply_status(self, message: str, error: bool = False) -> None:
        label = getattr(self, "apply_status", None)
        if label is None:
            return
        label.set_text(message)
        label.remove_css_class("error")
        label.remove_css_class("dim-label")
        label.add_css_class("error" if error else "dim-label")

    def _toast(self, message: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=message, timeout=4))


# --------------------------------------------------------------- helpers ---
def _detect_monitors() -> list[tuple[str, str, str]]:
    """Reads the current displays from hyprctl → (name, spec, description)."""
    if not shutil.which("hyprctl"):
        return []
    try:
        import json
        raw = subprocess.run(["hyprctl", "monitors", "-j"],
                             capture_output=True, text=True, timeout=5)
        data = json.loads(raw.stdout or "[]")
    except (OSError, ValueError, subprocess.SubprocessError):
        return []

    result = []
    for monitor in data:
        name = monitor.get("name", "?")
        width = monitor.get("width", 0)
        height = monitor.get("height", 0)
        rate = monitor.get("refreshRate", 60.0)
        x, y = monitor.get("x", 0), monitor.get("y", 0)
        scale = monitor.get("scale", 1.0)
        spec = f"{name},{width}x{height}@{rate:.2f},{x}x{y},{scale:g}"
        description = (f"{width}×{height} @ {rate:.0f} Hz · position {x},{y} · "
                       f"scale {scale:g}")
        model = monitor.get("description") or monitor.get("model")
        if model:
            description += f"\n{model}"
        result.append((name, spec, description))
    return result


class HyprsetupApp(Adw.Application):
    def __init__(self, root: Path, catalog: Catalog,
                 app_id: str = APP_ID, panel: bool = False):
        # The window class is deliberately different in panel mode; the Hyprland
        # rules float and slide both, but the user can target just one of them
        # with WINDOWRULES.
        super().__init__(application_id=app_id,
                         flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.root = root
        self.catalog = catalog
        self.panel = panel

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        GLib.set_application_name(APP_NAME)
        # Icon theme not installed → Adwaita (sidebar icons rendered broken).
        from .util import ensure_icon_theme
        ensure_icon_theme()
        # When not installed (running from the repo) the icon isn't in the theme:
        # the repo's assets/ folder is added to the search path.
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.IconTheme.get_for_display(display).add_search_path(
                str(self.root / "assets"))
        Gtk.Window.set_default_icon_name(ICON_NAME)

    def do_activate(self) -> None:
        window = MainWindow(self, self.root, self.catalog, panel=self.panel)
        window._on_state_changed()
        window.present()


def _monitor_size() -> tuple[int, int]:
    """Pixel size of the primary display — 1920×1080 is assumed if unavailable.

    The panel size is given RELATIVE to the screen in the window rule; if GTK's
    default size doesn't do the same calculation, the window first opens at its
    own size and is then resized by Hyprland right away, and the panel visibly
    jumps.
    """
    display = Gdk.Display.get_default()
    if display is not None:
        monitors = display.get_monitors()
        if monitors.get_n_items():
            geometry = monitors.get_item(0).get_geometry()
            return geometry.width, geometry.height
    return 1920, 1080


def run(root: Path, catalog_path: Path, templates: Path,
        panel: bool = False) -> int:
    root = root.resolve()
    if not catalog_path.is_absolute():
        catalog_path = root / catalog_path
    catalog = Catalog.load(catalog_path)
    os.environ.setdefault("GSK_RENDERER", "gl")
    return HyprsetupApp(root, catalog,
                        app_id=QUICK_APP_ID if panel else APP_ID,
                        panel=panel).run([])
