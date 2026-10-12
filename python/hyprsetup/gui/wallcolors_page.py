"""The settings app's "Wallpaper Colors" page (backend: ``wallcolors``).

Brings what ricemood does into the settings: the colors extracted from the
wallpaper are shown (node-vibrant's six swatches, this project's 11 roles, the
16 terminal colors), clicking one copies its template tag to the clipboard;
built-in templates (pywal compatibility, Zathura, tmux) can be toggled, and the
user can generate a template from their own config file in one click. When the
wallpaper changes (rotation included) everything is re-applied.
"""

from __future__ import annotations

import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from .. import palette as palette_mod  # noqa: E402
from .. import render as render_mod  # noqa: E402
from .. import themes  # noqa: E402
from .. import wallcolors  # noqa: E402
from .util import pick_file  # noqa: E402
from .preview import ShotPreview  # noqa: E402

_HELP = (
    "<b>Tag:</b> <tt>^r@Name&gt;filter(value)#format^</tt>, e.g. "
    "<tt>^r@Vibrant&gt;lighten(0.2)^</tt>, <tt>^r@ACCENT#rgb^</tt>, "
    "<tt>^r@DM&gt;darken(0.3)#hex^</tt>\n"
    "<b>Names:</b> Vibrant (V), LightVibrant (LV), DarkVibrant (DV), Muted (M), "
    "LightMuted (LM), DarkMuted (DM) · BG, BG_DARK, SURFACE, FG, SUBTEXT, ACCENT, "
    "ACCENT2, RED, GREEN, YELLOW, CYAN · color0–color15, background, foreground, cursor\n"
    "<b>Filters:</b> lighten/li, darken/da, saturate/sa, desaturate/de, whiten/wh, "
    "blacken/bl, fade/fa, opaquer/op, rotate/ro, grayscale/ge, negate/ne, "
    "ttc/btc (readable text color), r/g/b/h/s/l (set channel)\n"
    "<b>Formats:</b> (empty) #RRGGBB · hex · rgb(separator) · rgba · hsl · r g b h s l\n"
    "<b>pywal templates</b> work too: <tt>{color0}</tt>, <tt>{background.strip}</tt>, "
    "<tt>{color4.rgb}</tt> (<tt>{{ }}</tt> for literal braces).")


def _esc(text: str) -> str:
    return GLib.markup_escape_text(str(text))


class _Chip(Gtk.Box):
    """A single color: swatch + name + hex. Clicking copies its template tag."""

    def __init__(self, name: str, value: str, tag: str) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        area = Gtk.DrawingArea(content_width=64, content_height=40)
        rgba = Gdk.RGBA()
        rgba.parse("#" + value)

        def draw(_a, cr, width, height) -> None:
            cr.set_source_rgb(rgba.red, rgba.green, rgba.blue)
            radius = 8
            cr.new_sub_path()
            for x, y, start in ((width - radius, radius, -90), (width - radius, height - radius, 0),
                                (radius, height - radius, 90), (radius, radius, 180)):
                cr.arc(x, y, radius, start * 3.14159 / 180, (start + 90) * 3.14159 / 180)
            cr.close_path()
            cr.fill()
        area.set_draw_func(draw)
        button = Gtk.Button(child=area, tooltip_text=f"Click to copy {tag}")
        button.add_css_class("flat")
        button.connect("clicked", lambda _b: Gdk.Display.get_default().get_clipboard().set(tag))
        self.append(button)
        label = Gtk.Label(label=name, css_classes=["caption"], max_width_chars=10,
                          ellipsize=3)
        self.append(label)
        hex_label = Gtk.Label(label=f"#{value}", css_classes=["caption", "dim-label"],
                              selectable=True)
        self.append(hex_label)


class WallColorsPage(Adw.PreferencesPage):
    def __init__(self, win) -> None:
        super().__init__()
        self.win = win
        self.root = Path(win.root)
        if hasattr(win, "_widen_page"):
            win._widen_page(self, 940)
        self.config = wallcolors.load_config()
        self.image: Path | None = None
        self.colors: wallcolors.Colors | None = None
        self._entry_rows: list[Gtk.Widget] = []

        # --- image + colors ----------------------------------------------
        self._image_group = Adw.PreferencesGroup(
            title="Colors from the wallpaper",
            description="Clicking a color copies its template tag (e.g. ^r@Vibrant^) "
                        "to the clipboard. The first row is ricemood's six swatches "
                        "(node-vibrant), the second the 11 roles the desktop uses, "
                        "the third the terminal colors.")
        pick = Gtk.Button(label="Try another image…", valign=Gtk.Align.CENTER)
        pick.add_css_class("flat")
        pick.connect("clicked", lambda _b: self._pick_image())
        self._image_group.set_header_suffix(pick)
        self._image_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._image_group.add(self._image_box)
        self.add(self._image_group)

        # --- settings ----------------------------------------------------
        settings = Adw.PreferencesGroup(title="Behavior")
        self._auto_row = Adw.SwitchRow(
            title="Desktop colors from the wallpaper",
            subtitle="Bar, terminal, GTK, borders… (THEME=\"auto\"). Turning it off "
                     "returns to the previous theme.")
        self._auto_row.set_active(win.state.get("THEME").strip().lower() == "auto")
        self._auto_row.connect("notify::active", self._on_auto)
        settings.add(self._auto_row)
        follow = Adw.SwitchRow(
            title="Re-apply when the wallpaper changes",
            subtitle="On every change made by rotation or wallpaper.sh, the desktop and "
                     "the programs below take the new image's colors.")
        follow.set_active(bool(self.config.get("follow", True)))
        follow.connect("notify::active", lambda r, _p: self._config_set("follow", r.get_active()))
        settings.add(follow)

        schemes = [("dark", "Dark"), ("light", "Light")]
        scheme = Adw.ComboRow(title="Light / dark", model=Gtk.StringList.new([s[1] for s in schemes]))
        current = win.state.get("COLOR_SCHEME") or "dark"
        scheme.set_selected(next((i for i, s in enumerate(schemes) if s[0] == current), 0))
        scheme.connect("notify::selected", lambda r, _p: self._state_set(
            "COLOR_SCHEME", schemes[r.get_selected()][0]))
        settings.add(scheme)

        backends = [("auto", "Automatic (best available)")] + [
            (b, {"matugen": "matugen (Material You)", "magick": "ImageMagick",
                 "python": "Built-in (PNG only)"}.get(b, b))
            for b in palette_mod.backends_available()]
        backend = Adw.ComboRow(title="Color extractor",
                               subtitle="Used to extract the desktop roles",
                               model=Gtk.StringList.new([b[1] for b in backends]))
        current = win.state.get("PALETTE_BACKEND") or "auto"
        backend.set_selected(next((i for i, b in enumerate(backends) if b[0] == current), 0))
        backend.connect("notify::selected", lambda r, _p: self._state_set(
            "PALETTE_BACKEND", backends[r.get_selected()][0]))
        settings.add(backend)
        self.add(settings)

        # --- programs ------------------------------------------------------
        self._apps_group = Adw.PreferencesGroup(
            title="Programs",
            description="Every enabled template is filled in and written to its target "
                        "file. What this project already colors (bar, terminal, GTK, "
                        "notifications…) is not listed here; this is for every other program.")
        add = Gtk.Button(label="Add template…", valign=Gtk.Align.CENTER,
                         tooltip_text="Choose a config file: the colors in it are "
                                      "turned into tags")
        add.add_css_class("suggested-action")
        add.connect("clicked", lambda _b: self._add_template())
        self._apps_group.set_header_suffix(add)
        self.add(self._apps_group)

        help_group = Adw.PreferencesGroup()
        expander = Adw.ExpanderRow(title="Template syntax",
                                   subtitle="ricemood tags and pywal templates")
        label = Gtk.Label(label=_HELP, use_markup=True, wrap=True, xalign=0,
                          margin_top=8, margin_bottom=8, margin_start=12, margin_end=12)
        expander.add_row(Adw.PreferencesRow(child=label, activatable=False))
        help_group.add(expander)
        self.add(help_group)

        self._build_entries()
        self.reload_colors()

    # --------------------------------------------------------------- state
    def _config_set(self, key: str, value) -> None:
        self.config[key] = value
        wallcolors.save_config(self.config)

    def _state_set(self, key: str, value: str) -> None:
        self.win.state.set(key, value)
        GLib.timeout_add(400, lambda: (self.reload_colors(), False)[1])

    def _on_auto(self, row: Adw.SwitchRow, _param) -> None:
        state = self.win.state
        if row.get_active():
            current = state.get("THEME")
            if current and current != "auto":
                self._config_set("previous_theme", current)
            state.set("CUSTOM_COLORS", "")
            state.set("THEME", "auto")
        else:
            state.set("THEME", self.config.get("previous_theme") or themes.DEFAULT)

    # -------------------------------------------------------------- colors
    def reload_colors(self, image: Path | None = None) -> None:
        """Extract colors in the background (matugen/magick can take ~1 s)."""
        values = dict(self.win.state.values)
        target = image or self.image or wallcolors.current_wallpaper(values)
        dark = (values.get("COLOR_SCHEME", "dark").strip().lower() != "light")
        backend = values.get("PALETTE_BACKEND", "auto") or "auto"

        def work() -> None:
            colors = (wallcolors.extract(target, dark=dark, backend=backend, values=values)
                      if target else None)
            GLib.idle_add(self._show_colors, target, colors)
        threading.Thread(target=work, daemon=True).start()

    def _show_colors(self, image: Path | None, colors) -> bool:
        self.colors = colors
        child = self._image_box.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            self._image_box.remove(child)
            child = following
        if image is None or colors is None:
            self._image_box.append(Gtk.Label(label="No wallpaper found.",
                                             css_classes=["dim-label"]))
            return False
        top = Gtk.Box(spacing=16)
        top.append(ShotPreview(image, width=256, height=144))
        info = Gtk.Label(label=f"<b>{_esc(image.name)}</b>\n<small>{_esc(image.parent)}</small>",
                         use_markup=True, xalign=0, wrap=True, valign=Gtk.Align.CENTER)
        top.append(info)
        self._image_box.append(top)
        rows = [
            ("ricemood (node-vibrant)", [(n, v, f"^r@{n}^") for n, v in colors.vibrant.items()]),
            ("Desktop roles", [(n, v, f"^r@{n}^") for n, v in colors.roles.items()]),
            ("Terminal", [(f"color{i}", colors.names()[f"color{i}"], f"^r@color{i}^")
                          for i in range(16) if f"color{i}" in colors.names()]),
        ]
        for title, chips in rows:
            self._image_box.append(Gtk.Label(label=title, xalign=0, css_classes=["heading"]))
            flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=12,
                               column_spacing=6, row_spacing=6, homogeneous=True)
            for name, value, tag in chips:
                flow.append(_Chip(name, value, tag))
            self._image_box.append(flow)
        return False

    def _pick_image(self) -> None:
        def chosen(path: Path) -> None:
            self.image = path
            self.reload_colors(path)
            self.win._toast("Preview only: this image's colors. \"Apply now\" "
                            "writes the templates with these colors.")
        pick_file(self.win, "Image to extract colors from", chosen,
                  filter_name="Images", mimes=["image/*"])

    # ------------------------------------------------------------ templates
    def _build_entries(self) -> None:
        for row in self._entry_rows:
            self._apps_group.remove(row)
        self._entry_rows = []
        for entry in wallcolors.entries(self.root, self.config):
            targets = ", ".join(t.path for t in entry.targets)
            if entry.builtin:
                row = Adw.SwitchRow(title=_esc(entry.title),
                                    subtitle=_esc(f"{entry.desc}\n→ {targets}"))
                row.set_subtitle_lines(4)
                row.set_active(entry.enabled)
                row.connect("notify::active", self._on_builtin, entry.id)
            else:
                row = Adw.ActionRow(title=_esc(entry.title), subtitle=_esc(f"→ {targets}"))
                switch = Gtk.Switch(active=entry.enabled, valign=Gtk.Align.CENTER)
                switch.connect("notify::active", self._on_user_toggle, entry.id)
                edit = Gtk.Button(icon_name="document-edit-symbolic", valign=Gtk.Align.CENTER,
                                  tooltip_text="Edit template")
                edit.add_css_class("flat")
                edit.connect("clicked", lambda _b, e=entry: self._edit(e))
                remove = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER,
                                    tooltip_text="Delete template (the target file is not touched)")
                remove.add_css_class("flat")
                remove.connect("clicked", lambda _b, e=entry: self._remove(e))
                row.add_suffix(edit)
                row.add_suffix(remove)
                row.add_suffix(switch)
            self._apps_group.add(row)
            self._entry_rows.append(row)
        apply_row = Adw.ActionRow(
            title="Apply now",
            subtitle="Writes the enabled templates with the shown image's colors and "
                     "reloads the programs.")
        button = Gtk.Button(label="Apply", valign=Gtk.Align.CENTER)
        button.add_css_class("suggested-action")
        button.connect("clicked", lambda _b: self._apply())
        apply_row.add_suffix(button)
        self._apps_group.add(apply_row)
        self._entry_rows.append(apply_row)

    def _on_builtin(self, row: Adw.SwitchRow, _param, ident: str) -> None:
        enabled = [e for e in self.config.get("enabled", []) if e != ident]
        if row.get_active():
            enabled.append(ident)
        self._config_set("enabled", enabled)

    def _on_user_toggle(self, switch: Gtk.Switch, _param, ident: str) -> None:
        for raw in self.config.get("templates", []):
            if raw["id"] == ident:
                raw["enabled"] = switch.get_active()
        wallcolors.save_config(self.config)

    def _template_file(self, entry: wallcolors.Entry) -> Path | None:
        raw = next((t for t in self.config.get("templates", []) if t["id"] == entry.id), None)
        return wallcolors.config_dir() / "templates" / raw["template"] if raw else None

    def _edit(self, entry: wallcolors.Entry) -> None:
        path = self._template_file(entry)
        if path:
            Gio.AppInfo.launch_default_for_uri(path.as_uri(), None)

    def _remove(self, entry: wallcolors.Entry) -> None:
        path = self._template_file(entry)
        self.config["templates"] = [t for t in self.config.get("templates", [])
                                    if t["id"] != entry.id]
        wallcolors.save_config(self.config)
        if path:
            path.unlink(missing_ok=True)
        self._build_entries()

    def _reference(self) -> dict[str, str]:
        """The palette the file is assumed to be colored with now: this project's active palette."""
        selected = list(self.win.state.selected)
        values, _skipped = self.win.applier.export_vars(dict(self.win.state.values), selected)
        variables = render_mod.derived_vars(values, self.win.catalog, selected, self.win.keybinds)
        return {k[4:]: v for k, v in variables.items()
                if k.startswith("COL_") and k[4:] in themes.KEYS}

    def _add_template(self) -> None:
        def chosen(path: Path) -> None:
            try:
                raw, mapping = wallcolors.add_user_template(path, self._reference())
            except (OSError, UnicodeError) as exc:
                self.win._toast(f"Could not create template: {exc}")
                return
            self.config = wallcolors.load_config()
            self._build_entries()
            lines = "\n".join(f"#{old} → {role}" for old, role in list(mapping.items())[:14])
            more = f"\n… and {len(mapping) - 14} more colors" if len(mapping) > 14 else ""
            body = (f"{len(mapping)} colors turned into tags (nearest desktop role):\n\n"
                    f"{lines}{more}\n\nTemplate: {wallcolors.config_dir() / 'templates' / raw['template']}\n"
                    "You can change the tags however you like (e.g. ^r@Vibrant^). "
                    "The target file's original is kept as .hyprsetup-orig."
                    if mapping else
                    "No #rrggbb colors found in the file. Open the template and write "
                    "tags in place of the colors (e.g. ^r@ACCENT^).")
            alert = Adw.AlertDialog(heading=f"Template added: {raw['title']}", body=body)
            alert.add_response("ok", "OK")
            alert.add_response("edit", "Open template")
            alert.connect("response", lambda _a, r: r == "edit" and Gio.AppInfo.launch_default_for_uri(
                (wallcolors.config_dir() / "templates" / raw["template"]).as_uri(), None))
            alert.present(self.win)
        pick_file(self.win, "File whose colors should follow the wallpaper", chosen)

    def _apply(self) -> None:
        if self.colors is None:
            self.win._toast("Colors are not ready yet")
            return
        colors, config = self.colors, wallcolors.load_config()

        def work() -> None:
            result = wallcolors.apply(self.root, colors, config)
            GLib.idle_add(self._applied, result)
        threading.Thread(target=work, daemon=True).start()

    def _applied(self, result) -> bool:
        if result.errors:
            self.win._toast("Error: " + result.errors[0])
        else:
            self.win._toast(f"{len(result.written)} file(s) written")
        return False
