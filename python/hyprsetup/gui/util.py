"""Small helpers shared by the GUI pages: file chooser and CSS installation."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

PICTURES = Path.home() / "Pictures"
_installed_css: set[str] = set()


def ensure_css(css: str) -> None:
    """Add a stylesheet to the default display once (retries later if there is no display)."""
    display = Gdk.Display.get_default()
    if css in _installed_css or display is None:
        return
    provider = Gtk.CssProvider()
    provider.load_from_string(css)
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    _installed_css.add(css)


def pick_file(parent: Gtk.Window | None, title: str, on_path: Callable[[Path], None], *,
              filter_name: str = "", mimes: Iterable[str] = (),
              patterns: Iterable[str] = (), suffixes: Iterable[str] = (),
              folder: Path | None = None, save_as: str = "") -> None:
    """Let the user choose a file and pass the chosen path to ``on_path``.

    If ``mimes``/``patterns``/``suffixes`` are given, a single filter is set up.
    If ``save_as`` is set, a "save" dialog opens and suggests that name.
    """
    dialog = Gtk.FileDialog(title=title)
    mimes, patterns, suffixes = list(mimes), list(patterns), list(suffixes)
    if mimes or patterns or suffixes:
        flt = Gtk.FileFilter(name=filter_name)
        for mime in mimes:
            flt.add_mime_type(mime)
        for pattern in patterns:
            flt.add_pattern(pattern)
        for suffix in suffixes:
            flt.add_suffix(suffix.lstrip("."))
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(flt)
        dialog.set_filters(filters)
        dialog.set_default_filter(flt)
    if folder is not None and folder.is_dir():
        dialog.set_initial_folder(Gio.File.new_for_path(str(folder)))
    if save_as:
        dialog.set_initial_name(save_as)
    finish = dialog.save_finish if save_as else dialog.open_finish

    def done(_dialog, result) -> None:
        try:
            file = finish(result)
        except GLib.Error:
            return                                   # cancelled
        if file is not None and file.get_path():
            on_path(Path(file.get_path()))

    (dialog.save if save_as else dialog.open)(parent, None, done)
