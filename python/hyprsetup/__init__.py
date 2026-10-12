"""Souprland (package name: hyprsetup) — the Python side of the Hyprland installer.

It does two jobs:

* ``tui``    — interactive curses UI for picking components; writes the result to a
               file that bash can source.
* ``render`` — processes the templates under ``templates/`` according to the selection
               and settings, producing config files ready to install.

The bash side calls this module as ``python3 -m hyprsetup <subcommand>``.
"""

__version__ = "2.0.0"
