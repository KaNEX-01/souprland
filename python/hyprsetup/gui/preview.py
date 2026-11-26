"""Live previews and measurement diagrams.

Main widgets:

* ``DesktopPreview``: a mock desktop that draws gaps, borders, rounding,
  shadow and opacity close to real Hyprland behavior.
* ``LayoutDiagram``: a measurement diagram marking the same settings with
  arrows and labels, so you can see at a glance which number changes which
  part of the screen.
* ``BarPreview``: a preview that draws the status bar with its modules in the
  chosen zones (left/center/right).

All of them update instantly as settings change; the goal is to see what each
setting does without having to read about it.
"""

from __future__ import annotations

import hashlib
import math
import tempfile
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from .. import cursors as cursors_mod  # noqa: E402
from .. import render as render_mod  # noqa: E402
from .. import settings as schema  # noqa: E402
from .. import themes  # noqa: E402
from .. import wallpaper as wallpaper_mod  # noqa: E402

# Virtual screen resolution the preview represents
VIRTUAL_W, VIRTUAL_H = 1920.0, 1080.0

# ------------------------------------------------------------ wallpaper ---
# Previews show the real wallpaper: the user's own image if there is one,
# otherwise a small copy generated from the profile's WALLPAPER_STYLE pattern.
# Generation happens once per theme+pattern and is cached; this is required
# because the gallery page draws 48 cards at once.
_WP_SIZE = (384, 216)
_wp_cache: dict[tuple[str, str], "object | None"] = {}
_wp_dir: Path | None = None


def _image_surface(path: Path):
    """Turn an image (PNG/JPEG/WebP) into a preview-sized cairo surface.

    Only PNG used to be read: profiles with JPEG wallpapers (Wallhaven picks)
    fell back to a solid color on their card. Large images are scaled down to
    1280px once, since the gallery draws 48 cards at the same time.
    """
    import cairo
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), 1280, 1280, True)
    except GLib.Error:
        return None
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, pixbuf.get_width(),
                                 pixbuf.get_height())
    cr = cairo.Context(surface)
    Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
    cr.paint()
    return surface


def _wallpaper_surface(theme: str, style: str, custom_path: str = "",
                       overrides: str = ""):
    """Return a cairo surface; None if it cannot be made (the caller falls back to a gradient)."""
    global _wp_dir
    import cairo

    if custom_path:
        path = Path(custom_path).expanduser()
        if path.is_file() and path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
            key = ("__file__", str(path))
            if key not in _wp_cache:
                _wp_cache[key] = _image_surface(path)
            if _wp_cache[key] is not None:
                return _wp_cache[key]

    if not style or style not in wallpaper_mod.STYLES:
        return None
    # CUSTOM_COLORS is part of the cache key too: otherwise changing
    # BG/SURFACE/BG_DARK via "Customize colors" never updated the wallpaper,
    # because the earlier render stayed cached forever under the (theme, style)
    # key (a custom color change showed on the window borders in the preview,
    # but the background stayed frozen in the old theme colors).
    key = (theme, style, overrides)
    if key in _wp_cache:
        return _wp_cache[key]
    try:
        if _wp_dir is None:
            _wp_dir = Path(tempfile.mkdtemp(prefix="hyprsetup-preview-"))
        suffix = f"-{hashlib.md5(overrides.encode()).hexdigest()[:8]}" if overrides else ""
        png = _wp_dir / f"{theme}-{style}{suffix}.png"
        if not png.is_file():
            wallpaper_mod.generate(theme, style, png, _WP_SIZE, overrides)
        _wp_cache[key] = cairo.ImageSurface.create_from_png(str(png))
    except Exception:
        # The preview must never crash the install or the window, under any condition.
        _wp_cache[key] = None
    return _wp_cache[key]


def _hex_to_rgb(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    return (int(value[0:2], 16) / 255,
            int(value[2:4], 16) / 255,
            int(value[4:6], 16) / 255)


def _rgbs(palette: dict[str, str], *keys: str) -> tuple[tuple[float, float, float], ...]:
    """Several palette colors at once: ``bg, fg = _rgbs(palette, "BG", "FG")``."""
    return tuple(_hex_to_rgb(palette[key]) for key in keys)


def _superellipse_arc(cr, cx: float, cy: float, radius: float, power: float,
                      start: float, end: float) -> None:
    """Draw a superellipse arc centered at (cx, cy) from angle ``start`` to ``end``.

    Point = center + r · (sign(cosθ)·|cosθ|^e, sign(sinθ)·|sinθ|^e)
    where e = 2/power. power=2 gives a perfect circle; larger values make the
    corner approach a square, matching Hyprland's ``decoration:rounding_power``.
    """
    steps = 16
    exponent = 2.0 / max(power, 0.1)
    for i in range(steps + 1):
        angle = start + (end - start) * (i / steps)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        dx = math.copysign(abs(cos_a) ** exponent, cos_a)
        dy = math.copysign(abs(sin_a) ** exponent, sin_a)
        cr.line_to(cx + radius * dx, cy + radius * dy)


def rounded_path(cr, x: float, y: float, w: float, h: float,
                 radius: float, power: float = 2.0) -> None:
    radius = max(0.0, min(radius, w / 2, h / 2))
    cr.new_sub_path()
    if radius < 0.6:
        cr.rectangle(x, y, w, h)
        return

    half = math.pi / 2
    # Clockwise: start at the top edge and go around the four corners in turn.
    cr.move_to(x + radius, y)
    cr.line_to(x + w - radius, y)
    _superellipse_arc(cr, x + w - radius, y + radius, radius, power, -half, 0)
    cr.line_to(x + w, y + h - radius)
    _superellipse_arc(cr, x + w - radius, y + h - radius, radius, power, 0, half)
    cr.line_to(x + radius, y + h)
    _superellipse_arc(cr, x + radius, y + h - radius, radius, power, half, math.pi)
    cr.line_to(x, y + radius)
    _superellipse_arc(cr, x + radius, y + radius, radius, power,
                      math.pi, math.pi + half)
    cr.close_path()


def _screen(cr, x: float, y: float, w: float, h: float, bg, bg_dark) -> None:
    """The mockup's desktop background: rounded corners, diagonal gradient."""
    cr.set_source(_linear(cr, x, y, x + w, y + h, bg, bg_dark))
    rounded_path(cr, x, y, w, h, 6, 2)
    cr.fill()



def _wpengine_preview(daemon: str, ident: str) -> str:
    """Preview of a profile that uses Wallpaper Engine: the item's own image.

    When a profile picks a Wallpaper Engine item (WALLPAPER_DAEMON=
    wallpaperengine + WPENGINE_ID) that item plays on the desktop; if the item
    is downloaded on this machine (Steam Workshop) its preview.jpg/gif is shown.
    """
    if daemon != "wallpaperengine" or not ident:
        return ""
    try:
        from .. import wpengine
        preview = wpengine.preview_path(ident)
        return str(preview) if preview is not None else ""
    except Exception:                                            # noqa: BLE001
        return ""

class _SettingsArea(Gtk.DrawingArea):
    """Common base for widgets that read settings and draw them."""

    SIZE: tuple[int, int] | None = None     # content size (set by subclasses)

    def __init__(self, get_setting, get_palette):
        super().__init__()
        self._get = get_setting
        self._palette = get_palette
        self._zoom = 1.0
        self.set_hexpand(True)
        if self.SIZE:
            self.set_content_width(self.SIZE[0])
            self.set_content_height(self.SIZE[1])
        self.set_draw_func(self._draw_zoomed)

    def set_zoom(self, factor: float) -> None:
        """Enlarge the mockup as a whole.

        The drawing code uses absolute pixels (font size, title bar height,
        labels): enlarging the widget only added space around same-sized text
        and the mockup kept looking small. Applying the scale as a cairo
        transform enlarges everything together, giving a zoomed-in version of
        the card preview with proportions intact.
        """
        self._zoom = max(0.1, float(factor))
        self.queue_draw()

    def _draw_zoomed(self, area, cr, width, height) -> None:
        if self._zoom != 1.0:
            cr.scale(self._zoom, self._zoom)
            width /= self._zoom
            height /= self._zoom
        self._draw(area, cr, width, height)

    # ----------------------------------------------------------- helpers ---
    def _num(self, key: str, fallback: float) -> float:
        try:
            return float(self._get(key))
        except (TypeError, ValueError):
            return fallback

    def _flag(self, key: str, fallback: bool = False) -> bool:
        value = str(self._get(key) or "").strip().lower()
        if value in ("true", "yes", "1", "on"):
            return True
        if value in ("false", "no", "0", "off"):
            return False
        return fallback

    def _draw(self, _area, cr, width, height) -> None:  # filled in by subclasses
        raise NotImplementedError


class DesktopPreview(_SettingsArea):
    """A mock desktop reflecting the settings."""

    SIZE = (340, 320)

    def __init__(self, get_setting, get_palette, has_component,
                 use_custom_wallpaper: bool = True, root: Path | None = None):
        super().__init__(get_setting, get_palette)
        self._has = has_component
        # False on gallery cards: if the user has their own wallpaper, all 48
        # cards would show it and profiles could not be told apart. True in
        # the live preview, because there the real question is "how will it
        # look on my machine".
        self._use_custom_wallpaper = use_custom_wallpaper
        # WALLPAPER_IMAGE (the profile's generated image shipped in the repo,
        # wallpapers/<profile>.png) is tried in every mode: unlike the user's
        # own WALLPAPER_PATH it is profile-specific and fixed, so it is safe to
        # show on gallery cards too. Skipped if no root is given.
        self._root = root
        #: Share of the width taken by windows (right-aligned). Gallery cards
        #: lower it: with tiled windows filling the screen the profile's
        #: wallpaper never showed and the cards looked like solid-color themes.
        self.window_share = 1.0
        # Subclasses (gallery cards) override this with a smaller constant; in
        # the live preview it is the floor that keeps Gtk.Paned from squeezing
        # the pane until narrow/tiled windows become unreadable.

    # ----------------------------------------------------------- drawing ---
    def _draw(self, _area, cr, width, height) -> None:
        if getattr(self, "_card", False):
            # On a card everything is drawn 35% larger: the 11pt text of a 28px
            # bar was unreadable on a 300px-wide card.
            zoom = 1.35
            cr.scale(zoom, zoom)
            width, height = width / zoom, height / zoom
        palette = self._palette()
        bg, bg_dark, surface, fg, subtext, accent, accent2 = _rgbs(
            palette, "BG", "BG_DARK", "SURFACE", "FG", "SUBTEXT", "ACCENT", "ACCENT2")

        # Fit the virtual screen into the widget
        scale = min(width / VIRTUAL_W, height / VIRTUAL_H)
        screen_w, screen_h = VIRTUAL_W * scale, VIRTUAL_H * scale
        ox, oy = (width - screen_w) / 2, (height - screen_h) / 2

        cr.save()
        cr.translate(ox, oy)

        # ------------------------------------------------------- wallpaper --
        # The real wallpaper is drawn if there is one; otherwise fall back to
        # the palette gradient. The variable is deliberately named wp_surface:
        # `surface` is the palette's surface color above and is used for
        # drawing windows below.
        custom_path = _wpengine_preview(self._get("WALLPAPER_DAEMON"),
                                        self._get("WPENGINE_ID"))
        if not custom_path and self._root:
            image = self._get("WALLPAPER_IMAGE")
            if image:
                custom_path = str(self._root / image)
        if not custom_path and self._use_custom_wallpaper:
            custom_path = self._get("WALLPAPER_PATH")
        wp_surface = _wallpaper_surface(
            self._get("THEME") or themes.DEFAULT,
            self._get("WALLPAPER_STYLE"),
            custom_path,
            self._get("CUSTOM_COLORS"))
        rounded_path(cr, 0, 0, screen_w, screen_h, 8, 2)
        if wp_surface is not None:
            cr.save()
            cr.clip_preserve()
            sw, sh = wp_surface.get_width(), wp_surface.get_height()
            cr.scale(screen_w / max(1, sw), screen_h / max(1, sh))
            cr.set_source_surface(wp_surface, 0, 0)
            cr.paint()
            cr.restore()
            cr.new_path()
            # BLUR used to be drawn only on the gradient background (when
            # wp_surface was None); as soon as a real wallpaper was selected
            # (practically always, WALLPAPER_STYLE always has a value) toggling
            # the switch changed nothing in the preview. Now the same soft blobs
            # are overlaid on the image too, more faintly.
            if self._flag("BLUR", True):
                self._draw_blobs(cr, screen_w, screen_h, accent, accent2,
                                 base_alpha=0.16)
        else:
            cr.set_source(_linear(cr, 0, 0, screen_w, screen_h, bg, bg_dark))
            cr.fill()
            # Soft color blobs to hint at the effect of blur
            if self._flag("BLUR", True):
                self._draw_blobs(cr, screen_w, screen_h, accent, accent2)

        gaps_out = self._num("GAPS_OUT", 12) * scale
        gaps_in = self._num("GAPS_IN", 5) * scale
        border = self._num("BORDER_SIZE", 2) * scale
        radius = self._num("ROUNDING", 10) * scale
        power = self._num("ROUNDING_POWER", 2)

        top, bottom = gaps_out, screen_h - gaps_out
        left, right = gaps_out, screen_w - gaps_out
        # ------------------------------------------------------------ bar ---
        if self._has("bar"):
            position = (self._get("BAR_POSITION") or "top").strip()
            if position not in ("top", "bottom", "left", "right"):
                position = "top"
            vertical = position in ("left", "right")
            bar_margin = self._num("BAR_MARGIN", 6) * scale
            bar_radius = self._num("BAR_RADIUS", 10) * scale
            bar_alpha = max(0.05, min(self._num("BAR_OPACITY", 0.85), 1.0))
            edge = 10 * scale

            # On a vertical bar BAR_WIDTH sets the thickness, on a horizontal one BAR_HEIGHT.
            if vertical:
                bar_w = self._num("BAR_WIDTH", 44) * scale
                bar_h = screen_h - 2 * edge
                bar_x = (bar_margin if position == "left"
                         else screen_w - bar_margin - bar_w)
                bar_y = edge
            else:
                bar_h = self._num("BAR_HEIGHT", 38) * scale
                bar_w = screen_w - 2 * edge
                bar_x = edge
                bar_y = (bar_margin if position == "top"
                         else screen_h - bar_margin - bar_h)

            rounded_path(cr, bar_x, bar_y, bar_w, bar_h, bar_radius, power)
            cr.set_source_rgba(*bg_dark, bar_alpha)
            cr.fill()
            self._draw_bar_content(cr, bar_x, bar_y, bar_w, bar_h,
                                   accent, subtext, scale, bar_radius,
                                   vertical=vertical)

            # The window area is pulled back from the edge the bar sits on.
            if position == "top":
                top = bar_y + bar_h + gaps_in
            elif position == "bottom":
                bottom = bar_y - gaps_in
            elif position == "left":
                left = bar_x + bar_w + gaps_in
            else:
                right = bar_x - gaps_in

        # ----------------------------------------------------------- dock --
        dock = self._dock_rect(screen_w, screen_h, scale)
        if dock is not None and not self._flag("DOCK_AUTOHIDE"):
            # An always-visible dock reserves space (nwg-dock -x): windows move back.
            position, (dx, dy, dw, dh) = dock
            if position == "bottom":
                bottom = min(bottom, dy - gaps_in)
            elif position == "top":
                top = max(top, dy + dh + gaps_in)
            elif position == "left":
                left = max(left, dx + dw + gaps_in)
            else:
                right = min(right, dx - gaps_in)

        # ----------------------------------------------------------- windows
        share = max(0.3, min(self.window_share, 1.0))
        left = right - (right - left) * share
        area = (left, top, right - left, bottom - top)
        windows = self._layout_windows(area, gaps_in)

        for index, (wx, wy, ww, wh) in enumerate(windows):
            active = index == 0
            self._draw_window(cr, wx, wy, ww, wh, radius, power, border, scale,
                              active, surface, accent, accent2, fg, subtext)

        if dock is not None:
            self._draw_dock(cr, dock, scale, palette)

        cr.restore()

    # ------------------------------------------------------------ dock ----
    #: Icons in the preview (pinned + open) and their color roles.
    _DOCK_ICONS = ("ACCENT", "GREEN", "YELLOW", "ACCENT2", "RED", "CYAN")

    def _dock_rect(self, screen_w, screen_h, scale):
        """(position, (x, y, w, h)); None if the dock is off."""
        if not self._flag("DOCK_ENABLE"):
            return None
        position = self._get("DOCK_POSITION") or "bottom"
        if position not in ("bottom", "top", "left", "right"):
            position = "bottom"
        icon = self._num("DOCK_ICON_SIZE", 40) * scale
        cell = icon * 1.25
        count = len(self._DOCK_ICONS) + (1 if self._flag("DOCK_LAUNCHER", True) else 0)
        length = cell * count + 16 * scale
        thick = cell + 12 * scale
        margin = self._num("DOCK_MARGIN", 8) * scale
        if position in ("bottom", "top"):
            x = (screen_w - length) / 2
            y = screen_h - margin - thick if position == "bottom" else margin
            return position, (x, y, length, thick)
        y = (screen_h - length) / 2
        x = margin if position == "left" else screen_w - margin - thick
        return position, (x, y, thick, length)

    def _draw_dock(self, cr, dock, scale, palette) -> None:
        position, (x, y, w, h) = dock
        radius = self._num("DOCK_RADIUS", 18) * scale
        alpha = max(0.2, min(self._num("DOCK_OPACITY", 0.85), 1.0))
        rounded_path(cr, x, y, w, h, radius, 2)
        cr.set_source_rgba(*_hex_to_rgb(palette["BG"]), alpha)
        cr.fill_preserve()
        cr.set_source_rgba(*_hex_to_rgb(palette["SURFACE"]), 0.9)
        cr.set_line_width(max(1.0, scale))
        cr.stroke()

        icon = self._num("DOCK_ICON_SIZE", 40) * scale
        cell = icon * 1.25
        horizontal = position in ("bottom", "top")
        roles = list(self._DOCK_ICONS)
        if self._flag("DOCK_LAUNCHER", True):
            roles.append("")                 # launcher: grid icon
        for index, role in enumerate(roles):
            cx = (x + 8 * scale + cell * (index + 0.5)) if horizontal else x + w / 2
            cy = y + h / 2 if horizontal else (y + 8 * scale + cell * (index + 0.5))
            if role:
                rounded_path(cr, cx - icon / 2, cy - icon / 2, icon, icon,
                             icon * 0.26, 2)
                cr.set_source_rgb(*_hex_to_rgb(palette[role]))
                cr.fill()
            else:
                dot = icon / 7
                cr.set_source_rgb(*_hex_to_rgb(palette["FG"]))
                for gx in (-1, 0, 1):
                    for gy in (-1, 0, 1):
                        cr.arc(cx + gx * dot * 2, cy + gy * dot * 2, dot * 0.7,
                               0, 2 * math.pi)
                        cr.fill()
            # The first icon is the focused app: accent line under it (#active).
            if index == 0:
                cr.set_source_rgb(*_hex_to_rgb(palette["ACCENT"]))
                if horizontal:
                    cr.rectangle(cx - icon * 0.3, cy + icon / 2 + 2 * scale,
                                 icon * 0.6, 2.5 * scale)
                else:
                    cr.rectangle(cx + icon / 2 + 2 * scale, cy - icon * 0.3,
                                 2.5 * scale, icon * 0.6)
                cr.fill()

    # ----------------------------------------------------------- layouts ----
    def _layout_windows(self, area, gap):
        x, y, w, h = area
        if w <= 0 or h <= 0:
            return []
        if self._get("LAYOUT") == "master":
            # Master window on the left, a two-window stack on the right.
            # MASTER_MFACT (default 0.55) sets the master's share; a fixed 0.58
            # used to be used, so changing the setting had no effect in the
            # preview.
            mfact = max(0.1, min(self._num("MASTER_MFACT", 0.55), 0.9))
            main_w = w * mfact
            stack_x = x + main_w + gap
            stack_w = w - main_w - gap
            half = (h - gap) / 2
            return [(x, y, main_w, h),
                    (stack_x, y, stack_w, half),
                    (stack_x, y + half + gap, stack_w, half)]
        # dwindle: first split vertical, second split horizontal
        left_w = w * 0.55
        right_x = x + left_w + gap
        right_w = w - left_w - gap
        half = (h - gap) / 2
        return [(x, y, left_w, h),
                (right_x, y, right_w, half),
                (right_x, y + half + gap, right_w, half)]

    # ------------------------------------------------------------- parts ----
    def _draw_window(self, cr, x, y, w, h, radius, power, border, scale,
                     active, surface, accent, accent2, fg, subtext) -> None:
        if w <= 1 or h <= 1:
            return

        # Shadow: rings getting darker from outside in. The window area is cut
        # out of the path so each ring stays outside the window.
        if self._flag("SHADOW", True):
            spread = self._num("SHADOW_RANGE", 20) * scale
            sharpness = max(1.0, self._num("SHADOW_RENDER_POWER", 3))
            layers = 10
            offset_y = 4 * scale
            import cairo
            cr.save()
            # Cut the window itself out of the path so the area under the shadow is not painted
            cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
            for i in range(layers, 0, -1):
                grow = spread * (i / layers)
                if grow < 0.4:
                    continue
                alpha = 0.13 * ((1 - (i - 1) / layers) ** (sharpness / 2.5))
                rounded_path(cr, x - grow, y - grow + offset_y,
                             w + 2 * grow, h + 2 * grow, radius + grow, power)
                rounded_path(cr, x, y, w, h, radius, power)
                cr.set_source_rgba(0, 0, 0, alpha)
                cr.fill()
            cr.restore()

        opacity = self._num("ACTIVE_OPACITY" if active else "INACTIVE_OPACITY",
                            1.0 if active else 0.96)

        # Body
        rounded_path(cr, x, y, w, h, radius, power)
        cr.set_source_rgba(*surface, max(0.25, min(opacity, 1.0)))
        cr.fill_preserve()

        # Border: a gradient between the two accent colors on the active window
        if border > 0.2:
            if active:
                angle = math.radians(self._num("BORDER_ANGLE", 45))
                dx, dy = math.cos(angle) * w, math.sin(angle) * h
                cr.set_source(_linear(cr, x, y, x + dx, y + dy, accent, accent2))
            else:
                cr.set_source_rgba(*surface, 1.0)
            cr.set_line_width(border)
            cr.stroke()
        else:
            cr.new_path()

        # Dim the unfocused window
        if not active and self._flag("DIM_INACTIVE"):
            rounded_path(cr, x, y, w, h, radius, power)
            cr.set_source_rgba(0, 0, 0, self._num("DIM_STRENGTH", 0.05))
            cr.fill()

        self._draw_window_content(cr, x, y, w, h, scale, active, fg, subtext,
                                  accent)

    def _draw_window_content(self, cr, x, y, w, h, scale, active, fg, subtext,
                             accent) -> None:
        pad = 14 * scale
        if w < pad * 3 or h < pad * 3:
            return
        # Real terminal text: FONT_FAMILY/FONT_SIZE actually apply here; these
        # used to be fixed-size/color rectangles, so changing the font settings
        # had no effect in the preview.
        import cairo
        family = self._get("FONT_FAMILY") or "Sans"
        base_size = self._num("FONT_SIZE", 11)
        font_px = max(6.0, base_size * scale * 0.92)
        line_h = font_px * 1.8
        cr.select_font_face(family, cairo.FONT_SLANT_NORMAL,
                            cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(font_px)
        samples = ("~/projects $ nvim main.rs", "   Compiling project v0.3.0",
                  "warning: unused import", "    Finished in 4.21s",
                  "~/projects $ _")
        rows = int((h - pad * 2) // line_h)
        for i in range(min(rows, len(samples))):
            ly = y + pad + i * line_h + font_px
            if ly > y + h - pad:
                break
            colour = accent if (active and i == 0) else subtext
            alpha = 0.9 if active else 0.45
            cr.set_source_rgba(*colour, alpha)
            cr.move_to(x + pad, ly)
            cr.show_text(samples[i])

    def _draw_bar_content(self, cr, x, y, w, h, accent, subtext, scale,
                          radius=None, vertical: bool = False) -> None:
        pad = self._num("BAR_PADDING", 12) * scale
        style = self._get("BAR_WORKSPACE_STYLE") or "numbers"
        # On a vertical bar the indicators stack top to bottom; the "thickness"
        # axis becomes the width instead of the height.
        thickness = w if vertical else h
        length = h if vertical else w
        dot = thickness * 0.42
        pill = dot if style in ("dots", "occupied-only") else dot * 1.8

        for i in range(5):
            offset = pad + i * (pill + dot * 0.5)
            if offset + dot > length * 0.4:
                break
            active = i == 0
            cr.set_source_rgba(*(accent if active else subtext),
                               1.0 if active else 0.5)
            size = pill if active else dot
            if vertical:
                rounded_path(cr, x + (w - dot) / 2, y + offset, dot, size,
                             radius if active and radius is not None else dot / 2, 2)
            else:
                rounded_path(cr, x + offset, y + (h - dot) / 2, size, dot,
                             radius if active and radius is not None else dot / 2, 2)
            cr.fill()

        # A clock-like block at the opposite end
        cr.set_source_rgba(*accent, 0.9)
        block = length * 0.12
        if vertical:
            rounded_path(cr, x + (w - dot) / 2, y + h - pad - block,
                         dot, block, dot / 2, 2)
        else:
            rounded_path(cr, x + w - pad - block, y + (h - dot) / 2,
                         block, dot, dot / 2, 2)
        cr.fill()

    def _draw_blobs(self, cr, w, h, accent, accent2,
                    base_alpha: float = 0.30) -> None:
        """Soft color blobs while blur is on.

        BLUR_SIZE sets the blob radius, BLUR_PASSES the number of layers (and
        so the softness); both used to be ignored in favor of a fixed 2
        blobs/radius, so changing them had no effect in the preview.
        """
        size = max(0.0, min(self._num("BLUR_SIZE", 6), 20.0))
        passes = max(1, min(int(self._num("BLUR_PASSES", 3)), 6))
        radius_scale = 0.22 + (size / 20.0) * 0.45
        for cx_f, cy_f, colour in ((0.25, 0.3, accent), (0.78, 0.7, accent2)):
            for p in range(passes):
                grow = 1.0 + p * 0.22
                alpha = (base_alpha / passes) * (1.0 - p / (passes * 2))
                pattern = _radial(cx_f * w, cy_f * h,
                                  radius_scale * grow * max(w, h), colour, alpha)
                cr.set_source(pattern)
                cr.rectangle(0, 0, w, h)
                cr.fill()


def _values_getters(values: dict[str, str]):
    """Turn a ready-made values dict into ``DesktopPreview`` getters."""
    base = dict(schema.defaults())
    base.update({k: str(v) for k, v in values.items()})

    def get_setting(key: str) -> str:
        return base.get(key, "")

    def get_palette() -> dict[str, str]:
        return themes.resolve(base.get("THEME", themes.DEFAULT),
                              base.get("CUSTOM_COLORS", ""))

    return get_setting, get_palette


class PaletteStrip(Gtk.DrawingArea):
    """A small sample of a color scheme (the mix page's color cards):
    background, a surface card, text lines and accent colors."""

    _ACCENTS = ("ACCENT", "ACCENT2", "RED", "GREEN", "YELLOW", "CYAN")

    def __init__(self, palette: dict[str, str] | None, width: int = 220,
                 height: int = 124, label: str = ""):
        super().__init__()
        self._palette = palette
        self._label = label
        self.set_content_width(width)
        self.set_content_height(height)
        self.set_draw_func(self._draw)

    def _draw(self, _area, cr, width, height) -> None:
        pal = self._palette
        if not pal:
            # Colors not known yet (to be extracted from the wallpaper): a rainbow.
            for i, hue in enumerate(("f38ba8", "fab387", "f9e2af", "a6e3a1",
                                     "89dceb", "89b4fa", "cba6f7")):
                cr.set_source_rgb(*_hex_to_rgb(hue))
                cr.rectangle(width * i / 7, 0, width / 7 + 1, height)
                cr.fill()
            if self._label:
                cr.set_source_rgba(0, 0, 0, 0.55)
                cr.rectangle(0, height - 28, width, 28)
                cr.fill()
                cr.set_source_rgb(1, 1, 1)
                cr.select_font_face("Sans")
                cr.set_font_size(12)
                extent = cr.text_extents(self._label)
                cr.move_to((width - extent.width) / 2, height - 10)
                cr.show_text(self._label)
            return
        cr.set_source_rgb(*_hex_to_rgb(pal["BG"]))
        cr.paint()
        cr.set_source_rgb(*_hex_to_rgb(pal["BG_DARK"]))
        cr.rectangle(0, 0, width, 16)
        cr.fill()
        cr.set_source_rgb(*_hex_to_rgb(pal["ACCENT"]))
        rounded_path(cr, 8, 4, 22, 8, 4)
        cr.fill()
        cr.set_source_rgb(*_hex_to_rgb(pal["SURFACE"]))
        rounded_path(cr, 12, 26, width - 24, height - 64, 8)
        cr.fill()
        for i, (key, frac) in enumerate((("FG", 0.62), ("SUBTEXT", 0.45), ("SUBTEXT", 0.3))):
            cr.set_source_rgb(*_hex_to_rgb(pal[key]))
            rounded_path(cr, 24, 38 + i * 12, (width - 48) * frac, 6, 3)
            cr.fill()
        step = (width - 24) / len(self._ACCENTS)
        for i, key in enumerate(self._ACCENTS):
            cr.set_source_rgb(*_hex_to_rgb(pal[key]))
            cr.arc(12 + step * (i + 0.5), height - 19, min(10, step / 2 - 2), 0, 2 * math.pi)
            cr.fill()


class ShotPreview(Gtk.DrawingArea):
    """A profile's real screenshot, cropped to fill a fixed size.

    Gtk.Picture took its natural size from the image (1280px) and widened the
    gallery card; here the size is fixed like ValuesPreview. The image is
    scaled down once and cached (the gallery draws 13 cards at once).
    """

    _cache: dict[str, "GdkPixbuf.Pixbuf | None"] = {}

    def __init__(self, path: Path, width: int = 300, height: int = 170,
                 top: float = 1.0, fallback_label: str = ""):
        super().__init__()
        self._path = str(path)
        self._fallback_label = fallback_label
        #: How much of the image to show from the top (1 = all of it). Bar
        #: part cards enlarge the top strip of the screen; in a full-screen
        #: shot the bar was just a line a few pixels tall.
        self._top = max(0.05, min(1.0, top))
        self.set_content_width(width)
        self.set_content_height(height)
        self.set_hexpand(False)
        self.set_draw_func(self._draw)

    def _pixbuf(self):
        if self._path not in self._cache:
            try:
                self._cache[self._path] = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    self._path, 640, 360, True)
            except GLib.Error:
                self._cache[self._path] = None
        return self._cache[self._path]

    def _draw(self, _area, cr, width, height) -> None:
        pixbuf = self._pixbuf()
        if pixbuf is None:
            cr.set_source_rgb(0.11, 0.13, 0.16)
            cr.paint()
            if self._fallback_label:
                cr.set_source_rgba(0.85, 0.90, 0.96, 0.82)
                cr.select_font_face("sans-serif", 0, 1)
                cr.set_font_size(11)
                lines = self._fallback_label.splitlines()
                line_h = 16
                y0 = (height - len(lines) * line_h) / 2 + 11
                for i, line in enumerate(lines):
                    ext = cr.text_extents(line)
                    cr.move_to(max(6, (width - ext.width) / 2), y0 + i * line_h)
                    cr.show_text(line)
            return
        if self._top < 1.0:
            scale = max(width / pixbuf.get_width(),
                        height / (pixbuf.get_height() * self._top))
            cr.translate((width - pixbuf.get_width() * scale) / 2, 0)
            cr.scale(scale, scale)
            Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
            cr.paint()
            return
        scale = max(width / pixbuf.get_width(), height / pixbuf.get_height())
        cr.translate((width - pixbuf.get_width() * scale) / 2,
                     (height - pixbuf.get_height() * scale) / 2)
        cr.scale(scale, scale)
        Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
        cr.paint()


class ValuesPreview(DesktopPreview):
    """Desktop preview of a resolved values dict.

    On gallery cards the profile + its bar preset come resolved together
    (``presets.resolve_chain``), so the real height and position of the bar
    the profile points to are drawn.
    """

    def __init__(self, values: dict[str, str],
                 width: int = 248, height: int = 140,
                 root: Path | None = None):
        get_setting, get_palette = _values_getters(values)
        super().__init__(get_setting, get_palette, has_component=lambda _id: True,
                         use_custom_wallpaper=False, root=root)
        self.set_content_width(width)
        self.set_content_height(height)
        self.set_hexpand(False)
        # Let the wallpaper show on the card: windows on the right half.
        self.window_share = 0.55


class LauncherPreview(_SettingsArea):
    """A small mockup showing the typical layout style of wofi/rofi/fuzzel/walker.

    Not a real screenshot: the "App launcher" choices on the Components page
    only had title/description text, and how different the four UIs are
    (list / grid / single line / list with icons) was not visible at all. The
    palette comes from the live theme so it stays consistent with the chosen
    colors.
    """

    SIZE = (92, 56)

    _STYLES = ("wofi", "rofi", "fuzzel", "walker")

    def __init__(self, launcher_id: str, get_palette):
        super().__init__(lambda _key: "", get_palette)
        self._style = launcher_id if launcher_id in self._STYLES else "wofi"
        self.set_hexpand(False)
        self.set_valign(Gtk.Align.CENTER)

    def _draw(self, _area, cr, width, height) -> None:
        palette = self._palette()
        bg, surface, fg, subtext, accent = _rgbs(
            palette, "BG", "SURFACE", "FG", "SUBTEXT", "ACCENT")

        rounded_path(cr, 0.5, 0.5, width - 1, height - 1, 6, 2)
        cr.set_source_rgb(*bg)
        cr.fill_preserve()
        cr.set_source_rgba(*subtext, 0.35)
        cr.set_line_width(1.0)
        cr.stroke()

        pad = 4.0
        x, y = pad, pad
        w, h = width - 2 * pad, height - 2 * pad
        method = getattr(self, f"_draw_{self._style}")
        method(cr, x, y, w, h, surface, fg, subtext, accent)

    def _search_dot(self, cr, x, y, h, subtext) -> None:
        cr.set_source_rgba(*subtext, 0.6)
        cr.set_line_width(1.0)
        cr.arc(x + h * 0.5, y + h * 0.5, h * 0.16, 0, 2 * math.pi)
        cr.stroke()

    def _draw_wofi(self, cr, x, y, w, h, surface, fg, subtext, accent) -> None:
        # Classic GTK-based dmenu: search box on top, vertical list below.
        search_h = h * 0.24
        rounded_path(cr, x, y, w, search_h, search_h / 2, 2)
        cr.set_source_rgb(*surface)
        cr.fill()
        self._search_dot(cr, x, y, search_h, subtext)

        list_y = y + search_h + 3
        row_h = (h - search_h - 3) / 3
        for i in range(3):
            ry = list_y + i * row_h
            active = i == 0
            if active:
                cr.set_source_rgba(*accent, 0.25)
                cr.rectangle(x, ry, w, row_h - 1.5)
                cr.fill()
            cr.set_source_rgba(*(fg if active else subtext), 0.9 if active else 0.5)
            cr.rectangle(x + 4, ry + row_h * 0.35, w * 0.55, row_h * 0.3)
            cr.fill()

    def _draw_rofi(self, cr, x, y, w, h, surface, fg, subtext, accent) -> None:
        # rofi's best-known mode: the drun grid.
        cols, rows = 3, 2
        gap = 3.0
        cell_w = (w - gap * (cols - 1)) / cols
        cell_h = (h - gap * (rows - 1)) / rows
        for row in range(rows):
            for col in range(cols):
                active = row == 0 and col == 0
                cx = x + col * (cell_w + gap)
                cy = y + row * (cell_h + gap)
                rounded_path(cr, cx, cy, cell_w, cell_h, 3, 2)
                cr.set_source_rgba(*(accent if active else surface),
                                   0.55 if active else 1.0)
                cr.fill()

    def _draw_fuzzel(self, cr, x, y, w, h, surface, fg, subtext, accent) -> None:
        # Single line: search box + inline results next to it; very compact.
        bar_h = h * 0.4
        by = y + (h - bar_h) / 2
        rounded_path(cr, x, by, w, bar_h, bar_h / 2, 2)
        cr.set_source_rgb(*surface)
        cr.fill()
        cr.set_source_rgba(*accent, 0.9)
        cr.arc(x + bar_h * 0.5, by + bar_h * 0.5, bar_h * 0.16, 0, 2 * math.pi)
        cr.fill()
        seg_w = (w - bar_h * 1.3) / 3
        for i in range(3):
            sx = x + bar_h * 1.3 + i * (seg_w + 4)
            cr.set_source_rgba(*subtext, 0.6)
            cr.rectangle(sx, by + bar_h * 0.35, max(1.0, seg_w * 0.7), bar_h * 0.3)
            cr.fill()

    def _draw_walker(self, cr, x, y, w, h, surface, fg, subtext, accent) -> None:
        # Module-based: search box + vertical list with icons.
        search_h = h * 0.24
        rounded_path(cr, x, y, w, search_h, search_h / 2, 2)
        cr.set_source_rgb(*surface)
        cr.fill()
        self._search_dot(cr, x, y, search_h, subtext)

        list_y = y + search_h + 3
        row_h = (h - search_h - 3) / 2
        for i in range(2):
            ry = list_y + i * row_h
            active = i == 0
            if active:
                rounded_path(cr, x, ry, w, row_h - 1.5, 3, 2)
                cr.set_source_rgba(*accent, 0.25)
                cr.fill()
            icon = row_h * 0.55
            rounded_path(cr, x + 3, ry + (row_h - icon) / 2, icon, icon,
                        icon * 0.3, 2)
            cr.set_source_rgba(*(accent if active else subtext),
                               0.9 if active else 0.5)
            cr.fill()
            cr.set_source_rgba(*(fg if active else subtext), 0.9 if active else 0.5)
            cr.rectangle(x + icon + 6, ry + row_h * 0.4, w * 0.4, row_h * 0.25)
            cr.fill()


# -------------------------------------------------------- text/measures ---
def _font(cr, size: float, bold: bool = False) -> None:
    import cairo
    cr.select_font_face(
        "Sans", cairo.FONT_SLANT_NORMAL,
        cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    cr.set_font_size(size)


def _text(cr, x: float, y: float, text: str, colour, size: float = 11,
          bold: bool = False, anchor: str = "left", alpha: float = 1.0) -> float:
    """Draw text and return its width. ``anchor``: left | center | right."""
    _font(cr, size, bold)
    extents = cr.text_extents(text)
    if anchor == "center":
        x -= extents.width / 2 + extents.x_bearing
    elif anchor == "right":
        x -= extents.width + extents.x_bearing
    cr.set_source_rgba(*colour, alpha)
    cr.move_to(x, y)
    cr.show_text(text)
    return extents.width


def _text_width(cr, text: str, size: float, bold: bool = False) -> float:
    _font(cr, size, bold)
    return cr.text_extents(text).width


def _arrow_head(cr, x: float, y: float, dx: float, dy: float) -> None:
    """Small triangle at (x, y) pointing in direction (dx, dy)."""
    size = 4.0
    if abs(dx) > abs(dy):
        cr.move_to(x, y)
        cr.line_to(x + size * (1 if dx > 0 else -1), y - size * 0.7)
        cr.line_to(x + size * (1 if dx > 0 else -1), y + size * 0.7)
    else:
        cr.move_to(x, y)
        cr.line_to(x - size * 0.7, y + size * (1 if dy > 0 else -1))
        cr.line_to(x + size * 0.7, y + size * (1 if dy > 0 else -1))
    cr.close_path()
    cr.fill()


def _measure_h(cr, x0: float, x1: float, y: float, label: str, colour,
               size: float = 10, bounds: tuple[float, float] | None = None) -> None:
    """Horizontal measure line: |←──── label ────→|

    If ``bounds`` is given, the label is shifted to stay inside that range
    instead of the middle of the measure: for narrow measures at the screen
    edge (e.g. GAPS_OUT) a centered label spilled off the left and got clipped.
    """
    def label_x() -> float:
        centre = (x0 + x1) / 2
        if bounds is None:
            return centre
        half = _text_width(cr, label, size) / 2 + 2
        low, high = bounds
        return min(max(centre, low + half), high - half)

    if x1 - x0 < 3:
        # If the measure is too narrow, show only the label instead of the line
        _text(cr, label_x(), y - 6, label, colour, size, anchor="center")
        return
    cr.set_source_rgba(*colour, 0.9)
    cr.set_line_width(1.0)
    cr.move_to(x0, y)
    cr.line_to(x1, y)
    cr.stroke()
    _arrow_head(cr, x0, y, 1, 0)
    _arrow_head(cr, x1, y, -1, 0)
    # Vertical ticks at the ends
    for x in (x0, x1):
        cr.move_to(x, y - 5)
        cr.line_to(x, y + 5)
    cr.stroke()
    _text(cr, label_x(), y - 7, label, colour, size, anchor="center")


def _measure_v(cr, y0: float, y1: float, x: float, label: str, colour,
               size: float = 10) -> None:
    """Vertical measure line; the label goes on the right."""
    if y1 - y0 < 3:
        _text(cr, x + 6, (y0 + y1) / 2, label, colour, size)
        return
    cr.set_source_rgba(*colour, 0.9)
    cr.set_line_width(1.0)
    cr.move_to(x, y0)
    cr.line_to(x, y1)
    cr.stroke()
    _arrow_head(cr, x, y0, 0, 1)
    _arrow_head(cr, x, y1, 0, -1)
    for y in (y0, y1):
        cr.move_to(x - 5, y)
        cr.line_to(x + 5, y)
    cr.stroke()
    _text(cr, x + 7, (y0 + y1) / 2 + size / 3, label, colour, size)


def _leader(cr, x0: float, y0: float, x1: float, y1: float, label: str,
            colour, size: float = 10, anchor: str = "left") -> None:
    """Leader line connecting a point to a label."""
    cr.set_source_rgba(*colour, 0.75)
    cr.set_line_width(1.0)
    cr.set_dash([3, 3])
    cr.move_to(x0, y0)
    cr.line_to(x1, y1)
    cr.stroke()
    cr.set_dash([])
    cr.arc(x0, y0, 2.0, 0, 2 * math.pi)
    cr.fill()
    pad = 4 if anchor == "left" else -4
    _text(cr, x1 + pad, y1 + size / 3, label, colour, size, anchor=anchor)


# ----------------------------------------------------- measurement diagram ---
class LayoutDiagram(_SettingsArea):
    """Zoomed-in diagram showing window settings with arrows and labels.

    The live preview answers "how will it look"; this diagram answers "which
    number changes what". To keep sizes readable, a small part of the screen
    is drawn at 1:1 scale, i.e. the diagram is zoomed in.
    """

    SIZE = (300, 260)

    def _draw(self, _area, cr, width, height) -> None:
        palette = self._palette()
        bg, bg_dark, surface, fg, subtext, accent, accent2 = _rgbs(
            palette, "BG", "BG_DARK", "SURFACE", "FG", "SUBTEXT", "ACCENT", "ACCENT2")

        gaps_out = self._num("GAPS_OUT", 12)
        gaps_in = self._num("GAPS_IN", 5)
        border = self._num("BORDER_SIZE", 2)
        radius = self._num("ROUNDING", 10)
        power = self._num("ROUNDING_POWER", 2)
        active_opacity = self._num("ACTIVE_OPACITY", 1.0)
        inactive_opacity = self._num("INACTIVE_OPACITY", 0.96)

        top_label = 16.0          # label strip on top
        bottom_label = 34.0       # measure strip at the bottom
        screen_x, screen_y = 8.0, top_label
        screen_w = max(80.0, width - 16.0)
        screen_h = max(60.0, height - top_label - bottom_label)

        # ------------------------------------------------------ screen ------
        _screen(cr, screen_x, screen_y, screen_w, screen_h, bg, bg_dark)
        cr.set_source_rgba(*subtext, 0.5)
        cr.set_line_width(1.0)
        rounded_path(cr, screen_x, screen_y, screen_w, screen_h, 6, 2)
        cr.stroke()
        _text(cr, screen_x + 2, top_label - 5, "screen edge", subtext, 9)

        # ------------------------------------------------------- windows ----
        inner_x = screen_x + gaps_out
        inner_y = screen_y + gaps_out
        inner_w = max(20.0, screen_w - 2 * gaps_out)
        inner_h = max(20.0, screen_h - 2 * gaps_out)
        left_w = max(20.0, (inner_w - gaps_in) * 0.56)
        right_x = inner_x + left_w + gaps_in
        right_w = max(16.0, inner_w - left_w - gaps_in)

        # Unfocused window (right)
        rounded_path(cr, right_x, inner_y, right_w, inner_h, radius, power)
        cr.set_source_rgba(*surface, max(0.3, min(inactive_opacity, 1.0)))
        cr.fill_preserve()
        if border > 0.2:
            cr.set_source_rgba(*surface, 1.0)
            cr.set_line_width(border)
            cr.stroke()
        else:
            cr.new_path()
        _text(cr, right_x + right_w / 2, inner_y + inner_h / 2,
              "background", subtext, 10, anchor="center")
        _text(cr, right_x + right_w / 2, inner_y + inner_h / 2 + 13,
              f"opacity {inactive_opacity:g}", subtext, 9, anchor="center")

        # Focused window (left)
        rounded_path(cr, inner_x, inner_y, left_w, inner_h, radius, power)
        cr.set_source_rgba(*surface, max(0.3, min(active_opacity, 1.0)))
        cr.fill_preserve()
        if border > 0.2:
            angle = math.radians(self._num("BORDER_ANGLE", 45))
            dx, dy = math.cos(angle) * left_w, math.sin(angle) * inner_h
            cr.set_source(_linear(cr, inner_x, inner_y,
                                  inner_x + dx, inner_y + dy, accent, accent2))
            cr.set_line_width(border)
            cr.stroke()
        else:
            cr.new_path()
        _text(cr, inner_x + left_w / 2, inner_y + inner_h / 2,
              "focused window", fg, 11, bold=True, anchor="center")
        _text(cr, inner_x + left_w / 2, inner_y + inner_h / 2 + 14,
              f"opacity {active_opacity:g}", subtext, 9, anchor="center")

        # ------------------------------------------------------ measures ----
        mid_y = inner_y + inner_h * 0.78
        _measure_h(cr, screen_x, inner_x, mid_y, f"GAPS_OUT {gaps_out:g}",
                   accent2, bounds=(2.0, width - 2.0))
        _measure_h(cr, inner_x + left_w, right_x, inner_y + inner_h * 0.35,
                   f"GAPS_IN {gaps_in:g}", accent2,
                   bounds=(2.0, width - 2.0))
        _measure_v(cr, screen_y, inner_y, screen_x + screen_w * 0.72,
                   f"GAPS_OUT {gaps_out:g}", accent2)

        # Border and rounding guides
        _leader(cr, inner_x + left_w * 0.5, inner_y,
                screen_x + screen_w * 0.30, screen_y - 6,
                f"BORDER_SIZE {border:g}", accent)
        _leader(cr, inner_x + radius * 0.3, inner_y + radius * 0.3,
                screen_x + screen_w * 0.62, screen_y - 6,
                f"ROUNDING {radius:g} · power {power:g}", accent)

        # -------------------------------------------------------- legend ---
        legend = (f"Diagram is zoomed in: sizes are drawn 1:1 "
                  f"in pixels · layout: {self._get('LAYOUT') or 'dwindle'}")
        _text(cr, screen_x, height - 8, legend, subtext, 9)


# ---------------------------------------------------------- mouse/touchpad ---
class MouseInputDiagram(_SettingsArea):
    """Show SENSITIVITY, ACCEL_PROFILE and NATURAL_SCROLL in one diagram.

    On the Behavior page these three were bare numbers/switches: sensitivity
    was a -1..1 slider and natural scroll a switch, but "how fast is 0.3"
    or "which way does content move with natural scroll" was not intuitive.
    The gauge and the two direction arrows here show it without reading.
    """

    SIZE = (300, 170)

    def _draw(self, _area, cr, width, height) -> None:
        palette = self._palette()
        fg, subtext, surface_c, accent, accent2 = _rgbs(
            palette, "FG", "SUBTEXT", "SURFACE", "ACCENT", "ACCENT2")

        sens = max(-1.0, min(1.0, self._num("SENSITIVITY", 0.0)))
        profile = (self._get("ACCEL_PROFILE") or "").strip().lower()
        natural = self._flag("NATURAL_SCROLL", False)
        scroll_factor = max(0.1, min(3.0, self._num("TOUCHPAD_SCROLL_FACTOR", 0.8)))

        # ---------------------------------------------------- sensitivity gauge
        gauge_x, gauge_y = 16.0, 34.0
        gauge_w, gauge_h = width - 32.0, 10.0
        rounded_path(cr, gauge_x, gauge_y, gauge_w, gauge_h, gauge_h / 2, 2)
        cr.set_source_rgb(*surface_c)
        cr.fill()

        mid_x = gauge_x + gauge_w / 2
        cr.set_source_rgba(*subtext, 0.6)
        cr.set_line_width(1.2)
        cr.move_to(mid_x, gauge_y - 3)
        cr.line_to(mid_x, gauge_y + gauge_h + 3)
        cr.stroke()

        marker_x = gauge_x + (sens + 1.0) / 2.0 * gauge_w
        cr.set_source_rgb(*accent)
        cr.arc(marker_x, gauge_y + gauge_h / 2, 6.0, 0, 2 * math.pi)
        cr.fill()

        _text(cr, gauge_x, gauge_y - 12, "slow", subtext, 9)
        _text(cr, gauge_x + gauge_w, gauge_y - 12, "fast", subtext, 9,
              anchor="right")
        profile_label = {"flat": "flat accel (ignores speed)",
                         "adaptive": "adaptive accel"}.get(
            profile, "system default accel")
        _text(cr, mid_x, gauge_y + gauge_h + 16,
              f"sensitivity {sens:+.2f}", fg, 11, bold=True, anchor="center")
        _text(cr, mid_x, gauge_y + gauge_h + 30, profile_label, subtext, 9,
              anchor="center")

        # ------------------------------------------- scroll direction arrow -
        # The arrow band has a fixed height; TOUCHPAD_SCROLL_FACTOR only changes
        # the arrow length inside the band, so it never collides with the text
        # above (the arrow used to grow past the top as the factor rose and
        # overlapped the "sensitivity" line).
        track_top, track_bottom = 100.0, 128.0
        norm = (scroll_factor - 0.1) / (3.0 - 0.1)
        arrow_len = 14.0 + norm * (track_bottom - track_top - 14.0)
        col_gap = 76.0
        origin_x = width / 2 - col_gap / 2

        def _dir_arrow(cx: float, label: str, points_down: bool, colour) -> None:
            top_y = track_bottom - arrow_len
            bottom_y = track_bottom
            y0, y1 = (top_y, bottom_y) if points_down else (bottom_y, top_y)
            cr.set_source_rgb(*colour)
            cr.set_line_width(2.2)
            cr.move_to(cx, y0)
            cr.line_to(cx, y1)
            cr.stroke()
            _arrow_head(cr, cx, y1, 0.0, 1.0 if points_down else -1.0)
            _text(cr, cx, track_bottom + 16, label, fg, 9, anchor="center")

        _dir_arrow(origin_x, "finger", True, subtext)
        _dir_arrow(origin_x + col_gap, "content", natural, accent2)
        _text(cr, width / 2, track_top - 10,
              ("natural scroll" if natural else "classic scroll") +
              f" · factor {scroll_factor:.1f}×", subtext, 9, anchor="center")


def _bezier_ease(x1: float, y1: float, x2: float, y2: float,
                 progress: float) -> float:
    """y for x=progress on the cubic-bezier(x1,y1,x2,y2) curve.

    Same math as Hyprland's ``bezier``: a cubic Bézier with fixed end points
    (0,0) and (1,1). No need to solve t from x in closed form; six Newton
    steps leave no visible error. The result may exceed 1: that is exactly
    the overshoot in the "fluid" set (passing the target and settling back)
    and must not be clamped.
    """
    def axis(a: float, b: float, t: float) -> float:
        u = 1.0 - t
        return 3 * u * u * t * a + 3 * u * t * t * b + t ** 3

    t = progress
    for _ in range(6):
        dx = axis(x1, x2, t) - progress
        if abs(dx) < 1e-4:
            break
        u = 1.0 - t
        slope = 3 * u * u * x1 + 6 * u * t * (x2 - x1) + 3 * t * t * (1 - x2)
        if abs(slope) < 1e-6:
            break
        t -= dx / slope
    return axis(y1, y2, max(0.0, min(1.0, t)))


class AnimationDiagram(_SettingsArea):
    """Actually plays ANIMATIONS / ANIMATION_PRESET / ANIMATION_SPEED.

    On the page these were a switch, a dropdown and a slider: the difference
    between "Snappy" and "Fluid" could only be seen after installing, and
    whether the speed factor should be 0.5 or 2.0 was guesswork. This
    scene loops through four transitions (window open, move, workspace
    switch, close) and reads durations/curves from
    ``render.ANIMATION_PRESETS``, so it shows the same values the install
    really generates instead of keeping a separate "demo" table.

    The small graph on the right is the selected curve itself; the dot running
    along it marks the current progress, so terms like "popin" and "overshoot"
    can be seen without being defined.
    """

    SIZE = (300, 190)

    #: Scenes played in the loop: (Hyprland animation name, label).
    _SCENES = (
        ("windowsIn", "Window opens"),
        ("windowsMove", "Window moves"),
        ("workspaces", "Workspace switch"),
        ("windowsOut", "Window closes"),
    )
    #: Hyprland animation tree: (branch, parent). Order matters: the parent is
    #: filled first, so a lone "global" definition trickles down to every scene.
    _ANIM_PARENTS = (
        ("windows", "global"), ("workspaces", "global"),
        ("windowsIn", "windows"), ("windowsOut", "windows"),
        ("windowsMove", "windows"),
    )
    #: Pause between scenes (s), so you can see where the transition ends.
    _HOLD = 0.5

    def __init__(self, get_setting, get_palette):
        super().__init__(get_setting, get_palette)
        self._start = time.monotonic()
        self._tick_id = 0
        self._was_running = False
        # The frame callback only runs while the widget is on screen: redrawing
        # at 60 fps while the page is hidden just wastes power.
        self.connect("map", lambda _w: self._start_ticking())
        self.connect("unmap", lambda _w: self._stop_ticking())

    # -------------------------------------------------------------- loop ---
    def _start_ticking(self) -> None:
        if not self._tick_id:
            self._start = time.monotonic()
            self._tick_id = self.add_tick_callback(self._tick)

    def _stop_ticking(self) -> None:
        if self._tick_id:
            self.remove_tick_callback(self._tick_id)
            self._tick_id = 0

    def _tick(self, _widget, _clock) -> bool:
        running = bool(self._timeline())
        # With animations off the scene is static: drawn one last time, then the
        # per-frame queue_draw calls stop.
        if running or self._was_running != running:
            self.queue_draw()
        self._was_running = running
        return True

    # -------------------------------------------------------------- time ----
    def _timeline(self) -> list[dict]:
        """Scenes: name, label, duration (s), curve points, style.

        Returns an empty list if ANIMATIONS is off or the preset is "none"; the
        caller draws that as the "no animation" state.
        """
        if not self._flag("ANIMATIONS", True):
            return []
        preset = render_mod.animation_preset({
            "ANIMATION_PRESET": self._get("ANIMATION_PRESET") or "",
            "ANIMATION_CUSTOM": self._get("ANIMATION_CUSTOM") or ""})
        animations = {a[0]: a for a in preset["animations"]}
        if not animations:
            return []
        # Custom sets (mix) often define only the parent branch
        # ("windows"); Hyprland applies it to the children, and so does the preview.
        for name, parent in self._ANIM_PARENTS:
            if name not in animations and parent in animations:
                animations[name] = (name, *animations[parent][1:])
        curves = {c[0]: tuple(float(v) for v in c[1:])
                  for c in preset["curves"]}
        speed = max(0.3, min(3.0, self._num("ANIMATION_SPEED", 1.0)))

        scenes = []
        for name, label in self._SCENES:
            entry = animations.get(name)
            if entry is None:
                continue
            _n, decisecs, curve_name, style = entry
            scenes.append({
                "name": name,
                "label": label,
                # Hyprland durations are in deciseconds; ANIMATION_SPEED divides them
                # (same calculation as render._animation_lines).
                "duration": float(decisecs) / 10.0 / speed,
                "curve": curves.get(curve_name, (0.0, 0.0, 1.0, 1.0)),
                "curve_name": curve_name,
                "style": style,
            })
        return scenes

    def _now(self, scenes: list[dict]) -> tuple[dict, float]:
        """The loop's current scene and the progress within it (0..1)."""
        cycle = sum(s["duration"] + self._HOLD for s in scenes)
        elapsed = (time.monotonic() - self._start) % cycle
        for scene in scenes:
            span = scene["duration"] + self._HOLD
            if elapsed < span:
                return scene, min(1.0, elapsed / max(scene["duration"], 1e-3))
            elapsed -= span
        return scenes[-1], 1.0

    # ----------------------------------------------------------- drawing ---
    def _draw(self, _area, cr, width, height) -> None:
        palette = self._palette()
        bg_dark, surface_c, fg, subtext, accent, accent2 = _rgbs(
            palette, "BG_DARK", "SURFACE", "FG", "SUBTEXT", "ACCENT", "ACCENT2")

        plot_w = 96.0
        gap = 12.0
        stage_x, stage_y = 12.0, 12.0
        stage_w = width - plot_w - gap - 2 * stage_x
        stage_h = height - 46.0

        scenes = self._timeline()
        if not scenes:
            self._draw_stage_frame(cr, stage_x, stage_y, stage_w, stage_h,
                                   bg_dark, subtext)
            self._draw_window(cr, stage_x + stage_w * 0.22,
                              stage_y + stage_h * 0.24,
                              stage_w * 0.46, stage_h * 0.5,
                              surface_c, accent, 1.0)
            reason = ("Animations off" if not self._flag("ANIMATIONS", True)
                      else "Character: Off")
            _text(cr, width / 2, height - 16,
                  f"{reason}: windows appear instantly, no transition",
                  subtext, 9.5, anchor="center")
            self._draw_curve_plot(cr, width - plot_w - stage_x, stage_y,
                                  plot_w, stage_h, None,
                                  None, surface_c, subtext, accent, "no curve")
            return

        scene, progress = self._now(scenes)
        eased = _bezier_ease(*scene["curve"], progress)

        cr.save()
        self._draw_stage_frame(cr, stage_x, stage_y, stage_w, stage_h,
                               bg_dark, subtext)
        rounded_path(cr, stage_x, stage_y, stage_w, stage_h, 6, 2)
        cr.clip()
        self._draw_scene(cr, scene, eased, stage_x, stage_y, stage_w, stage_h,
                         surface_c, accent, accent2, subtext)
        cr.restore()

        # --- caption: which transition, how long, which curve --------------
        ms = int(round(scene["duration"] * 1000))
        _text(cr, stage_x, height - 26, scene["label"], fg, 10.5, bold=True)
        style = scene["style"] or "plain"
        _text(cr, stage_x, height - 13,
              f"{ms} ms · {scene['curve_name']} · {style}", subtext, 9)

        self._draw_curve_plot(cr, width - plot_w - stage_x, stage_y,
                              plot_w, stage_h, scene["curve"], progress,
                              surface_c, subtext, accent, scene["curve_name"])

    @staticmethod
    def _draw_stage_frame(cr, x, y, w, h, bg, border) -> None:
        rounded_path(cr, x, y, w, h, 6, 2)
        cr.set_source_rgb(*bg)
        cr.fill()
        rounded_path(cr, x + 0.5, y + 0.5, w - 1, h - 1, 6, 2)
        cr.set_source_rgba(*border, 0.35)
        cr.set_line_width(1.0)
        cr.stroke()

    @staticmethod
    def _draw_window(cr, x, y, w, h, body, accent, alpha) -> None:
        """The mock window in the scene: title strip + body."""
        if w <= 1 or h <= 1:
            return
        rounded_path(cr, x, y, w, h, 4, 2)
        cr.set_source_rgba(*body, alpha)
        cr.fill()
        bar_h = min(7.0, h * 0.22)
        cr.save()
        rounded_path(cr, x, y, w, h, 4, 2)
        cr.clip()
        cr.set_source_rgba(*accent, alpha * 0.85)
        cr.rectangle(x, y, w, bar_h)
        cr.fill()
        cr.restore()

    def _draw_scene(self, cr, scene, eased, x, y, w, h,
                    surface_c, accent, accent2, subtext) -> None:
        """Draw the scene for the eased progress.

        The style string uses the same vocabulary as Hyprland: "popin 80%" gives
        the start scale, "slide"/"slidefade"/"fade" the form of the workspace
        switch. An unknown style falls back to a plain fade.
        """
        name = scene["name"]
        style = scene["style"]
        win_w, win_h = w * 0.46, h * 0.52
        win_y = y + (h - win_h) / 2
        left_x = x + w * 0.08
        right_x = x + w - win_w - w * 0.08

        if name in ("windowsIn", "windowsOut"):
            start = self._popin_scale(style)
            factor = eased if name == "windowsIn" else 1.0 - eased
            scale = start + (1.0 - start) * factor
            alpha = max(0.0, min(1.0, factor))
            cx, cy = x + w / 2, y + h / 2
            self._draw_window(cr, cx - win_w * scale / 2,
                              cy - win_h * scale / 2,
                              win_w * scale, win_h * scale,
                              surface_c, accent, alpha)
            return

        if name == "windowsMove":
            # A frame for the vacated spot, so where the window moves from and
            # to stays visible.
            cr.save()
            cr.set_dash([3.0, 3.0])
            cr.set_line_width(1.0)
            cr.set_source_rgba(*subtext, 0.45)
            cr.rectangle(left_x + 0.5, win_y + 0.5, win_w - 1, win_h - 1)
            cr.stroke()
            cr.restore()
            self._draw_window(cr, left_x + (right_x - left_x) * eased, win_y,
                              win_w, win_h, surface_c, accent, 1.0)
            return

        # workspaces: two workspaces side by side, one pushes the other.
        shift = w * eased
        fade = "fade" in style
        slide = "slide" in style
        offset = shift if slide else 0.0
        first_alpha = 1.0 - eased if fade or not slide else 1.0
        second_alpha = eased if fade or not slide else 1.0
        self._draw_window(cr, x + w * 0.27 - offset, win_y, win_w, win_h,
                          surface_c, accent, max(0.0, first_alpha))
        self._draw_window(cr, x + w * 0.27 + w - offset, win_y, win_w, win_h,
                          surface_c, accent2, max(0.0, second_alpha))
        # Workspace numbers at the bottom edge, so it's clear which one comes in.
        _text(cr, x + w * 0.27 + win_w / 2 - offset, y + h - 6, "1",
              subtext, 9, anchor="center", alpha=max(0.0, first_alpha))
        _text(cr, x + w * 0.27 + w + win_w / 2 - offset, y + h - 6, "2",
              subtext, 9, anchor="center", alpha=max(0.0, second_alpha))

    @staticmethod
    def _popin_scale(style: str) -> float:
        """"popin 80%" → 0.80. Without a percentage the window starts at full size."""
        if "popin" not in style:
            return 1.0
        for token in style.split():
            if token.endswith("%"):
                try:
                    return max(0.05, min(1.0, float(token[:-1]) / 100.0))
                except ValueError:
                    break
        return 1.0

    @staticmethod
    def _draw_curve_plot(cr, x, y, w, h, curve, progress,
                         surface_c, subtext, accent, label) -> None:
        """The selected Bézier curve + a dot running along it. curve=None → empty box."""
        size = min(w, h - 14.0)
        px, py = x + (w - size) / 2, y + (h - 14.0 - size) / 2
        rounded_path(cr, px, py, size, size, 4, 2)
        cr.set_source_rgba(*surface_c, 0.6)
        cr.fill()
        if curve is None:
            _text(cr, x + w / 2, y + h - 2, label, subtext, 8.5, anchor="center")
            return

        # The y axis may exceed 1 (overshoot); the plot area is compressed for it.
        peak = max(1.0, max(_bezier_ease(*curve, i / 24.0) for i in range(25)))
        top = 0.10 * size
        span = size - 2 * top

        def point(t: float) -> tuple[float, float]:
            value = _bezier_ease(*curve, t)
            return (px + top + t * span,
                    py + size - top - (value / peak) * span)

        cr.set_source_rgba(*subtext, 0.30)
        cr.set_line_width(1.0)
        cr.move_to(px + top, py + size - top)
        cr.line_to(px + size - top, py + size - top)
        cr.stroke()

        cr.set_source_rgb(*accent)
        cr.set_line_width(1.6)
        cr.move_to(*point(0.0))
        for step in range(1, 33):
            cr.line_to(*point(step / 32.0))
        cr.stroke()

        if progress is not None:
            dot_x, dot_y = point(max(0.0, min(1.0, progress)))
            cr.set_source_rgb(*accent)
            cr.arc(dot_x, dot_y, 3.0, 0, 2 * math.pi)
            cr.fill()

        _text(cr, x + w / 2, y + h - 2, label, subtext, 8.5, anchor="center")


class CursorSizeDiagram(_SettingsArea):
    """Show CURSOR_THEME with its real image and CURSOR_SIZE at 1:1 pixel
    scale, so how much the slider's number enlarges the cursor can be seen
    without waiting for an install.
    """

    SIZE = (300, 90)

    def _draw(self, _area, cr, width, height) -> None:
        palette = self._palette()
        fg, subtext, accent = _rgbs(palette, "FG", "SUBTEXT", "ACCENT")

        theme = self._get("CURSOR_THEME") or "Bibata-Modern-Ice"
        size = int(max(12.0, min(64.0, self._num("CURSOR_SIZE", 24))))

        cx, cy = 34.0, height / 2 - 6
        surface = cursors_mod.pointer_surface(theme, size)
        cr.save()
        if surface is not None:
            sw, sh = surface.get_width(), surface.get_height()
            cr.translate(cx - sw / 2, cy - sh / 2)
            cr.set_source_surface(surface, 0, 0)
            cr.paint()
        else:
            # Theme not installed on this system: a placeholder arrow sketch.
            cr.translate(cx - size * 0.3, cy - size * 0.3)
            s = size * 0.6
            cr.move_to(0, 0)
            cr.line_to(0, s)
            cr.line_to(s * 0.28, s * 0.78)
            cr.line_to(s * 0.46, s)
            cr.line_to(s * 0.62, s * 0.86)
            cr.line_to(s * 0.42, s * 0.62)
            cr.line_to(s * 0.7, s * 0.52)
            cr.close_path()
            cr.set_source_rgba(*subtext, 0.35)
            cr.fill_preserve()
            cr.set_source_rgba(*subtext, 0.6)
            cr.set_line_width(1.2)
            cr.stroke()
        cr.restore()

        text_x = 76.0
        _text(cr, text_x, cy - 8, theme, fg, 12, bold=True)
        note = "" if surface is not None else "  (not installed on this system)"
        _text(cr, text_x, cy + 10, f"{size}px actual size{note}", subtext, 10)

        ruler_x0, ruler_x1 = 8.0, width - 8.0
        ruler_y = height - 10.0
        cr.set_source_rgba(*subtext, 0.4)
        cr.set_line_width(1.0)
        cr.move_to(ruler_x0, ruler_y)
        cr.line_to(ruler_x1, ruler_y)
        cr.stroke()
        t = (size - 12) / (64 - 12)
        marker_x = ruler_x0 + t * (ruler_x1 - ruler_x0)
        cr.set_source_rgb(*accent)
        cr.arc(marker_x, ruler_y, 3.5, 0, 2 * math.pi)
        cr.fill()
        _text(cr, ruler_x0, ruler_y - 6, "12px", subtext, 8)
        _text(cr, ruler_x1, ruler_y - 6, "64px", subtext, 8, anchor="right")


# ------------------------------------------------------------ bar preview ---
# Module id → sample content shown in the preview. Not real values, just
# representative text that helps understand the layout.
BAR_SAMPLES = {
    "hyprland/submap": "resize",
    "cpu": "CPU 12%",
    "memory": "RAM 4.2G",
    "temperature": "48°C",
    "disk": "128G",
    "backlight": "Light 80%",
    "pulseaudio": "Vol 60%",
    "bluetooth": "BT",
    "network": "Wi-Fi",
    "battery": "76%",
    "idle_inhibitor": "Awake",
    "tray": "▣ ▣",
    "custom/power": "Power",
    "custom/weather": "☀ 21°",
    "custom/powerprofile": "󰾅",
    "custom/privacy": "󰍬",
    "custom/record": "󰑊 00:42",
    "custom/shazam": "󰝚",
    "custom/gamemode": "󰊗",
    "custom/notifications": "󰂚",
    "custom/updates": "󰚰 12",
    "custom/mic": "󰍬",
    # The output of user slots can't be known in advance; a placeholder of
    # typical length is used so they take up space in the preview.
    "custom/user1": "Custom 1",
    "custom/user2": "Custom 2",
    "custom/user3": "Custom 3",
}


#: A bar preset's shape IN THE PREVIEW. The numbers (height/radius/opacity)
#: come from the preset file; what makes a preset recognizable is the shape
#: of its modules: capsules, bare text, or dividers. The CSS block in the
#: template (templates/waybar/style.css.tmpl) is the source of truth; this
#: table is its summary for the preview, so update both together. While
#: all cards were drawn as the same row of grey boxes, "which is which" was unclear.
#:
#: Shapes:
#:   chip      — default: each module in its own soft-cornered box
#:   pill      — fully rounded capsules, each in a different palette color
#:   bare      — no box, text only
#:   underline — no box, an accent line under each module
#:   divider   — no box, vertical dividers between modules
#:   island    — the whole zone is one box, modules adjacent inside it
#:   capsule   — the zone is one capsule with fully rounded ends
#:   outline   — unfilled boxes with a 1px frame
#:   bracket   — the zone between [ … ], no box
BAR_PREVIEW_SHAPES: dict[str, dict] = {
    "islands":            {"shape": "island"},
    "sameemul-islands":   {"shape": "island"},
    "pill-single":        {"shape": "capsule", "inset": 0.12},
    "catppuccin-pills":   {"shape": "pill", "colored": True},
    "jakoolit-simple-l":  {"shape": "pill", "colored": True, "power_dot": True},
    "hyde-wallbash":      {"shape": "capsule", "power_dot": True},
    "ml4w-glass":         {"shape": "chip", "glass": True},
    "minimal":            {"shape": "bare"},
    "rainz-nebula":       {"shape": "bare", "glow": True},
    "cyberarch-hud":      {"shape": "underline", "mono": True},
    "telemetry":          {"shape": "underline", "mono": True},
    "gruvbox-solid":      {"shape": "divider"},
    "binnewbs-compact":   {"shape": "divider"},
    "outline":            {"shape": "outline"},
    "bracket":            {"shape": "bracket"},
    "colorshell-dock":    {"shape": "chip", "inset": 0.18},
    "corner-tray":        {"shape": "chip", "corner_only": True},
    "glass":              {"shape": "chip", "glass": True},
    "sharp":              {"shape": "chip", "square": True},
    # Script Test (our own profiles)
    "st-yaprak":          {"shape": "bare"},
    "st-gunbatimi":       {"shape": "bare", "mono": True},
    "st-kizil":           {"shape": "outline"},
    "st-gecegolu":        {"shape": "bare", "mono": True},
    "st-sepya":           {"shape": "outline", "square": True, "mono": True},
    "st-metro":           {"shape": "divider", "mono": True},
    "st-lavanta":         {"shape": "divider", "mono": True},
    "st-nane":            {"shape": "capsule", "inset": 0.28},
    "st-ay":              {"shape": "pill", "colored": True},
    "st-siyah":           {"shape": "bare", "mono": True},
    "st-alacakaranlik":   {"shape": "pill", "colored": True},
    "st-galaksi":         {"shape": "outline", "mono": True},
    "st-zirve":           {"shape": "bare"},
    "st-karadelik":       {"shape": "bare"},
    "st-nerv":            {"shape": "underline"},
    "st-kurbaga":         {"shape": "chip"},
    "st-doom":            {"shape": "outline", "square": True, "mono": True},
    "st-mando":           {"shape": "outline"},
    "st-kule":            {"shape": "underline"},
    "st-gozcu":           {"shape": "chip"},
    # Vertical presets (see BarPreview._draw_vertical)
    "rail":               {"shape": "chip"},
    "eclipse-sidebar":    {"shape": "bare"},
    "gdots-rail":         {"shape": "bare"},
    "st-manga":           {"shape": "bare"},
    "st-limon":           {"shape": "capsule", "inset": 0.04},
    "caelestia":          {"shape": "capsule", "inset": 0.04},
    "illogical-impulse":  {"shape": "pill"},
}


class BarPreview(_SettingsArea):
    """Draw the status bar with its modules at 1:1 scale.

    Height, margin, module spacing, padding, rounding, opacity and the
    workspace indicator settings show up directly here; modules are placed
    in the zone you chose (left/center/right).
    """

    SIZE = (360, 170)

    def __init__(self, get_setting, get_palette):
        super().__init__(get_setting, get_palette)
        # see DesktopPreview: the minimum width that keeps the pane from squeezing
        # this area down to a few pixels with narrow/tiled windows and making the
        # modules unreadable. Gallery cards override it with their own size.
        #: Gallery card mode: no measure arrows, no "window area" text and no long
        #: window title; the bar is enlarged instead. On a card the question is
        #: not "how many pixels" but "what does this preset look like"; sizes are
        #: already in the badges under the card and overlapped on the small canvas.
        self._card = False

    def set_card_mode(self, enabled: bool = True) -> None:
        self._card = enabled
        self.queue_draw()

    # ----------------------------------------------------------- helpers ---
    def _modules(self, zone: str) -> list[str]:
        raw = self._get(f"BAR_MODULES_{zone}") or ""
        names = [m.strip() for m in raw.split(",") if m.strip()]
        if getattr(self, "_card", False) and len(names) > 3:
            # All ten modules don't fit on a card, and trying to fit them made them
            # overlap. The zone's first three are enough to convey the shape.
            return names[:3]
        return names

    def _clock_text(self) -> str:
        fmt = self._get("BAR_CLOCK_FORMAT") or "%H:%M"
        try:
            return time.strftime(fmt)
        except (ValueError, TypeError):
            return "12:34"

    def _window_text(self) -> str:
        """Actually applies BAR_WINDOW_MAX_LENGTH.

        The previous fixed sample ("kitty — ~/projects", 19 characters) was far
        below the default limit (60), so changing the slider had no visible
        effect in the preview. We use a realistic long sample title and really
        truncate it.
        """
        if getattr(self, "_card", False):
            # On a card a long title filled the center zone by itself and pushed the
            # modules on the right out.
            return "nvim"
        base = "nvim ~/projects/hyprsetup/render.py — unsaved changes"
        try:
            max_len = int(self._num("BAR_WINDOW_MAX_LENGTH", 60))
        except (TypeError, ValueError):
            max_len = 60
        max_len = max(4, max_len)
        if len(base) <= max_len:
            return base
        return base[: max_len - 1].rstrip() + "…"

    # ----------------------------------------------------------- drawing ---
    def _draw(self, _area, cr, width, height) -> None:
        palette = self._palette()
        bg, bg_dark, surface, fg, subtext, accent = _rgbs(
            palette, "BG", "BG_DARK", "SURFACE", "FG", "SUBTEXT", "ACCENT")

        bar_h = max(12.0, self._num("BAR_HEIGHT", 38))
        margin = self._num("BAR_MARGIN", 6)
        spacing = self._num("BAR_SPACING", 6)
        padding = self._num("BAR_PADDING", 12)
        radius = self._num("BAR_RADIUS", 10)
        opacity = max(0.05, min(self._num("BAR_OPACITY", 0.85), 1.0))
        at_top = (self._get("BAR_POSITION") or "top") != "bottom"

        card = getattr(self, "_card", False)
        if (self._get("BAR_POSITION") or "top") in ("left", "right"):
            # Vertical rail/panel presets (rail, eclipse-sidebar, gdots-rail,
            # quickshell-rail, wayle-rail) used to fall back to the full desktop
            # sketch: all six looked like the same thin strip, and the difference
            # between them (icon rail, rounded panel, or two-line clock) could
            # not be seen at all.
            self._draw_vertical(cr, width, height, palette, card)
            return
        legend_h = 0.0 if card else 26.0
        screen_x, screen_y = 6.0, 6.0
        # A separate strip is left on the right for the height measure. The
        # arrow used to be drawn inside the desktop, over the bar's right zone:
        # the "height 38" text overlapped the clock/battery module text
        # and both became unreadable.
        gutter = 0.0 if card else _text_width(cr, f"height {bar_h:g}", 10) + 18.0
        screen_w = max(120.0, width - 12.0 - gutter)
        screen_h = max(bar_h + 2 * margin + 10.0, height - 12.0 - legend_h)

        # -------------------------------------------------------- desktop ---
        _screen(cr, screen_x, screen_y, screen_w, screen_h, bg, bg_dark)

        inset = float(self._style().get("inset", 0.0)) * screen_w
        bar_x = screen_x + margin + inset
        bar_w = max(60.0, screen_w - 2 * margin - 2 * inset)
        bar_y = (screen_y + margin) if at_top \
            else (screen_y + screen_h - margin - bar_h)

        # A window sketch to make clear which edge the bar sits on
        win_y = (bar_y + bar_h + margin) if at_top else (screen_y + margin)
        win_h = max(10.0, (screen_h - bar_h - 3 * margin))
        rounded_path(cr, bar_x, win_y, bar_w, win_h,
                     self._num("ROUNDING", 10), self._num("ROUNDING_POWER", 2))
        cr.set_source_rgba(*surface, 0.55)
        cr.fill()
        if not card:
            _text(cr, bar_x + bar_w / 2, win_y + win_h / 2 + 4,
                  "window area", subtext, 10, anchor="center")

        # ------------------------------------------------------------ bar ---
        rounded_path(cr, bar_x, bar_y, bar_w, bar_h, radius, 2)
        cr.set_source_rgba(*bg_dark, opacity)
        cr.fill()

        chip_h = max(8.0, bar_h - 8)
        chip_y = bar_y + (bar_h - chip_h) / 2

        left = self._chip_widths(cr, self._modules("LEFT"), padding, chip_h)
        center = self._chip_widths(cr, self._modules("CENTER"), padding, chip_h)
        right = self._chip_widths(cr, self._modules("RIGHT"), padding, chip_h)

        # If modules don't fit in the bar, clip them at the edge like the real bar;
        # overflowing boxes must not paint outside the preview.
        cr.save()
        rounded_path(cr, bar_x, bar_y, bar_w, bar_h, radius, 2)
        cr.clip()

        def total(chips) -> float:
            return sum(w for _n, w in chips) + spacing * max(0, len(chips) - 1)

        left_x = bar_x + spacing
        center_x = bar_x + (bar_w - total(center)) / 2
        right_x = bar_x + bar_w - spacing - total(right)

        # Each zone draws only within its own share. Since the three zones were
        # positioned separately, on a narrow bar (e.g. Quickshell presets) the
        # center and right modules overlapped and the two texts ran into each
        # other. On the real bar a module that doesn't fit is clipped too, not overlapped.
        for chips, start, limit in (
                (left, left_x, center_x if center else right_x),
                (center, center_x, right_x),
                (right, right_x, bar_x + bar_w)):
            if not chips:
                continue
            cr.save()
            cr.rectangle(start, bar_y, max(0.0, limit - start), bar_h)
            cr.clip()
            self._draw_zone(cr, chips, start, chip_y, chip_h, spacing,
                            radius, surface, fg, accent, subtext)
            cr.restore()

        cr.restore()

        # -------------------------------------------------------- measures --
        if card:
            return                       # no measure arrows on cards
        # The height arrow sits in the strip right of the bar (see `gutter`).
        _measure_v(cr, bar_y, bar_y + bar_h, screen_x + screen_w + 7,
                   f"height {bar_h:g}", accent)
        # The margin is usually under 12px; writing the label in the middle of
        # that range put it on top of the bar. The arrow stays in the range and
        # the text moves to the empty edge of the window area.
        if at_top:
            _measure_v(cr, screen_y, bar_y, screen_x + 16, "", accent)
            _text(cr, screen_x + 23, bar_y + bar_h + 14,
                  f"margin {margin:g}", accent, 10)
        else:
            _measure_v(cr, bar_y + bar_h, screen_y + screen_h, screen_x + 16,
                       "", accent)
            _text(cr, screen_x + 23, bar_y - 6, f"margin {margin:g}", accent, 10)

        # ----------------------------------------------------------- legend -
        legend = (f"spacing {spacing:g} · padding {padding:g} · "
                  f"rounding {radius:g} · opacity {opacity:g} · "
                  f"position: {'top' if at_top else 'bottom'}")
        _text(cr, screen_x, height - 8, legend, subtext, 9)

    # ------------------------------------------------------------- parts ----
    def _chip_widths(self, cr, modules, padding: float, chip_h: float):
        """Produce (name, width) pairs for each module."""
        out = []
        for name in modules:
            if name == "hyprland/workspaces":
                out.append((name, chip_h * 5.4))
                continue
            if name == "clock":
                text = self._clock_text()
            elif name == "hyprland/window":
                text = self._window_text()
            else:
                text = BAR_SAMPLES.get(name)
                if text is None:
                    continue
            if not text:
                continue
            out.append((name, _text_width(cr, text, 11) + 2 * padding))
        return out

    def _style(self) -> dict:
        """Preview shape of the selected bar preset (see BAR_PREVIEW_SHAPES)."""
        return BAR_PREVIEW_SHAPES.get(self._get("BAR_PRESET") or "", {})

    def _draw_zone(self, cr, chips, x: float, y: float, chip_h: float,
                   spacing: float, radius: float, surface, fg, accent,
                   subtext) -> None:
        """Draw a zone's modules according to the preset's shape.

        The shape table is in BAR_PREVIEW_SHAPES; the branching here only
        applies it. While every preset was drawn as the same row of boxes, you
        could not tell "which is which" from the gallery cards.
        """
        style = self._style()
        shape = style.get("shape", "chip")
        palette = self._palette()
        tints = [_hex_to_rgb(palette[k]) for k in
                 ("ACCENT", "GREEN", "YELLOW", "ACCENT2", "RED")
                 if k in palette]
        total = sum(w for _n, w in chips) + spacing * max(0, len(chips) - 1)

        if shape in ("island", "capsule") and chips:
            zone_r = chip_h / 2 if shape == "capsule" else min(radius, chip_h / 2)
            rounded_path(cr, x - spacing / 2, y, total + spacing, chip_h,
                         zone_r, 2)
            cr.set_source_rgba(*surface, 0.9)
            cr.fill()
        if shape == "bracket" and chips:
            _text(cr, x - spacing * 0.6, y + chip_h / 2 + 4, "[", accent, 12,
                  bold=True, anchor="center")
            _text(cr, x + total + spacing * 0.6, y + chip_h / 2 + 4, "]",
                  accent, 12, bold=True, anchor="center")

        for index, (name, chip_w) in enumerate(chips):
            chip_r = min(radius, chip_h / 2)
            if shape == "pill":
                chip_r = chip_h / 2
            elif style.get("square"):
                chip_r = 0.0

            if shape == "pill":
                tint = tints[index % len(tints)] if style.get("colored") else surface
                rounded_path(cr, x, y, chip_w, chip_h, chip_r, 2)
                cr.set_source_rgba(*tint, 0.95 if style.get("colored") else 0.85)
                cr.fill()
            elif shape == "chip":
                rounded_path(cr, x, y, chip_w, chip_h, chip_r, 2)
                cr.set_source_rgba(*surface, 0.45 if style.get("glass") else 0.85)
                cr.fill()
                if style.get("glass"):            # top highlight of the glass
                    cr.set_source_rgba(*fg, 0.12)
                    cr.rectangle(x + 2, y + 0.5, chip_w - 4, 1)
                    cr.fill()
            elif shape == "outline":
                rounded_path(cr, x + 0.5, y + 0.5, chip_w - 1, chip_h - 1,
                             chip_r, 2)
                cr.set_source_rgba(*fg, 0.45)
                cr.set_line_width(1)
                cr.stroke()
            elif shape == "underline":
                cr.set_source_rgba(*accent, 0.55)
                cr.rectangle(x + 2, y + chip_h - 1.5, chip_w - 4, 1.5)
                cr.fill()
            elif shape == "divider" and index:
                cr.set_source_rgba(*subtext, 0.35)
                cr.rectangle(x - spacing / 2, y + 2, 1, chip_h - 4)
                cr.fill()

            if name == "hyprland/workspaces":
                self._draw_workspaces(cr, x, y, chip_w, chip_h, accent, subtext)
            elif name == "custom/power" and style.get("power_dot"):
                # In these presets the power button is round and red; drawing it
                # instead of text makes the card recognizable at a glance.
                red = _hex_to_rgb(palette.get("RED", "e06c75"))
                size = chip_h * 0.72
                rounded_path(cr, x + (chip_w - size) / 2, y + (chip_h - size) / 2,
                             size, size, size / 2, 2)
                cr.set_source_rgba(*red, 0.95)
                cr.fill()
            else:
                text = (self._clock_text() if name == "clock"
                       else self._window_text() if name == "hyprland/window"
                       else BAR_SAMPLES.get(name, name))
                if shape == "pill" and style.get("colored"):
                    colour = _hex_to_rgb(palette["BG"])
                elif name in ("clock", "custom/power"):
                    colour = accent
                elif shape in ("bare", "underline"):
                    colour = subtext
                else:
                    colour = fg
                _text(cr, x + chip_w / 2, y + chip_h / 2 + 4, text, colour,
                      10 if style.get("mono") else 11, anchor="center")
            x += chip_w + spacing

    def _draw_vertical(self, cr, width: float, height: float, palette,
                       card: bool) -> None:
        """Vertical bar on the left/right edge: modules stacked top to bottom.

        The vertical counterpart of the horizontal drawing: it uses the same
        shape table (BAR_PREVIEW_SHAPES), but modules are laid out in a column
        and labels get shorter: "Vol 60%" doesn't fit a narrow rail, nor on the real bar.
        """
        bg, bg_dark, surface, fg, subtext, accent = _rgbs(
            palette, "BG", "BG_DARK", "SURFACE", "FG", "SUBTEXT", "ACCENT")

        style = self._style()
        shape = style.get("shape", "chip")
        bar_w = max(16.0, self._num("BAR_WIDTH", 44))
        margin = self._num("BAR_MARGIN", 6)
        spacing = max(4.0, self._num("BAR_SPACING", 8))
        radius = self._num("BAR_RADIUS", 10)
        opacity = max(0.05, min(self._num("BAR_OPACITY", 0.9), 1.0))
        on_left = (self._get("BAR_POSITION") or "left") != "right"

        screen_x, screen_y = 6.0, 6.0
        screen_w = max(120.0, width - 12.0)
        screen_h = max(80.0, height - 12.0 - (0.0 if card else 20.0))
        _screen(cr, screen_x, screen_y, screen_w, screen_h, bg, bg_dark)

        bar_x = (screen_x + margin) if on_left \
            else (screen_x + screen_w - margin - bar_w)
        bar_y = screen_y + margin
        bar_h = screen_h - 2 * margin

        win_x = (bar_x + bar_w + margin) if on_left else (screen_x + margin)
        win_w = screen_w - bar_w - 3 * margin
        rounded_path(cr, win_x, bar_y, max(10.0, win_w), bar_h,
                     self._num("ROUNDING", 10), self._num("ROUNDING_POWER", 2))
        cr.set_source_rgba(*surface, 0.55)
        cr.fill()
        if not card:
            _text(cr, win_x + win_w / 2, bar_y + bar_h / 2 + 4,
                  "window area", subtext, 10, anchor="center")

        rounded_path(cr, bar_x, bar_y, bar_w, bar_h, radius, 2)
        cr.set_source_rgba(*bg_dark, opacity)
        cr.fill()

        # The top group (LEFT) stacks from the top, the bottom group (RIGHT) from
        # the bottom; zones behave like this on real vertical bars too.
        cell = max(10.0, bar_w - 10)
        top = [m for m in self._modules("LEFT")]
        bottom = [m for m in self._modules("RIGHT")]
        if card:
            top, bottom = top[:2], bottom[:4]

        def label(name: str) -> str:
            if name == "clock":
                return self._clock_text().replace("\n", " ")
            short = {"pulseaudio": "♪", "network": "≋", "battery": "▮",
                     "bluetooth": "ᛒ", "tray": "▣", "custom/power": "⏻",
                     "cpu": "CPU", "memory": "RAM", "temperature": "°C",
                     "clock": "12:34"}
            return short.get(name, BAR_SAMPLES.get(name, name)[:4])

        def draw_stack(names, start_y: float, downward: bool) -> None:
            y = start_y
            for name in names:
                cell_h = cell if name != "hyprland/workspaces" else cell * 2.2
                box_y = y if downward else y - cell_h
                if name == "hyprland/workspaces":
                    self._draw_workspaces_vertical(cr, bar_x + 5, box_y,
                                                   cell, cell_h, accent,
                                                   subtext, shape)
                else:
                    if shape in ("chip", "pill", "island", "capsule"):
                        r = cell / 2 if shape in ("pill", "capsule") else min(radius, cell / 2)
                        rounded_path(cr, bar_x + 5, box_y, cell, cell_h, r, 2)
                        cr.set_source_rgba(*surface, 0.85)
                        cr.fill()
                    elif shape == "underline":
                        cr.set_source_rgba(*accent, 0.55)
                        cr.rectangle(bar_x + 6, box_y + cell_h - 1.5,
                                     cell - 2, 1.5)
                        cr.fill()
                    colour = accent if name in ("clock", "custom/power") else fg
                    _text(cr, bar_x + 5 + cell / 2, box_y + cell_h / 2 + 4,
                          label(name), colour, 10, anchor="center")
                y = (y + cell_h + spacing) if downward else (y - cell_h - spacing)

        draw_stack(top, bar_y + spacing, True)
        draw_stack(list(reversed(bottom)), bar_y + bar_h - spacing, False)

    def _draw_workspaces_vertical(self, cr, x: float, y: float, w: float,
                                  h: float, accent, subtext, shape) -> None:
        """Workspace indicator on a vertical rail: dots stacked vertically."""
        style = self._get("BAR_WORKSPACE_STYLE") or "numbers"
        count = 3 if style == "occupied-only" else 4
        step = h / count
        for index in range(count):
            cy = y + step * index + step / 2
            active = index == 0
            size = min(w * 0.5, step * 0.5)
            if style in ("dots", "app-icons", "id-icons", "pill-expand"):
                rounded_path(cr, x + (w - size) / 2, cy - size / 2,
                             size * (1.8 if active and style == "pill-expand" else 1),
                             size, size / 2, 2)
                cr.set_source_rgba(*(accent if active else subtext),
                                   1.0 if active else 0.5)
                cr.fill()
            elif style == "underline" and active:
                cr.set_source_rgba(*accent, 0.9)
                cr.rectangle(x, cy + size / 2, w, 2)
                cr.fill()
                _text(cr, x + w / 2, cy + 4, str(index + 1), accent, 10,
                      anchor="center")
            else:
                _text(cr, x + w / 2, cy + 4, str(index + 1),
                      accent if active else subtext, 10, anchor="center")

    def _draw_workspaces(self, cr, x: float, y: float, w: float, h: float,
                         accent, subtext) -> None:
        """Visually distinguishes all 9 BAR_WORKSPACE_STYLE options.

        Only "dots"/"roman" used to be handled specially; the other 6 options
        (pill-expand, underline, bracket, occupied-only, app-icons, named)
        fell back to the same empty-label default, so changing the dropdown
        had no visible effect in the preview.
        """
        style = self._get("BAR_WORKSPACE_STYLE") or "numbers"

        if style == "occupied-only":
            count, labels = 3, ("1", "2", "3")
        else:
            count = 5
            labels = {
                "numbers": ("1", "2", "3", "4", "5"),
                "roman": ("I", "II", "III", "IV", "V"),
                "named": ("desk", "web", "code", "chat", "media"),
            }.get(style, ("1", "2", "3", "4", "5"))

        bracket_pad = h * 0.32 if style == "bracket" else 0.0
        if style == "bracket":
            _text(cr, x + bracket_pad * 0.4, y + h / 2 + 4, "[", subtext, 12,
                  bold=True, anchor="center")
            _text(cr, x + w - bracket_pad * 0.4, y + h / 2 + 4, "]", subtext,
                  12, bold=True, anchor="center")

        inner_x = x + bracket_pad
        step = (w - 2 * bracket_pad) / count
        for i in range(count):
            cx = inner_x + step * i + step / 2
            active = i == 0

            if style == "dots":
                cr.set_source_rgba(*(accent if active else subtext),
                                   1.0 if active else 0.5)
                cr.arc(cx, y + h / 2, h * (0.20 if active else 0.13), 0,
                       2 * math.pi)
                cr.fill()
                continue

            if style in ("app-icons", "id-icons"):
                size = h * (0.38 if active else 0.26)
                rounded_path(cr, cx - size / 2, y + (h - size) / 2, size, size,
                             size * 0.28, 2)
                cr.set_source_rgba(*(accent if active else subtext),
                                   0.9 if active else 0.4)
                cr.fill()
                continue

            if style == "pill-expand" and active:
                pill_w = step * 0.86
                rounded_path(cr, cx - pill_w / 2, y + h * 0.15, pill_w,
                             h * 0.7, h * 0.35, 2)
                cr.set_source_rgba(*accent, 0.9)
                cr.fill()

            label = labels[i] if i < len(labels) else str(i + 1)
            colour = (0.1, 0.1, 0.12) if (active and style == "pill-expand") \
                else (accent if active else subtext)
            _text(cr, cx, y + h / 2 + 4, label, colour, 10,
                  bold=active, anchor="center")

            if style == "underline" and active:
                uw = step * 0.55
                cr.set_source_rgba(*accent, 0.9)
                cr.set_line_width(max(1.4, h * 0.09))
                cr.move_to(cx - uw / 2, y + h * 0.8)
                cr.line_to(cx + uw / 2, y + h * 0.8)
                cr.stroke()


# ----------------------------------------------------------- patterns ------
def _linear(cr, x0, y0, x1, y1, c0, c1):
    import cairo
    pattern = cairo.LinearGradient(x0, y0, x1, y1)
    pattern.add_color_stop_rgb(0, *c0)
    pattern.add_color_stop_rgb(1, *c1)
    return pattern


def _radial(cx, cy, radius, colour, alpha: float = 0.30):
    import cairo
    pattern = cairo.RadialGradient(cx, cy, 0, cx, cy, max(radius, 1))
    pattern.add_color_stop_rgba(0, *colour, alpha)
    pattern.add_color_stop_rgba(1, *colour, 0.0)
    return pattern


class TerminalPreview(_SettingsArea):
    """Terminal window mockup reflecting the TERM_* settings.

    So opacity is really visible, a diagonal stripe standing in for the
    wallpaper is drawn behind the window: as TERM_OPACITY drops, the stripe
    shows through behind the text. Padding, font size, cursor style and
    blinking are drawn faithfully too, so what a slider does is understood
    from the picture, not from text.
    """

    SIZE = (320, 170)

    _LINES = (
        ("$", "hyprctl monitors | head"),
        ("", "Monitor DP-1 (ID 0): 2560x1440@165"),
        ("", "  scale: 1.00   transform: 0"),
        ("$", "cargo build --release"),
        ("", "   Compiling hyprsetup v0.3.0"),
        ("", "    Finished in 4.21s"),
    )

    def __init__(self, get_setting, get_palette):
        super().__init__(get_setting, get_palette)
        #: The "opacity · padding…" caption at the bottom (turned off on cards).
        self.legend = True

    def _draw(self, _area, cr, width, height) -> None:
        palette = self._palette()
        bg, bg_dark, surface, fg, subtext, accent, green = _rgbs(
            palette, "BG", "BG_DARK", "SURFACE", "FG", "SUBTEXT", "ACCENT", "GREEN")

        opacity = max(0.05, min(self._num("TERM_OPACITY", 0.95), 1.0))
        padding = max(0.0, min(self._num("TERM_PADDING", 8), 40.0))
        try:
            font_px = float(self._get("TERM_FONT_SIZE") or 0) or self._num("FONT_SIZE", 11)
        except (TypeError, ValueError):
            font_px = 11.0
        font_px = max(6.0, min(font_px, 20.0))
        cursor = (self._get("TERM_CURSOR_STYLE") or "block").strip().lower()
        blink = self._flag("TERM_CURSOR_BLINK", False)

        # --- background: a diagonal stripe standing in for the wallpaper ----
        cr.set_source_rgb(*bg_dark)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        cr.save()
        cr.set_source_rgba(*accent, 0.35)
        cr.set_line_width(18)
        cr.move_to(-10, height * 0.85)
        cr.line_to(width * 0.55, -10)
        cr.stroke()
        cr.set_source_rgba(*green, 0.22)
        cr.move_to(width * 0.35, height + 10)
        cr.line_to(width + 10, height * 0.15)
        cr.stroke()
        cr.restore()

        # --- window ----------------------------------------------------------
        win_x, win_y = 14.0, 12.0
        win_w, win_h = width - 28.0, height - 24.0
        title_h = 16.0
        rounded_path(cr, win_x, win_y, win_w, win_h, 8, 2)
        cr.set_source_rgba(*bg, opacity)
        cr.fill()

        # background image: darkened with the theme's background color
        bg_image = self._image("TERM_BG_IMAGE")
        if bg_image is not None:
            dim = max(0.0, min(self._num("TERM_BG_DIM", 0.75), 0.95))
            cr.save()
            rounded_path(cr, win_x, win_y, win_w, win_h, 8, 2)
            cr.clip()
            fit = (self._get("TERM_BG_FIT") or "cover").strip()
            _paint_pixbuf(cr, bg_image, win_x, win_y, win_w, win_h, fit, opacity)
            cr.set_source_rgba(*bg, dim * opacity)
            cr.paint()
            cr.restore()

        # title bar (a bit more opaque, as in real terminals)
        cr.save()
        rounded_path(cr, win_x, win_y, win_w, win_h, 8, 2)
        cr.clip()
        cr.set_source_rgba(*surface, min(1.0, opacity + 0.08))
        cr.rectangle(win_x, win_y, win_w, title_h)
        cr.fill()
        cr.restore()
        _text(cr, win_x + 8, win_y + title_h - 5, "kitty — ~/projects", subtext, 8.5)

        # --- padding indicator ---------------------------------------------
        pad = min(padding, win_w / 3, (win_h - title_h) / 3)
        text_x = win_x + pad
        text_y = win_y + title_h + pad
        text_w = win_w - 2 * pad
        text_h = win_h - title_h - 2 * pad
        if pad >= 3:
            cr.set_source_rgba(*accent, 0.30)
            cr.set_line_width(1.0)
            cr.set_dash([3.0, 3.0])
            cr.rectangle(text_x + 0.5, text_y + 0.5, text_w - 1, text_h - 1)
            cr.stroke()
            cr.set_dash([])

        # --- text -------------------------------------------------------------
        line_h = font_px * 1.55
        y = text_y + font_px
        last_x, last_y = text_x, y
        lines = self._LINES
        if (self._get("TERM_FETCH") or "default") == "on":
            y = self._draw_fetch(cr, text_x, text_y, text_w, text_h, font_px, palette)
            lines = (("$", ""),)
        for prompt, body in lines:
            if y > text_y + text_h:
                break
            x = text_x
            if prompt:
                # _text measures ink width; a trailing space is not included, so one
                # character's worth of room is added in between.
                x += _text(cr, x, y, prompt, green, font_px, bold=True)
                x += font_px * 0.45
            width_used = _text(cr, x, y, body, fg if prompt else subtext, font_px)
            last_x, last_y = x + width_used + font_px * 0.35, y
            y += line_h

        # --- cursor -----------------------------------------------------------
        if last_y <= text_y + text_h:
            cell_w = max(3.0, font_px * 0.6)
            alpha = 0.45 if blink else 1.0
            cr.set_source_rgba(*accent, alpha)
            if cursor == "beam":
                cr.rectangle(last_x, last_y - font_px, max(1.5, font_px * 0.12), font_px)
            elif cursor == "underline":
                cr.rectangle(last_x, last_y + 1, cell_w, max(1.5, font_px * 0.12))
            else:
                cr.rectangle(last_x, last_y - font_px, cell_w, font_px)
            cr.fill()

        # --- caption ----------------------------------------------------------
        if not self.legend:
            return
        legend = (f"opacity {opacity:.2f} · padding {int(padding)} · "
                  f"font {int(font_px)} · cursor {cursor}"
                  + (" (blinking)" if blink else ""))
        _text(cr, width / 2, height - 5, legend, subtext, 8.5, anchor="center")


    _pixbufs: dict[str, "GdkPixbuf.Pixbuf | None"] = {}

    def _image(self, key: str):
        value = (self._get(key) or "").strip()
        if not value:
            return None
        path = str(Path(value).expanduser())
        if path not in self._pixbufs:
            try:
                self._pixbufs[path] = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    path, 640, 640, True)
            except GLib.Error:
                self._pixbufs[path] = None
        return self._pixbufs[path]

    def _draw_fetch(self, cr, x, y, w, h, font_px, palette) -> float:
        """A small imitation of fastfetch output; returns the y of the line below it."""
        fg, accent, accent2, subtext = _rgbs(palette, "FG", "ACCENT", "ACCENT2", "SUBTEXT")
        full = (self._get("TERM_FETCH_INFO") or "short") == "full"
        if full:
            font_px *= 0.78                     # full info: more, denser lines
        line_h = font_px * (1.2 if full else 1.35)
        info = [("kanex@souprland", None), ("-" * 15, None),
                ("OS", "Arch Linux"), ("Kernel", "6.x"), ("Uptime", "2 hours"),
                ("WM", "Hyprland")]
        if full:
            info += [("Host", "ThinkPad"), ("Packages", "1204"), ("Shell", "fish"),
                     ("CPU", "Ryzen 7"), ("GPU", "Radeon")]
        info.append(("Memory", "6 / 16 GiB"))
        rows = min(len(info), max(1, int(h / line_h) - 2))
        block_h = rows * line_h

        logo = (self._get("TERM_LOGO") or "distro").strip()
        cell_w = font_px * 0.6
        logo_w = 0.0
        image = None
        if logo == "image":
            image = self._image("TERM_LOGO_IMAGE")
        elif logo == "souprland":
            image = _souprland_logo()
        if image is not None:
            cols = max(4, min(self._num("TERM_LOGO_WIDTH", 24), 60))
            logo_w = min(cols * cell_w, w * 0.42)
            ratio = image.get_height() / max(1, image.get_width())
            logo_h = min(logo_w * ratio, block_h)
            logo_w = logo_h / ratio if ratio else logo_w
            style = (self._get("TERM_LOGO_STYLE") or "image").strip()
            terminal = (self._get("TERMINAL") or "kitty").strip()
            if style == "image" and terminal in ("foot", "alacritty"):
                style = "block"                   # they cannot draw real images
            if style == "image":
                _paint_pixbuf(cr, image, x, y, logo_w, logo_h, "contain", 1.0)
            else:
                mono = fg if self._flag("TERM_LOGO_MONO", False) else None
                _draw_char_logo(cr, image, x, y, logo_w, logo_h, cell_w,
                                style, mono, font_px)
        elif logo in ("distro", "small"):
            # A triangle standing in for the distro logo (Arch); the small logo is half size.
            size = min(block_h, w * 0.3) * (0.55 if logo == "small" else 1.0)
            cr.set_source_rgb(*accent)
            cr.move_to(x + size / 2, y)
            cr.line_to(x + size, y + size)
            cr.line_to(x + size * 0.5, y + size * 0.72)
            cr.line_to(x, y + size)
            cr.close_path()
            cr.fill()
            logo_w = size
        tx = x + (logo_w + font_px if logo_w else 0)
        ty = y + font_px
        for key, value in info[:rows]:
            if value is None:
                _text(cr, tx, ty, key, accent2 if "@" in key else subtext, font_px,
                      bold="@" in key)
            else:
                used = _text(cr, tx, ty, key, accent, font_px, bold=True)
                _text(cr, tx + used + font_px * 0.05, ty, ": " + value, fg, font_px)
            ty += line_h
        # color blocks
        bx = tx
        for role in ("RED", "GREEN", "YELLOW", "ACCENT", "ACCENT2", "CYAN"):
            cr.set_source_rgb(*_hex_to_rgb(palette[role]))
            cr.rectangle(bx, ty - font_px * 0.8, cell_w * 1.6, font_px * 0.9)
            cr.fill()
            bx += cell_w * 1.6
        return max(ty, y + block_h) + line_h * 1.1


def _draw_char_logo(cr, pixbuf, x, y, w, h, cell_w, style, mono, font_px) -> None:
    """Sample an image onto a character grid and draw it, the way chafa does.

    braille: 2×4 dots per cell; block: two half blocks per cell;
    ascii: one letter per cell (by brightness). If ``mono`` is given, all
    characters use that color (the terminal's text color).
    """
    cell_h = cell_w * 2
    cols, rows = max(1, int(w / cell_w)), max(1, int(h / cell_h))
    sub_x, sub_y = {"braille": (2, 4), "block": (1, 2)}.get(style, (1, 1))
    small = pixbuf.add_alpha(False, 0, 0, 0).scale_simple(
        cols * sub_x, rows * sub_y, GdkPixbuf.InterpType.BILINEAR)
    data, stride = small.get_pixels(), small.get_rowstride()

    def pixel(px, py):
        i = py * stride + px * 4
        return data[i] / 255, data[i + 1] / 255, data[i + 2] / 255, data[i + 3] / 255

    ramp = " .:-=+*#%@"
    # In monochrome chafa picks foreground or background for each dot: light
    # areas of the photo become dots, dark areas blanks. The threshold is
    # the average brightness of the image's opaque pixels.
    threshold = 0.0
    if mono is not None:
        lights = [0.3 * r + 0.59 * g + 0.11 * b
                  for py in range(rows * sub_y) for px in range(cols * sub_x)
                  for r, g, b, a in (pixel(px, py),) if a >= 0.45]
        threshold = sum(lights) / len(lights) if lights else 0.0
    for row in range(rows * sub_y):
        for col in range(cols * sub_x):
            r, g, b, a = pixel(col, row)
            if a < 0.45:
                continue
            if mono is not None and 0.3 * r + 0.59 * g + 0.11 * b < threshold:
                continue
            colour = mono or (r, g, b)
            if style == "braille":
                cx = x + (col + 0.5) * cell_w / 2
                cy = y + (row + 0.5) * cell_h / 4
                cr.set_source_rgb(*colour)
                cr.arc(cx, cy, cell_w * 0.16, 0, 6.2832)
                cr.fill()
            elif style == "block":
                cr.set_source_rgb(*colour)
                cr.rectangle(x + col * cell_w, y + row * cell_h / 2,
                             cell_w + 0.3, cell_h / 2 + 0.3)
                cr.fill()
            else:
                light = (0.3 * r + 0.59 * g + 0.11 * b) * a
                char = ramp[min(len(ramp) - 1, int(light * len(ramp)))]
                if char != " ":
                    _text(cr, x + col * cell_w, y + (row + 0.8) * cell_h, char,
                          colour, font_px * 0.95)


def _souprland_logo():
    path = str(Path(__file__).resolve().parents[3] / "assets" / "souprland-mark.png")
    if path not in TerminalPreview._pixbufs:
        try:
            TerminalPreview._pixbufs[path] = GdkPixbuf.Pixbuf.new_from_file(path)
        except GLib.Error:
            TerminalPreview._pixbufs[path] = None
    return TerminalPreview._pixbufs[path]


def _paint_pixbuf(cr, pixbuf, x, y, w, h, fit: str, alpha: float) -> None:
    """Draw an image into a box: cover (fill), contain/center (fit), tile."""
    pw, ph = pixbuf.get_width(), pixbuf.get_height()
    if pw <= 0 or ph <= 0 or w <= 0 or h <= 0:
        return
    cr.save()
    cr.rectangle(x, y, w, h)
    cr.clip()
    if fit == "tile":
        scale = min(1.0, h / ph / 2)
        cr.translate(x, y)
        cr.scale(scale, scale)
        Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
        import cairo
        cr.get_source().set_extend(cairo.EXTEND_REPEAT)
        cr.paint_with_alpha(alpha)
    else:
        scale = (max(w / pw, h / ph) if fit == "cover" else min(w / pw, h / ph))
        cr.translate(x + (w - pw * scale) / 2, y + (h - ph * scale) / 2)
        cr.scale(scale, scale)
        Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
        cr.paint_with_alpha(alpha)
    cr.restore()


class LauncherLayoutPreview(_SettingsArea):
    """Mockup showing the LAUNCHER_* settings at screen scale.

    ``LauncherPreview`` shows what each PROGRAM looks like (wofi or
    fuzzel); this one shows how much screen the selected settings take:
    width percentage, number of rows, position, icon size and opacity.
    """

    SIZE = (320, 170)

    def _draw(self, _area, cr, width, height) -> None:
        palette = self._palette()
        bg, bg_dark, surface, fg, subtext, accent = _rgbs(
            palette, "BG", "BG_DARK", "SURFACE", "FG", "SUBTEXT", "ACCENT")

        pct = max(10.0, min(self._num("LAUNCHER_WIDTH", 45), 100.0))
        lines = int(max(1.0, min(self._num("LAUNCHER_LINES", 10), 30.0)))
        position = (self._get("LAUNCHER_POSITION") or "center").strip().lower()
        opacity = max(0.05, min(self._num("LAUNCHER_OPACITY", 0.93), 1.0))
        icons = self._flag("LAUNCHER_ICONS", True)
        icon_px = max(8.0, min(self._num("LAUNCHER_ICON_SIZE", 32), 64.0))
        prompt = (self._get("LAUNCHER_PROMPT") or "Search…").strip()
        # Shape (same rule as render.py:_launcher_vars): empty = same as windows.
        radius = self._num("LAUNCHER_RADIUS", self._num("ROUNDING", 10))
        border = self._num("LAUNCHER_BORDER", self._num("BORDER_SIZE", 2))

        # --- screen ------------------------------------------------------------
        legend_h = 18.0
        sx, sy = 8.0, 8.0
        sw, sh = width - 16.0, height - 16.0 - legend_h
        rounded_path(cr, sx, sy, sw, sh, 6, 2)
        cr.set_source_rgb(*bg_dark)
        cr.fill()
        cr.set_source_rgba(*subtext, 0.25)
        cr.set_line_width(1.0)
        rounded_path(cr, sx + 0.5, sy + 0.5, sw - 1, sh - 1, 6, 2)
        cr.stroke()

        # Real pixels are scaled relative to the screen; corners have a minimum
        # so they stay distinguishable.
        px = max(0.35, sw / 700.0)

        # --- active bar preset --------------------------------------------------
        # How the launcher matches the bar only shows when both are side by side.
        bar_pos = (self._get("BAR_POSITION") or "top").strip().lower()
        bar_top = 0.0
        if bar_pos in ("top", "bottom"):
            bar_h = max(4.0, self._num("BAR_HEIGHT", 32) * px * 0.55)
            margin = self._num("BAR_MARGIN", 0) * px * 0.55
            bar_y = (sy + 2 + margin if bar_pos == "top"
                     else sy + sh - 2 - margin - bar_h)
            bar_r = min(bar_h / 2, self._num("BAR_RADIUS", 0) * px * 0.55)
            rounded_path(cr, sx + 2 + margin, bar_y, sw - 4 - 2 * margin,
                         bar_h, bar_r, 2)
            cr.set_source_rgba(*bg, max(0.25, self._num("BAR_OPACITY", 0.9)))
            cr.fill()
            if bar_pos == "top":
                bar_top = bar_y + bar_h - sy

        # --- launcher window --------------------------------------------------
        # Row height grows with the icon size (as in real launchers); the scale
        # is reduced according to the screen width.
        scale = sw / 1000.0
        row_h = max(5.0, (icon_px if icons else 18.0) * 0.55 * scale * 1.6)
        input_h = max(9.0, 26.0 * scale * 1.6)
        pad = max(3.0, 12.0 * scale * 1.6)

        box_w = sw * (pct / 100.0)
        box_h = min(sh - 12, input_h + lines * row_h + pad * 2)
        box_x = sx + (sw - box_w) / 2
        box_y = (sy + max(10.0, bar_top + 6) if position == "top"
                 else sy + (sh - box_h) / 2)

        box_r = min(box_h / 2, max(0.0, radius) * px)
        inner_r = max(0.0, box_r - 4 * px) if box_r > 4 * px else box_r
        rounded_path(cr, box_x, box_y, box_w, box_h, box_r, 2)
        cr.set_source_rgba(*bg, opacity)
        cr.fill()
        if border > 0:
            line = max(0.8, border * px)
            rounded_path(cr, box_x + line / 2, box_y + line / 2,
                         box_w - line, box_h - line, box_r, 2)
            cr.set_source_rgba(*accent, 0.85)
            cr.set_line_width(line)
            cr.stroke()

        # search box
        inner_x = box_x + pad
        inner_w = box_w - 2 * pad
        rounded_path(cr, inner_x, box_y + pad, inner_w, input_h, inner_r, 2)
        cr.set_source_rgba(*surface, opacity)
        cr.fill()
        _text(cr, inner_x + 6, box_y + pad + input_h * 0.72,
              prompt, subtext, min(10.0, input_h * 0.6))

        # result rows
        y = box_y + pad + input_h + 3
        for index in range(lines):
            if y + row_h > box_y + box_h - pad * 0.5:
                break
            if index == 0:
                rounded_path(cr, inner_x, y, inner_w, row_h - 2,
                             min(inner_r, (row_h - 2) / 2), 2)
                cr.set_source_rgba(*accent, 0.85)
                cr.fill()
            text_x = inner_x + 4
            if icons:
                icon_side = min(row_h - 4, icon_px * 0.5 * scale * 1.6)
                if icon_side >= 2:
                    rounded_path(cr, text_x, y + (row_h - 2 - icon_side) / 2,
                                 icon_side, icon_side, 2, 2)
                    cr.set_source_rgba(*(bg if index == 0 else accent), 0.9)
                    cr.fill()
                    text_x += icon_side + 4
            bar_w = inner_w * (0.55 if index % 3 else 0.4) - (text_x - inner_x)
            if bar_w > 2:
                cr.set_source_rgba(*(bg if index == 0 else fg),
                                   0.9 if index == 0 else 0.45)
                cr.rectangle(text_x, y + (row_h - 2) / 2 - 1.5,
                             max(4.0, bar_w), 3)
                cr.fill()
            y += row_h

        legend = (f"{int(pct)}% · {lines} rows · "
                  f"{'center' if position == 'center' else 'top'} · "
                  f"corner {int(radius)} · border {int(border)} · "
                  + (f"icons {int(icon_px)}" if icons else "no icons"))
        _text(cr, width / 2, height - 5, legend, subtext, 8.5, anchor="center")


class WidgetPreview(_SettingsArea):
    """Draw WHERE the desktop widgets will land on screen.

    The Widgets page's live preview. The box positions are not guessed
    here: they are computed by the same function that generates the config
    (render.widget_layout), so the preview and the real desktop cannot
    diverge. Sizes are reduced to the screen ratio; since the real
    resolution isn't needed for the screen itself, 1920x1080 is assumed;
    even if the ratio changes, "which corner, in what order" stays the same.
    """

    SIZE = (420, 260)

    #: Default screen the scaling is based on.
    SCREEN = (1920.0, 1080.0)

    def __init__(self, get_setting, get_palette, get_layout):
        super().__init__(get_setting, get_palette)
        #: () -> [{name, zone, v_edge, h_edge, x, y, width, height}]
        self._layout = get_layout

    def _draw(self, _area, cr, width, height) -> None:
        palette = self._palette()
        bg, bg_dark, surface, fg, subtext, accent = _rgbs(
            palette, "BG", "BG_DARK", "SURFACE", "FG", "SUBTEXT", "ACCENT")

        pad = 6.0
        legend = 18.0
        screen_w = max(120.0, width - 2 * pad)
        screen_h = max(90.0, height - 2 * pad - legend)
        # Keep the screen ratio, so boxes sit as they really would.
        ratio = self.SCREEN[0] / self.SCREEN[1]
        if screen_w / screen_h > ratio:
            screen_w = screen_h * ratio
        else:
            screen_h = screen_w / ratio
        screen_x = pad + (width - 2 * pad - screen_w) / 2
        screen_y = pad
        scale = screen_w / self.SCREEN[0]

        _screen(cr, screen_x, screen_y, screen_w, screen_h, bg, bg_dark)

        # Bar: show that widgets keep clear of it.
        position = (self._get("BAR_POSITION") or "top").strip()
        hidden = self._flag("BAR_AUTOHIDE")
        bar_margin = self._num("BAR_MARGIN", 6) * scale
        if not hidden:
            vertical = position in ("left", "right")
            thickness = (self._num("BAR_WIDTH", 44) if vertical
                         else self._num("BAR_HEIGHT", 38)) * scale
            if vertical:
                bar_x = (screen_x + bar_margin if position == "left"
                         else screen_x + screen_w - bar_margin - thickness)
                bar_rect = (bar_x, screen_y + bar_margin, thickness,
                            screen_h - 2 * bar_margin)
            else:
                bar_y = (screen_y + bar_margin if position == "top"
                         else screen_y + screen_h - bar_margin - thickness)
                bar_rect = (screen_x + bar_margin, bar_y,
                            screen_w - 2 * bar_margin, thickness)
            rounded_path(cr, *bar_rect, 4, 2)
            cr.set_source_rgba(*surface, 0.9)
            cr.fill()

        items = list(self._layout())

        # Audio visualizer (VIS_*): behind the windows in desktop mode, on top
        # and shortening the windows in bottom-strip mode.
        vis = self._flag("VIS_ENABLE")
        vis_strip = vis and (self._get("VIS_MODE") or "desktop").strip() == "strip"
        vis_h = max(4.0, self._num("VIS_HEIGHT", 130) * scale)
        if vis and not vis_strip:
            self._draw_visualizer(cr, palette, screen_x, screen_y, screen_w,
                                  screen_h, vis_h)

        # Sample window: with WIDGET_LAYER "bottom" it lands ON TOP of the widgets,
        # with "top" below them, so you can see what the layer means.
        win_w, win_h = screen_w * 0.38, screen_h * 0.46
        win_x = screen_x + (screen_w - win_w) / 2
        win_y = screen_y + screen_h * 0.22
        if vis_strip:
            win_h = min(win_h, screen_y + screen_h - vis_h - 4 - win_y)
        layer_top = (self._get("WIDGET_LAYER") or "bottom").strip() == "top"

        def ghost_window() -> None:
            rounded_path(cr, win_x, win_y, win_w, win_h, 4, 2)
            cr.set_source_rgba(*surface, 0.92)
            cr.fill()
            rounded_path(cr, win_x, win_y, win_w, win_h, 4, 2)
            cr.set_source_rgba(*subtext, 0.6)
            cr.set_line_width(1.0)
            cr.stroke()
            _text(cr, win_x + win_w / 2, win_y + win_h / 2 + 3, "window",
                  subtext, 9, anchor="center")

        if layer_top:
            ghost_window()

        radius = max(2.0, self._num("WIDGET_RADIUS", 12) * scale)
        opacity = max(0.15, min(self._num("WIDGET_OPACITY", 0.85), 1.0))
        for item in items:
            box_w = float(item["width"]) * scale
            box_h = float(item["height"]) * scale
            off_x = float(item["x"]) * scale
            off_y = float(item["y"]) * scale
            if item["h_edge"] == "center":
                box_x = screen_x + (screen_w - box_w) / 2
            elif item["h_edge"] == "left":
                box_x = screen_x + off_x
            else:
                box_x = screen_x + screen_w - off_x - box_w
            box_y = (screen_y + off_y if item["v_edge"] == "top"
                     else screen_y + screen_h - off_y - box_h)

            rounded_path(cr, box_x, box_y, box_w, box_h, radius, 2)
            cr.set_source_rgba(*bg_dark, opacity)
            cr.fill()
            rounded_path(cr, box_x, box_y, box_w, box_h, radius, 2)
            cr.set_source_rgba(*accent, 0.8)
            cr.set_line_width(1.0)
            cr.stroke()

            label = WIDGET_PREVIEW_LABELS.get(str(item["name"]), str(item["name"]))
            if _text_width(cr, label, 9) < box_w - 6:
                _text(cr, box_x + box_w / 2, box_y + box_h / 2 + 3,
                      label, fg, 9, anchor="center")

        if not layer_top:
            ghost_window()
        if not items:
            # Below the sample window, so they don't overlap.
            _text(cr, screen_x + screen_w / 2, win_y + win_h + 22,
                  "No active widgets", subtext, 11, anchor="center")
        if vis_strip:
            strip_y = screen_y + screen_h - vis_h
            cr.save()
            rounded_path(cr, screen_x, screen_y, screen_w, screen_h, 6, 2)
            cr.clip()
            cr.set_source_rgba(*bg_dark, 0.6)
            cr.rectangle(screen_x, strip_y, screen_w, vis_h)
            cr.fill()
            cr.restore()
            self._draw_visualizer(cr, palette, screen_x, screen_y, screen_w,
                                  screen_h, vis_h)

        note = (f"{len(items)} widgets · margin "
                f"{self._num('WIDGET_MARGIN', 16):g} · gap "
                f"{self._num('WIDGET_GAP', 10):g} · scale "
                f"{self._num('WIDGET_SCALE', 1.0):.2f} · "
                + ("above windows" if layer_top else "below windows"))
        if vis:
            note += " · visualizer"
        _text(cr, screen_x, height - 5, note, subtext, 9)

    def _draw_visualizer(self, cr, palette, sx, sy, sw, sh, bar_h) -> None:
        """cava bars: bass in the middle (tall), treble at the edges (short)."""
        colour_hex = (self._get("VIS_COLOR") or "").strip() or palette["ACCENT"]
        try:
            colour = _hex_to_rgb(colour_hex)
        except ValueError:
            colour = _hex_to_rgb(palette["ACCENT"])
        bright = max(0.05, min(1.0, self._num("VIS_BRIGHTNESS", 60) / 100))
        span = sw * max(0.1, min(1.0, self._num("VIS_WIDTH", 60) / 100))
        x0 = sx + (sw - span) / 2
        count = max(8, int(span / 5))
        bar_w = span / count
        for i in range(count):
            # Bars near the middle are tall and a bit wavy.
            centre = 1 - abs(i - (count - 1) / 2) / ((count - 1) / 2 or 1)
            level = 0.25 + 0.65 * centre ** 1.4 + 0.1 * math.sin(i * 1.7) ** 2
            h = bar_h * min(1.0, level)
            cr.set_source_rgba(*colour, 0.25 + 0.75 * bright)
            cr.rectangle(x0 + i * bar_w + bar_w * 0.15, sy + sh - h,
                         bar_w * 0.7, h)
            cr.fill()


#: Short names in the preview boxes; full titles don't fit.
WIDGET_PREVIEW_LABELS = {
    "clock": "clock",
    "sysinfo": "system",
    "battery": "battery",
    "calendar": "calendar",
    "music": "music",
    "network": "network",
    "volume": "volume",
    "brightness": "light",
    "uptime": "uptime",
    "disk": "disk",
    "temperature": "temp",
    "worldclock": "clocks",
    "kblayout": "keyboard",
    "fetch-mini": "system card",
    "workspace": "workspace",
}


class WidgetSample(_SettingsArea):
    """A small sample of how a single widget looks on the desktop.

    It sits next to the name in the Widgets page list: names like "System
    card" or "Workspace" alone did not tell what would be drawn. The
    content mirrors the lines in the templates (templates/eww/eww.yuck.tmpl)
    with sample values; colors come from the selected theme, corner radius
    and opacity from the Widgets settings. Since the icon font (Nerd Font)
    isn't on every system, icons are drawn as simple cairo shapes.
    """

    SIZE = (150, 76)

    def __init__(self, name: str, get_setting, get_palette):
        super().__init__(get_setting, get_palette)
        self.name = name
        self.set_hexpand(False)

    def _draw(self, _area, cr, width, height) -> None:
        palette = self._palette()
        fg, sub, accent = _rgbs(palette, "FG", "SUBTEXT", "ACCENT")
        green = _hex_to_rgb(palette.get("GREEN") or palette["ACCENT"])
        bg, bg_dark, surface = _rgbs(palette, "BG", "BG_DARK", "SURFACE")

        # Desktop background, so the box's opacity is visible.
        cr.set_source(_linear(cr, 0, 0, width, height, bg, bg_dark))
        rounded_path(cr, 0, 0, width, height, 8, 2)
        cr.fill()

        opacity = max(0.15, min(self._num("WIDGET_OPACITY", 0.85), 1.0))
        radius = max(0.0, min(self._num("WIDGET_RADIUS", 12), 18))
        pad = 8.0
        bx, by, bw, bh = pad, pad, width - 2 * pad, height - 2 * pad
        rounded_path(cr, bx, by, bw, bh, radius * 0.7, 2)
        cr.set_source_rgba(*bg_dark, opacity)
        cr.fill()
        rounded_path(cr, bx, by, bw, bh, radius * 0.7, 2)
        cr.set_source_rgba(*surface, 0.9)
        cr.set_line_width(1.0)
        cr.stroke()

        cx, cy = bx + bw / 2, by + bh / 2
        left = bx + 10

        def bar(x, y, w, frac, colour=accent):
            rounded_path(cr, x, y, w, 4, 2, 2)
            cr.set_source_rgba(*surface, 1.0)
            cr.fill()
            rounded_path(cr, x, y, max(4, w * frac), 4, 2, 2)
            cr.set_source_rgba(*colour, 1.0)
            cr.fill()

        name = self.name
        if name == "clock":
            _text(cr, cx, cy + 3, "14:32:07", fg, 17, bold=True, anchor="center")
            _text(cr, cx, cy + 17, "Tuesday, Sep 23", sub, 8.5, anchor="center")
        elif name == "sysinfo":
            for i, (label, frac) in enumerate((("CPU", 0.23), ("RAM", 0.58))):
                y = by + 20 + i * 20
                _text(cr, left, y, f"{label}  {round(frac * 100)}%", fg, 9.5)
                bar(left + 62, y - 5, bw - 82, frac)
        elif name == "battery":
            # Battery icon: body + tip + charge level.
            ix, iy = left, cy - 7
            rounded_path(cr, ix, iy, 24, 14, 3, 2)
            cr.set_source_rgba(*fg, 0.9); cr.set_line_width(1.4); cr.stroke()
            cr.rectangle(ix + 24, iy + 4, 2.5, 6); cr.fill()
            rounded_path(cr, ix + 2.5, iy + 2.5, 19 * 0.76, 9, 1.5, 2)
            cr.set_source_rgba(*green, 1.0); cr.fill()
            _text(cr, ix + 34, cy + 4, "76%  charging", fg, 10)
        elif name == "calendar":
            _text(cr, cx, by + 13, "September 2026", fg, 8, bold=True, anchor="center")
            cols, rows = 7, 4
            cw, ch = (bw - 16) / cols, (bh - 20) / rows
            day = 1
            for r in range(rows):
                for c in range(cols):
                    x = bx + 8 + c * cw + cw / 2
                    y = by + 24 + r * ch + ch / 2
                    if day == 23:
                        cr.arc(x, y - 2.5, min(cw, ch) / 2, 0, 2 * math.pi)
                        cr.set_source_rgba(*accent, 1.0); cr.fill()
                        colour = bg_dark
                    else:
                        colour = sub
                    _text(cr, x, y + 1, str(day), colour, 6.5, anchor="center")
                    day += 1
        elif name == "music":
            # Play triangle.
            cr.move_to(left, cy - 12); cr.line_to(left + 10, cy - 6)
            cr.line_to(left, cy); cr.close_path()
            cr.set_source_rgba(*accent, 1.0); cr.fill()
            _text(cr, left + 16, cy - 3, "Daft Punk — Veridis…", fg, 8.5)
            bar(left, cy + 8, bw - 20, 0.42)
        elif name in ("network", "volume", "brightness", "disk",
                      "temperature", "uptime", "kblayout"):
            icon_x, icon_y = left + 8, cy
            cr.set_source_rgba(*accent, 1.0)
            cr.set_line_width(1.6)
            if name == "network":
                for r in (4, 8, 12):
                    cr.arc(icon_x, icon_y + 5, r, math.radians(225),
                           math.radians(315))
                    cr.stroke()
                text, frac = "Home-WiFi  ·  82%", None
            elif name == "volume":
                cr.rectangle(icon_x - 7, icon_y - 3, 4, 6); cr.fill()
                cr.move_to(icon_x - 3, icon_y - 3); cr.line_to(icon_x + 2, icon_y - 7)
                cr.line_to(icon_x + 2, icon_y + 7); cr.line_to(icon_x - 3, icon_y + 3)
                cr.close_path(); cr.fill()
                cr.arc(icon_x + 3, icon_y, 6, -0.8, 0.8); cr.stroke()
                text, frac = "Volume  65%", 0.65
            elif name == "brightness":
                cr.arc(icon_x, icon_y, 4, 0, 2 * math.pi); cr.fill()
                for k in range(8):
                    a = k * math.pi / 4
                    cr.move_to(icon_x + 6 * math.cos(a), icon_y + 6 * math.sin(a))
                    cr.line_to(icon_x + 8.5 * math.cos(a), icon_y + 8.5 * math.sin(a))
                cr.stroke()
                text, frac = "Brightness  80%", 0.80
            elif name == "disk":
                rounded_path(cr, icon_x - 7, icon_y - 8, 14, 16, 2, 2); cr.stroke()
                cr.arc(icon_x, icon_y + 3, 2, 0, 2 * math.pi); cr.fill()
                text, frac = "/  64% full", 0.64
            elif name == "temperature":
                cr.move_to(icon_x, icon_y - 9); cr.line_to(icon_x, icon_y + 3); cr.stroke()
                cr.arc(icon_x, icon_y + 5, 3.5, 0, 2 * math.pi); cr.fill()
                text, frac = "CPU  52°C", 0.52
            elif name == "uptime":
                cr.arc(icon_x, icon_y, 7.5, 0, 2 * math.pi); cr.stroke()
                cr.move_to(icon_x, icon_y); cr.line_to(icon_x, icon_y - 5)
                cr.move_to(icon_x, icon_y); cr.line_to(icon_x + 4, icon_y); cr.stroke()
                text, frac = "3 h 12 min", None
            else:   # kblayout
                rounded_path(cr, icon_x - 8, icon_y - 6, 16, 12, 2, 2); cr.stroke()
                for k in range(3):
                    cr.rectangle(icon_x - 5 + k * 4, icon_y - 3, 2, 2)
                cr.rectangle(icon_x - 4, icon_y + 2, 8, 1.6); cr.fill()
                text, frac = "English (US)", None
            if frac is None:
                _text(cr, left + 22, cy + 4, text, fg, 10)
            else:
                _text(cr, left + 22, cy - 1, text, fg, 9.5)
                bar(left + 22, cy + 6, bw - 42, frac)
        elif name == "worldclock":
            for i, (city, time_) in enumerate((("London", "12:32"),
                                               ("Tokyo", "20:32"),
                                               ("New York", "07:32"))):
                y = by + 17 + i * 15
                _text(cr, left, y, city, sub, 8.5)
                _text(cr, bx + bw - 10, y, time_, fg, 9, bold=True, anchor="right")
        elif name == "fetch-mini":
            _text(cr, left, by + 18, "user@arch", accent, 9.5, bold=True)
            _text(cr, left, by + 33, "linux 6.16-arch", sub, 8)
            _text(cr, left, by + 46, "fish", sub, 8)
        elif name == "workspace":
            _text(cr, cx, cy + 2, "3", fg, 20, bold=True, anchor="center")
            for k in range(5):
                x = cx - 20 + k * 10
                cr.arc(x, cy + 13, 2.2 if k != 2 else 3, 0, 2 * math.pi)
                cr.set_source_rgba(*(accent if k == 2 else sub), 1.0)
                cr.fill()
        else:
            _text(cr, cx, cy + 3, name, fg, 10, anchor="center")


# --------------------------------------------------- full-screen mockups ---
# The Setup Wizard's notification / lock / login screen steps. None of the
# three has its own settings: colors come from the palette, corners from
# ROUNDING, text from FONT_FAMILY. Sizes match the templates
# (templates/hypr/hyprlock.conf.tmpl, mako/config.tmpl, dunst/dunstrc.tmpl,
# swaync/style.css.tmpl); drawn on a 1920×1080 screen and scaled to the widget.
def _family_font(cr, family: str, size: float, bold: bool = False) -> None:
    import cairo
    cr.select_font_face(family or "Sans", cairo.FONT_SLANT_NORMAL,
                        cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    cr.set_font_size(size)


def _family_text(cr, x: float, y: float, text: str, colour, size: float,
                 family: str, bold: bool = False, anchor: str = "left",
                 alpha: float = 1.0) -> float:
    _family_font(cr, family, size, bold)
    extents = cr.text_extents(text)
    if anchor == "center":
        x -= extents.width / 2 + extents.x_bearing
    elif anchor == "right":
        x -= extents.width + extents.x_bearing
    cr.set_source_rgba(*colour, alpha)
    cr.move_to(x, y)
    cr.show_text(text)
    return extents.width


class _ScreenMockup(_SettingsArea):
    """Base that fits a 16:9 screen into the widget and paints it with the wallpaper."""

    SIZE = (360, 220)

    def _screen(self, width: float, height: float) -> tuple[float, float, float, float]:
        """The 16:9 rectangle inside the widget (x, y, w, h)."""
        w = min(width, height * 16 / 9)
        h = w * 9 / 16
        return (width - w) / 2, (height - h) / 2, w, h

    def _wallpaper(self):
        return _wallpaper_surface(self._get("THEME") or themes.DEFAULT,
                                  self._get("WALLPAPER_STYLE"),
                                  self._get("WALLPAPER_PATH"),
                                  self._get("CUSTOM_COLORS"))

    def _paint_wallpaper(self, cr, x, y, w, h, blur: bool = False,
                         surface=None) -> None:
        import cairo
        palette = self._palette()
        surface = surface if surface is not None else self._wallpaper()
        cr.save()
        rounded_path(cr, x, y, w, h, 6, 2)
        cr.clip()
        cr.set_source_rgb(*_hex_to_rgb(palette["BG"]))
        cr.paint()
        if surface is not None:
            sw, sh = surface.get_width(), surface.get_height()
            if blur:
                # Cairo has no blur: the image is scaled down to a small surface and
                # back up with a smooth filter, close to hyprlock's blur.
                small = cairo.ImageSurface(cairo.FORMAT_RGB24, 48, 27)
                sc = cairo.Context(small)
                sc.scale(48 / max(1, sw), 27 / max(1, sh))
                sc.set_source_surface(surface, 0, 0)
                sc.paint()
                surface, sw, sh = small, 48, 27
            cr.translate(x, y)
            cr.scale(w / sw, h / sh)
            cr.set_source_surface(surface, 0, 0)
            cr.get_source().set_filter(cairo.FILTER_BILINEAR if blur
                                       else cairo.FILTER_GOOD)
            cr.paint()
        cr.restore()


class LockPreview(_ScreenMockup):
    """hyprlock lock screen: blurred wallpaper, clock, date, password box."""

    def _draw(self, _area, cr, width, height) -> None:
        palette = self._palette()
        fg, sub, accent, surface = _rgbs(palette, "FG", "SUBTEXT", "ACCENT", "SURFACE")
        family = self._get("FONT_FAMILY")
        x, y, w, h = self._screen(width, height)
        self._paint_wallpaper(cr, x, y, w, h, blur=True)
        # brightness = 0.8
        cr.set_source_rgba(0, 0, 0, 0.2)
        rounded_path(cr, x, y, w, h, 6, 2)
        cr.fill()
        s = h / 1080.0
        cx, cy = x + w / 2, y + h / 2
        _family_text(cr, cx, cy - 220 * s + 40 * s, time.strftime("%H:%M"), fg,
                     110 * s, family, anchor="center")
        _family_text(cr, cx, cy - 130 * s + 10 * s, time.strftime("%A, %B %d, %Y"),
                     sub, 20 * s, family, anchor="center")
        fw, fh = 320 * s, 52 * s
        fx, fy = cx - fw / 2, cy + 70 * s - fh / 2
        radius = self._num("ROUNDING", 10) * s
        rounded_path(cr, fx, fy, fw, fh, radius, 2)
        cr.set_source_rgb(*surface)
        cr.fill_preserve()
        cr.set_source_rgb(*accent)
        cr.set_line_width(max(1.0, 2 * s))
        cr.stroke()
        _family_text(cr, cx, fy + fh / 2 + 5 * s, "Password…", sub, 16 * s, family,
                     anchor="center")


class NotificationPreview(_ScreenMockup):
    """The top-right corner of the screen and the selected notifier's cards.

    ``get_notifier`` returns the currently selected program ("mako" | "dunst"
    | "swaync"); card width and opacity change accordingly.
    """

    def __init__(self, get_setting, get_palette, get_notifier):
        super().__init__(get_setting, get_palette)
        self._notifier = get_notifier

    def _draw(self, _area, cr, width, height) -> None:
        palette = self._palette()
        bg, fg, sub, accent, red = _rgbs(palette, "BG", "FG", "SUBTEXT", "ACCENT", "RED")
        family = self._get("FONT_FAMILY")
        notifier = self._notifier() or "mako"
        # The top-right 960×540 quarter of the screen is shown close to 1:1: on
        # the full screen a 380-pixel card shrank until it was unreadable.
        x, y, w, h = self._screen(width, height)
        full = self._wallpaper()
        if full is not None:
            import cairo
            quarter = cairo.ImageSurface(cairo.FORMAT_RGB24, 480, 270)
            qc = cairo.Context(quarter)
            sw, sh = full.get_width(), full.get_height()
            qc.scale(960 / max(1, sw), 540 / max(1, sh))
            qc.translate(-sw / 2, 0)
            qc.set_source_surface(full, 0, 0)
            qc.paint()
            full = quarter
        self._paint_wallpaper(cr, x, y, w, h, surface=full)
        s = h / 540.0
        card_w = (400 if notifier == "swaync" else 380) * s
        alpha = (max(0.3, min(1.0, self._num("BAR_OPACITY", 0.85)))
                 if notifier == "swaync" else 0.95)
        radius = self._num("ROUNDING", 10) * s
        size = max(8.0, self._num("FONT_SIZE", 11)) * 1.33 * s
        margin = 12 * s
        cards = (("Souprland", "Setup Wizard finished.", accent),
                 ("Battery low", "8% left; plug in the charger.", red))
        cy = y + margin
        for title, body, border in cards:
            ch = size * 4.6
            cx = x + w - margin - card_w
            rounded_path(cr, cx, cy, card_w, ch, radius, 2)
            cr.set_source_rgba(*bg, alpha)
            cr.fill_preserve()
            cr.set_source_rgb(*border)
            cr.set_line_width(max(1.0, 2 * s))
            cr.stroke()
            icon = size * 2.2
            cr.arc(cx + 14 * s + icon / 2, cy + ch / 2, icon / 2, 0, 2 * math.pi)
            cr.set_source_rgba(*border, 0.35)
            cr.fill()
            tx = cx + 14 * s + icon + 12 * s
            _family_text(cr, tx, cy + ch / 2 - size * 0.25, title,
                         red if border is red else fg, size, family, bold=True)
            _family_text(cr, tx, cy + ch / 2 + size * 1.2, body,
                         red if border is red else sub, size * 0.92, family)
            cy += ch + 10 * s
        _text(cr, x + 8, y + h - 8, f"{notifier} · top-right corner (zoomed in)",
              fg, 9, alpha=0.8)


class GreeterPreview(_ScreenMockup):
    """Login screen sketch: background, clock, user and password box.

    ``get_choice`` returns ("keep" | "wallpaper" | "color", clock on?, my
    palette?). With "keep" the background is drawn neutral grey; we do not
    read the system's current image.
    """

    def __init__(self, get_setting, get_palette, get_choice):
        super().__init__(get_setting, get_palette)
        self._choice = get_choice

    def _draw(self, _area, cr, width, height) -> None:
        mode, clock, own_colours = self._choice()
        palette = self._palette() if own_colours else {
            "BG": "232629", "FG": "eff0f1", "SUBTEXT": "a1a9b1",
            "ACCENT": "3daee9", "SURFACE": "31363b"}
        fg, sub, accent, surface = _rgbs(palette, "FG", "SUBTEXT", "ACCENT", "SURFACE")
        x, y, w, h = self._screen(width, height)
        if mode == "wallpaper":
            self._paint_wallpaper(cr, x, y, w, h)
        else:
            colour = (_hex_to_rgb(self._palette()["BG"]) if mode == "color"
                      else (0.23, 0.25, 0.27))
            rounded_path(cr, x, y, w, h, 6, 2)
            cr.set_source_rgb(*colour)
            cr.fill()
        s = h / 1080.0
        cx, cy = x + w / 2, y + h / 2
        if clock:
            _text(cr, cx, cy - 250 * s, time.strftime("%H:%M"), fg, 96 * s,
                  anchor="center")
        cr.new_path()      # don't connect show_text's leftover point to the arc
        cr.arc(cx, cy - 60 * s, 64 * s, 0, 2 * math.pi)
        cr.set_source_rgba(*surface, 0.9)
        cr.fill_preserve()
        cr.set_source_rgb(*accent)
        cr.set_line_width(max(1.0, 3 * s))
        cr.stroke()
        _text(cr, cx, cy + 40 * s, "user", fg, 26 * s, anchor="center")
        fw, fh = 360 * s, 50 * s
        rounded_path(cr, cx - fw / 2, cy + 70 * s, fw, fh, 8 * s, 2)
        cr.set_source_rgba(*surface, 0.9)
        cr.fill_preserve()
        cr.set_source_rgba(*accent, 0.8)
        cr.set_line_width(max(1.0, 2 * s))
        cr.stroke()
        _text(cr, cx, cy + 70 * s + fh / 2 + 6 * s, "Password", sub, 18 * s,
              anchor="center")
