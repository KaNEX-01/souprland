"""Boot animation (Plymouth) preview, using the theme's own images.

Running Plymouth needs root and takes over the screen; instead
``login.plymouth_scene`` describes what the theme draws as data, and here it
is drawn with cairo scaled down into a 16:9 area. For two-step themes (bgrt,
spinner, cachyos…) the real frames play at their real positions; themes
without images (details, text, tribar) imitate what the screen looks like.

At boot, images are drawn at their natural pixel size, so a 32-pixel spinner
is a tiny part of a 1920-wide screen. The preview keeps the same ratio; only
animations that would vanish into a few pixels are enlarged to at least
``MIN_FRAME`` or 8% of the preview width, so you can tell what they are.
"""

from __future__ import annotations

import math
import random

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from .. import login  # noqa: E402

REFERENCE_WIDTH = 1920
FPS = 30
MIN_FRAME = 14

_KERNEL_LINES = (
    "[  OK  ] Mounted /boot.",
    "[  OK  ] Started Load Kernel Modules.",
    "[  OK  ] Reached target Local File Systems.",
    "[  OK  ] Started Network Manager.",
    "[  OK  ] Started Bluetooth service.",
    "[  OK  ] Reached target Graphical Interface.",
    "         Starting Hold until boot process finishes up...",
    "[  OK  ] Started User Login Management.",
)

#: The same file is needed by several cards (bgrt + cachyos use the same
#: spinner) and on every redraw; it is read once.
_PIXBUFS: dict[str, GdkPixbuf.Pixbuf | None] = {}


def _pixbuf(path) -> GdkPixbuf.Pixbuf | None:
    key = str(path)
    if key not in _PIXBUFS:
        try:
            _PIXBUFS[key] = GdkPixbuf.Pixbuf.new_from_file(key)
        except GLib.Error:
            _PIXBUFS[key] = None
    return _PIXBUFS[key]


def _rgb(hex_color: str) -> tuple[float, float, float]:
    rgba = Gdk.RGBA()
    if not rgba.parse(hex_color):
        rgba.parse("#000000")
    return rgba.red, rgba.green, rgba.blue


class PlymouthPreview(Gtk.DrawingArea):
    """A theme's scaled-down, animated boot screen."""

    def __init__(self, scene: login.PlymouthScene, width: int = 256,
                 animate: bool = True) -> None:
        super().__init__()
        self.scene = scene
        self.set_content_width(width)
        self.set_content_height(round(width * 9 / 16))
        self.add_css_class("card")
        self.set_overflow(Gtk.Overflow.HIDDEN)
        self._t = 0.0
        self._start: int | None = None
        self._tick: int | None = None
        rng = random.Random(scene.theme)
        self._stars = [(rng.random(), rng.random(), rng.random() * math.tau)
                       for _ in range(14)]
        self._name = login.distro_name()
        self.set_draw_func(self._draw)
        # When not animating, show the middle frame: the one that best
        # conveys what the animation is.
        self._still = scene.still
        self.set_animating(animate)

    # ------------------------------------------------------------ animation
    def set_animating(self, on: bool) -> None:
        if on and self._tick is None:
            self._start = None
            self._tick = self.add_tick_callback(self._on_tick)
        elif not on and self._tick is not None:
            self.remove_tick_callback(self._tick)
            self._tick = None
            self._t = 0.0
            self.queue_draw()

    def _on_tick(self, _widget, clock) -> bool:
        now = clock.get_frame_time()
        if self._start is None:
            self._start = now
        t = (now - self._start) / 1_000_000
        # FPS frames per second is enough; drawing on every refresh is wasted work.
        if int(t * FPS) != int(self._t * FPS):
            self.queue_draw()
        self._t = t
        return GLib.SOURCE_CONTINUE

    # -------------------------------------------------------------- drawing
    def _image(self, cr, path, h_align: float, v_align: float, w: int, h: int,
               scale: float, alpha: float = 1.0, minimum: int = 0) -> None:
        pix = _pixbuf(path)
        if pix is None:
            return
        s = scale
        if minimum and pix.get_width() * s < minimum:
            s = minimum / pix.get_width()
        iw, ih = pix.get_width() * s, pix.get_height() * s
        x = h_align * (w - iw)
        y = v_align * (h - ih)
        self._paint(cr, pix, x, y, s, alpha)

    @staticmethod
    def _paint(cr, pix, x: float, y: float, s: float, alpha: float = 1.0) -> None:
        cr.save()
        cr.translate(x, y)
        cr.scale(s, s)
        Gdk.cairo_set_source_pixbuf(cr, pix, 0, 0)
        if alpha >= 0.999:
            cr.paint()
        else:
            cr.paint_with_alpha(max(0.0, alpha))
        cr.restore()

    def _background(self, cr, w: int, h: int) -> None:
        import cairo
        grad = cairo.LinearGradient(0, 0, 0, h)
        grad.add_color_stop_rgb(0, *_rgb(self.scene.bg_top))
        grad.add_color_stop_rgb(1, *_rgb(self.scene.bg_bottom))
        cr.set_source(grad)
        cr.paint()

    def _draw(self, _area, cr, w: int, h: int) -> None:
        scene = self.scene
        scale = w / REFERENCE_WIDTH
        self._background(cr, w, h)
        animating = self._tick is not None
        t = self._t

        if scene.kind == "two-step":
            if scene.firmware is not None:
                pix = _pixbuf(scene.firmware)
                fx, fy, fw = scene.firmware_box
                if pix is not None and fw > 0:
                    s = fw * w / pix.get_width()
                    self._paint(cr, pix, fx * w, fy * h, s)
            if scene.watermark is not None:
                self._image(cr, scene.watermark, *scene.watermark_align, w, h, scale)
            if scene.frames:
                index = int(t * FPS) % len(scene.frames) if animating else self._still
                self._image(cr, scene.frames[index], *scene.frames_align, w, h,
                            scale, minimum=max(MIN_FRAME, round(w * 0.08)))
        elif scene.kind == "fade-in":
            if scene.star is not None:
                for sx, sy, phase in self._stars:
                    alpha = (math.sin(t * 2 + phase) + 1) / 2 if animating else 0.7
                    self._image(cr, scene.star, sx, sy, w, h, scale, alpha, minimum=4)
            if scene.logo is not None:
                alpha = (math.sin(t * 1.2) + 1) / 2 if animating else 1.0
                self._image(cr, scene.logo, 0.5, 0.5, w, h, scale, alpha)
        elif scene.kind == "solar":
            if scene.star is not None:
                pulse = 1 + 0.04 * math.sin(t * 3) if animating else 1
                self._image(cr, scene.star, 1.0, 0.5, w, h, scale * pulse)
            self._bar(cr, w, h, (t * 0.15) % 1 if animating else 0.6,
                      (0.55, 0.75, 1.0), y_frac=0.9, width_frac=0.25)
        elif scene.kind == "script":
            if scene.logo is not None:
                alpha = 0.3 + 0.7 * (math.cos(t * math.pi) + 1) / 2 if animating else 1.0
                self._image(cr, scene.logo, 0.5, 0.5, w, h, scale, alpha)
        elif scene.kind == "details":
            self._details(cr, w, h, t if animating else 3.0)
        elif scene.kind == "text":
            self._text_mode(cr, w, h, t if animating else 1.0)
        elif scene.kind == "tribar":
            self._text(cr, self._name, w / 2, h * 0.45, h * 0.07, (0.85, 0.85, 0.85), center=True)
            progress = (t * 0.2) % 1 if animating else 0.6
            third = progress * 3
            for i, color in enumerate(((0.2, 0.4, 0.9), (0.9, 0.9, 0.9), (0.9, 0.3, 0.2))):
                part = min(max(third - i, 0), 1)
                if part:
                    cr.set_source_rgb(*color)
                    cr.rectangle(w * 0.2 + i * w * 0.2, h * 0.9, w * 0.2 * part, max(2, h * 0.02))
                    cr.fill()

    def _bar(self, cr, w, h, progress, color, y_frac, width_frac) -> None:
        bw, bh = w * width_frac, max(2, h * 0.015)
        x, y = (w - bw) / 2, h * y_frac
        cr.set_source_rgba(1, 1, 1, 0.15)
        cr.rectangle(x, y, bw, bh)
        cr.fill()
        cr.set_source_rgb(*color)
        cr.rectangle(x, y, bw * progress, bh)
        cr.fill()

    @staticmethod
    def _text(cr, text, x, y, size, color, center=False, mono=False) -> None:
        cr.select_font_face("monospace" if mono else "sans")
        cr.set_font_size(max(4.0, size))
        if center:
            ext = cr.text_extents(text)
            x -= ext.width / 2 + ext.x_bearing
        cr.set_source_rgb(*color)
        cr.move_to(x, y)
        cr.show_text(text)

    def _details(self, cr, w, h, t) -> None:
        size = max(4.0, h * 0.045)
        shown = min(len(_KERNEL_LINES), int(t * 2.5) % (len(_KERNEL_LINES) + 4))
        for i, line in enumerate(_KERNEL_LINES[:shown]):
            ok = line.startswith("[  OK  ]")
            y = size * 1.5 * (i + 1)
            if ok:
                self._text(cr, "[", size * 0.6, y, size, (0.8, 0.8, 0.8), mono=True)
                self._text(cr, "  OK  ", size * 0.6 + cr.text_extents("[").x_advance, y,
                           size, (0.3, 0.85, 0.3), mono=True)
                self._text(cr, line[1:].replace("  OK  ]", "]", 1), size * 0.6
                           + cr.text_extents("[  OK  ").x_advance, y, size, (0.8, 0.8, 0.8), mono=True)
            else:
                self._text(cr, line, size * 0.6, y, size, (0.8, 0.8, 0.8), mono=True)

    def _text_mode(self, cr, w, h, t) -> None:
        self._text(cr, self._name, w / 2, h * 0.45, h * 0.07, (0.85, 0.85, 0.85), center=True)
        lit = int(t * 2) % 3
        box = h * 0.05
        for i in range(3):
            x = w / 2 + (i - 1) * box * 2 - box / 2
            cr.set_source_rgb(*((0.4, 0.6, 1.0) if i == lit else (0.35, 0.35, 0.35)))
            cr.rectangle(x, h * 0.6, box, box)
            cr.fill()
