"""Mix: pick parts from rices one by one and assemble your own desktop.

A rice (rice.py) brings the author's files as a WHOLE. A mix is the reverse:
the base is always this project's own configuration (keybindings, keyboard,
ALT+Tab…) and each "slot" is filled from a different rice — one's
wallpaper, another's colors, a third one's window look.

Slots are translated into this project's settings; the author's files are not
installed:

* ``wallpaper`` — the wallpaper of one of the rice's looks (variants).
  Put into WALLPAPER_PATH; for video wallpapers the first frame is taken.
* ``colors``    — a look's color scheme. If the author uses a fixed palette
  (catppuccin, gruvbox) that theme; if the colors are generated from the
  wallpaper (matugen/pywal), the palette extracted from that image the same way.
  The value "wallpaper" extracts from the selected wallpaper (THEME="auto").
* ``look``      — gaps, border, corners, opacity, blur, shadow and animations
  from the author's Hyprland config (curves exactly as written:
  ANIMATION_PRESET="custom").

The parts catalog lives in ``presets/mix/parts.json`` and is generated from the
authors' files with ``python -m hyprsetup mix scan`` (committed to the repo so
every machine gets the same result). This project's own profiles are parts too: their
photo, palette and window look are read from ``presets/profile`` when the
catalog is loaded (``own_parts``), so they are never written to parts.json. The selection and saved mixes live in
``~/.config/hyprsetup/mix.json``; when a slot is first filled, the previous
values of the settings it changes are written there too, and come back when
the slot is cleared.
"""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from . import palette as palette_mod
from . import presets as presets_mod
from . import rice as rice_mod
from . import themes

STATE_NAME = "mix.json"

#: (slot, label) — the UI and CLI show them in this order.
SLOTS: tuple[tuple[str, str], ...] = (
    ("wallpaper", "Wallpaper"),
    ("colors", "Color scheme"),
    ("look", "Window look"),
)
SLOT_IDS = tuple(s for s, _ in SLOTS)

#: Special value of the colors slot: colors are extracted from the selected wallpaper.
COLORS_FROM_WALLPAPER = "wallpaper"

_VIDEO = {".webm", ".mp4", ".mkv", ".mov"}

#: If the author did not set a value, Hyprland's own default applies — not
#: this project's default (e.g. rounding: Hyprland 0, project 10). For an
#: exact look the missing values are filled with these.
LOOK_DEFAULTS: dict[str, str] = {
    "GAPS_IN": "5", "GAPS_OUT": "20", "GAPS_WORKSPACES": "0",
    "BORDER_SIZE": "1", "ROUNDING": "0", "ROUNDING_POWER": "2",
    "ACTIVE_OPACITY": "1.0", "INACTIVE_OPACITY": "1.0",
    "DIM_INACTIVE": "false", "DIM_STRENGTH": "0.5",
    "BLUR": "true", "BLUR_SIZE": "8", "BLUR_PASSES": "1",
    "BLUR_NOISE": "0.0117", "BLUR_CONTRAST": "0.8916",
    "BLUR_BRIGHTNESS": "0.8172", "BLUR_VIBRANCY": "0.1696",
    "BLUR_XRAY": "false", "BLUR_POPUPS": "false", "BLUR_SPECIAL": "false",
    "SHADOW": "true", "SHADOW_RANGE": "4", "SHADOW_RENDER_POWER": "3",
    "SHADOW_OFFSET": "0 0",
    "ANIMATIONS": "true",
    "VIS_ENABLE": "false",
}

#: Hyprland key → (setting, type). Type: int · float · bool · offset.
_LOOK_MAP: dict[str, tuple[str, str]] = {
    "general:gaps_in": ("GAPS_IN", "int"),
    "general:gaps_out": ("GAPS_OUT", "int"),
    "general:gaps_workspaces": ("GAPS_WORKSPACES", "int"),
    "general:border_size": ("BORDER_SIZE", "int"),
    "decoration:rounding": ("ROUNDING", "int"),
    "decoration:rounding_power": ("ROUNDING_POWER", "int"),
    "decoration:active_opacity": ("ACTIVE_OPACITY", "float"),
    "decoration:inactive_opacity": ("INACTIVE_OPACITY", "float"),
    "decoration:dim_inactive": ("DIM_INACTIVE", "bool"),
    "decoration:dim_strength": ("DIM_STRENGTH", "float"),
    "decoration:blur:enabled": ("BLUR", "bool"),
    "decoration:blur:size": ("BLUR_SIZE", "int"),
    "decoration:blur:passes": ("BLUR_PASSES", "int"),
    "decoration:blur:noise": ("BLUR_NOISE", "float"),
    "decoration:blur:contrast": ("BLUR_CONTRAST", "float"),
    "decoration:blur:brightness": ("BLUR_BRIGHTNESS", "float"),
    "decoration:blur:vibrancy": ("BLUR_VIBRANCY", "float"),
    "decoration:blur:xray": ("BLUR_XRAY", "bool"),
    "decoration:blur:popups": ("BLUR_POPUPS", "bool"),
    "decoration:blur:special": ("BLUR_SPECIAL", "bool"),
    "decoration:shadow:enabled": ("SHADOW", "bool"),
    "decoration:shadow:range": ("SHADOW_RANGE", "int"),
    "decoration:shadow:render_power": ("SHADOW_RENDER_POWER", "int"),
    "decoration:shadow:offset": ("SHADOW_OFFSET", "offset"),
    "animations:enabled": ("ANIMATIONS", "bool"),
}

#: Settings a slot writes (their previous values are saved and restored).
SLOT_KEYS: dict[str, tuple[str, ...]] = {
    "wallpaper": ("WALLPAPER_PATH", "WALLPAPER_IMAGE", "WALLPAPER_STYLE",
                  "WALLPAPER_DAEMON", "WPENGINE_ID"),
    "colors": ("THEME", "CUSTOM_COLORS"),
    "look": (*LOOK_DEFAULTS, "ANIMATION_PRESET", "ANIMATION_CUSTOM"),
}


# ------------------------------------------------------------------- paths ---
def parts_path(root: Path) -> Path:
    return Path(root) / "presets" / "mix" / "parts.json"


def state_path(home: Path | None = None) -> Path:
    return (Path(home) if home else Path.home()) / ".config" / "hyprsetup" / STATE_NAME


def wallpaper_cache(home: Path | None = None) -> Path:
    base = os.environ.get("XDG_CACHE_HOME") if home is None else None
    root = Path(base) if base else (Path(home) if home else Path.home()) / ".cache"
    return root / "hyprsetup" / "mix" / "wallpapers"


def user_parts_path() -> Path:
    """Parts of imported rices (per user, not committed to the repo)."""
    return rice_mod.imported_dir() / "parts.json"


def thumbnail_path(root: Path, profile: str, variant: str) -> Path:
    """Small preview of the wallpaper (the UI's cards): shipped ones live in the
    repo, imported ones in the user's folder."""
    if variant == OWN_VARIANT and not rice_mod.is_rice(Path(root), profile):
        values = presets_mod.resolve_chain(Path(root), profile=profile)
        if values.get("WALLPAPER_DAEMON") == "wallpaperengine" and values.get("WPENGINE_ID"):
            from . import wpengine
            preview = wpengine.preview_path(values["WPENGINE_ID"])
            if preview is not None:
                return preview
            return Path(root) / "presets" / "mix" / "thumbs" / f"{profile}-wpengine-missing.jpg"
        image = _own_image(root, values)
        if image is not None:
            return image
    if rice_mod.is_imported(root, profile):
        return rice_mod.imported_dir() / "thumbs" / f"{profile}-{variant}.jpg"
    return Path(root) / "presets" / "mix" / "thumbs" / f"{profile}-{variant}.jpg"


def _make_thumbnail(image: Path, dest: Path) -> bool:
    if not (shutil.which("magick") or shutil.which("convert")):
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    tool = shutil.which("magick") or shutil.which("convert")
    out = subprocess.run([tool, f"{image}[0]", "-auto-orient", "-thumbnail", "480x270^",
                          "-gravity", "center", "-extent", "480x270", "-strip",
                          "-quality", "80", str(dest)],
                         capture_output=True, check=False, timeout=120)
    return out.returncode == 0 and dest.is_file()


#: Variant name of an own profile's part (its photo / palette).
OWN_VARIANT = "own"


def _own_image(root: Path, values: dict[str, str]) -> Path | None:
    image = (values.get("WALLPAPER_IMAGE") or "").strip()
    if not image:
        return None
    path = Path(root).resolve() / image
    if not path.is_file():
        from . import photos
        path = photos.resolve(Path(root).resolve(), image) or path
    return Path(path) if Path(path).is_file() else None


def own_parts(root: Path) -> dict[str, dict]:
    """This project's profiles as mix parts: wallpaper (the profile's photo),
    colors (its palette) and window look (its corners, gaps, blur, animations).

    Built from presets/profile each time, so a new or edited profile shows up
    without ``mix scan``; profiles with no image file only give colors and look.
    """
    out: dict[str, dict] = {}
    for preset in presets_mod.load_profiles(Path(root)):
        name = preset.name
        if rice_mod.is_rice(Path(root), name):
            continue
        try:
            values = presets_mod.resolve_chain(Path(root), profile=name)
        except (OSError, ValueError, KeyError):
            continue
        owner, _, rest = (preset.label or name).partition(" — ")
        variant: dict = {"title": rest or owner}
        wp_daemon = (values.get("WALLPAPER_DAEMON") or "").strip()
        wp_id = (values.get("WPENGINE_ID") or "").strip()
        if wp_daemon == "wallpaperengine" and wp_id:
            variant["wpengine"] = wp_id
            variant["wallpaper"] = f"wpengine:{wp_id}"
        else:
            image = _own_image(root, values)
            if image is not None:
                variant["wallpaper"] = str(image.relative_to(Path(root).resolve())
                                           if image.is_relative_to(Path(root).resolve()) else image)
        theme = (values.get("THEME") or "").strip()
        if theme and theme != "auto" and themes.resolve(theme):
            variant["colors"] = {"theme": theme}
        look = {key: (values.get(key) or default) for key, default in LOOK_DEFAULTS.items()}
        look["ANIMATION_PRESET"] = values.get("ANIMATION_PRESET", "") or ""
        look["ANIMATION_CUSTOM"] = values.get("ANIMATION_CUSTOM", "") or ""
        out[name] = {"title": preset.label or name, "own": True,
                     "variants": {OWN_VARIANT: variant},
                     "look": {"values": look, "source": "profile"}}
    return out


def is_own(parts: dict, profile: str) -> bool:
    return bool(parts.get("profiles", {}).get(profile, {}).get("own"))


def own_app_keys(slot: str) -> tuple[str, ...]:
    """Settings an own profile writes in an app slot (bar, launcher, …).

    The authors' parts install files; our profiles describe the same pieces
    with settings, so picking one copies the profile's values for that piece.
    """
    from . import settings as settings_mod

    def group(gid: str) -> list[str]:
        return [s.key for s in settings_mod.group(gid).settings]

    keys = {
        "bar": ["BAR", "BAR_PRESET", *presets_mod.BAR_KEYS],
        "launcher": ["LAUNCHER", "LAUNCHER_PRESET", *presets_mod.LAUNCHER_KEYS,
                     *group("launcher")],
        "terminal": ["TERMINAL", "TERM_PRESET", *presets_mod.TERM_KEYS,
                     *group("terminal_look")],
        "notify": ["NOTIFIER", *group("notify")],
        "lock": group("lock"),
        "widget": ["WIDGET_ENGINE", "WIDGET_SET", *presets_mod.WIDGET_SET_KEYS,
                   *group("widget"), *group("visualizer")],
    }.get(slot, [])
    return tuple(dict.fromkeys(keys))


_OWN_VALUES: dict[tuple[str, str], dict[str, str]] = {}


def _own_values(root: Path, profile: str) -> dict[str, str]:
    key = (str(Path(root).resolve()), profile)
    if key not in _OWN_VALUES:
        _OWN_VALUES[key] = presets_mod.resolve_chain(Path(root), profile=profile)
    return _OWN_VALUES[key]


def own_app_values(root: Path, profile: str, slot: str) -> dict[str, str]:
    """The profile's values for one app slot; keys it leaves out get their defaults."""
    from . import settings as settings_mod
    defaults = {s.key: s.default for s in settings_mod.all_settings()}
    values = _own_values(root, profile)
    return {k: str(values.get(k, defaults.get(k, ""))) for k in own_app_keys(slot)
            if k in values or k in defaults}


def own_app_summary(root: Path, profile: str, slot: str) -> str | None:
    """Card subtitle of an own profile in an app slot; None = nothing to offer."""
    values = _own_values(root, profile)
    if slot == "bar":
        return " · ".join(v for v in (values.get("BAR", "waybar"), values.get("BAR_PRESET", "")) if v)
    if slot == "launcher":
        return values.get("LAUNCHER") or None
    if slot == "notify":
        return values.get("NOTIFIER") or None
    if slot == "terminal":
        return values.get("TERMINAL") or None
    if slot == "lock":
        return "hyprlock"
    if slot == "widget":
        widgets = presets_mod.split_widgets(values.get("WIDGETS", ""))
        return ", ".join(widgets[:4]) if widgets else None
    return None


def is_own_ref(parts: dict, slot: str, value: str) -> bool:
    """An app-slot value that names one of our profiles (not an author's part)."""
    return slot in APP_SLOT_IDS and bool(value) and "/" not in value and is_own(parts, value)


def slot_keys(slot: str) -> tuple[str, ...]:
    return SLOT_KEYS.get(slot) or own_app_keys(slot)


def load_parts(root: Path) -> dict:
    try:
        data = json.loads(parts_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {"profiles": {}}
    # Our own profiles come first in every slot, then the authors' rices.
    shipped = data.get("profiles") or {}
    data["profiles"] = {**own_parts(root), **shipped}
    # Imported ones (importer.py) live in a separate file; they do not take
    # precedence over the shipped ones.
    try:
        user = json.loads(user_parts_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        user = {}
    for name, entry in (user.get("profiles") or {}).items():
        if rice_mod.is_imported(root, name):
            data.setdefault("profiles", {}).setdefault(name, entry)
    # Not written to the file (scan deletes it first): lets options() look at the manifests.
    data["root"] = str(Path(root).resolve())
    return data


def scan_imported(root: Path, name: str, log=print) -> dict:
    """Writes the parts of an imported rice to the user's catalog."""
    path = user_parts_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {"profiles": {}}
    entry = scan_profile(root, name)
    data.setdefault("profiles", {})[name] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return entry


def forget_imported(name: str) -> None:
    path = user_parts_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    data.get("profiles", {}).pop(name, None)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for thumb in (rice_mod.imported_dir() / "thumbs").glob(f"{name}-*.jpg"):
        thumb.unlink(missing_ok=True)


def read_state(home: Path | None = None) -> dict:
    try:
        data = json.loads(state_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data.setdefault("slots", {})
    data.setdefault("saved", {})
    data.setdefault("before", {})
    return data


def write_state(state: dict, home: Path | None = None) -> None:
    path = state_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def split_ref(ref: str) -> tuple[str, str]:
    """``"ad1822/sis"`` → ``("ad1822", "sis")``; ``""`` if no variant is given."""
    profile, _, variant = (ref or "").partition("/")
    return profile.strip(), variant.strip()


# ------------------------------------------------- unpacking author files --
def stage_home(root: Path, profile: str, into: Path) -> Path:
    """Installs the rice into a temporary home directory (running no commands).

    The author's files are prepared with ``rice.prepare`` (Hyprland syntax
    updated, fixes applied), then copied into a fake home directory and the
    links are created — ``source = ~/.config/hypr/...`` lines and ``~/...``
    wallpaper paths resolve just like in a real install.
    """
    manifest = rice_mod.load(root, profile)
    home = into / "home"
    home.mkdir(parents=True, exist_ok=True)
    repo = rice_mod.fetch(manifest)
    groups = manifest.groups
    plan = rice_mod.prepare(manifest, repo, into / "staging", home, groups)
    for src, dest, _mode in plan.items:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir() and not src.is_symlink():
            shutil.copytree(src, dest, symlinks=True, dirs_exist_ok=True)
        elif src.exists() or src.is_symlink():
            shutil.copy2(src, dest, follow_symlinks=False)
    for link_to, link_target in manifest.links:
        link = rice_mod.expand(link_to, home)
        if link.exists() or link.is_symlink():
            continue
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(rice_mod.expand(link_target, home))
    return home


# ---------------------------------------------------------- hyprlang reader --
def _strip_comment(line: str) -> str:
    # In hyprlang "##" means a literal "#"; a single "#" starts a comment.
    return line.replace("##", "\0").split("#", 1)[0].replace("\0", "#").strip()


def _source_targets(value: str, base: Path, home: Path) -> list[Path]:
    text = value.strip().strip('"').replace("${HOME}", str(home)).replace("$HOME", str(home))
    if text.startswith("~"):
        path = home / text.lstrip("~").lstrip("/")
    elif os.path.isabs(text):
        path = Path(text)
        # Absolute path into the author's own home (/home/author/.config/...).
        match = re.match(r"^/home/[^/]+/(.*)$", text)
        if match and not path.exists():
            path = home / match.group(1)
    else:
        path = base / text
    return [Path(p) for p in sorted(glob.glob(str(path)))]


def parse_hyprlang(entry: Path, home: Path) -> tuple[dict[str, str], list[str]]:
    """Flattens values starting from the main file, following the ``source`` chain.

    The returned dict has the form ``"decoration:blur:size" → "3"`` (last
    write wins, as in Hyprland); the second value is the ``bezier``/``animation``
    lines from the animations block, in the order they were written.
    """
    values: dict[str, str] = {}
    animation: list[str] = []
    variables: dict[str, str] = {}
    seen: set[Path] = set()

    def expand(text: str) -> str:
        for name in sorted(variables, key=len, reverse=True):
            text = text.replace("$" + name, variables[name])
        return text

    def walk(path: Path) -> None:
        key_path = path.resolve()
        if key_path in seen or not path.is_file():
            return
        seen.add(key_path)
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return
        stack: list[str] = []
        for raw in text.splitlines():
            line = _strip_comment(raw)
            while line.startswith("}"):
                if stack:
                    stack.pop()
                line = line[1:].strip()
            if not line:
                continue
            if line.endswith("{"):
                stack.append(line[:-1].strip().split("[", 1)[0].strip())
                continue
            key, sep, value = line.partition("=")
            if not sep:
                continue
            key, value = key.strip(), value.strip()
            closes = 0
            while value.endswith("}"):              # "blur { size = 3 }" on one line
                value = value[:-1].strip()
                closes += 1
            if key.startswith("$"):
                variables[key[1:]] = expand(value)
                continue
            value = expand(value)
            if key == "source" and not stack:
                for target in _source_targets(value, path.parent, home):
                    walk(target)
                continue
            full = ":".join([*stack, key])
            leaf = full.rsplit(":", 1)[-1]
            if leaf in ("bezier", "animation") and full.startswith(("animations:", "bezier",
                                                                    "animation")):
                animation.append(f"{leaf} = {value}")
            else:
                values[full] = value
            for _ in range(closes):
                if stack:
                    stack.pop()

    walk(entry)
    return values, animation


# --------------------------------------------------------------- Lua reader ---
_LUA_ASSIGN_TABLE = re.compile(r"([A-Za-z_]\w*)\s*=\s*\{")
_LUA_ASSIGN_VALUE = re.compile(
    r"""([A-Za-z_]\w*)\s*=\s*("(?:[^"\\]|\\.)*"|'[^']*'|0x[0-9a-fA-F]+|[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?|true|false)\s*(?=[,}\n])""")
_LUA_ASSIGN_OTHER = re.compile(r"([A-Za-z_]\w*)\s*=\s*")
_LUA_CURVE = re.compile(
    r'hl\.curve\(\s*"([^"]+)"\s*,\s*\{[^{}]*points\s*=\s*\{\s*\{\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\}'
    r'\s*,\s*\{\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\}')
_LUA_ANIMATION = re.compile(r"hl\.animation\(\s*\{(.*?)\}\s*\)", re.S)
_LUA_PAIR = re.compile(r'(\w+)\s*=\s*("([^"]*)"|[\w.%-]+)')


def _lua_strip(text: str) -> str:
    text = re.sub(r"--\[\[.*?\]\]", "", text, flags=re.S)
    return re.sub(r"--[^\n]*", "", text)


def _lua_config_blocks(text: str) -> dict[str, str]:
    """``hl.config({ general = { gaps_in = 4 } })`` → ``{"general:gaps_in": "4"}``."""
    values: dict[str, str] = {}
    for match in re.finditer(r"hl\.config\s*\(\s*\{", text):
        i, stack = match.end(), []
        while i < len(text):
            ch = text[i]
            if ch.isspace() or ch == ",":
                i += 1
                continue
            if ch == "}":
                if not stack:
                    break
                stack.pop()
                i += 1
                continue
            m = _LUA_ASSIGN_TABLE.match(text, i)
            if m:
                stack.append(m.group(1))
                i = m.end()
                continue
            if ch == "{":
                stack.append("")
                i += 1
                continue
            m = _LUA_ASSIGN_VALUE.match(text, i)
            if m:
                if "" not in stack:
                    values[":".join([*stack, m.group(1)])] = m.group(2).strip("\"'")
                i = m.end()
                continue
            m = _LUA_ASSIGN_OTHER.match(text, i)
            if m:
                # Variable/expression (active_border = RED): skip the value.
                i = m.end()
                depth = 0
                while i < len(text):
                    c = text[i]
                    if c in "({":
                        depth += 1
                    elif c in ")}":
                        if depth == 0:
                            break
                        depth -= 1
                    elif c == "," and depth == 0:
                        break
                    i += 1
                continue
            i += 1
    return values


def parse_lua(hypr: Path) -> tuple[dict[str, str], list[str]]:
    """Values and animations from a Lua config (Hyprland 0.56+)."""
    from .keybinds import RICE_OVERLAY_LUA

    files = [hypr / "hyprland.lua"] + sorted(
        p for p in hypr.rglob("*.lua")
        if p.name not in ("hyprland.lua", RICE_OVERLAY_LUA) and "quickshell" not in p.parts)
    values: dict[str, str] = {}
    animation: list[str] = []
    for path in files:
        try:
            text = _lua_strip(path.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
        values.update(_lua_config_blocks(text))
        for m in _LUA_CURVE.finditer(text):
            animation.append("bezier = " + ", ".join(m.groups()))
        for m in _LUA_ANIMATION.finditer(text):
            pairs = {k: (q if q is not None and raw.startswith('"') else raw)
                     for k, raw, q in _LUA_PAIR.findall(m.group(1))}
            leaf = pairs.get("leaf", "")
            if not leaf:
                continue
            if pairs.get("enabled", "true") == "false":
                animation.append(f"animation = {leaf}, 0")
                continue
            parts = [leaf, "1", pairs.get("speed", "10"), pairs.get("bezier", "default")]
            if pairs.get("style"):
                parts.append(pairs["style"])
            animation.append("animation = " + ", ".join(parts))
    return values, animation


# ------------------------------------------------------------------ look -------
def _convert(value: str, kind: str) -> str | None:
    text = value.strip().strip("\"'")
    if kind == "bool":
        low = text.lower()
        if low in ("true", "yes", "on", "1"):
            return "true"
        if low in ("false", "no", "off", "0"):
            return "false"
        return None
    if kind == "offset":
        nums = re.findall(r"-?\d+(?:\.\d+)?", text)
        return " ".join(str(round(float(n))) for n in nums[:2]) if len(nums) >= 2 else None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    number = float(match.group(0))
    if kind == "int":
        # "gaps_out = 5,10,10,10" (CSS shorthand): first value — the setting is one number.
        return str(max(0, round(number)))
    return str(round(number, 4))


def look_settings(values: dict[str, str], animation: list[str]) -> dict[str, str]:
    """Flattened Hyprland values → this project's settings (missing ones with
    Hyprland's defaults)."""
    out = dict(LOOK_DEFAULTS)
    for key, (setting, kind) in _LOOK_MAP.items():
        if key in values:
            converted = _convert(values[key], kind)
            if converted is not None:
                out[setting] = converted
    out["ANIMATION_PRESET"] = "custom"
    out["ANIMATION_CUSTOM"] = ";;".join(animation)
    return out


def read_look(root: Path, profile: str, home: Path) -> dict | None:
    """The rice's window look; if the author did not share a Hyprland config
    (rice.conf mode), the profile's own values."""
    hypr = home / ".config" / "hypr"
    entry_name = rice_mod.load(root, profile).hypr_entry or "hyprland.conf"
    source = ""
    if (hypr / "hyprland.lua").is_file() and not (hypr / "hyprland.conf").is_file():
        values, animation = parse_lua(hypr.resolve())
        source = "hyprland.lua"
    elif (hypr / entry_name).is_file() or (hypr / "hyprland.conf").is_file():
        entry = hypr / entry_name if (hypr / entry_name).is_file() else hypr / "hyprland.conf"
        values, animation = parse_hyprlang(entry, home)
        source = entry.name
    else:
        values, animation = {}, []
    if not source and (hypr / "rice.conf").is_file():
        # rice.conf mode (athena, vantage): the Hyprland config comes from this
        # project's template; look = project defaults + the profile's .conf
        # values + what the author overrides in rice.conf.
        from . import settings as settings_mod

        defaults = settings_mod.defaults()
        out = {k: defaults.get(k, v) for k, v in LOOK_DEFAULTS.items()}
        preset = presets_mod.find(presets_mod.default_dir(root, "profile"), profile)
        own = preset.values if preset else {}
        out.update({k: v for k, v in own.items() if k in LOOK_DEFAULTS})
        out["ANIMATION_PRESET"] = own.get("ANIMATION_PRESET",
                                          defaults.get("ANIMATION_PRESET", "default"))
        out["ANIMATION_CUSTOM"] = ""
        values, animation = parse_hyprlang(hypr / "rice.conf", home)
        for key, (setting, kind) in _LOOK_MAP.items():
            converted = _convert(values[key], kind) if key in values else None
            if converted is not None:
                out[setting] = converted
        if animation:
            out["ANIMATION_PRESET"] = "custom"
            out["ANIMATION_CUSTOM"] = ";;".join(animation)
        return {"values": out, "source": "rice.conf"}
    if not any(k in values for k in _LOOK_MAP):
        return None
    return {"values": look_settings(values, animation), "source": source}


# -------------------------------------------------------------- wallpaper ------
def _suffix(source: str, dest: str) -> str:
    for text in (dest, urlparse(source.partition("#")[2] or source).path):
        suffix = Path(text).suffix.lower()
        if suffix and len(suffix) <= 5:
            return suffix
    return ".jpg"


def _still(video: Path) -> Path | None:
    """Frame at second 1 of a video wallpaper (for the palette and a still image)."""
    still = video.with_name(video.stem + ".still.jpg")
    if still.is_file():
        return still
    if not shutil.which("ffmpeg"):
        return None
    out = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", "1", "-i", str(video),
                          "-frames:v", "1", str(still)],
                         capture_output=True, check=False, timeout=120)
    return still if out.returncode == 0 and still.is_file() else None


def fetch_wallpaper(root: Path, profile: str, variant: str,
                    home: Path | None = None, staged: Path | None = None) -> tuple[Path | None, bool]:
    """Fetches a look's wallpaper into the cache: (still image, is video).

    The source may be a URL, a repo-relative path, an absolute path installed
    by a package, or among the author's files (``~/...``); for the last one
    the rice is unpacked into a temporary home (``staged`` is used if given).
    """
    if variant == OWN_VARIANT and not rice_mod.is_rice(Path(root), profile):
        return _own_image(root, presets_mod.resolve_chain(Path(root), profile=profile)), False
    manifest = rice_mod.load(root, profile)
    chosen = manifest.variants.get(variant)
    if chosen is None or not chosen.wallpaper:
        return None, False
    cache = wallpaper_cache(home)
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / f"{profile}-{variant}{_suffix(chosen.wallpaper, chosen.wallpaper_dest)}"
    video = target.suffix in _VIDEO
    if not target.is_file():
        source = chosen.wallpaper
        try:
            if "://" in source:
                rice_mod._download(source, target, home)        # noqa: SLF001
            elif source.startswith("~/"):
                if staged is None:
                    with tempfile.TemporaryDirectory(prefix="hyprsetup-mix-") as tmp:
                        fake = stage_home(root, profile, Path(tmp))
                        found = rice_mod.expand(source, fake)
                        if found.is_file():
                            shutil.copyfile(found, target)
                else:
                    found = rice_mod.expand(source, staged)
                    if found.is_file():
                        shutil.copyfile(found, target)
            else:
                found = Path(source) if os.path.isabs(source) else Path(root) / source
                if found.is_file():
                    shutil.copyfile(found, target)
        except (OSError, RuntimeError, ValueError):
            return None, video
    if not target.is_file():
        return None, video
    return (_still(target) if video else target), video


# ------------------------------------------------------------------ scanning ----
def _variant_colors(root: Path, profile: str, variant: str,
                    image: Path | None) -> dict | None:
    values = presets_mod.resolve_chain(root, profile=profile, variant=variant)
    theme = values.get("THEME", "")
    if theme in themes.THEMES:
        return {"theme": theme}
    if image is None:
        return None
    from . import palette as palette_mod
    extracted = palette_mod.extract(image, dark=True)
    return {"palette": extracted} if extracted else None


def scan_profile(root: Path, profile: str, home: Path | None = None,
                 previous: dict | None = None, log=print) -> dict:
    """A rice's parts: its looks (wallpaper + colors) and its window
    look.

    ``previous`` is the profile's existing entry: if a wallpaper cannot be
    fetched on this machine (package not installed, download failed) the
    earlier result is kept instead of being downgraded to "no wallpaper"."""
    old_variants = (previous or {}).get("variants", {})
    manifest = rice_mod.load(root, profile)
    preset = presets_mod.find(presets_mod.default_dir(root, "profile"), profile)
    entry: dict = {"title": preset.label if preset else profile,
                   "repo": manifest.repo, "variants": {}, "look": None}
    with tempfile.TemporaryDirectory(prefix="hyprsetup-mix-") as tmp:
        staged = stage_home(root, profile, Path(tmp))
        entry["look"] = read_look(root, profile, staged)
        for name, variant in manifest.variants.items():
            image, video = fetch_wallpaper(root, profile, name, home, staged)
            if image is not None:
                _make_thumbnail(image, thumbnail_path(root, profile, name))
            elif old_variants.get(name, {}).get("wallpaper"):
                log(f"  {profile}/{name}: wallpaper not available here, keeping the previous result")
                entry["variants"][name] = old_variants[name]
                continue
            entry["variants"][name] = {
                "title": variant.title or name,
                "credit": variant.credit,
                "wallpaper": bool(image),
                "video": video,
                "colors": _variant_colors(root, profile, name, image),
            }
    return entry


def scan(root: Path, profiles: list[str] | None = None,
         home: Path | None = None, log=print) -> dict:
    """(Re)generates ``presets/mix/parts.json``; the given profiles are
    updated, the others stay as they are."""
    data = load_parts(root)
    data.pop("root", None)
    data["profiles"] = {k: v for k, v in data.get("profiles", {}).items()
                        if not v.get("own")}
    names = profiles or [n for n in rice_mod.all_profiles(root)
                         if not rice_mod.is_imported(root, n)]
    for name in names:
        try:
            data["profiles"][name] = scan_profile(
                root, name, home, data["profiles"].get(name), log)
            log(f"  {name}: ok")
        except Exception as exc:                                  # noqa: BLE001
            log(f"  {name}: ERROR — {exc}")
    data["profiles"] = dict(sorted(data["profiles"].items()))
    path = parts_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return data


# ---------------------------------------------------------------- options ----
def options(parts: dict, slot: str) -> list[tuple[str, str]]:
    """Parts that can go into a slot: (value, label)."""
    out: list[tuple[str, str]] = []
    if slot == "colors":
        out.append((COLORS_FROM_WALLPAPER, "From the selected wallpaper"))
    for name, entry in parts.get("profiles", {}).items():
        seen: set[str] = set()
        if slot == "wallpaper":
            # Looks sharing the same image (athena: four colors, one
            # wallpaper) are listed once.
            try:
                sources = {v: m.wallpaper for v, m in rice_mod.load(
                    Path(parts.get("root", ".")), name).variants.items()}                     if parts.get("root") else {}
            except (OSError, ValueError, KeyError):
                sources = {}
        if slot == "look":
            if entry.get("look"):
                out.append((name, entry["title"]))
            continue
        for variant, info in entry.get("variants", {}).items():
            label = (entry["title"] if entry.get("own")
                     else f"{entry['title']} — {info['title']}")
            if slot == "wallpaper" and info.get("wallpaper"):
                source = sources.get(variant) or variant
                if source in seen:
                    continue
                seen.add(source)
                out.append((f"{name}/{variant}", label))
            elif slot == "colors" and info.get("colors"):
                out.append((f"{name}/{variant}", label))
    return out


def palette_of(parts: dict, ref: str) -> dict[str, str] | None:
    """11-key palette of a color part (for preview and comparison)."""
    profile, variant = split_ref(ref)
    info = parts.get("profiles", {}).get(profile, {}).get("variants", {}).get(variant, {})
    colors = info.get("colors") or {}
    if "theme" in colors:
        return themes.resolve(colors["theme"])
    return dict(colors["palette"]) if colors.get("palette") else None


def describe(parts: dict, slot: str, value: str) -> str:
    if not value:
        return "your own settings"
    return dict(options(parts, slot)).get(value, value)


# ------------------------------------------------------ mapping to settings ---
def _wallpaper_hint(root: Path, profile: str, variant: str) -> str:
    """Why fetch_wallpaper came back empty, in words the user can act on."""
    manifest = rice_mod.load(root, profile)
    chosen = manifest.variants.get(variant)
    source = chosen.wallpaper if chosen else ""
    if "://" in source:
        return " (download failed — check the internet connection)"
    if os.path.isabs(source) and not Path(source).is_file():
        # e.g. athena: /usr/share/backgrounds/archlinux/… from archlinux-wallpaper
        names = [p for p in (*manifest.packages_repo, *manifest.packages_aur)
                 if "wallpaper" in p or "background" in p]
        need = f"install {', '.join(names)}" if names else "it comes with a package of this rice"
        return f" ({source} is missing — {need})"
    return ""


def slot_values(root: Path, parts: dict, slot: str, value: str,
                home: Path | None = None) -> dict[str, str]:
    """Settings a slot selection writes. The wallpaper slot also puts the image
    under ``~/Pictures/wallpapers``."""
    home_dir = Path(home) if home else Path.home()
    if slot == "wallpaper":
        profile, variant = split_ref(value)
        info = parts.get("profiles", {}).get(profile, {}).get("variants", {}).get(variant, {})
        wp_id = (info.get("wpengine") or "").strip()
        if wp_id:
            return {"WALLPAPER_DAEMON": "wallpaperengine", "WPENGINE_ID": wp_id,
                    "WALLPAPER_IMAGE": "", "WALLPAPER_STYLE": ""}
        image, _video = fetch_wallpaper(root, profile, variant, home)
        if image is None:
            raise RuntimeError(f"could not fetch wallpaper: {value}"
                               f"{_wallpaper_hint(root, profile, variant)}")
        dest = home_dir / "Pictures" / "wallpapers" / f"mix-{profile}-{variant}{image.suffix}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.is_file() or dest.read_bytes() != image.read_bytes():
            shutil.copyfile(image, dest)
        return {"WALLPAPER_PATH": "~/" + str(dest.relative_to(home_dir)),
                "WALLPAPER_IMAGE": "", "WALLPAPER_STYLE": ""}
    if slot == "colors":
        if value == COLORS_FROM_WALLPAPER:
            return {"THEME": "auto", "CUSTOM_COLORS": ""}
        profile, variant = split_ref(value)
        info = parts["profiles"][profile]["variants"][variant]
        colors = info.get("colors") or {}
        if "theme" in colors:
            return {"THEME": colors["theme"], "CUSTOM_COLORS": ""}
        palette = colors.get("palette")
        if not palette:
            raise RuntimeError(f"no color scheme: {value}")
        return {"THEME": themes.DEFAULT,
                "CUSTOM_COLORS": themes.format_overrides(palette, themes.DEFAULT)}
    if slot == "look":
        look = parts["profiles"][value].get("look")
        if not look:
            raise RuntimeError(f"no window look: {value}")
        return dict(look["values"])
    if is_own_ref(parts, slot, value):
        return own_app_values(root, value, slot)
    raise ValueError(f"unknown slot: {slot}")


def with_daemon(values: dict[str, str], is_selected) -> dict[str, str]:
    """``values`` plus WALLPAPER_DAEMON, which is derived from the component
    selection (not stored as a setting); plan() needs it to see a live
    Wallpaper Engine scene."""
    out = dict(values)
    for daemon in ("wallpaperengine", "hyprpaper", "swww", "waypaper"):
        if is_selected(daemon):
            out["WALLPAPER_DAEMON"] = daemon
            break
    return out


def plan(root: Path, slots: dict[str, str], current: dict[str, str],
         home: Path | None = None) -> tuple[dict[str, str], dict]:
    """Setting changes for a new slot selection, and the updated state.

    ``current``: the current settings (settings.conf). When a slot is first
    filled, the current values of the keys it will write are saved under
    ``before``; when the slot is cleared they are written back.
    """
    parts = load_parts(root)
    state = read_state(home)
    changes: dict[str, str] = {}
    for slot in (*SLOT_IDS, *APP_SLOT_IDS):
        old = state["slots"].get(slot, "")
        new = (slots.get(slot, old) or "").strip()
        if slot in APP_SLOT_IDS:
            # Only our profiles are settings here; an author's part is
            # installed as files by install_parts (and replaces ours).
            if new and not is_own_ref(parts, slot, new):
                new = ""
            if not new and not old:
                continue
        if new:
            if not old:
                state["before"][slot] = {k: current.get(k, "") for k in slot_keys(slot)}
            else:
                before = state["before"].setdefault(slot, {})
                for k in slot_keys(slot):
                    before.setdefault(k, current.get(k, ""))
            slot_ch = slot_values(root, parts, slot, new, home)
            changes.update(slot_ch)
            if (slot == "wallpaper"
                    and slot_ch.get("WALLPAPER_DAEMON") != "wallpaperengine"
                    and current.get("WALLPAPER_DAEMON") == "wallpaperengine"):
                # A live Wallpaper Engine scene covers any image: show the
                # picked wallpaper with an image daemon (back on mix off).
                changes["WALLPAPER_DAEMON"] = next(
                    (d for d in ("hyprpaper", "swww") if shutil.which(d)), "hyprpaper")
            state["slots"][slot] = new
        elif old:
            changes.update(state["before"].pop(slot, {}))
            state["slots"].pop(slot, None)
    return changes, state


def preview_values(root: Path, parts: dict, pending: dict[str, str],
                   current: dict[str, str],
                   home: Path | None = None) -> dict[str, str]:
    """What the settings would be if the pending selection were applied — preview only.

    Unlike plan() it has no side effects: the wallpaper is not downloaded and
    copied to ~/Pictures, its small preview (thumbnail_path) is shown instead;
    nothing is written to the state file either. A cleared slot, if it was
    applied, returns to its pre-mix values (same rule as plan).
    """
    state = read_state(home)
    values = dict(current)
    for slot in (*SLOT_IDS, *APP_SLOT_IDS):
        new = (pending.get(slot, "") or "").strip()
        if slot in APP_SLOT_IDS and not is_own_ref(parts, slot, new):
            if not new and state["slots"].get(slot):
                values.update(state["before"].get(slot, {}))
            continue
        if new:
            if slot == "wallpaper":
                profile, variant = split_ref(new)
                info = parts.get("profiles", {}).get(profile, {}).get("variants", {}).get(variant, {})
                wp_id = (info.get("wpengine") or "").strip()
                if wp_id:
                    values.update({"WALLPAPER_DAEMON": "wallpaperengine", "WPENGINE_ID": wp_id,
                                   "WALLPAPER_PATH": "", "WALLPAPER_IMAGE": "", "WALLPAPER_STYLE": ""})
                else:
                    values.update({"WALLPAPER_DAEMON": "hyprpaper", "WPENGINE_ID": "",
                                   "WALLPAPER_PATH": str(thumbnail_path(root, profile, variant)),
                                   "WALLPAPER_IMAGE": "", "WALLPAPER_STYLE": ""})
                continue
            try:
                values.update(slot_values(root, parts, slot, new, home))
            except (RuntimeError, KeyError, ValueError):
                continue
        elif state["slots"].get(slot):
            values.update(state["before"].get(slot, {}))
    return values


def selection(home: Path | None = None) -> dict[str, str]:
    """Current selection of all slots (setting slots + app parts)."""
    state = read_state(home)
    return {**state["slots"], **state.get("parts", {})}


def save(name: str, home: Path | None = None,
         chosen: dict[str, str] | None = None) -> dict[str, str]:
    """Saves the mix under a name: if ``chosen`` is not given, the one currently applied."""
    state = read_state(home)
    current = ({k: v for k, v in chosen.items() if v} if chosen is not None
               else {**state["slots"], **state.get("parts", {})})
    if not current:
        raise ValueError("no mix to save (no slot is filled)")
    state["saved"][name] = current
    write_state(state, home)
    return current


def saved(name: str, home: Path | None = None) -> dict[str, str]:
    found = read_state(home)["saved"].get(name)
    if found is None:
        raise KeyError(name)
    # A slot missing from the saved mix means "your own settings": it is cleared.
    return {slot: found.get(slot, "") for slot in (*SLOT_IDS, *APP_SLOT_IDS)}


def delete_saved(name: str, home: Path | None = None) -> None:
    state = read_state(home)
    state["saved"].pop(name, None)
    write_state(state, home)


# --------------------------------------------------------------- app parts --
#: Slots of the parts that come with the author's files (see rice.Part).
APP_SLOTS: tuple[tuple[str, str], ...] = (
    ("bar", "Status bar"),
    ("launcher", "Launcher"),
    ("notify", "Notifications"),
    ("terminal", "Terminal"),
    ("lock", "Lock screen"),
    ("widget", "Desktop widgets"),
)
APP_SLOT_IDS = tuple(s for s, _ in APP_SLOTS)

#: Command variable → the slot owning that job (see install_parts).
_COMMAND_SLOT = {"CMD_LAUNCHER": "launcher", "CMD_DMENU": "launcher",
                 "DMENU_PROMPT_FLAG": "launcher", "CMD_TERMINAL": "terminal",
                 "LOCK_CMD": "lock"}

#: Processes started by parts run in this slice; when the mix changes they
#: stop with a single command (same idea as rice.SLICE).
SLICE = "hyprsetup-mix.slice"
HYPR_CONF = "mix.conf"            # ~/.config/hypr/ — the parts' startup lines
HYPR_LUA = "mix.lua"

#: Files that get recolored: text formats (no extension: dunstrc, config…).
_TEXT_SUFFIXES = {"", ".css", ".scss", ".sass", ".rasi", ".conf", ".ini", ".json",
                  ".jsonc", ".toml", ".qml", ".yuck", ".js", ".ts", ".sh", ".py",
                  ".lua", ".theme", ".txt", ".yaml", ".yml", ".xml", ".svg"}


def app_parts(root: Path) -> dict[str, list[tuple[str, rice_mod.Part]]]:
    """Slot → [(``profile/part``, part)] — the parts of all rices."""
    out: dict[str, list[tuple[str, rice_mod.Part]]] = {s: [] for s in APP_SLOT_IDS}
    for name in rice_mod.all_profiles(root):
        try:
            manifest = rice_mod.load(root, name)
        except (OSError, ValueError, KeyError):
            continue                     # a broken import must not break the list
        for part in manifest.parts:
            out.setdefault(part.slot, []).append((f"{name}/{part.id}", part))
    return out


def find_part(root: Path, ref: str) -> tuple[str, rice_mod.Part]:
    profile, part_id = split_ref(ref)
    for part in rice_mod.load(root, profile).parts:
        if part.id == part_id:
            return profile, part
    raise KeyError(ref)


def part_label(root: Path, ref: str) -> str:
    try:
        profile, part = find_part(root, ref)
    except (KeyError, OSError, ValueError):
        return ref
    preset = presets_mod.find(presets_mod.default_dir(root, "profile"), profile)
    owner = (preset.label.split(" — ")[0] if preset else profile)
    return f"{owner} — {part.title or part.slot}"


# ------------------------------------------------------------------ recoloring --


class Recolor:
    """Translates the author's colors into the user's palette.

    Each color is mapped to its perceptually closest role in the author's
    palette (BG, ACCENT, RED…) and that role's value in the new palette is
    written; opacity is kept. The author's palette comes from the rice's own
    look (parts.json).
    """

    #: Colors below this saturation (Lab chroma) count as neutral: a neutral
    #: color is only mapped to neutral roles (BG, FG…), a colorful one only to
    #: colorful roles (ACCENT, RED…) — otherwise a light blue accent could turn
    #: into the secondary text color just because its lightness was close.
    _NEUTRAL = 18.0

    def __init__(self, author: dict[str, str], target: dict[str, str]):
        self.author = {k: (v, palette_mod.hex_lab(v)) for k, v in author.items() if k in target}
        self.target = target
        self._cache: dict[str, str] = {}

    @classmethod
    def _chroma(cls, lab: tuple[float, float, float]) -> float:
        return (lab[1] ** 2 + lab[2] ** 2) ** 0.5

    def hex6(self, value: str) -> str:
        value = value.lower()
        if value not in self._cache:
            lab = palette_mod.hex_lab(value)
            neutral = self._chroma(lab) < self._NEUTRAL
            same = [k for k, (_v, label) in self.author.items()
                    if (self._chroma(label) < self._NEUTRAL) == neutral] or list(self.author)
            role = min(same, key=lambda k: sum(
                (a - b) ** 2 for a, b in zip(self.author[k][1], lab, strict=False)))
            self._cache[value] = self.target[role].lower()
        return self._cache[value]

    _HEX = re.compile(r"(?<![\w&])#([0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![\w-])")
    _HYPR = re.compile(r"\b(rgba?)\(([0-9a-fA-F]{6})([0-9a-fA-F]{2})?\)")
    _FUNC = re.compile(r"\b(rgba?)\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*"
                       r"(,\s*[\d.]+%?\s*)?\)")

    #: Colors whose name carries their meaning (wallust/pywal templates, kitty):
    #: mapped by NAME rather than to the nearest color. saatvik333's colors.css
    #: is a snapshot generated from a light wallpaper (light background, dark
    #: foreground); nearest-color mapping made "foreground" dark on a dark
    #: theme, and the bar's text was unreadable.
    _NAMED_ROLES = {
        "background": "BG", "foreground": "FG", "cursor": "FG",
        "selection_background": "SURFACE", "selection_foreground": "FG",
        "color0": "SURFACE", "color1": "RED", "color2": "GREEN", "color3": "YELLOW",
        "color4": "ACCENT", "color5": "ACCENT2", "color6": "CYAN", "color7": "FG",
        "color8": "SUBTEXT", "color9": "RED", "color10": "GREEN", "color11": "YELLOW",
        "color12": "ACCENT", "color13": "ACCENT2", "color14": "CYAN", "color15": "FG",
    }
    _NAMED = re.compile(
        r"^(\s*(?:@define-color\s+|\$|--)?)(" + "|".join(sorted(_NAMED_ROLES, key=len, reverse=True))
        + r")(\s*[:=]?\s*[\"']?#)([0-9a-fA-F]{6})(?![0-9a-fA-F])", re.M)

    def text(self, text: str, argb: bool = False) -> str:
        # Lines mapped by name skip the general mapping (so the new color is not
        # mapped to the nearest role again and broken): parked in a placeholder first.
        named: list[str] = []

        def named_sub(m: re.Match) -> str:
            role = self._NAMED_ROLES[m.group(2)]
            if role not in self.target:
                return m.group(0)
            named.append(self.target[role].lower())
            return f"{m.group(1)}{m.group(2)}{m.group(3)}\0{len(named) - 1}\0"

        text = self._NAMED.sub(named_sub, text)

        def hex_sub(m: re.Match) -> str:
            raw = m.group(1)
            if len(raw) == 8:
                # QML (Qt) #AARRGGBB, CSS #RRGGBBAA.
                alpha, rgb = (raw[:2], raw[2:]) if argb else (raw[6:], raw[:6])
                new = self.hex6(rgb)
                return "#" + (alpha + new if argb else new + alpha)
            return "#" + self.hex6(raw)

        def hypr_sub(m: re.Match) -> str:
            return f"{m.group(1)}({self.hex6(m.group(2))}{m.group(3) or ''})"

        def func_sub(m: re.Match) -> str:
            rgb = [int(m.group(i)) for i in (2, 3, 4)]
            if max(rgb) > 255:
                return m.group(0)
            new = self.hex6("".join(f"{c:02x}" for c in rgb))
            parts = ", ".join(str(int(new[i:i + 2], 16)) for i in (0, 2, 4))
            return f"{m.group(1)}({parts}{m.group(5) or ''})"

        text = self._HEX.sub(hex_sub, text)
        text = self._HYPR.sub(hypr_sub, text)
        text = self._FUNC.sub(func_sub, text)
        return re.sub(r"\0(\d+)\0", lambda m: named[int(m.group(1))], text)

    def file(self, path: Path) -> bool:
        if path.is_symlink() or path.suffix.lower() not in _TEXT_SUFFIXES:
            return False
        try:
            if path.stat().st_size > 2_000_000:
                return False
            data = path.read_bytes()
        except OSError:
            return False
        if b"\0" in data:
            return False
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return False
        new = self.text(text, argb=path.suffix.lower() == ".qml")
        if new != text:
            path.write_text(new, encoding="utf-8")
            return True
        return False


def current_palette(values: dict[str, str]) -> dict[str, str]:
    """Palette produced by the settings (same rule as render.derived_vars)."""
    from . import render as render_mod

    return render_mod.effective_palette(values)[1]


def author_palette(parts: dict, profile: str, root: Path) -> dict[str, str]:
    """Palette of the rice's default look (the source for recoloring)."""
    entry = parts.get("profiles", {}).get(profile, {})
    manifest = rice_mod.load(root, profile)
    order = [manifest.default_variant, *entry.get("variants", {})]
    for variant in order:
        found = palette_of(parts, f"{profile}/{variant}")
        if found:
            return found
    return themes.resolve(themes.DEFAULT)


# ------------------------------------------------------------ palette files --
_PYWAL_ORDER = ("BG", "RED", "GREEN", "YELLOW", "ACCENT", "ACCENT2", "CYAN", "FG",
                "SURFACE", "RED", "GREEN", "YELLOW", "ACCENT", "ACCENT2", "CYAN", "FG")


def palette_file(kind: str, palette: dict[str, str], wallpaper: str) -> str:
    colors = ["#" + palette[k] for k in _PYWAL_ORDER]
    if kind == "pywal":
        return json.dumps({
            "wallpaper": wallpaper, "alpha": "100",
            "special": {"background": "#" + palette["BG"], "foreground": "#" + palette["FG"],
                        "cursor": "#" + palette["FG"]},
            "colors": {f"color{i}": c for i, c in enumerate(colors)},
        }, indent=4) + "\n"
    if kind == "kitty":
        lines = [f"foreground #{palette['FG']}", f"background #{palette['BG']}",
                 f"cursor #{palette['FG']}", f"selection_background #{palette['SURFACE']}",
                 f"selection_foreground #{palette['FG']}",
                 f"active_border_color #{palette['ACCENT']}",
                 f"active_tab_background #{palette['ACCENT']}",
                 f"active_tab_foreground #{palette['BG']}"]
        lines += [f"color{i} {c}" for i, c in enumerate(colors)]
        return "\n".join(lines) + "\n"
    raise ValueError(f"unknown palette file format: {kind}")


#: Material You (matugen) color roles → this project's palette roles. If the
#: author's file is generated by a matugen template AT RUNTIME (ilyamiro: rofi's
#: theme.rasi, swaync's style.css) it is not in the repo; the mix does not run
#: matugen, the template is filled with the user's palette.
_MATUGEN_ROLES = {
    "background": "BG", "on_background": "FG",
    "surface": "BG", "surface_dim": "BG_DARK", "surface_bright": "SURFACE",
    "surface_container_lowest": "BG_DARK", "surface_container_low": "BG",
    "surface_container": "SURFACE", "surface_container_high": "SURFACE",
    "surface_container_highest": "SURFACE", "surface_variant": "SURFACE",
    "on_surface": "FG", "on_surface_variant": "SUBTEXT",
    "outline": "SUBTEXT", "outline_variant": "SURFACE",
    "inverse_surface": "FG", "inverse_on_surface": "BG", "inverse_primary": "ACCENT",
    "primary": "ACCENT", "on_primary": "BG", "primary_container": "SURFACE",
    "on_primary_container": "FG", "primary_fixed": "ACCENT", "primary_fixed_dim": "ACCENT",
    "secondary": "ACCENT2", "on_secondary": "BG", "secondary_container": "SURFACE",
    "on_secondary_container": "FG", "secondary_fixed": "ACCENT2",
    "tertiary": "CYAN", "on_tertiary": "BG", "tertiary_container": "SURFACE",
    "on_tertiary_container": "FG", "tertiary_fixed": "CYAN",
    "error": "RED", "on_error": "BG", "error_container": "RED", "on_error_container": "BG",
    "source_color": "ACCENT", "shadow": "BG_DARK", "scrim": "BG_DARK",
}
_MATUGEN_TAG = re.compile(r"\{\{\s*colors\.(\w+)\.(?:default|dark|light)\.(\w+)\s*(\|[^}]*)?\}\}")


def render_matugen(template: str, palette: dict[str, str], wallpaper: str) -> str:
    """Fills a matugen template with the user's palette (hex, hex_stripped, rgb, rgba)."""
    def sub(m: re.Match) -> str:
        hex6 = palette.get(_MATUGEN_ROLES.get(m.group(1), "ACCENT"), palette["ACCENT"]).lower()
        fmt = m.group(2)
        if fmt == "hex_stripped":
            return hex6
        if fmt in ("rgb", "rgba"):
            r, g, b = (int(hex6[i:i + 2], 16) for i in (0, 2, 4))
            return f"rgb({r}, {g}, {b})" if fmt == "rgb" else f"rgba({r}, {g}, {b}, 1.0)"
        return "#" + hex6
    text = _MATUGEN_TAG.sub(sub, template)
    return re.sub(r"\{\{\s*image\s*\}\}", wallpaper, text)


# ---------------------------------------------------------- install/remove --
def _move_aside(target: Path, backup: Path, home: Path) -> None:
    rice_mod._move_aside(target, backup, home)                    # noqa: SLF001


def _place(src: Path, dest: Path, backup: Path, home: Path, owned: list[str]) -> None:
    if src.is_symlink() and src.resolve().exists():
        # The author links the folder from the repo (r4ppz19: ~/.config/rofi →
        # ~/Arch-dotfiles/rofi); the part takes the contents, not the link.
        src = src.resolve()
    if dest.exists() or dest.is_symlink():
        _move_aside(dest, backup, home)
    else:
        from . import backups as backups_mod
        backups_mod.record_created(backup, dest)
    rice_mod._copy(src, dest)                                     # noqa: SLF001
    owned.append(str(dest))


def _rewrite_entry(entry: Path, modules: set[str], known: set[str]) -> None:
    """Removes unselected components from the ShellRoot file.

    ``known``: all components the rice distributes across parts. Components
    that belong to no part (e.g. the shell's internal services) stay.
    """
    lines = entry.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines:
        match = re.match(r"^\s*(?:[A-Za-z_]\w*\.)?([A-Z]\w*)\s*\{\s*\}\s*$", line)
        if match and match.group(1) in known and match.group(1) not in modules:
            out.append(re.sub(r"^(\s*)", r"\1// hyprsetup mix: disabled — ", line, count=1))
            continue
        out.append(line)
    entry.write_text("\n".join(out) + "\n", encoding="utf-8")


def _wallpaper_lines(path: Path, wallpaper: str) -> None:
    """hyprlock: points ``background { path = ... }`` lines at the user's image."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return
    depth_bg, out = False, []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^background\s*\{", stripped):
            depth_bg = True
        elif stripped.startswith("}"):
            depth_bg = False
        if depth_bg and re.match(r"^path\s*=", stripped):
            indent = line[: len(line) - len(line.lstrip())]
            line = f"{indent}path = {wallpaper}"
        out.append(line)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def remove_parts(home: Path | None = None, stop: bool = True) -> list[str]:
    """Reverts installed parts: files are deleted, the backup comes back."""
    home_dir = Path(home) if home else Path.home()
    state = read_state(home)
    installed = state.get("installed") or {}
    restored: list[str] = []
    if stop and shutil.which("systemctl") and home is None:
        subprocess.run(["systemctl", "--user", "stop", SLICE],
                       capture_output=True, check=False, timeout=30)
    for path in map(Path, installed.get("owned", [])):
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists() or path.is_symlink():
            path.unlink()
        # Parent folders the install created go too if left empty
        # (~/.config/quickshell, ~/.cache/wal…).
        parent = path.parent
        while parent not in (home_dir, home_dir / ".config", home_dir / ".cache") \
                and home_dir in parent.parents:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
    backup = Path(installed.get("backup", "") or "/nonexistent")
    if backup.is_dir():
        for item in sorted(backup.rglob("*")):
            rel = item.relative_to(backup)
            if rel.parts[0].startswith("_") or not (item.is_file() or item.is_symlink()):
                continue
            target = home_dir / rel
            if target.exists() or target.is_symlink():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target, follow_symlinks=False)
            restored.append(str(target))
    for name in (HYPR_CONF, HYPR_LUA):
        (home_dir / ".config" / "hypr" / name).unlink(missing_ok=True)
    state["installed"] = {}
    write_state(state, home)
    return restored


def validate_parts(root: Path, chosen: dict[str, str]) -> None:
    """Can the selection be installed: does each part fit its slot, are its
    requirements selected. If not, ValueError — called BEFORE the state is written."""
    chosen = {slot: ref for slot, ref in chosen.items() if ref and "/" in ref}
    for slot, ref in chosen.items():
        try:
            _profile, part = find_part(root, ref)
        except (KeyError, OSError) as exc:
            raise ValueError(f"unknown part: {ref}") from exc
        if part.slot != slot:
            raise ValueError(f"{ref} is a '{part.slot}' part, not '{slot}'")
        missing = [r for r in part.requires if r not in chosen.values()]
        if missing:
            raise ValueError(f"{part_label(root, ref)} must be selected together with: "
                             + ", ".join(part_label(root, r) for r in missing))


#: Shell lines in terminal configs: kitty "shell zsh", foot
#: "shell=zsh", alacritty "program = …" under "[terminal.shell]"/"[shell]".
_SHELL_LINE = re.compile(r"^(\s*)(shell\s+\S.*|shell\s*=.*)$", re.M)
_TOML_SHELL = re.compile(r"^\[(?:terminal\.)?shell\]\s*$(.*?)(?=^\[|\Z)", re.M | re.S)


def _keep_user_shell(path: Path) -> None:
    """A terminal part must not change the user's shell.

    athena's kitty says "shell zsh": for a user on fish the terminal opened
    with zsh (and the Powerlevel10k wizard). The line is not deleted but
    commented out — the terminal opens the user's login shell.
    """
    if path.suffix not in ("", ".conf", ".ini", ".toml") or path.is_symlink():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    note = "# hyprsetup: disabled to keep your shell — "
    if path.suffix == ".toml":
        new = _TOML_SHELL.sub(lambda m: "\n".join(
            note + line if line.strip() else line
            for line in m.group(0).splitlines()) + "\n", text)
    else:
        new = _SHELL_LINE.sub(lambda m: f"{m.group(1)}{note}{m.group(2)}", text)
    if new != text:
        path.write_text(new, encoding="utf-8")



def _top_luminance(image: str) -> float | None:
    """Average brightness of the wallpaper's top strip (where the bar sits)."""
    tool = shutil.which("magick") or shutil.which("convert")
    if not tool:
        return None
    out = subprocess.run([tool, f"{image}[0]", "-gravity", "north", "-crop", "100%x6%+0+0",
                          "+repage", "-colorspace", "RGB", "-resize", "1x1!",
                          "-format", "%[fx:luminance]", "info:"],
                         capture_output=True, text=True, check=False, timeout=60)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return None


def _low_bar_contrast(wallpaper: str, palette: dict[str, str]) -> bool:
    """Is a translucent bar's text (FG) unreadable on top of the wallpaper?

    The author's bar was designed with colors generated from the wallpaper
    (wallust): on a translucent background the text always matches the
    wallpaper. In a mix the colors and the wallpaper may come from different
    rices — a light color scheme means dark text on a dark wallpaper
    (WCAG contrast < 3).
    """
    top = _top_luminance(wallpaper)
    if top is None or "FG" not in palette:
        return False
    fg = palette_mod.hex_luminance(palette["FG"])
    light, dark = max(fg, top), min(fg, top)
    return (light + 0.05) / (dark + 0.05) < 3.0


_RGBA_ALPHA = re.compile(r"(rgba\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*)(0?\.\d+|0)(\s*\))")


def _solid_backgrounds(path: Path) -> bool:
    """Raises nearly transparent backgrounds (rgba alpha < 0.5) to 0.85."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    new = _RGBA_ALPHA.sub(
        lambda m: f"{m.group(1)}0.85{m.group(3)}" if float(m.group(2)) < 0.5 else m.group(0),
        text)
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def _dmenu_commands(part: rice_mod.Part) -> dict[str, str]:
    """The launcher part's "pick from a list" (dmenu) command.

    Keybindings like clipboard history (SUPER+V) use CMD_DMENU, which was
    derived from the user's own launcher: in a mix with a rofi launcher the
    clipboard still opened with wofi. The program is recognized from its
    package or command; if the part provides CMD_DMENU itself, that wins.
    """
    from . import render as render_mod

    if part.slot != "launcher":
        return {}
    words = " ".join([*part.packages_repo, *part.packages_aur,
                      part.commands.get("CMD_LAUNCHER", "")])
    for name, command in render_mod._DMENU_CMDS.items():  # noqa: SLF001
        if re.search(rf"\b{name}\b", words):
            return {"CMD_DMENU": command,
                    "DMENU_PROMPT_FLAG": render_mod._DMENU_PROMPT_FLAGS.get(name, "")}  # noqa: SLF001
    return {}


def _missing_program(command: str, home: Path) -> str:
    """First program of ``command`` that is not installed ("" = all there).

    A path (``~/.config/eww/scripts/start.sh``) counts as installed if the
    file exists; ``_command_binaries`` alone only keeps the base name, which
    ``which`` cannot find."""
    for name in rice_mod._command_binaries(command):              # noqa: SLF001
        if shutil.which(name):
            continue
        paths = [rice_mod.expand(word, home) for word in command.split()
                 if "/" in word and os.path.basename(word) == name]
        if not any(p.is_file() for p in paths):
            return name
    return ""


def _missing_shell_package(part) -> str:
    """A bar/shell program the part depends on but is not installed.

    The start command may be the author's script (hyprclouds:
    ``~/.config/eww/scripts/start.sh``): the script exists, but the eww it
    runs does not, so checking the command alone stopped the user's waybar
    for a bar that never opened. Only programs of the autostart groups count
    — a missing jq or playerctl leaves the bar on screen.
    """
    shells = set().union(*rice_mod._AUTOSTART_GROUPS)            # noqa: SLF001
    for name in (*part.packages_repo, *part.packages_aur):
        if name in shells and not shutil.which(name):
            return name
    return ""


def install_parts(root: Path, chosen: dict[str, str], values: dict[str, str],
                  home: Path | None = None, log=print) -> list[str]:
    """Installs the selected app parts (previous ones are reverted first).

    ``chosen``: slot → ``profile/part``. ``values``: the CURRENT settings —
    parts are recolored to their palette, the lock screen shows this wallpaper.
    Returns: warnings.
    """
    from . import backups as backups_mod

    root = Path(root)
    home_dir = Path(home) if home else Path.home()
    validate_parts(root, chosen)
    remove_parts(home)
    chosen = {slot: ref for slot, ref in chosen.items() if ref}
    state = read_state(home)
    if not chosen:
        return []
    parts_data = load_parts(root)
    palette = current_palette(values)
    wallpaper_raw = values.get("WALLPAPER_PATH", "") or ""
    wallpaper = str(home_dir / wallpaper_raw[2:]) if wallpaper_raw.startswith("~/") \
        else wallpaper_raw
    backup = backups_mod.new_dir("live", home)
    owned: list[str] = []
    warnings: list[str] = []
    provides: list[str] = []
    #: start command → roles its part takes over (launch_parts stops the
    #: role's other programs only for these).
    exec_roles: dict[str, list[str]] = {}
    commands: dict[str, str] = {}
    starts: list[str] = []
    hypr_lines: list[str] = []

    by_profile: dict[str, list[tuple[str, rice_mod.Part]]] = {}
    for slot, ref in chosen.items():
        profile, part = find_part(root, ref)
        by_profile.setdefault(profile, []).append((slot, part))
    claimed = {rice_mod.expand(p, home_dir) for items in by_profile.values()
               for _s, part in items for p in part.paths}

    for profile, items in by_profile.items():
        recolor = Recolor(author_palette(parts_data, profile, root), palette)
        manifest = rice_mod.load(root, profile)
        with tempfile.TemporaryDirectory(prefix="hyprsetup-mix-") as tmp:
            staged = stage_home(root, profile, Path(tmp))
            placed: list[tuple[Path, rice_mod.Part]] = []
            for _slot, part in items:
                wanted = [(p, True) for p in part.paths] + [(p, False) for p in part.needs]
                for text, own in wanted:
                    dest = rice_mod.expand(text, home_dir)
                    src = rice_mod.expand(text, staged)
                    if not (src.exists() or src.is_symlink()):
                        warnings.append(f"{profile}: {text} is missing from the rice")
                        continue
                    if rice_mod.is_owned(dest, [Path(o) for o in owned]):
                        continue                  # already came with another part
                    if not own and any(dest == c or c in dest.parents or dest in c.parents
                                       for c in claimed):
                        warnings.append(f"{part.title or part.slot}: {text} belongs to "
                                        "another part; that part's copy will be used")
                        continue
                    _place(src, dest, backup, home_dir, owned)
                    placed.append((dest, part))
            # Shell split: components of parts sharing the same entry file.
            known: dict[str, set[str]] = {}
            for part in manifest.parts:
                if part.entry:
                    known.setdefault(part.entry, set()).update(part.modules)
            entries: dict[str, set[str]] = {}
            for _slot, part in items:
                if part.entry:
                    entries.setdefault(part.entry, set()).update(part.modules)
            for entry_text, modules in entries.items():
                entry = rice_mod.expand(entry_text, home_dir)
                if entry.is_file():
                    _rewrite_entry(entry, modules, known.get(entry_text, set()))
            for dest, part in placed:
                if part.recolor:
                    files = [dest] if dest.is_file() else [
                        f for f in dest.rglob("*") if f.is_file()]
                    for f in files:
                        recolor.file(f)
                if part.wallpaper_lines and wallpaper:
                    for f in ([dest] if dest.is_file() else dest.rglob("*.conf")):
                        _wallpaper_lines(f, wallpaper)
                if part.slot == "terminal":
                    for f in ([dest] if dest.is_file() else dest.rglob("*")):
                        if f.is_file():
                            _keep_user_shell(f)
                if part.slot == "bar" and wallpaper and _low_bar_contrast(wallpaper, palette):
                    for f in ([dest] if dest.is_file() else dest.rglob("*")):
                        if f.suffix in (".css", ".scss") and _solid_backgrounds(f):
                            note = (f"{part.title or part.slot}: text was unreadable on "
                                    "the top edge of the wallpaper; the bar's translucent "
                                    "backgrounds were made more solid")
                            if note not in warnings:
                                warnings.append(note)
            # "matugen:~/template=~/target": the template comes from the author's
            # repo (staged), the result goes to the user's home.
            for _slot, part in items:
                for spec in part.palette_files:
                    kind, _, rest = spec.partition(":")
                    if kind != "matugen":
                        continue
                    template_text, _, target_text = rest.partition("=")
                    template = rice_mod.expand(template_text, staged)
                    if not template.is_file():
                        warnings.append(f"{profile}: {template_text} is missing from the rice")
                        continue
                    target = rice_mod.expand(target_text, home_dir)
                    if target.exists() or target.is_symlink():
                        if not rice_mod.is_owned(target, [Path(o) for o in owned]):
                            _move_aside(target, backup, home_dir)
                    else:
                        backups_mod.record_created(backup, target)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(render_matugen(template.read_text(encoding="utf-8"),
                                                     palette, wallpaper), encoding="utf-8")
                    if str(target) not in owned:
                        owned.append(str(target))
        for _slot, part in items:
            for spec in part.palette_files:
                kind, _, target_text = spec.partition(":")
                if kind == "matugen":
                    continue                     # handled above, with its template
                target = rice_mod.expand(target_text, home_dir)
                if target.exists() or target.is_symlink():
                    _move_aside(target, backup, home_dir)
                else:
                    backups_mod.record_created(backup, target)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(palette_file(kind, palette, wallpaper), encoding="utf-8")
                owned.append(str(target))
            missing = ((_missing_program(part.start, home_dir)
                        or _missing_shell_package(part)) if part.start else "")
            if missing:
                # The part cannot do its job: it does not take over the role
                # or the autostart. Otherwise the user's own bar was stopped
                # and nothing replaced it (athena's eww bar without eww).
                warnings.append(f"{part.title or part.slot}: '{missing}' is not installed "
                                f"(package: {' '.join(part.packages_repo + part.packages_aur) or missing})"
                                " — not started, your own one stays")
            else:
                provides += [c for c in part.provides if c not in provides]
            for key, value in {**_dmenu_commands(part), **part.commands}.items():
                # A key command whose program is not installed is NOT taken
                # over: r4ppz19's lock bound SUPER+L to swaylock without
                # swaylock installed, so the lock key silently did nothing.
                absent = (_missing_program(value, home_dir)
                          if key in ("CMD_LAUNCHER", "CMD_TERMINAL", "LOCK_CMD") else "")
                if absent:
                    warnings.append(f"{part.title or part.slot}: '{absent}' is not installed "
                                    f"(package: {' '.join(part.packages_repo + part.packages_aur) or absent})"
                                    f" — your own {_COMMAND_SLOT.get(key, key)} command stays")
                    continue
                # If two parts want the same command, the slot owning that job
                # wins (the launcher slot's command overrides the bar's).
                if key not in commands or _COMMAND_SLOT.get(key) == _slot:
                    commands[key] = value
            if part.start and not missing:
                if part.start not in starts:
                    starts.append(part.start)
                roles = exec_roles.setdefault(part.start, [])
                roles += [c for c in part.provides if c not in roles]
            hypr_lines += [line for line in part.hypr if line not in hypr_lines]
            if part.note:
                warnings.append(f"{part.title or part.slot}: {part.note}")

    hypr = home_dir / ".config" / "hypr"
    hypr.mkdir(parents=True, exist_ok=True)
    header = ["# hyprsetup mix — the parts' startup commands and extras.",
              "# Generated by: python3 -m hyprsetup mix … (do not edit by hand)", ""]
    (hypr / HYPR_CONF).write_text("\n".join(
        header + [f"exec-once = {c}" for c in starts] + [""] + hypr_lines) + "\n",
        encoding="utf-8")
    lua = ["-- hyprsetup mix — the parts' startup commands (generated).",
           'hl.on("hyprland.start", function()']
    lua += [f"    hl.exec_cmd({json.dumps(c)})" for c in starts]
    lua += ["end)"]
    (hypr / HYPR_LUA).write_text("\n".join(lua) + "\n", encoding="utf-8")

    state = read_state(home)
    state["installed"] = {"parts": chosen, "owned": owned, "backup": str(backup),
                          "provides": provides, "commands": commands,
                          "exec": starts, "exec_roles": exec_roles, "warnings": warnings}
    write_state(state, home)
    # Manual settings saved for this bar on the bar page (ricebar) are
    # written again because the files were reinstalled.
    from . import ricebar as ricebar_mod
    try:
        ricebar_mod.reapply(root, home)
    except (OSError, ValueError, KeyError) as exc:
        warnings.append(f"could not rewrite your bar settings: {exc}")
    return warnings


def launch_parts(home: Path | None = None) -> list[str]:
    """Starts the parts' programs now (exec-once only runs at login).
    Running programs doing the same job (e.g. the user's mako) are
    stopped."""
    if not os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") or home is not None:
        return []
    installed = read_state(home).get("installed") or {}
    started = []
    # If a part takes over a role WITHOUT using one of that role's known
    # programs (athena's eww bar), the user's program is stopped separately:
    # stopping peers only worked within the same family (waybar ↔ hyprpanel),
    # so the user's waybar stayed up next to the eww bar.
    own = {name for command in installed.get("exec", [])
           for name in rice_mod._command_binaries(command)}          # noqa: SLF001
    roles = dict(zip(("notify", "wallpaper", "bar"), rice_mod._AUTOSTART_GROUPS, strict=False))  # noqa: SLF001
    for role in installed.get("provides", []):
        group = roles.get(role, set())
        if group and not group & own:
            for name in group:
                subprocess.run(["pkill", "-x", name], capture_output=True, check=False)
    group_role = {frozenset(g): r for r, g in roles.items()}
    # Mixes installed before exec_roles existed: every command owns its group.
    exec_roles = installed.get("exec_roles")
    for command in installed.get("exec", []):
        binaries = rice_mod._command_binaries(command)            # noqa: SLF001
        owned_roles = None if exec_roles is None else set(exec_roles.get(command, []))
        restart_only = False
        for name in binaries:
            group = next((g for g in rice_mod._AUTOSTART_GROUPS   # noqa: SLF001
                          if name in g), None)
            if group is None:
                peers = {name}
            elif owned_roles is None or group_role.get(frozenset(group)) in owned_roles:
                peers = group
            else:
                # An extra program that is not the role's (eww desktop
                # cards, a quickshell widget): stopping its group killed the
                # user's waybar. Only an earlier copy of this command goes.
                restart_only = True
                continue
            for peer in peers:
                subprocess.run(["pkill", "-x", peer], capture_output=True, check=False)
        if restart_only:
            subprocess.run(["pkill", "-f", "-x", f"(bash -lc )?{re.escape(command)}"],
                           capture_output=True, check=False)
        argv = (["systemd-run", "--user", "--scope", "--quiet", f"--slice={SLICE}",
                 "--", "bash", "-lc", command] if shutil.which("systemd-run")
                else ["bash", "-lc", command])
        subprocess.Popen(argv, cwd=Path.home(), stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        started.append(command)
    return started


def render_vars(home: Path | None = None) -> dict[str, str]:
    """Mix variables passed to templates: the parts' keybinding commands
    (MIX_OVERRIDE_*) and whether mix.conf is loaded."""
    home_dir = Path(home) if home else Path.home()
    installed = read_state(home).get("installed") or {}
    out = {f"MIX_OVERRIDE_{k}": v for k, v in (installed.get("commands") or {}).items()}
    hypr = home_dir / ".config" / "hypr"
    out["MIX_HYPR"] = "1" if (hypr / HYPR_CONF).is_file() else ""
    out["MIX_HYPR_LUA"] = "1" if (hypr / HYPR_LUA).is_file() else ""
    return out


# ------------------------------------------------------------------ apply -------
def apply(root: Path, slots: dict[str, str], log=print) -> dict[str, str]:
    """Writes the selection to settings.conf and applies it (CLI; the UI updates
    its own state with ``plan``).

    If a rice is active it is uninstalled first: the mix's base is this
    project's configuration, and while the author's files stand in its place
    the settings cannot be written anywhere.
    """
    from .catalog import Catalog
    from .gui.state import SetupState, config_path

    root = Path(root).resolve()
    wanted = dict(read_state().get("parts", {}))
    wanted.update({k: v for k, v in slots.items() if k in APP_SLOT_IDS})
    validate_parts(root, wanted)
    if rice_mod.read_state():
        # Fetch everything that can fail (wallpaper download, missing package
        # file) BEFORE removing the rice: otherwise a failed mix leaves the
        # user with neither the rice nor the mix. plan() writes no state.
        plan(root, {k: v for k, v in slots.items() if k in SLOT_IDS}, {})
        restored = rice_mod.uninstall()
        log(f"Rice uninstalled ({len(restored)} files restored from backup)")
    catalog = Catalog.load(root / "config" / "components.json")
    setup = SetupState(catalog)
    path = config_path()
    if path.is_file():
        setup.load_conf(path)
    changes, state = plan(root, dict(slots), with_daemon(setup.values, setup.is_selected))
    changed = {k: v for k, v in changes.items() if setup.get(k) != v}
    for key, value in changed.items():
        setup.set(key, value)
    catalog_parts = load_parts(root)
    parts = dict(state.get("parts", {}))
    parts.update({k: v for k, v in slots.items() if k in APP_SLOT_IDS})
    state["parts"] = {k: v for k, v in parts.items()
                      if v and not is_own_ref(catalog_parts, k, v)}
    for var in ("TERMINAL", "LAUNCHER", "NOTIFIER", "WIDGET_ENGINE", "BAR", "WALLPAPER_DAEMON"):
        want = changes.get(var, "")
        if want and setup.catalog.component(want) and shutil.which(want.split("-")[0]):
            setup.toggle(want, True)
    validate_parts(root, state["parts"])
    setup.preset, setup.variant = profile_marker(state, setup.preset, setup.variant)
    setup.save_conf(path)
    write_state(state)
    # Parts are installed AFTER the settings are written: recolored to the new color scheme.
    if state["parts"] or (state.get("installed") or {}).get("owned"):
        for warning in install_parts(root, state["parts"], setup.values, log=log):
            log(f"WARNING: {warning}")
    return changed


def profile_marker(state: dict, preset: str, variant: str) -> tuple[str, str]:
    """While a mix is active the selected profile name is cleared; it comes back
    when the mix is turned off (``state`` is updated).

    If the profile name stayed, changing the bar/terminal preset would resolve
    the profile again (SetupState.apply_profile_preset) and override the mix.
    """
    if state["slots"] or state.get("parts"):
        if "profile" not in state:
            state["profile"] = [preset, variant]
        return "", ""
    previous = state.pop("profile", None)
    return (previous[0], previous[1]) if previous else (preset, variant)
