<p align="center">
  <img src="assets/souprland-wordmark.svg" alt="Souprland" width="520">
</p>

# Souprland

**A Hyprland desktop for Arch Linux / CachyOS: one install, then a settings app.**
An installer that sets up Hyprland and the whole desktop ecosystem from
scratch — **and a settings app that takes over after installation.**

- **`./install.sh`** runs once, asks a single question ("start the
  installation?") and sets up the desktop.
- **`SUPER + I`** (or `souprland`) does everything after that: theme, gaps,
  bar, keybindings, displays. Changes are applied **instantly**; you never
  need to re-run the installer.

80 palettes &nbsp;·&nbsp; 49 profiles &nbsp;·&nbsp; 66 bar layouts &nbsp;·&nbsp; 15 desktop widgets &nbsp;·&nbsp; MIT

Built with:

- **Bash** — orchestration, package installation, system integration
- **Python** — the template engine and the GTK4/libadwaita settings app
- **No external dependencies** — just `bash`, `python3` (stdlib), `jq`, `pacman`
  (plus `gtk4 libadwaita python-gobject python-cairo` for the settings app)

Target version: **Hyprland 0.50+** (tested on 0.56). The keybinding layout is
aligned with [end-4/dots-hyprland](https://github.com/end-4/dots-hyprland), and
the not-yet-released **Hyprland 0.57 (Lua config)** is supported too — see
[Configuration language: .conf or Lua?](#configuration-language-conf-or-lua).

---

## At a glance

<!-- intro:start — generated from assets/intro/pages.json, do not edit by hand -->

### What is Souprland?

![What is Souprland?](assets/intro/genel.gif)

An installer that sets up a Hyprland desktop from scratch, and a settings app that takes over after installation.

- Theme, bar, terminal, launcher, keybinds: all from this window, applied instantly.
- Ready-made desktops install in one click and can be rolled back.
- Your keybinds and ALT+Tab stay the same on every theme.

### This Project Is Made With AI And Can Be Buggy As Hell

![This Project Is Made With AI And Can Be Buggy As Hell](assets/intro/merhaba.gif)

Souprland is basically a script that controls Hyprland with a GUI.

- You can use ready-made dotfiles,
- make your own with the setup wizard,
- or mix dotfiles together with Soup Maker.

If you see any bug, please open an issue on GitHub. I'll do my best to fix it.

### No bloat

![No bloat](assets/intro/sisman.gif)

By default you only get what a desktop needs. No AUR, no extras.

Want more? You choose it, nothing gets installed behind your back.

The repo is a bit big (~100 MB) because of the themes and wallpapers inside, but they just sit there until you use them.

### Security

![Security](assets/intro/guvenlik.gif)

There are dotfiles using AUR packages, and some features also need AUR. It is up to you to choose whether to use them or not. All settings and dotfiles that use AUR can be seen in the GUI.

#### AUR packages

As always with AUR, review PKGBUILDs before installing.

#### Third-party dotfiles

Some dotfiles include configs and scripts from other authors. So review them before use.

### Credits

Thanks to the authors whose dotfiles and scripts are used in this project:

- [0xbbuddha/dotfiles_nothing_os](https://github.com/0xbbuddha/dotfiles_nothing_os) – dotfiles for the NothingOS profile (MIT)
- [ad1822/hyprdots](https://github.com/ad1822/hyprdots) – dotfiles for the ad1822 profile (MIT)
- [arfan-on-clouds/hyprclouds](https://github.com/arfan-on-clouds/hyprclouds) – dotfiles for the hyprclouds profile (no license stated)
- [Brainitech/Brain_Shell](https://github.com/Brainitech/Brain_Shell) – dotfiles for the Brain Shell profile (MIT)
- [caelestia-dots/caelestia](https://github.com/caelestia-dots/caelestia) – used by the Caelestia profile (no license stated)
- [caelestia-dots/cli](https://github.com/caelestia-dots/cli) – used by the Caelestia profile (no license stated)
- [caelestia-dots/shell](https://github.com/caelestia-dots/shell) – dotfiles for the Caelestia profile (GPL-3.0)
- [dhrruvsharma/shell](https://github.com/dhrruvsharma/shell) – dotfiles for the dhruvsharma profile (no license stated)
- [end-4/dots-hyprland](https://github.com/end-4/dots-hyprland) – dotfiles for the end-4 profile (GPL-3.0)
- [end-4/google-sans-flex](https://github.com/end-4/google-sans-flex) – used by the end-4 profile (OFL-1.1)
- [end-4/rounded-polygon-qmljs](https://github.com/end-4/rounded-polygon-qmljs) – used by the end-4 profile (Apache-2.0)
- [haikal-hakim/athena-eww](https://github.com/haikal-hakim/athena-eww) – dotfiles for the Athena profile (MIT)
- [ilyamiro/hypr-comp](https://github.com/ilyamiro/hypr-comp) – used by the ilyamiro profile (no license stated)
- [ilyamiro/imperative-dots](https://github.com/ilyamiro/imperative-dots) – dotfiles for the ilyamiro profile (no license stated)
- [ilyamiro/serpantinum](https://github.com/ilyamiro/serpantinum) – dotfiles for the Serpantinum profile (AGPL-3.0)
- [k4ditano/k4](https://github.com/k4ditano/k4) – dotfiles for the k4 profile (MIT)
- [kianblakley/pibble](https://github.com/kianblakley/pibble) – dotfiles for the pibble profile (GPL-3.0)
- [r4ppz19/Arch-dotfiles](https://github.com/r4ppz19/Arch-dotfiles) – dotfiles for the r4ppz19 profile (MIT)
- [saatvik333/hyprland-dotfiles](https://github.com/saatvik333/hyprland-dotfiles) – dotfiles for the saatvik333 profile (no license stated)
- [samyns/Unit-3](https://github.com/samyns/Unit-3) – dotfiles for the Unit-3 profile (MIT)
- [simeulinuxkaliaiwr/vantage](https://github.com/simeulinuxkaliaiwr/vantage) – dotfiles for the Vantage profile (MIT)
- [zephardev/hyprcraft](https://github.com/zephardev/hyprcraft) – dotfiles for the HyprCraft profile (MIT)

<!-- intro:end -->

---

## Quick start

```bash
git clone --depth 1 https://github.com/KaNEX-01/souprland.git
cd souprland
./install.sh
```

`--depth 1` skips the history and keeps the download small. Requirements: Arch
Linux or CachyOS, a normal user with `sudo` (not root), and `git`
(`sudo pacman -S git`). To update later, run `./install.sh` again in the same
folder: it pulls the new version first.

That is the whole installation. It installs packages, generates every config
file, enables services and installs the settings app under `~/.local`. **It
asks nothing** — only a single confirmation before it starts.

To see what it would do first (touches nothing, asks nothing):

```bash
./install.sh --dry-run
```

When it finishes:

```
SUPER + I        or        souprland
```

Out of the box the desktop is generated from this project's own templates:
one palette flows into **every** application at once — Hyprland borders,
Waybar, your terminal, the launcher, notifications, GTK, Qt, the lock screen,
the login screen and (optionally) Firefox, Discord and Spotify. Nothing is
overwritten without a backup, and every run is idempotent.

---

## After installing: the settings app

At the end, `install.sh` **installs the settings app** on the system:

```
~/.local/bin/souprland                  executable (hyprsetup = symlink)
~/.local/share/hyprsetup/{python,templates,config,presets,wallpapers,assets}
~/.local/share/applications/souprland.desktop
~/.local/share/icons/hicolor/scalable/apps/souprland.svg
```

So **you can delete the cloned repository**; `SUPER + I` keeps working. (This
used to be different: the keybinding called `hyprsetup-gui` straight from the
repository, and settings died for anyone who moved the repo.)

> **Name:** the project is called **Souprland**. Internally — the Python
> package (`python3 -m hyprsetup`), `~/.config/hyprsetup`, window classes and
> systemd units — it deliberately keeps its original `hyprsetup` name so
> existing installs keep working. The `hyprsetup` command stays available as
> an alias of `souprland`.

When `SUPER + I` is pressed, `~/.config/hypr/scripts/settings.sh` tries, in
order: `~/.local/bin/hyprsetup --quick` → `hyprsetup --quick` on PATH →
[hyprmod](https://github.com/mylinuxforwork/hyprland-settings) →
[better-control](https://github.com/better-control/better-control) →
[nwg-displays](https://github.com/nwg-piotr/nwg-displays); if none exists, it
warns with a notification.

### The `SUPER + I` panel

`SUPER + I` opens **the settings app itself** — as a floating window that
slides down from the top of the screen. There is no separate "quick"
interface: tabs on the left, the selected page on the right. So the panel has
**everything** the app has — all 289 schema settings, the bar/terminal/launcher
preset galleries, the color editor, keybinding capture, display detection,
component selection and the live previews. The panel opens on the
**Appearance** page (whoever presses `SUPER + I` almost always wants the
theme, gaps or blur); `Esc` closes it.

```
                       ↓ slides down from the top of the screen
┌────────────────────┬─────────────────────────────────────────────────────┐
│ Souprland          │                  Appearance                  ─ □ ✕  │
├────────────────────┼─────────────────────────────────────────────────────┤
│  Home              │ SYSTEM COLOR                   ╭──────────────╮     │
│  Setup Wizard      │  ( ) Dark  ( ) Light           │ live         │     │
│  Profiles          │                                │ preview      │     │
│  Soup Maker        │ THEME                          │              │     │
│▸ Appearance        │  (•) catppuccin-mocha  ▪▪▪▪▪   │  ┌────┬────┐ │     │
│  Wallpaper Colors  │  ( ) tokyo-night       ▪▪▪▪▪   │  │    │    │ │     │
│  Wallpaper Engine  │                                │  └────┴────┘ │     │
│  Bar Presets       │ LAYOUT                         ╰──────────────╯     │
│  Status Bar        │  Gaps in       ──●─────────  5px                    │
│  Terminal          │  Gaps out      ────●───────  12px                   │
│  Launcher          │  Rounding      ───●────────  10px                   │
│  Widgets           │  Border        ─●──────────  2px                    │
│  Behavior          │                                                     │
│  Mouse Cursor      │ DECORATION                                          │
│  Window Rules      │  Blur                [ ●]   Shadow        [ ●]      │
│  Session           │  Blur size     ──●──────────────────  6             │
│  Login Screen      │                                                     │
│  Keybindings       │ ANIMATION                                           │
│  Applications      │  Preset        default ▾                            │
│  Autostart         │  Speed         ────●───────  1.0                    │
│  Components        │                                                     │
│  Displays          │                                                     │
│  System            │                                                     │
│                    │                                                     │
│Theme: catppuccin   │                                                     │
│waybar · kitty      │                                                     │
│Up to date          │                                                     │
└────────────────────┴─────────────────────────────────────────────────────┘
```

(In simple mode, Soup Maker, Bar Presets, Terminal, Launcher, Widgets, Login
Screen, Components and System are hidden from the sidebar; switch to advanced
mode to see them.)

There used to be a separate four-slider "Quick Settings" window here, and
most of what you were looking for was not in it; instead an "All settings…"
button opened a second window. Now it is one window, one code path
(`gui/app.py`), one `settings.conf`.

**Floating, position and slide-in** come from four window rules (in the
generated `windowrules.conf`):

```
windowrule = float on,            match:class ^(dev\.hyprsetup\.Quick)$
windowrule = size 80% 80%,        match:class ^(dev\.hyprsetup\.Quick)$
windowrule = move 10% 58,         match:class ^(dev\.hyprsetup\.Quick)$
windowrule = animation slide,     match:class ^(dev\.hyprsetup\.Quick)$
```

The size is **a percentage of the screen** (`render.py:QUICK_PANEL_WIDTH_PCT` /
`..._HEIGHT_PCT`): it comes out in the same proportion on a 1366×768 laptop
and on 4K, where a fixed pixel box would either look tiny or overflow. The GTK
window does the same calculation (`render.quick_panel_pixels`); otherwise the
panel would first open at its own size, get resized by Hyprland right after,
and jump. The vertical position is not fixed: `render.py:_quick_panel_vars`
computes the panel's `y` from your `BAR_POSITION` / `BAR_HEIGHT` /
`BAR_MARGIN`, so with the bar at the top the panel starts **below** it, and
with the bar at the bottom it sits at the top of the screen. The parameter of
`animation slide` is a percentage (`slide 70%`), not a direction — Hyprland
derives the slide direction from the window position, and since the panel
sits at the top it comes down from above.

The window class differs on purpose: the panel opened with `SUPER + I` is
`dev.hyprsetup.Quick`, the window opened from the application menu or with
`souprland` on the command line is `dev.hyprsetup.Gui`. The rules match both,
so the full app also floats above your windows and slides in from the top.
The panel additionally opens on the Appearance page and closes with Esc. Both
are the same app and write the same file.

If you want the app as a normal tiled window, add a `tile on` rule for the
`dev.hyprsetup.Gui` / `dev.hyprsetup.Quick` class via `WINDOWRULES`.

### How it works

> `HYPR_LANG="auto"` (the default) is resolved in the settings app too: the
> installed Hyprland version decides between `conf` and `lua`. If it were not
> resolved, the hypr templates' condition (`HYPR_LANG==conf`) would not match
> and **no Hyprland configuration would be generated** — window borders,
> shadows and corner colors would stay on the old theme while
> waybar/kitty/GTK were refreshed.
>
> Applying a profile refreshes not only the files under `~/.config` but also
> the **wallpaper** (the profile's image is copied to `WALLPAPER_PATH` —
> `THEME="auto"` derives its palette from this file) and the **Firefox theme**
> (the generated `userChrome.css` goes into the `chrome/` directory of every
> Firefox profile). Both used to happen only in `install.sh`; anyone changing
> the theme from the settings app kept the old wallpaper, and `auto` palettes
> fell back to the default colors.

The app reads and writes `~/.config/hyprsetup/settings.conf`. When you change
a setting:

1. only the templates affected by that setting are regenerated,
2. only files whose **content actually changed** are written to disk,
3. only the daemons that depend on those files are reloaded (`hyprctl reload`,
   `pkill -SIGUSR1 waybar`, `makoctl reload`…).

An unchanged file is not rewritten — otherwise every "apply" round would
needlessly restart every daemon.

### The settings app does NOT install packages

A deliberate decision: moving a slider should not ask for a root password. An
option that is not installed (e.g. a different status bar) is greyed out in
the app, with the required `pacman` command next to it. If you want it, you
run the command yourself.

Profiles are the one place where it helps: applying a profile first checks
the programs that profile needs (its bar backend, and a widget engine if it
ships widgets) and, if one is missing, offers **Install and apply** — which
opens **your terminal** and runs `pacman` / `paru` there, where you see the
command and type the password.

### Pages

| Page | Contents |
|---|---|
| **Home** | Scope switches (`MANAGE_HYPR_CONFIGS`, `MANAGE_MONITORS`) and overall status |
| **Setup Wizard** | Builds the desktop from scratch, step by step: window behavior, wallpaper, colors, window look, terminal, launcher, bar, notifications/lock and login screen — large choices and fine-tuning rows on the left, a large live preview on the right. "Try live on the desktop" applies each choice immediately; otherwise everything goes at once on "Finish", and "Cancel" restores the state from when the wizard opened |
| **Profiles** | 49 profiles: 18 complete desktops installed from their authors' own dotfiles (16 recreated from Reddit posts, plus end-4's illogical-impulse and hyprclouds), every look in the post (wallpaper included) a selectable variant; and 31 of the project's own (`st-*`), built from its templates |
| **Soup Maker** | Mixes parts of different profiles — see [Soup Maker](#soup-maker-mixing-profiles) |
| **Appearance** | **Live preview** + theme picker (with color swatches) + **color editor** + wallpaper, color tone, day / night theme, layout/decoration/animation sliders |
| **Wallpaper Colors** | ricemood-style: the wallpaper's colors (6 node-vibrant swatches, 11 roles, 16 terminal colors) are written into **any** program's file through `^r@Vibrant>lighten(0.2)^` tags or pywal templates; built-in templates: pywal compatibility (`~/.cache/wal`), Zathura, tmux. "Add template" turns your own config file into a template automatically. Re-applied on every wallpaper change, rotation included (`hyprsetup wallcolors`) |
| **Wallpaper Engine** | A preview gallery of your installed Steam Workshop wallpapers; click to play, a separate scene **per display** (`WPENGINE_PER_SCREEN`) |
| **Bar Presets** | 66 bar layouts; the chosen preset also determines the bar backend |
| **Status Bar** | Position, height, gaps, rounding, opacity, clock format + which zone each module sits in; custom bar modules; dock |
| **Terminal** / **Launcher** | Program-independent preset looks (6 terminal, 7 launcher) + individual settings |
| **Widgets** | Desktop widgets (eww / Quickshell) and the audio visualizer |
| **Behavior** | Behavior, window switcher, window groups, Hyprland plugins, input, gestures and environment settings |
| **Mouse Cursor** | Cursor theme, size and hiding |
| **Window Rules** | Pick an open window and mark it float / center / size / opacity / workspace / display; "Discord always on workspace 3" lives here. Written to `USER_WINDOWRULES`, kept across profile switches |
| **Session** | Idle and lock, lock screen, power menu, notifications, night light, screen recording and screenshots, game mode, desktop tools |
| **Login Screen** | Community SDDM themes (Astronaut, SilentSDDM, Catppuccin, Pixie…) installed and picked from a preview list; edit the preset look, *paint from my palette*, *my wallpaper* and every setting (colors, fonts, blur, clock format…), previewed in SDDM's test mode. For Plasma Login: clock, background and color scheme; switching SDDM ↔ Plasma Login. Edits go to `<ConfigFile>.user`, not the theme's own file, so package updates never overwrite them. Also the **boot animation** (Plymouth) |
| **Keybindings** | Every keyboard shortcut; click a key and press the new combination to rebind, with conflict warnings |
| **Applications** | Default terminal / file manager / launcher / browser |
| **Autostart** | Add installed apps (or a hand-written command) to session start (`EXTRA_EXEC_ONCE`) |
| **Components** | The multi-select components this tool configures (hyprsunset, swayosd, cava, wlogout, clipboard history, screen recording, matugen, hyprpm plugins, nwg-displays…) — on/off |
| **Displays** | Displays detected from `hyprctl` — copied into the settings in one click |
| **System** | Settings file path, backups, version info; **Update** (refreshes the installed copy from the repository, with `git pull --ff-only` when it is a clone; `souprland self-update`) and **Share my desktop** (look + wallpaper in a single `.tar.gz`; commands, locations and machine-specific settings never travel either way; `souprland share export\|import`) |
| **Search** | The box at the top left searches every setting by name, key and description; clicking a result opens the page and highlights the row |

### Desktop tools

- **Bar panel tabs** (left-click a bar module): per-app volume sliders in
  *Sound*; *Brightness* also drives external displays over DDC/CI
  (`ddcutil`) and toggles the night light; *Notifications* keeps this
  session's history (whatever the daemon, stored only in `$XDG_RUNTIME_DIR`)
  with a do-not-disturb switch; *Media* has Shazam-style song recognition
  (`songrec`).
- **Game mode** (`MOD+F12`, or automatically when a game goes fullscreen):
  animations/blur/shadows off, Wallpaper Engine paused, visualizer and sakura
  stopped, notifications silenced; everything comes back when you leave it.
- **Bar modules**: `custom/shazam`, `custom/gamemode`, `custom/notifications`,
  `custom/updates` (pending pacman + AUR updates, click to upgrade).
- **Day / night theme** (*Appearance*): switches between two palettes at set
  times (systemd user timer); GTK/Qt light/dark follows.
- **Snapshots**: before NVIDIA, Plymouth, login manager and login screen
  changes, a snapper/timeshift snapshot is taken when available
  (`SNAPSHOT_BEFORE_SYSTEM=auto`).
- All of this is adjustable in the settings app: *Session → Game mode* and
  *Session → Desktop tools* (song recognition length, notification history
  on/off and size, update check on/off/interval/AUR, external display
  brightness, per-app volume, installed-copy sync, snapshots).

### Live preview

The preview on the Appearance page draws the settings close to how Hyprland
really behaves: outer/inner gaps, border width and gradient angle, corner
rounding, **corner curve** (`rounding_power` — drawn as a superellipse),
shadow spread and sharpness, focused/background window opacity, dimming and
the tiling layout (dwindle / master). Move a slider and you see the result
instantly.

Every setting has a description line underneath explaining what it does.

### Settings schema

The app's widgets are generated automatically from the schema in
`python/hyprsetup/settings.py` — a new setting only needs a default in
`lib/config.sh` and a `Setting` entry in the schema; the GUI code does not
change.

To verify the two sides have not drifted apart:

```bash
python3 -m hyprsetup check-schema
```

To try it from the repository without installing anything: `./hyprsetup-gui`.

> **Warning:** `./hyprsetup-gui` also writes to your real `~/.config`. A copy
> of every overwritten file is kept under `~/.config/hyprsetup-backups/`.

---

## Usage

```bash
./install.sh [options]
```

| Option | Description |
|---|---|
| `-n, --dry-run` | Change nothing, only describe what would be done (asks nothing either) |
| `-y, --yes` | Do not ask for confirmation (for scripted use) |
| `-v, --verbose` | Detailed log |
| `--compile ask\|never\|always` | Whether AUR packages may be built on this machine |
| `--skip-pkg a,b` | Never install these packages (comma-separated) |
| `-c, --config <file>` | Start from a settings file (see `config/settings.conf.example`) |
| `--doctor` | Audit the installation: missing packages, disabled services, broken settings (read-only) |
| `--plymouth <theme>` | Run only the Plymouth step with that theme and exit (the Login Screen page calls this) |
| `--update` | Force update mode (already the default when installed) |
| `--reinstall` | Install from scratch even when installed; `settings.conf` goes back to defaults |
| `--no-fetch` | When updating, do not download a new version; use the one in this folder |
| `-V, --version` | Show the version |
| `-h, --help` | Help |

Profile selection, the component wizard (TUI), `--preset`, `--only/--skip`,
`--reapply`, `--set` and the `--list-*` options **no longer exist**: the
installer asks nothing any more, and the look is chosen in the settings app
after installation.

### Examples

```bash
./install.sh                              # default desktop
./install.sh --dry-run                    # show what it would do first
./install.sh -y --compile never           # no questions, no building from source
./install.sh --skip-pkg dolphin,sddm      # never touch these packages
./install.sh -c ~/backup/settings.conf    # install with saved settings
./install.sh --doctor                     # audit the installed system
```

---

## What gets installed

The components to install are a plain bash array at the top of `install.sh`:

```bash
DEFAULT_COMPONENTS=(
    hyprland portal polkit        # core: compositor, portal, authorization
    waybar                        # status bar
    kitty                         # terminal
    wofi                          # application launcher
    mako                          # notification daemon
    hyprpaper                     # wallpaper
    pipewire networkmanager       # audio, network
    clipboard screenshot-base
    fonts-base xdg-dirs
)
```

Edit it **before** installing. Valid ids are in
[`config/components.json`](config/components.json) — 83 components in
20 categories. The only automatic addition is the GPU driver: the `nvidia`
component is added when an NVIDIA card is detected, because installing the
wrong driver can leave you with a black screen.

Since the settings app installs no packages, a program you leave out here has
to be installed by hand later (`sudo pacman -S <package>`); only then can it
be selected in the app. Review the list once, up front.

| Category | Options |
|---|---|
| **Bar** | Waybar · HyprPanel · Quickshell · Wayle |
| **Widgets** | eww · Quickshell |
| **Terminal** | Kitty · Alacritty · foot · Ghostty · WezTerm |
| **Launcher** | wofi · rofi · fuzzel · walker · tofi |
| **Notifications** | mako · dunst · SwayNotificationCenter |
| **Wallpaper** | hyprpaper · swww · waypaper · linux-wallpaperengine |
| **Files** | Dolphin · Thunar · Nautilus · Nemo · Yazi |
| **Login screen** | SDDM · ly · greetd |
| **Session** | hyprlock · hypridle · wlogout |
| **Screen** | grim/slurp · swappy · gpu-screen-recorder (instant replay) |
| **Feedback** | SwayOSD volume/brightness indicator · cava visualizer |
| **Shaders** | hyprshade — blue light, vibrance, grayscale, CRT |
| **Boot** | Plymouth *(opt-in — touches the initramfs)* |
| **Plugins** | hyprexpo · hy3 · hyprbars · borders-plus-plus · hyprtrails *(opt-in)* |
| **App themes** | Firefox userChrome · Discord (Vencord) · Spotify (spicetify) |

### Deliberately not in the defaults

Two groups are **not** in the default list, because they can break in ways
that are hard to trace:

- **hyprpm plugins** must be recompiled after every Hyprland update. If the
  build fails, Hyprland starts without them — your layout engine or window
  titles silently disappear. `--doctor` reports this.
- **Plymouth** modifies the initramfs and the kernel command line. Its theme
  can be changed later under *Login Screen → Boot animation*; the page runs
  `./install.sh --plymouth <theme>` in a terminal. The same place has an
  animated preview gallery, 84 community themes (adi1090x, Catppuccin;
  installed from AUR) and a *My theme* tab that builds a theme from your own
  logo or GIF.

---

## Health check

`--doctor` changes nothing; it checks the following and tells you what to do:

- Is Hyprland running, and what does `hyprctl configerrors` say
- Are the generated files in place (including `custom.conf`/`custom.lua` —
  Hyprland errors out without it)
- Which configuration language (`HYPR_LANG`) was resolved, and the installed
  Hyprland version
- Are the packages of the installed components in place (the list is read
  from the `COMPONENTS` line in `settings.conf`)
- NetworkManager/bluetooth/pipewire/polkit services
- Portal configuration and process for screen sharing
- Font, cursor theme, wallpaper, the `hyprlock` PAM rule
- Conflicting keybindings

If there are errors the exit code is 1, so you can call it from scripts.

---

## Configuration language: .conf or Lua?

In Hyprland's main repository, the old hyprlang `.conf` parser was removed
entirely on the **`main`** branch heading to 0.57 (2026-07-22,
[`config: remove legacy config support` (PR #15539)](https://github.com/hyprwm/Hyprland/pull/15539)) —
from then on only **Lua** configuration (`hyprland.lua`) is supported. The
change is not in an official release yet (latest released: **v0.56.1**,
2026-07-27), but it will affect anyone running a dev/main build such as
`hyprland-git`, and everyone who updates once 0.57 is out.

The installer handles this with the **`HYPR_LANG`** setting:

| Value | Behavior |
|---|---|
| `auto` (default) | Looks at the installed Hyprland version: `< 0.57` → `.conf`, `>= 0.57` or `hyprland-git` → Lua |
| `conf` | Always generate classic `.conf` |
| `lua` | Always generate Lua (experimental — see below) |

When left at `auto`, it is written to `settings.conf` as `auto` rather than
the detected result — so the next generation detects again after you upgrade
Hyprland.

Files generated in Lua mode: `~/.config/hypr/hyprland.lua` and
`~/.config/hypr/hyprland/{monitors,workspaces,env,autostart,keybinds,windowrules}.lua`
(the same split as conf mode, just with the `hl.config()` / `hl.bind()` /
`hl.monitor()` / `hl.window_rule()` API). For your personal additions,
**`custom.lua`** is used instead of `custom.conf`. `hyprlock.conf` /
`hypridle.conf` / `hyprpaper.conf` do not change — those are separate
projects from the Hyprland core, and the legacy-config removal does not
affect them.

**Use it knowing it is experimental:** these templates were written against
Hyprland's not-yet-released Lua API (with `example/hyprland.lua` on the
`hyprwm/Hyprland` `main` branch and `end-4/dots-hyprland`'s own Lua config as
references, as of 2026-07-28); small API differences may show up when 0.57 is
actually released. If you run into problems, `./install.sh --doctor` checks
`hyprctl configerrors` first; for a lasting fix, check
[the Lua configuration page on the wiki](https://wiki.hypr.land/Configuring/Start/).

---

## Choosing a look

The axes are independent and can be combined freely — all from the settings
app.

| Axis | Where | What it controls |
|---|---|---|
| Palette | *Appearance → Theme* | 80 palettes, or `auto` from the wallpaper |
| Profile | *Profiles* | 49 profiles: 18 real setups (the author's files + the looks from the post) and 31 of the project's own (`st-*`) |
| Soup Maker | *Soup Maker* | parts from different profiles: wallpaper, color scheme, window look, bar, launcher, notifications, terminal, lock screen, desktop widgets |
| Wallpaper colors | *Wallpaper Colors* | the wallpaper's colors written into any program's config (see [Pages](#pages)) |
| Bar | *Bar Presets* | 66 bar layouts — each works with any palette |
| Terminal | *Terminal* | 6 looks: opacity, padding, cursor, scrollback. Plus a **startup screen** (fastfetch: distro logo, the Souprland logo or your own picture — a real image in kitty/Ghostty/WezTerm, or drawn with braille dots ⣿, blocks or letters in any terminal; in color or a single color) and a **background picture** with dimming (kitty, Ghostty, WezTerm) |
| Launcher | *Launcher* | 7 looks: width, rows, position, icons |
| Animation | *Appearance* | `default` · `snappy` · `fluid` · `minimal` · `none` (plus `custom`, set by Soup Maker) |
| Widgets | *Widgets* | 15 desktop widgets (eww / Quickshell) |
| Login screen | *Login Screen* | community SDDM themes and Plasma Login (see [Pages](#pages)) |
| Animated wallpaper | *Wallpaper Engine* | your Steam Workshop wallpapers, a scene **per display** (`WPENGINE_PER_SCREEN`) |
| Day / night | *Appearance → Day / night theme* | switches between a day and a night palette at set times; GTK/Qt light/dark follows |

The terminal and launcher looks (`presets/terminal/`, `presets/launcher/`) are
program-independent: the same opacity/padding/cursor values are translated for
kitty, foot, Alacritty, Ghostty and WezTerm, and the same width/rows/icon
values for wofi, rofi, fuzzel, walker and tofi. A setting with no equivalent
is silently skipped.

The preset files are plain config fragments (`presets/bar/`,
`presets/terminal/`, `presets/launcher/`, `presets/widget/`); the `# title:`
and `# desc:` lines in their header are the name and description shown in the
app.

> [!IMPORTANT]
> **Our own profiles.** The 31 profiles we designed ourselves
> (`presets/profile/st-*.conf`) sit in *Profiles* next to the 18 author
> setups. They are installed only with this project's templates: their own
> palettes, bar presets and generated wallpapers
> (`tools/script-test-wallpapers.py`). Each one also picks its own bar
> engine, launcher, terminal, notification daemon and widget set
> (`TERMINAL=`, `LAUNCHER=`, `NOTIFIER=`, `WIDGET_ENGINE=` in the profile).
> Seventeen of them are adaptations of reference screenshots (kept in a
> `temaornek/` folder that is not part of the repository): the look is
> rebuilt with our own palette, bar CSS and a procedurally drawn wallpaper —
> no image is copied from the references.

> **The author profiles are real setups.** Each of the 18 author profiles
> installs **the author's own dotfiles** instead of imitating them with this
> project's templates. Sixteen recreate a Reddit post (r/hyprland and
> r/unixporn) as faithfully as possible, from the commit closest to the post
> date; `end4` is end-4's illogical-impulse, the most-starred Hyprland setup
> on GitHub; and `hyprclouds` is a GitHub repository (eww, Material You colors
> from the wallpaper). When a post shows more than one look (e.g. a video
> switching wallpapers), each one is a separate *variant* with its own
> wallpaper.
>
> ```bash
> python3 -m hyprsetup rice list                  # profiles and their variants
> python3 -m hyprsetup rice install caelestia --variant raiden
> python3 -m hyprsetup rice variant caelestia --variant room   # switch variant later
> python3 -m hyprsetup rice uninstall             # restore the previous state
> ```
>
> The authors' files ship with the project as archives of the pinned commit
> (`vendor/rices/`, only the installed paths, no history) — installing needs
> no network. Archives of repositories without a stated license are built
> locally with `python3 -m hyprsetup rice vendor` but kept out of git; on
> another machine those are fetched from the author's repository. Wallpapers
> are always fetched from their public source, at a pinned version. The
> authors' install scripts are never run; the user-level steps they perform
> are written out one by one in the manifest
> (`presets/profile/<name>.rice.toml`) with a reason for each, and
> system-wide steps (sudo, display manager, telemetry) are left out. Old
> configs are converted to Hyprland 0.56 / hyprpaper 0.8 syntax during
> install, and every manifest passes Hyprland's own validator
> (`python3 -m hyprsetup rice verify <name>`). Everything replaced is backed
> up and comes back on uninstall.
>
> [`docs/preset-sources.md`](docs/preset-sources.md) lists every profile's
> post, repository and commit, and where every variant's wallpaper comes from
> (wallpapers were found for 36 of the 49 variants; the rest were deleted by
> their authors or are private commissions). The old palette-based profiles
> are archived under `docs/archive/profiles-v2/`.

### Soup Maker: mixing profiles

Instead of installing a profile whole, you can pick its parts separately: one
profile's wallpaper, another's colors, a third one's bar. Your own
configuration always stays the base. Your keybindings, keyboard layout and
ALT+Tab never change; only the program a key opens does (e.g. tapping SUPER
opens another setup's launcher).

| Slot | From | How it is applied |
|---|---|---|
| Wallpaper | the profiles' variants | `WALLPAPER_PATH`; the first frame of videos |
| Color scheme | the profiles' variants, or the chosen wallpaper | a theme name, or the extracted palette (`CUSTOM_COLORS`) |
| Window look | the author's Hyprland files (`.conf` and Lua) | gaps, border, rounding, opacity, blur, shadow; animations with their exact curves (`ANIMATION_PRESET=custom`) |
| Bar, launcher, notifications, terminal, lock screen, widgets | the `[[part]]` tables in the manifest | the author's files are installed (with backups) and recolored to your color scheme |

```bash
python3 -m hyprsetup mix list                       # every part
python3 -m hyprsetup mix set wallpaper=caelestia/violet colors=r4ppz19/kiz \
        look=nothingos bar=ad1822/bar launcher=r4ppz19/launcher
python3 -m hyprsetup mix save evening               # store under a name; mix load evening
python3 -m hyprsetup mix clear                      # everything back to how it was
```

Quickshell shells can be split too: vantage's shell is offered as separate
bar, launcher and desktop widget parts. `shell.qml` is rewritten with only the
selected components. The parts catalog (`presets/mix/parts.json`) is generated
from the authors' files with `python3 -m hyprsetup mix scan`.

### Adding a setup by link

A dotfiles repository that is not in the list can be added by its link
(*Profiles → Add by link*, or the command line):

```bash
python3 -m hyprsetup rice import https://github.com/JaKooLit/Hyprland-Dots --dry-run  # report only
python3 -m hyprsetup rice import JaKooLit/Hyprland-Dots        # write the manifest
python3 -m hyprsetup rice install jakoolit-hyprland            # install (with backups, reversible)
python3 -m hyprsetup rice forget jakoolit-hyprland             # remove from the list
```

The repository is pinned to its current commit and its layout is recognized:
a `.config/` copy, GNU stow packages, folders next to `hypr/`, a `config/`
folder, a Quickshell-only shell. Repositories the author expects to live
somewhere like `~/Arch-dotfiles` are installed there and linked;
`/home/<author>/` paths are rewritten to your home directory. Shell and
editor configs (fish, zsh, nvim) and unrecognized folders go into optional
groups. A report is shown before installing: what goes where, which commands
run at login (lines that ask for root, run a script from the internet or
delete files are flagged), which packages are needed, and whether Hyprland's
validation passed. The author's install script is never run. Imported setups
live under `~/.config/hyprsetup/imported/` and can be picked part by part on
the Soup Maker page too.

### Precedence

```
your --config file  >  bar/terminal/launcher preset  >  lib/config.sh defaults
```

A preset only fills in the settings **you did not specify**; no value in your
own `settings.conf` is overridden by a preset.

---

## Screenshots

> **These need to be captured on a running system.** The repository ships
> generated wallpapers and a mockup gallery, but no real screenshots yet.
>
> To regenerate the mockup gallery: `./tools/preview.sh` → `docs/preview.html`

| | | |
|---|---|---|
| ![tokyo-night](wallpapers/tokyo-night.png) | ![gruvbox-dark](wallpapers/gruvbox-dark.png) | ![nord](wallpapers/nord.png) |
| `tokyo-night` | `gruvbox-dark` | `nord` |
| ![catppuccin-mocha](wallpapers/catppuccin-mocha.png) | ![rose-pine](wallpapers/rose-pine.png) | ![everforest-dark](wallpapers/everforest-dark.png) |
| `catppuccin-mocha` | `rose-pine` | `everforest-dark` |

These wallpapers are generated from each palette's own colors — the reference
rices they are inspired by use copyrighted art that cannot be redistributed,
so each image is drawn from the palette instead
(see [`docs/gallery-catalog.md`](docs/gallery-catalog.md)).

---

## Pre-generated dotfiles (script-free use)

> [!NOTE]
> There are **no** `dotfiles/` trees for the current profiles: profiles now
> install their authors' own files (`python3 -m hyprsetup rice install`), so
> there is nothing left to generate from this project's templates;
> `build-dotfiles.sh` skips them.

Configuration files are kept pre-generated in the repository under
`dotfiles/<name>/`. They can be copied without installing packages and
without going through the installer at all.

```bash
./dotfiles/install-dotfiles.sh                  # list the sets
./dotfiles/install-dotfiles.sh nord-frost             # install under ~/.config
./dotfiles/install-dotfiles.sh nord-frost --packages  # also install the programs they need
./dotfiles/install-dotfiles.sh nord-frost -n          # show what it would do first
```

Your existing files are still backed up under
`~/.config/hyprsetup-backups/<date-time>/`, and `custom.conf` is created if
missing.

`--packages` installs the list in `dotfiles/packages.txt` (generated along
with the trees): repo packages with `pacman -S --needed`, AUR packages with
whichever helper is found (paru/yay/pikaur), then enables the
`NetworkManager`, `bluetooth`, `power-profiles-daemon` and `sddm` services.
This list is generated just like the templates — it is the programs the files
actually need.

The files are not edited by hand; they are generated from `templates/` +
`presets/profile/`, and are deliberately free of machine-specific values (no
monitor names, no absolute home paths):

```bash
./tools/build-dotfiles.sh <name1> <name2> ...  # regenerate only these
./tools/build-dotfiles.sh --check              # do the committed ones match the templates
```

When there is no profile to generate a tree for (the author-setup profiles
are skipped), `./tools/build-dotfiles.sh` without arguments generates nothing
and exits with 0. Details: [`dotfiles/README.md`](dotfiles/README.md).

---

## Settings

Every setting lives in one file: **`~/.config/hyprsetup/settings.conf`**. The
settings app reads and writes exactly that file — editing it by hand and using
the app are the same thing; there is no second source of truth.

```bash
cp config/settings.conf.example ~/.config/hyprsetup/settings.conf
$EDITOR ~/.config/hyprsetup/settings.conf
hyprsetup                 # reads the file on start
```

**Changes to the file are applied automatically.** While the settings app is
open it watches `settings.conf`: when you edit the file in an editor (or copy
it over from another machine), the values are read back into the app and
applied to the desktop. With the app closed, a command does the same job:

```bash
hyprsetup watch &          # watch the file, apply on every change
```

There are 314 settings;
[`config/settings.conf.example`](config/settings.conf.example) lists them all
with descriptions. 289 of them appear in the app's settings schema as regular
rows; the rest (theme, fonts, bar modules, keybindings, default apps,
displays…) have dedicated editors on their pages. Where each feature lives in
the settings app (and which ones are deliberately not settings) is described
in [`docs/settings-guide.md`](docs/settings-guide.md). Groups:

| Group | Example variables |
|---|---|
| General | `HYPR_LANG` (see [Configuration language](#configuration-language-conf-or-lua)) |
| Appearance | `THEME`, `PALETTE_BACKEND`, `CUSTOM_COLORS`, `COLOR_SCHEME`, `CURSOR_THEME`, `GTK_THEME_NAME`, `ICON_THEME_NAME`, `FONT_FAMILY`, `FONT_SIZE` |
| Status bar | `BAR_PRESET`, `BAR_POSITION`, `BAR_HEIGHT`, `BAR_RADIUS`, `BAR_OPACITY`, `BAR_MODULES_*`, `BAR_AUTOHIDE`, `BAR_AUTOHIDE_TRIGGER/RELEASE`, `BAR_CUSTOM1..3_*`, `WEATHER_LOCATION`, `WEATHER_UNIT`, `WEATHER_REFRESH` |
| Terminal / Launcher | `TERM_*`, `LAUNCHER_*` (plus `LAUNCHER_PROVIDERS` for walker) |
| Layout | `GAPS_IN/OUT`, `GAPS_WORKSPACES`, `BORDER_SIZE`, `BORDER_ANGLE`, `ROUNDING`, `ROUNDING_POWER`, `LAYOUT` |
| Decoration | `BLUR_*` (size, passes, xray, noise, contrast, vibrancy…), `SHADOW_*`, `DIM_*`, `ACTIVE/INACTIVE_OPACITY` |
| Animation | `ANIMATIONS`, `ANIMATION_PRESET`, `ANIMATION_SPEED`, `RICE_TRANSITION` |
| Behavior | `ALLOW_TEARING`, `SNAP*`, `VRR`, `ENABLE_SWALLOW`, `SWALLOW_REGEX`, `ON_FOCUS_UNDER_FULLSCREEN`, `DPMS_ON_INPUT`, `RULE_*`, `PIP_WIDTH`, `QUICK_PANEL_*` |
| Window groups / plugins | `GROUPBAR*`, `HYPREXPO_COLUMNS`, `HYPRBARS_*` |
| Input | `KB_LAYOUT/VARIANT/OPTIONS`, `REPEAT_DELAY/RATE`, `FOLLOW_MOUSE`, `SENSITIVITY`, `ACCEL_PROFILE`, `TOUCHPAD_*` |
| Gestures | `GESTURE_SWIPE`, `GESTURE_FINGERS`, `SWIPE_DISTANCE`, `SWIPE_CANCEL_RATIO` |
| Keybindings | `KEYBINDS` (see [Keybindings](#keybindings)) |
| Displays | `MANAGE_HYPR_CONFIGS`, `MANAGE_MONITORS`, `MONITOR_SPEC`, `WORKSPACE_MONITOR_MAP` |
| Wallpaper | `WALLPAPER_PATH`, `WALLPAPER_ROTATE`, `WALLPAPER_DIR`, `SWWW_*`, `WPENGINE_*` |
| Screen recording and screenshots | `RECORD_DIR`, `RECORD_FPS`, `RECORD_AUDIO`, `RECORD_FORMAT/CODEC/QUALITY/CURSOR`, `REPLAY_SECONDS`, `SCREENSHOT_DIR` |
| Idle and lock | `IDLE_DIM`, `IDLE_LOCK`, `IDLE_DPMS`, `IDLE_SUSPEND`, `IDLE_DIM_LEVEL`, `IDLE_KBD_BACKLIGHT`, `IDLE_LOCK_BEFORE_SLEEP`, `IDLE_RESPECT_INHIBIT` |
| Lock screen | `LOCK_BACKGROUND`, `LOCK_BLUR_*`, `LOCK_CLOCK_*`, `LOCK_SHOW_DATE`, `LOCK_PLACEHOLDER`, `LOCK_GRACE` |
| Notifications | `NOTIFY_POSITION`, `NOTIFY_TIMEOUT`, `NOTIFY_WIDTH`, `NOTIFY_MAX_VISIBLE`, `NOTIFY_*` |
| Power menu | `POWERMENU_HIBERNATE`, `POWERMENU_CONFIRM` |
| Night light | `NIGHT_SHADER`, `NIGHT_SHADER_START/END`, `NIGHT_TEMP` |
| Environment | `QT_PLATFORM_THEME`, `XDG_MENU_PREFIX`, `FLATPAK_DIRS`, `EDITOR_CMD`, `TERMINAL_ARGS`, `EXTRA_ENV` |
| Autostart | `EXTRA_EXEC_ONCE`, `GNOME_KEYRING` |

### Not in here: install-time decisions

`settings.conf` deliberately holds **only** things the settings app can
change. These are not in it:

| Decision | Where |
|---|---|
| Which components get installed | `install.sh` → `DEFAULT_COMPONENTS` |
| AUR helper, PKGBUILD review, Chaotic-AUR | `lib/config.sh` defaults (`AUR_HELPER`, `AUR_REVIEW`, `CHAOTIC_AUR`) |
| Build-from-source policy | `./install.sh --compile ask\|never\|always` |
| Package filtering | `./install.sh --skip-pkg a,b` |
| Enabling services, overwriting existing files | `ENABLE_SERVICES`, `OVERWRITE_CONFIGS` (installer-internal) |
| Login screen background, boot animation | `SDDM_BACKGROUND`, `PLYMOUTH_THEME` — install steps, need root |
| Login manager | `LOGIN_MANAGER` — chosen at install time |

If these were in `settings.conf`, you would edit the line in the app and
nothing would happen.

The file can be fed back to the installer to reproduce the same desktop
exactly on another machine:

```bash
./install.sh -c ~/.config/hyprsetup/settings.conf
```

### Window dimensions

```
┌──────────────────────── screen ───────────────────────────┐
│  ↕ GAPS_OUT (between windows and the screen edge)         │
│   ┌────────────────────┐ ↔ GAPS_IN ┌──────────────────┐   │
│   │                    │           │                  │   │
│   │  focused window    │           │  background      │   │
│   │  ACTIVE_OPACITY    │           │ INACTIVE_OPACITY │   │
│   │                    │           │                  │   │
│   └────────────────────┘           └──────────────────┘   │
│    ╰ BORDER_SIZE: border width                            │
│      (a gradient between two accent colors on the focused │
│       window; its direction is set by BORDER_ANGLE)       │
│    ⌐ ROUNDING: corner radius · ROUNDING_POWER: 2 circle,  │
│      4 squircle (between square and circle)               │
└───────────────────────────────────────────────────────────┘
```

On the **Appearance** page of the settings app these dimensions are also drawn
as a diagram marked with arrows and labels; when you move a slider, both the
realistic preview and the diagram update together.

Commonly used:

```bash
THEME="tokyo-night"              # list with: python3 -m hyprsetup themes
MOD_KEY="SUPER"                  # main modifier key
LAYOUT="dwindle"                 # dwindle | master
KB_LAYOUT="us"
GAPS_IN=5; GAPS_OUT=12; ROUNDING=10; BORDER_SIZE=2
ANIMATION_SPEED=1.5              # make animations 50% faster
FONT_FAMILY="Noto Sans"                  # UI font
FONT_MONO="JetBrainsMono Nerd Font"      # terminal font (must be monospace)
WALLPAPER_ROTATE=0               # minutes; >0 installs a systemd rotation timer
MONITOR_SPEC="DP-1,2560x1440@165,0x0,1;HDMI-A-1,1920x1080@60,2560x0,1"
WORKSPACE_MONITOR_MAP="1:DP-1:default;6:HDMI-A-1:default"
EXTRA_EXEC_ONCE="easyeffects --hide-window --service-mode;;solaar -w hide"
TERMINAL="kitty"; LAUNCHER="wofi"; BAR="waybar"; NOTIFIER="mako"
```

### Launcher providers (walker)

With **walker** as the launcher, extra query sources can be enabled on top of
the application list: calculator, clipboard history, emoji/symbols, file
search, open windows, command runner, todos, bookmarks, Bluetooth devices,
audio devices, media player, Arch package search, text snippets.

Each source has a prefix; typing a query that starts with that character
switches to that source:

| Prefix | Source | | Prefix | Source |
|---|---|---|---|---|
| `=` | calculator | | `>` | command runner |
| `:` | clipboard history | | `;` | source list (those without a prefix) |
| `.` | emoji and symbols | | `!` | todos |
| `/` | file search | | `%` | bookmarks |
| `$` | open windows | | `@` | web search |

```bash
LAUNCHER_PROVIDERS="calc,websearch,clipboard,symbols,files,windows,runner,providerlist"
```

In the app, the switches at the bottom of the *Launcher* page write the same
line. A query without a prefix lists only applications (plus the calculator
and web search when enabled); to keep it uncluttered, the rest are reached by
prefix.

walker does not collect the data itself; it gets it from a backend service
called **elephant**, and every source is a separate elephant plugin. That is
why the walker component installs `walker-bin` + `elephant-bin` + the plugins
for the sources above together, and the service is started with the session
(`exec-once = elephant`). The other launchers (wofi/rofi/fuzzel/tofi) ignore
this setting.

### Default applications

Terminal, file manager and browser are set in **one place**: the
`TERMINAL` / `FILEMANAGER` / `BROWSER` lines in `settings.conf` (in the app:
*Applications*). Each value is a component id (`config/components.json`) and
goes from there to three places at once:

| Where | What for | Field used |
|---|---|---|
| Keybindings | `MOD+Return` opens the terminal, `MOD+E` the file manager | the component's `exec` field |
| `~/.config/mimeapps.list` | which application opens which file type | the component's `desktop` field |
| `~/.config/xdg-terminals.list` | the terminal anything that says "open in terminal" uses | the component's `desktop` field |

So changing one line changes all three; there are no separate places to keep
in sync. The project standard is **kitty** (terminal) and **dolphin** (file
manager).

Which MIME type goes to which role lives in the
`python/hyprsetup/render.py` → `DEFAULT_APP_ROLES` /
`DEFAULT_APP_COMPONENT_ROLES` tables. For a component to become a default
application, its catalog entry must have a `"desktop"` field; terminal tools
such as `yazi` leave it empty, and if such a tool is selected no file-manager
association is written to `mimeapps.list` at all.

### Integration with community projects

The catalog has ready-made components for three widely used community
projects.

**[Almamu/linux-wallpaperengine](https://github.com/Almamu/linux-wallpaperengine)**
— runs Steam Wallpaper Engine wallpapers on Wayland (compatible with Hyprland
through `wlr-layer-shell`). AUR: `linux-wallpaperengine-git`.

```bash
WALLPAPER_DAEMON="wallpaperengine"
WPENGINE_ID="2667198602"     # ls ~/.steam/steam/steamapps/workshop/content/431960
WPENGINE_SCREEN="DP-1"
WPENGINE_SCALING="fill"
WPENGINE_FPS=30
```

The full command is generated into `autostart.conf` from these settings.
**Wallpaper Engine must be bought and installed on Steam**; during
installation the script looks for the Steam asset directories and warns if it
cannot find them.

**[Quickshell](https://quickshell.outfoxxed.me)** — a QtQuick-based shell
engine. It can be selected as the bar; the `presets/bar/quickshell-*.conf`
presets bring a ready-made panel, and beyond that you write your own QML.

**[mylinuxforwork/hyprland-settings](https://github.com/mylinuxforwork/hyprland-settings)**
— ML4W Hyprland Settings. **This repository was archived on May 27, 2026**;
the developer recommends HyprMod instead. It is in the catalog as the `hyprmod`
component (GTK4/libadwaita, still new). Adding it to `DEFAULT_COMPONENTS`
gives `SUPER + I` an extra fallback — but that is no longer needed: the
settings app is installed to `~/.local/bin/hyprsetup`, so it works even if
the repository is deleted.

`nwg-displays` is in the catalog too, for the display layout. That tool
generates `monitors.conf` / `workspaces.conf` itself and puts a
`# Generated by nwg-displays ...` line at the top; when the script sees that
line it hands the file over to it **automatically** (`MANAGE_MONITORS=0` is
set and saved that way in `settings.conf`) and never touches its content
again. To take management back, turn on *Displays → "let this tool manage
monitors.conf"* in the settings app: the file is backed up and regenerated
from `MONITOR_SPEC`.

### Coexisting with an existing setup

If you have your own Hyprland configuration (hand-written, or a ready-made
rice that takes over the whole `~/.config/hypr` directory):

```bash
MANAGE_HYPR_CONFIGS=0   # the script never touches the hypr configs
MANAGE_MONITORS=0       # leave monitors.conf to a tool like nwg-displays
```

Both are switches on the *Home* page of the settings app. In this mode the
script only installs packages, enables services and configures the other
applications such as waybar/terminal/theme — the Hyprland configuration stays
yours. If `WORKSPACE_MONITOR_MAP` is left empty, `workspaces.conf` is not
generated at all.

### Themes and colors

There are 80 palettes; `catppuccin-mocha`, `catppuccin-macchiato`,
`tokyo-night`, `gruvbox-dark`, `nord`, `rose-pine` and `everforest-dark` are
the best known.

The theme is applied to Hyprland borders, waybar, kitty/foot/alacritty,
wofi/fuzzel, mako/dunst **and** all GTK/Qt applications at once.

```bash
python3 -m hyprsetup themes      # themes with their colors
```

**`THEME="auto"`** is a special value: the palette is extracted from your
wallpaper instead of a fixed theme (settings app → *Appearance → Theme*).
Three backends are tried in order —
[`matugen`](https://github.com/InioX/matugen) (Material You), ImageMagick,
then a dependency-free PNG decoder built into the project (can be forced with
`PALETTE_BACKEND`).

Only **hue and saturation** are taken from the image; lightness is forced onto
a fixed scale for each role, and text/background contrast is guaranteed to
meet WCAG AA. Unreadable desktops come from using an image's dominant colors
directly as background and text; this design makes that impossible.

Individual palette colors can be overridden with `CUSTOM_COLORS` — in the
app, with color pickers under Appearance → "Customize colors":

```bash
CUSTOM_COLORS="ACCENT=ff7a18;;ACCENT2=ffd166;;BG=0d0d12"
```

Keys: `BG` `BG_DARK` `SURFACE` `FG` `SUBTEXT` `ACCENT` `ACCENT2`
`RED` `GREEN` `YELLOW` `CYAN`. An invalid value stops the installation
(`config_validate` checks the hex format).

`COLOR_SCHEME` (`dark` | `light`; in the app, Appearance → "System color")
is separate from these: it decides whether GTK4/libadwaita and GTK3
applications open in dark or light mode — it is independent of `THEME`'s
accent colors, and `light` can be forced even while a dark theme is selected.

### Status bar

Which number changes what:

```
┌──────────────────────── screen ───────────────────────────┐
│   ↕ BAR_MARGIN (gap from the edge the bar sits on)        │
│  ┌─────────┐  ┌──────────────┐        ┌────┐ ┌─────────┐  │ ↕ BAR_HEIGHT
│  │ 1  2  3 │  │ kitty — ~/p… │        │Vol │ │  12:34  │  │
│  └─────────┘  └──────────────┘        └────┘ └─────────┘  │
│   MODULES_LEFT    MODULES_CENTER        MODULES_RIGHT     │
│            ↔ BAR_SPACING      ⌐ BAR_RADIUS                │
│           (between boxes)    (box corner)                 │
│  ┌───────────────┐                                        │
│  │←→ BAR_PADDING │  horizontal padding inside a box       │
│  └───────────────┘                                        │
│  BAR_OPACITY: opacity of the box background (0–1)         │
└───────────────────────────────────────────────────────────┘
```

The **Status Bar** page of the settings app draws this live at 1:1 scale with
the modules you selected — height and margin are dimensioned with arrows, and
the workspace indicator (numbers/dots/roman) appears exactly as it will look.

```bash
BAR_POSITION="bottom"; BAR_HEIGHT=44; BAR_MARGIN=10
BAR_RADIUS=22; BAR_OPACITY=0.6; BAR_PADDING=16
BAR_WORKSPACE_STYLE="roman"          # numbers | dots | roman
BAR_CLOCK_FORMAT="%a %d %b  %H:%M"
BAR_MODULES_LEFT="hyprland/workspaces"
BAR_MODULES_CENTER="clock"
BAR_MODULES_RIGHT="temperature,disk,pulseaudio,network,tray,custom/power"
```

Available modules: `hyprland/workspaces` `hyprland/submap`
`hyprland/window` `cpu` `memory` `temperature` `disk` `backlight`
`pulseaudio` `bluetooth` `network` `battery` `idle_inhibitor` `tray`
`clock` `custom/power` `custom/cava` `custom/weather` `custom/powerprofile`
`custom/privacy` `custom/user1` `custom/user2` `custom/user3`.

The last six are drawn by this project's own scripts (in Waybar; silently
skipped on the other backends):

| Module | What it shows | Requires |
|---|---|---|
| `custom/weather` | Temperature from wttr.in; click to refresh. Location and unit come from `WEATHER_LOCATION` / `WEATHER_UNIT`, and the result is cached for 15 minutes | `curl` |
| `custom/powerprofile` | The current power profile; click to switch to the next | the `power` component (power-profiles-daemon) |
| `custom/privacy` | A warning icon while an app is using the microphone, camera or screen **right now**; otherwise the module is not drawn at all. The source is the PipeWire graph (`pw-dump`) | the `pipewire` component |
| `custom/user1..3` | The output of your own command — see below | — |

**Your own module.** Each of the three slots takes a command, a format, a
refresh interval and an optional click command. A slot with a command becomes
available in the module list; an empty slot is not written to the generated
config at all.

```bash
BAR_CUSTOM1_CMD="df -h / | awk 'NR==2{print \$4}'"
BAR_CUSTOM1_FORMAT="󰋊 {}"      # {} = first line of the command's output; empty = "{}"
BAR_CUSTOM1_INTERVAL=300       # seconds
BAR_CUSTOM1_CLICK="kitty -e btop"
BAR_MODULES_RIGHT="custom/user1,pulseaudio,clock"
```

**Auto-hide.** `BAR_AUTOHIDE="true"` pulls the bar off the screen; it comes
back when the pointer touches that edge, and the bar stops reserving space for
windows. In Quickshell the bar hides itself; in Waybar a small helper process
(`hypr/scripts/bar-autohide.py`) watches the pointer over Hyprland's IPC
socket and sends the bar show/hide signals — Waybar's own `mode: hide` does
this over Sway IPC and does not work on Hyprland. `MOD + J` toggles it by hand
in every case (with auto-hide on, it **pins** the bar; press again to return
to automatic).

The module lists are generated as JSON arrays on the Python side; if the
component a module needs is not installed (e.g. the `bluetooth` module without
the Bluetooth component), it is removed from the list automatically. That way
the generated `config.jsonc` is always valid JSON.

**The bar backend is a separate axis:** which program runs (waybar /
hyprpanel / quickshell / wayle) is determined by the selected bar preset, and
only one is started at a time.

### Desktop widgets

There are 15 desktop widgets, and **both** engines (eww and Quickshell) draw
all of them:

| Widget | What it shows | Requires |
|---|---|---|
| `clock` | Large clock + date | — |
| `sysinfo` | CPU and RAM percentage | — |
| `battery` | Battery percentage and status ("--" without a battery) | — |
| `calendar` | Monthly calendar | — |
| `music` | Now playing (playerctl) | audio tools |
| `network` | Name of the active connection (nmcli) | NetworkManager |
| `volume` | Volume / muted (pamixer) | audio tools |
| `brightness` | Screen brightness (brightnessctl) | brightness control |
| `uptime` | Uptime | — |
| `disk` | Usage of the "/" partition | — |
| `temperature` | CPU temperature | — |
| `worldclock` | London · Tokyo · New York | — |
| `kblayout` | Active keyboard layout | — |
| `fetch-mini` | Hostname, kernel, shell | — |
| `workspace` | Active workspace | — |

**Placement uses six positions:** the four corners, top center (`TC`) and
bottom center (`BC`). The widgets in each position stack away from the edge,
one after another, in list order. For a position left empty, each widget's
own default corner applies. `WIDGET_OFFSETS` nudges a single widget pixel by
pixel (`name:x:y`; a vertical nudge also pushes the widgets below it, and
horizontal nudges are not applied in the center positions).

```bash
WIDGETS="clock,sysinfo,disk,calendar"
WIDGET_ZONE_TR="clock,sysinfo"     # top right, top to bottom
WIDGET_ZONE_BL="disk"
WIDGET_ZONE_TL="calendar"
WIDGET_ZONE_BC="music"             # bottom center, centered horizontally
WIDGET_OFFSETS="clock:0:24"        # push the clock 24 px down
WIDGET_MARGIN=16       # gap from the screen edge
WIDGET_GAP=10          # gap between widgets
WIDGET_SCALE=1.0       # box + text scale (0.5–2.0)
WIDGET_RADIUS=12
WIDGET_OPACITY=0.85    # background opacity; text stays opaque
```

Positions are computed: **the edge the bar occupies is subtracted up front**,
so with a top bar the top-right widget does not disappear under the bar.
With `BAR_AUTOHIDE` on, the bar reserves no space, so nothing is subtracted.

The **Widgets** page of the settings app edits this as chip lists in a 3×2
grid laid out like the screen (click a chip for order, position and pixel
nudge), and the preview on the right shows where the boxes will land on
screen — the preview positions are computed by the same function that
generates the config. The page also names the selected engine, warns when the
engine's package is not installed, and says why when a component a widget
needs is missing. Ready-made widget sets live in `presets/widget-set/`.

---

## Generated files

HYPR_LANG=conf (the default, see [Configuration language](#configuration-language-conf-or-lua)):

```
~/.config/hypr/hyprland.conf      main config (sources the others)
              /monitors.conf      display layout
              /env.conf           environment variables (NVIDIA included)
              /autostart.conf     exec-once lines
              /keybinds.conf      keyboard shortcuts
              /windowrules.conf   window and layer rules
              /custom.conf        YOURS — the script never touches it
```

HYPR_LANG=lua:

```
~/.config/hypr/hyprland.lua              main config (requires the others)
              /hyprland/monitors.lua     display layout
              /hyprland/workspaces.lua   workspace → display mapping
              /hyprland/env.lua          environment variables
              /hyprland/autostart.lua    hl.on("hyprland.start", …)
              /hyprland/keybinds.lua     keyboard shortcuts
              /hyprland/windowrules.lua  window and layer rules
              /custom.lua                YOURS — the script never touches it
```

In both modes:

```
~/.config/hypr/hyprlock.conf      lock screen
              /hypridle.conf      idle behavior
              /hyprpaper.conf     wallpaper
              /scripts/keybind-help.sh
              /scripts/settings.sh    SUPER+I — opens the settings app
              /scripts/powermenu.sh   power menu (when wlogout is not installed)
~/.config/hyprsetup/settings.conf           your settings (single source of truth)
~/.config/waybar/{config.jsonc,style.css}
~/.config/{kitty,foot,alacritty,ghostty,wezterm}/…  (depending on the chosen terminal)
~/.config/{wofi,fuzzel,rofi,tofi,walker}/…          (depending on the chosen launcher)
~/.config/{mako,dunst,swaync}/…             (depending on the notification daemon)
~/.config/dolphinrc, kdeglobals             (when the file manager is Dolphin)
~/.config/yazi/theme.toml                   (when yazi is selected)
~/.config/wlogout/{layout,style.css}        (when wlogout is selected)
~/.config/gtk-3.0/{settings.ini,gtk.css}    GTK3 theme/cursor/font + Adwaita accent colors
~/.config/gtk-4.0/{settings.ini,gtk.css}    GTK4 + libadwaita accent colors
~/.config/{qt5ct,qt6ct}/…                   Qt color scheme (when qt-theme is selected)
~/.config/btop/{btop.conf,themes/…}         (when cli-tools is selected)
~/.config/xdg-desktop-portal/hyprland-portals.conf   for screen sharing
~/.local/bin/hyprsetup                      the settings app
~/.local/share/hyprsetup/…                  its copy of the python/templates/catalog
```

The theme is applied to Hyprland, the bar, terminal, launcher, notifications
**and** GTK/Qt applications at once — the file manager, settings tools and
browser dialogs match the palette too.

For your personal changes use **`~/.config/hypr/custom.conf`** (in Lua mode
**`custom.lua`**): it is read last, so it overrides every generated setting,
and the script never modifies it.

---

## Keybindings

All keybindings are defined in [`config/keybinds.json`](config/keybinds.json);
`keybinds.conf` is generated from it. You can view and change them in three
places:

- **`SUPER + F1`** — shows the active keybindings on screen on a running system
- **Settings app → Keybindings** — click, press the new key
- **`config/keybinds.json`** — the source file

### Rebinding

On the **Keybindings** page of the settings app, click a binding's key and
press the new combination: `Esc` cancels, `Backspace` removes the binding
entirely. Two conflicting bindings are shown in red. Changes are written to
`settings.conf` as a single line:

```bash
KEYBINDS="terminal=MOD+Return;;filemanager=MOD+E;;color-picker="
```

| Syntax | Meaning |
|---|---|
| `MOD` | The main modifier — whatever `MOD_KEY` is (default `SUPER`) |
| `MOD+SHIFT+L` | Modifiers are joined with `+`: `MOD` `CTRL` `ALT` `SHIFT` |
| `Print` | A key without modifiers |
| `id=` (empty) | Removes that binding entirely |

Binding ids (`terminal`, `lock`, `screenshot-region` …) are the `id` fields in
`config/keybinds.json`. To add a new binding, write an entry there:

```json
{ "id": "steam", "title": "Steam", "keys": "MOD+G", "dispatcher": "exec", "args": "steam" }
```

With a `require` field (`"require": "HAS_CLIPBOARD"`) the binding is only
generated when the matching component is installed. For one-off additions,
`~/.config/hypr/custom.conf` is more practical than `keybinds.json`.

The conflict check runs on every generation — Hyprland silently drops
duplicate bindings, so the script does not let that happen silently:

```bash
PYTHONPATH=python python3 -m hyprsetup keybinds --mod SUPER
```

### Defaults

The key combinations are aligned with
[end-4/dots-hyprland](https://github.com/end-4/dots-hyprland)
(illogical-impulse). Their Quickshell-specific bindings (OSK, Google Lens, OCR,
translation, overview…) were not taken over because this project has no
equivalent; those with a close equivalent were mapped (SUPER tap for the
launcher, SUPER+N for the notification center, SUPER+G for widgets). The
`_note_end4` field at the top of `config/keybinds.json` explains the
deliberate deviations (SUPER+Tab, SUPER+C, SUPER+ALT+R/G) and why.

`SUPER + /` (or `SUPER + F1`) opens the **keybinding cheatsheet**: a
searchable window grouped by category. The list is generated from
`config/keybinds.json` and shows only the bindings that are ACTUALLY active —
your own overrides (`KEYBINDS`) are applied, and bindings tied to an
unselected component are not drawn at all. Clicking a row and pressing a new
key combination changes that binding on the spot (Backspace removes it,
changed ones are highlighted); it is saved to the same `KEYBINDS` line as the
settings app and applied immediately. Without GTK, the old plain list opens
in dmenu.

105 bindings in total. Highlights:

| Binding | Action |
|---|---|
| `SUPER + Return` / `SUPER + T` / `CTRL + ALT + T` | Terminal |
| `SUPER` (tap) | Application launcher |
| `SUPER + A` | Actions: song recognition (Shazam via songrec), color picker, emoji, screenshot, calculator, power — also found by searching in the launcher |
| `SUPER + E` | File manager |
| `SUPER + W` | Web browser |
| `SUPER + I` | Settings app as a floating panel — every page; `Esc` closes |
| `ALT + Tab` | Window switcher: a live thumbnail of every window + app icon; brings the chosen one forward **by switching to its workspace** (releasing ALT selects, Esc cancels) |
| ``ALT + ` `` | Jump straight back to the last used window, without the list |
| `SUPER + G` | Show/hide desktop widgets (eww) |
| `SUPER + N` | Notification center (swaync) |
| `SUPER + .` | Emoji picker |
| `SUPER + Q` | Close window |
| `SUPER + F` / `SUPER + D` | Fullscreen / maximize |
| `SUPER + ALT + Space` | Floating window |
| `SUPER + P` / `SUPER + ALT + P` | Pin / pseudo-tiling |
| `SUPER + arrow` | Move focus |
| `SUPER + SHIFT + arrow` | Move window |
| `SUPER + ALT + arrow` | Resize window |
| `SUPER + CTRL + left/right` | Adjacent workspace |
| `SUPER + 1…0` / `SUPER + ALT + 1…0` | Go to workspace / send window there |
| `SUPER + S` / `SUPER + ALT + S` | Special workspace: scratchpad / send to it |
| `SUPER + V` | Clipboard history |
| `SUPER + /` or `SUPER + F1` | Keybinding cheatsheet — searchable, grouped |
| `SUPER + J` | Show/hide the bar (Waybar) |
| `SUPER + SHIFT + S` | Screenshot of a selected region |
| `Print` / `CTRL + Print` | Copy the whole screen to the clipboard / + save to a file |
| `SUPER + SHIFT + G` | Screen filter menu (hyprshade) |
| `SUPER + ALT + R` / `SUPER + ALT + G` | Instant replay buffer on/off / save the last moments (`REPLAY_SECONDS`, 60 by default) |
| `SUPER + L` | Lock the screen |
| `SUPER + SHIFT + L` | Sleep |
| `CTRL + ALT + Delete` | Power menu (lock / sleep / shut down — asks for confirmation) |
| `SUPER + SHIFT + R` | Start/stop screen recording |
| `SUPER + CTRL + R` | Reload the configuration |
| `SUPER + SHIFT + N/B/P` | Next / previous track / play-pause |

---

## Backup and restore

Every overwritten file is copied to:

```
~/.config/hyprsetup-backups/<date-time>/
```

To restore:

```bash
./restore.sh --list
```

```bash
./restore.sh            # the latest INSTALL backup (install.sh)
./restore.sh --first    # the first backup: the original state before hyprsetup
```

Without arguments it restores the latest **install** backup; the settings
app's session backups (`live` in `--list`) are only selected by name. Files
created from scratch by that installation are removed too. System files under
`/etc` need root, so they are not restored automatically; the script prints
the copy commands for you.

Backups are pruned automatically: the first backup is never deleted, and
after that the newest 5 install backups and 10 settings app backups are kept
(`python3 -m hyprsetup backups`). Install logs are under
`~/.local/state/hyprsetup/logs/`.

---

## Extending

The script is data-driven; most changes require no code.

### Adding an application

Add an entry to `config/components.json`:

```json
{
  "id": "zellij",
  "title": "Zellij",
  "desc": "Terminal multiplexer",
  "repo": ["zellij"],
  "aur": [],
  "services": [],
  "exec": "zellij"
}
```

You can now add `zellij` to the `DEFAULT_COMPONENTS` array in `install.sh` to
install it; it shows up in the settings app and can be used as a condition in
templates with `{{#if HAS_ZELLIJ}}`.

### Adding a config file

Put a file under `templates/`. The path corresponds to the target under
`~/.config/` (`templates/btop/btop.conf.tmpl` → `~/.config/btop/btop.conf`).

Template syntax:

| Construct | Meaning |
|---|---|
| `{{VAR}}` | Variable substitution |
| `{{#if VAR}} … {{/if}}` | Conditional block |
| `{{#unless VAR}} … {{/unless}}` | Inverted conditional block |
| `{{! require: EXPR }}` | Under which condition the file is generated |
| `{{! target: path }}` | Set the output path explicitly |
| `{{! mode: 755 }}` | Output file permissions |

A `require` expression can use `VAR`, `!VAR`, `VAR==value`, `VAR!=value`,
combined with `&&` and `||`. Example:

```
{{! require: TERMINAL==kitty && HAS_KITTY }}
```

Available variables: theme colors (`HEX_ACCENT`, `RGBA_BG`, `COL_FG`…),
settings (`MOD_KEY`, `GAPS_IN`, `FONT_FAMILY`…), component flags (`HAS_*`),
commands (`CMD_TERMINAL`, `CMD_LAUNCHER`, `LOCK_CMD`, `SCREENSHOT_CMD`…) and
computed values (`WORKSPACE_BINDS`, `MONITOR_LINES`, `AUTOSTART_LINES`).

A new template also needs an entry in the file → action table in
`python/hyprsetup/apply.py`; otherwise the settings app writes the file but
nothing changes on screen, because the matching daemon is never reloaded.
`tools/test.sh` checks this.

### Adding a theme

Add an 11-color entry to the `THEMES` dictionary in
`python/hyprsetup/themes.py` — it is applied to every application
automatically.

### Adding a setting

1. the default in `lib/config.sh` → `config_defaults`,
2. its name in the `lib/config.sh` → `CONFIG_VARS` list (unless it is an
   install-time setting),
3. a `Setting` entry in `python/hyprsetup/settings.py`,
4. if needed, a commented line in `config/settings.conf.example`.

`python3 -m hyprsetup check-schema` verifies the two have not drifted apart.

### Component-specific install step

Define `hook_<component_id>()` in `modules/*.sh` (underscores instead of
dashes). If the component is selected, `install.sh` calls it after installing
the packages:

```bash
hook_zellij() {
    step "Zellij default shell integration"
    run some-command
}
```

---

## Project layout

```
install.sh                 entry point, flow control, DEFAULT_COMPONENTS
hyprsetup-gui              runs the settings app from the repository (before install)
restore.sh                 restore from a backup
lib/core.sh                logging, colors, dry-run, backups, sudo
   /config.sh              defaults, settings file, validation
   /preset.sh              applying bar/terminal/launcher presets
   /doctor.sh              --doctor health checks
   /preflight.sh           system checks, AUR helper
   /packages.sh            catalog queries, pacman/AUR, services
   /render.sh              template generation and installation
modules/*.sh               component-specific post-install steps
config/components.json     component catalog (single source of truth)
config/keybinds.json       keybindings (conf + app + help screen)
config/settings.conf.example  example settings file
presets/bar|terminal|launcher|widget|widget-set/*.conf   preset looks
presets/profile/           profiles (*.conf; author setups also *.rice.toml)
templates/                 configuration templates
dotfiles/<name>/           ready-made configs generated from the templates
tools/build-dotfiles.sh    regenerates the dotfiles/ tree (--check)
tools/test.sh              repository integrity checks
python/hyprsetup/          template engine, themes, palette extraction, keybindings
python/hyprsetup/apply.py  applying a setting: write + reload the matching daemon
python/hyprsetup/gui/      the GTK4 settings app (app.py: the full window)
python/hyprsetup/gui/quick.py  SUPER+I: opens app.py in panel mode
```

---

## Troubleshooting

Run `./install.sh --doctor` first; it finds most of the following by itself.

| Symptom | Cause / fix |
|---|---|
| `SUPER + I` opens nothing | Check that `~/.local/bin/hyprsetup` exists; if not, run `./install.sh` again. It works even if `~/.local/bin` is not on PATH, because the keybinding tries the full path |
| Bar icons show up as boxes | No Nerd Font: `sudo pacman -S ttf-jetbrains-mono-nerd`, then `fc-cache -f` |
| Hyprland shows an error at startup | `~/.config/hypr/custom.conf` (`custom.lua` in Lua mode) may have been deleted — recreate it with `touch`; see `hyprctl configerrors` for details |
| `Failed to load config` / Lua error | `HYPR_LANG=lua` is experimental — 0.57 is not officially out yet and the API may have changed. Set `HYPR_LANG="conf"` in `settings.conf` and apply from the settings app |
| `Invalid dispatcher: <name>` | The binding's dispatcher does not exist in that version. Hyprland 0.54 removed `togglesplit`/`swapsplit` → `layoutmsg, togglesplit`. Check your own bindings against the [dispatcher list](https://wiki.hypr.land/Configuring/Dispatchers/); the session still starts, only that key does not work |
| `getCurrentCRTC: No CRTC` + black screen | The display/driver layer: usually a virtual machine (VirtualBox/VMware), or missing `nvidia_drm.modeset=1` on NVIDIA. See "In a virtual machine" below |
| Screen sharing is black / the picker does not open | Portal mix-up: check that `~/.config/xdg-desktop-portal/hyprland-portals.conf` was generated, then log in again |
| GTK apps are unthemed | If `~/.config/gtk-3.0/settings.ini` is missing, change and apply any setting in the settings app; GTK4 needs `gtk-4.0/gtk.css` |
| GTK apps are still black/white (Adwaita blue/gray) | Without the `gtk-theme` component, GTK3 stays on Adwaita/Adwaita-dark by default — in that case `~/.config/gtk-3.0/gtk.css` injects THEME's accent/background colors into Adwaita |
| Qt apps are unthemed | `QT_PLATFORM_THEME` must match the qt6ct/kde choice; for Dolphin use `QT_PLATFORM_THEME="kde"` |
| The cursor disappears/flickers | Try `NO_HARDWARE_CURSORS="true"`; is the cursor theme installed (`--doctor` tells you) |
| The lock screen rejects the password | `/etc/pam.d/hyprlock` is missing: `echo 'auth include system-auth' \| sudo tee /etc/pam.d/hyprlock` |
| No sound | `systemctl --user status pipewire wireplumber`; if PulseAudio is left over, disable it |
| Black screen / flicker on NVIDIA | The `nvidia` component + a reboot; if it persists, uncomment the `WLR_DRM_NO_ATOMIC` line in `env.conf` |
| No `z`, `CTRL+R` or `ls` colors | The shell integration was not added: put `[ -f ~/.config/hyprsetup/shell.sh ] && . ~/.config/hyprsetup/shell.sh` in `.bashrc`/`.zshrc` |
| The installer warned about a "partial upgrade" | Run `sudo pacman -Syu` and try again — installing packages after `-Sy` on Arch can break the system |
| I changed something but it does not show | The settings app should have reloaded the daemon; by hand: `hyprctl reload` or `SUPER + CTRL + R`, for waybar `pkill -SIGUSR1 waybar` |
| I cannot select a program in the app (greyed out) | It is not installed. Run the `pacman` command next to it; when applying a profile with a missing program, the app asks and can run the command in your terminal |
| I want to undo everything | `./restore.sh --list` → `./restore.sh <backup-dir>` |

### If the session does not start at all

Switch to a TTY (`Ctrl + Alt + F3`), log in and check:

```bash
tail -40 ~/.local/share/hyprland/hyprland.log
```

```bash
systemd-detect-virt; lspci -k | grep -A3 -iE 'vga|3d'
```

If the screen never comes up but the Hyprland log keeps going, the problem is
not the configuration but the DRM/GPU layer — configuration errors such as
`Invalid dispatcher` do not prevent the session, they only disable the key in
question.

### In a virtual machine

A `getCurrentCRTC: No CRTC` pile-up almost always comes from the virtualized
display driver:

- **VirtualBox** — does not support the atomic modesetting Hyprland needs; in
  practice it does not work. Switching to QEMU/KVM is the fastest fix.
- **QEMU/KVM** — set the display card to `virtio-gpu` (`-vga virtio`, or
  "Video: Virtio" in virt-manager with 3D acceleration on). For testing,
  software rendering:
  ```bash
  WLR_RENDERER_ALLOW_SOFTWARE=1 LIBGL_ALWAYS_SOFTWARE=1 Hyprland
  ```
- **VMware** — the `svga` driver is troublesome; try software rendering.
- In any VM, against a disappearing cursor turn on *Mouse Cursor → Software
  cursor* in the settings app (`NO_HARDWARE_CURSORS="true"`); turning off
  blur and shadows also improves performance noticeably.

If you see the same error on real hardware and the GPU is NVIDIA, install the
`nvidia` component and **reboot** (`nvidia_drm.modeset=1` is written into the
initramfs).

---

## Development

```bash
./tools/test.sh              # every check (lint, data, render matrix)
./tools/test.sh --quick      # skip the render matrix
./tools/test.sh --only lint  # a single group: lint | schema | render
./tools/build-dotfiles.sh --check   # is dotfiles/ up to date?
```

The test suite renders the default configuration (plus every profile in
`presets/profile/`) and verifies that the output has no undefined template
variables, unbalanced Hyprland blocks, broken JSON/TOML/bash/fish, non-monospace
terminal font or machine-specific leaks. It also checks that every id in
`DEFAULT_COMPONENTS` exists in the catalog, that `--dry-run` asks nothing, the
palette contrast enforcement and the bootloader `sed` expressions — if the
last ones break, the machine may not boot.

On a machine with Hyprland installed, the generated configuration is also run
through Hyprland's **own parser** (`Hyprland --verify-config`, for both the
`.conf` and the Lua tree). A misspelled option name or a window rule that does
not exist shows up in no other check — it would surface as a "config error"
when the user logs in.

Adding a theme, a preset or a template requires no code changes:

| To add | Do this |
|---|---|
| A palette | Add an entry to `python/hyprsetup/themes.py` |
| A config file | Drop a `.tmpl` into `templates/` |
| An application | Add an entry to `config/components.json` |
| A setting | A default in `lib/config.sh` + a `Setting` in `python/hyprsetup/settings.py` |

Before the installer has ever run, the settings app can be started from the
repository with `./hyprsetup-gui`.

---

## Requirements

Arch Linux or CachyOS, `bash`, `python3`, `jq`, and an AUR helper for a
handful of optional packages. The settings app additionally needs
`gtk4 libadwaita python-gobject python-cairo`. Do **not** run the installer as
root — it calls `sudo` only where required.

## Third-party code

- The *Wallpaper Colors* page reimplements the idea of
  [ricemood](https://github.com/fhadiel/ricemood) (tag syntax, node-vibrant
  swatches); no code was copied.

## Notes and known limitations

- **Rule syntax:** Hyprland 0.51+ **no longer accepts** the old
  `windowrule = float, class:^(x)$` syntax; the generated files use the new
  form: `windowrule = float on, match:class ^(x)$`. The same goes for
  `layerrule` (`blur on, match:namespace ^(waybar)$`). Use this form when
  writing your own rules in `custom.conf`.
- 82 option names in the generated `hyprland.conf` were verified on a live
  Hyprland 0.56 with `hyprctl getoption`. Before 0.50 some options
  (`rounding_power`, `snap`, `gesture`) do not exist.
- The script **must not be run as root**; it uses `sudo` where needed and
  keeps the sudo session alive during installation.
- The settings app never uses `sudo` and never installs packages behind your
  back; it only writes to your home directory. The one exception is profiles:
  if a program the profile needs (the bar backend, and its engine if it has
  widgets) is not installed, it asks before applying, and if you choose
  “Install and apply” it runs the command **in your terminal** — you enter
  the password there, seeing the command.
- Already installed packages are skipped and existing config files are backed
  up — the script can be run again and again (idempotent).
- If an AUR package fails to build, the installation does not stop; failures
  are listed at the end.
- **NVIDIA:** when the `nvidia` component is selected, `nvidia_drm.modeset=1`
  is set, the `mkinitcpio` modules are added and the initramfs is regenerated.
  These changes **require a reboot**.
- **Login manager:** if a display manager is already enabled, the script warns
  and asks for your confirmation. SDDM is left in X11 mode by default (Wayland
  mode needs a separate compositor, and a wrong configuration can break the
  login).
- If `/etc/pam.d/hyprlock` is missing for `hyprlock`, the script offers to
  create it; without that file the lock screen cannot verify the password.
- If no wallpaper is found and ImageMagick is installed, a plain image in the
  theme's background color is generated.

## License

[MIT](LICENSE) © kanex

The author profiles install other people's dotfiles, which keep their own
licenses (MIT, GPL-3.0, AGPL-3.0, Apache-2.0, OFL-1.1). See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for each source, its pinned
commit and license. Sources with no stated license, and all images, video
and audio over 64 KB, are never shipped in this repository; the installer
downloads them from the author's repo on your machine.
