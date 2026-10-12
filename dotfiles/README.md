# Pre-generated dotfiles

**There are no trees for the current profiles.**

Each folder here holds the configuration files **generated** by
`tools/build-dotfiles.sh` from the profile of the same name under
`presets/profile/` — so it is not a source of its own, it is the output of the
profile system.

Profiles now install the setups from Reddit posts **with the authors' own
files** (`python3 -m hyprsetup rice install <name>`; see
`docs/preset-sources.md`). Since there is nothing to generate from this
project's templates, `build-dotfiles.sh` skips those profiles (the ones with a
`<name>.rice.toml`). If a template-based profile is added, its tree is again
one command away:

```bash
./tools/build-dotfiles.sh          # presets/profile/*.conf → dotfiles/<name>/
```

Which rice the old sets were based on, which palette they used and what they
looked like is not lost:

* `docs/gallery-catalog.md` — source, palette and layout notes for the OLD profiles
* `docs/preview.html` — visual preview
* `wallpapers/` — the wallpapers the profiles use
* `python/hyprsetup/themes.py` — every color palette (none were removed)

Once the sets are generated, they can be installed without ever running the
installer:

```bash
./install-dotfiles.sh                  # list the sets
./install-dotfiles.sh nord-frost             # install the nord files under ~/.config
./install-dotfiles.sh nord-frost --packages  # also install the programs they need
./install-dotfiles.sh nord-frost -n          # show what it would do first
```

Your existing files are backed up under
`~/.config/hyprsetup-backups/<date-time>/`. `~/.config/hypr/custom.conf` is
created if missing and left alone if it exists.
