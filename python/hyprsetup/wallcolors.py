"""Wallpaper colors: writes the image's colors into every program's config file.

The idea of **ricemood** (fhadiel/ricemood, 2019) from r/unixporn: the user writes
tags instead of colors in a copy of their own config file,

    color0 ^r@Vibrant>lighten(0.2)^

the tool extracts colors from the wallpaper, fills in the tags and writes the file
to its real location. This project's ``THEME="auto"`` only colored its own templates
(bar, terminal, GTK…); this module carries the same colors to EVERY file the user
picks and reapplies them whenever the wallpaper changes (including rotation,
``wallpaper.sh`` → ``hyprsetup wallcolors follow``).

Color names (case-insensitive):

* ricemood/node-vibrant swatches: ``Vibrant`` (``V``), ``LightVibrant``
  (``LV``), ``DarkVibrant`` (``DV``), ``Muted`` (``M``), ``LightMuted``
  (``LM``), ``DarkMuted`` (``DM``)
* this project's roles: ``BG BG_DARK SURFACE FG SUBTEXT ACCENT ACCENT2 RED
  GREEN YELLOW CYAN`` (palette.extract — readability enforced)
* terminal: ``color0``…``color15``, ``background``, ``foreground``, ``cursor``

Two template syntaxes:

* **ricemood** (default): ``^r@Name>filter(value)>filter#format(separator)^`` —
  ricemood's filters and formats (table: FILTERS, _format).
* **pywal**: ``{color0}``, ``{background.strip}``, ``{color4.rgb}``;
  ``{{`` / ``}}`` are literal braces. Ready-made templates written for pywal can
  be used as-is.
"""

from __future__ import annotations

import colorsys
import json
import math
import os
import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import palette as palette_mod
from . import themes

# ------------------------------------------------------------ color helpers -
RGB = tuple[float, float, float]            # 0–255, float (filters work with fractions)


@dataclass
class Color:
    r: float
    g: float
    b: float
    a: float = 1.0

    @classmethod
    def parse(cls, text: str) -> "Color":
        value = text.strip().lstrip("#")
        if len(value) == 3:
            value = "".join(c * 2 for c in value)
        if len(value) == 8:                        # RRGGBBAA
            return cls(*(int(value[i:i + 2], 16) for i in (0, 2, 4)),
                       a=int(value[6:8], 16) / 255)
        return cls(*(int(value[i:i + 2], 16) for i in (0, 2, 4)))

    def clamp(self) -> "Color":
        return Color(*(min(255.0, max(0.0, c)) for c in (self.r, self.g, self.b)),
                     a=min(1.0, max(0.0, self.a)))

    def hex(self) -> str:
        c = self.clamp()
        return "".join(f"{round(v):02X}" for v in (c.r, c.g, c.b))

    def hls(self) -> tuple[float, float, float]:
        return colorsys.rgb_to_hls(self.r / 255, self.g / 255, self.b / 255)

    @classmethod
    def from_hls(cls, h: float, light: float, s: float, a: float = 1.0) -> "Color":
        r, g, b = colorsys.hls_to_rgb(h % 1.0, min(1, max(0, light)), min(1, max(0, s)))
        return cls(r * 255, g * 255, b * 255, a)

    def luminance(self) -> float:
        def channel(v: float) -> float:
            v /= 255
            return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
        return 0.2126 * channel(self.r) + 0.7152 * channel(self.g) + 0.0722 * channel(self.b)


def _contrast(a: Color, b: Color) -> float:
    la, lb = sorted((a.luminance(), b.luminance()), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _text_color(color: Color, minimum: float) -> Color:
    """node-vibrant getTitleTextColor/getBodyTextColor: white or black."""
    white = Color(255, 255, 255)
    return white if _contrast(color, white) >= minimum else Color(0, 0, 0)


def _hsl_edit(color: Color, fn) -> Color:
    h, light, s = color.hls()
    h, light, s = fn(h, light, s)
    return Color.from_hls(h, light, s, color.a)


def _num(arg: str, default: float) -> float:
    try:
        return float(arg) if arg.strip() else default
    except ValueError:
        return default


#: ricemood filters (with Qix/color semantics): short name → (full name, function).
def _grayscale(c: Color, _a: str) -> Color:
    v = c.r * 0.3 + c.g * 0.59 + c.b * 0.11
    return Color(v, v, v, c.a)


def _whiten(c: Color, a: str) -> Color:
    # HWB whiteness grows by the ratio: the color is mixed toward white.
    r = _num(a, 0.5)
    w = min(c.r, c.g, c.b) / 255
    target = min(1.0, w + w * r) if w else r * 0.5
    return Color(*(v + (255 - v) * (target - w) / max(1e-6, 1 - w) for v in (c.r, c.g, c.b)), a=c.a)


def _blacken(c: Color, a: str) -> Color:
    r = _num(a, 0.5)
    k = 1 - max(c.r, c.g, c.b) / 255
    target = min(1.0, k + k * r) if k else r * 0.5
    scale = (1 - target) / max(1e-6, 1 - k)
    return Color(c.r * scale, c.g * scale, c.b * scale, c.a)


FILTERS = {
    "ge": ("grayscale", _grayscale),
    "ne": ("negate", lambda c, _a: Color(255 - c.r, 255 - c.g, 255 - c.b, c.a)),
    "ttc": ("titletextcolor", lambda c, _a: _text_color(c, 3.0)),
    "btc": ("bodytextcolor", lambda c, _a: _text_color(c, 4.5)),
    "da": ("darken", lambda c, a: _hsl_edit(c, lambda h, lt, s: (h, lt - lt * _num(a, 0.5), s))),
    "li": ("lighten", lambda c, a: _hsl_edit(c, lambda h, lt, s: (h, lt + lt * _num(a, 0.5), s))),
    "de": ("desaturate", lambda c, a: _hsl_edit(c, lambda h, lt, s: (h, lt, s - s * _num(a, 0.5)))),
    "sa": ("saturate", lambda c, a: _hsl_edit(c, lambda h, lt, s: (h, lt, s + s * _num(a, 0.5)))),
    "wh": ("whiten", _whiten),
    "bl": ("blacken", _blacken),
    "fa": ("fade", lambda c, a: Color(c.r, c.g, c.b, c.a - c.a * _num(a, 0.5))),
    "op": ("opaquer", lambda c, a: Color(c.r, c.g, c.b, c.a + c.a * _num(a, 0.5))),
    "ro": ("rotate", lambda c, a: _hsl_edit(c, lambda h, lt, s: (h + _num(a, 90) / 360, lt, s))),
    "r": ("red", lambda c, a: Color(_num(a, 255), c.g, c.b, c.a)),
    "g": ("green", lambda c, a: Color(c.r, _num(a, 255), c.b, c.a)),
    "b": ("blue", lambda c, a: Color(c.r, c.g, _num(a, 255), c.a)),
    "h": ("hue", lambda c, a: _hsl_edit(c, lambda _h, lt, s: (_num(a, 0) / 360, lt, s))),
    "s": ("saturationl", lambda c, a: _hsl_edit(c, lambda h, lt, _s: (h, lt, _num(a, 100) / 100))),
    "l": ("lightness", lambda c, a: _hsl_edit(c, lambda h, _l, s: (h, _num(a, 50) / 100, s))),
}
_FILTER_BY_NAME = {name: fn for alias, (name, fn) in FILTERS.items()} | {
    alias: fn for alias, (_name, fn) in FILTERS.items()}


def _format(color: Color, kind: str, arg: str) -> str:
    c = color.clamp()
    sep = arg if arg else ","
    kind = kind.lower()
    if kind == "":
        return "#" + c.hex()
    if kind == "hex":
        return c.hex()
    if kind == "rgb":
        return sep.join(str(round(v)) for v in (c.r, c.g, c.b))
    if kind == "rgba":
        return sep.join([*(str(round(v)) for v in (c.r, c.g, c.b)), f"{c.a:.2f}"])
    h, light, s = c.hls()
    if kind == "hsl":
        return sep.join(str(round(v)) for v in (h * 360, s * 100, light * 100))
    single = {"r": c.r, "g": c.g, "b": c.b, "h": h * 360, "s": s * 100, "l": light * 100,
              "a": c.a * 255}
    if kind in single:
        return str(round(single[kind]))
    raise ValueError(f"unknown format: #{kind}")


# ---------------------------------------------------- node-vibrant swatches -
#: Name → (lightness min, target, max, saturation min, target, max) — node-vibrant
#: DefaultGenerator values (ricemood uses these).
_VIBRANT_TARGETS = {
    "Vibrant":      (0.30, 0.50, 0.70, 0.35, 1.00, 1.00),
    "LightVibrant": (0.55, 0.74, 1.00, 0.35, 1.00, 1.00),
    "DarkVibrant":  (0.00, 0.26, 0.45, 0.35, 1.00, 1.00),
    "Muted":        (0.30, 0.50, 0.70, 0.00, 0.30, 0.40),
    "LightMuted":   (0.55, 0.74, 1.00, 0.00, 0.30, 0.40),
    "DarkMuted":    (0.00, 0.26, 0.45, 0.00, 0.30, 0.40),
}
_WEIGHTS = (3.0, 6.5, 0.5)          # saturation, lightness, population
ALIASES = {"v": "Vibrant", "lv": "LightVibrant", "dv": "DarkVibrant",
           "m": "Muted", "lm": "LightMuted", "dm": "DarkMuted"}


def _dominant(image: Path) -> list[tuple[tuple[int, int, int], int]]:
    """Quantized colors of the image (rgb, pixel count)."""
    colors = palette_mod._from_magick(image)                      # noqa: SLF001
    if not colors:
        pixels = palette_mod._png_pixels(image)                   # noqa: SLF001
        colors = palette_mod._quantize(pixels) if pixels else []  # noqa: SLF001
    # node-vibrant's default filter: pixels very close to white are not counted.
    return [(rgb, n) for rgb, n in colors if not all(v > 250 for v in rgb)]


def vibrant(image: Path) -> dict[str, str]:
    """ricemood's six swatches (hex, without #). Swatches that are not found are
    derived from the ones found, as node-vibrant does."""
    colors = _dominant(image)
    if not colors:
        return {}
    top = max(n for _rgb, n in colors) or 1
    chosen: dict[str, tuple[float, float, float]] = {}
    used: set[tuple[int, int, int]] = set()
    for name, (lmin, ltarget, lmax, smin, starget, smax) in _VIBRANT_TARGETS.items():
        best, best_score = None, -1.0
        for rgb, count in colors:
            h, light, s = colorsys.rgb_to_hls(*(v / 255 for v in rgb))
            if rgb in used or not (lmin <= light <= lmax and smin <= s <= smax):
                continue
            ws, wl, wp = _WEIGHTS
            score = (ws * (1 - abs(s - starget)) + wl * (1 - abs(light - ltarget))
                     + wp * (count / top)) / (ws + wl + wp)
            if score > best_score:
                best, best_score = rgb, score
        if best is not None:
            used.add(best)
            chosen[name] = colorsys.rgb_to_hls(*(v / 255 for v in best))

    def derive(name: str, sources: tuple[str, ...], light: float) -> None:
        """Builds a missing swatch from the hue of a found one; saturation is pulled
        toward the target class (so a muted one derived from a vibrant one is muted)."""
        if name in chosen:
            return
        muted = "Muted" in name
        for source in sources:
            if source in chosen:
                h, _l, s = chosen[source]
                s = min(s, 0.30) if muted else max(s, 0.55)
                chosen[name] = (h, light, s)
                return

    derive("Vibrant", ("DarkVibrant", "LightVibrant", "Muted", "DarkMuted", "LightMuted"), 0.50)
    derive("DarkVibrant", ("Vibrant", "LightVibrant"), 0.26)
    derive("LightVibrant", ("Vibrant", "DarkVibrant"), 0.74)
    derive("Muted", ("DarkMuted", "LightMuted", "Vibrant"), 0.50)
    derive("DarkMuted", ("Muted", "LightMuted", "DarkVibrant"), 0.26)
    derive("LightMuted", ("Muted", "DarkMuted", "LightVibrant"), 0.74)
    return {name: Color.from_hls(*chosen[name]).hex()
            for name in _VIBRANT_TARGETS if name in chosen}


# --------------------------------------------------------------- color set --
#: Terminal colors — same mapping as this project's kitty/foot templates.
ANSI = ("SURFACE", "RED", "GREEN", "YELLOW", "ACCENT", "ACCENT2", "CYAN", "FG",
        "SUBTEXT", "RED", "GREEN", "YELLOW", "ACCENT", "ACCENT2", "CYAN", "FG")


@dataclass
class Colors:
    image: str
    vibrant: dict[str, str] = field(default_factory=dict)
    roles: dict[str, str] = field(default_factory=dict)

    def names(self) -> dict[str, str]:
        """All names templates can use → hex (without #)."""
        out: dict[str, str] = {}
        out.update(self.vibrant)
        out.update(self.roles)
        for index, role in enumerate(ANSI):
            if role in self.roles:
                out[f"color{index}"] = self.roles[role]
        if self.roles:
            out["background"] = self.roles["BG"]
            out["foreground"] = self.roles["FG"]
            out["cursor"] = self.roles["ACCENT"]
        return out

    def lookup(self, name: str) -> Color:
        table = {k.lower(): v for k, v in self.names().items()}
        key = ALIASES.get(name.lower(), name).lower()
        if key not in table:
            raise KeyError(f"unknown color: {name}")
        return Color.parse(table[key])

    def to_json(self) -> dict:
        return {"image": self.image, "vibrant": self.vibrant, "roles": self.roles}


def extract(image: str | Path, dark: bool = True, backend: str = "auto",
            values: dict[str, str] | None = None) -> Colors:
    """Colors of the image. If ``values`` is given, the manual tone from the settings
    (PALETTE_HUE/SATURATION/LIGHTNESS) is applied too — so the desktop and the
    templated programs get the same tone. With THEME="auto", CUSTOM_COLORS are also
    written over these roles (under another theme those colors belong to that theme)."""
    path = Path(image).expanduser()
    roles = palette_mod.extract(path, dark=dark, backend=backend) or {}
    roles = {**themes.THEMES[themes.DEFAULT], **roles}
    swatches = vibrant(path) if path.is_file() else {}
    if values:
        tone = palette_mod.tone_from(values)
        roles = palette_mod.adjust(roles, *tone)
        swatches = palette_mod.adjust(swatches, *tone, hue_keys=None)
        if (values.get("THEME") or "").strip().lower() == "auto":
            roles.update(themes.parse_overrides(values.get("CUSTOM_COLORS", "")))
    roles = {k: v.lstrip("#").upper() for k, v in roles.items() if k in themes.KEYS}
    swatches = {k: v.lstrip("#").upper() for k, v in swatches.items()}
    return Colors(image=str(path), vibrant=swatches, roles=roles)


# ---------------------------------------------------------------- template --
_RICEMOOD_TAG = re.compile(r"\^r(.*?)\^", re.S)
_STEP = re.compile(r"(\w+)(?:\(([^)]*)\))?")


def _ricemood_expr(expr: str, colors: Colors) -> str:
    expr = expr.strip()
    if not expr.startswith("@"):
        raise ValueError(f"tag must start with @: ^r{expr}^")
    body, _, fmt = expr[1:].partition("#")
    parts = body.split(">")
    color = colors.lookup(parts[0].strip())
    for step in parts[1:]:
        match = _STEP.fullmatch(step.strip())
        if not match or match.group(1).lower() not in _FILTER_BY_NAME:
            raise ValueError(f"unknown filter: {step}")
        color = _FILTER_BY_NAME[match.group(1).lower()](color, match.group(2) or "")
    fmt_match = _STEP.fullmatch(fmt.strip()) if fmt.strip() else None
    return _format(color, fmt_match.group(1) if fmt_match else "",
                   (fmt_match.group(2) or "") if fmt_match else "")


_PYWAL_TAG = re.compile(r"\{\{|\}\}|\{([A-Za-z_][\w]*)(?:\.(\w+))?\}")


def _pywal_value(name: str, mod: str, colors: Colors) -> str:
    if name == "wallpaper":
        return colors.image
    color = colors.lookup(name).clamp()
    mod = (mod or "").lower()
    if mod == "":
        return "#" + color.hex().lower()
    if mod == "strip":
        return color.hex().lower()
    if mod == "rgb":
        return ",".join(str(round(v)) for v in (color.r, color.g, color.b))
    if mod == "rgba":
        return ",".join([*(str(round(v)) for v in (color.r, color.g, color.b)), "1.0"])
    if mod == "xrgba":
        return "/".join(color.hex().lower()[i:i + 2] for i in (0, 2, 4)) + "/ff"
    if mod in ("red", "green", "blue"):
        return str(round(getattr(color, mod[0])))
    raise ValueError(f"unknown pywal format: .{mod}")


def render(text: str, colors: Colors, syntax: str = "ricemood") -> str:
    if syntax == "pywal":
        def sub(match: re.Match) -> str:
            token = match.group(0)
            if token in ("{{", "}}"):
                return token[0]
            return _pywal_value(match.group(1), match.group(2) or "", colors)
        return _PYWAL_TAG.sub(sub, text)
    return _RICEMOOD_TAG.sub(lambda m: _ricemood_expr(m.group(1), colors), text)


# ---------------------------------------------------------- auto-templating --
_HEX_IN_TEXT = re.compile(r"(?<![\w&])#([0-9a-fA-F]{6})(?![0-9a-fA-F])")



def templatize(text: str, reference: dict[str, str]) -> tuple[str, dict[str, str]]:
    """Replaces the #rrggbb colors in the file with the tag of the nearest role.

    ``reference``: role → hex (the palette the file is currently colored with;
    usually this project's active palette). Returns: (template text, {old color: role}).
    """
    roles = {k: palette_mod.hex_lab(v) for k, v in reference.items() if k in themes.KEYS}
    mapping: dict[str, str] = {}

    def nearest(hex_value: str) -> str:
        lab = palette_mod.hex_lab(hex_value)
        return min(roles, key=lambda k: math.dist(lab, roles[k]))

    def sub(match: re.Match) -> str:
        value = match.group(1).lower()
        role = mapping.setdefault(value, nearest(value))
        return f"^r@{role}^"
    return _HEX_IN_TEXT.sub(sub, text), mapping


# ------------------------------------------------------------------- config -
@dataclass
class Target:
    """The file a template writes."""
    path: str                    # ~/... target
    template: str                # template text
    syntax: str = "ricemood"


@dataclass
class Entry:
    """A set of templates to apply (from the bundled library or the user's)."""
    id: str
    title: str
    desc: str = ""
    targets: list[Target] = field(default_factory=list)
    reload: str = ""
    #: (file, line): appended if missing from the file (e.g. "include …" in zathurarc).
    ensure: list[tuple[str, str]] = field(default_factory=list)
    builtin: bool = True
    enabled: bool = False


def config_dir() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "hyprsetup" / "wallcolors"


def config_path() -> Path:
    return config_dir() / "config.json"


def load_config() -> dict:
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data.setdefault("follow", True)
    data.setdefault("enabled", [])
    data.setdefault("templates", [])
    return data


def save_config(data: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def library(root: Path) -> list[Entry]:
    """Bundled templates shipped with the project: presets/wallcolors/*.toml."""
    out = []
    for path in sorted((Path(root) / "presets" / "wallcolors").glob("*.toml")):
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        out.append(Entry(
            id=path.stem, title=data.get("title", path.stem), desc=data.get("desc", ""),
            targets=[Target(t["path"], t["template"], t.get("syntax", "ricemood"))
                     for t in data.get("file", [])],
            reload=data.get("reload", ""),
            ensure=[(e["file"], e["line"]) for e in data.get("ensure", [])]))
    return out


def entries(root: Path, config: dict | None = None) -> list[Entry]:
    config = config if config is not None else load_config()
    out = library(root)
    for entry in out:
        entry.enabled = entry.id in config["enabled"]
    for raw in config["templates"]:
        template = config_dir() / "templates" / raw["template"]
        try:
            text = template.read_text(encoding="utf-8")
        except OSError:
            continue
        out.append(Entry(id=raw["id"], title=raw.get("title", raw["id"]),
                         desc=str(template),
                         targets=[Target(raw["target"], text, raw.get("syntax", "ricemood"))],
                         reload=raw.get("reload", ""), builtin=False,
                         enabled=raw.get("enabled", True)))
    return out


def add_user_template(source: Path, reference: dict[str, str], title: str = "",
                      reload: str = "") -> tuple[dict, dict[str, str]]:
    """Builds a template from one of the user's config files and saves it.

    The colors in the file are turned into the nearest role tag (templatize); the user
    can refine the template by hand afterwards. Returns: (config record, mapping).
    """
    text = source.read_text(encoding="utf-8", errors="replace")
    template, mapping = templatize(text, reference)
    config = load_config()
    # "sablon" ("template"): Turkish-looking default id, kept as-is.
    base = re.sub(r"[^A-Za-z0-9]+", "-", source.name).strip("-").lower() or "sablon"
    ident, n = base, 2
    while any(t["id"] == ident for t in config["templates"]):
        ident, n = f"{base}-{n}", n + 1
    folder = config_dir() / "templates"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ident).write_text(template, encoding="utf-8")
    home = str(Path.home())
    target = str(source)
    if target.startswith(home + "/"):
        target = "~" + target[len(home):]
    raw = {"id": ident, "title": title or source.name, "template": ident,
           "target": target, "syntax": "ricemood", "reload": reload, "enabled": True}
    config["templates"].append(raw)
    save_config(config)
    return raw, mapping


# ------------------------------------------------------------------- apply --
def current_wallpaper(values: dict[str, str] | None = None) -> Path | None:
    """The wallpaper on screen: wallpaper.sh's state, otherwise WALLPAPER_PATH."""
    state = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    try:
        path = Path((state / "hyprsetup" / "wallpaper").read_text().strip())
        if path.is_file():
            return path
    except OSError:
        pass
    raw = (values or {}).get("WALLPAPER_PATH", "") or "~/Pictures/wallpapers/wallpaper.png"
    path = Path(os.path.expanduser(raw))
    return path if path.is_file() else None


def cache_path() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "hyprsetup" / "wallcolors.json"


@dataclass
class Result:
    written: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def apply(root: Path, colors: Colors, config: dict | None = None,
          run_reload: bool = True) -> Result:
    """Fills the enabled templates, writes them to their targets and runs the reload
    commands. When a target file is written for the first time, a copy is kept as
    ``.hyprsetup-orig`` (so the user's hand-written file is not lost)."""
    result = Result()
    reloads: list[str] = []
    for entry in entries(root, config):
        if not entry.enabled:
            continue
        try:
            rendered = [(t, render(t.template, colors, t.syntax)) for t in entry.targets]
        except (ValueError, KeyError) as exc:
            result.errors.append(f"{entry.title}: {exc}")
            continue
        for target, text in rendered:
            path = Path(os.path.expanduser(target.path))
            path.parent.mkdir(parents=True, exist_ok=True)
            original = path.with_name(path.name + ".hyprsetup-orig")
            if path.is_file() and not original.exists() and not entry.builtin:
                shutil.copy2(path, original)
            tmp = path.with_name(path.name + ".hyprsetup-tmp")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(path)
            result.written.append(str(path))
        for file, line in entry.ensure:
            ensure = Path(os.path.expanduser(file))
            try:
                current = ensure.read_text(encoding="utf-8")
            except OSError:
                current = ""
            if line not in current.splitlines():
                ensure.parent.mkdir(parents=True, exist_ok=True)
                sep = "" if not current or current.endswith("\n") else "\n"
                ensure.write_text(current + sep + line + "\n", encoding="utf-8")
        if entry.reload:
            reloads.append(entry.reload)
    path = cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(colors.to_json(), indent=1) + "\n", encoding="utf-8")
    if run_reload:
        for command in reloads:
            subprocess.Popen(["bash", "-c", command], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
    return result
