"""Syncs the installed copy (~/.local/share/hyprsetup) with the source repo.

install.sh copies the settings app from the repo to ``~/.local/share/hyprsetup``;
MOD+I, the bar panel and the keybinding cheatsheet run from that copy. The copy was
only refreshed by install.sh, so no change made in the repo (a new bar panel tab, a
template fix) reached the installed app; worse, changing a setting from MOD+I
rendered the OLD templates over the newer files applied from the repo.

Here:
  * ``source_root()``  path of the source repo (install.sh writes it to ``.source``),
  * ``differs()``      whether the installed copy differs from the repo (size + mtime, fast),
  * ``sync()``         re-copies the directories if they differ,
  * ``git_status()`` / ``git_pull()``  if the repo is a git clone, counts new remote
    commits and runs ``pull --ff-only``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

#: Root of the installed copy.
INSTALL = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "hyprsetup"
#: Directories install.sh copies (same as install.sh:install_app_step).
DIRS = ("python", "templates", "config", "presets", "wallpapers", "assets")
#: File holding the path of the source repo.
SOURCE_FILE = INSTALL / ".source"
_SKIP = {"__pycache__", ".pytest_cache"}


def is_source_tree(root: Path) -> bool:
    """Whether root is a source repo (not the installed copy itself)."""
    root = Path(root).resolve()
    return ((root / "install.sh").is_file() and (root / "python/hyprsetup").is_dir()
            and root != INSTALL.resolve())


def source_root() -> Path | None:
    """Repo the installed copy came from; None if unknown or deleted."""
    try:
        path = Path(SOURCE_FILE.read_text(encoding="utf-8").strip())
    except OSError:
        return None
    return path if is_source_tree(path) else None


def _files(base: Path) -> dict[str, tuple[int, int]]:
    """{relative path: (size, mtime seconds)} — excluding cache directories."""
    found: dict[str, tuple[int, int]] = {}
    for name in DIRS:
        top = base / name
        if not top.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(top):
            dirnames[:] = [d for d in dirnames if d not in _SKIP]
            for filename in filenames:
                if filename.endswith(".pyc"):
                    continue
                path = Path(dirpath) / filename
                try:
                    stat = path.stat()
                except OSError:
                    continue
                found[str(path.relative_to(base))] = (stat.st_size, int(stat.st_mtime))
    return found


def differs(src: Path, dest: Path = INSTALL) -> list[str]:
    """Files that differ, are missing or extra in the installed copy (empty = up to date).

    copy2 preserves mtime, so comparing size + mtime is enough without reading
    content, and is instant even for 4000 files.
    """
    a, b = _files(Path(src)), _files(Path(dest))
    return sorted(k for k in a.keys() | b.keys() if a.get(k) != b.get(k))


def installed() -> bool:
    return (INSTALL / "python/hyprsetup").is_dir()


def sync(src: Path, dest: Path = INSTALL) -> list[str]:
    """Writes the repo to the installed copy; returns the changed files.

    Each directory is first copied next to it (``.<name>.new``), then swapped with
    the old one: if copying is interrupted, the running app is not left with a
    half-copied tree.
    """
    src, dest = Path(src).resolve(), Path(dest)
    changed = differs(src, dest)
    if not changed:
        return []
    dest.mkdir(parents=True, exist_ok=True)
    ignore = shutil.ignore_patterns(*_SKIP, "*.pyc")
    for name in DIRS:
        source = src / name
        if not source.is_dir():
            continue
        if not any(path.startswith(name + os.sep) for path in changed):
            continue
        staging = dest / f".{name}.new"
        old = dest / f".{name}.old"
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(old, ignore_errors=True)
        shutil.copytree(source, staging, ignore=ignore, symlinks=True)
        target = dest / name
        if target.exists():
            target.rename(old)
        staging.rename(target)
        shutil.rmtree(old, ignore_errors=True)
    icon = src / "assets/souprland.svg"
    icon_dir = dest.parent / "icons/hicolor/scalable/apps"
    if icon.is_file() and icon_dir.is_dir():
        shutil.copy2(icon, icon_dir / "souprland.svg")
    try:
        (dest / ".source").write_text(f"{src}\n", encoding="utf-8")
    except OSError:
        pass
    # The entry's text (name, sub-actions) can change along with the repo.
    from . import desktop_entry
    desktop_entry.ensure(src)
    return changed


def _git(src: Path, *args: str, timeout: float = 30) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(["git", "-C", str(src), *args], capture_output=True,
                              text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def git_status(src: Path, fetch: bool = True) -> dict:
    """{"git": bool, "upstream": str, "behind": int, "dirty": int, "error": str}."""
    info = {"git": False, "upstream": "", "behind": 0, "dirty": 0, "error": ""}
    if not (Path(src) / ".git").exists() or shutil.which("git") is None:
        return info
    info["git"] = True
    upstream = _git(src, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if upstream is None or upstream.returncode != 0:
        info["error"] = "branch has no upstream"
        return info
    info["upstream"] = upstream.stdout.strip()
    if fetch:
        fetched = _git(src, "fetch", "--quiet", timeout=60)
        if fetched is None or fetched.returncode != 0:
            info["error"] = "could not reach the remote"
    behind = _git(src, "rev-list", "--count", "HEAD..@{u}")
    if behind is not None and behind.returncode == 0:
        info["behind"] = int(behind.stdout.strip() or 0)
    status = _git(src, "status", "--porcelain")
    if status is not None:
        info["dirty"] = len([line for line in status.stdout.splitlines() if line.strip()])
    return info


def git_pull(src: Path) -> tuple[bool, str]:
    """``git pull --ff-only``: does nothing if it conflicts with local commits."""
    result = _git(src, "pull", "--ff-only", timeout=120)
    if result is None:
        return False, "could not run git"
    text = (result.stdout + result.stderr).strip()
    return result.returncode == 0, text.splitlines()[-1] if text else ""
