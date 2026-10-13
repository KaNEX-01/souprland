"""``python3 -m hyprsetup`` entry point. Called from the bash side."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .catalog import Catalog
from . import keybinds as keybinds_mod
from . import presets as presets_mod
from . import render as render_mod
from . import themes
from . import wallpaper as wallpaper_mod


def _cmd_render(args: argparse.Namespace) -> int:
    catalog = Catalog.load(args.catalog)
    variables = render_mod.parse_vars_file(Path(args.vars))
    selected = [s for s in args.selected.split(",") if s]
    binds = (keybinds_mod.Keybinds.load(args.keybinds)
             if args.keybinds and Path(args.keybinds).is_file() else None)

    # --strict: report templates that reference a {{VARIABLE}} never defined.
    # In a normal install silence is the right behavior (there are conditional
    # variables), but in a repo check this is the only way a typo becomes visible.
    unknown: dict[str, set[str]] | None = {} if args.strict else None

    written = render_mod.render_tree(
        templates_dir=Path(args.templates),
        out_dir=Path(args.out),
        variables=variables,
        catalog=catalog,
        selected=selected,
        keybinds=binds,
        unknown=unknown,
    )
    for path in written:
        print(path.relative_to(args.out))

    if unknown:
        print("\nTemplates referencing undefined variables:", file=sys.stderr)
        for template in sorted(unknown):
            names = ", ".join(sorted(unknown[template]))
            print(f"  {template}: {names}", file=sys.stderr)
        return 1
    return 0


def _cmd_gui(args: argparse.Namespace) -> int:
    try:
        if getattr(args, "quick", False):
            from .gui.quick import run as run_gui
        else:
            from .gui.app import run as run_gui
    except ImportError as exc:
        print(f"Could not start the GUI: {exc}", file=sys.stderr)
        print("Required packages: gtk4 libadwaita python-gobject python-cairo",
              file=sys.stderr)
        print("To install: sudo pacman -S --needed gtk4 libadwaita "
              "python-gobject python-cairo", file=sys.stderr)
        return 1
    _ensure_desktop_entry(Path(args.root))
    return run_gui(root=Path(args.root), catalog_path=Path(args.catalog),
                   templates=Path(args.templates))


def _ensure_desktop_entry(root: Path) -> None:
    """Make sure souprland.desktop is in the launcher and up to date (desktop_entry.py)."""
    from . import desktop_entry, selfupdate
    source = root.resolve() if selfupdate.is_source_tree(root) else selfupdate.source_root()
    try:
        desktop_entry.ensure(source)
    except Exception as exc:                              # noqa: BLE001
        print(f"Could not write the launcher entry: {exc}", file=sys.stderr)


def _cmd_watch(args: argparse.Namespace) -> int:
    """Watches settings.conf and applies it on every change (no GUI).

    While the settings app is open the window does the same job itself (see
    gui/app.py:_watch_conf). This command is for people managing the file from
    an editor or a script: while ``hyprsetup watch &`` runs, every change
    written to ``settings.conf`` reaches the desktop by itself.
    """
    import time

    from .apply import Applier
    from .gui.state import SetupState, config_path

    catalog = Catalog.load(args.catalog)
    root = Path(args.root).resolve()
    binds = keybinds_mod.load_default(root)
    applier = Applier(root, catalog, binds)

    path = Path(args.conf) if args.conf else config_path()
    print(f"Watching: {path}  (Ctrl+C to quit)")

    last = ""
    while True:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        if text and text != last:
            first = not last
            last = text
            state = SetupState(catalog)
            state.load_conf(path)
            if first and not args.apply_first:
                # Applying at startup is a needless round (and daemon restart)
                # in the normal case where the file and the desktop already
                # match; done only for whoever asks with --apply-first.
                print("Initial state read.")
            else:
                result = applier.apply(state.values, sorted(state.selected))
                if result.errors:
                    print(f"Error: {result.errors[0]}", file=sys.stderr)
                else:
                    detail = ", ".join(result.actions) or "no changes"
                    print(f"Applied: {len(result.written)} files · {detail}")
        time.sleep(max(0.2, args.interval))


def _cmd_cheatsheet(args: argparse.Namespace) -> int:
    """Keybinding cheat sheet — opened by MOD+/ (hypr/scripts/keybind-help.sh)."""
    try:
        from .gui.cheatsheet import run as run_cheatsheet
    except ImportError as exc:
        print(f"Could not open the keybinding cheat sheet: {exc}", file=sys.stderr)
        print("Required packages: gtk4 libadwaita python-gobject", file=sys.stderr)
        return 1
    return run_cheatsheet(root=Path(args.root), catalog_path=Path(args.catalog))


def _cmd_share(args: argparse.Namespace) -> int:
    """Export the desktop to a file, or import a shared file as a profile."""
    from . import profileshare
    from .apply import Applier
    from .gui.state import SetupState, config_path

    if args.action == "import":
        try:
            name, skipped = profileshare.import_archive(Path(args.file),
                                                        root=Path(args.root).resolve())
        except Exception as exc:   # noqa: BLE001 — same as the GUI: a broken archive can raise anything
            print(f"could not import {args.file}: {exc}", file=sys.stderr)
            return 1
        print(f"Imported: {name} → {profileshare.SHARED_DIR / (name + '.conf')}")
        print("It can be applied from Profiles.")
        if skipped:
            print("Settings not imported, for safety: " + ", ".join(skipped))
        return 0
    root = Path(args.root).resolve()
    catalog = Catalog.load(root / "config/components.json")
    state = SetupState(catalog)
    state.load_conf(config_path())
    values = dict(state.values)
    for cat in catalog.categories:
        if cat.var and state.primary(cat.id):
            values[cat.var] = state.primary(cat.id)
    wallpaper = Applier(root, catalog).wallpaper_file(state.values)
    out = profileshare.export(values, wallpaper, Path(args.file),
                              args.title or "My desktop", args.desc)
    print(f"Exported: {out}")
    return 0


def _cmd_theme_schedule(args: argparse.Namespace) -> int:
    """Day/night theme: switches and applies the theme if needed."""
    from . import themeschedule

    root = Path(args.root).resolve()
    print(themeschedule.run(root, root / "config/components.json"))
    return 0


def _cmd_self_update(args: argparse.Namespace) -> int:
    """Refreshes the installed copy from the source repo (optionally git pull first)."""
    from . import selfupdate

    src = Path(args.source).resolve() if args.source else selfupdate.source_root()
    if src is None and selfupdate.is_source_tree(Path(args.root)):
        src = Path(args.root).resolve()
    if src is None or not selfupdate.is_source_tree(src):
        print("Source repo not found; pass it with --source.", file=sys.stderr)
        return 1
    if args.pull:
        info = selfupdate.git_status(src)
        if info["git"] and info["upstream"]:
            ok, text = selfupdate.git_pull(src)
            print(("git: " if ok else "git pull failed: ") + text)
            if not ok:
                return 1
    changed = selfupdate.differs(src)
    if args.check:
        print(f"{len(changed)} files differ" if changed else "Installed copy is up to date.")
        return 1 if changed else 0
    selfupdate.sync(src)
    print(f"Updated: {len(changed)} files ({src} → {selfupdate.INSTALL})"
          if changed else "Installed copy is already up to date.")
    return 0


def _cmd_reapply(args: argparse.Namespace) -> int:
    """Re-applies settings.conf once (install.sh --update)."""
    message = _reapply_settings(Path(args.root).resolve(),
                                start_missing=not args.no_start)
    print(message)
    return 1 if message.startswith("reapply error") else 0


def _cmd_switcher(args: argparse.Namespace) -> int:
    """ALT+Tab window switcher (opened by hypr/scripts/windowswitch.py)."""
    try:
        from .gui.switcher import run as run_switcher
    except ImportError as exc:
        print(f"Could not open the window switcher: {exc}", file=sys.stderr)
        print("Required packages: gtk4 libadwaita python-gobject", file=sys.stderr)
        return 1
    return run_switcher(root=Path(args.root), catalog_path=Path(args.catalog))


def _reapply_settings(root: Path, start_missing: bool = False) -> str:
    """Re-applies settings.conf once (same steps as watch).

    A rice install finishes in the terminal, independently of the settings
    app: the paths the rice owns and the categories it brings (rice.json) are
    only known at that moment. So this project's own configuration (e.g.
    hyprland.conf sourcing rice.conf, its own bar shutting down) is
    regenerated at the END of the install.
    """
    from .apply import Applier
    from .gui.state import SetupState, config_path

    path = config_path()
    if not path.is_file():
        return "no settings file, reapply skipped"
    catalog = Catalog.load(root / "config" / "components.json")
    binds = keybinds_mod.load_default(root)
    state = SetupState(catalog)
    state.load_conf(path)
    applier = Applier(root, catalog, binds)
    result = applier.apply(state.values, sorted(state.selected))
    if start_missing:
        started = applier.start_missing(state.selected)
        if started:
            print("started: " + ", ".join(started))
    if result.errors:
        return f"reapply error: {result.errors[0]}"
    return f"settings re-applied ({len(result.written)} files)"


def _cmd_rice(args: argparse.Namespace) -> int:
    """Rices (rice.py): installs the author's files from a pinned commit."""
    from . import presets as presets_mod
    from . import rice, transition

    root = Path(args.root).resolve()
    if args.action == "list":
        for name in rice.all_profiles(root):
            m = rice.load(root, name)
            local = all(rice.vendor_archive(m.vendor, u, c) for u, c in m.sources())
            origin = "imported" if rice.is_imported(root, name) else (
                "local " if local else "GitHub")
            print(f"{name:14} {m.repo.removeprefix('https://github.com/'):40} "
                  f"{m.commit[:8]}  {origin}  "
                  f"variants: {', '.join(m.variants) or '-'}")
        return 0
    if args.action == "import":
        from . import importer
        if not args.name:
            print("usage: rice import <github link> [--as NAME] [--commit SHA]",
                  file=sys.stderr)
            return 2
        try:
            report = importer.analyze(args.name, name=args.as_name, commit=args.commit)
        except (RuntimeError, ValueError) as exc:
            print(f"could not import: {exc}", file=sys.stderr)
            return 1
        if rice.is_rice(root, report.name) and not rice.is_imported(root, report.name):
            print(f"'{report.name}' is the name of a rice shipped with the project; "
                  "pick another name with --as",
                  file=sys.stderr)
            return 2
        if not args.dry_run:
            path = importer.write(report)
            importer.verify(root, report)
        print("\n".join(importer.describe(report)))
        if args.dry_run:
            print("\n(--dry-run: manifest not written)")
            return 0
        from . import mix
        print("\nScanning mix parts (wallpapers, colors, look)…")
        try:
            mix.scan_imported(root, report.name)
        except Exception as exc:                                  # noqa: BLE001
            print(f"  could not scan: {exc}")
        print(f"\nmanifest: {path}")
        print(f"to install:  python3 -m hyprsetup rice install {report.name}")
        print("parts:       python3 -m hyprsetup mix list  (Soup Maker page)")
        return 0
    if args.action == "forget":
        from . import importer
        if not args.name or not importer.remove(args.name):
            print(f"no imported rice: {args.name}", file=sys.stderr)
            return 2
        print(f"deleted: {args.name} (if installed, first: rice uninstall)")
        return 0
    if args.action == "vendor":
        names = [args.name] if args.name else [
            path.name[: -len(rice.SUFFIX)] for path in
            sorted(presets_mod.default_dir(root, "profile").glob("*" + rice.SUFFIX))]
        failed = 0
        for name in names:
            try:
                archives = rice.vendor_profile(root, name)
            except (RuntimeError, OSError, ValueError) as exc:
                print(f"{name}: {exc}", file=sys.stderr)
                failed += 1
                continue
            size = sum(a.stat().st_size for a in archives) / 1024 / 1024
            print(f"{name:14} {len(archives)} archives · {size:.1f} MB")
        return 1 if failed else 0
    if args.action == "bar":
        from . import ricebar
        bar = ricebar.detect(root)
        if bar is None:
            print("The active rice has no adjustable bar.")
            return 1
        print(f"Active bar: {bar.label} [{bar.kind}]")
        if bar.note:
            print(f"  {bar.note}")
        pairs = [a for a in (args.name.split(",") if args.name else []) if "=" in a]
        if pairs:
            changes = {}
            types = {f.key: f.type for f in bar.fields}
            for pair in pairs:
                key, _, value = pair.partition("=")
                kind = types.get(key.strip())
                if kind is None:
                    print(f"unknown field: {key}", file=sys.stderr)
                    return 2
                changes[key.strip()] = (int(value) if kind == "int" else
                                        value.lower() in ("1", "true", "on") if kind == "bool"
                                        else value)
            ricebar.write(bar, changes)
            print("applied:", changes)
        for key, value in ricebar.read(bar).items():
            print(f"  {key:20} {value}")
        return 0
    if args.action == "status":
        state = rice.read_state()
        if not state:
            print("No active rice.")
            return 0
        print(f"{state['profile']} · variant {state.get('variant') or '-'} · "
              f"{state['repo']}@{state['commit'][:8]}")
        print(f"backup: {state.get('backup')}")
        for path in state.get("owned", []):
            print(f"  {path}")
        return 0
    if args.action == "uninstall":
        # Keep the screen from going black until the old bar/wallpaper close
        # and yours come up (transition.py).
        fade = (transition.begin(label="Cooking your own desktop…")
                if rice.read_state() else None)
        try:
            restored = rice.uninstall()
            print(f"Rice uninstalled; {len(restored)} files restored from backup.")
            if not args.no_reapply:
                print(_reapply_settings(root, start_missing=True))
        finally:
            if fade:
                fade.finish()
        return 0
    if not args.name:
        print("profile name required", file=sys.stderr)
        return 2
    if not rice.is_rice(root, args.name):
        print(f"not a rice: {args.name}", file=sys.stderr)
        return 2
    manifest = rice.load(root, args.name)
    if args.action == "show":
        print(f"{manifest.name}: {manifest.repo} @ {manifest.commit}")
        print(f"post: {manifest.post}\nlicense: {manifest.license or 'none'}")
        for url, commit in manifest.sources():
            archive = rice.vendor_archive(manifest.vendor, url, commit)
            print(f"  source {url}@{commit[:8]}: "
                  f"{archive.relative_to(root) if archive else 'GitHub (no archive)'}")
        for item in manifest.installs:
            origin = f" ← {item.repo}@{item.commit[:8]}" if item.repo else ""
            print(f"  [{item.group}] {item.src} → {item.dest} ({item.mode}){origin}")
        for name, v in manifest.variants.items():
            mark = "*" if name == manifest.default_variant else " "
            print(f" {mark} variant {name}: {v.title} "
                  f"{'(no wallpaper)' if not v.wallpaper else ''}")
        for note in manifest.notes:
            print(f"  note: {note}")
        return 0
    if args.action == "packages":
        repo, aur = rice.packages(root, args.name)
        print(" ".join(repo))
        print(" ".join(aur))
        return 0
    if args.action == "verify":
        errors = rice.verify(root, args.name)
        for line in errors:
            print(f"  {line}")
        print(f"{args.name}: {'Hyprland config valid' if not errors else f'{len(errors)} errors'}")
        return 1 if errors else 0
    if args.action == "variant":
        ran = rice.set_variant(root, args.name, args.variant)
        print(f"Variant: {args.variant} ({len(ran)} commands)")
        return 0
    # install
    # Keep the screen from going black between themes: the old desktop stays
    # frozen and fades out once the new theme is ready (transition.py).
    fade = None if args.dry_run else transition.begin(label=f"Cooking {args.name}…")
    try:
        return _rice_install(root, args)
    finally:
        if fade:
            fade.finish()


def _rice_install(root: Path, args: argparse.Namespace) -> int:
    from . import rice

    result = rice.install(root, args.name, variant=args.variant or "",
                          groups=args.group or [], dry_run=args.dry_run,
                          start_later=not args.dry_run)
    verb = "to install" if args.dry_run else "installed"
    print(f"{args.name}: {len(result.installed)} targets {verb}")
    for path in result.installed:
        print(f"  {path}")
    for line in result.migrated:
        print(f"  Hyprland syntax updated — {line}")
    if result.backup_dir:
        print(f"Backup of the old files: {result.backup_dir}")
    for warning in result.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    if not args.dry_run and not args.no_reapply:
        print(_reapply_settings(root))
    if not args.dry_run:
        from . import ricebar
        # Per-theme saved bar settings (the settings app's bar page) are
        # written again because the author's files were just reinstalled.
        if ricebar.reapply(root):
            print("your bar settings were re-applied")
        # exec-once lines only run at login; start the author's startup
        # programs now so the rice shows up right away.
        provides = rice.read_state().get("provides", [])
        started, note = rice.start_session(
            root, args.name, args.variant or "",
            skip=os.environ.get("HYPRSETUP_AUTOSTART_SKIP", ""),
            pending=result.session)
        if rice.read_state().get("provides", []) != provides:
            # A role went back to the user (its program is not installed):
            # their bar/notifier starts again.
            print(_reapply_settings(root, start_missing=True))
        if started:
            print(f"started ({len(started)}): " + ", ".join(c.split()[0] for c in started))
        if note:
            print(f"NOTE: {note}")
    return 0


def _cmd_wallcolors(args: argparse.Namespace) -> int:
    """Wallpaper colors (wallcolors.py): ricemood/pywal templates.

    ``follow`` is called from wallpaper.sh: every time the wallpaper changes
    (rotation included) the desktop (if THEME="auto") and the enabled
    templates take the new image's colors.
    """
    import fcntl

    from . import wallcolors
    from .gui.state import SetupState, config_path

    root = Path(args.root).resolve()
    catalog = Catalog.load(root / "config" / "components.json")
    state = SetupState(catalog)
    if config_path().is_file():
        state.load_conf(config_path())
    values = dict(state.values)
    image = Path(args.image).expanduser() if args.image else wallcolors.current_wallpaper(values)
    dark = (values.get("COLOR_SCHEME", "dark").strip().lower() != "light")
    backend = values.get("PALETTE_BACKEND", "auto") or "auto"

    if args.action == "templatize":
        if not args.file:
            print("usage: wallcolors templatize FILE", file=sys.stderr)
            return 2
        reference = {k[4:]: v for k, v in render_mod.derived_vars(
            values, catalog, sorted(state.selected)).items()
            if k.startswith("COL_") and k[4:] in themes.KEYS}
        text, mapping = wallcolors.templatize(
            Path(args.file).expanduser().read_text(encoding="utf-8", errors="replace"), reference)
        print(text, end="")
        for old, role in mapping.items():
            print(f"# #{old} → {role}", file=sys.stderr)
        return 0
    config = wallcolors.load_config()
    if args.action == "follow":
        # wallpaper.sh calls this on every change: if there is nothing to do,
        # color extraction (~1 s) is skipped entirely.
        desktop = values.get("THEME", "").strip().lower() == "auto" and config.get("desktop", True)
        if not config.get("follow", True) or os.environ.get("HYPRSETUP_WALLCOLORS") or not (
                desktop or any(e.enabled for e in wallcolors.entries(root, config))):
            return 0
    if image is None or not image.is_file():
        print("wallpaper not found (pass it with --image)", file=sys.stderr)
        return 1
    colors = wallcolors.extract(image, dark=dark, backend=backend, values=values)

    if args.action == "show":
        def swatch(name: str, value: str) -> str:
            r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
            return f"\x1b[48;2;{r};{g};{b}m    \x1b[0m {name:13} #{value}"
        print(f"image: {image}")
        for name, value in colors.vibrant.items():
            print(swatch(name, value))
        for name, value in colors.roles.items():
            print(swatch(name, value))
        return 0
    if args.action == "render":
        if not args.file:
            print("usage: wallcolors render FILE [--syntax pywal]", file=sys.stderr)
            return 2
        text = Path(args.file).expanduser().read_text(encoding="utf-8")
        print(wallcolors.render(text, colors, args.syntax), end="")
        return 0

    if args.action == "follow":
        # Re-applying the desktop may restart the wallpaper daemon but does
        # not call wallpaper.sh; still, a marker is left for child processes
        # to guard against a loop.
        os.environ["HYPRSETUP_WALLCOLORS"] = "1"
    lock_path = wallcolors.cache_path().with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as lock:
        # Two changes in a row (fast rotation) must not write over each other.
        fcntl.flock(lock, fcntl.LOCK_EX)
        if values.get("THEME", "").strip().lower() == "auto" and config.get("desktop", True) \
                and config_path().is_file():
            from .apply import Applier

            binds = keybinds_mod.load_default(root)
            # Not written to the settings file: rotation must not change
            # settings.conf every time; the palette comes from the image on screen.
            desktop = dict(values, WALLPAPER_PATH=str(image))
            result = Applier(root, catalog, binds).apply(desktop, sorted(state.selected))
            print(f"desktop colors: {len(result.written)} files")
        result = wallcolors.apply(root, colors, config)
    for path in result.written:
        print(f"written: {path}")
    for error in result.errors:
        print(f"error: {error}", file=sys.stderr)
    return 1 if result.errors else 0


def _cmd_mix(args: argparse.Namespace) -> int:
    """Mix (mix.py): picking parts from rices and combining them."""
    from . import mix

    root = Path(args.root).resolve()
    if args.action == "scan":
        print("Scanning parts (authors' files, wallpapers)…")
        mix.scan(root, args.items or None)
        print(f"written: {mix.parts_path(root)}")
        return 0
    parts = mix.load_parts(root)
    app = mix.app_parts(root)
    if args.action == "list":
        slots = args.items or [*mix.SLOT_IDS, *mix.APP_SLOT_IDS]
        for slot, label in mix.SLOTS:
            if slot not in slots:
                continue
            print(f"{slot} — {label}")
            for value, text in mix.options(parts, slot):
                print(f"  {value:28} {text}")
        for slot, label in mix.APP_SLOTS:
            if slot not in slots:
                continue
            print(f"{slot} — {label}")
            for value, _part in app.get(slot, []):
                print(f"  {value:28} {mix.part_label(root, value)}")
        return 0
    state = mix.read_state()
    if args.action == "show":
        for slot, label in mix.SLOTS:
            print(f"{label:22} {mix.describe(parts, slot, state['slots'].get(slot, ''))}")
        for slot, label in mix.APP_SLOTS:
            ref = state.get("parts", {}).get(slot, "")
            print(f"{label:22} {mix.part_label(root, ref) if ref else 'your own settings'}")
        for warning in (state.get("installed") or {}).get("warnings", []):
            print(f"  note: {warning}")
        if state["saved"]:
            print("saved: " + ", ".join(sorted(state["saved"])))
        return 0
    if args.action == "save":
        if len(args.items) != 1:
            print("usage: mix save NAME", file=sys.stderr)
            return 2
        mix.save(args.items[0])
        print(f"saved: {args.items[0]}")
        return 0
    if args.action == "load":
        if len(args.items) != 1:
            print("usage: mix load NAME", file=sys.stderr)
            return 2
        try:
            slots = mix.saved(args.items[0])
        except KeyError:
            print(f"no saved mix: {args.items[0]}", file=sys.stderr)
            return 2
    elif args.action == "clear":
        slots = {slot: "" for slot in (args.items or [*mix.SLOT_IDS, *mix.APP_SLOT_IDS])}
    else:                                                       # set
        slots = {}
        all_slots = (*mix.SLOT_IDS, *mix.APP_SLOT_IDS)
        for item in args.items:
            slot, sep, value = item.partition("=")
            if not sep or slot not in all_slots:
                print(f"expected slot=value ({', '.join(all_slots)}): {item}",
                      file=sys.stderr)
                return 2
            valid = ({v for v, _t in mix.options(parts, slot)} if slot in mix.SLOT_IDS
                     else {v for v, _p in app.get(slot, [])})
            if value and value not in valid:
                print(f"unknown part for {slot}: {value} "
                      f"(list: python3 -m hyprsetup mix list {slot})", file=sys.stderr)
                return 2
            slots[slot] = value
    from . import rice, transition

    # The active rice will be removed: keep the transition from going black.
    fade = transition.begin(label="Cooking your mix…") if rice.read_state() else None
    try:
        try:
            changes = mix.apply(root, slots)
        except (RuntimeError, KeyError, ValueError) as exc:
            print(f"could not apply the mix: {exc}", file=sys.stderr)
            return 1
        print(f"{len(changes)} settings written")
        if not args.no_reapply:
            print(_reapply_settings(root, start_missing=True))
            started = mix.launch_parts()
            if started:
                print("started: " + ", ".join(c.split()[0] for c in started))
    finally:
        if fade:
            fade.finish()
    return 0


def _cmd_backups(args: argparse.Namespace) -> int:
    """Lists or prunes the backup directories (see backups.py)."""
    from . import backups

    base = backups.root()
    if args.action == "prune":
        for directory in backups.prune(base):
            print(f"deleted: {directory}")
        return 0
    dirs = sorted(d for d in base.iterdir() if d.is_dir()) if base.is_dir() else []
    for index, directory in enumerate(dirs):
        note = "  (first backup — state before hyprsetup)" if index == 0 else ""
        print(f"{directory.name}  {backups.kind_of(directory):7}{note}")
    return 0


def _cmd_check_schema(args: argparse.Namespace) -> int:
    """Compares the settings.py schema with the lib/config.sh defaults."""
    import re

    from . import settings as settings_mod

    text = Path(args.config_sh).read_text(encoding="utf-8")
    # capture  : "${KEY:=VALUE}"  lines
    shell_defaults = {
        m.group(1): m.group(2)
        for m in re.finditer(r':\s*"\$\{([A-Z0-9_]+):=(.*?)\}"', text)
    }
    declared = set(re.findall(r"^\s{4}([A-Z0-9_ ]+)$", text, re.M))
    config_vars: set[str] = set()
    for line in declared:
        config_vars.update(line.split())

    problems = 0
    for setting in settings_mod.all_settings():
        if setting.key not in shell_defaults:
            print(f"MISSING   {setting.key}: no default in lib/config.sh")
            problems += 1
            continue
        # lib/config.sh writes some paths ESCAPED (: "${RECORD_DIR:=\$HOME/
        # Videos}"): the value must be resolved at runtime inside the generated
        # script, the installing machine's home directory must not be baked in.
        # On the schema side these paths are in readable "~/..." form, so the
        # escape is removed first — otherwise every such setting would be
        # reported as "DIFFERENT".
        shell_value = (shell_defaults[setting.key]
                       .replace("\\$HOME", "$HOME")
                       .replace("$HOME", "~"))
        if shell_value != setting.default:
            print(f"DIFFERENT {setting.key}: config.sh={shell_value!r} "
                  f"schema={setting.default!r}")
            problems += 1

    for setting in settings_mod.all_settings():
        if setting.kind == "choice" and setting.choices and setting.default not in [
                c[0] for c in setting.choices]:
            print(f"INVALID   {setting.key}: default '{setting.default}' "
                  f"is not among the choices")
            problems += 1

    total = len(settings_mod.all_settings())
    if problems:
        print(f"\n{problems} problems found ({total} settings checked).")
        return 1
    print(f"All {total} settings are consistent with lib/config.sh.")
    return 0


def _cmd_presets(args: argparse.Namespace) -> int:
    """Lists presets (same data as install.sh --list-presets/-bars/-widgets)."""
    directory = Path(args.dir)
    # --dir may point at the repo root or directly at a preset directory.
    if not sorted(directory.glob("*.conf")):
        directory = presets_mod.default_dir(directory.parent, args.kind)
    items = presets_mod.load_all(directory)
    if not items:
        print(f"{args.kind}: no presets found: {directory}", file=sys.stderr)
        return 1
    for preset in items:
        print(f"{preset.name:<22} {preset.label}")
        if preset.desc:
            print(f"{'':<22} {preset.desc}")
        if args.kind == "profile":
            bar = preset.values.get("BAR_PRESET", "—")
            print(f"{'':<22} theme: {preset.theme} · bar: {bar} · {len(preset.values)} settings")
        else:
            print(f"{'':<22} {len(preset.values)} settings")
    return 0


def _cmd_wallpaper(args: argparse.Namespace) -> int:
    """Generates a wallpaper from the theme palette (called by install.sh)."""
    if args.list:
        for name, desc in sorted(wallpaper_mod.STYLES.items()):
            print(f"{name:<8} {desc}")
        return 0
    missing = [f"--{n}" for n in ("theme", "style", "out")
               if not getattr(args, n)]
    if missing:
        print(f"Missing argument: {', '.join(missing)}", file=sys.stderr)
        return 2
    try:
        path = wallpaper_mod.generate(
            args.theme, args.style, Path(args.out),
            (args.width, args.height), args.colors)
    except ValueError as exc:
        print(f"Could not generate wallpaper: {exc}", file=sys.stderr)
        return 1
    print(f"{path} ({path.stat().st_size // 1024} KB)")
    return 0


def _cmd_keybinds(args: argparse.Namespace) -> int:
    """Lists keybindings category by category (with KEYBINDS overrides applied)."""
    binds = keybinds_mod.Keybinds.load(args.keybinds)
    overrides = keybinds_mod.parse_overrides(args.overrides)
    mod_key = args.mod or "SUPER"

    # Conditions (require) cannot be evaluated here — which components are
    # installed is unknown; all are listed, removed ones are marked separately.
    removed: list[str] = []
    combos: dict[str, list[str]] = {}

    for category in binds.categories:
        print(f"\n{category.title}")
        for bind in category.binds:
            combo = keybinds_mod.normalize(overrides.get(bind.id, bind.keys))
            if not combo:
                removed.append(bind.id)
                continue
            combos.setdefault(combo, []).append(bind.id)
            note = f"  · requires: {bind.require}" if bind.require else ""
            print(f" {'*' if bind.id in overrides else ' '} "
                  f"{keybinds_mod.display(combo, mod_key):<26} "
                  f"{bind.title:<32} {bind.id}{note}")

    if removed:
        print("\nRemoved: " + ", ".join(removed))

    clashes = {combo: ids for combo, ids in combos.items() if len(ids) > 1}
    for combo, ids in clashes.items():
        print(f"\nCONFLICT  {keybinds_mod.display(combo, mod_key)}: {', '.join(ids)}")

    print("\n* = changed via KEYBINDS · conditional keybindings are only generated "
          "if the related component is installed")
    return 1 if clashes else 0


def _cmd_anims(_args: argparse.Namespace) -> int:
    """Lists the animation presets with sample durations."""
    for name, preset in render_mod.ANIMATION_PRESETS.items():
        animations = preset["animations"]
        mark = " (default)" if name == render_mod.DEFAULT_ANIMATION_PRESET else ""
        print(f"{name:<10} {preset['label']}{mark}")
        print(f"{'':<10} {preset['desc']}")
        if animations:
            durations = {leaf: duration for leaf, duration, _, _ in animations}
            print(f"{'':<10} window open {durations.get('windowsIn')}, "
                  f"workspace {durations.get('workspaces')}, "
                  f"border {durations.get('border')} "
                  f"· {len(preset['curves'])} curves")
        print()
    return 0


def _cmd_themes(_args: argparse.Namespace) -> int:
    for name in themes.names():
        palette = themes.THEMES[name]
        print(f"{name:<22} bg=#{palette['BG']} accent=#{palette['ACCENT']} fg=#{palette['FG']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hyprsetup", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_render = sub.add_parser("render", help="render the templates")
    p_render.add_argument("--catalog", required=True)
    p_render.add_argument("--templates", required=True)
    p_render.add_argument("--vars", required=True)
    p_render.add_argument("--selected", default="")
    p_render.add_argument("--keybinds", default="config/keybinds.json")
    p_render.add_argument("--out", required=True)
    p_render.add_argument("--strict", action="store_true",
                          help="report templates referencing undefined variables "
                               "and exit with 1 (for repo checks)")
    p_render.set_defaults(func=_cmd_render)

    p_themes = sub.add_parser("themes", help="list the available themes")
    p_themes.set_defaults(func=_cmd_themes)

    p_anims = sub.add_parser("anims", help="list the animation presets")
    p_anims.set_defaults(func=_cmd_anims)

    p_presets = sub.add_parser("presets", help="list the built-in look presets")
    p_presets.add_argument("--dir", default="presets")
    p_presets.add_argument("--kind", default="profile", choices=presets_mod.KINDS,
                           help="Axis to list (default: profile)")
    p_presets.set_defaults(func=_cmd_presets)

    p_wp = sub.add_parser("wallpaper",
                          help="generate a wallpaper from the theme colors")
    # Not required so that --list can be used on its own; when missing,
    # _cmd_wallpaper gives a meaningful error.
    p_wp.add_argument("--theme")
    p_wp.add_argument("--style", choices=sorted(wallpaper_mod.STYLES))
    p_wp.add_argument("--out")
    p_wp.add_argument("--width", type=int, default=wallpaper_mod.DEFAULT_SIZE[0])
    p_wp.add_argument("--height", type=int, default=wallpaper_mod.DEFAULT_SIZE[1])
    p_wp.add_argument("--colors", default="",
                      help="same format as CUSTOM_COLORS: ACCENT=ff8800;;BG=101014")
    p_wp.add_argument("--list", action="store_true",
                      help="list the patterns and exit")
    p_wp.set_defaults(func=_cmd_wallpaper)

    p_keys = sub.add_parser("keybinds", help="list the keybindings")
    p_keys.add_argument("--keybinds", default="config/keybinds.json")
    p_keys.add_argument("--overrides", default="",
                        help='KEYBINDS string: "terminal=MOD+T;;lock="')
    p_keys.add_argument("--mod", default="SUPER", help="what the MOD key maps to")
    p_keys.set_defaults(func=_cmd_keybinds)

    p_rice = sub.add_parser("rice", help="rices (the author's files)")
    p_rice.add_argument("action", choices=("list", "show", "install", "uninstall", "vendor", "bar",
                                           "variant", "packages", "status", "verify",
                                           "import", "forget"))
    p_rice.add_argument("name", nargs="?", default="")
    p_rice.add_argument("--variant", default="")
    p_rice.add_argument("--group", action="append",
                        help="optional group (e.g. shell, editor)")
    p_rice.add_argument("--dry-run", action="store_true")
    p_rice.add_argument("--as", dest="as_name", default="",
                        help="import: name of the rice (default: owner-repo)")
    p_rice.add_argument("--commit", default="",
                        help="import: pin to this commit (default: latest)")
    p_rice.add_argument("--no-reapply", action="store_true",
                        help="do not re-apply settings.conf after installing")
    p_rice.add_argument("--root", default=".", help="script root directory")
    p_rice.set_defaults(func=_cmd_rice)

    p_mix = sub.add_parser("mix", help="mix: pick parts from rices")
    p_mix.add_argument("action", choices=("list", "show", "set", "clear", "save", "load",
                                          "scan"))
    p_mix.add_argument("items", nargs="*", default=[],
                       help="set: slot=value (e.g. wallpaper=ad1822/sis colors=wallpaper "
                            "look=nothingos) · clear/list: slots · save/load: name · "
                            "scan: profiles")
    p_mix.add_argument("--no-reapply", action="store_true",
                       help="write settings.conf but do not apply it")
    p_mix.add_argument("--root", default=".", help="script root directory")
    p_mix.set_defaults(func=_cmd_mix)

    p_wc = sub.add_parser("wallcolors",
                          help="apply the wallpaper colors to programs (ricemood/pywal)")
    p_wc.add_argument("action", choices=("show", "apply", "follow", "render", "templatize"))
    p_wc.add_argument("file", nargs="?", default="",
                      help="render/templatize: template or config file")
    p_wc.add_argument("--image", default="", help="image (default: the wallpaper on screen)")
    p_wc.add_argument("--syntax", default="ricemood", choices=("ricemood", "pywal"))
    p_wc.add_argument("--root", default=".", help="script root directory")
    p_wc.set_defaults(func=_cmd_wallcolors)

    p_backups = sub.add_parser("backups", help="list / prune backups")
    p_backups.add_argument("action", choices=("list", "prune"), nargs="?",
                           default="list")
    p_backups.set_defaults(func=_cmd_backups)

    p_check = sub.add_parser("check-schema",
                             help="settings.py vs lib/config.sh consistency")
    p_check.add_argument("--config-sh", default="lib/config.sh")
    p_check.set_defaults(func=_cmd_check_schema)

    p_watch = sub.add_parser(
        "watch", help="watch settings.conf and apply it on change")
    p_watch.add_argument("--catalog", default="config/components.json")
    p_watch.add_argument("--root", default=".", help="script root directory")
    p_watch.add_argument("--conf", default="",
                         help="file to watch (default: "
                              "~/.config/hyprsetup/settings.conf)")
    p_watch.add_argument("--interval", type=float, default=1.0,
                         help="how often to poll the file, in seconds")
    p_watch.add_argument("--apply-first", action="store_true",
                         help="apply on the first read too")
    p_watch.set_defaults(func=_cmd_watch)

    p_cheat = sub.add_parser("cheatsheet",
                             help="keybinding cheat sheet (GTK4)")
    p_cheat.add_argument("--catalog", default="config/components.json")
    p_cheat.add_argument("--root", default=".", help="script root directory")
    p_cheat.set_defaults(func=_cmd_cheatsheet)

    p_switch = sub.add_parser(
        "switcher", help="ALT+Tab window switcher (GTK4)")
    p_switch.add_argument("--catalog", default="config/components.json")
    p_switch.add_argument("--root", default=".", help="script root directory")
    p_switch.set_defaults(func=_cmd_switcher)

    p_share = sub.add_parser("share", help="export the desktop to a file / import from a file")
    p_share.add_argument("action", choices=("export", "import"))
    p_share.add_argument("file", help="archive (.tar.gz)")
    p_share.add_argument("--root", default=".", help="script root directory")
    p_share.add_argument("--title", default="", help="profile name when exporting")
    p_share.add_argument("--desc", default="", help="description when exporting")
    p_share.set_defaults(func=_cmd_share)

    p_ts = sub.add_parser(
        "theme-schedule", help="apply the day/night theme if needed")
    p_ts.add_argument("--root", default=".", help="script root directory")
    p_ts.set_defaults(func=_cmd_theme_schedule)

    p_upd = sub.add_parser(
        "self-update", help="refresh the installed app from the source repo")
    p_upd.add_argument("--root", default=".", help="script root directory")
    p_upd.add_argument("--source", default="", help="source repo (default: .source)")
    p_upd.add_argument("--check", action="store_true",
                       help="check only; exit code 1 if it differs")
    p_upd.add_argument("--pull", action="store_true",
                       help="git pull --ff-only in the repo first")
    p_upd.set_defaults(func=_cmd_self_update)

    p_reapply = sub.add_parser(
        "reapply", help="re-apply settings.conf once")
    p_reapply.add_argument("--root", default=".", help="script root directory")
    p_reapply.add_argument("--no-start", action="store_true",
                           help="do not start stopped processes (bar, notifications…)")
    p_reapply.set_defaults(func=_cmd_reapply)

    p_gui = sub.add_parser("gui", help="graphical setup interface (GTK4)")
    p_gui.add_argument("--catalog", default="config/components.json")
    p_gui.add_argument("--templates", default="templates")
    p_gui.add_argument("--root", default=".", help="script root directory")
    # MOD+I uses this (templates/hypr/scripts/settings.sh.tmpl): the SAME app,
    # only in panel mode — separate window class, screen-proportional size and
    # closing with Esc (gui/quick.py → gui/app.py).
    p_gui.add_argument("--quick", action="store_true",
                       help="panel mode: floating window sliding down from the top")
    p_gui.set_defaults(func=_cmd_gui)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
