"""Filesystem snapshot before touching system files.

Login screen (SDDM/Plasma Login) and display manager changes write under /etc and
/usr/share with sudo. A theme that goes wrong can break login; if snapper (btrfs) or
timeshift is installed, the script takes a snapshot FIRST, so you can roll back from
the bootloader's snapshot menu or with ``snapper rollback``. If neither is present
this is silently skipped; if the snapshot fails, the job still runs (with a warning).

The install.sh counterpart is lib/core.sh:system_snapshot.
"""

from __future__ import annotations

import shlex
import shutil
from pathlib import Path


def tool() -> str:
    """"snapper" (if a root config exists), "timeshift" or ""."""
    if shutil.which("snapper") and Path("/etc/snapper/configs/root").exists():
        return "snapper"
    if shutil.which("timeshift"):
        return "timeshift"
    return ""


def shell_line(reason: str, setting: str = "auto") -> str:
    """Line to prepend to the root script (empty if there is no tool).

    ``setting`` is SNAPSHOT_BEFORE_SYSTEM (Settings → Session → Desktop tools);
    "false" means no snapshot is taken. It never stops the job, even under
    ``set -e``: if the snapshot fails, a warning is printed and the script continues.
    """
    if setting == "false":
        return ""
    description = shlex.quote(f"Souprland: {reason}")
    which = tool()
    if which == "snapper":
        command = f"sudo snapper -c root create -t single -c number -d {description}"
    elif which == "timeshift":
        command = f"sudo timeshift --create --scripted --comments {description}"
    else:
        return ""
    return (f"echo '==> Taking a snapshot ({which}) — in case you need to roll back'; "
            f"{command} && echo '    done' || echo '    !! snapshot failed, continuing'")
