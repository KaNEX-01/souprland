"""Login screen: SDDM themes (community catalog + editor) and Plasma Login.

Backend of the settings app's "Login Screen" page; does not touch GTK.

The login screen's files live under ``/usr/share``, ``/etc`` and ``/var/lib``
(the greeter runs as a separate user and cannot read the home directory). This
module writes nothing as root: it prepares the files to write in the user's cache
(``~/.cache/hyprsetup/login``) and returns a shell script that puts them in place.
The UI runs the script in a visible terminal, where sudo asks for the password
(the app's general rule: it never asks for sudo itself).

SDDM edits are not written to the theme's file: SDDM reads ``<ConfigFile>.user`` on
top of the theme's settings (sddm ``ThemeConfig::setTo``). The chosen preset + the
user's changes go into that file; package updates do not overwrite it. Limitation:
SDDM ignores EMPTY values in ``.user``, so a key left empty by a preset cannot clear
a non-empty default value.
"""

from __future__ import annotations

import configparser
import fnmatch
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import tomllib
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

SDDM_THEMES = Path("/usr/share/sddm/themes")
SDDM_THEME_CONF = Path("/etc/sddm.conf.d/20-theme.conf")
PLASMALOGIN_CONF = Path("/etc/plasmalogin.conf")
PLASMALOGIN_HOME = Path("/var/lib/plasmalogin")
DM_LINK = Path("/etc/systemd/system/display-manager.service")

#: Display manager service → display name.
MANAGERS = {
    "sddm": "SDDM",
    "plasmalogin": "Plasma Login",
    "ly": "ly",
    "greetd": "greetd",
    "gdm": "GDM",
    "lightdm": "LightDM",
}

#: Palette roles (COL_<role> in the output of themes.derive).
ROLES = ("BG", "BG_DARK", "SURFACE", "FG", "SUBTEXT", "ACCENT", "ACCENT2",
         "RED", "GREEN", "YELLOW", "CYAN")

_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".mp4", ".webm",
              ".mkv", ".mov", ".avi", ".m4v")
_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


# ---------------------------------------------------------- display manager
def current_manager() -> str:
    """Active display manager (the unit display-manager.service points to)."""
    try:
        target = os.readlink(DM_LINK)
    except OSError:
        return ""
    return Path(target).name.removesuffix(".service")


def manager_installed(name: str) -> bool:
    return any(Path(d, f"{name}.service").is_file()
               for d in ("/usr/lib/systemd/system", "/etc/systemd/system"))


def switch_script(target: str) -> str:
    """Commands that switch the display manager (effective after reboot)."""
    current = current_manager()
    lines = []
    if current and current != target:
        lines.append(f"sudo systemctl disable {shlex.quote(current)}.service")
    lines.append(f"sudo systemctl enable {shlex.quote(target)}.service")
    lines.append(f"echo 'Login screen: {MANAGERS.get(target, target)} — "
                 "takes effect on next boot.'")
    return "\n".join(lines)


# --------------------------------------------------------------- Plymouth
PLYMOUTH_THEMES = Path("/usr/share/plymouth/themes")
PLYMOUTH_CONFS = (Path("/etc/plymouth/plymouthd.conf"),
                  Path("/usr/share/plymouth/plymouthd.defaults"))


def plymouth_installed() -> bool:
    return shutil.which("plymouth-set-default-theme") is not None


def plymouth_themes() -> list[str]:
    """Installed boot animation themes (directories with ``<name>/<name>.plymouth``)."""
    try:
        return sorted(d.name for d in PLYMOUTH_THEMES.iterdir()
                      if (d / f"{d.name}.plymouth").is_file())
    except OSError:
        return []


def plymouth_current() -> str:
    """Active theme: /etc/plymouth/plymouthd.conf, otherwise the distro default.

    plymouth-set-default-theme looks at these two files too; [Daemon] Theme= is
    read from the first file found.
    """
    for conf in PLYMOUTH_CONFS:
        try:
            text = conf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        section = ""
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("["):
                section = line
            elif section == "[Daemon]" and line.startswith("Theme="):
                return line.split("=", 1)[1].strip()
    return ""


#: Short description of each boot animation (subtitle of the gallery card).
PLYMOUTH_DESCRIPTIONS = {
    "bgrt": "Motherboard vendor logo with a small spinning ring below",
    "cachyos": "Motherboard logo, CachyOS text and a spinning ring below",
    "cachyos-bootanimation": "Animated CachyOS logo growing in the center",
    "spinner": "Plain spinning ring on black, distro name below",
    "spinfinity": "Spinning infinity sign on a blue background",
    "glow": "Filling pie chart, then a glowing logo",
    "fade-in": "Twinkling stars, a logo fading in and out",
    "solar": "Blue space with a flaring star on the right",
    "script": "Logo slowly pulsing on a blue background",
    "details": "No animation: kernel and service messages scroll by",
    "text": "Text mode: distro name and a three-box counter",
    "tribar": "Text mode: three-color progress bar at the bottom",
}

PLYMOUTH_LOGOS = (Path("/usr/share/pixmaps/system-logo-white.png"),
                  Path("/usr/share/pixmaps/archlinux-logo.png"))
BGRT = Path("/sys/firmware/acpi/bgrt")


@dataclass
class PlymouthScene:
    """What a theme draws on screen at boot — as data, for the preview.

    Positions follow Plymouth's alignment rule: ``(h, v)`` = the image's top-left
    corner is at ``h * (screen - image)``. Images are drawn at their natural pixel
    size, so the preview scale is ``preview_width / 1920``.
    """
    theme: str
    kind: str                 # two-step | fade-in | solar | script | details | text | tribar
    description: str = ""
    bg_top: str = "#000000"
    bg_bottom: str = "#000000"
    #: Motherboard logo (ACPI BGRT) and its top-left corner relative to screen width.
    firmware: Path | None = None
    firmware_box: tuple[float, float, float] = (0.0, 0.0, 0.0)   # x, y, width (fraction)
    watermark: Path | None = None
    watermark_align: tuple[float, float] = (0.5, 0.96)
    frames: list[Path] = field(default_factory=list)
    frames_align: tuple[float, float] = (0.5, 0.7)
    #: Frame shown in the still preview: the middle of the main animation.
    still: int = 0
    logo: Path | None = None          # distro logo (fade-in, script)
    star: Path | None = None          # fade-in star / solar sun


def _plymouth_color(value: str, default: str) -> str:
    digits = value.strip().lower().removeprefix("0x")
    if not re.fullmatch(r"[0-9a-f]{6,8}", digits):
        return default
    return "#" + digits[-6:]


def _numbered(directory: Path, prefix: str) -> list[Path]:
    found = []
    for path in directory.glob(f"{prefix}*.png"):
        number = path.stem[len(prefix):]
        if number.isdigit():
            found.append((int(number), path))
    return [p for _n, p in sorted(found)]


def _bgrt_box() -> tuple[Path | None, tuple[float, float, float]]:
    """Motherboard logo and its place on screen (fractions). The logo is centered on
    the screen; width is 2*xoffset + logo width, height is assumed 16:9."""
    image = BGRT / "image"
    try:
        head = image.read_bytes()[:26]
        x = int((BGRT / "xoffset").read_text().strip())
        y = int((BGRT / "yoffset").read_text().strip())
    except (OSError, ValueError):
        return None, (0.0, 0.0, 0.0)
    if head[:2] != b"BM":
        return None, (0.0, 0.0, 0.0)
    width = int.from_bytes(head[18:22], "little", signed=True)
    screen_w = 2 * x + width
    if width <= 0 or screen_w <= 0:
        return None, (0.0, 0.0, 0.0)
    screen_h = screen_w * 9 / 16
    return image, (x / screen_w, y / screen_h, width / screen_w)


def distro_name() -> str:
    """/etc/os-release NAME — text-mode themes (text, tribar) print this."""
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            if line.startswith("NAME="):
                return line.split("=", 1)[1].strip().strip('"') or "Linux"
    except OSError:
        pass
    return "Linux"


def plymouth_scene(theme: str, directory: Path | None = None) -> PlymouthScene:
    """If ``directory`` is given the theme is read from there (an uninstalled draft:
    My theme); since ImageDir in the .plymouth points to the install path, the
    images are taken from that folder too."""
    staged = directory is not None
    directory = Path(directory) if staged else PLYMOUTH_THEMES / theme
    conf = configparser.ConfigParser(strict=False, interpolation=None)
    conf.optionxform = str
    try:
        conf.read(directory / f"{theme}.plymouth", encoding="utf-8")
    except (configparser.Error, UnicodeDecodeError):
        pass
    module = conf.get("Plymouth Theme", "ModuleName", fallback="")
    scene = PlymouthScene(
        theme=theme, kind=module,
        description=PLYMOUTH_DESCRIPTIONS.get(theme)
        or conf.get("Plymouth Theme", "Description", fallback=""))
    scene.logo = next((p for p in PLYMOUTH_LOGOS if p.is_file()), None)

    if module == "two-step":
        sec = "two-step"
        image_dir = directory if staged else Path(conf.get(sec, "ImageDir",
                                                           fallback=str(directory)))

        def num(key: str, default: float) -> float:
            try:
                return float(conf.get(sec, key, fallback=str(default)))
            except ValueError:
                return default
        scene.bg_top = _plymouth_color(conf.get(sec, "BackgroundStartColor", fallback=""), "#000000")
        scene.bg_bottom = _plymouth_color(conf.get(sec, "BackgroundEndColor", fallback=""), scene.bg_top)
        if (image_dir / "watermark.png").is_file():
            scene.watermark = image_dir / "watermark.png"
            scene.watermark_align = (num("WatermarkHorizontalAlignment", 1.0),
                                     num("WatermarkVerticalAlignment", 0.5))
        scene.frames_align = (num("HorizontalAlignment", 0.5), num("VerticalAlignment", 0.5))
        # At boot the progress animation (progress-) or loop (throbber-) plays
        # first, then animation- plays once at the end if UseEndAnimation is on.
        frames = _numbered(image_dir, "progress-") + _numbered(image_dir, "throbber-")
        loop = len(frames)
        if conf.getboolean("boot-up", "UseEndAnimation", fallback=True) or not frames:
            frames += _numbered(image_dir, "animation-")
        scene.frames = frames
        # If there is an end animation, it is the theme's main show and its last
        # frame is the complete state (cachyos-bootanimation: small ring, then a big
        # logo; in-between frames may be empty). Otherwise the middle of the loop.
        scene.still = len(frames) - 1 if len(frames) > loop else loop // 2
        if conf.getboolean("boot-up", "UseFirmwareBackground", fallback=False):
            scene.firmware, scene.firmware_box = _bgrt_box()
    elif module == "fade-throbber":
        scene.kind = "fade-in"
        scene.star = directory / "star.png" if (directory / "star.png").is_file() else None
    elif module == "space-flares":
        scene.kind = "solar"
        scene.bg_top, scene.bg_bottom = "#05081a", "#10204a"
        scene.star = directory / "star.png" if (directory / "star.png").is_file() else None
    elif module == "script":
        scene.bg_top, scene.bg_bottom = "#3c6eb4", "#294071"
    return scene


@dataclass
class PlymouthCatalogTheme:
    """One of the community themes (presets/login/plymouth.toml)."""
    id: str
    title: str
    source: str = ""
    desc: str = ""
    repo: str = ""
    stars: int = 0
    license: str = ""
    aur: str = ""
    preview: str = ""          # URL of the animated preview
    thumb: Path | None = None  # card image in the repo
    #: Zoom box on the card (x, y, width, height; fractions) — so the logo is not tiny.
    crop: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)


def _crop(value) -> tuple[float, float, float, float]:
    try:
        x, y, w, h = (float(v) for v in value)
    except (TypeError, ValueError):
        return (0.0, 0.0, 1.0, 1.0)
    if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 and 0 < h <= 1):
        return (0.0, 0.0, 1.0, 1.0)
    return (x, y, min(w, 1 - x), min(h, 1 - y))


def load_plymouth_catalog(root: Path) -> list[PlymouthCatalogTheme]:
    path = Path(root) / "presets/login/plymouth.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    themes = []
    for item in data.get("theme", []):
        if not item.get("id"):
            continue
        thumb = path.parent / "plymouth-previews" / f"{item['id']}.jpg"
        themes.append(PlymouthCatalogTheme(
            id=item["id"], title=item.get("title", item["id"]),
            source=item.get("source", ""), desc=item.get("desc", ""),
            repo=item.get("repo", ""), stars=int(item.get("stars", 0) or 0),
            license=item.get("license", ""), aur=item.get("aur", ""),
            preview=item.get("preview", ""),
            thumb=thumb if thumb.is_file() else None,
            crop=_crop(item.get("crop"))))
    return themes


def _preview_cache() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "hyprsetup" / "plymouth-previews"


def cached_plymouth_preview(entry: PlymouthCatalogTheme) -> Path | None:
    path = _preview_cache() / f"{entry.id}.gif"
    return path if path.is_file() and path.stat().st_size > 0 else None


def fetch_plymouth_preview(entry: PlymouthCatalogTheme, timeout: int = 60) -> Path | None:
    """Downloads the animated preview (once; then from the cache) — as a GIF.

    GdkPixbuf cannot read WebP, so WebP previews (catppuccin) are converted to GIF
    if Pillow is available; otherwise None (the UI stays on the card image). Also
    None without network. The UI calls this from a worker thread.
    """
    if not entry.preview.startswith("https://"):
        return None
    cached = cached_plymouth_preview(entry)
    if cached:
        return cached
    target = _preview_cache() / f"{entry.id}.gif"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(entry.preview,
                                         headers={"User-Agent": "souprland"})
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            data = resp.read()
    except (OSError, ValueError):
        return None
    if entry.preview.lower().endswith(".gif"):
        payload = data
    else:
        try:
            import io
            from PIL import Image
        except ImportError:
            return None
        try:
            image = Image.open(io.BytesIO(data))
            out = io.BytesIO()
            image.save(out, format="GIF", save_all=True, loop=0,
                       duration=image.info.get("duration", 40))
            payload = out.getvalue()
        except (OSError, ValueError):
            return None
    tmp = target.with_suffix(".part")
    try:
        tmp.write_bytes(payload)
        tmp.replace(target)
    except OSError:
        return None
    return target


def plymouth_script(install_root: Path, theme: str, snapshot: bool = False) -> str:
    """Command that sets the boot animation to ``theme``: ``install.sh --plymouth``.

    The real work (initramfs hook, kernel command line, one-off initramfs rebuild,
    limine-update) is done by the SAME code as the installer
    (modules/system.sh:hook_plymouth); there is no second copy here. If the UI
    already took a snapshot, install.sh's own snapshot is turned off.
    """
    env = "" if snapshot else "SNAPSHOT_BEFORE_SYSTEM=false "
    return (f"{env}bash {shlex.quote(str(Path(install_root).resolve() / 'install.sh'))} "
            f"--plymouth {shlex.quote(theme)}")


# --------------------------------------------------------- My theme (Plymouth)
CUSTOM_PLYMOUTH = "souprland-ozel"  # Turkish-looking theme id ("custom"), kept as-is
#: Limits for frames going into the initramfs: every frame is loaded into memory
#: at boot and grows the initramfs (and therefore /boot).
CUSTOM_MAX_FRAMES = 120
CUSTOM_MAX_SIDE = 512
CUSTOM_FPS = 30                     # two-step loop runs at ~30 frames per second
CUSTOM_WARN_BYTES = 4 * 1024 * 1024
CUSTOM_LIMIT_BYTES = 12 * 1024 * 1024
#: Password box (encrypted disk) and keyboard layout images: two-step looks for
#: these in the theme folder; without them the password prompt is drawn plain/broken.
_DIALOG_IMAGES = ("entry.png", "bullet.png", "lock.png", "capslock.png",
                  "keyboard.png", "keymap-render.png")
#: Spinner animation sets: (label, theme folder, frame prefix) — offered if installed.
CUSTOM_SPINNERS = {
    "spinner": ("Ring", "spinner", "throbber-"),
    "spinfinity": ("Infinity", "spinfinity", "throbber-"),
    "cachyos-bootanimation": ("CachyOS ring", "cachyos-bootanimation", "throbber-"),
}

PLYMOUTH_DESCRIPTIONS[CUSTOM_PLYMOUTH] = "The theme you made (My theme tab)"


@dataclass
class CustomPlymouth:
    """My theme settings (login.json → "plymouth_custom")."""
    image: str = ""              # logo or GIF; empty = no image
    image_width: int = 240       # pixels on a 1920-wide screen
    image_v: float = 0.45        # vertical position (0 top, 1 bottom)
    spinner: str = "spinner"     # CUSTOM_SPINNERS key or "none"
    spinner_v: float = 0.8
    firmware: bool = False       # motherboard logo (BGRT) in the background
    bg_top: str = "#000000"
    bg_bottom: str = "#000000"

    @classmethod
    def from_dict(cls, data: dict | None) -> "CustomPlymouth":
        cfg = cls()
        for key, value in (data or {}).items():
            if hasattr(cfg, key):
                setattr(cfg, key, type(getattr(cfg, key))(value))
        return cfg

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class CustomReport:
    """Summary of the generated draft — the UI derives its warnings from this."""
    directory: Path
    bytes: int = 0
    frames: int = 0
    animated: bool = False
    shortened: bool = False      # GIF squeezed into CUSTOM_MAX_FRAMES (plays faster)
    shrunk: bool = False         # image scaled down to CUSTOM_MAX_SIDE
    dialog: bool = True          # password box images were found
    error: str = ""


def available_spinners() -> dict[str, str]:
    return {key: label for key, (label, theme, prefix) in CUSTOM_SPINNERS.items()
            if _numbered(PLYMOUTH_THEMES / theme, prefix)}


def custom_stage_dir() -> Path:
    return _preview_cache().parent / "plymouth-custom" / CUSTOM_PLYMOUTH


def _hex_rgb(value: str) -> str:
    digits = value.strip().lstrip("#")
    return "0x" + (digits[:6] if re.fullmatch(r"[0-9a-fA-F]{6,8}", digits) else "000000")


def build_custom_plymouth(cfg: CustomPlymouth, stage: Path | None = None) -> CustomReport:
    """Builds a real two-step theme folder from the settings (no root needed).

    The preview reads this folder via plymouth_scene(directory=...); installing
    copies the same folder under /usr/share/plymouth/themes — what you see is exactly
    what gets installed. Images are drawn at their natural size on screen, so they
    are scaled to the target size here. Image frames are only regenerated when the
    source or size changes (so color changes stay fast).
    """
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf, GLib

    stage = Path(stage or custom_stage_dir())
    report = CustomReport(directory=stage)
    stage.mkdir(parents=True, exist_ok=True)
    image = Path(cfg.image).expanduser() if cfg.image else None
    key = json.dumps([str(image) if image else "",
                      image.stat().st_mtime if image and image.is_file() else 0,
                      cfg.image_width, cfg.spinner])
    key_file = stage / ".source"
    reuse = key_file.is_file() and key_file.read_text(encoding="utf-8") == key

    def scaled(pix, width: int):
        w, h = pix.get_width(), pix.get_height()
        width = max(8, int(width))
        if width > CUSTOM_MAX_SIDE:
            width, report.shrunk = CUSTOM_MAX_SIDE, True
        height = max(1, round(h * width / w))
        if height > CUSTOM_MAX_SIDE:
            width, height = max(1, round(width * CUSTOM_MAX_SIDE / height)), CUSTOM_MAX_SIDE
            report.shrunk = True
        return pix.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)

    if not reuse:
        for old in list(stage.glob("*.png")):
            old.unlink()
        if image is not None:
            if not image.is_file():
                report.error = f"Image not found: {image}"
            else:
                try:
                    anim = GdkPixbuf.PixbufAnimation.new_from_file(str(image))
                except GLib.Error as exc:
                    anim, report.error = None, f"Could not read image: {exc.message}"
                if anim is not None and anim.is_static_image():
                    scaled(anim.get_static_image(), cfg.image_width).savev(
                        str(stage / "watermark.png"), "png", [], [])
                elif anim is not None:
                    _gif_frames(anim, cfg.image_width, stage, scaled, report)
        if not report.animated and cfg.spinner in CUSTOM_SPINNERS:
            _label, theme, prefix = CUSTOM_SPINNERS[cfg.spinner]
            for i, src in enumerate(_numbered(PLYMOUTH_THEMES / theme, prefix), 1):
                shutil.copyfile(src, stage / f"throbber-{i:04d}.png")
        if not report.error:
            key_file.write_text(key, encoding="utf-8")
    else:
        report.animated = (stage / ".animated").is_file()
        report.shortened = (stage / ".shortened").is_file()
        report.shrunk = (stage / ".shrunk").is_file()
    for flag in ("animated", "shortened", "shrunk"):
        marker = stage / f".{flag}"
        if getattr(report, flag):
            marker.touch()
        elif marker.exists():
            marker.unlink()

    spinner_src = PLYMOUTH_THEMES / "spinner"
    found = 0
    for name in _DIALOG_IMAGES:
        if (spinner_src / name).is_file():
            shutil.copyfile(spinner_src / name, stage / name)
            found += 1
    report.dialog = found >= 3

    # With an animated image the frames become the throbber and loop at the image's
    # position; with a still image the image is the watermark and the frames (if
    # chosen) are the spinner animation.
    frames_v = cfg.image_v if report.animated else cfg.spinner_v
    lines = [
        "[Plymouth Theme]",
        "Name=Souprland (my theme)",
        "Description=Generated in the settings app's My theme tab",
        "ModuleName=two-step",
        "",
        "[two-step]",
        "Font=Cantarell 12",
        f"ImageDir={PLYMOUTH_THEMES / CUSTOM_PLYMOUTH}",
        "DialogHorizontalAlignment=.5",
        "DialogVerticalAlignment=.382",
        "TitleHorizontalAlignment=.5",
        "TitleVerticalAlignment=.382",
        "HorizontalAlignment=.5",
        f"VerticalAlignment={frames_v:.3f}",
        "WatermarkHorizontalAlignment=.5",
        f"WatermarkVerticalAlignment={cfg.image_v:.3f}",
        "Transition=none",
        "TransitionDuration=0.0",
        f"BackgroundStartColor={_hex_rgb(cfg.bg_top)}",
        f"BackgroundEndColor={_hex_rgb(cfg.bg_bottom)}",
        "ProgressBarBackgroundColor=0x606060",
        "ProgressBarForegroundColor=0xffffff",
        "MessageBelowAnimation=true",
        "",
    ]
    for mode in ("boot-up", "shutdown", "reboot"):
        lines += [f"[{mode}]", "UseEndAnimation=false",
                  f"UseFirmwareBackground={'true' if cfg.firmware else 'false'}", ""]
    (stage / f"{CUSTOM_PLYMOUTH}.plymouth").write_text("\n".join(lines), encoding="utf-8")

    report.frames = len(list(stage.glob("throbber-*.png")))
    report.bytes = sum(p.stat().st_size for p in stage.iterdir() if p.is_file())
    return report


def _gif_frames(anim, width: int, stage: Path, scaled, report: CustomReport) -> None:
    """Samples the GIF at CUSTOM_FPS and splits it into throbber-NNNN.png frames.

    two-step does not know frame durations and plays all frames at the same rate;
    so first the duration of one GIF loop is found (delays summed up to the last
    frame), then the frame at every 1/30 second is taken. A GIF exceeding
    CUSTOM_MAX_FRAMES is thinned out evenly (plays faster; the report says so).
    """
    from gi.repository import GLib

    def at(ms: float):
        tv = GLib.TimeVal()
        tv.tv_sec, tv.tv_usec = int(ms // 1000), int(ms % 1000) * 1000
        return tv

    it = anim.get_iter(at(0))
    duration = 0
    for _ in range(5000):
        if it.on_currently_loading_frame():
            duration += max(it.get_delay_time(), 10)
            break
        duration += max(it.get_delay_time(), 10)
        it.advance(at(duration))
    count = max(1, round(duration / 1000 * CUSTOM_FPS))
    if count > CUSTOM_MAX_FRAMES:
        count, report.shortened = CUSTOM_MAX_FRAMES, True
    it = anim.get_iter(at(0))
    for i in range(count):
        it.advance(at(i * duration / count))
        scaled(it.get_pixbuf(), width).savev(str(stage / f"throbber-{i + 1:04d}.png"),
                                            "png", [], [])
    report.animated = count > 1


def custom_plymouth_script(stage: Path, install_root: Path) -> str:
    """Commands that put the draft into the theme folder and activate it (in a terminal)."""
    target = PLYMOUTH_THEMES / CUSTOM_PLYMOUTH
    src = shlex.quote(str(stage))
    dst = shlex.quote(str(target))
    return "\n".join([
        f"sudo rm -rf {dst}",
        f"sudo install -d -m755 {dst}",
        f"sudo cp -r {src}/. {dst}/",
        f"sudo rm -f {dst}/.source {dst}/.animated {dst}/.shortened {dst}/.shrunk",
        plymouth_script(install_root, CUSTOM_PLYMOUTH),
    ])


# ------------------------------------------------------------ INI (QSettings)
def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return value


def read_ini(path: Path) -> dict[str, str]:
    """QSettings-style file → {"Section/key": value} (order preserved).

    configparser is not used: theme files have repeated keys, lines outside any
    section and ``;`` comments, and all of these must be tolerated.
    """
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    section = "General"
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip() or "General"
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[f"{section}/{key.strip()}"] = _unquote(value)
    return out


def write_ini(values: dict[str, str]) -> str:
    """{"Section/key": value} → QSettings text (values quoted)."""
    sections: dict[str, list[str]] = {}
    for full, value in values.items():
        section, key = split_key(full)
        escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
        sections.setdefault(section, []).append(f'{key}="{escaped}"')
    blocks = [f"[{name}]\n" + "\n".join(lines) for name, lines in sections.items()]
    return ("# hyprsetup: generated by the Login Screen page "
            "(read on top of the theme's settings)\n"
            + "\n\n".join(blocks) + "\n")


def split_key(full: str) -> tuple[str, str]:
    section, _, key = full.rpartition("/")
    return section or "General", key


# ------------------------------------------------------------------ catalog --
@dataclass
class CatalogTheme:
    id: str
    title: str
    desc: str = ""
    repo: str = ""
    stars: int = 0
    license: str = ""
    aur: list[str] = field(default_factory=list)
    packages: list[str] = field(default_factory=list)
    dirs: list[str] = field(default_factory=list)
    presets: str = ""
    background: list[str] = field(default_factory=list)
    background_dir: str = ""
    background_prefix: str = ""
    palette: dict[str, str] = field(default_factory=dict)
    set_with_palette: dict[str, str] = field(default_factory=dict)
    set_with_background: dict[str, str] = field(default_factory=dict)

    def matches(self, directory: str) -> bool:
        return any(fnmatch.fnmatch(directory, pattern) for pattern in self.dirs)


def catalog_path(root: Path) -> Path:
    return Path(root) / "presets" / "login" / "sddm.toml"


def preview_image(root: Path, theme_id: str) -> Path | None:
    path = Path(root) / "presets" / "login" / "previews" / f"{theme_id}.jpg"
    return path if path.is_file() else None


def load_catalog(root: Path) -> list[CatalogTheme]:
    path = catalog_path(root)
    if not path.is_file():
        return []
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    out = []
    for raw in data.get("theme", []):
        out.append(CatalogTheme(
            id=raw["id"], title=raw.get("title", raw["id"]), desc=raw.get("desc", ""),
            repo=raw.get("repo", ""), stars=int(raw.get("stars", 0)),
            license=raw.get("license", ""), aur=list(raw.get("aur", [])),
            packages=list(raw.get("packages", [])), dirs=list(raw.get("dirs", [])),
            presets=raw.get("presets", ""), background=list(raw.get("background", [])),
            background_dir=raw.get("background_dir", ""),
            background_prefix=raw.get("background_prefix", ""),
            palette=dict(raw.get("palette", {})),
            set_with_palette=dict(raw.get("set_with_palette", {})),
            set_with_background=dict(raw.get("set_with_background", {}))))
    return out


# -------------------------------------------------------- installed themes -
@dataclass
class Theme:
    """An installed theme under /usr/share/sddm/themes."""
    dir: Path
    name: str
    config_file: str = ""                 # metadata.desktop ConfigFile (relative)
    qt: int = 5
    screenshot: Path | None = None
    catalog: CatalogTheme | None = None

    @property
    def id(self) -> str:
        return self.dir.name

    @property
    def config_path(self) -> Path | None:
        return self.dir / self.config_file if self.config_file else None

    @property
    def user_file(self) -> str:
        """File the edits are written to (relative to the theme directory)."""
        return (self.config_file or "theme.conf") + ".user"

    def presets(self) -> list[tuple[str, str]]:
        """Presets: (display name, .conf path relative to the theme directory).

        The first one is always the theme's own default (ConfigFile).
        """
        default = self.config_file or "theme.conf"
        # Themes/hyprsetup.conf written by the installer: shown with the project name.
        stem = Path(default).stem
        out = [("Souprland" if stem.startswith("hyprsetup") else stem, default)]
        if self.catalog and self.catalog.presets:
            folder = self.dir / self.catalog.presets
            for conf in sorted(folder.glob("*.conf")) if folder.is_dir() else []:
                rel = str(conf.relative_to(self.dir))
                if rel != default and not conf.name.startswith("hyprsetup"):
                    out.append((conf.stem, rel))
        return out

    def base_values(self, preset: str = "") -> dict[str, str]:
        """The theme's own settings + the chosen preset (if any)."""
        values = read_ini(self.config_path) if self.config_path else {}
        if preset and preset != self.config_file:
            values.update(read_ini(self.dir / preset))
        return values

    def preset_preview(self, preset: str) -> Path | None:
        """The preset's own screenshot; otherwise its background image.

        The astronaut package on the AUR only ships astronaut.png under Previews/:
        picking any of the other nine presets left the preview showing the
        astronaut. The preset's own background (or the same-named still frame if it
        is a video) represents it best.
        """
        stem = Path(preset).stem
        for folder in ("Previews", "docs/previews", "previews"):
            for ext in (".png", ".jpg", ".webp"):
                path = self.dir / folder / f"{stem}{ext}"
                if path.is_file():
                    return path
        return self.preset_background(preset)

    def preset_background(self, preset: str) -> Path | None:
        """The preset's background image (the still frame next to it for video/gif)."""
        keys = (self.catalog.background if self.catalog and self.catalog.background
                else ["General/Background", "General/background"])
        values = self.base_values(preset)
        value = next((values[k] for k in keys if values.get(k)), "")
        if not value:
            return None
        path = Path(value.strip('"'))
        path = path if path.is_absolute() else self.dir / path
        if path.suffix.lower() in (".mp4", ".webm", ".mov", ".mkv", ".avi"):
            for ext in (".png", ".jpg", ".webp"):
                still = path.with_suffix(ext)
                if still.is_file():
                    return still
            return None
        return path if path.is_file() else None


def _metadata(path: Path) -> dict[str, str]:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str                 # type: ignore[assignment]
    try:
        parser.read(path, encoding="utf-8")
    except (configparser.Error, OSError):
        return {}
    for section in ("SddmGreeterTheme", "Desktop Entry"):
        if parser.has_section(section):
            return dict(parser.items(section))
    return {}


def installed_themes(root: Path, base: Path = SDDM_THEMES) -> list[Theme]:
    catalog = load_catalog(root)
    out = []
    for directory in sorted(base.iterdir()) if base.is_dir() else []:
        meta_path = directory / "metadata.desktop"
        if not meta_path.is_file():
            continue
        meta = _metadata(meta_path)
        shot = meta.get("Screenshot", "")
        out.append(Theme(
            dir=directory, name=meta.get("Name", directory.name),
            config_file=meta.get("ConfigFile", "theme.conf" if (directory / "theme.conf").is_file() else ""),
            qt=6 if meta.get("QtVersion", "5").strip() == "6" else 5,
            screenshot=(directory / shot) if shot and (directory / shot).is_file() else None,
            catalog=next((c for c in catalog if c.matches(directory.name)), None)))
    return out


def find_theme(root: Path, directory: str, base: Path = SDDM_THEMES) -> Theme | None:
    return next((t for t in installed_themes(root, base) if t.id == directory), None)


def active_sddm_theme() -> str:
    """[Theme] Current from /etc/sddm.conf(.d) (the last one read wins)."""
    current = ""
    files = [Path("/etc/sddm.conf")] + sorted(Path("/etc/sddm.conf.d").glob("*.conf"))
    for path in files:
        values = read_ini(path) if path.is_file() else {}
        current = values.get("Theme/Current", current)
    return current


# ------------------------------------------------------------------- fields --
@dataclass
class Field:
    key: str                 # "Section/key"
    title: str
    type: str                # color | bool | int | float | image | text
    value: str
    group: str


def _field_type(name: str, value: str) -> str:
    low = name.lower()
    if _HEX.match(value) or (("color" in low or "colour" in low)
                             and not low.startswith(("use-", "enable", "override"))
                             and value and not value.replace(".", "").isdigit()
                             and value.lower() not in ("true", "false", "random")):
        return "color"
    if value.lower() in ("true", "false"):
        return "bool"
    if re.fullmatch(r"-?\d+", value):
        return "int"
    if re.fullmatch(r"-?\d*\.\d+", value):
        return "float"
    if value.lower().endswith(_IMAGE_EXT) or (
            not value and low in ("background", "bgsource", "wallpaper", "image")):
        return "image"
    return "text"


def _general_group(name: str, kind: str) -> str:
    low = name.lower()
    if kind == "color":
        return "Colors"
    if kind == "image" or any(w in low for w in ("blur", "dim", "background", "bg",
                                                   "crop", "scaleimage")):
        return "Background"
    if low.startswith("translate") or "placeholder" in low or low in ("headertext", "text"):
        return "Texts"
    if any(w in low for w in ("font",)):
        return "Font"
    if any(w in low for w in ("format", "clock", "hour", "date", "time", "locale")):
        return "Clock and date"
    if kind == "bool":
        return "Behavior"
    return "Layout"


def _title(name: str) -> str:
    """"LoginButtonBackgroundColor" / "active-border-color" → readable title."""
    text = re.sub(r"[-_.]", " ", name)
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    return text[:1].upper() + text[1:]


def fields(theme: Theme, preset: str = "", edits: dict[str, str] | None = None) -> list[Field]:
    """Fields shown in the editor (types are inferred from the values)."""
    values = theme.base_values(preset)
    # The theme's active file may lack some keys entirely (old installs pointed
    # astronaut at a Themes/hyprsetup.conf holding only colors). Keys found in the
    # other presets are added with their first value so they can be edited too;
    # the .user file adds the missing key.
    for _label, other in theme.presets():
        for key, value in read_ini(theme.dir / other).items():
            values.setdefault(key, value)
    edits = edits or {}
    sectioned = len({split_key(k)[0] for k in values}) > 1
    out = []
    for full, value in values.items():
        section, name = split_key(full)
        kind = _field_type(name, value)
        if theme.catalog and full in theme.catalog.background:
            kind = "image"
        group = section.replace(".", " › ") if sectioned else _general_group(name, kind)
        out.append(Field(key=full, title=_title(name), type=kind,
                         value=edits.get(full, value), group=group))
    return out


# --------------------------------------------------------------- coloring --
def palette_edits(theme: Theme, colors: dict[str, str]) -> dict[str, str]:
    """"Color from my palette": color keys via the catalog's mapping.

    ``colors`` is the output of themes.derive (COL_*). For a theme without a
    mapping, each color field's role is guessed from its name (background/text/accent).
    """
    def hex_of(role: str) -> str:
        value = colors.get(f"COL_{role}", "").lstrip("#")
        return f"#{value}" if value else ""

    if theme.catalog and theme.catalog.palette:
        out = {key: hex_of(role) for key, role in theme.catalog.palette.items() if hex_of(role)}
        out.update(theme.catalog.set_with_palette)
        return out
    out = {}
    for item in fields(theme):
        if item.type != "color":
            continue
        low = item.key.lower()
        if any(w in low for w in ("text", "font", "foreground", "icon", "fg")):
            role = "FG"
        elif any(w in low for w in ("accent", "button", "highlight", "hover", "border",
                                      "cursor", "active", "selected")):
            role = "ACCENT"
        elif any(w in low for w in ("warning", "error", "wrong")):
            role = "RED"
        else:
            role = "BG"
        if hex_of(role):
            out[item.key] = hex_of(role)
    return out


def background_keys(theme: Theme) -> list[str]:
    if theme.catalog and theme.catalog.background:
        return list(theme.catalog.background)
    return [f.key for f in fields(theme) if f.type == "image"]


def background_edits(theme: Theme, image: Path) -> dict[str, str]:
    """This image for the background keys (copied into the theme directory on apply)."""
    out = {key: str(image) for key in background_keys(theme)}
    if theme.catalog:
        out.update(theme.catalog.set_with_background)
    return out


# ------------------------------------------------------------ staging/applying
def cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "hyprsetup" / "login"


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower() or "x"


def stage(theme: Theme, preset: str, edits: dict[str, str],
          dest: Path) -> list[tuple[Path, str]]:
    """Prepares the files to put into the theme directory under ``dest``.

    Returns: (staged file, target path relative to the theme directory). Image
    fields holding absolute paths are copied into the theme directory and their
    values turned into the relative name the theme expects (the greeter cannot
    read the home directory).
    """
    dest.mkdir(parents=True, exist_ok=True)
    values: dict[str, str] = {}
    if preset and preset != theme.config_file:
        values.update(read_ini(theme.dir / preset))
    values.update({k: v for k, v in edits.items() if v is not None})

    staged: list[tuple[Path, str]] = []
    catalog = theme.catalog
    folder = catalog.background_dir if catalog else ""
    prefix = catalog.background_prefix if catalog else ""
    for key, value in list(values.items()):
        path = Path(value)
        if not (value.startswith("/") and path.is_file()):
            continue
        name = f"hyprsetup-{_slug(split_key(key)[1])}{path.suffix.lower()}"
        rel = f"{folder}/{name}" if folder else name
        target = dest / rel
        if (target, rel) not in staged:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.unlink(missing_ok=True)       # in a preview it may be a link to the system copy
            shutil.copyfile(path, target)
            staged.append((target, rel))
        values[key] = prefix + name
    user = dest / theme.user_file
    user.parent.mkdir(parents=True, exist_ok=True)
    user.unlink(missing_ok=True)
    user.write_text(write_ini(values), encoding="utf-8")
    staged.append((user, theme.user_file))
    return staged


def greeter_binary(theme: Theme) -> str:
    names = ["sddm-greeter-qt6", "sddm-greeter"] if theme.qt == 6 else ["sddm-greeter"]
    return next((shutil.which(n) for n in names if shutil.which(n)), "")


def preview(theme: Theme, preset: str, edits: dict[str, str]) -> subprocess.Popen | None:
    """Opens the theme with the edits in test mode (no root, the system is unchanged).

    The theme is put into a temporary "link copy" (real folders, files symlinked to
    the system copies — themes with video backgrounds are hundreds of MB), and the
    edits are placed on top. Copies from earlier previews are deleted.
    """
    binary = greeter_binary(theme)
    if not binary:
        return None
    for old in Path(tempfile.gettempdir()).glob("hyprsetup-sddm-preview-*"):
        shutil.rmtree(old, ignore_errors=True)
    tmp = Path(tempfile.mkdtemp(prefix="hyprsetup-sddm-preview-"))
    copy = tmp / theme.id
    result = subprocess.run(["cp", "-rs", str(theme.dir), str(copy)], capture_output=True)
    if result.returncode != 0:
        shutil.copytree(theme.dir, copy, symlinks=True)
    stage(theme, preset, edits, copy)
    return subprocess.Popen([binary, "--test-mode", "--theme", str(copy)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)


def sddm_script(theme: Theme, preset: str, edits: dict[str, str],
                switch: bool = False) -> str:
    """Script that installs the chosen theme and edits on the system (with sudo)."""
    staging = cache_dir() / "sddm" / theme.id
    shutil.rmtree(staging, ignore_errors=True)
    staged = stage(theme, preset, edits, staging)
    lines = ["set -e",
             f"echo 'SDDM theme: {theme.name}'"]
    # Images left from a previous apply (the name may have changed) are cleaned up.
    lines.append(f"sudo find {shlex.quote(str(theme.dir))} -maxdepth 2 -type f "
                 "-name 'hyprsetup-*' -delete")
    for src, rel in staged:
        lines.append(f"sudo install -Dm644 {shlex.quote(str(src))} "
                     f"{shlex.quote(str(theme.dir / rel))}")
    lines.append(f"printf '[Theme]\\nCurrent=%s\\n' {shlex.quote(theme.id)} | "
                 f"sudo install -Dm644 /dev/stdin {SDDM_THEME_CONF}")
    if switch:
        lines.append(switch_script("sddm"))
    lines.append("echo 'Done — the login screen will look like this at the next login.'")
    return "\n".join(lines)


# ------------------------------------------------------------ Plasma Login --
@dataclass
class PlasmaLogin:
    show_clock: bool = True
    #: "keep" (leave alone) | "image" | "color"
    wallpaper: str = "keep"
    image: str = ""                       # absolute path
    color: str = ""                       # "#rrggbb"
    #: "keep" | "palette" | <color scheme name, /usr/share/color-schemes/<name>.colors>
    colors: str = "keep"


def read_kconfig(path: Path) -> list[tuple[str, list[str]]]:
    """KConfig file → [(group header line, lines)] (order preserved).

    Nested groups (``[Greeter][Wallpaper][org.kde.image][General]``) are kept as a
    single header line.
    """
    groups: list[tuple[str, list[str]]] = [("", [])]
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return groups
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("["):
            groups.append((line, []))
        elif line:
            groups[-1][1].append(line)
    return groups


def plasmalogin_state(path: Path = PLASMALOGIN_CONF) -> PlasmaLogin:
    state = PlasmaLogin()
    for header, lines in read_kconfig(path):
        entries = dict(line.split("=", 1) for line in lines if "=" in line)
        if header == "[Greeter]":
            state.show_clock = entries.get("ShowClock", "true").lower() != "false"
            plugin = entries.get("WallpaperPluginId", "")
            if plugin == "org.kde.image":
                state.wallpaper = "image"
            elif plugin == "org.kde.color":
                state.wallpaper = "color"
        elif header == "[Greeter][Wallpaper][org.kde.image][General]":
            image = entries.get("Image", "")
            state.image = image.removeprefix("file://")
        elif header == "[Greeter][Wallpaper][org.kde.color][General]":
            rgb = entries.get("Color", "")
            try:
                r, g, b = (int(x) for x in rgb.split(",")[:3])
                state.color = f"#{r:02x}{g:02x}{b:02x}"
            except ValueError:
                pass
    return state


def color_schemes() -> list[tuple[str, Path]]:
    """Installed KDE color schemes: (name, .colors file)."""
    out: dict[str, Path] = {}
    for base in (Path("/usr/share/color-schemes"),
                 Path.home() / ".local/share/color-schemes"):
        for path in sorted(base.glob("*.colors")) if base.is_dir() else []:
            out[path.stem] = path
    return sorted(out.items(), key=lambda kv: kv[0].lower())


def plasmalogin_conf_text(state: PlasmaLogin, image_name: str = "",
                          path: Path = PLASMALOGIN_CONF) -> str:
    """New content of /etc/plasmalogin.conf: the [Greeter] groups are rewritten, the
    others (Autologin, Users…) and Greeter's other keys are preserved."""
    kept: list[tuple[str, list[str]]] = []
    greeter: list[str] = []
    wallpaper_groups: list[tuple[str, list[str]]] = []
    for header, lines in read_kconfig(path):
        if header == "[Greeter]":
            greeter = [ln for ln in lines
                       if not ln.startswith(("ShowClock=", "WallpaperPluginId="))]
        elif header.startswith("[Greeter][Wallpaper]"):
            wallpaper_groups.append((header, lines))
        else:
            kept.append((header, lines))
    greeter.append(f"ShowClock={'true' if state.show_clock else 'false'}")
    if state.wallpaper == "image" and image_name:
        greeter.append("WallpaperPluginId=org.kde.image")
        wallpaper_groups = [("[Greeter][Wallpaper][org.kde.image][General]",
                             [f"Image=file://{PLASMALOGIN_HOME}/wallpapers/{image_name}",
                              "FillMode=2"])]
    elif state.wallpaper == "color" and _HEX.match(state.color or ""):
        value = state.color.lstrip("#")
        rgb = ",".join(str(int(value[i:i + 2], 16)) for i in (0, 2, 4))
        greeter.append("WallpaperPluginId=org.kde.color")
        wallpaper_groups = [("[Greeter][Wallpaper][org.kde.color][General]",
                             [f"Color={rgb}"])]
    else:
        current = plasmalogin_state(path)
        if current.wallpaper == "image":
            greeter.append("WallpaperPluginId=org.kde.image")
        elif current.wallpaper == "color":
            greeter.append("WallpaperPluginId=org.kde.color")
    blocks = []
    for header, lines in kept:
        if header or lines:
            blocks.append("\n".join(([header] if header else []) + lines))
    blocks.append("\n".join(["[Greeter]"] + greeter))
    for header, lines in wallpaper_groups:
        blocks.append("\n".join([header] + lines))
    return "\n\n".join(blocks) + "\n"


def plasmalogin_script(state: PlasmaLogin, kdeglobals: str = "") -> str:
    """Script that installs the Plasma Login settings on the system (with sudo).

    The wallpaper and colors go into the greeter user's (plasmalogin) home directory
    — owned by that user, as KDE's own settings module does it.
    ``kdeglobals``: color scheme text to write (empty = leave colors alone).
    """
    staging = cache_dir() / "plasmalogin"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    home = PLASMALOGIN_HOME
    lines = ["set -e", "echo 'Applying Plasma Login settings'"]
    image_name = ""
    if state.wallpaper == "image" and state.image and Path(state.image).is_file():
        image = Path(state.image)
        image_name = f"hyprsetup-background{image.suffix.lower()}"
        staged = staging / image_name
        shutil.copyfile(image, staged)
        lines.append(f"sudo install -d -o plasmalogin -g plasmalogin -m 755 {home}/wallpapers")
        lines.append(f"sudo find {home}/wallpapers -maxdepth 1 -name 'hyprsetup-background.*' -delete")
        lines.append(f"sudo install -o plasmalogin -g plasmalogin -m 644 "
                     f"{shlex.quote(str(staged))} {home}/wallpapers/{image_name}")
    conf = staging / "plasmalogin.conf"
    conf.write_text(plasmalogin_conf_text(state, image_name), encoding="utf-8")
    lines.append(f"sudo install -m 644 {shlex.quote(str(conf))} {PLASMALOGIN_CONF}")
    if kdeglobals:
        globals_file = staging / "kdeglobals"
        globals_file.write_text(kdeglobals, encoding="utf-8")
        lines.append(f"sudo install -d -o plasmalogin -g plasmalogin -m 755 {home}/.config")
        lines.append(f"sudo install -o plasmalogin -g plasmalogin -m 644 "
                     f"{shlex.quote(str(globals_file))} {home}/.config/kdeglobals")
    lines.append("echo 'Done — the login screen will look like this at the next login.'")
    return "\n".join(lines)


def scheme_kdeglobals(path: Path) -> str:
    """A .colors color scheme as kdeglobals (color groups + name)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    return f"[General]\nColorScheme={path.stem}\n\n{text}"


# ----------------------------------------------------------------- state ----
def state_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "hyprsetup" / "login.json"


def load_state() -> dict:
    try:
        return json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(data: dict) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def palette_kdeglobals(root: Path, variables: dict[str, str]) -> str:
    """This project's kdeglobals template, with the given variables (my palette)."""
    from . import render as render_mod

    template = Path(root) / "templates" / "kde" / "kdeglobals.tmpl"
    text = "\n".join(line for line in template.read_text(encoding="utf-8").splitlines()
                     if not line.startswith("{{!"))
    return render_mod.render_text(text, variables)
