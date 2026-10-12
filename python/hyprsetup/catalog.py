"""Loading and querying the component catalog."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Component:
    id: str
    title: str
    desc: str = ""
    repo: list[str] = field(default_factory=list)
    aur: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    user_services: list[str] = field(default_factory=list)
    exec: str = ""
    url: str = ""            # upstream project URL (shown as a link in the GUI)
    # Name of the app's .desktop entry. This is the single source for default-app
    # assignment (mimeapps.list, xdg-terminals.list) — see
    # render.py:_default_app_vars and modules/desktop.sh:apply_default_apps.
    # Empty for terminal-only tools (yazi) and library components.
    desktop: str = ""


@dataclass
class Category:
    id: str
    title: str
    select: str = "multi"          # "multi" | "single"
    required: bool = False
    var: str | None = None         # target variable for single-select categories
    components: list[Component] = field(default_factory=list)

    @property
    def single(self) -> bool:
        return self.select == "single"


@dataclass
class Catalog:
    profiles: dict[str, list[str]]
    categories: list[Category]

    @classmethod
    def load(cls, path: str | Path) -> "Catalog":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        categories = []
        for c in raw.get("categories", []):
            components = [
                Component(
                    id=comp["id"],
                    title=comp.get("title", comp["id"]),
                    desc=comp.get("desc", ""),
                    repo=comp.get("repo", []),
                    aur=comp.get("aur", []),
                    services=comp.get("services", []),
                    user_services=comp.get("user_services", []),
                    exec=comp.get("exec", ""),
                    url=comp.get("url", ""),
                    desktop=comp.get("desktop", ""),
                )
                for comp in c.get("components", [])
            ]
            categories.append(
                Category(
                    id=c["id"],
                    title=c.get("title", c["id"]),
                    select=c.get("select", "multi"),
                    required=c.get("required", False),
                    var=c.get("var"),
                    components=components,
                )
            )
        return cls(profiles=raw.get("profiles", {}), categories=categories)

    # ------------------------------------------------------------- queries --
    def component(self, comp_id: str) -> Component | None:
        for cat in self.categories:
            for comp in cat.components:
                if comp.id == comp_id:
                    return comp
        return None

    def category_of(self, comp_id: str) -> Category | None:
        for cat in self.categories:
            if any(c.id == comp_id for c in cat.components):
                return cat
        return None

    def all_ids(self) -> list[str]:
        return [c.id for cat in self.categories for c in cat.components]

    def profile(self, name: str) -> list[str]:
        """Component ids in the profile (ids missing from the catalog are dropped)."""
        known = set(self.all_ids())
        return [i for i in self.profiles.get(name, []) if i in known]

    def required_ids(self) -> list[str]:
        return [c.id for cat in self.categories if cat.required for c in cat.components]

    def primary_vars(self, selected: list[str]) -> dict[str, str]:
        """Picks the primary tool for single-select categories (e.g. TERMINAL=kitty)."""
        result: dict[str, str] = {}
        for cat in self.categories:
            if not cat.var:
                continue
            for comp in cat.components:
                if comp.id in selected:
                    result[cat.var] = comp.id
                    break
        return result
