"""GUI state: selected components, setting values and settings.conf generation."""

from __future__ import annotations

import os
from pathlib import Path

from ..apply import foreign_owner
from ..catalog import Catalog
from .. import conffile
from .. import presets as presets_mod
from .. import settings as schema
from .. import render as render_mod
from .. import palette as palette_mod
from .. import themes

# Settings not in the schema but edited in the GUI (they have custom widgets)
EXTRA_DEFAULTS = {
    "THEME": themes.DEFAULT,
    "CUSTOM_COLORS": "",
    "COLOR_SCHEME": "dark",
    "BAR_MODULES_LEFT": "hyprland/workspaces,hyprland/submap",
    "BAR_MODULES_CENTER": "hyprland/window",
    "BAR_MODULES_RIGHT": ("cpu,memory,backlight,pulseaudio,bluetooth,network,"
                          "battery,tray,clock,custom/mic,custom/power"),
    "CURSOR_THEME": "Bibata-Modern-Ice",
    "FONT_FAMILY": "Noto Sans",
    "FONT_SIZE": "11",
    "MOD_KEY": "SUPER",
    "MONITOR_SPEC": ",preferred,auto,1",
    "WORKSPACE_MONITOR_MAP": "",
    "MANAGE_HYPR_CONFIGS": "1",
    "MANAGE_MONITORS": "1",
    "WIDGET_SET": "",
    "WIDGET_STYLE": "",
    "GLOBAL_OPACITY": "",
    "EXTRA_ENV": "",
    "EXTRA_EXEC_ONCE": "",
    "BROWSER": "firefox",
    "KEYBINDS": "",
}

# Keys written by to_conf() outside the schema. Settings that come from a preset
# and are in none of these lists (e.g. MASTER_MFACT) are written in a separate
# section; otherwise they would silently get lost when installing from the UI.
HEADER_KEYS = ("THEME", "CUSTOM_COLORS", "COLOR_SCHEME", "CURSOR_THEME",
               "CURSOR_SIZE", "FONT_FAMILY", "FONT_SIZE", "MOD_KEY")
BAR_MODULE_KEYS = ("BAR_MODULES_LEFT", "BAR_MODULES_CENTER",
                   "BAR_MODULES_RIGHT")
SCOPE_KEYS = ("WIDGET_SET", "WIDGET_STYLE", "MANAGE_HYPR_CONFIGS", "MANAGE_MONITORS", "MONITOR_SPEC",
              "WORKSPACE_MONITOR_MAP", "GLOBAL_OPACITY", "EXTRA_ENV",
              "EXTRA_EXEC_ONCE", "BROWSER")
KEYBIND_KEYS = ("KEYBINDS",)

#: Component selected automatically when a widget is enabled and no engine is
#: selected (config/components.json → "widget" category).
DEFAULT_WIDGET_ENGINE = "eww"

# Keep profile images in the usual wallpaper folder without replacing custom
# wallpapers or the copies Soup Maker uses for its saved selections.
PROFILE_WALLPAPER_PATH = "~/Pictures/wallpapers/souprland-profile.png"


def config_path() -> Path:
    """Persistent location of the settings: ``~/.config/hyprsetup/settings.conf``.

    For a settings app independent of the installer, ``~/.cache`` is the wrong
    place: any cache-cleaning tool could wipe all settings. install.sh
    (SETTINGS_FILE) writes exactly this file too.
    """
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "hyprsetup" / "settings.conf"


def config_candidates() -> list[Path]:
    """Places to read settings from, in priority order.

    The order is for backward compatibility: old versions wrote the GUI's last
    state to ~/.cache/hyprsetup/gui.conf and the installer wrote setup.conf.
    The first readable one wins; the next save goes to the new path anyway, so
    the migration happens once, on its own.
    """
    cache = Path(os.environ.get("XDG_CACHE_HOME")
                 or str(Path.home() / ".cache")) / "hyprsetup"
    return [config_path(), cache / "gui.conf", cache / "setup.conf"]


def parse_conf_file(path: Path) -> dict[str, str]:
    """Read the KEY="value" file written by install.sh and by this app.

    As plain text, without running bash; the escaping rules are in conffile.py.
    """
    return conffile.parse_file(path)


class SetupState:
    def __init__(self, catalog: Catalog, profile: str = "standard"):
        self.catalog = catalog
        self.values: dict[str, str] = dict(schema.defaults())
        self.values.update(EXTRA_DEFAULTS)
        self.profile = profile
        self.preset = ""                 # name of the applied profile
        #: Selected look variant of the profile (presets/profile/<name>.variants/).
        self.variant = ""
        # The preset the user explicitly picked on the Bar Presets page. If empty
        # the bar comes from the profile; if set it survives profile changes.
        self.pinned_bar = ""
        self.pinned_term = ""
        self.pinned_launcher = ""
        self.extra_values: dict[str, str] = {}   # preset settings outside the schema
        self.selected: set[str] = set()
        self.apply_profile(profile)
        self._listeners: list = []
        #: Dependency checker: (requirements, name, on_ok, on_cancel).
        #: Set by the UI (MainWindow._require); while None, values are written
        #: unchecked (e.g. tests, headless use).
        self.require = None

    # ------------------------------------------------------------- events --
    def connect(self, callback) -> None:
        self._listeners.append(callback)

    def _notify(self) -> None:
        for callback in self._listeners:
            callback()

    # ----------------------------------------------------------- settings --
    def get(self, key: str) -> str:
        return self.values.get(key, "")

    def set(self, key: str, value) -> None:
        text = str(value)
        if self.values.get(key) == text:
            return
        self.values[key] = text
        self._notify()

    # ------------------------------------------------------------ preset ---
    @staticmethod
    def _base_defaults() -> dict[str, str]:
        """Initial values that a reset goes back to.

        ``schema.defaults()`` alone is not enough: some keys such as the module
        zones live in ``EXTRA_DEFAULTS``, not the schema, and would end up empty
        if reset from the schema alone, i.e. a bar without modules.
        """
        base = dict(schema.defaults())
        base.update(EXTRA_DEFAULTS)
        return base

    @staticmethod
    def _conf_keys() -> set[str]:
        """Setting keys that to_conf() writes on its own."""
        keys = {"PROFILE", "PRESET", "PROFILE_VARIANT", *HEADER_KEYS,
                *BAR_MODULE_KEYS, *SCOPE_KEYS,
                *KEYBIND_KEYS}
        keys.update(setting.key for setting in schema.all_settings())
        return keys

    def apply_preset(self, name: str, values: dict[str, str]) -> None:
        """Write a look preset into the state (does not touch the component selection)."""
        known = self._conf_keys()
        if "THEME" in values:
            # Manual color edits belonged to another theme.
            self.values["CUSTOM_COLORS"] = ""
        for key, value in values.items():
            self.values[key] = str(value)
            if key not in known:
                self.extra_values[key] = str(value)
        self.preset = name
        self._notify()

    # ---------------------------------------------------- persistent state ----
    def load_conf(self, path: Path) -> bool:
        """Load a previously installed/saved settings file into the state.

        The GUI starts from ``schema.defaults()`` (and the "standard" profile)
        on every launch; if this file is not read, then when the user changes a
        single setting and presses "Apply", ALL the other settings not yet seen
        are written reset to their schema defaults instead of the actually
        installed/wanted values. That is why on GUI startup both its own
        ``~/.cache/hyprsetup/gui.conf`` and the ``~/.cache/hyprsetup/settings.conf``
        written by install.sh are tried (see app.py MainWindow).
        """
        loaded = parse_conf_file(path)
        if not loaded:
            return False

        primary_var_names = {cat.var for cat in self.catalog.categories if cat.var}
        skip = {"COMPONENTS"} | primary_var_names

        for key, value in loaded.items():
            if key in skip:
                continue
            self.values[key] = value

        # Old settings files: WINDOW_SWITCHER="off" is now a separate key.
        if self.values.get("WINDOW_SWITCHER") == "off":
            self.values["SWITCHER_ENABLED"] = "false"
            self.values["WINDOW_SWITCHER"] = "overlay"

        if "PROFILE" in loaded:
            self.profile = loaded["PROFILE"]
        if "PRESET" in loaded:
            self.preset = loaded["PRESET"]
        self.variant = loaded.get("PROFILE_VARIANT", "")
        self.pinned_bar = loaded.get("BAR_PRESET", "")
        self.pinned_term = loaded.get("TERM_PRESET", "")
        self.pinned_launcher = loaded.get("LAUNCHER_PRESET", "")

        components = loaded.get("COMPONENTS", "")
        if components:
            known = set(self.catalog.all_ids())
            self.selected = {c for c in components.split(",") if c in known}
            self.selected.update(self.catalog.required_ids())

        known_keys = self._conf_keys()
        self.extra_values = {k: v for k, v in loaded.items()
                             if k not in known_keys and k not in skip
                             and k not in ("PROFILE", "OVERWRITE_CONFIGS")}
        self._notify()
        return True

    def adopt_foreign_monitors(self) -> dict[str, str]:
        """Leave the display settings to another tool if it manages those files.

        nwg-displays generates monitors.conf/workspaces.conf itself. As long as
        MANAGE_MONITORS=1 (the default), this tool regenerated those files on
        ANY setting change and completely reset the display layout the user
        made in nwg-displays. Matching the state to reality makes the switch
        show correctly in the UI and makes the next save_conf persist the
        decision (apply.py does the same detection on its own).

        Returns {relative path: tool name}; the UI tells the user about it.
        """
        base = Path(os.environ.get("XDG_CONFIG_HOME")
                    or str(Path.home() / ".config"))
        owners: dict[str, str] = {}
        for rel, key, value in (
                ("hypr/monitors.conf", "MANAGE_MONITORS", "0"),
                ("hypr/workspaces.conf", "WORKSPACE_MONITOR_MAP", "")):
            owner = foreign_owner(base / rel)
            if not owner:
                continue
            owners[rel] = owner
            self.values[key] = value
        return owners

    # --------------------------------------------------------- gallery axes --
    # The three axes are independent: profile, bar preset, widgets. The profile
    # only provides defaults for the other two; if the user picks a bar preset
    # separately, that wins. Resolution happens in presets.resolve_chain, with
    # the same rules as lib/preset.sh.
    def apply_profile_preset(self, root, name: str, variant: str = "", *,
                             select_wallpaper: bool = True) -> None:
        """Apply a profile and drop the bar pin, so the profile's own bar
        preset takes effect ("Leave to profile" is the default for every
        profile).

        Even if you pinned a bar preset by hand earlier, switching profiles
        clears that pin; to pin a bar style again, pick it again on the Bar
        Presets page.

        Look settings the new profile does not define do not carry over from
        the old profile but go back to their defaults; otherwise switching from
        a profile with blur to one without would leave blur on.

        ``select_wallpaper`` is false when clearing a pinned component preset.
        """
        self.pinned_bar = ""
        self.pinned_term = ""
        self.pinned_launcher = ""
        values = presets_mod.resolve_chain(
            root, profile=name, bar=self.pinned_bar, widgets=self.get("WIDGETS"),
            variant=variant)
        # The resolved variant (the profile's default if none given); empty if
        # the profile has no variants.
        self.variant = values.pop("PROFILE_VARIANT", "")
        keys = (list(presets_mod.LOOK_KEYS) + list(presets_mod.BAR_KEYS)
                + list(presets_mod.TERM_KEYS) + list(presets_mod.LAUNCHER_KEYS))
        own = presets_mod.find(presets_mod.default_dir(root, "profile"), name)
        if own is not None and ("WIDGET_SET" in own.values or "WIDGETS" in own.values):
            # The profile states its widgets explicitly (even if empty): the
            # profile's choice applies, not the user's previous one. Otherwise
            # Sakura's widgets carried over to widget-less Neon, and Orman's own
            # set never arrived.
            chain = presets_mod.resolve_chain(root, profile=name, bar=self.pinned_bar,
                                              variant=variant)
            chain.pop("PROFILE_VARIANT", None)
            keys += list(presets_mod.WIDGET_SET_KEYS) + ["WIDGET_SET"]
            for key in (*presets_mod.WIDGET_SET_KEYS, "WIDGET_SET"):
                values.pop(key, None)
                if key in chain:
                    values[key] = chain[key]
            values.setdefault("WIDGETS", "")
        merged = presets_mod.reset_values(keys, self._base_defaults())
        merged.update(values)
        if select_wallpaper and (merged.get("WALLPAPER_IMAGE") or merged.get("WALLPAPER_STYLE")):
            merged.setdefault("WALLPAPER_PATH", PROFILE_WALLPAPER_PATH)
        self.apply_preset(name, merged)

    #: Component selections a profile can change (category variable →
    #: component id). The bar backend is separate: MainWindow._sync_bar_backend.
    PROFILE_COMPONENT_VARS = ("TERMINAL", "LAUNCHER", "NOTIFIER", "WIDGET_ENGINE",
                              "WALLPAPER_DAEMON")

    #: A Wallpaper Engine scene shows no image: when switching to a profile that
    #: does not want it, the first installed one of these is selected, otherwise
    #: the new profile's WALLPAPER_IMAGE would never reach the screen.
    IMAGE_WALLPAPER_DAEMONS = ("hyprpaper", "swww")

    def sync_profile_components(self, root, name: str, installed=None) -> list[str]:
        """Select the terminal/launcher/notifier/widget engine the profile wants.

        Values like ``TERMINAL="foot"`` in the profile file used to be written
        only as values; since the component selection did not change, the
        generated config (apply.export_vars derives it from the selection)
        stayed on the old program. If ``installed(id)`` is given, components
        that are not installed are not selected (so you are never left without
        a terminal); returns notes to show the user.
        """
        variant = self.variant if self.preset == name else ""
        values = presets_mod.resolve_chain(root, profile=name, variant=variant)
        notes: list[str] = []
        if self.is_selected("wallpaperengine") and not values.get("WALLPAPER_DAEMON"):
            values["WALLPAPER_DAEMON"] = next(
                (c for c in self.IMAGE_WALLPAPER_DAEMONS
                 if installed is None or installed(c)),
                self.IMAGE_WALLPAPER_DAEMONS[0])
        for var in self.PROFILE_COMPONENT_VARS:
            want = (values.get(var) or "").strip()
            comp = self.catalog.component(want) if want else None
            if comp is None or self.is_selected(want):
                continue
            if installed is not None and not installed(want):
                packages = " ".join((comp.repo or []) + (comp.aur or []))
                notes.append(f"{comp.title} is not installed" +
                             (f" (pacman -S {packages})" if packages else ""))
                continue
            self.toggle(want, True)
            notes.append(f"{comp.title} selected")
        return notes

    def apply_bar_preset(self, root, name: str) -> None:
        """Pin a bar preset as the user's choice and apply it.

        Being pinned, it overrides the profile's own BAR_* tweaks; the choice
        survives later profile changes (see apply_profile_preset).

        Only BAR_KEYS are reset: theme, layout and decoration belong to the
        profile, and changing the bar preset must not touch them.
        """
        self.pinned_bar = name
        values = presets_mod.resolve_chain(
            root, profile=self.preset, variant=self.variant, bar=name, widgets=self.get("WIDGETS"))
        merged = presets_mod.reset_values(presets_mod.BAR_KEYS,
                                          self._base_defaults())
        merged.update({k: v for k, v in values.items()
                       if k in presets_mod.BAR_KEYS or k == "BAR_PRESET"})
        known = self._conf_keys()
        for key, value in merged.items():
            self.values[key] = str(value)
            if key not in known:
                self.extra_values[key] = str(value)
        # A "match the bar preset" terminal/launcher is re-picked for the new bar.
        self.follow_bar(root, notify=False)
        self._notify()

    def follow_bar(self, root, notify: bool = True) -> None:
        """If TERM_PRESET / LAUNCHER_PRESET is "auto", refresh those presets to match the bar."""
        for kind, key in (("terminal", "TERM_PRESET"),
                          ("launcher", "LAUNCHER_PRESET")):
            if self.get(key) == presets_mod.AUTO:
                self.apply_axis_preset(root, kind, presets_mod.AUTO,
                                       notify=False)
        if notify:
            self._notify()

    def apply_widget_set(self, root, name: str) -> None:
        """Apply a widget set layout (presets/widget-set/<name>.conf).

        Writes which widgets are enabled AND which corner they go in together;
        sizes (margin, scale, radius, opacity) are part of the set too. Only
        WIDGET_SET_KEYS are reset; theme, layout and bar settings do not belong
        to this axis.
        """
        values = presets_mod.resolve_chain(
            root, profile=self.preset, variant=self.variant, bar=self.pinned_bar, widget_set=name)
        merged = presets_mod.reset_values(presets_mod.WIDGET_SET_KEYS,
                                          self._base_defaults())
        merged.update({k: v for k, v in values.items()
                       if k in presets_mod.WIDGET_SET_KEYS})
        merged["WIDGET_SET"] = name
        known = self._conf_keys()
        for key, value in merged.items():
            self.values[key] = str(value)
            if key not in known:
                self.extra_values[key] = str(value)
        # The set writes the widget list, but if no engine is selected nothing
        # is generated; that was the source of "I applied it, it doesn't work".
        self._ensure_widget_engine(root)
        self._notify()

    def apply_widget_style(self, root, name: str) -> None:
        """Apply a widget look preset (presets/widget-style/<name>.conf).

        Only WIDGET_STYLE_KEYS are reset and rewritten: which widgets are on
        and where (the widget set) stay as they are. Every key can then be
        changed one by one on the Widgets page.
        """
        values = presets_mod.resolve_chain(
            root, profile=self.preset, variant=self.variant, bar=self.pinned_bar,
            widget_style=name)
        merged = presets_mod.reset_values(presets_mod.WIDGET_STYLE_KEYS,
                                          self._base_defaults())
        merged.update({k: v for k, v in values.items()
                       if k in presets_mod.WIDGET_STYLE_KEYS})
        merged["WIDGET_STYLE"] = name
        known = self._conf_keys()
        for key, value in merged.items():
            self.values[key] = str(value)
            if key not in known:
                self.extra_values[key] = str(value)
        self._notify()

    def apply_axis_preset(self, root, kind: str, name: str,
                          notify: bool = True) -> None:
        """Pin a terminal/launcher preset as the user's choice.

        Same rule as ``apply_bar_preset``: only that axis's keys are reset and
        rewritten; theme and layout stay with the profile.
        """
        keys, key_name = self._axis(kind)
        if kind == "terminal":
            self.pinned_term = name
        else:
            self.pinned_launcher = name
        values = presets_mod.resolve_chain(
            root, profile=self.preset, variant=self.variant, bar=self.pinned_bar,
            widgets=self.get("WIDGETS"), **{kind: name})
        merged = presets_mod.reset_values(keys, self._base_defaults())
        merged.update({k: v for k, v in values.items()
                       if k in keys or k == key_name})
        known = self._conf_keys()
        for key, value in merged.items():
            self.values[key] = str(value)
            if key not in known:
                self.extra_values[key] = str(value)
        if notify:
            self._notify()

    def clear_axis_preset(self, root, kind: str) -> None:
        """Drop the terminal/launcher pin; the profile's own comes back."""
        _keys, key_name = self._axis(kind)
        if kind == "terminal":
            self.pinned_term = ""
        else:
            self.pinned_launcher = ""
        if self.preset:
            self.apply_profile_preset(root, self.preset, select_wallpaper=False)
        else:
            self.set(key_name, "")

    @staticmethod
    def _axis(kind: str) -> tuple[tuple[str, ...], str]:
        if kind == "terminal":
            return presets_mod.TERM_KEYS, "TERM_PRESET"
        if kind == "launcher":
            return presets_mod.LAUNCHER_KEYS, "LAUNCHER_PRESET"
        raise ValueError(f"unknown axis: {kind}")

    def pinned_axis(self, kind: str) -> str:
        return self.pinned_term if kind == "terminal" else self.pinned_launcher

    def clear_bar_preset(self, root) -> None:
        """Drop the bar pin; the profile's own preset comes back."""
        self.pinned_bar = ""
        if self.preset:
            self.apply_profile_preset(root, self.preset, select_wallpaper=False)
        else:
            self.set("BAR_PRESET", "")

    def widgets(self) -> list[str]:
        return presets_mod.split_widgets(self.get("WIDGETS"))

    # --------------------------------------------------------- components --
    def apply_profile(self, profile: str) -> None:
        self.profile = profile
        self.selected = set(self.catalog.profile(profile))
        self.selected.update(self.catalog.required_ids())
        self._notify() if getattr(self, "_listeners", None) else None

    def is_selected(self, comp_id: str) -> bool:
        return comp_id in self.selected

    def toggle(self, comp_id: str, active: bool) -> None:
        category = self.catalog.category_of(comp_id)
        if category and category.required:
            return
        if active and category and category.single:
            for sibling in category.components:
                self.selected.discard(sibling.id)
        if active:
            self.selected.add(comp_id)
        else:
            self.selected.discard(comp_id)
        self._notify()

    # ------------------------------------------------ theme colors --------
    def palette(self) -> dict[str, str]:
        """The palette the desktop will ACTUALLY get: theme (or the wallpaper
        if "auto") + manual tone + individual colors. Same rule as generation
        (render.effective_palette); the previews draw this."""
        return render_mod.effective_palette(self.values)[1]

    def set_colour(self, key: str, hex_value: str) -> None:
        """Write a single color to CUSTOM_COLORS; other edits are kept.

        No diff against the whole palette is computed: palette() now includes
        the wallpaper and tone shift too, so diffing would freeze all current
        colors into CUSTOM_COLORS and none would change when the wallpaper/tone
        changes. A value equal to the theme's own color removes the edit.
        """
        value = hex_value.lstrip("#").lower()
        overrides = themes.parse_overrides(self.get("CUSTOM_COLORS"))
        theme = self.get("THEME")
        base = themes.THEMES.get(theme) if theme in themes.THEMES else None
        tone = palette_mod.tone_from(self.values)
        if base is not None and not any(tone) and base.get(key) == value:
            overrides.pop(key, None)
        else:
            overrides[key] = value
        self.set("CUSTOM_COLORS", ";;".join(
            f"{k}={overrides[k]}" for k in themes.KEYS if k in overrides))

    def reset_colours(self) -> None:
        self.set("CUSTOM_COLORS", "")

    # ------------------------------------------------ bar modules ---------

    def zone_modules(self, zone: str) -> list[str]:
        """Return the modules in a zone IN ORDER.

        Order matters: BAR_MODULES_* is an ordered comma-separated list and all
        four backends draw the modules in that order. The old dropdown editor
        could only answer "which zone", so the order could not be edited at all.
        """
        return [m.strip() for m in self.get(f"BAR_MODULES_{zone}").split(",")
                if m.strip()]

    def _write_zone(self, zone: str, items: list[str]) -> None:
        self.values[f"BAR_MODULES_{zone}"] = ",".join(items)

    def add_module(self, zone: str, module: str) -> None:
        """Append the module to the END of the zone; remove it from any other zone."""
        for candidate in ("LEFT", "CENTER", "RIGHT"):
            items = self.zone_modules(candidate)
            if candidate == zone:
                if module not in items:
                    items.append(module)
            elif module in items:
                items.remove(module)
            self._write_zone(candidate, items)
        self._notify()

    def remove_module(self, module: str) -> None:
        """Remove the module from every zone it is in."""
        for zone in ("LEFT", "CENTER", "RIGHT"):
            items = self.zone_modules(zone)
            if module in items:
                items.remove(module)
                self._write_zone(zone, items)
        self._notify()

    def move_module(self, zone: str, module: str, delta: int) -> None:
        """Move the module within its zone by delta (-1 left, +1 right)."""
        items = self.zone_modules(zone)
        if module not in items:
            return
        index = items.index(module)
        target = index + delta
        if not 0 <= target < len(items):
            return
        items[index], items[target] = items[target], items[index]
        self._write_zone(zone, items)
        self._notify()

    # ---------------------------------------------- widget layout ----------
    # WIDGETS answers "which are enabled", WIDGET_ZONE_* answers "in which
    # corner and in what order". Both are written together here: enabling a
    # widget in the UI puts it both in the list and in a corner, disabling it
    # removes it from both, so the two keys can never diverge into "enabled
    # but in no corner".
    def widget_zone_list(self, zone: str) -> list[str]:
        """Widgets in the corner, in drawing order.

        Enabled widgets never written to any list are shown in their default
        corner from the catalog; the render side applies the same rule
        (see render.widget_zone_of).
        """
        explicit = [w.strip() for w in self.get(f"WIDGET_ZONE_{zone}").split(",")
                    if w.strip()]
        active = self.widgets()
        out = [w for w in explicit if w in active]
        placed = {w for z in render_mod.WIDGET_ZONES
                  for w in [x.strip() for x in
                            self.get(f"WIDGET_ZONE_{z}").split(",") if x.strip()]}
        for name in active:
            if name in placed or name in out:
                continue
            spec = render_mod.WIDGET_CATALOG.get(name)
            if spec and spec.zone == zone:
                out.append(name)
        return out

    def _write_widget_zone(self, zone: str, items: list[str]) -> None:
        self.values[f"WIDGET_ZONE_{zone}"] = ",".join(items)

    def _write_widgets(self) -> None:
        """Rebuild WIDGETS from the corner lists (order: TL, TR, BL, BR)."""
        names: list[str] = []
        for zone in render_mod.WIDGET_ZONES:
            for name in [w.strip() for w in
                         self.get(f"WIDGET_ZONE_{zone}").split(",") if w.strip()]:
                if name not in names:
                    names.append(name)
        self.values["WIDGETS"] = ",".join(names)

    def add_widget(self, root, zone: str, name: str) -> None:
        """Append the widget to the end of the corner; remove it from any other corner."""
        for candidate in render_mod.WIDGET_ZONES:
            items = self.widget_zone_list(candidate)
            if candidate == zone:
                if name not in items:
                    items.append(name)
            elif name in items:
                items.remove(name)
            self._write_widget_zone(candidate, items)
        self._write_widgets()
        self._ensure_widget_engine(root)
        # If the engine is already selected, _ensure_widget_engine does not
        # notify; live apply and the preview still need to hear about the change.
        self._notify()

    def set_widget_enabled(self, root, name: str, active: bool) -> None:
        """The on/off switch on the Widgets page.

        An enabled widget is appended to the end of its default position
        (catalog); from there it can be moved with the corner editor. Disabling
        removes it from every position and from the offsets.
        """
        if active == (name in self.widgets()):
            return
        # A manually changed layout is no longer the widget set itself.
        self.values["WIDGET_SET"] = ""
        if active:
            spec = render_mod.WIDGET_CATALOG.get(name)
            self.add_widget(root, spec.zone if spec else "TR", name)
        else:
            self.remove_widget(root, name)

    def remove_widget(self, root, name: str) -> None:
        for zone in render_mod.WIDGET_ZONES:
            items = self.widget_zone_list(zone)
            if name in items:
                items.remove(name)
            self._write_widget_zone(zone, items)
        self._write_widgets()
        # Do not let a disabled widget's offset leak into the next time it is enabled.
        self.set_widget_offset(name, 0, 0, notify=False)
        self._ensure_widget_engine(root)
        self._notify()

    def widget_offset(self, name: str) -> tuple[int, int]:
        """The widget's (x, y) fine offset; (0, 0) if none."""
        return render_mod.widget_offsets(self.values).get(name, (0, 0))

    def set_widget_offset(self, name: str, x: int, y: int,
                          notify: bool = True) -> None:
        offsets = render_mod.widget_offsets(self.values)
        offsets[name] = (int(x), int(y))
        self.values["WIDGET_OFFSETS"] = render_mod.format_widget_offsets(offsets)
        if notify:
            self._notify()

    def move_widget(self, zone: str, name: str, delta: int) -> None:
        items = self.widget_zone_list(zone)
        if name not in items:
            return
        index = items.index(name)
        target = index + delta
        if not 0 <= target < len(items):
            return
        items[index], items[target] = items[target], items[index]
        self._write_widget_zone(zone, items)
        self._write_widgets()
        self._notify()

    def _ensure_widget_engine(self, root) -> None:
        """Make sure an engine is selected if a widget is on; drop it if all are off.

        Enabling a widget with no engine selected generates nothing, and the
        user cannot see why.
        """
        current = self.widgets()
        if current and not self.category_has_selection("widget"):
            self.toggle(DEFAULT_WIDGET_ENGINE, True)
        elif not current and self.is_selected(DEFAULT_WIDGET_ENGINE):
            self.toggle(DEFAULT_WIDGET_ENGINE, False)
        self._notify()

    def category_has_selection(self, category_id: str) -> bool:
        category = next((c for c in self.catalog.categories
                         if c.id == category_id), None)
        if not category:
            return False
        return any(c.id in self.selected for c in category.components)

    def primary(self, category_id: str) -> str:
        category = next((c for c in self.catalog.categories
                         if c.id == category_id), None)
        if not category:
            return ""
        for comp in category.components:
            if comp.id in self.selected:
                return comp.id
        return ""

    # -------------------------------------------------------- statistics ---

    # ------------------------------------------------------- settings.conf ----
    def to_conf(self) -> str:
        primaries = self.catalog.primary_vars(sorted(self.selected))
        lines = [
            "# hyprsetup — generated by the settings app",
            "# Reuse this file with --config: ./install.sh --config <this file>",
        ]
        if self.preset:
            # Informational: the values below started from this preset and
            # reached their final form through changes made in the UI.
            lines.append(f"# Starting preset: {self.preset}")
        lines.append("")

        def emit(key: str, value: str) -> None:
            # Values containing quotes/$ (custom module commands) written
            # unescaped were EXECUTED by install.sh while reading them; the
            # rule lives in conffile.quote.
            lines.append(conffile.line(key, value))

        emit("PROFILE", self.profile)
        # Selected profile and look variant. PRESET used to be read but never
        # written: the selected profile was forgotten when the app reopened.
        emit("PRESET", self.preset)
        emit("PROFILE_VARIANT", self.variant)
        # The choice was already confirmed in the GUI; under install.sh --no-tui the
        # OVERWRITE_CONFIGS default is "ask", which opens a terminal prompt for every
        # existing file, and if the user skips them the install ends without the
        # theme/bar ever being applied.
        emit("OVERWRITE_CONFIGS", "always")
        for key in HEADER_KEYS:
            emit(key, self.get(key))
        lines.append("")

        lines.append("# --- Status bar modules ---")
        for key in BAR_MODULE_KEYS:
            emit(key, self.get(key))
        lines.append("")

        # Keys written in their own section (header, scope…) are skipped here:
        # otherwise the file carries the same key twice.
        own_section = {*HEADER_KEYS, *BAR_MODULE_KEYS, *KEYBIND_KEYS, *SCOPE_KEYS}
        for group in schema.GROUPS:
            lines.append(f"# --- {group.title} ---")
            for setting in group.settings:
                if setting.key in own_section:
                    continue
                emit(setting.key, self.get(setting.key))
            lines.append("")

        lines.append("# --- Keybinding overrides (config/keybinds.json) ---")
        for key in KEYBIND_KEYS:
            emit(key, self.get(key))
        lines.append("")

        lines.append("# --- Displays and scope ---")
        for key in SCOPE_KEYS:
            emit(key, self.get(key))
        lines.append("")

        # Variables of single-choice categories (BAR, TERMINAL…) are written
        # below from the selection; since a bar preset's BAR="hyprpanel" line
        # also landed in extra_values, the same key was emitted twice.
        # load_conf skips these anyway (see primary_var_names).
        extra = {k: v for k, v in self.extra_values.items()
                 if k not in primaries}
        if extra:
            lines.append("# --- Settings from the preset that are not edited in the UI ---")
            for key in sorted(extra):
                emit(key, self.get(key))
            lines.append("")

        lines.append("# --- Primary tools ---")
        for var, value in sorted(primaries.items()):
            emit(var, value)
        lines.append("")

        lines.append("# --- Selected components ---")
        order = self.catalog.all_ids()
        ordered = sorted(self.selected, key=lambda c: order.index(c)
                         if c in order else 999)
        emit("COMPONENTS", ",".join(ordered))
        return "\n".join(lines) + "\n"

    def save_conf(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_conf(), encoding="utf-8")
        return path
