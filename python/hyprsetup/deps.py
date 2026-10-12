"""Before turning a setting on, are the programs it needs actually there?

A setting or widget used to switch on silently even when the program it needs was
not installed: the value was written to settings.conf, render skipped that section,
and the user saw nothing on the desktop. Two kinds of dependency are expressed here
in a single form:

* ``"<component id>"`` — a component in config/components.json. Its packages must
  be installed AND it must be selected (render never generates it otherwise).
* ``"pkg:<package>"``  — a single package without a component (e.g. gnome-keyring).

This module is UI-independent; it works out what is missing. Asking and installing
is done by gui/app.py (``MainWindow._require``).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field

from .catalog import Catalog

PKG_PREFIX = "pkg:"

#: Key in the requires dict that means "any value that is not off".
ANY_VALUE = "*"

#: These values are a setting's "off" state; "*" does not trigger on them.
_OFF_VALUES = {"", "false", "no", "0", "off", "none"}


@dataclass
class Unmet:
    """A single unmet dependency."""
    dep: str                                  # "audio-tools" / "pkg:flatpak"
    title: str                                # name shown in the UI
    packages: list[str] = field(default_factory=list)   # packages to install
    #: Packages are installed but the component is not selected (selecting is enough).
    only_unselected: bool = False
    #: In a single-select category (bar, wallpaper backend…): selecting it REPLACES
    #: the current choice, so it must not happen without asking.
    replaces: str = ""

    @property
    def component(self) -> str:
        return "" if self.dep.startswith(PKG_PREFIX) else self.dep


def triggered(requires: dict[str, tuple[str, ...]], value: str) -> tuple[str, ...]:
    """Dependencies this value asks for in the ``requires`` mapping.

    The value itself is looked up first, then ``"*"`` (any value that is not off).
    Bool settings are written with the "true" key.
    """
    if not requires:
        return ()
    text = (value or "").strip()
    if text in requires:
        return tuple(requires[text])
    if text.lower() in ("true", "yes", "1", "on") and "true" in requires:
        return tuple(requires["true"])
    if text.lower() not in _OFF_VALUES and ANY_VALUE in requires:
        return tuple(requires[ANY_VALUE])
    return ()


def unmet(deps, catalog: Catalog, selected, installed: set[str]) -> list[Unmet]:
    """Unmet dependencies, in the given order (no duplicates).

    If ``installed`` is empty (pacman could not be read, non-Arch environment) the
    packages cannot be checked; then only the component selection is checked —
    Applier makes the same call (see apply.Applier.component_installed).
    """
    selected = set(selected)
    out: list[Unmet] = []
    seen: set[str] = set()
    for dep in deps:
        if not dep or dep in seen:
            continue
        seen.add(dep)
        if dep.startswith(PKG_PREFIX):
            package = dep[len(PKG_PREFIX):]
            if installed and package not in installed:
                out.append(Unmet(dep, package, [package]))
            continue

        comp = catalog.component(dep)
        if comp is None:
            continue
        packages = list(comp.repo) + list(comp.aur)
        missing = [p for p in packages if installed and p not in installed]
        if not missing and dep in selected:
            continue
        category = catalog.category_of(dep)
        replaces = ""
        if category is not None and category.single and dep not in selected:
            current = next((c for c in category.components
                            if c.id in selected), None)
            replaces = current.title if current else ""
        out.append(Unmet(dep, comp.title, missing,
                         only_unselected=not missing, replaces=replaces))
    return out


def packages_of(items: list[Unmet]) -> list[str]:
    """Packages to install, without duplicates."""
    out: list[str] = []
    for item in items:
        for package in item.packages:
            if package not in out:
                out.append(package)
    return out


def in_sync_repos(packages: list[str]) -> set[str]:
    """Packages found in a configured repo (core/extra, Chaotic-AUR…).

    Counterpart of ``lib/packages.sh:repo_has_package``; a single ``pacman -Si``
    call. Empty set without pacman (every AUR package is assumed to be built).
    """
    if not packages:
        return set()
    try:
        out = subprocess.run(["pacman", "-Si", *packages], capture_output=True,
                             text=True, timeout=30, check=False,
                             env={**os.environ, "LC_ALL": "C"}).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    return {line.split(":", 1)[1].strip() for line in out.splitlines()
            if line.startswith("Name ")}


def aur_note(package: str, in_repo: set[str]) -> tuple[str, bool]:
    """How an AUR package will be installed: (note, whether it builds on this machine).

    Same classification as ``lib/packages.sh:pkg_build_note``.
    """
    if package.endswith("-bin"):
        return "prebuilt binary — no build", False
    if package in in_repo:
        return "signed binary in a repo (e.g. Chaotic-AUR) — no build", False
    if package.endswith("-git"):
        return "built from source · -git: not a fixed release, latest code", True
    return "built from source", True
