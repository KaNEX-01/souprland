"""Rices: installs the author's own files from a pinned commit.

The profile system knows two kinds of profile:

* Template profile (``presets/profile/<name>.conf``) — values are rendered
  through this project's templates; the settings app can edit everything.
* Rice (``presets/profile/<name>.rice.toml`` + a ``.conf`` of the same name) —
  to bring the setup from a Reddit post EXACTLY, the author's repo is fetched
  at the commit closest to the post's publication date and the files are put
  in place as they are. Custom Quickshell/eww shells (circular Bluetooth
  panel, moon-globe launcher…) cannot be imitated by templates, so this is the
  only way. The ``.conf`` only feeds the gallery card (title, description,
  preview palette).

The author's install script is NOT RUN: most of them touch system files with
sudo, some take over the Hyprland config without asking. Instead the mapping
in the manifest is applied; every step is backed up and can be reverted:

1. Files are taken first from the archive shipped with the project
   (``vendor/rices/``); without an archive the repo is fetched into
   ``~/.cache/hyprsetup/rices/<name>``. The commit is pinned in both cases.
2. Files are prepared in a temporary tree; the Hyprland config is converted to
   the current syntax (hyprmigrate.py) — old commits often give a "config
   error" on current Hyprland.
3. Every existing file/directory at the target is MOVED to the backup
   directory (backups.py), then the new files are copied. The paths the rice
   owns are written to ``~/.config/hyprsetup/rice.json``; this project's own
   settings engine (apply.py, lib/render.sh) does not write over them.
4. The selected look's (variant's) wallpaper is installed and the author's own
   wallpaper/palette commands are run.

Archives are produced with ``python -m hyprsetup rice vendor``: only the
installed paths at the pinned commit, via ``git archive`` (no history),
plus the repo's top-level license files. Images, video and audio over
64 KB are left out and downloaded from the author's repo at install time
(REMOTE_LIST): dotfile repos often carry art their license cannot cover.
The license is tracked per source (Manifest.source_licenses).
Archives of repos with no stated license are produced locally but are not
committed to git (``vendor/rices/.gitignore``) — there is no permission to
redistribute them; on another machine they are again fetched from the
author's repo.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import urllib.parse
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import backups as backups_mod
from . import displays as displays_mod
from . import hyprmigrate

STATE_NAME = "rice.json"
SUFFIX = ".rice.toml"

#: Compatibility wrappers for renamed programs (~/.local/bin). The authors'
#: scripts call the old name; on current Arch the program ships under the new
#: name. The wrapper forwards to the new name if present, otherwise to the old
#: program on the system — it works either way.
SHIMS: dict[str, str] = {
    # swww → awww (the Arch package only installs awww/awww-daemon). "swww init"
    # started the daemon in old versions; in awww the equivalent is awww-daemon.
    "swww": """#!/usr/bin/env bash
# hyprsetup compatibility wrapper: swww → awww (python/hyprsetup/rice.py)
if command -v awww >/dev/null 2>&1; then
    if [[ "${1:-}" == init ]]; then shift; exec awww-daemon "$@"; fi
    exec awww "$@"
fi
exec /usr/bin/swww "$@"
""",
    "swww-daemon": """#!/usr/bin/env bash
# hyprsetup compatibility wrapper: swww-daemon → awww-daemon
command -v awww-daemon >/dev/null 2>&1 && exec awww-daemon "$@"
exec /usr/bin/swww-daemon "$@"
""",
    # saatvik333's waybar update module calls the author's personal script
    # (not in the AUR); without it every check raised a "Dependency Missing" notification.
    "checkupdates-with-aur": """#!/usr/bin/env bash
# hyprsetup compatibility wrapper: repo + AUR updates, one package per line
checkupdates 2>/dev/null
for helper in paru yay; do
    if command -v "$helper" >/dev/null 2>&1; then "$helper" -Qua 2>/dev/null; break; fi
done
exit 0
""",
}
#: What a wrapper brings along.
SHIM_GROUPS: dict[str, list[str]] = {"swww": ["swww", "swww-daemon"],
                                     "checkupdates-with-aur": ["checkupdates-with-aur"]}


# ---------------------------------------------------------------- manifest --
@dataclass
class Install:
    """A path in the repo → the target in the home directory."""
    src: str
    dest: str
    #: "replace": the target directory is fully replaced by the author's (backed up).
    #: "merge": only the author's files are written over, the rest stays.
    mode: str = "replace"
    #: "core" is always installed; the other groups (e.g. "shell", "editor") are
    #: optional — overriding the user's shell/editor config is a big deal.
    group: str = "core"
    #: This item is taken from another commit (empty = the manifest's commit).
    #: If the author used a file at post time but only put it in the repo a bit
    #: later (e.g. the lock screen config), only that file comes from the later
    #: commit while the rest of the rice stays unchanged.
    commit: str = ""
    #: This item comes from another repo (empty = the manifest's repo); then
    #: ``commit`` is required. If the author published a part in a separate repo
    #: (e.g. a launcher written for a contest) it is put on top of the main rice.
    repo: str = ""
    #: License of that repo if it comes from a separate one (for the credits list).
    license: str = ""


@dataclass
class Fix:
    """Repairs a missing/broken spot in the author's repo during install.

    Some repos were in the middle of a half-done reorganization at post time
    (e.g. the main file ``source``s files not in the repo); the screenshot is
    from the author's own machine. A fix only makes the config load, it does
    not touch the look. Every fix is written in the manifest with its reason.
    """
    file: str                          # ~/... target path
    create: str | None = None          # create with this content if the file is MISSING
    replace: list[str] = field(default_factory=list)   # [old, new, old, new…]
    append: str = ""                   # text to append to the end of the file
    delete: bool = False               # the author's script deletes this file
    why: str = ""
    #: Apply only on this hardware: "" (always), "nvidia", "no-nvidia".
    #: Lines specific to the author's machine (e.g. NVIDIA env variables) stay
    #: as-is on a machine similar to the author's.
    gpu: str = ""


@dataclass
class Variant:
    name: str
    title: str = ""
    #: Path relative to the project root (wallpapers/...), an https:// URL or an
    #: absolute path installed by a package (athena: /usr/share/backgrounds/...).
    wallpaper: str = ""
    #: Where the wallpaper goes in the home directory (where the author's scripts look).
    wallpaper_dest: str = ""
    #: Commands run in the session after install; the {wallpaper} placeholder
    #: expands to the full path of the placed file.
    apply: list[str] = field(default_factory=list)
    #: The wallpaper's original source (artist/site) — for the card and docs.
    credit: str = ""


@dataclass
class Part:
    """A part that can be taken on its own in a mix (mix.py): bar, launcher…

    Installed on top of this project's configuration, without the rest of the
    author's rice. Paths are copied from the rice's prepared state (with fixes
    applied).
    """
    slot: str                          # bar | launcher | notify | terminal | lock | widget
    id: str = ""                       # tells parts apart if a slot has several
    title: str = ""
    #: The part's files (~/... targets, from inside the rice).
    paths: list[str] = field(default_factory=list)
    #: Paths the part calls that may belong to another part (e.g. rofi
    #: scripts the bar opens on click). If another slot claims the same path it
    #: is not installed and a warning is given.
    needs: list[str] = field(default_factory=list)
    #: Command run at session start (and right after install).
    start: str = ""
    #: New command for the user's keybinding: {"LAUNCHER": "...", "LOCK": "..."}.
    commands: dict[str, str] = field(default_factory=dict)
    #: Component categories this project no longer starts (no two bars).
    provides: list[str] = field(default_factory=list)
    packages_repo: list[str] = field(default_factory=list)
    packages_aur: list[str] = field(default_factory=list)
    #: Whether colors in the files are translated to the user's color scheme.
    recolor: bool = True
    #: Splitting a Quickshell shell: ``entry`` (ShellRoot file, ~/...) is
    #: rewritten with only the ``modules`` components of the selected parts.
    entry: str = ""
    modules: list[str] = field(default_factory=list)
    #: Files generated from the color scheme: "format:~/path" (pywal, kitty).
    palette_files: list[str] = field(default_factory=list)
    #: Lock screen: point the background image lines at the user's wallpaper.
    wallpaper_lines: bool = False
    #: Lines to add to Hyprland (e.g. a layerrule for the shell's layers).
    hypr: list[str] = field(default_factory=list)
    #: Parts that must be selected together ("profile/part"): e.g. a launcher
    #: opened from inside the bar is not visible without the bar itself.
    requires: list[str] = field(default_factory=list)
    note: str = ""


@dataclass
class Manifest:
    name: str
    repo: str
    commit: str
    post: str = ""
    license: str = ""
    installs: list[Install] = field(default_factory=list)
    packages_repo: list[str] = field(default_factory=list)
    packages_aur: list[str] = field(default_factory=list)
    variants: dict[str, Variant] = field(default_factory=dict)
    default_variant: str = ""
    #: Commands run once after install (e.g. matugen's first generation).
    post_install: list[str] = field(default_factory=list)
    #: Build commands run during install, independent of the session and with
    #: visible output (e.g. a program the author only published as source).
    #: Must be user-level: no sudo.
    build: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    fixes: list[Fix] = field(default_factory=list)
    #: If the author's Hyprland main file is not hyprland.conf (e.g. hypr.conf),
    #: the hyprland.conf Hyprland reads is pointed at it.
    hypr_entry: str = ""
    #: Required compatibility wrappers (SHIM_GROUPS keys).
    shims: list[str] = field(default_factory=list)
    #: Symlinks: (link target, installed path it points to). If the author puts
    #: the repo under ~/<dir> and links it into ~/.config (and calls scripts from
    #: that path) the same is done.
    links: list[tuple[str, str]] = field(default_factory=list)
    #: Files generated by the rice that are not in the repo: (target, content).
    #: E.g. if the author did not share a Hyprland config, the lines starting
    #: their own windows are written as ~/.config/hypr/rice.conf and this
    #: project's hyprland.conf sources it.
    files: list[tuple[str, str]] = field(default_factory=list)
    #: Component categories the rice brings itself (catalog id: "bar",
    #: "notify", "launcher"…). While active, this project's component in that
    #: category is not started and its config is not generated — no two bars.
    provides: list[str] = field(default_factory=list)
    #: Parts that can be taken on their own in a mix (see Part, mix.py).
    parts: list[Part] = field(default_factory=list)
    path: Path | None = None
    #: Directory of the source archives shipped with the project (vendor/rices).
    vendor: Path | None = None

    def sources(self) -> dict[tuple[str, str], list[str]]:
        """(repo, commit) the rice needs → paths in the repo."""
        out: dict[tuple[str, str], list[str]] = {}
        for item in self.installs:
            key = (item.repo or self.repo, item.commit or self.commit)
            paths = out.setdefault(key, [])
            if item.src not in paths:
                paths.append(item.src)
        return out

    def source_licenses(self) -> dict[tuple[str, str], str]:
        """(repo, commit) → license of that source ("" = none stated).

        An extra repo carries its own ``license`` on its install items and never
        inherits the main repo's: caelestia's shell is GPL-3.0, but the
        caelestia/cli repos had no license at the pinned commits.
        """
        out: dict[tuple[str, str], str] = {}
        for item in self.installs:
            key = (item.repo or self.repo, item.commit or self.commit)
            license_ = item.license if item.repo else self.license
            out[key] = out.get(key) or license_
        return out

    @property
    def groups(self) -> list[str]:
        return sorted({i.group for i in self.installs} - {"core"})


def imported_dir(home: Path | None = None) -> Path:
    """Rices imported via link (importer.py) — per user."""
    return _home(home) / ".config" / "hyprsetup" / "imported"


def manifest_path(root: Path, profile: str) -> Path:
    from .presets import default_dir
    bundled = default_dir(root, "profile") / f"{profile}{SUFFIX}"
    if bundled.is_file() or not profile or "/" in profile:
        return bundled
    imported = imported_dir() / f"{profile}{SUFFIX}"
    return imported if imported.is_file() else bundled


def all_profiles(root: Path) -> list[str]:
    """Names of all rices, shipped and imported."""
    from .presets import default_dir
    names = [p.name[: -len(SUFFIX)] for p in default_dir(root, "profile").glob("*" + SUFFIX)]
    names += [p.name[: -len(SUFFIX)] for p in imported_dir().glob("*" + SUFFIX)]
    return sorted(dict.fromkeys(names))


def is_imported(root: Path, profile: str) -> bool:
    return manifest_path(root, profile).parent == imported_dir()


def is_rice(root: Path, profile: str) -> bool:
    return bool(profile) and manifest_path(root, profile).is_file()


#: Allowed keys. In TOML a top-level key written after a table ([packages],
#: [[fix]]…) belongs to that table and used to be silently ignored
#: (post_install/notes were lost this way in every manifest); an unknown
#: key now raises an error.
_KEYS = {
    "": {"source", "install", "fix", "file", "link", "packages", "variants", "bar",
         "post_install", "build", "notes", "default_variant", "hypr_entry",
         "shims", "provides", "part"},
    "source": {"repo", "commit", "post", "license"},
    "install": {"from", "to", "mode", "group", "commit", "repo", "license"},
    "fix": {"file", "create", "replace", "append", "delete", "why", "gpu"},
    "file": {"to", "content"},
    "link": {"to", "target"},
    "packages": {"repo", "aur"},
    "variants": {"title", "wallpaper", "wallpaper_dest", "apply", "credit"},
    "part": {"slot", "id", "title", "paths", "needs", "start", "commands", "provides",
             "packages", "aur", "recolor", "entry", "modules", "palette_files",
             "wallpaper_lines", "hypr", "requires", "note"},
}


def _check_keys(data: dict, path: Path) -> None:
    def bad(section: str, keys) -> None:
        extra = set(keys) - _KEYS[section]
        if extra:
            where = f"[{section}]" if section else "top level"
            raise ValueError(f"{path.name}: unknown key in {where}: "
                             f"{', '.join(sorted(extra))}")
    bad("", data)
    for section in ("source", "packages"):
        bad(section, data.get(section, {}))
    for section in ("install", "fix", "file", "link", "part"):
        for item in data.get(section, []):
            bad(section, item)
    for variant in (data.get("variants") or {}).values():
        bad("variants", variant)


def load(root: Path, profile: str) -> Manifest:
    path = manifest_path(root, profile)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    _check_keys(data, path)
    src = data.get("source", {})
    installs = [Install(src=i["from"], dest=i["to"], mode=i.get("mode", "replace"),
                        group=i.get("group", "core"), commit=i.get("commit", ""),
                        repo=i.get("repo", ""), license=i.get("license", ""))
                for i in data.get("install", [])]
    variants = {}
    for name, v in (data.get("variants") or {}).items():
        variants[name] = Variant(name=name, title=v.get("title", name),
                                 wallpaper=v.get("wallpaper", ""),
                                 wallpaper_dest=v.get("wallpaper_dest", ""),
                                 apply=list(v.get("apply", [])),
                                 credit=v.get("credit", ""))
    pkgs = data.get("packages", {})
    return Manifest(
        name=profile, repo=src["repo"], commit=src["commit"],
        post=src.get("post", ""), license=src.get("license", ""),
        installs=installs,
        packages_repo=list(pkgs.get("repo", [])),
        packages_aur=list(pkgs.get("aur", [])),
        variants=variants,
        default_variant=data.get("default_variant", next(iter(variants), "")),
        post_install=list(data.get("post_install", [])),
        build=list(data.get("build", [])),
        notes=list(data.get("notes", [])),
        fixes=[Fix(file=f["file"], create=f.get("create"),
                   replace=list(f.get("replace", [])), append=f.get("append", ""),
                   delete=bool(f.get("delete", False)), why=f.get("why", ""),
                   gpu=f.get("gpu", ""))
               for f in data.get("fix", [])],
        hypr_entry=data.get("hypr_entry", ""),
        shims=list(data.get("shims", [])),
        links=[(ln["to"], ln["target"]) for ln in data.get("link", [])],
        files=[(f["to"], f["content"]) for f in data.get("file", [])],
        provides=list(data.get("provides", [])),
        parts=[Part(slot=p["slot"], id=p.get("id", "") or p["slot"],
                    title=p.get("title", ""), paths=list(p.get("paths", [])),
                    needs=list(p.get("needs", [])), start=p.get("start", ""),
                    commands=dict(p.get("commands", {})),
                    provides=list(p.get("provides", [])),
                    packages_repo=list(p.get("packages", [])),
                    packages_aur=list(p.get("aur", [])),
                    recolor=bool(p.get("recolor", True)), entry=p.get("entry", ""),
                    modules=list(p.get("modules", [])),
                    palette_files=list(p.get("palette_files", [])),
                    wallpaper_lines=bool(p.get("wallpaper_lines", False)),
                    hypr=list(p.get("hypr", [])), requires=list(p.get("requires", [])),
                    note=p.get("note", ""))
               for p in data.get("part", [])],
        path=path, vendor=vendor_dir(root))


# ------------------------------------------------------------------- paths ---
def _home(home: Path | None) -> Path:
    return Path(home) if home else Path.home()


def expand(path: str, home: Path) -> Path:
    if path == "~" or path.startswith("~/"):
        return home / path[2:]
    raise ValueError(f"target cannot be outside the home directory: {path}")


def cache_dir(name: str, home: Path | None = None) -> Path:
    base = os.environ.get("XDG_CACHE_HOME") if home is None else None
    root = Path(base) if base else _home(home) / ".cache"
    return root / "hyprsetup" / "rices" / name


def state_path(home: Path | None = None) -> Path:
    return _home(home) / ".config" / "hyprsetup" / STATE_NAME


def read_state(home: Path | None = None) -> dict:
    try:
        return json.loads(state_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _mix_parts(home: Path | None = None) -> dict:
    """Parts installed by the mix (mix.py, ~/.config/hyprsetup/mix.json)."""
    try:
        data = json.loads((_home(home) / ".config" / "hyprsetup" / "mix.json")
                          .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data.get("installed") or {}


def owned_paths(home: Path | None = None) -> list[Path]:
    """Targets owned by the active rice and the mix parts
    (apply.py does not write to them)."""
    return ([Path(p) for p in read_state(home).get("owned", [])]
            + [Path(p) for p in _mix_parts(home).get("owned", [])])


def provided_categories(home: Path | None = None) -> list[str]:
    """Component categories brought by the active rice and the mix parts."""
    return list(dict.fromkeys([*read_state(home).get("provides", []),
                               *_mix_parts(home).get("provides", [])]))


def is_owned(target: Path, owned: list[Path]) -> bool:
    target = Path(target)
    return any(target == o or o in target.parents for o in owned)


# ---------------------------------------------------------------- archive ---
def vendor_dir(root: Path) -> Path:
    return Path(root) / "vendor" / "rices"


def _slug(url: str) -> str:
    return "_".join(url.rstrip("/").removesuffix(".git").split("/")[-2:])


#: Top-level license files added to every archive (LICENSE, LICENSE.md, COPYING…).
_LICENSE_FILE = re.compile(r"(?i)^(licen[cs]e|copying|notice)([.-].*)?$")

#: Images, video and audio are left out of the archives and downloaded from the
#: author's repo at install time. Dotfile repos often carry art the author does
#: not own (game/anime characters, franchise wallpapers); their license cannot
#: cover it, so the project must not redistribute it. Small files (icons, UI
#: glyphs) are almost always the author's own and stay in the archive.
_MEDIA_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".avif",
                             ".mp4", ".webm", ".mkv", ".mov",
                             ".wav", ".mp3", ".ogg", ".flac", ".opus"})
_MEDIA_KEEP_BYTES = 64 * 1024

#: Archive member listing the paths left out by _is_remote_media (one per line).
REMOTE_LIST = ".souprland-remote-files"


def _is_remote_media(member: tarfile.TarInfo) -> bool:
    return (member.isfile() and member.size > _MEDIA_KEEP_BYTES
            and Path(member.name).suffix.lower() in _MEDIA_SUFFIXES)


def _add_text(tar: tarfile.TarFile, name: str, text: str) -> None:
    data = text.encode("utf-8")
    info = tarfile.TarInfo(name)
    info.size, info.mode = len(data), 0o644
    tar.addfile(info, io.BytesIO(data))


def _raw_url(url: str, commit: str, path: str) -> str:
    """Raw download URL of ``path`` at ``commit`` (GitHub repos only)."""
    repo = url.rstrip("/").removesuffix(".git").removeprefix("https://github.com/")
    return (f"https://raw.githubusercontent.com/{repo}/{commit}/"
            f"{urllib.parse.quote(path)}")


def vendor_archive(vendor: Path | None, url: str, commit: str) -> Path | None:
    """Archive shipped with the project (None if missing): ``<owner>_<repo>-<commit>.tar.xz``."""
    if vendor is None:
        return None
    path = vendor / f"{_slug(url)}-{commit}.tar.xz"
    return path if path.is_file() else None


def vendor_profile(root: Path, profile: str, cache_home: Path | None = None) -> list[Path]:
    """Archives the rice's sources under ``vendor/rices``.

    Only the installed paths are taken (the whole tree if ``from = "."``); no
    history. An existing archive is left alone — the commit is pinned, the
    content does not change.
    """
    manifest = load(root, profile)
    out_dir = vendor_dir(root)
    out_dir.mkdir(parents=True, exist_ok=True)
    main = cache_dir(manifest.name, cache_home)
    written: list[Path] = []
    for (url, commit), paths in manifest.sources().items():
        target = out_dir / f"{_slug(url)}-{commit}.tar.xz"
        if target.is_file():
            written.append(target)
            continue
        repo = main if url == manifest.repo else _extra_dir(main, url)
        _clone(url, repo, {commit})
        wanted = ["."] if "." in paths else list(paths)
        if "." not in wanted:
            # MIT/GPL/Apache/OFL all require the license text to travel with
            # every copy; the installed paths alone usually leave it out.
            top = _git("ls-tree", "--name-only", commit, cwd=repo).splitlines()
            wanted += [n for n in top if _LICENSE_FILE.match(n) and n not in wanted]
        archive = subprocess.run(["git", "archive", "--format=tar", commit, "--", *wanted],
                                 cwd=repo, capture_output=True, check=False, timeout=900)
        if archive.returncode:
            raise RuntimeError(f"{url}@{commit[:8]}: {archive.stderr.decode()[-200:]}")
        partial = target.with_suffix(".part")
        remote: list[str] = []
        with tempfile.TemporaryFile() as buf:
            buf.write(archive.stdout)
            buf.seek(0)
            with tarfile.open(fileobj=buf) as src, \
                    tarfile.open(partial, "w:xz", preset=9) as dst:
                for member in src:
                    if _is_remote_media(member):
                        remote.append(member.name)
                        continue
                    dst.addfile(member, src.extractfile(member) if member.isfile() else None)
                if remote:
                    _add_text(dst, REMOTE_LIST, "\n".join(remote) + "\n")
        partial.rename(target)
        written.append(target)
    _write_vendor_ignore(root)
    return written


def _write_vendor_ignore(root: Path) -> None:
    """Keep archives of repos with no stated license out of git."""
    from .presets import default_dir
    lines = ["# generated by rice vendor — repos whose license is not stated",
             "# (no permission to redistribute). Used locally, not committed to git."]
    for path in sorted(default_dir(root, "profile").glob("*" + SUFFIX)):
        manifest = load(root, path.name[: -len(SUFFIX)])
        for (url, commit), license_ in manifest.source_licenses().items():
            if not license_:
                lines.append(f"{_slug(url)}-{commit}.tar.xz")
    (vendor_dir(root) / ".gitignore").write_text(
        "\n".join(dict.fromkeys(lines)) + "\n", encoding="utf-8")


# ------------------------------------------------------------------- fetch ---
def _git(*args: str, cwd: Path | None = None) -> str:
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                         text=True, check=False, timeout=900)
    if out.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {out.stderr.strip()[-400:]}")
    return out.stdout


def _extra_dir(main: Path, url: str) -> Path:
    """Cache directory of an extra repo: next to the main repo, ``<name>+<owner>_<repo>``."""
    return main.parent / f"{main.name}+{_slug(url)}"


def _repo_of(main: Path, item: Install) -> Path:
    return _extra_dir(main, item.repo) if item.repo else main


def _clone(url: str, repo: Path, commits: set[str]) -> None:
    if not (repo / ".git").is_dir():
        repo.parent.mkdir(parents=True, exist_ok=True)
        # For big repos (wallpaper collections) blobs are fetched on demand;
        # only the files the commit needs come down.
        _git("clone", "--filter=blob:none", "--no-checkout", url, str(repo))
    for commit in commits:
        try:
            _git("cat-file", "-e", f"{commit}^{{commit}}", cwd=repo)
        except RuntimeError:
            _git("fetch", "origin", commit, cwd=repo)


def fetch(manifest: Manifest, home: Path | None = None) -> Path:
    """Fetches repos without an archive into the cache and verifies the pinned commits.

    Returns the main repo's path; extra repos sit next to it (_extra_dir).
    If every source's archive ships with the project, no network is used.
    """
    repo = cache_dir(manifest.name, home)
    missing: dict[str, set[str]] = {}
    for url, commit in manifest.sources():
        if vendor_archive(manifest.vendor, url, commit) is None:
            missing.setdefault(url, set()).add(commit)
    for url, commits in missing.items():
        _clone(url, repo if url == manifest.repo else _extra_dir(repo, url), commits)
    return repo


def _export(repo: Path, commit: str, src: str, into: Path,
            archive_path: Path | None = None, url: str = "") -> Path:
    """Extracts the ``src`` path at the commit under ``into``; returns the extracted root.

    If ``archive_path`` is given (archive shipped with the project) git is not used;
    media left out of the archive (REMOTE_LIST) is downloaded from ``url`` at the
    same commit. A failed download only costs that file, not the install.
    """
    into.mkdir(parents=True, exist_ok=True)
    if archive_path is not None:
        prefix = src.rstrip("/")

        def selected(name: str) -> bool:
            return src == "." or name == prefix or name.startswith(prefix + "/")

        with tarfile.open(archive_path) as tar:
            members = [m for m in tar.getmembers() if m.name != REMOTE_LIST and selected(m.name)]
            try:
                listed = tar.extractfile(REMOTE_LIST)
                remote = listed.read().decode("utf-8").split() if listed else []
            except KeyError:
                remote = []
            remote = [name for name in remote if selected(name)]
            if not members and not remote:
                raise RuntimeError(f"{src}: not in the archive ({archive_path.name})")
            tar.extractall(into, members=members, filter="tar")
        for name in remote:
            dest = into / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                _download(_raw_url(url, commit, name), dest)
            except RuntimeError as exc:
                print(f"warning: {exc}", file=sys.stderr)
        return into / src
    archive = subprocess.run(["git", "archive", commit, "--", src], cwd=repo,
                             capture_output=True, check=False, timeout=900)
    if archive.returncode:
        raise RuntimeError(f"{src}: not in the repo ({archive.stderr.decode()[-200:]})")
    with tempfile.TemporaryFile() as buf:
        buf.write(archive.stdout)
        buf.seek(0)
        with tarfile.open(fileobj=buf) as tar:
            tar.extractall(into, filter="tar")
    return into / src


# ------------------------------------------------------------- preparation ---
@dataclass
class Plan:
    manifest: Manifest
    variant: str
    staging: Path
    home: Path
    #: (prepared source, target, mode)
    items: list[tuple[Path, Path, str]] = field(default_factory=list)
    migrated: list[str] = field(default_factory=list)


def prepare(manifest: Manifest, repo: Path, staging: Path, home: Path,
            groups: list[str] | None = None, variant: str = "") -> Plan:
    groups = set(groups or []) | {"core"}
    plan = Plan(manifest, variant or manifest.default_variant, staging, home)
    for index, item in enumerate(manifest.installs):
        if item.group not in groups:
            continue
        commit = item.commit or manifest.commit
        url = item.repo or manifest.repo
        src = _export(_repo_of(repo, item), commit, item.src, staging / str(index),
                      vendor_archive(manifest.vendor, url, commit), url)
        dest = expand(item.dest, home)
        plan.items.append((src, dest, item.mode))
    for index, (dest_text, content) in enumerate(manifest.files):
        generated = staging / f"file-{index}" / Path(dest_text).name
        generated.parent.mkdir(parents=True, exist_ok=True)
        generated.write_text(content.replace("{home}", str(home)), encoding="utf-8")
        if content.startswith("#!"):
            generated.chmod(0o755)       # a script (e.g. a helper the author never published)
        plan.items.append((generated, expand(dest_text, home), "replace"))
    _apply_fixes(manifest, plan, home)
    _hook_keybind_overlay(manifest, plan, home)
    hypr_dirs = [home / ".config/hypr"]
    for link_to, link_target in manifest.links:
        if expand(link_to, home) == home / ".config/hypr":
            hypr_dirs.append(expand(link_target, home))
    for src, dest, _mode in plan.items:
        # The Hyprland config is converted to the current syntax (the directory
        # going directly to ~/.config/hypr or linked there).
        roots = [h for h in hypr_dirs if dest == h or h in dest.parents]
        roots += [h for h in hypr_dirs if dest in h.parents]
        if roots:
            base = src
            for h in roots:
                if dest in h.parents:
                    base = src / h.relative_to(dest)
            # *.conf.template: some authors' scripts regenerate Hyprland files
            # from these templates during the session; they must be converted too.
            files = [base] if base.is_file() else [
                *base.rglob("*.conf"), *base.rglob("*.conf.template")]
            for conf in files:
                if not conf.is_file() or conf.is_symlink():
                    continue
                text = conf.read_text(encoding="utf-8", errors="ignore")
                convert = (hyprmigrate.migrate_hyprpaper
                           if conf.name == "hyprpaper.conf" else hyprmigrate.migrate)
                new, report = convert(text)
                if new != text:
                    conf.write_text(new, encoding="utf-8")
                    plan.migrated.append(
                        f"{conf.name}: {len(report.changed)} converted, "
                        f"{len(report.disabled)} disabled")
    return plan


def _hook_keybind_overlay(manifest: Manifest, plan: Plan, home: Path) -> None:
    """Hooks the user's keybinding layer onto the END of the author's Hyprland main file.

    When the install replaced ~/.config/hypr with the author's, this project's
    keybindings (ALT+Tab included) were never loaded; on every profile switch
    the keybindings reverted to the author's. The layer is generated by the
    settings engine (apply._stage_rice_overlay); here it is only made to load,
    and an empty copy is put in place so the first load does not hit a
    "file not found" error. It must be at the end: the layer unbinds the
    author's binding on the same key.
    """
    from .keybinds import RICE_OVERLAY_CONF, RICE_OVERLAY_LUA

    hypr = home / ".config/hypr"
    wanted = {hypr} | {expand(target, home) for to, target in manifest.links
                       if expand(to, home) == hypr}
    root = None
    for src, dest, _mode in plan.items:
        if not src.is_dir():
            continue
        for want in wanted:
            # The link may point at a subfolder of the repo (r4ppz19:
            # ~/.config/hypr → ~/Arch-dotfiles/hypr, repo at ~/Arch-dotfiles).
            if want == dest or dest in want.parents:
                candidate = src / want.relative_to(dest)
                if candidate.is_dir():
                    root = candidate
    if root is None:
        return
    conf = root / (manifest.hypr_entry or "hyprland.conf")
    lua = root / "hyprland.lua"
    if lua.is_file() and not (root / "hyprland.conf").is_file():
        text = lua.read_text(encoding="utf-8")
        name = RICE_OVERLAY_LUA.removesuffix(".lua")
        if name not in text:
            lua.write_text(text.rstrip("\n") + "\n\n-- hyprsetup: your keybindings "
                           f"(generated by the settings app)\npcall(require, \"{name}\")\n",
                           encoding="utf-8")
        (root / RICE_OVERLAY_LUA).touch()
        _append_displays(lua, displays_mod.lua_lines(home), "--")
    elif conf.is_file():
        text = conf.read_text(encoding="utf-8")
        if RICE_OVERLAY_CONF not in text:
            conf.write_text(text.rstrip("\n") + "\n\n# hyprsetup: your keybindings "
                            f"(generated by the settings app)\nsource = ~/.config/hypr/{RICE_OVERLAY_CONF}\n",
                            encoding="utf-8")
        (root / RICE_OVERLAY_CONF).touch()
        _append_displays(conf, displays_mod.conf_lines(home), "#")


_DISPLAYS_MARK = "hyprsetup: your nwg-displays monitor layout"
#: Legacy Turkish marker from pre-English installs (still recognized when reading).
_LEGACY_DISPLAYS_MARK = "hyprsetup: nwg-displays ekran düzeniniz"


def _append_displays(entry: Path, lines: list[str], comment: str) -> None:
    """Makes the author's main file load the nwg-displays layout at its END.

    The author's file usually only contains "monitor = ,preferred,auto,1" and
    never loads monitors.conf; at the end, the user's monitor and workspace
    rules override the author's. install() puts the files in place
    (displays.restore), so only saved ones are added.
    """
    if not lines:
        return
    text = entry.read_text(encoding="utf-8")
    if _DISPLAYS_MARK in text or _LEGACY_DISPLAYS_MARK in text:
        return
    entry.write_text(text.rstrip("\n") + f"\n\n{comment} {_DISPLAYS_MARK}\n"
                     + "\n".join(lines) + "\n", encoding="utf-8")


def _staged(plan: Plan, target: Path) -> Path | None:
    """The counterpart in the staging tree of a target in the home directory.

    A path given through a link (~/.config/hypr/x → ~/dotfiles/hypr/x) is
    translated to the link's target."""
    for link_to, link_target in plan.manifest.links:
        link_path = expand(link_to, plan.home)
        if target == link_path or link_path in target.parents:
            target = expand(link_target, plan.home) / target.relative_to(link_path)
            break
    # Items are copied in order, later ones overwrite earlier ones; a fix must
    # be applied to the LAST item covering the target (e.g. a file put inside
    # the hypr directory from a separate repo).
    for src, dest, _mode in reversed(plan.items):
        if target == dest:
            return src
        if dest in target.parents:
            return src / target.relative_to(dest)
    return None


def has_nvidia() -> bool:
    """Is there an NVIDIA device in lspci (same criterion as apply.py:_gpu_vars).
    HYPRSETUP_GPU=nvidia|other pins the result in tests."""
    forced = os.environ.get("HYPRSETUP_GPU", "")
    if forced:
        return forced == "nvidia"
    try:
        listing = subprocess.run(["lspci"], capture_output=True, text=True,
                                 timeout=10, check=False).stdout.lower()
    except (OSError, subprocess.SubprocessError):
        return False
    return "nvidia" in listing


def _fix_applies(fix: Fix) -> bool:
    if fix.gpu == "nvidia":
        return has_nvidia()
    if fix.gpu == "no-nvidia":
        return not has_nvidia()
    return True


def _apply_fixes(manifest: Manifest, plan: Plan, home: Path) -> None:
    hypr = home / ".config/hypr"
    if manifest.hypr_entry:
        entry = _staged(plan, hypr / "hyprland.conf")
        if entry is not None and not entry.exists():
            entry.write_text(f"# hyprsetup: the author's main file is {manifest.hypr_entry}\n"
                             f"source = ~/.config/hypr/{manifest.hypr_entry}\n",
                             encoding="utf-8")
    # {home}: the author's install script writes an explicit home directory
    # path into some values (env = WALLPAPER_DIR,/home/<user>/...); it cannot
    # be hard-coded in the manifest.
    def fill(text: str) -> str:
        return text.replace("{home}", str(home))

    for fix in manifest.fixes:
        if not _fix_applies(fix):
            continue
        staged = _staged(plan, expand(fix.file, home))
        if staged is None:
            continue
        if fix.delete:
            if staged.is_file() or staged.is_symlink():
                staged.unlink()
            continue
        if fix.create is not None and not staged.exists():
            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_text(fill(fix.create), encoding="utf-8")
        if fix.replace and staged.is_file():
            text = staged.read_text(encoding="utf-8", errors="ignore")
            pairs = zip(fix.replace[::2], fix.replace[1::2], strict=True)
            for old, new in pairs:
                text = text.replace(old, fill(new))
            staged.write_text(text, encoding="utf-8")
        if fix.append and staged.is_file():
            text = staged.read_text(encoding="utf-8", errors="ignore")
            if fill(fix.append) not in text:
                staged.write_text(text.rstrip("\n") + "\n" + fill(fix.append),
                                  encoding="utf-8")


# ----------------------------------------------------------------- install ---
@dataclass
class Result:
    installed: list[str] = field(default_factory=list)
    backup_dir: str = ""
    migrated: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    #: Commands not run during install because of ``start_later``: start_session
    #: runs them after starting the daemons.
    session: list[str] = field(default_factory=list)


#: The user's shared theme files that authors' scripts rewrite at run time
#: although the rice does not install them (vantage: apply-foot-colors.py
#: rewrites foot.ini; end4 applies its palette to KDE's kdeglobals,
#: Trolltech.conf, gtkrc). They are not "owned", so uninstall used to leave
#: the author's colors in them. Snapshotted at install, put back at uninstall.
SHARED_FILES = (
    ".config/foot/foot.ini", ".config/kdeglobals", ".config/Trolltech.conf",
    ".config/gtkrc", ".config/gtkrc-2.0", ".gtkrc-2.0", ".config/konsolerc",
    ".config/qt5ct/qt5ct.conf", ".config/qt6ct/qt6ct.conf",
    ".config/Kvantum/kvantum.kvconfig", ".config/gtk-3.0/gtk.css",
    ".config/gtk-4.0/gtk.css", ".config/gtk-3.0/colors.css", ".config/gtk-4.0/colors.css",
)
_SHARED = "_shared"            # snapshot in the backup ("_": not restored as a file)
_SHARED_ABSENT = ".absent"     # shared files that did not exist at install
_SHARED_RICE = "_shared-rice"  # the rice-time versions, kept in case they are wanted


def _snapshot_shared(backup: Path, home: Path) -> None:
    absent = []
    for rel in SHARED_FILES:
        path = home / rel
        if path.is_file() and not path.is_symlink():
            _copy(path, backup / _SHARED / rel)
        elif not path.exists() and not path.is_symlink():
            absent.append(rel)
    (backup / _SHARED).mkdir(parents=True, exist_ok=True)
    (backup / _SHARED / _SHARED_ABSENT).write_text("\n".join(absent), encoding="utf-8")


def _restore_shared(backup: Path, home: Path, owned: list[str]) -> list[str]:
    """Shared files the rice changed go back to their install-time content;
    ones it created are removed. Both rice-time versions go to _shared-rice."""
    snap = backup / _SHARED
    if not snap.is_dir():
        return []                   # installed before this existed
    mine = [Path(o) for o in owned]
    absent = set((snap / _SHARED_ABSENT).read_text(encoding="utf-8").split()) \
        if (snap / _SHARED_ABSENT).is_file() else set()
    restored = []
    for rel in SHARED_FILES:
        target = home / rel
        if any(o == target or o in target.parents for o in mine):
            continue                # the rice installs it: owned/backup handle it
        saved = snap / rel
        if saved.is_file():
            if target.is_file() and target.read_bytes() == saved.read_bytes():
                continue
        elif not (rel in absent and target.is_file()):
            continue
        if target.is_file() or target.is_symlink():
            _copy(target, backup / _SHARED_RICE / rel)
            target.unlink()
        if saved.is_file():
            _copy(saved, target)
        restored.append(str(target))
    return restored


def _move_aside(target: Path, backup: Path, home: Path) -> None:
    rel = target.relative_to(home)
    dest = backup / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(target), str(dest))
    with (backup / backups_mod.MANIFEST_FILE).open("a", encoding="utf-8") as fh:
        fh.write(f"{target}\n")


def _copy(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir() and not src.is_symlink():
        shutil.copytree(src, dest, symlinks=True, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dest, follow_symlinks=False)


def install(root: Path, profile: str, variant: str = "",
            groups: list[str] | None = None, home: Path | None = None,
            run_commands: bool = True, dry_run: bool = False,
            start_later: bool = False) -> Result:
    """Applies the rice. Does NOT install packages (needs sudo; see packages()).

    ``start_later``: post-install and look commands are not run, they are left
    to start_session in ``result.session`` (the wallpaper daemon only starts
    there).
    """
    home = _home(home)
    manifest = load(root, profile)
    result = Result()
    if variant and variant not in manifest.variants:
        raise ValueError(f"unknown variant: {variant}")

    # If another rice is active it is reverted first: the two authors' files
    # must not mix, and the old rice's backup must not be lost.
    previous = read_state(home)
    if not dry_run:
        displays_mod.save(home)
    if previous and not dry_run:
        uninstall(home=home)

    repo = fetch(manifest, home)
    with tempfile.TemporaryDirectory(prefix="hyprsetup-rice-") as tmp:
        plan = prepare(manifest, repo, Path(tmp), home, groups, variant)
        result.migrated = plan.migrated
        if dry_run:
            result.installed = [str(d) for _s, d, _m in plan.items]
            return result

        backup = backups_mod.new_dir("install", home)
        _snapshot_shared(backup, home)
        owned: list[str] = []
        for src, dest, mode in plan.items:
            # A target that falls inside an earlier item (e.g. hypr/hyprlock.conf
            # from another commit after hypr/ was installed): the file there is
            # not the user's but one we just copied, so it is not backed up.
            inside_ours = any(Path(o) == dest or Path(o) in dest.parents for o in owned)
            if inside_ours:
                _copy(src, dest)
                continue
            if mode == "merge" and dest.is_dir() and not dest.is_symlink():
                # merge: the folder belongs to the user; only the author's files
                # are backed up/owned. Owning the folder would delete the other
                # files in it on uninstall.
                for f in sorted(src.rglob("*")):
                    if f.is_dir() and not f.is_symlink():
                        continue
                    target = dest / f.relative_to(src)
                    if target.exists() or target.is_symlink():
                        _move_aside(target, backup, home)
                    else:
                        backups_mod.record_created(backup, target)
                    owned.append(str(target))
                _copy(src, dest)
                result.installed.append(str(dest))
                continue
            if dest.exists() or dest.is_symlink():
                _move_aside(dest, backup, home)
            else:
                backups_mod.record_created(backup, dest)
            _copy(src, dest)
            owned.append(str(dest))
            result.installed.append(str(dest))
        for link_to, link_target in manifest.links:
            link = expand(link_to, home)
            if link.exists() or link.is_symlink():
                _move_aside(link, backup, home)
            else:
                backups_mod.record_created(backup, link)
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(expand(link_target, home))
            owned.append(str(link))
            result.installed.append(f"{link} → {link_target}")
        for group in manifest.shims:
            for shim in SHIM_GROUPS.get(group, []):
                target = home / ".local/bin" / shim
                if target.exists() or target.is_symlink():
                    _move_aside(target, backup, home)
                else:
                    backups_mod.record_created(backup, target)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(SHIMS[shim], encoding="utf-8")
                target.chmod(0o755)
                owned.append(str(target))
                result.installed.append(str(target))
        result.backup_dir = str(backup)
        # The nwg-displays layout goes into the author's hypr folder (see _append_displays).
        displays_mod.restore(home)

    chosen = plan.variant
    state = {"profile": profile, "variant": chosen, "commit": manifest.commit,
             "repo": manifest.repo, "owned": owned, "backup": result.backup_dir,
             "provides": _available_provides(
                 manifest.provides, home, (*manifest.packages_repo, *manifest.packages_aur)),
             "installed_at": datetime.now().isoformat(timespec="seconds")}
    state_path(home).parent.mkdir(parents=True, exist_ok=True)
    state_path(home).write_text(json.dumps(state, indent=2), encoding="utf-8")

    # A Lua setup has just replaced hyprland.conf: a conf session falls back to
    # Hyprland's STUB at once (no keybindings, SUPER+M logs out). The builds
    # below can take minutes (end4: uv over a slow network), so the bridge
    # goes in now, not only in start_session.
    if (run_commands and home == Path.home() and config_provider() not in ("", "lua")
            and _lua_rice_without_conf(home / ".config/hypr")):
        _write_lua_bridge(home / ".config/hypr")

    if run_commands:
        for command in manifest.build:
            print(f":: building: {command}", flush=True)
            out = subprocess.run(["bash", "-lc", command], cwd=home, check=False)
            if out.returncode:
                result.warnings.append(f"build failed ({out.returncode}): {command}")

    # Post-install commands first (permissions, font cache, dependent
    # environments), THEN the look — in order in the same script; run in
    # separate processes the look commands raced with unprepared files.
    look = set_variant(root, profile, chosen, home=home, run_commands=False,
                       record=False)
    enabled_before = _enabled_user_units() if run_commands else set()
    # When installing in a session the wallpaper daemon does not exist yet (the
    # previous theme's closed on uninstall, this theme's opens in start_session):
    # "swww img" went nowhere, and awww-daemon restored the previous theme's
    # wallpaper when it came up. So commands can be left to start_session.
    session = [*manifest.post_install, *look]
    result.commands += _run(session, home, {}, execute=run_commands and not start_later)
    if run_commands and start_later:
        result.session = session
    if run_commands:
        # The author's services (r4ppz19: "systemctl --user enable waybar…")
        # are persistent; they are saved in the state so uninstall can revert them.
        # Otherwise the uninstalled rice's bar came back at the next login.
        # Commands run in the background (see _run) so the result is not
        # awaited: the units to be enabled are read from the command text.
        new_units = sorted(_units_enabled_by(manifest.post_install) - enabled_before)
        if new_units:
            state["enabled_units"] = new_units
            state_path(home).write_text(json.dumps(state, indent=2), encoding="utf-8")
    return result


def _units_enabled_by(commands: list[str]) -> set[str]:
    """Units in ``systemctl --user enable [--now] a b.service …`` lines."""
    units: set[str] = set()
    for command in commands:
        for match in re.finditer(r"systemctl\s+--user\s+enable\s+([^;&|]+)", command):
            for word in match.group(1).split():
                if word.startswith("-") or word in ("2>/dev/null", ">/dev/null"):
                    continue
                if word.startswith(("2>", ">")):
                    break
                units.add(word if "." in word else f"{word}.service")
    return units


def _enabled_user_units() -> set[str]:
    try:
        out = subprocess.run(["systemctl", "--user", "list-unit-files", "--state=enabled",
                              "--no-legend", "--plain"], capture_output=True, text=True,
                             timeout=30, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    return {line.split()[0] for line in out.splitlines() if line.split()}


def set_variant(root: Path, profile: str, variant: str, home: Path | None = None,
                run_commands: bool = True, record: bool = True) -> list[str]:
    """Switches the look: places the wallpaper, runs the commands."""
    home = _home(home)
    manifest = load(root, profile)
    chosen = manifest.variants.get(variant)
    if chosen is None:
        return []
    placeholders = {}
    if chosen.wallpaper.startswith("~/"):
        # The image is among the author's installed files: no need to copy.
        placeholders["wallpaper"] = str(expand(chosen.wallpaper, home))
    elif chosen.wallpaper and chosen.wallpaper_dest:
        dest = expand(chosen.wallpaper_dest, home)
        dest.parent.mkdir(parents=True, exist_ok=True)
        source = Path(root) / chosen.wallpaper   # an absolute path stays as-is
        if "://" in chosen.wallpaper:          # http(s)://, file://…
            _download(chosen.wallpaper, dest, home)
            placeholders["wallpaper"] = str(dest)
        elif source.is_file():
            shutil.copy2(source, dest)
            placeholders["wallpaper"] = str(dest)
        else:
            # An image from a system package (athena: archlinux-wallpaper) that
            # is not installed yet: commands containing {wallpaper} are skipped
            # (_run), the rest of the look (theme) is still applied.
            print(f"WARNING: no wallpaper ({source}); is the related package installed?",
                  file=sys.stderr)
    if record:
        state = read_state(home)
        if state.get("profile") == profile:
            state["variant"] = variant
            state_path(home).write_text(json.dumps(state, indent=2), encoding="utf-8")
    return _run(chosen.apply, home, placeholders, execute=run_commands)


def _download(url: str, dest: Path, home: Path | None = None) -> None:
    """``url`` → ``dest``. The ``...archive.zip#member`` form downloads the
    archive into the cache once and extracts only that member (if the author
    published the wallpapers as a single zip)."""
    url, _, member = url.partition("#")
    target = dest
    if member:
        digest = hashlib.sha1(url.encode()).hexdigest()[:16]
        target = cache_dir("", home).parent / "archives" / f"{digest}.zip"
        target.parent.mkdir(parents=True, exist_ok=True)
    if not member or not target.is_file():
        part = target.with_name(target.name + ".part")
        out = subprocess.run(["curl", "-fsSL", "--max-time", "600", "-o", str(part), url],
                             capture_output=True, check=False)
        if out.returncode:
            part.unlink(missing_ok=True)
            raise RuntimeError(f"could not download: {url}")
        part.replace(target)
    if member:
        try:
            with zipfile.ZipFile(target) as archive, archive.open(member) as src, \
                    dest.open("wb") as out_file:
                shutil.copyfileobj(src, out_file)
        except (KeyError, zipfile.BadZipFile) as exc:
            raise RuntimeError(f"{url}: {member} not in archive ({exc})") from exc


_WALLPAPER_CLIENT = re.compile(r"\b[as]www\s+(img|clear|restore)\b")

#: "swww img" fails and moves on if run before the daemon is up; wait until
#: the daemon is ready (at most 15 s). Since awww-daemon restores the previous
#: wallpaper on startup, a short margin is left afterwards.
_WAIT_WALLPAPER_DAEMON = (
    "_q() { if command -v awww >/dev/null 2>&1; then awww query; else swww query; fi; }\n"
    "if command -v awww >/dev/null 2>&1 || command -v swww >/dev/null 2>&1; then\n"
    "  for _ in $(seq 75); do _q >/dev/null 2>&1 && break; sleep 0.2; done; sleep 0.5\n"
    "fi\n")


def _run(commands: list[str], home: Path, placeholders: dict[str, str],
         execute: bool = True, wait_daemon: bool = False) -> list[str]:
    """Fills in and runs the session commands (only returns them if
    ``execute`` is false or Hyprland is not running). ``wait_daemon``: the
    wallpaper daemon was just started; the commands (the author's scripts may
    call "awww img" too: vantage, dhruvsharma) wait for it."""
    ran = []
    for command in commands:
        # Not str.format: commands contain the shell's own braces
        # (find -exec … {} +, ${var}).
        line = command
        for key, value in placeholders.items():
            line = line.replace("{" + key + "}", shlex.quote(value))
        if "{wallpaper}" in line:
            # The look has no wallpaper: this command is pointless, skip it.
            continue
        ran.append(line)
    # Commands run in ONE script, in order: "kill the old wallpaper process"
    # and "start the new one" must not race in separate processes.
    if execute and ran and os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        script = "\n".join(ran)
        if wait_daemon or _WALLPAPER_CLIENT.search(script):
            script = _WAIT_WALLPAPER_DAEMON + script
        subprocess.Popen(_in_slice(script), cwd=home,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    return ran


# --------------------------------------------------------- session start ---
#: Every process the rice starts runs in this systemd user slice; on uninstall
#: (or when switching to another theme) it stops with a single command — the
#: previous theme's bar/wallpaper do not linger on screen.
SLICE = "hyprsetup-rice.slice"

#: Startup commands that make persistent changes or do not belong to the
#: session are not run at install (the author's config already runs them at
#: login). The keyring (gnome-keyring, kwallet) is unlocked by PAM at login;
#: if started in the theme's slice it was killed along with the slice on the
#: next theme switch. The keyring D-Bus opened instead came up locked, and
#: with no password prompt possible, apps like Proton VPN could not find
#: their saved session and asked to log in again.
_AUTOSTART_NEVER = re.compile(
    r"trash-empty|\bgsettings\b|systemctl\s+--user\s+(enable|disable|mask|import-environment)"
    r"|dbus-update-activation-environment|^\[workspace"
    r"|gnome-keyring-daemon|\bkwalletd\d*\b|pam_kwallet_init")

#: Helpers started by D-Bus (the keyring's password prompt gcr-prompter,
#: portals) learn the display from the systemd user environment. If an old
#: session's DISPLAY lingers there ("cannot open display: :1") no window opens.
_SESSION_ENV = ("WAYLAND_DISPLAY", "DISPLAY", "XDG_CURRENT_DESKTOP",
                "HYPRLAND_INSTANCE_SIGNATURE", "XDG_SESSION_TYPE")


def update_activation_env() -> None:
    names = [n for n in _SESSION_ENV if os.environ.get(n)]
    if not names or not shutil.which("dbus-update-activation-environment"):
        return
    subprocess.run(["dbus-update-activation-environment", "--systemd", *names],
                   capture_output=True, check=False, timeout=15)

#: Shells/daemons that read their config at startup: if running (the user's
#: or the previous theme's) they are stopped and restarted with the author's config.
_AUTOSTART_RESTART = {"waybar", "hyprpanel", "quickshell", "qs", "eww", "ags", "wayle",
                      "mako", "dunst", "swaync", "hyprpaper", "awww-daemon",
                      "swww-daemon", "mpvpaper"}


#: Programs doing the same job: when the theme starts one, the others are
#: stopped — swaync could not start while the user's mako held the
#: notification service name, and two wallpaper daemons drew on the same
#: layer. On uninstall the user's comes back (apply.Applier.start_missing).
_AUTOSTART_GROUPS = (
    {"mako", "dunst", "swaync"},
    {"hyprpaper", "awww-daemon", "swww-daemon", "mpvpaper"},
    # Bars / desktop shells: quickshell's short name "qs" is a separate process
    # name; without it in the group, a Lua theme's "qs -p …" bar and the user's
    # waybar stayed up under the new theme's quickshell bar.
    {"waybar", "hyprpanel", "wayle", "quickshell", "qs", "eww", "ags"},
)


_LUA_EXEC_CMD = re.compile(r"""(?<!dsp\.)\bexec_cmd\(\s*(\[=*\[.*?\]=*\]|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')""",
                           re.S)


def _rice_daemons(home: Path) -> set[str]:
    """Bar/notification/wallpaper programs the installed config starts at
    startup (conf exec-once + Lua exec_cmd)."""
    commands = list(autostart_commands(home))
    hypr = home / ".config/hypr"
    for lua in hypr.rglob("*.lua") if hypr.is_dir() else []:
        if lua.is_symlink() or not lua.is_file() or "quickshell" in lua.parts:
            continue
        for literal in _LUA_EXEC_CMD.findall(lua.read_text(errors="ignore")):
            commands.append(re.sub(r"^\[=*\[|\]=*\]$|^[\"']|[\"']$", "", literal))
    return {name for command in commands for name in _command_binaries(command)
            if name in _AUTOSTART_RESTART}


def _in_slice(command: str) -> list[str]:
    if shutil.which("systemd-run"):
        return ["systemd-run", "--user", "--scope", "--quiet", f"--slice={SLICE}",
                "--", "bash", "-lc", command]
    return ["bash", "-lc", command]


def autostart_commands(home: Path | None = None) -> list[str]:
    """``exec-once`` commands in the installed Hyprland config.

    The ``source`` chain and ``$variable`` definitions are followed. ``exec =``
    lines are not taken: Hyprland already runs them on every reload.
    """
    import glob

    home = _home(home)
    out: list[str] = []
    seen: set[Path] = set()
    variables: dict[str, str] = {}

    def expand(pattern: str, base: Path) -> list[str]:
        for key, value in sorted(variables.items(), key=lambda kv: -len(kv[0])):
            pattern = pattern.replace(key, value)
        pattern = pattern.replace("~", str(home)).replace("$HOME", str(home))
        if not pattern.startswith("/"):
            pattern = str(base / pattern)
        return sorted(glob.glob(pattern))

    def walk(path: Path) -> None:
        if path in seen or not path.is_file():
            return
        seen.add(path)
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if not line.startswith("exec"):
                line = line.split(" #")[0].strip()
            match = re.match(r"^\$(\w+)\s*=\s*(.*)$", line)
            if match:
                variables["$" + match.group(1)] = match.group(2).strip()
                continue
            match = re.match(r"^source\s*=\s*(.+)$", line)
            if match:
                for found in expand(match.group(1).strip(), path.parent):
                    walk(Path(found))
                continue
            match = re.match(r"^exec-once\s*=\s*(.+)$", line)
            if match:
                command = match.group(1).strip()
                for key, value in sorted(variables.items(), key=lambda kv: -len(kv[0])):
                    command = command.replace(key, value)
                out.append(command)

    walk(home / ".config/hypr/hyprland.conf")
    return out


def _command_binaries(command: str) -> list[str]:
    """``sleep 2 && eww open bar`` → [eww]; ``hyprpaper & waybar`` →
    [hyprpaper, waybar]; ``swww init`` → [awww-daemon] (compatibility wrapper)."""
    names: list[str] = []
    for part in re.split(r"&&|\|\||;|&", command):
        words = part.split()
        while words and (words[0] in ("env", "exec", "nohup", "setsid")
                         or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0])):
            words = words[1:]
        if not words or words[0] == "sleep":
            continue
        name = os.path.basename(words[0])
        names.append("awww-daemon" if name == "swww" and "init" in words else name)
    return names


LUA_BRIDGE_MARK = "# hyprsetup: temporary bridge for the Lua setup"
#: Legacy Turkish marker from pre-English installs (still recognized when reading).
_LEGACY_LUA_BRIDGE_MARK = "# hyprsetup: Lua kurulumu için geçici köprü"


def _lua_rice_without_conf(hypr: Path) -> bool:
    """The author's setup is Lua (hyprland.lua) and hyprland.conf is gone, is
    Hyprland's STUB or our bridge — a conf session then needs the bridge."""
    conf = hypr / "hyprland.conf"
    head = conf.read_text(errors="ignore") if conf.is_file() else ""
    stub = "This config is a STUB" in head or head.startswith(
        (LUA_BRIDGE_MARK, _LEGACY_LUA_BRIDGE_MARK))
    lua = hypr / "hyprland.lua"
    lua_rice = (lua.is_file() and not lua.read_text(errors="ignore")
                .startswith((CONF_BRIDGE_MARK, _LEGACY_CONF_BRIDGE_MARK)))
    return lua_rice and (stub or not conf.is_file())


def _write_lua_bridge(hypr: Path) -> None:
    """Temporary hyprland.conf for a (conf) session running a Lua setup.

    Hyprland picks its main file once at session start (Jeremy::
    getMainConfigPath, 0.56): a session started with conf fell back to the
    "STUB" Hyprland generates once the author's setup removed hyprland.conf —
    default keybindings (SUPER+M logs out) and a config warning. The bridge
    keeps the user's keybindings, monitors and keyboard until the next login.
    If both exist at login hyprland.lua is picked, so the theme is not broken.
    """
    conf = hypr / "hyprland.conf"
    lines = [LUA_BRIDGE_MARK,
             "# After logging out and back in Hyprland reads hyprland.lua; this file",
             "# only exists so the current session is not left without keybindings.", ""]
    for name in ("monitors.conf", "workspaces.conf", "hyprsetup-keybinds.conf"):
        if (hypr / name).is_file():
            lines.append(f"source = ~/.config/hypr/{name}")
    conf.write_text("\n".join(lines) + "\n", encoding="utf-8")
    subprocess.run(["hyprctl", "reload"], capture_output=True, check=False, timeout=10)


CONF_BRIDGE_MARK = "-- hyprsetup: temporary bridge for the conf config"
#: Legacy Turkish marker from pre-English installs (still recognized when reading).
_LEGACY_CONF_BRIDGE_MARK = "-- hyprsetup: conf yapılandırması için geçici köprü"


def config_provider() -> str:
    """The config the running Hyprland session reads: "lua", "conf" or ""."""
    if not os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") or not shutil.which("hyprctl"):
        return ""
    try:
        out = subprocess.run(["hyprctl", "-j", "status"], capture_output=True,
                             text=True, timeout=5).stdout
        return str(json.loads(out).get("configProvider", ""))
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        return ""


def _conf_bridge_text(hypr: Path) -> str:
    from . import keybinds as keybinds_mod

    path = hypr / "hyprland.lua"
    lines = [CONF_BRIDGE_MARK,
             "-- This session started with Lua; Hyprland does not read hyprland.conf",
             "-- for the rest of the session. Log out and back in to load the theme fully;",
             "-- this file deletes itself on shutdown.",
             f"local path = {json.dumps(str(path))}",
             f"local signature = {json.dumps(os.environ.get('HYPRLAND_INSTANCE_SIGNATURE', ''))}",
             "if os.getenv(\"HYPRLAND_INSTANCE_SIGNATURE\") ~= signature then",
             "    -- If it could not be deleted on shutdown (reboot, crash), this login",
             "    -- started with this file instead of hyprland.conf: it is deleted and the",
             "    -- theme's startup programs (bar, wallpaper) are launched from here;",
             "    -- otherwise the desktop was left without a bar and wallpaper.",
             "    os.remove(path)",
             f"    local autostart = {_lua_list(autostart_commands())}",
             "    hl.on(\"hyprland.start\", function()",
             "        for _, command in ipairs(autostart) do hl.exec_cmd(command) end",
             "        hl.notification.create({ text = \"Theme not fully loaded: log out "
             "and back in.\", duration = 15000 })",
             "    end)",
             "end",
             "hl.on(\"hyprland.shutdown\", function() os.remove(path) end)", ""]
    for name in ("monitors", "workspaces"):
        if (hypr / f"{name}.lua").is_file():
            lines.append(f'pcall(require, "{name}")')
    overlay = hypr / keybinds_mod.RICE_OVERLAY_LUA
    if overlay.is_file():
        lines.append(f'pcall(require, "{overlay.stem}")')
    elif (hypr / "keybinds.conf").is_file():
        keyboard: dict[str, str] = {}
        for conf in sorted(hypr.glob("*.conf")):
            keyboard = keybinds_mod.keyboard_settings(conf.read_text(errors="ignore"))
            if keyboard:
                break
        lines += ["", keybinds_mod.rice_overlay(
            (hypr / "keybinds.conf").read_text(errors="ignore"), "lua",
            move_scripts=False, keyboard=keyboard)]
    return "\n".join(lines).rstrip("\n") + "\n"


def _lua_list(items: list[str]) -> str:
    return "{" + ", ".join(json.dumps(item, ensure_ascii=False) for item in items) + "}"


#: systemd user unit that deletes the bridge at session end. On reboot
#: Hyprland exits without emitting "hyprland.shutdown", the bridge stayed and
#: the next login read it instead of hyprland.conf: no theme, no bar, no
#: wallpaper. When the user manager stops (on logout and shutdown) ExecStop
#: deletes the bridge.
_BRIDGE_UNIT = "hyprsetup-lua-bridge.service"


def _arm_bridge_cleanup(lua: Path) -> None:
    if not shutil.which("systemd-run"):
        return
    subprocess.run(["systemctl", "--user", "reset-failed", _BRIDGE_UNIT],
                   capture_output=True, check=False, timeout=10)
    remove = (f"grep -qF -e {shlex.quote(CONF_BRIDGE_MARK)}"
              f" -e {shlex.quote(_LEGACY_CONF_BRIDGE_MARK)} {shlex.quote(str(lua))}"
              f" && rm -f {shlex.quote(str(lua))}")
    subprocess.run(["systemd-run", "--user", "--quiet", f"--unit={_BRIDGE_UNIT}",
                    "-p", "RemainAfterExit=yes",
                    "-p", f'ExecStop=/bin/sh -c "{remove}"', "true"],
                   capture_output=True, check=False, timeout=10)


def _disarm_bridge_cleanup() -> None:
    if shutil.which("systemctl"):
        subprocess.run(["systemctl", "--user", "stop", _BRIDGE_UNIT],
                       capture_output=True, check=False, timeout=10)


def sync_conf_bridge(home: Path | None = None, reload: bool = True) -> bool:
    """Temporary hyprland.lua for the conf config in a session started with Lua.

    Hyprland picks its main file once at session start. After logging in with
    a Lua theme (nothingos) and switching to a conf theme (ilyamiro, standard),
    hyprland.lua could not be found and the session fell back to Hyprland's 3
    default keybindings: the launcher did not open, SUPER+Q did not close
    windows. The bridge keeps the user's keybindings, monitors and keyboard
    until the next login. Removed when not needed (conf session, the author's
    real hyprland.lua). True if the file changed.
    """
    home = _home(home)
    if home != Path.home():
        return False
    hypr = home / ".config/hypr"
    lua = hypr / "hyprland.lua"
    old = lua.read_text(errors="ignore") if lua.is_file() else ""
    bridge = old.startswith((CONF_BRIDGE_MARK, _LEGACY_CONF_BRIDGE_MARK))
    if lua.is_file() and not bridge:
        return False                    # the author's Lua config
    if config_provider() != "lua" or not (hypr / "hyprland.conf").is_file():
        if bridge:
            lua.unlink()
            _disarm_bridge_cleanup()
        return False
    text = _conf_bridge_text(hypr)
    _arm_bridge_cleanup(lua)
    if text == old:
        return False
    lua.write_text(text, encoding="utf-8")
    if reload:
        subprocess.run(["hyprctl", "reload"], capture_output=True, check=False, timeout=10)
    return True


def _available_provides(provides: list[str], home: Path,
                        packages: tuple[str, ...] = ()) -> list[str]:
    """The roles the theme can really take over on this machine.

    athena "provides" the bar with eww; without eww installed the user's
    waybar was still dropped (the role belonged to the theme) and the screen
    had no bar at all. A role whose programs named in the theme's autostart
    are all missing stays with the user. A role started through a script
    (hyprclouds' start.sh) is judged by the theme's packages; with neither
    (vantage's launch.sh) it is kept.
    """
    roles = dict(zip(("notify", "wallpaper", "bar"), _AUTOSTART_GROUPS, strict=False))
    named = {b for c in autostart_commands(home) for b in _command_binaries(c)}
    named |= set(packages)
    out = []
    for role in provides:
        programs = named & roles.get(role, set())
        if programs and not any(shutil.which(b) for b in programs):
            continue
        out.append(role)
    return out


def _roles_in_slice() -> set[str]:
    """Roles (bar/notify/wallpaper) with a program running in the theme's SLICE."""
    roles = dict(zip(("notify", "wallpaper", "bar"), _AUTOSTART_GROUPS, strict=False))
    out: set[str] = set()
    for role, group in roles.items():
        for name in group:
            pids = subprocess.run(["pgrep", "-u", str(os.getuid()), "-x", name],
                                  capture_output=True, text=True).stdout.split()
            for pid in pids:
                try:
                    if SLICE in Path(f"/proc/{pid}/cgroup").read_text():
                        out.add(role)
                except OSError:
                    continue
    return out


def _stop_replaced_outside_slice(settle: float = 2.0) -> list[str]:
    """Stops the user's bar/notifier/wallpaper daemon the theme has replaced.

    Peers were only stopped when the theme's command line named a known
    program; a theme starting its bar through a script (vantage's
    ``launch.sh``, ``caelestia shell``) left the user's waybar on screen next
    to the theme's own bar. Everything the theme starts runs in SLICE, so per
    role: if a program of that role runs inside the slice, the same role's
    programs outside it are the user's and go (they come back on uninstall).
    """
    import signal
    import time

    time.sleep(settle)                  # scripts spawn their real programs late
    stopped: list[str] = []
    for group in _AUTOSTART_GROUPS:
        inside: list[int] = []
        outside: list[tuple[str, int]] = []
        for name in sorted(group):
            out = subprocess.run(["pgrep", "-u", str(os.getuid()), "-x", name],
                                 capture_output=True, text=True).stdout
            for pid in map(int, out.split()):
                try:
                    cgroup = Path(f"/proc/{pid}/cgroup").read_text()
                except OSError:
                    continue
                (inside.append(pid) if SLICE in cgroup
                 else outside.append((name, pid)))
        if not inside:
            continue
        for name, pid in outside:
            try:
                os.kill(pid, signal.SIGTERM)
                stopped.append(name)
            except OSError:
                pass
    return stopped


def start_session(root: Path, profile: str, variant: str = "",
                  home: Path | None = None, skip: str = "",
                  pending: list[str] | None = None) -> tuple[list[str], str]:
    """Starts the author's startup programs right after install.

    ``hyprctl reload`` reads the config but does not run ``exec-once`` lines:
    the theme is installed and the files are in place, but the bar, wallpaper
    and notification center would only arrive at the next login ("nothing
    changed"). Then ``pending`` (install(start_later=True).session; if not
    given, only the look commands) runs. Returns: (started commands, note for
    the user).
    """
    home = _home(home)
    if not os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return [], ""

    def run_look(wait_daemon: bool = False) -> None:
        # In the background, independent of this process: the wallpaper arrives
        # even if the install terminal closes (it used to wait 3 s here; if the
        # terminal closed meanwhile the look was never applied).
        look = pending
        if look is None:
            look = set_variant(root, profile, variant or read_state(home).get("variant", ""),
                               home=home, run_commands=False, record=False)
        _run(look, home, {}, wait_daemon=wait_daemon)

    hypr = home / ".config/hypr"
    provider = config_provider()
    if _lua_rice_without_conf(hypr):
        if provider == "lua":
            # The session is already Lua: the author's hyprland.lua loads directly.
            subprocess.run(["hyprctl", "reload"], capture_output=True, check=False,
                           timeout=10)
            run_look()
            return [], ("This theme's startup programs start at the next login; "
                        "log out and back in to see them right away.")
        _write_lua_bridge(hypr)
        run_look()
        return [], ("This theme uses Hyprland's Lua config; the current "
                    "session cannot load it. Log out and back in to see it.")
    note = ""
    if provider == "lua" and sync_conf_bridge(home):
        note = ("The session was started with a Lua theme; your keybindings were "
                "loaded temporarily. Log out and back in for the full theme "
                "(borders, animations).")
    update_activation_env()
    skip_re = re.compile(skip) if skip else None
    handled: set[str] = set()
    started: list[str] = []
    missing: set[str] = set()
    # Bars that do not specify a monitor are placed on the focused one: like at
    # login, focus the primary monitor and start, then restore the old focus.
    was_focused = displays_mod.focused_monitor()
    primary = displays_mod.primary_monitor()
    displays_mod.focus_monitor(primary)
    for command in autostart_commands(home):
        if _AUTOSTART_NEVER.search(command) or (skip_re and skip_re.search(command)):
            continue
        binaries = _command_binaries(command)

        def running(name: str) -> bool:
            return subprocess.run(["pgrep", "-x", name], capture_output=True).returncode == 0
        restart = [b for b in binaries if b in _AUTOSTART_RESTART]
        absent = [b for b in restart if not shutil.which(b)]
        if absent:
            # Stopping the user's waybar/mako for an eww that is not installed
            # (athena, hyprclouds without their packages) left no bar at all.
            missing.update(absent)
            continue
        if not restart and binaries and running(binaries[-1]):
            continue                    # already running (e.g. the polkit agent)
        for name in restart:
            peers = next((g for g in _AUTOSTART_GROUPS if name in g), {name})
            for peer in peers:
                if peer not in handled and running(peer):
                    subprocess.run(["pkill", "-x", peer], capture_output=True)
                handled.add(peer)
        subprocess.Popen(_in_slice(command), cwd=home, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        started.append(command)
    # The wallpaper daemon has now been started; the look commands wait for it.
    run_look(wait_daemon=any(b in ("awww-daemon", "swww-daemon")
                             for c in started for b in _command_binaries(c)))
    if started and shutil.which("systemd-run"):
        _stop_replaced_outside_slice()
    # Now the autostart lines are all in place (rice.conf themes get them
    # from this project's render): drop the roles nothing here can play.
    state = read_state(home)
    try:
        manifest = load(root, profile)
        packages = (*manifest.packages_repo, *manifest.packages_aur)
    except (OSError, ValueError, KeyError):
        packages = ()
    # What really runs in the theme's slice wins over any guess: vantage
    # lists a missing mpvpaper but draws its wallpaper with awww-daemon.
    live = _roles_in_slice() if started and shutil.which("systemd-run") else set()
    guess = _available_provides(state.get("provides", []), home, packages)
    keep = [r for r in state.get("provides", []) if r in live or r in guess]
    if state and keep != state.get("provides", []):
        state["provides"] = keep
        state_path(home).write_text(json.dumps(state, indent=2), encoding="utf-8")
    if missing:
        note = " ".join(filter(None, [note, (
            f"Not installed: {', '.join(sorted(missing))} — install this theme's packages; "
            "until then your own bar/notifications stay.")]))
    if was_focused != primary:
        displays_mod.focus_monitor(was_focused)
    return started, note


def uninstall(home: Path | None = None) -> list[str]:
    """Reverts the active rice: owned paths are deleted, the backup comes back."""
    home = _home(home)
    state = read_state(home)
    if not state:
        return []
    restored = []
    # Processes the rice started (see start_session, _run).
    if shutil.which("systemctl"):
        subprocess.run(["systemctl", "--user", "stop", SLICE],
                       capture_output=True, check=False, timeout=30)
    # Bars/daemons started at login from the author's config are not in the
    # slice: after logging in with a Lua theme and switching to another one the
    # old bar ("qs -p …/nothing") stayed open next to the new one. The user's
    # come back after uninstall (apply.Applier.start_missing).
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") and home == Path.home():
        for name in sorted(_rice_daemons(home)):
            subprocess.run(["pkill", "-x", name], capture_output=True, check=False)
    # Changes made in nwg-displays while the rice was active are saved before
    # they are deleted along with the author's folder.
    displays_mod.save(home)
    units = state.get("enabled_units", [])
    if units:
        # User services the rice enabled (see install).
        subprocess.run(["systemctl", "--user", "disable", "--now", *units],
                       capture_output=True, check=False, timeout=60)
    for path in map(Path, state.get("owned", [])):
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists() or path.is_symlink():
            path.unlink()
    backup = Path(state.get("backup", ""))
    if backup.is_dir():
        for item in sorted(backup.rglob("*")):
            rel = item.relative_to(backup)
            if rel.parts[0].startswith("_") or not (item.is_file() or item.is_symlink()):
                continue
            target = home / rel
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target, follow_symlinks=False)
            restored.append(str(target))
        restored += _restore_shared(backup, home, state.get("owned", []))
    # The layout in the backup is the pre-install state; the latest layout is put back.
    displays_mod.restore(home)
    state_path(home).unlink(missing_ok=True)
    # The author's config may have put Hyprland in a submap (caelestia:
    # "global"); if it stays in the running session, none of the next theme's
    # or the user's keybindings worked (mouse wheel included).
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") and _home(home) == Path.home():
        subprocess.run(["hyprctl", "dispatch", "submap", "reset"],
                       capture_output=True, check=False, timeout=10)
    return restored


def packages(root: Path, profile: str) -> tuple[list[str], list[str]]:
    manifest = load(root, profile)
    return manifest.packages_repo, manifest.packages_aur


_SESSION_VARS = {"HYPRLAND_INSTANCE_SIGNATURE", "WAYLAND_DISPLAY", "DISPLAY",
                 "DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR", "SWAYSOCK"}
_EXEC_LINE = re.compile(r"^(\s*)(exec(?:-once|-shutdown|r|r-once)?\s*=)", re.M)


_LUA_EXEC = re.compile(r"(?<!dsp\.)\bhl\.exec_cmd\(")


def _disarm_execs(home: Path) -> None:
    """Comments out exec lines in the temporary copy.

    ``Hyprland --verify-config`` really runs ``exec =`` lines; verification
    must not run the author's scripts (they are not needed to check the
    config's validity).
    """
    for conf in home.rglob("*.conf"):
        if conf.is_symlink() or not conf.is_file():
            continue
        text = conf.read_text(encoding="utf-8", errors="ignore")
        new = _EXEC_LINE.sub(r"\1# hyprsetup-verify: \2", text)
        if new != text:
            conf.write_text(new, encoding="utf-8")
    # Lua mode: hl.exec_cmd(...) runs while the config is read (nothingos calls
    # its startup block directly) — verification launched endless loops like
    # bt-agent.sh and left them running. hl.dsp.exec_cmd(...) in keybindings
    # only creates an action object and is left alone.
    for lua in home.rglob("*.lua"):
        if lua.is_symlink() or not lua.is_file():
            continue
        text = lua.read_text(encoding="utf-8", errors="ignore")
        # Leading ";": Lua treats a line starting with a parenthesis as a
        # continuation of the previous expression ("startup()" + "(...)" → call on nil).
        new = _LUA_EXEC.sub(";(function() end)(", text)
        if new != text:
            lua.write_text(new, encoding="utf-8")


def _unapplied_fixes(manifest: Manifest, home: Path) -> list[str]:
    """Fixes whose result is not visible in the installed tree (unmatched text etc.)."""
    missing = []
    for fix in manifest.fixes:
        if not _fix_applies(fix):
            continue
        path = expand(fix.file, home)
        if fix.delete:
            ok = not path.exists()
        else:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                text = None
            fill = [t.replace("{home}", str(home))
                    for t in (*fix.replace[1::2], fix.append)]
            ok = text is not None and all(t in text for t in fill)
        if not ok:
            missing.append(f"fix not applied: {fix.file} ({fix.why})")
    return missing


def verify(root: Path, profile: str, cache_home: Path | None = None) -> list[str]:
    """Tries the rice in a temporary home directory; returns Hyprland errors.

    The repo is read from the real cache (``cache_home``), so the network is
    only needed the first time. If Hyprland is not installed, only the install
    steps are tried.
    """
    manifest = load(root, profile)
    repo = fetch(manifest, cache_home)
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="hyprsetup-verify-",
                                     ignore_cleanup_errors=True) as tmp:
        home = Path(tmp) / "home"
        with tempfile.TemporaryDirectory() as staging:
            plan = prepare(manifest, repo, Path(staging), home,
                           groups=manifest.groups)
            for src, dest, _mode in plan.items:
                _copy(src, dest)
            for link_to, link_target in manifest.links:
                link = expand(link_to, home)
                link.parent.mkdir(parents=True, exist_ok=True)
                if not link.exists():
                    link.symlink_to(expand(link_target, home))
        errors += _unapplied_fixes(manifest, home)
        hypr = home / ".config/hypr"
        conf, lua = hypr / "hyprland.conf", hypr / "hyprland.lua"
        if conf.is_file():
            entries = [conf]
        elif lua.is_file():
            entries = [lua]              # the author's Lua config (0.56+)
        else:
            # This project's template generates the main file and sources
            # rice.conf (rice.lua in Lua mode); the same is installed so the
            # added lines are verified.
            entries = []
            if (hypr / "rice.conf").is_file():
                conf.write_text("source = ~/.config/hypr/rice.conf\n", encoding="utf-8")
                entries.append(conf)
            if (hypr / "rice.lua").is_file():
                lua.write_text('require("rice")\n', encoding="utf-8")
                entries.append(lua)
            if not entries:
                return errors        # a rice that does not touch Hyprland
        if shutil.which("Hyprland") is None:
            return errors
        _disarm_execs(home)
        # Without the session variables: the author's scripts (hyprctl reload
        # etc.) must not reach the user's running session.
        env = {k: v for k, v in os.environ.items()
               if k not in _SESSION_VARS}
        env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"),
                   XDG_DATA_HOME=str(home / ".local/share"),
                   XDG_STATE_HOME=str(home / ".local/state"),
                   XDG_CACHE_HOME=str(home / ".cache"),
                   XDG_RUNTIME_DIR=str(Path(tmp) / "run"))
        (Path(tmp) / "run").mkdir(mode=0o700, exist_ok=True)
        for entry in entries:
            out = subprocess.run(["Hyprland", "--verify-config", "-c", str(entry)],
                                 capture_output=True, text=True, timeout=120, env=env)
            text = out.stdout + out.stderr
            if "config ok" in text.lower():
                continue
            # Hyprland repeats the same error for every source chain; keep only
            # the innermost (real) error, once.
            seen: dict[str, None] = {}
            for line in text.splitlines():
                if line.startswith("Config error"):
                    inner = line.split("Config error in file ")[-1]
                    seen.setdefault("Config error in file " + inner.replace(str(home), "~"))
            errors += list(seen) or [f"{entry.name}: " + text[-400:].replace(str(home), "~")]
    return errors

