"""Built-in look presets — reading the ``presets/*.conf`` files.

A preset is a plain shell file that gives curated values to the settings in
``lib/config.sh``; on the bash side it is applied by ``lib/preset.sh``. Here the
same files are parsed for the GUI and ``python3 -m hyprsetup presets``.

Info lines in the header::

    #  preset: tokyo-night
    #  title: Tokyo Night — Neon
    #  desc: Narrow gaps, thick gradient border…
    #        (indented lines continue the description)

To add a new preset just drop a file under ``presets/``; no code change is
needed here or in the UI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import themes

META_KEYS = ("preset", "title", "desc", "group")

_META = re.compile(r"^\s*(%s)\s*:\s*(.*)$" % "|".join(META_KEYS))
_ASSIGN = re.compile(r"^\s*([A-Z][A-Z0-9_]*)=(.*)$")


@dataclass
class Preset:
    name: str
    title: str = ""
    desc: str = ""
    #: Which tab it sits in in the UI. Empty: Profiles (all of them for now;
    #: the old "script-test" tab was merged into Profiles on 2026-10-04).
    group: str = ""
    path: Path | None = None
    values: dict[str, str] = field(default_factory=dict)

    @property
    def theme(self) -> str:
        return self.values.get("THEME", themes.DEFAULT)

    @property
    def palette(self) -> dict[str, str]:
        return themes.resolve(self.theme)

    @property
    def label(self) -> str:
        return self.title or self.name


def _parse_value(raw: str) -> str:
    """``"0 4"  # comment`` → ``0 4`` — strips quotes and trailing comments."""
    raw = raw.strip()
    if raw[:1] in ('"', "'"):
        quote = raw[0]
        end = raw.find(quote, 1)
        return raw[1:end] if end > 0 else raw[1:]
    return raw.split("#", 1)[0].strip()


def parse(path: Path) -> Preset:
    preset = Preset(name=path.stem, path=path)
    meta: dict[str, list[str]] = {}
    last_key = ""
    in_header = True

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if in_header and stripped.startswith("#"):
            body = stripped[1:]
            match = _META.match(body)
            if match:
                last_key = match.group(1)
                meta.setdefault(last_key, []).append(match.group(2).strip())
                continue
            # "#        continuation line" — continues the previous info line
            if last_key and body[:3].isspace() and body.strip():
                meta[last_key].append(body.strip())
                continue
            last_key = ""
            continue
        if stripped and not stripped.startswith("#"):
            in_header = False
        match = _ASSIGN.match(line)
        if match:
            preset.values[match.group(1)] = _parse_value(match.group(2))

    preset.title = " ".join(meta.get("title", []))
    preset.desc = " ".join(meta.get("desc", []))
    preset.group = " ".join(meta.get("group", [])).strip()
    return preset


#: Keys owned by a widget set: when the set changes, corners and sizes must
#: not leak from the previous set (same as lib/preset.sh:PRESET_WIDGET_KEYS).
WIDGET_SET_KEYS = (
    "WIDGETS", "WIDGET_ZONE_TL", "WIDGET_ZONE_TC", "WIDGET_ZONE_TR",
    "WIDGET_ZONE_BL", "WIDGET_ZONE_BC", "WIDGET_ZONE_BR", "WIDGET_OFFSETS",
    "WIDGET_MARGIN", "WIDGET_GAP", "WIDGET_SCALE",
    "WIDGET_RADIUS", "WIDGET_OPACITY",
)

#: Independent axes — see lib/preset.sh
KINDS = ("profile", "bar", "terminal", "launcher", "widget", "widget-set")

#: Settings "owned" by a bar preset. All of them are reset when the preset
#: changes: otherwise leftover values from the previous preset leak — e.g.
#: rail's two-line clock (%H%n%M) or the center module area it leaves empty
#: would stay as-is after switching to a horizontal preset.
#: If a new BAR_* setting is added it must be added here too; the same list
#: is repeated in lib/preset.sh as PRESET_BAR_KEYS.
BAR_KEYS = (
    # "BAR" (waybar/hyprpanel backend) is defined by some bar presets
    # (hyprpanel-*); if it is not included here, switching to e.g. islands
    # leaves a stale "hyprpanel" and no bar backend gets picked correctly.
    "BAR",
    "BAR_POSITION", "BAR_HEIGHT", "BAR_WIDTH", "BAR_MARGIN", "BAR_SPACING",
    "BAR_PADDING", "BAR_RADIUS", "BAR_OPACITY", "BAR_WORKSPACE_STYLE",
    "BAR_CLOCK_FORMAT", "BAR_CLOCK_FORMAT_ALT", "BAR_WINDOW_MAX_LENGTH",
    "BAR_MODULES_LEFT", "BAR_MODULES_CENTER", "BAR_MODULES_RIGHT",
)

#: Look settings owned by a profile. Reset when the profile changes, so the
#: previous profile's blur/shadow does not carry over to the new one.
#: BAR_KEYS is separate because the bar preset may have been pinned by the
#: user.
#: Settings owned by a terminal preset (lib/preset.sh:PRESET_TERM_KEYS).
TERM_KEYS = (
    "TERM_OPACITY", "TERM_PADDING", "TERM_FONT_SIZE", "TERM_CURSOR_STYLE",
    "TERM_CURSOR_BLINK", "TERM_SCROLLBACK",
)

#: Settings owned by a launcher preset (PRESET_LAUNCHER_KEYS).
LAUNCHER_KEYS = (
    "LAUNCHER_WIDTH", "LAUNCHER_LINES", "LAUNCHER_POSITION",
    "LAUNCHER_OPACITY", "LAUNCHER_ICONS", "LAUNCHER_ICON_SIZE",
    "LAUNCHER_PROMPT", "LAUNCHER_RADIUS", "LAUNCHER_BORDER",
)

#: When TERM_PRESET / LAUNCHER_PRESET take this value the preset is not picked
#: by hand: it is derived from the active bar preset's character (see
#: bar_family / match_axis). Why: the three axes were picked unaware of each
#: other — a rounded frosted-glass launcher and a translucent terminal under a
#: square, opaque bar made for a desktop where nothing matched.
AUTO = "auto"

#: Bar family → (terminal preset, launcher preset). Must be EXACTLY the same
#: as lib/preset.sh:preset_match_axis.
FAMILY_MATCH: dict[str, tuple[str, str]] = {
    "glass": ("glass", "glass"),        # translucent, blurred bar
    "sharp": ("classic", "sharp"),      # no corners, solid bar
    "bare": ("minimal", "minimal"),     # no background, bare text
    "rounded": ("soft", "rounded"),     # pronounced rounded capsules
    "soft": ("minimal", "centered"),    # slightly rounded, restrained
}

FAMILY_LABELS = {
    "glass": "frosted glass", "sharp": "sharp", "bare": "bare",
    "rounded": "rounded", "soft": "soft",
}


#: Order in the gallery filter.
FAMILY_ORDER = ("sharp", "rounded", "soft", "glass", "bare")

#: Which character(s) each terminal/launcher preset belongs to — the pages'
#: "How should it look?" filter reads this. The preset FAMILY_MATCH picks is
#: always in its own family (added separately below); the rest are by hand.
_AXIS_FAMILY_EXTRA: dict[str, dict[str, tuple[str, ...]]] = {
    "terminal": {
        "compact": ("sharp",),
        "readable": ("soft", "rounded"),
        "classic": ("soft",),
        "minimal": ("rounded",),
    },
    "launcher": {
        "spotlight": ("sharp", "soft"),
        "grid": ("rounded", "soft"),
        "centered": ("rounded",),
        "minimal": ("sharp",),
    },
}


def axis_families(kind: str, name: str) -> set[str]:
    """Families of a terminal ("terminal") or launcher ("launcher") preset."""
    index = 0 if kind == "terminal" else 1
    found = {fam for fam, pair in FAMILY_MATCH.items() if pair[index] == name}
    found.update(_AXIS_FAMILY_EXTRA.get(kind, {}).get(name, ()))
    return found


def _num(value, fallback: float) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return fallback


def bar_family(values: dict) -> str:
    """Visual character of a bar preset — from corner radius and opacity."""
    radius = _num(values.get("BAR_RADIUS"), 10)
    opacity = _num(values.get("BAR_OPACITY"), 1.0)
    if 0 < opacity < 0.7:
        return "glass"
    if radius <= 0:
        return "sharp" if opacity > 0 else "bare"
    if radius >= 12:
        return "rounded"
    return "soft"


def match_axis(kind: str, values: dict) -> str:
    """Terminal ("terminal") or launcher ("launcher") preset matching the bar preset."""
    term, launcher = FAMILY_MATCH[bar_family(values)]
    return term if kind == "terminal" else launcher

LOOK_KEYS = (
    "THEME", "CUSTOM_COLORS", "FONT_FAMILY", "FONT_SIZE",
    "LAYOUT", "GAPS_IN", "GAPS_OUT", "GAPS_WORKSPACES", "BORDER_SIZE",
    "BORDER_ANGLE", "ROUNDING", "ROUNDING_POWER",
    "BLUR", "BLUR_SIZE", "BLUR_PASSES", "BLUR_XRAY", "BLUR_NOISE",
    "BLUR_CONTRAST", "BLUR_BRIGHTNESS", "BLUR_VIBRANCY", "BLUR_SPECIAL",
    "BLUR_POPUPS",
    "SHADOW", "SHADOW_RANGE", "SHADOW_RENDER_POWER", "SHADOW_OFFSET",
    "ACTIVE_OPACITY", "INACTIVE_OPACITY", "DIM_INACTIVE", "DIM_STRENGTH",
    "DIM_SPECIAL", "ANIMATIONS", "ANIMATION_PRESET", "ANIMATION_SPEED",
    # The wallpaper belongs to the profile too: on a profile switch the old
    # one's image must not stay on screen. WALLPAPER_PATH is NOT here — it is
    # the user's own file, no profile owns it.
    "WALLPAPER_IMAGE", "WALLPAPER_STYLE",
    # The animated Wallpaper Engine scene is part of the profile's look too:
    # on a profile switch the old scene id must not carry over.
    "WPENGINE_ID", "WPENGINE_SCREEN", "WPENGINE_PER_SCREEN", "WPENGINE_SCALING", "WPENGINE_FPS",
    "WPENGINE_SILENT", "WPENGINE_EXTRA_ARGS",
    # The audio visualizer is part of the profile's look too (e.g. st-gozcu):
    # it turns off when switching to another profile.
    "VIS_ENABLE", "VIS_MODE", "VIS_COLOR", "VIS_BRIGHTNESS", "VIS_HEIGHT", "VIS_WIDTH",
    "MASTER_NEW_STATUS", "MASTER_MFACT",
    "DWINDLE_PRESERVE_SPLIT", "DWINDLE_SMART_SPLIT", "DWINDLE_SMART_RESIZING",
)


def default_dir(root: Path, kind: str = "profile") -> Path:
    """The ``presets/<kind>/`` path.

    Before the axes were split, all presets lived directly under ``presets/``.
    If the subdirectory is missing it falls back to the old layout, so an
    un-updated working copy still opens.
    """
    base = Path(root) / "presets"
    sub = base / kind
    if sub.is_dir():
        return sub
    return base if kind == "profile" else sub


def load_all(directory: Path) -> list[Preset]:
    directory = Path(directory)
    if not directory.is_dir():
        return []
    return [parse(path) for path in sorted(directory.glob("*.conf"))]


#: Removed preset names → their replacement, keyed as ``"<kind>:<old>"``.
#: If a deleted name remains in the user's settings.conf it is silently
#: translated so resolution does not fail. The same table is repeated in
#: ``lib/preset.sh`` as ``PRESET_ALIAS``; update both together.
PRESET_ALIASES: dict[str, str] = {
    # media was a copy of islands shrunk by a few pixels and, lacking its own
    # CSS, did not even give the island look; islands already has CENTER=mpris.
    "bar:media": "islands",
}


def canonical(name: str, kind: str = "profile") -> str:
    """If a removed preset name is given, returns its replacement."""
    return PRESET_ALIASES.get(f"{kind}:{name}", name)


def variants_dir(root: Path, profile: str) -> Path:
    """Directory of a profile's look variants.

    A rice often comes as a single layout + several wallpapers/palettes: the
    same bar and window language, different colors. If each were a separate
    profile the layout would be copied N times; instead the profile carries
    the shared part and ``<profile>.variants/<name>.conf`` only overrides the
    keys that change the look (THEME, WALLPAPER_IMAGE…). Because the
    ``*.conf`` scan does not descend into subdirectories, variants do not show
    up separately in the profile list.
    """
    return default_dir(root, "profile") / f"{profile}.variants"


def load_variants(root: Path, profile: str) -> list[Preset]:
    if not profile or "/" in profile or profile.startswith("."):
        return []
    return load_all(variants_dir(root, profile))


def find_variant(root: Path, profile: str, name: str) -> Preset | None:
    if not name or "/" in name or name.startswith("."):
        return None
    path = variants_dir(root, profile) / f"{name}.conf"
    return parse(path) if path.is_file() else None


def imported_profiles_dir() -> Path:
    """Cards of rices imported via link (importer.py)."""
    return Path.home() / ".config" / "hyprsetup" / "imported"


def shared_profiles_dir() -> Path:
    """Shared desktops imported from a file (profileshare.py)."""
    return Path.home() / ".config" / "hyprsetup" / "shared"


def find(directory: Path, name: str) -> Preset | None:
    kind = Path(directory).name
    path = Path(directory) / f"{canonical(name, kind)}.conf"
    if not path.is_file() and kind == "profile" and name and "/" not in name:
        path = imported_profiles_dir() / f"{name}.conf"
        if not path.is_file():
            path = shared_profiles_dir() / f"{name}.conf"
    return parse(path) if path.is_file() else None


def load_profiles(root: Path) -> list[Preset]:
    """Profiles shipped with the project + imported ones (name clashes skipped)."""
    found = load_all(default_dir(root, "profile"))
    for extra in (imported_profiles_dir(), shared_profiles_dir()):
        names = {p.name for p in found}
        found += [p for p in load_all(extra) if p.name not in names]
    return found


def split_widgets(value: str) -> list[str]:
    """``"calendar, cava"`` → ``["calendar", "cava"]``"""
    return [w.strip() for w in (value or "").split(",") if w.strip()]


def reset_values(keys, defaults: dict[str, str]) -> dict[str, str]:
    """Builds a dict that resets the given keys to their schema defaults.

    When a preset changes this is applied first, then the new preset's values
    are written. So if the new preset does not define a key, the default
    applies instead of the old preset's value.
    """
    return {key: defaults.get(key, "") for key in keys}


def resolve_chain(root: Path, profile: str = "", bar: str = "",
                  widgets: str = "", terminal: str = "",
                  launcher: str = "", widget_set: str = "",
                  variant: str = "") -> dict[str, str]:
    """Resolves the profile → bar / terminal / launcher preset → widget chain.

    Same precedence rules as ``lib/preset.sh:preset_apply_chain``:

    * The profile only gives **defaults** for ``BAR_PRESET`` and ``WIDGETS``.
    * If the bar preset was given explicitly by the caller it **overrides**
      the profile's own ``BAR_*`` fine-tuning — so "I picked slim but the
      profile's height stayed" does not happen. If it came from the profile
      it is the opposite: the profile's setting wins and the bar preset only
      fills the gaps.

    Values the user edited one by one are not here; the caller
    (``SetupState``) writes them on top of the result.
    """
    root = Path(root)
    values: dict[str, str] = {}

    profile_preset = find(default_dir(root, "profile"), profile) if profile else None
    if profile_preset:
        values.update(profile_preset.values)
        # The look variant writes OVER the profile (same as lib/preset.sh):
        # if none is given the profile's own PROFILE_VARIANT default is used.
        variant_name = variant or values.get("PROFILE_VARIANT", "")
        variant_preset = find_variant(root, profile, variant_name)
        if variant_preset:
            values.update(variant_preset.values)
            values["PROFILE_VARIANT"] = variant_name
        else:
            values.pop("PROFILE_VARIANT", None)

    pinned = bool(bar)
    # Translate a removed name to its replacement; otherwise BAR_PRESET stays
    # on a name with no file and the template's BAR_IS_<NAME> flag is never
    # set.
    bar_name = canonical(bar or values.get("BAR_PRESET", ""), "bar")
    if bar_name:
        bar_preset = find(default_dir(root, "bar"), bar_name)
        if bar_preset:
            if pinned:
                values.update(bar_preset.values)       # overrides the profile
            else:
                for key, value in bar_preset.values.items():
                    values.setdefault(key, value)      # only the gaps
            values["BAR_PRESET"] = bar_name

    # The terminal and launcher axes follow exactly the same rule as the bar:
    # from the caller it overrides the profile, from the profile it only
    # fills the gaps.
    # widget-set: which widgets are on and in which corner — all in one.
    # Behaves like a bar preset, but since it also writes the WIDGETS list it
    # must be applied BEFORE the widget resolution below.
    for kind, given, key in (("widget-set", widget_set, "WIDGET_SET"),
                             ("terminal", terminal, "TERM_PRESET"),
                             ("launcher", launcher, "LAUNCHER_PRESET")):
        name = given or values.get(key, "")
        if not name and kind != "widget-set":
            name = AUTO          # no name given: the preset matching the bar preset
        if not name:
            continue
        real = match_axis(kind, values) if name == AUTO else name
        preset = find(default_dir(root, kind), real)
        if not preset:
            continue
        if given:
            values.update(preset.values)
        else:
            for k, value in preset.values.items():
                values.setdefault(k, value)
        values[key] = name

    widget_names = split_widgets(widgets or values.get("WIDGETS", ""))
    for name in widget_names:
        widget_preset = find(default_dir(root, "widget"), name)
        if widget_preset:
            for key, value in widget_preset.values.items():
                values.setdefault(key, value)
    if widget_names:
        values["WIDGETS"] = ",".join(widget_names)
    return values
