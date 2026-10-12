"""Theme transition: a smooth handover from the old desktop to the new one.

Switching themes used to black out the screen for a few seconds: the old setup's
bar and wallpaper daemon were stopped (rice.uninstall), and the new ones only came
up once the files were installed and start_session ran. In between, only
Hyprland's empty (black in most themes) background was on screen.

During the transition:

1. ``begin()`` captures each display's current image with grim and shows them in
   a separate process in fullscreen windows on the OVERLAY layer
   (gtk4-layer-shell). The first frame shows the old desktop frozen; right on top
   of it the boot animation's backdrop fades in and soup cooks on the focused
   display (gui/welcome.py SoupIntro): ingredients drop into the bowl and the ladle
   stirs until the theme is ready. Other displays only show the backdrop. If
   animations are off (gtk-enable-animations), a small label sits in the middle
   of the frozen screen.
2. Behind it, the old processes stop and the new ones start.
3. ``finish()`` signals completion. The overlay waits for the new theme's
   background layer (wallpaper) to appear and for the soup to cook at least until
   the steam rises, then fades out: the new desktop appears.

The overlay also closes on its own: if ``finish`` never arrives (the install
failed), when the launching process exits, at the latest after ``_MAX_SECONDS``.
A click also ends the transition immediately. RICE_TRANSITION=false in the
settings (Appearance → Animation) or HYPRSETUP_TRANSITION=0 disables it.

The overlay runs in a systemd scope independent of the install terminal: it is
not in the slice rice.uninstall stops (hyprsetup-rice.slice).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

#: The overlay's name in Hyprland (layerrule, hyprctl layers).
NAMESPACE = "hyprsetup-transition"
_LIB = "/usr/lib/libgtk4-layer-shell.so"
#: Even without any signal, the overlay goes away after this many seconds.
_MAX_SECONDS = 40
#: Longest wait after finish for the new wallpaper to appear.
_WAIT_BACKGROUND = 6.0
#: Wait after the wallpaper appears (the daemon's own transition, the bar).
_SETTLE = 0.7
_FADE = 0.6
#: Time for the animation backdrop to fade in over the frozen screen.
_COVER = 0.45
#: Minimum time the soup scene plays: ingredients drop, steam and the name rise
#: (gui/welcome.py: STEAM_AT + the steam fading in).
_MIN_SCENE = 4.2
#: Soup scene size as a fraction of the display height.
_SCENE_SIZE = 0.42


@dataclass
class Handle:
    directory: Path

    def finish(self) -> None:
        try:
            (self.directory / "done").touch()
        except OSError:
            pass


def _setting_on() -> bool:
    """RICE_TRANSITION from settings.conf (on if missing).

    The path is resolved here to avoid importing gui.state, which loads GTK
    (same file as gui/state.py:config_path).
    """
    from . import conffile
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    value = conffile.parse_file(Path(base) / "hyprsetup" / "settings.conf").get(
        "RICE_TRANSITION", "true")
    return value.strip().lower() not in ("false", "0", "no", "off")


def _enabled() -> bool:
    return (bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"))
            and os.environ.get("HYPRSETUP_TRANSITION", "1") != "0"
            and _setting_on()
            and shutil.which("grim") is not None
            and Path(_LIB).is_file())


def _hyprctl_json(*args: str):
    try:
        out = subprocess.run(["hyprctl", "-j", *args], capture_output=True,
                             text=True, timeout=5, check=False)
        return json.loads(out.stdout or "null")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def background_layers() -> dict[str, set[str]]:
    """Display → addresses of its background layers (wallpapers)."""
    found: dict[str, set[str]] = {}
    for monitor, data in (_hyprctl_json("layers") or {}).items():
        levels = (data or {}).get("levels", {})
        found[monitor] = {layer.get("address", "")
                          for level in ("0", "1") for layer in levels.get(level, [])
                          if layer.get("namespace") != NAMESPACE}
    return found


def begin(watch_pid: int | None = None, label: str = "Cooking your new theme…") -> Handle | None:
    """Freezes the screen and opens the overlay; returns once the overlay is shown.

    When ``watch_pid`` exits (e.g. the install command), the overlay goes away
    without waiting for finish. None if no transition is possible (no Hyprland,
    no grim…).
    """
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        # If Hyprland auto-reloads the config on every file as they change one by
        # one, the intermediate state has no display settings: monitors drop to the
        # default mode (60 Hz) and then come back. Every mode change blanks the
        # monitor in hardware; the overlay cannot cover that (the screen went black
        # and the animation was invisible). The single "hyprctl reload" at the end
        # of the install restores the new theme's own value anyway.
        subprocess.run(["hyprctl", "keyword", "misc:disable_autoreload", "true"],
                       capture_output=True, timeout=5, check=False)
    if not _enabled():
        return None
    monitors = [m for m in (_hyprctl_json("monitors") or [])
                if not m.get("disabled") and m.get("name")]
    if not monitors:
        return None
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir())
    directory = Path(tempfile.mkdtemp(prefix="hyprsetup-transition-", dir=runtime))

    def shoot(name: str) -> str | None:
        out = directory / f"{name}.png"
        done = subprocess.run(["grim", "-l", "0", "-o", name, str(out)],
                              capture_output=True, timeout=10, check=False)
        return name if done.returncode == 0 and out.is_file() else None

    with ThreadPoolExecutor(max_workers=len(monitors)) as pool:
        shot = [n for n in pool.map(shoot, [m["name"] for m in monitors]) if n]
    if not shot:
        shutil.rmtree(directory, ignore_errors=True)
        return None
    focused = next((m["name"] for m in monitors if m.get("focused")), shot[0])
    (directory / "info.json").write_text(json.dumps({
        "monitors": shot, "focused": focused, "label": label,
        "watch_pid": watch_pid or os.getpid(),
        "backgrounds": {k: sorted(v) for k, v in background_layers().items()},
    }), encoding="utf-8")
    # Keep Hyprland's layer animation (slide, pop-in) off the frozen image: the
    # same image sliding in looks like a flicker.
    subprocess.run(["hyprctl", "keyword", "layerrule",
                    f"no_anim on, match:namespace ^({NAMESPACE})$"],
                   capture_output=True, timeout=5, check=False)
    env = dict(os.environ, LD_PRELOAD=_LIB,
               PYTHONPATH=str(Path(__file__).resolve().parent.parent))
    argv = [sys.executable, "-m", "hyprsetup.transition", str(directory)]
    if shutil.which("systemd-run"):
        argv = ["systemd-run", "--user", "--scope", "--quiet", "--collect",
                f"--unit=hyprsetup-transition-{os.getpid()}", "--", *argv]
    try:
        subprocess.Popen(argv, env=env, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        shutil.rmtree(directory, ignore_errors=True)
        return None
    # If the old processes exit before the overlay is shown, black shows through again.
    deadline = time.monotonic() + 2.5
    while time.monotonic() < deadline and not (directory / "ready").exists():
        time.sleep(0.03)
    return Handle(directory)


# ------------------------------------------------------------ overlay -------
def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def run_overlay(directory: Path) -> int:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gdk, GLib, Gtk  # noqa: E402
    from gi.repository import Gtk4LayerShell as Layer  # noqa: E402

    from .gui.welcome import SoupIntro, _ease_out  # noqa: E402

    info = json.loads((directory / "info.json").read_text(encoding="utf-8"))
    before = {k: set(v) for k, v in info.get("backgrounds", {}).items()}
    started = time.monotonic()
    app = Gtk.Application(application_id=None)
    windows: list[Gtk.Window] = []
    phase = {"name": "wait", "since": started}
    intros: list[SoupIntro] = []
    settings = Gtk.Settings.get_default()
    animate = settings is None or settings.get_property("gtk-enable-animations")

    css = Gtk.CssProvider()
    css.load_from_string(
        "window.hyprsetup-transition { background: transparent; }"
        ".hyprsetup-transition .pill { background: alpha(black, 0.55);"
        " color: white; border-radius: 999px; padding: 10px 18px; }"
        # gui/welcome.py BG_TOP/BG_BOTTOM; drawn on the GPU (a fullscreen cairo
        # gradient on every frame was maxing out a CPU core).
        ".hyprsetup-transition .backdrop {"
        " background: linear-gradient(135deg, #24273a, #181926); }")
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def cover() -> float:
        """The boot animation's backdrop fades in over the frozen screen."""
        return _ease_out((time.monotonic() - started) / _COVER)

    def fade() -> None:
        if phase["name"] == "fade":
            return
        phase.update(name="fade", since=time.monotonic())

        def tick(widget, clock) -> bool:
            t = min(1.0, (time.monotonic() - phase["since"]) / _FADE)
            eased = t * t * (3 - 2 * t)
            for window in windows:
                window.get_child().set_opacity(1.0 - eased)
            if t >= 1.0:
                app.quit()
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE
        windows[0].add_tick_callback(tick)

    def new_background() -> bool:
        now = background_layers()
        return any(addresses - before.get(monitor, set())
                   for monitor, addresses in now.items())

    def poll() -> bool:
        now = time.monotonic()
        if phase["name"] == "fade":
            return GLib.SOURCE_REMOVE
        if now - started > _MAX_SECONDS:
            fade()
            return GLib.SOURCE_REMOVE
        if phase["name"] == "wait":
            if (directory / "done").exists() or not _alive(int(info["watch_pid"])):
                phase.update(name="background", since=now)
        if phase["name"] == "background":
            if new_background() or now - phase["since"] > _WAIT_BACKGROUND:
                phase.update(name="settle", since=now)
        # Let the soup cook at least until its steam and name appear (an animation
        # cut off midway looks like a stutter); a click skips the wait.
        scene_ok = all(intro.elapsed >= _MIN_SCENE for intro in intros)
        if phase["name"] == "settle" and now - phase["since"] >= _SETTLE and scene_ok:
            fade()
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def backdrop() -> Gtk.Widget:
        box = Gtk.Box(hexpand=True, vexpand=True, opacity=0.0)
        box.add_css_class("backdrop")

        def tick(widget, _clock) -> bool:
            widget.set_opacity(cover())
            return GLib.SOURCE_CONTINUE if cover() < 1.0 else GLib.SOURCE_REMOVE
        box.add_tick_callback(tick)
        return box

    def scene(height: int) -> SoupIntro:
        # The scene (300×390 units) is _SCENE_SIZE of the display height, centered:
        # at full height it covered the screen and looked too big.
        height = int(height * _SCENE_SIZE)
        intro = SoupIntro(fade, loop=True, subtitle=info.get("label", ""), max_fps=60)
        intro.set_hexpand(False)
        intro.set_vexpand(False)
        intro.set_halign(Gtk.Align.CENTER)
        intro.set_valign(Gtk.Align.CENTER)
        intro.set_size_request(height * 300 // 390, height)
        intro.set_draw_func(lambda _a, cr, w, h: intro.paint_scene(cr, w, h))
        intros.append(intro)
        return intro

    def pill() -> Gtk.Widget:
        box = Gtk.Box(spacing=10, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        box.add_css_class("pill")
        box.append(Gtk.Spinner(spinning=True))
        box.append(Gtk.Label(label=info.get("label", "")))
        return box

    def activate(_app) -> None:
        display = Gdk.Display.get_default()
        monitors = display.get_monitors()
        by_name = {monitors.get_item(i).get_connector(): monitors.get_item(i)
                   for i in range(monitors.get_n_items())}
        for name in info["monitors"]:
            monitor = by_name.get(name)
            if monitor is None:
                continue
            window = Gtk.Window(application=app)
            window.add_css_class("hyprsetup-transition")
            Layer.init_for_window(window)
            Layer.set_namespace(window, NAMESPACE)
            Layer.set_layer(window, Layer.Layer.OVERLAY)
            Layer.set_monitor(window, monitor)
            Layer.set_exclusive_zone(window, -1)
            Layer.set_keyboard_mode(window, Layer.KeyboardMode.NONE)
            for edge in (Layer.Edge.TOP, Layer.Edge.BOTTOM, Layer.Edge.LEFT, Layer.Edge.RIGHT):
                Layer.set_anchor(window, edge, True)
            overlay = Gtk.Overlay()
            # First the frozen image of the old screen: it shows instead of black the
            # moment the overlay opens, and the boot animation fades in over it.
            picture = Gtk.Picture.new_for_filename(str(directory / f"{name}.png"))
            picture.set_content_fit(Gtk.ContentFit.FILL)
            picture.set_can_shrink(True)
            overlay.set_child(picture)
            focused = name == info.get("focused")
            if not animate:
                if focused:
                    overlay.add_overlay(pill())
            else:
                overlay.add_overlay(backdrop())
                if focused:
                    overlay.add_overlay(scene(monitor.get_geometry().height))
            click = Gtk.GestureClick()
            click.connect("released", lambda *_a: fade())
            overlay.add_controller(click)
            window.set_child(overlay)
            windows.append(window)
        if not windows:
            app.quit()
            return

        # "ready" after one frame is drawn: begin() returns then.
        def drawn(*_a) -> None:
            GLib.timeout_add(60, lambda: (directory / "ready").touch() or False)
        windows[0].connect("map", drawn)
        for window in windows:
            window.present()
        GLib.timeout_add(120, poll)

    app.connect("activate", activate)
    try:
        app.run([])
    finally:
        shutil.rmtree(directory, ignore_errors=True)
    return 0

if __name__ == "__main__":
    sys.exit(run_overlay(Path(sys.argv[1])))
