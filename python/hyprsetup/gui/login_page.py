"""The settings app's "Login Screen" page (backend: ``hyprsetup.login``).

Sections:

* **Login manager**: which one is active; switching SDDM ↔ Plasma Login.
* **SDDM themes**: community catalog (install / select) and an editor for the
  selected theme: preset look, paint from my palette, my wallpaper, and one
  row per setting by type (color, on/off, number, image, text). The Preview
  button opens the theme in SDDM's test mode (no root needed, the system is
  not changed).
* **Plasma Login**: clock, wallpaper and colors.
* **Boot animation**: Plymouth theme; the same code as the installer's
  ``install.sh --plymouth`` (initramfs hook, kernel command line, initramfs).

Changes are written to ``~/.config/hyprsetup/login.json`` right away but only
reach the system via "Apply": the script runs in a visible terminal and the
sudo password is asked there (the app itself never asks for sudo).
"""

from __future__ import annotations

import os
import shlex
import subprocess
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango  # noqa: E402

from .. import login  # noqa: E402
from .. import render as render_mod  # noqa: E402
from . import aur as aur_mod  # noqa: E402
from .util import ensure_css, pick_file  # noqa: E402
from .preview import ShotPreview  # noqa: E402


def _esc(text: str) -> str:
    return GLib.markup_escape_text(str(text))


def _stars(count: int) -> str:
    if not count:
        return ""
    return f"★ {count / 1000:.1f}k" if count >= 1000 else f"★ {count}"


def _rgba(value: str) -> Gdk.RGBA:
    """Qt color string → Gdk.RGBA (in Qt's #AARRGGBB the alpha comes first)."""
    rgba = Gdk.RGBA()
    text = value.strip()
    if len(text) == 9 and text.startswith("#"):
        alpha = int(text[1:3], 16) / 255
        rgba.parse("#" + text[3:])
        rgba.alpha = alpha
        return rgba
    if not rgba.parse(text):
        rgba.parse("#000000")
    return rgba


def _qt_color(rgba: Gdk.RGBA) -> str:
    rgb = "".join(f"{round(c * 255):02x}" for c in (rgba.red, rgba.green, rgba.blue))
    if rgba.alpha < 0.999:
        return f"#{round(rgba.alpha * 255):02x}{rgb}"
    return f"#{rgb}"


#: Boot animation gallery sizes (pixels).
BIG = 320             # the big preview on top
CARD = 120            # card image
CATALOG_HEIGHT = 230  # the tabs' scrolling box


#: Notice box on the My theme tab: background and border in the warning color.
_NOTES_CSS = """
.hs-plymouth-notes {
  background-color: alpha(@warning_color, 0.10);
  border: 1px solid alpha(@warning_color, 0.55);
}
"""


class LoginPage(Adw.PreferencesPage):
    def __init__(self, win) -> None:
        super().__init__()
        self.win = win
        if hasattr(win, "_widen_page"):
            win._widen_page(self, 940)
        self.root = Path(win.root)
        self.data = login.load_state()
        self.data.setdefault("sddm", {})
        self.data.setdefault("plasmalogin", {})
        self._editor_groups: list[Adw.PreferencesGroup] = []
        self._theme_rows: list[Adw.PreferencesGroup] = []

        self._manager_group = Adw.PreferencesGroup(title="Login manager")
        self.add(self._manager_group)
        self._catalog_group = Adw.PreferencesGroup(
            title="SDDM themes",
            description="The community's most used themes. Ones not installed are "
                        "installed in a terminal; AUR ones carry a badge. Every installed theme, "
                        "even if not listed, can be selected and edited below.")
        refresh = Gtk.Button(icon_name="view-refresh-symbolic", valign=Gtk.Align.CENTER,
                             tooltip_text="Rescan installed themes")
        refresh.add_css_class("flat")
        refresh.connect("clicked", lambda _b: self.refresh())
        self._catalog_group.set_header_suffix(refresh)
        self.add(self._catalog_group)
        self._plasma_group: Adw.PreferencesGroup | None = None
        self._plymouth_group: Adw.PreferencesGroup | None = None
        #: Install/Apply running in a terminal (see _start_plymouth_job); None = none.
        self._plymouth_job: dict | None = None
        self.refresh()

    # --------------------------------------------------------------- helpers
    def _save(self) -> None:
        login.save_state(self.data)

    def _run_script(self, script: str, done_message: str,
                    status: Path | None = None) -> bool:
        """Run the script in a visible terminal.

        If ``status`` is given, the script writes its exit code to that file
        when it ends (before waiting for Enter). Waiting on the terminal process
        is unreliable: single-window terminals (kitty --single-instance etc.)
        return immediately. The page learns about completion from this file
        (see _watch_plymouth_job).
        """
        from .. import snapshot
        # Snapshot before writing system files (if snapper/timeshift exists),
        # so a broken login screen can be rolled back.
        prefix = snapshot.shell_line("login screen change",
                                     self.win.state.get("SNAPSHOT_BEFORE_SYSTEM") or "auto")
        body = script
        if status is not None:
            status.unlink(missing_ok=True)
            # set -e in a subshell: stops at the first error and its code lands in the file.
            body = (f"(\nset -e\n{script}\n)\n"
                    f"echo $? > {shlex.quote(str(status))}")
        if not self.win._open_terminal((f"{prefix}\n" if prefix else "") + body):
            return False
        self.win._toast(done_message)
        return True

    def _variables(self) -> dict[str, str]:
        """Template variables (my palette, my wallpaper); same path as cheatsheet."""
        selected = list(self.win.state.selected)
        values, _skipped = self.win.applier.export_vars(dict(self.win.state.values), selected)
        return render_mod.derived_vars(values, self.win.catalog, selected, self.win.keybinds)

    def _wallpaper(self) -> Path | None:
        path = self.win.applier.wallpaper_file(self.win.state.values)
        return path if path.is_file() else None

    def refresh(self) -> None:
        self.themes = login.installed_themes(self.root)
        self.catalog = login.load_catalog(self.root)
        self._build_manager()
        self._build_catalog()
        self._build_editor()
        self._build_plasma()
        self._build_plymouth()

    # ----------------------------------------------------------- login manager
    def _build_manager(self) -> None:
        group = self._manager_group
        for child in list(getattr(self, "_manager_rows", [])):
            group.remove(child)
        self._manager_rows = []
        current = login.current_manager()
        name = login.MANAGERS.get(current, current or "not found")
        row = Adw.ActionRow(title=f"Active: {_esc(name)}")
        if current == "sddm":
            row.set_subtitle("The SDDM theme below is shown on the login screen.")
        elif current == "plasmalogin":
            row.set_subtitle("Plasma Login draws its own screen; SDDM themes only show "
                             "after switching to SDDM (Preview works either way). "
                             "Plasma Login settings are at the end of the page.")
        else:
            row.set_subtitle("SDDM themes show while SDDM is active.")
        row.add_prefix(Gtk.Image.new_from_icon_name("system-users-symbolic"))
        if current != "sddm":
            if login.manager_installed("sddm"):
                button = Gtk.Button(label="Switch to SDDM", valign=Gtk.Align.CENTER)
                button.connect("clicked", lambda _b: self._confirm_switch("sddm"))
            else:
                button = Gtk.Button(label="Install SDDM", valign=Gtk.Align.CENTER)
                button.connect("clicked", lambda _b: self._install(["sddm"], []))
            row.add_suffix(button)
        elif login.manager_installed("plasmalogin"):
            button = Gtk.Button(label="Back to Plasma Login", valign=Gtk.Align.CENTER)
            button.connect("clicked", lambda _b: self._confirm_switch("plasmalogin"))
            row.add_suffix(button)
        group.add(row)
        self._manager_rows.append(row)

    def _confirm_switch(self, target: str) -> None:
        name = login.MANAGERS.get(target, target)
        dialog = Adw.AlertDialog(
            heading=f"Switch to {name}?",
            body=(f"The current login manager is disabled and {name} is "
                  "enabled; it shows up on the next boot. The commands run "
                  "in a terminal (the sudo password is asked there).\n\n"
                  "You can use the button on this page to switch back."))
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("switch", f"Switch to {name}")
        dialog.set_response_appearance("switch", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_close_response("cancel")

        def chosen(_d, response: str) -> None:
            if response == "switch":
                self._run_script("set -e\n" + login.switch_script(target),
                                 f"Switch to {name} started in a terminal")
        dialog.connect("response", chosen)
        dialog.present(self.win)

    def _install(self, repo: list[str], aur: list[str]) -> None:
        commands = self.win._package_commands(repo, aur)
        self._run_script(" && ".join(commands),
                         "Installation started in a terminal; refresh with ↻ when it is done")

    # ---------------------------------------------------------------- catalog
    def _installed_for(self, entry: login.CatalogTheme) -> list[login.Theme]:
        return [t for t in self.themes if t.catalog is entry or
                (t.catalog and t.catalog.id == entry.id)]

    def _selected_dir(self) -> str:
        chosen = self.data["sddm"].get("selected", "")
        if any(t.id == chosen for t in self.themes):
            return chosen
        active = login.active_sddm_theme()
        if any(t.id == active for t in self.themes):
            return active
        return self.themes[0].id if self.themes else ""

    def _build_catalog(self) -> None:
        group = self._catalog_group
        for child in self._theme_rows:
            group.remove(child)
        self._theme_rows = []
        selected = self._selected_dir()
        radio_group: Gtk.CheckButton | None = None

        def add_row(title: str, subtitle: str, picture: Path | None,
                    installed: list[login.Theme], entry: login.CatalogTheme | None) -> None:
            nonlocal radio_group
            row = Adw.ActionRow(title=_esc(title), subtitle=_esc(subtitle))
            row.set_subtitle_lines(3)
            if picture:
                row.add_prefix(ShotPreview(picture, width=144, height=81))
            if installed:
                check = Gtk.CheckButton(valign=Gtk.Align.CENTER)
                if radio_group is None:
                    radio_group = check
                else:
                    check.set_group(radio_group)
                check.set_active(any(t.id == selected for t in installed))
                check.connect("toggled", self._on_theme_toggled, installed[0].id)
                row.add_suffix(check)
                row.set_activatable_widget(check)
            elif entry:
                if entry.aur:
                    row.add_suffix(aur_mod.badge(entry.aur))
                button = Gtk.Button(label="Install", valign=Gtk.Align.CENTER)
                button.add_css_class("suggested-action")
                button.connect("clicked", lambda _b: self._install(entry.packages, entry.aur))
                row.add_suffix(button)
            if entry and entry.repo:
                link = Gtk.Button(icon_name="adw-external-link-symbolic",
                                  valign=Gtk.Align.CENTER, tooltip_text=entry.repo)
                link.add_css_class("flat")
                link.connect("clicked", lambda _b: Gio.AppInfo.launch_default_for_uri(
                    entry.repo, None))
                row.add_suffix(link)
            group.add(row)
            self._theme_rows.append(row)

        for entry in sorted(self.catalog, key=lambda c: -c.stars):
            installed = self._installed_for(entry)
            meta = " · ".join(x for x in (_stars(entry.stars), entry.license,
                                          "installed" if installed else "not installed") if x)
            add_row(entry.title, f"{entry.desc}\n{meta}",
                    login.preview_image(self.root, entry.id), installed, entry)
        for theme in self.themes:
            if theme.catalog is None:
                add_row(theme.name, f"Installed theme · {theme.dir}", theme.screenshot,
                        [theme], None)

    def _on_theme_toggled(self, check: Gtk.CheckButton, directory: str) -> None:
        if not check.get_active():
            return
        self.data["sddm"]["selected"] = directory
        self._save()
        self._build_editor()

    # ------------------------------------------------------------------ editor
    def _looks(self, theme: login.Theme) -> list[tuple[str, str, str]]:
        """Selectable looks: (theme directory, preset look, label).

        If a catalog theme installs several folders (Catppuccin: one per
        flavor), the looks of all of them are in one list.
        """
        sisters = ([t for t in self.themes if t.catalog and theme.catalog
                    and t.catalog.id == theme.catalog.id] or [theme])
        out = []
        for t in sisters:
            for label, preset in t.presets():
                prefix = f"{t.id} › " if len(sisters) > 1 else ""
                out.append((t.id, preset, prefix + label))
        return out

    def _current(self) -> tuple[login.Theme | None, str]:
        directory = self._selected_dir()
        theme = next((t for t in self.themes if t.id == directory), None)
        if theme is None:
            return None, ""
        preset = self.data["sddm"].setdefault("preset", {}).get(
            directory, theme.config_file)
        return theme, preset

    def _edits(self, theme: login.Theme, preset: str) -> dict[str, str]:
        return (self.data["sddm"].setdefault("edits", {})
                .setdefault(theme.id, {}).setdefault(preset, {}))

    def _build_editor(self) -> None:
        for group in self._editor_groups:
            self.remove(group)
        self._editor_groups = []
        theme, preset = self._current()
        if theme is None:
            group = Adw.PreferencesGroup(title="Theme editor")
            group.add(Adw.ActionRow(title="No SDDM theme installed",
                                    subtitle="Install a theme above."))
            self._insert_editor(group)
            return
        edits = self._edits(theme, preset)

        # Adw puts non-row widgets BELOW the group's list; the preview gets its
        # own group so it stays above the buttons.
        top = Adw.PreferencesGroup(
            title=f"Edit: {_esc(theme.name)}",
            description=f"Changes are written to {theme.dir}/{theme.user_file}; "
                        "the theme's own files are not touched.")
        picture = (theme.preset_preview(preset) or theme.screenshot
                   or (login.preview_image(self.root, theme.catalog.id)
                       if theme.catalog else None))
        if picture:
            box = Gtk.Box(halign=Gtk.Align.CENTER)
            box.append(ShotPreview(picture, width=480, height=270))
            top.add(box)
        self._insert_editor(top)
        head = Adw.PreferencesGroup()

        looks = self._looks(theme)
        if len(looks) > 1:
            index = next((i for i, (d, p, _l) in enumerate(looks)
                          if d == theme.id and p == preset), 0)
            gallery = self._look_gallery(looks, index)
            if gallery is not None:
                self._insert_editor(gallery)
            else:
                combo = Adw.ComboRow(title="Preset look",
                                     model=Gtk.StringList.new([label for _d, _p, label in looks]))
                combo.set_selected(index)
                combo.connect("notify::selected", self._on_look, looks)
                head.add(combo)

        actions = Adw.ActionRow(title="Quick actions")
        for label, handler, tip in (
                ("Paint from my palette", self._on_paint,
                 "Fills the color fields with your desktop palette"),
                ("My wallpaper", self._on_wallpaper,
                 "Uses your desktop wallpaper as the background"),
                ("Reset", self._on_reset, "Removes all changes made to this look")):
            button = Gtk.Button(label=label, valign=Gtk.Align.CENTER, tooltip_text=tip)
            if label == "Reset":
                button.add_css_class("destructive-action")
            button.connect("clicked", lambda _b, h=handler: h())
            actions.add_suffix(button)
        head.add(actions)

        apply_row = Adw.ActionRow(
            title="Preview and apply",
            subtitle="Preview: the theme opens in a window in SDDM's test mode (the "
                     "system is not changed). Apply: the files are put in place with "
                     "sudo in a terminal.")
        preview = Gtk.Button(label="Preview", valign=Gtk.Align.CENTER)
        preview.connect("clicked", lambda _b: self._on_preview())
        apply = Gtk.Button(label="Apply", valign=Gtk.Align.CENTER)
        apply.add_css_class("suggested-action")
        apply.connect("clicked", lambda _b: self._on_apply())
        apply_row.add_suffix(preview)
        apply_row.add_suffix(apply)
        head.add(apply_row)
        self._insert_editor(head)

        groups: dict[str, list[login.Field]] = {}
        for item in login.fields(theme, preset, edits):
            groups.setdefault(item.group, []).append(item)
        fields_group = Adw.PreferencesGroup(title="Settings")
        for name, items in groups.items():
            expander = Adw.ExpanderRow(title=_esc(name), subtitle=f"{len(items)} settings")
            for item in items:
                expander.add_row(self._field_row(theme, preset, item))
            fields_group.add(expander)
        self._insert_editor(fields_group)

    def _insert_editor(self, group: Adw.PreferencesGroup) -> None:
        # Keep the Plasma Login group at the end of the page.
        if self._plasma_group is not None:
            self.remove(self._plasma_group)
        self.add(group)
        self._editor_groups.append(group)
        if self._plasma_group is not None:
            self.add(self._plasma_group)

    def _set(self, theme: login.Theme, preset: str, key: str, value: str) -> None:
        self._edits(theme, preset)[key] = value
        self._save()

    def _field_row(self, theme: login.Theme, preset: str, item: login.Field) -> Gtk.Widget:
        title = _esc(item.title)
        subtitle = _esc(item.key)
        if item.type == "color":
            row = Adw.ActionRow(title=title, subtitle=subtitle)
            button = Gtk.ColorDialogButton(valign=Gtk.Align.CENTER)
            button.set_dialog(Gtk.ColorDialog(with_alpha=True))
            button.set_rgba(_rgba(item.value))
            button.connect("notify::rgba", lambda b, _p: self._set(
                theme, preset, item.key, _qt_color(b.get_rgba())))
            row.add_suffix(button)
            return row
        if item.type == "bool":
            row = Adw.SwitchRow(title=title, subtitle=subtitle)
            row.set_active(item.value.lower() == "true")
            row.connect("notify::active", lambda r, _p: self._set(
                theme, preset, item.key, "true" if r.get_active() else "false"))
            return row
        if item.type in ("int", "float"):
            from .app import no_scroll_change        # app imports this module

            is_int = item.type == "int"
            row = Adw.SpinRow.new_with_range(-100000, 100000, 1 if is_int else 0.05)
            no_scroll_change(row)
            row.set_title(title)
            row.set_subtitle(subtitle)
            row.set_digits(0 if is_int else 2)
            try:
                row.set_value(float(item.value))
            except ValueError:
                pass
            row.connect("notify::value", lambda r, _p: self._set(
                theme, preset, item.key,
                str(int(r.get_value())) if is_int else f"{r.get_value():.2f}"))
            return row
        if item.type == "image":
            row = Adw.ActionRow(title=title, subtitle=_esc(item.value or "(empty)"))
            pick = Gtk.Button(label="Choose…", valign=Gtk.Align.CENTER)
            pick.connect("clicked", lambda _b: self._pick_image(theme, preset, item.key, row))
            mine = Gtk.Button(icon_name="preferences-desktop-wallpaper-symbolic",
                              valign=Gtk.Align.CENTER,
                              tooltip_text="My desktop wallpaper")
            mine.connect("clicked", lambda _b: self._image_chosen(
                theme, preset, item.key, row, self._wallpaper()))
            row.add_suffix(mine)
            row.add_suffix(pick)
            return row
        row = Adw.EntryRow(title=f"{title} · {subtitle}")
        row.set_text(item.value)
        row.connect("changed", lambda r: self._set(theme, preset, item.key, r.get_text()))
        return row

    def _pick_image(self, theme, preset, key, row) -> None:
        pick_file(self.win, "Background image",
                  lambda path: self._image_chosen(theme, preset, key, row, path),
                  filter_name="Images and videos", mimes=["image/*", "video/*"])

    def _image_chosen(self, theme, preset, key, row, path: Path | None) -> None:
        if path is None:
            self.win._toast("Desktop wallpaper not found")
            return
        self._set(theme, preset, key, str(path))
        row.set_subtitle(_esc(str(path)))

    def _look_gallery(self, looks, selected: int) -> Adw.PreferencesGroup | None:
        """Preset looks as thumbnail cards (for themes that have images).

        The dropdown only had file names like "black_hole", "pixel_sakura"; you
        could only recognize the looks by selecting them one by one.
        """
        by_id = {t.id: t for t in self.themes}
        thumbs = [by_id[d].preset_preview(p) if d in by_id else None
                  for d, p, _l in looks]
        if sum(1 for t in thumbs if t) < 2:
            return None
        group = Adw.PreferencesGroup(title="Preset look",
                                     description=f"{len(looks)} looks, click one")
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                           min_children_per_line=2, max_children_per_line=5,
                           row_spacing=8, column_spacing=8)
        for index, ((_d, _p, label), thumb) in enumerate(zip(looks, thumbs, strict=False)):
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            inner.set_margin_top(6)
            inner.set_margin_bottom(6)
            inner.set_margin_start(6)
            inner.set_margin_end(6)
            if thumb:
                inner.append(ShotPreview(thumb, width=160, height=90))
            else:
                blank = Gtk.Box()
                blank.set_size_request(160, 90)
                inner.append(blank)
            name = Gtk.Label(label=label.replace("_", " "), xalign=0,
                             ellipsize=Pango.EllipsizeMode.END, max_width_chars=18)
            name.add_css_class("caption")
            inner.append(name)
            button = Gtk.ToggleButton(child=inner, active=index == selected)
            button.add_css_class("card")
            button.add_css_class("flat")
            button.connect("clicked", lambda _b, i=index: self._pick_look(looks, i))
            flow.append(button)
        group.add(flow)
        return group

    def _on_look(self, combo: Adw.ComboRow, _param, looks) -> None:
        self._pick_look(looks, combo.get_selected())

    def _pick_look(self, looks, index: int) -> None:
        if not 0 <= index < len(looks):
            return
        directory, preset, _label = looks[index]
        self.data["sddm"]["selected"] = directory
        self.data["sddm"].setdefault("preset", {})[directory] = preset
        self._save()
        # If the catalog theme moved to another folder (Catppuccin flavors),
        # move the selection in the list too.
        GLib.idle_add(lambda: (self._build_editor(), False)[1])

    def _on_paint(self) -> None:
        theme, preset = self._current()
        if theme is None:
            return
        edits = login.palette_edits(theme, self._variables())
        if not edits:
            self.win._toast("No color fields found in this theme")
            return
        self._edits(theme, preset).update(edits)
        self._save()
        self._build_editor()
        self.win._toast(f"{len(edits)} colors filled from your palette")

    def _on_wallpaper(self) -> None:
        theme, preset = self._current()
        image = self._wallpaper()
        if theme is None or image is None:
            self.win._toast("Desktop wallpaper not found")
            return
        edits = login.background_edits(theme, image)
        if not edits:
            self.win._toast("This theme has no background setting")
            return
        self._edits(theme, preset).update(edits)
        self._save()
        self._build_editor()
        self.win._toast("Background: your desktop wallpaper")

    def _on_reset(self) -> None:
        theme, preset = self._current()
        if theme is None:
            return
        self._edits(theme, preset).clear()
        self._save()
        self._build_editor()

    def _on_preview(self) -> None:
        theme, preset = self._current()
        if theme is None:
            return
        proc = login.preview(theme, preset, self._edits(theme, preset))
        if proc is None:
            self.win._toast("sddm-greeter not found (is sddm installed?)")
        else:
            self.win._toast("Opening preview; close its window to end it")

    def _on_apply(self) -> None:
        theme, preset = self._current()
        if theme is None:
            return
        edits = self._edits(theme, preset)
        # From now on install.sh --reapply leaves the SDDM theme alone (login.sh).
        self.data["sddm"]["applied"] = theme.id
        self._save()
        if login.current_manager() == "sddm":
            self._run_script(login.sddm_script(theme, preset, edits),
                             "Applying the SDDM theme in a terminal")
            return
        dialog = Adw.AlertDialog(
            heading="SDDM is not active",
            body=("The theme files can be put in place, but they only show on the "
                  "login screen while SDDM is active. Switch to SDDM now too? (It "
                  "takes effect on the next boot.)"))
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("files", "Only write the theme")
        dialog.add_response("switch", "Write the theme and switch to SDDM")
        dialog.set_response_appearance("switch", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_close_response("cancel")

        def chosen(_d, response: str) -> None:
            if response in ("files", "switch"):
                self._run_script(login.sddm_script(theme, preset, edits,
                                                   switch=response == "switch"),
                                 "Applying the SDDM theme in a terminal")
        dialog.connect("response", chosen)
        dialog.present(self.win)

    # ------------------------------------------------------------ Plasma Login
    def _build_plasma(self) -> None:
        if self._plasma_group is not None:
            self.remove(self._plasma_group)
            self._plasma_group = None
        if not login.manager_installed("plasmalogin"):
            return
        state = login.plasmalogin_state()
        saved = self.data["plasmalogin"]
        group = Adw.PreferencesGroup(
            title="Plasma Login",
            description="KDE's login screen. Instead of a theme you set the wallpaper, "
                        "color scheme and clock. Apply: the files are written with sudo in a "
                        "terminal to /etc/plasmalogin.conf and under /var/lib/plasmalogin.")

        clock = Adw.SwitchRow(title="Show clock")
        clock.set_active(saved.get("show_clock", state.show_clock))
        clock.connect("notify::active", lambda r, _p: self._plasma_set("show_clock", r.get_active()))
        group.add(clock)

        modes = [("keep", "Don't change"), ("wallpaper", "My desktop wallpaper"),
                 ("file", "Choose file…"), ("color", "Solid color (my palette's background)")]
        wallpaper = Adw.ComboRow(title="Background",
                                 model=Gtk.StringList.new([m[1] for m in modes]))
        current = saved.get("wallpaper", "keep")
        wallpaper.set_selected(next((i for i, m in enumerate(modes) if m[0] == current), 0))
        if saved.get("image"):
            wallpaper.set_subtitle(_esc(saved["image"]))
        wallpaper.connect("notify::selected", self._on_plasma_wallpaper, modes)
        group.add(wallpaper)

        schemes = login.color_schemes()
        options = [("keep", "Don't change"), ("palette", "My palette (same as the desktop)")]
        options += [(name, name) for name, _p in schemes]
        colors = Adw.ComboRow(title="Color scheme",
                              model=Gtk.StringList.new([o[1] for o in options]))
        colors.set_enable_search(True)
        chosen = saved.get("colors", "keep")
        colors.set_selected(next((i for i, o in enumerate(options) if o[0] == chosen), 0))
        colors.connect("notify::selected", lambda r, _p: self._plasma_set(
            "colors", options[r.get_selected()][0]))
        group.add(colors)

        row = Adw.ActionRow(title="Apply")
        kcm = Gtk.Button(label="Open in KDE settings", valign=Gtk.Align.CENTER)
        kcm.connect("clicked", lambda _b: subprocess.Popen(
            ["kcmshell6", "kcm_plasmalogin"], start_new_session=True))
        apply = Gtk.Button(label="Apply", valign=Gtk.Align.CENTER)
        apply.add_css_class("suggested-action")
        apply.connect("clicked", lambda _b: self._on_plasma_apply())
        row.add_suffix(kcm)
        row.add_suffix(apply)
        group.add(row)
        self._plasma_group = group
        self.add(group)

    def _plasma_set(self, key: str, value) -> None:
        self.data["plasmalogin"][key] = value
        self._save()

    def _on_plasma_wallpaper(self, combo: Adw.ComboRow, _param, modes) -> None:
        mode = modes[combo.get_selected()][0]
        if mode == "file":
            def chosen(path: Path) -> None:
                self._plasma_set("image", str(path))
                self._plasma_set("wallpaper", "file")
                combo.set_subtitle(_esc(str(path)))
            pick_file(self.win, "Login screen background", chosen)
            return
        self._plasma_set("wallpaper", mode)

    def _on_plasma_apply(self) -> None:
        saved = self.data["plasmalogin"]
        state = login.PlasmaLogin(show_clock=bool(saved.get("show_clock", True)))
        mode = saved.get("wallpaper", "keep")
        variables: dict[str, str] | None = None
        if mode == "wallpaper":
            image = self._wallpaper()
            if image is None:
                self.win._toast("Desktop wallpaper not found")
                return
            state.wallpaper, state.image = "image", str(image)
        elif mode == "file" and saved.get("image"):
            state.wallpaper, state.image = "image", saved["image"]
        elif mode == "color":
            variables = self._variables()
            state.wallpaper, state.color = "color", "#" + variables.get("COL_BG", "000000").lstrip("#")
        kdeglobals = ""
        scheme = saved.get("colors", "keep")
        if scheme == "palette":
            kdeglobals = login.palette_kdeglobals(self.root, variables or self._variables())
        elif scheme != "keep":
            path = dict(login.color_schemes()).get(scheme)
            if path:
                kdeglobals = login.scheme_kdeglobals(path)
        self._run_script(login.plasmalogin_script(state, kdeglobals),
                         "Applying Plasma Login settings in a terminal")

    # --------------------------------------------------------- boot animation
    def _install_root(self) -> Path | None:
        """The repo containing install.sh: the root when running from source, or
        the repo the install came from when running an installed copy
        (selfupdate .source)."""
        if (self.root / "install.sh").is_file():
            return self.root
        from .. import selfupdate
        return selfupdate.source_root()

    def _build_plymouth(self) -> None:
        if self._plymouth_group is not None:
            self.remove(self._plymouth_group)
            self._plymouth_group = None
        group = Adw.PreferencesGroup(
            title="Boot animation (Plymouth)",
            description="The animation shown instead of kernel messages while the "
                        "computer boots. Apply runs the installer's step in a terminal: "
                        "the initramfs hook and 'quiet splash' (if missing) are added and "
                        "the initramfs is regenerated once. Takes a few minutes; visible "
                        "after a reboot.")
        if self._plymouth_job is not None:
            group.add(self._job_banner())
        install_root = self._install_root()
        if install_root is None:
            row = Adw.ActionRow(title="install.sh not found",
                                subtitle="The repo the install came from was moved or deleted. "
                                         "Run ./install.sh --plymouth <theme> from the repo.")
            row.add_prefix(Gtk.Image.new_from_icon_name("dialog-warning-symbolic"))
            group.add(row)
        elif not login.plymouth_installed():
            row = Adw.ActionRow(title="Plymouth is not installed",
                                subtitle="Installs it and enables the default 'spinner' theme.")
            button = Gtk.Button(label="Install and enable", valign=Gtk.Align.CENTER)
            button.add_css_class("suggested-action")
            button.connect("clicked", lambda _b: self._apply_plymouth(install_root, "spinner"))
            row.add_suffix(button)
            group.add(row)
        else:
            themes = login.plymouth_themes()
            current = login.plymouth_current()
            catalog = login.load_plymouth_catalog(self.root)
            known = set(themes) | {e.id for e in catalog}
            if getattr(self, "_plymouth_choice", "") not in known:
                self._plymouth_choice = current if current in themes else (themes or [""])[0]
            group.add(self._plymouth_gallery(install_root, themes, current, catalog))
        self._plymouth_group = group
        self.add(group)

    def _plymouth_gallery(self, install_root: Path, themes: list[str], current: str,
                          catalog: list[login.PlymouthCatalogTheme]) -> Gtk.Widget:
        """On top, the selected theme's preview (left) and name/button (right);
        below, "Installed | Community" tabs, both in a fixed-height scrolling
        box. Clicking a card selects it.

        Installed themes not in the catalog are drawn from the theme's own
        files (plymouth_preview); catalog ones (script-based adi1090x themes
        cannot be imitated with cairo) are shown with a card image, and with a
        downloaded animated GIF once selected.
        """
        from .plymouth_preview import PlymouthPreview
        from .welcome import IntroMedia

        class Media(IntroMedia):
            # The tour's 480-pixel player took up too much room on this page.
            WIDTH, HEIGHT = BIG, round(BIG * 9 / 16)
            MAX_WIDTH, MAX_HEIGHT = BIG, round(BIG * 9 / 16)

            def _show_frame(self) -> None:
                # The GIFs are 1366 px; GTK's downscaling blurred thin lines and
                # made them flicker. The frame is scaled to its display size
                # here with a good filter.
                pixbuf = self._anim_iter.get_pixbuf()
                width = BIG * max(1, self.get_scale_factor())
                if pixbuf.get_width() > width:
                    height = max(1, round(pixbuf.get_height() * width / pixbuf.get_width()))
                    pixbuf = pixbuf.scale_simple(width, height, GdkPixbuf.InterpType.HYPER)
                self._picture.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))

        by_id = {e.id: e for e in catalog}
        installed = set(themes)
        scenes = {name: login.plymouth_scene(name) for name in themes if name not in by_id}

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                      margin_top=6, margin_bottom=12)

        # --- top: preview + info -----------------------------------------
        top = Gtk.Box(spacing=16)
        big_holder = Gtk.Box(valign=Gtk.Align.CENTER)
        big_holder.set_size_request(BIG, round(BIG * 9 / 16))
        # Spinner on top while the preview is being prepared (GIF downloading,
        # custom theme being built), so an empty/stale image is not mistaken for
        # a hang.
        overlay = Gtk.Overlay(child=big_holder, valign=Gtk.Align.CENTER)
        busy = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
                       visible=False)
        busy.add_css_class("osd")
        busy.add_css_class("toolbar")
        busy_spinner = Gtk.Spinner()
        busy.append(busy_spinner)
        busy_label = Gtk.Label(label="Preparing…")
        busy.append(busy_label)
        overlay.add_overlay(busy)
        top.append(overlay)

        def set_busy(text: str | None) -> None:
            busy.set_visible(bool(text))
            busy_spinner.set_spinning(bool(text))
            if text:
                busy_label.set_label(text)
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                       valign=Gtk.Align.CENTER, hexpand=True)
        caption = Gtk.Label(wrap=True, xalign=0)
        info.append(caption)
        hint = Gtk.Label(wrap=True, xalign=0)
        hint.add_css_class("dim-label")
        hint.add_css_class("caption")
        info.append(hint)
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.START, margin_top=4)
        badge_slot = Gtk.Box(valign=Gtk.Align.CENTER)
        button = Gtk.Button(valign=Gtk.Align.CENTER)
        button.add_css_class("suggested-action")
        buttons.append(button)
        buttons.append(badge_slot)
        info.append(buttons)
        top.append(info)
        box.append(top)
        token = {"n": 0}

        def clear(widget: Gtk.Box) -> None:
            child = widget.get_first_child()
            while child:
                nxt = child.get_next_sibling()
                widget.remove(child)
                child = nxt

        def thumb_picture(entry, width: int, crop: bool = True) -> Gtk.Widget:
            picture = Gtk.Picture(content_fit=Gtk.ContentFit.FILL, can_shrink=True)
            height = round(width * 9 / 16)
            if entry.thumb:
                # The image is scaled here to exactly its display size (with
                # the screen scale): handing the big file to Gtk.Picture meant
                # GTK's simple filter, i.e. a blurry card. The card also zooms
                # in on the logo (entry.crop); the big preview is the full frame,
                # to show how it will really look on screen.
                scale = max(1, self.get_scale_factor())
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(entry.thumb))
                    if crop:
                        x, y, w, h = entry.crop
                        pw, ph = pixbuf.get_width(), pixbuf.get_height()
                        sx, sy = int(x * pw), int(y * ph)
                        sw = max(1, min(pw - sx, round(w * pw)))
                        sh = max(1, min(ph - sy, round(h * ph)))
                        pixbuf = pixbuf.new_subpixbuf(sx, sy, sw, sh)
                    pixbuf = pixbuf.scale_simple(width * scale, height * scale,
                                                 GdkPixbuf.InterpType.HYPER)
                    picture.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
                except GLib.Error:
                    picture.set_filename(str(entry.thumb))
            picture.set_size_request(width, height)
            frame = Gtk.Frame(child=picture)
            frame.add_css_class("card")
            frame.set_overflow(Gtk.Overflow.HIDDEN)
            return frame

        def show(name: str) -> None:
            token["n"] += 1
            mine = token["n"]
            clear(big_holder)
            clear(badge_slot)
            set_busy(None)
            entry = by_id.get(name)
            if entry is None:
                big_holder.append(PlymouthPreview(scenes[name], width=BIG))
                title, desc = name, scenes[name].description
            else:
                title = entry.title
                desc = f"{entry.desc} · ★ {entry.stars} · {entry.license}"
                cached = login.cached_plymouth_preview(entry)
                if cached:
                    big_holder.append(Media(cached, entry.title))
                else:
                    big_holder.append(thumb_picture(entry, BIG, crop=False))
                    if entry.preview.endswith(".gif"):
                        set_busy("Downloading preview…")

                        def load() -> None:
                            path = login.fetch_plymouth_preview(entry)
                            GLib.idle_add(loaded, path)

                        def loaded(path) -> bool:
                            # Another theme was picked meanwhile: do not show the old download.
                            if token["n"] != mine:
                                return False
                            set_busy(None)
                            if path:
                                clear(big_holder)
                                big_holder.append(Media(path, entry.title))
                            return False
                        threading.Thread(target=load, daemon=True).start()
            state = " · <i>active now</i>" if name == current else ""
            caption.set_markup(f"<b>{_esc(title)}</b>{state}\n"
                               f"<span size='small'>{_esc(desc)}</span>")
            button.set_sensitive(self._plymouth_job is None)
            if name in installed:
                button.set_label("Apply")
                hint.set_label("Enables it: the initramfs is regenerated once (a few "
                               "minutes), visible after a reboot. The sudo password is "
                               "asked in the terminal.")
            else:
                button.set_label("Install")
                hint.set_label(f"{entry.aur} is installed in a terminal. When it is done, "
                               "refresh with ↻ and press Apply.")
                badge_slot.append(aur_mod.badge([entry.aur]))

        def on_button(_b) -> None:
            if stack.get_visible_child_name() == "custom":
                self._apply_custom_plymouth(install_root)
                return
            name = self._plymouth_choice
            if not name:
                return
            if name in installed:
                self._apply_plymouth(install_root, name)
            else:
                self._start_plymouth_job(
                    "install", name, " && ".join(self.win._package_commands([], [by_id[name].aur])),
                    f"Installing {by_id[name].title} in a terminal")
        button.connect("clicked", on_button)

        # --- bottom: tabs ------------------------------------------------
        flows: list[Gtk.FlowBox] = []

        def selected(flow: Gtk.FlowBox) -> None:
            children = flow.get_selected_children()
            if not children:
                return
            for other in flows:
                if other is not flow:
                    other.unselect_all()
            self._plymouth_choice = children[0].theme
            show(children[0].theme)

        def new_flow() -> Gtk.FlowBox:
            flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.SINGLE, homogeneous=True,
                               max_children_per_line=8, min_children_per_line=3,
                               column_spacing=6, row_spacing=6, margin_top=6,
                               margin_bottom=6, margin_start=6, margin_end=6,
                               valign=Gtk.Align.START)
            flow.connect("selected-children-changed", selected)
            flows.append(flow)
            return flow

        def scrolled(child: Gtk.Widget) -> Gtk.ScrolledWindow:
            # Fixed height: 84 cards stacked made the page several screens long.
            scroller = Gtk.ScrolledWindow(child=child, min_content_height=CATALOG_HEIGHT,
                                          max_content_height=CATALOG_HEIGHT,
                                          hscrollbar_policy=Gtk.PolicyType.NEVER)
            scroller.add_css_class("card")
            return scroller

        def card(name: str, widget: Gtk.Widget, label: str, tip: str) -> Gtk.FlowBoxChild:
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            inner.append(widget)
            text = Gtk.Label(label=label, ellipsize=Pango.EllipsizeMode.END,
                             max_width_chars=14)
            text.add_css_class("caption")
            inner.append(text)
            child = Gtk.FlowBoxChild(child=inner, tooltip_text=tip)
            child.theme = name
            return child

        stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        installed_flow = new_flow()
        for name in themes:
            mark = " ✓" if name == current else ""
            if name in by_id:
                widget = thumb_picture(by_id[name], CARD)
                tip, label = by_id[name].desc, by_id[name].title + mark
            else:
                widget = PlymouthPreview(scenes[name], width=CARD, animate=False)
                hover = Gtk.EventControllerMotion()
                hover.connect("enter", lambda *_a, p=widget: p.set_animating(True))
                hover.connect("leave", lambda *_a, p=widget: p.set_animating(False))
                widget.add_controller(hover)
                tip, label = scenes[name].description, name + mark
            installed_flow.append(card(name, widget, label, tip))
        stack.add_titled(scrolled(installed_flow), "installed", f"Installed ({len(themes)})")

        others = [e for e in catalog if e.id not in installed]
        search = Gtk.SearchEntry(placeholder_text="Search…", width_chars=16,
                                 halign=Gtk.Align.END, hexpand=True)
        if others:
            community = new_flow()
            for entry in others:
                community.append(card(entry.id, thumb_picture(entry, CARD), entry.title,
                                      entry.desc))
            query = {"text": ""}
            community.set_filter_func(
                lambda child: query["text"] in child.theme.replace("_", " ").lower()
                or query["text"] in by_id[child.theme].title.lower())

            def on_search(entry_widget) -> None:
                query["text"] = entry_widget.get_text().strip().lower()
                community.invalidate_filter()
            search.connect("search-changed", on_search)
            stack.add_titled(scrolled(community), "community",
                             f"Community ({len(others)})")

        custom = self._plymouth_custom_page(big_holder, caption, hint, button, badge_slot,
                                            clear, token, stack, set_busy)
        stack.add_titled(scrolled(custom), "custom", "My theme")

        bar = Gtk.Box(spacing=12)
        bar.append(Gtk.StackSwitcher(stack=stack))
        bar.append(search)
        box.append(bar)
        box.append(stack)
        if others:
            note = Gtk.Label(label="Community: adi1090x (Android boot animations) and "
                                   "Catppuccin. Cards are still images; selecting one "
                                   "downloads an animated preview.", xalign=0, wrap=True)
            note.add_css_class("dim-label")
            note.add_css_class("caption")
            box.append(note)

        def on_page(*_a) -> None:
            page = stack.get_visible_child_name()
            self._plymouth_tab = page
            search.set_visible(page == "community")
            if page == "custom":
                self._custom_show()
            elif self._plymouth_choice and getattr(self, "_custom_was_shown", False):
                show(self._plymouth_choice)
            self._custom_was_shown = page == "custom"
        stack.connect("notify::visible-child-name", on_page)
        self._custom_was_shown = False
        search.set_visible(False)

        for flow_box in flows:
            child = flow_box.get_first_child()
            while child:
                if getattr(child, "theme", None) == self._plymouth_choice:
                    flow_box.select_child(child)
                    if flow_box is not installed_flow:
                        stack.set_visible_child_name("community")
                    break
                child = child.get_next_sibling()
        saved = getattr(self, "_plymouth_tab", "")
        if saved and stack.get_child_by_name(saved) is not None:
            stack.set_visible_child_name(saved)
        if self._plymouth_choice and saved != "custom":
            show(self._plymouth_choice)
        return box

    # ---------------------------------------------------- My theme (Plymouth)
    def _plymouth_custom_page(self, big_holder, caption, hint, button, badge_slot,
                              clear, token, stack, set_busy) -> Gtk.Widget:
        """The My theme tab: settings + caveats. Every change builds a real
        theme folder in the cache (login.build_custom_plymouth); while the tab
        is open the preview on top draws that folder, which is exactly what
        will be installed."""
        from .app import no_scroll_change        # app imports this module
        from .plymouth_preview import PlymouthPreview

        cfg = login.CustomPlymouth.from_dict(self.data.get("plymouth_custom"))
        spinners = login.available_spinners()
        self._custom_report: login.CustomReport | None = None
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                       margin_top=8, margin_bottom=8, margin_start=8, margin_end=8)

        # --- caveats (in the warning color) ------------------------------
        ensure_css(_NOTES_CSS)
        notes = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        notes.add_css_class("card")
        notes.add_css_class("hs-plymouth-notes")
        head = Gtk.Box(spacing=6, margin_top=8, margin_start=10, margin_end=10)
        icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
        icon.add_css_class("warning")
        head.append(icon)
        title = Gtk.Label(label="Things to keep in mind", xalign=0)
        title.add_css_class("warning")
        title.add_css_class("heading")
        head.append(title)
        notes.append(head)
        note_lines = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3,
                             margin_start=10, margin_end=10, margin_bottom=8)
        notes.append(note_lines)
        page.append(notes)

        # --- settings -------------------------------------------------------
        rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        rows.add_css_class("boxed-list")
        page.append(rows)

        image_row = Adw.ActionRow(title="Image or GIF",
                                  subtitle=_esc(cfg.image) if cfg.image else
                                  "Logo, icon, picture (PNG/JPG/SVG) or animated GIF")
        pick = Gtk.Button(label="Choose…", valign=Gtk.Align.CENTER)
        drop = Gtk.Button(icon_name="edit-clear-symbolic", valign=Gtk.Align.CENTER,
                          tooltip_text="Remove image")
        drop.add_css_class("flat")
        image_row.add_suffix(drop)
        image_row.add_suffix(pick)
        rows.append(image_row)

        def spin(title_text, subtitle, lo, hi, step, value) -> Adw.SpinRow:
            row = Adw.SpinRow.new_with_range(lo, hi, step)
            row.set_title(title_text)
            row.set_subtitle(subtitle)
            row.set_value(value)
            no_scroll_change(row)
            rows.append(row)
            return row

        width_row = spin("Image width", "Pixels, on a 1920-wide screen; at most "
                         f"{login.CUSTOM_MAX_SIDE}", 32, 1200, 8, cfg.image_width)
        image_v_row = spin("Image vertical position", "%: 0 top, 100 bottom",
                           0, 100, 1, round(cfg.image_v * 100))
        options = [("none", "None")] + list(spinners.items())
        spinner_row = Adw.ComboRow(title="Spinner animation",
                                   model=Gtk.StringList.new([o[1] for o in options]))
        spinner_row.set_selected(next((i for i, o in enumerate(options) if o[0] == cfg.spinner), 0))
        rows.append(spinner_row)
        spinner_v_row = spin("Animation vertical position", "%", 0, 100, 1,
                             round(cfg.spinner_v * 100))

        color_row = Adw.ActionRow(title="Background", subtitle="Top and bottom color (gradient)")
        top_btn = Gtk.ColorDialogButton(valign=Gtk.Align.CENTER, dialog=Gtk.ColorDialog())
        bottom_btn = Gtk.ColorDialogButton(valign=Gtk.Align.CENTER, dialog=Gtk.ColorDialog())
        top_btn.set_rgba(_rgba(cfg.bg_top))
        bottom_btn.set_rgba(_rgba(cfg.bg_bottom))
        palette_btn = Gtk.Button(label="From my palette", valign=Gtk.Align.CENTER,
                                 tooltip_text="Background colors of your desktop theme")
        color_row.add_suffix(palette_btn)
        color_row.add_suffix(top_btn)
        color_row.add_suffix(bottom_btn)
        rows.append(color_row)

        firmware_row = Adw.SwitchRow(title="Motherboard logo",
                                     subtitle="The manufacturer's logo (e.g. ASUS) shows behind it")
        firmware_row.set_active(cfg.firmware)
        firmware_row.set_sensitive(login.BGRT.joinpath("image").exists())
        rows.append(firmware_row)

        pending = {"id": 0}

        def note(text: str, level: str = "") -> None:
            label = Gtk.Label(label="• " + text, xalign=0, wrap=True)
            label.add_css_class("caption")
            if level:
                label.add_css_class(level)
            note_lines.append(label)

        def refresh_notes(report: login.CustomReport | None) -> None:
            clear(note_lines)
            note("Every apply regenerates the initramfs: it takes a few minutes, "
                 "and the change shows after a reboot.", "warning")
            if report is not None:
                size = report.bytes / 1024 / 1024
                text = (f"Theme size {size:.1f} MB, {report.frames} frames. It goes into "
                        "the initramfs; the bigger it is, the slower the boot, and /boot "
                        "can fill up.")
                if report.bytes >= login.CUSTOM_LIMIT_BYTES:
                    note(text + f" The {login.CUSTOM_LIMIT_BYTES // 1024 // 1024} MB limit "
                         "is exceeded: shrink the image or pick a shorter GIF.", "error")
                else:
                    note(text, "warning" if report.bytes >= login.CUSTOM_WARN_BYTES else "")
                if report.shortened:
                    note(f"A GIF can have at most {login.CUSTOM_MAX_FRAMES} frames: it was thinned "
                         "out and will play faster for real.", "warning")
                if report.shrunk:
                    note(f"The image can be at most {login.CUSTOM_MAX_SIDE} pixels: "
                         "it was scaled down.", "warning")
                if report.animated:
                    note("With an animated GIF selected the spinner animation is not used; "
                         "the GIF itself animates.")
                if not report.dialog:
                    note("Password box images (spinner theme) not found: if the disk is "
                         "encrypted, the password screen may look plain or broken.", "error")
                else:
                    note("Encrypted disk: the password box images were copied from the "
                         "spinner theme.")
                if report.error:
                    note(report.error, "error")
            note("The preview is scaled down; at boot images are drawn at their real "
                 "pixel size.")

        build = {"running": False, "again": False}

        def rebuild() -> bool:
            """Build the theme in a thread (takes ~2 s with a GIF; keep the UI
            responsive). If a new change arrives during a build, it is rebuilt
            once more afterwards, so two jobs never write the same folder at once."""
            pending["id"] = 0
            if build["running"]:
                build["again"] = True
                return False
            build["running"] = True
            snapshot = login.CustomPlymouth.from_dict(cfg.to_dict())
            if stack.get_visible_child_name() == "custom":
                set_busy("Preparing theme…")
            button.set_sensitive(False)

            def work() -> None:
                try:
                    report = login.build_custom_plymouth(snapshot)
                except Exception as exc:  # a broken image must not crash the UI
                    report = login.CustomReport(directory=login.custom_stage_dir(),
                                                error=f"Could not build the theme: {exc}")
                GLib.idle_add(finished, report)
            threading.Thread(target=work, daemon=True).start()
            return False

        def finished(report: login.CustomReport) -> bool:
            build["running"] = False
            if build["again"]:
                build["again"] = False
                rebuild()
                return False
            self._custom_report = report
            spinner_row.set_sensitive(not report.animated)
            spinner_v_row.set_sensitive(not report.animated and cfg.spinner != "none")
            refresh_notes(report)
            if stack.get_visible_child_name() == "custom":
                set_busy(None)
                self._custom_show()
            else:
                button.set_sensitive(self._plymouth_job is None)
            return False

        def changed() -> None:
            self.data["plymouth_custom"] = cfg.to_dict()
            self._save()
            if pending["id"]:
                GLib.source_remove(pending["id"])
            pending["id"] = GLib.timeout_add(250, rebuild)

        def set_attr(name, value) -> None:
            setattr(cfg, name, value)
            changed()

        width_row.connect("notify::value", lambda r, _p: set_attr("image_width", int(r.get_value())))
        image_v_row.connect("notify::value", lambda r, _p: set_attr("image_v", r.get_value() / 100))
        spinner_v_row.connect("notify::value", lambda r, _p: set_attr("spinner_v", r.get_value() / 100))
        spinner_row.connect("notify::selected", lambda r, _p: set_attr(
            "spinner", options[r.get_selected()][0]))
        top_btn.connect("notify::rgba", lambda b, _p: set_attr("bg_top", _qt_color(b.get_rgba())))
        bottom_btn.connect("notify::rgba", lambda b, _p: set_attr("bg_bottom", _qt_color(b.get_rgba())))
        firmware_row.connect("notify::active", lambda r, _p: set_attr("firmware", r.get_active()))

        def from_palette(_b) -> None:
            variables = self._variables()
            top_btn.set_rgba(_rgba("#" + variables.get("COL_BG", "1e1e2e").lstrip("#")))
            bottom_btn.set_rgba(_rgba("#" + variables.get("COL_BG_DARK",
                                                          variables.get("COL_BG", "11111b")).lstrip("#")))
        palette_btn.connect("clicked", from_palette)

        def on_pick(_b) -> None:
            def chosen(path: Path) -> None:
                image_row.set_subtitle(_esc(str(path)))
                set_attr("image", str(path))
            pick_file(self.win, "Boot animation image", chosen, filter_name="Images",
                      patterns=["*.png", "*.jpg", "*.jpeg", "*.svg", "*.gif", "*.webp", "*.bmp"])
        pick.connect("clicked", on_pick)

        def on_drop(_b) -> None:
            image_row.set_subtitle("Logo, icon, picture (PNG/JPG/SVG) or animated GIF")
            set_attr("image", "")
        drop.connect("clicked", on_drop)

        def show_custom() -> None:
            token["n"] += 1
            clear(big_holder)
            clear(badge_slot)
            report = self._custom_report
            if report is not None:
                scene = login.plymouth_scene(login.CUSTOM_PLYMOUTH, report.directory)
                big_holder.append(PlymouthPreview(scene, width=BIG))
            current = login.plymouth_current() == login.CUSTOM_PLYMOUTH
            caption.set_markup("<b>My theme</b>" + (" · <i>active now</i>" if current else "")
                               + "\n<span size='small'>A theme built from the settings below; "
                               "once installed it also shows on the Installed tab.</span>")
            blocked = report is None or bool(report.error) or \
                report.bytes >= login.CUSTOM_LIMIT_BYTES
            button.set_label("Build and apply")
            set_busy("Preparing theme…" if build["running"] else None)
            button.set_sensitive(not blocked and self._plymouth_job is None
                                 and not build["running"])
            hint.set_label("The theme is copied to /usr/share/plymouth/themes/souprland-ozel "
                           "and enabled; the sudo password is asked in the terminal."
                           if not blocked else "First fix the red issue in the notes.")

        self._custom_show = show_custom
        # The button must be re-enabled when going back to the other tabs.
        stack.connect("notify::visible-child-name", lambda s, _p: button.set_sensitive(
            self._plymouth_job is None) if s.get_visible_child_name() != "custom" else None)
        refresh_notes(None)
        rebuild()
        return page

    def _apply_custom_plymouth(self, install_root: Path) -> None:
        report = getattr(self, "_custom_report", None)
        if report is None or report.error or report.bytes >= login.CUSTOM_LIMIT_BYTES:
            return
        self._start_plymouth_job("apply", login.CUSTOM_PLYMOUTH,
                                 login.custom_plymouth_script(report.directory, install_root),
                                 "Installing my theme in a terminal")

    def _apply_plymouth(self, install_root: Path, theme: str) -> None:
        # _run_script already takes the snapshot; install.sh's own is turned off.
        self._start_plymouth_job("apply", theme, login.plymouth_script(install_root, theme),
                                 f"Applying boot animation ({theme}) in a terminal")

    # ------------------------------------------------- running job (terminal)
    #: Stop watching after this long (the terminal may have been left open).
    JOB_WATCH_SECONDS = 45 * 60

    def _start_plymouth_job(self, kind: str, theme: str, script: str, message: str) -> None:
        """An Install/Apply running in a terminal: a spinner above the section,
        buttons locked; when it ends the section refreshes itself and reports
        the result."""
        if self._plymouth_job is not None:
            return
        runtime = Path(GLib.get_user_runtime_dir() or GLib.get_tmp_dir())
        status = runtime / f"hyprsetup-plymouth-{os.getpid()}-{int(time.time())}.status"
        if not self._run_script(script, message, status=status):
            return
        self._plymouth_job = {"kind": kind, "theme": theme, "status": status,
                              "started": time.monotonic()}
        self._build_plymouth()
        GLib.timeout_add_seconds(1, self._watch_plymouth_job)

    def _watch_plymouth_job(self) -> bool:
        job = self._plymouth_job
        if job is None:
            return False
        status: Path = job["status"]
        if not status.is_file():
            if time.monotonic() - job["started"] > self.JOB_WATCH_SECONDS:
                self._plymouth_job = None
                self._build_plymouth()
                return False
            return True
        try:
            code = int(status.read_text().strip() or "1")
        except (OSError, ValueError):
            code = 1
        status.unlink(missing_ok=True)
        self._plymouth_job = None
        theme = job["theme"]
        if job["kind"] == "install":
            ok = code == 0 and theme in login.plymouth_themes()
            message = (f"✓ {theme} installed; you can press Apply now" if ok else
                       f"Install did not complete (exit code {code}); see the terminal output")
        else:
            ok = code == 0 and login.plymouth_current() == theme
            message = (f"✓ Boot animation is now “{theme}”; visible after a reboot"
                       if ok else f"Apply did not complete (exit code {code}); "
                       "check the terminal output")
        self._plymouth_choice = theme
        self._build_plymouth()
        self.win._toast(message)
        return False

    def _job_banner(self) -> Gtk.Widget:
        job = self._plymouth_job
        what = {"install": "installing", "apply": "applying"}.get(job["kind"], "running")
        bar = Gtk.Box(spacing=10, margin_bottom=6)
        bar.add_css_class("card")
        spinner = Gtk.Spinner(spinning=True, margin_start=12, margin_top=10, margin_bottom=10)
        bar.append(spinner)
        label = Gtk.Label(xalign=0, wrap=True, hexpand=True)
        label.set_markup(f"<b>{_esc(job['theme'])}</b>: {what} in a terminal. "
                         "This section refreshes itself when it is done.")
        bar.append(label)
        stop = Gtk.Button(label="Stop watching", valign=Gtk.Align.CENTER, margin_end=10)
        stop.add_css_class("flat")
        stop.set_tooltip_text("Does not stop the job in the terminal; only hides this indicator.")

        def on_stop(_b) -> None:
            self._plymouth_job = None
            self._build_plymouth()
        stop.connect("clicked", on_stop)
        bar.append(stop)
        return bar
