"""ALT+Tab window switcher, with thumbnails + app icons.

``hyprsetup switcher`` (shortcut: ALT+Tab). Like on Windows and KDE: for each
window, that window's **current image** with the app's icon on top. If the
selected window is on another workspace, Hyprland switches there.

How thumbnails are captured
---------------------------
On Wayland, reading a window's contents from outside is not free-for-all;
the compositor has to allow it. Hyprland 0.56 offers the
``ext-image-copy-capture`` + ``ext-foreign-toplevel-image-capture-source``
protocols and grim 1.5 uses them via the ``-T <identifier>`` flag:

    grim -T "$(hyprctl -j activewindow | jq -r .stableId)" window.png

The identifier is the ``stableId`` field in ``hyprctl clients`` output. This
works even when the window is on ANOTHER workspace (i.e. not visible on screen
at all); do not confuse it with ``grim -g``, which crops a screen region and
can only capture what is visible at that moment.

Capturing takes ~50 ms per window. So the window opens with icons FIRST, and
the thumbnails drop into place as they arrive from background threads: no
waiting when you press ALT+Tab.

Why not a separate app
----------------------
Ready-made alt-tab apps (hyprshell etc.) need a constantly running background
process and are AUR-only. Here there is no process: it opens when the shortcut
is pressed and closes once a choice is made. A second copy is never opened at
the same time: pressing Tab again while ALT is held sends SIGUSR1 to the
existing window and the selection moves forward by one (see
``_single_instance``).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

#: Window class; windowrules.conf makes it floating and centered.
APP_ID = "dev.hyprsetup.Switcher"

#: Single instance. Every Tab press while ALT is held re-triggers Hyprland's
#: shortcut (it works regardless of focus); the second process sees this file,
#: signals the existing window and exits.
_LOCK = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp") / "hyprsetup-switcher.pid"

#: "Move the selection forward by one" requests (see hypr/scripts/windowswitch.py).
#: No signal is used: SIGUSR1 kills the process by default, and a signal arriving
#: while GTK was loading took down the switcher that was opening.
_QUEUE = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp") / "hyprsetup-switcher.queue"


def _queue_size() -> int:
    """Counter = the file's byte count: every press APPENDS one byte (O_APPEND).

    The counter used to be consumed with "read → write zero"; a press landing
    between the two (or on the post-selection reset) was lost, Tab
    occasionally did nothing and ALT+Tab had to be pressed again. Now the file
    is never truncated while the window is open; the reader keeps track of how
    far it has read (``SwitcherApp._seen``) itself.
    """
    try:
        return _QUEUE.stat().st_size
    except OSError:
        return 0


#: Hyprland's ALT-release shortcut (``windowswitch.py release``) touches this
#: file: it reports the release without depending on the window's focus
#: (see keybinds.release_combos).
_RELEASE = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp") / "hyprsetup-switcher.release"


def _released() -> bool:
    """Was ALT released AFTER the last Tab press?

    Every press writes to the queue, so the queue's mtime is the last press;
    a release older than that belongs to an earlier ALT and does not count.
    """
    try:
        return _RELEASE.stat().st_mtime_ns > _QUEUE.stat().st_mtime_ns
    except OSError:
        return False


def _append_request() -> None:
    try:
        fd = os.open(_QUEUE, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, b"1")
        finally:
            os.close(fd)
    except OSError:
        pass

#: Polling interval of the counter file. This is the delay between repeated
#: ALT+Tab presses and the selection moving; since the window is open only a
#: few seconds, the cost is one file read.
_QUEUE_POLL_MS = 40

#: Idle polling interval in preload mode. This is the delay between pressing
#: ALT+Tab and the window starting to draw; reading a 1-byte file comes from
#: the page cache, so the cost is too small to measure.
_IDLE_POLL_MS = 10

#: The preloaded copy starts with the session and its output goes nowhere;
#: when an error silently killed the timer, ALT+Tab would "stop working" for
#: no visible reason. Errors are written here (at most ~64 KB is kept).
_LOG = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "hyprsetup" / "switcher.log"


def _log_error(where: str) -> None:
    import time
    import traceback
    try:
        _LOG.parent.mkdir(parents=True, exist_ok=True)
        old = _LOG.read_text(encoding="utf-8")[-48_000:] if _LOG.exists() else ""
        _LOG.write_text(old + f"--- {time.strftime('%F %T')} {where}\n"
                        + traceback.format_exc() + "\n", encoding="utf-8")
    except OSError:
        pass

_CSS = b"""
.hs-sw-card {
    background-color: alpha(currentColor, 0.05);
    border: 2px solid transparent;
    border-radius: 12px;
    padding: 8px;
}
.hs-sw-card--on {
    background-color: alpha(@accent_bg_color, 0.20);
    border-color: @accent_bg_color;
}
.hs-sw-shot {
    background-color: alpha(currentColor, 0.08);
    border-radius: 8px;
}
.hs-sw-ws {
    background-color: alpha(currentColor, 0.15);
    border-radius: 6px;
    padding: 0 6px;
    font-size: 0.8em;
}
.hs-sw-title { font-size: 0.9em; }
"""


def _hyprctl(*args: str):
    try:
        out = subprocess.run(["hyprctl", "-j", *args], check=True, timeout=5,
                             capture_output=True, text=True).stdout
        return json.loads(out or "null")
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _hyprctl_batch() -> tuple[list, dict, list]:
    """clients + activeworkspace + monitors in a SINGLE process.

    Three separate ``hyprctl`` calls mean starting three processes (~11 ms);
    ``--batch`` returns them all over one connection (~4 ms). ALT+Tab's total
    budget is around 200 ms, so the difference is noticeable.

    The output is CONSECUTIVE JSON documents separated by blank lines; a
    single json.loads() cannot read it, so they are decoded one by one with
    raw_decode.
    """
    try:
        out = subprocess.run(
            ["hyprctl", "--batch", "j/clients ; j/activeworkspace ; j/monitors"],
            check=True, timeout=5, capture_output=True, text=True).stdout
    except (OSError, subprocess.SubprocessError):
        return [], {}, []

    decoder = json.JSONDecoder()
    documents = []
    index = 0
    while index < len(out):
        while index < len(out) and out[index].isspace():
            index += 1
        if index >= len(out):
            break
        try:
            value, index = decoder.raw_decode(out, index)
        except ValueError:
            break
        documents.append(value)
    while len(documents) < 3:
        documents.append(None)
    clients, workspace, monitors = documents[:3]
    return (clients or [], workspace or {}, monitors or [])


def _focus_commands(client: dict) -> str:
    """Commands to switch to the selected window (for ``hyprctl --batch``).

    XWayland windows (War Thunder, Proton/Wine games) additionally get an ALT
    press-and-release: when ALT+Tab is pressed, the ALT press goes to the game
    but the release goes to the switcher. Games that ignore key events while
    unfocused kept thinking ALT was held; back in the game Tab became
    "ALT+Tab", Caps became "ALT+Caps" and nothing worked.
    """
    target = f"address:{client['address']}"
    commands = f"dispatch focuswindow {target}"
    if client.get("xwayland"):
        commands += f" ; dispatch sendshortcut , Alt_L, {target}"
    return commands


def windows(values: dict[str, str], data=None) -> list[dict]:
    """Window list filtered and sorted according to the settings.

    Same rules as ``windowswitch.py``: most recently used first, the focused
    window last (so ALT+Tab → Enter means "previous window").
    """
    clients, workspace, monitors = data if data is not None else _hyprctl_batch()
    scope = values.get("SWITCHER_SCOPE", "all")
    special = values.get("SWITCHER_SPECIAL", "false") == "true"

    active_ws = workspace.get("id", -1)
    active_monitor = -1
    for monitor in monitors:
        if monitor.get("focused"):
            active_monitor = monitor.get("id", -1)

    out = []
    for client in clients:
        if not client.get("mapped", True):
            continue
        if client.get("class") == APP_ID:
            continue                      # the switcher's own window
        workspace = client.get("workspace") or {}
        if not special and str(workspace.get("name", "")).startswith("special"):
            continue
        if scope == "current" and workspace.get("id") != active_ws:
            continue
        if scope == "monitor" and client.get("monitor") != active_monitor:
            continue
        out.append(client)

    def key(client: dict):
        history = client.get("focusHistoryID", 0)
        recent = (1, 0) if history == 0 else (0, history)
        if values.get("SWITCHER_SORT") == "workspace":
            return ((client.get("workspace") or {}).get("id", 0), recent)
        return recent

    out.sort(key=key)
    return out


#: Result of the full .desktop scan (class → icon). Built only when needed:
#: Gio.AppInfo.get_all() parses 200 apps (~13 ms) and is unnecessary for most
#: window classes; the "kitty" class's icon can be read straight from
#: kitty.desktop.
_ICON_INDEX: dict[str, Gio.Icon] | None = None


def _icon_index() -> dict[str, Gio.Icon]:
    """``class`` → icon. Scans StartupWMClass and the .desktop id."""
    global _ICON_INDEX
    if _ICON_INDEX is not None:
        return _ICON_INDEX
    index: dict[str, Gio.Icon] = {}
    for info in Gio.AppInfo.get_all():
        icon = info.get_icon()
        if icon is None:
            continue
        keys = []
        wm_class = info.get_string("StartupWMClass") if hasattr(info, "get_string") else None
        if wm_class:
            keys.append(wm_class)
        ident = info.get_id() or ""
        if ident.endswith(".desktop"):
            keys.append(ident[: -len(".desktop")])
        for name in keys:
            index.setdefault(name.lower(), icon)
    _ICON_INDEX = index
    return index


def _icon_for(client: dict) -> Gio.Icon:
    """The window's icon, in four steps from cheap to expensive.

    1. Read ``<class>.desktop`` directly (one file, ~0 ms).
    2. Is there an icon with the same name in the icon theme?
    3. The last part of the class name: "one.ablaze.floorp" → "floorp".
    4. Last resort: scan all .desktop files (StartupWMClass match).
    """
    theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
    names = [n for n in (client.get("class"), client.get("initialClass")) if n]

    def desktop_icon(basename: str):
        # PyGObject does NOT return None if the file is missing: it raises
        # TypeError("constructor returned NULL").
        try:
            info = Gio.DesktopAppInfo.new(f"{basename}.desktop")
        except TypeError:
            return None
        return info.get_icon() if info is not None else None

    for name in names:
        icon = desktop_icon(name)
        if icon is not None:
            return icon
        tail = name.rsplit(".", 1)[-1]
        if tail != name:
            icon = desktop_icon(tail)
            if icon is not None:
                return icon
        for candidate in (name.lower(), tail.lower()):
            if theme is not None and theme.has_icon(candidate):
                return Gio.ThemedIcon.new(candidate)

    index = _icon_index()
    for name in names:
        icon = index.get(name.lower()) or index.get(name.rsplit(".", 1)[-1].lower())
        if icon is not None:
            return icon
    return Gio.ThemedIcon.new("application-x-executable")


def _capture(stable_id: str, directory: Path) -> Path | None:
    """Current image of a single window via ``grim -T``.

    Scaling (``-s``) is deliberately NOT used: grim downscales itself after
    capturing, which measured twice as slow (47 ms → 103 ms). Downscaling on
    the GTK side is free anyway.
    """
    target = directory / f"{stable_id}.png"
    try:
        result = subprocess.run(
            ["grim", "-T", str(stable_id), "-t", "png", "-l", "1", str(target)],
            capture_output=True, timeout=8, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return target if result.returncode == 0 and target.is_file() else None


def _focused_monitor(monitors=None) -> tuple[int, int]:
    """(width, height) of the focused monitor, with scale applied."""
    for monitor in (monitors if monitors is not None else _hyprctl("monitors") or []):
        if monitor.get("focused"):
            scale = float(monitor.get("scale") or 1) or 1
            return (int(monitor.get("width", 1920) / scale),
                    int(monitor.get("height", 1080) / scale))
    return (1920, 1080)


class SwitcherWindow(Adw.ApplicationWindow):
    def __init__(self, app, clients: list[dict], values: dict[str, str],
                 tmpdir: Path, monitors=None):
        super().__init__(application=app, title="Windows")
        self.clients = clients
        self.index = 0
        self._closing = False
        self._active_ticks = 0
        self._tmpdir = tmpdir
        self._pictures: dict[str, Gtk.Picture] = {}

        try:
            width = max(160, min(480, int(values.get("SWITCHER_THUMB_WIDTH", "260"))))
        except ValueError:
            width = 260
        self._thumb = (width, int(width * 9 / 16))
        self._thumbs_on = values.get("SWITCHER_THUMBS", "true") == "true"

        # How many cards fit side by side? A fixed cap (5) overflowed the
        # screen: with 7 windows the window came out 3754 px wide on a
        # 1920 px screen. The cap is computed from the screen; the rest wrap.
        screen_w, screen_h = _focused_monitor(monitors)
        usable = int(screen_w * 0.92)
        # NOTE: the variable CANNOT be named "card": the loop below uses that
        # name for the card widget, and by the time set_default_size ran it
        # held a Gtk.Box instead of a number.
        card_width = self._thumb[0] + 34       # padding + border + spacing
        columns = max(1, min(len(clients), usable // card_width))

        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
                           column_spacing=10, row_spacing=10,
                           homogeneous=True, valign=Gtk.Align.CENTER,
                           halign=Gtk.Align.CENTER,
                           min_children_per_line=columns,
                           max_children_per_line=columns)
        flow.set_margin_top(14); flow.set_margin_bottom(14)
        flow.set_margin_start(14); flow.set_margin_end(14)

        self._cards: list[Gtk.Widget] = []
        for position, client in enumerate(clients):
            card = self._build_card(client)
            click = Gtk.GestureClick()
            click.connect("released", self._on_click, position)
            card.add_controller(click)
            flow.append(card)
            self._cards.append(card)

        rows = (len(clients) + columns - 1) // columns
        scroller = Gtk.ScrolledWindow(child=flow)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_content(scroller)
        # Height: card height ≈ thumbnail + two lines of text.
        self.set_default_size(
            min(usable, columns * card_width + 28),
            min(int(screen_h * 0.85), rows * (self._thumb[1] + 90) + 28))
        self._refresh_selection()

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        keys.connect("key-released", self._on_key_release)
        self.add_controller(keys)

        # Cancel if the mouse goes to another window or focus is lost: a
        # switcher stuck on screen is a trap for a user who doesn't know how to
        # close it.
        self.connect("notify::is-active", self._on_active_change)

    # -------------------------------------------------------------- cards --
    def _build_card(self, client: dict) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.add_css_class("hs-sw-card")
        # The thumbnail sets the card's width; a long window title must not
        # stretch the card (and the window).
        box.set_size_request(self._thumb[0], -1)
        box.set_hexpand(False)

        shot = Gtk.Picture(content_fit=Gtk.ContentFit.COVER,
                           can_shrink=True, hexpand=False)
        shot.set_size_request(*self._thumb)
        shot.add_css_class("hs-sw-shot")
        self._pictures[str(client.get("stableId"))] = shot

        icon = Gtk.Image.new_from_gicon(_icon_for(client))
        icon.set_pixel_size(44)
        icon.set_halign(Gtk.Align.START)
        icon.set_valign(Gtk.Align.END)
        icon.set_margin_start(6)
        icon.set_margin_bottom(6)

        overlay = Gtk.Overlay(child=shot)
        overlay.add_overlay(icon)
        box.append(overlay)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        workspace = Gtk.Label(label=str((client.get("workspace") or {}).get("name", "?")))
        workspace.add_css_class("hs-sw-ws")
        head.append(workspace)
        name = Gtk.Label(label=client.get("class") or "?", xalign=0,
                         hexpand=True)
        name.add_css_class("heading")
        name.set_ellipsize(3)             # Pango.EllipsizeMode.END
        # width_chars=1 + ellipsize: the label's NATURAL width comes from this
        # value, not the text, so a long class name cannot widen the card.
        name.set_width_chars(1)
        name.set_max_width_chars(max(8, self._thumb[0] // 11))
        head.append(name)
        box.append(head)

        title = Gtk.Label(label=(client.get("title") or "").strip(), xalign=0)
        title.add_css_class("dim-label")
        title.add_css_class("hs-sw-title")
        title.set_ellipsize(3)
        title.set_width_chars(1)
        title.set_max_width_chars(max(12, self._thumb[0] // 9))
        box.append(title)
        return box

    def load_thumbnails(self) -> None:
        """Capture thumbnails in the background and place them as they arrive."""
        if not self._thumbs_on or not GLib.find_program_in_path("grim"):
            return

        def work(client: dict) -> None:
            stable_id = str(client.get("stableId"))
            path = _capture(stable_id, self._tmpdir)
            if path is not None:
                GLib.idle_add(self._set_thumb, stable_id, str(path))

        pool = ThreadPoolExecutor(max_workers=4)
        for client in self.clients:
            pool.submit(work, client)
        pool.shutdown(wait=False)

    def _set_thumb(self, stable_id: str, path: str) -> bool:
        picture = self._pictures.get(stable_id)
        if picture is not None:
            try:
                picture.set_paintable(Gdk.Texture.new_from_filename(path))
            except GLib.Error:
                pass
        return False                      # GLib.idle_add: run once

    # ---------------------------------------------------------- selection --
    def _refresh_selection(self) -> None:
        for position, card in enumerate(self._cards):
            if position == self.index:
                card.add_css_class("hs-sw-card--on")
            else:
                card.remove_css_class("hs-sw-card--on")

    def advance(self, step: int = 1) -> None:
        if self._cards:
            self.index = (self.index + step) % len(self._cards)
            self._refresh_selection()

    def activate_selection(self) -> None:
        if self._closing:
            return
        application = self.get_application()
        # Tabs pressed right before ALT may not have been polled yet.
        if application is not None:
            application.consume_requests()
        self._closing = True
        client = self.clients[self.index]
        preload = getattr(application, "preload", False)
        # The lock is released FIRST: focuswindow switches workspace and the
        # user may press ALT+Tab right away; if the lock were still there the
        # new call would send its command to this closing window. In preload
        # mode the lock represents the process, so it stays.
        if not preload:
            _LOCK.unlink(missing_ok=True)
            _QUEUE.unlink(missing_ok=True)
        subprocess.run(["hyprctl", "--batch", _focus_commands(client)], check=False)
        self.close()
        if application is not None and not preload:
            application.quit()

    # ------------------------------------------------------------- events --
    def _on_click(self, _gesture, _n, _x, _y, position: int) -> None:
        self.index = position
        self.activate_selection()

    def _on_key(self, _controller, keyval, _code, state) -> bool:
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        if keyval in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab, Gdk.KEY_Right,
                      Gdk.KEY_Down):
            self.advance(-1 if (shift or keyval == Gdk.KEY_ISO_Left_Tab) else 1)
            return True
        if keyval in (Gdk.KEY_Left, Gdk.KEY_Up):
            self.advance(-1)
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            self.activate_selection()
            return True
        if keyval == Gdk.KEY_Escape:
            self._closing = True
            self.close()
            return True
        # 1..9: jump straight to that card.
        if Gdk.KEY_1 <= keyval <= Gdk.KEY_9:
            position = keyval - Gdk.KEY_1
            if position < len(self._cards):
                self.index = position
                self.activate_selection()
            return True
        return False

    def _on_key_release(self, _controller, keyval, _code, _state) -> bool:
        # Windows/KDE behavior: releasing ALT switches to the selected window.
        # Since the shortcut fires while ALT is held, the release event lands
        # in this window (Wayland reports held keys when granting focus).
        if keyval in (Gdk.KEY_Alt_L, Gdk.KEY_Alt_R, Gdk.KEY_Meta_L,
                      Gdk.KEY_Meta_R):
            self.activate_selection()
            return True
        return False

    def modifiers_released(self) -> bool:
        """Has ALT (or the shortcut's other modifier) been released?

        The release event only arrives while the window has focus. If ALT was
        released before the window got focus, the event went to the previous
        window and the switcher stayed open on screen. When focus arrives,
        Wayland reports the current modifier keys; checking them catches the
        missed release.
        """
        if not self.is_active():
            self._active_ticks = 0
            return False
        # On the first poll after focus arrives the state may not be updated yet.
        self._active_ticks += 1
        if self._active_ticks < 2:
            return False
        seat = self.get_display().get_default_seat()
        keyboard = seat.get_keyboard() if seat is not None else None
        if keyboard is None:
            return False
        held = (Gdk.ModifierType.ALT_MASK | Gdk.ModifierType.SUPER_MASK
                | Gdk.ModifierType.META_MASK | Gdk.ModifierType.CONTROL_MASK)
        return not keyboard.get_modifier_state() & held

    def _on_active_change(self, *_args) -> None:
        if not self.is_active() and not self._closing:
            self._closing = True
            self.close()

    def watch_workspace(self) -> None:
        """Close the window if the workspace changes.

        Focus loss alone was not enough: after a selection switched to another
        workspace, this window could stay open INVISIBLY on the old workspace
        and later ALT+Tabs moved it around. Hyprland's event socket
        (.socket2.sock) reports this for free: no polling, no hyprctl call
        every second.
        """
        signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
        runtime = os.environ.get("XDG_RUNTIME_DIR")
        if not signature or not runtime:
            return
        path = Path(runtime) / "hypr" / signature / ".socket2.sock"
        if not path.exists():
            return

        def listen() -> None:
            import socket
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                    sock.connect(str(path))
                    buffer = b""
                    while True:
                        chunk = sock.recv(4096)
                        if not chunk:
                            return
                        buffer += chunk
                        while b"\n" in buffer:
                            line, buffer = buffer.split(b"\n", 1)
                            event = line.decode("utf-8", "replace")
                            if event.startswith(("workspace>>", "focusedmon>>")):
                                GLib.idle_add(self._close_from_thread)
                                return
            except OSError:
                return

        thread = threading.Thread(target=listen, daemon=True)
        thread.start()

    def _close_from_thread(self) -> bool:
        if not self._closing:
            self._closing = True
            self.close()
        return False


class SwitcherApp(Adw.Application):
    """The switcher app.

    Runs in two modes:

    * **one-shot** (default): starts when the shortcut is pressed, draws the
      window, and the process ends once a choice is made.
    * **preload** (``SWITCHER_PRELOAD``): starts invisibly with the session and
      only builds the window on ALT+Tab. Loading GTK (~95 ms) and app setup
      are paid once, at login; when the shortcut is pressed only drawing the
      window is left.
    """

    def __init__(self, values: dict[str, str], clients: list[dict] | None,
                 tmpdir: Path | None, monitors=None, preload: bool = False):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.values = values
        self.clients = clients
        self.tmpdir = tmpdir
        self.monitors = monitors
        self.preload = preload
        self.window: SwitcherWindow | None = None
        self._own_tmp: tempfile.TemporaryDirectory | None = None
        #: Presses in the counter file up to here have been handled (see _queue_size).
        self._seen = 0

    def _take_requests(self) -> int:
        size = _queue_size()
        if size < self._seen:            # the file was recreated
            self._seen = 0
        pending = size - self._seen
        self._seen = size
        return pending

    def consume_requests(self) -> None:
        if self.window is not None:
            for _ in range(self._take_requests()):
                self.window.advance(1)

    def do_activate(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(_CSS)
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        if self.preload:
            # No window: hold the app so it stays alive, and poll the request
            # counter. The polling interval is the only delay between pressing
            # ALT+Tab and the window starting to draw.
            self.hold()
            GLib.timeout_add(_IDLE_POLL_MS, self._wait_for_request)
            # Build the icon index while idle, so the first ALT+Tab does not
            # pay for the 13 ms .desktop scan.
            GLib.idle_add(lambda: (_icon_index(), False)[1])
            return

        self.show_window()
        GLib.timeout_add(_QUEUE_POLL_MS, self._drain_queue)

    # ------------------------------------------------------------- window --
    def show_window(self, advance: int = 0) -> None:
        """Build and show the window (a new one on every call in preload mode)."""
        if self.clients is None or self.preload:
            data = _hyprctl_batch()
            self.clients = windows(self.values, data)
            self.monitors = data[2]
            if not self.clients:
                return
            self._own_tmp = tempfile.TemporaryDirectory(
                prefix="hyprsetup-switcher-")
            self.tmpdir = Path(self._own_tmp.name)

        self.window = SwitcherWindow(self, self.clients, self.values,
                                     self.tmpdir, self.monitors)
        self.window.connect("close-request", self._on_window_closed)
        self.window.present()
        for _ in range(advance):
            self.window.advance(1)
        # Capturing starts AFTER the window is visible, so whoever pressed
        # ALT+Tab is not staring at an empty screen.
        GLib.idle_add(self.window.load_thumbnails)
        self.window.watch_workspace()

    def _on_window_closed(self, *_args) -> bool:
        """In preload mode the window closes but the PROCESS keeps running."""
        if not self.preload:
            return False
        self.window = None
        if self._own_tmp is not None:
            self._own_tmp.cleanup()
            self._own_tmp = None
        self.clients = None
        GLib.timeout_add(_IDLE_POLL_MS, self._wait_for_request)
        return False

    def _wait_for_request(self) -> bool:
        """While idle: show the window when the counter grows.

        This poll is the preloaded copy's ONLY lifeline: if it returns False
        and is not re-armed, the process lives on but never hears ALT+Tab
        again (presses pile up in the counter file). So polling continues even
        when the window cannot be opened (no windows to list, or an error while
        building it).
        """
        if self.window is not None:
            return False                  # window is open, _drain_queue is in charge
        pending = self._take_requests()
        if pending <= 0:
            return True
        # The first press opens the window (the selection already sits on the
        # "previous window"); extra presses that piled up advance the selection.
        try:
            self.show_window(advance=pending - 1)
        except Exception:
            _log_error("show_window")
            if self.window is not None:
                # When the half-built window closes, _on_window_closed re-arms
                # the poll; do not start a second one here.
                self._close_broken_window()
                return False
            self.clients = None
            return True
        if self.window is None:
            return True                   # no windows to list: keep waiting
        GLib.timeout_add(_QUEUE_POLL_MS, self._drain_queue)
        return False

    def _close_broken_window(self) -> None:
        window = self.window
        try:
            window._closing = True
            window.close()
        except Exception:
            _log_error("close")
            self._on_window_closed()

    def _drain_queue(self) -> bool:
        """Apply pending "move forward" requests."""
        if self.window is None or self.window._closing:
            return False
        try:
            self.consume_requests()
            if _released() or self.window.modifiers_released():
                self.window.activate_selection()
                return False
        except Exception:
            _log_error("drain_queue")
            if self.window is not None:
                self._close_broken_window()
            return False
        return True                       # keep polling


def _alive(pid: int) -> bool:
    """Is the PID really OUR switcher?

    Checking "does the process exist" is not enough: the lock file can be left
    behind after a crash or SIGKILL, and another program may have taken that
    PID in the meantime. Sending SIGUSR1 to it is useless at best and kills it
    at worst (SIGUSR1's default action is to terminate).
    """
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().decode("utf-8", "replace")
    except OSError:
        return False
    # windowswitch.py writes the lock BEFORE execvp; in that window the command
    # line does not contain "switcher" yet, so either name is good enough.
    return "hyprsetup" in cmdline or "windowswitch" in cmdline


def _single_instance() -> bool:
    """If a switcher is already open, tell it 'forward by one' and return False.

    On the normal path ``hypr/scripts/windowswitch.py`` has ALREADY written the
    lock (without waiting for GTK to load, in ~19 ms), and since ``execvp``
    keeps the PID, that lock is ours. This function only remains for a direct
    ``hyprsetup switcher`` call.
    """
    try:
        pid = int(_LOCK.read_text().split()[0])
    except (OSError, ValueError, IndexError):
        pid = 0
    if pid == os.getpid():
        return True                       # the lock was taken by the script
    if pid > 0 and _alive(pid):
        # A switcher is open: write the request to the counter, it reads it
        # (no signal is used; see the _QUEUE comment).
        _append_request()
        return False
    try:
        workspace = (_hyprctl("activeworkspace") or {}).get("id", 0)
        _LOCK.write_text(f"{os.getpid()} {workspace}")
        _QUEUE.write_text("")
    except OSError:
        pass
    return True


def run_with(values: dict[str, str]) -> int:
    """Run with settings passed in READY-MADE: ALT+Tab's normal path.

    ``hypr/scripts/windowswitch.py`` carries all settings embedded from the
    template and calls this function IN ITS OWN PROCESS. That skips a separate
    python startup (~20 ms), the ``hyprsetup`` bash wrapper (~5 ms),
    ``hyprsetup.__main__`` + argparse (~19 ms) and parsing settings.conf
    (~8 ms) entirely.
    """
    if not _single_instance():
        return 0

    data = _hyprctl_batch()
    clients = windows(values, data)
    if not clients:
        subprocess.run(["notify-send", "-a", "Window switcher",
                        "No windows to switch to"], check=False)
        _LOCK.unlink(missing_ok=True)
        _QUEUE.unlink(missing_ok=True)
        return 0

    GLib.set_prgname(APP_ID)
    with tempfile.TemporaryDirectory(prefix="hyprsetup-switcher-") as tmp:
        try:
            return SwitcherApp(values, clients, Path(tmp), data[2]).run([])
        finally:
            _LOCK.unlink(missing_ok=True)
            _QUEUE.unlink(missing_ok=True)


def run_preload(values: dict[str, str]) -> int:
    """``--preload``: invisible waiting copy (started with the session)."""
    if _LOCK.exists():
        try:
            pid = int(_LOCK.read_text().split()[0])
        except (OSError, ValueError, IndexError):
            pid = 0
        if pid and pid != os.getpid() and _alive(pid):
            return 0                      # a waiting copy already exists
    try:
        _LOCK.write_text(f"{os.getpid()} preload")
        _QUEUE.write_text("")
    except OSError:
        return 1

    GLib.set_prgname(APP_ID)
    try:
        return SwitcherApp(values, None, None, preload=True).run([])
    finally:
        _LOCK.unlink(missing_ok=True)
        _QUEUE.unlink(missing_ok=True)


def run(root: Path, catalog_path: Path) -> int:
    """``hyprsetup switcher``: entry point that reads settings from settings.conf.

    This is NOT the path the shortcut uses (see run_with): it is for people
    running the app by hand and for cases where the script cannot find the
    import path.
    """
    # Heavy imports (state → apply → render) are only needed on this path.
    from .state import SetupState, config_candidates
    from ..catalog import Catalog

    catalog_path = Path(catalog_path)
    if not catalog_path.is_absolute():
        catalog_path = Path(root) / catalog_path
    state = SetupState(Catalog.load(catalog_path))
    for candidate in config_candidates():
        if state.load_conf(candidate):
            break
    return run_with(state.values)
