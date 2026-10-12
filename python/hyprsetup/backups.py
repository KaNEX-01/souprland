"""~/.config/hyprsetup-backups — kind, bookkeeping and pruning of backup directories.

Every install (install.sh) and every settings app session opens its own timestamped
directory. These used to never be deleted (183 directories on one machine), and
``restore.sh`` picked the NEWEST directory by default: since the live app opens a
new directory every session, the "latest backup" was not the pre-install state but
the previous small settings change.

Each directory contains:

* ``_kind``        — ``install`` (install.sh) or ``live`` (settings app).
  Old directories without this file count as install if ``_manifest.txt`` exists
  (only lib/core.sh:backup_path writes it), otherwise as live.
* ``_created.txt`` — files that did NOT EXIST before and were created in that run.
  Restoring deletes them; otherwise a revert would only bring back overwritten
  files and leave the added ones behind.

Pruning: the OLDEST directory (the original state before hyprsetup) is never
deleted; after it, the newest ``KEEP_INSTALL`` install and ``KEEP_LIVE`` live
backups are kept.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

KEEP_INSTALL = 5
KEEP_LIVE = 10

KIND_FILE = "_kind"
CREATED_FILE = "_created.txt"
MANIFEST_FILE = "_manifest.txt"


def root(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".config" / "hyprsetup-backups"


def kind_of(directory: Path) -> str:
    try:
        text = (directory / KIND_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        text = ""
    if text in ("install", "live"):
        return text
    return "install" if (directory / MANIFEST_FILE).exists() else "live"


def new_dir(kind: str, home: Path | None = None) -> Path:
    """Opens a new, EMPTY backup directory and marks its kind.

    The name is a timestamp with one-second resolution; if a second directory is
    needed within the same second, "-2", "-3"… is appended. Previously a profile's
    backup and the backup of the settings app run right after it landed in the same
    directory; uninstalling the profile then "restored" the files the settings
    engine had backed up (e.g. the keybinding overlay) into the user's folder.
    """
    from datetime import datetime

    base = root(home)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate, n = base / stamp, 2
    while candidate.exists():
        candidate, n = base / f"{stamp}-{n}", n + 1
    mark(candidate, kind)
    return candidate


def mark(directory: Path, kind: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    marker = directory / KIND_FILE
    if not marker.exists():
        marker.write_text(kind + "\n", encoding="utf-8")


def record_created(directory: Path, target: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / CREATED_FILE).open("a", encoding="utf-8") as handle:
        handle.write(f"{target}\n")


def prune(base: Path | None = None, keep_install: int = KEEP_INSTALL,
          keep_live: int = KEEP_LIVE) -> list[Path]:
    """Deletes excess backups; returns the deleted directories."""
    base = base or root()
    if not base.is_dir():
        return []
    dirs = sorted(d for d in base.iterdir() if d.is_dir())
    if len(dirs) <= 1:
        return []
    first, rest = dirs[0], dirs[1:]
    keep = {first}
    # The active profile's (rice.py) backup is needed to revert; it is never
    # deleted, however old it is.
    try:
        state = json.loads((base.parent / "hyprsetup" / "rice.json")
                           .read_text(encoding="utf-8"))
        keep.add(Path(state.get("backup", "")))
    except (OSError, ValueError):
        pass
    # Same for the backup of the mix parts (mix.py).
    try:
        state = json.loads((base.parent / "hyprsetup" / "mix.json")
                           .read_text(encoding="utf-8"))
        keep.add(Path((state.get("installed") or {}).get("backup", "")))
    except (OSError, ValueError):
        pass
    for kind, limit in (("install", keep_install), ("live", keep_live)):
        of_kind = [d for d in rest if kind_of(d) == kind]
        keep.update(of_kind[-limit:] if limit > 0 else [])
    removed = []
    for directory in rest:
        if directory in keep:
            continue
        shutil.rmtree(directory, ignore_errors=True)
        removed.append(directory)
    return removed
