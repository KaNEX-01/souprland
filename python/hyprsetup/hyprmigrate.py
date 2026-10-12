"""Converts an old Hyprland config to the current syntax.

Profiles (rices) are installed from their authors' repos, pinned to the commit from
the date the post was published (see rice.py). The ``hyprland.conf`` from that date
often does not load in current Hyprland: ``windowrulev2`` was removed, window/layer
rules moved to the ``match:`` form, some options were deleted. The session starts
with "config error" and the setup looks broken.

This conversion does NOT change the look; it only writes the same rule in the new
language. Lines without an equivalent are not deleted but turned into comments with
the reason — the user can see in the file what was disabled and why.

Correctness is measured with ``Hyprland --verify-config`` (tools/test.sh).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Old rule name → (new name, whether it is a value-less on/off effect).
#: On/off effects need an explicit "on" in the new syntax: "float" → "float on".
_EFFECTS: dict[str, tuple[str, bool]] = {
    "float": ("float", True), "tile": ("tile", True),
    "fullscreen": ("fullscreen", True), "maximize": ("maximize", True),
    "pseudo": ("pseudo", True), "pin": ("pin", True),
    "center": ("center", True), "noblur": ("no_blur", True),
    "noshadow": ("no_shadow", True), "nofocus": ("no_focus", True),
    "noanim": ("no_anim", True), "nodim": ("no_dim", True),
    "noinitialfocus": ("no_initial_focus", True),
    "noborder": ("border_size 0", False),
    "norounding": ("rounding 0", False),
    "keepaspectratio": ("keep_aspect_ratio", True),
    "stayfocused": ("stay_focused", True), "dimaround": ("dim_around", True),
    "forcergbx": ("force_rgbx", True), "immediate": ("immediate", True),
    "xray": ("xray", True), "renderunfocused": ("render_unfocused", True),
    "nomaxsize": ("no_max_size", True), "syncfullscreen": ("sync_fullscreen", True),
    "allowsinput": ("allows_input", True), "noscreenshare": ("no_screen_share", True),
    "novrr": ("no_vrr", True), "persistentsize": ("persistent_size", True),
    "opaque": ("opaque", True),
    # Effects with a value (the value is carried over as-is).
    "opacity": ("opacity", False), "size": ("size", False),
    "move": ("move", False), "workspace": ("workspace", False),
    "monitor": ("monitor", False), "animation": ("animation", False),
    "rounding": ("rounding", False), "bordersize": ("border_size", False),
    "bordercolor": ("border_color", False), "minsize": ("min_size", False),
    "maxsize": ("max_size", False), "idleinhibit": ("idle_inhibit", False),
    "suppressevent": ("suppress_event", False), "group": ("group", False),
    "tag": ("tag", False), "fullscreenstate": ("fullscreen_state", False),
    "scrollmouse": ("scroll_mouse", False), "scrolltouchpad": ("scroll_touchpad", False),
    "roundingpower": ("rounding_power", False), "content": ("content", False),
    "noclosefor": ("no_close_for", False),
}

#: Old matcher → new match: property.
_MATCHERS: dict[str, str] = {
    "class": "class", "title": "title", "initialclass": "initial_class",
    "initialtitle": "initial_title", "floating": "float", "xwayland": "xwayland",
    "fullscreen": "fullscreen", "pinned": "pin", "focus": "focus",
    "workspace": "workspace", "tag": "tag", "group": "group",
    "fullscreenstate": "fullscreen_state", "onworkspace": "workspace",
    "content": "content", "xdgtag": "xdg_tag",
}

#: Old layer rule → (new name, whether it is on/off).
_LAYER_EFFECTS: dict[str, tuple[str, bool]] = {
    "blur": ("blur", True), "blurpopups": ("blur_popups", True),
    "noanim": ("no_anim", True), "dimaround": ("dim_around", True),
    "xray": ("xray", True), "abovelock": ("above_lock", False),
    "ignorezero": ("ignore_alpha 0", False), "ignorealpha": ("ignore_alpha", False),
    "animation": ("animation", False), "order": ("order", False),
    "noscreenshare": ("no_screen_share", True),
}

#: Removed options: "section:name" → reason. The line is turned into a comment.
_REMOVED: dict[str, str] = {
    "decoration:shadow:ignore_window": "removed from Hyprland",
    "dwindle:pseudotile": "removed from Hyprland (pseudo is now a window rule)",
    "gestures:workspace_swipe_fingers": "gestures moved to the 'gesture =' line",
    "gestures:workspace_swipe_min_fingers": "gestures moved to the 'gesture =' line",
    "gestures:workspace_swipe_distance": "removed from Hyprland",
    "gestures:workspace_swipe_invert": "removed from Hyprland",
    "gestures:workspace_swipe_min_speed_to_force": "removed from Hyprland",
    "gestures:workspace_swipe_cancel_ratio": "removed from Hyprland",
    "gestures:workspace_swipe_create_new": "removed from Hyprland",
    "gestures:workspace_swipe_direction_lock": "removed from Hyprland",
    "gestures:workspace_swipe_direction_lock_threshold": "removed from Hyprland",
    "gestures:workspace_swipe_forever": "removed from Hyprland",
    "gestures:workspace_swipe_use_r": "removed from Hyprland",
    "general:no_border_on_floating": "removed from Hyprland",
    "misc:vfr": "removed from Hyprland (variable frame rate is now always on)",
}

#: Renamed options: old full name → new leaf name (same section).
_RENAMED: dict[str, str] = {
    "misc:new_window_takes_over_fullscreen": "on_focus_under_fullscreen",
}


#: Former dispatchers that moved to layout messages (layoutmsg).
_LAYOUTMSG = {"togglesplit", "swapsplit", "preselect", "splitratio"}

_BIND = re.compile(r"^bind[a-z]*$")

#: Strings whose value goes straight to xkb (in input and device blocks).
_XKB_KEYS = {"kb_layout", "kb_variant", "kb_model", "kb_rules", "kb_options"}


@dataclass
class Report:
    changed: list[str] = field(default_factory=list)
    disabled: list[str] = field(default_factory=list)


def _split_rule(value: str) -> tuple[str, list[str]]:
    """Effect + items. Commas inside a regex ("a, b") are not split: a piece is a new
    item only if it starts with a known matcher ("title:", "class:"…); otherwise it
    continues the previous matcher."""
    raw = value.split(",")
    effect, items = raw[0].strip(), []
    for piece in raw[1:]:
        key = piece.strip().partition(":")[0].lower()
        starts_matcher = ":" in piece and key in _MATCHERS
        if items and not starts_matcher and ":" in items[-1] \
                and items[-1].partition(":")[0].strip().lower() in _MATCHERS:
            items[-1] += "," + piece
        else:
            items.append(piece.strip())
    return effect, [i for i in items if i]


def _convert_matchers(items: list[str]) -> list[str] | None:
    out = []
    for item in items:
        key, sep, val = item.partition(":")
        new = _MATCHERS.get(key.strip().lower())
        if not sep or new is None:
            return None
        # Hyprland splits the line on raw commas; a comma inside a regex is written
        # with RE2's \x2c escape — it matches the same character without splitting.
        # An empty value ("title:") used to match an empty title; the new syntax
        # rejects a matcher without a value.
        val = val.strip() or "^$"
        out.append(f"match:{new} {val.replace(',', chr(92) + 'x2c')}")
    return out


def _effect(raw: str, table: dict[str, tuple[str, bool]]) -> str | None:
    name, _sp, args = raw.strip().partition(" ")
    mapped = table.get(name.lower())
    if mapped is None:
        return None
    new, is_toggle = mapped
    if is_toggle:
        # "float" → "float on"; explicit old values like "noblur 0"/"pin 1" are kept too.
        value = args.strip() or "on"
        value = {"1": "on", "0": "off", "true": "on", "false": "off"}.get(value, value)
        return f"{new} {value}"
    return f"{new} {args.strip()}".strip()


def _windowrule(value: str, v2: bool) -> str | None:
    effect, rest = _split_rule(value)
    if not v2 and len(rest) == 1 and ":" not in rest[0]:
        # v1: "windowrule = float, ^(kitty)$" — a lone regex applied to the class.
        rest = [f"class:{rest[0]}"]
    # Some configs put several effects on one line
    # ("size 800 600, center, class:^(x)$"); the new syntax supports this.
    # Items that are not matchers (do not start with a known "property:" prefix)
    # are effects.
    effects = [effect]
    matchers_raw = []
    for item in rest:
        key = item.partition(":")[0].strip().lower()
        if ":" in item and key in _MATCHERS:
            matchers_raw.append(item)
        else:
            effects.append(item)
    new_effects = [_effect(e, _EFFECTS) for e in effects]
    matchers = _convert_matchers(matchers_raw)
    if any(e is None for e in new_effects) or not matchers:
        return None
    return f"windowrule = {', '.join(new_effects)}, " + ", ".join(matchers)


def _layerrule(value: str) -> str | None:
    effect, rest = _split_rule(value)
    if len(rest) != 1:
        return None
    new_effect = _effect(effect, _LAYER_EFFECTS)
    if new_effect is None:
        return None
    target = rest[0]
    if target.startswith("match:"):
        return None                                  # already the new format
    target = target.removeprefix("namespace:")
    return f"layerrule = {new_effect}, match:namespace {target}"


_ASSIGN = re.compile(r"^(\s*)([A-Za-z0-9_.:-]+)\s*=\s*(.*?)\s*$")
_OPEN = re.compile(r"^\s*([A-Za-z0-9_.:-]+)\s*\{\s*$")


def migrate(text: str) -> tuple[str, Report]:
    """Converts a single config file; returns (new text, report)."""
    report = Report()
    out: list[str] = []
    stack: list[str] = []
    gestures: list[str] = []
    trailing: list[str] = []          # lines that must go at the root, outside any section
    # Block-style rules ("windowrule { ... }") need a name as the first key in
    # Hyprland 0.56; an unnamed block gets a numbered name.
    rule_blocks = 0
    needs_name = False
    fingers = "3"
    match = re.search(r"workspace_swipe_fingers\s*=\s*(\d+)", text)
    if match:
        fingers = match.group(1)
    for lineno, line in enumerate(text.splitlines(), 1):
        code, hash_, comment = line.partition("#")
        # "##" is an escape in Hyprland; color values contain no "#" (they use rgb()/0x).
        opened = _OPEN.match(code)
        if opened:
            stack.append(opened.group(1))
            out.append(line)
            needs_name = opened.group(1) in ("windowrule", "layerrule")
            continue
        if code.strip() == "}":
            if stack:
                stack.pop()
            out.append(line)
            continue
        match = _ASSIGN.match(code)
        if not match:
            out.append(line)
            continue
        indent, key, value = match.groups()
        full = ":".join([*stack, key]) if stack else key
        tail = f" #{comment}" if hash_ else ""

        if needs_name:
            needs_name = False
            if key != "name":
                rule_blocks += 1
                out.append(f"{indent}name = hyprsetup-{stack[-1]}-{rule_blocks}")
                report.changed.append(f"{lineno}: added a name to the {stack[-1]} block")
        if stack and stack[-1] in ("windowrule", "layerrule") and key == "no_border":
            size = "0" if value.strip().lower() in ("on", "1", "true", "yes") else "-1"
            out.append(f"{indent}border_size = {size}{tail}")
            report.changed.append(f"{lineno}: no_border → border_size")
            continue

        if full in _RENAMED:
            out.append(f"{indent}{_RENAMED[full]} = {value}{tail}")
            report.changed.append(f"{lineno}: {full} → {_RENAMED[full]}")
            continue
        if key in _XKB_KEYS and value.strip() in ('""', "''"):
            # hyprlang treats quotes as part of the value: kb_variant = "" sends two
            # quote characters to xkb and the layout fails to compile ("Invalid
            # keyboard layout passed"; ilyamiro: us,ru). An empty value is meant.
            out.append(f"{indent}{key} ={tail}")
            report.changed.append(f"{lineno}: {key} = \"\" → empty")
            continue
        if full in ("decoration:blur:blurls", "blurls"):
            # The old "blur this layer" list (and the even older top-level
            # "blurls =" keyword) → a layer rule (at the root).
            out.append(f"{indent}# [hyprsetup] blurls → layerrule at the end of the file")
            trailing.append(f"layerrule = blur on, match:namespace {value}")
            report.changed.append(f"{lineno}: blurls → layerrule")
            continue
        if full in _REMOVED:
            out.append(f"{indent}# [hyprsetup] {_REMOVED[full]}: {code.strip()}")
            report.disabled.append(f"{lineno}: {full}")
            continue
        if full == "gestures:workspace_swipe":
            # Old on/off → new gesture line (3-finger horizontal workspace swipe).
            # "gesture =" is defined at the root, not inside a section: the line is
            # appended at the end of the file, and only a marker is left here.
            if value.strip().lower() in ("true", "1", "yes", "on"):
                out.append(f"{indent}# [hyprsetup] workspace_swipe → 'gesture =' "
                           f"line at the end of the file")
                report.changed.append(f"{lineno}: workspace_swipe → gesture")
                gestures.append(f"gesture = {fingers}, horizontal, workspace")
            else:
                out.append(f"{indent}# [hyprsetup] removed: {code.strip()}")
            continue
        if _BIND.match(key) and not stack:
            # "bindd" carries a description field: mod, key, description, dispatcher.
            desc = 1 if "d" in key.strip()[4:] else 0
            parts = value.split(",", 3 + desc)
            d = 2 + desc
            if len(parts) >= d + 1 and parts[d].strip() in _LAYOUTMSG:
                args = parts[d + 1].strip() if len(parts) == d + 2 else ""
                msg = f"{parts[d].strip()} {args}".strip()
                head = ", ".join(p.strip() for p in parts[:d])
                out.append(f"{indent}{key} = {head}, layoutmsg, {msg}{tail}")
                report.changed.append(f"{lineno}: {parts[d].strip()} → layoutmsg")
                continue
        if full in ("windowrulev2", "windowrule"):
            if "match:" in value:
                out.append(line)
                continue
            new = _windowrule(value, full == "windowrulev2")
            if new is None:
                out.append(f"{indent}# [hyprsetup] could not convert: {code.strip()}")
                report.disabled.append(f"{lineno}: {code.strip()}")
            else:
                out.append(f"{indent}{new}{tail}")
                report.changed.append(f"{lineno}: {key}")
            continue
        if full == "layerrule":
            if "match:" in value:
                out.append(line)
                continue
            new = _layerrule(value)
            if new is None:
                out.append(f"{indent}# [hyprsetup] could not convert: {code.strip()}")
                report.disabled.append(f"{lineno}: {code.strip()}")
            else:
                out.append(f"{indent}{new}{tail}")
                report.changed.append(f"{lineno}: layerrule")
            continue
        out.append(line)
    if gestures:
        out.append("")
        out.append("# [hyprsetup] replacement for the old gestures:workspace_swipe")
        out.extend(dict.fromkeys(gestures))
    if trailing:
        out.append("")
        out.append("# [hyprsetup] replacement for the old decoration:blur:blurls")
        out.extend(dict.fromkeys(trailing))
    return "\n".join(out) + ("\n" if text.endswith("\n") else ""), report


# ------------------------------------------------------------- hyprpaper ---
#: Top-level keys hyprpaper 0.8 recognizes (src/config/ConfigManager).
_HYPRPAPER_KEYS = {"splash", "splash_offset", "splash_opacity", "ipc", "source"}
_HYPRPAPER_FIT = {"contain": "contain", "cover": "cover", "tile": "tile",
                  "fill": "fill", "fit": "fill"}


def migrate_hyprpaper(text: str) -> tuple[str, Report]:
    """Converts hyprpaper.conf to the 0.8 syntax.

    0.8 removed "preload" and wants a ``wallpaper { monitor = …; path = …;
    fit_mode = … }`` block instead of "wallpaper = monitor, path"; on any line it
    does not recognize, it treats the config as invalid and shows no wallpaper.
    """
    report = Report()
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        key, sep, value = line.partition("=")
        key = key.strip().lower()
        if not sep or line.startswith("#") or key.startswith("$"):
            out.append(raw)
            continue
        value = value.strip()
        if key == "wallpaper":
            monitor, _c, path = value.partition(",")
            path = path.strip()
            fit = "cover"
            prefix, colon, rest = path.partition(":")
            if colon and prefix in _HYPRPAPER_FIT:
                fit, path = _HYPRPAPER_FIT[prefix], rest.strip()
            out += ["wallpaper {", f"    monitor = {monitor.strip()}",
                    f"    path = {path}", f"    fit_mode = {fit}", "}"]
            report.changed.append(line)
        elif key in _HYPRPAPER_KEYS:
            out.append(raw)
        else:
            # preload, unload, splash_color… do not exist in 0.8.
            out.append(f"# hyprsetup: not in hyprpaper 0.8 — {line}")
            report.disabled.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else ""), report
