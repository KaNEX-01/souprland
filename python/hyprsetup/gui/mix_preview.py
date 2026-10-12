"""Soup Maker's live desktop preview.

Draws what the pending (not yet applied) selection will turn into on the
desktop: wallpaper, color scheme and window look as setting values
(mix.preview_values → DesktopPreview), and bar/launcher/notification/terminal/
lock/widget as small palette-painted parts. Each part is a "hotspot":
hovering shows its name, clicking opens that ingredient's step. The selected
step's region is highlighted so you can see what you are changing.
"""

from __future__ import annotations

import math

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from .. import render as render_mod  # noqa: E402
from .. import themes  # noqa: E402
from .preview import (VIRTUAL_H, VIRTUAL_W, DesktopPreview, _hex_to_rgb,  # noqa: E402
                      _text, _text_width, rounded_path)


class MixPreview(DesktopPreview):
    """Desktop with clickable regions. ``on_slot(slot)`` fires when a region is clicked."""

    def __init__(self, root, has_component, on_slot) -> None:
        self._values: dict[str, str] = {}
        self._pal: dict[str, str] = dict(themes.resolve(themes.DEFAULT))
        super().__init__(get_setting=lambda k: self._values.get(k, ""),
                         get_palette=lambda: self._pal,
                         has_component=has_component,
                         use_custom_wallpaper=True, root=root)
        # Windows on the right, so the wallpaper and parts show on the left.
        self.window_share = 0.52
        self.set_content_width(640)
        self.set_content_height(330)
        self.set_vexpand(False)
        self._on_slot = on_slot
        #: slot → (short name, name of the selection)
        self.labels: dict[str, tuple[str, str]] = {}
        #: app parts to draw (the ones that have a tab on the page)
        self.slots: set[str] = set()
        self.current = ""
        self._hover = ""
        self._rects: list[tuple[str, tuple[float, float, float, float]]] = []
        self._transform = (1.0, 0.0, 0.0)

        click = Gtk.GestureClick()
        click.connect("released", self._on_click)
        self.add_controller(click)
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion)
        motion.connect("leave", lambda *_a: self._set_hover(""))
        self.add_controller(motion)

    # ------------------------------------------------------------ state ---
    def update(self, values: dict[str, str]) -> None:
        self._values = dict(values)
        try:
            self._pal = render_mod.effective_palette(self._values)[1]
        except (OSError, ValueError, KeyError):
            self._pal = dict(themes.resolve(themes.DEFAULT))
        self.queue_draw()

    def set_current(self, slot: str) -> None:
        self.current = slot
        self.queue_draw()

    # ------------------------------------------------------------ regions --
    def _hotspots(self) -> list[tuple[str, tuple[float, float, float, float]]]:
        """(slot, x, y, w, h on the virtual screen), smallest first (click order)."""
        W, H = VIRTUAL_W, VIRTUAL_H
        position = (self._get("BAR_POSITION") or "top").strip()
        margin = self._num("BAR_MARGIN", 6)
        thick = (self._num("BAR_WIDTH", 44) if position in ("left", "right")
                 else self._num("BAR_HEIGHT", 38))
        if position == "bottom":
            bar = (margin, H - margin - thick, W - 2 * margin, thick)
        elif position == "left":
            bar = (margin, margin, thick, H - 2 * margin)
        elif position == "right":
            bar = (W - margin - thick, margin, thick, H - 2 * margin)
        else:
            bar = (margin, margin, W - 2 * margin, thick)
        top = (margin + thick + 24) if position == "top" else 40
        left = (margin + thick + 40) if position == "left" else 70
        right_edge = (W - margin - thick - 30) if position == "right" else W - 30
        bottom = (H - margin - thick - 24) if position == "bottom" else H - 30
        free_w = W * (1 - self.window_share)
        spots = [
            ("notify", (right_edge - 440, top + 20, 420, 112)),
            ("lock", (right_edge - 300, bottom - 180, 280, 168)),
            ("colors", (left + 360, bottom - 70, 380, 64)),
            ("widget", (left, bottom - 190, 320, 170)),
            ("launcher", (left, top + 10, min(560, free_w - left - 40), 230)),
            ("terminal", (left + 60, top + 280, min(640, free_w - left - 20), 300)),
            ("bar", bar),
            ("look", (free_w, top, right_edge - free_w, bottom - top)),
            ("wallpaper", (0, 0, W, H)),
        ]
        return [(s, r) for s, r in spots
                if s in ("wallpaper", "colors", "look", "bar") or s in self.slots]

    def _to_widget(self, rect):
        scale, ox, oy = self._transform
        x, y, w, h = rect
        return ox + x * scale, oy + y * scale, w * scale, h * scale

    def _hit(self, px: float, py: float) -> str:
        for slot, rect in self._rects:
            x, y, w, h = self._to_widget(rect)
            if x <= px <= x + w and y <= py <= y + h:
                return slot
        return ""

    def _on_click(self, _gesture, _n, x, y) -> None:
        slot = self._hit(x, y)
        if slot:
            self._on_slot(slot)

    def _on_motion(self, _ctl, x, y) -> None:
        self._set_hover(self._hit(x, y))

    def _set_hover(self, slot: str) -> None:
        if slot != self._hover:
            self._hover = slot
            self.set_cursor_from_name("pointer" if slot else None)
            self.queue_draw()

    # ------------------------------------------------------------ drawing --
    def _draw(self, area, cr, width, height) -> None:
        super()._draw(area, cr, width, height)
        scale = min(width / VIRTUAL_W, height / VIRTUAL_H)
        ox = (width - VIRTUAL_W * scale) / 2
        oy = (height - VIRTUAL_H * scale) / 2
        self._transform = (scale, ox, oy)
        self._rects = self._hotspots()
        c = {k: _hex_to_rgb(v) for k, v in self._pal.items()
             if isinstance(v, str) and len(v.lstrip("#")) == 6}
        for slot, rect in reversed(self._rects):
            draw = getattr(self, f"_part_{slot}", None)
            if draw is not None:
                draw(cr, c, *self._to_widget(rect), scale)
        for slot, rect in self._rects:
            if slot in (self.current, self._hover):
                self._outline(cr, c, slot, self._to_widget(rect))

    def _outline(self, cr, c, slot, rect) -> None:
        x, y, w, h = rect
        current = slot == self.current
        inset = 3.0 if slot == "wallpaper" else -2.0
        x, y, w, h = x + inset, y + inset, w - 2 * inset, h - 2 * inset
        rounded_path(cr, x, y, w, h, 8, 2)
        cr.set_line_width(2.5 if current else 1.5)
        if current:
            cr.set_source_rgb(*c["ACCENT"])
        else:
            cr.set_source_rgba(1, 1, 1, 0.85)
            cr.set_dash([5, 4])
        cr.stroke()
        cr.set_dash([])
        name, value = self.labels.get(slot, (slot, ""))
        text = f"{name} · {value}" if value else name
        size = 11
        tw = _text_width(cr, text, size, bold=True)
        lx = min(max(x, 4.0), self.get_width() - tw - 22)
        ly = y - 11 if y > 18 else y + 6
        rounded_path(cr, lx, ly, tw + 18, 21, 10.5, 2)
        if current:
            cr.set_source_rgb(*c["ACCENT"])
        else:
            cr.set_source_rgba(0.08, 0.08, 0.1, 0.9)
        cr.fill()
        _text(cr, lx + 9, ly + 15, text,
              c["BG_DARK"] if current else (1, 1, 1), size, bold=True)

    # Parts: small palette-painted sketches ------------------------------
    @staticmethod
    def _panel(cr, c, x, y, w, h, radius, alpha=0.94, border=None):
        rounded_path(cr, x, y, w, h, radius, 2)
        cr.set_source_rgba(*c["BG_DARK"], alpha)
        cr.fill()
        if border is not None:
            rounded_path(cr, x, y, w, h, radius, 2)
            cr.set_source_rgba(*border, 0.9)
            cr.set_line_width(1.2)
            cr.stroke()

    def _radius(self, s: float) -> float:
        return max(2.0, min(14.0, self._num("ROUNDING", 10) * s * 1.6))

    def _part_launcher(self, cr, c, x, y, w, h, s) -> None:
        r = self._radius(s)
        self._panel(cr, c, x, y, w, h, r, border=c["ACCENT"])
        pad = 10 * s * 2
        rounded_path(cr, x + pad, y + pad, w - 2 * pad, h * 0.2, r / 2, 2)
        cr.set_source_rgb(*c["SURFACE"])
        cr.fill()
        _text(cr, x + pad * 1.6, y + pad + h * 0.14, "Search…", c["SUBTEXT"],
              max(7.0, 22 * s))
        row_h = (h - h * 0.2 - pad * 3) / 3
        for i in range(3):
            ry = y + pad * 2 + h * 0.2 + i * row_h
            if i == 0:
                rounded_path(cr, x + pad * 0.6, ry, w - pad * 1.2, row_h - 2, r / 2, 2)
                cr.set_source_rgba(*c["ACCENT"], 0.35)
                cr.fill()
            cr.set_source_rgb(*(c["ACCENT"], c["GREEN"], c["YELLOW"])[i])
            cr.arc(x + pad * 1.4, ry + row_h / 2, row_h * 0.22, 0, 2 * math.pi)
            cr.fill()
            cr.set_source_rgba(*c["FG"], 0.85)
            rounded_path(cr, x + pad * 2.2, ry + row_h / 2 - 2, w * (0.5 - 0.1 * i), 4, 2, 2)
            cr.fill()

    def _part_terminal(self, cr, c, x, y, w, h, s) -> None:
        r = self._radius(s)
        border = max(1.0, self._num("BORDER_SIZE", 2) * s * 1.5)
        rounded_path(cr, x, y, w, h, r, 2)
        cr.set_source_rgba(*c["BG"], 0.96)
        cr.fill()
        rounded_path(cr, x, y, w, h, r, 2)
        cr.set_source_rgb(*c["ACCENT"])
        cr.set_line_width(border)
        cr.stroke()
        size = max(7.0, 20 * s)
        line = size * 1.5
        lines = (("> ", c["GREEN"], "fastfetch"), ("", c["SUBTEXT"], "os  Arch Linux"),
                 ("", c["SUBTEXT"], "wm  Hyprland"), ("> ", c["GREEN"], "ls"),
                 ("", c["ACCENT"], "Documents  Pictures  dotfiles"), ("> ", c["GREEN"], ""))
        for i, (prompt, colour, body) in enumerate(lines):
            ty = y + line * (i + 1.2)
            if ty > y + h - 6:
                break
            tx = x + 10 * s * 2
            if prompt:
                tx += _text(cr, tx, ty, prompt, c["GREEN"], size, bold=True) + 3
            _text(cr, tx, ty, body, c["FG"] if prompt else colour, size)

    def _part_notify(self, cr, c, x, y, w, h, s) -> None:
        r = self._radius(s)
        self._panel(cr, c, x, y, w, h, r)
        cr.set_source_rgb(*c["ACCENT"])
        rounded_path(cr, x, y, 6 * s * 2, h, min(r, 3 * s * 2), 2)
        cr.fill()
        cr.arc(x + h * 0.4 + 6 * s * 2, y + h / 2, h * 0.22, 0, 2 * math.pi)
        cr.set_source_rgba(*c["ACCENT2"], 0.9)
        cr.fill()
        tx = x + h * 0.75 + 6 * s * 2
        _text(cr, tx, y + h * 0.42, "Notification", c["FG"], max(7.0, 22 * s), bold=True)
        cr.set_source_rgba(*c["SUBTEXT"], 0.8)
        rounded_path(cr, tx, y + h * 0.6, w * 0.5, 4, 2, 2)
        cr.fill()

    def _part_widget(self, cr, c, x, y, w, h, s) -> None:
        self._panel(cr, c, x, y, w, h, self._radius(s), alpha=0.72)
        _text(cr, x + w / 2, y + h * 0.58, "14:32", c["FG"], max(10.0, 64 * s),
              bold=True, anchor="center")
        _text(cr, x + w / 2, y + h * 0.84, "Monday", c["SUBTEXT"],
              max(7.0, 20 * s), anchor="center")

    def _part_colors(self, cr, c, x, y, w, h, s) -> None:
        self._panel(cr, c, x, y, w, h, h / 2, alpha=0.85)
        keys = ("ACCENT", "ACCENT2", "RED", "GREEN", "YELLOW", "CYAN", "FG")
        step = w / len(keys)
        for i, key in enumerate(keys):
            if key not in c:
                continue
            cr.set_source_rgb(*c[key])
            cr.arc(x + step * (i + 0.5), y + h / 2, min(h * 0.32, step * 0.4), 0, 2 * math.pi)
            cr.fill()

    def _part_lock(self, cr, c, x, y, w, h, s) -> None:
        r = self._radius(s)
        self._panel(cr, c, x, y, w, h, r, alpha=0.9, border=c["SUBTEXT"])
        _text(cr, x + w / 2, y + h * 0.36, "14:32", c["FG"], max(8.0, 40 * s),
              bold=True, anchor="center")
        cr.set_source_rgb(*c["ACCENT"])
        rounded_path(cr, x + w * 0.2, y + h * 0.58, w * 0.6, h * 0.16, h * 0.08, 2)
        cr.set_line_width(1.2)
        cr.stroke()
        # padlock
        lx, ly, size = x + w / 2, y + h * 0.86, max(4.0, 14 * s)
        cr.set_source_rgb(*c["SUBTEXT"])
        cr.rectangle(lx - size * 0.6, ly - size * 0.3, size * 1.2, size * 0.8)
        cr.fill()
        cr.set_line_width(max(1.0, 3 * s))
        cr.arc(lx, ly - size * 0.3, size * 0.4, math.pi, 0)
        cr.stroke()
