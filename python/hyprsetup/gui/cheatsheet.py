"""Keybinding cheat sheet: ``hyprsetup cheatsheet`` (opened with {{MOD_KEY}} + /).

The source is ``config/keybinds.json``, NOT the generated ``keybinds.conf``:
that way the sheet can show each binding's human-written name ("Screenshot of
a selected region"). The old help script grepped the generated file and
printed dispatcher names, and an "exec, grim -g ..." line does not tell the
user what the binding does.

The list shown is the bindings that are ACTUALLY active: ``KEYBINDS``
overrides are applied, and bindings whose ``require`` condition is not met
(tied to an unselected component, or specific to another bar backend) are not
drawn at all.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from ..catalog import Catalog  # noqa: E402
from .. import keybinds as keybinds_mod  # noqa: E402
from .. import render as render_mod  # noqa: E402
from .state import SetupState, config_candidates, config_path  # noqa: E402
from .util import ensure_css  # noqa: E402

APP_ID = "dev.hyprsetup.Cheatsheet"

#: X keysym name → character shown on the sheet. keybinds.json stores keys
#: by keysym name (that is what Hyprland wants); "slash" on the sheet does
#: not tell the user which key to press.
_KEY_GLYPHS = {
    "slash": "/", "backslash": "\\", "comma": ",", "period": ".",
    "semicolon": ";", "apostrophe": "'", "grave": "`", "minus": "-",
    "equal": "=", "bracketleft": "[", "bracketright": "]",
    "Return": "⏎", "space": "␣", "Escape": "Esc", "Delete": "Del",
    "Print": "PrtSc", "Tab": "⇥",
    "left": "←", "right": "→", "up": "↑", "down": "↓",
    "mouse_up": "wheel ↑", "mouse_down": "wheel ↓",
    "mouse:272": "left click", "mouse:273": "right click",
}


def _keycap(part: str) -> str:
    return _KEY_GLYPHS.get(part, part)

_CSS = """
.hs-keycap {
    background-color: alpha(currentColor, 0.10);
    border: 1px solid alpha(currentColor, 0.18);
    border-radius: 6px;
    padding: 1px 7px;
    font-family: monospace;
    font-size: 0.85em;
}
.hs-keycap-changed {
    border-color: @accent_color;
    color: @accent_color;
}
.hs-cheat-row label {
    font-weight: normal;              /* plain text, not button bold */
}
.hs-cheat-row {
    padding: 3px 6px;
    min-height: 0;
    border-radius: 8px;
}
.hs-cheat-card {
    background-color: alpha(currentColor, 0.04);
    border-radius: 12px;
    padding: 12px;
}
"""


@dataclass
class Row:
    combo: str                 # as shown on the sheet ("SUPER + SHIFT + S")
    title: str
    bind_id: str = ""          # empty = not editable (numbered workspace keys)
    changed: bool = False      # differs from the default via KEYBINDS


def resolved_binds(root: Path, catalog_path: Path):
    """(mod key, [(category, [Row])], {combo: title}): the active bindings.

    Variables go through the same path the settings app uses
    (Applier.export_vars + render.derived_vars), so ``require`` conditions mean
    the same thing here as there. If the two diverged, the sheet would show a
    binding that does not work. The third value is for conflict checks: every
    normalized active combo → name of the binding that uses it.
    """
    from ..apply import Applier

    catalog = Catalog.load(catalog_path)
    state = SetupState(catalog)
    for candidate in config_candidates():
        if state.load_conf(candidate):
            break

    binds = keybinds_mod.load_default(root)

    selected = list(state.selected)
    values, _skipped = Applier(root, catalog, binds).export_vars(
        dict(state.values), selected)
    variables = render_mod.derived_vars(values, catalog, selected, binds)

    mod_key = values.get("MOD_KEY") or "SUPER"
    overrides = keybinds_mod.parse_overrides(values.get("KEYBINDS", ""))
    resolved = keybinds_mod.resolve(binds, variables, overrides)

    # Category order is the catalog order; the sheet follows it.
    order = [c.id for c in binds.categories]
    titles = {c.id: c.title for c in binds.categories}
    grouped: dict[str, list[Row]] = {cid: [] for cid in order}
    used: dict[str, str] = {}
    for item in resolved:
        used.setdefault(item.keys, item.bind.title)
        if item.bind.hidden:
            continue
        combo = keybinds_mod.display(item.keys, mod_key)
        # A press-and-release binding (MOD+Super_L, flags r) is a single key on the sheet.
        if item.keys.split("+")[-1] in ("Super_L", "Super_R"):
            combo = mod_key
        grouped.setdefault(item.bind.category, []).append(Row(
            combo, item.bind.title,
            item.bind.id if item.bind.editable else "",
            item.bind.id in overrides))

    # Numbered workspace keys are not in keybinds.json; render.py generates
    # them from WORKSPACE_COUNT. Show them on the sheet anyway.
    try:
        count = max(1, min(20, int(values.get("WORKSPACE_COUNT") or 10)))
    except ValueError:
        count = 10
    last = "0" if count >= 10 else str(count)
    numbered = [Row(f"{mod_key} + 1…{last}", "Go to workspace"),
                Row(f"{mod_key} + ALT + 1…{last}", "Move window to that workspace")]
    if count > 10:
        high = "0" if count == 20 else str(count - 10)
        numbered += [Row(f"{mod_key} + CTRL + 1…{high}", "Go to workspace 11+"),
                     Row(f"{mod_key} + CTRL + ALT + 1…{high}",
                         "Move window to workspace 11+")]
    grouped.setdefault("workspace", [])[:0] = numbered
    for i in range(1, count + 1):
        digit = str(i % 10)
        mods = "MOD+CTRL+" if i > 10 else "MOD+"
        used.setdefault(f"{mods}{digit}", "Go to workspace")
        used.setdefault(keybinds_mod.normalize(f"{mods}ALT+{digit}"),
                        "Move window to that workspace")
    return mod_key, [(titles.get(cid, cid), rows)
                     for cid, rows in grouped.items() if rows], used


def save_override(root: Path, catalog_path: Path, bind_id: str,
                  combo: str | None) -> None:
    """Write a single binding into KEYBINDS and apply the settings right away.

    ``combo`` None → back to default, "" → remove the binding. Writes to the
    same file (settings.conf) in the same format as the settings app's
    Keybindings page.
    """
    from ..apply import Applier

    catalog = Catalog.load(catalog_path)
    binds = keybinds_mod.Keybinds.load(keybinds_mod.default_path(root))
    bind = binds.by_id()[bind_id]
    state = SetupState(catalog)
    path = config_path()
    for candidate in config_candidates():
        if state.load_conf(candidate):
            break
    overrides = keybinds_mod.parse_overrides(state.get("KEYBINDS"))
    if combo is None or keybinds_mod.normalize(combo) == keybinds_mod.normalize(bind.keys):
        overrides.pop(bind_id, None)
    else:
        overrides[bind_id] = keybinds_mod.normalize(combo)
    state.set("KEYBINDS", keybinds_mod.format_overrides(overrides))
    state.save_conf(path)
    Applier(root, catalog, binds).apply(state.values, sorted(state.selected))


_MODIFIER_KEYNAMES = {
    "Super_L", "Super_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
    "Shift_L", "Shift_R", "Meta_L", "Meta_R", "ISO_Level3_Shift",
    "Caps_Lock", "Num_Lock",
}


class CaptureDialog(Adw.Window):
    """Capture a new key combination.

    While the window is open, system shortcuts are inhibited
    (keyboard-shortcuts-inhibit): otherwise Hyprland grabbed a bound combo like
    SUPER+T itself and the key never reached this window. The inhibit is tied
    to the surface; when the window closes (or the process dies) Hyprland
    restores its shortcuts on its own.
    """

    def __init__(self, parent, row: Row, mod_key: str, on_done):
        super().__init__(modal=True, transient_for=parent,
                         title=f"Shortcut: {row.title}")
        self.set_default_size(460, 230)
        self._mod_key = mod_key
        self._on_done = on_done

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for margin in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{margin}")(24)
        heading = Gtk.Label(label=row.title)
        heading.add_css_class("title-2")
        prompt = Gtk.Label(label="Press the new key combination")
        current = Gtk.Label(label=f"Current: {row.combo}")
        current.add_css_class("dim-label")
        hint = Gtk.Label(label="Esc: cancel   ·   Backspace: remove shortcut")
        hint.add_css_class("caption")
        hint.add_css_class("dim-label")
        for widget in (heading, prompt, current, hint):
            widget.set_wrap(True)
            box.append(widget)
        if row.changed:
            reset = Gtk.Button(label="Reset to default", halign=Gtk.Align.CENTER)
            reset.connect("clicked", lambda _b: self._finish(None))
            box.append(reset)
        self.set_content(box)

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)
        self.connect("realize", self._inhibit)
        self.connect("close-request", self._restore)

    def _inhibit(self, *_args) -> None:
        surface = self.get_surface()
        if isinstance(surface, Gdk.Toplevel):
            surface.inhibit_system_shortcuts(None)

    def _restore(self, *_args) -> bool:
        surface = self.get_surface()
        if isinstance(surface, Gdk.Toplevel):
            surface.restore_system_shortcuts()
        return False

    def _finish(self, combo: str | None) -> None:
        self.close()
        self._on_done(combo)

    def _on_key(self, _controller, keyval, _keycode, state) -> bool:
        name = Gdk.keyval_name(keyval) or ""
        if name in _MODIFIER_KEYNAMES:
            return True
        if name == "Escape":
            self.close()
            return True
        if name in ("BackSpace", "Delete"):
            self._finish("")
            return True
        mods = []
        for mask, label in ((Gdk.ModifierType.SUPER_MASK, "SUPER"),
                            (Gdk.ModifierType.CONTROL_MASK, "CTRL"),
                            (Gdk.ModifierType.ALT_MASK, "ALT"),
                            (Gdk.ModifierType.SHIFT_MASK, "SHIFT")):
            if state & mask:
                mods.append("MOD" if label == self._mod_key else label)
        key = name.upper() if len(name) == 1 and name.isalpha() else name
        self._finish("+".join(mods + [key]))
        return True


class CheatsheetWindow(Adw.ApplicationWindow):
    def __init__(self, app, categories: list[tuple[str, list[Row]]],
                 total: int):
        super().__init__(application=app, title="Keybindings")
        self.set_default_size(1100, 720)
        self._app = app
        self._rows: list[tuple[Gtk.Widget, str]] = []
        self._cards: list[tuple[Gtk.Widget, list[Gtk.Widget]]] = []

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self._title = Adw.WindowTitle(title="Keybindings")
        header.set_title_widget(self._title)
        self.search = Gtk.SearchEntry(placeholder_text="Search…", hexpand=True)
        self.search.set_size_request(260, -1)
        self.search.connect("search-changed", self._on_search)
        header.pack_end(self.search)
        toolbar.add_top_bar(header)

        self._toasts = Adw.ToastOverlay()
        self._scroller = Gtk.ScrolledWindow(vexpand=True)
        self._toasts.set_child(self._scroller)
        toolbar.set_content(self._toasts)
        self.set_content(toolbar)
        self.fill(categories, total)

        # Esc closes it: the sheet is something you glance at and close, no
        # need to reach for the mouse.
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

    def fill(self, categories: list[tuple[str, list[Row]]], total: int) -> None:
        self._title.set_subtitle(f"{total} active shortcuts · click to change")
        self._rows.clear()
        self._cards.clear()
        # Categories are laid out in columns: 65 bindings in one column overflowed
        # the screen three times and "glance at the sheet, find the key" turned
        # into scrolling.
        # homogeneous=False: cards keep their own height. With True the tallest
        # card in a row set the height of the others too, leaving a screen-high
        # empty area under short categories (Applications, Session).
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
                           column_spacing=14, row_spacing=14,
                           homogeneous=False, valign=Gtk.Align.START,
                           min_children_per_line=1, max_children_per_line=3)
        flow.set_margin_top(16); flow.set_margin_bottom(16)
        flow.set_margin_start(16); flow.set_margin_end(16)

        for title, rows in categories:
            card, row_widgets = self._build_card(title, rows)
            flow.append(card)
            self._cards.append((card, row_widgets))

        adj = self._scroller.get_vadjustment().get_value()
        self._scroller.set_child(flow)
        GLib.idle_add(lambda: self._scroller.get_vadjustment().set_value(adj) and False)
        self._on_search(self.search)

    def toast(self, text: str) -> None:
        toast = Adw.Toast(title=text, timeout=3)
        if hasattr(toast, "set_use_markup"):
            toast.set_use_markup(False)      # so key names like "<" are not taken as markup
        self._toasts.add_toast(toast)

    def _build_card(self, title: str, rows: list[Row]):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.add_css_class("hs-cheat-card")
        # Column width: keycaps + the longest binding name. Without a size the
        # FlowBox sized the card to its widest row's natural width, and long
        # names spilled out of the card in a narrow window.
        box.set_size_request(330, -1)
        heading = Gtk.Label(label=title, xalign=0)
        heading.add_css_class("heading")
        heading.set_margin_bottom(4)
        box.append(heading)

        row_widgets: list[Gtk.Widget] = []
        for row in rows:
            line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            keycaps = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
            for part in row.combo.split(" + "):
                cap = Gtk.Label(label=_keycap(part))
                cap.add_css_class("hs-keycap")
                if row.changed:
                    cap.add_css_class("hs-keycap-changed")
                keycaps.append(cap)
            line.append(keycaps)
            # Without max_width_chars the label says "I can wrap but don't need
            # to" and asks for its natural width; when the card could not reach
            # that width the text got clipped.
            label = Gtk.Label(label=row.title, xalign=1, hexpand=True, wrap=True,
                              max_width_chars=22,
                              justify=Gtk.Justification.RIGHT)
            label.add_css_class("dim-label")
            line.append(label)
            if row.bind_id:
                widget = Gtk.Button(child=line)
                widget.add_css_class("flat")
                widget.add_css_class("hs-cheat-row")
                widget.set_tooltip_text("Click to change")
                widget.connect("clicked", self._on_row_clicked, row)
            else:
                widget = line
                widget.add_css_class("hs-cheat-row")
            box.append(widget)
            row_widgets.append(widget)
            self._rows.append((widget, f"{row.combo} {row.title}".lower()))
        return box, row_widgets

    def _on_row_clicked(self, _button, row: Row) -> None:
        CaptureDialog(self, row, self._app.mod_key,
                      lambda combo: self._app.change(row, combo)).present()

    def _on_search(self, entry: Gtk.SearchEntry) -> None:
        needle = entry.get_text().strip().lower()
        for row, haystack in self._rows:
            row.set_visible(not needle or needle in haystack)
        # A category card with no rows left is hidden; otherwise the screen
        # fills with empty headings.
        for card, rows in self._cards:
            card.set_visible(any(row.get_visible() for row in rows))

    def _on_key(self, _controller, keyval, _keycode, _state) -> bool:
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False


class CheatsheetApp(Adw.Application):
    def __init__(self, root: Path, catalog_path: Path):
        super().__init__(application_id=APP_ID)
        self.root = root
        self.catalog_path = catalog_path
        self.mod_key = "SUPER"
        self.used: dict[str, str] = {}
        self.window: CheatsheetWindow | None = None

    def _load(self):
        self.mod_key, categories, self.used = resolved_binds(
            self.root, self.catalog_path)
        return categories, sum(len(rows) for _title, rows in categories)

    def do_activate(self) -> None:
        ensure_css(_CSS)
        if self.window is None:
            self.window = CheatsheetWindow(self, *self._load())
        self.window.present()

    def change(self, row: Row, combo: str | None) -> None:
        """Validate the captured combo, save it, apply it and refresh the sheet."""
        window = self.window
        shown = keybinds_mod.display(keybinds_mod.normalize(combo or ""), self.mod_key)
        if combo:
            combo = keybinds_mod.normalize(combo)
            if not keybinds_mod.valid_combo(combo):
                window.toast(f"This key cannot be used: {combo}")
                return
            owner = self.used.get(combo)
            if owner and owner != row.title:
                window.toast(f"{shown} is already used by: {owner}")
                return
        window.toast("Applying…")

        def work():
            try:
                save_override(self.root, self.catalog_path, row.bind_id, combo)
                error = ""
            except Exception as exc:          # noqa: BLE001 — show it to the user
                error = str(exc)
            GLib.idle_add(done, error)

        def done(error: str):
            if error:
                window.toast(f"Could not save: {error}")
                return False
            window.fill(*self._load())
            if combo is None:
                window.toast(f"{row.title}: reset to default")
            elif combo == "":
                window.toast(f"{row.title}: shortcut removed")
            else:
                window.toast(f"{row.title}: {shown}")
            return False

        threading.Thread(target=work, daemon=True).start()


def run(root: Path, catalog_path: Path) -> int:
    root = Path(root).resolve()
    catalog_path = Path(catalog_path)
    if not catalog_path.is_absolute():
        catalog_path = root / catalog_path
    GLib.set_prgname(APP_ID)
    return CheatsheetApp(root, catalog_path).run([])
