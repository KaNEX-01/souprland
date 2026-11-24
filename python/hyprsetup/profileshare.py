"""Sharing the desktop: export / import the look as a single file.

The exported ``.tar.gz``:

    souprland-profile/<name>.conf   profile card (presets/profile format)
    souprland-profile/wallpaper.*   wallpaper (if any)
    souprland-profile/README.txt    instructions for the recipient

An imported profile is written under ``~/.config/hyprsetup/shared/`` and shows up
in Profiles like any other profile.

Security: a shared file comes from someone else. Keys that could run commands
(custom bar modules, extra startup commands, environment), reveal location
(weather) or are machine-specific (displays, file paths) are neither exported nor
accepted on import — the allowlist is applied in both directions, and the archive's
contents are not trusted. Only the two known files are read from the archive, with
a size limit; nothing is extracted to disk as-is.

Wallpaper Engine scenes are not shared (Workshop content belongs to its author);
only the id is included, and the recipient subscribes on the Workshop.
"""

from __future__ import annotations

import io
import re
import tarfile
import time
import unicodedata
from pathlib import Path

from . import presets as presets_mod
from . import settings as schema

#: Folder shared profiles are imported into.
SHARED_DIR = presets_mod.shared_profiles_dir()
PREFIX = "souprland-profile"
MAX_CONF = 256 * 1024
MAX_IMAGE = 40 * 1024 * 1024
_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")

#: Shareable settings groups (group ids in the schema).
_GROUPS = {"layout", "decoration", "animation", "bar", "dock", "terminal", "launcher",
           "widget", "visualizer", "tone", "theme_schedule"}
#: Keys outside the schema groups that are still part of the profile.
_EXTRA = {"THEME", "CUSTOM_COLORS", "COLOR_SCHEME", "CURSOR_THEME", "CURSOR_SIZE",
          "GTK_THEME_NAME", "ICON_THEME_NAME", "FONT_FAMILY", "FONT_MONO", "FONT_SIZE",
          "BAR", "LAUNCHER", "TERMINAL", "NOTIFIER", "WALLPAPER_DAEMON",
          "BAR_PRESET", "TERM_PRESET", "LAUNCHER_PRESET", "WIDGET_SET", "WIDGET_STYLE", "WIDGETS",
          "BAR_MODULES_LEFT", "BAR_MODULES_CENTER", "BAR_MODULES_RIGHT",
          "WPENGINE_ID", "WPENGINE_SCALING", "WPENGINE_FPS", "WPENGINE_SILENT",
          "WINDOWRULES", "ACTIVE_OPACITY", "INACTIVE_OPACITY"}
#: Never carried over, even when in an allowed group.
_DENY = re.compile(r"(CMD|EXEC|CLICK|ARGS|ENV|COMMAND|SCRIPT|PATH|DIR|MONITOR|SCREEN|"
                   r"WEATHER|LOCATION|^USER_)")


def shareable_keys() -> set[str]:
    keys = {s.key for g in schema.GROUPS if g.id in _GROUPS for s in g.settings}
    keys |= _EXTRA
    return {k for k in keys if not _DENY.search(k)}


def _slug(text: str) -> str:
    # ı/ø/ß/æ/đ/ł have no ASCII decomposition; map them before NFKD drops them.
    text = text.lower().translate(str.maketrans({"ı": "i", "ø": "o", "ß": "ss",
                                                 "æ": "ae", "đ": "d", "ł": "l"}))
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", folded).strip("-")
    return slug[:40] or "paylasilan"  # legacy Turkish default id ("shared"), kept


def _quote(value: str) -> str | None:
    """The profile parser (presets._parse_value) knows no escapes and stops at the
    first matching quote; bash also sources profiles. So: double quotes, single
    quotes if the value contains " $ `, and None if neither works."""
    if not re.search(r'["$`]', value):
        return f'"{value}"'
    if "'" not in value:
        return f"'{value}'"
    return None


def card(name: str, title: str, desc: str, values: dict[str, str],
         wallpaper: str = "") -> str:
    keys = shareable_keys()
    title = " ".join(title.split()) or name
    desc = " ".join((desc or "").split())
    lines = ["# " + "-" * 75,
             f"#  preset: {name}",
             f"#  title: {title}",
             f"#  desc: {desc or 'Shared desktop.'} (from a shared file)",
             f"#  shared: {time.strftime('%Y-%m-%d')}",
             "# " + "-" * 75, ""]
    for key in sorted(values):
        quoted = _quote(str(values[key]))
        if key in keys and key != "WALLPAPER_IMAGE" and quoted is not None:
            lines.append(f"{key}={quoted}")
    if wallpaper and _quote(wallpaper):
        lines.append(f"WALLPAPER_IMAGE={_quote(wallpaper)}")
    return "\n".join(lines) + "\n"


def _anonymous(info: tarfile.TarInfo) -> tarfile.TarInfo:
    """Strip the user name/id from the shared file."""
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mode = 0o644
    return info


def export(values: dict[str, str], wallpaper: Path | None, dest: Path,
           title: str, desc: str = "") -> Path:
    """Writes the look to the ``dest`` archive; returns the archive path."""
    name = _slug(title)
    dest = Path(dest)
    if not dest.name.endswith((".tar.gz", ".tgz")):
        dest = dest.with_name(dest.name + ".tar.gz")
    image_name = ""
    if wallpaper and wallpaper.is_file() and wallpaper.suffix.lower() in _IMAGE_EXT \
            and wallpaper.stat().st_size <= MAX_IMAGE:
        image_name = f"wallpaper{wallpaper.suffix.lower()}"
    text = card(name, title, desc, values, image_name)
    readme = (f"{title}\n\nSouprland desktop profile. To import: Settings → "
              "System → Share my desktop → Import\nor: souprland share import "
              f"{dest.name}\n")
    if values.get("WPENGINE_ID") and values.get("WALLPAPER_DAEMON") == "wallpaperengine":
        readme += ("\nThe animated wallpaper is from Wallpaper Engine: Steam Workshop "
                   f"{values['WPENGINE_ID']} — plays once you subscribe\n"
                   "(https://steamcommunity.com/sharedfiles/filedetails/?id="
                   f"{values['WPENGINE_ID']}).\n")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dest, "w:gz") as tar:
        for member, data in ((f"{name}.conf", text.encode()), ("README.txt", readme.encode())):
            info = tarfile.TarInfo(f"{PREFIX}/{member}")
            info.size, info.mtime, info.mode = len(data), int(time.time()), 0o644
            tar.addfile(info, io.BytesIO(data))
        if image_name:
            tar.add(str(wallpaper), arcname=f"{PREFIX}/{image_name}", filter=_anonymous)
    return dest


def import_archive(path: Path, target: Path = SHARED_DIR,
                   root: Path | None = None) -> tuple[str, list[str]]:
    """Imports the archive; returns (profile name, skipped keys).

    If the name clashes with a bundled profile or one fetched by link, "-paylasim"
    (legacy Turkish id suffix, kept) is appended: otherwise the same-named profile
    would shadow it.
    """
    with tarfile.open(path, "r:gz") as tar:
        members = {m.name: m for m in tar.getmembers() if m.isfile()}
        confs = [n for n in members if re.fullmatch(rf"{PREFIX}/[a-z0-9-]+\.conf", n)]
        if len(confs) != 1:
            raise ValueError("no single profile card found in the archive")
        conf = members[confs[0]]
        if conf.size > MAX_CONF:
            raise ValueError("profile card is too large")
        text = tar.extractfile(conf).read().decode("utf-8", errors="replace")
        images = [n for n in members
                  if re.fullmatch(rf"{PREFIX}/wallpaper\.(png|jpe?g|webp)", n)]
        image = members[images[0]] if images else None
        image_data = (tar.extractfile(image).read()
                      if image is not None and image.size <= MAX_IMAGE else b"")

    name = Path(confs[0]).stem
    taken = {presets_mod.imported_profiles_dir() / f"{name}.conf"}
    if root is not None:
        taken.add(presets_mod.default_dir(root, "profile") / f"{name}.conf")
    if any(path_.is_file() for path_ in taken):
        name = f"{name}-paylasim"
    target.mkdir(parents=True, exist_ok=True)
    tmp = target / f".{name}.tmp.conf"
    tmp.write_text(text, encoding="utf-8")
    try:
        parsed = presets_mod.parse(tmp)
    finally:
        tmp.unlink(missing_ok=True)
    keys = shareable_keys()
    safe = {k: v for k, v in parsed.values.items() if k in keys}
    skipped = sorted(k for k in parsed.values if k not in keys and k != "WALLPAPER_IMAGE")
    wallpaper = ""
    if image_data:
        image_path = target / f"{name}{Path(image.name).suffix}"
        image_path.write_bytes(image_data)
        wallpaper = str(image_path)
    title = (parsed.title if getattr(parsed, "title", "") else name)
    # "(paylaşılan dosyadan)": legacy Turkish marker from pre-English exports.
    desc = re.sub(r"\s*\((?:from a shared file|paylaşılan dosyadan)\)$", "",
                  getattr(parsed, "desc", "") or "Shared desktop.")
    (target / f"{name}.conf").write_text(card(name, title, desc, safe, wallpaper),
                                         encoding="utf-8")
    return name, skipped

