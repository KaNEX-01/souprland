"""Rule builder for the Window Rules page (USER_WINDOWRULES).

The UI picks a window (class, optional title) and a set of effects; this module
turns them into Hyprland 0.51+ rule bodies and parses them back:

    float on, match:class ^(discord)$
    workspace 3 silent, match:class ^(discord)$

Bodies are separated by ``;;`` (same format as WINDOWRULES, see
render._windowrule_lines). Every generated effect was verified with
``Hyprland --verify-config`` on 0.56.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: (effect key, display name). Effects without a value are written with "on".
TOGGLES = (
    ("float", "Float"),
    ("center", "Open centered"),
    ("pin", "Show on every workspace"),
    ("maximize", "Open maximized"),
    ("fullscreen", "Open fullscreen"),
    ("no_blur", "No blur"),
)
_TOGGLE_NAMES = dict(TOGGLES)


@dataclass
class Rule:
    effect: str          # "float on", "workspace 3 silent", "opacity 0.9" …
    match_class: str     # regex, e.g. ^(discord)$
    match_title: str = ""

    def body(self) -> str:
        text = f"{self.effect}, match:class {self.match_class}"
        if self.match_title:
            text += f", match:title {self.match_title}"
        return text

    def describe(self) -> str:
        """Human-readable summary of the rule: "Float", "Open on workspace 3 (silent)"."""
        name, _, rest = self.effect.partition(" ")
        if name in _TOGGLE_NAMES:
            return _TOGGLE_NAMES[name]
        if name == "workspace":
            number, _, flag = rest.partition(" ")
            return f"Open on workspace {number}" + (" (in background)" if flag else "")
        if name == "monitor":
            return f"Open on display {rest}"
        if name == "size":
            return f"Size {rest.replace(' ', '×')}"
        if name == "opacity":
            return f"Opacity {round(float(rest or 1) * 100)}%"
        return self.effect


def exact(value: str) -> str:
    """Turns a class name into an exact-match regex.

    Only regex special characters are escaped (re.escape also turns a space into
    "\\ ", which Hyprland's RE2 may reject). A comma would split the rule body, so
    it is written as \\x2c, which Hyprland expects.
    """
    escaped = re.sub(r"([.^$*+?()\[\]{}|\\])", r"\\\1", value).replace(",", "\\x2c")
    return f"^({escaped})$"


def build(match_class: str, match_title: str = "", *, toggles: set[str] = frozenset(),
          workspace: int = 0, silent: bool = False, monitor: str = "",
          size: tuple[int, int] | None = None, opacity: float = 1.0) -> list[Rule]:
    rules = [Rule(f"{key} on", match_class, match_title)
             for key, _ in TOGGLES if key in toggles]
    if workspace:
        rules.append(Rule(f"workspace {workspace}" + (" silent" if silent else ""),
                          match_class, match_title))
    if monitor:
        rules.append(Rule(f"monitor {monitor}", match_class, match_title))
    if size and size[0] > 0 and size[1] > 0:
        rules.append(Rule(f"size {size[0]} {size[1]}", match_class, match_title))
    if opacity < 0.999:
        rules.append(Rule(f"opacity {opacity:.2f}", match_class, match_title))
    return rules


_BODY = re.compile(r"^(?P<effect>[^,]+),\s*match:class\s+(?P<cls>[^,]+?)"
                   r"(?:,\s*match:title\s+(?P<title>.+))?$")


def parse(value: str) -> list[Rule]:
    """USER_WINDOWRULES → rules; bodies this page did not generate are not skipped,
    they are kept as-is (without a description)."""
    rules = []
    for body in (item.strip() for item in (value or "").split(";;")):
        if not body:
            continue
        match = _BODY.match(body)
        if match:
            rules.append(Rule(match["effect"].strip(), match["cls"].strip(),
                              (match["title"] or "").strip()))
        else:
            rules.append(Rule(body, "", ""))
    return rules


def dump(rules: list[Rule]) -> str:
    return ";;".join(r.body() if r.match_class else r.effect for r in rules)


def label_for(rule: Rule) -> str:
    """Which window the rule is for: ^(discord)$ → discord."""
    match = re.fullmatch(r"\^\((.*)\)\$", rule.match_class or "")
    name = re.sub(r"\\(.)", r"\1", match.group(1)) if match else rule.match_class
    return name + (f" · title {rule.match_title}" if rule.match_title else "")
