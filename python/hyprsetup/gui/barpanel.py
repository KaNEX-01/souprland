"""Bar detail panel: the small panel that opens below a bar item when clicked.

In Waybar, left-clicking volume, network, bluetooth, battery, brightness or the
clock used to open separate apps (pavucontrol, nmtui in a terminal, blueman).
As in most profiles, a panel in the theme's colors now opens right below the
bar:

    Sound       output and microphone sliders, mute, output device
    Network     Wi-Fi on/off, connections, nearby networks (click → connect)
    Bluetooth   on/off, paired devices (click → connect/disconnect)
    Battery     percentage, state, time remaining, power mode
    Brightness  display brightness slider
    Calendar    today's date and the month calendar
    Media       cover, title/artist/album, seekable progress, previous/
                play/next, shuffle/repeat, player volume, player choice

The Battery and Brightness tabs only show if that hardware exists. Right/middle
click still opens the old apps (see templates/waybar/config.jsonc.tmpl).

Opening: ``hypr/scripts/barpanel.py <tab>`` (a template that passes the colors
in VALUES) imports this module in the same process and calls ``run_with``.

Closing: Esc, clicking outside the panel (there is a transparent
screen-covering catcher layer behind the panel) or clicking the same item
again. Clicking another item while the panel is open does not start a new
process; the open panel switches to that tab (SIGUSR1 + request file).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import textwrap
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("Graphene", "1.0")

from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Graphene, Gtk  # noqa: E402
from gi.repository import Gtk4LayerShell as Layer  # noqa: E402

NAMESPACE = "hyprsetup-panel"
_RUN = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp")
_PID = _RUN / "hyprsetup-barpanel.pid"
_REQUEST = _RUN / "hyprsetup-barpanel.request"

TABS = (
    ("ses", "Sound", "audio-volume-high-symbolic"),
    ("ag", "Network", "network-wireless-symbolic"),
    ("bluetooth", "Bluetooth", "bluetooth-symbolic"),
    ("sistem", "System", "utilities-system-monitor-symbolic"),
    ("pil", "Battery", "battery-good-symbolic"),
    ("parlaklik", "Brightness", "display-brightness-symbolic"),
    ("takvim", "Calendar", "x-office-calendar-symbolic"),
    ("medya", "Media", "audio-x-generic-symbolic"),
    ("kayit", "Recording", "media-record-symbolic"),
    ("bildirim", "Notifications", "preferences-system-notifications-symbolic"),
)
#: Script that keeps the notification history (hypr/scripts/notifylog.py).
NOTIFYLOG = Path.home() / ".config/hypr/scripts/notifylog.py"
WIDTH = 380
#: Open/close slide (s): the card slides out of the bar edge like a drawer.
SLIDE = 0.22
#: Tab → the Waybar modules that open it. If the module sits in the bar's
#: CENTER group the panel opens in the middle of the screen (the center group
#: is always centred); otherwise at the click, but later clicks on the same
#: item "stick" to the first spot (see Panel._anchor_x): the panel always
#: opens in the same place for each item.
TAB_MODULES = {
    "medya": ("custom/media", "custom/media-prev", "custom/media-play",
              "custom/media-next", "mpris"),
    "ses": ("pulseaudio", "custom/mic"),
    "ag": ("network",),
    "bluetooth": ("bluetooth",),
    "sistem": ("cpu", "memory", "temperature", "disk"),
    "pil": ("battery",),
    "parlaklik": ("backlight",),
    "takvim": ("clock",),
    "bildirim": ("custom/notifications",),
    "kayit": ("custom/record",),
}
#: Snap radius (px) to an item's remembered position.
ANCHOR_SNAP = 90
_ANCHORS = _RUN / "hyprsetup-barpanel.anchors.json"
_WAYBAR_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") \
    / "waybar" / "config.jsonc"


def _center_modules() -> set[str]:
    """Union of every "modules-center" list in the Waybar config."""
    try:
        text = _WAYBAR_CONFIG.read_text(encoding="utf-8")
    except OSError:
        return set()
    found: set[str] = set()
    for block in re.findall(r'"modules-center"\s*:\s*\[([^\]]*)\]', text):
        found.update(re.findall(r'"([^"]+)"', block))
    return found


class _SlideBin(Gtk.Widget):
    """Single-child container that draws its child shifted and faded.

    The open slide used to reload the WHOLE display's CSS on every frame
    (translateY + opacity written into a CssProvider): each frame meant a
    full style recalculation and the slide stuttered. Here the transform is
    applied only at draw time; measuring and layout stay the child's own.
    """

    def __init__(self, child: Gtk.Widget) -> None:
        super().__init__()
        self.child = child
        self.offset = 0.0
        self.alpha = 1.0
        child.set_parent(self)

    def set_slide(self, offset: float, alpha: float) -> None:
        self.offset, self.alpha = offset, alpha
        self.queue_draw()

    def do_measure(self, orientation, for_size):
        return self.child.measure(orientation, for_size)

    def do_size_allocate(self, width: int, height: int, baseline: int) -> None:
        self.child.allocate(width, height, baseline, None)

    def do_snapshot(self, snapshot) -> None:
        snapshot.save()
        snapshot.translate(Graphene.Point().init(0, self.offset))
        snapshot.push_opacity(self.alpha)
        self.snapshot_child(self.child, snapshot)
        snapshot.pop()
        snapshot.restore()

    def do_dispose(self) -> None:
        if self.child is not None:
            self.child.unparent()
            self.child = None


# ------------------------------------------------------------ helpers -----
def _out(*argv: str, timeout: float = 4) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout, check=False).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _bg(*argv: str) -> None:
    """Run a command without blocking the UI."""
    try:
        subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        pass


def _later(work, done) -> None:
    """Slow command (nmcli scan, bluetoothctl) in the background; result on the main loop."""
    def run() -> None:
        result = work()
        GLib.idle_add(lambda: (done(result), False)[1])
    threading.Thread(target=run, daemon=True).start()


def has_battery() -> bool:
    return any(Path("/sys/class/power_supply").glob("BAT*"))


def has_backlight() -> bool:
    base = Path("/sys/class/backlight")
    return base.is_dir() and any(base.iterdir())


#: External displays found by ddcutil; detection takes seconds, so it is
#: cached and rescanned when the set of connected displays changes.
DDC_CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") \
    / "hyprsetup" / "ddc.json"


def has_ddc() -> bool:
    return shutil.which("ddcutil") is not None and any(Path("/dev").glob("i2c-*"))


def _monitor_names() -> list[str]:
    try:
        return sorted(m["name"] for m in json.loads(_out("hyprctl", "monitors", "-j") or "[]"))
    except (ValueError, KeyError, TypeError):
        return []


def _ddc_brightness(bus: str) -> tuple[int, int] | None:
    """(current, max) brightness; None if the display does not support DDC/CI."""
    match = re.search(r"VCP 10 C (\d+) (\d+)",
                      _out("ddcutil", "--bus", bus, "getvcp", "10", "--brief", timeout=20))
    return (int(match.group(1)), int(match.group(2)) or 100) if match else None


def ddc_displays(rescan: bool = False) -> list[dict]:
    """[{name, bus, model, max}]; max=0: the display does not expose brightness via DDC/CI.

    Slow (a few s per display); call it from a background thread.
    """
    names = _monitor_names()
    if not rescan:
        try:
            cached = json.loads(DDC_CACHE.read_text(encoding="utf-8"))
            if cached.get("monitors") == names:
                return cached["displays"]
        except (OSError, ValueError, KeyError):
            pass
    displays: list[dict] = []
    current: dict = {}
    for line in _out("ddcutil", "detect", "--brief", timeout=40).splitlines():
        line = line.strip()
        if line.startswith("Display ") or line == "Invalid display":
            # "Invalid display": the display is connected but DDC/CI does not respond.
            current = {"invalid": line == "Invalid display"}
            displays.append(current)
        elif line.startswith("I2C bus:"):
            current["bus"] = line.rsplit("-", 1)[-1]
        elif line.startswith("DRM connector:"):
            current["name"] = line.split(":", 1)[1].strip().split("-", 1)[-1]
        elif line.startswith("Monitor:"):
            parts = line.split(":", 1)[1].strip().split(":")
            current["model"] = parts[1] if len(parts) > 1 else parts[0]
    displays = [d for d in displays if d.get("bus")]
    for display in displays:
        value = None if display.pop("invalid", False) else _ddc_brightness(display["bus"])
        display["max"] = value[1] if value else 0
        display.setdefault("name", f"i2c-{display['bus']}")
        display.setdefault("model", display["name"])
    try:
        DDC_CACHE.parent.mkdir(parents=True, exist_ok=True)
        DDC_CACHE.write_text(json.dumps({"monitors": names, "displays": displays}),
                             encoding="utf-8")
    except OSError:
        pass
    return displays


class _DdcWriter:
    """Does not run ddcutil on every step while the slider is dragged: one
    thread per bus writes the latest requested value (older steps are skipped)."""

    def __init__(self, bus: str) -> None:
        self.bus = bus
        self.pending: int | None = None
        self.lock = threading.Lock()
        self.busy = False

    def set(self, value: int) -> None:
        with self.lock:
            self.pending = value
            if self.busy:
                return
            self.busy = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        while True:
            with self.lock:
                value, self.pending = self.pending, None
                if value is None:
                    self.busy = False
                    return
            _out("ddcutil", "--bus", self.bus, "--noverify", "setvcp", "10",
                 str(value), timeout=20)


#: Character limit for the dim description lines (based on the panel width).
_FOLD_WIDTH = 50


def _fold(text: str) -> str:
    """Split a long description into lines (each paragraph separately)."""
    return "\n".join(textwrap.fill(part, _FOLD_WIDTH) if part else ""
                     for part in (text or "").split("\n"))


def _volume(target: str) -> tuple[float, bool]:
    text = _out("wpctl", "get-volume", target)
    match = re.search(r"([\d.]+)", text)
    return (float(match.group(1)) if match else 0.0), "MUTED" in text


# --------------------------------------------------------------- panel ----
class Panel:
    def __init__(self, app: Gtk.Application, values: dict[str, str], tab: str) -> None:
        self.app = app
        self.values = values
        self.tab = tab
        self.windows: list[Gtk.Window] = []
        self.refreshers: dict[str, callable] = {}
        self._css()
        # Settings → Session → Desktop tools (empty = script generated by an old version: on).
        self.ddc = values.get("BRIGHTNESS_DDC", "true") != "false" and has_ddc()
        tabs = [t for t in TABS
                if (t[0] != "pil" or has_battery())
                and (t[0] != "parlaklik" or has_backlight() or self.ddc)
                and (t[0] != "bildirim" or (NOTIFYLOG.is_file()
                                            and values.get("NOTIFY_HISTORY", "true") != "false"))]
        if tab not in {t[0] for t in tabs}:
            self.tab = tabs[0][0]
        self._catcher()
        self._build(tabs)
        GLib.timeout_add(2000, self._tick)
        # The player's progress bar should advance once per second.
        GLib.timeout_add(1000, self._media_tick)

    # ---- appearance
    def _css(self) -> None:
        v = self.values
        radius = min(18, max(4, int(float(v.get("ROUNDING") or 12))))
        css = f"""
        window.hs-panel-catcher {{ background: transparent; }}
        window.hs-panel {{ background: transparent; }}
        .hs-card {{
            background: alpha({v.get('HEX_BG_DARK', '#11111b')}, 0.985);
            color: {v.get('HEX_FG', '#cdd6f4')};
            border: 1px solid alpha({v.get('HEX_ACCENT', '#89b4fa')}, 0.45);
            border-radius: {radius}px;
            padding: 12px;
            font-family: "{v.get('FONT_FAMILY', 'sans')}";
        }}
        .hs-card label {{ color: {v.get('HEX_FG', '#cdd6f4')}; }}
        .hs-card .dim {{ color: {v.get('HEX_SUBTEXT', '#a6adc8')}; font-size: 0.9em; }}
        .hs-card .big {{ font-size: 1.6em; font-weight: 700; }}
        .hs-card .section {{
            color: {v.get('HEX_ACCENT', '#89b4fa')};
            font-size: 0.8em; font-weight: 700; letter-spacing: 1px;
            margin-top: 6px;
        }}
        .hs-tabs button {{
            background: alpha({v.get('HEX_SURFACE', '#313244')}, 0.6);
            color: {v.get('HEX_FG', '#cdd6f4')};
            border-radius: {max(4, radius - 6)}px;
            padding: 4px 5px; min-width: 0; border: none; box-shadow: none;
        }}
        .hs-tabs button:checked,
        .hs-tabs button:checked label,
        .hs-tabs button:checked image {{
            background: {v.get('HEX_ACCENT', '#89b4fa')};
            color: {v.get('HEX_BG_DARK', '#11111b')};
        }}
        .hs-card .row {{
            background: alpha({v.get('HEX_SURFACE', '#313244')}, 0.55);
            border-radius: {max(4, radius - 6)}px;
            padding: 8px 10px;
        }}
        .hs-card .row:hover {{ background: alpha({v.get('HEX_SURFACE', '#313244')}, 0.9); }}
        .hs-card .row.active {{
            box-shadow: inset 0 0 0 1px {v.get('HEX_ACCENT', '#89b4fa')};
        }}
        .hs-card button.flat-row {{
            background: none; border: none; box-shadow: none; padding: 0;
        }}
        .hs-card scale trough {{
            background: alpha({v.get('HEX_SURFACE', '#313244')}, 0.9);
            min-height: 6px; border-radius: 999px;
        }}
        .hs-card scale highlight {{
            background: {v.get('HEX_ACCENT', '#89b4fa')}; border-radius: 999px;
        }}
        .hs-card scale slider {{
            background: {v.get('HEX_FG', '#cdd6f4')}; min-width: 14px; min-height: 14px;
            margin: -4px 0;
            border-radius: 999px; box-shadow: none; border: none;
        }}
        .hs-card switch:checked {{ background: {v.get('HEX_ACCENT', '#89b4fa')}; }}
        .hs-card button.text {{
            background: alpha({v.get('HEX_SURFACE', '#313244')}, 0.7);
            color: {v.get('HEX_FG', '#cdd6f4')}; border: none; box-shadow: none;
            border-radius: {max(4, radius - 6)}px; padding: 4px 10px;
        }}
        .hs-card button.text:checked, .hs-card button.text.on,
        .hs-card button.text.on image {{
            background: {v.get('HEX_ACCENT', '#89b4fa')};
            color: {v.get('HEX_BG_DARK', '#11111b')};
        }}
        .hs-card calendar {{
            background: transparent; color: {v.get('HEX_FG', '#cdd6f4')};
            border: none;
        }}
        .hs-card calendar > grid > label.today {{
            background: {v.get('HEX_ACCENT', '#89b4fa')};
            color: {v.get('HEX_BG_DARK', '#11111b')}; border-radius: 999px;
        }}
        .hs-card levelbar trough {{
            background: alpha({v.get('HEX_SURFACE', '#313244')}, 0.9);
            border-radius: 999px; min-height: 6px; min-width: 6px; border: none;
        }}
        .hs-card levelbar block.filled {{
            background: {v.get('HEX_ACCENT', '#89b4fa')}; border-radius: 999px;
        }}
        .hs-card levelbar block.empty {{ background: transparent; }}
        .hs-card .cores levelbar trough {{ border-radius: 3px; min-width: 4px; }}
        .hs-card .cores levelbar block.filled {{ border-radius: 3px; }}
        .hs-card .value {{ color: {v.get('HEX_ACCENT', '#89b4fa')}; font-weight: 700; }}
        .hs-card .cover {{
            border-radius: {max(4, radius - 4)}px;
            background: alpha({v.get('HEX_SURFACE', '#313244')}, 0.9);
        }}
        .hs-card .media-title {{ font-size: 1.15em; font-weight: 700; }}
        .hs-card .tnum {{ font-feature-settings: "tnum"; }}
        .hs-card button.media {{ transition: background 160ms ease-out, color 160ms ease-out; }}
        .hs-card button.media:active {{
            background: alpha({v.get('HEX_ACCENT', '#89b4fa')}, 0.35);
        }}
        .hs-card button.media.main:active {{
            background: alpha({v.get('HEX_ACCENT', '#89b4fa')}, 0.7);
        }}
        .hs-card button.media {{
            background: alpha({v.get('HEX_SURFACE', '#313244')}, 0.7);
            color: {v.get('HEX_FG', '#cdd6f4')}; border: none; box-shadow: none;
            border-radius: 999px; min-width: 34px; min-height: 34px; padding: 0;
        }}
        .hs-card button.media.main {{
            background: {v.get('HEX_ACCENT', '#89b4fa')};
            color: {v.get('HEX_BG_DARK', '#11111b')};
            min-width: 44px; min-height: 44px;
        }}
        .hs-card button.media:disabled {{ opacity: 0.35; }}
        .hs-card button.media.on {{
            color: {v.get('HEX_ACCENT', '#89b4fa')};
            box-shadow: inset 0 0 0 1px {v.get('HEX_ACCENT', '#89b4fa')};
        }}
        .hs-card entry {{
            background: alpha({v.get('HEX_SURFACE', '#313244')}, 0.9);
            color: {v.get('HEX_FG', '#cdd6f4')};
        }}
        """
        provider = Gtk.CssProvider()
        provider.load_from_string(css)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _layer(self, window: Gtk.Window, keyboard: bool) -> None:
        Layer.init_for_window(window)
        Layer.set_namespace(window, NAMESPACE)
        Layer.set_layer(window, Layer.Layer.TOP)
        Layer.set_exclusive_zone(window, -1)
        Layer.set_keyboard_mode(window, Layer.KeyboardMode.ON_DEMAND if keyboard
                                else Layer.KeyboardMode.NONE)
        monitor = self._monitor()
        if monitor is not None:
            Layer.set_monitor(window, monitor)

    def _monitor(self):
        info = json.loads(_out("hyprctl", "-j", "monitors") or "[]")
        name = next((m["name"] for m in info if m.get("focused")), "")
        monitors = Gdk.Display.get_default().get_monitors()
        for i in range(monitors.get_n_items()):
            item = monitors.get_item(i)
            if item.get_connector() == name:
                return item
        return None

    def _catcher(self) -> None:
        """Transparent screen-covering layer that catches clicks outside the panel."""
        window = Gtk.Window(application=self.app)
        window.add_css_class("hs-panel-catcher")
        self._layer(window, keyboard=False)
        for edge in (Layer.Edge.TOP, Layer.Edge.BOTTOM, Layer.Edge.LEFT, Layer.Edge.RIGHT):
            Layer.set_anchor(window, edge, True)
        area = Gtk.Box(hexpand=True, vexpand=True)
        click = Gtk.GestureClick(button=0)
        click.connect("pressed", lambda *_a: self.close())
        area.add_controller(click)
        window.set_child(area)
        window.present()
        self.windows.append(window)

    def _place(self, window: Gtk.Window) -> None:
        """The panel sits at the bar edge, below the clicked spot (cursor x)."""
        bottom = self.values.get("BAR_POSITION", "top") == "bottom"
        edge = Layer.Edge.BOTTOM if bottom else Layer.Edge.TOP
        Layer.set_anchor(window, edge, True)
        Layer.set_anchor(window, Layer.Edge.LEFT, True)
        try:
            bar = int(float(self.values.get("BAR_HEIGHT") or 32))
            margin = int(float(self.values.get("BAR_MARGIN") or 0))
        except ValueError:
            bar, margin = 32, 0
        Layer.set_margin(window, edge, bar + margin * 2 + 6)
        info = json.loads(_out("hyprctl", "-j", "monitors") or "[]")
        mon = next((m for m in info if m.get("focused")), None)
        cursor = json.loads(_out("hyprctl", "-j", "cursorpos") or "{}")
        if mon and cursor:
            scale = float(mon.get("scale") or 1)
            width = int(mon["width"] / scale)
            if mon.get("transform", 0) in (1, 3, 5, 7):
                width = int(mon["height"] / scale)
            x = self._anchor_x(int(cursor.get("x", 0)) - int(mon["x"]),
                               width, str(mon.get("name", ""))) - WIDTH // 2
            left = max(8, min(x, width - WIDTH - 8))
            Layer.set_margin(window, Layer.Edge.LEFT, left)
            # Also anchored to the right edge: width = screen − two margins = WIDTH.
            # Anchored only to the left, the layer surface opened 587 px wide
            # instead of 380 on pages with wrapping labels (notification bodies).
            Layer.set_anchor(window, Layer.Edge.RIGHT, True)
            Layer.set_margin(window, Layer.Edge.RIGHT, max(0, width - left - WIDTH))

    def _anchor_x(self, cursor_x: int, width: int, monitor: str) -> int:
        """The x the panel centres on: fixed per item (see TAB_MODULES)."""
        if self.values.get("BAR_POSITION", "top") not in ("top", "bottom"):
            return cursor_x
        if _center_modules() & set(TAB_MODULES.get(self.tab, ())):
            return width // 2
        key = f"{monitor}:{self.tab}"
        try:
            anchors = json.loads(_ANCHORS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            anchors = {}
        known = anchors.get(key)
        if isinstance(known, int) and abs(known - cursor_x) <= ANCHOR_SNAP:
            return known
        anchors[key] = cursor_x
        try:
            _ANCHORS.write_text(json.dumps(anchors), encoding="utf-8")
        except OSError:
            pass
        return cursor_x

    def _build(self, tabs) -> None:
        window = Gtk.Window(application=self.app)
        window.add_css_class("hs-panel")
        self._layer(window, keyboard=True)
        self._place(window)
        keys = Gtk.EventControllerKey()
        # CAPTURE: so a focused widget (the calendar itself) does not swallow arrow keys.
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_key)
        window.add_controller(keys)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                       width_request=WIDTH, hexpand=False)
        card.add_css_class("hs-card")
        # Not equal widths: with homogeneous every button took the width of the
        # selected tab with its label, doubling the panel with nine tabs.
        bar = Gtk.Box(spacing=4)
        bar.add_css_class("hs-tabs")
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,
                               vhomogeneous=False, interpolate_size=True)
        self.buttons: dict[str, Gtk.ToggleButton] = {}
        self.tab_labels: dict[str, Gtk.Label] = {}
        group = None
        for tab_id, title, icon in tabs:
            button = Gtk.ToggleButton(hexpand=True)
            inner = Gtk.Box(spacing=4, halign=Gtk.Align.CENTER)
            inner.append(_icon(icon))
            # Label only on the selected tab, so six or seven tabs fit side by side.
            label = Gtk.Label(label=title, visible=False)
            inner.append(label)
            self.tab_labels[tab_id] = label
            button.set_child(inner)
            button.set_tooltip_text(title)
            if group is None:
                group = button
            else:
                button.set_group(group)
            button.connect("toggled", self._on_tab, tab_id)
            bar.append(button)
            self.buttons[tab_id] = button
            self.stack.add_named(getattr(self, f"_page_{tab_id}")(), tab_id)
        card.append(bar)
        card.append(self.stack)
        self.card = card
        self.slider = _SlideBin(card)
        window.set_child(self.slider)
        self.buttons[self.tab].set_active(True)
        self.stack.set_visible_child_name(self.tab)
        self._set_slide(1.0)
        window.present()
        self.windows.append(window)
        self.panel_window = window
        self.closing = False
        self._animate(opening=True)

    # ---- open / close
    def _set_slide(self, hidden: float) -> None:
        """hidden 1 → card fully behind the bar, 0 → in place."""
        height = self.card.get_height() or 400
        sign = 1 if self.values.get("BAR_POSITION", "top") == "bottom" else -1
        self.slider.set_slide(sign * hidden * (height + 12), 1 - hidden * 0.6)

    def _animate(self, opening: bool, then=None) -> None:
        start = time.monotonic()

        def tick(_widget, _clock) -> bool:
            t = min(1.0, (time.monotonic() - start) / SLIDE)
            eased = 1 - (1 - t) ** 3
            self._set_slide(1 - eased if opening else eased)
            if t >= 1.0:
                if then:
                    then()
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE
        self.slider.add_tick_callback(tick)

    def close(self) -> None:
        """The card slides back into the bar edge, then the process ends."""
        if self.closing:
            return
        self.closing = True
        self._animate(opening=False, then=self.app.quit)

    def _on_tab(self, button: Gtk.ToggleButton, tab_id: str) -> None:
        # With many tabs (nine or ten on a desktop with brightness +
        # notifications) the selected tab's label is hidden too, so the panel
        # width (WIDTH) is not exceeded.
        self.tab_labels[tab_id].set_visible(button.get_active()
                                            and len(self.tab_labels) <= 8)
        if button.get_active():
            self.tab = tab_id
            self.stack.set_visible_child_name(tab_id)
            refresh = self.refreshers.get(tab_id)
            if refresh:
                refresh()
            # The layer surface does not shrink by itself when the content
            # does: switching from the long Sound tab to Calendar left an empty
            # area at the bottom. The default size is re-requested once the
            # transition ends.
            window = getattr(self, "panel_window", None)
            if window is not None:
                GLib.timeout_add(self.stack.get_transition_duration() + 30,
                                 lambda: (window.set_default_size(WIDTH, 1), False)[1])

    #: Arrow keys on the Calendar tab: ←/→ month, ↑/↓ year (month·12); Home/T today.
    _CALENDAR_KEYS = {Gdk.KEY_Left: -1, Gdk.KEY_Right: 1, Gdk.KEY_Up: -12,
                      Gdk.KEY_Down: 12, Gdk.KEY_Page_Up: -1, Gdk.KEY_Page_Down: 1}

    def _on_key(self, _controller, key: int, _code: int, _state) -> bool:
        if key == Gdk.KEY_Escape:
            self.close()
            return True
        if self.tab == "takvim" and getattr(self, "calendar", None) is not None:
            if key in self._CALENDAR_KEYS:
                self._calendar_shift(self._CALENDAR_KEYS[key])
                return True
            if key in (Gdk.KEY_Home, Gdk.KEY_t, Gdk.KEY_T):
                self._calendar_today()
                return True
        return False

    def _calendar_shift(self, months: int) -> None:
        """Shift the shown month; the selected day (highlight) stays put."""
        calendar = self.calendar
        index = calendar.get_property("year") * 12 + calendar.get_property("month") + months
        year, month = divmod(index, 12)
        calendar.set_property("month", month)
        calendar.set_property("year", year)

    def _calendar_today(self) -> None:
        self.calendar.select_day(GLib.DateTime.new_now_local())

    def switch(self, tab: str) -> None:
        """Another item was clicked: switch to that tab; close if it is the same tab."""
        if tab == self.tab or tab not in self.buttons:
            self.close()
            return
        self.buttons[tab].set_active(True)

    def _tick(self) -> bool:
        refresh = self.refreshers.get(self.tab)
        if refresh and self.tab in ("ses", "pil", "parlaklik", "sistem", "kayit", "bildirim"):
            refresh()
        return True

    def _media_tick(self) -> bool:
        if self.tab == "medya" and "medya" in self.refreshers:
            self.refreshers["medya"]()
        return True

    # ---- shared parts
    @staticmethod
    def _section(text: str) -> Gtk.Label:
        label = Gtk.Label(label=text.upper(), xalign=0)
        label.add_css_class("section")
        return label

    @staticmethod
    def _dim(text: str) -> Gtk.Label:
        # GTK's own wrapping (wrap=True) breaks width negotiation on a layer
        # surface: on pages with a wrapping label (calendar, recording) the
        # panel opened 498 px wide instead of 380 and the calendar overflowed
        # the card. The text is split into lines here; the label does not wrap.
        label = Gtk.Label(label=_fold(text), xalign=0, max_width_chars=1,
                          hexpand=True, ellipsize=3)
        label.add_css_class("dim")
        return label

    def _more(self, text: str, argv: list[str]) -> Gtk.Button:
        button = Gtk.Button(label=text, halign=Gtk.Align.END)
        button.add_css_class("text")

        def clicked(_b) -> None:
            _bg(*argv)
            self.close()
        button.connect("clicked", clicked)
        return button

    def _row(self, title: str, subtitle: str, icon: str, active: bool,
             on_click=None, suffix: Gtk.Widget | None = None) -> Gtk.Widget:
        box = Gtk.Box(spacing=10)
        box.add_css_class("row")
        if active:
            box.add_css_class("active")
        box.append(_icon(icon))
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        name = Gtk.Label(label=title, xalign=0, ellipsize=3, max_width_chars=1,
                         hexpand=True)
        name.set_tooltip_text(title)
        texts.append(name)
        if subtitle:
            texts.append(self._dim(subtitle))
        box.append(texts)
        if suffix is not None:
            box.append(suffix)
        if on_click is None:
            return box
        button = Gtk.Button(child=box)
        button.add_css_class("flat-row")
        button.connect("clicked", lambda _b: on_click())
        return button

    def _slider(self, icon: str, value: float, on_change, mute=None,
                muted: bool = False, maximum: float = 1.0):
        line = Gtk.Box(spacing=8)
        button = Gtk.Button(icon_name=icon)
        button.add_css_class("text")
        if muted:
            button.add_css_class("on")
        if mute:
            button.connect("clicked", lambda _b: mute())
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, maximum, 0.01)
        scale.set_hexpand(True)
        scale.set_value(value)
        percent = Gtk.Label(label=f"{round(value * 100)}%", width_chars=5, xalign=1)
        percent.add_css_class("dim")
        state = {"user": True}

        def changed(widget) -> None:
            percent.set_label(f"{round(widget.get_value() * 100)}%")
            if state["user"]:
                on_change(widget.get_value())
        scale.connect("value-changed", changed)
        line.append(button)
        line.append(scale)
        line.append(percent)

        def set_quiet(new: float, new_muted: bool) -> None:
            if abs(scale.get_value() - new) > 0.011:
                state["user"] = False
                scale.set_value(new)
                state["user"] = True
            if new_muted:
                button.add_css_class("on")
            else:
                button.remove_css_class("on")
        return line, set_quiet

    # ---- Sound
    def _page_ses(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        sink = "@DEFAULT_AUDIO_SINK@"
        source = "@DEFAULT_AUDIO_SOURCE@"
        vol, muted = _volume(sink)
        page.append(self._section("Output"))
        out_line, out_set = self._slider(
            "audio-volume-high-symbolic", vol,
            lambda v: _bg("wpctl", "set-volume", sink, f"{v:.2f}"),
            mute=lambda: (_bg("wpctl", "set-mute", sink, "toggle"),
                          GLib.timeout_add(150, lambda: (refresh(), False)[1])),
            muted=muted, maximum=1.0)
        page.append(out_line)
        mic, mic_muted = _volume(source)
        page.append(self._section("Microphone"))
        in_line, in_set = self._slider(
            "audio-input-microphone-symbolic", mic,
            lambda v: _bg("wpctl", "set-volume", source, f"{v:.2f}"),
            mute=lambda: (_bg("wpctl", "set-mute", source, "toggle"),
                          GLib.timeout_add(150, lambda: (refresh(), False)[1])),
            muted=mic_muted)
        page.append(in_line)

        # Per-app volume (pactl sink-inputs): Spotify, Discord, browser,
        # games… When the stream list changes the rows are rebuilt; otherwise
        # only the values are quietly updated (so dragging is not interrupted).
        apps_title = self._section("Applications")
        apps_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        page.append(apps_title)
        page.append(apps_box)
        streams: dict = {"ids": None, "setters": {}}

        def read_streams() -> list[dict]:
            try:
                data = json.loads(_out("pactl", "--format=json", "list", "sink-inputs") or "[]")
            except ValueError:
                return []
            found = []
            for item in data:
                props = item.get("properties", {})
                channels = list((item.get("volume") or {}).values())
                try:
                    level = int(str(channels[0].get("value_percent", "100%")).rstrip("%")) / 100
                except (IndexError, ValueError, AttributeError):
                    level = 1.0
                name = (props.get("application.name") or props.get("application.process.binary")
                        or props.get("media.name") or "?")
                found.append({"id": item.get("index"), "name": name,
                              "media": props.get("media.name", ""),
                              "icon": props.get("application.icon_name")
                              or (props.get("application.process.binary") or "").removesuffix(".bin")
                              or "audio-x-generic",
                              "level": level, "muted": bool(item.get("mute"))})
            return found

        def fill_streams() -> None:
            if self.values.get("PANEL_APP_VOLUME", "true") == "false":
                apps_title.set_visible(False)
                apps_box.set_visible(False)
                return
            found = read_streams()
            ids = [stream["id"] for stream in found]
            apps_title.set_visible(bool(found))
            apps_box.set_visible(bool(found))
            if ids == streams["ids"]:
                for stream in found:
                    setter = streams["setters"].get(stream["id"])
                    if setter:
                        setter(stream["level"], stream["muted"])
                return
            streams["ids"] = ids
            streams["setters"] = {}
            child = apps_box.get_first_child()
            while child:
                apps_box.remove(child)
                child = apps_box.get_first_child()
            theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
            for stream in found:
                index = str(stream["id"])
                title = Gtk.Label(label=stream["name"], xalign=0, ellipsize=3,
                                  max_width_chars=1, hexpand=True)
                title.add_css_class("dim")
                if stream["media"] and stream["media"] != stream["name"]:
                    title.set_tooltip_text(stream["media"])
                apps_box.append(title)
                icon = stream["icon"] if theme.has_icon(stream["icon"]) else "audio-volume-high-symbolic"
                line, setter = self._slider(
                    icon, stream["level"],
                    lambda v, i=index: _bg("pactl", "set-sink-input-volume", i, f"{round(v * 100)}%"),
                    mute=lambda i=index: (_bg("pactl", "set-sink-input-mute", i, "toggle"),
                                          GLib.timeout_add(150, lambda: (fill_streams(), False)[1])),
                    muted=stream["muted"])
                apps_box.append(line)
                streams["setters"][stream["id"]] = setter

        page.append(self._section("Output device"))
        devices = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        page.append(devices)
        page.append(self._more("Advanced sound settings", ["pavucontrol"]))

        def fill_devices() -> None:
            child = devices.get_first_child()
            while child:
                devices.remove(child)
                child = devices.get_first_child()
            try:
                sinks = json.loads(_out("pactl", "--format=json", "list", "sinks") or "[]")
            except ValueError:
                sinks = []
            default = _out("pactl", "get-default-sink").strip()
            for item in sinks:
                name = item.get("name", "")
                title = item.get("description") or name
                devices.append(self._row(
                    title, "", "audio-speakers-symbolic", name == default,
                    on_click=lambda n=name: (_bg("pactl", "set-default-sink", n),
                                             GLib.timeout_add(250, lambda: (fill_devices(), False)[1]))))

        def refresh() -> None:
            out_set(*_volume(sink))
            in_set(*_volume(source))
            fill_streams()
        fill_devices()
        fill_streams()
        self.refreshers["ses"] = refresh
        return page

    # ---- Network
    def _page_ag(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        head = Gtk.Box(spacing=8)
        head.append(Gtk.Label(label="Wi-Fi", xalign=0, hexpand=True))
        wifi = Gtk.Switch(valign=Gtk.Align.CENTER)
        head.append(wifi)
        page.append(head)
        page.append(self._section("Connections"))
        active = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        page.append(active)
        page.append(self._section("Nearby networks"))
        nearby = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                      propagate_natural_height=True,
                                      max_content_height=240)
        scroller.set_child(nearby)
        page.append(scroller)
        status = self._dim("")
        page.append(status)
        terminal = (self.values.get("CMD_TERMINAL") or "kitty").split()
        flag = self.values.get("TERMINAL_EXEC_FLAG") or "-e"
        page.append(self._more("Detailed network settings",
                               ["nm-connection-editor"] if shutil.which("nm-connection-editor")
                               else [*terminal, *flag.split(), "nmtui"]))
        state = {"quiet": False}

        def clear(box) -> None:
            child = box.get_first_child()
            while child:
                box.remove(child)
                child = box.get_first_child()

        def connect(ssid: str, secure: bool) -> None:
            known = ssid in _out("nmcli", "-t", "-f", "NAME", "connection", "show").splitlines()
            if secure and not known:
                ask_password(ssid)
                return
            status.set_label(f"Connecting to {ssid}…")
            _later(lambda: _out("nmcli", "dev", "wifi", "connect", ssid, timeout=30),
                   lambda out: (status.set_label(out.strip()[:120]), refresh()))

        def ask_password(ssid: str) -> None:
            clear(nearby)
            nearby.append(self._dim(f"Password for {ssid}:"))
            entry = Gtk.PasswordEntry(show_peek_icon=True)
            nearby.append(entry)

            def go(*_a) -> None:
                password = entry.get_text()
                status.set_label(f"Connecting to {ssid}…")
                _later(lambda: _out("nmcli", "dev", "wifi", "connect", ssid,
                                    "password", password, timeout=40),
                       lambda out: (status.set_label(out.strip()[:120]), refresh()))
            entry.connect("activate", go)
            entry.grab_focus()

        def fill(data) -> None:
            radio, devices, networks = data
            state["quiet"] = True
            wifi.set_active(radio == "enabled")
            state["quiet"] = False
            clear(active)
            for line in devices:
                dev, kind, st, con = (line.split(":") + ["", "", "", ""])[:4]
                if kind in ("loopback", "dummy") or not con:
                    continue
                icon = {"ethernet": "network-wired-symbolic",
                        "wifi": "network-wireless-symbolic",
                        "wireguard": "network-vpn-symbolic"}.get(kind, "network-workgroup-symbolic")
                active.append(self._row(con, f"{dev} · {st}", icon, True))
            clear(nearby)
            if radio != "enabled":
                nearby.append(self._dim("Wi-Fi is off."))
            elif not networks:
                nearby.append(self._dim("No networks found (or no Wi-Fi card)."))
            seen = set()
            for line in networks:
                parts = re.split(r"(?<!\\):", line)
                if len(parts) < 4 or not parts[1] or parts[1] in seen:
                    continue
                in_use, ssid, signal_, security = parts[:4]
                ssid = ssid.replace("\\:", ":")
                seen.add(ssid)
                secure = bool(security and security != "--")
                nearby.append(self._row(
                    ssid, f"{signal_}% · {security if secure else 'open'}",
                    "network-wireless-signal-good-symbolic" if int(signal_ or 0) > 50
                    else "network-wireless-signal-weak-symbolic",
                    in_use == "*",
                    on_click=None if in_use == "*" else
                    (lambda s=ssid, sec=secure: connect(s, sec))))

        def load():
            radio = _out("nmcli", "radio", "wifi").strip()
            devices = _out("nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "dev").splitlines()
            networks = (_out("nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "dev",
                             "wifi", "list", timeout=8).splitlines()
                        if radio == "enabled" else [])
            return radio, devices, networks

        def refresh() -> None:
            _later(load, fill)

        def toggled(sw, _p) -> None:
            if not state["quiet"]:
                _bg("nmcli", "radio", "wifi", "on" if sw.get_active() else "off")
                GLib.timeout_add(1200, lambda: (refresh(), False)[1])
        wifi.connect("notify::active", toggled)
        self.refreshers["ag"] = refresh
        if self.tab == "ag":
            refresh()
        return page

    # ---- Bluetooth
    def _page_bluetooth(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        head = Gtk.Box(spacing=8)
        head.append(Gtk.Label(label="Bluetooth", xalign=0, hexpand=True))
        power = Gtk.Switch(valign=Gtk.Align.CENTER)
        head.append(power)
        page.append(head)
        page.append(self._section("Paired devices"))
        devices = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        page.append(devices)
        status = self._dim("")
        page.append(status)
        page.append(self._more("Bluetooth manager", ["blueman-manager"]))
        state = {"quiet": False}

        def load():
            show = _out("bluetoothctl", "show")
            powered = "Powered: yes" in show
            items = []
            for line in _out("bluetoothctl", "devices", "Paired").splitlines():
                parts = line.split(" ", 2)
                if len(parts) < 3:
                    continue
                mac, name = parts[1], parts[2]
                info = _out("bluetoothctl", "info", mac)
                icon = re.search(r"Icon: (\S+)", info)
                battery = re.search(r"Battery Percentage: \S+ \((\d+)\)", info)
                items.append((mac, name, "Connected: yes" in info,
                              (icon.group(1) if icon else "bluetooth") + "-symbolic",
                              battery.group(1) if battery else ""))
            return powered, items

        def fill(data) -> None:
            powered, items = data
            state["quiet"] = True
            power.set_active(powered)
            state["quiet"] = False
            child = devices.get_first_child()
            while child:
                devices.remove(child)
                child = devices.get_first_child()
            if not powered:
                devices.append(self._dim("Bluetooth is off."))
                return
            if not items:
                devices.append(self._dim("No paired devices. Open the Bluetooth "
                                         "manager to pair one."))
            for mac, name, connected, icon, battery in items:
                sub = ("connected" if connected else "not connected") + (f" · {battery}%" if battery else "")
                devices.append(self._row(
                    name, sub, icon, connected,
                    on_click=lambda m=mac, c=connected, n=name: act(m, c, n)))

        def act(mac: str, connected: bool, name: str) -> None:
            status.set_label(f"{'Disconnecting' if connected else 'Connecting'} {name}…")
            _later(lambda: _out("bluetoothctl", "disconnect" if connected else "connect",
                                mac, timeout=20),
                   lambda out: (status.set_label(out.strip().splitlines()[-1][:120]
                                                 if out.strip() else ""), refresh()))

        def refresh() -> None:
            _later(load, fill)

        def toggled(sw, _p) -> None:
            if not state["quiet"]:
                _bg("bluetoothctl", "power", "on" if sw.get_active() else "off")
                GLib.timeout_add(1200, lambda: (refresh(), False)[1])
        power.connect("notify::active", toggled)
        self.refreshers["bluetooth"] = refresh
        if self.tab == "bluetooth":
            refresh()
        return page

    # ---- System
    def _page_sistem(self) -> Gtk.Widget:
        """CPU (total + per core), temperature, RAM, swap, disk and the top
        resource-using processes. Numbers are read from /proc and /sys."""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        def meter(title: str) -> tuple[Gtk.Widget, Gtk.Label, Gtk.LevelBar, Gtk.Label]:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            head = Gtk.Box(spacing=6)
            name = Gtk.Label(label=title, xalign=0, hexpand=True)
            value = Gtk.Label(xalign=1)
            value.add_css_class("value")
            head.append(name)
            head.append(value)
            level = Gtk.LevelBar(min_value=0, max_value=1)
            level.set_mode(Gtk.LevelBarMode.CONTINUOUS)
            for name_ in ("low", "high", "full"):
                level.remove_offset_value(name_)
            detail = self._dim("")
            box.append(head)
            box.append(level)
            box.append(detail)
            return box, value, level, detail

        cpu_box, cpu_value, cpu_level, cpu_detail = meter("CPU")
        page.append(cpu_box)
        cores = Gtk.Box(spacing=3, halign=Gtk.Align.FILL)
        cores.add_css_class("cores")
        page.append(cores)
        ram_box, ram_value, ram_level, ram_detail = meter("Memory (RAM)")
        page.append(ram_box)
        swap_box, swap_value, swap_level, swap_detail = meter("Swap")
        page.append(swap_box)
        disk_box, disk_value, disk_level, disk_detail = meter("Disk ( / )")
        page.append(disk_box)
        page.append(self._section("Top processes"))
        procs = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        page.append(procs)
        terminal = (self.values.get("CMD_TERMINAL") or "kitty").split()
        flag = self.values.get("TERMINAL_EXEC_FLAG") or "-e"
        page.append(self._more("Task manager (btop)",
                               [*terminal, *flag.split(), "btop"]))
        core_bars: list[Gtk.LevelBar] = []
        last: dict[str, list[tuple[int, int]]] = {}

        def cpu_times() -> list[tuple[int, int]]:
            """[(idle, total)]: first the whole CPU, then each core."""
            rows = []
            for line in Path("/proc/stat").read_text().splitlines():
                if not line.startswith("cpu"):
                    break
                nums = [int(x) for x in line.split()[1:]]
                idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
                rows.append((idle, sum(nums)))
            return rows

        def temperature() -> str:
            for hw in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
                try:
                    name = (hw / "name").read_text().strip()
                except OSError:
                    continue
                if name in ("k10temp", "coretemp", "zenpower", "cpu_thermal"):
                    try:
                        return f"{int((hw / 'temp1_input').read_text()) / 1000:.0f}°C"
                    except (OSError, ValueError):
                        return ""
            return ""

        def gib(kib: int) -> str:
            return f"{kib / 1048576:.1f} GiB"

        def refresh() -> None:
            now = cpu_times()
            before = last.get("cpu") or now
            last["cpu"] = now
            usage = []
            for (i0, t0), (i1, t1) in zip(before, now, strict=False):
                total = t1 - t0
                usage.append(0.0 if total <= 0 else 1 - (i1 - i0) / total)
            if usage:
                cpu_level.set_value(usage[0])
                cpu_value.set_label(f"{usage[0] * 100:.0f}%")
                load = os.getloadavg()
                temp = temperature()
                cpu_detail.set_label("  ·  ".join(x for x in (
                    f"{len(usage) - 1} cores", temp,
                    f"load {load[0]:.2f} {load[1]:.2f} {load[2]:.2f}") if x))
                while len(core_bars) < len(usage) - 1:
                    bar = Gtk.LevelBar(min_value=0, max_value=1,
                                       orientation=Gtk.Orientation.VERTICAL,
                                       inverted=True, height_request=26,
                                       hexpand=True)
                    for name_ in ("low", "high", "full"):
                        bar.remove_offset_value(name_)
                    core_bars.append(bar)
                    cores.append(bar)
                for bar, value in zip(core_bars, usage[1:], strict=False):
                    bar.set_value(value)
                    bar.set_tooltip_text(f"{value * 100:.0f}%")
            mem = {}
            for line in Path("/proc/meminfo").read_text().splitlines():
                key, _, rest = line.partition(":")
                mem[key] = int(rest.split()[0])
            total = mem.get("MemTotal", 1)
            used = total - mem.get("MemAvailable", 0)
            ram_level.set_value(used / total)
            ram_value.set_label(f"{used / total * 100:.0f}%")
            ram_detail.set_label(f"{gib(used)} / {gib(total)} used  ·  "
                                 f"cache {gib(mem.get('Cached', 0))}")
            stotal = mem.get("SwapTotal", 0)
            sused = stotal - mem.get("SwapFree", 0)
            swap_box.set_visible(stotal > 0)
            if stotal:
                swap_level.set_value(sused / stotal)
                swap_value.set_label(f"{sused / stotal * 100:.0f}%")
                swap_detail.set_label(f"{gib(sused)} / {gib(stotal)}")
            disk = shutil.disk_usage("/")
            disk_level.set_value(disk.used / disk.total)
            disk_value.set_label(f"{disk.used / disk.total * 100:.0f}%")
            disk_detail.set_label(f"{disk.used / 1e9:.0f} GB / {disk.total / 1e9:.0f} GB  ·  "
                                  f"free {disk.free / 1e9:.0f} GB")
            _later(lambda: _out("ps", "-eo", "pcpu,rss,comm", "--sort=-pcpu",
                                "--no-headers"), fill_procs)

        def fill_procs(text: str) -> None:
            child = procs.get_first_child()
            while child:
                procs.remove(child)
                child = procs.get_first_child()
            shown = 0
            for line in text.splitlines():
                parts = line.split(None, 2)
                # The ps producing the list always showed itself at 100%.
                if len(parts) < 3 or parts[2] == "ps":
                    continue
                if shown == 5:
                    break
                shown += 1
                cpu, rss, name = parts
                row = Gtk.Box(spacing=8)
                row.append(Gtk.Label(label=name, xalign=0, hexpand=True, ellipsize=3,
                                     max_width_chars=1))
                for text_, width in ((f"{float(cpu):.0f}%", 5),
                                     (f"{int(rss) / 1024:.0f} MB", 8)):
                    label = Gtk.Label(label=text_, xalign=1, width_chars=width)
                    label.add_css_class("dim")
                    row.append(label)
                procs.append(row)

        last["cpu"] = cpu_times()
        refresh()
        # After a short wait for the first measurement delta, the real value.
        GLib.timeout_add(500, lambda: (refresh(), False)[1])
        self.refreshers["sistem"] = refresh
        return page

    # ---- Battery
    def _page_pil(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        top = Gtk.Box(spacing=12)
        icon = Gtk.Image.new_from_icon_name("battery-good-symbolic")
        icon.set_pixel_size(40)
        top.append(icon)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        percent = Gtk.Label(xalign=0)
        percent.add_css_class("big")
        state_label = self._dim("")
        texts.append(percent)
        texts.append(state_label)
        top.append(texts)
        page.append(top)
        details = self._dim("")
        page.append(details)
        profiles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        if shutil.which("powerprofilesctl"):
            page.append(self._section("Power mode"))
            page.append(profiles)

        def refresh() -> None:
            device = next((d for d in _out("upower", "-e").split()
                           if "battery_" in d), "")
            info = _out("upower", "-i", device) if device else ""

            def field(name: str) -> str:
                match = re.search(rf"^\s*{name}:\s*(.+)$", info, re.M)
                return match.group(1).strip() if match else ""
            pct = field("percentage") or "?"
            percent.set_label(pct)
            raw = field("state")
            state_label.set_label({"charging": "Charging", "discharging": "On battery",
                                   "fully-charged": "Fully charged",
                                   "pending-charge": "Waiting to charge"}.get(raw, raw))
            left = field("time to empty") or field("time to full")
            rate = field("energy-rate")
            energy = f"{field('energy')} / {field('energy-full')}"
            details.set_label("  ·  ".join(x for x in (
                f"{left} left" if left else "", f"power {rate}" if rate else "",
                energy if field("energy") else "") if x))
            try:
                value = int(pct.rstrip("%"))
            except ValueError:
                value = 50
            level = ("full" if value > 90 else "good" if value > 50
                     else "low" if value > 20 else "caution")
            icon.set_from_icon_name(f"battery-{level}{'-charging' if raw == 'charging' else ''}-symbolic")
            current = _out("powerprofilesctl", "get").strip()
            child = profiles.get_first_child()
            while child:
                profiles.remove(child)
                child = profiles.get_first_child()
            for key, title, sym in (("power-saver", "Power saver", "power-profile-power-saver-symbolic"),
                                    ("balanced", "Balanced", "power-profile-balanced-symbolic"),
                                    ("performance", "Performance", "power-profile-performance-symbolic")):
                profiles.append(self._row(
                    title, "active" if key == current else "", sym, key == current,
                    on_click=lambda k=key: (_bg("powerprofilesctl", "set", k),
                                            GLib.timeout_add(300, lambda: (refresh(), False)[1]))))
        refresh()
        self.refreshers["pil"] = refresh
        return page

    # ---- Brightness
    def _page_parlaklik(self) -> Gtk.Widget:
        """Laptop panel (brightnessctl) + external displays (ddcutil, DDC/CI).

        External displays are slow to detect: the page first says "searching",
        then puts a slider for each display once the result arrives. A display
        without DDC/CI support is listed by name with a note (no software
        dimming: Hyprland does not offer per-display gamma).
        """
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        refresh = []
        if has_backlight():
            def read() -> float:
                parts = _out("brightnessctl", "-m", "-c", "backlight").strip().split(",")
                try:
                    return int(parts[3].rstrip("%")) / 100
                except (IndexError, ValueError):
                    return 0.5
            page.append(self._section("Display"))
            line, setter = self._slider(
                "display-brightness-symbolic", read(),
                lambda v: _bg("brightnessctl", "-q", "-c", "backlight", "set",
                              f"{max(1, round(v * 100))}%"))
            page.append(line)
            refresh.append(lambda: setter(read(), False))

        if self.ddc:
            page.append(self._section("External displays"))
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            box.append(self._dim("Searching for displays (DDC/CI)…"))
            page.append(box)

            def clear() -> None:
                child = box.get_first_child()
                while child:
                    box.remove(child)
                    child = box.get_first_child()

            def fill(displays: list[dict]) -> None:
                clear()
                if not displays:
                    box.append(self._dim("No displays controllable via DDC/CI found."))
                for display in displays:
                    title = Gtk.Label(label=f"{display['name']} · {display['model']}",
                                      xalign=0, ellipsize=3, max_width_chars=1, hexpand=True)
                    box.append(title)
                    if not display.get("max"):
                        box.append(self._dim("This display does not support brightness "
                                             "via DDC/CI (it may be enabled in its OSD menu)."))
                        continue
                    writer = _DdcWriter(display["bus"])
                    top = display["max"]
                    line, setter = self._slider(
                        "display-brightness-symbolic", 0.5,
                        lambda v, w=writer, m=top: w.set(max(0, round(v * m))))
                    line.set_sensitive(False)
                    box.append(line)

                    def got(value, line=line, setter=setter, m=top) -> None:
                        if value is not None:
                            setter(value[0] / m, False)
                            line.set_sensitive(True)
                    _later(lambda b=display["bus"]: _ddc_brightness(b), got)
                rescan = Gtk.Button(label="Rescan", halign=Gtk.Align.END)
                rescan.add_css_class("text")
                rescan.connect("clicked", lambda _b: start(True))
                box.append(rescan)

            def start(again: bool = False) -> None:
                clear()
                box.append(self._dim("Searching for displays (DDC/CI)…"))
                _later(lambda: ddc_displays(rescan=again), fill)
            start()

        if shutil.which("hyprsunset"):
            page.append(self._section("Night light"))
            night = Gtk.Switch(halign=Gtk.Align.END, valign=Gtk.Align.CENTER)
            night.set_active(bool(_out("pgrep", "-x", "hyprsunset").strip()))
            temp = self.values.get("NIGHT_TEMP") or "4000"

            def toggled(sw, _param) -> None:
                running = bool(_out("pgrep", "-x", "hyprsunset").strip())
                if sw.get_active() and not running:
                    _bg("hyprsunset", "-t", str(temp))
                elif not sw.get_active() and running:
                    _bg("pkill", "-x", "hyprsunset")
            night.connect("notify::active", toggled)
            page.append(self._row(f"Warm colors ({temp} K)", "Reduces blue light",
                                  "weather-clear-night-symbolic", False, suffix=night))
        self.refreshers["parlaklik"] = lambda: [f() for f in refresh]
        return page

    # ---- Notifications
    def _page_bildirim(self) -> Gtk.Widget:
        """Notification history (notifylog.py) + do-not-disturb switch.

        The history is kept independently of the notification server and only
        lives for the session (XDG_RUNTIME_DIR). The list is redrawn when the
        file changes.
        """
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        quiet = Gtk.Switch(halign=Gtk.Align.END, valign=Gtk.Align.CENTER)
        quiet.set_active(_out(str(NOTIFYLOG), "dnd").strip() == "on")
        quiet.connect("notify::active", lambda sw, _p: _bg(
            str(NOTIFYLOG), "dnd", "on" if sw.get_active() else "off"))
        page.append(self._row("Do not disturb", "Notifications are not shown, only logged",
                              "notifications-disabled-symbolic", False, suffix=quiet))

        head = Gtk.Box()
        head.append(self._section("History"))
        clear = Gtk.Button(label="Clear", halign=Gtk.Align.END, hexpand=True)
        clear.add_css_class("text")
        head.append(clear)
        page.append(head)
        items_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scroller = Gtk.ScrolledWindow(child=items_box, vexpand=True,
                                      hscrollbar_policy=Gtk.PolicyType.NEVER,
                                      propagate_natural_height=True,
                                      max_content_height=420)
        page.append(scroller)
        log = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp") / "hyprsetup-notifications.json"
        state = {"mtime": -1.0}

        def ago(stamp: int) -> str:
            seconds = max(0, int(time.time()) - int(stamp))
            if seconds < 60:
                return "just now"
            if seconds < 3600:
                return f"{seconds // 60} min ago"
            if seconds < 86400:
                return f"{seconds // 3600} h ago"
            return time.strftime("%b %d, %H:%M", time.localtime(stamp))

        def fill(force: bool = False) -> None:
            try:
                mtime = log.stat().st_mtime
            except OSError:
                mtime = 0.0
            if mtime == state["mtime"] and not force:
                return
            state["mtime"] = mtime
            child = items_box.get_first_child()
            while child:
                items_box.remove(child)
                child = items_box.get_first_child()
            try:
                items = json.loads(log.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                items = []
            clear.set_sensitive(bool(items))
            if not items:
                items_box.append(self._dim("No notifications this session."))
                return
            for item in reversed(items):
                body = re.sub(r"<[^>]+>", "", item.get("body", "")).strip()
                subtitle = f"{item.get('app') or 'App'} · {ago(item.get('time', 0))}"
                if body:
                    subtitle += "\n" + (body if len(body) < 160 else body[:157] + "…")
                icon = item.get("icon", "")
                if not icon or "/" in icon:
                    icon = ("dialog-warning-symbolic" if item.get("urgency") == 2
                            else "preferences-system-notifications-symbolic")
                row = self._row(item.get("summary") or "(untitled)", subtitle, icon,
                                item.get("urgency") == 2)
                items_box.append(row)

        def clear_all(_b) -> None:
            _out(str(NOTIFYLOG), "clear")
            fill(force=True)
        clear.connect("clicked", clear_all)
        fill()
        self.refreshers["bildirim"] = fill
        return page

    # ---- Calendar
    def _page_takvim(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        now = GLib.DateTime.new_now_local()
        big = Gtk.Label(label=now.format("%H:%M"), xalign=0)
        big.add_css_class("big")
        page.append(big)
        page.append(self._dim(now.format("%A, %d %B %Y")))
        self.calendar = Gtk.Calendar()
        # The wheel changes the month too (down = next month).
        wheel = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL
                                              | Gtk.EventControllerScrollFlags.DISCRETE)
        wheel.connect("scroll", lambda _c, _dx, dy: (
            self._calendar_shift(1 if dy > 0 else -1), True)[1])
        self.calendar.add_controller(wheel)
        page.append(self.calendar)
        foot = Gtk.Box(spacing=6)
        hint = Gtk.Label(label="←/→ month · ↑/↓ year · T today", xalign=0, hexpand=True)
        hint.add_css_class("dim")
        foot.append(hint)
        today = Gtk.Button(label="Today", halign=Gtk.Align.END)
        today.add_css_class("text")
        today.connect("clicked", lambda _b: self._calendar_today())
        foot.append(today)
        page.append(foot)
        return page

    # ---- Recording
    def _page_kayit(self) -> Gtk.Widget:
        """Screen recording, instant replay and screenshots, via record.sh.

        State is read from record.sh's PID files; a recording started with a
        key (MOD+SHIFT+R, MOD+ALT+R) shows up here just the same.
        """
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        script = Path.home() / ".config/hypr/scripts/record.sh"
        run = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp")
        record_pid = run / "hyprsetup-record.pid"
        replay_pid = run / "hyprsetup-replay.pid"
        seconds = self.values.get("REPLAY_SECONDS") or "60"
        folder = os.path.expanduser(os.path.expandvars(
            self.values.get("RECORD_DIR") or "~/Videos"))

        def alive(path: Path) -> bool:
            try:
                os.kill(int(path.read_text().strip()), 0)
                return True
            except (OSError, ValueError):
                return False

        def record(action: str, later: bool = False) -> None:
            # Recording captures the focused display: if it started before the
            # panel closed, the panel would show in the first frames.
            if later:
                _bg("sh", "-c", f"sleep 0.5; exec '{script}' {action}")
                self.close()
            else:
                _bg(str(script), action)
                GLib.timeout_add(400, lambda: (refresh(), False)[1])

        if script.is_file():
            page.append(self._section("Screen recording"))
            rec_state = self._dim("")
            rec_button = Gtk.Button()
            rec_button.add_css_class("text")
            rec_button.connect("clicked", lambda _b: record(
                "record-toggle", later=not alive(record_pid)))
            line = Gtk.Box(spacing=8)
            line.append(Gtk.Image.new_from_icon_name("media-record-symbolic"))
            line.append(rec_state)
            line.append(rec_button)
            page.append(line)

            page.append(self._section("Instant replay"))
            head = Gtk.Box(spacing=8)
            head.append(Gtk.Label(label=f"Keep the last {seconds} seconds", xalign=0,
                                  hexpand=True))
            replay = Gtk.Switch(valign=Gtk.Align.CENTER)
            head.append(replay)
            page.append(head)
            save = Gtk.Button(label=f"Save the last {seconds} s")
            save.add_css_class("text")
            save.connect("clicked", lambda _b: record("replay-save"))
            page.append(save)
            state = {"quiet": False}

            def toggled(sw, _p) -> None:
                if not state["quiet"] and sw.get_active() != alive(replay_pid):
                    record("replay-toggle")
            replay.connect("notify::active", toggled)
        else:
            rec_state = rec_button = replay = save = None
            page.append(self._section("Screen recording"))
            page.append(self._dim("Recording is off: the “Instant replay "
                                  "(gpu-screen-recorder)” component is not selected "
                                  "in the settings, or its package is missing."))

        page.append(self._section("Screenshot"))
        shots = Gtk.Box(spacing=8, homogeneous=True)
        pictures = (self.values.get("SCREENSHOT_DIR_SH")
                    or "$(xdg-user-dir PICTURES)/Screenshots")
        name = '"Screenshot_$(date +%Y-%m-%d_%H.%M.%S).png"'
        for label, command in (
                ("Select region", 'grim -g "$(slurp)" - | wl-copy'),
                ("Full screen", f'mkdir -p "{pictures}" && f="{pictures}"/{name} '
                              '&& grim "$f" && wl-copy < "$f"')):
            button = Gtk.Button(label=label)
            button.add_css_class("text")
            button.connect("clicked", lambda _b, c=command: (
                _bg("sh", "-c", f"sleep 0.5; {c}"), self.close()))
            shots.append(button)
        page.append(shots)
        page.append(self._more("Open recordings folder", ["xdg-open", folder]))

        def refresh() -> None:
            if rec_state is None:
                return
            if alive(record_pid):
                secs = int(time.time() - record_pid.stat().st_mtime)
                rec_state.set_label(f"Recording · {secs // 60:02d}:{secs % 60:02d}")
                rec_button.set_label("Stop")
                rec_button.add_css_class("on")
            else:
                rec_state.set_label("Records the focused display")
                rec_button.set_label("Start")
                rec_button.remove_css_class("on")
            on = alive(replay_pid)
            state["quiet"] = True
            replay.set_active(on)
            state["quiet"] = False
            save.set_sensitive(on)
        refresh()
        self.refreshers["kayit"] = refresh
        return page

    # ---- Media
    def _page_medya(self) -> Gtk.Widget:
        """MPRIS player: read and controlled with playerctl.

        If several players are open (Spotify + browser) a chooser appears on
        top; the chosen player is targeted with ``-p``. The ``mpris:artUrl``
        cover is shown directly if it is a local file, or downloaded under
        ~/.cache first if it is http.

        Fixed layout: no row is hidden or shown when data arrives — every
        item always stays in its own place and is only dimmed when there is
        no player. The artist/album rows, the player chooser and the "nothing
        playing" text used to toggle, so everything shifted after the panel
        opened. On a track change the title block and the cover cross-fade;
        between polls the seek bar advances smoothly on a local clock.
        """
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        if not shutil.which("playerctl"):
            page.append(self._dim("playerctl is not installed (pacman -S playerctl)."))
            return page
        # Player chooser: shown (by name) even with one player; the row stays put.
        players_box = Gtk.Box(spacing=4, height_request=28)
        page.append(players_box)

        top = Gtk.Box(spacing=12)
        cover_stack = Gtk.Stack(hhomogeneous=True, vhomogeneous=True,
                                valign=Gtk.Align.CENTER,
                                transition_type=Gtk.StackTransitionType.CROSSFADE,
                                transition_duration=260)
        # No cover (live stream, local file): an icon instead of an empty square.
        placeholder = Gtk.Image.new_from_icon_name("audio-x-generic-symbolic")
        placeholder.set_pixel_size(40)
        placeholder.add_css_class("cover")
        placeholder.add_css_class("dim")
        placeholder.set_size_request(96, 96)
        cover_stack.add_named(placeholder, "none")
        # Two pictures take turns: the new cover loads into the hidden one and
        # cross-fades to the front, never dropping to the empty icon between.
        covers = []
        for name in ("art0", "art1"):
            picture = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True,
                                  width_request=96, height_request=96,
                                  hexpand=False, vexpand=False,
                                  overflow=Gtk.Overflow.HIDDEN)
            picture.add_css_class("cover")
            cover_stack.add_named(picture, name)
            covers.append(picture)
        top.append(cover_stack)

        # Title block: two identical pages; on a track change the idle page is
        # filled and slides to the front. Labels are never hidden (an empty
        # one still takes a line), so the block's height is fixed.
        text_stack = Gtk.Stack(hhomogeneous=True, vhomogeneous=True, hexpand=True,
                               valign=Gtk.Align.CENTER,
                               transition_type=Gtk.StackTransitionType.SLIDE_LEFT,
                               transition_duration=280)
        text_pages = []
        for name in ("t0", "t1"):
            texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                            valign=Gtk.Align.CENTER, hexpand=True)
            title = Gtk.Label(xalign=0, ellipsize=3, max_width_chars=1, hexpand=True)
            title.add_css_class("media-title")
            artist = Gtk.Label(xalign=0, ellipsize=3, max_width_chars=1, hexpand=True)
            album = Gtk.Label(xalign=0, ellipsize=3, max_width_chars=1, hexpand=True)
            album.add_css_class("dim")
            player_name = Gtk.Label(xalign=0, ellipsize=3, max_width_chars=1, hexpand=True)
            player_name.add_css_class("dim")
            for widget in (title, artist, album, player_name):
                texts.append(widget)
            text_stack.add_named(texts, name)
            text_pages.append({"name": name, "title": title, "artist": artist,
                               "album": album, "player": player_name})
        top.append(text_stack)
        page.append(top)

        seek = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 1)
        seek.set_draw_value(False)
        seek.set_hexpand(True)
        page.append(seek)
        times = Gtk.Box()
        pos_label = Gtk.Label(xalign=0, hexpand=True)
        len_label = Gtk.Label(xalign=1)
        for label in (pos_label, len_label):
            label.add_css_class("dim")
            label.add_css_class("tnum")
            times.append(label)
        page.append(times)

        controls = Gtk.Box(spacing=10, halign=Gtk.Align.CENTER)

        def media_button(icon: str, tooltip: str, main: bool = False) -> Gtk.Button:
            button = Gtk.Button(icon_name=icon, valign=Gtk.Align.CENTER)
            button.add_css_class("media")
            if main:
                button.add_css_class("main")
            button.set_tooltip_text(tooltip)
            controls.append(button)
            return button
        shuffle = media_button("media-playlist-shuffle-symbolic", "Shuffle")
        prev = media_button("media-skip-backward-symbolic", "Previous")
        play = media_button("media-playback-start-symbolic", "Play / pause", main=True)
        nxt = media_button("media-skip-forward-symbolic", "Next")
        loop = media_button("media-playlist-repeat-symbolic", "Repeat")
        page.append(controls)

        page.append(self._section("Player volume"))
        vol_line, vol_set = self._slider(
            "audio-volume-high-symbolic", 1.0,
            lambda v: _bg("playerctl", *target(), "volume", f"{v:.2f}"))
        page.append(vol_line)

        # Recognize song (songrec): independent of the playing player, it listens
        # to any audio (video, stream, game). The result arrives as a
        # notification; the panel closes.
        actions = Path.home() / ".config/hypr/scripts/actions.py"
        if actions.is_file() and shutil.which("songrec"):
            page.append(self._section("Recognize song"))
            song = Gtk.Box(spacing=6, homogeneous=True)
            for label, ident in (("󰝚  What's playing", "sarki"),
                                 ("󰍬  From microphone", "sarki-mikrofon")):
                button = Gtk.Button(label=label, hexpand=True)
                button.add_css_class("text")

                def clicked(_b, i=ident) -> None:
                    _bg(str(actions), i)
                    self.close()
                button.connect("clicked", clicked)
                song.append(button)
            page.append(song)

        state = {"player": "", "players": None, "length": 0.0, "art": "",
                 "loop": "None", "dragging_until": 0.0, "key": None, "text": 0,
                 "cover": -1, "pos": 0.0, "pos_at": 0.0, "playing": False,
                 "shown_second": -1, "ignore_until": 0.0}
        live = (seek, controls, vol_line)

        def target() -> list[str]:
            return ["-p", state["player"]] if state["player"] else []

        def ctl(*args: str) -> None:
            _bg("playerctl", *target(), *args)
            # Browser players report the new track 300-600 ms later.
            for delay in (200, 650):
                GLib.timeout_add(delay, lambda: (refresh(), False)[1])

        def toggle_play(_b) -> None:
            # Optimistic: icon and progress change at once, a poll confirms
            # later. A poll still reporting the old state is briefly ignored.
            state["pos"] = predicted()
            state["pos_at"] = time.monotonic()
            state["playing"] = not state["playing"]
            state["ignore_until"] = time.monotonic() + 0.6
            play.set_icon_name("media-playback-pause-symbolic" if state["playing"]
                               else "media-playback-start-symbolic")
            ctl("play-pause")

        prev.connect("clicked", lambda _b: ctl("previous"))
        play.connect("clicked", toggle_play)
        nxt.connect("clicked", lambda _b: ctl("next"))
        shuffle.connect("clicked", lambda _b: ctl("shuffle", "toggle"))
        loop.connect("clicked", lambda _b: ctl(
            "loop", {"None": "Playlist", "Playlist": "Track"}.get(state["loop"], "None")))

        def on_seek(_scale, _scroll, value) -> bool:
            # change-value only fires when the user drags; updates pause briefly
            # so the tick does not pull the position back.
            state["dragging_until"] = time.monotonic() + 1.2
            state["pos"] = max(0.0, value)
            state["pos_at"] = time.monotonic() + 1.2
            _bg("playerctl", *target(), "position", f"{max(0.0, value):.1f}")
            return False
        seek.connect("change-value", on_seek)

        def clock(seconds: float) -> str:
            seconds = max(0, int(seconds))
            hours, rest = divmod(seconds, 3600)
            return (f"{hours}:{rest // 60:02d}:{rest % 60:02d}" if hours
                    else f"{rest // 60}:{rest % 60:02d}")

        def predicted() -> float:
            pos = state["pos"]
            if state["playing"]:
                pos += max(0.0, time.monotonic() - state["pos_at"])
            return min(pos, state["length"]) if state["length"] else pos

        def tick(_widget, _clock) -> bool:
            # Every frame: while playing the bar advances on a local clock
            # (polls are once a second; the bar no longer jumps each second).
            if state["length"] and time.monotonic() > state["dragging_until"]:
                value = predicted()
                if abs(seek.get_value() - value) > 0.01:
                    seek.set_value(value)
                second = int(value)
                if second != state["shown_second"]:
                    state["shown_second"] = second
                    pos_label.set_label(clock(value))
            return GLib.SOURCE_CONTINUE
        seek.add_tick_callback(tick)

        def fill_players(players: list[str]) -> None:
            child = players_box.get_first_child()
            while child:
                players_box.remove(child)
                child = players_box.get_first_child()
            if not players:
                players_box.append(self._dim("No player"))
            for name in players:
                button = Gtk.Button(label=name.split(".")[0].capitalize())
                button.add_css_class("text")
                if name == state["player"]:
                    button.add_css_class("on")
                button.connect("clicked", lambda _b, n=name: choose(n))
                players_box.append(button)

        def choose(name: str) -> None:
            state["player"] = name
            fill_players(state["players"] or [])
            refresh()

        def set_cover(picture: Gtk.Picture, path: str) -> None:
            # Picture takes its natural size from the image: a 300 px video
            # thumbnail squeezed the title in the fixed-width panel. A square
            # crop scaled down to 96 px is shown instead.
            try:
                pix = GdkPixbuf.Pixbuf.new_from_file(path)
                side = min(pix.get_width(), pix.get_height())
                pix = pix.new_subpixbuf((pix.get_width() - side) // 2,
                                        (pix.get_height() - side) // 2, side, side)
                pix = pix.scale_simple(96, 96, GdkPixbuf.InterpType.BILINEAR)
                picture.set_paintable(Gdk.Texture.new_for_pixbuf(pix))
            except GLib.Error:
                picture.set_filename(path)

        def present_cover(path: str) -> None:
            # Load into the hidden picture, then cross-fade it to the front.
            index = 1 - max(0, state["cover"])
            set_cover(covers[index], path)
            state["cover"] = index
            cover_stack.set_visible_child_name(f"art{index}")

        def show_art(url: str) -> None:
            if url == state["art"]:
                return
            state["art"] = url
            if not url.startswith(("file://", "http://", "https://")):
                state["cover"] = -1
                cover_stack.set_visible_child_name("none")
                return
            if url.startswith("file://"):
                present_cover(urllib.parse.unquote(url[7:]))
                return
            cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") \
                / "hyprsetup" / "cover"
            path = cache / hashlib.sha1(url.encode()).hexdigest()

            def fetch() -> str:
                if not path.is_file():
                    try:
                        cache.mkdir(parents=True, exist_ok=True)
                        with urllib.request.urlopen(url, timeout=6) as response:
                            path.write_bytes(response.read())
                    except (OSError, ValueError):
                        return ""
                return str(path)

            def shown(f: str) -> None:
                if state["art"] != url:
                    return
                if f:
                    present_cover(f)
                else:
                    state["cover"] = -1
                    cover_stack.set_visible_child_name("none")
            _later(fetch, shown)

        def show_text(title: str, artist: str, album: str, player: str) -> None:
            key = (title, artist, album, player)
            if key == state["key"]:
                return
            first = state["key"] is None
            # If only the player name changed: no slide, written in place.
            same_track = state["key"] is not None and state["key"][:3] == key[:3]
            state["key"] = key
            if first or same_track:
                current = text_pages[state["text"]]
            else:
                state["text"] = 1 - state["text"]
                current = text_pages[state["text"]]
            current["title"].set_label(title)
            current["title"].set_tooltip_text(title)
            current["artist"].set_label(artist)
            current["album"].set_label(album)
            current["player"].set_label(player)
            if first:
                text_stack.set_visible_child_full(
                    current["name"], Gtk.StackTransitionType.NONE)
            else:
                text_stack.set_visible_child_name(current["name"])

        fields = ("status", "title", "artist", "album", "mpris:artUrl",
                  "mpris:length", "position", "shuffle", "loop", "volume",
                  "playerName")
        fmt = "\x1f".join("{{" + f + "}}" for f in fields)

        def load():
            players = [p for p in _out("playerctl", "-l").split() if p]
            if not players:
                return players, {}, time.monotonic()
            if state["player"] not in players:
                # The SAME choice as the bar's player module (media.sh player):
                # the playing one, else the last one played. Without the script:
                # the playing one or the first.
                script = Path.home() / ".config/hypr/scripts/media.sh"
                chosen = (_out(str(script), "player").strip()
                          if os.access(script, os.X_OK) else "")
                if chosen not in players:
                    playing = [p for p in players
                               if _out("playerctl", "-p", p, "status").strip() == "Playing"]
                    chosen = (playing or players)[0]
                state["player"] = chosen
            raw = _out("playerctl", "-p", state["player"], "metadata", "--format", fmt)
            stamp = time.monotonic()
            parts = (raw.rstrip("\n").split("\x1f") + [""] * len(fields))[:len(fields)]
            return players, dict(zip(fields, parts, strict=False)), stamp

        def fill(data) -> None:
            players, meta, stamp = data
            if players != state["players"]:
                state["players"] = players
                fill_players(players)
            has = bool(meta) and meta.get("status") in ("Playing", "Paused")
            for widget in live:
                widget.set_sensitive(has)
            if not has:
                state.update(length=0.0, playing=False, pos=0.0)
                show_text("Nothing is playing right now", "", "", "")
                show_art("")
                seek.set_value(0)
                pos_label.set_label(clock(0))
                len_label.set_label(clock(0))
                return
            show_text(meta["title"] or "Unknown track", meta["artist"],
                      meta["album"], meta["playerName"] or state["player"])
            if time.monotonic() > state["ignore_until"]:
                state["playing"] = meta["status"] == "Playing"
                play.set_icon_name("media-playback-pause-symbolic" if state["playing"]
                                   else "media-playback-start-symbolic")
            for button, on in ((shuffle, meta["shuffle"] == "true"),
                               (loop, meta["loop"] in ("Track", "Playlist"))):
                (button.add_css_class if on else button.remove_css_class)("on")
            state["loop"] = meta["loop"] or "None"
            loop.set_icon_name("media-playlist-repeat-song-symbolic"
                               if meta["loop"] == "Track"
                               else "media-playlist-repeat-symbolic")
            shuffle.set_sensitive(bool(meta["shuffle"]))
            loop.set_sensitive(bool(meta["loop"]))
            try:
                length = int(meta["mpris:length"] or 0) / 1e6
            except ValueError:
                length = 0.0
            # On live streams browsers report the int64 ceiling.
            if length > 100 * 3600:
                length = 0.0
            try:
                position = int(meta["position"] or 0) / 1e6
            except ValueError:
                position = 0.0
            seek.set_sensitive(length > 0)
            if length > 0 and length != state["length"]:
                seek.set_range(0, length)
            state["length"] = length
            # A prediction close to reality is left alone (no bounce back); on a
            # new track, a seek or a pause the bar jumps to the new position.
            if time.monotonic() > state["dragging_until"] and (
                    abs(predicted() - position) > 0.75 or not state["playing"]):
                state["pos"], state["pos_at"] = position, stamp
            if not length:
                seek.set_value(0)
                pos_label.set_label(clock(position))
            len_label.set_label(clock(length) if length else "live")
            try:
                vol_set(float(meta["volume"] or 1.0), False)
            except ValueError:
                pass
            show_art(meta["mpris:artUrl"])

        busy = {"on": False}

        def refresh() -> None:
            if busy["on"]:
                return
            busy["on"] = True

            def done(data) -> None:
                busy["on"] = False
                fill(data)
            _later(load, done)

        self.refreshers["medya"] = refresh
        refresh()
        return page


# ------------------------------------------------------- single instance ----
def _running() -> int:
    try:
        pid = int(_PID.read_text().strip())
        os.kill(pid, 0)
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
        return pid if b"barpanel" in cmdline else 0
    except (OSError, ValueError):
        return 0


#: Fallback icons: names Adwaita lacks, tried in order.
_ICON_FALLBACKS = {
    "utilities-system-monitor-symbolic": ("utilities-system-monitor-symbolic",
                                          "org.gnome.SystemMonitor-symbolic",
                                          "computer-symbolic"),
}


def _icon(name: str) -> Gtk.Image:
    """An icon, with fallbacks for names Adwaita lacks (_ICON_FALLBACKS)."""
    names = _ICON_FALLBACKS.get(name)
    if names:
        return Gtk.Image.new_from_gicon(Gio.ThemedIcon.new_from_names(list(names)))
    return Gtk.Image.new_from_icon_name(name)


def _ensure_icon_theme() -> None:
    """See gui/util.py:ensure_icon_theme (the settings app uses it too)."""
    from .util import ensure_icon_theme
    ensure_icon_theme()


def run_with(values: dict[str, str], tab: str) -> int:
    pid = _running()
    if pid:
        # A panel is open: switch it to that tab (or close it if it is the same tab).
        _REQUEST.write_text(tab)
        os.kill(pid, signal.SIGUSR1)
        return 0
    _PID.write_text(str(os.getpid()))
    app = Gtk.Application(application_id=None)
    holder: dict[str, Panel] = {}

    def activate(_app) -> None:
        _ensure_icon_theme()
        holder["panel"] = Panel(app, values, tab)

    def on_signal() -> bool:
        try:
            wanted = _REQUEST.read_text().strip()
        except OSError:
            wanted = ""
        if "panel" in holder:
            holder["panel"].switch(wanted)
        return GLib.SOURCE_CONTINUE

    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, on_signal)
    app.connect("activate", activate)
    try:
        return app.run([])
    finally:
        try:
            if _PID.read_text().strip() == str(os.getpid()):
                _PID.unlink()
        except OSError:
            pass
