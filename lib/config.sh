# shellcheck shell=bash
# config.sh — default settings and loading of the user configuration
#
# Every variable added to CONFIG_VARS is passed to the templates automatically
# (see the RENDER_VARS list in lib/render.sh) and written by config_save to
# ~/.config/hyprsetup/settings.conf.

[[ -n "${_CONFIG_SH_LOADED:-}" ]] && return 0
_CONFIG_SH_LOADED=1

# All settings passed to the templates and saved to settings.conf.
# The order determines the order in the generated settings.conf.
#
# INSTALL-TIME SETTINGS DO NOT GO HERE. settings.conf is the file the settings
# app (MOD+I) reads and writes; keeping something there that cannot be changed
# from the app is misleading — the user edits the line and nothing happens.
# That is why AUR_HELPER, COMPILE, PKG_SKIP, ENABLE_SERVICES, OVERWRITE_CONFIGS,
# SDDM_BACKGROUND, PLYMOUTH_THEME and LOGIN_MANAGER are NOT listed below;
# their defaults live in config_defaults and are only read by install.sh
# and modules/*. PROFILE/PRESET are absent for the same reason: the profile
# axis was removed (see presets/profile/.gitkeep).
CONFIG_VARS=(
    # general
    HYPR_LANG
    # appearance
    THEME PALETTE_BACKEND CUSTOM_COLORS PALETTE_HUE PALETTE_SATURATION
    PALETTE_LIGHTNESS COLOR_SCHEME CURSOR_THEME CURSOR_SIZE GTK_THEME_NAME
    THEME_SCHEDULE THEME_DAY THEME_NIGHT THEME_DAY_START THEME_NIGHT_START
    ICON_THEME_NAME FONT_FAMILY FONT_MONO FONT_SIZE
    # status bar
    BAR_PRESET
    BAR_POSITION BAR_HEIGHT BAR_WIDTH BAR_MARGIN BAR_SPACING BAR_PADDING
    BAR_RADIUS BAR_OPACITY BAR_CLOCK_FORMAT BAR_CLOCK_FORMAT_ALT
    BAR_WORKSPACE_STYLE BAR_ICON_STYLE
    BAR_WINDOW_MAX_LENGTH BAR_MODULES_LEFT BAR_MODULES_CENTER BAR_MODULES_RIGHT
    BAR_AUTOHIDE WEATHER_LOCATION WEATHER_UNIT
    BAR_AUTOHIDE_TRIGGER BAR_AUTOHIDE_RELEASE WEATHER_REFRESH
    BAR_CUSTOM1_CMD BAR_CUSTOM1_FORMAT BAR_CUSTOM1_INTERVAL BAR_CUSTOM1_CLICK
    BAR_CUSTOM2_CMD BAR_CUSTOM2_FORMAT BAR_CUSTOM2_INTERVAL BAR_CUSTOM2_CLICK
    BAR_CUSTOM3_CMD BAR_CUSTOM3_FORMAT BAR_CUSTOM3_INTERVAL BAR_CUSTOM3_CLICK
    # widgets
    WIDGET_ENGINE WIDGETS
    WIDGET_SET
    WIDGET_ZONE_TL WIDGET_ZONE_TC WIDGET_ZONE_TR
    WIDGET_ZONE_BL WIDGET_ZONE_BC WIDGET_ZONE_BR WIDGET_OFFSETS
    WIDGET_MARGIN WIDGET_GAP WIDGET_SCALE WIDGET_RADIUS WIDGET_OPACITY
    WIDGET_LAYER WIDGET_MONITOR WIDGET_AUTOSTART
    VIS_ENABLE VIS_MODE VIS_COLOR VIS_BRIGHTNESS VIS_HEIGHT VIS_WIDTH VIS_MONITOR
    DOCK_ENABLE DOCK_POSITION DOCK_AUTOHIDE DOCK_ICON_SIZE DOCK_MARGIN
    DOCK_RADIUS DOCK_OPACITY DOCK_LAUNCHER DOCK_MONITOR
    # terminal
    TERM_PRESET TERM_OPACITY TERM_PADDING TERM_FONT_SIZE TERM_CURSOR_STYLE
    TERM_CURSOR_BLINK TERM_SCROLLBACK
    TERM_FETCH TERM_LOGO TERM_LOGO_IMAGE TERM_LOGO_STYLE TERM_LOGO_MONO
    TERM_LOGO_WIDTH TERM_FETCH_INFO
    TERM_BG_IMAGE TERM_BG_DIM TERM_BG_FIT
    # application launcher
    LAUNCHER_PRESET LAUNCHER_WIDTH LAUNCHER_LINES LAUNCHER_POSITION
    LAUNCHER_OPACITY LAUNCHER_ICONS LAUNCHER_ICON_SIZE LAUNCHER_PROMPT
    LAUNCHER_RADIUS LAUNCHER_BORDER LAUNCHER_PROVIDERS
    # layout
    MOD_KEY LAYOUT GAPS_IN GAPS_OUT GAPS_WORKSPACES BORDER_SIZE BORDER_ANGLE
    ROUNDING ROUNDING_POWER WORKSPACE_COUNT
    # decoration
    BLUR BLUR_SIZE BLUR_PASSES BLUR_XRAY BLUR_NOISE BLUR_CONTRAST
    BLUR_BRIGHTNESS BLUR_VIBRANCY BLUR_SPECIAL BLUR_POPUPS
    SHADOW SHADOW_RANGE SHADOW_RENDER_POWER SHADOW_OFFSET
    ACTIVE_OPACITY INACTIVE_OPACITY DIM_INACTIVE DIM_STRENGTH DIM_SPECIAL
    # animation
    ANIMATIONS ANIMATION_PRESET ANIMATION_SPEED ANIMATION_CUSTOM RICE_TRANSITION
    NIGHT_SHADER NIGHT_SHADER_START NIGHT_SHADER_END NIGHT_TEMP
    # idle (hypridle)
    IDLE_DIM IDLE_LOCK IDLE_DPMS IDLE_SUSPEND
    IDLE_DIM_LEVEL IDLE_KBD_BACKLIGHT IDLE_LOCK_BEFORE_SLEEP IDLE_RESPECT_INHIBIT
    # lock screen (hyprlock)
    LOCK_BACKGROUND LOCK_BLUR_PASSES LOCK_BLUR_SIZE LOCK_BRIGHTNESS
    LOCK_CLOCK_FORMAT LOCK_CLOCK_SIZE LOCK_SHOW_DATE LOCK_DATE_FORMAT
    LOCK_SHOW_USER LOCK_INPUT_WIDTH LOCK_PLACEHOLDER LOCK_GRACE
    # notifications (mako / dunst / swaync)
    NOTIFY_POSITION NOTIFY_TIMEOUT NOTIFY_CRITICAL_STICKY NOTIFY_WIDTH
    NOTIFY_MAX_VISIBLE NOTIFY_MARGIN NOTIFY_ICON_SIZE
    RECORD_DIR RECORD_FPS RECORD_AUDIO REPLAY_SECONDS
    RECORD_FORMAT RECORD_CODEC RECORD_QUALITY RECORD_CURSOR SCREENSHOT_DIR
    POWERMENU_HIBERNATE POWERMENU_CONFIRM
    GAMEMODE_AUTO GAMEMODE_MATCH GAMEMODE_EFFECTS GAMEMODE_PAUSE_WALLPAPER GAMEMODE_DND
    SONG_LISTEN_SECONDS NOTIFY_HISTORY NOTIFY_HISTORY_KEEP UPDATES_CHECK UPDATES_INTERVAL
    UPDATES_AUR BRIGHTNESS_DDC PANEL_APP_VOLUME SELFUPDATE_SYNC SNAPSHOT_BEFORE_SYSTEM
    SWWW_TRANSITION SWWW_TRANSITION_DURATION SWWW_TRANSITION_FPS
    WALLPAPER_DIR WALLPAPER_ROTATE
    # layout engines
    DWINDLE_PRESERVE_SPLIT DWINDLE_SMART_SPLIT
    DWINDLE_SMART_RESIZING MASTER_NEW_STATUS MASTER_MFACT
    # behavior
    ALLOW_TEARING NO_FOCUS_FALLBACK RESIZE_ON_BORDER SNAP SNAP_WINDOW_GAP
    SNAP_MONITOR_GAP VRR ENABLE_SWALLOW SWALLOW_REGEX DPMS_ON_INPUT
    FOCUS_ON_ACTIVATE ANIMATE_MANUAL_RESIZES ON_FOCUS_UNDER_FULLSCREEN
    SCROLL_EVENT_DELAY
    HIDE_SPECIAL_ON_WS_CHANGE
    RULE_SUPPRESS_MAXIMIZE RULE_FLOAT_TOOLS RULE_PIP PIP_WIDTH
    QUICK_PANEL_WIDTH QUICK_PANEL_HEIGHT
    # window groups (tabs)
    GROUPBAR GROUPBAR_STYLE GROUPBAR_HEIGHT GROUPBAR_FONT_SIZE
    # hyprpm plugins
    HYPREXPO_COLUMNS HYPRBARS_HEIGHT HYPRBARS_BUTTONS
    # keybindings
    KEYBINDS
    # window switcher (ALT+Tab)
    SWITCHER_ENABLED WINDOW_SWITCHER SWITCHER_SCOPE SWITCHER_SORT SWITCHER_SPECIAL
    SWITCHER_SHOW_WORKSPACE SWITCHER_THUMBS SWITCHER_THUMB_WIDTH
    SWITCHER_ANIM SWITCHER_PRELOAD SWITCHER_PRIORITY
    # input
    KB_LAYOUT KB_VARIANT KB_OPTIONS REPEAT_DELAY REPEAT_RATE NUMLOCK
    FOLLOW_MOUSE SENSITIVITY ACCEL_PROFILE OFF_WINDOW_AXIS_EVENTS
    NATURAL_SCROLL TOUCHPAD_TAP TOUCHPAD_DWT TOUCHPAD_CLICKFINGER
    TOUCHPAD_SCROLL_FACTOR
    # gestures
    GESTURE_SWIPE GESTURE_FINGERS SWIPE_DISTANCE SWIPE_CANCEL_RATIO
    SWIPE_CREATE_NEW SWIPE_DIRECTION_LOCK
    # cursor
    CURSOR_INACTIVE_TIMEOUT CURSOR_HOTSPOT_PADDING NO_HARDWARE_CURSORS
    # display / workspace
    MANAGE_HYPR_CONFIGS MANAGE_MONITORS MONITOR_SPEC WORKSPACE_MONITOR_MAP WORKSPACE_SPLIT
    # linux-wallpaperengine
    WPENGINE_ID WPENGINE_SCREEN WPENGINE_PER_SCREEN WPENGINE_SCALING WPENGINE_FPS WPENGINE_SILENT
    WPENGINE_EXTRA_ARGS
    # window rules
    GLOBAL_OPACITY XWAYLAND_NO_BLUR
    # environment
    QT_PLATFORM_THEME XDG_MENU_PREFIX FLATPAK_DIRS EDITOR_CMD TERMINAL_ARGS
    EXTRA_ENV
    # autostart
    EXTRA_EXEC_ONCE GNOME_KEYRING
    # wallpaper and primary tools
    WALLPAPER_PATH WALLPAPER_STYLE WALLPAPER_IMAGE TERMINAL LAUNCHER BAR
    NOTIFIER FILEMANAGER WALLPAPER_DAEMON BROWSER
)

config_defaults() {
    # -------------------------------------------- install-time settings ---
    # These are NOT in CONFIG_VARS (reason above): they are not written to
    # settings.conf and not passed to templates. Only install.sh and modules/* read them.
    # The applied look preset (presets/profile/*.conf) — always empty right now
    # because the profile axis was removed, but preset_apply_chain still reads it.
    : "${PRESET:=}"
    # Look variant of the selected profile (presets/profile/<name>.variants/).
    # If empty, the profile's own PROFILE_VARIANT default is used.
    : "${PROFILE_VARIANT:=}"
    : "${AUR_HELPER:=auto}"
    # AUR packages are unsigned, community-submitted build scripts.
    # true (default): the helper shows the PKGBUILD review.
    # false: the review is skipped — the right flag is chosen for the helper
    #        (see lib/packages.sh:aur_helper_flags; "--skipreview" is
    #        paru-specific, yay rejects it and exits with 1).
    : "${AUR_REVIEW:=true}"
    # Chaotic-AUR: a THIRD-PARTY repo that ships AUR packages prebuilt and
    # signed. If set to true, an extra confirmation is asked during install
    # and the repo is added with "Usage = Sync Search Install" (no Upgrade —
    # it cannot override official packages). See lib/chaotic.sh.
    : "${CHAOTIC_AUR:=false}"
    # Build-from-source policy. AUR packages are built on this machine; that
    # both takes time and runs every command in the PKGBUILD's build step
    # here (e.g. `npm install` in ags-hyprpanel-git).
    #   ask    (default) asked one by one for each source build
    #   never  never builds — only packages with a signed binary are installed
    #   always builds without asking (old behavior)
    # "-bin" packages and those available as binaries in a repo do not count
    # as builds and are not affected by this policy. With -y/--yes, "ask" counts as yes.
    : "${COMPILE:=ask}"
    # Packages that never enter the install (separated by commas or spaces).
    # Works at the PACKAGE level, not the component level: to keep a component
    # but leave out a single one of its packages. From the command line: --skip-pkg
    : "${PKG_SKIP:=}"
    : "${ENABLE_SERVICES:=1}"
    : "${USE_TUI:=1}"
    : "${OVERWRITE_CONFIGS:=ask}"        # ask | always | never
    # Hyprland config language. On the 'main' branch of Hyprland's main repo,
    # heading for the (not yet released) 0.57, the old hyprlang .conf parser
    # was removed entirely — only the Lua config remains.
    # If left at 'auto', preflight_detect_hypr_lang (lib/preflight.sh) looks at
    # the installed Hyprland version and resolves it to conf/lua; 'conf' or 'lua'
    # can be forced by hand. The value becomes concrete at render time; keeping
    # it as 'auto' here and saving it to settings.conf that way is intentional —
    # so later install runs detect it again if the version changed.
    : "${HYPR_LANG:=auto}"               # auto | conf | lua

    # -------------------------------------------------------- appearance ---
    # Palette name, or "auto" → extract the colors from the wallpaper.
    : "${THEME:=catppuccin-mocha}"       # python3 -m hyprsetup themes
    # Extraction backend for THEME="auto". auto = try them in order.
    #   matugen  Material You (extra: matugen) — best result
    #   magick   ImageMagick histogram — reads every image format
    #   python   built-in PNG decoder — no dependencies, PNG only
    : "${PALETTE_BACKEND:=auto}"         # auto | matugen | magick | python
    # To override individual colors in the theme palette:
    #   "ACCENT=ff8800;;BG=101014"
    # Keys: BG BG_DARK SURFACE FG SUBTEXT ACCENT ACCENT2 RED GREEN
    #       YELLOW CYAN
    # Also applies when THEME="auto" and overrides the extracted color.
    : "${CUSTOM_COLORS:=}"
    # Manual tone adjustment for the whole palette (preset theme and "auto"
    # alike). Order: palette → these shifts → CUSTOM_COLORS. All 0 = leave as is.
    #   PALETTE_HUE        -180..180  rotation on the color wheel (degrees);
    #                                 RED/GREEN/YELLOW/CYAN carry meaning, so
    #                                 they are not rotated
    #   PALETTE_SATURATION -100..100  minus = muted, plus = vivid (%)
    #   PALETTE_LIGHTNESS   -20..20   background/surface lightness (%)
    : "${PALETTE_HUE:=0}"
    : "${PALETTE_SATURATION:=0}"
    : "${PALETTE_LIGHTNESS:=0}"
    # System-wide dark/light mode preference (org.gnome.desktop.interface
    # color-scheme + GTK3/4 settings) — independent of THEME's accent colors:
    # "light" can be forced even with a dark theme selected, or vice versa.
    # GTK4/libadwaita apps read dark mode from this.
    : "${COLOR_SCHEME:=dark}"            # dark | light
    # Day/night theme (python/hyprsetup/themeschedule.py, systemd timer)
    : "${THEME_SCHEDULE:=false}"
    : "${THEME_DAY:=catppuccin-latte}"
    : "${THEME_NIGHT:=catppuccin-mocha}"
    : "${THEME_DAY_START:=07:00}"
    : "${THEME_NIGHT_START:=19:00}"
    : "${CURSOR_THEME:=Bibata-Modern-Ice}"
    : "${CURSOR_SIZE:=24}"
    # GTK and icon theme. If left empty, derived from the selected components:
    # Catppuccin if the gtk-theme component is present, otherwise Adwaita-dark;
    # Papirus-Dark if the icon-theme component is present, otherwise Adwaita.
    : "${GTK_THEME_NAME:=}"
    : "${ICON_THEME_NAME:=}"
    # UI font: bar, notifications, GTK/Qt, launcher.
    : "${FONT_FAMILY:=Noto Sans}"
    # Monospace font: terminal emulators and the audio visualizer.
    #
    # It HAS to be separate: FONT_FAMILY may be a proportional family (the
    # default "Noto Sans" is) and kitty/foot/alacritty do not work properly
    # with a proportional font — kitty prints a warning and falls back to
    # another font, alignment breaks. Before this split, 40 of 48 profiles
    # were generating "Noto Sans" as the terminal font.
    : "${FONT_MONO:=JetBrainsMono Nerd Font}"
    : "${FONT_SIZE:=11}"

    # -------------------------------------------------------- status bar ---
    # Bar preset (presets/bar/*.conf). May come from the profile; if the user
    # picks one separately, theirs wins. If left empty, the individual
    # BAR_* values below apply.
    : "${BAR_PRESET:=}"
    : "${BAR_POSITION:=top}"             # top | bottom | left | right
    : "${BAR_HEIGHT:=38}"                # height for horizontal bars
    : "${BAR_WIDTH:=44}"                 # width for vertical (left/right) bars
    : "${BAR_MARGIN:=6}"                 # gap from the edge the bar sits on
    : "${BAR_SPACING:=6}"                # gap between modules
    : "${BAR_PADDING:=12}"               # inner padding of module boxes
    : "${BAR_RADIUS:=10}"                # module box corner rounding
    : "${BAR_OPACITY:=0.85}"             # module box background opacity
    : "${BAR_CLOCK_FORMAT:=%H:%M}"
    : "${BAR_CLOCK_FORMAT_ALT:=%d.%m.%Y %H:%M}"
    # numbers | roman | dots | pill-expand | underline | bracket
    # | occupied-only | app-icons | id-icons | named
    : "${BAR_WORKSPACE_STYLE:=numbers}"
    : "${BAR_ICON_STYLE:=material}"
    : "${BAR_WINDOW_MAX_LENGTH:=60}"
    : "${BAR_AUTOHIDE:=false}"           # slide the bar off the edge?
    : "${WEATHER_LOCATION:=}"            # empty = guessed from IP (wttr.in)
    : "${WEATHER_UNIT:=metric}"          # metric | imperial
    : "${WEATHER_REFRESH:=15}"           # minutes; wttr.in is queried at most this often
    # bar-autohide.py: how many px from the edge it opens / how far outside
    # the bar it closes (without a margin it flickers on the last pixel).
    : "${BAR_AUTOHIDE_TRIGGER:=2}"
    : "${BAR_AUTOHIDE_RELEASE:=8}"

    # Three slots where users put their own command on the bar. If the
    # command is empty, the slot is not written to the generated config at
    # all; otherwise it appears in the bar layout as "custom/user1..3".
    : "${BAR_CUSTOM1_CMD:=}"
    : "${BAR_CUSTOM1_FORMAT:=}"          # empty = "{}", i.e. the output itself
    : "${BAR_CUSTOM1_INTERVAL:=60}"      # seconds
    : "${BAR_CUSTOM1_CLICK:=}"
    : "${BAR_CUSTOM2_CMD:=}"
    : "${BAR_CUSTOM2_FORMAT:=}"
    : "${BAR_CUSTOM2_INTERVAL:=60}"
    : "${BAR_CUSTOM2_CLICK:=}"
    : "${BAR_CUSTOM3_CMD:=}"
    : "${BAR_CUSTOM3_FORMAT:=}"
    : "${BAR_CUSTOM3_INTERVAL:=60}"
    : "${BAR_CUSTOM3_CLICK:=}"

    # --------------------------------------------------------- terminal ---
    # Terminal preset (presets/terminal/*.conf) — same logic as bar presets:
    # may come from the profile; if the user picks one separately, theirs wins.
    # Values are translated for the selected terminal
    # (kitty/foot/alacritty/ghostty/wezterm);
    # a setting with no equivalent is silently skipped (see render.py:_terminal_vars).
    # "auto" = the preset matching the active bar preset (lib/preset.sh:preset_match_axis).
    : "${TERM_PRESET:=auto}"
    : "${TERM_OPACITY:=0.95}"            # window background opacity
    : "${TERM_PADDING:=8}"               # between text and window edge
    : "${TERM_FONT_SIZE:=}"              # empty = same as FONT_SIZE
    : "${TERM_CURSOR_STYLE:=block}"      # block | beam | underline
    : "${TERM_CURSOR_BLINK:=false}"      # true | false
    : "${TERM_SCROLLBACK:=10000}"        # lines kept
    # Startup screen (fastfetch) and background image. TERM_FETCH=default
    # leaves the distro's own greeting alone (fastfetch in CachyOS fish).
    : "${TERM_FETCH:=default}"           # default | on | off
    : "${TERM_LOGO:=distro}"             # distro|small|souprland|image|none
    : "${TERM_LOGO_IMAGE:=}"             # PNG path (TERM_LOGO=image)
    : "${TERM_LOGO_STYLE:=image}"        # image | braille | block | ascii
    : "${TERM_LOGO_MONO:=false}"         # single color in the character styles
    : "${TERM_LOGO_WIDTH:=24}"           # columns
    : "${TERM_FETCH_INFO:=short}"        # short | full
    : "${TERM_BG_IMAGE:=}"               # empty = no image (kitty/ghostty/wezterm)
    : "${TERM_BG_DIM:=0.75}"             # 0 the image itself … 0.95 nearly solid
    : "${TERM_BG_FIT:=cover}"            # cover | center | tile

    # ------------------------------------------------- application launcher ---
    # Launcher preset (presets/launcher/*.conf). Values are translated for the
    # selected launcher (wofi/rofi/fuzzel/walker/tofi).
    : "${LAUNCHER_PRESET:=auto}"
    : "${LAUNCHER_WIDTH:=45}"            # percentage of screen width
    : "${LAUNCHER_LINES:=10}"            # visible result lines
    : "${LAUNCHER_POSITION:=center}"     # center | top
    : "${LAUNCHER_OPACITY:=0.93}"        # window background opacity
    : "${LAUNCHER_ICONS:=true}"          # show app icons?
    : "${LAUNCHER_ICON_SIZE:=32}"        # icon edge length
    : "${LAUNCHER_PROMPT:=Search…}"      # prompt text in the search box
    : "${LAUNCHER_RADIUS:=}"             # corner radius; empty = same as windows (ROUNDING)
    : "${LAUNCHER_BORDER:=}"             # border width; empty = same as windows (BORDER_SIZE)
    # walker-specific: extra query sources besides the app list (elephant
    # providers). Each one is invoked with its own prefix — see
    # python/hyprsetup/render.py:LAUNCHER_PROVIDERS.
    : "${LAUNCHER_PROVIDERS:=calc,websearch,clipboard,symbols,files,windows,runner,providerlist}"

    # ----------------------------------------------------------- widget ---
    # Widget engine: comes from the "Widget Engine" category in the component
    # wizard. Empty = no desktop widgets. Independent of the bar choice:
    # it can be used together with any bar preset.
    : "${WIDGET_ENGINE:=}"               # eww | quickshell | (empty)
    # Enabled widgets, comma-separated (presets/widget/*.conf).
    # E.g. "control-center,calendar,cava". Empty = no widgets.
    # This list is ignored if no WIDGET_ENGINE is selected.
    : "${WIDGETS:=}"
    # Widget layout preset (presets/widget-set/<name>.conf): says together
    # which widgets are on and which corner each goes to.
    # Empty = the user's own list applies.
    : "${WIDGET_SET:=}"
    # Which layer are widgets drawn on?
    #   bottom  above the wallpaper, BELOW WINDOWS. On a tiling desktop the
    #           screen is almost always covered by windows, so in practice
    #           widgets are only visible on an empty workspace — this is the
    #           cause of the "I turned widgets on but nothing shows" complaint.
    #   top     above windows. Not meant to stay on permanently; designed
    #           to be toggled with MOD+W (see widgets.sh).
    : "${WIDGET_LAYER:=bottom}"          # bottom | top
    # Which display? Empty = first display (0). Give an index: 0, 1…
    # A name is accepted too, but it is the MODEL name eww sees ("MSI G2412F"),
    # NOT Hyprland's connector name (DP-1) — if that is given, eww does not open
    # the window ("Failed to get monitor DP-1").
    : "${WIDGET_MONITOR:=}"
    # Show widgets at session start? When "false" they only open with the
    # MOD+W binding (the natural choice for the top-layer mode).
    : "${WIDGET_AUTOSTART:=true}"

    # ------------------------------------------------ audio visualizer ---
    # Bars at the bottom edge that react to music, via cava; drawn with kitty's
    # panel mode above the wallpaper, below windows. OFF by default.
    : "${VIS_ENABLE:=false}"
    : "${VIS_MODE:=desktop}"             # desktop: in the background | strip: reserves space at the bottom
    : "${VIS_COLOR:=}"                   # empty: the theme's accent color (#rrggbb)
    : "${VIS_BRIGHTNESS:=60}"            # 20-100: color is dimmed toward the background
    : "${VIS_HEIGHT:=130}"               # pixels
    : "${VIS_WIDTH:=60}"                 # percentage of screen width
    : "${VIS_MONITOR:=}"                 # empty: every display

    # ---------------------------------------------------------------- dock ---
    # App bar floating at the edge (nwg-dock-hyprland, component "dock").
    # Independent of the bar backend. OFF by default.
    : "${DOCK_ENABLE:=false}"
    : "${DOCK_POSITION:=bottom}"         # bottom | left | right | top
    : "${DOCK_AUTOHIDE:=false}"          # true: appears when the mouse hits the edge
    : "${DOCK_ICON_SIZE:=40}"            # px
    : "${DOCK_MARGIN:=8}"                # gap from the edge (px)
    : "${DOCK_RADIUS:=18}"               # corner rounding (px)
    : "${DOCK_OPACITY:=0.85}"            # background, 0.2–1
    : "${DOCK_LAUNCHER:=true}"           # launcher button at the end
    : "${DOCK_MONITOR:=}"                # empty: whichever display the mouse is on
    # Placement: which widget in which corner, in which order. Empty corner =
    # each widget goes to its default corner from the catalog
    # (python/hyprsetup/render.py:WIDGET_CATALOG).
    : "${WIDGET_ZONE_TL:=}"              # top left
    : "${WIDGET_ZONE_TC:=}"              # top center
    : "${WIDGET_ZONE_TR:=}"              # top right
    : "${WIDGET_ZONE_BL:=}"              # bottom left
    : "${WIDGET_ZONE_BC:=}"              # bottom center
    : "${WIDGET_ZONE_BR:=}"              # bottom right
    # Per-widget fine tuning: "name:x:y,…" (px, see render.widget_offsets).
    : "${WIDGET_OFFSETS:=}"
    : "${WIDGET_MARGIN:=16}"             # gap from the screen edge (px)
    : "${WIDGET_GAP:=10}"                # gap between widgets (px)
    : "${WIDGET_SCALE:=1.0}"             # box + text scale
    : "${WIDGET_RADIUS:=12}"             # corner rounding (px)
    : "${WIDGET_OPACITY:=0.85}"          # opacity of the box background
    # Modules: names from the BAR_MODULES section, comma-separated.
    # Modules depending on an unselected component (e.g. bluetooth) are dropped automatically.
    # Note: '=' is used here, not ':='. ':=' also treats an empty string as
    # "no value given" and writes the default back; but a bar preset leaving
    # a region empty on purpose is meaningful (e.g. rail does not want the
    # window title on a vertical bar). '=' only assigns if the variable is not defined at all.
    : "${BAR_MODULES_LEFT=hyprland/workspaces,hyprland/submap}"
    : "${BAR_MODULES_CENTER=hyprland/window}"
    : "${BAR_MODULES_RIGHT=cpu,memory,backlight,pulseaudio,bluetooth,network,battery,tray,clock,custom/mic,custom/power}"

    # ------------------------------------------------------------ layout ---
    : "${MOD_KEY:=SUPER}"                # SUPER | ALT | CTRL
    : "${LAYOUT:=dwindle}"               # dwindle | master
    : "${GAPS_IN:=5}"
    : "${GAPS_OUT:=12}"
    : "${GAPS_WORKSPACES:=0}"            # gap during the workspace switch
    : "${BORDER_SIZE:=2}"
    : "${BORDER_ANGLE:=45}"              # border gradient angle (degrees)
    : "${ROUNDING:=10}"
    : "${ROUNDING_POWER:=2}"             # 2 = circle, 4 = pronounced squircle
    : "${WORKSPACE_COUNT:=10}"

    # --------------------------------------------------------- decoration --
    : "${BLUR:=true}"
    : "${BLUR_SIZE:=6}"
    : "${BLUR_PASSES:=3}"
    : "${BLUR_XRAY:=false}"              # also blur what is behind windows
    : "${BLUR_NOISE:=0.0117}"
    : "${BLUR_CONTRAST:=0.9}"
    : "${BLUR_BRIGHTNESS:=1.0}"
    : "${BLUR_VIBRANCY:=0.17}"
    : "${BLUR_SPECIAL:=false}"
    : "${BLUR_POPUPS:=true}"

    : "${SHADOW:=true}"
    : "${SHADOW_RANGE:=20}"
    : "${SHADOW_RENDER_POWER:=3}"
    : "${SHADOW_OFFSET:=0 4}"

    : "${ACTIVE_OPACITY:=1.0}"
    : "${INACTIVE_OPACITY:=0.96}"
    : "${DIM_INACTIVE:=false}"
    : "${DIM_STRENGTH:=0.05}"
    : "${DIM_SPECIAL:=0.2}"

    # ---------------------------------------------------------- animation --
    : "${ANIMATIONS:=true}"
    # The animation's CHARACTER (curve + duration set); ANIMATION_SPEED is
    # applied on top of it as a multiplier.
    : "${ANIMATION_PRESET:=default}"     # default|snappy|fluid|minimal|none|custom
    : "${ANIMATION_SPEED:=1.0}"          # >1 faster, <1 slower
    : "${ANIMATION_CUSTOM:=}"            # ANIMATION_PRESET=custom: "bezier = …;;animation = …"
    # Frozen screen + soup transition while a profile/mix changes
    # (python/hyprsetup/transition.py). false = the transition layer is not opened.
    : "${RICE_TRANSITION:=true}"

    # ------------------------------------------------------- screen filter ---
    # Automatic night filter with hyprshade. OFF by default: hyprsunset also
    # lowers the color temperature, and with both on the screen turns twice as yellow.
    # To turn it on: NIGHT_SHADER="blue-light-filter"
    # Available: blue-light-filter | vibrance | grayscale | crt
    : "${NIGHT_SHADER:=}"
    : "${NIGHT_SHADER_START:=20:00}"
    : "${NIGHT_SHADER_END:=06:00}"
    # hyprsunset color temperature (Kelvin). The MOD+SHIFT+N binding toggles
    # with this value; it used to be HARDCODED as 4000 in the binding, so the
    # only way to change it was editing the generated keybinds.conf by hand.
    : "${NIGHT_TEMP:=4000}"

    # ---------------------------------------------------- window switcher -
    # Window selection with ALT+Tab. "menu" uses the generated windowswitch.py:
    # it lists windows in the dmenu mode of the already-selected launcher and
    # calls the chosen one with "hyprctl dispatch focuswindow" — if the window
    # is on another workspace, Hyprland SWITCHES there. Ready-made alt-tab apps
    # (hyprshell/hyprswitch) are AUR-only and want a permanently running
    # background process; that is why our own script is the default.
    # overlay: GTK4 window — each window's CURRENT IMAGE with the app icon on
    #          top (like Windows/KDE alt-tab). Thumbnails are taken with
    #          "grim -T <stableId>"; without grim only the icon is shown and
    #          the binding still works.
    # menu:    plain text list in the launcher's dmenu mode (no GTK needed).
    # SWITCHER_ENABLED=false: our ALT+Tab is not generated at all; the
    # profile's own alt-tab (or another app) keeps those keys.
    : "${SWITCHER_ENABLED:=true}"
    : "${WINDOW_SWITCHER:=overlay}"       # overlay | menu
    # Old settings files: WINDOW_SWITCHER="off" is now SWITCHER_ENABLED=false.
    if [[ $WINDOW_SWITCHER == off ]]; then
        SWITCHER_ENABLED=false
        WINDOW_SWITCHER=overlay
    fi
    : "${SWITCHER_SCOPE:=all}"            # all | current | monitor
    : "${SWITCHER_SORT:=recent}"          # recent (most recently used) | workspace
    : "${SWITCHER_SPECIAL:=false}"        # special (scratchpad) windows
    : "${SWITCHER_SHOW_WORKSPACE:=true}"  # workspace name on each row
    : "${SWITCHER_THUMBS:=true}"          # overlay: thumbnails (needs grim)
    : "${SWITCHER_THUMB_WIDTH:=260}"      # overlay: card width (pixels)
    # Switcher opening animation. "none" is the fastest and the default:
    # the whole ALT+Tab should last as long as pressing and releasing the key.
    # CAREFUL: in Hyprland the field that disables animation is "no_anim";
    # writing "animation none" does nothing (an unknown style silently falls
    # back to the default), which is why the rule is generated in render.py:_switcher_vars.
    : "${SWITCHER_ANIM:=none}"            # none | popin | slide
    # A copy waiting ready in the background: ALT+Tab does not wait for GTK to
    # load (~95 ms) or for window setup, so the switcher opens ~3x faster.
    # The cost is a process sitting in ~60 MB of memory, so it is off by
    # default.
    : "${SWITCHER_PRELOAD:=false}"
    # off | alttab | session — CachyOS ananicy priority fix (priority.py);
    # needs root, the settings app applies it with sudo in a terminal when changed.
    : "${SWITCHER_PRIORITY:=off}"

    # --------------------------------------------------------------- idle ---
    # hypridle timeouts, in SECONDS. 0 for any of them = that step is absent.
    # The order should make sense: dim < lock < display off < sleep. The values
    # go to templates/hypr/hypridle.conf.tmpl; they used to be HARDCODED there,
    # so someone saying "it locks after 5 minutes and I can't extend it" had
    # no option but to edit the generated file by hand (and lose it on the
    # next apply).
    : "${IDLE_DIM:=150}"        # dim the display (only when brightnessctl is present)
    : "${IDLE_LOCK:=300}"       # lock with hyprlock
    : "${IDLE_DPMS:=330}"       # turn the display off
    : "${IDLE_SUSPEND:=1800}"   # suspend the system (0 = desktop machines)
    : "${IDLE_DIM_LEVEL:=10}"           # brightness when dimmed (%)
    : "${IDLE_KBD_BACKLIGHT:=true}"     # also turn off the keyboard backlight when dimming
    : "${IDLE_LOCK_BEFORE_SLEEP:=true}" # lock before sleep
    # true: when a player/browser says "keep the screen on" (D-Bus inhibit),
    # dim/lock/sleep wait. false: they always run on time.
    : "${IDLE_RESPECT_INHIBIT:=true}"

    # -------------------------------------------------------- lock screen ---
    # templates/hypr/hyprlock.conf.tmpl. It used to be fully hardcoded (24-hour,
    # 110 pt clock, 3×8 blur).
    : "${LOCK_BACKGROUND:=wallpaper}"   # wallpaper | screenshot | color
    : "${LOCK_BLUR_PASSES:=3}"          # 0 = no blur
    : "${LOCK_BLUR_SIZE:=8}"
    : "${LOCK_BRIGHTNESS:=0.8}"
    : "${LOCK_CLOCK_FORMAT:=%H:%M}"     # date(1) format; 12-hour: %I:%M %p
    : "${LOCK_CLOCK_SIZE:=110}"
    : "${LOCK_SHOW_DATE:=true}"
    : "${LOCK_DATE_FORMAT:=%d %B %Y, %A}"
    : "${LOCK_SHOW_USER:=true}"         # username above the password field
    : "${LOCK_INPUT_WIDTH:=320}"
    : "${LOCK_PLACEHOLDER:=Password…}"
    # How many seconds after an idle lock no password is asked
    # (hyprlock --grace). NEVER applied when locking before sleep.
    : "${LOCK_GRACE:=2}"

    # ------------------------------------------------------ window groups ---
    # group:groupbar. Colors come from the theme; the section used to be
    # missing entirely and Hyprland's yellow defaults showed.
    : "${GROUPBAR:=true}"               # tab bar above a grouped window
    : "${GROUPBAR_STYLE:=tabs}"         # tabs | line | indicator
    : "${GROUPBAR_HEIGHT:=18}"
    : "${GROUPBAR_FONT_SIZE:=10}"

    # ----------------------------------------------------- hyprpm plugins ---
    # Only effective while the matching plugin (Components → Plugins) is installed.
    : "${HYPREXPO_COLUMNS:=3}"          # hyprexpo overview column count
    : "${HYPRBARS_HEIGHT:=26}"          # hyprbars title bar height
    : "${HYPRBARS_BUTTONS:=true}"       # close/maximize/float buttons

    # --------------------------------------------------------- power menu ---
    # wlogout and (when wlogout is absent) hypr/scripts/powermenu.sh.
    : "${POWERMENU_HIBERNATE:=true}"    # hibernation does not work without swap
    : "${POWERMENU_CONFIRM:=true}"      # confirm shutdown/reboot/logout (script)

    # ------------------------------------------------------ notifications ---
    # The mako, dunst and swaync templates read the same values.
    # auto = right corner, on the edge the bar sits on (bar at bottom → notifications at bottom).
    : "${NOTIFY_POSITION:=auto}"
    : "${NOTIFY_TIMEOUT:=6}"            # seconds; 0 = does not close by itself
    : "${NOTIFY_CRITICAL_STICKY:=true}" # critical notifications stay until clicked
    : "${NOTIFY_WIDTH:=380}"
    : "${NOTIFY_MAX_VISIBLE:=5}"        # mako/dunst; no equivalent in swaync
    : "${NOTIFY_MARGIN:=12}"            # distance from the screen edge (mako/dunst)
    : "${NOTIFY_ICON_SIZE:=48}"

    # --------------------------------------------------- screen recording ---
    # gpu-screen-recorder ("instant-replay" component) settings.
    #
    # The default is a LITERAL '$HOME' on purpose — if bash expanded it here,
    # the generating machine's home directory (/home/<someone>/Videos) would be
    # baked into the generated script and distributed dotfiles would write to
    # the wrong place for another user. Because the value is put in double
    # quotes inside the generated record.sh, it resolves against that machine's
    # $HOME at run time. The user may give an absolute path if they want.
    # shellcheck disable=SC2016
    : "${RECORD_DIR:=\$HOME/Videos}"
    : "${RECORD_FPS:=60}"
    # Audio source: gpu-screen-recorder's -a flag. Empty = silent recording.
    #   default_output          audio coming out of the speakers
    #   default_output|default_input   system audio + microphone together
    : "${RECORD_AUDIO:=default_output}"
    # Instant replay buffer (seconds). Memory use is proportional to it.
    : "${REPLAY_SECONDS:=60}"
    : "${RECORD_FORMAT:=mp4}"           # mp4 | mkv (mkv still opens if interrupted)
    : "${RECORD_CODEC:=auto}"           # auto | h264 | hevc | av1
    : "${RECORD_QUALITY:=very_high}"    # medium | high | very_high | ultra
    : "${RECORD_CURSOR:=true}"          # include the mouse cursor in the recording
    # Screenshot folder; empty = XDG Pictures/Screenshots. ~ and $HOME are
    # expanded at run time (binding, Actions menu, bar panel).
    : "${SCREENSHOT_DIR:=}"

    # ------------------------------------------------------------ game mode -
    # In a fullscreen game, effects turn off, Wallpaper Engine pauses,
    # notifications are muted (hypr/scripts/gamemode.py). By hand: MOD+F12.
    : "${GAMEMODE_AUTO:=games}"          # off | games | fullscreen
    : "${GAMEMODE_MATCH:=^(steam_app_[0-9]+|gamescope|.+\.exe|Minecraft.*|cs2|dota2|factorio|hl2_linux)}"
    : "${GAMEMODE_EFFECTS:=true}"        # turn off animation/blur/shadow
    : "${GAMEMODE_PAUSE_WALLPAPER:=true}"
    : "${GAMEMODE_DND:=true}"            # mute notifications

    # ------------------------------------------------------ desktop tools -
    : "${SONG_LISTEN_SECONDS:=9}"        # song recognition recording (s)
    : "${NOTIFY_HISTORY:=true}"          # notifylog.py (for the session only)
    : "${NOTIFY_HISTORY_KEEP:=50}"
    : "${UPDATES_CHECK:=true}"           # custom/updates on the bar
    : "${UPDATES_INTERVAL:=30}"          # minutes
    : "${UPDATES_AUR:=true}"
    : "${BRIGHTNESS_DDC:=true}"          # bar panel: external displays via ddcutil
    : "${PANEL_APP_VOLUME:=true}"        # bar panel: per-app volume
    : "${SELFUPDATE_SYNC:=true}"         # sync the installed copy when applying from the repo
    # snapper/timeshift snapshot before touching system files (NVIDIA, Plymouth,
    # login manager/screen): auto = take one if the tool exists, false = don't.
    : "${SNAPSHOT_BEFORE_SYSTEM:=auto}"

    # ----------------------------------------------- wallpaper transition -
    # swww transition effect (only when WALLPAPER_DAEMON="swww").
    # none|simple|fade|left|right|top|bottom|wipe|grow|center|outer|random
    : "${SWWW_TRANSITION:=grow}"
    : "${SWWW_TRANSITION_DURATION:=2}"
    : "${SWWW_TRANSITION_FPS:=60}"

    # Wallpaper rotation. WALLPAPER_ROTATE is in minutes; 0 = off.
    # If WALLPAPER_DIR is empty, the directory containing WALLPAPER_PATH is scanned.
    : "${WALLPAPER_DIR:=}"
    : "${WALLPAPER_ROTATE:=0}"

    # Login screen (SDDM) background:
    #   wallpaper  copy the wallpaper system-wide and show it
    #   color      solid theme background color
    : "${SDDM_BACKGROUND:=wallpaper}"

    # Plymouth boot animation theme. To list the installed ones:
    #   plymouth-set-default-theme --list
    # Common built-in themes: spinner | bgrt | fade-in | glow | solar | tribar
    : "${PLYMOUTH_THEME:=spinner}"

    # ------------------------------------------------------ layout engine ---
    : "${DWINDLE_PRESERVE_SPLIT:=true}"
    : "${DWINDLE_SMART_SPLIT:=false}"
    : "${DWINDLE_SMART_RESIZING:=true}"
    : "${MASTER_NEW_STATUS:=master}"     # master | slave | inherit
    : "${MASTER_MFACT:=0.55}"

    # ----------------------------------------------------------- behavior --
    : "${ALLOW_TEARING:=false}"          # for the 'immediate' rule in games
    : "${NO_FOCUS_FALLBACK:=false}"
    : "${RESIZE_ON_BORDER:=true}"
    : "${SNAP:=true}"                    # snap floating windows to edges
    : "${SNAP_WINDOW_GAP:=4}"
    : "${SNAP_MONITOR_GAP:=5}"
    : "${VRR:=1}"                        # 0 off | 1 on | 2 fullscreen
    # Profile/user window rules — rule bodies separated by ";;"
    # (see settings.py:WINDOWRULES, render.py:_windowrule_lines).
    : "${WINDOWRULES:=}"
    : "${USER_WINDOWRULES:=}"            # Window Rules page; kept when the profile changes
    : "${ENABLE_SWALLOW:=false}"         # GUI launched from a terminal hides the terminal
    : "${SWALLOW_REGEX:=^(kitty|foot|Alacritty|com.mitchellh.ghostty|org.wezfurlong.wezterm)$}"
    : "${DPMS_ON_INPUT:=true}"           # mouse/keyboard wakes the display
    : "${FOCUS_ON_ACTIVATE:=true}"
    : "${ANIMATE_MANUAL_RESIZES:=false}"
    : "${ON_FOCUS_UNDER_FULLSCREEN:=2}"   # 0 ignore | 1 exit fullscreen | 2 send to back
    : "${SCROLL_EVENT_DELAY:=0}"
    : "${HIDE_SPECIAL_ON_WS_CHANGE:=true}"

    # -------------------------------------------------------- keybindings --
    # Keybindings are defined in config/keybinds.json; here they are overridden one by one:
    #   "terminal=MOD+T;;lock=MOD+CTRL+L;;color-picker="
    # An empty value removes that binding. MOD = MOD_KEY (default SUPER).
    # Full list: config/keybinds.json (or MOD+F1 in a running session).
    : "${KEYBINDS:=}"

    # -------------------------------------------------------------- input --
    : "${KB_LAYOUT:=us}"
    : "${KB_VARIANT:=}"
    : "${KB_OPTIONS:=}"                  # e.g. grp:alt_shift_toggle,caps:escape
    : "${REPEAT_DELAY:=250}"
    : "${REPEAT_RATE:=35}"
    : "${NUMLOCK:=true}"
    : "${FOLLOW_MOUSE:=1}"               # 0..3
    : "${SENSITIVITY:=0}"                # -1.0 .. 1.0
    : "${ACCEL_PROFILE:=}"               # empty | flat | adaptive
    : "${OFF_WINDOW_AXIS_EVENTS:=1}"
    : "${NATURAL_SCROLL:=false}"
    : "${TOUCHPAD_TAP:=true}"
    : "${TOUCHPAD_DWT:=true}"            # disable the touchpad while typing
    : "${TOUCHPAD_CLICKFINGER:=false}"   # two fingers = right click
    : "${TOUCHPAD_SCROLL_FACTOR:=0.8}"

    # ----------------------------------------------------------- gestures --
    : "${GESTURE_SWIPE:=true}"
    : "${GESTURE_FINGERS:=3}"            # 3 | 4 | 5
    : "${SWIPE_DISTANCE:=300}"
    : "${SWIPE_CANCEL_RATIO:=0.5}"
    : "${SWIPE_CREATE_NEW:=true}"
    : "${SWIPE_DIRECTION_LOCK:=true}"

    # ------------------------------------------------------------- cursor --
    : "${CURSOR_INACTIVE_TIMEOUT:=5}"    # 0 = never hide
    : "${CURSOR_HOTSPOT_PADDING:=1}"
    : "${NO_HARDWARE_CURSORS:=false}"

    # ------------------------------------------------ display / workspace --
    # 0 → no file under ~/.config/hypr is generated. If you have your own
    # Hyprland config (hand-written or a ready-made rice), turn this off;
    # the script then only installs packages and configures the other apps.
    : "${MANAGE_HYPR_CONFIGS:=1}"
    : "${MANAGE_MONITORS:=1}"            # 0 → never touch monitors.conf
    : "${MONITOR_SPEC:=,preferred,auto,1}"
    # "1:DP-1:default;2:DP-1;6:HDMI-A-1:default" — if empty, no file is generated
    : "${WORKSPACE_MONITOR_MAP:=}"
    # "auto" → if WORKSPACE_MONITOR_MAP is empty, workspaces are split evenly
    # across connected displays (2 displays, 10 workspaces: 1-5 / 6-10). See render.py:_auto_workspace_split
    : "${WORKSPACE_SPLIT:=}"

    # ------------------------------------------- linux-wallpaperengine -----
    # Steam Workshop wallpaper ID (folder name) or a .pkg path.
    # Wallpaper Engine must be bought on Steam and installed.
    : "${WPENGINE_ID:=}"
    : "${WPENGINE_SCREEN:=}"             # e.g. DP-1 — if empty, all displays
    : "${WPENGINE_PER_SCREEN:=}"         # "DP-1=123;HDMI-A-2=456" — scene per display
    : "${WPENGINE_SCALING:=default}"     # default | stretch | fit | fill
    : "${WPENGINE_FPS:=}"                # e.g. 30 — to save battery/GPU
    : "${WPENGINE_SILENT:=true}"         # mute the wallpaper's audio
    : "${WPENGINE_EXTRA_ARGS:=}"

    # ------------------------------------------------------- window rules --
    : "${GLOBAL_OPACITY:=}"              # e.g. 0.92 — not applied if empty
    : "${XWAYLAND_NO_BLUR:=false}"
    # Built-in window rules (windowrules.conf). A disabled block is not written at all.
    : "${RULE_SUPPRESS_MAXIMIZE:=true}"  # apps may not maximize themselves
    : "${RULE_FLOAT_TOOLS:=true}"        # settings tools/file dialogs float
    : "${RULE_PIP:=true}"                # picture-in-picture bottom right, pinned
    : "${PIP_WIDTH:=640}"                # height is computed from 16:9
    # Size of the MOD+I panel relative to the screen (%); GTK and the window rule read the same value.
    : "${QUICK_PANEL_WIDTH:=80}"
    : "${QUICK_PANEL_HEIGHT:=80}"

    # -------------------------------------------------------- environment ---
    : "${QT_PLATFORM_THEME:=qt6ct}"      # qt6ct | qt5ct | kde | gtk3 | empty
    : "${XDG_MENU_PREFIX:=}"             # for the KDE application menu: plasma-
    : "${FLATPAK_DIRS:=true}"            # add flatpak paths to XDG_DATA_DIRS
    : "${EDITOR_CMD:=}"                  # e.g. nvim — if empty, no env is written
    : "${TERMINAL_ARGS:=}"               # e.g. "-1" for kitty (single instance)
    : "${EXTRA_ENV:=}"                   # "NAME=value;;NAME2=value2"

    # ---------------------------------------------------------- autostart --
    : "${EXTRA_EXEC_ONCE:=}"             # "command1;;command2"
    : "${GNOME_KEYRING:=false}"          # start gnome-keyring-daemon

    # ---------------------------------------------------------- wallpaper ---
    : "${WALLPAPER_PATH:=$HOME/Pictures/wallpapers/wallpaper.png}"
    # The reference rice's actual image — a path relative to SETUP_ROOT (e.g.
    # wallpapers/lamp-paper.png). If set and the file exists, it takes
    # precedence over WALLPAPER_STYLE: wallpaper_step() copies it straight to WALLPAPER_PATH.
    : "${WALLPAPER_IMAGE:=}"
    # Wallpaper pattern. If WALLPAPER_IMAGE is empty/missing and this is set,
    # the file at WALLPAPER_PATH is generated from the selected theme's colors
    # (python3 -m hyprsetup wallpaper). If both are empty, nothing is generated
    # and you put your own image there.
    # waves | stars | orb | mist | grid | paper | solid | dunes
    : "${WALLPAPER_STYLE:=}"

    # ------------------------------------------------------ primary tools ---
    # If left empty, derived from the selected components.
    : "${TERMINAL:=}"
    : "${LAUNCHER:=}"
    : "${BAR:=}"
    : "${NOTIFIER:=}"
    : "${FILEMANAGER:=}"
    : "${WALLPAPER_DAEMON:=}"
    : "${LOGIN_MANAGER:=}"
    : "${BROWSER:=firefox}"

    # Writing "~/Pictures/..." in the settings file is natural, but bash does
    # not expand a tilde inside quotes. If we did not expand it, the script
    # would create a real folder named "~" in its working directory and write
    # the wallpaper to the wrong place.
    #
    # This alone is NOT enough — tools/build-dotfiles.sh deliberately assigns
    # a literal "~" after this point; file operations therefore also go
    # through wallpaper_file() (see lib/core.sh).
    WALLPAPER_PATH="$(expand_tilde "${WALLPAPER_PATH-}")"

    local var
    for var in "${CONFIG_VARS[@]}"; do export "${var?}"; done
}

# Loads the user configuration. Values given on the CLI override the file,
# so install.sh writes the CLI values back after the file is read.
config_load() {
    local file="$1"
    if [[ -n "$file" && -r "$file" ]]; then
        step "Reading configuration: $file"
        _conf_read "$file"
        ok "Configuration loaded"
    elif [[ -n "$file" ]]; then
        warn "Could not read configuration file: $file (defaults will be used)"
    fi
    # Presets: profile → bar preset → widgets. Names come from --preset/--bar-preset/
    # --widgets or from the PRESET/BAR_PRESET/WIDGETS lines in the settings
    # file. Each link in the chain only writes values for settings that are
    # not defined yet, so the user's own values and CLI options are preserved.
    #
    # Careful: an empty value is NOT ASSIGNED, the variable is left unset.
    # Because preset_apply checks "is it defined" (`-v`), a BAR_PRESET=""
    # assignment would silently block the bar preset given by the profile.
    if declare -F preset_apply_chain >/dev/null; then
        local _cli
        for _cli in PRESET:CLI_PRESET PROFILE_VARIANT:CLI_VARIANT \
                    BAR_PRESET:CLI_BAR_PRESET \
                    TERM_PRESET:CLI_TERM_PRESET \
                    LAUNCHER_PRESET:CLI_LAUNCHER_PRESET WIDGETS:CLI_WIDGETS; do
            local _var="${_cli%%:*}" _from="${_cli#*:}"
            if [[ -n "${!_from:-}" ]]; then
                printf -v "$_var" '%s' "${!_from}"
            elif [[ -n "${CLI_PRESET:-}" && "$_var" != PRESET ]]; then
                # The profile is being changed from the CLI (in this run) and no
                # separate CLI choice was given for bar/widgets. BAR_PRESET/WIDGETS
                # were sourced from the old file, so they still carry the previous
                # profile's value here; preset_apply_chain would take that as "the
                # user picked the bar separately" (pinned_bar) and silently ignore
                # the new profile's BAR_PRESET — the bar always stayed from the previous profile.
                unset "${_var?}"
            elif [[ -z "${!_var:-}" ]]; then
                unset "${_var?}"
            fi
        done
        # The BAR_PRESET name was cleared above, but the bar preset's OWN
        # fine-tuning keys (BAR_HEIGHT, BAR_RADIUS, BAR_MODULES_* …) also come
        # in defined from the old file. preset_apply_chain's _PRESET_USER_KEYS
        # records them assuming "everything defined right now was given by the
        # user"; entering the chain with these keys still defined, the new
        # profile's bar preset would apply "0 settings" and stay frozen at the
        # old preset's sizes (height/opacity/modules) — the name changes, the
        # look does not. Unless --bar-preset was given on the CLI, clear them here too.
        if [[ -n "${CLI_PRESET:-}" && -z "${CLI_BAR_PRESET:-}" ]]; then
            local _bar_key
            for _bar_key in "${PRESET_BAR_KEYS[@]}"; do
                unset "${_bar_key?}"
            done
        fi
        # Same for terminal/launcher presets (see the reasoning above).
        if [[ -n "${CLI_PRESET:-}" && -z "${CLI_TERM_PRESET:-}" ]]; then
            local _term_key
            for _term_key in "${PRESET_TERM_KEYS[@]}"; do
                unset "${_term_key?}"
            done
        fi
        if [[ -n "${CLI_PRESET:-}" && -z "${CLI_LAUNCHER_PRESET:-}" ]]; then
            local _launcher_key
            for _launcher_key in "${PRESET_LAUNCHER_KEYS[@]}"; do
                unset "${_launcher_key?}"
            done
        fi
        # If --preset came from the CLI in this run (e.g. --reapply --preset X),
        # the user EXPLICITLY wants to switch to another profile. But the old
        # settings.conf sourced from the file above has already defined all of
        # CONFIG_VARS, such as THEME, WALLPAPER_IMAGE, BAR_PRESET, GAPS_* —
        # a normal (non-force) preset_apply_chain counts them as "already
        # defined" and writes none of the new profile's values. Result: the
        # profile name changes but THEME/BAR_PRESET/wallpaper etc. stay frozen
        # at the previous profile's values — this was the real cause of the
        # "nothing changes / the bar doesn't work when I switch profiles"
        # complaint. force mode is safe here: values given with a real --set are
        # reapplied in apply_cli_sets (install.sh) AFTER config_load and stay on top.
        if [[ -n "${CLI_PRESET:-}" ]]; then
            preset_apply_chain force
        else
            preset_apply_chain
        fi
    fi
    config_defaults
}

config_validate() {
    local n _canon

    # hy3 is a plugin layout (see modules/hypr.sh:hook_hy3); it only makes
    # sense when the 'hy3' component is installed, but validation here does not
    # know the component list — the hook warns about the mismatch separately after install.
    [[ "$LAYOUT" =~ ^(dwindle|master|hy3)$ ]] || die "LAYOUT must be 'dwindle', 'master' or 'hy3' (currently: $LAYOUT)"
    [[ "$MOD_KEY" =~ ^(SUPER|ALT|CTRL)$ ]] || die "MOD_KEY must be 'SUPER', 'ALT' or 'CTRL' (currently: $MOD_KEY)"
    [[ "$OVERWRITE_CONFIGS" =~ ^(ask|always|never)$ ]] || die "OVERWRITE_CONFIGS must be 'ask|always|never'"
    [[ "$COMPILE" =~ ^(ask|never|always)$ ]] || die "COMPILE must be 'ask|never|always' (currently: $COMPILE)"
    [[ "$HYPR_LANG" =~ ^(auto|conf|lua)$ ]] || die "HYPR_LANG must be 'auto', 'conf' or 'lua' (currently: $HYPR_LANG)"
    [[ "$COLOR_SCHEME" =~ ^(dark|light)$ ]] || die "COLOR_SCHEME must be 'dark' or 'light' (currently: $COLOR_SCHEME)"
    [[ "$SDDM_BACKGROUND" =~ ^(wallpaper|color)$ ]] || die "SDDM_BACKGROUND must be 'wallpaper' or 'color' (currently: $SDDM_BACKGROUND)"
    [[ "$PALETTE_BACKEND" =~ ^(auto|matugen|magick|python)$ ]] || die "PALETTE_BACKEND must be 'auto|matugen|magick|python' (currently: $PALETTE_BACKEND)"
    [[ "$DOCK_POSITION" =~ ^(bottom|left|right|top)$ ]] || die "DOCK_POSITION must be 'bottom|left|right|top' (currently: $DOCK_POSITION)"
    local tone
    for tone in PALETTE_HUE PALETTE_SATURATION PALETTE_LIGHTNESS; do
        [[ "${!tone}" =~ ^-?[0-9]+$ ]] || die "$tone must be an integer (currently: ${!tone})"
    done
    [[ "$ANIMATION_PRESET" =~ ^(default|snappy|fluid|minimal|none|custom)$ ]] || die "ANIMATION_PRESET must be 'default|snappy|fluid|minimal|none|custom' (currently: $ANIMATION_PRESET)"
    # THEME must be either a known palette or "auto"; a typo should not
    # silently install with the default theme and mislead the user.
    if [[ "$THEME" != "auto" ]] && have python3; then
        PYTHONPATH="${SETUP_ROOT:-.}/python" python3 -c "
import sys; from hyprsetup import themes
sys.exit(0 if '$THEME' in themes.THEMES else 1)" 2>/dev/null \
            || die "Unknown THEME: $THEME — list: python3 -m hyprsetup themes (or 'auto')"
    fi
    [[ "$MASTER_NEW_STATUS" =~ ^(master|slave|inherit)$ ]] || die "MASTER_NEW_STATUS must be 'master|slave|inherit'"
    [[ -z "$ACCEL_PROFILE" || "$ACCEL_PROFILE" =~ ^(flat|adaptive)$ ]] || die "ACCEL_PROFILE must be empty, 'flat' or 'adaptive'"
    [[ -z "$QT_PLATFORM_THEME" || "$QT_PLATFORM_THEME" =~ ^(qt5ct|qt6ct|kde|gtk3|gtk2)$ ]] || die "Invalid QT_PLATFORM_THEME: $QT_PLATFORM_THEME"
    [[ "$VRR" =~ ^[0-2]$ ]] || die "VRR must be 0, 1 or 2 (currently: $VRR)"
    [[ "$FOLLOW_MOUSE" =~ ^[0-3]$ ]] || die "FOLLOW_MOUSE must be between 0 and 3 (currently: $FOLLOW_MOUSE)"
    [[ "$GESTURE_FINGERS" =~ ^[3-5]$ ]] || die "GESTURE_FINGERS must be 3, 4 or 5"

    # must be integers
    for n in GAPS_IN GAPS_OUT GAPS_WORKSPACES BORDER_SIZE BORDER_ANGLE ROUNDING \
             ROUNDING_POWER CURSOR_SIZE WORKSPACE_COUNT FONT_SIZE BLUR_SIZE \
             BLUR_PASSES SHADOW_RANGE SHADOW_RENDER_POWER REPEAT_DELAY \
             REPEAT_RATE SWIPE_DISTANCE SNAP_WINDOW_GAP SNAP_MONITOR_GAP \
             CURSOR_INACTIVE_TIMEOUT CURSOR_HOTSPOT_PADDING SCROLL_EVENT_DELAY \
             OFF_WINDOW_AXIS_EVENTS ON_FOCUS_UNDER_FULLSCREEN; do
        [[ "${!n}" =~ ^[0-9]+$ ]] || die "$n must be an integer (currently: ${!n})"
    done

    # may be decimals
    for n in ANIMATION_SPEED ACTIVE_OPACITY INACTIVE_OPACITY DIM_STRENGTH \
             DIM_SPECIAL BLUR_NOISE BLUR_CONTRAST BLUR_BRIGHTNESS BLUR_VIBRANCY \
             MASTER_MFACT TOUCHPAD_SCROLL_FACTOR SWIPE_CANCEL_RATIO SENSITIVITY; do
        [[ "${!n}" =~ ^-?[0-9]+(\.[0-9]+)?$ ]] || die "$n must be a number (currently: ${!n})"
    done

    # must be true/false
    for n in BLUR BLUR_XRAY BLUR_SPECIAL BLUR_POPUPS SHADOW ANIMATIONS \
             DIM_INACTIVE DWINDLE_PRESERVE_SPLIT \
             DWINDLE_SMART_SPLIT DWINDLE_SMART_RESIZING ALLOW_TEARING \
             NO_FOCUS_FALLBACK RESIZE_ON_BORDER SNAP ENABLE_SWALLOW \
             DPMS_ON_INPUT FOCUS_ON_ACTIVATE ANIMATE_MANUAL_RESIZES \
             HIDE_SPECIAL_ON_WS_CHANGE NUMLOCK NATURAL_SCROLL TOUCHPAD_TAP \
             TOUCHPAD_DWT TOUCHPAD_CLICKFINGER GESTURE_SWIPE SWIPE_CREATE_NEW \
             SWIPE_DIRECTION_LOCK NO_HARDWARE_CURSORS XWAYLAND_NO_BLUR \
             FLATPAK_DIRS GNOME_KEYRING WPENGINE_SILENT; do
        [[ "${!n}" =~ ^(true|false|yes|no)$ ]] || die "$n must be 'true' or 'false' (currently: ${!n})"
    done

    [[ -z "$GLOBAL_OPACITY" || "$GLOBAL_OPACITY" =~ ^[0-9]+(\.[0-9]+)?$ ]] ||
        die "GLOBAL_OPACITY must be empty or a number between 0 and 1 (currently: $GLOBAL_OPACITY)"

    [[ "$BAR_POSITION" =~ ^(top|bottom|left|right)$ ]] ||
        die "BAR_POSITION must be 'top|bottom|left|right' (currently: $BAR_POSITION)"
    [[ "$BAR_WORKSPACE_STYLE" =~ ^(numbers|roman|dots|pill-expand|underline|bracket|occupied-only|app-icons|id-icons|named)$ ]] ||
        die "Invalid BAR_WORKSPACE_STYLE: $BAR_WORKSPACE_STYLE (see lib/config.sh)"
    [[ "$BAR_ICON_STYLE" =~ ^(material|fontawesome|octicons|emoji|text)$ ]] ||
        die "Invalid BAR_ICON_STYLE: $BAR_ICON_STYLE (material|fontawesome|octicons|emoji|text)"
    # If a removed preset name (e.g. media) was given, swap in its replacement —
    # so old settings.conf files do not fail with "BAR_PRESET not found".
    if [[ -n "${BAR_PRESET:-}" ]]; then
        _canon=$(preset_canonical "$BAR_PRESET" bar)
        if [[ "$_canon" != "$BAR_PRESET" ]]; then
            warn "Bar preset '$BAR_PRESET' was removed; using '$_canon' instead."
            BAR_PRESET="$_canon"; export BAR_PRESET
        fi
    fi
    [[ -z "${BAR_PRESET:-}" ]] || preset_file "$BAR_PRESET" bar >/dev/null ||
        die "BAR_PRESET not found: $BAR_PRESET (available presets: presets/bar/*.conf)"
    [[ -z "${WALLPAPER_STYLE:-}" || "$WALLPAPER_STYLE" =~ ^(waves|stars|orb|mist|grid|paper|solid|dunes)$ ]] ||
        die "Invalid WALLPAPER_STYLE: $WALLPAPER_STYLE (leave empty or: waves|stars|orb|mist|grid|paper|solid|dunes)"
    for n in BAR_HEIGHT BAR_WIDTH BAR_MARGIN BAR_SPACING BAR_PADDING BAR_RADIUS \
             BAR_WINDOW_MAX_LENGTH; do
        [[ "${!n}" =~ ^[0-9]+$ ]] || die "$n must be an integer (currently: ${!n})"
    done
    [[ "$BAR_OPACITY" =~ ^[01](\.[0-9]+)?$ ]] ||
        die "BAR_OPACITY must be between 0 and 1 (currently: $BAR_OPACITY)"

    # --- terminal / launcher ---
    [[ -z "${TERM_PRESET:-}" || "$TERM_PRESET" == auto ]] || preset_file "$TERM_PRESET" terminal >/dev/null ||
        die "TERM_PRESET not found: $TERM_PRESET (available presets: presets/terminal/*.conf)"
    [[ -z "${LAUNCHER_PRESET:-}" || "$LAUNCHER_PRESET" == auto ]] || preset_file "$LAUNCHER_PRESET" launcher >/dev/null ||
        die "LAUNCHER_PRESET not found: $LAUNCHER_PRESET (available presets: presets/launcher/*.conf)"
    [[ "$TERM_CURSOR_STYLE" =~ ^(block|beam|underline)$ ]] ||
        die "Invalid TERM_CURSOR_STYLE: $TERM_CURSOR_STYLE (block|beam|underline)"
    [[ "$LAUNCHER_POSITION" =~ ^(center|top)$ ]] ||
        die "Invalid LAUNCHER_POSITION: $LAUNCHER_POSITION (center|top)"
    for n in TERM_PADDING TERM_SCROLLBACK LAUNCHER_WIDTH LAUNCHER_LINES \
             LAUNCHER_ICON_SIZE; do
        [[ "${!n}" =~ ^[0-9]+$ ]] || die "$n must be an integer (currently: ${!n})"
    done
    # TERM_FONT_SIZE may be left empty on purpose: when empty, FONT_SIZE applies.
    [[ -z "$TERM_FONT_SIZE" || "$TERM_FONT_SIZE" =~ ^[0-9]+$ ]] ||
        die "TERM_FONT_SIZE must be an integer or left empty (currently: $TERM_FONT_SIZE)"
    for n in TERM_OPACITY LAUNCHER_OPACITY; do
        [[ "${!n}" =~ ^[01](\.[0-9]+)?$ ]] ||
            die "$n must be between 0 and 1 (currently: ${!n})"
    done
    for n in TERM_CURSOR_BLINK LAUNCHER_ICONS; do
        [[ "${!n}" =~ ^(true|false)$ ]] ||
            die "$n must be true or false (currently: ${!n})"
    done

    # CUSTOM_COLORS: "NAME=rrggbb" entries separated by ';;'.
    # Note: printf '%s' adds no trailing newline, so the last entry would not be
    # read; that is why we turn the separator into newlines and feed it with '%s\n'.
    if [[ -n "$CUSTOM_COLORS" ]]; then
        local colour_entry
        local -a colour_entries=()
        mapfile -t colour_entries < <(printf '%s\n' "${CUSTOM_COLORS//;;/$'\n'}")
        for colour_entry in "${colour_entries[@]}"; do
            [[ -z "$colour_entry" ]] && continue
            [[ "$colour_entry" =~ ^(BG|BG_DARK|SURFACE|FG|SUBTEXT|ACCENT|ACCENT2|RED|GREEN|YELLOW|CYAN)=[0-9a-fA-F]{6}$ ]] ||
                die "Invalid CUSTOM_COLORS entry: '$colour_entry' (expected: ACCENT=89b4fa)"
        done
    fi

    # KEYBINDS: "id=MOD+SHIFT+L" entries separated by ';;', an empty value removes.
    if [[ -n "$KEYBINDS" ]]; then
        local bind_entry
        local -a bind_entries=()
        mapfile -t bind_entries < <(printf '%s\n' "${KEYBINDS//;;/$'\n'}")
        for bind_entry in "${bind_entries[@]}"; do
            [[ -z "$bind_entry" ]] && continue
            [[ "$bind_entry" =~ ^[a-z0-9-]+=((MOD|SUPER|SHIFT|CTRL|ALT)\+)*[A-Za-z0-9_:-]*$ ]] ||
                die "Invalid KEYBINDS entry: '$bind_entry' (expected: terminal=MOD+T)"
        done
    fi

    [[ "$WPENGINE_SCALING" =~ ^(default|stretch|fit|fill)$ ]] ||
        die "WPENGINE_SCALING must be 'default|stretch|fit|fill' (currently: $WPENGINE_SCALING)"
    [[ -z "$WPENGINE_FPS" || "$WPENGINE_FPS" =~ ^[0-9]+$ ]] ||
        die "WPENGINE_FPS must be empty or an integer (currently: $WPENGINE_FPS)"

    [[ -z "$WORKSPACE_SPLIT" || "$WORKSPACE_SPLIT" =~ ^(auto|off)$ ]] ||
        die "WORKSPACE_SPLIT must be empty, 'auto' or 'off' (currently: $WORKSPACE_SPLIT)"

    # WORKSPACE_MONITOR_MAP format: "no:monitor[:default]" entries separated by ';'
    if [[ -n "$WORKSPACE_MONITOR_MAP" ]]; then
        local entry
        IFS=';' read -r -a _wsmap <<<"$WORKSPACE_MONITOR_MAP"
        for entry in "${_wsmap[@]}"; do
            [[ -z "$entry" ]] && continue
            [[ "$entry" =~ ^[0-9]+:[^:]+(:default)?$ ]] ||
                die "Invalid WORKSPACE_MONITOR_MAP entry: '$entry' (expected: 1:DP-1 or 1:DP-1:default)"
        done
    fi
}

# Leaves the display files to another tool if that tool manages them.
#
# nwg-displays generates monitors.conf and workspaces.conf itself. As long as
# MANAGE_MONITORS=1 (the default) stayed, those files were regenerated every
# time the script ran — or whenever any setting changed in the settings app —
# and the display layout the user made in nwg-displays was reset entirely.
# The decision is made here and config_save writes it to settings.conf; so it
# is detected once and becomes permanent.
#
# Only runs in conf mode: in lua mode hyprland.lua requires monitors.lua with
# "{{#if MANAGE_MONITORS}}", so resetting the variable would not just skip
# generating the file, it would also mean the foreign tool's file is never
# READ. There, protection comes from render_install's foreign-file check.
config_adopt_foreign_monitors() {
    [[ "${HYPR_LANG_RESOLVED:-${HYPR_LANG:-conf}}" == conf ]] || return 0
    local owner
    owner=$(foreign_config_owner "$HOME/.config/hypr/monitors.conf")
    if [[ -n "$owner" && "${MANAGE_MONITORS:-1}" == 1 ]]; then
        MANAGE_MONITORS=0
        # shellcheck disable=SC2088  # literal ~ on purpose (path shown to the user / portable output)
        warn "~/.config/hypr/monitors.conf was generated by '$owner' — its contents will not be touched (MANAGE_MONITORS=0)."
        warn "If you want this script to manage the display layout, delete that file and run the install again."
    fi
    owner=$(foreign_config_owner "$HOME/.config/hypr/workspaces.conf")
    if [[ -n "$owner" && -n "${WORKSPACE_MONITOR_MAP:-}" ]]; then
        WORKSPACE_MONITOR_MAP=""
        # shellcheck disable=SC2088  # literal ~ on purpose (path shown to the user / portable output)
        warn "~/.config/hypr/workspaces.conf was generated by '$owner' — workspace mapping is left to it."
    fi
}

# Brings a value into a form that is safe to write to settings.conf:
# the SAME rule as python/hyprsetup/conffile.py:quote. Without special
# characters (" $ ` \) a readable "value"; otherwise single quotes, in which
# the shell expands nothing. Values used to be written as unescaped "value",
# and a value containing quotes/$ such as a custom module command was
# executed while the file was being READ.
_conf_quote() {  # <value>
    local value="$1"
    if [[ "$value" != *[\"\$\`\\]* ]]; then
        printf '"%s"' "$value"
    else
        printf "'%s'" "${value//\'/\'\\\'\'}"
    fi
}

# READS settings.conf — without source/eval.
#
# The file used to be sourced directly; since values were also written
# unescaped, a value containing "$(...)" (e.g. a custom module command) was
# EXECUTED while being read. The rule is the same as python/hyprsetup/conffile.py:unquote:
#   'value'   → as is; an inner '\'' sequence becomes a single quote
#   "value"   → as is; only $HOME / ${HOME} is expanded (hand-written
#               "$HOME/..." paths were always read that way)
#   value     → as is
# Does not need Python: this step runs before python is installed.
_CONF_COMMENT_RE='^("[^"]*"|'\''[^'\'']*'\''|[^[:space:]"'\'']+)[[:space:]]+#'
_conf_read() {  # <file>
    local line key raw value sq="'" esc="'\\''"
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line#"${line%%[![:space:]]*}"}"
        [[ -z "$line" || "$line" == \#* ]] && continue
        [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]] || continue
        key="${BASH_REMATCH[1]}"
        raw="${BASH_REMATCH[2]}"
        raw="${raw%"${raw##*[![:space:]]}"}"
        # Trailing comment (LAYOUT="dwindle"   # dwindle | master): if
        # whitespace + '#' follows a single-token value, the rest is dropped.
        # Same rule as conffile.py:strip_comment.
        [[ "$raw" =~ $_CONF_COMMENT_RE ]] && raw="${BASH_REMATCH[1]}"
        if ((${#raw} >= 2)) && [[ "$raw" == "$sq"*"$sq" ]]; then
            value="${raw:1:${#raw}-2}"
            value="${value//"$esc"/$sq}"
        elif ((${#raw} >= 2)) && [[ "$raw" == \"*\" ]]; then
            value="${raw:1:${#raw}-2}"
            value="${value//'${HOME}'/$HOME}"
            value="${value//'$HOME'/$HOME}"
        else
            value="$raw"
        fi
        printf -v "$key" '%s' "$value"
    done <"$1"
}

# Saves the active settings to a file (can be reused for reinstalling).
config_save() {
    local out="$1" var
    # On first install ~/.config/hyprsetup does not exist yet; keep the redirect from failing.
    mkdir -p -- "$(dirname -- "$out")"
    {
        printf '# hyprsetup — generated on %s\n' "$(date '+%Y-%m-%d %H:%M')"
        printf '# Reuse this file with --config to reproduce the same setup.\n\n'
        for var in "${CONFIG_VARS[@]}"; do
            printf '%s=%s\n' "$var" "$(_conf_quote "${!var-}")"
        done
        printf '\n# Selected components\n'
        printf 'COMPONENTS=%s\n' "$(_conf_quote "$(join_by , "${SELECTED[@]}")")"
    } >"$out"
    ok "Active settings saved: $out"
}
