"""Template engine and config generator.

Template syntax (deliberately minimal — no external dependencies):

* ``{{VAR}}``                        variable substitution
* ``{{#if VAR}} ... {{/if}}``        emit the block if VAR is truthy
* ``{{#unless VAR}} ... {{/unless}}``emit the block if VAR is falsy
* ``{{! require: EXPR }}``           condition under which the template is rendered
* ``{{! target: path/file }}``       set the output path by hand
* ``{{! mode: 755 }}``               output file permissions

``require`` expression: ``VAR``, ``!VAR``, ``VAR==value``, ``VAR!=value``;
joined with ``&&`` for AND, ``||`` for OR.

To add a new template just drop a file under ``templates/`` — no change is
needed in this file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
import re
import shlex
import subprocess
from pathlib import Path

from .catalog import Catalog
from . import baricons
from . import keybinds as keybinds_mod
from . import themes

FALSY = {"", "0", "false", "no", "off", "none"}

# Launchers' dmenu (pick from a list) mode — see CMD_DMENU
_DMENU_CMDS = {
    "wofi": "wofi --dmenu",
    "rofi": "rofi -dmenu",
    "fuzzel": "fuzzel --dmenu",
    "walker": "walker --dmenu",
    # tofi's dmenu mode needs no separate flag: tofi-drun is run for the app
    # list, plain `tofi` for picking from stdin.
    "tofi": "tofi",
}

# Prompt text flag; left empty for launchers that do not support it (see
# hypr/scripts/powermenu.sh — if the flag is empty no prompt is passed).
_DMENU_PROMPT_FLAGS = {
    "wofi": "-p",
    "rofi": "-p",
    "fuzzel": "-p",
    "walker": "",
    "tofi": "--prompt-text",
}

_DIRECTIVE = re.compile(r"\{\{!\s*(require|target|mode)\s*:\s*(.+?)\s*\}\}")
_BLOCK = re.compile(r"\{\{(#if|#unless|/if|/unless)(?:\s+([A-Za-z0-9_]+))?\s*\}\}")
_VAR = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")


# ------------------------------------------------------------- conditions ---
def truthy(value: str | None) -> bool:
    return str(value if value is not None else "").strip().lower() not in FALSY


def eval_condition(expr: str, variables: dict[str, str]) -> bool:
    """Evaluates a ``require`` expression.

    The grammar is deliberately flat: OR groups separated by ``||``, each group
    made of atoms separated by ``&&``. Grouping with parentheses is **not
    supported**; an error is raised rather than silently giving a wrong result.
    """
    expr = expr.strip()
    if not expr:
        return True
    if "(" in expr or ")" in expr:
        raise ValueError(
            f"parentheses are not supported in require expressions: {expr!r} — "
            "write the conditions as a flat '&&' / '||' chain"
        )
    for or_part in expr.split("||"):
        if all(_eval_atom(a, variables) for a in or_part.split("&&")):
            return True
    return False


def _eval_atom(atom: str, variables: dict[str, str]) -> bool:
    atom = atom.strip()
    if not atom:
        return True
    if "!=" in atom:
        name, _, want = atom.partition("!=")
        return variables.get(name.strip(), "") != want.strip()
    if "==" in atom:
        name, _, want = atom.partition("==")
        return variables.get(name.strip(), "") == want.strip()
    if atom.startswith("!"):
        return not truthy(variables.get(atom[1:].strip(), ""))
    return truthy(variables.get(atom, ""))


# --------------------------------------------------------- template engine -
def render_text(text: str, variables: dict[str, str],
                unknown: set[str] | None = None) -> str:
    out = _substitute(_apply_blocks(text, variables), variables, unknown)
    # Skipped {{#if}} blocks leave piles of blank lines behind; clean them up.
    return re.sub(r"\n{3,}", "\n\n", out)


def _apply_blocks(text: str, variables: dict[str, str]) -> str:
    """Resolves nestable {{#if}} / {{#unless}} blocks."""
    out: list[str] = []
    stack: list[bool] = []          # per level: "is this block being emitted"
    pos = 0

    for match in _BLOCK.finditer(text):
        if all(stack):
            out.append(text[pos:match.start()])
        pos = match.end()
        tag, name = match.group(1), match.group(2) or ""

        if tag == "#if":
            stack.append(truthy(variables.get(name, "")))
        elif tag == "#unless":
            stack.append(not truthy(variables.get(name, "")))
        else:  # /if or /unless
            if not stack:
                raise ValueError(f"Unmatched closing tag: {match.group(0)}")
            stack.pop()

    if stack:
        raise ValueError("Unclosed {{#if}} / {{#unless}} block")
    out.append(text[pos:])
    return "".join(out)


def _substitute(text: str, variables: dict[str, str],
                unknown: set[str] | None = None) -> str:
    """Replaces {{VAR}} with its value; an empty string if undefined.

    Undefined variables are silent on purpose: a template may reference a
    variable that is only filled in some configurations (like
    {{ACCEL_PROFILE}}). But this also swallows typos — a template writing
    {{ROUNDNG}} drops the setting without any warning. When `unknown` is given,
    every name never defined is collected there; tools/test.sh uses this as a
    check.
    """
    def _sub(match: re.Match[str]) -> str:
        name = match.group(1)
        if unknown is not None and name not in variables:
            unknown.add(name)
        return variables.get(name, "")

    return _VAR.sub(_sub, text)


# ---------------------------------------------------------- derived values -
def derived_vars(variables: dict[str, str], catalog: Catalog,
                 selected: list[str],
                 keybinds: "keybinds_mod.Keybinds | None" = None) -> dict[str, str]:
    """Produces the computed variables the templates need."""
    # The module default is applied FIRST: if done after the `out =
    # dict(variables)` copy below, _hyprpanel_vars (reads from out) and
    # _bar_vars/_quickshell_bar_vars (read from variables) see different lists.
    variables = _bar_module_defaults(variables)
    # WORKSPACE_SPLIT=auto → WORKSPACE_MONITOR_MAP is generated from the
    # connected monitors; resolved FIRST so both workspaces.conf and waybar's
    # persistent-workspaces see the same mapping.
    variables = _auto_workspace_split(variables)
    out = dict(variables)
    theme_name, palette = effective_palette(variables)
    # derive() turns an unknown theme name ("auto") into DEFAULT; passing the
    # palette as a full override gives the right result.
    out.update(themes.derive(theme_name if theme_name in themes.THEMES
                             else themes.DEFAULT, palette))
    if theme_name == "auto":
        out["THEME"] = "auto"
    # So generated scripts (barpanel.py) can find this package: if there is no
    # installed copy (settings app running from the repo), the generating copy's path.
    out.setdefault("SETUP_PYTHON", str(Path(__file__).resolve().parent.parent))
    return _finish_derived(out, variables, catalog, selected, keybinds)


def effective_palette(variables: dict[str, str]) -> tuple[str, dict[str, str]]:
    """The palette the settings ACTUALLY produce: (theme name, 11 colors).

    Order: base palette (a built-in theme, or extracted from the wallpaper if
    THEME="auto") → manual tone (PALETTE_HUE/SATURATION/LIGHTNESS) →
    CUSTOM_COLORS. Individually picked colors are on top: a color the user set
    by hand must win over both the extracted and the tone-shifted color.

    A single place so rendering, the GUI preview and the mix use the same rule
    — previously the GUI previewed the default theme while THEME="auto".

    Order matters: install.sh runs wallpaper_step BEFORE render_run, so
    WALLPAPER_PATH here points at a file that really exists.
    """
    from . import palette as palette_mod

    theme_name = (variables.get("THEME") or themes.DEFAULT).strip()
    base = None
    if theme_name.lower() == "auto":
        extracted = _auto_palette(variables)
        # The backend may return missing roles; the gaps come from the default theme.
        base = ({**themes.THEMES[themes.DEFAULT], **extracted}
                if extracted else None)
        # If extraction fails, silently fall back to the default theme — the
        # install must not stop because the wallpaper could not be read.
        theme_name = "auto" if base else themes.DEFAULT
    if base is None:
        base = themes.resolve(theme_name)
    palette = palette_mod.adjust(base, *palette_mod.tone_from(variables))
    palette.update(themes.parse_overrides(variables.get("CUSTOM_COLORS", "")))
    return theme_name, palette


#: (path, mtime, dark, backend) → extracted palette. matugen/magick take ~1 s
#: per image; since the GUI preview asks for the palette again on every
#: settings change, the UI would stutter without a cache. mtime is in the key:
#: if a new image is written to the same path (pattern generation) it is re-extracted.
_AUTO_CACHE: dict[tuple, dict[str, str] | None] = {}


def _auto_palette(variables: dict[str, str]) -> dict[str, str] | None:
    """Extracts a palette from the wallpaper for THEME="auto"."""
    from . import palette as palette_mod

    wallpaper = variables.get("WALLPAPER_PATH", "")
    if not wallpaper:
        return None
    dark = (variables.get("COLOR_SCHEME", "dark").strip().lower() != "light")
    backend = (variables.get("PALETTE_BACKEND", "auto").strip().lower() or "auto")
    path = Path(wallpaper).expanduser()
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return None
    key = (str(path), stamp, dark, backend)
    if key not in _AUTO_CACHE:
        if len(_AUTO_CACHE) > 16:
            _AUTO_CACHE.clear()
        _AUTO_CACHE[key] = palette_mod.extract(path, dark=dark, backend=backend)
    cached = _AUTO_CACHE[key]
    return dict(cached) if cached else None


# ------------------------------------------------------- terminal settings --
# The TERM_* keys are one abstract set of settings; four terminals want the
# same thing under different names (cursor "beam" vs "bar" vs "Beam", scrollback
# in lines vs bytes). Translation happens here so templates stay one-line assignments.
def _bool(value: str, default: bool = False) -> bool:
    text = (value or "").strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off"):
        return False
    return default


def _int(value: str, fallback: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _clamp01(value: str, fallback: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return fallback


def _terminal_vars(variables: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}

    style = (variables.get("TERM_CURSOR_STYLE") or "block").strip().lower()
    if style not in ("block", "beam", "underline"):
        style = "block"
    out["TERM_CURSOR"] = style                       # kitty + foot
    out["TERM_CURSOR_ALACRITTY"] = style.capitalize()  # Block | Beam | Underline
    # Ghostty says "bar" instead of "beam" (see ghostty +show-config --docs).
    out["TERM_CURSOR_GHOSTTY"] = "bar" if style == "beam" else style

    blink = _bool(variables.get("TERM_CURSOR_BLINK", ""), False)
    # WezTerm combines cursor shape and blinking in ONE key
    # (SteadyBlock / BlinkingBar …), so it is built after reading blink.
    out["TERM_CURSOR_WEZTERM"] = ("Blinking" if blink else "Steady") + {
        "block": "Block", "beam": "Bar", "underline": "Underline",
    }[style]
    out["TERM_BLINK"] = "true" if blink else "false"      # ghostty
    out["TERM_BLINK_YESNO"] = "yes" if blink else "no"    # foot
    # kitty wants the interval in seconds; 0 = no blinking.
    out["TERM_BLINK_KITTY"] = "0.5" if blink else "0"
    out["TERM_BLINK_ALACRITTY"] = "Always" if blink else "Never"

    lines = max(0, _int(variables.get("TERM_SCROLLBACK", ""), 10000))
    out["TERM_SCROLLBACK_LINES"] = str(lines)
    # Ghostty limits scrollback in BYTES; ~1 KB per line is a good
    # approximation for 80-column text (its own default is 10 MB).
    out["TERM_SCROLLBACK_BYTES"] = str(lines * 1024)

    out["TERM_OPACITY_VALUE"] = f"{_clamp01(variables.get('TERM_OPACITY', ''), 0.95):.2f}"
    out["TERM_PADDING_VALUE"] = str(max(0, _int(variables.get("TERM_PADDING", ""), 8)))
    # An empty TERM_FONT_SIZE means "use the general font size".
    size = (variables.get("TERM_FONT_SIZE") or "").strip()
    out["TERM_FONT_SIZE_VALUE"] = str(_int(size, _int(variables.get("FONT_SIZE", ""), 11)))
    out.update(_fetch_vars(variables))
    out.update(_term_background_vars(variables))
    return out


#: Terminals that can draw real images (kitty graphics protocol). In the others
#: (foot, Alacritty) the image is drawn from characters with chafa.
_KITTY_GRAPHICS = ("kitty", "ghostty", "wezterm")

#: Logo drawing style → chafa symbol set. "image" falls back to blocks in a
#: terminal that cannot draw real images (foot, Alacritty).
_CHAFA_SYMBOLS = {"image": "block", "braille": "braille", "block": "block",
                  "ascii": "ascii"}

_FETCH_MODULES = {
    "short": ["title", "separator", "os", "kernel", "uptime", "wm",
              "terminal", "memory", "break", "colors"],
    "full": ["title", "separator", "os", "host", "kernel", "uptime", "packages",
             "shell", "display", "de", "wm", "wmtheme", "theme", "icons", "font",
             "cursor", "terminal", "terminalfont", "cpu", "gpu", "memory", "swap",
             "disk", "localip", "battery", "poweradapter", "locale", "break",
             "colors"],
}


def png_size(path: Path) -> tuple[int, int] | None:
    """A PNG's (width, height) — from the header, no library."""
    try:
        with open(path, "rb") as handle:
            head = handle.read(24)
    except OSError:
        return None
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def _image_path(value: str) -> Path | None:
    value = (value or "").strip()
    if not value:
        return None
    path = Path(value).expanduser().resolve()
    return path if path.is_file() else None


def _fetch_vars(variables: dict[str, str]) -> dict[str, str]:
    """fastfetch's logo fields and module list (TERM_LOGO, TERM_FETCH_INFO).

    Image logo: ``kitty-direct`` in kitty/Ghostty/WezTerm (the terminal reads
    the file itself, no imagemagick needed; it wants PNG — the UI converts the
    chosen image to PNG), ``chafa`` in foot/Alacritty. Height follows the
    image's ratio: a character cell is about twice as tall, so the ratio is
    halved. If the file is missing it falls back to the distro logo, so
    fastfetch does not error on an empty logo.
    """
    mode = (variables.get("TERM_FETCH") or "default").strip()
    out = {"TERM_FETCH_ON": "1" if mode == "on" else "",
           "TERM_FETCH_OFF": "1" if mode == "off" else ""}
    logo = (variables.get("TERM_LOGO") or "distro").strip()
    fields: dict[str, object] = {}
    image = None
    if logo == "image":
        image = _image_path(variables.get("TERM_LOGO_IMAGE", ""))
    elif logo == "souprland":
        image = _image_path(variables.get("SOUPRLAND_LOGO", ""))
    if image is not None:
        terminal = (variables.get("TERMINAL") or "kitty").strip()
        width = max(4, min(_int(variables.get("TERM_LOGO_WIDTH", ""), 24), 80))
        size = png_size(image)
        ratio = size[1] / size[0] if size and size[0] else 1.0
        style = (variables.get("TERM_LOGO_STYLE") or "image").strip()
        if style not in _CHAFA_SYMBOLS:
            style = "image"
        fields = {"type": "chafa", "source": str(image), "width": width,
                  "height": max(2, round(width * ratio * 0.5)),
                  "padding": {"top": 1, "left": 1, "right": 3}}
        if style == "image" and terminal in _KITTY_GRAPHICS:
            fields["type"] = "kitty-direct"
        else:
            chafa: dict[str, object] = {"symbols": _CHAFA_SYMBOLS[style], "fgOnly": True}
            if _bool(variables.get("TERM_LOGO_MONO", ""), False) and style != "image":
                # No color codes: the terminal's own text color (the theme's FG).
                chafa["canvasMode"] = "FGBG"
            fields["chafa"] = chafa
            # fastfetch caches the chafa drawing per image+size; when the style
            # changes the old drawing must not come back.
            fields["cache"] = False
    elif logo == "small":
        fields = {"type": "small"}
    elif logo == "none":
        fields = {"type": "none"}
    else:
        fields = {"type": "builtin"}
    out["FETCH_LOGO_FIELDS"] = "".join(
        f"{json.dumps(k)}: {json.dumps(v)}, " for k, v in fields.items())
    info = (variables.get("TERM_FETCH_INFO") or "short").strip()
    out["FETCH_MODULES_JSON"] = json.dumps(_FETCH_MODULES.get(info, _FETCH_MODULES["short"]))
    return out


def _term_background_vars(variables: dict[str, str]) -> dict[str, str]:
    """Terminal background image: kitty, Ghostty and WezTerm equivalents.

    TERM_BG_DIM is a single "dimming" value; kitty wants it as background_tint
    (the image is tinted with the background color), Ghostty as the image's
    opacity, WezTerm as brightness.
    """
    image = _image_path(variables.get("TERM_BG_IMAGE", ""))
    dim = _clamp01(variables.get("TERM_BG_DIM", ""), 0.75)
    fit = (variables.get("TERM_BG_FIT") or "cover").strip()
    if fit not in ("cover", "center", "tile"):
        fit = "cover"
    return {
        "TERM_BG_ON": "1" if image else "",
        "TERM_BG_PATH": str(image or ""),
        "TERM_BG_KITTY_LAYOUT": {"cover": "cscaled", "center": "centered",
                                 "tile": "tiled"}[fit],
        "TERM_BG_KITTY_TINT": f"{dim:.2f}",
        "TERM_BG_GHOSTTY_FIT": {"cover": "cover", "center": "none",
                                "tile": "none"}[fit],
        "TERM_BG_GHOSTTY_REPEAT": "true" if fit == "tile" else "false",
        "TERM_BG_GHOSTTY_POSITION": "center",
        "TERM_BG_GHOSTTY_OPACITY": f"{1 - dim:.2f}",
        "TERM_BG_WEZTERM_SIZE": {"cover": "'Cover'", "center": "'Contain'",
                                 "tile": "'Contain'"}[fit],
        "TERM_BG_WEZTERM_REPEAT": "'Repeat'" if fit == "tile" else "'NoRepeat'",
        "TERM_BG_WEZTERM_BRIGHTNESS": f"{1 - dim:.2f}",
    }


# ------------------------------------------------ app launcher settings --
#: walker's extra query sources: name → (prefix, elephant package, label).
#:
#: walker 1.x does not gather data itself; it gets it from a backend service
#: called "elephant", and every source is a separate elephant plugin (a
#: separate package in the AUR). So enabling a provider means two things:
#: writing its prefix into config.toml (here) and installing its package
#: (config/components.json → walker). The prefixes are upstream's own
#: defaults (resources/config.toml); ones without a prefix are reached via
#: ";" (providerlist).
LAUNCHER_PROVIDERS: dict[str, tuple[str, str, str]] = {
    "calc":         ("=", "elephant-calc-bin", "Calculator"),
    "websearch":    ("@", "elephant-websearch-bin", "Web search"),
    "clipboard":    (":", "elephant-clipboard-bin", "Clipboard history"),
    "symbols":      (".", "elephant-symbols-bin", "Emoji and symbols"),
    "files":        ("/", "elephant-files-bin", "File search"),
    "windows":      ("$", "elephant-windows-bin", "Open windows"),
    "runner":       (">", "elephant-runner-bin", "Run command"),
    "providerlist": (";", "elephant-providerlist-bin", "Provider list"),
    "todo":         ("!", "elephant-todo-bin", "To-do"),
    "bookmarks":    ("%", "elephant-bookmarks-bin", "Bookmarks"),
    "unicode":      ("", "elephant-unicode-bin", "Unicode characters"),
    "bluetooth":    ("", "elephant-bluetooth-bin", "Bluetooth devices"),
    "wireplumber":  ("", "elephant-wireplumber-bin", "Audio devices"),
    "playerctl":    ("", "elephant-playerctl-bin", "Media player"),
    "archlinuxpkgs": ("", "elephant-archlinuxpkgs-bin", "Arch package search"),
    "snippets":     ("", "elephant-snippets-bin", "Text snippets"),
}

#: Providers queried even without a prefix: the user sees their results next
#: to the apps without typing anything. This is upstream's default too
#: (desktopapplications + calc + websearch); the rest are called with a
#: prefix, otherwise typing "fi" would mix calculator and file results in
#: among the apps.
LAUNCHER_PROVIDERS_ALWAYS = ("calc", "websearch")


def split_launcher_providers(value: str) -> list[str]:
    """Turns the LAUNCHER_PROVIDERS setting into known provider names."""
    seen: list[str] = []
    for name in (n.strip() for n in (value or "").split(",")):
        if name in LAUNCHER_PROVIDERS and name not in seen:
            seen.append(name)
    return seen


def _launcher_provider_vars(variables: dict[str, str]) -> dict[str, str]:
    """Generates the [providers] section of walker's config.toml."""
    enabled = split_launcher_providers(variables.get("LAUNCHER_PROVIDERS", ""))

    # desktopapplications always comes first: if the app list does not show
    # on an empty query, the launcher stops being a launcher.
    default = ["desktopapplications"]
    default += [name for name in LAUNCHER_PROVIDERS_ALWAYS if name in enabled]
    blocks = []
    for name in enabled:
        prefix = LAUNCHER_PROVIDERS[name][0]
        if not prefix:
            continue
        blocks.append("[[providers.prefixes]]\n"
                      f"prefix = {json.dumps(prefix)}\n"
                      f"provider = {json.dumps(name)}")
    return {
        "LAUNCHER_PROVIDERS_DEFAULT": json.dumps(default),
        "LAUNCHER_PROVIDERS_PREFIXES": "\n\n".join(blocks),
        "LAUNCHER_HAS_PROVIDERS": "1" if enabled else "",
    }


def _launcher_vars(variables: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = dict(_launcher_provider_vars(variables))

    width = max(5, min(100, _int(variables.get("LAUNCHER_WIDTH", ""), 45)))
    out["LAUNCHER_WIDTH_PCT"] = str(width)
    # fuzzel wants the width in CHARACTERS; a one-to-one mapping to a
    # percentage is not possible (depends on the font). The repo's old fixed
    # value was 45%↔45 characters, and that ratio is kept — so the setting
    # works in the right direction.
    out["LAUNCHER_WIDTH_CHARS"] = str(width)

    out["LAUNCHER_LINES_VALUE"] = str(max(1, _int(variables.get("LAUNCHER_LINES", ""), 10)))

    position = (variables.get("LAUNCHER_POSITION") or "center").strip().lower()
    if position not in ("center", "top"):
        position = "center"
    out["LAUNCHER_POS"] = position                                   # wofi
    out["LAUNCHER_ANCHOR"] = "center" if position == "center" else "top"   # fuzzel
    # rofi gives the position as a number: 0 = center, 2 = top center.
    out["LAUNCHER_POS_ROFI"] = "0" if position == "center" else "2"

    opacity = _clamp01(variables.get("LAUNCHER_OPACITY", ""), 0.93)
    out["LAUNCHER_OPACITY_VALUE"] = f"{opacity:.2f}"
    # fuzzel/rofi colors want alpha as a hex suffix (#rrggbbaa).
    out["LAUNCHER_ALPHA_HEX"] = f"{round(opacity * 255):02x}"

    icons = _bool(variables.get("LAUNCHER_ICONS", ""), True)
    out["LAUNCHER_ICONS_BOOL"] = "true" if icons else "false"
    out["LAUNCHER_ICONS_YESNO"] = "yes" if icons else "no"
    out["LAUNCHER_ICON_SIZE_VALUE"] = str(max(1, _int(variables.get("LAUNCHER_ICON_SIZE", ""), 32)))
    out["LAUNCHER_PROMPT_TEXT"] = (variables.get("LAUNCHER_PROMPT") or "Search…").strip()

    # Shape: same as windows if empty. The five launchers' templates carried
    # their own fixed border (2px) and corners (10px/5px); the launcher looked
    # detached from the windows and the bar on screen.
    radius = max(0, _int(variables.get("LAUNCHER_RADIUS", ""),
                         _int(variables.get("ROUNDING", ""), 10)))
    border = max(0, _int(variables.get("LAUNCHER_BORDER", ""),
                         _int(variables.get("BORDER_SIZE", ""), 2)))
    out["LAUNCHER_RADIUS_VALUE"] = str(radius)
    # Inner items (selected row, search box) should be slightly smaller than
    # the outer corner, otherwise two equal nested arcs look "bloated".
    out["LAUNCHER_INNER_RADIUS"] = str(max(0, radius - 4) if radius > 4 else radius)
    out["LAUNCHER_BORDER_VALUE"] = str(border)

    # tofi does not grow the window to its content (unlike wofi/fuzzel): it
    # draws whatever width and height are given. LAUNCHER_LINES cannot be used
    # directly as a height — a line count is not pixels. A fixed share is
    # reserved for the input line + margins, plus about 4% of screen height
    # per line; the result is clamped to 20%–90% so it does not overflow.
    lines = max(1, _int(variables.get("LAUNCHER_LINES", ""), 10))
    out["LAUNCHER_HEIGHT_PCT_TOFI"] = str(max(20, min(90, 8 + lines * 4)))
    return out


#: Selected terminal/browser/file manager → .desktop id. When the dock first
#: opens these come pinned (see dock.sh: seed_pins). The id is the name of
#: the .desktop file the package installs; the script only writes the ones
#: actually found, so if a guess is wrong the icon simply does not appear.
DOCK_DESKTOP_IDS: dict[str, tuple[str, ...]] = {
    "kitty": ("kitty",),
    "alacritty": ("Alacritty", "alacritty"),
    "foot": ("foot",),
    "ghostty": ("com.mitchellh.ghostty", "ghostty"),
    "wezterm": ("org.wezfurlong.wezterm", "wezterm"),
    "firefox": ("firefox",),
    "chromium": ("chromium",),
    "brave": ("brave-browser",),
    "zen-browser": ("zen", "zen-browser"),
    "thunar": ("thunar",),
    "nautilus": ("org.gnome.Nautilus",),
    "nemo": ("nemo",),
    "dolphin": ("org.kde.dolphin",),
    "yazi": ("yazi",),
}


def _dock_vars(variables: dict[str, str]) -> dict[str, str]:
    """nwg-dock-hyprland's command line and initial pinned apps."""
    position = variables.get("DOCK_POSITION") or "bottom"
    if position not in ("bottom", "top", "left", "right"):
        position = "bottom"
    margin = _int(variables.get("DOCK_MARGIN"), 8)
    icon = max(16, min(128, _int(variables.get("DOCK_ICON_SIZE"), 40)))
    args = ["-p", position, "-i", str(icon),
            f"-m{position[0]}", str(max(0, margin)),
            "-w", str(max(1, _int(variables.get("WORKSPACE_COUNT"), 10)))]
    # An auto-hiding dock floats over windows; an always-visible dock reserves
    # space (-x), otherwise it would cover the bottom rows.
    args.append("-d" if _bool(variables.get("DOCK_AUTOHIDE")) else "-x")
    monitor = (variables.get("DOCK_MONITOR") or "").strip()
    if monitor:
        args += ["-o", monitor]
    if not _bool(variables.get("DOCK_LAUNCHER"), True):
        args.append("-nolauncher")
    pins: list[str] = []
    for key in ("TERMINAL", "BROWSER", "FILEMANAGER"):
        value = (variables.get(key) or "").strip()
        # Ones not in the list (e.g. a hand-typed browser) are tried by their own name.
        pins += DOCK_DESKTOP_IDS.get(value, (value,) if value else ())
    try:
        opacity = max(0.0, min(1.0, float(variables.get("DOCK_OPACITY") or 0.85)))
    except ValueError:
        opacity = 0.85
    return {
        # Embedded in the script as a bash array; values are quoted for the shell.
        "DOCK_ARGS": " ".join(shlex.quote(a) for a in args),
        "DOCK_PIN_CANDIDATES": " ".join(shlex.quote(p) for p in pins),
        "DOCK_OPACITY_CSS": f"{opacity:.2f}",
        "DOCK_RADIUS_PX": str(max(0, _int(variables.get("DOCK_RADIUS"), 18))),
        "DOCK_ICON_PAD": str(max(2, icon // 10)),
    }


def _hyprlang_text(value: str) -> str:
    """Safely puts free text into a hyprlang value.

    In hyprlang '#' starts a comment ('##' is a literal hash); a line break
    ends the value. Lock screen labels also go through Pango markup.
    """
    text = " ".join((value or "").split())
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return text.replace("#", "##")


def _strftime_arg(value: str, fallback: str) -> str:
    """A format to go inside `date +'...'`: quotes and shell characters are dropped.

    The format is embedded in hyprlock's `cmd[...] echo "$(date +'…')"` line;
    a quote or backtick would break the command, '#' would count as a
    hyprlang comment.
    """
    text = "".join(ch for ch in (value or "") if ch not in "'\"`$\\\n")
    return (text.strip() or fallback).replace("#", "##")


def _lock_vars(variables: dict[str, str]) -> dict[str, str]:
    """Lock screen values for hyprlock.conf and hypridle.conf."""
    background = (variables.get("LOCK_BACKGROUND") or "wallpaper").strip()
    if background == "screenshot":
        bg_path = "screenshot"
    elif background == "color":
        bg_path = ""
    else:
        bg_path = variables.get("WALLPAPER_PATH", "")
    clock_size = max(30, min(240, _int(variables.get("LOCK_CLOCK_SIZE"), 110)))
    try:
        brightness = max(0.1, min(1.5, float(variables.get("LOCK_BRIGHTNESS") or 0.8)))
    except ValueError:
        brightness = 0.8
    grace = max(0, min(60, _int(variables.get("LOCK_GRACE"), 0)))
    return {
        "LOCK_BG_PATH": bg_path,
        "LOCK_BLUR_PASSES_VALUE": str(max(0, min(6, _int(variables.get("LOCK_BLUR_PASSES"), 3)))),
        "LOCK_BLUR_SIZE_VALUE": str(max(1, min(30, _int(variables.get("LOCK_BLUR_SIZE"), 8)))),
        "LOCK_BRIGHTNESS_VALUE": f"{brightness:.2f}",
        "LOCK_CLOCK_FMT": _strftime_arg(variables.get("LOCK_CLOCK_FORMAT", ""), "%H:%M"),
        "LOCK_CLOCK_SIZE_VALUE": str(clock_size),
        # The clock sits above the date; the gap between them widens as the
        # clock grows (the old fixed layout at 110 pt: clock 220, date 130).
        "LOCK_CLOCK_Y": str(130 + round(clock_size * 0.82)),
        "LOCK_DATE_FMT": _strftime_arg(variables.get("LOCK_DATE_FORMAT", ""),
                                       "%d %B %Y, %A"),
        "LOCK_DATE_SIZE": str(max(11, round(clock_size * 0.18))),
        "LOCK_INPUT_WIDTH_VALUE": str(max(160, min(800, _int(variables.get("LOCK_INPUT_WIDTH"), 320)))),
        "LOCK_PLACEHOLDER_TEXT": (_hyprlang_text(variables.get("LOCK_PLACEHOLDER", ""))
                                  or "Password…"),
        # hyprlock 0.6+ removed the `general:grace` setting, there is only the
        # --grace flag. The flag is added ONLY to the listener that locks on
        # idle: if locking before sleep (before_sleep_cmd) had a delay, anyone
        # opening the lid would get in without a password.
        "LOCK_GRACE_FLAG": f" --grace {grace}" if grace else "",
        "IDLE_DIM_LEVEL_VALUE": str(max(1, min(90, _int(variables.get("IDLE_DIM_LEVEL"), 10)))),
        "IDLE_IGNORE_INHIBIT": ("false" if _bool(variables.get("IDLE_RESPECT_INHIBIT"), True)
                                else "true"),
    }


def _groupbar_vars(variables: dict[str, str]) -> dict[str, str]:
    """Tab bar of window groups (hyprland.conf → group:groupbar)."""
    style = (variables.get("GROUPBAR_STYLE") or "tabs").strip()
    height = max(4, min(40, _int(variables.get("GROUPBAR_HEIGHT"), 18)))
    tabs = style == "tabs"
    return {
        # tabs: filled tabs · line: thin line + title · indicator: line only
        "GROUPBAR_GRADIENTS": "true" if tabs else "false",
        "GROUPBAR_RENDER_TITLES": "false" if style == "indicator" else "true",
        "GROUPBAR_HEIGHT_VALUE": str(height),
        "GROUPBAR_FONT_SIZE_VALUE": str(max(6, min(24, _int(variables.get("GROUPBAR_FONT_SIZE"), 10)))),
        "GROUPBAR_ROUNDING": str(min(_int(variables.get("ROUNDING"), 8), height // 2)),
        # On a filled tab the text sits on the accent color and must be dark;
        # in line mode it sits on the window and must be light.
        "GROUPBAR_TEXT": variables.get("RGBA_BG_DARK" if tabs else "RGBA_FG", ""),
        "GROUPBAR_TEXT_INACTIVE": variables.get("RGBA_FG" if tabs else "RGBA_SUBTEXT", ""),
    }


def _plugin_vars(variables: dict[str, str]) -> dict[str, str]:
    """Adjustable sizes of the hyprpm plugins (plugins.conf)."""
    height = max(16, min(48, _int(variables.get("HYPRBARS_HEIGHT"), 26)))
    return {
        "HYPREXPO_COLUMNS_VALUE": str(max(2, min(6, _int(variables.get("HYPREXPO_COLUMNS"), 3)))),
        "HYPRBARS_HEIGHT_VALUE": str(height),
        # Buttons scale with the title bar (the old fixed 14 px at 26 px).
        "HYPRBARS_BUTTON_SIZE": str(round(height * 14 / 26)),
    }


def _screenshot_dir_vars(variables: dict[str, str]) -> dict[str, str]:
    """SCREENSHOT_DIR in the forms embedded in shell and Python scripts.

    The value goes both into a double-quoted shell string (keybinding, bar
    panel) and a Python string literal (actions.py); quotes, backticks and
    backslashes that could break either are dropped. A leading ~ is turned
    into $HOME since it does not expand inside shell quotes. Empty = XDG
    Pictures/Screenshots.
    """
    raw = "".join(ch for ch in (variables.get("SCREENSHOT_DIR") or "")
                  if ch not in "\"'`\\\n").strip().rstrip("/")
    shell = ("$HOME" + raw[1:]) if raw.startswith("~") else raw
    return {
        "SCREENSHOT_DIR_SH": shell or "$(xdg-user-dir PICTURES)/Screenshots",
        "SCREENSHOT_DIR_PY": raw,
    }


def _record_vars(variables: dict[str, str]) -> dict[str, str]:
    """gpu-screen-recorder flag values for record.sh.

    If settings.conf is hand-edited with an unrecognized value,
    gpu-screen-recorder would die before starting; every unrecognized value
    falls back to the default.
    """
    def pick(key: str, allowed: tuple[str, ...], default: str) -> str:
        value = (variables.get(key) or "").strip().lower()
        return value if value in allowed else default
    codec = pick("RECORD_CODEC", ("auto", "h264", "hevc", "av1"), "auto")
    return {
        "RECORD_FORMAT_VALUE": pick("RECORD_FORMAT", ("mp4", "mkv"), "mp4"),
        "RECORD_QUALITY_VALUE": pick("RECORD_QUALITY",
                                     ("medium", "high", "very_high", "ultra"),
                                     "very_high"),
        # auto: -k is not passed at all, gpu-screen-recorder picks by GPU.
        "RECORD_CODEC_VALUE": "" if codec == "auto" else codec,
        "RECORD_CURSOR_VALUE": "yes" if _bool(variables.get("RECORD_CURSOR"), True) else "no",
    }


def _rule_vars(variables: dict[str, str]) -> dict[str, str]:
    """Sizes for the built-in window rules (picture-in-picture)."""
    width = max(240, min(1920, _int(variables.get("PIP_WIDTH"), 640)))
    height = round(width * 9 / 16)
    return {
        "PIP_SIZE": f"{width} {height}",
        # Bottom-right corner, 20 px from the edge; 40 px at the bottom (old 640×360 → -660 -400).
        "PIP_MOVE": f"100%-{width + 20} 100%-{height + 40}",
    }


#: NOTIFY_POSITION value → (horizontal, vertical). "auto" is the right corner
#: and follows the bar's edge (bar at the bottom → notifications at the bottom).
_NOTIFY_POSITIONS = {
    "top-right": ("right", "top"), "top-left": ("left", "top"),
    "top-center": ("center", "top"), "bottom-right": ("right", "bottom"),
    "bottom-left": ("left", "bottom"), "bottom-center": ("center", "bottom"),
}


def _notify_vars(variables: dict[str, str]) -> dict[str, str]:
    """Shared notification values for mako, dunst and swaync."""
    position = (variables.get("NOTIFY_POSITION") or "auto").strip()
    if position in _NOTIFY_POSITIONS:
        horizontal, vertical = _NOTIFY_POSITIONS[position]
    else:
        # With a vertical bar (left/right) notifications still sit at the top;
        # swaync's positionY used to take BAR_POSITION directly and wrote an
        # invalid value like "left" when the bar was on the side.
        horizontal = "right"
        vertical = "bottom" if variables.get("BAR_POSITION") == "bottom" else "top"
    timeout = max(0, min(120, _int(variables.get("NOTIFY_TIMEOUT"), 6)))
    # Low-priority notifications stay two thirds as long as normal (6 → 4 s,
    # the old fixed values). 0 = none closes by itself.
    low = max(1, timeout * 2 // 3) if timeout else 0
    critical = 0 if _bool(variables.get("NOTIFY_CRITICAL_STICKY"), True) else timeout
    width = max(200, min(900, _int(variables.get("NOTIFY_WIDTH"), 380)))
    return {
        "NOTIFY_ANCHOR": f"{vertical}-{horizontal}",
        "NOTIFY_POS_X": horizontal,
        "NOTIFY_POS_Y": vertical,
        "NOTIFY_TIMEOUT_SEC": str(timeout),
        "NOTIFY_TIMEOUT_MS": str(timeout * 1000),
        "NOTIFY_TIMEOUT_LOW_SEC": str(low),
        "NOTIFY_TIMEOUT_LOW_MS": str(low * 1000),
        "NOTIFY_TIMEOUT_CRIT_SEC": str(critical),
        "NOTIFY_TIMEOUT_CRIT_MS": str(critical * 1000),
        "NOTIFY_WIDTH_VALUE": str(width),
        # dunst's progress bar is 20 px narrower than the box (the old 380/360 ratio).
        "NOTIFY_PROGRESS_MAX": str(width - 20),
        "NOTIFY_MAX_VISIBLE_VALUE": str(max(1, min(20, _int(variables.get("NOTIFY_MAX_VISIBLE"), 5)))),
        "NOTIFY_MARGIN_VALUE": str(max(0, min(200, _int(variables.get("NOTIFY_MARGIN"), 12)))),
        "NOTIFY_ICON_SIZE_VALUE": str(max(16, min(128, _int(variables.get("NOTIFY_ICON_SIZE"), 48)))),
    }


def _finish_derived(out: dict[str, str], variables: dict[str, str],
                    catalog: Catalog, selected: list[str],
                    keybinds: "keybinds_mod.Keybinds | None") -> dict[str, str]:
    """Shared tail of derived_vars after the palette."""
    out.update(_bar_vars(variables, selected))
    # Waybar module icons (BAR_I_*): the selected icon set, see baricons.py.
    out.update(baricons.template_vars(variables.get("BAR_ICON_STYLE", "")))
    out.update(_terminal_vars(variables))
    out.update(_launcher_vars(variables))
    out.update(_hyprpanel_vars(out, selected))
    out.update(_wayle_vars(out, selected))
    out.update(_eww_widget_vars(variables, selected, out))
    out.update(_quickshell_widget_vars(variables, selected, out))
    out.update(_quickshell_bar_vars(variables, selected))
    out.update(_dock_vars(variables))
    out.update(_lock_vars(out))
    out.update(_notify_vars(variables))
    out.update(_groupbar_vars(out))
    out.update(_plugin_vars(variables))
    out.update(_screenshot_dir_vars(variables))
    out.update(_record_vars(variables))
    out.update(_rule_vars(variables))

    mod = variables.get("MOD_KEY", "SUPER")
    # HYPR_LANG is already a concrete value ('conf' or 'lua') at this point —
    # 'auto' is resolved by lib/preflight.sh in the render_export_vars stage.
    lang = (variables.get("HYPR_LANG") or "conf").strip().lower()
    if lang not in ("conf", "lua"):
        lang = "conf"

    # --- workspace keybindings ---------------------------------------------
    try:
        count = max(1, min(20, int(variables.get("WORKSPACE_COUNT") or 10)))
    except ValueError:
        count = 10
    # end-4 layout: MOD+n focuses, MOD+ALT+n sends the window to that workspace
    # but focus stays put (movetoworkspacesilent). 11..20 same layout with CTRL.
    binds = []
    for i in range(1, count + 1):
        key = "0" if i == 10 else str(i % 10) if i > 10 else str(i)
        high = i > 10                   # 11..20 → MOD+CTRL+n
        if lang == "lua":
            mods = f"{mod} + CTRL" if high else mod
            binds.append(f'hl.bind("{mods} + {key}", hl.dsp.focus({{ workspace = {i} }}))')
            binds.append(f'hl.bind("{mods} + ALT + {key}", '
                         f'hl.dsp.window.move({{ workspace = {i}, follow = false }}))')
        else:
            mods = f"{mod} CTRL" if high else mod
            binds.append(f"bind = {mods}, {key}, workspace, {i}")
            binds.append(f"bind = {mods} ALT, {key}, movetoworkspacesilent, {i}")
    out["WORKSPACE_BINDS"] = "\n".join(binds)

    # --- monitors -----------------------------------------------------------
    specs = [s.strip() for s in (variables.get("MONITOR_SPEC") or "").split(";") if s.strip()]
    if not specs:
        specs = [",preferred,auto,1"]
    # A rule with an empty name covers every display; the template's own
    # catch-all default must then not follow it (the last rule wins).
    out["MONITOR_NEEDS_DEFAULT"] = "" if any(not s.split(",")[0].strip() for s in specs) else "1"
    if lang == "lua":
        out["MONITOR_LINES"] = "\n".join(_lua_monitor_line(s) for s in specs)
    else:
        out["MONITOR_LINES"] = "\n".join(f"monitor = {s}" for s in specs)

    # --- workspace → monitor mapping ----------------------------------------
    out["WORKSPACE_MONITOR_LINES"] = "\n".join(
        _workspace_monitor_lines(variables.get("WORKSPACE_MONITOR_MAP", ""), lang)
    )

    # --- animations (scaled by ANIMATION_SPEED) ------------------------------
    out["ANIMATION_LINES"] = "\n".join(_animation_lines(variables, lang))

    # Lua's shadow.offset field expects an {x, y} table; convert the legacy
    # "0 4" form (only hyprland.lua.tmpl uses it, no effect in conf mode).
    offset_parts = (variables.get("SHADOW_OFFSET") or "0 4").split()
    out["SHADOW_OFFSET_LUA"] = "{ " + ", ".join(offset_parts or ["0", "0"]) + " }"

    # --- gestures -----------------------------------------------------------
    out["GESTURE_LINES"] = "\n".join(_gesture_lines(variables, lang))

    # --- user-defined environment variables ---------------------------------
    pairs = _split_pairs(variables.get("EXTRA_ENV", ""))
    if lang == "lua":
        out["EXTRA_ENV_LINES"] = "\n".join(
            f"hl.env({_lua_quote(name)}, {_lua_quote(value)})" for name, value in pairs)
    else:
        out["EXTRA_ENV_LINES"] = "\n".join(f"env = {name},{value}" for name, value in pairs)

    # --- updates module: Waybar wants seconds, the setting is minutes --------
    try:
        minutes = max(5, int(float(variables.get("UPDATES_INTERVAL") or 30)))
    except ValueError:
        minutes = 30
    out["UPDATES_INTERVAL_SEC"] = str(minutes * 60)

    # --- profile/user window rules ------------------------------------------
    out["WINDOWRULE_LINES"] = "\n".join(_windowrule_lines(variables, lang))

    # --- MOD+I settings panel (gui/quick.py → gui/app.py panel mode) ---------
    out.update(_quick_panel_vars(variables))

    # --- autostart ----------------------------------------------------------
    autostart_entries = _autostart_entries(variables, catalog, selected)
    if lang == "lua":
        out["AUTOSTART_LINES"] = "\n".join(_autostart_lua_lines(autostart_entries))
    else:
        out["AUTOSTART_LINES"] = "\n".join(_autostart_conf_lines(autostart_entries))

    # --- volume / brightness commands ---------------------------------------
    out.update(_media_command_vars(selected))

    # --- default applications (mimeapps.list / xdg-terminals.list) ---------
    out.update(_default_app_vars(variables, catalog, selected))

    # --- hyprpm plugins -----------------------------------------------------
    # hyprland.conf should only source plugins.conf when it was really
    # generated: sourcing a nonexistent file is a config error in Hyprland
    # (which is also why monitors.conf gets a placeholder).
    out["HAS_ANY_PLUGIN"] = "1" if (set(selected) & PLUGIN_COMPONENTS) else ""

    # --- primary tool commands ---------------------------------------------
    for var in ("TERMINAL", "LAUNCHER", "FILEMANAGER", "NOTIFIER", "BAR",
                "WALLPAPER_DAEMON"):
        comp = catalog.component(variables.get(var, ""))
        out[f"CMD_{var}"] = (comp.exec if comp else "") or variables.get(var, "")

    # User arguments are appended to the terminal (e.g. "-1" for kitty).
    terminal_args = (variables.get("TERMINAL_ARGS") or "").strip()
    if terminal_args and out.get("CMD_TERMINAL"):
        out["CMD_TERMINAL"] = f"{out['CMD_TERMINAL']} {terminal_args}"

    # Command invoking the launcher in "pick from a menu" (dmenu) mode:
    # keybindings like clipboard history use it. Since CMD_LAUNCHER already
    # contains a mode (e.g. "wofi --show drun"), --dmenu cannot be added to it.
    out["CMD_DMENU"] = _DMENU_CMDS.get(variables.get("LAUNCHER", ""),
                                       out.get("CMD_LAUNCHER", ""))
    out["DMENU_PROMPT_FLAG"] = _DMENU_PROMPT_FLAGS.get(
        variables.get("LAUNCHER", ""), "")
    # The dock's trailing button opens the selected launcher (dock.sh -c).
    out["DOCK_LAUNCHER_CMD"] = shlex.quote(out.get("CMD_LAUNCHER", ""))

    # The terminal's "run a command" argument depends on the emulator.
    out["TERMINAL_EXEC_FLAG"] = {
        "kitty": "-e", "alacritty": "-e", "foot": "-e", "ghostty": "-e",
    }.get(variables.get("TERMINAL", ""), "-e")

    # --- GTK / icon theme ---------------------------------------------------
    # If the user did not set it in settings.conf it follows COLOR_SCHEME
    # directly: Adwaita-dark if dark, otherwise Adwaita. The same rule applies
    # in the gsettings step in modules/theme.sh. The "gtk-theme" component
    # only installs nwg-look (and the Catppuccin GTK packages you may pick by
    # hand); the automatic choice does not depend on them.
    # IMPORTANT: the Adwaita/Adwaita-dark names only map to something real
    # thanks to the gnome-themes-extra package (always installed with
    # core/hyprland, see config/components.json) — without it Arch's gtk3
    # finds no real theme folder for either and silently falls back to GTK's
    # bare/unstyled (seemingly always LIGHT) default; native windows stay white
    # even with COLOR_SCHEME and prefer-dark-theme set correctly.
    # SYSTEM_IS_LIGHT is also used in the gtk-3.0/gtk-4.0 settings.ini templates.
    light = variables.get("COLOR_SCHEME", "dark") == "light"
    out["SYSTEM_IS_LIGHT"] = "1" if light else ""
    out["GTK_THEME_NAME"] = variables.get("GTK_THEME_NAME") or (
        "Adwaita" if light else "Adwaita-dark")
    out["ICON_THEME_NAME"] = variables.get("ICON_THEME_NAME") or (
        ("Papirus-Light" if light else "Papirus-Dark") if "icon-theme" in selected
        else "Adwaita")

    # --- helper flags -------------------------------------------------------
    # waypaper and wallpaper.sh need to know which folder to scan.
    # The USER's WALLPAPER_DIR wins if set; this line used to override it
    # unconditionally, so the "rotation directory" setting (documented in
    # settings.conf) did nothing and rotation always scanned the wallpaper's
    # own folder. If empty, the old behavior: the directory part of
    # WALLPAPER_PATH (~ expansion is left to the tool).
    wallpaper_path = variables.get("WALLPAPER_PATH", "") or "~/Pictures/wallpapers/wallpaper.png"
    out["WALLPAPER_DIR"] = (variables.get("WALLPAPER_DIR", "").strip()
                            or str(Path(wallpaper_path).parent)
                            or "~/Pictures/wallpapers")

    # The ALT+Tab switcher's window rule. SWITCHER_ANIM is turned into a rule
    # here because "no animation" and "this animation" are TWO SEPARATE fields
    # in Hyprland: "no_anim on" disables, "animation <style>" picks. Passing
    # the raw value to the template and writing if/else there invited rules
    # like "animation none" that silently do nothing (see windowrules.conf.tmpl).
    anim = (variables.get("SWITCHER_ANIM") or "none").strip()
    out["SWITCHER_ANIM_RULE"] = ("no_anim on" if anim in FALSY or anim == "none"
                                 else f"animation {anim}")
    out["SWITCHER_ANIM_LUA"] = ("no_anim = true" if anim in FALSY or anim == "none"
                                else f'animation = "{anim}"')

    out["SCREENSHOT_CMD"] = _screenshot_cmd(selected)
    out["LOCK_CMD"] = "hyprlock" if "hyprlock" in selected else "loginctl lock-session"
    out["LOGOUT_CMD"] = "wlogout" if "wlogout" in selected else "hyprctl dispatch exit"

    # Power menu: wlogout if present, otherwise the generated powermenu.sh
    # (pick via the launcher + confirm). If the Hypr config is not managed the
    # script is not generated, so it falls back to the plain exit command.
    if "wlogout" in selected:
        out["POWERMENU_CMD"] = "wlogout"
    elif truthy(variables.get("MANAGE_HYPR_CONFIGS", "1")):
        out["POWERMENU_CMD"] = "~/.config/hypr/scripts/powermenu.sh"
    else:
        out["POWERMENU_CMD"] = out["LOGOUT_CMD"]

    # Commands of mix parts (mix.py → MIX_OVERRIDE_<variable>): the user's key
    # runs the part's command — e.g. tapping SUPER opens another rice's
    # launcher. The keys do not change, only the command.
    for key, value in variables.items():
        if key.startswith("MIX_OVERRIDE_") and value:
            out[key[len("MIX_OVERRIDE_"):]] = value

    # --- keybindings --------------------------------------------------------
    # Keybinding lines are generated from config/keybinds.json; they need
    # values like CMD_* and SCREENSHOT_CMD, so they are computed last.
    if keybinds is not None:
        resolved = keybinds_mod.resolve(keybinds, out,
                                        variables.get("KEYBINDS", ""))
        out["KEYBIND_LINES"] = keybinds_mod.to_lines(resolved, lang=lang, mod_key=mod)
    else:
        out["KEYBIND_LINES"] = ""
    return out


# -------------------------------------------------------------- status bar -
# Available Waybar modules: id → (label, required component)
# If the component name is empty the module is always available.
BAR_MODULES: dict[str, tuple[str, str]] = {
    "hyprland/workspaces": ("Workspaces", ""),
    "hyprland/submap": ("Submap indicator", ""),
    "hyprland/window": ("Window title", ""),
    "cpu": ("CPU", ""),
    "memory": ("Memory", ""),
    "temperature": ("Temperature", ""),
    "disk": ("Disk", ""),
    "backlight": ("Brightness", "brightness"),
    "pulseaudio": ("Volume", ""),
    "bluetooth": ("Bluetooth", "bluetooth"),
    "network": ("Network", "networkmanager"),
    "battery": ("Battery", ""),
    "idle_inhibitor": ("Idle inhibitor", ""),
    "tray": ("System tray", ""),
    "clock": ("Clock", ""),
    "custom/power": ("Power button", ""),
    "custom/cava": ("Audio visualizer (Waybar)", "cava"),
    "mpris": ("Now playing", ""),
    # Detailed player + buttons; hidden when there is no player. All four
    # target the same player (hypr/scripts/media.sh).
    "custom/media": ("Player (title · artist · time)", ""),
    "custom/media-prev": ("Player: previous", ""),
    "custom/media-play": ("Player: play/pause", ""),
    "custom/media-next": ("Player: next", ""),
    "custom/shazam": ("Recognize song (Shazam · songrec)", ""),
    "custom/gamemode": ("Game mode indicator (visible when on)", ""),
    "custom/notifications": ("Notifications (history + do not disturb)", ""),
    "custom/updates": ("Pending updates (pacman + AUR)", ""),
    # Waybar modules drawn by our own scripts: they have no counterpart in
    # Waybar's built-in module list; each reads the JSON output of a script
    # under hypr/scripts (see templates/hypr/scripts/*.sh.tmpl). HyprPanel's
    # own "weather" module is separate and listed below.
    "custom/weather": ("Weather (Waybar)", ""),
    "custom/powerprofile": ("Power profile", "power"),
    "custom/privacy": ("Privacy indicator", "pipewire"),
    "custom/mic": ("Microphone (status + click: mute/unmute)", "pipewire"),
    "custom/record": ("Recording indicator (screen recording / instant replay)", "instant-replay"),
    # The user's own command — generated if BAR_CUSTOM<N>_CMD is set
    # (see _bar_custom_vars).
    "custom/user1": ("Custom module 1", ""),
    "custom/user2": ("Custom module 2", ""),
    "custom/user3": ("Custom module 3", ""),
    # Not real modules; fake "custom" modules used only by the bracket bar
    # preset to wrap each zone in static "[" / "]" text. Since GTK CSS does
    # not support ::before/::after content generation (see the comments in
    # render.py:_bar_vars), square brackets can only be added as real
    # characters this way.
    "custom/bracket-open": ("Bracket: [", ""),
    "custom/bracket-close": ("Bracket: ]", ""),
    # HyprPanel-specific modules — no Waybar counterpart, so they never enter
    # the Waybar module list (even though they are in BAR_MODULES they have
    # no definitions in config.jsonc.tmpl; render_export_vars/_bar_vars only
    # write tokens recognized there to the JSON, so an undefined module name
    # never reaches Waybar — see templates/waybar/config.jsonc.tmpl).
    # The accent color mapping (_HYPRPANEL_MODULE_ACCENT) already existed for
    # them, only the module list was missing.
    "dashboard": ("Dashboard button", ""),
    "notifications": ("Notification center", ""),
    "weather": ("Weather", ""),
    "cava": ("Audio visualizer", ""),
    "kbLayout": ("Keyboard layout indicator", ""),
    "netstat": ("Network speed (up/down)", "networkmanager"),
    "microphone": ("Microphone", ""),
    "updates": ("Pending updates", ""),
    "hyprsunset": ("Night light button", ""),
    "worldclock": ("World clock", ""),
}

#: HyprPanel-specific modules (only the BAR_MODULES tokens above) — hidden
#: in _page_bar's module list when BAR is not hyprpanel, so Waybar users are
#: not confused by an option with no counterpart.
HYPRPANEL_ONLY_MODULES = frozenset({
    "dashboard", "notifications", "weather", "cava", "kbLayout", "netstat",
    "microphone", "updates", "hyprsunset", "worldclock",
})

BAR_ZONES = ("LEFT", "CENTER", "RIGHT")

#: Workspace indicator styles. The template gets a BAR_WS_<NAME> flag for
#: each; the name is upper-cased with dashes turned into underscores
#: (pill-expand → BAR_WS_PILL_EXPAND).
BAR_WS_STYLES = (
    "numbers", "roman", "dots", "pill-expand", "underline",
    "bracket", "occupied-only", "app-icons", "id-icons", "named",
)

#: Bar presets with their own QML block in the Quickshell template. Every
#: other preset (and every case with Waybar/HyprPanel/Wayle selected) gets
#: the default background via BAR_QS_PLAIN.
QS_BAR_STYLES = ("caelestia", "illogical-impulse")

#: On a vertical bar Waybar wants "width" instead of "height".
BAR_VERTICAL = ("left", "right")

#: Bar presets (presets/bar/*.conf). The template gets a BAR_IS_<NAME> flag for
#: each; only the ones needing structurally different CSS are listed here
#: — the rest (slim, media, stats-only, taskbar, dock) already come out right
#: with the existing BAR_* sizes and need no extra CSS. "sharp" and "telemetry"
#: are listed too: their descriptions ("thick top border/all-caps typography"
#: and "small type" respectively) were not covered by the BAR_* sizes, leaving
#: one real difference each — see the chat history (the "single-feature bar
#: presets" complaint).
BAR_STYLES = ("islands", "pill-single", "bracket", "corner-tray", "minimal",
              "rail", "sharp", "telemetry", "glass", "outline",
              # Presets derived from real rices (docs/preset-sources.md).
              # Each has its own block in style.css.tmpl: sizes come from the
              # preset file, the SHAPE (capsule/bare text/separator line/edge
              # marker) from there. Without the flag a preset differs only in
              # its numbers and "doesn't look like the source".
              "jakoolit-simple-l", "hyde-wallbash", "ml4w-glass",
              "cyberarch-hud", "gruvbox-solid",
              "catppuccin-pills", "sameemul-islands", "eclipse-sidebar",
              "gdots-rail", "colorshell-dock", "rainz-nebula",
              "binnewbs-compact",
              # Script Test: our own profiles' bars (st-*).
              "st-yaprak", "st-gunbatimi", "st-kizil", "st-gecegolu",
              # Script Test third party (temaornek/ adaptations); CSS blocks
              # at the very end of style.css.tmpl.
              "st-sepya", "st-metro", "st-manga", "st-lavanta", "st-nane",
              "st-ay", "st-siyah", "st-limon", "st-alacakaranlik",
              "st-galaksi", "st-zirve", "st-karadelik", "st-nerv",
              "st-kurbaga", "st-doom", "st-mando",
              # Personal: attached top strip + detailed player (end of
              # style.css.tmpl).
              "st-kule", "st-gozcu",
              # Quickshell presets: they have their own blocks on the QML side
              # (templates/quickshell/shell.qml.tmpl).
              "caelestia", "illogical-impulse")

#: Fallback layout used when no module list arrives at all.
#:
#: settings.py has NO default for BAR_MODULES_*; in a normal install the
#: values come from lib/config.sh:config_defaults. But templates can also be
#: rendered directly (``python3 -m hyprsetup render``, tools/build-dotfiles.sh)
#: and bash never runs on that path: all three zones stay empty, the generated
#: config means "draw no modules" and the bar comes out empty.
#:
#: The values are EXACTLY the same as lib/config.sh:202-204 — keeping two
#: different defaults would mean the same selection produces a different bar
#: depending on the path taken. Update this when changing that.
BAR_FALLBACK_MODULES = {
    "LEFT": "hyprland/workspaces,hyprland/submap",
    "CENTER": "hyprland/window",
    "RIGHT": ("cpu,memory,backlight,pulseaudio,bluetooth,network,battery,"
              "tray,clock,custom/mic,custom/power"),
}


def _bar_module_defaults(variables: dict[str, str]) -> dict[str, str]:
    """Puts the default layout into BAR_MODULES_* if all three zones are empty.

    Only kicks in when *all* are empty: if the user deliberately defined a
    single-zone bar (e.g. only CENTER) it is left alone.
    """
    if any((variables.get(f"BAR_MODULES_{zone}") or "").strip()
           for zone in BAR_ZONES):
        return variables
    filled = dict(variables)
    for zone in BAR_ZONES:
        filled[f"BAR_MODULES_{zone}"] = BAR_FALLBACK_MODULES[zone]
    return filled


#: User-defined module slots — the N of the BAR_CUSTOM<N>_* keys.
BAR_CUSTOM_SLOTS = (1, 2, 3)


def _bar_custom_vars(variables: dict[str, str]) -> dict[str, str]:
    """Turns the BAR_CUSTOM<N>_* settings into JSON fragments Waybar understands.

    A slot with an empty command is NOT GENERATED: no definition is written
    and it is dropped from the module list (see _bar_vars). Values are escaped
    with json.dumps — the command may freely contain quotes, backslashes and
    braces (a command like ``awk '{print $4}'`` written raw into the template
    would break the JSON).
    """
    out: dict[str, str] = {}
    for slot in BAR_CUSTOM_SLOTS:
        cmd = (variables.get(f"BAR_CUSTOM{slot}_CMD") or "").strip()
        out[f"BAR_CUSTOM{slot}_ON"] = "1" if cmd else ""
        if not cmd:
            # The template will skip them via {{#if}}; still define them so
            # the --strict check does not flag them as "undefined variable".
            out[f"BAR_CUSTOM{slot}_CMD_JSON"] = '""'
            out[f"BAR_CUSTOM{slot}_FORMAT_JSON"] = '"{}"'
            out[f"BAR_CUSTOM{slot}_INTERVAL_VALUE"] = "60"
            out[f"BAR_CUSTOM{slot}_CLICK_JSON"] = '""'
            out[f"BAR_CUSTOM{slot}_HAS_CLICK"] = ""
            continue
        # An empty format means "{}": the command's output is shown as is.
        # The default is empty in the SCHEMA too because of bash: writing
        # `: "${X:={}}"` in lib/config.sh ends the parameter expansion at the
        # first `}` and the variable gets `{` (see the generated vars file).
        fmt = (variables.get(f"BAR_CUSTOM{slot}_FORMAT") or "").strip() or "{}"
        click = (variables.get(f"BAR_CUSTOM{slot}_CLICK") or "").strip()
        out[f"BAR_CUSTOM{slot}_CMD_JSON"] = json.dumps(cmd, ensure_ascii=False)
        out[f"BAR_CUSTOM{slot}_FORMAT_JSON"] = json.dumps(fmt, ensure_ascii=False)
        out[f"BAR_CUSTOM{slot}_INTERVAL_VALUE"] = str(
            max(1, _int(variables.get(f"BAR_CUSTOM{slot}_INTERVAL", ""), 60)))
        out[f"BAR_CUSTOM{slot}_CLICK_JSON"] = json.dumps(click, ensure_ascii=False)
        out[f"BAR_CUSTOM{slot}_HAS_CLICK"] = "1" if click else ""
    return out


#: The weather script's unit flag — wttr.in "m" (metric) / "u" (US).
_WEATHER_UNIT_FLAG = {"metric": "m", "imperial": "u"}


def _bar_module_extra_vars(variables: dict[str, str]) -> dict[str, str]:
    """Variables of modules drawn by our own scripts (weather…)."""
    unit = (variables.get("WEATHER_UNIT") or "metric").strip().lower()
    if unit not in _WEATHER_UNIT_FLAG:
        unit = "metric"
    return {
        # The script does not hit wttr.in more often than this (see weather.sh).
        "WEATHER_CACHE_MINUTES": str(max(5, min(180, _int(variables.get("WEATHER_REFRESH"), 15)))),
        "WEATHER_UNIT_FLAG": _WEATHER_UNIT_FLAG[unit],
        "WEATHER_UNIT_SYMBOL": "°C" if unit == "metric" else "°F",
        # An empty location means "guess from IP" in wttr.in; the script puts
        # it into the URL as is.
        "WEATHER_LOCATION_VALUE": (variables.get("WEATHER_LOCATION") or "").strip(),
    }


def _bar_vars(variables: dict[str, str], selected: list[str]) -> dict[str, str]:
    """Generates the Waybar module lists as JSON arrays.

    Building the module lists with conditional lines in the template risked a
    trailing-comma error in the JSON; here the full list is built and handed
    to the template as ready JSON. Modules depending on an unselected
    component are dropped.
    """
    # The bar preset — must be known before building the module lists: in the
    # "bracket" preset every zone is wrapped in real "[" / "]" characters
    # (since GTK CSS does not support ::before/::after content, the only way
    # is adding these fake custom modules to the module array — see BAR_MODULES).
    bar_style_early = (variables.get("BAR_PRESET") or "").strip()

    out: dict[str, str] = {}
    for zone in BAR_ZONES:
        raw = variables.get(f"BAR_MODULES_{zone}", "")
        modules = []
        for name in (m.strip() for m in raw.split(",")):
            if not name or name not in BAR_MODULES or name in HYPRPANEL_ONLY_MODULES:
                continue
            requires = BAR_MODULES[name][1]
            if requires and requires not in selected:
                continue
            # A custom slot with no command is not written to the bar: Waybar
            # silently skips an undefined module name, but the user would see an empty box.
            if name.startswith("custom/user"):
                slot = name[len("custom/user"):]
                if not (variables.get(f"BAR_CUSTOM{slot}_CMD") or "").strip():
                    continue
            modules.append(name)
        if bar_style_early == "bracket" and modules:
            modules = ["custom/bracket-open", *modules, "custom/bracket-close"]
        out[f"BAR_JSON_{zone}"] = json.dumps(modules, ensure_ascii=False)

    # Workspace indicator format → {{#if}} flags in the template
    style = (variables.get("BAR_WORKSPACE_STYLE") or "numbers").strip()
    if style not in BAR_WS_STYLES:
        style = "numbers"
    for candidate in BAR_WS_STYLES:
        flag = candidate.upper().replace("-", "_")
        out[f"BAR_WS_{flag}"] = "1" if candidate == style else ""

    # The outer "format" field of hyprland/workspaces — depends on the style.
    # IMPORTANT: Waybar uses format-icons values as literal text and does NOT
    # EXPAND field names like "{id}" inside them (verified with real Waybar —
    # "default": "{id}" showed the literal text "{id}" on the button, not the
    # number). So styles showing a number use "format": "{id}" directly
    # instead of format-icons; format-icons stays only for styles that assign
    # real custom icons/labels (dots/roman/named).
    if style == "app-icons":
        out["BAR_WS_FORMAT"] = "{windows}"
    elif style == "id-icons":
        # Number + the icons of the windows on that workspace ("1  ").
        out["BAR_WS_FORMAT"] = "{id}  {windows}"
    elif style in ("dots", "roman", "named"):
        out["BAR_WS_FORMAT"] = "{icon}"
    else:
        out["BAR_WS_FORMAT"] = "{id}"

    # named: 1-5 get custom labels; beyond that cannot be covered with
    # "default" in format-icons (note above) — so the real number is generated
    # for every possible workspace (leaving headroom above WORKSPACE_COUNT).
    try:
        ws_count = int(variables.get("WORKSPACE_COUNT") or 10)
    except ValueError:
        ws_count = 10
    named_extra = {str(n): str(n) for n in range(6, max(ws_count, 10) + 1)}
    out["BAR_WS_NAMED_EXTRA_JSON"] = ", ".join(f'"{k}": "{v}"' for k, v in named_extra.items())

    out["BAR_WS_PERSISTENT_JSON"] = _persistent_workspaces_json(variables, ws_count)

    # Bar preset → {{#if}} flags in style.css
    bar_style = bar_style_early
    for candidate in BAR_STYLES:
        flag = candidate.upper().replace("-", "_")
        out[f"BAR_IS_{flag}"] = "1" if candidate == bar_style else ""

    # The Quickshell template has three cases (caelestia / illogical-impulse /
    # others) but the template engine has no {{else}}: "others" needs its own
    # flag, otherwise the two special presets draw OVER the default background.
    out["BAR_QS_PLAIN"] = ("" if bar_style in QS_BAR_STYLES else "1")

    # The "dock" preset wants a second, thin bottom taskbar (an icon row of
    # open windows) — it cannot be expressed with a single Waybar bar object,
    # the config root has to be an ARRAY (see templates/waybar/config.jsonc.tmpl).
    # Previously this was never generated: the top bar came out right but the
    # "bottom dock" was missing (see docs/gallery-catalog.md — 7 profiles using
    # a dock looked half done: ambxst-lava, nixos-lantern, hyper-olive,
    # warm-amber, tokyo-dock, cinnamon-night, nothing-mono).
    out["BAR_HAS_DOCK"] = "1" if bar_style == "dock" else ""

    # "rail-top" also wants a second bar, but on the LEFT rather than the
    # bottom: a thin top status bar + a vertical app icon strip on the left
    # edge. In 3 of the references' 5 vertical-rail examples (mando-sand,
    # alpine-light, abomination-forest) there was also a top bar next to the
    # rail; "rail" alone only produces the rail, and that top bar was lost.
    # The main (first) object is the top bar — ALL module DEFINITIONS live
    # there, the second array element only carries the module it uses.
    out["BAR_HAS_RAIL"] = "1" if bar_style == "rail-top" else ""

    # Whether the root JSON is an array or a single object: the shared flag of
    # two-bar presets. Tying the brackets to it avoids rewriting the bracket
    # logic in the template when a new two-bar preset is added.
    out["BAR_MULTI"] = "1" if bar_style in ("dock", "rail-top") else ""

    position = (variables.get("BAR_POSITION") or "top").strip()
    if position not in ("top", "bottom", *BAR_VERTICAL):
        position = "top"
    out["BAR_POSITION"] = position
    vertical = position in BAR_VERTICAL

    # On a vertical bar Waybar wants the width rather than the height; the
    # reverse when horizontal. Giving 0 for the unused size lets Waybar grow to its content.
    out["BAR_SIZE_KEY"] = "width" if vertical else "height"
    out["BAR_SIZE"] = (variables.get("BAR_WIDTH", "44") if vertical
                       else variables.get("BAR_HEIGHT", "38"))

    # On a vertical bar BAR_SIZE ("width") is only a LOWER BOUND: Waybar grows
    # to the widest module. Icon+word formats like "󰈀 connected" / "󰝟 off" take
    # ~50-57px at 11pt; even with BAR_WIDTH=44 the rail came out that thick
    # (measured: Pango, Noto Sans 11pt + rail padding). This flag is used in
    # config.jsonc.tmpl to replace text formats with icon/two-line formats,
    # and in style.css.tmpl to narrow the horizontal padding.
    out["BAR_IS_VERTICAL"] = "1" if vertical else ""

    # pill-single: a single capsule "centered and narrower than the screen".
    # This used to be done in CSS by giving window#waybar "margin: Npx 12%";
    # GTK CSS does not accept percentages ("Junk at end of value for margin"),
    # the rule was dropped entirely and the capsule came out full width. With
    # a fixed horizontal "width" given to Waybar the layer-shell surface does
    # not stick to the edges and is centered (tested live). 1200px also fits
    # 1366px laptop screens.
    out["BAR_FIXED_WIDTH"] = ("1200" if variables.get("BAR_PRESET", "").strip() == "pill-single"
                              and not vertical else "")

    # The margin is only applied on the edge the bar sits on.
    margin = variables.get("BAR_MARGIN", "6")
    for edge in ("TOP", "BOTTOM", "LEFT", "RIGHT"):
        out[f"BAR_MARGIN_{edge}"] = margin if position == edge.lower() else "0"

    # Auto-hide. Waybar's own "mode: hide" brings the bar back on edge hover
    # via Sway IPC, which has no Hyprland counterpart; so the bar is started
    # hidden (start_hidden) and its visibility toggled with SIGUSR1. The helper
    # that waits for the mouse at the edge and sends the signal is
    # hypr/scripts/bar-autohide.py (added to autostart when BAR_AUTOHIDE is
    # on, see _autostart_entries). Reserving space while hidden is pointless,
    # so exclusive is turned off too.
    out["BAR_AUTOHIDE_ON"] = "1" if truthy(variables.get("BAR_AUTOHIDE")) else ""
    out["BAR_EXCLUSIVE_JSON"] = "false" if out["BAR_AUTOHIDE_ON"] else "true"

    out.update(_bar_custom_vars(variables))
    out.update(_bar_module_extra_vars(variables))
    return out


# --------------------------------------------------------- HyprPanel bar ---
# Unlike Waybar, HyprPanel (BAR=hyprpanel) uses a single-level JSON config
# with "flat dot-paths" rather than nesting (e.g. {"bar.layouts": ...,
# "theme.bar.background": "#11111b"}). Source: upstream's own theme
# files — see https://github.com/Jas-SinghFSU/HyprPanel/tree/master/themes
# (also verified with ags-hyprpanel-git installed on this machine).

# Generic module token (the keys of the BAR_MODULES dict) → HyprPanel's own
# BarModule name. backlight has no HyprPanel counterpart and is not in the
# mapping — if it appears in the module list it is silently skipped.
_HYPRPANEL_MODULE_MAP: dict[str, str] = {
    "hyprland/workspaces": "workspaces",
    "hyprland/submap": "submap",
    "hyprland/window": "windowtitle",
    "cpu": "cpu",
    "memory": "ram",
    "temperature": "cputemp",
    "disk": "storage",
    "pulseaudio": "volume",
    "bluetooth": "bluetooth",
    "network": "network",
    "battery": "battery",
    "idle_inhibitor": "hypridle",
    "tray": "systray",
    "clock": "clock",
    "custom/power": "power",
    "mpris": "media",
    # HyprPanel-specific modules (see BAR_MODULES/HYPRPANEL_ONLY_MODULES) —
    # no Waybar counterpart; the name is the same, so mapped one-to-one here.
    "dashboard": "dashboard",
    "notifications": "notifications",
    "weather": "weather",
    "cava": "cava",
    "kbLayout": "kbLayout",
    "netstat": "netstat",
    "microphone": "microphone",
    "updates": "updates",
    "hyprsunset": "hyprsunset",
    "worldclock": "worldclock",
}

# HyprPanel only supports "top"/"bottom" bar positions (unlike Waybar there is
# no vertical left/right bar) — see src/lib/options/types.ts BarLocation.
_HYPRPANEL_VERTICAL_FALLBACK = "top"

#: Module segment → theme accent color bucket. An accent-needing key
#: (icon/active/border etc.) of an unmapped module falls back to the general ACCENT.
_HYPRPANEL_MODULE_ACCENT: dict[str, str] = {
    "power": "RED", "cpu": "RED",
    "battery": "YELLOW", "volume": "YELLOW", "ram": "YELLOW", "hyprsunset": "YELLOW",
    "storage": "ACCENT2", "updates": "ACCENT2", "network": "ACCENT2",
    "netstat": "GREEN", "microphone": "GREEN",
    "bluetooth": "CYAN", "cava": "CYAN", "kbLayout": "CYAN", "submap": "CYAN",
    "weather": "ACCENT", "dashboard": "ACCENT", "clock": "ACCENT",
    "media": "ACCENT", "notifications": "ACCENT", "windowtitle": "ACCENT",
    "systray": "ACCENT", "hypridle": "ACCENT", "worldclock": "ACCENT",
    "workspaces": "ACCENT",
}

#: Leaf key names that carry an "accent" meaning — leaves outside these
#: (background/text/border/disabled etc.) are considered structural.
_HYPRPANEL_ACCENT_LEAVES = (
    "icon", "icon_background", "active", "enabled", "primary", "hover",
    "occupied", "available", "customicon",
)
_HYPRPANEL_ACCENT_LEAF2 = (
    "scroller.color", "listitems.active", "icons.active", "iconbuttons.active",
    "iconbutton.active", "switch.enabled",
)

# ALL color keys in upstream's themes/*.json files (the one exception,
# "theme.bar.buttons.style", is not here because it is a style name like
# "default", not a color — we never touch that key).
_HYPRPANEL_THEME_KEYS: tuple[str, ...] = (
    "theme.bar.background",
    "theme.bar.border.color",
    "theme.bar.buttons.background",
    "theme.bar.buttons.battery.background",
    "theme.bar.buttons.battery.border",
    "theme.bar.buttons.battery.icon",
    "theme.bar.buttons.battery.icon_background",
    "theme.bar.buttons.battery.text",
    "theme.bar.buttons.bluetooth.background",
    "theme.bar.buttons.bluetooth.border",
    "theme.bar.buttons.bluetooth.icon",
    "theme.bar.buttons.bluetooth.icon_background",
    "theme.bar.buttons.bluetooth.text",
    "theme.bar.buttons.borderColor",
    "theme.bar.buttons.clock.background",
    "theme.bar.buttons.clock.border",
    "theme.bar.buttons.clock.icon",
    "theme.bar.buttons.clock.icon_background",
    "theme.bar.buttons.clock.text",
    "theme.bar.buttons.dashboard.background",
    "theme.bar.buttons.dashboard.border",
    "theme.bar.buttons.dashboard.icon",
    "theme.bar.buttons.hover",
    "theme.bar.buttons.icon",
    "theme.bar.buttons.icon_background",
    "theme.bar.buttons.media.background",
    "theme.bar.buttons.media.border",
    "theme.bar.buttons.media.icon",
    "theme.bar.buttons.media.icon_background",
    "theme.bar.buttons.media.text",
    "theme.bar.buttons.modules.cava.background",
    "theme.bar.buttons.modules.cava.border",
    "theme.bar.buttons.modules.cava.icon",
    "theme.bar.buttons.modules.cava.icon_background",
    "theme.bar.buttons.modules.cava.text",
    "theme.bar.buttons.modules.cpu.background",
    "theme.bar.buttons.modules.cpu.border",
    "theme.bar.buttons.modules.cpu.icon",
    "theme.bar.buttons.modules.cpu.icon_background",
    "theme.bar.buttons.modules.cpu.text",
    "theme.bar.buttons.modules.hypridle.background",
    "theme.bar.buttons.modules.hypridle.border",
    "theme.bar.buttons.modules.hypridle.icon",
    "theme.bar.buttons.modules.hypridle.icon_background",
    "theme.bar.buttons.modules.hypridle.text",
    "theme.bar.buttons.modules.hyprsunset.background",
    "theme.bar.buttons.modules.hyprsunset.border",
    "theme.bar.buttons.modules.hyprsunset.icon",
    "theme.bar.buttons.modules.hyprsunset.icon_background",
    "theme.bar.buttons.modules.hyprsunset.text",
    "theme.bar.buttons.modules.kbLayout.background",
    "theme.bar.buttons.modules.kbLayout.border",
    "theme.bar.buttons.modules.kbLayout.icon",
    "theme.bar.buttons.modules.kbLayout.icon_background",
    "theme.bar.buttons.modules.kbLayout.text",
    "theme.bar.buttons.modules.microphone.background",
    "theme.bar.buttons.modules.microphone.border",
    "theme.bar.buttons.modules.microphone.icon",
    "theme.bar.buttons.modules.microphone.icon_background",
    "theme.bar.buttons.modules.microphone.text",
    "theme.bar.buttons.modules.netstat.background",
    "theme.bar.buttons.modules.netstat.border",
    "theme.bar.buttons.modules.netstat.icon",
    "theme.bar.buttons.modules.netstat.icon_background",
    "theme.bar.buttons.modules.netstat.text",
    "theme.bar.buttons.modules.power.background",
    "theme.bar.buttons.modules.power.border",
    "theme.bar.buttons.modules.power.icon",
    "theme.bar.buttons.modules.power.icon_background",
    "theme.bar.buttons.modules.ram.background",
    "theme.bar.buttons.modules.ram.border",
    "theme.bar.buttons.modules.ram.icon",
    "theme.bar.buttons.modules.ram.icon_background",
    "theme.bar.buttons.modules.ram.text",
    "theme.bar.buttons.modules.storage.background",
    "theme.bar.buttons.modules.storage.border",
    "theme.bar.buttons.modules.storage.icon",
    "theme.bar.buttons.modules.storage.icon_background",
    "theme.bar.buttons.modules.storage.text",
    "theme.bar.buttons.modules.submap.background",
    "theme.bar.buttons.modules.submap.border",
    "theme.bar.buttons.modules.submap.icon",
    "theme.bar.buttons.modules.submap.icon_background",
    "theme.bar.buttons.modules.submap.text",
    "theme.bar.buttons.modules.updates.background",
    "theme.bar.buttons.modules.updates.border",
    "theme.bar.buttons.modules.updates.icon",
    "theme.bar.buttons.modules.updates.icon_background",
    "theme.bar.buttons.modules.updates.text",
    "theme.bar.buttons.modules.weather.background",
    "theme.bar.buttons.modules.weather.border",
    "theme.bar.buttons.modules.weather.icon",
    "theme.bar.buttons.modules.weather.icon_background",
    "theme.bar.buttons.modules.weather.text",
    "theme.bar.buttons.modules.worldclock.background",
    "theme.bar.buttons.modules.worldclock.border",
    "theme.bar.buttons.modules.worldclock.icon",
    "theme.bar.buttons.modules.worldclock.icon_background",
    "theme.bar.buttons.modules.worldclock.text",
    "theme.bar.buttons.network.background",
    "theme.bar.buttons.network.border",
    "theme.bar.buttons.network.icon",
    "theme.bar.buttons.network.icon_background",
    "theme.bar.buttons.network.text",
    "theme.bar.buttons.notifications.background",
    "theme.bar.buttons.notifications.border",
    "theme.bar.buttons.notifications.icon",
    "theme.bar.buttons.notifications.icon_background",
    "theme.bar.buttons.notifications.total",
    "theme.bar.buttons.systray.background",
    "theme.bar.buttons.systray.border",
    "theme.bar.buttons.systray.customIcon",
    "theme.bar.buttons.text",
    "theme.bar.buttons.volume.background",
    "theme.bar.buttons.volume.border",
    "theme.bar.buttons.volume.icon",
    "theme.bar.buttons.volume.icon_background",
    "theme.bar.buttons.volume.text",
    "theme.bar.buttons.windowtitle.background",
    "theme.bar.buttons.windowtitle.border",
    "theme.bar.buttons.windowtitle.icon",
    "theme.bar.buttons.windowtitle.icon_background",
    "theme.bar.buttons.windowtitle.text",
    "theme.bar.buttons.workspaces.active",
    "theme.bar.buttons.workspaces.available",
    "theme.bar.buttons.workspaces.background",
    "theme.bar.buttons.workspaces.border",
    "theme.bar.buttons.workspaces.hover",
    "theme.bar.buttons.workspaces.numbered_active_highlighted_text_color",
    "theme.bar.buttons.workspaces.numbered_active_underline_color",
    "theme.bar.buttons.workspaces.occupied",
    "theme.bar.menus.background",
    "theme.bar.menus.border.color",
    "theme.bar.menus.buttons.active",
    "theme.bar.menus.buttons.default",
    "theme.bar.menus.buttons.disabled",
    "theme.bar.menus.buttons.text",
    "theme.bar.menus.cards",
    "theme.bar.menus.check_radio_button.active",
    "theme.bar.menus.check_radio_button.background",
    "theme.bar.menus.dimtext",
    "theme.bar.menus.dropdownmenu.background",
    "theme.bar.menus.dropdownmenu.divider",
    "theme.bar.menus.dropdownmenu.text",
    "theme.bar.menus.feinttext",
    "theme.bar.menus.iconbuttons.active",
    "theme.bar.menus.iconbuttons.passive",
    "theme.bar.menus.icons.active",
    "theme.bar.menus.icons.passive",
    "theme.bar.menus.label",
    "theme.bar.menus.listitems.active",
    "theme.bar.menus.listitems.passive",
    "theme.bar.menus.menu.battery.background.color",
    "theme.bar.menus.menu.battery.border.color",
    "theme.bar.menus.menu.battery.card.color",
    "theme.bar.menus.menu.battery.icons.active",
    "theme.bar.menus.menu.battery.icons.passive",
    "theme.bar.menus.menu.battery.label.color",
    "theme.bar.menus.menu.battery.listitems.active",
    "theme.bar.menus.menu.battery.listitems.passive",
    "theme.bar.menus.menu.battery.slider.background",
    "theme.bar.menus.menu.battery.slider.backgroundhover",
    "theme.bar.menus.menu.battery.slider.primary",
    "theme.bar.menus.menu.battery.slider.puck",
    "theme.bar.menus.menu.battery.text",
    "theme.bar.menus.menu.bluetooth.background.color",
    "theme.bar.menus.menu.bluetooth.border.color",
    "theme.bar.menus.menu.bluetooth.card.color",
    "theme.bar.menus.menu.bluetooth.iconbutton.active",
    "theme.bar.menus.menu.bluetooth.iconbutton.passive",
    "theme.bar.menus.menu.bluetooth.icons.active",
    "theme.bar.menus.menu.bluetooth.icons.passive",
    "theme.bar.menus.menu.bluetooth.label.color",
    "theme.bar.menus.menu.bluetooth.listitems.active",
    "theme.bar.menus.menu.bluetooth.listitems.passive",
    "theme.bar.menus.menu.bluetooth.scroller.color",
    "theme.bar.menus.menu.bluetooth.status",
    "theme.bar.menus.menu.bluetooth.switch.disabled",
    "theme.bar.menus.menu.bluetooth.switch.enabled",
    "theme.bar.menus.menu.bluetooth.switch.puck",
    "theme.bar.menus.menu.bluetooth.switch_divider",
    "theme.bar.menus.menu.bluetooth.text",
    "theme.bar.menus.menu.clock.background.color",
    "theme.bar.menus.menu.clock.border.color",
    "theme.bar.menus.menu.clock.calendar.contextdays",
    "theme.bar.menus.menu.clock.calendar.currentday",
    "theme.bar.menus.menu.clock.calendar.days",
    "theme.bar.menus.menu.clock.calendar.paginator",
    "theme.bar.menus.menu.clock.calendar.weekdays",
    "theme.bar.menus.menu.clock.calendar.yearmonth",
    "theme.bar.menus.menu.clock.card.color",
    "theme.bar.menus.menu.clock.text",
    "theme.bar.menus.menu.clock.time.time",
    "theme.bar.menus.menu.clock.time.timeperiod",
    "theme.bar.menus.menu.clock.weather.hourly.icon",
    "theme.bar.menus.menu.clock.weather.hourly.temperature",
    "theme.bar.menus.menu.clock.weather.hourly.time",
    "theme.bar.menus.menu.clock.weather.icon",
    "theme.bar.menus.menu.clock.weather.stats",
    "theme.bar.menus.menu.clock.weather.status",
    "theme.bar.menus.menu.clock.weather.temperature",
    "theme.bar.menus.menu.clock.weather.thermometer.cold",
    "theme.bar.menus.menu.clock.weather.thermometer.extremelycold",
    "theme.bar.menus.menu.clock.weather.thermometer.extremelyhot",
    "theme.bar.menus.menu.clock.weather.thermometer.hot",
    "theme.bar.menus.menu.clock.weather.thermometer.moderate",
    "theme.bar.menus.menu.dashboard.background.color",
    "theme.bar.menus.menu.dashboard.border.color",
    "theme.bar.menus.menu.dashboard.card.color",
    "theme.bar.menus.menu.dashboard.controls.bluetooth.background",
    "theme.bar.menus.menu.dashboard.controls.bluetooth.text",
    "theme.bar.menus.menu.dashboard.controls.disabled",
    "theme.bar.menus.menu.dashboard.controls.input.background",
    "theme.bar.menus.menu.dashboard.controls.input.text",
    "theme.bar.menus.menu.dashboard.controls.notifications.background",
    "theme.bar.menus.menu.dashboard.controls.notifications.text",
    "theme.bar.menus.menu.dashboard.controls.volume.background",
    "theme.bar.menus.menu.dashboard.controls.volume.text",
    "theme.bar.menus.menu.dashboard.controls.wifi.background",
    "theme.bar.menus.menu.dashboard.controls.wifi.text",
    "theme.bar.menus.menu.dashboard.directories.left.bottom.color",
    "theme.bar.menus.menu.dashboard.directories.left.middle.color",
    "theme.bar.menus.menu.dashboard.directories.left.top.color",
    "theme.bar.menus.menu.dashboard.directories.right.bottom.color",
    "theme.bar.menus.menu.dashboard.directories.right.middle.color",
    "theme.bar.menus.menu.dashboard.directories.right.top.color",
    "theme.bar.menus.menu.dashboard.monitors.bar_background",
    "theme.bar.menus.menu.dashboard.monitors.cpu.bar",
    "theme.bar.menus.menu.dashboard.monitors.cpu.icon",
    "theme.bar.menus.menu.dashboard.monitors.cpu.label",
    "theme.bar.menus.menu.dashboard.monitors.disk.bar",
    "theme.bar.menus.menu.dashboard.monitors.disk.icon",
    "theme.bar.menus.menu.dashboard.monitors.disk.label",
    "theme.bar.menus.menu.dashboard.monitors.gpu.bar",
    "theme.bar.menus.menu.dashboard.monitors.gpu.icon",
    "theme.bar.menus.menu.dashboard.monitors.gpu.label",
    "theme.bar.menus.menu.dashboard.monitors.ram.bar",
    "theme.bar.menus.menu.dashboard.monitors.ram.icon",
    "theme.bar.menus.menu.dashboard.monitors.ram.label",
    "theme.bar.menus.menu.dashboard.powermenu.confirmation.background",
    "theme.bar.menus.menu.dashboard.powermenu.confirmation.body",
    "theme.bar.menus.menu.dashboard.powermenu.confirmation.border",
    "theme.bar.menus.menu.dashboard.powermenu.confirmation.button_text",
    "theme.bar.menus.menu.dashboard.powermenu.confirmation.card",
    "theme.bar.menus.menu.dashboard.powermenu.confirmation.confirm",
    "theme.bar.menus.menu.dashboard.powermenu.confirmation.deny",
    "theme.bar.menus.menu.dashboard.powermenu.confirmation.label",
    "theme.bar.menus.menu.dashboard.powermenu.logout",
    "theme.bar.menus.menu.dashboard.powermenu.restart",
    "theme.bar.menus.menu.dashboard.powermenu.shutdown",
    "theme.bar.menus.menu.dashboard.powermenu.sleep",
    "theme.bar.menus.menu.dashboard.profile.name",
    "theme.bar.menus.menu.dashboard.shortcuts.background",
    "theme.bar.menus.menu.dashboard.shortcuts.recording",
    "theme.bar.menus.menu.dashboard.shortcuts.text",
    "theme.bar.menus.menu.media.album",
    "theme.bar.menus.menu.media.artist",
    "theme.bar.menus.menu.media.background.color",
    "theme.bar.menus.menu.media.border.color",
    "theme.bar.menus.menu.media.buttons.background",
    "theme.bar.menus.menu.media.buttons.enabled",
    "theme.bar.menus.menu.media.buttons.inactive",
    "theme.bar.menus.menu.media.buttons.text",
    "theme.bar.menus.menu.media.card.color",
    "theme.bar.menus.menu.media.slider.background",
    "theme.bar.menus.menu.media.slider.backgroundhover",
    "theme.bar.menus.menu.media.slider.primary",
    "theme.bar.menus.menu.media.slider.puck",
    "theme.bar.menus.menu.media.song",
    "theme.bar.menus.menu.media.timestamp",
    "theme.bar.menus.menu.network.background.color",
    "theme.bar.menus.menu.network.border.color",
    "theme.bar.menus.menu.network.card.color",
    "theme.bar.menus.menu.network.iconbuttons.active",
    "theme.bar.menus.menu.network.iconbuttons.passive",
    "theme.bar.menus.menu.network.icons.active",
    "theme.bar.menus.menu.network.icons.passive",
    "theme.bar.menus.menu.network.label.color",
    "theme.bar.menus.menu.network.listitems.active",
    "theme.bar.menus.menu.network.listitems.passive",
    "theme.bar.menus.menu.network.scroller.color",
    "theme.bar.menus.menu.network.status.color",
    "theme.bar.menus.menu.network.switch.disabled",
    "theme.bar.menus.menu.network.switch.enabled",
    "theme.bar.menus.menu.network.switch.puck",
    "theme.bar.menus.menu.network.text",
    "theme.bar.menus.menu.notifications.background",
    "theme.bar.menus.menu.notifications.border",
    "theme.bar.menus.menu.notifications.card",
    "theme.bar.menus.menu.notifications.clear",
    "theme.bar.menus.menu.notifications.label",
    "theme.bar.menus.menu.notifications.no_notifications_label",
    "theme.bar.menus.menu.notifications.pager.background",
    "theme.bar.menus.menu.notifications.pager.button",
    "theme.bar.menus.menu.notifications.pager.label",
    "theme.bar.menus.menu.notifications.scrollbar.color",
    "theme.bar.menus.menu.notifications.switch.disabled",
    "theme.bar.menus.menu.notifications.switch.enabled",
    "theme.bar.menus.menu.notifications.switch.puck",
    "theme.bar.menus.menu.notifications.switch_divider",
    "theme.bar.menus.menu.power.background.color",
    "theme.bar.menus.menu.power.border.color",
    "theme.bar.menus.menu.power.buttons.logout.background",
    "theme.bar.menus.menu.power.buttons.logout.icon",
    "theme.bar.menus.menu.power.buttons.logout.icon_background",
    "theme.bar.menus.menu.power.buttons.logout.text",
    "theme.bar.menus.menu.power.buttons.restart.background",
    "theme.bar.menus.menu.power.buttons.restart.icon",
    "theme.bar.menus.menu.power.buttons.restart.icon_background",
    "theme.bar.menus.menu.power.buttons.restart.text",
    "theme.bar.menus.menu.power.buttons.shutdown.background",
    "theme.bar.menus.menu.power.buttons.shutdown.icon",
    "theme.bar.menus.menu.power.buttons.shutdown.icon_background",
    "theme.bar.menus.menu.power.buttons.shutdown.text",
    "theme.bar.menus.menu.power.buttons.sleep.background",
    "theme.bar.menus.menu.power.buttons.sleep.icon",
    "theme.bar.menus.menu.power.buttons.sleep.icon_background",
    "theme.bar.menus.menu.power.buttons.sleep.text",
    "theme.bar.menus.menu.systray.dropdownmenu.background",
    "theme.bar.menus.menu.systray.dropdownmenu.divider",
    "theme.bar.menus.menu.systray.dropdownmenu.text",
    "theme.bar.menus.menu.volume.audio_slider.background",
    "theme.bar.menus.menu.volume.audio_slider.backgroundhover",
    "theme.bar.menus.menu.volume.audio_slider.primary",
    "theme.bar.menus.menu.volume.audio_slider.puck",
    "theme.bar.menus.menu.volume.background.color",
    "theme.bar.menus.menu.volume.border.color",
    "theme.bar.menus.menu.volume.card.color",
    "theme.bar.menus.menu.volume.iconbutton.active",
    "theme.bar.menus.menu.volume.iconbutton.passive",
    "theme.bar.menus.menu.volume.icons.active",
    "theme.bar.menus.menu.volume.icons.passive",
    "theme.bar.menus.menu.volume.input_slider.background",
    "theme.bar.menus.menu.volume.input_slider.backgroundhover",
    "theme.bar.menus.menu.volume.input_slider.primary",
    "theme.bar.menus.menu.volume.input_slider.puck",
    "theme.bar.menus.menu.volume.label.color",
    "theme.bar.menus.menu.volume.listitems.active",
    "theme.bar.menus.menu.volume.listitems.passive",
    "theme.bar.menus.menu.volume.text",
    "theme.bar.menus.popover.background",
    "theme.bar.menus.popover.border",
    "theme.bar.menus.popover.text",
    "theme.bar.menus.progressbar.background",
    "theme.bar.menus.progressbar.foreground",
    "theme.bar.menus.slider.background",
    "theme.bar.menus.slider.backgroundhover",
    "theme.bar.menus.slider.primary",
    "theme.bar.menus.slider.puck",
    "theme.bar.menus.switch.disabled",
    "theme.bar.menus.switch.enabled",
    "theme.bar.menus.switch.puck",
    "theme.bar.menus.text",
    "theme.bar.menus.tooltip.background",
    "theme.bar.menus.tooltip.text",
    "theme.notification.actions.background",
    "theme.notification.actions.text",
    "theme.notification.background",
    "theme.notification.border",
    "theme.notification.close_button.background",
    "theme.notification.close_button.label",
    "theme.notification.label",
    "theme.notification.labelicon",
    "theme.notification.text",
    "theme.notification.time",
    "theme.osd.bar_color",
    "theme.osd.bar_container",
    "theme.osd.bar_empty_color",
    "theme.osd.bar_overflow_color",
    "theme.osd.icon",
    "theme.osd.icon_container",
    "theme.osd.label",
)


def _classify_hyprpanel_key(key: str) -> str:
    """Maps a HyprPanel theme key to one of the 11 semantic HEX_* color buckets."""
    segs = key.split(".")
    leaf = segs[-1]
    leaf2 = ".".join(segs[-2:])
    leaf_l = leaf.lower()

    # Tier 1 — structural rules (menu/card/text/broken/divider).
    if "card" in segs:
        return "SURFACE"
    if leaf == "background" or leaf2 == "background.color":
        return "SURFACE" if ("buttons" in segs and "modules" in segs) else "BG_DARK"
    if leaf in ("text", "label") and leaf2 != "label.color":
        return "FG"
    if leaf in ("disabled", "passive", "dimtext", "feinttext", "inactive"):
        return "SUBTEXT"
    if leaf in ("puck", "backgroundhover", "switch_divider", "divider"):
        return "SURFACE"
    if leaf_l in ("border", "bordercolor") or leaf2 == "border.color":
        if not ("buttons" in segs and "modules" in segs):
            return "SURFACE"
        # buttons.modules.X.border -> falls through to Tier 2 (module accent).
    if leaf == "bar_overflow_color":
        return "RED"
    if leaf in ("bar_color", "icon_container"):
        return "ACCENT"
    if leaf == "bar_empty_color":
        return "SURFACE"

    # Tier 2 — module accent (icon/active/border-of-module/etc.).
    is_accent_leaf = (leaf_l in _HYPRPANEL_ACCENT_LEAVES or leaf2 in _HYPRPANEL_ACCENT_LEAF2
                      or leaf.startswith("numbered_active"))
    if is_accent_leaf:
        for seg in reversed(segs):
            if seg in _HYPRPANEL_MODULE_ACCENT:
                return _HYPRPANEL_MODULE_ACCENT[seg]
        return "ACCENT"

    # Tier 3 — default.
    return "FG"


def _hyprpanel_workspace_opts(style: str) -> dict[str, object]:
    """BAR_WORKSPACE_STYLE → settings of HyprPanel's workspaces module.

    HyprPanel's workspace indicator is less varied than Waybar's (numbered or
    with icons, active indicator underline/highlight/color); styles with no
    exact counterpart (roman, named, pill-expand, bracket) fall back to the
    closest visual equivalent.
    """
    if style not in BAR_WS_STYLES:
        style = "numbers"
    opts: dict[str, object] = {
        "show_numbered": False,
        "showApplicationIcons": False,
        "showAllActive": True,
        "numbered_active_indicator": "underline",
    }
    if style == "numbers":
        opts["show_numbered"] = True
    elif style in ("app-icons", "id-icons"):
        opts["showApplicationIcons"] = True
    elif style == "occupied-only":
        opts["showAllActive"] = False
    elif style in ("pill-expand", "bracket"):
        opts["numbered_active_indicator"] = "highlight"
    elif style == "dots":
        opts["numbered_active_indicator"] = "color"
    return opts


def _hyprpanel_em(px_value: str, fallback_px: float) -> str:
    """Converts a BAR_* value in pixels to the em unit HyprPanel expects."""
    try:
        px = float(px_value)
    except (TypeError, ValueError):
        px = fallback_px
    return f"{px / 16:.2f}em"


#: For how many monitors bar.layouts keys are written when MONITOR_SPEC is
#: empty (auto-detection). The install usually happens before Hyprland is even
#: running, so the real monitor count cannot be read reliably at render time;
#: 3 covers the typical desktops (single screen, dual screen, laptop + two
#: external).
_HYPRPANEL_MIN_MONITORS = 3


# --------------------------------------------------------------- Wayle bar ---
# Wayle (BAR=wayle) reads TOML and puts modules into the left/center/right
# arrays inside [[bar.layout]]. Module names are taken verbatim from upstream's
# docs (https://wayle.app/config/ — the "Bar modules" table, 30 modules).
#
# Generic modules with no counterpart are not in the map and are silently skipped:
#   temperature → not a separate module in Wayle, part of the cpu module
#   updates     → no counterpart
#   custom/bracket-* → a Waybar CSS trick, meaningless in Wayle
_WAYLE_MODULE_MAP: dict[str, str] = {
    "hyprland/workspaces": "hyprland-workspaces",
    "hyprland/window": "window-title",
    "hyprland/submap": "keybind-mode",
    "cpu": "cpu",
    "memory": "ram",
    "disk": "storage",
    "backlight": "brightness",
    "pulseaudio": "volume",
    "bluetooth": "bluetooth",
    "network": "network",
    "battery": "battery",
    "idle_inhibitor": "idle-inhibit",
    "tray": "systray",
    "clock": "clock",
    "custom/power": "power",
    "custom/cava": "cava",
    "mpris": "media",
    "dashboard": "dashboard",
    "notifications": "notifications",
    "weather": "weather",
    "cava": "cava",
    "kbLayout": "keyboard-input",
    "netstat": "netstat",
    "microphone": "microphone",
    "hyprsunset": "hyprsunset",
    "worldclock": "world-clock",
}

#: ROUNDING (pixels) → Wayle's RoundingLevel enum. Wayle does not take the
#: corner radius in pixels, it uses a five-step scale.
def _wayle_rounding(px: float) -> str:
    if px <= 0:
        return "none"
    if px <= 6:
        return "sm"
    if px <= 12:
        return "md"
    if px <= 20:
        return "lg"
    return "full"


def _wayle_vars(colors: dict[str, str], selected: list[str]) -> dict[str, str]:
    """Generates the module arrays and sizes for Wayle's config.toml."""
    out: dict[str, str] = {}

    zone_key = {"LEFT": "LEFT", "CENTER": "CENTER", "RIGHT": "RIGHT"}
    for zone in BAR_ZONES:
        names: list[str] = []
        for name in (m.strip() for m in (colors.get(f"BAR_MODULES_{zone}") or "").split(",")):
            if not name or name not in BAR_MODULES:
                continue
            requires = BAR_MODULES[name][1]
            if requires and requires not in selected:
                continue
            mapped = _WAYLE_MODULE_MAP.get(name)
            if mapped and mapped not in names:
                names.append(mapped)
        out[f"WAYLE_LAYOUT_{zone_key[zone]}"] = json.dumps(names)

    position = (colors.get("BAR_POSITION") or "top").strip().lower()
    if position not in ("top", "bottom", "left", "right"):
        position = "top"
    out["WAYLE_LOCATION"] = position

    try:
        opacity = round(float(colors.get("BAR_OPACITY", "0.95")) * 100)
    except (TypeError, ValueError):
        opacity = 95
    out["WAYLE_OPACITY"] = str(max(0, min(100, opacity)))

    out["WAYLE_ROUNDING"] = _wayle_rounding(_num_or(colors.get("ROUNDING"), 10))

    # The spacing fields are proportional (upstream defaults 0.35 / 0.5), not
    # pixels. A scale taking 16px as 1.0 brings the project's pixel settings
    # to values close to the upstream defaults.
    def spacing(key: str, fallback: float) -> str:
        return f"{max(0.0, _num_or(colors.get(key), fallback) / 16.0):.2f}"

    out["WAYLE_INSET_EDGE"] = spacing("BAR_MARGIN", 6)
    out["WAYLE_PADDING"] = spacing("BAR_PADDING", 12)
    out["WAYLE_MODULE_GAP"] = spacing("BAR_SPACING", 8)
    return out


def _num_or(value: str | None, fallback: float) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return fallback


def _hyprpanel_vars(colors: dict[str, str], selected: list[str]) -> dict[str, str]:
    """Generates the single-file, flat-keyed config.json content for HyprPanel.

    `colors` is the `out` dict with themes.derive() and _bar_vars() already
    applied — derived values like BAR_POSITION/HEX_*/BAR_* are ready here.
    """
    cfg: dict[str, object] = {}

    # --- module list ---------------------------------------------------------
    layout: dict[str, list[str]] = {"left": [], "middle": [], "right": []}
    zone_key = {"LEFT": "left", "CENTER": "middle", "RIGHT": "right"}
    for zone in BAR_ZONES:
        raw = colors.get(f"BAR_MODULES_{zone}", "")
        for name in (m.strip() for m in raw.split(",")):
            if not name or name not in BAR_MODULES:
                continue
            requires = BAR_MODULES[name][1]
            if requires and requires not in selected:
                continue
            mapped = _HYPRPANEL_MODULE_MAP.get(name)
            if not mapped:
                continue
            layout[zone_key[zone]].append(mapped)

    # HyprPanel keys bar.layouts by monitor ID and only draws a bar on monitors
    # that have a key. A fixed {"0": ...} used to be written here: on a
    # two-screen setup no bar ever appeared on the second monitor (id 1) — if
    # the user mostly works on that screen the panel looks like it "never
    # opened".
    #
    # The same layout is written for every monitor. The count comes from
    # MONITOR_SPEC; if not given (auto-detection) _HYPRPANEL_MIN_MONITORS keys
    # are generated. A key for a nonexistent monitor is not used by HyprPanel
    # and is harmless — a missing key removes the bar entirely, so erring on
    # the side of too many is the right side.
    specs = [s for s in (colors.get("MONITOR_SPEC") or "").split(";") if s.strip()]
    count = max(len(specs), _HYPRPANEL_MIN_MONITORS)
    cfg["bar.layouts"] = {str(i): layout for i in range(count)}

    # --- position / gaps / opacity -------------------------------------------
    position = colors.get("BAR_POSITION", "top")
    rail_fallback = position not in ("top", "bottom")
    location = _HYPRPANEL_VERTICAL_FALLBACK if rail_fallback else position
    cfg["bar.location"] = location
    out_flags = {"HYPRPANEL_RAIL_FALLBACK": "1" if rail_fallback else ""}

    margin_em = _hyprpanel_em(colors.get("BAR_MARGIN", "6"), 6)
    cfg["bar.margin_top"] = margin_em if location == "top" else "0em"
    cfg["bar.margin_bottom"] = margin_em if location == "bottom" else "0em"
    cfg["bar.margin_sides"] = margin_em
    cfg["bar.border_radius"] = _hyprpanel_em(colors.get("BAR_RADIUS", "6"), 6)
    cfg["bar.outer_spacing"] = _hyprpanel_em(colors.get("BAR_SPACING", "8"), 8)

    try:
        opacity = round(float(colors.get("BAR_OPACITY", "0.95")) * 100)
    except (TypeError, ValueError):
        opacity = 95
    cfg["bar.opacity"] = max(0, min(100, opacity))
    cfg["bar.transparent"] = False
    # A bar preset with gaps (islands, dock, media…) only really floats in
    # HyprPanel when floating is on; with it off the bar is drawn stuck to the
    # edge even with a margin, and the preset looks different from its Waybar
    # counterpart.
    try:
        margin_px = float(colors.get("BAR_MARGIN", "6"))
    except (TypeError, ValueError):
        margin_px = 6.0
    cfg["bar.floating"] = margin_px > 0

    # --- workspace indicator -------------------------------------------------
    for key, value in _hyprpanel_workspace_opts(colors.get("BAR_WORKSPACE_STYLE", "numbers")).items():
        cfg[f"bar.workspaces.{key}"] = value

    # --- clock ---------------------------------------------------------------
    # HyprPanel's clock format also uses strftime, passed through directly.
    clock_format = colors.get("BAR_CLOCK_FORMAT") or "%a %b %d  %I:%M:%S %p"
    cfg["bar.clock.format"] = clock_format

    # --- font ------------------------------------------------------------------
    try:
        font_size = float(colors.get("FONT_SIZE", "11")) / 10
    except (TypeError, ValueError):
        font_size = 1.1
    cfg["theme.font.name"] = colors.get("FONT_FAMILY", "Sans")
    cfg["theme.font.size"] = f"{font_size:.2f}rem"

    # --- color theme: 11 semantic HEX_* → ~370 HyprPanel theme keys --------
    for key in _HYPRPANEL_THEME_KEYS:
        bucket = _classify_hyprpanel_key(key)
        cfg[key] = colors.get(f"HEX_{bucket}", colors.get("HEX_FG", "#cdd6f4"))
    cfg["theme.bar.background"] = colors.get("HEX_BG_DARK", colors.get("HEX_BG", "#11111b"))

    out = dict(out_flags)
    out["HYPRPANEL_CONFIG_JSON"] = json.dumps(cfg, ensure_ascii=False, indent=2)
    return out


# ============================================================= widgets ====
#
# ONE CATALOG. There used to be three separate lists (EWW_WIDGETS,
# QUICKSHELL_WIDGETS and position/size numbers hand-written into each
# template) and they disagreed: with 15 widgets under presets/widget/, eww
# knew only 6 of them. Someone turning on "Disk usage" in the UI with the
# default engine (eww) saw nothing and got no warning either.
#
# To add a new widget: (1) presets/widget/<id>.conf, (2) a WidgetSpec here,
# (3) the matching block in both templates (templates/eww/eww.yuck.tmpl and
# templates/quickshell/shell.qml.tmpl).
#
# The center positions (TC, BC) sit horizontally centered on the screen: the
# layer-shell surface is not anchored to the left/right edge and the
# compositor centers it horizontally. So no horizontal offset (x) can be
# applied there — both Hyprland and eww ignore the margin of an unanchored
# edge. Vertical center (left-center, right-center) deliberately does not
# exist: vertically centered surfaces cannot stack, two widgets one below the
# other would land on the same spot.
WIDGET_ZONES = ("TL", "TC", "TR", "BL", "BC", "BR")

#: Position → (vertical edge, horizontal edge). QML anchors and eww :anchor are
#: generated from this; "center" means not anchored to any edge on that axis.
WIDGET_ZONE_EDGES: dict[str, tuple[str, str]] = {
    "TL": ("top", "left"),
    "TC": ("top", "center"),
    "TR": ("top", "right"),
    "BL": ("bottom", "left"),
    "BC": ("bottom", "center"),
    "BR": ("bottom", "right"),
}

#: The positions' names in the UI.
WIDGET_ZONE_LABELS: dict[str, str] = {
    "TL": "Top left", "TC": "Top center", "TR": "Top right",
    "BL": "Bottom left", "BC": "Bottom center", "BR": "Bottom right",
}

#: Limit of the per-widget offset (px, in both directions).
WIDGET_OFFSET_LIMIT = 800


@dataclass(frozen=True)
class WidgetSpec:
    """zone: default corner · width/height: box size (multiplied by
    WIDGET_SCALE) · engines: engines that can really draw it · requires: component."""
    label: str
    zone: str
    width: int
    height: int
    engines: tuple[str, ...] = ("eww", "quickshell")
    requires: str = ""


WIDGET_CATALOG: dict[str, WidgetSpec] = {
    "clock":       WidgetSpec("Digital clock", "TR", 220, 90),
    "sysinfo":     WidgetSpec("System info", "TR", 220, 80),
    "battery":     WidgetSpec("Battery status", "TR", 220, 50),
    "calendar":    WidgetSpec("Calendar", "TL", 240, 220),
    "music":       WidgetSpec("Now playing", "TR", 260, 50,
                              requires="audio-tools"),
    "network":     WidgetSpec("Network status", "TR", 220, 50,
                              requires="networkmanager"),
    "volume":      WidgetSpec("Volume", "BR", 180, 50,
                              requires="audio-tools"),
    "brightness":  WidgetSpec("Screen brightness", "BR", 180, 50,
                              requires="brightness"),
    "uptime":      WidgetSpec("Uptime", "BL", 220, 50),
    "disk":        WidgetSpec("Disk usage", "BL", 180, 50),
    "temperature": WidgetSpec("Temperature", "BL", 180, 50),
    "worldclock":  WidgetSpec("World clock", "BL", 220, 90),
    "kblayout":    WidgetSpec("Keyboard layout", "BR", 140, 44),
    "fetch-mini":  WidgetSpec("System card", "BR", 220, 90),
    "workspace":   WidgetSpec("Workspace", "TL", 140, 64),
}

#: Backward-compatible names — read under these names from outside (GUI, tests).
EWW_WIDGETS: tuple[str, ...] = tuple(
    name for name, spec in WIDGET_CATALOG.items() if "eww" in spec.engines)
QUICKSHELL_WIDGETS: tuple[str, ...] = tuple(
    name for name, spec in WIDGET_CATALOG.items() if "quickshell" in spec.engines)
EWW_WIDGET_REQUIRES: dict[str, str] = {
    name: spec.requires for name, spec in WIDGET_CATALOG.items()
    if spec.requires and "eww" in spec.engines}
QUICKSHELL_WIDGET_REQUIRES: dict[str, str] = {
    name: spec.requires for name, spec in WIDGET_CATALOG.items()
    if spec.requires and "quickshell" in spec.engines}


def _split_widgets(value: str) -> list[str]:
    return [w.strip() for w in (value or "").split(",") if w.strip()]


def widget_flag(name: str) -> str:
    """How a widget id is spelled in the template flag (fetch-mini → FETCH_MINI)."""
    return name.upper().replace("-", "_")


def active_widgets(variables: dict[str, str], selected: list[str],
                   engine: str) -> list[str]:
    """Widgets the selected engine will ACTUALLY draw.

    Three filters: is it in the catalog, can the engine draw it, is its
    required component selected. All three are shown separately in the UI
    (see gui/app.py _page_widgets) — so the user does not have to guess why a
    widget they turned on is not showing.
    """
    out = []
    for name in _split_widgets(variables.get("WIDGETS", "")):
        spec = WIDGET_CATALOG.get(name)
        if spec is None or engine not in spec.engines:
            continue
        if spec.requires and spec.requires not in selected:
            continue
        out.append(name)
    return out


def widget_zone_map(variables: dict[str, str]) -> dict[str, list[str]]:
    """The user's WIDGET_ZONE_* lists (empty list if empty)."""
    return {zone: _split_widgets(variables.get(f"WIDGET_ZONE_{zone}", ""))
            for zone in WIDGET_ZONES}


def widget_offsets(variables: dict[str, str]) -> dict[str, tuple[int, int]]:
    """WIDGET_OFFSETS="clock:20:-10,calendar:0:40" → {ad: (x, y)}.

    x: EXTRA distance from the horizontal edge, y: extra distance from the
    vertical edge (px). A positive value moves the widget away from the edge,
    a negative one closer. Malformed or zero entries are skipped; the limit is
    ±WIDGET_OFFSET_LIMIT.
    """
    out: dict[str, tuple[int, int]] = {}
    for entry in _split_widgets(variables.get("WIDGET_OFFSETS", "")):
        parts = [p.strip() for p in entry.split(":")]
        if len(parts) != 3 or not parts[0]:
            continue
        try:
            x, y = (max(-WIDGET_OFFSET_LIMIT, min(int(v), WIDGET_OFFSET_LIMIT))
                    for v in parts[1:])
        except ValueError:
            continue
        if x or y:
            out[parts[0]] = (x, y)
    return out


def format_widget_offsets(offsets: dict[str, tuple[int, int]]) -> str:
    """The inverse of widget_offsets; zero offsets are not written."""
    return ",".join(f"{name}:{x}:{y}" for name, (x, y) in offsets.items()
                    if x or y)


def widget_zone_of(name: str, zones: dict[str, list[str]]) -> str:
    """The widget's corner: where the user put it in a list, otherwise the
    catalog default."""
    for zone in WIDGET_ZONES:
        if name in zones.get(zone, ()):
            return zone
    spec = WIDGET_CATALOG.get(name)
    return spec.zone if spec else "TR"


def widget_layout(variables: dict[str, str], selected: list[str],
                  engine: str) -> list[dict[str, object]]:
    """Places the active widgets into corners and computes each one's box.

    Positions used to be hand-written into the TEMPLATE (clock top:16,
    sysinfo top:120, battery top:220…) and only looked right in the "all on"
    combination: a user turning on a single widget found it floating in the
    middle of the screen, and with the bar at the top the top widget
    disappeared under the bar. Here the order comes from the real list: in
    each corner widgets start at the edge and stack one below the other, and
    the edge the bar occupies is subtracted up front.

    WIDGET_OFFSETS gives per-widget fine-tuning: the vertical offset (y) also
    pushes the NEXT widgets in the same stack — so when one is pushed down,
    the one below does not overlap it. The horizontal offset (x) only affects
    that widget and is not applied in the center positions (see the
    WIDGET_ZONES note).
    """
    scale = max(0.5, min(_num_or(variables.get("WIDGET_SCALE"), 1.0), 2.0))
    margin = max(0, _int(variables.get("WIDGET_MARGIN", ""), 16))
    gap = max(0, _int(variables.get("WIDGET_GAP", ""), 10))

    # Do not enter the edge the bar occupies. A hidden bar (BAR_AUTOHIDE)
    # reserves no space, so no margin is subtracted either.
    bar_edge = (variables.get("BAR_POSITION") or "top").strip()
    if truthy(variables.get("BAR_AUTOHIDE")):
        bar_depth = 0
    else:
        vertical_bar = bar_edge in BAR_VERTICAL
        size_key = "BAR_WIDTH" if vertical_bar else "BAR_HEIGHT"
        bar_depth = (_int(variables.get(size_key, ""), 44 if vertical_bar else 38)
                     + _int(variables.get("BAR_MARGIN", ""), 6))

    zones = widget_zone_map(variables)
    offsets = widget_offsets(variables)
    ordered: dict[str, list[str]] = {zone: [] for zone in WIDGET_ZONES}
    active = active_widgets(variables, selected, engine)
    # First the order the user gave, then the ones not written into any list.
    for zone in WIDGET_ZONES:
        for name in zones[zone]:
            if name in active and name not in ordered[zone]:
                ordered[zone].append(name)
    for name in active:
        zone = widget_zone_of(name, zones)
        if name not in ordered[zone]:
            ordered[zone].append(name)

    out: list[dict[str, object]] = []
    for zone in WIDGET_ZONES:
        v_edge, h_edge = WIDGET_ZONE_EDGES[zone]
        offset = margin + (bar_depth if bar_edge == v_edge else 0)
        side = margin + (bar_depth if bar_edge == h_edge else 0)
        if h_edge == "center":
            side = 0
        for name in ordered[zone]:
            spec = WIDGET_CATALOG[name]
            width = int(round(spec.width * scale))
            height = int(round(spec.height * scale))
            dx, dy = offsets.get(name, (0, 0))
            if h_edge == "center":
                dx = 0
            offset = max(0, offset + dy)
            out.append({"name": name, "zone": zone,
                        "v_edge": v_edge, "h_edge": h_edge,
                        "x": max(0, side + dx), "y": offset,
                        "dx": dx, "dy": dy,
                        "width": width, "height": height})
            offset += height + gap
    return out


def _widget_bg(colors: dict[str, str], opacity: float) -> tuple[str, str]:
    """The widget box's background: (QML "#AARRGGBB", CSS "rgba(r,g,b,a)").

    We put the opacity into the box's COLOR, not Rectangle.opacity: opacity
    also fades the children and the clock/text becomes unreadable.
    """
    raw = (colors.get("HEX_BG") or "#1e1e2e").lstrip("#")[:6] or "1e1e2e"
    try:
        red, green, blue = (int(raw[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        red, green, blue = 30, 30, 46
    alpha = max(0.0, min(opacity, 1.0))
    return (f"#{round(alpha * 255):02x}{raw}",
            f"rgba({red}, {green}, {blue}, {alpha:.2f})")


def _widget_vars(variables: dict[str, str], selected: list[str],
                 colors: dict[str, str], engine: str,
                 prefix: str) -> dict[str, str]:
    """An engine's template variables: flags + computed boxes.

    Flags are written for EVERY widget (empty too); the template engine
    treats an undefined variable as an error (see test.sh "undefined
    variable check").
    """
    out: dict[str, str] = {}
    placed = {item["name"]: item
              for item in widget_layout(variables, selected, engine)}
    # Only the SELECTED engine draws a widget. With the Quickshell bar
    # selected, shell.qml is always generated, so with eww as the engine the
    # widgets were drawn twice (eww + Quickshell). Shared variables (WG_*,
    # WIDGET_NAMES) are still computed; only the engine's own flag is off.
    drawn = engine in selected
    scale = max(0.5, min(_num_or(variables.get("WIDGET_SCALE"), 1.0), 2.0))

    for name, spec in WIDGET_CATALOG.items():
        flag = widget_flag(name)
        item = placed.get(name)
        out[f"{prefix}{flag}"] = "1" if item and drawn else ""
        v_edge, h_edge = WIDGET_ZONE_EDGES[spec.zone]
        box = item or {"v_edge": v_edge, "h_edge": h_edge, "x": 16, "y": 16,
                       "width": spec.width, "height": spec.height}
        out[f"WG_{flag}_TOP"] = "true" if box["v_edge"] == "top" else "false"
        out[f"WG_{flag}_BOTTOM"] = "true" if box["v_edge"] == "bottom" else "false"
        out[f"WG_{flag}_LEFT"] = "true" if box["h_edge"] == "left" else "false"
        out[f"WG_{flag}_RIGHT"] = "true" if box["h_edge"] == "right" else "false"
        out[f"WG_{flag}_V_EDGE"] = str(box["v_edge"])
        out[f"WG_{flag}_H_EDGE"] = str(box["h_edge"])
        out[f"WG_{flag}_X"] = str(box["x"])
        out[f"WG_{flag}_Y"] = str(box["y"])
        out[f"WG_{flag}_W"] = str(box["width"])
        out[f"WG_{flag}_H"] = str(box["height"])
        # eww :anchor wants a single string ("top right", "top center").
        out[f"WG_{flag}_ANCHOR"] = f'{box["v_edge"]} {box["h_edge"]}'

    # Layer: eww wants the ":stacking" short form, Quickshell a WlrLayer
    # constant. "bottom" = above the wallpaper, below windows; "top" = above
    # windows (to toggle with MOD+W).
    layer = (variables.get("WIDGET_LAYER") or "bottom").strip().lower()
    if layer not in ("bottom", "top"):
        layer = "bottom"
    out["WIDGET_STACKING_EWW"] = "bt" if layer == "bottom" else "fg"
    out["WIDGET_LAYER_QML"] = ("WlrLayer.Bottom" if layer == "bottom"
                               else "WlrLayer.Top")
    # Quickshell draws its widgets from the start; WIDGET_AUTOSTART=false
    # starts them hidden (shown with MOD+G → widgets.sh → IpcHandler).
    out["WIDGET_AUTOSTART_QML"] = ("true" if truthy(variables.get("WIDGET_AUTOSTART", "true"))
                                   else "false")
    # eww :monitor wants an INDEX or the monitor NAME eww sees.
    # CAUTION: the name here is NOT the Wayland connector ("DP-1") but the
    # monitor's model name ("MSI G2412F") — given a connector name eww never
    # opens the window and says "Failed to get monitor DP-1". So the default
    # and recommended value is the index.
    monitor = (variables.get("WIDGET_MONITOR") or "").strip()
    if not monitor:
        out["WIDGET_MONITOR_EWW"] = "0"
    elif monitor.isdigit():
        out["WIDGET_MONITOR_EWW"] = monitor
    else:
        out["WIDGET_MONITOR_EWW"] = f'"{monitor}"'

    # Window names hypr/scripts/widgets.sh opens and closes — in the order the
    # layout function returns, i.e. the widgets that are actually generated.
    out["WIDGET_NAMES"] = " ".join(placed)

    opacity = _clamp01(variables.get("WIDGET_OPACITY", ""), 0.85)
    qml_bg, css_bg = _widget_bg(colors, opacity)
    out["WIDGET_SCALE_VALUE"] = f"{scale:.2f}"
    out["WIDGET_OPACITY_VALUE"] = f"{opacity:.2f}"
    out["WIDGET_RADIUS_VALUE"] = str(max(0, _int(variables.get("WIDGET_RADIUS", ""), 12)))
    out["WIDGET_BG_QML"] = qml_bg
    out["WIDGET_BG_CSS"] = css_bg
    # Precomputed font sizes and padding for the eww/GTK side: SCSS has no
    # multiplication, these numbers are the counterpart of QML's Item.scale.
    out["WIDGET_FS_TITLE"] = str(max(8, round(28 * scale)))
    out["WIDGET_FS_BODY"] = str(max(7, round(15 * scale)))
    out["WIDGET_FS_SMALL"] = str(max(6, round(13 * scale)))
    out["WIDGET_PAD_V"] = str(max(2, round(10 * scale)))
    out["WIDGET_PAD_H"] = str(max(4, round(16 * scale)))
    # The text scale grows with the box scale; on the eww side SCSS font
    # sizes are multiplied by it (the QML side uses Item.scale).
    out["WIDGET_FONT_SCALE"] = f"{scale:.2f}"
    return out


def _eww_widget_vars(variables: dict[str, str], selected: list[str],
                     colors: dict[str, str]) -> dict[str, str]:
    return _widget_vars(variables, selected, colors, "eww", "HAS_WIDGET_")


def _quickshell_widget_vars(variables: dict[str, str], selected: list[str],
                            colors: dict[str, str]) -> dict[str, str]:
    return _widget_vars(variables, selected, colors, "quickshell",
                        "HAS_QS_WIDGET_")


# ------------------------------------------------------- quickshell bar -----
#: Modules with a QML counterpart in the Quickshell bar: waybar module name →
#: the short name in the template flag. A module name not here (e.g. "tray" —
#: writing an SNI client on the Quickshell side is a separate job) is silently
#: skipped; the same as is done for unrecognized modules in Waybar (see _bar_vars).
QS_BAR_MODULES: dict[str, str] = {
    "hyprland/workspaces": "WORKSPACES",
    "hyprland/window": "WINDOW",
    "clock": "CLOCK",
    "cpu": "CPU",
    "memory": "MEMORY",
    "battery": "BATTERY",
    "pulseaudio": "VOLUME",
    "network": "NETWORK",
}

#: The component a module depends on — if not selected the module is not drawn.
QS_BAR_MODULE_REQUIRES: dict[str, str] = {
    "network": "networkmanager",
}


def _quickshell_bar_vars(variables: dict[str, str], selected: list[str]) -> dict[str, str]:
    """Generates the bar's QML variables when ``BAR=quickshell-bar``.

    The module lists are really read: a ``QS_{L,C,R}_<NAME>`` flag is set for
    each zone (left/center/right) and the template only draws the ones set.
    So the ``BAR_MODULES_*`` contract of Waybar means the same in Quickshell.
    """
    out: dict[str, str] = {}
    is_qs = (variables.get("BAR") or "") == "quickshell-bar"
    out["QS_BAR"] = "1" if is_qs else ""

    # Flags must be set in every case (empty too): the template engine treats
    # an undefined variable as an error (see test.sh "undefined variable check").
    for zone_key, zone in (("L", "LEFT"), ("C", "CENTER"), ("R", "RIGHT")):
        names = [] if not is_qs else [
            m.strip() for m in (variables.get(f"BAR_MODULES_{zone}") or "").split(",")
        ]
        for module, flag in QS_BAR_MODULES.items():
            requires = QS_BAR_MODULE_REQUIRES.get(module)
            ok = (module in names) and (not requires or requires in selected)
            out[f"QS_{zone_key}_{flag}"] = "1" if ok else ""

    position = (variables.get("BAR_POSITION") or "top").strip()
    if position not in ("top", "bottom", *BAR_VERTICAL):
        position = "top"
    vertical = position in BAR_VERTICAL
    out["QS_BAR_VERTICAL"] = "1" if vertical else ""
    # In QML anchors want four separate bools; derived from the position. A
    # vertical bar also sticks to the top/bottom edges (full height), a
    # horizontal one to left/right.
    for edge in ("top", "bottom", "left", "right"):
        if vertical:
            on = edge in ("top", "bottom") or edge == position
        else:
            on = edge in ("left", "right") or edge == position
        out[f"QS_ANCHOR_{edge.upper()}"] = "true" if on else "false"

    size_key = "BAR_WIDTH" if vertical else "BAR_HEIGHT"
    try:
        out["QS_BAR_SIZE"] = str(int(float(variables.get(size_key) or (48 if vertical else 34))))
    except ValueError:
        out["QS_BAR_SIZE"] = "48" if vertical else "34"

    # Layout axis: on a vertical bar the zones become a Column, the edges turn
    # to top/bottom, and the cross axis (centering) is vertical when horizontal
    # and horizontal when vertical. These are passed to the template as plain
    # text — QML has no other way to use one item in both directions
    # (Row/Column are separate types).
    out["QS_ZONE"] = "Column" if vertical else "Row"
    out["QS_CROSS"] = "horizontalCenter" if vertical else "verticalCenter"
    out["QS_START"] = "top" if vertical else "left"
    out["QS_END"] = "bottom" if vertical else "right"
    # The long side of the workspace dot grows along the bar's direction.
    grow, fixed = "modelData.active ? 18 : 8", "8"
    out["QS_WS_WIDTH"] = fixed if vertical else grow
    out["QS_WS_HEIGHT"] = grow if vertical else fixed
    # The window title is capped to the rail width on a vertical rail so it
    # does not overflow the bar (the old 320px cap is kept when horizontal).
    out["QS_TEXT_MAX"] = out["QS_BAR_SIZE"] if vertical else "320"

    # Auto-hide: the bar slides off screen and comes back when the mouse
    # touches the edge. Unlike its Waybar counterpart no helper process is
    # needed here — the window itself sees the mouse. While hidden the window
    # stays only QS_BAR_PEEK pixels thick; exclusiveZone becomes 0 too,
    # otherwise the hidden bar keeps reserving space for windows and hiding
    # is pointless.
    autohide = truthy(variables.get("BAR_AUTOHIDE"))
    out["QS_BAR_AUTOHIDE"] = "1" if autohide else ""
    peek = "2"
    out["QS_BAR_PEEK"] = peek
    out["QS_BAR_EXCLUSIVE"] = "0" if autohide else out["QS_BAR_SIZE"]
    # The window's thickness: normally fixed, a mouse-dependent QML
    # expression with auto-hide. Built here to avoid writing four separate
    # {{#if}} combinations (horizontal/vertical × hides/does not) in the template.
    out["QS_BAR_SIZE_EXPR"] = (f"qsBar.revealed ? {out['QS_BAR_SIZE']} : {peek}"
                               if autohide else out["QS_BAR_SIZE"])
    return out


# Base animation definitions: (name, duration[ds], curve, style)
# Durations are divided by ANIMATION_SPEED — a larger value means faster animation.
ANIMATION_BASE: tuple[tuple[str, float, str, str], ...] = (
    ("windowsIn",   4, "easeOutQuint",  "popin 80%"),
    ("windowsOut",  3, "easeOutQuint",  "popin 80%"),
    ("windowsMove", 4, "easeOutQuint",  "slide"),
    ("fadeIn",      4, "easeOutQuint",  ""),
    ("fadeOut",     3, "easeOutQuint",  ""),
    ("border",      8, "easeOutQuint",  ""),
    ("workspaces",  5, "easeOutQuint",  "slide"),
    ("specialWorkspace", 5, "easeOutQuint", "slidevert"),
    ("layersIn",    4, "easeOutQuint",  "popin 90%"),
    ("layersOut",   3, "easeInOutCubic", "popin 90%"),
    ("fadeLayersIn",  3, "easeOutQuint", ""),
    ("fadeLayersOut", 3, "easeInOutCubic", ""),
)

#: The default preset's curves. (name, x1, y1, x2, y2)
#:
#: Control points are strings ON PURPOSE: "1.00" and "1" are the same to
#: Hyprland but look different in the generated file. Keeping strings makes
#: both the .conf and Lua output stay exactly as they were before this change
#: (no fake diff in the dotfiles/ tree).
_CURVES_DEFAULT = (
    ("easeOutQuint",   "0.23", "1.00", "0.32", "1.00"),
    ("easeInOutCubic", "0.65", "0.05", "0.36", "1.00"),
    ("linear",         "0",    "0",    "1",    "1"),
)

#: Animation character. ANIMATION_SPEED sits ON TOP of these as a multiplier:
#: the preset answers "how", ANIMATION_SPEED "how fast".
#:
#: "default" deliberately produces EXACTLY the same output as before — the
#: config of a user who never touched the setting must not shift with this commit.
ANIMATION_PRESETS: dict[str, dict[str, object]] = {
    "default": {
        "label": "Balanced",
        "desc": "Medium speed, light popin — the project's original preset",
        "curves": _CURVES_DEFAULT,
        "animations": ANIMATION_BASE,
    },
    "snappy": {
        "label": "Snappy",
        "desc": "Very short and sharp; the desktop feels like it reacts instantly",
        "curves": (
            ("snap",   "0.05", "0.90", "0.10", "1.00"),
            ("snapIn", "0.30", "0.00", "0.60", "1.00"),
            ("linear", "0",    "0",    "1",    "1"),
        ),
        "animations": (
            ("windowsIn",   2, "snap",   "popin 90%"),
            ("windowsOut",  2, "snapIn", "popin 90%"),
            ("windowsMove", 2, "snap",   "slide"),
            ("fadeIn",      2, "snap",   ""),
            ("fadeOut",     2, "snapIn", ""),
            ("border",      4, "snap",   ""),
            ("workspaces",  3, "snap",   "slide"),
            ("specialWorkspace", 3, "snap", "slidevert"),
            ("layersIn",    2, "snap",   "popin 95%"),
            ("layersOut",   2, "snapIn", "popin 95%"),
            ("fadeLayersIn",  2, "snap",   ""),
            ("fadeLayersOut", 2, "snapIn", ""),
        ),
    },
    "fluid": {
        "label": "Fluid",
        "desc": "Long, smooth, slightly springy — the most 'showy' preset",
        "curves": (
            # The y > 1.0 control point is intentional: Hyprland reads it as
            # overshoot (going slightly past the target and settling back).
            ("overshot",  "0.05", "0.90", "0.10", "1.05"),
            ("smoothOut", "0.36", "0.00", "0.66", "-0.56"),
            ("smoothIn",  "0.25", "1.00", "0.50", "1.00"),
        ),
        "animations": (
            ("windowsIn",   7, "overshot",  "popin 60%"),
            ("windowsOut",  5, "smoothOut", "popin 60%"),
            ("windowsMove", 7, "overshot",  "slide"),
            ("fadeIn",      6, "smoothIn",  ""),
            ("fadeOut",     5, "smoothOut", ""),
            ("border",     12, "smoothIn",  ""),
            ("workspaces",  8, "overshot",  "slidefade 20%"),
            ("specialWorkspace", 8, "overshot", "slidevert"),
            ("layersIn",    6, "overshot",  "popin 80%"),
            ("layersOut",   5, "smoothOut", "popin 80%"),
            ("fadeLayersIn",  5, "smoothIn",  ""),
            ("fadeLayersOut", 4, "smoothOut", ""),
        ),
    },
    "minimal": {
        "label": "Minimal",
        "desc": "Fade only — nothing slides or grows",
        "curves": (
            ("fade",   "0.25", "0.10", "0.25", "1.00"),
            ("linear", "0",    "0",    "1",    "1"),
        ),
        "animations": (
            ("windowsIn",   3, "fade", "popin 100%"),
            ("windowsOut",  3, "fade", "popin 100%"),
            ("windowsMove", 3, "fade", ""),
            ("fadeIn",      3, "fade", ""),
            ("fadeOut",     3, "fade", ""),
            ("border",      5, "fade", ""),
            ("workspaces",  3, "fade", "fade"),
            ("specialWorkspace", 3, "fade", "fade"),
            ("layersIn",    3, "fade", "popin 100%"),
            ("layersOut",   3, "fade", "popin 100%"),
            ("fadeLayersIn",  3, "fade", ""),
            ("fadeLayersOut", 3, "fade", ""),
        ),
    },
    "none": {
        "label": "Off",
        "desc": "No animations at all — lowest latency",
        "curves": (),
        "animations": (),
    },
}

DEFAULT_ANIMATION_PRESET = "default"


#: ANIMATION_PRESET="custom": the preset is read from ANIMATION_CUSTOM. The mix
#: (mix.py) carries a rice's animations over exactly this way; rounding to the
#: built-in presets would lose the author's curves. Format: Hyprland lines
#: separated by ";;" —
#: "bezier = name, x1, y1, x2, y2;;animation = windows, 1, 6, name, popin 80%"
CUSTOM_ANIMATION_PRESET = "custom"


def resolve_animation_preset(name: str) -> str:
    """Turns an invalid/empty preset name into the default."""
    key = (name or "").strip().lower()
    return key if key in ANIMATION_PRESETS else DEFAULT_ANIMATION_PRESET


def parse_custom_animations(spec: str) -> dict[str, object]:
    """ANIMATION_CUSTOM → a dict in the same shape as the built-in presets.

    Disabled branches ("animation = fade, 0") are also returned under
    ``disabled``. A line with no curve uses Hyprland's "default" curve.
    """
    curves: list[tuple[str, ...]] = []
    animations: list[tuple[str, float, str, str]] = []
    disabled: list[str] = []
    order: list[str] = []          # order the branches were written (parent first)
    for item in (spec or "").split(";;"):
        key, sep, value = item.partition("=")
        if not sep:
            continue
        key = key.strip().lower()
        parts = [p.strip() for p in value.split(",")]
        if key == "bezier" and len(parts) == 5:
            try:
                [float(p) for p in parts[1:]]
            except ValueError:
                continue
            curves.append(tuple(parts))
        elif key == "animation" and len(parts) >= 2 and parts[0]:
            if parts[1].lower() in ("0", "false", "no", "off"):
                disabled.append(parts[0])
                order.append(parts[0])
                continue
            try:
                duration = float(parts[2]) if len(parts) > 2 else 10.0
            except ValueError:
                continue
            curve = parts[3] if len(parts) > 3 and parts[3] else "default"
            animations.append((parts[0], duration, curve, ", ".join(parts[4:])))
            order.append(parts[0])
    return {"label": "Custom", "desc": "Preset from the mix (ANIMATION_CUSTOM)",
            "curves": tuple(curves), "animations": tuple(animations),
            "disabled": tuple(disabled), "order": tuple(order)}


def animation_preset(variables: dict[str, str]) -> dict[str, object]:
    """What ANIMATION_PRESET resolves to: a built-in preset or ANIMATION_CUSTOM."""
    name = (variables.get("ANIMATION_PRESET") or "").strip().lower()
    if name == CUSTOM_ANIMATION_PRESET:
        return parse_custom_animations(variables.get("ANIMATION_CUSTOM", ""))
    return ANIMATION_PRESETS[resolve_animation_preset(name)]


def _animation_lines(variables: dict[str, str], lang: str = "conf") -> list[str]:
    try:
        speed = float(variables.get("ANIMATION_SPEED") or 1.0)
    except ValueError:
        speed = 1.0
    speed = min(max(speed, 0.1), 10.0)

    preset = animation_preset(variables)
    custom = "disabled" in preset
    curves: tuple = preset["curves"]        # type: ignore[assignment]
    animations: tuple = preset["animations"]  # type: ignore[assignment]
    disabled: tuple = preset.get("disabled", ())  # type: ignore[assignment]
    # In the custom preset lines come out in the author's order: the order
    # must be kept so a later parent branch does not override an earlier child.
    by_name = {a[0]: a for a in animations}
    sequence = [(n, by_name.get(n)) for n in preset.get("order", ())] or \
        [(a[0], a) for a in animations]

    def duration_text(duration: float) -> str:
        # Built-in presets produce whole deciseconds (so their output does not
        # change); the custom preset keeps the author's fractional durations.
        if not custom:
            return str(max(1, round(duration / speed)))
        return f"{max(0.1, round(duration / speed, 2)):g}"

    if custom and not animations and not disabled:
        # The author defined no animations: Hyprland's own defaults.
        return []

    # "none": a single line turns everything off. Same result as
    # ANIMATIONS=false, but it must also work when the user leaves the
    # animations block on and changes the preset.
    if not animations and not custom:
        return (['hl.animation({ leaf = "global", enabled = false })'] if lang == "lua"
                else ["    animation = global, 0"])

    if lang == "lua":
        lines = []
        for name, x1, y1, x2, y2 in curves:
            lines.append(
                f'hl.curve({_lua_quote(name)}, {{ type = "bezier", points = {{ '
                f'{{{x1}, {y1}}}, {{{x2}, {y2}}} }} }})')
        lines.append("")
        for leaf, entry in sequence:
            if entry is None:
                lines.append(f'hl.animation({{ leaf = {_lua_quote(leaf)}, enabled = false }})')
                continue
            name, duration, curve, style = entry
            style_part = f', style = {_lua_quote(style)}' if style else ""
            lines.append(
                f'hl.animation({{ leaf = {_lua_quote(name)}, enabled = true, '
                f'speed = {duration_text(duration)}, bezier = {_lua_quote(curve)}{style_part} }})')
        return lines

    # Lines go inside the animations {} block, so they are indented.
    lines = [
        f"    bezier = {name}, {x1}, {y1}, {x2}, {y2}"
        for name, x1, y1, x2, y2 in curves
    ]
    lines.append("")
    for leaf, entry in sequence:
        if entry is None:
            lines.append(f"    animation = {leaf}, 0")
            continue
        name, duration, curve, style = entry
        suffix = f", {style}" if style else ""
        lines.append(f"    animation = {name}, 1, {duration_text(duration)}, {curve}{suffix}")
    return lines


def _gesture_lines(variables: dict[str, str], lang: str = "conf") -> list[str]:
    """Hyprland 0.51+ gesture syntax (hl.gesture() in Lua)."""
    if not truthy(variables.get("GESTURE_SWIPE", "true")):
        return (["-- Gestures off (GESTURE_SWIPE=false)"] if lang == "lua"
                 else ["# Gestures off (GESTURE_SWIPE=false)"])
    try:
        fingers = int(variables.get("GESTURE_FINGERS") or 3)
    except ValueError:
        fingers = 3
    fingers = min(max(fingers, 3), 5)
    if lang == "lua":
        return [f'hl.gesture({{ fingers = {fingers}, direction = "horizontal", action = "workspace" }})']
    return [f"gesture = {fingers}, horizontal, workspace"]


def _persistent_workspaces_json(variables: dict[str, str], ws_count: int,
                                 workspaces_conf: Path | None = None) -> str:
    """Waybar ``hyprland/workspaces`` → the ``persistent-workspaces`` value.

    The numeric wildcard form (``{"*": N}``) mimics Sway's LOCAL (per-output)
    workspace numbering in Waybar: each output gets its own numbers starting
    at 1. In Hyprland workspaces use GLOBAL IDs (e.g. number 6 bound to HDMI
    is always 6) — with a static mapping between monitors
    (WORKSPACE_MONITOR_MAP or a workspaces.conf generated by a tool like
    nwg-displays) the wildcard form shows the wrong number (a button that is
    really 6 says "1"). If such a mapping can be found, a per-monitor array
    is generated from the real ID lists; otherwise (the typical single screen,
    or multiple screens with no static mapping) it falls back to the wildcard.
    """
    mapping = _parse_workspace_monitor_map_spec(variables.get("WORKSPACE_MONITOR_MAP", ""))
    if not mapping and not truthy(variables.get("PORTABLE_OUTPUT", "")):
        # PORTABLE_OUTPUT: the output is generated for distribution, not for
        # THIS machine (tools/build-dotfiles.sh). Then the live workspaces.conf
        # in the home directory must NOT be consulted — otherwise the generating
        # machine's monitor names (DP-1, HDMI-A-2 …) leak into the distributed
        # dotfiles and waybar shows wrong workspace buttons for users without
        # those monitors. (That is exactly why all of the repo's
        # dotfiles/*/waybar/config.jsonc files carried a single developer's
        # monitor layout.)
        mapping = _parse_workspaces_conf_monitors(
            workspaces_conf or (Path.home() / ".config/hypr/workspaces.conf"))
    if mapping:
        body = ", ".join(
            f'"{monitor}": {json.dumps(ids)}' for monitor, ids in mapping.items()
        )
        return "{ " + body + " }"
    return f'{{ "*": {ws_count} }}'


def _auto_workspace_split(variables: dict[str, str]) -> dict[str, str]:
    """``WORKSPACE_SPLIT=auto``: splits workspaces evenly across connected monitors.

    Monitor names cannot be hard-coded in a profile (they differ per machine:
    eDP-1, DP-2 …), so the mapping is generated on the installing machine:
    WORKSPACE_COUNT=10 and two monitors give 1-5 to the first and 6-10 to the
    second. Monitor order is Hyprland's monitor id order (/sys/class/drm by
    name if there is no session). Nothing is done with a single monitor, when
    a hand-written WORKSPACE_MONITOR_MAP exists, when generating distributable
    output (PORTABLE_OUTPUT), or when another tool (nwg-displays) manages
    workspaces.conf — in that case waybar already reads that file.
    """
    if (variables.get("WORKSPACE_SPLIT", "").strip().lower() != "auto"
            or variables.get("WORKSPACE_MONITOR_MAP", "").strip()
            or truthy(variables.get("PORTABLE_OUTPUT", ""))):
        return variables
    lang = (variables.get("HYPR_LANG") or "conf").strip().lower()
    target = Path.home() / (".config/hypr/hyprland/workspaces.lua" if lang == "lua"
                            else ".config/hypr/workspaces.conf")
    try:
        if "hyprsetup:managed" not in target.read_text():
            return variables
    except OSError:
        pass
    monitors = _connected_monitors()
    if len(monitors) < 2:
        return variables
    count = max(1, min(20, _int(variables.get("WORKSPACE_COUNT"), 10)))
    per, extra = divmod(count, len(monitors))
    entries: list[str] = []
    start = 1
    for index, monitor in enumerate(monitors):
        size = per + (1 if index < extra else 0)
        for number in range(start, start + size):
            entries.append(f"{number}:{monitor}" + (":default" if number == start else ""))
        start += size
    return {**variables, "WORKSPACE_MONITOR_MAP": ";".join(entries)}


def _connected_monitors() -> list[str]:
    """Names of connected monitors: hyprctl first, DRM connectors if there is no session."""
    try:
        result = subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True,
                                text=True, timeout=3, check=False)
        data = json.loads(result.stdout) if result.returncode == 0 else []
        names = [m["name"] for m in sorted(data, key=lambda m: m.get("id", 0))
                 if m.get("name")]
        if names:
            return names
    except (OSError, ValueError, subprocess.SubprocessError, TypeError, KeyError):
        pass
    names = []
    for status in sorted(Path("/sys/class/drm").glob("card*-*/status")):
        try:
            if status.read_text().strip() != "connected":
                continue
        except OSError:
            continue
        # "card1-HDMI-A-2" → "HDMI-A-2" (the name Hyprland uses)
        name = status.parent.name.split("-", 1)[1]
        if not name.startswith("Writeback") and name not in names:
            names.append(name)
    return names


def _parse_workspace_monitor_map_spec(spec: str) -> dict[str, list[int]]:
    mapping: dict[str, list[int]] = {}
    for entry in (e.strip() for e in spec.split(";")):
        if not entry:
            continue
        parts = entry.split(":")
        if len(parts) < 2:
            continue
        try:
            mapping.setdefault(parts[1], []).append(int(parts[0]))
        except ValueError:
            continue
    return mapping


def _parse_workspaces_conf_monitors(path: Path) -> dict[str, list[int]]:
    """Best-effort parse of a workspaces.conf generated by nwg-displays etc.

    Expected format: ``workspace=6,monitor:HDMI-A-2,default:true`` (the
    spaced ``workspace = 6, monitor:HDMI-A-2`` form is accepted too).
    """
    mapping: dict[str, list[int]] = {}
    try:
        text = path.read_text()
    except OSError:
        return mapping
    for line in text.splitlines():
        line = line.strip()
        if not line.lower().startswith("workspace") or "=" not in line or "monitor:" not in line:
            continue
        _, _, body = line.partition("=")
        fields = [f.strip() for f in body.split(",")]
        if not fields:
            continue
        try:
            number = int(fields[0])
        except ValueError:
            continue
        monitor = next((f.split(":", 1)[1].strip() for f in fields[1:] if f.startswith("monitor:")), "")
        if monitor:
            mapping.setdefault(monitor, []).append(number)
    return mapping


def _workspace_monitor_lines(spec: str, lang: str = "conf") -> list[str]:
    """"1:DP-1:default;2:DP-1" → workspace = 1, monitor:DP-1, default:true"""
    lines: list[str] = []
    for entry in (e.strip() for e in spec.split(";")):
        if not entry:
            continue
        parts = entry.split(":")
        if len(parts) < 2:
            continue
        number, monitor = parts[0], parts[1]
        is_default = len(parts) > 2 and parts[2] == "default"
        if lang == "lua":
            default_part = ", default = true" if is_default else ""
            lines.append(
                f'hl.workspace_rule({{ workspace = {_lua_quote(number)}, '
                f'monitor = {_lua_quote(monitor)}{default_part} }})')
        else:
            line = f"workspace = {number}, monitor:{monitor}"
            if is_default:
                line += ", default:true"
            lines.append(line)
    return lines


# ------------------------------------------------------------------ Lua -----
def _lua_quote(value: str) -> str:
    escaped = (value or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _lua_monitor_line(spec: str) -> str:
    """"DP-1,2560x1440@165,0x0,1" → hl.monitor({ output = ..., ... })"""
    fields = [f.strip() for f in spec.split(",")]
    fields += [""] * (4 - len(fields))
    output, mode, position, scale = fields[0], fields[1] or "preferred", fields[2] or "auto", fields[3] or "1"
    scale_lit = scale if re.fullmatch(r"-?\d+(\.\d+)?", scale) else _lua_quote(scale)
    return (f"hl.monitor({{ output = {_lua_quote(output)}, mode = {_lua_quote(mode)}, "
            f"position = {_lua_quote(position)}, scale = {scale_lit} }})")


#: Size of the MOD+I panel, as a PERCENTAGE of the screen size. THIS IS THE
#: SINGLE SOURCE OF TRUTH: both the Hyprland window rule
#: (templates/hypr/windowrules.*) and the GTK window's own default size
#: (gui/app.py, panel mode) read it. If the two diverge, Hyprland resizes the
#: window RIGHT AFTER it opens and the panel visibly jumps as it opens.
#:
#: Percentages replaced fixed pixels: the panel is now the full settings app
#: itself (sidebar + page + live preview); a fixed box like 1280×700 was tiny
#: on a 4K screen and big enough to overflow on a 1366×768 laptop.
QUICK_PANEL_WIDTH_PCT = 80
QUICK_PANEL_HEIGHT_PCT = 80
#: Gap from the edge the panel sits on. So it does not stick to the top of the screen.
QUICK_PANEL_TOP_GAP = 8
#: Default screen if the screen size cannot be read (headless session, first draw).
QUICK_PANEL_FALLBACK_SCREEN = (1920, 1080)


def quick_panel_percent(variables: dict | None = None) -> tuple[int, int]:
    """The panel's ratio to the screen: QUICK_PANEL_WIDTH/HEIGHT setting, else the constants."""
    variables = variables or {}
    def pct(name: str, fallback: int) -> int:
        try:
            return max(40, min(100, int(float(variables.get(name) or fallback))))
        except (TypeError, ValueError):
            return fallback
    return (pct("QUICK_PANEL_WIDTH", QUICK_PANEL_WIDTH_PCT),
            pct("QUICK_PANEL_HEIGHT", QUICK_PANEL_HEIGHT_PCT))


def quick_panel_pixels(screen: tuple[int, int] | None = None,
                       variables: dict | None = None) -> tuple[int, int]:
    """The panel's size in pixels — for GTK's default size.

    The window rule is written in percent; if GTK does not do the same math
    the window first opens at its own size, then Hyprland immediately resizes
    it and the panel jumps. So both sides use this function.
    """
    width, height = screen or QUICK_PANEL_FALLBACK_SCREEN
    width_pct, height_pct = quick_panel_percent(variables)
    return (max(640, width * width_pct // 100),
            max(480, height * height_pct // 100))


def _quick_panel_vars(variables: dict) -> dict:
    """The panel's position at the TOP center of the screen.

    If there is a status bar at the top the panel starts below it: overlapping
    it would hide the bar's clock/modules behind the panel. Height and margin
    are read from the user's own BAR_* settings, not fixed.
    """
    def _int(name: str, fallback: int) -> int:
        try:
            return int(float(variables.get(name) or fallback))
        except (TypeError, ValueError):
            return fallback

    top = QUICK_PANEL_TOP_GAP
    if (variables.get("BAR_POSITION") or "top") == "top":
        top += _int("BAR_HEIGHT", 38) + 2 * _int("BAR_MARGIN", 6)

    width_pct, height_pct = quick_panel_percent(variables)
    return {
        "QUICK_PANEL_SIZE": f"{width_pct}% {height_pct}%",
        # "10% 58": centered horizontally (half of the remaining space at the
        # edges), vertically below the bar. Since the percentage is computed
        # from the screen, the panel looks the same on 1366×768 and on 4K.
        "QUICK_PANEL_MOVE": f"{(100 - width_pct) // 2}% {top}",
    }


def _windowrule_lines(variables: dict[str, str], lang: str) -> list[str]:
    """Turns the WINDOWRULES setting into hypr window rule lines.

    The value is ";;"-separated *bodies* in Hyprland 0.51+ syntax (without the
    leading "windowrule = "). Example:

        WINDOWRULES="float on, match:class ^(pavucontrol)$;;opacity 0.9, match:class ^(kitty)$"

    Added so profiles can carry character beyond colors: a "gaming" profile
    can open Steam fullscreen, a "minimal" profile can float helper windows.

    Lua mode (HYPR_LANG=lua, experimental) writes the rules as COMMENTS:
    hl.window_rule() wants a structured table, and we cannot reliably convert
    a free-text conf body into it. Leaving them visible in the file instead of
    silently swallowing them makes it readable why the rule is not applied.
    """
    rules = _split_list(variables.get("WINDOWRULES", ""))
    # Rules the user set up on the Window Rules page: kept in a separate key
    # so they survive a profile switch; written after, so they win on conflict.
    rules += _split_list(variables.get("USER_WINDOWRULES", ""))
    if not rules:
        return []
    if lang == "lua":
        return [
            "-- Profile/user window rules (WINDOWRULES).",
            "-- NOTE: NOT APPLIED in Lua mode — hl.window_rule() wants a structured",
            "-- table, the conf bodies below cannot be converted to it.",
            "-- If you want these rules, install with HYPR_LANG=conf.",
            *(f"--   windowrule = {rule}" for rule in rules),
        ]
    return ["# Profile/user window rules (WINDOWRULES)",
            *(f"windowrule = {rule}" for rule in rules)]


def _split_list(value: str) -> list[str]:
    """Splits a ";;"-separated list (since commands may contain ';')."""
    return [item.strip() for item in (value or "").split(";;") if item.strip()]


def _split_pairs(value: str) -> list[tuple[str, str]]:
    """"NAME=value;;NAME2=value2" → [(NAME, value), …]"""
    pairs = []
    for item in _split_list(value):
        name, sep, val = item.partition("=")
        if sep:
            pairs.append((name.strip(), val.strip()))
    return pairs


# Autostart entry: ('cmd', command) | ('comment', text) | ('blank', None)
AutostartEntry = tuple[str, "str | None"]


#: Plugin components installed with hyprpm (config/components.json → "plugins").
#: They are not pacman packages; they are built from source (see modules/hypr.sh).
PLUGIN_COMPONENTS = frozenset({
    "hyprexpo", "hyprbars", "borders-plus-plus", "hyprtrails", "hy3",
})

#: Commands for the volume/brightness keys. If swayosd is installed they are
#: routed to the client that does the same job but draws an on-screen indicator.
#:
#: swayosd-client applies the change ITSELF (not in addition to
#: pamixer/brightnessctl but INSTEAD of them) — calling both would change the
#: volume twice, i.e. by 10% per step.
_MEDIA_COMMANDS = {
    False: {   # no swayosd — the tools directly
        "CMD_VOLUME_UP":     "pamixer -i 5",
        "CMD_VOLUME_DOWN":   "pamixer -d 5",
        "CMD_VOLUME_MUTE":   "pamixer -t",
        "CMD_MIC_MUTE":      "pamixer --default-source -t",
        "CMD_BRIGHTNESS_UP": "brightnessctl set 5%+",
        "CMD_BRIGHTNESS_DOWN": "brightnessctl set 5%-",
    },
    True: {    # swayosd present — the client that draws an indicator
        "CMD_VOLUME_UP":     "swayosd-client --output-volume raise",
        "CMD_VOLUME_DOWN":   "swayosd-client --output-volume lower",
        "CMD_VOLUME_MUTE":   "swayosd-client --output-volume mute-toggle",
        "CMD_MIC_MUTE":      "swayosd-client --input-volume mute-toggle",
        "CMD_BRIGHTNESS_UP": "swayosd-client --brightness raise",
        "CMD_BRIGHTNESS_DOWN": "swayosd-client --brightness lower",
    },
}


def _media_command_vars(selected: list[str]) -> dict[str, str]:
    return dict(_MEDIA_COMMANDS["swayosd" in selected])


def _autostart_entries(variables: dict[str, str], catalog: Catalog,
                       selected: list[str]) -> list[AutostartEntry]:
    """Generates the exec-once commands in a sensible order, independent of language.

    In conf mode they become ``exec-once = ...`` lines, in lua mode
    ``hl.exec_cmd(...)`` calls inside ``hl.on("hyprland.start", ...)`` — see
    _autostart_conf_lines / _autostart_lua_lines.
    """
    lines: list[AutostartEntry] = []

    def add(cmd: str, note: str = "") -> None:
        if not cmd:
            return
        if note:
            lines.append(("comment", note))
        lines.append(("cmd", cmd))

    if "polkit" in selected:
        add("systemctl --user start hyprpolkitagent.service", "Authentication agent")

    if truthy(variables.get("GNOME_KEYRING")):
        add("gnome-keyring-daemon --start --components=secrets", "Keyring")

    for var, note in (("BAR", "Status bar"),
                      ("NOTIFIER", "Notifications"),
                      ("WALLPAPER_DAEMON", "Wallpaper")):
        comp = catalog.component(variables.get(var, ""))
        # quickshell-bar is started in the shared block below: the bar and the
        # widgets share the same shell.qml, and if started twice, two processes
        # draw two copies of the panel.
        if comp and comp.id in selected and comp.id != "quickshell-bar":
            add(comp.exec, note)

    # walker's data backend: all providers (the app list included) come from
    # this service; if it is not running the launcher opens empty. The package
    # itself ships no systemd unit ("elephant service enable" writes into the
    # user's home); starting it with the session is the least surprising way.
    if variables.get("LAUNCHER") == "walker" and "walker" in selected:
        add("elephant", "walker data service (elephant)")

    # Helper that waits at the edge and shows/hides the bar: only needed for
    # Waybar (the Quickshell bar hides itself, see QS_BAR_AUTOHIDE).
    if (truthy(variables.get("BAR_AUTOHIDE"))
            and variables.get("BAR") == "waybar" and "waybar" in selected):
        add("python3 ~/.config/hypr/scripts/bar-autohide.py",
            "Bar auto-hide")

    if "clipboard" in selected:
        add("wl-paste --type text --watch cliphist store", "Clipboard history (text)")
        add("wl-paste --type image --watch cliphist store")

    if "hypridle" in selected:
        add("hypridle", "Idle management")

    if "eww" in selected:
        add("eww daemon", "Widget engine")
        # Windows are opened with ONE command. There used to be one
        # "sleep 1 && eww open <name>" line per widget: fifteen widgets meant
        # fifteen shells + fifteen client processes, all relying on the same
        # 1 second for the daemon to be ready. "open-many" exists exactly for
        # this. The widget list comes from the layout function (so "which
        # widgets were actually generated" has a single answer).
        names = active_widgets(variables, selected, "eww")
        if names and truthy(variables.get("WIDGET_AUTOSTART", "true")):
            add("~/.config/hypr/scripts/widgets.sh show",
                "Desktop widgets")

    if "quickshell" in selected or "quickshell-bar" in selected:
        # All widgets AND (if selected) the bar are defined in a single
        # shell.qml (see templates/quickshell/shell.qml.tmpl) — unlike eww no
        # separate "open" command per widget is needed, a single process
        # keeping the file open is enough. If both roles go to Quickshell it is still one line.
        both = "quickshell" in selected and "quickshell-bar" in selected
        note = ("Quickshell (bar + widgets)" if both
                else "Bar (Quickshell)" if "quickshell-bar" in selected
                else "Widget engine (Quickshell)")
        add("quickshell -p ~/.config/quickshell/hyprsetup/shell.qml", note)

    if "swayosd" in selected:
        # The server must be running first: swayosd-client connects to it on
        # a key press, and without the server no indicator ever appears (the
        # command fails silently and the volume still changes — the error goes
        # unnoticed).
        add("swayosd-server", "Volume/brightness indicator")

    # nm-applet (the network icon in the tray) is deliberately not started
    # (2026-10-04): the bar has its own network module (click for the network
    # panel, right-click for nmtui), and nm-applet's old-style icon did not fit
    # the theme, leaving two network icons in the bar. The cost: no windows
    # asking for Wi-Fi/VPN passwords; connections are set up from the network
    # panel or nmtui.

    if "bluetooth" in selected:
        add("blueman-applet", "Bluetooth tray icon")

    if "swww" in selected:
        wallpaper = variables.get("WALLPAPER_PATH", "")
        if wallpaper:
            # Transition flags apply to the first apply too: the wallpaper
            # "appearing" at login is the rice's first impression.
            transition = variables.get("SWWW_TRANSITION", "") or "grow"
            duration = variables.get("SWWW_TRANSITION_DURATION", "") or "2"
            fps = variables.get("SWWW_TRANSITION_FPS", "") or "60"
            # swww's new name is awww (the Arch package only has awww/awww-daemon).
            add(f"sleep 1 && awww img '{wallpaper}'"
                f" --transition-type {transition}"
                f" --transition-duration {duration}"
                f" --transition-fps {fps}")

    if "wallpaperengine" in selected:
        cmd = _wallpaperengine_cmd(variables)
        if cmd:
            add(cmd, "Wallpaper Engine wallpaper")
        else:
            lines.append(("comment", "linux-wallpaperengine is not started automatically"))
            lines.append(("comment", "because WPENGINE_ID is not set. To see the IDs:"))
            lines.append(("comment", "ls ~/.steam/steam/steamapps/workshop/content/431960"))

    # ALT+Tab switcher in "preload" mode: an invisible instance is opened at
    # session start and only draws the window when the keybinding is pressed.
    # Only meaningful for the thumbnail mode (the plain list opens instantly anyway).
    if (truthy(variables.get("SWITCHER_PRELOAD"))
            and variables.get("WINDOW_SWITCHER") == "overlay"
            and truthy(variables.get("SWITCHER_ENABLED", "true"))
            and truthy(variables.get("MANAGE_HYPR_CONFIGS", "1"))):
        add("~/.config/hypr/scripts/windowswitch.py --preload",
            "ALT+Tab switcher (waits ready in the background)")

    extra = _split_list(variables.get("EXTRA_EXEC_ONCE", ""))
    if extra:
        lines.append(("blank", None))
        lines.append(("comment", "User-defined (EXTRA_EXEC_ONCE)"))
        lines.extend(("cmd", cmd) for cmd in extra)

    return lines


def _autostart_conf_lines(entries: list[AutostartEntry]) -> list[str]:
    out: list[str] = []
    for kind, value in entries:
        if kind == "cmd":
            out.append(f"exec-once = {value}")
        elif kind == "comment":
            out.append(f"# {value}")
        else:
            out.append("")
    return out


def _autostart_lua_lines(entries: list[AutostartEntry]) -> list[str]:
    body: list[str] = []
    for kind, value in entries:
        if kind == "cmd":
            body.append(f"    hl.exec_cmd({_lua_quote(value or '')})")
        elif kind == "comment":
            body.append(f"    -- {value}")
        else:
            body.append("")
    return ['hl.on("hyprland.start", function()', *body, "end)"]


#: The generated script that starts linux-wallpaperengine
#: (templates/hypr/scripts/wallpaperengine.sh.tmpl).
WPENGINE_SCRIPT = "~/.config/hypr/scripts/wallpaperengine.sh"


def _wallpaperengine_cmd(variables: dict[str, str]) -> str:
    """The command that starts linux-wallpaperengine; "" if WPENGINE_ID is empty.

    The script builds the command line, not this function: without a screen
    name (--screen-root) linux-wallpaperengine opens a separate window
    instead of a wallpaper. With WPENGINE_SCREEN empty the monitors can only
    be known at runtime (hyprctl monitors). The command generated here used to
    open a window in the middle of the desktop when WPENGINE_SCREEN was empty;
    --scaling was also written BEFORE --screen-root, so it applied to no
    screen. See https://github.com/Almamu/linux-wallpaperengine
    """
    if not (variables.get("WPENGINE_ID") or "").strip():
        return ""
    return WPENGINE_SCRIPT


def _screenshot_cmd(selected: list[str]) -> str:
    if "screenshot-base" not in selected:
        return ""
    if "screenshot-annotate" in selected:
        return "grim -g \"$(slurp)\" - | swappy -f -"
    return "grim -g \"$(slurp)\" - | wl-copy"


# --------------------------------------------------- default applications --
# Default application associations are defined HERE in a single place. They
# used to be spread over three places and none knew about the others:
#   · modules/desktop.sh → hook_thunar/hook_nautilus/hook_nemo/hook_dolphin
#     only assigned inode/directory via xdg-mime, and the hook only fired
#     when the component was installed IN THAT RUN — never on --reapply, so
#     once the association broke it never fixed itself.
#   · modules/desktop.sh → hook_firefox wrote a fixed "firefox.desktop",
#     even when BROWSER was set to something else.
#   · Every other type (text, image, archive, http) was never assigned; the
#     desktop asked "which app should open this" or picked one at random —
#     that was the "default app settings are broken" picture users saw.
#
# Now there is a single source: the "desktop" field in config/components.json
# + the table below. Both ~/.config/mimeapps.list and
# ~/.config/xdg-terminals.list are generated from it (templates/xdg/), and
# modules/desktop.sh only refreshes xdg-mime's own cache. To add a new role:
# (1) give the component a "desktop" field, (2) add a row to DEFAULT_APP_ROLES.
#
#: role -> (which variable holds that role's component, MIME types to assign)
DEFAULT_APP_ROLES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("FILEMANAGER", "FILEMANAGER", (
        "inode/directory",
        "x-directory/normal",
        "x-scheme-handler/file",
    )),
    ("BROWSER", "BROWSER", (
        "text/html",
        "application/xhtml+xml",
        "x-scheme-handler/http",
        "x-scheme-handler/https",
        "x-scheme-handler/about",
        "x-scheme-handler/unknown",
    )),
    ("TERMINAL", "TERMINAL", (
        # The terminal itself opens no MIME type; it is written to
        # xdg-terminals.list (handled separately below). It is here so the
        # DESKTOP_TERMINAL variable gets generated.
    )),
)

#: Roles tied directly to a component being selected, not to a variable.
#: If the component is not selected those types are not written to
#: mimeapps.list at all — assigning to a nonexistent .desktop is worse than
#: no assignment (the desktop says "application not found" and offers no
#: alternative).
DEFAULT_APP_COMPONENT_ROLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("archive", (
        "application/zip",
        "application/x-7z-compressed",
        "application/vnd.rar",
        "application/x-rar-compressed",
        "application/x-tar",
        "application/gzip",
        "application/x-xz",
        "application/x-bzip2",
        "application/x-compressed-tar",
    )),
    ("dev-tools", (
        "text/plain",
        "text/markdown",
        "text/x-shellscript",
        "application/json",
        "text/x-python",
        "application/x-yaml",
    )),
)


def _default_app_vars(variables: dict[str, str], catalog: Catalog,
                      selected: list[str]) -> dict[str, str]:
    """Generates the variables for mimeapps.list / xdg-terminals.list."""
    def desktop_of(comp_id: str) -> str:
        comp = catalog.component(comp_id)
        return (comp.desktop if comp else "") or ""

    out: dict[str, str] = {}
    #: MIME type -> .desktop. dict order is preserved, so the output is stable.
    assoc: dict[str, str] = {}

    for name, var, mimes in DEFAULT_APP_ROLES:
        desktop = desktop_of(variables.get(var, ""))
        out[f"DESKTOP_{name}"] = desktop
        if not desktop:
            continue
        for mime in mimes:
            assoc[mime] = desktop

    for comp_id, mimes in DEFAULT_APP_COMPONENT_ROLES:
        if comp_id not in selected:
            continue
        desktop = desktop_of(comp_id)
        if not desktop:
            continue
        for mime in mimes:
            # If a more specific role (e.g. text/html for the browser) already
            # assigned it, leave it alone.
            assoc.setdefault(mime, desktop)

    out["MIMEAPPS_LINES"] = "\n".join(f"{mime}={desktop}"
                                      for mime, desktop in assoc.items())
    out["HAS_DEFAULT_APPS"] = "1" if assoc else ""
    return out


# ------------------------------------------------------------------ driver --
def render_tree(templates_dir: Path, out_dir: Path, variables: dict[str, str],
                catalog: Catalog, selected: list[str],
                keybinds: "keybinds_mod.Keybinds | None" = None,
                unknown: dict[str, set[str]] | None = None) -> list[Path]:
    """Processes the templates/ tree and writes under out_dir; returns the written files.

    If ``unknown`` is given, templates referencing never-defined variables are
    written there as {template path: {name, ...}} (see _substitute).
    """
    variables = derived_vars(variables, catalog, selected, keybinds)
    written: list[Path] = []

    for src in sorted(templates_dir.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(templates_dir)
        text = src.read_text(encoding="utf-8")

        directives: dict[str, str] = {
            m.group(1): m.group(2) for m in _DIRECTIVE.finditer(text)}
        text = _DIRECTIVE.sub("", text)

        if not eval_condition(directives.get("require", ""), variables):
            continue

        target = directives.get("target") or str(rel)
        if target.endswith(".tmpl"):
            target = target[: -len(".tmpl")]

        dest = out_dir / target
        dest.parent.mkdir(parents=True, exist_ok=True)
        seen: set[str] | None = set() if unknown is not None else None
        # Clean up blank lines left behind by directives.
        dest.write_text(render_text(text, variables, seen).lstrip("\n"),
                        encoding="utf-8")
        if unknown is not None and seen:
            unknown.setdefault(str(rel), set()).update(seen)
        mode = directives.get("mode")
        dest.chmod(int(mode, 8) if mode else 0o644)
        written.append(dest)

    return written


def parse_vars_file(path: Path) -> dict[str, str]:
    """Reads the KEY=VALUE file generated by bash."""
    variables: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        # ONLY the wrapping PAIR of quotes is stripped. The previous
        # .strip('"').strip("'") worked on a character set and also ate the
        # value's TRAILING quote: `awk 'NR==2{print $4}'` lost its trailing
        # single quote and `echo "hello"` its double quote. Every setting that
        # can hold a shell command (BAR_CUSTOM*_CMD, EXTRA_EXEC_ONCE,
        # SWALLOW_REGEX) was affected. Same rule as gui/state.py:parse_conf_file.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        variables[key.strip()] = value
    return variables
