"""Intro tour pages — a single source for the app and the README.

The pages live in ``assets/intro/pages.json``: a title, body text and a
GIF/video. The settings app shows them as a step-by-step tour on first launch
(gui/welcome.py:IntroTour); the intro section of README.md is generated from
the same file (``sync_readme``), so the two never drift apart. After editing
the text:

    python3 tools/intro-readme.py          # update the README
    python3 tools/intro-readme.py --check  # is it up to date (tools/test.sh)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

PAGES_FILE = Path("assets/intro/pages.json")

#: Boundaries of the generated README section; nothing between them should be
#: edited by hand.
START = "<!-- intro:start — generated from assets/intro/pages.json, do not edit by hand -->"
END = "<!-- intro:end -->"
#: Start markers still recognized when reading a README; the section is
#: rewritten with ``START``. Legacy Turkish marker from pre-English READMEs.
LEGACY_STARTS = (
    "<!-- intro:start — assets/intro/pages.json'dan üretilir, elle düzenlemeyin -->",
)


@dataclass
class Page:
    id: str
    title: str
    body: list[str]
    media: str = ""
    draft: bool = False
    #: The credits for the bundled themes are appended to the body
    #: (``credit_lines``; generated from the manifests, never written by hand).
    credits: bool = False

    def media_path(self, root: Path) -> Path | None:
        if not self.media:
            return None
        return Path(root) / PAGES_FILE.parent / self.media


def load(root: Path) -> list[Page]:
    path = Path(root) / PAGES_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    pages = []
    for raw in data.get("pages", []):
        if not raw.get("id") or not raw.get("title"):
            continue
        pages.append(Page(
            id=str(raw["id"]), title=str(raw["title"]),
            body=[str(line) for line in raw.get("body", [])],
            media=str(raw.get("media", "")),
            draft=bool(raw.get("draft", False)),
            credits=bool(raw.get("credits", False))))
    return pages


def credit_lines(root: Path) -> list[str]:
    """Sources of the bundled profiles, one bullet per repository.

    "- [owner/repo](url) – what is used (license)". The main repository is the
    manifest's ``[source]``, extra ones are ``[[install]] repo`` entries;
    profiles using the same repository are merged into one bullet. Setups
    imported by link belong to the user and are not listed.
    """
    from . import presets, rice

    root = Path(root)
    profile_dir = presets.default_dir(root, "profile")
    # repository url → [license, is main repo, profile names]
    repos: dict[str, list] = {}

    def add(url: str, license_: str, main: bool, title: str) -> None:
        entry = repos.setdefault(url, [license_, main, []])
        entry[0] = entry[0] or license_
        entry[1] = entry[1] or main
        if title not in entry[2]:
            entry[2].append(title)

    for name in rice.all_profiles(root):
        if rice.is_imported(root, name):
            continue
        try:
            manifest = rice.load(root, name)
        except (OSError, ValueError, KeyError):
            continue
        preset = presets.find(profile_dir, name)
        title = ((preset.title if preset else "") or name).split(" — ")[0]
        add(manifest.repo, manifest.license, True, title)
        for item in manifest.installs:
            if item.repo and item.repo != manifest.repo:
                add(item.repo, item.license, False, title)

    out = []
    for url, (license_, main, titles) in sorted(
            repos.items(), key=lambda kv: kv[0].lower()):
        slug = url.removeprefix("https://github.com/").rstrip("/")
        names = ", ".join(titles)
        what = (f"dotfiles for the {names} profile" if main
                else f"used by the {names} profile")
        lic = license_ or "no license stated"
        out.append(f"- [{slug}]({url}) – {what} ({lic})")
    return out


def body_of(root: Path, page: Page) -> list[str]:
    """The page body as displayed (credits included)."""
    body = page.body
    if page.credits:
        body = list(body) + credit_lines(root)
    return body


def _markdown(root: Path, pages: list[Page]) -> str:
    out = [START, ""]
    for page in pages:
        title = page.title
        body = body_of(root, page)
        out.append(f"### {title}")
        out.append("")
        if page.media:
            out.append(f"![{title}]({PAGES_FILE.parent.as_posix()}/{page.media})")
            out.append("")
        bullets = False
        for line in body:
            if line.startswith("### "):
                # The page title is already ###; a subheading goes one level down.
                if bullets:
                    out.append("")
                    bullets = False
                out.append("#" + line)
                out.append("")
                continue
            if line.startswith("- "):
                out.append(line)
                bullets = True
                continue
            if bullets:
                out.append("")
                bullets = False
            out.append(line)
            out.append("")
        if bullets:
            out.append("")
    out.append(END)
    return "\n".join(out)


def sync_readme(path: Path, pages: list[Page], check: bool = False) -> bool:
    """Regenerates the README section. Returns whether the file was up to date.

    Without the boundary markers the section is inserted after the first
    ``---`` separator (right after the header blurb).
    """
    text = path.read_text(encoding="utf-8")
    section = _markdown(path.parent, pages)
    start = next((marker for marker in (START, *LEGACY_STARTS) if marker in text), None)
    if start is not None and END in text:
        head, rest = text.split(start, 1)
        _old, tail = rest.split(END, 1)
        new = head + section + tail
    else:
        heading = "## At a glance"
        block = f"{heading}\n\n{section}\n\n---\n\n"
        marker = "\n---\n"
        index = text.find(marker)
        new = (text[:index + len(marker)] + "\n" + block + text[index + len(marker):].lstrip("\n")
               if index >= 0 else text + "\n" + block)
    if new == text:
        return True
    if not check:
        path.write_text(new, encoding="utf-8")
    return False
