"""First launch: soup animation + "how do you want to start?" screen.

Shown BEFORE the settings screen the first time the app opens:

1. ``SoupIntro``: the bowl from the logo appears and the ladle starts
   stirring; the status bar, a window, a terminal, a wallpaper and a
   notification drop into the soup one by one and splash; finally steam
   rises and the name appears. Clicking, Esc or Enter skips the animation.
   If animations are disabled system-wide (gtk-enable-animations) it is not
   played at all.
2. ``IntroTour``: a step-by-step tour with a GIF/video and short text on
   each page (overview, bloat, AUR safety…). Pages come from
   assets/intro/pages.json; the README's intro section is generated from the
   same file (see intro.py). If the file is empty the tour is skipped.
3. ``WelcomeChoice``: setup wizard from scratch, or a profile?
   "Skip" is one click too; the app then opens as the usual settings app.

That it was shown is remembered via ~/.config/hyprsetup/welcome-done; the
file is written only once a choice is made on the second screen (if the
window is closed during the animation, it is shown again next time).
HYPRSETUP_WELCOME=1 forces it on every launch.

Colors come from the logo (assets/souprland.svg), not the user's theme:
this screen is the brand itself, and no theme may have been chosen yet.
"""

from __future__ import annotations

import math
import os
import re
from pathlib import Path

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import (Adw, Gdk, GdkPixbuf, GLib, Gtk, Pango,  # noqa: E402
                           PangoCairo)

from .. import intro as intro_mod  # noqa: E402
from .state import config_path  # noqa: E402
from .util import ensure_css  # noqa: E402

# ---------------------------------------------------------- first launch ---


def marker_path() -> Path:
    return config_path().parent / "welcome-done"


def should_show() -> bool:
    if os.environ.get("HYPRSETUP_WELCOME") == "1":
        return True
    return not marker_path().exists()


def mark_done() -> None:
    path = marker_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("1\n", encoding="utf-8")
    except OSError as exc:
        print(f"hyprsetup: could not write the welcome marker: {exc}")


# ------------------------------------------------------------------- colors
def _rgb(hex_value: str) -> tuple[float, float, float]:
    return tuple(int(hex_value[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _theme_rgb(widget: Gtk.Widget, name: str) -> tuple[float, float, float] | None:
    """A libadwaita named color (window_bg_color…), or None if not found."""
    try:
        found, rgba = widget.get_style_context().lookup_color(name)
    except (AttributeError, TypeError):
        return None
    return (rgba.red, rgba.green, rgba.blue) if found else None


BG_TOP, BG_BOTTOM = _rgb("24273a"), _rgb("181926")
BOWL_A, BOWL_B = _rgb("f5a97f"), _rgb("ed8796")
SOUP_A, SOUP_B = _rgb("8bd5ca"), _rgb("7dc4e4")
STEAM_A, STEAM_B = _rgb("c6a0f6"), _rgb("8aadf4")
DARK, SURFACE, BLUE = _rgb("181926"), _rgb("363a4f"), _rgb("8aadf4")
GREEN, YELLOW, MAUVE, TEXT = _rgb("a6da95"), _rgb("eed49f"), _rgb("c6a0f6"), _rgb("cad3f5")

# ------------------------------------------------------------------ timing
#: The scene is drawn in the logo's 256-unit coordinates (bowl rim at y=136).
RIM_Y = 136.0
FALL = 0.85          # how long a piece takes to fall (s)
SINK = 0.35          # sinking into the soup
#: (kind, time it starts falling, start x, landing x)
DROPS = (
    ("bar", 0.55, 20.0, 110.0),
    ("window", 1.00, 236.0, 150.0),
    ("terminal", 1.45, 40.0, 100.0),
    ("wallpaper", 1.90, 220.0, 140.0),
    ("notify", 2.35, 128.0, 126.0),
)
STEAM_AT = 3.25      # steam and name
DURATION = 4.9       # then switch to the choice screen


def _ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def _mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b, strict=False))


def _round_rect(cr, x, y, w, h, r) -> None:
    r = min(r, w / 2, h / 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


# ---------------------------------------------------------------- pieces ----
# Each piece is drawn centered on (0,0); position/rotation/scale are up to the caller.
def _draw_bar(cr) -> None:
    _round_rect(cr, -34, -7, 68, 14, 7)
    cr.set_source_rgb(*DARK)
    cr.fill()
    for i, colour in enumerate((BLUE, MAUVE, GREEN)):
        cr.arc(-25 + i * 8, 0, 2.6, 0, 2 * math.pi)
        cr.set_source_rgb(*colour)
        cr.fill()
    _round_rect(cr, -4, -3, 14, 6, 3)
    cr.set_source_rgb(*TEXT)
    cr.fill()
    _round_rect(cr, 16, -3, 12, 6, 3)
    cr.set_source_rgb(*YELLOW)
    cr.fill()


def _draw_window(cr) -> None:
    _round_rect(cr, -24, -18, 48, 36, 6)
    cr.set_source_rgb(*SURFACE)
    cr.fill_preserve()
    cr.set_line_width(2.2)
    cr.set_source_rgb(*BLUE)
    cr.stroke()
    for i, colour in enumerate((_rgb("ed8796"), YELLOW, GREEN)):
        cr.arc(-16 + i * 6, -11, 2, 0, 2 * math.pi)
        cr.set_source_rgb(*colour)
        cr.fill()
    cr.set_source_rgba(*TEXT, 0.5)
    for i, width in enumerate((30, 22, 26)):
        _round_rect(cr, -16, -3 + i * 6, width, 3, 1.5)
        cr.fill()


def _draw_terminal(cr) -> None:
    _round_rect(cr, -24, -17, 48, 34, 6)
    cr.set_source_rgb(*DARK)
    cr.fill_preserve()
    cr.set_line_width(1.6)
    cr.set_source_rgb(*SURFACE)
    cr.stroke()
    cr.set_source_rgb(*GREEN)
    cr.set_line_width(2.6)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.move_to(-15, -7)
    cr.line_to(-8, -1)
    cr.line_to(-15, 5)
    cr.stroke()
    cr.set_source_rgb(*TEXT)
    cr.move_to(-4, 6)
    cr.line_to(8, 6)
    cr.stroke()


def _draw_wallpaper(cr) -> None:
    _round_rect(cr, -24, -16, 48, 32, 5)
    cr.save()
    cr.clip_preserve()
    cr.set_source_rgb(*_rgb("91d7e3"))
    cr.fill()
    cr.move_to(-26, 17)
    cr.line_to(-8, -4)
    cr.line_to(4, 8)
    cr.line_to(12, 0)
    cr.line_to(28, 17)
    cr.close_path()
    cr.set_source_rgb(*_rgb("5b6078"))
    cr.fill()
    cr.arc(12, -8, 4.5, 0, 2 * math.pi)
    cr.set_source_rgb(*YELLOW)
    cr.fill()
    cr.restore()


def _draw_notify(cr) -> None:
    _round_rect(cr, -26, -12, 52, 24, 8)
    cr.set_source_rgb(*SURFACE)
    cr.fill()
    cr.arc(-15, 0, 6, 0, 2 * math.pi)
    cr.set_source_rgb(*MAUVE)
    cr.fill()
    cr.set_source_rgba(*TEXT, 0.8)
    _round_rect(cr, -5, -5, 24, 3.5, 1.7)
    cr.fill()
    cr.set_source_rgba(*TEXT, 0.45)
    _round_rect(cr, -5, 2, 17, 3.5, 1.7)
    cr.fill()


_PIECES = {"bar": _draw_bar, "window": _draw_window, "terminal": _draw_terminal,
           "wallpaper": _draw_wallpaper, "notify": _draw_notify}


class SoupIntro(Gtk.DrawingArea):
    """Soup-stirring animation. ``on_done()`` is called once when it ends.

    ``loop``: does not end at DURATION, keeps stirring until ``finish()``
    (theme transition, transition.py). ``subtitle`` is the line under the name.
    ``speed`` speeds up the timeline; ``max_scale`` is the most the scene may
    be enlarged (0: as much as fits). The welcome screen uses both: a
    five-second scene filling a large window could not be taken in "at a
    glance".
    """

    def __init__(self, on_done, loop: bool = False,
                 subtitle: str = "Your desktop is cooking…", max_fps: int = 0,
                 speed: float = 1.0, max_scale: float = 0.0) -> None:
        super().__init__(hexpand=True, vexpand=True)
        self._on_done = on_done
        self._loop = loop
        self._speed = speed
        self._max_scale = max_scale
        # 0: draw every frame. During the theme transition on a 180 Hz display
        # cairo maxed out a core; 60 fps is indistinguishable to the eye.
        self._frame_gap = 1.0 / max_fps if max_fps else 0.0
        self._drawn_at = -1.0
        self.subtitle = subtitle
        self._start: int | None = None
        self._elapsed = 0.0
        self._finished = False
        #: Background (top, bottom) and name color. Defaults to the logo's dark
        #: palette; the theme transition (transition.py) uses that. The welcome
        #: screen ties it to the GTK theme via follow_theme(), so it does not
        #: look like an app separate from the settings app.
        self.bg_colors = (BG_TOP, BG_BOTTOM)
        self.fg = TEXT
        self.set_draw_func(self._draw)
        self._tick = self.add_tick_callback(self._on_tick)

        click = Gtk.GestureClick()
        click.connect("released", lambda *_a: self.finish())
        self.add_controller(click)
        self.set_focusable(True)
        self.set_cursor(Gdk.Cursor.new_from_name("pointer", None))

    def finish(self) -> None:
        if self._finished:
            return
        self._finished = True
        if self._tick:
            self.remove_tick_callback(self._tick)
            self._tick = 0
        self._on_done()

    def _on_tick(self, _widget, clock) -> bool:
        now = clock.get_frame_time()
        if self._start is None:
            self._start = now
        self._elapsed = (now - self._start) / 1_000_000 * self._speed
        if self._elapsed - self._drawn_at >= self._frame_gap:
            self._drawn_at = self._elapsed
            self.queue_draw()
        if self._elapsed >= DURATION and not self._loop:
            self._tick = 0
            GLib.idle_add(lambda: (self.finish(), False)[1])
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    # ---------------------------------------------------------- drawing --
    @property
    def elapsed(self) -> float:
        return self._elapsed

    def follow_theme(self) -> None:
        """Take the background and text from the GTK theme's window colors.

        Re-read on realize and whenever the theme (light/dark, accent) changes.
        The bowl, soup and falling pieces keep the logo's colors; they are an
        illustration, not UI.
        """
        def read(*_args) -> None:
            bg = _theme_rgb(self, "window_bg_color")
            fg = _theme_rgb(self, "window_fg_color")
            if bg is not None:
                # Slight diagonal gradient: a flat color made the animation look flat.
                self.bg_colors = (bg, _mix(bg, fg or bg, 0.06))
            if fg is not None:
                self.fg = fg
            self.queue_draw()

        self.connect("realize", read)
        manager = Adw.StyleManager.get_default()
        for prop in ("dark", "accent-color", "high-contrast"):
            manager.connect(f"notify::{prop}", lambda *_a: GLib.idle_add(
                lambda: (read(), False)[1]))

    def _draw(self, _area, cr, width, height) -> None:
        self.paint_background(cr, width, height)
        self.paint_scene(cr, width, height)

    def paint_background(self, cr, width, height, alpha: float = 1.0) -> None:
        """Background gradient over the whole screen."""
        top, bottom = self.bg_colors
        grad = cairo.LinearGradient(0, 0, width, height)
        grad.add_color_stop_rgba(0, *top, alpha)
        grad.add_color_stop_rgba(1, *bottom, alpha)
        cr.set_source(grad)
        cr.paint()

    def paint_scene(self, cr, width, height) -> None:
        t = self._elapsed
        # Scene spans y=-70..320 units: room for falling pieces above, the name below.
        scale = min(width / 300, height / 390)
        if self._max_scale:
            scale = min(scale, self._max_scale)
        cr.translate(width / 2 - 128 * scale, height / 2 - 125 * scale)
        cr.scale(scale, scale)

        appear = _ease_out(t / 0.55)
        # The bowl rises gently from below.
        cr.translate(0, (1 - appear) * 40)

        self._draw_steam(cr, t)
        self._draw_drops(cr, t)
        cr.push_group()
        self._draw_bowl(cr, t)
        self._draw_splashes(cr, t)
        self._draw_ladle(cr, t)
        cr.pop_group_to_source()
        cr.paint_with_alpha(appear)
        self._draw_title(cr, t)

    def _draw_bowl(self, cr, t: float) -> None:
        # body
        cr.move_to(40, RIM_Y)
        cr.line_to(216, RIM_Y)
        cr.curve_to(216, 184, 178, 212, 128, 212)
        cr.curve_to(78, 212, 40, 184, 40, RIM_Y)
        cr.close_path()
        grad = cairo.LinearGradient(40, RIM_Y, 216, 212)
        grad.add_color_stop_rgb(0, *BOWL_A)
        grad.add_color_stop_rgb(1, *BOWL_B)
        cr.set_source(grad)
        cr.fill()
        _round_rect(cr, 100, 210, 56, 10, 5)
        cr.set_source_rgb(*BOWL_B)
        cr.fill()

        # soup surface; its color shifts a little with each piece that lands
        landed = sum(1 for _k, start, _x0, _x1 in DROPS if t > start + FALL)
        shift = landed / len(DROPS)
        cr.save()
        cr.translate(128, RIM_Y)
        cr.scale(1, 16 / 88)
        cr.arc(0, 0, 88, 0, 2 * math.pi)
        cr.restore()
        soup = cairo.LinearGradient(40, 0, 216, 0)
        soup.add_color_stop_rgb(0, *_mix(SOUP_A, STEAM_A, shift * 0.45))
        soup.add_color_stop_rgb(1, *_mix(SOUP_B, STEAM_B, shift * 0.3))
        cr.set_source(soup)
        cr.fill_preserve()
        cr.save()
        cr.clip()
        # stirring swirl: rotating arcs
        spin = t * 3.2
        cr.translate(128, RIM_Y)
        cr.scale(1, 16 / 88)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        for radius, width, offset in ((26, 5, 0.0), (48, 6, 2.1), (70, 5, 4.0)):
            cr.set_line_width(width)
            cr.set_source_rgba(1, 1, 1, 0.28)
            start = spin * (1.2 - radius / 140) + offset
            cr.arc(0, 0, radius, start, start + 1.9)
            cr.stroke()
        cr.restore()
        cr.new_path()
        # rim line
        cr.save()
        cr.translate(128, RIM_Y)
        cr.scale(1, 16 / 88)
        cr.arc(0, 0, 88, 0, 2 * math.pi)
        cr.restore()
        cr.set_line_width(5)
        cr.set_source_rgb(*BOWL_A)
        cr.stroke()

    def _ladle_angle(self, t: float) -> float:
        return max(0.0, t - 0.3) * 4.2

    def _draw_ladle(self, cr, t: float) -> None:
        if t < 0.3:
            return
        angle = self._ladle_angle(t)
        hx = 128 + 50 * math.cos(angle)
        hy = RIM_Y + 8 * math.sin(angle)
        # the handle points up-right and sways slightly while stirring
        tip_x = 214 + 10 * math.cos(angle)
        tip_y = 40 + 6 * math.sin(angle * 0.5)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_width(7)
        cr.set_source_rgb(*_rgb("f4dbd6"))
        cr.move_to(hx, hy - 3)
        cr.line_to(tip_x, tip_y)
        cr.stroke()
        cr.set_line_width(3)
        cr.set_source_rgba(1, 1, 1, 0.55)
        cr.move_to(hx + (tip_x - hx) * 0.55, hy + (tip_y - hy) * 0.55 - 1)
        cr.line_to(tip_x - 3, tip_y + 2)
        cr.stroke()
        # the ladle head dipping into the soup
        cr.save()
        cr.translate(hx, hy)
        cr.scale(1, 0.45)
        cr.arc(0, 0, 11, 0, 2 * math.pi)
        cr.restore()
        cr.set_source_rgba(*_rgb("f4dbd6"), 0.85)
        cr.fill()

    def _drop_state(self, t: float, start: float, x0: float, x1: float):
        """(x, y, rotation, scale) or None if not visible"""
        local = t - start
        if local < 0:
            return None
        if local < FALL:
            p = local / FALL
            y = -55 + (RIM_Y - 6 + 55) * p * p        # gravity
            x = x0 + (x1 - x0) * _ease_out(p)
            return x, y, (1 - p) * (2.4 if x0 < x1 else -2.4), 1.0
        sink = (local - FALL) / SINK
        if sink >= 1:
            return None
        return (x1, RIM_Y - 6 + 26 * sink, 0.0, 1 - 0.5 * sink)

    def _draw_drops(self, cr, t: float) -> None:
        # Pieces are drawn BEFORE the bowl: once they land, the bowl body and
        # soup surface cover their lower half, which is what "fell in" looks like.
        for kind, start, x0, x1 in DROPS:
            state = self._drop_state(t, start, x0, x1)
            if state is None:
                continue
            x, y, rot, scale = state
            cr.save()
            cr.translate(x, y)
            cr.rotate(rot)
            cr.scale(scale * 1.35, scale * 1.35)
            # fade in from the top of the screen instead of popping in
            cr.push_group()
            _PIECES[kind](cr)
            cr.pop_group_to_source()
            cr.paint_with_alpha(min(1.0, (t - start) / 0.15))
            cr.restore()

    def _draw_splashes(self, cr, t: float) -> None:
        for index, (_kind, start, _x0, x1) in enumerate(DROPS):
            local = t - start - FALL
            if not 0 <= local < 0.7:
                continue
            p = local / 0.7
            # ring
            cr.save()
            cr.translate(x1, RIM_Y)
            cr.scale(1, 0.22)
            cr.arc(0, 0, 8 + 34 * _ease_out(p), 0, 2 * math.pi)
            cr.restore()
            cr.set_line_width(2.4)
            cr.set_source_rgba(1, 1, 1, 0.6 * (1 - p))
            cr.stroke()
            # droplets
            for d in range(6):
                spread = (d - 2.5) * 9 + (index % 2) * 3
                h = 26 + (d * 7 % 12)
                dx = x1 + spread * p * 1.4
                dy = RIM_Y - 4 - h * 4 * p * (1 - p)
                cr.arc(dx, dy, 3.4 * (1 - p * 0.5), 0, 2 * math.pi)
                cr.set_source_rgba(*_mix(SOUP_A, (1, 1, 1), 0.35), 1 - p)
                cr.fill()

    def _draw_steam(self, cr, t: float) -> None:
        local = t - STEAM_AT
        if local <= 0:
            return
        p = _ease_out(local / 0.9)
        rise = (1 - p) * 26
        grad = cairo.LinearGradient(0, 118, 0, 36)
        grad.add_color_stop_rgb(0, *STEAM_A)
        grad.add_color_stop_rgb(1, *STEAM_B)
        cr.push_group()
        cr.set_source(grad)
        cr.set_line_width(9)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        wobble = math.sin(t * 3) * 3
        for x in (86, 170):
            cr.move_to(x, 118 + rise)
            cr.curve_to(x - 16 + wobble, 102 + rise, x + 16 - wobble, 88 + rise,
                        x, 68 + rise)
            cr.stroke()
        # the middle drop, as in the logo
        cr.move_to(128, 36 + rise)
        cr.curve_to(112, 60 + rise, 102, 76 + rise, 102, 92 + rise)
        cr.arc_negative(128, 92 + rise, 26, math.pi, 0)
        cr.curve_to(154, 76 + rise, 144, 60 + rise, 128, 36 + rise)
        cr.close_path()
        cr.fill()
        cr.pop_group_to_source()
        cr.paint_with_alpha(p)

    def _draw_title(self, cr, t: float) -> None:
        local = t - STEAM_AT - 0.2
        if local <= 0:
            return
        p = _ease_out(local / 0.7)
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(Pango.FontDescription.from_string("Sans Bold 30"))
        layout.set_text("Souprland", -1)
        _ink, logical = layout.get_pixel_extents()
        cr.move_to(128 - logical.width / 2, 228 + (1 - p) * 10)
        cr.set_source_rgba(*self.fg, p)
        PangoCairo.show_layout(cr, layout)

        sub = PangoCairo.create_layout(cr)
        # In the small scene (max_scale) the subtitle shrank to ~8 px; keep it
        # at least ~12 px on screen.
        size = max(11.0, 12.0 / max(cr.get_matrix().xx, 0.01))
        sub.set_font_description(Pango.FontDescription.from_string(f"Sans {size:.1f}"))
        sub.set_text(self.subtitle, -1)
        _ink, logical = sub.get_pixel_extents()
        cr.move_to(128 - logical.width / 2, 288 + (1 - p) * 10)
        cr.set_source_rgba(*self.fg, 0.6 * p)
        PangoCairo.show_layout(cr, sub)


# ---------------------------------------------------------------- choice ----
#: The welcome screen carries the same GTK theme as the settings app: colors
#: come from libadwaita's named colors (window background, card, accent).
#: It used to use the logo's fixed dark palette and looked like a completely
#: different app from the settings.
_CSS = """
.souprland-welcome {
    background: linear-gradient(135deg, @window_bg_color,
                                mix(@window_bg_color, @window_fg_color, 0.06));
    color: @window_fg_color;
}
.souprland-welcome headerbar { background: transparent; box-shadow: none; }
.souprland-welcome button.card {
    background: @card_bg_color;
    border-radius: 18px;
    box-shadow: inset 0 0 0 1px alpha(@window_fg_color, 0.08);
}
.souprland-welcome button.card:hover {
    background: mix(@card_bg_color, @window_fg_color, 0.06);
}
.souprland-welcome button.card.suggested-action {
    background: alpha(@accent_bg_color, 0.22);
    color: @window_fg_color;
    box-shadow: inset 0 0 0 1px alpha(@accent_bg_color, 0.7);
}
.souprland-welcome button.card.suggested-action:hover {
    background: alpha(@accent_bg_color, 0.32);
}
.souprland-welcome .intro-media {
    background: alpha(@window_fg_color, 0.05);
    border-radius: 18px;
    box-shadow: 0 0 0 1px alpha(@accent_color, 0.3),
                0 12px 40px alpha(#000000, 0.25);
}
.souprland-welcome .intro-placeholder {
    border: 2px dashed alpha(@window_fg_color, 0.3);
    border-radius: 14px;
}
.souprland-welcome .intro-draft {
    background: alpha(@accent_bg_color, 0.18);
    color: @accent_color;
    border-radius: 999px;
    padding: 2px 10px;
}
.souprland-welcome .intro-title { color: @accent_color; }
.souprland-welcome .intro-dot { color: @accent_color; font-size: 0.7em;
                                margin-top: 0.35em; }
"""


def _choice_card(icon: str, title: str, text: str, on_click,
                 suggested: bool = False) -> Gtk.Button:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                  margin_top=22, margin_bottom=22, margin_start=18, margin_end=18)
    image = Gtk.Image.new_from_icon_name(icon)
    image.set_pixel_size(48)
    box.append(image)
    heading = Gtk.Label(label=title, wrap=True, justify=Gtk.Justification.CENTER)
    heading.add_css_class("title-3")
    box.append(heading)
    body = Gtk.Label(label=text, wrap=True, justify=Gtk.Justification.CENTER,
                     max_width_chars=28)
    body.add_css_class("dim-label")
    box.append(body)
    button = Gtk.Button(child=box)
    button.add_css_class("card")
    if suggested:
        button.add_css_class("suggested-action")
    button.set_size_request(260, -1)
    button.connect("clicked", lambda _b: on_click())
    return button


class WelcomeChoice(Adw.Bin):
    """"How do you want to start?": wizard, profile, or skip.

    ``on_pick(page_id)``: the chosen page id ("wizard", "profiles") or ""
    (skip: the settings app opens as is).
    """

    def __init__(self, root: Path, on_pick) -> None:
        super().__init__()
        ensure_css(_CSS)
        self.add_css_class("souprland-welcome")
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar(show_title=False)
        header.add_css_class("flat")
        skip_top = Gtk.Button(label="Skip")
        skip_top.set_tooltip_text("Go straight to the settings")
        skip_top.connect("clicked", lambda _b: on_pick(""))
        header.pack_end(skip_top)
        toolbar.add_top_bar(header)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18,
                      halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
                      margin_start=16, margin_end=16, margin_bottom=24)
        logo = root / "assets" / "souprland.svg"
        image = (Gtk.Image.new_from_file(str(logo)) if logo.is_file()
                 else Gtk.Image.new_from_icon_name("applications-graphics-symbolic"))
        image.set_pixel_size(96)
        box.append(image)
        title = Gtk.Label(label="Welcome to Souprland")
        title.add_css_class("title-1")
        box.append(title)
        subtitle = Gtk.Label(
            label="How do you want to set up your desktop? You can change "
                  "everything later from the menu on the left.",
            wrap=True, justify=Gtk.Justification.CENTER, max_width_chars=60)
        subtitle.add_css_class("dim-label")
        box.append(subtitle)

        cards = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
                            homogeneous=True, max_children_per_line=2,
                            min_children_per_line=1, column_spacing=16,
                            row_spacing=16, halign=Gtk.Align.CENTER)
        cards.set_margin_top(10)
        cards.append(_choice_card(
            "starred-symbolic", "Start from scratch",
            "The Setup Wizard asks step by step: windows, colors, wallpaper, "
            "terminal, bar… Every choice gets a live preview.",
            lambda: on_pick("wizard"), suggested=True))
        cards.append(_choice_card(
            "view-paged-symbolic", "Pick a profile",
            "Install a desktop you like from the gallery in one click, then "
            "change it as much as you want.",
            lambda: on_pick("profiles")))
        # FlowBox children draw their own focus ring; the card itself is
        # already a button.
        child = cards.get_first_child()
        while child is not None:
            child.set_focusable(False)
            child = child.get_next_sibling()
        box.append(cards)

        skip = Gtk.Button(label="Skip for now, open settings",
                          halign=Gtk.Align.CENTER)
        skip.add_css_class("flat")
        skip.add_css_class("pill")
        skip.connect("clicked", lambda _b: on_pick(""))
        box.append(skip)

        toolbar.set_content(Gtk.ScrolledWindow(
            child=box, hscrollbar_policy=Gtk.PolicyType.NEVER))
        self.set_child(toolbar)


class IntroMedia(Gtk.Box):
    """A tour page's media: GIF (frame by frame), image or video.

    GTK4's Gtk.Picture shows only the first frame of a GIF; frames are fed via
    GdkPixbuf.PixbufAnimation with their own delays and only advance while
    the widget is on screen (so hidden pages do not eat CPU). .webm/.mp4 play
    muted and looped via Gtk.MediaFile. If the file does not exist yet (GIFs
    are added later), a dashed box showing its path appears instead.
    """

    #: 16:9 box when there is no media (and for video).
    WIDTH, HEIGHT = 480, 270
    #: The image box takes the image's aspect ratio, fitted within these limits.
    MAX_WIDTH, MAX_HEIGHT = 560, 380

    def __init__(self, path: Path | None, label: str) -> None:
        super().__init__(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.set_size_request(self.WIDTH, self.HEIGHT)
        self._anim_iter = None
        self._timer = 0
        self._picture: Gtk.Picture | None = None
        self._media = None
        if path is None or not path.is_file():
            self._placeholder(path, label)
            return
        self.add_css_class("intro-media")
        self.set_overflow(Gtk.Overflow.HIDDEN)
        picture = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN,
                              hexpand=True, vexpand=True)
        self._picture = picture
        self.append(picture)
        if path.suffix.lower() in (".webm", ".mp4", ".mkv", ".mov"):
            self._media = Gtk.MediaFile.new_for_filename(str(path))
            self._media.set_loop(True)
            self._media.set_muted(True)
            picture.set_paintable(self._media)
        else:
            try:
                anim = GdkPixbuf.PixbufAnimation.new_from_file(str(path))
            except GLib.Error:
                self.remove(picture)
                self._placeholder(path, label)
                return
            self._fit(anim.get_width(), anim.get_height())
            if anim.is_static_image():
                picture.set_paintable(
                    Gdk.Texture.new_for_pixbuf(anim.get_static_image()))
            else:
                self._anim_iter = anim.get_iter(None)
                self._show_frame()
        self.connect("map", lambda _w: self._play(True))
        self.connect("unmap", lambda _w: self._play(False))

    def _fit(self, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            return
        scale = min(self.MAX_WIDTH / width, self.MAX_HEIGHT / height)
        self.set_size_request(round(width * scale), round(height * scale))

    def _placeholder(self, path: Path | None, label: str) -> None:
        self.add_css_class("intro-placeholder")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                      hexpand=True, valign=Gtk.Align.CENTER)
        icon = Gtk.Image.new_from_icon_name("image-x-generic-symbolic")
        icon.set_pixel_size(48)
        icon.add_css_class("dim-label")
        box.append(icon)
        name = path.name if path else "(no media)"
        text = Gtk.Label(label=f"{label}: media goes here: assets/intro/{name}",
                         wrap=True, justify=Gtk.Justification.CENTER)
        text.add_css_class("dim-label")
        box.append(text)
        self.append(box)

    def _show_frame(self) -> None:
        pixbuf = self._anim_iter.get_pixbuf()
        self._picture.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))

    def _tick(self) -> bool:
        self._timer = 0
        self._anim_iter.advance(None)
        self._show_frame()
        self._schedule()
        return False

    def _schedule(self) -> None:
        delay = self._anim_iter.get_delay_time()
        if delay >= 0:
            self._timer = GLib.timeout_add(max(20, delay), self._tick)

    def _play(self, on: bool) -> None:
        if self._media is not None:
            (self._media.play if on else self._media.pause)()
        if self._anim_iter is None:
            return
        if on and not self._timer:
            self._schedule()
        elif not on and self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0


_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def _link_markup(line: str) -> str:
    """Markdown ``[text](url)`` → clickable Pango link."""
    out, last = [], 0
    for match in _LINK.finditer(line):
        out.append(GLib.markup_escape_text(line[last:match.start()]))
        out.append(f'<a href="{GLib.markup_escape_text(match.group(2))}">'
                   f"{GLib.markup_escape_text(match.group(1))}</a>")
        last = match.end()
    out.append(GLib.markup_escape_text(line[last:]))
    return "".join(out)


def _intro_page(root: Path, page) -> Gtk.Widget:
    """Wide window: media left, text right; narrow window: stacked."""
    layout = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=36,
                     halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
                     margin_start=24, margin_end=24, margin_top=12,
                     margin_bottom=12)
    # A page without media (e.g. thanks) gives the full width to the text.
    chars = 40 if page.media else 64
    if page.media:
        layout.append(IntroMedia(page.media_path(root), page.title))

    text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                   valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
    text.set_size_request(340, -1)
    title = Gtk.Label(label=page.title, wrap=True, xalign=0,
                      max_width_chars=24, margin_bottom=8)
    title.add_css_class("title-1")
    title.add_css_class("intro-title")
    text.append(title)
    if page.draft:
        draft = Gtk.Label(label="draft", halign=Gtk.Align.START)
        draft.add_css_class("intro-draft")
        draft.add_css_class("caption")
        text.append(draft)
    for line in intro_mod.body_of(root, page):
        if line.startswith("### "):
            head = Gtk.Label(label=line[4:], wrap=True, xalign=0,
                             margin_top=10)
            head.add_css_class("heading")
            head.add_css_class("intro-subtitle")
            text.append(head)
            continue
        if line.startswith("- "):
            # The bullet is a Pac-Man pellet.
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10,
                          margin_start=4)
            dot = Gtk.Label(label="●", valign=Gtk.Align.START)
            dot.add_css_class("intro-dot")
            row.append(dot)
            row.append(Gtk.Label(label=_link_markup(line[2:]), use_markup=True,
                                 wrap=True, xalign=0, max_width_chars=chars))
            text.append(row)
            continue
        label = Gtk.Label(label=_link_markup(line), use_markup=True, wrap=True,
                          xalign=0, max_width_chars=chars, margin_top=6)
        label.add_css_class("dim-label")
        text.append(label)
    layout.append(text)

    scroller = Gtk.ScrolledWindow(child=layout, hexpand=True, vexpand=True,
                                  hscrollbar_policy=Gtk.PolicyType.NEVER)
    # hexpand is required: otherwise Adw.Carousel gives the page only its
    # natural width (~600 px); neighbor pages show at the edges, and when the
    # scroll ends the content snaps into an off-center spot and the narrow
    # layout kicks in.
    page_bin = Adw.BreakpointBin(child=scroller, hexpand=True, vexpand=True)
    page_bin.set_size_request(360, 300)
    # Widest side-by-side page: 498 px GIF + 36 + 340 px text + margins.
    narrow = Adw.Breakpoint.new(Adw.BreakpointCondition.parse(
        "max-width: 1000px"))
    narrow.add_setter(layout, "orientation", Gtk.Orientation.VERTICAL)
    narrow.add_setter(layout, "spacing", 18)
    page_bin.add_breakpoint(narrow)
    return page_bin


class IntroTour(Adw.Bin):
    """Step-by-step tour: GIF + text page by page. ``on_done()`` moves to the choice."""

    def __init__(self, root: Path, pages, on_done) -> None:
        super().__init__()
        ensure_css(_CSS)
        self.add_css_class("souprland-welcome")
        self._on_done = on_done
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar(show_title=False)
        header.add_css_class("flat")
        skip = Gtk.Button(label="Skip tour")
        skip.set_tooltip_text("Skip the introduction (Esc)")
        skip.connect("clicked", lambda _b: on_done())
        header.pack_end(skip)
        toolbar.add_top_bar(header)

        self.carousel = Adw.Carousel(hexpand=True, vexpand=True,
                                     allow_scroll_wheel=False)
        for page in pages:
            self.carousel.append(_intro_page(root, page))
        self.carousel.connect("page-changed", lambda *_a: self._update())

        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12,
                         margin_start=24, margin_end=24, margin_bottom=20,
                         margin_top=8)
        self.back = Gtk.Button(label="Back")
        self.back.add_css_class("flat")
        self.back.add_css_class("pill")
        self.back.connect("clicked", lambda _b: self.step(-1))
        bottom.append(self.back)
        dots = Adw.CarouselIndicatorDots(carousel=self.carousel, hexpand=True)
        bottom.append(dots)
        self.next = Gtk.Button(label="Next")
        self.next.add_css_class("suggested-action")
        self.next.add_css_class("pill")
        self.next.connect("clicked", lambda _b: self.step(1))
        bottom.append(self.next)

        single = self.carousel.get_n_pages() <= 1
        self.back.set_visible(not single)
        dots.set_opacity(0 if single else 1)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.append(self.carousel)
        content.append(bottom)
        toolbar.set_content(content)
        self.set_child(toolbar)
        self._update()

    def _index(self) -> int:
        return round(self.carousel.get_position())

    def _update(self) -> None:
        index, count = self._index(), self.carousel.get_n_pages()
        self.back.set_sensitive(index > 0)
        self.next.set_label("Let's go" if index >= count - 1 else "Next")

    def step(self, delta: int) -> None:
        index = self._index() + delta
        if index >= self.carousel.get_n_pages():
            self._on_done()
            return
        if index < 0:
            return
        self.carousel.scroll_to(self.carousel.get_nth_page(index), True)


class Welcome(Gtk.Stack):
    """Animation → choice. ``on_finish(page_id)`` is called at the end."""

    def __init__(self, root: Path, on_finish) -> None:
        super().__init__(transition_type=Gtk.StackTransitionType.CROSSFADE,
                         transition_duration=450)
        self._on_finish = on_finish
        self.intro: SoupIntro | None = None
        settings = Gtk.Settings.get_default()
        animate = settings is None or settings.get_property("gtk-enable-animations")
        pages = intro_mod.load(root)
        self.tour: IntroTour | None = None
        if pages:
            self.tour = IntroTour(root, pages, self._show_choice)
            self.add_named(self.tour, "tour")
        after_intro = "tour" if pages else "choice"
        if animate:
            # ~3 s, bowl at most ~200×260 px: it should evoke the logo, not fill the window.
            self.intro = SoupIntro(lambda: self.set_visible_child_name(after_intro),
                                   speed=1.6, max_scale=0.68)
            self.intro.follow_theme()
            self.add_named(self.intro, "intro")
        self.add_named(WelcomeChoice(root, self._picked), "choice")
        self.set_visible_child_name("intro" if animate else after_intro)

    def on_key(self, _controller, keyval, _keycode, _state) -> bool:
        if self.get_visible_child_name() == "intro" and keyval in (
                Gdk.KEY_Escape, Gdk.KEY_Return, Gdk.KEY_space, Gdk.KEY_KP_Enter):
            self.intro.finish()
            return True
        if self.get_visible_child_name() == "tour" and self.tour is not None:
            if keyval == Gdk.KEY_Escape:
                self._show_choice()
                return True
            if keyval in (Gdk.KEY_Right, Gdk.KEY_Return, Gdk.KEY_KP_Enter):
                self.tour.step(1)
                return True
            if keyval == Gdk.KEY_Left:
                self.tour.step(-1)
                return True
        if self.get_visible_child_name() == "choice" and keyval == Gdk.KEY_Escape:
            self._picked("")
            return True
        return False

    def _show_choice(self) -> None:
        self.set_visible_child_name("choice")

    def _picked(self, page_id: str) -> None:
        mark_done()
        self._on_finish(page_id)
