"""Settings schema — the GUI widgets and help texts are generated from it.

The defaults here must match those in ``lib/config.sh`` exactly;
``python3 -m hyprsetup check-schema`` compares the two and reports differences.

To add a new setting: first add its default to ``lib/config.sh`` and its name
to the ``CONFIG_VARS`` list, then add a ``Setting`` here.
The GUI creates the matching widget automatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import baricons


@dataclass
class Setting:
    key: str
    label: str
    help: str = ""
    kind: str = "text"                 # bool | int | float | choice | text | image
    default: str = ""
    minimum: float = 0
    maximum: float = 100
    step: float = 1
    choices: list[tuple[str, str]] = field(default_factory=list)  # (value, label)
    unit: str = ""
    # Whether the live preview is redrawn when this setting changes
    affects_preview: bool = False
    # The bar backends that ACTUALLY apply this setting. Empty means
    # "backend-independent" and no note is shown in the UI.
    #
    # Why it exists: four backends read the same BAR_* settings but not all
    # of them can apply all of them — BAR_HEIGHT has no effect in Wayle (it
    # derives the height from font and padding), BAR_WORKSPACE_STYLE only
    # fully works in Waybar, a vertical position falls back to top in
    # HyprPanel. If this information is not in the schema, the user turns a
    # slider that does nothing and cannot tell why nothing changed.
    # The values are derived from the actual mappings in render.py.
    backends: tuple[str, ...] = ()
    # If a VALUE of this setting needs a program: value → dependency list
    # (see deps.py). Written as a component id or "pkg:<package>";
    # bool settings use the key "true", "any value other than off" uses "*".
    # The UI checks these BEFORE that value is selected and offers to
    # install what is missing — previously the setting turned on but, if the
    # program was missing, silently nothing happened.
    requires: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # Hidden in simple mode (see ADVANCED_KEYS). Not written by hand; set at
    # the end of the module from ADVANCED_KEYS/ADVANCED_GROUPS.
    advanced: bool = False


#: Font quick-pick list — (fontconfig family name, label).
#:
#: FONT_FAMILY is free text; this list is only a shortcut, you can type your
#: own font by hand. The entries are deliberately chosen from packages **this
#: project installs** (config/components.json → fonts-base /
#: fonts-extra); the labels say which one is needed, because fontconfig
#: silently replaces a family name that is not installed with another font.
FONT_SUGGESTIONS: list[tuple[str, str]] = [
    ("Noto Sans", "Noto Sans — UI default (base fonts)"),
    ("JetBrainsMono Nerd Font",
     "JetBrainsMono Nerd Font — monospace + icons (base fonts)"),
    ("Noto Serif", "Noto Serif — serif (base fonts)"),
    ("CaskaydiaCove Nerd Font",
     "CaskaydiaCove Nerd Font — Cascadia Code (needs extra fonts)"),
    ("Noto Sans CJK JP",
     "Noto Sans CJK JP — Chinese/Japanese/Korean (needs extra fonts)"),
    ("DejaVu Sans", "DejaVu Sans — available on almost every system"),
]


@dataclass
class Group:
    id: str
    title: str
    icon: str
    subtitle: str = ""
    settings: list[Setting] = field(default_factory=list)
    # The WHOLE group is hidden in simple mode (see ADVANCED_GROUPS).
    advanced: bool = False


def _theme_names() -> list[str]:
    """Preset palette names for the theme pickers (day/night theme)."""
    from .themes import THEMES
    return list(THEMES)


# ----------------------------------------------------------------- groups ---
GROUPS: list[Group] = [
    Group("layout", "Layout", "view-grid-symbolic",
          "How windows are arranged on the screen",
          [
              Setting("LAYOUT", "Tiling layout", kind="choice", default="dwindle",
                      choices=[("dwindle", "Dwindle — each new window splits the space in two"),
                               ("master", "Master — one main window, a stack beside it")],
                      help="Dwindle splits in a spiral; in master a large main "
                           "window sits on the left and the others stack on the right.",
                      affects_preview=True),
              Setting("GAPS_IN", "Gap between windows", kind="int", default="5",
                      minimum=0, maximum=40, unit="px", affects_preview=True,
                      help="Space left between two windows."),
              Setting("GAPS_OUT", "Screen edge gap", kind="int", default="12",
                      minimum=0, maximum=80, unit="px", affects_preview=True,
                      help="Space between the windows and the screen edge."),
              Setting("GAPS_WORKSPACES", "Workspace gap", kind="int",
                      default="0", minimum=0, maximum=200, unit="px",
                      help="Distance between workspaces in the switch animation."),
              Setting("BORDER_SIZE", "Border width", kind="int", default="2",
                      minimum=0, maximum=12, unit="px", affects_preview=True,
                      help="Frame width of the focused window. 0 = no border."),
              Setting("BORDER_ANGLE", "Border gradient angle", kind="int",
                      default="45", minimum=0, maximum=360, unit="°",
                      affects_preview=True,
                      help="The active border blends between two accent colors; "
                           "this angle sets the direction of the blend."),
              Setting("ROUNDING", "Corner rounding", kind="int", default="10",
                      minimum=0, maximum=40, unit="px", affects_preview=True,
                      help="Radius of window corners. 0 = sharp corners."),
              Setting("ROUNDING_POWER", "Corner curve", kind="int", default="2",
                      minimum=2, maximum=6, affects_preview=True,
                      help="2 = normal circle. Higher values turn the corner into "
                           "a 'squircle' (between square and circle)."),
              Setting("WORKSPACE_COUNT", "Number of workspaces", kind="int",
                      default="10", minimum=1, maximum=20,
                      help="How many workspaces get keyboard shortcuts."),
              Setting("WORKSPACE_SPLIT", "Split workspaces across displays",
                      kind="choice", default="",
                      choices=[("", "Off — every bar shows all workspaces"),
                               ("auto", "Automatic — split evenly across connected displays")],
                      help="Distributes workspaces across displays on multi-monitor "
                           "setups: with two displays and 10 workspaces, the first "
                           "gets 1-5 and the second 6-10. An nwg-displays mapping "
                           "takes precedence if present."),
              Setting("MASTER_MFACT", "Master ratio", kind="float",
                      default="0.55", minimum=0.1, maximum=0.9, step=0.05,
                      affects_preview=True,
                      help="Only applies when LAYOUT=master. The share of the "
                           "screen the main window takes; 0.55 = 55% of the "
                           "screen."),
              Setting("MASTER_NEW_STATUS", "Does a new window become master",
                      kind="choice", default="master",
                      choices=[("master", "Master — the new window becomes the main window"),
                               ("slave", "Slave — the new window joins the stack"),
                               ("inherit",
                                "Inherit — takes the role of the window it opened from")],
                      help="Only applies when LAYOUT=master."),
              Setting("DWINDLE_PRESERVE_SPLIT", "Preserve split direction",
                      kind="bool", default="true",
                      help="Only applies when LAYOUT=dwindle. When off, the "
                           "split direction may change as windows are moved "
                           "and resized."),
              Setting("DWINDLE_SMART_SPLIT", "Smart split", kind="bool",
                      default="false",
                      help="Only applies when LAYOUT=dwindle. When on, the "
                           "split direction follows the mouse position instead "
                           "of the window's aspect ratio."),
              Setting("DWINDLE_SMART_RESIZING", "Smart resizing",
                      kind="bool", default="true",
                      help="Only applies when LAYOUT=dwindle. When dragging a "
                           "window by its edge, the sibling window is resized "
                           "sensibly as well."),
          ]),

    Group("decoration", "Decoration", "applications-graphics-symbolic",
          "Blur, shadow and opacity",
          [
              Setting("BLUR", "Blur", kind="bool", default="true",
                      affects_preview=True,
                      help="Blurs what is behind transparent windows. "
                           "Puts some load on the GPU."),
              Setting("BLUR_SIZE", "Blur radius", kind="int", default="6",
                      minimum=1, maximum=20, affects_preview=True,
                      help="Size of the blur kernel. Higher values blur the "
                           "background more strongly."),
              Setting("BLUR_PASSES", "Blur passes", kind="int", default="3",
                      minimum=1, maximum=5, affects_preview=True,
                      help="More passes = smoother but more expensive."),
              Setting("BLUR_XRAY", "X-ray mode", kind="bool", default="false",
                      help="Blurs only the wallpaper, not the other windows "
                           "behind a window."),
              Setting("BLUR_SPECIAL", "Blur on special workspace", kind="bool",
                      default="false",
                      help="While a special workspace (e.g. scratchpad) is open, "
                           "also blurs the normal workspace behind it."),
              Setting("BLUR_POPUPS", "Blur popups",
                      kind="bool", default="true",
                      help="Also blurs what is behind popups such as "
                           "tooltips and menus."),
              Setting("BLUR_NOISE", "Grain", kind="float", default="0.0117",
                      minimum=0, maximum=0.2, step=0.005,
                      help="Adds a light texture to the blur to hide banding."),
              Setting("BLUR_CONTRAST", "Contrast", kind="float", default="0.9",
                      minimum=0, maximum=2, step=0.05,
                      help="Adjusts the contrast in the blurred area. 1.0 = "
                           "no change."),
              Setting("BLUR_BRIGHTNESS", "Brightness", kind="float", default="1.0",
                      minimum=0, maximum=2, step=0.05,
                      help="Adjusts the brightness in the blurred area. 1.0 = "
                           "no change."),
              Setting("BLUR_VIBRANCY", "Vibrancy", kind="float", default="0.17",
                      minimum=0, maximum=1, step=0.05,
                      help="Increases color saturation in the blurred area."),
              Setting("SHADOW", "Shadow", kind="bool", default="true",
                      affects_preview=True,
                      help="Turns the shadow cast behind windows on/off."),
              Setting("SHADOW_RANGE", "Shadow spread", kind="int", default="20",
                      minimum=0, maximum=80, unit="px", affects_preview=True,
                      help="How far the shadow extends past the window edge."),
              Setting("SHADOW_RENDER_POWER", "Shadow sharpness", kind="int",
                      default="3", minimum=1, maximum=4, affects_preview=True,
                      help="Higher values make the shadow fade faster from the edge."),
              Setting("SHADOW_OFFSET", "Shadow offset", kind="text",
                      default="0 4",
                      help="Pixel offset in \"x y\" form — how far the shadow "
                           "is shifted down/sideways relative to the window. "
                           "E.g. '0 4' = 4px down."),
              Setting("ACTIVE_OPACITY", "Focused window opacity", kind="float",
                      default="1.0", minimum=0.3, maximum=1.0, step=0.01,
                      affects_preview=True,
                      help="1.0 = fully opaque. Lower it and what is behind the "
                           "focused window shows through slightly."),
              Setting("INACTIVE_OPACITY", "Background window opacity",
                      kind="float", default="0.96", minimum=0.3, maximum=1.0,
                      step=0.01, affects_preview=True,
                      help="Opacity for unfocused windows. Usually kept a bit "
                           "lower to make the focused one stand out "
                           "visually."),
              Setting("DIM_INACTIVE", "Dim unfocused windows", kind="bool",
                      default="false", affects_preview=True,
                      help="When on, unfocused windows are dimmed by "
                           "DIM_STRENGTH."),
              Setting("DIM_STRENGTH", "Dim strength", kind="float", default="0.05",
                      minimum=0, maximum=1, step=0.05, affects_preview=True,
                      help="Amount of dimming applied while DIM_INACTIVE is on. "
                           "0 = no effect."),
              Setting("GLOBAL_OPACITY", "Global opacity", kind="text",
                      default="",
                      help="Empty = off. A number between 0 and 1 is applied to "
                           "ALL windows (apps where visual accuracy matters, "
                           "such as Firefox/mpv/GIMP, are excluded). Unlike "
                           "ACTIVE_OPACITY/INACTIVE_OPACITY, it makes no "
                           "theme/window distinction."),
              Setting("XWAYLAND_NO_BLUR", "Disable blur in XWayland",
                      kind="bool", default="false",
                      help="Disables blur for legacy (X11) apps to gain "
                           "performance."),
          ]),

    Group("bar", "Status Bar", "view-continuous-symbolic",
          "Waybar's position, size and look",
          [
              Setting("BAR_PRESET", "Bar preset", kind="text", default="",
                      help="Name of a preset under presets/bar/. Picked on the "
                           "Bar Presets page; the individual values here "
                           "override the preset. Writing this field by hand "
                           "does NOT affect the preview — it is only a label "
                           "showing which preset was applied last; actual "
                           "applying is done through the cards on the Bar "
                           "Presets page."),
              Setting("BAR_POSITION", "Position", kind="choice", default="top",
                      choices=[("top", "Top"), ("bottom", "Bottom"),
                               ("left", "Left"), ("right", "Right")],
                      affects_preview=True,
                      backends=("waybar", "hyprpanel", "quickshell-bar", "wayle"),
                      help="Which screen edge the bar sits on. Left/right "
                           "makes it vertical, and the width (BAR_WIDTH) "
                           "applies."),
              Setting("BAR_HEIGHT", "Height", kind="int", default="38",
                      minimum=20, maximum=80, unit="px", affects_preview=True,
                      backends=("waybar", "hyprpanel", "quickshell-bar"),
                      help="Applies to horizontal bars."),
              Setting("BAR_WIDTH", "Width", kind="int", default="44",
                      minimum=24, maximum=120, unit="px", affects_preview=True,
                      backends=("waybar", "quickshell-bar"),
                      help="Applies to vertical bars (left/right)."),
              Setting("BAR_MARGIN", "Gap from the edge", kind="int", default="6",
                      minimum=0, maximum=40, unit="px", affects_preview=True,
                      backends=("waybar", "hyprpanel", "quickshell-bar", "wayle"),
                      help="At 0 the bar sticks to the screen edge."),
              Setting("BAR_SPACING", "Gap between modules", kind="int",
                      default="6", minimum=0, maximum=24, unit="px",
                      backends=("waybar", "hyprpanel", "quickshell-bar", "wayle"),
                      help="Space left between modules in the same region "
                           "(left/center/right)."),
              Setting("BAR_PADDING", "Module padding", kind="int",
                      default="12", minimum=2, maximum=30, unit="px",
                      backends=("waybar", "hyprpanel", "quickshell-bar", "wayle"),
                      help="Space between a module's text/icon and the edge "
                           "of its own box."),
              Setting("BAR_RADIUS", "Module corner rounding", kind="int",
                      default="10", minimum=0, maximum=30, unit="px",
                      affects_preview=True,
                      backends=("waybar", "hyprpanel", "quickshell-bar"),
                      help="Corner radius of each module's separate background "
                           "box. 0 = sharp corners."),
              Setting("BAR_OPACITY", "Module background opacity", kind="float",
                      default="0.85", minimum=0.0, maximum=1.0, step=0.05,
                      affects_preview=True,
                      backends=("waybar", "hyprpanel", "quickshell-bar", "wayle"),
                      help="Background opacity of the module boxes. Affects the "
                           "individual module boxes, not the bar itself."),
              Setting("BAR_WORKSPACE_STYLE", "Workspace indicator",
                      kind="choice", default="numbers",
                      choices=[("numbers", "Numbers — 1 2 3"),
                               ("dots", "Dots — ● ○ ○"),
                               ("roman", "Roman numerals — I II III"),
                               ("pill-expand", "Active one expands"),
                               ("underline", "Underlined"),
                               ("bracket", "Bracketed — [ 1 2 3 ]"),
                               ("occupied-only", "Occupied workspaces only"),
                               ("app-icons", "Window icons"),
                               ("id-icons", "Number + window icons"),
                               ("named", "Named — desk web code")],
                      affects_preview=True,
                      backends=("waybar", "hyprpanel"),
                      help="How the workspace indicator is drawn on the "
                           "bar."),
              Setting("BAR_ICON_STYLE", "Bar icons",
                      kind="choice", default="material",
                      choices=baricons.CHOICES,
                      backends=("waybar",),
                      help="Icon set for the modules (CPU, volume, network, "
                           "battery, clock, power, microphone…). Emoji and "
                           "Text do not need a Nerd Font."),
              Setting("BAR_CLOCK_FORMAT", "Clock format", kind="text",
                      default="%H:%M",
                      backends=("waybar", "hyprpanel", "quickshell-bar", "wayle"),
                      help="strftime format. E.g. %H:%M:%S or %a %d %b %H:%M"),
              Setting("BAR_CLOCK_FORMAT_ALT", "On clock click", kind="text",
                      default="%d.%m.%Y %H:%M",
                      backends=("waybar",),
                      help="strftime format. Clicking the clock on the bar "
                           "briefly switches to this format; clicking again "
                           "switches back."),
              Setting("BAR_WINDOW_MAX_LENGTH", "Window title length",
                      kind="int", default="60", minimum=10, maximum=200,
                      unit=" chars",
                      backends=("waybar", "wayle"),
                      help="Maximum number of characters shown in the active "
                           "window title module; longer titles are truncated."),
              Setting("BAR_AUTOHIDE", "Auto-hide", kind="bool",
                      default="false",
                      backends=("waybar", "quickshell-bar"),
                      help="The bar slides off the screen and comes back when "
                           "the mouse touches that edge. In Waybar a separate "
                           "helper process does this (hypr/scripts/bar-autohide.py) "
                           "and the bar stops reserving space for windows; "
                           "in Quickshell the bar hides itself. "
                           "MOD+J toggles it by hand in either case."),
              Setting("BAR_AUTOHIDE_TRIGGER", "Hidden bar reveal distance",
                      kind="int", default="2", minimum=1, maximum=30,
                      unit=" px", backends=("waybar",),
                      help="The bar appears when the mouse gets this close to "
                           "the screen edge."),
              Setting("BAR_AUTOHIDE_RELEASE", "Hide margin", kind="int",
                      default="8", minimum=0, maximum=80, unit=" px",
                      backends=("waybar",),
                      help="The bar hides again once the mouse moves this far "
                           "outside it. Too small and the bar flickers."),
              Setting("WEATHER_LOCATION", "Weather location", kind="text",
                      default="",
                      backends=("waybar",),
                      help="The place the weather module queries — "
                           "\"Istanbul\", \"Berlin\" or a postal code. If left "
                           "empty, the location is guessed from the IP address. "
                           "The data source is wttr.in."),
              Setting("WEATHER_UNIT", "Temperature unit", kind="choice",
                      default="metric",
                      choices=[("metric", "Celsius (°C)"),
                               ("imperial", "Fahrenheit (°F)")],
                      backends=("waybar",),
                      help="Unit system of the weather module."),
              Setting("WEATHER_REFRESH", "Weather refresh", kind="int",
                      default="15", minimum=5, maximum=180, step=5,
                      unit=" min", backends=("waybar",),
                      help="wttr.in is not queried more often than this; a very "
                           "short interval can get you temporarily blocked."),
          ]),

    # Three slots where users put their own command on the bar. Why three
    # separate key sets rather than a single list: commands freely contain
    # commas, semicolons and quotes (df -h / | awk 'NR==2{print $4}'), a
    # one-line list syntax would have to escape them and settings.conf would
    # no longer be editable by hand.
    #
    # The slots appear in the bar layout as the "custom/user1..3" module
    # (see render.BAR_MODULES); a slot with an empty command is not written
    # to the generated config at all.
    Group("bar_custom", "Custom Bar Modules", "view-continuous-symbolic",
          "Shows the output of your own command on the bar",
          [
              *(setting
                for slot in (1, 2, 3)
                for setting in (
                    Setting(f"BAR_CUSTOM{slot}_CMD", f"Slot {slot}: command",
                            kind="text", default="",
                            backends=("waybar",),
                            help="Command to run in the shell. The FIRST line "
                                 "of its output shows on the bar. If left "
                                 "empty, this slot is not generated."),
                    Setting(f"BAR_CUSTOM{slot}_FORMAT", f"Slot {slot}: format",
                            kind="text", default="",
                            backends=("waybar",),
                            help="Template the command output is placed in; "
                                 "{} is the output itself. E.g. \"󰋊 {}\". "
                                 "If left empty, the output is shown as "
                                 "is."),
                    Setting(f"BAR_CUSTOM{slot}_INTERVAL",
                            f"Slot {slot}: refresh", kind="int",
                            default="60", minimum=1, maximum=3600, unit=" s",
                            backends=("waybar",),
                            help="How many seconds between runs of the "
                                 "command."),
                    Setting(f"BAR_CUSTOM{slot}_CLICK", f"Slot {slot}: click",
                            kind="text", default="",
                            backends=("waybar",),
                            help="Command to run when the module is clicked. If "
                                 "left empty, clicking does nothing."),
                )),
          ]),

    # TERMINAL/LAUNCHER themselves (which program) are not here — like
    # WIDGET_ENGINE they come from the component category. These are that
    # program's look: all four understand the same keys, ones without an
    # equivalent are skipped.
    Group("dock", "Dock", "view-app-grid-symbolic",
          "A bar floating at the screen edge that holds only app icons "
          "(nwg-dock-hyprland). Works independently of the status bar "
          "you choose. Right-click an icon to pin or unpin "
          "it.",
          [
              Setting("DOCK_ENABLE", "Show the dock", kind="bool",
                      default="false", requires={"true": ("dock",)},
                      affects_preview=True,
                      help="Starts right away when turned on and launches by "
                           "itself at every login. On first start your terminal, "
                           "browser and file manager come pinned."),
              Setting("DOCK_POSITION", "Position", kind="choice", default="bottom",
                      choices=[("bottom", "Bottom"), ("left", "Left"),
                               ("right", "Right"), ("top", "Top")],
                      affects_preview=True,
                      help="If you pick the same edge as the status bar, the "
                           "two overlap."),
              Setting("DOCK_AUTOHIDE", "Auto-hide", kind="bool",
                      default="false", affects_preview=True,
                      help="When on, the dock only appears when the mouse goes "
                           "to that screen edge. When off, it is always visible "
                           "and windows do not go under it."),
              Setting("DOCK_ICON_SIZE", "Icon size", kind="int",
                      default="40", minimum=24, maximum=96, step=4, unit="px",
                      affects_preview=True),
              Setting("DOCK_MARGIN", "Gap from the edge", kind="int", default="8",
                      minimum=0, maximum=60, unit="px", affects_preview=True,
                      help="How far above the screen edge the dock floats. "
                           "0 = flush with the edge."),
              Setting("DOCK_RADIUS", "Corner rounding", kind="int",
                      default="18", minimum=0, maximum=40, unit="px",
                      affects_preview=True),
              Setting("DOCK_OPACITY", "Background opacity", kind="float",
                      default="0.85", minimum=0.2, maximum=1.0, step=0.05,
                      affects_preview=True,
                      help="1 = fully solid. The color comes from the selected theme."),
              Setting("DOCK_LAUNCHER", "App menu button", kind="bool",
                      default="true", affects_preview=True,
                      help="A button at the end of the dock that opens the "
                           "selected launcher (wofi, rofi, fuzzel…)."),
              Setting("DOCK_MONITOR", "Display", kind="text", default="",
                      help="Empty = whichever display the mouse is on. For a "
                           "specific display, write its Hyprland name (e.g. DP-1)."),
          ]),
    Group("terminal", "Terminal", "utilities-terminal-symbolic",
          "Look of the selected terminal — kitty, foot, Alacritty, Ghostty and "
          "WezTerm are generated from the same settings",
          [
              Setting("TERM_OPACITY", "Background opacity", kind="float",
                      default="0.95", minimum=0.0, maximum=1.0, step=0.05,
                      help="Background opacity of the terminal window. "
                           "Separate from Hyprland's window opacity: this "
                           "only affects what is behind the text."),
              Setting("TERM_PADDING", "Padding", kind="int", default="8",
                      minimum=0, maximum=40, unit="px",
                      help="Space between the text and the window edge."),
              Setting("TERM_FONT_SIZE", "Font size", kind="text",
                      default="",
                      help="If left empty, the global FONT_SIZE is used. "
                           "Write a number here if you want a smaller/larger "
                           "size in the terminal."),
              Setting("TERM_CURSOR_STYLE", "Cursor style", kind="choice",
                      default="block",
                      choices=[("block", "Block — █"),
                               ("beam", "Beam — |"),
                               ("underline", "Underline — _")],
                      help="All four terminals support it; the name "
                           "mapping is done at render time."),
              Setting("TERM_CURSOR_BLINK", "Blinking cursor", kind="bool",
                      default="false",
                      help="When off, the cursor stays steady."),
              Setting("TERM_SCROLLBACK", "Scrollback lines", kind="int",
                      default="10000", minimum=0, maximum=200000,
                      help="Number of lines reachable by scrolling up. "
                           "Ghostty wants this as a byte limit, so it is "
                           "converted assuming ~1 KB per line."),
          ]),

    # Logo + system info (fastfetch) when the terminal opens, and an image
    # behind the window. Images picked in the UI are converted to PNG and
    # copied under ~/.config/hyprsetup/images/ (kitty wants PNG).
    Group("terminal_look", "Startup screen and background", "image-x-generic-symbolic",
          "Logo and system info (fastfetch) when a terminal opens, "
          "an image behind the window",
          [
              Setting("TERM_FETCH", "Logo and system info on startup", kind="choice",
                      default="default",
                      choices=[("default", "Leave as is — distro default"),
                               ("on", "Show"),
                               ("off", "Don't show")],
                      requires={"on": ("fastfetch", "cli-tools")},
                      affects_preview=True,
                      help="fastfetch runs in every new terminal window "
                           "(bash, zsh, fish). On distros that already run "
                           "fastfetch in the fish greeting, like CachyOS, \"Leave as is\" "
                           "leaves it untouched; \"Show\" prevents it from "
                           "appearing twice."),
              Setting("TERM_LOGO", "Logo", kind="choice", default="distro",
                      choices=[("distro", "Distro logo"),
                               ("small", "Small distro logo"),
                               ("souprland", "Souprland logo"),
                               ("image", "My own image"),
                               ("none", "No logo")],
                      affects_preview=True,
                      help="Images are drawn as real images in kitty, Ghostty "
                           "and WezTerm; foot and Alacritty cannot show "
                           "images, so there they are drawn from characters "
                           "with chafa (needs the chafa package)."),
              Setting("TERM_LOGO_IMAGE", "Logo image", kind="image", default="",
                      affects_preview=True,
                      help="Used when Logo is \"My own image\"."),
              Setting("TERM_LOGO_STYLE", "Drawing style", kind="choice",
                      default="image",
                      choices=[("image", "Real image"),
                               ("braille", "Dots — ⣿⣷⣄"),
                               ("block", "Blocks — ▟█▙"),
                               ("ascii", "Letters — @#*:")],
                      affects_preview=True,
                      help="For the Souprland logo and your own image. The dots, "
                           "block and letter styles draw the image from "
                           "characters (chafa); it looks the same in every "
                           "terminal. Real image falls back to blocks in foot "
                           "and Alacritty."),
              Setting("TERM_LOGO_MONO", "Single-color logo", kind="bool",
                      default="false", affects_preview=True,
                      help="In the character styles, draws the logo in the "
                           "terminal's text color instead of the image's colors."),
              Setting("TERM_LOGO_WIDTH", "Logo width", kind="int",
                      default="24", minimum=8, maximum=60, unit=" columns",
                      affects_preview=True,
                      help="Width of image logos in character cells; the "
                           "height follows from the aspect ratio."),
              Setting("TERM_FETCH_INFO", "Amount of info", kind="choice",
                      default="short",
                      choices=[("short", "Short — system, kernel, uptime, memory"),
                               ("full", "Full — hardware, theme, packages…")],
                      affects_preview=True),
              Setting("TERM_BG_IMAGE", "Background image", kind="image", default="",
                      affects_preview=True,
                      help="Shown behind the text. Supported by kitty, Ghostty "
                           "and WezTerm; no effect in foot and Alacritty."),
              Setting("TERM_BG_DIM", "Dim the image", kind="float", default="0.75",
                      minimum=0.0, maximum=0.95, step=0.05, affects_preview=True,
                      help="The image is darkened with the theme's background "
                           "color so it does not make the text hard to read. "
                           "0 is the image itself."),
              Setting("TERM_BG_FIT", "Placement", kind="choice", default="cover",
                      choices=[("cover", "Fill the window"),
                               ("center", "Center"),
                               ("tile", "Tile")],
                      affects_preview=True),
          ]),

    Group("launcher", "Launcher", "system-search-symbolic",
          "Look of the app launcher — wofi, rofi, fuzzel, walker and "
          "tofi are generated from the same settings",
          [
              Setting("LAUNCHER_WIDTH", "Width", kind="int", default="45",
                      minimum=15, maximum=100, unit="%",
                      help="Percentage of the screen width. fuzzel wants the "
                           "width in characters, so it is converted to an "
                           "approximate equivalent there."),
              Setting("LAUNCHER_LINES", "Result lines", kind="int",
                      default="10", minimum=1, maximum=30,
                      help="Number of results visible at once."),
              Setting("LAUNCHER_POSITION", "Position", kind="choice",
                      default="center",
                      choices=[("center", "Center of the screen"),
                               ("top", "Top edge")],
                      help="Where the launcher window sits on the screen."),
              Setting("LAUNCHER_OPACITY", "Background opacity", kind="float",
                      default="0.93", minimum=0.0, maximum=1.0, step=0.05,
                      help="Background opacity of the launcher window."),
              Setting("LAUNCHER_ICONS", "App icons", kind="bool",
                      default="true",
                      help="When off, only app names are listed — "
                           "the plainest look."),
              Setting("LAUNCHER_ICON_SIZE", "Icon size", kind="int",
                      default="32", minimum=8, maximum=64, unit="px",
                      help="No effect if app icons are off."),
              Setting("LAUNCHER_PROMPT", "Prompt text", kind="text",
                      default="Search…",
                      help="Text shown to the left of the search box."),
              Setting("LAUNCHER_RADIUS", "Corner radius", kind="text",
                      default="",
                      help="Empty = same as windows (the Rounding setting). "
                           "0 is square, 16+ clearly rounded."),
              Setting("LAUNCHER_BORDER", "Border width", kind="text",
                      default="",
                      help="Empty = same as the window border. 0 = no border."),
              Setting("LAUNCHER_PROVIDERS", "Enabled providers", kind="text",
                      default="calc,websearch,clipboard,symbols,files,windows,"
                              "runner,providerlist",
                      help="walker ONLY: sources the launcher can query in "
                           "addition to the app list. Each one is invoked "
                           "with its own prefix (= calculator, "
                           ": clipboard, . symbols…). Names are comma-separated; "
                           "valid ones are in the render.LAUNCHER_PROVIDERS "
                           "table. wofi/rofi/fuzzel/tofi ignore this "
                           "setting."),
          ]),

    # WIDGET_ENGINE is deliberately not here: like BAR/TERMINAL it derives
    # from the component category (config/components.json → "widget") and is
    # written to the settings file in the "Primary tools" section. If it were
    # also added to the schema, the same key would land twice in the
    # generated settings.conf.
    Group("widget", "Look and size", "view-grid-symbolic",
          "Shared sizes for all widget boxes",
          [
              Setting("WIDGETS", "Enabled widgets", kind="text", default="",
                      help="Comma-separated names (presets/widget/). "
                           "E.g. clock,calendar,disk — a Widget Engine must "
                           "be selected on the Components page for them to "
                           "work. In the UI this line is written via the "
                           "corner lists."),
              # The corner lists determine placement; for a corner left empty
              # each widget's default corner from the catalog applies
              # (see render.WIDGET_CATALOG).
              Setting("WIDGET_ZONE_TL", "Top left corner", kind="text", default="",
                      help="Widgets stacked top to bottom in this corner, "
                           "comma-separated."),
              Setting("WIDGET_ZONE_TC", "Top center", kind="text", default="",
                      help="On the top edge of the screen, centered "
                           "horizontally; stacked top to bottom."),
              Setting("WIDGET_ZONE_TR", "Top right corner", kind="text", default="",
                      help="Widgets stacked top to bottom in this corner."),
              Setting("WIDGET_ZONE_BL", "Bottom left corner", kind="text", default="",
                      help="Widgets stacked bottom to top in this corner."),
              Setting("WIDGET_ZONE_BC", "Bottom center", kind="text", default="",
                      help="On the bottom edge of the screen, centered "
                           "horizontally; stacked bottom to top."),
              Setting("WIDGET_ZONE_BR", "Bottom right corner", kind="text", default="",
                      help="Widgets stacked bottom to top in this corner."),
              Setting("WIDGET_OFFSETS", "Per-widget offset", kind="text",
                      default="",
                      help="name:x:y list, e.g. clock:20:-10,calendar:0:40. "
                           "x is extra distance from the horizontal edge, y "
                           "from the vertical edge (px); a negative value "
                           "moves it closer to the edge. A vertical offset "
                           "also pushes the widgets below it in the same "
                           "corner. x is not applied in the center positions."),
              Setting("WIDGET_LAYER", "Layer", kind="choice", default="bottom",
                      choices=[("bottom", "Desktop — BELOW windows"),
                               ("top", "Top — above windows")],
                      help="On a tiling desktop the screen is almost always "
                           "covered by windows; widgets on the 'desktop' "
                           "layer are only visible on an empty workspace. "
                           "If you want to see them at any time, choose "
                           "'top' and toggle them with MOD+G."),
              Setting("WIDGET_AUTOSTART", "Show on startup", kind="bool",
                      default="true",
                      help="When off, widgets are not shown at session "
                           "start; they only open with the MOD+G "
                           "binding. That is the natural use together with "
                           "the 'Top' layer."),
              Setting("WIDGET_MONITOR", "Display", kind="text", default="",
                      help="Empty = first display (0). Write an index: 0, 1… "
                           "A display NAME is accepted too, but it is NOT the "
                           "connector name Hyprland uses (DP-1); it is the "
                           "display's model name (\"MSI G2412F\"); if a "
                           "connector name is given the widgets never open. "
                           "Only applies to the eww engine."),
              Setting("WIDGET_MARGIN", "Gap from the screen edge", kind="int",
                      default="16", minimum=0, maximum=120, unit="px",
                      affects_preview=True,
                      help="Distance of the first widget from the screen edge. "
                           "On the edge the bar occupies, the bar thickness is "
                           "added to it, so widgets do not end up under the bar."),
              Setting("WIDGET_GAP", "Gap between widgets", kind="int",
                      default="10", minimum=0, maximum=60, unit="px",
                      affects_preview=True,
                      help="Space between widgets stacked in the same "
                           "corner."),
              Setting("WIDGET_SCALE", "Scale", kind="float", default="1.0",
                      minimum=0.5, maximum=2.0, step=0.05,
                      affects_preview=True,
                      help="Enlarges/shrinks the widget boxes and their text "
                           "together. 1.0 = the designed size."),
              Setting("WIDGET_RADIUS", "Corner rounding", kind="int",
                      default="12", minimum=0, maximum=999, unit="px",
                      affects_preview=True,
                      help="Corner radius of the widget box. A value above half "
                           "the box height (e.g. 999) makes a pill."),
              Setting("WIDGET_OPACITY", "Background opacity", kind="float",
                      default="0.85", minimum=0.0, maximum=1.0, step=0.05,
                      affects_preview=True,
                      help="Opacity of the box background. The text always "
                           "stays fully opaque."),
              # ---- Look: written together by a widget style
              # (presets/widget-style/, WIDGET_STYLE) and changeable one by one.
              # The Quickshell engine draws all of them; eww uses the plate,
              # border and surface settings only.
              Setting("WIDGET_BOX", "Draw a box", kind="bool", default="true",
                      affects_preview=True,
                      help="Off: no plate at all — the text sits straight on "
                           "the wallpaper with a soft shadow."),
              Setting("WIDGET_SURFACE", "Box colour", kind="choice", default="bg",
                      choices=[("bg", "Background — the theme's darkest tone"),
                               ("surface", "Surface — the lighter tonal colour")],
                      affects_preview=True,
                      help="Which theme colour the box is painted with."),
              Setting("WIDGET_BORDER", "Border width", kind="int", default="2",
                      minimum=0, maximum=8, unit="px", affects_preview=True,
                      help="0 = no border."),
              Setting("WIDGET_BORDER_TONE", "Border colour", kind="choice",
                      default="accent",
                      choices=[("accent", "Accent — the theme's accent colour"),
                               ("soft", "Soft — faded accent"),
                               ("light", "Light — a thin glass edge")],
                      affects_preview=True),
              Setting("WIDGET_SHADOW", "Drop shadow", kind="bool", default="false",
                      help="A soft shadow under each box (Quickshell)."),
              Setting("WIDGET_BLUR", "Blur behind boxes", kind="bool",
                      default="false",
                      help="Hyprland blurs the wallpaper behind the box — the "
                           "frosted-glass look. Best with a low opacity "
                           "(Quickshell)."),
              Setting("WIDGET_METER", "Gauges", kind="choice", default="text",
                      choices=[("text", "Text — \"CPU 39%\""),
                               ("bar", "Bar — a thin progress bar"),
                               ("ring", "Ring — a circular gauge")],
                      affects_preview=True,
                      help="How CPU/RAM, disk, battery, volume, brightness and "
                           "temperature are drawn (Quickshell)."),
              Setting("WIDGET_MUSIC", "Music widget", kind="choice",
                      default="line",
                      choices=[("line", "Line — artist and title"),
                               ("card", "Card — cover, progress and buttons")],
                      affects_preview=True,
                      help="(Quickshell)"),
              Setting("WIDGET_CLOCK", "Clock", kind="choice", default="compact",
                      choices=[("compact", "Compact — time and date in a small box"),
                               ("large", "Large — a big thin clock"),
                               ("stacked", "Stacked — hours over minutes")],
                      affects_preview=True,
                      help="(Quickshell)"),
          ]),

    Group("visualizer", "Audio visualizer", "audio-x-generic-symbolic",
          "Spectrum bars at the bottom edge of the screen that react to music. "
          "They sit above the wallpaper and below windows, and do not push "
          "them. cava listens to the playing audio; drawn with kitty's panel mode.",
          [
              Setting("VIS_ENABLE", "Show the visualizer", kind="bool",
                      default="false", requires={"true": ("kitty", "cava")},
                      help="Starts right away when turned on and launches by "
                           "itself at every login. Bass in the middle, treble at the edges."),
              Setting("VIS_MODE", "Placement", kind="choice", default="desktop",
                      choices=[("desktop", "Desktop — behind windows"),
                               ("strip", "Bottom strip — always visible")],
                      help="In the bottom strip, windows shrink by the height of "
                           "the bars and clicks are not blocked. On the desktop, "
                           "the bars are only visible on an empty workspace."),
              Setting("VIS_COLOR", "Color", kind="text", default="",
                      help="#rrggbb. Empty: the theme's accent color."),
              Setting("VIS_BRIGHTNESS", "Brightness", kind="int", default="60",
                      minimum=20, maximum=100, unit=" %",
                      help="The color is dimmed toward the background; lower is fainter."),
              Setting("VIS_HEIGHT", "Height", kind="int", default="130",
                      minimum=40, maximum=400, unit=" px"),
              Setting("VIS_WIDTH", "Width", kind="int", default="60",
                      minimum=20, maximum=100, unit=" %",
                      help="Percentage of the screen width, centered."),
              Setting("VIS_MONITOR", "Display", kind="text", default="",
                      help="Output name (e.g. DP-1; hyprctl monitors). Empty: "
                           "every display."),
          ]),

    Group("animation", "Animation", "media-playback-start-symbolic",
          "Window and workspace transitions",
          [
              Setting("ANIMATIONS", "Animations", kind="bool", default="true",
                      help="If you turn them off, all transitions such as "
                           "opening/closing windows and switching workspaces "
                           "happen instantly."),
              Setting("ANIMATION_PRESET", "Character", kind="choice",
                      default="default", affects_preview=True,
                      choices=[("default", "Balanced — medium speed, light popin"),
                               ("snappy", "Snappy — very short, instant response"),
                               ("fluid", "Fluid — long, smooth, springy"),
                               ("minimal", "Minimal — fade only"),
                               ("none", "Off — no animation at all"),
                               ("custom", "Custom — set from a mix")],
                      help="The animation's set of curves and durations. The "
                           "speed setting is applied on top of it as a "
                           "multiplier: the preset answers 'how', speed "
                           "'how fast'."),
              Setting("ANIMATION_SPEED", "Speed", kind="float", default="1.0",
                      minimum=0.3, maximum=3.0, step=0.1, unit="×",
                      help="1.0 = default. 2.0 twice as fast, 0.5 twice as slow. "
                           "All animation durations are scaled by this factor."),
              Setting("ANIMATION_CUSTOM", "Custom animation lines", kind="text",
                      default="",
                      help="Used when Character is 'Custom'. Hyprland lines "
                           "joined with ';;': \"bezier = name, 0.2, 1, 0.3, 1;;"
                           "animation = windows, 1, 6, name, popin 80%\". The "
                           "Soup Maker page moves a profile's animations "
                           "here."),
              Setting("RICE_TRANSITION", "Transition animation on theme change",
                      kind="bool", default="true",
                      help="While a profile or mix is being applied, the "
                           "screen freezes, soup cooks on top of it, and the "
                           "new desktop fades in. When off, a short black "
                           "screen appears during the switch."),
          ]),

    Group("behavior", "Behavior", "preferences-system-symbolic",
          "Window management and display behavior",
          [
              Setting("ALLOW_TEARING", "Allow screen tearing", kind="bool",
                      default="false",
                      help="Reduces latency in games but the image may tear. "
                           "When on, the 'immediate' window rule is applied to games."),
              Setting("VRR", "Variable refresh rate (VRR)", kind="choice", default="1",
                      choices=[("0", "Off"), ("1", "On"),
                               ("2", "Fullscreen only")],
                      help="FreeSync/G-Sync support. Turn it off if it causes "
                           "flicker on some displays."),
              Setting("SNAP", "Snap floating windows", kind="bool",
                      default="true",
                      help="Floating windows align magnetically to edges and "
                           "other windows."),
              Setting("SNAP_WINDOW_GAP", "Window snap distance",
                      kind="int", default="4", minimum=0, maximum=40, unit="px",
                      help="Only applies while SNAP is on. A window snaps "
                           "to another once it comes within this distance."),
              Setting("SNAP_MONITOR_GAP", "Screen edge snap distance",
                      kind="int", default="5", minimum=0, maximum=40, unit="px",
                      help="Only applies while SNAP is on. A window snaps "
                           "to the screen edge once it comes within this distance."),
              Setting("RESIZE_ON_BORDER", "Resize from the border", kind="bool",
                      default="true",
                      help="Resize a window by clicking and dragging its border."),
              Setting("WINDOWRULES", "Extra window rules", kind="text",
                      default="",
                      help="Hyprland 0.51+ rule bodies separated by ';;' "
                           "(without the leading 'windowrule = '). Example: "
                           "float on, match:class ^(pavucontrol)$;;"
                           "opacity 0.9, match:class ^(kitty)$ — profiles "
                           "carry their own character through this. "
                           "Not applied in the experimental HYPR_LANG=lua mode; "
                           "only written as a comment."),
              Setting("USER_WINDOWRULES", "My own window rules", kind="text",
                      default="",
                      help="Rules written by the Window Rules page "
                           "(same format as WINDOWRULES). Kept when the "
                           "profile changes; written after the profile's "
                           "rules, so they override them."),
              Setting("RULE_SUPPRESS_MAXIMIZE", "Prevent self-maximizing",
                      kind="bool", default="true",
                      help="Apps cannot enlarge themselves to cover the "
                           "screen when they open; the tiling layout is preserved."),
              Setting("RULE_FLOAT_TOOLS", "Float tool windows",
                      kind="bool", default="true",
                      help="Audio/network/Bluetooth settings, file pickers, "
                           "theme tools and the archive manager are not tiled; "
                           "they float in the center."),
              Setting("RULE_PIP", "Keep picture-in-picture in the corner",
                      kind="bool", default="true",
                      help="The browser's small video window floats in the "
                           "bottom right corner and shows on every workspace."),
              Setting("PIP_WIDTH", "Picture-in-picture width", kind="int",
                      default="640", minimum=240, maximum=1920, step=20,
                      unit=" px", help="The height is computed at a 16:9 ratio."),
              Setting("QUICK_PANEL_WIDTH", "Settings panel width", kind="int",
                      default="80", minimum=40, maximum=100, step=5, unit=" %",
                      help="Size of the MOD+I panel relative to the screen."),
              Setting("QUICK_PANEL_HEIGHT", "Settings panel height", kind="int",
                      default="80", minimum=40, maximum=100, step=5, unit=" %"),
              Setting("ENABLE_SWALLOW", "Terminal swallowing", kind="bool",
                      default="false",
                      help="When you open a GUI app from a terminal, the "
                           "terminal window is hidden and comes back when the app closes."),
              Setting("SWALLOW_REGEX", "Terminals to swallow", kind="text",
                      default="^(kitty|foot|Alacritty|com.mitchellh.ghostty|org.wezfurlong.wezterm)$",
                      help="Only applies while ENABLE_SWALLOW is on. "
                           "Regex selecting which terminal window classes "
                           "get swallowed."),
              Setting("NO_FOCUS_FALLBACK", "No focus fallback", kind="bool",
                      default="false",
                      help="When on, Hyprland does not try to focus another "
                           "window automatically when the focused window closes."),
              Setting("FOCUS_ON_ACTIVATE", "Focus on activation request",
                      kind="bool", default="true",
                      help="Whether an app that asks to come to the front "
                           "(e.g. a notification click) actually gets focus, "
                           "or only requests attention (urgent)."),
              Setting("ANIMATE_MANUAL_RESIZES", "Animate manual resizing",
                      kind="bool", default="false",
                      help="Whether the window animation also plays while "
                           "resizing by dragging with the mouse. When off it "
                           "feels instant, with less latency."),
              Setting("SCROLL_EVENT_DELAY", "Scroll event delay",
                      kind="int", default="0", minimum=0, maximum=500, unit="ms",
                      help="Mandatory minimum time between mouse wheel events. "
                           "Prevents a single scroll from registering as "
                           "multiple steps on some mice."),
              Setting("DIM_SPECIAL", "Special workspace dimming", kind="float",
                      default="0.2", minimum=0, maximum=1, step=0.05,
                      help="How much the normal workspace behind is dimmed "
                           "while a special workspace (e.g. scratchpad) is open."),
              Setting("ON_FOCUS_UNDER_FULLSCREEN", "Focus under fullscreen",
                      kind="choice", default="2",
                      choices=[("0", "Ignore"), ("1", "Exit fullscreen"),
                               ("2", "Send fullscreen to back")],
                      help="What happens when another window is focused while "
                           "a fullscreen window exists."),
              Setting("DPMS_ON_INPUT", "Mouse/keyboard wakes the display",
                      kind="bool", default="true",
                      help="While the display is off, moving the mouse or "
                           "pressing a key turns it back on."),
              Setting("HIDE_SPECIAL_ON_WS_CHANGE", "Hide scratchpad on workspace change",
                      kind="bool", default="true",
                      help="When on, a special workspace (scratchpad etc.) "
                           "left open closes automatically when you switch to "
                           "a normal workspace."),
          ]),

    Group("input", "Input", "input-keyboard-symbolic",
          "Keyboard, mouse and touchpad",
          [
              Setting("KB_LAYOUT", "Keyboard layout", kind="text", default="us",
                      help="XKB layout code (e.g. us, tr). For several layouts, "
                           "separate them with commas: us,tr — add a switch key "
                           "such as grp:alt_shift_toggle to KB_OPTIONS to "
                           "switch between them."),
              Setting("KB_VARIANT", "Layout variant", kind="text", default="",
                      help="E.g. for a Turkish F keyboard: f"),
              Setting("KB_OPTIONS", "Keyboard options", kind="text", default="",
                      help="E.g. grp:alt_shift_toggle,caps:escape"),
              Setting("REPEAT_DELAY", "Key repeat delay", kind="int",
                      default="250", minimum=100, maximum=1000, step=10, unit="ms",
                      help="How long to hold a key before repeating "
                           "starts."),
              Setting("REPEAT_RATE", "Key repeat rate", kind="int", default="35",
                      minimum=5, maximum=100, unit="/s",
                      help="How many times per second a held key "
                           "repeats."),
              Setting("NUMLOCK", "Start with NumLock on", kind="bool", default="true",
                      help="Turns on the numeric keypad lock automatically at "
                           "session start."),
              Setting("FOLLOW_MOUSE", "Mouse focus", kind="choice", default="1",
                      choices=[("0", "Off — only on click"),
                               ("1", "Normal — on mouse hover"),
                               ("2", "Loose"), ("3", "Full")],
                      help="Whether hovering the mouse over a window changes "
                           "focus, and how closely focus follows the "
                           "mouse."),
              Setting("SENSITIVITY", "Mouse sensitivity", kind="float", default="0",
                      minimum=-1.0, maximum=1.0, step=0.05,
                      help="libinput mouse speed. 0 = default, negative values "
                           "slow it down, positive values speed it up."),
              Setting("ACCEL_PROFILE", "Mouse acceleration", kind="choice", default="",
                      choices=[("", "System default"), ("flat", "Flat — no acceleration"),
                               ("adaptive", "Adaptive")],
                      help="With Flat, cursor speed ignores how fast you move "
                           "the mouse; preferred for gaming/design "
                           "work."),
              Setting("OFF_WINDOW_AXIS_EVENTS", "Scrolling over empty space", kind="int",
                      default="1", minimum=0, maximum=2,
                      help="How much wheel scrolling does when the cursor is "
                           "not over any window (on the empty desktop). "
                           "0 = ignore, 2 = full."),
              Setting("NATURAL_SCROLL", "Natural scrolling", kind="bool",
                      default="false", help="Reversed scroll direction on the touchpad."),
              Setting("TOUCHPAD_TAP", "Tap to click", kind="bool", default="true",
                      help="Allows clicking with a light tap on the touchpad "
                           "without pressing the button."),
              Setting("TOUCHPAD_DWT", "Disable touchpad while typing", kind="bool",
                      default="true",
                      help="\"Disable While Typing\": briefly disables the "
                           "touchpad while typing on the keyboard to prevent "
                           "accidental touches."),
              Setting("TOUCHPAD_CLICKFINGER", "Two fingers = right click", kind="bool",
                      default="false",
                      help="When on, right click depends on how many fingers "
                           "are on the pad when clicking (two fingers = right "
                           "click); when off you have to click the bottom corner of the pad."),
              Setting("TOUCHPAD_SCROLL_FACTOR", "Scroll factor", kind="float",
                      default="0.8", minimum=0.1, maximum=3.0, step=0.1,
                      help="Scales the scroll speed on the touchpad. "
                           "1.0 = no change."),
          ]),

    Group("gestures", "Gestures", "input-touchpad-symbolic",
          "Touchpad swipe gestures",
          [
              Setting("GESTURE_SWIPE", "Swipe gestures", kind="bool",
                      default="true",
                      help="Switch workspaces by swiping with fingers on the "
                           "touchpad."),
              Setting("GESTURE_FINGERS", "Number of fingers", kind="choice", default="3",
                      choices=[("3", "3 fingers"), ("4", "4 fingers"),
                               ("5", "5 fingers")],
                      help="Number of fingers that triggers the workspace "
                           "switch swipe."),
              Setting("SWIPE_DISTANCE", "Swipe distance", kind="int",
                      default="300", minimum=100, maximum=1000, step=50, unit="px",
                      help="Finger travel needed to move one workspace. "
                           "Larger value = slower transition."),
              Setting("SWIPE_CANCEL_RATIO", "Cancel threshold", kind="float",
                      default="0.5", minimum=0.1, maximum=0.9, step=0.05,
                      help="If you let go below this ratio, the transition is cancelled."),
              Setting("SWIPE_CREATE_NEW", "Create a new workspace at the end", kind="bool",
                      default="true",
                      help="Keep swiping forward on the last workspace to "
                           "create a new empty one."),
              Setting("SWIPE_DIRECTION_LOCK", "Direction lock", kind="bool",
                      default="true",
                      help="Locks the horizontal/vertical direction as soon as "
                           "the swipe starts, so a slightly diagonal finger "
                           "does not break the transition."),
          ]),

    Group("cursor", "Cursor", "input-mouse-symbolic", "",
          [
              Setting("CURSOR_SIZE", "Cursor size", kind="int", default="24",
                      minimum=12, maximum=64, unit="px",
                      help="XCursor size. HiDPI displays may need larger "
                           "values."),
              Setting("CURSOR_INACTIVE_TIMEOUT", "Hide when idle", kind="int",
                      default="5", minimum=0, maximum=60, unit="s",
                      help="0 = never hide."),
              Setting("CURSOR_HOTSPOT_PADDING", "Cursor edge padding", kind="int",
                      default="1", minimum=0, maximum=10, unit="px",
                      help="Inner padding limiting how close the cursor can "
                           "get to the screen edge."),
              Setting("NO_HARDWARE_CURSORS", "Software cursor", kind="bool",
                      default="false",
                      help="Turn on if the cursor disappears or flickers. Uses "
                           "a bit more GPU."),
          ]),

    Group("environment", "Environment", "utilities-terminal-symbolic",
          "Environment variables passed to applications",
          [
              Setting("HYPR_LANG", "Hyprland config language", kind="choice",
                      default="auto",
                      choices=[("auto", "Automatic — based on the Hyprland version"),
                               ("conf", "hyprland.conf (classic)"),
                               ("lua", "hyprland.lua (experimental)")],
                      help="Hyprland 0.57 removed the .conf parser; "
                           "Automatic looks at the installed version and picks "
                           "the right one. Choose by hand only when "
                           "troubleshooting: forcing conf on a new version or "
                           "lua on an old one leaves Hyprland unable to read "
                           "its config."),
              Setting("QT_PLATFORM_THEME", "Qt theme engine", kind="choice",
                      requires={"qt6ct": ("qt-theme",), "qt5ct": ("qt-theme",),
                                "kde": ("pkg:plasma-integration",)},
                      default="qt6ct",
                      choices=[("qt6ct", "qt6ct"), ("qt5ct", "qt5ct"),
                               ("kde", "KDE (Plasma tools)"), ("gtk3", "GTK3"),
                               ("", "Don't set")],
                      help="Which tool is used to theme Qt applications."),
              Setting("XDG_MENU_PREFIX", "Application menu prefix", kind="text",
                      default="", help="For the KDE application menu: plasma-"),
              Setting("FLATPAK_DIRS", "Add Flatpak paths", kind="bool",
                      requires={"true": ("pkg:flatpak",)},
                      default="true",
                      help="Make the icons and .desktop files of Flatpak apps "
                           "show up in the launcher."),
              Setting("GTK_THEME_NAME", "GTK theme", kind="text", default="",
                      help="If left empty, derived from the selected components "
                           "(Catppuccin or Adwaita-dark). You can write the "
                           "name you see in nwg-look."),
              Setting("ICON_THEME_NAME", "Icon theme", kind="text", default="",
                      help="If left empty, Papirus-Dark (if installed) is used."),
              Setting("EDITOR_CMD", "Default editor", kind="text", default="",
                      help="EDITOR/VISUAL variables. E.g. nvim"),
              Setting("TERMINAL_ARGS", "Terminal arguments", kind="text",
                      default="", help="E.g. single-instance mode for kitty: -1"),
              Setting("GNOME_KEYRING", "GNOME keyring", kind="bool",
                      requires={"true": ("pkg:gnome-keyring",)},
                      default="false",
                      help="Starts gnome-keyring-daemon at session start — "
                           "turn on if GNOME/Chromium-based apps need a "
                           "password store."),
              Setting("EXTRA_ENV", "Extra environment variables", kind="text",
                      default="",
                      help="Extra environment variables to add to hyprland.conf, "
                           "in the form \"NAME=value;;NAME2=value2\"."),
              Setting("EXTRA_EXEC_ONCE", "Extra startup commands", kind="text",
                      default="",
                      help="Extra commands to add to the autostart list at "
                           "session start, in the form \"command1;;command2\"."),
          ]),

    Group("theme_schedule", "Day / night theme", "weather-clear-night-symbolic",
          "The theme changes by itself with the time of day: e.g. a light "
          "palette by day, a dark one at night. The system color (GTK/Qt "
          "light/dark) switches along with the theme. A systemd user timer "
          "runs at both times and at login.",
          [
              Setting("THEME_SCHEDULE", "Switch theme by time of day", kind="bool",
                      default="false",
                      help="When on, the theme you picked by hand is replaced "
                           "by the day/night theme at the next switch."),
              Setting("THEME_DAY", "Day theme", kind="choice",
                      default="catppuccin-latte",
                      choices=[(name, name) for name in _theme_names()]),
              Setting("THEME_NIGHT", "Night theme", kind="choice",
                      default="catppuccin-mocha",
                      choices=[(name, name) for name in _theme_names()]),
              Setting("THEME_DAY_START", "Day starts at", kind="text",
                      default="07:00", help="HH:MM"),
              Setting("THEME_NIGHT_START", "Night starts at", kind="text",
                      default="19:00", help="HH:MM"),
          ]),

    Group("tone", "Color tone", "color-select-symbolic",
          "Shifts the whole palette by hand — both preset themes and colors "
          "taken from the wallpaper. Window borders, the bar, the terminal, "
          "GTK/Qt apps, notifications and the programs under Wallpaper Colors "
          "change together.",
          [
              Setting("PALETTE_HUE", "Hue", kind="int", default="0",
                      minimum=-180, maximum=180, step=5, unit="°",
                      affects_preview=True,
                      help="Rotates on the color wheel: e.g. a purple palette "
                           "shifts to pink at +60 and to blue at -60. Red/green/"
                           "yellow warning colors are not rotated so they keep "
                           "their meaning."),
              Setting("PALETTE_SATURATION", "Saturation", kind="int", default="0",
                      minimum=-100, maximum=100, step=5, unit="%",
                      affects_preview=True,
                      help="Minus: more muted, fully gray at -100. Plus: more vivid."),
              Setting("PALETTE_LIGHTNESS", "Background lightness", kind="int",
                      default="0", minimum=-20, maximum=20, unit="%",
                      affects_preview=True,
                      help="Lightens or darkens the background and surfaces. Text "
                           "and accents adjust themselves to stay readable."),
          ]),
    Group("wallpaper", "Wallpaper", "preferences-desktop-wallpaper-symbolic", "",
          [
              Setting("WALLPAPER_STYLE", "Wallpaper pattern", kind="choice",
                      default="",
                      choices=[("", "Don't generate — I'll use my own image"),
                               ("waves", "Flowing bands"),
                               ("stars", "Star field"),
                               ("orb", "Large disc (moon/sun)"),
                               ("mist", "Misty hills + rain"),
                               ("grid", "Technical grid"),
                               ("paper", "Paper grain"),
                               ("solid", "Solid color"),
                               ("dunes", "Diagonal sand bands")],
                      help="Generated from the selected theme's colors. An "
                           "existing wallpaper is not overwritten. If the "
                           "profile has its own WALLPAPER_IMAGE, this choice is skipped."),
              Setting("WALLPAPER_PATH", "Wallpaper path", kind="text",
                      default="~/Pictures/wallpapers/wallpaper.png",
                      help="Your own image goes here. If WALLPAPER_STYLE "
                           "is selected and this file does not exist, the "
                           "generated wallpaper is written to this path."),
              Setting("PALETTE_BACKEND", "Palette extraction backend", kind="choice",
                      requires={"matugen": ("matugen",),
                                "magick": ("pkg:imagemagick",)},
                      default="auto",
                      choices=[("auto", "Automatic — try in order"),
                               ("matugen", "matugen (Material You)"),
                               ("magick", "ImageMagick histogram"),
                               ("python", "Built-in PNG decoder")],
                      help="Only used when the theme is 'auto': colors are "
                           "extracted from the wallpaper. matugen gives the "
                           "best result (package: matugen); the built-in "
                           "decoder has no dependencies but only reads PNG."),
              Setting("WALLPAPER_IMAGE", "Bundled image in the repo", kind="text",
                      default="",
                      help="Advanced: a path relative to the repo (e.g. "
                           "wallpapers/lamp-paper.png) — if the file exists "
                           "it takes precedence over WALLPAPER_STYLE and is "
                           "copied straight to WALLPAPER_PATH. Usually filled "
                           "in automatically by preset selection; you do not "
                           "need to fill it by hand."),
              Setting("WALLPAPER_ROTATE", "Automatic rotation", kind="int",
                      default="0", minimum=0, maximum=240, step=5, unit=" min",
                      help="0 = off. When on, a systemd user timer picks a "
                           "random new wallpaper from a directory every this "
                           "many minutes (hyprsetup-wallpaper.timer). Only "
                           "works with the hyprpaper or swww backend."),
              Setting("WALLPAPER_DIR", "Rotation directory", kind="text", default="",
                      help="If left empty, the directory containing the "
                           "wallpaper path is scanned. E.g. ~/Pictures/wallpapers"),
              Setting("SWWW_TRANSITION", "Transition effect", kind="choice",
                      default="grow",
                      choices=[("none", "None — change instantly"),
                               ("simple", "Simple — plain blend"),
                               ("fade", "Fade — soft fade"),
                               ("left", "Slide left"), ("right", "Slide right"),
                               ("top", "Slide up"), ("bottom", "Slide down"),
                               ("wipe", "Wipe — wipe across"),
                               ("grow", "Grow — grow from the cursor"),
                               ("center", "Center — open from the center"),
                               ("outer", "Outer — outside in"),
                               ("random", "Random")],
                      help="Only applies when the wallpaper backend is swww; "
                           "hyprpaper does not support transition effects."),
              Setting("SWWW_TRANSITION_DURATION", "Transition duration", kind="float",
                      default="2", minimum=0.1, maximum=10, step=0.1, unit=" s",
                      help="How many seconds the transition effect lasts."),
              Setting("SWWW_TRANSITION_FPS", "Transition frame rate", kind="int",
                      default="60", minimum=24, maximum=240, step=5, unit=" fps",
                      help="Smoothness of the transition. Going above your "
                           "display's refresh rate does nothing."),
              Setting("WPENGINE_ID", "Wallpaper Engine ID", kind="text",
                      default="",
                      help="Steam Workshop wallpaper ID if "
                           "linux-wallpaperengine is selected."),
              Setting("WPENGINE_SCREEN", "On which display", kind="text", default="",
                      help="Empty = all displays. E.g. DP-1"),
              Setting("WPENGINE_PER_SCREEN", "Scene per display", kind="text",
                      default="",
                      help="A separate Workshop ID per display: \"DP-1=123;"
                           "HDMI-A-2=456\". A display not in the list plays "
                           "the ID above. The gallery on the Wallpaper Engine "
                           "page writes this itself."),
              Setting("WPENGINE_SCALING", "Scaling", kind="choice",
                      default="default",
                      choices=[("default", "Default"), ("fill", "Fill"),
                               ("fit", "Fit"), ("stretch", "Stretch")],
                      help="How the wallpaper is placed when it does not match "
                           "the screen's aspect ratio."),
              Setting("WPENGINE_FPS", "Frame cap", kind="text", default="",
                      help="E.g. 30 — to save GPU and battery."),
              Setting("WPENGINE_SILENT", "Mute audio", kind="bool", default="true",
                      help="Mutes the Wallpaper Engine wallpaper's own audio/"
                           "music."),
              Setting("WPENGINE_EXTRA_ARGS", "Extra command-line arguments",
                      kind="text", default="",
                      help="Extra arguments passed as is to "
                           "linux-wallpaperengine."),
          ]),
    # These three groups were MISSING FROM THE SCHEMA for a long time: the
    # features worked (hypridle timeouts were hardcoded in the template,
    # NIGHT_SHADER/RECORD_* only changed by editing settings.conf by hand)
    # but they left no trace in the settings app — so for the user they
    # effectively did not exist.
    Group("switcher", "Window switcher", "view-paged-symbolic",
          "Window selection with ALT+Tab. If the selected window is on "
          "another workspace, Hyprland switches there; the list opens in the "
          "dmenu mode of the selected launcher (wofi/rofi/fuzzel/tofi/walker).",
          [
              Setting("SWITCHER_ENABLED", "Our ALT+Tab", kind="bool",
                      default="true",
                      help="When off, the ALT+Tab and ALT+` bindings are not "
                           "generated at all and the profile's (theme's) own "
                           "alt-tab keeps those keys. Turn it off if it "
                           "conflicts with a theme's own switcher or if you "
                           "use another alt-tab app."),
              Setting("WINDOW_SWITCHER", "Look", kind="choice",
                      default="overlay",
                      choices=[("overlay", "Window with thumbnails (like Windows/KDE)"),
                               ("menu", "Plain list — in the launcher's dmenu mode")],
                      help="In thumbnail mode each window's current image and "
                           "app icon are shown; releasing ALT selects, Tab "
                           "advances, Esc cancels."),
              Setting("SWITCHER_SCOPE", "Scope", kind="choice", default="all",
                      choices=[("all", "All workspaces"),
                               ("monitor", "This display only"),
                               ("current", "This workspace only")],
                      help="Which windows go into the list. 'All workspaces' "
                           "is the behavior you want: selecting a window on "
                           "another workspace switches there."),
              Setting("SWITCHER_SORT", "Sort order", kind="choice",
                      default="recent",
                      choices=[("recent", "Most recently used (MRU)"),
                               ("workspace", "By workspace")],
                      help="In MRU the first entry is the 'previous window' "
                           "and the focused window goes last — ALT+Tab → Enter "
                           "gives the classic behavior."),
              Setting("SWITCHER_SHOW_WORKSPACE", "Show the workspace",
                      kind="bool", default="true",
                      help="Prefixes each row with [workspace]."),
              Setting("SWITCHER_THUMBS", "Thumbnails", kind="bool",
                      requires={"true": ("screenshot-base",)},
                      default="true",
                      help="The current image of each window (needs grim — "
                           "the Screenshot & Recording component). When off, "
                           "only the app icon is drawn; opening is "
                           "faster. Only applies in thumbnail mode."),
              Setting("SWITCHER_THUMB_WIDTH", "Card width", kind="int",
                      default="260", minimum=160, maximum=480, step=20,
                      unit=" px",
                      help="Width of the thumbnail card; the height is "
                           "computed from a 16:9 ratio."),
              Setting("SWITCHER_ANIM", "Opening animation", kind="choice",
                      default="none",
                      choices=[("none", "None — the fastest"),
                               ("popin", "Popin — grow from the center"),
                               ("slide", "Slide — slide in")],
                      help="Hyprland animation of the switcher window. 'None' "
                           "makes ALT+Tab noticeably faster: the animation "
                           "delays the window appearing by its own "
                           "duration. Speed (bezier/duration) comes from the "
                           "global settings on the Appearance → Animation page."),
              Setting("SWITCHER_PRELOAD", "Keep ready in the background",
                      kind="bool", default="false",
                      help="When on, an invisible copy starts at session "
                           "start and ALT+Tab only draws the window: "
                           "opening takes ~80 ms instead of ~260 ms. The cost "
                           "is a process holding ~60 MB of memory while idle. "
                           "The change takes effect in the next session (or "
                           "when run by hand)."),
              Setting("SWITCHER_PRIORITY", "Priority", kind="choice",
                      default="off",
                      choices=[("off", "Leave as is"),
                               ("alttab", "High priority for ALT+Tab"),
                               ("session", "Normal priority for the whole session (recommended)")],
                      help="On CachyOS the login screen starts at low priority "
                           "(nice 16) and most programs in the session inherit "
                           "it; ALT+Tab lags when the CPU is busy (gaming). \"Whole "
                           "session\" gives Hyprland normal priority, which fixes "
                           "everything it launches (fully in a new session). This is a "
                           "system setting (an ananicy-cpp rule): changing it "
                           "opens a terminal that asks for the sudo password. "
                           "No effect without ananicy-cpp."),
              Setting("SWITCHER_SPECIAL", "List special windows too",
                      kind="bool", default="false",
                      help="Also adds scratchpad (special:magic) windows to "
                           "the list."),
          ]),
    Group("idle", "Idle and lock", "system-lock-screen-symbolic",
          "What happens, step by step, when the computer is left untouched "
          "(hypridle). Every value is in seconds; 0 removes that step entirely.",
          [
              Setting("IDLE_DIM", "Dim the display", kind="int", default="150",
                      minimum=0, maximum=1800, step=30, unit=" s",
                      help="Lowers the brightness to the dim level below and "
                           "restores it on the first movement. Only generated if "
                           "brightnessctl (Hardware → Brightness) is installed."),
              Setting("IDLE_LOCK", "Lock the screen", kind="int", default="300",
                      minimum=0, maximum=7200, step=30, unit=" s",
                      help="Locks with hyprlock. 0 = no automatic lock. "
                           "Only generated if hyprlock is installed."),
              Setting("IDLE_DPMS", "Turn the display off", kind="int", default="330",
                      minimum=0, maximum=7200, step=30, unit=" s",
                      help="Puts the monitor to sleep (dpms off). It makes "
                           "sense to have it come after the lock."),
              Setting("IDLE_SUSPEND", "Suspend the system", kind="int",
                      default="1800", minimum=0, maximum=14400, step=300,
                      unit=" s",
                      help="systemctl suspend. Set it to 0 on desktop machines."),
              Setting("IDLE_DIM_LEVEL", "Dim level", kind="int",
                      default="10", minimum=1, maximum=90, step=5, unit=" %",
                      help="Display brightness when dimmed. Raise it if the "
                           "screen is not visible at all."),
              Setting("IDLE_KBD_BACKLIGHT", "Turn off keyboard backlight too",
                      kind="bool", default="true",
                      help="Turns off the keyboard backlight along with dimming "
                           "(on laptops that support it)."),
              Setting("IDLE_LOCK_BEFORE_SLEEP", "Lock before sleep",
                      kind="bool", default="true",
                      help="The screen is locked first when the lid closes or "
                           "you suspend by hand. If you turn this off, no "
                           "password is asked on wake."),
              Setting("IDLE_RESPECT_INHIBIT", "Wait while video plays",
                      kind="bool", default="true",
                      help="When a player or browser says \"keep the screen on\", "
                           "dimming, locking and sleep are postponed. "
                           "When off, they always run on time."),
          ]),
    Group("groups", "Window groups", "view-paged-symbolic",
          "Gathers several windows in one place as tabs. Their keybindings "
          "are empty by default; assign them under Keybindings → Windows "
          "(\"Create window group\").",
          [
              Setting("GROUPBAR", "Tab bar", kind="bool", default="true",
                      help="Shows the tabs above a grouped window. "
                           "When off, tabs are only switched with keybindings."),
              Setting("GROUPBAR_STYLE", "Look", kind="choice",
                      default="tabs",
                      choices=[("tabs", "Filled tabs"),
                               ("line", "Thin line + title"),
                               ("indicator", "Line only")]),
              Setting("GROUPBAR_HEIGHT", "Height", kind="int", default="18",
                      minimum=4, maximum=40, unit=" px"),
              Setting("GROUPBAR_FONT_SIZE", "Font size", kind="int",
                      default="10", minimum=6, maximum=24, unit=" pt"),
          ]),
    Group("plugins", "Hyprland plugins", "application-x-addon-symbolic",
          "Settings for hyprpm plugins. Install the plugin from Components → "
          "Plugins; these settings have no effect while it is not installed.",
          [
              Setting("HYPREXPO_COLUMNS", "hyprexpo: number of columns", kind="int",
                      default="3", minimum=2, maximum=6,
                      help="How many workspaces are shown side by side in the "
                           "workspace overview."),
              Setting("HYPRBARS_HEIGHT", "hyprbars: title height",
                      kind="int", default="26", minimum=16, maximum=48,
                      unit=" px"),
              Setting("HYPRBARS_BUTTONS", "hyprbars: window buttons",
                      kind="bool", default="true",
                      help="Close / maximize / float buttons on the title "
                           "bar."),
          ]),
    Group("lock", "Lock screen", "changes-prevent-symbolic",
          "How hyprlock looks. MOD+L, idle and sleep use the same "
          "screen.",
          [
              Setting("LOCK_BACKGROUND", "Background", kind="choice",
                      default="wallpaper",
                      choices=[("wallpaper", "Wallpaper"),
                               ("screenshot", "Current screen image"),
                               ("color", "Solid color (theme background)")],
                      help="If screenshot is selected, the desktop right before "
                           "locking is shown blurred."),
              Setting("LOCK_BLUR_PASSES", "Blur passes", kind="int",
                      default="3", minimum=0, maximum=6,
                      help="0 = background is shown sharp."),
              Setting("LOCK_BLUR_SIZE", "Blur size", kind="int",
                      default="8", minimum=1, maximum=30),
              Setting("LOCK_BRIGHTNESS", "Background brightness", kind="float",
                      default="0.8", minimum=0.1, maximum=1.5, step=0.05,
                      help="Below 1 darkens; the clock and text are easier to "
                           "read."),
              Setting("LOCK_CLOCK_FORMAT", "Clock format", kind="text",
                      default="%H:%M",
                      help="date format. %I:%M %p for 12-hour, %H:%M:%S "
                           "with seconds."),
              Setting("LOCK_CLOCK_SIZE", "Clock size", kind="int",
                      default="110", minimum=30, maximum=240, step=5,
                      unit=" pt"),
              Setting("LOCK_SHOW_DATE", "Show the date", kind="bool",
                      default="true"),
              Setting("LOCK_DATE_FORMAT", "Date format", kind="text",
                      default="%d %B %Y, %A",
                      help="date format. Example: %A, %d %b → Monday, 05 Oct."),
              Setting("LOCK_SHOW_USER", "Show the username", kind="bool",
                      default="true"),
              Setting("LOCK_INPUT_WIDTH", "Password field width", kind="int",
                      default="320", minimum=160, maximum=800, step=10,
                      unit=" px"),
              Setting("LOCK_PLACEHOLDER", "Password field placeholder", kind="text",
                      default="Password…"),
              Setting("LOCK_GRACE", "Unlock-without-password window", kind="int",
                      default="2", minimum=0, maximum=60, unit=" s",
                      help="After an idle lock, moving the mouse within this "
                           "time unlocks without a password. Not applied to "
                           "manual locks or sleep. 0 = password asked "
                           "immediately."),
          ]),
    Group("power", "Power menu", "system-shutdown-symbolic",
          "Lock / sleep / shut down menu (wlogout, or a menu opened through "
          "the launcher).",
          [
              Setting("POWERMENU_HIBERNATE", "Hibernate button",
                      kind="bool", default="true",
                      help="Hibernation does not work without swap and a "
                           "kernel resume setting; turn it off "
                           "then."),
              Setting("POWERMENU_CONFIRM", "Ask for confirmation", kind="bool",
                      default="true",
                      help="Shut down, reboot, log out and hibernate first "
                           "ask \"Are you sure?\". "
                           "wlogout does not ask for its own confirmation."),
          ]),
    Group("notify", "Notifications", "preferences-system-notifications-symbolic",
          "Position, duration and size of notification bubbles. mako, dunst and "
          "swaync use the same settings; the notification program is chosen on "
          "the Components page.",
          [
              Setting("NOTIFY_POSITION", "Position", kind="choice", default="auto",
                      choices=[("auto", "Automatic — on the right, at the bar's edge"),
                               ("top-right", "Top right"),
                               ("top-center", "Top center"),
                               ("top-left", "Top left"),
                               ("bottom-right", "Bottom right"),
                               ("bottom-center", "Bottom center"),
                               ("bottom-left", "Bottom left")]),
              Setting("NOTIFY_TIMEOUT", "Time on screen", kind="int",
                      default="6", minimum=0, maximum=60, unit=" s",
                      help="Low-priority notifications stay two thirds as "
                           "long. 0 = stay until clicked."),
              Setting("NOTIFY_CRITICAL_STICKY", "Keep critical notifications",
                      kind="bool", default="true",
                      help="Critical notifications such as a dying battery stay "
                           "on screen until clicked."),
              Setting("NOTIFY_WIDTH", "Width", kind="int", default="380",
                      minimum=200, maximum=900, step=10, unit=" px"),
              Setting("NOTIFY_MAX_VISIBLE", "Maximum at once", kind="int",
                      default="5", minimum=1, maximum=20,
                      help="The rest are queued. swaync does not support this "
                           "setting."),
              Setting("NOTIFY_MARGIN", "Distance from the screen edge", kind="int",
                      default="12", minimum=0, maximum=200, step=2, unit=" px",
                      help="For mako and dunst. swaync uses its own "
                           "margin."),
              Setting("NOTIFY_ICON_SIZE", "Icon size", kind="int",
                      default="48", minimum=16, maximum=128, step=4,
                      unit=" px"),
          ]),
    Group("night", "Night light", "weather-clear-night-symbolic",
          "Time-based screen filter with hyprshade. Scheduling runs on a "
          "systemd user timer and is reinstalled when the setting changes.",
          [
              Setting("NIGHT_SHADER", "Filter", kind="choice", default="",
                      requires={"*": ("hyprland-extras",)},
                      choices=[("", "Off"),
                               ("blue-light-filter", "Blue light filter — yellowish"),
                               ("vibrance", "Vibrance — vivid colors"),
                               ("grayscale", "Grayscale"),
                               ("crt", "CRT — scanlines")],
                      help="Do NOT use it TOGETHER with hyprsunset: both lower "
                           "the color temperature and the screen turns twice as "
                           "yellow. The MOD+SHIFT+N binding toggles hyprsunset."),
              Setting("NIGHT_SHADER_START", "Start time", kind="text",
                      default="20:00",
                      help="In HH:MM format. The filter turns on at this time."),
              Setting("NIGHT_SHADER_END", "End time", kind="text",
                      default="06:00",
                      help="In HH:MM format. The filter turns off at this time."),
              Setting("NIGHT_TEMP", "hyprsunset color temperature", kind="int",
                      default="4000", minimum=1000, maximum=6500, step=100,
                      unit=" K",
                      help="Temperature set by the MOD+SHIFT+N binding. Lower "
                           "values are more yellow (1000–3000 K for night "
                           "reading), 6500 K is neutral. The binding is only "
                           "generated if the hyprsunset component is installed."),
          ]),
    Group("tools", "Desktop tools", "applications-utilities-symbolic",
          "Bar panel, song recognition, notification history, update checks "
          "and system snapshots. Where modules sit on the bar is changed on the "
          "Status Bar page, keybindings on the Keybindings page.",
          [
              Setting("SONG_LISTEN_SECONDS", "Song recognition listening time", kind="int",
                      default="9", minimum=4, maximum=20, unit=" s",
                      help="Recording length for Shazam (songrec). 6–10 s is "
                           "enough for most songs; increase it in noisy environments."),
              Setting("NOTIFY_HISTORY", "Notification history", kind="bool", default="true",
                      help="Incoming notifications are kept for this session (in "
                           "memory only, deleted when the session ends); the bar "
                           "panel's Notifications tab and the bell module show it."),
              Setting("NOTIFY_HISTORY_KEEP", "Notifications to keep", kind="int",
                      default="50", minimum=10, maximum=500, step=10),
              Setting("UPDATES_CHECK", "Check for updates", kind="bool",
                      default="true",
                      help="The update module on the bar counts pending packages "
                           "(checkupdates; does not touch the system package database)."),
              Setting("UPDATES_INTERVAL", "Check interval", kind="int", default="30",
                      minimum=5, maximum=360, step=5, unit=" min"),
              Setting("UPDATES_AUR", "Count AUR packages too", kind="bool",
                      default="true", help="If yay or paru is installed."),
              Setting("BRIGHTNESS_DDC", "External display brightness (DDC/CI)", kind="bool",
                      default="true",
                      help="The bar panel's Brightness tab adjusts desktop monitors "
                           "with ddcutil. Turn it off if your display does not "
                           "support DDC/CI or detection is slow."),
              Setting("PANEL_APP_VOLUME", "Per-app volume", kind="bool",
                      default="true",
                      help="A separate slider for every playing app on the bar "
                           "panel's Volume tab."),
              Setting("SELFUPDATE_SYNC", "Sync the installed copy automatically",
                      kind="bool", default="true",
                      help="When settings are applied from the repo folder, "
                           "~/.local/share/hyprsetup is updated too (MOD+I, the bar "
                           "panel and the keybinding cheat sheet run from there)."),
              Setting("SNAPSHOT_BEFORE_SYSTEM", "Snapshot before system changes",
                      kind="choice", default="auto",
                      choices=[("auto", "On — if snapper/timeshift is present"),
                               ("false", "Off")],
                      help="A snapshot you can roll back to is taken before "
                           "NVIDIA, Plymouth, login manager and login screen "
                           "changes."),
          ]),

    Group("gamemode", "Game mode", "input-gaming-symbolic",
          "Takes load off the desktop while gaming: animation, blur and shadow "
          "are turned off, Wallpaper Engine pauses, the visualizer stops, "
          "notifications are muted. Everything comes back when you leave the "
          "game. Toggle by hand: MOD+F12.",
          [
              Setting("GAMEMODE_AUTO", "Turn on automatically", kind="choice", default="games",
                      choices=[("games", "When a game goes fullscreen"),
                               ("fullscreen", "On any fullscreen window"),
                               ("off", "Off — keybinding only")],
                      help="Only the fullscreen window on the VISIBLE workspace "
                           "is checked; moving the game to another workspace "
                           "turns the mode off. A manually enabled mode does not turn itself off."),
              Setting("GAMEMODE_MATCH", "Game windows", kind="text",
                      default=r"^(steam_app_[0-9]+|gamescope|.+\.exe|Minecraft.*|cs2|dota2|factorio|hl2_linux)",
                      help="Regular expression matched against the window class "
                           "or title (case insensitive). Steam games "
                           "come with steam_app_<id>, Proton/Wine games with an "
                           ".exe class. To see the class: hyprctl activewindow."),
              Setting("GAMEMODE_EFFECTS", "Turn off effects", kind="bool", default="true",
                      help="Animation, blur and shadow. When the mode ends, the "
                           "config is reloaded and goes back to how it was."),
              Setting("GAMEMODE_PAUSE_WALLPAPER", "Pause Wallpaper Engine",
                      kind="bool", default="true",
                      help="The scene is frozen (uses no GPU) and resumes where "
                           "it left off."),
              Setting("GAMEMODE_DND", "Mute notifications", kind="bool", default="true",
                      help="Do-not-disturb mode of swaync, mako or dunst."),
          ]),
    Group("capture", "Screen recording and screenshots", "camera-video-symbolic",
          "gpu-screen-recorder wrapper (~/.config/hypr/scripts/"
          "record.sh). Instant replay keeps the recording in a ring buffer and "
          "only writes to disk when you ask.",
          [
              Setting("RECORD_DIR", "Recording folder", kind="text",
                      default="~/Videos",
                      help="Directory where recordings and instant replay "
                           "files are written; created if missing."),
              Setting("RECORD_FPS", "Frame rate", kind="int", default="60",
                      minimum=24, maximum=240, step=5, unit=" fps",
                      help="Higher value = smoother recording, larger file."),
              Setting("RECORD_AUDIO", "Audio source", kind="choice",
                      requires={"*": ("instant-replay",)},
                      default="default_output",
                      choices=[("", "Silent — no audio recorded"),
                               ("default_output", "System audio"),
                               ("default_input", "Microphone only"),
                               ("default_output|default_input",
                                "System audio + microphone")],
                      help="Passed to gpu-screen-recorder's -a flag."),
              Setting("REPLAY_SECONDS", "Instant replay buffer", kind="int",
                      default="60", minimum=15, maximum=600, step=15, unit=" s",
                      help="How far back can be saved. Memory use is "
                           "proportional to this duration."),
              Setting("RECORD_FORMAT", "File format", kind="choice",
                      default="mp4",
                      choices=[("mp4", "MP4 — opens everywhere"),
                               ("mkv", "MKV — survives an interrupted recording")]),
              Setting("RECORD_CODEC", "Video codec", kind="choice",
                      default="auto",
                      choices=[("auto", "Automatic — based on the graphics card"),
                               ("h264", "H.264 — most compatible"),
                               ("hevc", "HEVC — smaller file"),
                               ("av1", "AV1 — smallest, needs a recent card")],
                      help="If your card does not support the selected codec, "
                           "recording will not start; switch back to Automatic then."),
              Setting("RECORD_QUALITY", "Quality", kind="choice",
                      default="very_high",
                      choices=[("medium", "Medium"), ("high", "High"),
                               ("very_high", "Very high"),
                               ("ultra", "Ultra — very large file")]),
              Setting("RECORD_CURSOR", "Record the mouse cursor", kind="bool",
                      default="true"),
              Setting("SCREENSHOT_DIR", "Screenshot folder", kind="text",
                      default="",
                      help="If left empty, Pictures/Screenshots. The Print "
                           "binding, the Actions menu and the bar panel save "
                           "here."),
          ]),
]


# ------------------------------------------------------- simple / advanced ---
#: Settings HIDDEN in the settings app's "Simple" mode. Criterion: fine
#: tuning whose effect someone unfamiliar would not see when changing it, or
#: that could break the desktop (gradient angle, blur contrast, environment
#: variables, window rule text…). Their values are not lost — only the row is
#: hidden, and it comes back when "Advanced" is selected. The list lives here
#: instead of a separate ``advanced=True`` on every row, so which settings stay
#: in simple mode can be read at a glance. tools/test.sh checks that every key
#: here exists in the schema.
ADVANCED_KEYS: frozenset[str] = frozenset({
    # Layout
    "GAPS_WORKSPACES", "BORDER_ANGLE", "ROUNDING_POWER", "MASTER_MFACT",
    "MASTER_NEW_STATUS", "DWINDLE_PRESERVE_SPLIT", "DWINDLE_SMART_SPLIT",
    "DWINDLE_SMART_RESIZING",
    # Decoration
    "BLUR_PASSES", "BLUR_XRAY", "BLUR_SPECIAL", "BLUR_POPUPS", "BLUR_NOISE",
    "BLUR_CONTRAST", "BLUR_BRIGHTNESS", "BLUR_VIBRANCY", "SHADOW_RANGE",
    "SHADOW_RENDER_POWER", "SHADOW_OFFSET", "DIM_STRENGTH", "GLOBAL_OPACITY",
    "XWAYLAND_NO_BLUR",
    # Dock
    "DOCK_MONITOR",
    # Status bar
    "BAR_WIDTH", "BAR_SPACING", "BAR_PADDING", "BAR_CLOCK_FORMAT",
    "BAR_CLOCK_FORMAT_ALT", "BAR_WINDOW_MAX_LENGTH",
    # Animation
    "ANIMATION_CUSTOM",
    # Behavior
    "ALLOW_TEARING", "VRR", "SNAP_WINDOW_GAP", "SNAP_MONITOR_GAP",
    "WINDOWRULES", "USER_WINDOWRULES", "ENABLE_SWALLOW", "SWALLOW_REGEX", "NO_FOCUS_FALLBACK",
    "FOCUS_ON_ACTIVATE", "ANIMATE_MANUAL_RESIZES", "SCROLL_EVENT_DELAY",
    "DIM_SPECIAL", "ON_FOCUS_UNDER_FULLSCREEN", "DPMS_ON_INPUT",
    "HIDE_SPECIAL_ON_WS_CHANGE",
    # Window switcher
    "SWITCHER_SHOW_WORKSPACE", "SWITCHER_THUMB_WIDTH", "SWITCHER_ANIM",
    "SWITCHER_PRELOAD", "SWITCHER_SPECIAL",
    # Input, gestures, cursor
    "KB_VARIANT", "KB_OPTIONS", "REPEAT_DELAY", "REPEAT_RATE",
    "ACCEL_PROFILE", "OFF_WINDOW_AXIS_EVENTS", "TOUCHPAD_SCROLL_FACTOR",
    "SWIPE_DISTANCE", "SWIPE_CANCEL_RATIO", "SWIPE_CREATE_NEW",
    "SWIPE_DIRECTION_LOCK", "CURSOR_HOTSPOT_PADDING", "NO_HARDWARE_CURSORS",
    # Wallpaper
    "PALETTE_BACKEND", "WALLPAPER_IMAGE", "SWWW_TRANSITION_DURATION",
    "SWWW_TRANSITION_FPS", "WPENGINE_SCREEN", "WPENGINE_PER_SCREEN", "WPENGINE_SCALING",
    "WPENGINE_FPS", "WPENGINE_SILENT", "WPENGINE_EXTRA_ARGS",
    # Session
    "RECORD_FPS", "IDLE_RESPECT_INHIBIT", "LOCK_BLUR_SIZE", "LOCK_INPUT_WIDTH",
    "LOCK_PLACEHOLDER", "NOTIFY_MAX_VISIBLE", "NOTIFY_MARGIN", "NOTIFY_ICON_SIZE",
    "RECORD_CODEC", "RECORD_CURSOR",
    # Status bar / Behavior
    "BAR_AUTOHIDE_TRIGGER", "BAR_AUTOHIDE_RELEASE", "WEATHER_REFRESH",
    "RULE_SUPPRESS_MAXIMIZE", "PIP_WIDTH", "QUICK_PANEL_WIDTH", "QUICK_PANEL_HEIGHT",
    # Behavior → Window groups
    "GROUPBAR_HEIGHT", "GROUPBAR_FONT_SIZE",
})

#: Groups hidden ENTIRELY in simple mode.
ADVANCED_GROUPS: frozenset[str] = frozenset({"environment", "bar_custom", "plugins"})

for _group in GROUPS:
    _group.advanced = _group.id in ADVANCED_GROUPS
    for _setting in _group.settings:
        _setting.advanced = _group.advanced or _setting.key in ADVANCED_KEYS
del _group, _setting


def all_settings() -> list[Setting]:
    return [s for g in GROUPS for s in g.settings]


def by_key() -> dict[str, Setting]:
    return {s.key: s for s in all_settings()}


def defaults() -> dict[str, str]:
    return {s.key: s.default for s in all_settings()}


def group(group_id: str) -> Group:
    return next(g for g in GROUPS if g.id == group_id)
