"""Process priority fix (CachyOS ananicy-cpp) — SWITCHER_PRIORITY.

CachyOS's ananicy rules classify the display manager (plasmalogin, sddm) as type
"Launcher": nice 16 and the "idle" I/O class. Every process in the session without
a rule of its own inherits this — nearly everything Hyprland starts, including the
pre-started ALT+Tab instance. Unnoticeable on an idle system; but with something
CPU-heavy like a game running, ALT+Tab waits in the queue and shows up late
(measured 2026-10-04: ALT+Tab's own work is ~60 ms, the delay comes from priority).

Modes:

* ``off``      leave alone (default)
* ``alttab``   high priority for the ALT+Tab processes only (process name
               PROC_NAME, which windowswitch.py names itself)
* ``session``  ALT+Tab + normal priority for Hyprland: everything Hyprland starts
               runs at nice 0 / best-effort

The rule file needs root. The settings app does not ask for a password: on change
a terminal opens and the command runs there with sudo (same path as the login
screen page).
"""

from __future__ import annotations

import shlex
import shutil
from pathlib import Path

RULE_PATH = Path("/etc/ananicy.d/99-souprland.rules")
#: Name windowswitch.py takes via prctl(PR_SET_NAME) (15 bytes max).
PROC_NAME = "souprland-alt"
MODES = ("off", "alttab", "session")

_ALTTAB = f'{{ "name": "{PROC_NAME}", "nice": -10, "ioclass": "best-effort", "ionice": 2 }}'
#: We CANNOT override the display manager's own rule (CachyOS: plasmalogin →
#: Launcher): ananicy-cpp silently ignores a second rule with the same name, and
#: which one is read first depends on the filesystem (2026-10-04, tested with
#: unshare). Instead we target the next link in the chain: Hyprland and its starter
#: have no rule, and everything Hyprland starts inherits its nice/ionice values.
#: No "sched" — Hyprland puts itself on SCHED_RR, which is left alone.
_SESSION = [f'{{ "name": "{name}", "nice": 0, "ioclass": "best-effort", "ionice": 4 }}'
            for name in ("start-hyprland", "Hyprland")]


def available() -> bool:
    """Whether ananicy-cpp is installed (otherwise the setting has nothing to do)."""
    return bool(shutil.which("ananicy-cpp")) or Path("/etc/ananicy.d").is_dir()


def rules(mode: str) -> str:
    lines = ["# Souprland (Settings › Behavior › Window switcher › Priority).",
             "# If deleted, CachyOS's own rules apply."]
    if mode in ("alttab", "session"):
        lines.append(_ALTTAB)
    if mode == "session":
        lines += _SESSION
    return "\n".join(lines) + "\n"


def current_mode() -> str:
    """Current mode from the system rule file (the file is world-readable)."""
    try:
        text = RULE_PATH.read_text(encoding="utf-8")
    except OSError:
        return "off"
    if '"Hyprland"' in text:
        return "session"
    return "alttab" if PROC_NAME in text else "off"


def script(mode: str) -> str:
    """Shell script to run in the terminal (sudo asks for the password there)."""
    restart = "sudo systemctl restart ananicy-cpp"
    if mode == "off":
        body = [f"sudo rm -f {shlex.quote(str(RULE_PATH))}", restart]
        title = "Removing the priority fix"
    else:
        body = [f"printf %s {shlex.quote(rules(mode))} | sudo tee "
                f"{shlex.quote(str(RULE_PATH))} >/dev/null"]
        if mode == "session":
            # Fix the processes already running too (otherwise they stay at nice 16
            # until the next session). First everyone goes to 0, then the ananicy
            # restart sets those with their own rule (like kitty -4) back.
            body += ['sudo renice -n 0 -u "$USER" >/dev/null',
                     'for p in $(pgrep -u "$USER"); do '
                     'sudo ionice -c2 -n4 -p "$p" 2>/dev/null; done']
        body.append(restart)
        title = "Applying the priority fix"
    return (f"echo {shlex.quote(title + ' (you will be asked for your sudo password)')}; echo; "
            + " && ".join(body)
            + " && echo && echo 'Done.' || echo 'Failed.'"
            + "; echo; read -p 'Press Enter to close…' _")
