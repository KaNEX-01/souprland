"""Setup Wizard: setting up the desktop from scratch, step by step.

The other pages group settings by topic and show them all at once; the
wizard asks the same settings IN ORDER: how windows behave, wallpaper,
colors, window look, terminal, launcher, bar, notifications/lock and login
screen. Each step has a few big options (cards) and fine-tuning rows on the
left, and a big live preview explaining that step on the right.

There is no new settings mechanism: cards and rows write to the same
``SetupState``, and the previews are the widgets from preview.py. A few
things are specific to the wizard:

* The **Try live on the desktop** switch. While on, every choice is applied
  immediately as on any page; while off, applying is held back
  (``MainWindow.set_apply_hold``) and changes only show in the preview, all
  going out at once with "Finish".
* **Revert.** The state at the moment the wizard was opened is saved;
  "Cancel" restores it, so the desktop goes back even if things were tried
  live.
* The **login screen** is a system file (sudo): choices are written to the
  Login Screen page's login.json and only reach the system on "Finish", and
  only if the user turned on the step's switch, via that page's own apply
  path.
"""

from __future__ import annotations

import copy
import hashlib
import shutil
import subprocess
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Gtk, Pango  # noqa: E402

from .. import login  # noqa: E402
from .. import rice as rice_mod  # noqa: E402
from .. import transition as transition_mod  # noqa: E402
from .. import settings as schema  # noqa: E402
from .. import themes  # noqa: E402
from .. import wallpaper as wallpaper_mod  # noqa: E402
from .preview import (AnimationDiagram, BarPreview, DesktopPreview,  # noqa: E402
                      GreeterPreview, LauncherLayoutPreview, LauncherPreview,
                      LayoutDiagram, LockPreview, NotificationPreview,
                      PaletteStrip, TerminalPreview, _wallpaper_surface)
from . import aur as aur_mod  # noqa: E402
from .util import ensure_css, pick_file  # noqa: E402
from .state import SetupState  # noqa: E402
from .tone import WallpaperSwatches  # noqa: E402

_CSS = """
.hs-wiz-card { padding: 0; }
.hs-wiz-card:checked { outline: 2px solid @accent_color; outline-offset: -2px; }
.hs-wiz-step { padding: 4px 6px; }
.hs-wiz-step.hs-wiz-current { background: alpha(@accent_color, 0.18); }
.hs-wiz-step.hs-wiz-done label { opacity: 0.75; }
"""


def _same(a: str, b: str) -> bool:
    """Setting values are stored as text: "1" and "1.0" must count as equal."""
    if a == b:
        return True
    try:
        return abs(float(a) - float(b)) < 1e-6
    except (TypeError, ValueError):
        return False


def _caption(text: str, width: int = 0) -> Gtk.Label:
    label = Gtk.Label(label=text, xalign=0, wrap=True)
    if width:
        # A wrapping label's natural width is the whole text; since FlowBox
        # sizes homogeneous cards by the widest one, a single long description
        # reduced the number of cards per row.
        label.set_max_width_chars(width)
    label.add_css_class("caption")
    label.add_css_class("dim-label")
    return label


#: "Start from defaults" resets the settings in these groups to the schema
#: defaults. Personal ones (input devices, monitors, keybindings, the wallpaper
#: file path) are not touched: "from scratch" resets the look, not the machine.
_RESET_GROUPS = ("layout", "decoration", "animation", "terminal", "bar")
_RESET_EXTRA = ("THEME", "CUSTOM_COLORS", "COLOR_SCHEME", "WALLPAPER_STYLE",
                "WALLPAPER_IMAGE", "SWWW_TRANSITION", "SWWW_TRANSITION_DURATION",
                "BAR_MODULES_LEFT", "BAR_MODULES_CENTER", "BAR_MODULES_RIGHT")

#: Window look cards: styles where several settings make sense together.
_LOOKS = (
    ({"BORDER_SIZE": "1", "ROUNDING": "0", "SHADOW": "false", "BLUR": "false",
      "ACTIVE_OPACITY": "1.0", "INACTIVE_OPACITY": "1.0"},
     "Flat", "Square corners, no shadow, fully opaque: classic tiling"),
    ({"BORDER_SIZE": "2", "ROUNDING": "10", "SHADOW": "true", "BLUR": "true",
      "ACTIVE_OPACITY": "1.0", "INACTIVE_OPACITY": "0.95"},
     "Soft", "Rounded corners, light shadow; background windows slightly transparent"),
    ({"BORDER_SIZE": "2", "ROUNDING": "14", "SHADOW": "true", "BLUR": "true",
      "ACTIVE_OPACITY": "0.92", "INACTIVE_OPACITY": "0.82"},
     "Glass", "Strong transparency and blur: the wallpaper shows through"),
    ({"BORDER_SIZE": "4", "ROUNDING": "4", "SHADOW": "false", "BLUR": "false",
      "ACTIVE_OPACITY": "1.0", "INACTIVE_OPACITY": "1.0"},
     "Bold outline", "Thick colored border, little rounding: retro/brutalist"),
)
_GAPS = (
    ({"GAPS_IN": "2", "GAPS_OUT": "4"}, "Tight", "Every pixel of the screen goes to windows"),
    ({"GAPS_IN": "5", "GAPS_OUT": "12"}, "Balanced", "Default gaps"),
    ({"GAPS_IN": "10", "GAPS_OUT": "24"}, "Airy", "Plenty of breathing room between windows"),
)
_PATTERNS = (("waves", "Flowing bands"), ("stars", "Star field"),
             ("orb", "Big orb"), ("mist", "Misty hills"),
             ("grid", "Technical grid"), ("paper", "Paper grain"),
             ("dunes", "Sand dunes"), ("solid", "Solid color"))
_MONO_FONTS = (("JetBrainsMono Nerd Font", "JetBrains Mono"),
               ("CaskaydiaCove Nerd Font", "Cascadia Code"))
_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


_NOTIFIERS = (
    ("mako", "mako", "The lightest; popup notifications only, no history panel."),
    ("dunst", "dunst", "Classic and mature; rules, history and a context menu."),
    ("swaync", "SwayNC", "Popup notifications plus a slide-out notification "
                         "center (history, quick buttons)."),
)


class WizardPage(Gtk.Box):
    """Setup Wizard (see the module docstring)."""

    def __init__(self, win) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        ensure_css(_CSS)
        # app.py imports this module; its helpers are fetched here, when the
        # window is built, to avoid an import cycle.
        from . import app as app_mod
        self._app = app_mod
        self.win = win
        self.state: SetupState = win.state
        self.home = Path.home()
        #: Refreshers for the rows drawn from the schema. The window's _sync_rows
        #: is NOT used: it has a single callback per key, and the wizard's row
        #: would replace the Appearance page's.
        self._sync: dict[str, object] = {}
        self._card_syncs: list = []
        self._previews: list[Gtk.Widget] = []
        self._syncing = False
        #: The state when the wizard was opened (Cancel restores it).
        self._snapshot: dict | None = None
        self._last_theme = self.state.get("THEME")
        self._pattern_job = 0
        self._wall_loaded = False
        #: Login screen step: whether to also write to the system on "Finish"
        #: (needs sudo), and whether to apply my palette/wallpaper in SDDM.
        self._login_apply = False
        self._sddm_paint = True
        self._sddm_wall = True
        self._login_syncs: list = []

        self._steps = (
            ("start", "Start", self._step_start, "desktop"),
            ("behavior", "Behavior", self._step_behavior, "motion"),
            ("wallpaper", "Wallpaper", self._step_wallpaper, "desktop"),
            ("colors", "Colors", self._step_colors, "desktop"),
            ("look", "Windows", self._step_look, "measure"),
            ("terminal", "Terminal", self._step_terminal, "terminal"),
            ("launcher", "Launcher", self._step_launcher, "launcher"),
            ("bar", "Bar", self._step_bar, "bar"),
            ("notify", "Notifications", self._step_notify, "notify"),
            ("login", "Login", self._step_login, "login"),
            ("summary", "Summary", self._step_summary, "desktop"),
        )
        self._index = 0

        self.append(self._build_header())
        self.append(Gtk.Separator())

        self._options = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self._step_pages: dict[str, Gtk.Widget] = {}
        for step_id, _title, builder, _preview in self._steps:
            content = builder()
            scroller = Gtk.ScrolledWindow(child=content, vexpand=True,
                                          hscrollbar_policy=Gtk.PolicyType.NEVER)
            self._step_pages[step_id] = scroller
            self._options.add_named(scroller, step_id)

        self._preview_stack = Gtk.Stack(
            transition_type=Gtk.StackTransitionType.CROSSFADE)
        for name, builder in (("desktop", self._preview_desktop),
                              ("motion", self._preview_motion),
                              ("measure", self._preview_measure),
                              ("terminal", self._preview_terminal),
                              ("launcher", self._preview_launcher),
                              ("bar", self._preview_bar),
                              ("notify", self._preview_notify),
                              ("login", self._preview_login)):
            self._preview_stack.add_named(builder(), name)

        preview_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        preview_box.set_margin_top(18)
        preview_box.set_margin_bottom(18)
        preview_box.set_margin_start(12)
        preview_box.set_margin_end(18)
        heading = Gtk.Label(label="Live preview", xalign=0)
        heading.add_css_class("heading")
        preview_box.append(heading)
        self._preview_note = _caption("")
        preview_box.append(self._preview_note)
        self._preview_stack.set_valign(Gtk.Align.START)
        preview_box.append(self._preview_stack)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, wide_handle=True,
                          vexpand=True)
        paned.set_start_child(self._options)
        paned.set_resize_start_child(True)
        paned.set_shrink_start_child(False)
        paned.set_end_child(preview_box)
        paned.set_resize_end_child(True)
        paned.set_shrink_end_child(False)
        paned.set_position(640)
        self.append(paned)

        self.append(Gtk.Separator())
        self.append(self._build_footer())
        self._show_step(0)

    # ============================================================= framework ===
    def _build_header(self) -> Gtk.Widget:
        box = Gtk.Box(spacing=2, halign=Gtk.Align.CENTER)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        self._step_buttons: list[Gtk.Button] = []
        for index, (_id, title, _builder, _preview) in enumerate(self._steps):
            button = Gtk.Button(label=f"{index + 1}. {title}")
            button.add_css_class("flat")
            button.add_css_class("hs-wiz-step")
            button.connect("clicked", lambda _b, i=index: self._show_step(i))
            self._step_buttons.append(button)
            box.append(button)
        scroller = Gtk.ScrolledWindow(child=box,
                                      vscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_propagate_natural_height(True)
        return scroller

    def _build_footer(self) -> Gtk.Widget:
        bar = Gtk.Box(spacing=10)
        bar.set_margin_top(10)
        bar.set_margin_bottom(10)
        bar.set_margin_start(16)
        bar.set_margin_end(16)

        self._back = Gtk.Button(label="Back")
        self._back.connect("clicked", lambda _b: self._show_step(self._index - 1))
        bar.append(self._back)

        self._position = Gtk.Label(hexpand=True, xalign=0)
        self._position.add_css_class("dim-label")
        bar.append(self._position)

        live_label = Gtk.Label(label="Try live on the desktop")
        live_label.set_tooltip_text(
            "While on, every choice is applied to the desktop right away. While off, "
            "only the preview changes; everything is applied together with 'Finish'.")
        bar.append(live_label)
        self._live = Gtk.Switch(active=True, valign=Gtk.Align.CENTER)
        self._live.connect("notify::active", self._on_live_toggled)
        bar.append(self._live)

        self._cancel = Gtk.Button(label="Cancel")
        self._cancel.set_tooltip_text("Reverts everything done since you "
                                      "opened the wizard")
        self._cancel.connect("clicked", lambda _b: self._ask_cancel())
        bar.append(self._cancel)

        self._next = Gtk.Button(label="Next")
        self._next.add_css_class("suggested-action")
        self._next.connect("clicked", self._on_next)
        bar.append(self._next)
        return bar

    def _show_step(self, index: int) -> None:
        index = max(0, min(index, len(self._steps) - 1))
        self._index = index
        step_id, title, _builder, preview = self._steps[index]
        if step_id == "wallpaper":
            self._load_wallpapers()
        if step_id == "summary":
            self._fill_summary()
        if step_id == "start":
            self._refresh_rice_banner()
        if step_id == "login":
            self._fill_login()
        if step_id == "notify":
            self._lock_try.set_sensitive(not self.win._apply_hold)
        self._options.set_visible_child_name(step_id)
        self._preview_stack.set_visible_child_name(preview)
        self._preview_note.set_text(self._PREVIEW_NOTES.get(preview, ""))
        for i, button in enumerate(self._step_buttons):
            for css, on in (("hs-wiz-current", i == index),
                            ("hs-wiz-done", i < index)):
                (button.add_css_class if on else button.remove_css_class)(css)
        self._position.set_text(f"Step {index + 1} / {len(self._steps)} · {title}")
        self._back.set_sensitive(index > 0)
        last = index == len(self._steps) - 1
        self._next.set_label("Finish" if last else "Next")
        self._sync_widgets()

    _PREVIEW_NOTES = {
        "desktop": "Your choices show up instantly on this mock desktop.",
        "motion": "Layout on top; below, the selected animation played with its "
                  "real durations and curves.",
        "measure": "Desktop on top; gap/border/rounding sizes below.",
        "terminal": "A terminal window with the selected colors, font size, "
                    "opacity and cursor.",
        "bar": "The bar at its real size; below, its place on the desktop.",
        "launcher": "The space the launcher takes on screen: width, number of "
                    "rows, position, icons and opacity.",
        "notify": "Notification cards on top (top-right corner), lock screen "
                  "below; both use your palette, corner rounding and font.",
        "login": "A sketch of the login screen. With SDDM, the selected theme's "
                 "own screenshot is shown.",
    }

    def _on_next(self, _button) -> None:
        if self._index < len(self._steps) - 1:
            self._show_step(self._index + 1)
        else:
            self._finish()

    # ============================================================ lifecycle ===
    def on_shown(self) -> None:
        """The page was opened: take a revert point if this is a new session."""
        if self._snapshot is None:
            self._snapshot = self._take_snapshot()
        self._sync_widgets()

    def refresh(self) -> None:
        """The state changed (called by MainWindow._on_state_changed)."""
        for area in self._previews:
            area.queue_draw()
        theme = self.state.get("THEME")
        if theme != self._last_theme:
            self._last_theme = theme
            self._regenerate_pattern()
        if not self._syncing:
            self._sync_cards()

    def _take_snapshot(self) -> dict:
        st = self.state
        return {"values": dict(st.values), "extra": dict(st.extra_values),
                "preset": st.preset, "variant": st.variant,
                "pinned": (st.pinned_bar, st.pinned_term, st.pinned_launcher),
                "selected": set(st.selected),
                "login": copy.deepcopy(self._login_data())}

    def _login_page(self):
        return self.win.stack.get_child_by_name("login")

    def _login_data(self) -> dict:
        page = self._login_page()
        return page.data if page is not None else {}

    def _restore_snapshot(self) -> None:
        snap = self._snapshot
        if snap is None:
            return
        st = self.state
        st.values = dict(snap["values"])
        st.extra_values = dict(snap["extra"])
        st.preset, st.variant = snap["preset"], snap["variant"]
        st.pinned_bar, st.pinned_term, st.pinned_launcher = snap["pinned"]
        st.selected = set(snap["selected"])
        page = self._login_page()
        if page is not None and snap.get("login"):
            page.data = copy.deepcopy(snap["login"])
            page._save()
            page.refresh()
        self._login_apply = False
        st._notify()
        self.win._sync_all_rows()
        self.win._refresh_component_rows()

    def _on_live_toggled(self, switch, _param) -> None:
        self.win.set_apply_hold(not switch.get_active())

    def _finish(self) -> None:
        self._live.set_active(True)          # everything pending is applied now
        self.win.set_apply_hold(False)
        if self._login_apply:
            self._apply_login()
            self._login_apply = False
        self._snapshot = None
        self.win._toast("Setup complete: settings applied")
        self._show_step(0)
        self._snapshot = self._take_snapshot()

    def _ask_cancel(self) -> None:
        if self._snapshot is None or not self._changes():
            self._show_step(0)
            return
        dialog = Adw.AlertDialog(
            heading="Revert the wizard's changes?",
            body="Every choice made since you opened the wizard goes back to how "
                 "it was. If you tried things live, the desktop is restored too.")
        dialog.add_response("keep", "Keep")
        dialog.add_response("revert", "Revert")
        dialog.set_response_appearance("revert", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("keep")
        dialog.connect("response", self._on_cancel_response)
        dialog.present(self.win)

    def _on_cancel_response(self, _dialog, response: str) -> None:
        if response != "revert":
            return
        self._restore_snapshot()
        self._live.set_active(True)
        self.win.set_apply_hold(False)
        self.win._toast("The wizard's changes were reverted")
        self._show_step(0)

    # ============================================================== helpers ===
    def _palette(self) -> dict[str, str]:
        """Preview palette, including the wallpaper ("auto") and manual tone
        (SetupState.palette → render.effective_palette)."""
        return self.state.palette()

    def _set_many(self, values: dict[str, str]) -> None:
        """Write several settings with a single notification (one preview, one apply)."""
        changed = False
        for key, value in values.items():
            if self.state.values.get(key) != value:
                self.state.values[key] = value
                changed = True
        if changed:
            self.state._notify()
            self.win._sync_all_rows()

    def _page_box(self, title: str, text: str) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(18)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(18)
        heading = Gtk.Label(label=title, xalign=0, wrap=True)
        heading.add_css_class("title-2")
        box.append(heading)
        intro = Gtk.Label(label=text, xalign=0, wrap=True)
        intro.add_css_class("dim-label")
        box.append(intro)
        return box

    def _section(self, box: Gtk.Box, title: str, note: str = "") -> None:
        label = Gtk.Label(label=title, xalign=0)
        label.add_css_class("heading")
        label.set_margin_top(8)
        box.append(label)
        if note:
            box.append(_caption(note))

    def _cards(self, options, columns: int = 3, match=None, on_pick=None,
               syncs: list | None = None) -> Gtk.Widget:
        """Big choice cards.

        ``options``: (values, title, description, visual|None). A card shows as
        selected when its values match the state; clicking writes the values.
        If ``match``/``on_pick`` are given, matching and writing use them
        (e.g. component selection or a wallpaper file).
        A radio group is deliberately not used: when no card matches (the
        setting was fine-tuned by hand) all of them must show unselected.
        """
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                           min_children_per_line=min(2, columns),
                           max_children_per_line=columns,
                           row_spacing=8, column_spacing=8,
                           valign=Gtk.Align.START)
        buttons = []
        for values, title, subtitle, visual in options:
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            inner.set_margin_top(8)
            inner.set_margin_bottom(10)
            inner.set_margin_start(10)
            inner.set_margin_end(10)
            if visual is not None:
                inner.append(visual)
            name = Gtk.Label(label=title, xalign=0, wrap=True, max_width_chars=18)
            name.add_css_class("heading")
            comp = (self.state.catalog.component(values["comp"])
                    if "comp" in values else None)
            inner.append(aur_mod.titled(name, comp.aur if comp else None))
            if subtitle:
                inner.append(_caption(subtitle, 22))
            button = Gtk.ToggleButton(child=inner)
            button.add_css_class("card")
            button.add_css_class("hs-wiz-card")
            button.connect("toggled", self._on_card_toggled, values, on_pick)
            buttons.append((button, values))
            flow.append(button)

        def is_match(values) -> bool:
            if match is not None:
                return match(values)
            return all(_same(self.state.get(k), v) for k, v in values.items())

        def sync() -> None:
            for button, values in buttons:
                active = is_match(values)
                if button.get_active() != active:
                    button.set_active(active)

        (self._card_syncs if syncs is None else syncs).append(sync)
        return flow

    def _on_card_toggled(self, button, values, on_pick) -> None:
        if self._syncing:
            return
        if not button.get_active():
            # The selected card was clicked again: keep it selected.
            GLib.idle_add(self._sync_cards)
            return
        if on_pick is not None:
            on_pick(values)
        else:
            self._set_many(dict(values))
        GLib.idle_add(self._sync_cards)

    def _sync_cards(self) -> bool:
        self._syncing = True
        try:
            for sync in self._card_syncs + self._login_syncs:
                sync()
        finally:
            self._syncing = False
        return False

    def _sync_widgets(self) -> None:
        for callback in self._sync.values():
            callback()
        self._sync_cards()
        for area in self._previews:
            area.queue_draw()

    def _rows(self, keys: tuple[str, ...], title: str = "Fine-tuning") -> Gtk.Widget:
        settings = {s.key: s for s in schema.all_settings()}
        group = Adw.PreferencesGroup(title=title)
        for key in keys:
            setting = settings.get(key)
            if setting is not None:
                group.add(self._app.build_setting_row(setting, self.state, self._sync))
        return group

    def _goto_page(self, page_id: str) -> None:
        for index, (pid, _title, _icon) in enumerate(self.win.pages):
            if pid == page_id:
                self.win.listbox.select_row(self.win.listbox.get_row_at_index(index))
                return

    def _link_button(self, label: str, page_id: str) -> Gtk.Button:
        button = Gtk.Button(label=label, halign=Gtk.Align.START)
        button.add_css_class("pill")
        button.connect("clicked", lambda _b: self._goto_page(page_id))
        return button

    # ============================================================= previews ===
    def _framed(self, widget: Gtk.Widget) -> Gtk.Widget:
        self._previews.append(widget)
        frame = Gtk.Frame(child=widget)
        frame.add_css_class("view")
        return frame

    def _desktop(self) -> DesktopPreview:
        view = DesktopPreview(get_setting=self.state.get, get_palette=self._palette,
                              has_component=self.state.category_has_selection,
                              root=self.win.root)
        view.set_content_height(380)
        return view

    def _preview_desktop(self) -> Gtk.Widget:
        return self._framed(self._desktop())

    def _preview_motion(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.append(self._framed(self._desktop()))
        anim = AnimationDiagram(get_setting=self.state.get, get_palette=self._palette)
        anim.set_content_height(230)
        box.append(self._framed(anim))
        return box

    def _preview_measure(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.append(self._framed(self._desktop()))
        diagram = LayoutDiagram(get_setting=self.state.get, get_palette=self._palette)
        diagram.set_content_height(240)
        box.append(self._framed(diagram))
        return box

    def _preview_terminal(self) -> Gtk.Widget:
        term = TerminalPreview(get_setting=self.state.get, get_palette=self._palette)
        term.set_zoom(1.5)
        term.set_content_height(300)
        term.set_vexpand(True)
        return self._framed(term)

    def _preview_bar(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        bar = BarPreview(get_setting=self.state.get, get_palette=self._palette)
        bar.set_content_height(200)
        box.append(self._framed(bar))
        box.append(self._framed(self._desktop()))
        return box

    # ================================================================ steps ===
    # --- start ------------------------------------------------------------
    def _step_start(self) -> Gtk.Widget:
        box = self._page_box(
            "Let's set up your desktop step by step",
            "You'll be asked, in order, about window behavior, wallpaper, colors, "
            "window look, terminal and status bar. Every choice shows up right away "
            "in the preview on the right. Use the titles at the top to move "
            "between steps freely.")

        self._rice_banner = Adw.PreferencesGroup()
        self._rice_row = Adw.ActionRow(title="A profile is active")
        self._rice_row.add_prefix(Gtk.Image.new_from_icon_name("dialog-warning-symbolic"))
        remove = Gtk.Button(label="Remove", valign=Gtk.Align.CENTER)
        remove.add_css_class("destructive-action")
        remove.connect("clicked", lambda _b: self._ask_remove_rice())
        self._rice_row.add_suffix(remove)
        self._rice_banner.add(self._rice_row)
        box.append(self._rice_banner)

        self._section(box, "Where should we start?")
        start = Gtk.Box(spacing=8, homogeneous=True)
        for title, text, action in (
                ("From my current settings", "Choices are made on top of the "
                 "current settings; only what you change changes.",
                 lambda: self._show_step(1)),
                ("From defaults, from scratch", "Look, layout, animation, "
                 "terminal and bar settings go back to their initial values. "
                 "Keyboard, mouse, displays and keybindings are kept.",
                 self._start_fresh)):
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            for margin in ("top", "bottom", "start", "end"):
                getattr(inner, f"set_margin_{margin}")(12)
            name = Gtk.Label(label=title, xalign=0)
            name.add_css_class("title-4")
            inner.append(name)
            inner.append(_caption(text))
            button = Gtk.Button(child=inner)
            button.add_css_class("card")
            button.connect("clicked", lambda _b, a=action: a())
            start.append(button)
        box.append(start)

        self._section(box, "Trying live",
                      "While 'Try live on the desktop' at the bottom is on, every "
                      "choice is also applied to your real desktop right away. If you "
                      "turn it off, only the preview changes and everything is applied "
                      "together with 'Finish' on the last step. Either way, 'Cancel' "
                      "reverts everything.")
        return box

    def _refresh_rice_banner(self) -> None:
        state = rice_mod.read_state()
        self._rice_banner.set_visible(bool(state))
        if state:
            self._rice_row.set_subtitle(
                f"'{state.get('profile')}' is installed right now. Since that profile "
                "uses its author's own configuration, most wizard choices will not "
                "show on the desktop. To set up from scratch, remove it first; your "
                "old files come back from the backup.")

    def _ask_remove_rice(self) -> None:
        state = rice_mod.read_state()
        if not state:
            self._refresh_rice_banner()
            return
        dialog = Adw.AlertDialog(
            heading="Remove the profile?",
            body=f"'{state.get('profile')}' is removed, the author's files are deleted "
                 "and your old files come back from the backup. You can reinstall it "
                 "later from Profiles if you like.")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("go", "Remove")
        dialog.set_response_appearance("go", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _d, r: r == "go" and self._remove_rice())
        dialog.present(self.win)

    def _remove_rice(self) -> None:
        fade = transition_mod.begin(label="Cooking your own desktop…")
        restored = rice_mod.uninstall()
        self.win._toast(f"Profile removed ({len(restored)} files "
                        "restored from the backup)")
        # The profile had stopped your bar when it started its own (see
        # MainWindow._apply_profile_now).
        def restarted() -> None:
            self.win.applier.start_missing(self.state.selected)
            if fade:
                fade.finish()
        self.win._run_apply(then=restarted)
        self._refresh_rice_banner()

    def _start_fresh(self) -> None:
        base = SetupState._base_defaults()
        keys = {s.key for g in schema.GROUPS if g.id in _RESET_GROUPS
                for s in g.settings}
        keys.update(_RESET_EXTRA)
        self._set_many({key: base.get(key, "") for key in keys})
        self.win._toast("Look settings were reset to their initial values")
        self._show_step(1)

    # --- behavior ---------------------------------------------------------
    def _step_behavior(self) -> Gtk.Widget:
        box = self._page_box(
            "How should windows behave?",
            "How new windows are placed on screen, whether focus follows the "
            "mouse, and the character of the motion.")

        self._section(box, "Tiling layout")
        box.append(self._cards((
            ({"LAYOUT": "dwindle"}, "Dwindle",
             "Each new window splits the focused area in two; fills up like a spiral.", None),
            ({"LAYOUT": "master"}, "Master",
             "A big main window on the left, the others stacked on the right.", None),
        ), columns=2))

        self._section(box, "Focus")
        box.append(self._cards((
            ({"FOLLOW_MOUSE": "0"}, "On click", "Focus only moves to the clicked window", None),
            ({"FOLLOW_MOUSE": "1"}, "Follow mouse", "Whichever window the mouse is over", None),
            ({"FOLLOW_MOUSE": "2"}, "Loose", "Keyboard focus stays until you click", None),
        )))

        self._section(box, "Animation character",
                      "The diagram at the bottom right plays the selected set with its "
                      "real durations.")
        box.append(self._cards((
            ({"ANIMATIONS": "true", "ANIMATION_PRESET": "default"}, "Balanced",
             "Medium speed, opens with a slight grow", None),
            ({"ANIMATIONS": "true", "ANIMATION_PRESET": "snappy"}, "Snappy",
             "Very short; instant response", None),
            ({"ANIMATIONS": "true", "ANIMATION_PRESET": "fluid"}, "Fluid",
             "Long, smooth and springy", None),
            ({"ANIMATIONS": "true", "ANIMATION_PRESET": "minimal"}, "Minimal",
             "Fades only", None),
            ({"ANIMATIONS": "false"}, "Off", "No animations at all", None),
        )))
        box.append(self._rows(("ANIMATION_SPEED", "WORKSPACE_COUNT", "MASTER_MFACT",
                               "DWINDLE_PRESERVE_SPLIT", "SNAP", "RESIZE_ON_BORDER")))
        return box

    # --- wallpaper --------------------------------------------------------
    def _step_wallpaper(self) -> Gtk.Widget:
        box = self._page_box(
            "Wallpaper",
            "Pick one of the bundled images, one of your own pictures, or a "
            "pattern generated from your colors. In the next step you can also "
            "choose to extract the colors from this image.")

        self._section(box, "Images",
                      "Souprland's bundled images and those in ~/Pictures/wallpapers. "
                      "The preview only draws PNG; if you pick a JPG it shows on the "
                      "desktop but the preview keeps showing the pattern.")
        pick = Gtk.Button(label="Choose file…", halign=Gtk.Align.START)
        pick.add_css_class("pill")
        pick.connect("clicked", lambda _b: self._choose_file())
        box.append(pick)
        self._wall_flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
                                      homogeneous=True, min_children_per_line=2,
                                      max_children_per_line=4, row_spacing=8,
                                      column_spacing=8, valign=Gtk.Align.START)
        box.append(self._wall_flow)
        self._wall_buttons: list[tuple[Gtk.ToggleButton, Path]] = []

        def sync_walls() -> None:
            current = self._current_wallpaper()
            for button, dest in self._wall_buttons:
                active = current == dest and not self.state.get("WALLPAPER_STYLE")
                if button.get_active() != active:
                    button.set_active(active)

        self._card_syncs.append(sync_walls)

        self._section(box, "Generate from a pattern",
                      "Drawn with the selected color theme; when the theme changes "
                      "the pattern is regenerated with the new colors.")
        options = []
        for style, title in _PATTERNS:
            area = Gtk.DrawingArea(content_width=150, content_height=84)
            area.set_draw_func(self._draw_pattern, style)
            self._previews.append(area)
            options.append(({"WALLPAPER_STYLE": style}, title, "", area))
        box.append(self._cards(
            options, columns=4,
            match=lambda v: self.state.get("WALLPAPER_STYLE") == v["WALLPAPER_STYLE"],
            on_pick=lambda v: self._use_pattern(v["WALLPAPER_STYLE"])))

        box.append(self._rows(("SWWW_TRANSITION", "SWWW_TRANSITION_DURATION",
                               "WALLPAPER_ROTATE", "WALLPAPER_DIR")))
        return box

    def _current_wallpaper(self) -> Path:
        return Path(self.state.get("WALLPAPER_PATH") or "").expanduser()

    def _wallpaper_sources(self) -> list[tuple[Path, Path]]:
        """(file shown, path written to WALLPAPER_PATH when selected)."""
        out: list[tuple[Path, Path]] = []
        dest_dir = self.home / "Pictures" / "wallpapers"
        for path in sorted((self.win.root / "wallpapers").glob("*.png")):
            out.append((path, dest_dir / f"souprland-{path.name}"))
        seen = {dest for _src, dest in out}
        for folder in (dest_dir, self.home / "Pictures" / "Wallpapers"):
            if not folder.is_dir():
                continue
            for path in sorted(folder.iterdir()):
                if (path.suffix.lower() in _IMAGE_SUFFIXES and path not in seen
                        and not path.name.startswith("souprland-")):
                    out.append((path, path))
                    seen.add(path)
        return out[:120]

    def _load_wallpapers(self) -> None:
        """Thumbnails load one by one on first open, without blocking the UI."""
        if self._wall_loaded:
            return
        self._wall_loaded = True
        queue = list(self._wallpaper_sources())

        def load_next() -> bool:
            if not queue:
                self._sync_cards()
                return False
            src, dest = queue.pop(0)
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(src), 240, 135, True)
                texture = Gdk.Texture.new_for_pixbuf(pixbuf)
            except GLib.Error:
                return True
            picture = Gtk.Picture.new_for_paintable(texture)
            picture.set_content_fit(Gtk.ContentFit.COVER)
            picture.set_size_request(150, 84)
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            for margin in ("top", "bottom", "start", "end"):
                getattr(inner, f"set_margin_{margin}")(6)
            inner.append(picture)
            name = Gtk.Label(label=src.stem.removeprefix("souprland-"), xalign=0,
                             ellipsize=Pango.EllipsizeMode.END)
            name.add_css_class("caption")
            inner.append(name)
            button = Gtk.ToggleButton(child=inner)
            button.add_css_class("card")
            button.add_css_class("hs-wiz-card")
            button.connect("toggled", self._on_wall_toggled, src, dest)
            self._wall_buttons.append((button, dest))
            self._wall_flow.append(button)
            return True

        GLib.idle_add(load_next)

    def _on_wall_toggled(self, button, src: Path, dest: Path) -> None:
        if self._syncing:
            return
        if button.get_active():
            self._use_wallpaper(src, dest)
        GLib.idle_add(self._sync_cards)

    def _use_wallpaper(self, src: Path, dest: Path) -> None:
        if src != dest:
            # The repo image is copied: if WALLPAPER_PATH pointed into the repo
            # folder, the desktop would go blank when the repo is moved.
            try:
                if not dest.is_file() or dest.read_bytes() != src.read_bytes():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, dest)
            except OSError as exc:
                self.win._toast(f"Could not copy the wallpaper: {exc}")
                return
        self._set_many({"WALLPAPER_PATH": self._tilde(dest),
                        "WALLPAPER_IMAGE": "", "WALLPAPER_STYLE": ""})

    def _tilde(self, path: Path) -> str:
        try:
            return "~/" + str(path.relative_to(self.home))
        except ValueError:
            return str(path)

    def _choose_file(self) -> None:
        pick_file(self.win, "Choose wallpaper", lambda path: self._use_wallpaper(path, path),
                  filter_name="Images", suffixes=_IMAGE_SUFFIXES)

    def _draw_pattern(self, _area, cr, width, height, style: str) -> None:
        theme = self.state.get("THEME") or themes.DEFAULT
        if theme == "auto":
            theme = themes.DEFAULT
        surface = _wallpaper_surface(theme, style, "", self.state.get("CUSTOM_COLORS"))
        if surface is None:
            return
        cr.scale(width / surface.get_width(), height / surface.get_height())
        cr.set_source_surface(surface, 0, 0)
        cr.paint()

    def _pattern_target(self, style: str) -> Path:
        theme = self.state.get("THEME") or themes.DEFAULT
        extra = self.state.get("CUSTOM_COLORS")
        suffix = f"-{hashlib.md5(extra.encode()).hexdigest()[:6]}" if extra else ""
        return (self.home / "Pictures" / "wallpapers"
                / f"souprland-{style}-{theme}{suffix}.png")

    def _use_pattern(self, style: str) -> None:
        """Generate the pattern at full size (1–2 s, in the background), then select it."""
        theme = self.state.get("THEME") or themes.DEFAULT
        if theme == "auto":
            theme = themes.DEFAULT
        target = self._pattern_target(style)
        overrides = self.state.get("CUSTOM_COLORS")
        self._pattern_job += 1
        job = self._pattern_job
        if target.is_file():
            self._set_many({"WALLPAPER_STYLE": style, "WALLPAPER_IMAGE": "",
                            "WALLPAPER_PATH": self._tilde(target)})
            return
        self.win._set_apply_status("Generating pattern…")

        def work() -> None:
            error = ""
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                wallpaper_mod.generate(theme, style, target, overrides=overrides)
            except (OSError, ValueError) as exc:
                error = str(exc)
            GLib.idle_add(done, error)

        def done(error: str) -> bool:
            if job != self._pattern_job:
                return False          # another choice was made meanwhile
            if error:
                self.win._toast(f"Could not generate the pattern: {error}")
                return False
            self._set_many({"WALLPAPER_STYLE": style, "WALLPAPER_IMAGE": "",
                            "WALLPAPER_PATH": self._tilde(target)})
            return False

        threading.Thread(target=work, daemon=True).start()

    def _regenerate_pattern(self) -> None:
        """The theme changed: if a wizard-generated pattern is selected,
        regenerate it with the new colors (the user's own image is not touched)."""
        style = self.state.get("WALLPAPER_STYLE")
        if not style or self.state.get("THEME") == "auto":
            return
        if not self._current_wallpaper().name.startswith(f"souprland-{style}-"):
            return
        self._use_pattern(style)

    # --- colors -----------------------------------------------------------
    def _step_colors(self) -> Gtk.Widget:
        box = self._page_box(
            "Colors",
            "The chosen palette is applied together to window borders, the bar, "
            "the terminal, the launcher and notifications.")

        self._section(box, "Dark or light apps?",
                      "The mode of GTK/Qt apps; independent of the palette.")
        box.append(self._cards((
            ({"COLOR_SCHEME": "dark"}, "Dark", "Apps open in dark mode", None),
            ({"COLOR_SCHEME": "light"}, "Light", "Apps open in light mode", None),
        ), columns=2))

        self._section(box, "Palette")
        self._auto_strip = PaletteStrip(None, width=150, height=70, label="auto")
        options = [({"THEME": "auto", "CUSTOM_COLORS": ""}, "From the wallpaper",
                    "Colors change when the image changes", self._auto_strip)]
        for name in themes.names():
            options.append(({"THEME": name, "CUSTOM_COLORS": ""}, name, "",
                            PaletteStrip(themes.THEMES[name], width=150, height=70)))
        box.append(self._cards(
            options, columns=3,
            match=lambda v: self.state.get("THEME") == v["THEME"]))

        self._section(box, "Adjust the tone",
                      "Shifts the whole selected palette, including colors taken "
                      "from the wallpaper. Windows, the bar, the terminal and GTK/Qt "
                      "apps change together.")
        box.append(self._rows(("PALETTE_HUE", "PALETTE_SATURATION",
                               "PALETTE_LIGHTNESS"), title=""))
        box.append(WallpaperSwatches(self.win))

        expander = Adw.ExpanderRow(title="Change colors one by one",
                                   subtitle="Manual edits on top of the selected palette")
        for row in self.win._colour_rows():
            expander.add_row(row)
        group = Adw.PreferencesGroup()
        group.add(expander)
        box.append(group)

        def sync_auto() -> None:
            if self.state.get("THEME") == "auto":
                self._auto_strip._palette = self._palette()
            else:
                self._auto_strip._palette = None
            self._auto_strip.queue_draw()

        self._card_syncs.append(sync_auto)
        return box

    # --- window look ------------------------------------------------------
    def _step_look(self) -> Gtk.Widget:
        box = self._page_box(
            "Window look",
            "Pick an overall style first, then fine-tune any size below. When "
            "you change something by hand the cards above get deselected; that's "
            "normal, you now have your own style.")
        self._section(box, "Style")
        box.append(self._cards([(v, t, s, None) for v, t, s in _LOOKS], columns=2))
        self._section(box, "Gaps")
        box.append(self._cards([(v, t, s, None) for v, t, s in _GAPS]))
        box.append(self._rows(("GAPS_IN", "GAPS_OUT", "BORDER_SIZE", "ROUNDING",
                               "SHADOW", "BLUR", "BLUR_SIZE", "ACTIVE_OPACITY",
                               "INACTIVE_OPACITY", "DIM_INACTIVE")))
        return box

    # --- terminal ---------------------------------------------------------
    def _step_terminal(self) -> Gtk.Widget:
        box = self._page_box(
            "Terminal",
            "Which terminal to use and how it looks. Colors come from the "
            "palette you chose.")
        axis = self._app._APP_AXES["terminal"]
        options = [({"comp": comp_id}, label, axis["summary"].get(comp_id, ""), None)
                   for comp_id, label in axis["apps"]]
        self._section(box, "Program",
                      "If you pick one that is not installed, you are offered to install it first.")
        box.append(self._cards(
            options, columns=3,
            match=lambda v: self.state.is_selected(v["comp"]),
            on_pick=lambda v: self._pick_component(v["comp"])))

        self._section(box, "Font")
        box.append(self._cards(
            [({"FONT_MONO": family}, label, family, None) for family, label in _MONO_FONTS],
            columns=2))
        entry = Adw.EntryRow(title="Another monospace font")
        entry.connect("apply", lambda r: self.state.set("FONT_MONO", r.get_text()))
        entry.set_show_apply_button(True)
        self._sync["FONT_MONO"] = lambda: entry.set_text(self.state.get("FONT_MONO"))
        group = Adw.PreferencesGroup()
        group.add(entry)
        box.append(group)

        self._section(box, "Cursor")
        box.append(self._cards((
            ({"TERM_CURSOR_STYLE": "block"}, "Block", "█", None),
            ({"TERM_CURSOR_STYLE": "beam"}, "Beam", "|", None),
            ({"TERM_CURSOR_STYLE": "underline"}, "Underline", "_", None),
        )))
        box.append(self._rows(("TERM_FONT_SIZE", "TERM_OPACITY", "TERM_PADDING",
                               "TERM_CURSOR_BLINK", "TERM_SCROLLBACK")))
        return box

    def _pick_component(self, comp_id: str) -> None:
        def chosen() -> None:
            self.state.toggle(comp_id, True)
            self.win._refresh_component_rows()

        # If the package is not installed the user is asked; if they cancel,
        # the state does not change and the cards return to the old choice.
        self.win._require_component(comp_id, chosen)

    # --- bar --------------------------------------------------------------
    def _step_bar(self) -> Gtk.Widget:
        box = self._page_box(
            "Status bar",
            "Where the bar sits, how workspaces are shown, and its sizes. To place "
            "modules one by one or pick a bar preset, the links below open the "
            "relevant page.")
        self._section(box, "Position")
        box.append(self._cards((
            ({"BAR_POSITION": "top"}, "Top", "", None),
            ({"BAR_POSITION": "bottom"}, "Bottom", "", None),
            ({"BAR_POSITION": "left"}, "Left", "Vertical", None),
            ({"BAR_POSITION": "right"}, "Right", "Vertical", None),
        ), columns=4))
        self._section(box, "Workspace indicator")
        box.append(self._cards((
            ({"BAR_WORKSPACE_STYLE": "numbers"}, "Numbers", "1 2 3", None),
            ({"BAR_WORKSPACE_STYLE": "dots"}, "Dots", "● ○ ○", None),
            ({"BAR_WORKSPACE_STYLE": "roman"}, "Roman", "I II III", None),
            ({"BAR_WORKSPACE_STYLE": "pill-expand"}, "Active expands", "━ ● ●", None),
            ({"BAR_WORKSPACE_STYLE": "underline"}, "Underlined", "1̲ 2 3", None),
            ({"BAR_WORKSPACE_STYLE": "app-icons"}, "Window icons", "", None),
        )))
        box.append(self._rows(("BAR_HEIGHT", "BAR_WIDTH", "BAR_MARGIN", "BAR_SPACING",
                               "BAR_RADIUS", "BAR_OPACITY", "BAR_CLOCK_FORMAT",
                               "BAR_AUTOHIDE")))
        self._section(box, "Dock",
                      "A second bar floating at the screen edge that holds only "
                      "app icons. Independent of which status bar you chose.")
        box.append(self._rows(("DOCK_ENABLE", "DOCK_POSITION", "DOCK_AUTOHIDE",
                               "DOCK_ICON_SIZE"), title=""))
        links = Gtk.Box(spacing=8)
        links.append(self._link_button("Bar presets", "bars"))
        links.append(self._link_button("Edit modules", "bar"))
        box.append(links)
        return box

    # --- launcher ------------------------------------------------------------
    def _step_launcher(self) -> Gtk.Widget:
        box = self._page_box(
            "App launcher",
            "The app search window opened with a shortcut. Program, position on "
            "screen and size; colors come from your palette.")
        axis = self._app._APP_AXES["launcher"]
        options = []
        for comp_id, label in axis["apps"]:
            mock = LauncherPreview(comp_id, self._palette)
            mock.set_content_width(150)
            mock.set_content_height(84)
            mock.set_halign(Gtk.Align.START)
            self._previews.append(mock)
            options.append(({"comp": comp_id}, label,
                            axis["summary"].get(comp_id, ""), mock))
        self._section(box, "Program",
                      "If you pick one that is not installed, you are offered to install it first.")
        box.append(self._cards(
            options, columns=3,
            match=lambda v: self.state.is_selected(v["comp"]),
            on_pick=lambda v: self._pick_component(v["comp"])))
        self._section(box, "Position")
        box.append(self._cards((
            ({"LAUNCHER_POSITION": "center"}, "Center", "Opens in the middle of the screen", None),
            ({"LAUNCHER_POSITION": "top"}, "Top", "Drops down from the top edge", None),
        ), columns=2))
        box.append(self._rows(("LAUNCHER_WIDTH", "LAUNCHER_LINES", "LAUNCHER_OPACITY",
                               "LAUNCHER_ICONS", "LAUNCHER_ICON_SIZE",
                               "LAUNCHER_PROMPT")))
        box.append(self._link_button("Launcher presets", "launcher"))
        return box

    def _preview_launcher(self) -> Gtk.Widget:
        view = LauncherLayoutPreview(get_setting=self.state.get,
                                     get_palette=self._palette)
        view.set_content_height(380)
        return self._framed(view)

    # --- notifications and lock ---------------------------------------------
    def _step_notify(self) -> Gtk.Widget:
        box = self._page_box(
            "Notifications and lock screen",
            "Neither has its own color settings: they use your palette, corner "
            "rounding and font. Here you pick the program and what happens when "
            "the computer is idle.")
        self._section(box, "Notification program")
        box.append(self._cards(
            [({"comp": comp}, label, text, None) for comp, label, text in _NOTIFIERS],
            columns=3,
            match=lambda v: self.state.is_selected(v["comp"]),
            on_pick=lambda v: self._pick_component(v["comp"])))
        test = Gtk.Button(label="Send a test notification", halign=Gtk.Align.START)
        test.add_css_class("pill")
        test.set_tooltip_text("Sends a notification to your real notification program. "
                              "In preview mode it still arrives with the old look.")
        test.connect("clicked", lambda _b: self._send_test_notification())
        box.append(test)

        self._section(box, "When idle",
                      "In seconds; 0 turns that step off.")
        box.append(self._rows(("IDLE_DIM", "IDLE_LOCK", "IDLE_DPMS", "IDLE_SUSPEND"),
                              title=""))
        self._lock_try = Gtk.Button(label="Try the lock screen now",
                                    halign=Gtk.Align.START)
        self._lock_try.add_css_class("pill")
        self._lock_try.set_tooltip_text(
            "Really locks the screen; unlock it with your password. Disabled in "
            "preview mode, because the new look has not been written yet.")
        self._lock_try.connect("clicked", lambda _b: self._ask_lock())
        box.append(self._lock_try)
        return box

    def _preview_notify(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        note = NotificationPreview(self.state.get, self._palette,
                                   lambda: self.state.primary("notify"))
        note.set_content_height(300)
        box.append(self._framed(note))
        lock = LockPreview(self.state.get, self._palette)
        lock.set_content_height(300)
        box.append(self._framed(lock))
        return box

    def _send_test_notification(self) -> None:
        if not shutil.which("notify-send"):
            self.win._toast("notify-send not found (is libnotify installed?)")
            return
        subprocess.Popen(["notify-send", "-a", "Souprland", "Souprland",
                          "This is a test notification; this is how it looks."],
                         start_new_session=True)

    def _ask_lock(self) -> None:
        dialog = Adw.AlertDialog(
            heading="Lock the screen?",
            body="The lock screen opens right away; enter your password to come back.")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("lock", "Lock")
        dialog.set_response_appearance("lock", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _d, r: r == "lock" and self._lock_now())
        dialog.present(self.win)

    def _lock_now(self) -> None:
        argv = (["hyprlock"] if shutil.which("hyprlock")
                else ["loginctl", "lock-session"])
        try:
            subprocess.Popen(argv, start_new_session=True)
        except OSError as exc:
            self.win._toast(f"Could not lock: {exc}")

    # --- login screen --------------------------------------------------------
    def _step_login(self) -> Gtk.Widget:
        # The content is built each time the step opens (_fill_login): the login
        # manager or installed themes may have changed outside the wizard, and
        # the Login Screen page is created after this page.
        self._login_box = self._page_box(
            "Login screen",
            "The screen that asks for your password when the computer starts. "
            "Since it is a system file it is not applied right away: pressing "
            "'Finish' opens a terminal where your password is asked.")
        self._login_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self._login_box.append(self._login_body)
        return self._login_box

    def _preview_login(self) -> Gtk.Widget:
        self._login_preview = Gtk.Stack()
        greeter = GreeterPreview(self.state.get, self._palette, self._greeter_choice)
        greeter.set_content_height(380)
        self._login_preview.add_named(self._framed(greeter), "greeter")
        self._sddm_picture = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN,
                                         height_request=380)
        frame = Gtk.Frame(child=self._sddm_picture)
        frame.add_css_class("view")
        self._login_preview.add_named(frame, "sddm")
        return self._login_preview

    def _greeter_choice(self) -> tuple[str, bool, bool]:
        saved = self._login_data().get("plasmalogin", {})
        return (saved.get("wallpaper", "keep"), bool(saved.get("show_clock", True)),
                saved.get("colors", "keep") == "palette")

    def _fill_login(self) -> None:
        while (child := self._login_body.get_first_child()) is not None:
            self._login_body.remove(child)
        self._login_syncs = []
        page = self._login_page()
        manager = login.current_manager()
        body = self._login_body

        switch = Adw.SwitchRow(
            title="Also apply the login screen on 'Finish'",
            subtitle="If off, this step's choices are saved but not written to the "
                     "system; you can apply them later from the Login Screen page.")
        switch.set_active(self._login_apply)
        switch.connect("notify::active",
                       lambda r, _p: setattr(self, "_login_apply", r.get_active()))
        self._login_switch = switch
        top = Adw.PreferencesGroup()
        top.add(switch)
        body.append(top)

        if page is None or manager not in ("plasmalogin", "sddm"):
            name = login.MANAGERS.get(manager, manager) if manager else "unknown"
            body.append(_caption(
                f"Active login manager: {name}. The wizard can configure SDDM and "
                "Plasma Login; switching and other options are on the Login Screen page."))
            switch.set_sensitive(False)
        elif manager == "plasmalogin":
            self._fill_plasma(page)
        else:
            self._fill_sddm(page)
        body.append(self._link_button("All details on the Login Screen page", "login"))
        self._login_preview.set_visible_child_name(
            "sddm" if manager == "sddm" else "greeter")
        self._sync_cards()

    def _login_changed(self) -> None:
        if not self._login_apply:
            self._login_switch.set_active(True)
        self._sync_cards()
        for area in self._previews:
            area.queue_draw()

    def _fill_plasma(self, page) -> None:
        body = self._login_body
        body.append(_caption("Active login manager: Plasma Login (KDE)."))
        saved = page.data["plasmalogin"]

        def setter(key):
            def pick(values) -> None:
                page._plasma_set(key, values[key])
                page._build_plasma()
                self._login_changed()
            return pick

        def matcher(key, default):
            return lambda v: saved.get(key, default) == v[key]

        self._section(body, "Background")
        body.append(self._cards((
            ({"wallpaper": "wallpaper"}, "My wallpaper", "The image on the desktop", None),
            ({"wallpaper": "color"}, "Solid color", "My palette's background color", None),
            ({"wallpaper": "keep"}, "Don't change", "The current background stays", None),
        ), match=matcher("wallpaper", "keep"), on_pick=setter("wallpaper"),
            syncs=self._login_syncs))
        self._section(body, "Colors")
        body.append(self._cards((
            ({"colors": "palette"}, "My palette", "The same colors as the desktop", None),
            ({"colors": "keep"}, "Don't change", "KDE's current color scheme", None),
        ), columns=2, match=matcher("colors", "keep"), on_pick=setter("colors"),
            syncs=self._login_syncs))
        clock = Adw.SwitchRow(title="Show clock")
        clock.set_active(bool(saved.get("show_clock", True)))

        def on_clock(row, _p) -> None:
            page._plasma_set("show_clock", row.get_active())
            page._build_plasma()
            self._login_changed()

        clock.connect("notify::active", on_clock)
        group = Adw.PreferencesGroup()
        group.add(clock)
        body.append(group)

    def _fill_sddm(self, page) -> None:
        body = self._login_body
        body.append(_caption("Active login manager: SDDM. Pick one of the installed "
                             "themes; new ones are installed from the Login Screen page."))
        options = []
        for theme in page.themes:
            shot = theme.screenshot or (login.preview_image(page.root, theme.catalog.id)
                                        if theme.catalog else None)
            visual = None
            if shot:
                picture = Gtk.Picture.new_for_filename(str(shot))
                picture.set_content_fit(Gtk.ContentFit.COVER)
                picture.set_size_request(150, 84)
                visual = picture
            options.append(({"theme": theme.id}, theme.name, "", visual))

        def pick(values) -> None:
            page.data["sddm"]["selected"] = values["theme"]
            page._save()
            page.refresh()
            self._show_sddm_shot(page)
            self._login_changed()

        self._section(body, "Theme")
        body.append(self._cards(options, match=lambda v: page._selected_dir() == v["theme"],
                                on_pick=pick, syncs=self._login_syncs))
        group = Adw.PreferencesGroup()
        for attr, title, subtitle in (
                ("_sddm_paint", "Take colors from my palette",
                 "The theme's color fields are filled with your desktop palette"),
                ("_sddm_wall", "Background: my wallpaper",
                 "The theme's background image becomes your desktop wallpaper")):
            row = Adw.SwitchRow(title=title, subtitle=subtitle)
            row.set_active(getattr(self, attr))
            row.connect("notify::active",
                        lambda r, _p, a=attr: setattr(self, a, r.get_active()))
            group.add(row)
        body.append(group)
        real = Gtk.Button(label="Real preview (sddm-greeter)", halign=Gtk.Align.START)
        real.add_css_class("pill")
        real.set_tooltip_text("Opens the theme in a window in SDDM's test mode; "
                              "nothing is written to the system.")
        real.connect("clicked", lambda _b: self._sddm_real_preview(page))
        body.append(real)
        self._show_sddm_shot(page)

    def _show_sddm_shot(self, page) -> None:
        theme, _preset = page._current()
        shot = None
        if theme is not None:
            shot = theme.screenshot or (login.preview_image(page.root, theme.catalog.id)
                                        if theme.catalog else None)
        self._sddm_picture.set_filename(str(shot) if shot else None)

    def _sddm_edits(self, page) -> None:
        """Write the my-palette / my-wallpaper choices into the theme's edits."""
        theme, preset = page._current()
        if theme is None:
            return
        edits = page._edits(theme, preset)
        if self._sddm_paint:
            edits.update(login.palette_edits(theme, page._variables()))
        image = page._wallpaper()
        if self._sddm_wall and image is not None:
            edits.update(login.background_edits(theme, image))
        page._save()

    def _sddm_real_preview(self, page) -> None:
        self._sddm_edits(page)
        page._on_preview()

    def _login_plan(self) -> str:
        manager = login.current_manager()
        page = self._login_page()
        if manager == "plasmalogin" and page is not None:
            saved = page.data["plasmalogin"]
            labels = {"wallpaper": "my wallpaper", "color": "solid color",
                      "keep": "same background", "file": "chosen image"}
            return (f"Plasma Login — {labels.get(saved.get('wallpaper', 'keep'), '')}"
                    f", colors {'my palette' if saved.get('colors') == 'palette' else 'unchanged'}")
        if manager == "sddm" and page is not None:
            theme, _preset = page._current()
            return f"SDDM — {theme.name if theme else 'no theme'}"
        return manager or "—"

    def _apply_login(self) -> None:
        page = self._login_page()
        if page is None:
            return
        manager = login.current_manager()
        if manager == "plasmalogin":
            page._on_plasma_apply()
        elif manager == "sddm":
            self._sddm_edits(page)
            page.refresh()
            page._on_apply()

    # --- summary ------------------------------------------------------------
    def _step_summary(self) -> Gtk.Widget:
        box = self._page_box(
            "Summary",
            "What changed since you opened the wizard. 'Finish' applies all of it; "
            "'Cancel' reverts all of it.")
        self._summary_group = Adw.PreferencesGroup(title="Changes")
        box.append(self._summary_group)
        self._summary_rows: list[Gtk.Widget] = []

        self._section(box, "What's next?",
                      "Topics the wizard doesn't ask about are on their own pages:")
        links = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
                            max_children_per_line=3, column_spacing=8, row_spacing=8)
        for label, page_id in (("Keybindings", "keybinds"), ("Widgets", "widgets"),
                               ("Displays", "monitors"), ("Applications", "apps"),
                               ("Wallpaper Colors", "wallcolors"),
                               ("Night light and recording", "session")):
            links.append(self._link_button(label, page_id))
        box.append(links)
        return box

    def _changes(self) -> list[tuple[str, str, str]]:
        if self._snapshot is None:
            return []
        before = self._snapshot["values"]
        # "Position" exists for both the bar and the launcher: prefix the group name.
        labels = {s.key: f"{g.title} › {s.label}" for g in schema.GROUPS
                  for s in g.settings}
        labels.update({"THEME": "Color palette", "COLOR_SCHEME": "App mode",
                       "FONT_MONO": "Terminal font",
                       "CUSTOM_COLORS": "Manually edited colors"})
        out = []
        for key in sorted(set(before) | set(self.state.values)):
            old, new = before.get(key, ""), self.state.values.get(key, "")
            if not _same(old, new):
                out.append((labels.get(key, key), old, new))
        was, now = self._snapshot["selected"], self.state.selected
        catalog = self.state.catalog
        for comp_id in sorted(now - was):
            comp = catalog.component(comp_id)
            out.append(("Added program", "", comp.title if comp else comp_id))
        for comp_id in sorted(was - now):
            comp = catalog.component(comp_id)
            out.append(("Dropped program", comp.title if comp else comp_id, ""))
        if self._login_apply:
            out.append(("Login screen", "", self._login_plan() + " (on Finish; password is asked)"))
        return out

    def _fill_summary(self) -> None:
        for row in self._summary_rows:
            self._summary_group.remove(row)
        self._summary_rows = []
        changes = self._changes()
        if not changes:
            changes = [("No changes yet", "", "")]

        def short(text: str) -> str:
            text = text or "—"
            return text if len(text) <= 72 else text[:69] + "…"

        for label, old, new in changes:
            row = Adw.ActionRow(title=GLib.markup_escape_text(label))
            if old or new:
                row.set_subtitle(GLib.markup_escape_text(f"{short(old)}  →  {short(new)}"))
            self._summary_group.add(row)
            self._summary_rows.append(row)
