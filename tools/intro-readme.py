#!/usr/bin/env python3
"""Generates the intro section of README.md from assets/intro/pages.json.

    python3 tools/intro-readme.py          # update
    python3 tools/intro-readme.py --check  # check only (exit 1 = stale)
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))

from hyprsetup import intro  # noqa: E402

README = "README.md"


def main() -> int:
    check = "--check" in sys.argv[1:]
    pages = intro.load(ROOT)
    if not pages:
        print("assets/intro/pages.json could not be read or is empty", file=sys.stderr)
        return 1
    fresh = intro.sync_readme(ROOT / README, pages, check=check)
    if check and not fresh:
        print(f"out of date: {README} — python3 tools/intro-readme.py", file=sys.stderr)
        return 1
    if not fresh:
        print(f"updated: {README}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
