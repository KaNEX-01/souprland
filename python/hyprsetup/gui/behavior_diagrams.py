"""Live diagrams for the Behavior page.

The Behavior page used to have drawings only next to the mouse and cursor
groups; snapping, ALT+Tab, window groups, touchpad gestures and plugins were
plain switch/number rows. "Snap distance 5" or "filled tabs or a thin line"
cannot be grasped by reading. These diagrams read the same settings and are
redrawn as they change (app._on_state_changed).

All of them use the preview._SettingsArea base and its drawing helpers;
colors come from the selected palette.
"""

from __future__ import annotations

import math

from .preview import (_SettingsArea, _arrow_head, _hex_to_rgb, _linear,
                      _text, _text_width, rounded_path)

#: Screen the diagrams are based on (for ratios; the real resolution is not needed).
SCREEN_W, SCREEN_H = 1920.0, 1080.0


def _colours(palette: dict) -> dict:
    return {key: _hex_to_rgb(palette[key])
            for key in ("BG", "BG_DARK", "SURFACE", "FG", "SUBTEXT",
                        "ACCENT", "ACCENT2", "RED", "GREEN", "YELLOW")}


def _screen(cr, c: dict, x: float, y: float, w: float, h: float) -> None:
    cr.set_source(_linear(cr, x, y, x + w, y + h, c["BG"], c["BG_DARK"]))
    rounded_path(cr, x, y, w, h, 6, 2)
    cr.fill()


def _window(cr, c: dict, x: float, y: float, w: float, h: float,
            active: bool = False, radius: float = 4.0, dashed: bool = False,
            lines: int = 3) -> None:
    """Small window: body, border, a few content lines."""
    rounded_path(cr, x, y, w, h, radius, 2)
    cr.set_source_rgba(*c["SURFACE"], 0.95)
    cr.fill()
    rounded_path(cr, x, y, w, h, radius, 2)
    cr.set_source_rgba(*(c["ACCENT"] if active else c["SUBTEXT"]),
                       1.0 if active else 0.45)
    cr.set_line_width(1.6 if active else 1.0)
    if dashed:
        cr.set_dash([3, 2])
    cr.stroke()
    cr.set_dash([])
    cr.set_source_rgba(*c["SUBTEXT"], 0.35)
    for i in range(lines):
        line_y = y + 7 + i * 5
        if line_y > y + h - 4:
            break
        cr.rectangle(x + 5, line_y, max(4.0, (w - 10) * (0.9 - 0.2 * i)), 1.6)
        cr.fill()


def _chips(cr, c: dict, x: float, y: float, width: float,
           items: list[tuple[str, bool]]) -> None:
    """Small on/off labels that flow line by line."""
    cursor_x, cursor_y = x, y
    for label, on in items:
        text_w = _text_width(cr, label, 9)
        chip_w = text_w + 18
        if cursor_x + chip_w > x + width and cursor_x > x:
            cursor_x, cursor_y = x, cursor_y + 18
        rounded_path(cr, cursor_x, cursor_y, chip_w, 15, 7.5, 2)
        cr.set_source_rgba(*(c["ACCENT"] if on else c["SUBTEXT"]),
                           0.22 if on else 0.10)
        cr.fill()
        cr.set_source_rgba(*(c["ACCENT"] if on else c["SUBTEXT"]),
                           1.0 if on else 0.5)
        cr.arc(cursor_x + 7.5, cursor_y + 7.5, 2.6, 0, 2 * math.pi)
        cr.fill()
        _text(cr, cursor_x + 13, cursor_y + 11, label,
              c["FG"] if on else c["SUBTEXT"], 9, alpha=1.0 if on else 0.6)
        if not on:
            cr.set_source_rgba(*c["SUBTEXT"], 0.6)
            cr.set_line_width(0.8)
            cr.move_to(cursor_x + 13, cursor_y + 8)
            cr.line_to(cursor_x + 13 + text_w, cursor_y + 8)
            cr.stroke()
        cursor_x += chip_w + 5


# ----------------------------------------------------------- behavior ---
class WindowBehaviorDiagram(_SettingsArea):
    """Floating window snapping, resize on border, picture-in-picture.

    A tiled window on the left of the screen, a floating one on the right:
    with SNAP on it is snapped at SNAP_MONITOR_GAP from the edge, with the
    distance marked; with it off it is dashed and free. With RULE_PIP on, a
    video window sits in the bottom-right corner, sized by PIP_WIDTH. The
    labels below show the on/off state of the other switches.
    """

    SIZE = (320, 210)

    def _draw(self, _area, cr, width, height) -> None:
        c = _colours(self._palette())
        pad = 10.0
        screen_w = width - 2 * pad
        screen_h = min(140.0, screen_w * SCREEN_H / SCREEN_W)
        sx, sy = pad, pad
        scale = screen_w / SCREEN_W
        _screen(cr, c, sx, sy, screen_w, screen_h)
        radius = max(2.0, min(8.0, self._num("ROUNDING", 8) * scale * 3))

        # Tiled window (left half); snapping is drawn against the screen, not it.
        gap = 6.0
        _window(cr, c, sx + gap, sy + gap, screen_w * 0.45 - gap,
                screen_h - 2 * gap, radius=radius, lines=6)

        snap = self._flag("SNAP", True)
        resize = self._flag("RESIZE_ON_BORDER", True)
        pip = self._flag("RULE_PIP", True)
        float_w, float_h = screen_w * 0.30, screen_h * 0.34
        if snap:
            # The real distance is a few pixels; it is enlarged to be visible,
            # but the drawing still grows with the value.
            snap_gap = self._num("SNAP_MONITOR_GAP", 5)
            shown = max(2.0, min(24.0, snap_gap * 1.2))
            fx = sx + screen_w - shown - float_w
            fy = sy + 18
            _window(cr, c, fx, fy, float_w, float_h, active=True, radius=radius)
            # Distance line at the window's middle; its value in the caption.
            cr.set_source_rgb(*c["ACCENT2"])
            cr.set_line_width(1.4)
            mid_y = fy + float_h / 2
            cr.move_to(fx + float_w + 1, mid_y)
            cr.line_to(sx + screen_w - 1, mid_y)
            cr.stroke()
            for edge in (fx + float_w + 1, sx + screen_w - 1):
                cr.move_to(edge, mid_y - 4)
                cr.line_to(edge, mid_y + 4)
                cr.stroke()
            _text(cr, sx + screen_w - 4, fy - 5,
                  f"snaps {snap_gap:g} px from the edge", c["FG"], 9,
                  anchor="right")
        else:
            fx = sx + screen_w * 0.52
            fy = sy + 20
            _window(cr, c, fx, fy, float_w, float_h, active=True,
                    radius=radius, dashed=True)
            _text(cr, fx + float_w / 2, fy - 4, "free: does not snap",
                  c["SUBTEXT"], 9, anchor="center")

        if resize:
            # Diagonal double arrow at the bottom-left corner: grab the edge to resize.
            corner_x, corner_y = fx, fy + float_h
            cr.set_source_rgb(*c["YELLOW"])
            cr.set_line_width(1.6)
            cr.move_to(corner_x + 8, corner_y - 8)
            cr.line_to(corner_x - 6, corner_y + 6)
            cr.stroke()
            for tip, sx_, sy_ in (((corner_x - 6, corner_y + 6), 1, -1),
                                  ((corner_x + 8, corner_y - 8), -1, 1)):
                cr.move_to(*tip)
                cr.line_to(tip[0] + 5 * sx_, tip[1])
                cr.line_to(tip[0], tip[1] + 5 * sy_)
                cr.close_path()
                cr.fill()

        if pip:
            pip_w = max(24.0, min(screen_w * 0.5,
                                  self._num("PIP_WIDTH", 640) * scale))
            pip_h = pip_w * 9 / 16
            px = sx + screen_w - pip_w - 6
            py = sy + screen_h - pip_h - 6
            rounded_path(cr, px, py, pip_w, pip_h, 3, 2)
            cr.set_source_rgba(*c["BG_DARK"], 0.95)
            cr.fill()
            rounded_path(cr, px, py, pip_w, pip_h, 3, 2)
            cr.set_source_rgba(*c["ACCENT2"], 0.9)
            cr.set_line_width(1.2)
            cr.stroke()
            # play triangle
            cx, cy, r = px + pip_w / 2, py + pip_h / 2, min(pip_w, pip_h) / 5
            cr.set_source_rgb(*c["FG"])
            cr.move_to(cx - r * 0.6, cy - r)
            cr.line_to(cx + r, cy)
            cr.line_to(cx - r * 0.6, cy + r)
            cr.close_path()
            cr.fill()
            _text(cr, px - 4, py + pip_h - 2,
                  f"PiP {self._num('PIP_WIDTH', 640):g} px", c["SUBTEXT"], 8,
                  anchor="right")

        _chips(cr, c, pad, sy + screen_h + 10, width - 2 * pad, [
            ("Snap", snap),
            ("Resize on border", resize),
            ("Tools float", self._flag("RULE_FLOAT_TOOLS", True)),
            ("PiP in corner", pip),
            ("Terminal swallow", self._flag("ENABLE_SWALLOW", False)),
        ])


# ----------------------------------------------------------- ALT+Tab ----
#: (app, workspace, monitor): sample window list, in MRU order.
_SWITCHER_SAMPLE = (
    ("Firefox", 2, "DP-1"),
    ("Kitty", 1, "DP-1"),
    ("Files", 3, "HDMI"),
    ("Music", 1, "DP-1"),
)


class SwitcherDiagram(_SettingsArea):
    """What our ALT+Tab looks like: thumbnail cards or a plain list.

    Scope and sort really filter/sort the sample window list: choosing "this
    workspace only" removes cards, choosing "by workspace" changes the order.
    """

    SIZE = (320, 190)

    def _items(self) -> list[tuple[str, int, str]]:
        scope = (self._get("SWITCHER_SCOPE") or "all").strip()
        items = list(_SWITCHER_SAMPLE)
        if scope == "current":
            items = [i for i in items if i[1] == 1]
        elif scope == "monitor":
            items = [i for i in items if i[2] == "DP-1"]
        if (self._get("SWITCHER_SORT") or "recent").strip() == "workspace":
            items.sort(key=lambda i: i[1])
        return items

    def _draw(self, _area, cr, width, height) -> None:
        c = _colours(self._palette())
        pad = 10.0
        screen_w = width - 2 * pad
        screen_h = min(140.0, screen_w * SCREEN_H / SCREEN_W)
        sx, sy = pad, pad
        _screen(cr, c, sx, sy, screen_w, screen_h)
        _window(cr, c, sx + 6, sy + 6, screen_w - 12, screen_h - 12, lines=8)

        if not self._flag("SWITCHER_ENABLED", True):
            _text(cr, sx + screen_w / 2, sy + screen_h / 2 - 4,
                  "Our ALT+Tab is off", c["FG"], 11, bold=True,
                  anchor="center")
            _text(cr, sx + screen_w / 2, sy + screen_h / 2 + 12,
                  "the shortcut is left to the profile/Hyprland",
                  c["SUBTEXT"], 9, anchor="center")
            return

        # The background dims while the switcher is open.
        rounded_path(cr, sx, sy, screen_w, screen_h, 6, 2)
        cr.set_source_rgba(0, 0, 0, 0.35)
        cr.fill()

        items = self._items()
        if (self._get("WINDOW_SWITCHER") or "overlay").strip() == "menu":
            self._draw_menu(cr, c, sx, sy, screen_w, screen_h, items)
        else:
            self._draw_overlay(cr, c, sx, sy, screen_w, screen_h, items)

        scope = {"all": "all workspaces", "monitor": "this display",
                 "current": "this workspace"}.get(
            (self._get("SWITCHER_SCOPE") or "all").strip(), "all workspaces")
        sort = ("recent" if (self._get("SWITCHER_SORT") or "recent")
                .strip() != "workspace" else "by workspace")
        anim = {"popin": "popin", "slide": "slide"}.get(
            (self._get("SWITCHER_ANIM") or "none").strip(), "no animation")
        _text(cr, width / 2, sy + screen_h + 18,
              f"{len(items)} windows · {scope} · {sort} · {anim}",
              c["SUBTEXT"], 9, anchor="center")

    def _draw_overlay(self, cr, c, sx, sy, sw, sh, items) -> None:
        thumbs = self._flag("SWITCHER_THUMBS", True)
        show_ws = self._flag("SWITCHER_SHOW_WORKSPACE", True)
        # A 160..480 px card width shrinks to 38..74 px in the diagram.
        card_w = 38 + (max(160.0, min(480.0, self._num(
            "SWITCHER_THUMB_WIDTH", 260))) - 160) / 320 * 36
        card_h = card_w * 9 / 16 + 16 if thumbs else 40
        gap = 6.0
        count = max(1, len(items))
        panel_w = min(sw - 12, count * card_w + (count + 1) * gap)
        card_w = (panel_w - (count + 1) * gap) / count
        panel_h = card_h + 2 * gap
        px = sx + (sw - panel_w) / 2
        py = sy + (sh - panel_h) / 2
        rounded_path(cr, px, py, panel_w, panel_h, 8, 2)
        cr.set_source_rgba(*c["BG_DARK"], 0.95)
        cr.fill()
        accents = (c["ACCENT"], c["GREEN"], c["YELLOW"], c["ACCENT2"])
        for i, (name, ws, _mon) in enumerate(items):
            cx = px + gap + i * (card_w + gap)
            cy = py + gap
            selected = i == 0
            rounded_path(cr, cx, cy, card_w, card_h, 5, 2)
            cr.set_source_rgba(*c["SURFACE"], 1.0)
            cr.fill()
            if thumbs:
                thumb_h = card_h - 16
                rounded_path(cr, cx + 3, cy + 3, card_w - 6, thumb_h - 3, 3, 2)
                cr.set_source_rgba(*c["BG"], 1.0)
                cr.fill()
                cr.set_source_rgba(*c["SUBTEXT"], 0.4)
                for k in range(3):
                    cr.rectangle(cx + 6, cy + 7 + k * 4,
                                 (card_w - 12) * (0.8 - 0.2 * k), 1.5)
                    cr.fill()
                icon_y = cy + thumb_h - 4
                icon_r = 4.5
            else:
                icon_y = cy + 15
                icon_r = 8
            cr.set_source_rgb(*accents[_SWITCHER_SAMPLE.index(
                (name, ws, _mon)) % len(accents)])
            cr.arc(cx + card_w / 2, icon_y, icon_r, 0, 2 * math.pi)
            cr.fill()
            label = name if _text_width(cr, name, 8) < card_w - 4 else name[:4] + "…"
            _text(cr, cx + card_w / 2, cy + card_h - 4, label, c["FG"], 8,
                  anchor="center")
            if show_ws:
                rounded_path(cr, cx + card_w - 13, cy + 2, 11, 10, 3, 2)
                cr.set_source_rgba(*c["ACCENT"], 0.9)
                cr.fill()
                _text(cr, cx + card_w - 7.5, cy + 10, str(ws), c["BG_DARK"], 7,
                      bold=True, anchor="center")
            if selected:
                rounded_path(cr, cx - 1.5, cy - 1.5, card_w + 3, card_h + 3, 6, 2)
                cr.set_source_rgb(*c["ACCENT"])
                cr.set_line_width(2.0)
                cr.stroke()

    def _draw_menu(self, cr, c, sx, sy, sw, sh, items) -> None:
        show_ws = self._flag("SWITCHER_SHOW_WORKSPACE", True)
        row_h = 15.0
        box_w = sw * 0.62
        box_h = 20 + max(1, len(items)) * row_h + 6
        bx = sx + (sw - box_w) / 2
        by = sy + (sh - box_h) / 2
        rounded_path(cr, bx, by, box_w, box_h, 6, 2)
        cr.set_source_rgba(*c["BG_DARK"], 0.96)
        cr.fill()
        rounded_path(cr, bx + 5, by + 4, box_w - 10, 13, 3, 2)
        cr.set_source_rgba(*c["SURFACE"], 1.0)
        cr.fill()
        _text(cr, bx + 9, by + 14, "Window ›", c["SUBTEXT"], 8)
        for i, (name, ws, _mon) in enumerate(items):
            ry = by + 20 + i * row_h
            if i == 0:
                rounded_path(cr, bx + 4, ry, box_w - 8, row_h - 2, 3, 2)
                cr.set_source_rgba(*c["ACCENT"], 0.85)
                cr.fill()
            colour = c["BG_DARK"] if i == 0 else c["FG"]
            text = f"{name}  —  ws {ws}" if show_ws else name
            _text(cr, bx + 9, ry + 10, text, colour, 8.5)


# --------------------------------------------------------- window groups
class GroupbarDiagram(_SettingsArea):
    """Tab bar above a grouped window: style, height, font."""

    SIZE = (320, 150)

    def _draw(self, _area, cr, width, height) -> None:
        c = _colours(self._palette())
        pad = 10.0
        sw = width - 2 * pad
        sh = height - 2 * pad - 14
        sx, sy = pad, pad
        _screen(cr, c, sx, sy, sw, sh)

        enabled = self._flag("GROUPBAR", True)
        style = (self._get("GROUPBAR_STYLE") or "tabs").strip()
        bar_h = max(3.0, min(32.0, self._num("GROUPBAR_HEIGHT", 18)))
        font = max(6.0, min(16.0, self._num("GROUPBAR_FONT_SIZE", 10)))
        wx, wy = sx + 10, sy + 10
        ww, wh = sw - 20, sh - 20
        titles = ("kitty", "nvim", "btop")

        if enabled:
            tab_w = ww / len(titles)
            for i, title in enumerate(titles):
                tx = wx + i * tab_w
                active = i == 1
                colour = c["ACCENT"] if active else c["SUBTEXT"]
                if style == "tabs":
                    rounded_path(cr, tx + 1, wy, tab_w - 2, bar_h, 4, 2)
                    cr.set_source_rgba(*colour, 0.9 if active else 0.35)
                    cr.fill()
                    text_colour = c["BG_DARK"] if active else c["FG"]
                else:
                    line_h = 3.0
                    line_y = wy + bar_h - line_h if style == "line" else wy
                    cr.set_source_rgba(*colour, 1.0 if active else 0.5)
                    cr.rectangle(tx + 1, line_y, tab_w - 2, line_h)
                    cr.fill()
                    text_colour = c["FG"]
                if style != "indicator" and bar_h >= font:
                    _text(cr, tx + tab_w / 2, wy + bar_h / 2 + font / 3,
                          title, text_colour, font, bold=active,
                          anchor="center")
            body_y = wy + (bar_h if style != "indicator" else 3) + 3
        else:
            body_y = wy

        _window(cr, c, wx, body_y, ww, wy + wh - body_y, active=True, lines=5)
        if not enabled:
            _text(cr, wx + ww / 2, wy + wh / 2 + 4,
                  "no tab bar: only the border marks the group",
                  c["SUBTEXT"], 9, anchor="center")
        label = {"tabs": "filled tabs", "line": "thin line + title",
                 "indicator": "line only"}.get(style, style)
        _text(cr, width / 2, height - 6,
              (f"{label} · {bar_h:g} px · font {font:g}" if enabled
               else "off"), c["SUBTEXT"], 9, anchor="center")


# ------------------------------------------------------------- gestures --
class GestureDiagram(_SettingsArea):
    """Swiping with N fingers on the touchpad to switch workspaces."""

    SIZE = (320, 180)

    def _draw(self, _area, cr, width, height) -> None:
        c = _colours(self._palette())
        enabled = self._flag("GESTURE_SWIPE", True)
        fingers = int(self._num("GESTURE_FINGERS", 3))
        distance = self._num("SWIPE_DISTANCE", 300)
        cancel = max(0.0, min(1.0, self._num("SWIPE_CANCEL_RATIO", 0.5)))
        create_new = self._flag("SWIPE_CREATE_NEW", True)
        alpha = 1.0 if enabled else 0.35

        # Workspace strip: moving from workspace 2 to 3, up to the cancel threshold.
        strip_y, strip_h = 12.0, 46.0
        count = 4 if create_new else 3
        cell_w = (width - 24 - (count - 1) * 6) / count
        for i in range(count):
            x = 12 + i * (cell_w + 6)
            new = create_new and i == count - 1
            rounded_path(cr, x, strip_y, cell_w, strip_h, 5, 2)
            if new:
                cr.set_source_rgba(*c["SUBTEXT"], 0.6 * alpha)
                cr.set_line_width(1.0)
                cr.set_dash([3, 2])
                cr.stroke()
                cr.set_dash([])
                _text(cr, x + cell_w / 2, strip_y + strip_h / 2 + 5, "+",
                      c["SUBTEXT"], 14, anchor="center", alpha=alpha)
                continue
            cr.set_source(_linear(cr, x, strip_y, x + cell_w, strip_y + strip_h,
                                  c["BG"], c["BG_DARK"]))
            cr.fill()
            current = i == 1
            rounded_path(cr, x, strip_y, cell_w, strip_h, 5, 2)
            cr.set_source_rgba(*(c["ACCENT"] if current else c["SUBTEXT"]),
                               (1.0 if current else 0.35) * alpha)
            cr.set_line_width(1.6 if current else 1.0)
            cr.stroke()
            _text(cr, x + cell_w / 2, strip_y + strip_h / 2 + 4, str(i + 1),
                  c["FG"], 11, bold=current, anchor="center", alpha=alpha)
        if create_new:
            _text(cr, width - 12, strip_y + strip_h + 11,
                  "new workspace at the end", c["SUBTEXT"], 8, anchor="right",
                  alpha=alpha)

        # Touchpad + fingers.
        pad_x, pad_y, pad_w, pad_h = 12.0, 82.0, 120.0, 72.0
        rounded_path(cr, pad_x, pad_y, pad_w, pad_h, 8, 2)
        cr.set_source_rgba(*c["SURFACE"], alpha)
        cr.fill()
        spread = 14.0
        start = pad_x + pad_w / 2 - (fingers - 1) * spread / 2
        for k in range(fingers):
            fx = start + k * spread
            fy = pad_y + pad_h / 2 - (4 if k in (1, fingers - 2) else 0)
            cr.set_source_rgba(*c["ACCENT"], 0.85 * alpha)
            cr.arc(fx, fy, 5.0, 0, 2 * math.pi)
            cr.fill()
        cr.set_source_rgba(*c["ACCENT2"], alpha)
        cr.set_line_width(1.8)
        arrow_y = pad_y + pad_h - 12
        cr.move_to(pad_x + pad_w - 28, arrow_y)
        cr.line_to(pad_x + 28, arrow_y)
        cr.stroke()
        _arrow_head(cr, pad_x + 28, arrow_y, -1, 0)
        _text(cr, pad_x + pad_w / 2, pad_y + pad_h + 12,
              f"{fingers}-finger swipe left", c["FG"], 9, anchor="center",
              alpha=alpha)

        # Swipe distance and cancel threshold.
        right_x = pad_x + pad_w + 16
        track_w = width - right_x - 12
        track_y = pad_y + 22
        cr.set_source_rgba(*c["SURFACE"], alpha)
        rounded_path(cr, right_x, track_y, track_w, 8, 4, 2)
        cr.fill()
        cr.set_source_rgba(*c["ACCENT"], 0.85 * alpha)
        rounded_path(cr, right_x, track_y, track_w * cancel, 8, 4, 2)
        cr.fill()
        mark_x = right_x + track_w * cancel
        cr.set_source_rgba(*c["YELLOW"], alpha)
        cr.set_line_width(1.6)
        cr.move_to(mark_x, track_y - 4)
        cr.line_to(mark_x, track_y + 12)
        cr.stroke()
        _text(cr, right_x, track_y - 8, f"full swipe: {distance:g} px",
              c["FG"], 9, alpha=alpha)
        _text(cr, right_x, track_y + 24,
              f"release before {cancel * 100:.0f}% to snap back",
              c["SUBTEXT"], 8.5, alpha=alpha)
        lock = self._flag("SWIPE_DIRECTION_LOCK", True)
        _text(cr, right_x, track_y + 38,
              "direction lock on" if lock else "direction lock off",
              c["SUBTEXT"], 8.5, alpha=alpha)
        if not enabled:
            label_w = _text_width(cr, "gestures off", 10, True) + 20
            rounded_path(cr, (width - label_w) / 2, strip_y + strip_h / 2 - 10,
                         label_w, 20, 10, 2)
            cr.set_source_rgba(*c["BG_DARK"], 0.95)
            cr.fill()
            _text(cr, width / 2, strip_y + strip_h / 2 + 4, "gestures off",
                  c["RED"], 10, bold=True, anchor="center")


# ---------------------------------------------------------------- plugins -
class PluginsDiagram(_SettingsArea):
    """hyprexpo grid (column count) and hyprbars title bar."""

    SIZE = (320, 150)

    def _draw(self, _area, cr, width, height) -> None:
        c = _colours(self._palette())
        cols = int(max(1, min(6, self._num("HYPREXPO_COLUMNS", 3))))
        # hyprexpo: a columns × columns grid.
        gx, gy, gw = 10.0, 22.0, 140.0
        gh = gw * SCREEN_H / SCREEN_W
        _screen(cr, c, gx, gy, gw, gh)
        cell_gap = 3.0
        cw = (gw - (cols + 1) * cell_gap) / cols
        ch = (gh - (cols + 1) * cell_gap) / cols
        for row in range(cols):
            for col in range(cols):
                x = gx + cell_gap + col * (cw + cell_gap)
                y = gy + cell_gap + row * (ch + cell_gap)
                current = row == 0 and col == 0
                rounded_path(cr, x, y, cw, ch, 2, 2)
                cr.set_source_rgba(*c["SURFACE"], 0.9)
                cr.fill()
                if current:
                    rounded_path(cr, x, y, cw, ch, 2, 2)
                    cr.set_source_rgb(*c["ACCENT"])
                    cr.set_line_width(1.4)
                    cr.stroke()
        _text(cr, gx, 14, f"hyprexpo · {cols} columns", c["FG"], 9, bold=True)

        # hyprbars: window with a title bar.
        bx, by = gx + gw + 16, 22.0
        bw, bh = width - bx - 10, gh
        title_h = max(8.0, min(40.0, self._num("HYPRBARS_HEIGHT", 26) * 0.6))
        rounded_path(cr, bx, by, bw, bh, 4, 2)
        cr.set_source_rgba(*c["SURFACE"], 1.0)
        cr.fill()
        cr.save()
        rounded_path(cr, bx, by, bw, bh, 4, 2)
        cr.clip()
        cr.set_source_rgba(*c["BG_DARK"], 1.0)
        cr.rectangle(bx, by, bw, title_h)
        cr.fill()
        cr.restore()
        _text(cr, bx + 6, by + title_h / 2 + 3, "kitty", c["FG"], 8)
        if self._flag("HYPRBARS_BUTTONS", True):
            for k, colour in enumerate((c["RED"], c["YELLOW"], c["GREEN"])):
                cr.set_source_rgb(*colour)
                cr.arc(bx + bw - 8 - k * 10, by + title_h / 2, 3.2, 0,
                       2 * math.pi)
                cr.fill()
        _text(cr, bx, 14,
              f"hyprbars · {self._num('HYPRBARS_HEIGHT', 26):g} px",
              c["FG"], 9, bold=True)
        _text(cr, width / 2, height - 6,
              "install plugins from the Components page", c["SUBTEXT"], 8.5,
              anchor="center")
