# Preset Sources — what each preset is based on

This document records two things: which post and which repository each
profile is based on (below), and which setups the bar presets under
`presets/bar/` were derived from by their **measurements**.

---

## Profiles (18)

Each profile builds the desktop from a Reddit post **with the author's own
files** (`python -m hyprsetup rice install <name>`, *Profiles* in the settings
app). The manifest lives in `presets/profile/<name>.rice.toml`: the author's
repository, the commit closest to the post date (full SHA), which folder is
copied where, packages, fixes and the reasons for them. Every distinct look in
the post (each one, if a video shows several) can be selected as a **look**
(variant).
`end4` is the exception: it is based not on a post but on the current state of
the most-starred Hyprland repository on GitHub.
`hyprclouds` is also based not on a post but on the latest commit of the GitHub
repository the user provided (unlicensed: its files do not go into the repo,
they are downloaded from GitHub during installation).

**What was copied and what was not:** for licensed repositories, the installed
paths at the pinned commit ship with the project as an archive under
`vendor/rices/` (`python3 -m hyprsetup rice vendor`); installation looks there
first. For repositories with no stated license, the archive is generated
locally but does not go into git (`vendor/rices/.gitignore`); if it is missing,
it is downloaded from the author's repository at the pinned commit.
Wallpapers were not copied. The authors' install scripts are not run (sudo,
system files, login manager changes, telemetry); the user-level work they do is
rewritten step by step in the manifest.

**Hyprland version:** configuration from old commits is converted to Hyprland
0.56 syntax during installation (`python/hyprsetup/hyprmigrate.py`), and
hyprpaper files to 0.8 syntax; every manifest is checked by Hyprland's own
validator through `rice verify`.

Mentioning a source's name does not imply any affiliation with or endorsement
by that project.

| Profile | Title | Post | Author's repository | License | Looks |
|---|---|---|---|---|---|
| `ad1822` | ad1822 — Peace (Catppuccin Mantle) | [r/hyprland 1n5hl13](https://www.reddit.com/r/hyprland/comments/1n5hl13/its_a_peace_its_my_home/) | [ad1822/hyprdots](https://github.com/ad1822/hyprdots/tree/a92e70a264fce6d2844b0bc59b13533b2d466cc8) @ `a92e70a` | MIT | 2 |
| `athena` | Athena — rebuilt with eww | [r/hyprland 1tyv74j](https://www.reddit.com/r/hyprland/comments/1tyv74j/hyprland_eww_here_is_how_it_looks_now_after_a/) | [haikal-hakim/athena-eww](https://github.com/haikal-hakim/athena-eww/tree/a42d5010233977ecd8ebf928fe0e674567f7e92d) @ `a42d501` | MIT | 4 |
| `brainshell` | Brain Shell — Quickshell (Material You) | [r/hyprland 1u1b2xq](https://www.reddit.com/r/hyprland/comments/1u1b2xq/brain_shell_v010_released/) | [Brainitech/Brain_Shell](https://github.com/Brainitech/Brain_Shell/tree/9c56fca3dc4815df844a50da7bbb1c1a40309018) @ `9c56fca` | MIT | 6 |
| `caelestia` | Caelestia — Quickshell (Material You) | [r/unixporn 1l5ll27](https://www.reddit.com/r/unixporn/comments/1l5ll27/hyprland_i_3_quickshell/) | [caelestia-dots/shell](https://github.com/caelestia-dots/shell/tree/11f0ff76ad5e7eb5bd7f2570aafa984c842df1d5) @ `11f0ff7`<br>+ [caelestia-dots/caelestia](https://github.com/caelestia-dots/caelestia)<br>+ [caelestia-dots/cli](https://github.com/caelestia-dots/cli) | GPL-3.0 | 3 |
| `dhruvsharma` | dhruvsharma — 100% Quickshell | [r/hyprland 1seokvc](https://www.reddit.com/r/hyprland/comments/1seokvc/finally_100_quickshell_rice_now_replaced_rofi_as/) | [dhrruvsharma/shell](https://github.com/dhrruvsharma/shell/tree/95139083cb183e686cdc755bdeec617982eb68c3) @ `9513908` | unspecified | 2 |
| `end4` | end-4 — illogical-impulse (Material You, Quickshell) | — (GitHub, 16k★) | [end-4/dots-hyprland](https://github.com/end-4/dots-hyprland/tree/2f0c8bf42b803f4d597572f2a014d4e78d7d9f26) @ `2f0c8bf`<br>+ [end-4/rounded-polygon-qmljs](https://github.com/end-4/rounded-polygon-qmljs) (Apache-2.0)<br>+ [end-4/google-sans-flex](https://github.com/end-4/google-sans-flex) (OFL-1.1) | GPL-3.0 | 3 |
| `hyprclouds` | hyprclouds — eww, Material You | — (GitHub) | [arfan-on-clouds/hyprclouds](https://github.com/arfan-on-clouds/hyprclouds/tree/dc56aa5563da58ba1fd757c607a8630493686647) @ `dc56aa5` | unspecified | 3 |
| `hyprcraft` | HyprCraft — Coffee at sunset | [r/hyprland 1n8wzk5](https://www.reddit.com/r/hyprland/comments/1n8wzk5/hyprcraft_coffee_at_sunset/) | [zephardev/hyprcraft](https://github.com/zephardev/hyprcraft/tree/9ee55c480faca11eebf4101441028019216590f7) @ `9ee55c4` | MIT | 1 |
| `ilyamiro` | ilyamiro — Fluid (Quickshell + matugen) | [r/unixporn 1s84jik](https://www.reddit.com/r/unixporn/comments/1s84jik/hyprland_as_fluid_as_it_gets/) | [ilyamiro/imperative-dots](https://github.com/ilyamiro/imperative-dots/tree/bd8561bd6115e0adfb3f2ace2d84cc91e521eb82) @ `bd8561b` | unspecified | 9 |
| `ilyamiro-ay` | ilyamiro — Moon launcher (Quickshell + matugen) | [r/hyprland 1thgddl](https://www.reddit.com/r/hyprland/comments/1thgddl/are_we_winning_the_ricing_competition_with_this_one/) | [ilyamiro/imperative-dots](https://github.com/ilyamiro/imperative-dots/tree/eefff2fadceb28b52198175914576fbb55f57695) @ `eefff2f`<br>+ [ilyamiro/hypr-comp](https://github.com/ilyamiro/hypr-comp) | unspecified | 1 |
| `k4` | k4 — Dynamic Island (Quickshell) | [r/hyprland 1vwb5es](https://www.reddit.com/r/hyprland/comments/1vwb5es/my_island_bar_can_now_become_a_dock/) | [k4ditano/k4](https://github.com/k4ditano/k4/tree/aade326358f1e67fc27822d8f053bfc7b7b347fd) @ `aade326` | MIT | 1 |
| `nothingos` | NothingOS — Quickshell (inspired by Nothing OS) | [r/hyprland 1w8zykk](https://www.reddit.com/r/hyprland/comments/1w8zykk/nothingos/) | [0xbbuddha/dotfiles_nothing_os](https://github.com/0xbbuddha/dotfiles_nothing_os/tree/f245629316c810c5ebc9dde8d27421eae9c02838) @ `f245629` | MIT | 1 |
| `pibble` | pibble — launcher (Quickshell, text scramble) | [r/hyprland 1vp93er](https://www.reddit.com/r/hyprland/comments/1vp93er/text_scramble_effect_everywhere/) | [kianblakley/pibble](https://github.com/kianblakley/pibble/tree/915a2f983099eee66a5395d1fa34b4754e3bd5fe) @ `915a2f9` | GPL-3.0 | 1 |
| `r4ppz19` | r4ppz19 — Never going back to Windows (Gruvbox Material) | [r/hyprland 1l1i79c](https://www.reddit.com/r/hyprland/comments/1l1i79c/i_am_never_going_back_to_windows/) | [r4ppz19/Arch-dotfiles](https://github.com/r4ppz19/Arch-dotfiles/tree/6abfebcb6123b86a0428ff63f7d4e01b83131505) @ `6abfebc` | MIT | 2 |
| `saatvik333` | saatvik333 — Rice dungeon (wallust) | [r/hyprland 1mi964w](https://www.reddit.com/r/hyprland/comments/1mi964w/ive_fallen_down_in_the_dungen_help/) | [saatvik333/hyprland-dotfiles](https://github.com/saatvik333/hyprland-dotfiles/tree/3085c4a745fd619a40398661a7da6e34d860ebad) @ `3085c4a` | unspecified | 3 |
| `serpantinum` | Serpantinum — Quickshell desktop shell | [r/hyprland 1th2stg](https://www.reddit.com/r/hyprland/comments/1th2stg/quickshell_can_do_insane_things/) | [ilyamiro/serpantinum](https://github.com/ilyamiro/serpantinum/tree/990615ff0d205d185f0a6ca2f3cc83a8769c380a) @ `990615f` | AGPL-3.0 | 1 |
| `unit3` | Unit-3 — NieR:Automata (Quickshell) | [r/hyprland 1sw71vc](https://www.reddit.com/r/hyprland/comments/1sw71vc/hyprland_quickshell_unit3_nier_automata_inspired/) | [samyns/Unit-3](https://github.com/samyns/Unit-3/tree/bb38216c98340c9767912351b373c91128ced707) @ `bb38216` | MIT | 4 |
| `vantage` | Vantage — Quickshell (pywal) | [r/hyprland 1v2cof0](https://www.reddit.com/r/hyprland/comments/1v2cof0/my_first_rice_with_quickshell/) | [simeulinuxkaliaiwr/vantage](https://github.com/simeulinuxkaliaiwr/vantage/tree/b2c0ced8424d6e4b5e72c79a3f49896afee4262f) @ `b2c0ced` | MIT | 2 |

### Looks and wallpapers (36/49 found)

"Downloaded at install" = downloaded from the source's public address at a
pinned version (not copied into the repo). "Not found" = the image in the post
was searched for and not found, or cannot be distributed; the look still sets
up the author's layout and color flow.

| Profile · look | Title | Wallpaper | Source |
|---|---|---|---|
| `ad1822` · `sis` | Misty pier (grey-lavender) | not found | Source removed (the author's Drive folder) |
| `ad1822` · `bulut` | Sea of clouds | not found | Source removed (the author's Drive folder) |
| `athena` · `mocha` | Catppuccin Mocha (dark) | not found |  |
| `athena` · `latte` | Catppuccin Latte (light) | not found |  |
| `athena` · `tokyo-night` | Tokyo Night (dark) | not found |  |
| `athena` · `tokyo-night-light` | Tokyo Night Light (light) | not found |  |
| `brainshell` · `brain` | BRAIN SHELL — cream (from the post) | in the author's repo | src/assets/wallpapers/brain-shell-default-0.png in the author's repo |
| `brainshell` · `portre` | Blue-haired portrait | in the author's repo | src/assets/wallpapers/brain-shell-default-1.png in the author's repo |
| `brainshell` · `orman` | Green mountain forest | in the author's repo | src/assets/wallpapers/brain-shell-default-2.jpg in the author's repo |
| `brainshell` · `cicekler` | Anime among blue flowers | in the author's repo | src/assets/wallpapers/brain-shell-default-3.jpg in the author's repo |
| `brainshell` · `porsche` | Red Porsche, parking garage | in the author's repo | src/assets/wallpapers/brain-shell-default-4.jpg in the author's repo |
| `brainshell` · `siborg` | Cyborg portrait (dark) | in the author's repo | src/assets/wallpapers/brain-shell-default-5.jpg in the author's repo |
| `caelestia` · `violet` | Violet — light ink drawing (pink-cream) | downloaded at install | Sora's demo wallpapers: violet (post 14) |
| `caelestia` · `raiden` | Raiden — purple swordswoman (dark) | downloaded at install | Sora's demo wallpapers: raiden (post 14) |
| `caelestia` · `room` | Room — neon cyber room (dark) | downloaded at install | Sora's demo wallpapers: room (post 14) |
| `dhruvsharma` · `portre` | Red-grey portrait | downloaded at install | dhrruvsharma/wallpapers — 3qwx1v (Wallhaven), added to the repo the day after the post |
| `dhruvsharma` · `wlop-dans` | WLOP — Dance (purple-orange) | downloaded at install | dhrruvsharma/wallpapers — WLOP "Dance" |
| `end4` · `varsayilan` | Default — dark purple shapes (Tonal Spot) | in the author's repo | The shell's first-launch wallpaper (quickshell/ii/assets/images/default_wallpaper.png) |
| `end4` · `acik` | Light — the same shapes, light theme | in the author's repo | The same image, light mode |
| `end4` · `turuncu` | Orange roses — warm Material (dark) | downloaded at install | A lookalike (the source of the image in the author's "wow look its orange" screenshot is not stated): Orange rose bouquet (Unsplash) — Wikimedia Commons, CC0 |
| `hyprclouds` · `sakura` | Sakura — light, pink | not found | The author's ones (sakura and cat, black cat, mushroom forest, orange flowers) are not in the repo; this project's `st-sakura`, colors derived from it (matugen) |
| `hyprclouds` · `alacakaranlik` | Twilight — dark, purple | not found | This project's `st-alacakaranlik` |
| `hyprclouds` · `orman` | Forest — dark, orange | not found | This project's `st-orman` |
| `hyprcraft` · `merdiven` | Snowy stairs and a cat | not found |  |
| `ilyamiro` · `gunbatimi` | Mountain lake at sunset (lemon) | downloaded at install | ilyamiro/shell-wallpapers (post 15) |
| `ilyamiro` · `pembe-dag` | Snowy pink mountain | downloaded at install | ilyamiro/shell-wallpapers (post 15) |
| `ilyamiro` · `col` | Desert dunes (sand) | downloaded at install | ilyamiro/shell-wallpapers (post 15) |
| `ilyamiro` · `orman` | Misty forest — animated (turquoise) | downloaded at install | ilyamiro/shell-wallpapers (post 7) |
| `ilyamiro` · `kirmizi` | Red anime (ULTRAKILL) | downloaded at install | ilyamiro/shell-wallpapers (post 7) |
| `ilyamiro` · `gol` | Mountain lake (amber) | downloaded at install | ilyamiro/shell-wallpapers (post 7) |
| `ilyamiro` · `bulutlar` | Peaks in a sea of clouds (pink) | downloaded at install | ilyamiro/shell-wallpapers (post 7) |
| `ilyamiro` · `yosemite` | Yosemite valley (turquoise-peach) | downloaded at install | ilyamiro/shell-wallpapers (post 8) |
| `ilyamiro` · `samanyolu` | Snowy mountain under the Milky Way | downloaded at install | ilyamiro/shell-wallpapers (post 8) |
| `ilyamiro-ay` · `ay` | Crescent (olive) — moon launcher | not found | Wallpaper not found: crescent moon + airplane contrail photo (post 5) |
| `k4` · `island` | Island — bar that narrows at the edge, dock mode | not found | Wallpaper unchanged (no wallpaper in the author's repo) |
| `nothingos` · `nothing` | Nothing — matte black, concrete grey, red | in the author's repo | hypr/wallpaper.png in the author's repo (from the post) |
| `pibble` · `pibble` | pibble — launcher, text scramble effect | not found | Wallpaper unchanged (the source of the one in the post was not found) |
| `r4ppz19` · `kiz` | Cream background, girl drawing (hyprpaper default) | in the author's repo |  |
| `r4ppz19` · `iblis-avcisi` | Demon Slayer (white) | in the author's repo |  |
| `saatvik333` · `bataklik` | Cat in the swamp (green) | downloaded at install | MoeWalls — Cat In The Swamp (animated; the installer downloads the site's 720p preview and converts it to a gif like the author does): https://moewalls.com/animal/cat-in-the-swamp-live-wallpaper/ |
| `saatvik333` · `olum-yildizi` | Death Star (blue) | downloaded at install | RockLou — Star Wars: Death Star Wallpaper (DeviantArt, r/StarWars 5gbi6q): https://www.deviantart.com/rocklou/art/Star-Wars-Death-Star-Wallpaper-649222725 |
| `saatvik333` · `localhost` | There's no place like 127.0.0.1 (black-green) | downloaded at install | dovah — There's no place like 127.0.0.1 (Wallpaper Abyss 426359): https://wall.alphacoders.com/big.php?i=426359 |
| `serpantinum` · `pembe` | Pink flat mountains | downloaded at install | ilyamiro/shell-wallpapers (post 3) |
| `unit3` · `orman` | Forest — 2B and a mossy machine (from the post) | in the author's repo | assets/wallpapers in the author's repo (NieR:Automata art); the one in the post's preview |
| `unit3` · `yorha` | YoRHa — dark emblem | in the author's repo | assets/wallpapers/UDqXyQq.jpeg in the author's repo |
| `unit3` · `hollow-knight` | Hollow Knight — Vincent Bisschop | in the author's repo | assets/wallpapers in the author's repo (Vincent Bisschop, Hollow Knight fan art) |
| `unit3` · `savas` | 2B — red battle scene | in the author's repo | assets/wallpapers/wallpaperflare.com_wallpaper.jpg in the author's repo |
| `vantage` · `fuuka` | Fuuka Yamagishi — mint (animated) | downloaded at install | MoeWalls — Fuuka Yamagishi Persona 3 Reload Live Wallpaper: https://moewalls.com/anime/fuuka-yamagishi-persona-3-reload-live-wallpaper/ |
| `vantage` · `ken` | Ken Amada — orange (animated) | downloaded at install | MoeWalls — Ken Amada Persona 3 Reload Live Wallpaper: https://moewalls.com/anime/ken-amada-persona-3-reload-live-wallpaper/ |

Record of the 23 old (palette-based) profiles: `docs/archive/profiles-v2/` and
[`gallery-catalog.md`](gallery-catalog.md).

### Gallery images: the authors' own screenshots (2026-10-04)

Most of the images on the gallery cards (`presets/profile/<profile>.variants/<look>.jpg`)
were captured live on this machine. The live captures of the ones below were
broken (wallpaper not loaded, black screen, a menu left open, or a copy of
another look); they were replaced with the image from the author's OWN
repository or post (cropped to 1280x720):

| Profile · look | Source |
|---|---|
| `ad1822` · `sis` | [ad1822/hyprdots@a92e70a](https://github.com/ad1822/hyprdots/blob/a92e70a264fce6d2844b0bc59b13533b2d466cc8/Assets/main-2.png) `Assets/main-2.png` |
| `ad1822` · `bulut` | [ad1822/hyprdots@a92e70a](https://github.com/ad1822/hyprdots/blob/a92e70a264fce6d2844b0bc59b13533b2d466cc8/Assets/wallpicker.png) `Assets/wallpicker.png` |
| `athena` · `mocha`, `tokyo-night` | [haikal-hakim/athena-eww](https://github.com/haikal-hakim/athena-eww) README screenshots |
| `end4` · `varsayilan`, `turuncu` | [end-4/dots-hyprland](https://github.com/end-4/dots-hyprland) `.github/README.md` screenshots |
| `hyprclouds` · `sakura`, `alacakaranlik`, `orman` | [arfan-on-clouds/hyprclouds](https://github.com/arfan-on-clouds/hyprclouds) `workflow&assets/` screenshots — with the author's own wallpapers (no live capture was made) |
| `hyprcraft` · `merdiven` | The author's [Reddit gallery](https://www.reddit.com/r/hyprland/comments/1n8wzk5/) (no screenshot in the repo) |
| `ilyamiro-ay` · `ay` | A frame from the author's [Reddit video](https://www.reddit.com/r/hyprland/comments/1thgddl/) |
| `k4` · `island` | A frame from the author's [Reddit video](https://www.reddit.com/r/hyprland/comments/1vwb5es/) |
| `r4ppz19` · `iblis-avcisi` | [r4ppz19/Arch-dotfiles@6abfebc](https://github.com/r4ppz19/Arch-dotfiles/blob/6abfebcb6123b86a0428ff63f7d4e01b83131505/screenshot/screenshot_2025-06-02_20-39-54.png) (wallpaper `wallpaper2.png`) |
| `vantage` · `ken` | [simeulinuxkaliaiwr/vantage](https://github.com/simeulinuxkaliaiwr/vantage) README — with the author's own wallpaper; there is no screenshot with the Ken Amada wallpaper |

Still live captures: `athena` · `latte` / `tokyo-night-light` (the author has no
light theme screenshot; the background came out black). There is no image for
`end4` · `acik`; the card falls back to the schematic.

---

## Bar presets (14 new)

The ones below were added in this round. The other presets under
`presets/bar/` come from the screenshot generation in `gallery-catalog.md`.

Bar presets are **numeric measurements only** (gaps, corner radius, border,
blur, bar height, module layout): none of the source's files, CSS or scripts
were taken into the repo; colors come from this project's palettes and the
styling is built by this project's own templates.

| Bar preset | Title | Program | Source | Measurements |
|---|---|---|---|---|
| `caelestia` | Caelestia — Fluid Shell | Quickshell | [caelestia-dots/shell](https://github.com/caelestia-dots/shell) | A tall, heavily rounded floating bar with margins from the edges; media in the center, a workspace capsule on the left. |
| `illogical-impulse` | Illogical Impulse — Material 3 | Quickshell | [end-4/dots-hyprland](https://github.com/end-4/dots-hyprland) | Material Design 3 measurements: medium height, large corner radius, clock in the center, a cluster of counters on the right. |
| `jakoolit-simple-l` | JaKooLit — Simple-L | Waybar | [JaKooLit/Hyprland-Dots](https://github.com/JaKooLit/Hyprland-Dots) — "Simple-L [TOP]" | Workspaces + window on the left, clock in the center, tray and power button as capsules on the right; thin margin and medium… |
| `hyde-wallbash` | HyDE — Wallbash | Waybar | [prasanthrangan/hyprdots (HyDE)](https://github.com/prasanthrangan/hyprdots) | Power button on the left with a workspace capsule next to it; rounded module groups on the right. Colors from the wallpaper… |
| `ml4w-glass` | ML4W — Glass in the Center | Waybar | [mylinuxforwork/dotfiles (ML4W)](https://github.com/mylinuxforwork/dotfiles) | ML4W's signature: workspaces in the CENTER, a tall semi-transparent (glass) bar with margins from the edges. On the left, power and… |
| `cyberarch-hud` | CyberArch — HUD | Waybar | [ARCANGEL0/CyberArch-Shell](https://github.com/ARCANGEL0/CyberArch-Shell) | A dense, cornerless, fully opaque HUD strip: CPU, memory, temperature, network traffic and disk side by side on the right. |
| `gruvbox-solid` | Gruvbox — Solid Block | Waybar | [Pipshag/dotfiles_gruvbox](https://github.com/Pipshag/dotfiles_gruvbox) | No transparency and no rounding: a single-piece, fully opaque, square-cornered bar. The classic Waybar layout of retro gruvbox rices. |
| `catppuccin-pills` | Catppuccin — Pills | Waybar | [catppuccin/waybar](https://github.com/catppuccin/waybar) + [Srinath10X/catppuccin-waybar](https://github.com/Srinath10X/catppuccin-waybar) | The bar has no background of its own; each module group is a separate capsule. Large rounding, tuned to the pastel palette… |
| `sameemul-islands` | Island Layout — Catppuccin | Waybar | [sameemul-haque/dotfiles](https://github.com/sameemul-haque/dotfiles) | Three separate islands: workspaces on the left, window title in the center, media + counters + clock on the right. |
| `eclipse-sidebar` | Eclipse — Left Panel | Waybar | Arch Eclipse left panel | A rounded vertical panel with margins on the left: workspace dots at the top, tray, volume, battery and a two-line clock at the bottom. |
| `gdots-rail` | Gdots — Icon Rail | Waybar | Gdots vertical icon rail | A narrow, cornerless, fully opaque left rail; only occupied workspaces and a few icon-sized indicators. |
| `colorshell-dock` | Colorshell — Bottom Dock | Waybar | Colorshell bottom dock | A heavily rounded dock at the bottom of the screen with margins from the edges; workspaces with app icons in the center, on the right… |
| `rainz-nebula` | Nebula — Sparse and Transparent | Waybar | Rainz's Hyprland | Almost invisible: high transparency, wide gaps, an underlined workspace indicator and only four modules.… |
| `binnewbs-compact` | Compact Arch | Waybar | [binnewbs/arch-hyprland](https://github.com/binnewbs/arch-hyprland) | Low, slightly rounded and tightly spaced; workspaces + window on the left, tray with an update counter on the right. |

---

## Widget layouts (8)

`presets/widget-set/` — a layout sets **which widgets are on, which corner
they land in, and their measurements** (margin, spacing, scale, radius,
opacity) together. In the settings app: *Widgets → Preset layouts*, or
`WIDGET_SET="<name>"` in `settings.conf`.

Not to be confused with `presets/widget/`: that is a definition file PER widget
(name, description, requirements); this is the whole layout.

| Set | Title | Layout | Source |
|---|---|---|---|
| `minimal` | Plain — clock only | TR: clock | nord-frost · alpine-paper line |
| `dashboard` | Dashboard — all four corners filled | TL: fetch · TR: clock+calendar · BL: music · BR: counters | widget-desk profile · videoframe_1997 (NERV) · videoframe_2322 (DOOM) |
| `media` | Media corner | BL: music · BR: volume | [caelestia-dots/shell](https://github.com/caelestia-dots/shell) · [hyper-caelestia-rice](https://github.com/uryastra-beep/hyper-caelestia-rice) |
| `laptop` | Laptop | TR: clock+battery · BR: brightness+volume+network+keyboard | [ML4W](https://github.com/mylinuxforwork/dotfiles) · [JaKooLit](https://github.com/JaKooLit/Hyprland-Dots) indicator cluster |
| `monitor` | System monitoring | TR: cpu/ram+temperature · BR: disk+uptime+network | [ARCANGEL0/CyberArch-Shell](https://github.com/ARCANGEL0/CyberArch-Shell) · kde-sunday · cosmic |
| `material` | Material 3 | TL: clock · BR: music+volume | [end-4/dots-hyprland](https://github.com/end-4/dots-hyprland) · pphan-sil eww MD3 panel |
| `traveler` | World clocks | TR: clock+world clocks · BL: calendar | videoframe_1141 (world-clocks observation) |
| `showcase` | Showcase — everything on | 15 widgets spread across the four corners | this project's own widget catalog |

The measurements and layout are derived from the sources; **no files, QML/yuck
code or images were copied** — the "what was not copied" rule at the start of
this document applies to widget sets too.

A widget is silently not drawn while the component it requires (e.g. `music` →
`audio-tools`) is not selected; the set's row in the UI says so with a
"Missing component: …" note. `tools/test.sh` verifies that each set uses only
widgets from the catalog and writes only names enabled in that set into the
corners.

---

## Where the styling comes from

A bar preset's file carries only NUMBERS (height, gaps, radius, opacity,
module list). The STYLING that makes the source recognizable lives in its own
block in the template — `{{#if BAR_IS_<NAME>}} … {{/if}}` in
`templates/waybar/style.css.tmpl`, and `templates/quickshell/shell.qml.tmpl`
for the Quickshell presets. Examples:

| Preset | Distinctive styling in the template |
|---|---|
| `jakoolit-simple-l` | Each module in its own rounded capsule; the power button a red full circle, modules in different palette colors, a glow on the active workspace |
| `hyde-wallbash` | A fully round power button on the left; on the right, system modules lined up flush in a SINGLE capsule with rounded ends |
| `ml4w-glass` | Semi-transparent glass background + a thin top highlight; workspaces in the center and larger than the other modules |
| `cyberarch-hud` | Cornerless; an accent line under each module, spaced uppercase typography, counters in a monospaced font |
| `gruvbox-solid` | A single-piece opaque background, a 1px vertical separator between modules, a 2px accent strip underneath |
| `catppuccin-pills` | No bar background; each module fully rounded and in its own pastel color |
| `sameemul-islands` | Three islands; the modules INSIDE an island have no background, with thin separators between them |
| `eclipse-sidebar` | A rounded vertical panel, horizontal separators between groups, a two-line clock |
| `gdots-rail` | A narrow icon rail; the active workspace is a thick marker line on the left edge |
| `colorshell-dock` | A floating dock at the bottom; large icons that bounce up on hover |
| `rainz-nebula` | Almost invisible; wide letter spacing, a soft glow on the active workspace |
| `binnewbs-compact` | Tight padding, slight rounding, a yellow update counter |
| `caelestia` | QML: the background is not the whole bar but a fully rounded "island" floating in the center; the active workspace is an elongating capsule |
| `illogical-impulse` | QML: a full-width M3 background + a bottom divider line; the active workspace is a widening pill |

The same styling is also reflected in the **preview on the gallery card**
(`python/hyprsetup/gui/preview.py:BAR_PREVIEW_SHAPES`): the card draws the
capsule, bare text, separator, underline, island or square bracket; in vertical
presets the modules are stacked. As long as the preview only drew the
measurements, all presets looked like the same row of grey boxes.

`tools/test.sh` checks all three directions: every name in `BAR_STYLES` must
have a block in the template, every block in the template must have a bar
preset ("bar preset template blocks in place"), and every preset with its
own template block must also have a shape in the preview ("gallery previews
tell the presets apart").

---

## Palette mapping

Profiles take their colors from the author's own setup; most generate them from
the wallpaper (matugen, wallust, pywal, materialyoucolor), and the author's
script recomputes the palette when the look changes. `THEME="auto"` in the
profile's `.conf` file makes sure this project's own parts (the gallery card,
components the author does not install) also match the wallpaper when the
profile is applied. For bar presets the palette is a separate axis: *Appearance
→ Theme* in the settings app.
