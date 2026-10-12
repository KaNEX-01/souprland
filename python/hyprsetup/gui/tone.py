"""Picking palette colors from the wallpaper (Appearance + wizard).

The tone sliders (PALETTE_HUE/SATURATION/LIGHTNESS) are plain rows from the
schema; this module holds only the part the schema cannot draw: the image's
prominent colors are shown as swatches, and clicking one makes it the color
of the selected role (Accent 1 by default). The chosen color is written to
CUSTOM_COLORS, so it stays on top both with a preset theme and with
THEME="auto", and is not affected by the tone shift (the user picked exactly
that color).
"""

from __future__ import annotations

import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from .. import wallcolors  # noqa: E402

#: Role the clicked color is written to → label.
TARGETS: tuple[tuple[str, str], ...] = (
    ("ACCENT", "Accent 1 (active border, selection)"),
    ("ACCENT2", "Accent 2 (border gradient)"),
    ("BG", "Background"),
    ("SURFACE", "Surface (window body)"),
)


def _swatch_button(value: str, name: str, on_pick) -> Gtk.Button:
    rgba = Gdk.RGBA()
    rgba.parse("#" + value)
    area = Gtk.DrawingArea(content_width=44, content_height=32)

    def draw(_a, cr, width, height) -> None:
        radius = 7
        cr.new_sub_path()
        for x, y, start in ((width - radius, radius, -90),
                            (width - radius, height - radius, 0),
                            (radius, height - radius, 90), (radius, radius, 180)):
            cr.arc(x, y, radius, start * 3.14159 / 180, (start + 90) * 3.14159 / 180)
        cr.close_path()
        cr.set_source_rgb(rgba.red, rgba.green, rgba.blue)
        cr.fill()

    area.set_draw_func(draw)
    button = Gtk.Button(child=area, tooltip_text=f"{name} · #{value}")
    button.add_css_class("flat")
    button.connect("clicked", lambda _b: on_pick(value))
    return button


class WallpaperSwatches(Adw.PreferencesGroup):
    """The wallpaper's colors; the clicked color is written to the selected role.

    ``win`` is the MainWindow: for state, syncing the color buttons and
    toasts. Colors are extracted in the background (~0.5 s per image) and
    refreshed when the wallpaper changes (see refresh, the state listener).
    """

    def __init__(self, win, title: str = "Colors from the wallpaper") -> None:
        super().__init__(
            title=title,
            description="Click a color: the selected role takes that color and "
                        "windows, the bar, the terminal and GTK/Qt apps are "
                        "recolored together. The choice survives theme changes; "
                        "to undo it use \"Revert to theme colors\".")
        self.win = win
        self._shown: tuple = ()
        self._target = TARGETS[0][0]

        target_row = Adw.ComboRow(
            title="Apply the clicked color to",
            model=Gtk.StringList.new([label for _key, label in TARGETS]))
        target_row.connect(
            "notify::selected",
            lambda r, _p: setattr(self, "_target", TARGETS[r.get_selected()][0]))
        self.add(target_row)

        self._flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
                                 max_children_per_line=12, min_children_per_line=3,
                                 column_spacing=4, row_spacing=4)
        self._status = Gtk.Label(xalign=0, wrap=True,
                                 label="Extracting colors…")
        self._status.add_css_class("dim-label")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                      margin_top=10, margin_bottom=10, margin_start=12,
                      margin_end=12)
        box.append(self._flow)
        box.append(self._status)
        self.add(Adw.PreferencesRow(child=box, activatable=False))

        win.state.connect(self.refresh)
        self.refresh()

    def _image(self) -> Path | None:
        values = dict(self.win.state.values)
        raw = values.get("WALLPAPER_PATH", "")
        if raw:
            path = Path(raw).expanduser()
            if path.is_file():
                return path
        return wallcolors.current_wallpaper(values)

    def refresh(self, *_args) -> None:
        image = self._image()
        try:
            key = (str(image), image.stat().st_mtime) if image else ()
        except OSError:
            key = ()
        if key == self._shown:
            return
        self._shown = key
        if image is None:
            self._show(None, {})
            return

        def work() -> None:
            try:
                colors = wallcolors.vibrant(image)
            except Exception as exc:                   # noqa: BLE001
                print(f"hyprsetup: could not read wallpaper colors: {exc}")
                colors = {}
            GLib.idle_add(self._show, image, colors)

        threading.Thread(target=work, daemon=True).start()

    def _show(self, image: Path | None, colors: dict[str, str]) -> bool:
        while (child := self._flow.get_first_child()) is not None:
            self._flow.remove(child)
        seen: set[str] = set()
        for name, value in colors.items():
            value = value.lstrip("#").lower()
            if value in seen:
                continue
            seen.add(value)
            self._flow.append(_swatch_button(value, name, self._pick))
        if image is None:
            self._status.set_text("No wallpaper found; pick an image first.")
        elif not seen:
            self._status.set_text("Could not extract colors from this image.")
        else:
            self._status.set_text(image.name)
        return False

    def _pick(self, value: str) -> None:
        self.win.state.set_colour(self._target, value)
        self.win._sync_colour_buttons()
        label = dict(TARGETS)[self._target].split(" (")[0]
        self.win._toast(f"{label}: #{value}")
