#!/usr/bin/env python3
"""Renders preview images for the suggested icon sets (icons.SUGGESTED).

The Appearance → Icon theme gallery draws installed sets live with
Gtk.IconTheme; a set that is NOT installed used to sit there as an empty
card — users had to install the package without seeing what they would get.
This tool downloads each set's package into a temporary folder WITHOUT
installing it, draws the gallery's six sample icons (icons.PREVIEW_ICONS)
from it and writes ``assets/icon-previews/<theme>.png``. The card shows that
image when the set is not installed.

* pacman packages: downloaded from the ``pacman -Sp`` URL and unpacked with
  bsdtar (no root needed, nothing is written to the system).
* AUR packages: the AUR repo is cloned and built only into ``pkg/`` with
  ``makepkg --nodeps``; nothing is installed.

Usage::

    python3 tools/icon-previews.py               # missing previews
    python3 tools/icon-previews.py --force       # regenerate all
    python3 tools/icon-previews.py Fluent-dark   # only these set(s)
    python3 tools/icon-previews.py --check       # does every set have an image

The image layout matches the gallery card: 3×2 grid, 32 px icons, 4 px gap;
drawn at 2× scale (208×136) so it looks sharp.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from hyprsetup import icons  # noqa: E402

OUT = ROOT / "assets" / "icon-previews"
ICON, GAP, COLS, SCALE = 32, 4, 3, 2


def preview_path(theme: str) -> Path:
    return OUT / f"{theme}.png"


def _run(argv: list[str], cwd: Path | None = None) -> None:
    subprocess.run(argv, cwd=cwd, check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.PIPE)


def fetch_repo(package: str, work: Path) -> Path:
    # -dd: do not print the dependencies' URLs too (cosmic → pop-icon-theme).
    url = subprocess.run(["pacman", "-Sddp", "--print-format", "%l", package],
                         capture_output=True, text=True, check=True
                         ).stdout.split()[-1]
    archive = work / Path(url).name
    _run(["curl", "-fsSL", "-o", str(archive), url])
    dest = work / "root"
    dest.mkdir()
    _run(["bsdtar", "-xf", str(archive), "-C", str(dest), "usr/share/icons"])
    return dest / "usr/share/icons"


def _aur_base(package: str) -> str:
    """The AUR repo carries the package base (pkgbase) name, not the package's:
    yaru-icon-theme → yaru."""
    import json
    import urllib.request
    url = f"https://aur.archlinux.org/rpc/v5/info?arg[]={package}"
    with urllib.request.urlopen(url, timeout=30) as reply:
        results = json.load(reply).get("results") or []
    if not results:
        raise RuntimeError(f"{package} is not on the AUR")
    return results[0].get("PackageBase") or package


def fetch_aur(package: str, work: Path) -> Path:
    repo = work / package
    _run(["git", "clone", "--depth", "1",
          f"https://aur.archlinux.org/{_aur_base(package)}.git", str(repo)])
    _run(["makepkg", "--nodeps", "--skipinteg", "--noconfirm", "--noarchive",
          "--noprogressbar"], cwd=repo)
    # Split packages (fluent-icon-theme-git + fluent-cursor-theme-git) have
    # several folders under pkg/; the requested package's one is picked.
    own = repo / "pkg" / package / "usr/share/icons"
    if own.is_dir():
        return own
    found = sorted(repo.glob("pkg/*/usr/share/icons"))
    if not found:
        raise RuntimeError("package does not contain usr/share/icons")
    return found[0]


#: Ready-made Ubuntu packages for AUR packages whose build needs extra tools
#: (yaru: meson): (pool directory, file name prefix).
_DEB = {
    "yaru-icon-theme": ("https://archive.ubuntu.com/ubuntu/pool/main/y/yaru-theme/",
                        "yaru-theme-icon_"),
}


def fetch_deb(package: str, work: Path) -> Path:
    import re
    import urllib.request
    pool, prefix = _DEB[package]
    with urllib.request.urlopen(pool, timeout=30) as reply:
        listing = reply.read().decode(errors="replace")
    names = sorted(set(re.findall(rf'href="({re.escape(prefix)}[^"]+_all\.deb)"',
                                  listing)))
    if not names:
        raise RuntimeError(f"no {prefix}*.deb in {pool}")
    deb = work / names[-1]
    _run(["curl", "-fsSL", "-o", str(deb), pool + names[-1]])
    dest = work / "root"
    dest.mkdir()
    _run(["bsdtar", "-xf", str(deb), "-C", str(work)])
    data = next(work.glob("data.tar.*"))
    _run(["bsdtar", "-xf", str(data), "-C", str(dest)])
    return dest / "usr/share/icons"


def render(theme: str, icon_dirs: list[Path], out: Path) -> None:
    """Finds icons with Gtk.IconTheme (inheritance chain included) and draws them with cairo."""
    import cairo
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Rsvg", "2.0")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf, Gtk, Rsvg

    lookup = Gtk.IconTheme()
    lookup.set_search_path([str(d) for d in icon_dirs])
    lookup.set_theme_name(theme)
    # The theme folder must really exist: otherwise GTK falls back to hicolor,
    # draws the wrong icons and a wrong directory name in icons.SUGGESTED goes unnoticed.
    if theme not in {d.name for base in icon_dirs if base.is_dir()
                     for d in base.iterdir()}:
        found = sorted(d.name for d in icon_dirs[0].iterdir()) if icon_dirs[0].is_dir() else []
        raise RuntimeError(f"{theme} directory not in the package; the package has: {found}")

    rows = (len(icons.PREVIEW_ICONS) + COLS - 1) // COLS
    width = (COLS * ICON + (COLS - 1) * GAP) * SCALE
    height = (rows * ICON + (rows - 1) * GAP) * SCALE
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    px = ICON * SCALE
    for i, names in enumerate(icons.PREVIEW_ICONS):
        paintable = lookup.lookup_icon(names[0], list(names[1:]), ICON, SCALE,
                                       Gtk.TextDirection.NONE, 0)
        gfile = paintable.get_file()
        path = gfile.get_path() if gfile is not None else None
        if not path:
            continue
        x = (i % COLS) * (ICON + GAP) * SCALE
        y = (i // COLS) * (ICON + GAP) * SCALE
        cr.save()
        if path.endswith(".svg"):
            handle = Rsvg.Handle.new_from_file(path)
            viewport = Rsvg.Rectangle()
            viewport.x, viewport.y = x, y
            viewport.width = viewport.height = px
            handle.render_document(cr, viewport)
        else:
            from gi.repository import Gdk
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, px, px, True)
            Gdk.cairo_set_source_pixbuf(cr, pixbuf, x, y)
            cr.paint()
        cr.restore()
    out.parent.mkdir(parents=True, exist_ok=True)
    surface.write_to_png(str(out))


def build(sug: icons.IconSet, keep: Path) -> str:
    system = [Path("/usr/share/icons"), Path.home() / ".local/share/icons"]
    installed = {n.lower() for n in icons.available()}
    with tempfile.TemporaryDirectory(dir=keep) as tmp:
        work = Path(tmp)
        if sug.name.lower() in installed:
            dirs = system
            how = "installed"
        else:
            if sug.package in _DEB:
                fetched = fetch_deb(sug.package, work)
            else:
                fetched = (fetch_aur if sug.aur else fetch_repo)(sug.package, work)
            # The downloaded theme is searched first; the Inherits= chain (hicolor,
            # Adwaita, breeze…) comes from the system.
            dirs = [fetched, *system]
            how = "AUR" if sug.aur else "repo"
        render(sug.name, dirs, preview_path(sug.name))
    return how


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("themes", nargs="*")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--work", type=Path, default=None,
                        help="download folder (default: temporary)")
    args = parser.parse_args()

    if args.check:
        missing = [s.name for s in icons.SUGGESTED
                   if not preview_path(s.name).is_file()]
        for name in missing:
            print(f"no preview: {preview_path(name).relative_to(ROOT)}")
        return 1 if missing else 0

    wanted = {t.lower() for t in args.themes}
    work = args.work or Path(tempfile.gettempdir())
    work.mkdir(parents=True, exist_ok=True)
    failed = 0
    for sug in icons.SUGGESTED:
        if wanted and sug.name.lower() not in wanted:
            continue
        if preview_path(sug.name).is_file() and not args.force:
            continue
        try:
            how = build(sug, work)
        except (subprocess.CalledProcessError, RuntimeError, OSError) as exc:
            detail = getattr(exc, "stderr", b"") or b""
            if isinstance(detail, bytes):
                detail = detail.decode(errors="replace")
            print(f"✗ {sug.name} ({sug.package}): {exc} {detail.strip()[-300:]}")
            failed += 1
            continue
        print(f"✓ {sug.name} ({how})")
    if shutil.which("oxipng"):
        subprocess.run(["oxipng", "-q", "-o", "4", *map(str, OUT.glob("*.png"))],
                       check=False)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
