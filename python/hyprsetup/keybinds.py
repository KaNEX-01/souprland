"""Keybindings — the ``config/keybinds.json`` catalog.

The JSON file is the single source of truth; the ``keybinds.conf`` lines, the
Keybindings page in the GUI and the ``--list-keybinds`` output are all generated
from it. User overrides are kept in the ``KEYBINDS`` setting::

    KEYBINDS="terminal=MOD+T;;lock=MOD+CTRL+L;;color-picker="

An empty value removes that keybinding entirely. Key combo format::

    MOD+SHIFT+L      MOD = MOD_KEY from settings.conf (default SUPER)
    Print            no modifier
    MOD+mouse:272    mouse button
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

# The order defines the canonical spelling of combos: MOD+SUPER+CTRL+ALT+SHIFT+key
# MOD is the abstract key standing in for MOD_KEY; SUPER is the Windows key itself
# (so Super can still get keybindings when MOD_KEY is moved to another key).
MODIFIERS = ("MOD", "SUPER", "CTRL", "ALT", "SHIFT")
FLAG_SUFFIXES = ("", "e", "l", "el", "m", "r", "rnt")

#: Keybinding of the ALT+Tab switcher. Releasing its modifier (ALT) makes the
#: selection; Hyprland itself reports the release (see release_combos).
SWITCHER_BIND = "window-switcher"
_MOD_KEYSYMS = {"ALT": "Alt", "SUPER": "Super", "CTRL": "Control", "SHIFT": "Shift"}

_COMBO_KEY = re.compile(r"^[A-Za-z0-9_:+\-]+$")


@dataclass
class Bind:
    id: str
    title: str
    keys: str                      # default key combo
    dispatcher: str = ""
    args: str = ""
    flags: str = ""                # "" | e | l | el | m
    require: str = ""
    editable: bool = True
    category: str = ""             # category id
    category_title: str = ""
    hidden: bool = False           # generated but not shown on the cheatsheet

    @property
    def action(self) -> str:
        """For humans: "exec kitty" / "movefocus l"."""
        return f"{self.dispatcher} {self.args}".strip()


@dataclass
class Category:
    id: str
    title: str
    binds: list[Bind] = field(default_factory=list)


@dataclass
class Keybinds:
    categories: list[Category] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> "Keybinds":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        categories = []
        for cat in raw.get("categories", []):
            binds = [
                Bind(
                    id=item["id"],
                    title=item.get("title", item["id"]),
                    keys=item.get("keys", ""),
                    dispatcher=item.get("dispatcher", ""),
                    args=item.get("args", ""),
                    flags=item.get("flags", ""),
                    require=item.get("require", ""),
                    editable=item.get("editable", True),
                    category=cat["id"],
                    category_title=cat.get("title", cat["id"]),
                )
                for item in cat.get("binds", [])
            ]
            categories.append(Category(id=cat["id"],
                                       title=cat.get("title", cat["id"]),
                                       binds=binds))
        return cls(categories=categories)

    def all(self) -> list[Bind]:
        return [b for c in self.categories for b in c.binds]

    def by_id(self) -> dict[str, Bind]:
        return {b.id: b for b in self.all()}


def default_path(root: Path) -> Path:
    return Path(root) / "config" / "keybinds.json"


def load_default(root: Path) -> Keybinds:
    """The repo's keybinding set; an empty set if the file is missing."""
    path = default_path(root)
    return Keybinds.load(path) if path.is_file() else Keybinds()


# --------------------------------------------------------- override string --
def parse_overrides(spec: str) -> dict[str, str]:
    """``"terminal=MOD+T;;lock="`` → ``{"terminal": "MOD+T", "lock": ""}``"""
    out: dict[str, str] = {}
    for item in (spec or "").split(";;"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        key, _, value = item.partition("=")
        key = key.strip()
        if key:
            out[key] = value.strip()
    return out


def format_overrides(overrides: dict[str, str]) -> str:
    return ";;".join(f"{key}={overrides[key]}" for key in sorted(overrides))


def valid_combo(combo: str) -> bool:
    """An empty string (remove the keybinding) is valid too."""
    combo = (combo or "").strip()
    if not combo:
        return True
    parts = combo.split("+")
    key = parts[-1]
    if not key or not _COMBO_KEY.match(key):
        return False
    return all(part in MODIFIERS for part in parts[:-1])


def normalize(combo: str) -> str:
    """Puts modifiers in a fixed order: MOD+SUPER+CTRL+ALT+SHIFT+key."""
    combo = (combo or "").strip()
    if not combo:
        return ""
    parts = [p.strip() for p in combo.split("+") if p.strip()]
    if not parts:
        return ""
    key = parts[-1]
    mods = [m for m in MODIFIERS if m in parts[:-1]]
    return "+".join(mods + [key])


def display(combo: str, mod_key: str = "SUPER") -> str:
    """Readable form for the UI: ``SUPER + SHIFT + L``."""
    if not combo:
        return "—"
    parts = combo.split("+")
    return " + ".join(mod_key if p == "MOD" else p for p in parts)


# -------------------------------------------------------------- resolution ----
@dataclass
class ResolvedBind:
    bind: Bind
    keys: str                      # combo with overrides applied
    args: str                      # {{...}} placeholders filled in

    @property
    def id(self) -> str:
        return self.bind.id

    @property
    def line(self) -> str:
        """Hyprland ``bind`` line ($mod is defined in the conf)."""
        parts = self.keys.split("+")
        key = parts[-1]
        mods = " ".join("$mod" if m == "MOD" else m for m in parts[:-1])
        flags = self.bind.flags if self.bind.flags in FLAG_SUFFIXES else ""
        line = f"bind{flags} = {mods}, {key}, {self.bind.dispatcher}"
        if self.args:
            return f"{line}, {self.args}"
        # Dispatchers without arguments are written with an empty argument (like
        # "killactive,"); for mouse bindings (bindm) the trailing comma is invalid.
        return line if flags == "m" else f"{line},"

    def lua_line(self, mod_key: str) -> str:
        """``hl.bind(...)`` line for the Hyprland Lua config.

        The dispatcher name is translated to a known ``hl.dsp.*`` equivalent; those
        without one (e.g. centerwindow, resizeactive) are called via ``hyprctl
        dispatch`` — that always works at runtime whatever the dispatcher, it just
        is not "native" Lua sugar.
        """
        combo = _lua_combo(self.keys, mod_key)
        call = _lua_dispatch_call(self.bind.dispatcher, self.args)
        opts = _lua_opts(self.bind.flags)
        return f"hl.bind({_lua_str(combo)}, {call}{opts})"


def release_combos(keys: str, mod_key: str = "SUPER") -> list[str]:
    """Keys for RELEASING the switcher keybinding's modifier: "ALT+Tab" →
    ``["ALT+Alt_L", "ALT+Alt_R"]``.

    The switcher selects when ALT is released, but only the focused window
    receives the release event. In a fullscreen game (War Thunder) the switcher
    might never get focus, or ALT is released before it does: the event went to
    the game, the switcher stayed stuck on screen and every later Tab cycled it.
    Hyprland's ``bindrnt`` keybinding catches the release regardless of focus
    (r: on release, n: the event also reaches the window, t: not shadowed by
    other keybindings) and still fires after ALT+Tab.
    """
    parts = (keys or "").split("+")
    if len(parts) < 2:
        return []
    first = parts[0]
    name = _MOD_KEYSYMS.get((mod_key or "SUPER").upper() if first == "MOD" else first)
    if not name:
        return []
    prefix = "+".join(parts[:-1])
    return [f"{prefix}+{name}_L", f"{prefix}+{name}_R"]


def resolve(keybinds: Keybinds, variables: dict[str, str],
            overrides: str | dict[str, str] = "",
            condition=None) -> list[ResolvedBind]:
    """Builds the list of active keybindings from the catalog.

    Without ``condition``, ``require`` expressions are evaluated with the template
    engine's rules. Removed keybindings (overridden with an empty combo) and those
    whose condition is not met are left out.
    """
    from .render import eval_condition, render_text   # no circular import

    if isinstance(overrides, str):
        overrides = parse_overrides(overrides)
    if condition is None:
        def condition(expr: str) -> bool:
            return eval_condition(expr, variables)

    resolved: list[ResolvedBind] = []
    for bind in keybinds.all():
        keys = normalize(overrides.get(bind.id, bind.keys))
        if not keys:
            continue
        if bind.require and not condition(bind.require):
            continue
        resolved.append(ResolvedBind(bind=bind, keys=keys,
                                     args=render_text(bind.args, variables)))
        if bind.id == SWITCHER_BIND:
            release = replace(bind, id=f"{bind.id}-release", flags="rnt",
                              title="Select on switcher release", hidden=True,
                              editable=False)
            for combo in release_combos(keys, variables.get("MOD_KEY", "SUPER")):
                resolved.append(ResolvedBind(
                    bind=release, keys=combo,
                    args=render_text(f"{bind.args} release", variables)))
    return resolved


def to_lines(resolved: list[ResolvedBind], lang: str = "conf",
             mod_key: str = "SUPER") -> str:
    """Body of keybinds.conf / hyprland/keybinds.lua — with category headers."""
    if lang == "lua":
        comment, body = "--", (lambda item: item.lua_line(mod_key))
    else:
        comment, body = "#", (lambda item: item.line)

    lines: list[str] = []
    current = ""
    for item in resolved:
        if item.bind.category != current:
            current = item.bind.category
            title = item.bind.category_title
            if lines:
                lines.append("")
            lines.append(f"{comment} --- {title} " + "-" * max(0, 56 - len(title)))
        lines.append(body(item))
    return "\n".join(lines)


# ------------------------------------------------------------------- Lua ----
# Hyprland's Lua config has no runtime variable like $mod
# (see https://wiki.hypr.land/Configuring/Start/) — the actual MOD_KEY value is
# embedded in the text. For the dispatcher translation table see _lua_dispatch_call.
def _lua_combo(keys: str, mod_key: str) -> str:
    return " + ".join(mod_key if p == "MOD" else p for p in keys.split("+"))


def _lua_str(value: str) -> str:
    escaped = (value or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _lua_workspace_value(args: str) -> str:
    # Workspace IDs are always positive; any value starting with + / - (e.g.
    # "+1", "-1") is the special relative syntax and must be passed as a STRING,
    # not a raw Lua number — otherwise Hyprland may take it for an invalid absolute
    # workspace ID "-1" (the "-1" scroll-wheel bind must behave consistently with
    # "+1"/"m+1").
    args = (args or "").strip()
    return args if re.fullmatch(r"\d+", args) else _lua_str(args)


def _lua_opts(flags: str) -> str:
    opts = []
    if "e" in flags:
        opts.append("repeating = true")
    if "l" in flags:
        opts.append("locked = true")
    if "m" in flags:
        opts.append("mouse = true")
    if "r" in flags:
        opts.append("release = true")
    if "n" in flags:
        opts.append("non_consuming = true")
    if "t" in flags:
        opts.append("transparent = true")
    return ", { " + ", ".join(opts) + " }" if opts else ""


# Known dispatcher -> hl.dsp.* translation. When a new dispatcher is added without
# an equivalent here, it automatically falls back to 'hyprctl dispatch' (the final
# branch below), so a missing translation never produces invalid Lua.
def _lua_dispatch_call(dispatcher: str, args: str) -> str:
    args = (args or "").strip()

    if dispatcher == "exec":
        return f"hl.dsp.exec_cmd({_lua_str(args)})"
    if dispatcher == "killactive":
        return "hl.dsp.window.close()"
    if dispatcher == "togglefloating":
        return 'hl.dsp.window.float({ action = "toggle" })'
    if dispatcher == "pin":
        return "hl.dsp.window.pin()"
    if dispatcher == "pseudo":
        return "hl.dsp.window.pseudo()"
    if dispatcher == "layoutmsg":
        return f"hl.dsp.layout({_lua_str(args)})"
    if dispatcher == "fullscreen":
        mode = "maximized" if args == "1" else "fullscreen"
        return f'hl.dsp.window.fullscreen({{ mode = "{mode}", action = "toggle" }})'
    if dispatcher == "movefocus":
        return f'hl.dsp.focus({{ direction = "{args}" }})'
    if dispatcher == "movewindow":
        if not args:
            return "hl.dsp.window.drag()"          # move with the mouse (flags: m)
        return f'hl.dsp.window.move({{ direction = "{args}" }})'
    if dispatcher == "resizewindow":
        return "hl.dsp.window.resize()"             # resize with the mouse (flags: m)
    if dispatcher == "workspace":
        return f"hl.dsp.focus({{ workspace = {_lua_workspace_value(args)} }})"
    if dispatcher == "movetoworkspace":
        return f"hl.dsp.window.move({{ workspace = {_lua_workspace_value(args)} }})"
    if dispatcher == "togglespecialworkspace":
        return f"hl.dsp.workspace.toggle_special({_lua_str(args or 'special')})"
    if dispatcher == "exit":
        return 'hl.dsp.exec_cmd("hyprctl dispatch exit")'

    # centerwindow, resizeactive and anything not mapped yet: fall back to hyprctl.
    # The dispatcher runs over IPC, independent of the config language.
    cmd = f"hyprctl dispatch {dispatcher}" + (f" {args}" if args else "")
    return f"hl.dsp.exec_cmd({_lua_str(cmd)})"


# ---------------------------------------------------------------- profiles ---
# When a profile (rice.py) replaces ~/.config/hypr with the author's, this
# project's keybinds.conf is never loaded: on every profile switch the keybindings
# revert to the author's and our own modules like ALT+Tab disappear. Instead, the
# generated keybindings are appended as an overlay at the END of the author's
# config: before each keybinding the author's binding for the same key is removed
# (Hyprland runs both when a key is bound twice), and the author's non-conflicting
# keybindings (their own shell's panels) stay.
RICE_OVERLAY_CONF = "hyprsetup-keybinds.conf"
RICE_OVERLAY_LUA = "hyprsetup_keybinds.lua"      # require() name: no hyphens allowed
RICE_SCRIPTS = "hyprsetup/scripts"               # under ~/.config/hypr
ENV_IMPORT = "dbus-update-activation-environment --systemd --all"

# Keyboard settings go into the same overlay: the author's input block brings their
# own layout and options (e.g. caps:escape → Caps becomes an Esc that clears what
# you typed in the terminal). Empty model/rules are reset too, so the author's
# values do not linger.
KEYBOARD_KEYS = ("kb_layout", "kb_variant", "kb_model", "kb_rules", "kb_options",
                 "repeat_delay", "repeat_rate", "numlock_by_default")
_KEYBOARD_LINE = re.compile(r"^\s*(" + "|".join(KEYBOARD_KEYS) + r")\s*=(.*)$", re.M)


def app_window_rules(rules_text: str, lang: str = "conf") -> list[str]:
    """The rules for this project's own windows, taken from the generated rules.

    The ALT+Tab switcher, the keybinding cheatsheet and the SUPER+I panel must open
    floating, centered and (for the switcher) without animation. The rules live in
    windowrules.conf; when a profile takes over the Hyprland config, that file is
    never loaded and the switcher opened like an ordinary tiled window. The overlay
    carries these lines.
    """
    if lang != "lua":
        return [line.strip() for line in rules_text.splitlines()
                if re.match(r"^\s*windowrule\s*=", line) and "dev\\.hyprsetup" in line]
    blocks, start = [], 0
    while (start := rules_text.find("hl.window_rule(", start)) != -1:
        depth, i = 0, start + len("hl.window_rule")
        while i < len(rules_text):
            if rules_text[i] == "(":
                depth += 1
            elif rules_text[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        block = rules_text[start:i + 1]
        if "dev\\\\.hyprsetup" in block:
            # Comment lines are not carried into the overlay.
            blocks.append("\n".join(line for line in block.splitlines()
                                    if not line.strip().startswith("--")))
        start = i + 1
    return blocks


def window_rules_to_lua(lines: list[str]) -> list[str]:
    """Converts conf rules (app_window_rules) to Lua — Lua templates are only
    generated with HYPR_LANG=lua, so a conf session has no Lua rules, but the
    overlay of a Lua-based profile still needs them."""
    grouped: dict[str, dict[str, str]] = {}
    for line in lines:
        match = re.match(r"^\s*windowrule\s*=\s*(.+?),\s*match:class\s+(\S+)\s*$", line)
        if not match:
            continue
        rule, pattern = match.groups()
        name, _, value = rule.strip().partition(" ")
        value = value.strip()
        fields = grouped.setdefault(pattern, {})
        fields[name] = "true" if value == "on" else _lua_str(value)
    out = []
    for index, (pattern, fields) in enumerate(grouped.items()):
        body = ", ".join(f"{k} = {v}" for k, v in fields.items())
        out.append(f'hl.window_rule({{ name = "hyprsetup-app-{index}", '
                   f"match = {{ class = {_lua_str(pattern)} }}, {body} }})")
    return out


def keyboard_settings(config_text: str) -> dict[str, str]:
    """Keyboard values from the input block of the generated hyprland.conf/.lua."""
    found: dict[str, str] = {}
    for key, value in _KEYBOARD_LINE.findall(config_text):
        value = re.split(r"\s(?:#|--)", " " + value)[0].strip()
        found[key] = value.rstrip(",").strip().strip('"')
    if "kb_layout" not in found:
        return {}
    return {key: found.get(key, "") for key in KEYBOARD_KEYS}


_CONF_BIND = re.compile(r"^\s*bind([a-z]*)\s*=\s*([^,]*),\s*([^,]+?)\s*,\s*([^,]+?)\s*(?:,\s*(.*?))?\s*$")


# OSDs the author binds to lock keys (ilyamiro: "bindl = , Caps_Lock,
# exec, swayosd-client --caps-lock"). A Hyprland keybinding does not pass the key on
# to the app: games never saw Caps. The overlay rebinds these with the "n"
# (non-consuming) flag — the OSD works and the key still reaches the app.
LOCK_KEYS = ("Caps_Lock", "Num_Lock", "Scroll_Lock")
_LOCK_BIND = re.compile(r"^\s*bind([a-z]*)\s*=\s*,\s*(" + "|".join(LOCK_KEYS)
                        + r")\s*,(.*)$", re.M | re.I)


def lock_key_binds(config_text: str) -> list[str]:
    """The author's modifier-less lock key bindings, in non-consuming form."""
    out: list[str] = []
    for flags, key, rest in _LOCK_BIND.findall(config_text):
        if "n" in flags:
            continue
        line = f"bind{flags}n = , {key},{rest.rstrip()}"
        if line not in out:
            out += [f"unbind = , {key}", line]
    return out


_ANY_BIND_KEY = re.compile(r"^\s*bind[a-z]*\s*=\s*[^,]*,\s*([^,]+?)\s*,", re.M)
# In Lua the key string can be built from variables: hl.bind(mainMod .. " + Return", …).
# The key is what follows the last "+" of the last string piece before the first comma.
_LUA_BIND_KEY = re.compile(r"hl\.bind\(\s*([^,]+?)\s*,")


def author_key_spellings(config_text: str) -> dict[str, set[str]]:
    """Key names in the author's keybindings, keyed by their lowercase form.

    Hyprland's unbind compares key names CASE-sensitively: the author's
    "bind = ALT, TAB, …" line was not removed by the overlay's "unbind = ALT, Tab",
    and ALT+Tab opened two switchers at once (ilyamiro).
    """
    found: dict[str, set[str]] = {}
    for key in _ANY_BIND_KEY.findall(config_text):
        found.setdefault(key.strip().lower(), set()).add(key.strip())
    for combo in _LUA_BIND_KEY.findall(config_text):
        literals = re.findall(r"[\"']([^\"']*)[\"']", combo)
        if not literals:
            continue
        key = literals[-1].split("+")[-1].strip()
        if not key:
            continue
        found.setdefault(key.lower(), set()).add(key)
    return found


def _key_spellings(key: str, author: dict[str, set[str]]) -> list[str]:
    """Spellings to unbind: ours, common variants, and the author's."""
    out = [key]
    for variant in (key.upper(), key.lower(), key.capitalize(),
                    *sorted(author.get(key.lower(), ()))):
        if variant not in out:
            out.append(variant)
    return out


# The user's keybindings must COMPLETELY win under a profile (user request
# 2026-09-25): all of the author's keyboard bindings are removed and only this
# project's remain. E.g. caelestia binds a launcher to SUPER alone
# ("bindi = Super, Super_L") and listens to every SUPER combo with "catchall".
# Mouse bindings (drag, wheel) are not keyboard shortcuts and are left alone.
_MOD_BITS = (("SHIFT", 1), ("CAPS", 2), ("LOCK", 2), ("CTRL", 4), ("CONTROL", 4),
             ("ALT", 8), ("MOD1", 8), ("MOD2", 16), ("MOD3", 32), ("SUPER", 64),
             ("WIN", 64), ("LOGO", 64), ("MOD4", 64), ("META", 64), ("MOD5", 128))


def _mod_mask(mods: str) -> int:
    upper = mods.upper()
    mask = 0
    for name, bit in _MOD_BITS:
        if name in upper:
            mask |= bit
    return mask


def _is_mouse_key(key: str) -> bool:
    """Keys that are not cleared: mouse bindings and hardware function keys (XF86
    volume, brightness, media, keyboard backlight) — not shortcuts, the key's own job."""
    return key.lower().startswith(("mouse", "xf86"))


def author_binds(config_text: str, submaps: list[str] | tuple[str, ...] = ()
                 ) -> list[tuple[str, str]]:
    """The author's keyboard bindings: (modifiers, key), with variables resolved.

    conf: variables like "$mainMod = SUPER" and "$kbTerminal = Super, T" are
    substituted before the line is parsed. Only bindings in the default map and in
    always-active submaps (``submaps``) are taken; the author's submaps entered via
    a keybinding (e.g. resize) become unreachable anyway once that keybinding is
    gone. Lua: the first argument of hl.bind, as far as string variables
    (mainMod = "SUPER") can be resolved.
    """
    variables = dict(re.findall(r"^\s*\$(\w+)\s*=\s*(.*?)\s*$", config_text, re.M))

    def resolve(text: str) -> str:
        for _ in range(5):
            new = re.sub(r"\$(\w+)", lambda m: variables.get(m.group(1), m.group(0)), text)
            if new == text:
                break
            text = new
        return text

    found: list[tuple[str, str]] = []
    active = {"", *submaps}
    submap = ""
    for raw in config_text.splitlines():
        line = re.split(r"\s#", " " + raw)[0].strip()
        m = re.match(r"^submap\s*=\s*(\S+)", line)
        if m:
            submap = "" if m.group(1) == "reset" else m.group(1)
            continue
        m = re.match(r"^bind[a-z]*\s*=\s*(.*)$", line)
        if not m or submap not in active:
            continue
        parts = [part.strip() for part in resolve(m.group(1)).split(",")]
        if len(parts) < 2 or not parts[1] or "$" in parts[0] + parts[1]:
            continue
        if not _is_mouse_key(parts[1]) and (parts[0], parts[1]) not in found:
            found.append((parts[0], parts[1]))
    strings = dict(re.findall(r"^\s*(?:local\s+)?(\w+)\s*=\s*[\"']([^\"']*)[\"']",
                              config_text, re.M))
    for expr in _LUA_BIND_KEY.findall(config_text):
        pieces = []
        for token in re.split(r"\s*\.\.\s*", expr.strip()):
            literal = re.fullmatch(r"[\"']([^\"']*)[\"']", token)
            if literal:
                pieces.append(literal.group(1))
            elif token in strings:
                pieces.append(strings[token])
            else:
                pieces = []
                break
        if not pieces:
            continue
        combo = [part.strip() for part in "".join(pieces).split("+")]
        mods, key = " ".join(p for p in combo[:-1] if p), combo[-1]
        if key and not _is_mouse_key(key) and (mods, key) not in found:
            found.append((mods, key))
    return found


def rice_script_paths(text: str) -> str:
    """Path of the project's scripts → a place that does not clash with the author's scripts/."""
    for prefix in ("~/.config/hypr/scripts/", "$HOME/.config/hypr/scripts/"):
        text = text.replace(prefix, prefix.replace("scripts/", RICE_SCRIPTS + "/"))
    return text


def rice_overlay(keybinds_conf: str, lang: str = "conf",
                 preload: str | list[str] = "", move_scripts: bool = True,
                 submaps: list[str] | tuple[str, ...] = (),
                 keyboard: dict[str, str] | None = None,
                 window_rules: list[str] | tuple[str, ...] = (),
                 lock_binds: list[str] | tuple[str, ...] = (),
                 author_keys: dict[str, set[str]] | None = None,
                 clear_binds: list[tuple[str, str]] | tuple[tuple[str, str], ...] = (),
                 known_combos: list[str] | tuple[str, ...] = ()) -> str:
    """Profile overlay (conf or Lua) built from the generated keybinds.conf.

    ``preload``: command to run at session start (the pre-started ALT+Tab
    instance); omitted if empty. ``move_scripts``: script paths are redirected to a
    separate folder only if the profile owns the hypr folder.
    ``submaps``: submaps the author's config keeps permanently active (caelestia:
    "global" — all its keybindings live there and it switches to it on every load).
    Since a keybinding only works while its own submap is active, the same lines
    are written into those submaps too; otherwise the overlay never worked.
    ``keyboard``: the user's keyboard settings (keyboard_settings); written over
    the author's input block. ``lock_binds``: output of lock_key_binds (conf only;
    if the user bound the same key, theirs wins).
    ``author_keys``: output of author_key_spellings; the author's keybindings for
    the same key in a different letter case are removed too.
    ``clear_binds``: output of author_binds — all of the author's keyboard bindings
    are removed. Exception: keys whose command this project generated empty (the
    profile brings that category, e.g. the launcher) keep the author's function.
    ``known_combos``: every key this project knows ("MOD+D"); those not generated
    because their condition is unmet (volume keys, clipboard) also keep the
    author's function.
    """
    mod = "SUPER"
    match = re.search(r"^\s*\$mod\s*=\s*(\S+)", keybinds_conf, re.M)
    if match:
        mod = match.group(1)
    lua = lang == "lua"
    c = "--" if lua else "#"
    out = [f"{c} hyprsetup: your keybindings, layered on top of the profile.",
           f"{c} This file is generated; change keybindings on the settings app's",
           f"{c} Keybindings page. The author's binding on the same key is removed first.",
           ""]
    body: list[str] = []
    keep: set[tuple[int, str]] = set()
    for raw in keybinds_conf.splitlines():
        m = _CONF_BIND.match(raw.split(" #")[0])
        if not m:
            continue
        flags, mods, key, dispatcher, args = m.groups()
        command = (args or "").strip()
        if dispatcher == "exec" and (not command or command.startswith("|")
                                     or command.endswith("|")
                                     or re.search(r"\|\s*\|", command)):
            # The profile brings that category itself (e.g. the launcher): this
            # project's command was generated empty (no CMD_LAUNCHER). The key keeps
            # the author's function — an empty exec would override and kill it.
            keep.add((_mod_mask(mods.replace("$mod", mod)), key.lower()))
            continue
        mods = " ".join(mod if part == "$mod" else part for part in mods.split())
        args = rice_script_paths(args or "") if move_scripts else (args or "")
        if lua:
            # Mouse drag is ours too: when skipped, profiles whose author does not
            # bind it and the Lua bridge (standard profile) had no SUPER+drag at all.
            combo = " + ".join([*mods.split(), key])
            for spelling in _key_spellings(key, author_keys or {}):
                body.append(f"hl.unbind({_lua_str(' + '.join([*mods.split(), spelling]))})")
            body.append(f"hl.bind({_lua_str(combo)}, "
                        f"{_lua_dispatch_call(dispatcher, args)}{_lua_opts(flags)})")
        else:
            body += [f"unbind = {mods}, {spelling}"
                     for spelling in _key_spellings(key, author_keys or {})]
            line = f"bind{flags} = {mods}, {key}, {dispatcher}"
            body.append(f"{line}, {args}" if args else (line if flags == "m" else f"{line},"))
    rendered: set[tuple[int, str]] = set()
    for raw in keybinds_conf.splitlines():
        m = _CONF_BIND.match(raw.split(" #")[0])
        if m and (_mod_mask(m.group(2).replace("$mod", mod)), m.group(3).lower()) not in keep:
            rendered.add((_mod_mask(m.group(2).replace("$mod", mod)), m.group(3).lower()))
    for combo in known_combos:
        parts = combo.split("+")
        mask = _mod_mask(" ".join(mod if p == "MOD" else p for p in parts[:-1]))
        if (mask, parts[-1].lower()) not in rendered:
            keep.add((mask, parts[-1].lower()))
    clear = [(mods, key) for mods, key in clear_binds
             if (_mod_mask(mods), key.lower()) not in keep]
    if clear:
        body[:0] = [f"{c} Author's keybindings: only yours apply."] + [
            f"hl.unbind({_lua_str(' + '.join([*mods.split(), key]))})" if lua
            else f"unbind = {mods}, {key}" for mods, key in clear] + [""]
    if not lua:
        body += [line for line in lock_binds
                 if f"unbind = , {line.split(',')[1].strip()}" not in body]
    if lua:
        out += body
    else:
        # The author's file may end without closing a submap block (caelestia); the
        # overlay is always written into the default map.
        out.append("submap = reset")
        out += body
        for name in submaps:
            out += ["", f"# Submap the author keeps permanently active: {name}",
                    f"submap = {name}", *body, "submap = reset"]
    if window_rules:
        out += ["", f"{c} This project's windows (ALT+Tab, cheatsheet, SUPER+I panel):",
                *window_rules]
    if keyboard:
        out += ["", f"{c} Keyboard: your layout and options (not the author's)."]
        if lua:
            fields = []
            for key, value in keyboard.items():
                if key.startswith("kb_"):
                    fields.append(f"{key} = {_lua_str(value)}")
                elif value:
                    fields.append(f"{key} = {value}")
            out.append("hl.config({ input = { " + ", ".join(fields) + " } })")
        else:
            out.append("input {")
            out += [f"    {key} = {value}".rstrip() for key, value in keyboard.items()
                    if value or key.startswith("kb_")]
            out.append("}")
    # At login the session environment is exported to systemd/D-Bus; some authors
    # skip this, and with a stale DISPLAY left over the keyring's password prompt
    # could not open (apps could not find their saved login).
    out.append("")
    out.append(f'hl.on("hyprland.start", function() hl.exec_cmd({_lua_str(ENV_IMPORT)}) end)'
               if lua else f"exec-once = {ENV_IMPORT}")
    # A single command or a list (pre-started ALT+Tab instance, visualizer…).
    for command in ([preload] if isinstance(preload, str) else list(preload)):
        if not command:
            continue
        out.append(f'hl.on("hyprland.start", function() hl.exec_cmd({_lua_str(command)}) end)'
                   if lua else f"exec-once = {command}")
    return "\n".join(out) + "\n"
