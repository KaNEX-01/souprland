"""settings.conf format: KEY="value" lines — writing, reading, normalizing.

The file is read in two places: the settings app parses it as TEXT, while bash
(lib/config.sh:config_load) used to ``source`` it directly. Because values were
written unescaped as ``KEY="value"``, any value containing quotes or ``$`` (e.g. a
bar custom-module command like ``echo "$(date)"``) broke on the bash side — and
worse, the command inside ran while the file was being READ.

The rule now lives in one place:

* :func:`quote` — a readable ``"value"`` if there are no special characters,
  otherwise single quotes where the shell expands nothing (``'...'``, inner ``'``
  → ``'\\''``). lib/config.sh:_conf_quote applies the same rule.
* :func:`unquote` — reads both the new format and the old unescaped one correctly.
* lib/config.sh:_conf_read — the bash-side reader; same rule, reads the file
  WITHOUT source/eval.
"""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path

LINE_RE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)$')

#: Characters bash interprets inside double quotes.
_SPECIAL = re.compile(r'["$`\\]')

#: End-of-line comment after the value: ``LAYOUT="dwindle"   # dwindle | master``.
#: It only counts as a comment when whitespace + ``#`` comes AFTER a single-token
#: value (quoted or without spaces); a ``#`` inside quotes, as in ``"#ff0000"``, is
#: part of the value. lib/config.sh:_conf_read applies the same rule.
_TRAILING_COMMENT = re.compile(r'''^("[^"]*"|'[^']*'|[^\s"']+)\s+#''')


def strip_comment(raw: str) -> str:
    match = _TRAILING_COMMENT.match(raw.strip())
    return match.group(1) if match else raw


def quote(value: str) -> str:
    """Spelling of the value that bash reads back verbatim."""
    value = value or ""
    if not _SPECIAL.search(value):
        return f'"{value}"'
    return "'" + value.replace("'", "'\\''") + "'"


def unquote(raw: str) -> str:
    """Turns the part of the line after ``=`` into the value.

    The old writer did not escape: in lines like ``KEY="echo "x""`` the inner double
    quotes are left as-is. Parsed with shell rules, those quotes would be lost; so the
    old format is recognized and the content is taken verbatim.
    """
    raw = strip_comment(raw).strip()
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        inner = raw[1:-1]
        if re.search(r'(?<!\\)"', inner) or "$" in inner or "`" in inner:
            # Old, unescaped format. A hand-written "$HOME/..." used to be
            # expanded by bash; only that is preserved — nothing else (commands,
            # variables) is executed.
            home = os.environ.get("HOME", "")
            return inner.replace("${HOME}", home).replace("$HOME", home)
    try:
        parts = shlex.split(raw, posix=True)
    except ValueError:
        parts = None
    if parts is None:
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
            return raw[1:-1]
        return raw
    return " ".join(parts)


def parse_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = LINE_RE.match(line)
        if match:
            values[match.group(1)] = unquote(match.group(2))
    return values


def parse_file(path: Path) -> dict[str, str]:
    try:
        return parse_text(Path(path).read_text(encoding="utf-8"))
    except OSError:
        return {}


def line(key: str, value: str) -> str:
    return f"{key}={quote(value)}"

