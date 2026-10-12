# Settings Guide — where each feature is configured

Some features in this project had no trace at all in the settings app (MOD+I):
the config was generated, the service installed, the keybinding worked — but
the only way to change the value was to hand-edit
`~/.config/hyprsetup/settings.conf`, or to tinker with the generated file
(only to lose the change on the next apply). This document collects in one
table where each feature is configured, and says which ones have **no
settings on purpose**.

Page names are the tabs in the settings app's left column
(`hyprsetup`, or panel mode via `MOD + I`).

---

## 1. Newly exposed in the UI

All of these already worked; the only thing missing was the UI.

| Feature | Program | Setting | Page |
|---|---|---|---|
| Dim when idle | brightnessctl | `IDLE_DIM` | Session → Idle and lock |
| Auto lock | hyprlock | `IDLE_LOCK` | Session → Idle and lock |
| Turn off the screen (DPMS) | hypridle | `IDLE_DPMS` | Session → Idle and lock |
| Suspend | systemd | `IDLE_SUSPEND` | Session → Idle and lock |
| Time-based screen filter | hyprshade | `NIGHT_SHADER`, `NIGHT_SHADER_START`, `NIGHT_SHADER_END` | Session → Night light |
| Night light temperature (MOD+SHIFT+N) | hyprsunset | `NIGHT_TEMP` | Session → Night light |
| Screen recording | gpu-screen-recorder | `RECORD_DIR`, `RECORD_FPS`, `RECORD_AUDIO` | Session → Screen recording |
| Instant replay (ShadowPlay) | gpu-screen-recorder | `REPLAY_SECONDS` | Session → Screen recording |
| Wallpaper rotation | systemd timer | `WALLPAPER_ROTATE`, `WALLPAPER_DIR` | Appearance → Wallpaper |
| Wallpaper transition effect | swww | `SWWW_TRANSITION`, `SWWW_TRANSITION_DURATION`, `SWWW_TRANSITION_FPS` | Appearance → Wallpaper |
| Component on/off (hyprsunset, swayosd, cava, wlogout, clipboard, plugins…) | — | `COMPONENTS` | Components |
| ALT+Tab window switcher | `hyprsetup switcher` (GTK4) + grim | `SWITCHER_ENABLED`, `WINDOW_SWITCHER`, `SWITCHER_THUMBS`, `SWITCHER_THUMB_WIDTH`, `SWITCHER_ANIM`, `SWITCHER_PRELOAD`, `SWITCHER_SCOPE`, `SWITCHER_SORT`, `SWITCHER_SHOW_WORKSPACE`, `SWITCHER_SPECIAL` | Behavior → Window switcher |
| Lock screen look | hyprlock | `LOCK_BACKGROUND`, `LOCK_BLUR_*`, `LOCK_BRIGHTNESS`, `LOCK_CLOCK_*`, `LOCK_SHOW_DATE`, `LOCK_DATE_FORMAT`, `LOCK_SHOW_USER`, `LOCK_INPUT_WIDTH`, `LOCK_PLACEHOLDER`, `LOCK_GRACE` | Session → Lock screen |
| Idle details | hypridle | `IDLE_DIM_LEVEL`, `IDLE_KBD_BACKLIGHT`, `IDLE_LOCK_BEFORE_SLEEP`, `IDLE_RESPECT_INHIBIT` | Session → Idle and lock |
| Notification position, duration, size | mako · dunst · swaync | `NOTIFY_POSITION`, `NOTIFY_TIMEOUT`, `NOTIFY_CRITICAL_STICKY`, `NOTIFY_WIDTH`, `NOTIFY_MAX_VISIBLE`, `NOTIFY_MARGIN`, `NOTIFY_ICON_SIZE` | Session → Notifications |
| Power menu | wlogout · powermenu.sh | `POWERMENU_HIBERNATE`, `POWERMENU_CONFIRM` | Session → Power menu |
| Recording format and screenshot folder | gpu-screen-recorder · grim | `RECORD_FORMAT`, `RECORD_CODEC`, `RECORD_QUALITY`, `RECORD_CURSOR`, `SCREENSHOT_DIR` | Session → Screen recording and screenshots |
| Tabbed window groups | Hyprland `group`/`groupbar` | `GROUPBAR`, `GROUPBAR_STYLE`, `GROUPBAR_HEIGHT`, `GROUPBAR_FONT_SIZE` (keybindings ready on the Keybindings page as "unassigned") | Behavior → Window groups |
| Plugin settings | hyprexpo · hyprbars | `HYPREXPO_COLUMNS`, `HYPRBARS_HEIGHT`, `HYPRBARS_BUTTONS` | Behavior → Hyprland plugins |
| Preset window rules, PiP and quick panel size | Hyprland | `RULE_SUPPRESS_MAXIMIZE`, `RULE_FLOAT_TOOLS`, `RULE_PIP`, `PIP_WIDTH`, `QUICK_PANEL_WIDTH`, `QUICK_PANEL_HEIGHT` | Behavior → Behavior |
| Bar auto-hide distances, weather refresh | bar-autohide · wttr.in | `BAR_AUTOHIDE_TRIGGER`, `BAR_AUTOHIDE_RELEASE`, `WEATHER_REFRESH` | Status Bar |
| Rice transition animation | `transition.py` | `RICE_TRANSITION` (previously only the `HYPRSETUP_TRANSITION=0` env var) | Appearance → Animation |
| Hyprland config language | conf / lua | `HYPR_LANG` (advanced mode) | Behavior → Environment |

Three behavior notes:

* **The hypridle timeouts were HARD-CODED in the template** (150/300/330/1800 s).
  `templates/hypr/hypridle.conf.tmpl` now reads these four values, and setting
  one to 0 removes that `listener` block entirely — that is all it takes to
  turn off "suspend" on a desktop machine.
* **The night light did not work just by writing a file:** the schedule is
  driven by a systemd user timer. The settings app now runs `hyprshade
  install` + `systemctl --user enable --now hyprshade.timer` itself, and
  stops the timer when the filter is turned off
  (`python/hyprsetup/apply.py:_sync_night_shader`).
* The same applied to **wallpaper rotation**: writing the unit files was not
  enough, the timer had to be enabled; and when rotation was turned off, no
  file changed, so the timer kept running. Both are fixed
  (`_sync_wallpaper_timer`).

### Why the window switcher is our own script

The desired behavior: when an app is picked with ALT+Tab, **switch to the
workspace that app is on.** In Hyprland that is a single command:

```bash
hyprctl dispatch focuswindow address:0x...   # switches there if the window is on another workspace
```

Existing apps were surveyed and **not taken as dependencies**:

| Project | Status | Why not |
|---|---|---|
| [hyprshell](https://github.com/h3rmt/hyprshell) (formerly hyprswitch) | AUR: `hyprshell`, `hyprshell-bin` · MIT · ~593 stars | Not in the official repos, single maintainer, 5/4 votes on the AUR; needs a **permanently running background process** (systemd service or exec-once); builds against Hyprland ≥ 0.55 and Rust 1.92. It was also renamed recently; the old `hyprswitch` AUR package now points to **someone else's fork** (fragmentation). |
| hypr-altswitch · hyprspace · hypr-alttab · hypr-swap | GitHub only, unpackaged, very new | No package, no release, not reviewed. |
| alttab · sway-alttab | X11 / Sway specific | Do not work on Hyprland. |

Instead we have our own switcher. It has two modes:

**`overlay` (default)** — a GTK4 window: a **live snapshot** of each window,
with the app icon, a workspace badge and the title on top.
It behaves like the Windows/KDE alt-tab: Tab moves forward, Shift+Tab goes
back, **releasing ALT** switches to the selected window, Esc cancels, 1-9
pick directly, and mouse clicks work too. Code: `python/hyprsetup/gui/switcher.py`,
window class `dev.hyprsetup.Switcher` (windowrules make it floating and
centered).

Thumbnails are taken with **`grim -T <stableId>`**. Hyprland 0.56 offers the
`ext-image-copy-capture` + `ext-foreign-toplevel-image-capture-source`
protocols and grim 1.5 uses them, so a window can be captured even when it is
on ANOTHER workspace, i.e. not visible on screen at all
(do not confuse this with `grim -g` — that only captures the region visible
at that moment). Capture takes ~50 ms per window, so the switcher opens with
icons first and the images arrive in the background. Without grim only the
icon is drawn; the keybinding still works.

Only one instance runs at a time. Pressing Tab again while ALT is held does
not open a new window; the request is written to a counter file
(`$XDG_RUNTIME_DIR/hyprsetup-switcher.queue`), which the open window reads
every 40 ms to move the selection. Two details of this path are deliberate:

* **The lock is taken BEFORE GTK.** If the GTK app wrote the lock it would be
  ~150 ms late, and two quick Tabs would start TWO switchers: one makes the
  selection and closes, the other hangs invisibly on the workspace it opened
  on, and every later ALT+Tab would move its selection instead. The lock is
  taken by `windowswitch.py`, and since `os.execvp` keeps the PID, the same
  lock also holds for the GTK process.
* **A file, not a signal.** The default action of SIGUSR1 is to TERMINATE
  the process; a signal arriving before GTK installed its own handler killed
  the switcher while it was still opening.

The switcher closes itself in three cases: when a selection is made, when it
loses focus, and **when the workspace changes** (it listens on Hyprland's
event socket). If an instance is left behind on another workspace, a new
ALT+Tab closes it and opens a fresh one on the workspace you are on.

**Animation** is chosen with `SWITCHER_ANIM` (*Behavior → Window switcher*):
`none` (default, fastest), `popin`, `slide`. The rule is generated at render
time, because in Hyprland disabling and choosing are TWO SEPARATE fields:
`no_anim on` ↔ `animation <style>`. **Writing `animation none` does not
work** — Hyprland silently ignores a style name it does not know and falls
back to the default animation, and the config still looks error-free.

### Startup speed

Measured time from key press to the window being on screen:

| Setup | Time |
|---|---|
| First version (exec + argparse + animation) | ~315 ms |
| Current one-shot mode | **~260 ms** |
| `SWITCHER_PRELOAD=true` | **~90 ms** |

In one-shot mode almost all of it is fixed cost: python startup ~20 ms,
`gi` + GTK4 + libadwaita **~95 ms**, window setup + mapping ~120 ms.
What was trimmed: the script no longer runs the app as a separate process but
**hands over** to it in-process (separate python + bash wrapper + argparse ≈ 45 ms);
three `hyprctl` calls were merged into one with `--batch` (~7 ms); icons are
read directly from `<class>.desktop` first, and scanning all .desktop files
(~13 ms) is only the last resort.

**Preloading** (`SWITCHER_PRELOAD=true`) moves this fixed cost to session
start: an invisible instance starts at login (`exec-once`), and ALT+Tab only
sets up the window. The price is ~68 MB of memory while idle, so it is off by
default. Requests go through the lock/counter files, so the process the
keybinding launches never loads GTK; it bumps the counter and exits.

**`menu`** — for those who do not want GTK: the same list, as plain text in
the selected launcher's dmenu mode. `~/.config/hypr/scripts/windowswitch.py`
carries both modes; if the overlay cannot open (app not installed, GTK
missing) it falls back to this list on its own.

Behaviors borrowed from hyprshell: **MRU ordering** (first entry is the
"previous window", the focused window comes last), grouping by workspace,
hiding special (scratchpad) windows.

`ALT + \`` switches straight back to the last used window without opening
any UI.

---

## 2. The Components page

The single-choice axes (terminal, bar, launcher, notification daemon, file
manager, wallpaper backend) had their own pages. None of the **multi-choice**
categories were in the UI, even though this tool generates config for them:

`hyprsunset` · `swayosd` · `hyprland-extras` (hyprshade, hyprpicker) ·
`hyprlock` · `hypridle` · `wlogout` · `clipboard` · `screenshot-base` ·
`screenshot-annotate` · `screen-record` · `instant-replay` · `matugen` ·
`plymouth` · `firefox-theme` · `discord-theme` · `spicetify` · `cava` ·
`starship` · `fastfetch` · `nwg-displays` · `hyprmod` · hyprpm plugins
(`hyprexpo`, `hyprbars`, `borders-plus-plus`, `hyprtrails`, `hy3`)

On the Components page each one is a switch. Rules:

* **Turning a switch off** stops generating that component's config;
  existing files are not deleted (no backup needed, and they don't come back
  once you delete them).
* **Turning a switch on** does not install the package — this app never asks
  for sudo. If the package is not installed the switch is inactive and the
  row shows a copyable `pacman` command.
* **hyprpm plugins** are not pacman packages: they are built from source.
  Selecting them here only generates `plugins.conf`; building them needs
  `./install.sh`.

---

## 3. No settings on purpose

There is no "missing setting" here; there is nothing to configure.

| Program | Why |
|---|---|
| kitty · alacritty · foot · ghostty · wezterm | The `TERM_*` settings on the Terminal page (opacity, padding, font size, cursor, scrollback) apply to all of them at once; colors are generated from the palette. |
| btop · fastfetch · starship · yazi · dolphin | They only follow the theme; their own behavior settings are out of this project's scope. |
| discord-theme (Vencord) · spicetify · firefox-theme | The app's own settings live in its own UI; only the palette is applied from here. |
| swayosd · wlogout/mako/dunst/swaync colors | Color and corner rounding are derived from the palette and the `BAR_RADIUS`/`FONT_*` settings. Notification position/duration/size and the power menu buttons are configurable now, though (see §1). |
| pipewire · networkmanager · bluetooth · xdg-dirs · archive · dev-tools · gaming | No config is generated; the package is installed and the service enabled. |

---

## 4. Changed only by the installer (root)

The settings app never asks for the root password, so the following are left
out on purpose: they are changed with `./install.sh`.

| Setting | What it does |
|---|---|
| `LOGIN_MANAGER` | Login manager (sddm / ly / greetd) — a system service. |
| `SDDM_BACKGROUND` | Login screen background. |
| `PLYMOUTH_THEME` | Boot animation theme (requires regenerating the initramfs). After installation it is changed in **Login Screen → Boot animation**: the page does not perform the root step itself, it runs `./install.sh --plymouth <theme>` in a terminal. Community themes come from `presets/login/plymouth.toml` (generated by `tools/plymouth-catalog.py`); the *My own theme* tab builds the theme under `~/.cache/hyprsetup/plymouth-custom` and installs it as `souprland-ozel`. |
| `AUR_HELPER`, `CHAOTIC_AUR`, `COMPILE`, `PKG_SKIP` | Package installation policy. |

`HYPR_LANG` now lives under Behavior → Environment and is visible only in
advanced mode. The default, "Automatic", is resolved from the installed
Hyprland version (`lib/preflight.sh:preflight_detect_hypr_lang`); pinning
`conf`/`lua` by hand can break after an upgrade, so it should only be used
while troubleshooting.

---

## 5. Why widgets were not visible (and how they show up now)

Widgets were drawn on the **bottom** layer of `wlr-layer-shell`: above the
wallpaper, **below the windows**. On a tiling desktop the screen is almost
always covered by windows, so in practice the widgets were only visible on an
empty workspace — in real use, never. (We measured it: with 15 widgets open,
`hyprctl layers` shows all of them on "bottom", and not a single box appears
in a screenshot.)

Three settings fix this (*Widgets* page):

| Setting | What it does |
|---|---|
| **Layer** (`WIDGET_LAYER`) | `bottom` = on the desktop (old behavior) · `top` = above windows |
| **Show at startup** (`WIDGET_AUTOSTART`) | When off, widgets are not shown at login, only opened via the keybinding |
| **Display** (`WIDGET_MONITOR`) | Index (0, 1…). A name also works, but it is the **model** name eww sees ("MSI G2412F"), **not** Hyprland's connector name (`DP-1`) — if that is given, eww never opens the window. |

And a keybinding: **`SUPER + G`** toggles the widgets
(`~/.config/hypr/scripts/widgets.sh`). The natural use is: layer `top`,
show at startup off, peek and close with the keybinding. The script actually
waits for the `eww daemon` to be ready (the autostart line used to rely on a
fixed `sleep 1`) and opens the windows with a single `eww open-many` call —
previously there was one `exec-once` line per widget, i.e. 15 shell + 15
client processes.

Two visual bugs fixed in the same pass: the workspace box was declared
smaller than its real height, so it overlapped the calendar (140×44 →
140×64), and the keyboard layout widget cut long names off as `English (…`
(it now shows the part before the parenthesis).

## 6. Widget set presets

The corner editor on the Widgets page is powerful but a blank canvas. The
eight ready-made layouts under `presets/widget-set/` answer "which widget
goes where" with the arrangements of well-known setups: `minimal`,
`dashboard`, `media`, `laptop`, `monitor`, `material`, `traveler`,
`showcase`. A set writes the widget list, the corner layout and the sizes
together (`WIDGET_SET`); after applying it you can change it however you like
in the corner editor. Source table:
[`preset-sources.md`](preset-sources.md).

## 7. Finding a setting: search

The box at the top left of the settings app searches **all settings** by
name, schema key (e.g. `BLUR_SIZE`), help text and group name.
The query is split into words and all of them must match — typing "alt tab"
brings up the settings that mention `ALT+Tab`, "bar height" goes straight to
the bar height. Matching is case-insensitive.

Clicking a result (or pressing Enter) **opens that page, scrolls the row into
view and highlights it for two seconds**. Places that are not in the schema
but have their own dedicated UI are listed too: display layout, keybindings,
components, default applications, profiles, system check.

`tools/test.sh` verifies that **every** setting in the schema is in the
index: if a new setting is added without entering search, the test fails.

## 8. Seeing where a setting comes from

* `./install.sh --doctor` — also tells you who manages which file
  (e.g. if nwg-displays generated `monitors.conf`, it is left alone).
* `config/settings.conf.example` — all 313 settings, each documented line by
  line.
* The settings app and `settings.conf` read/write **the same file**; there
  is no second source of truth between them.
