"""Color palettes.

Each palette provides a shared key set used in templates through variables
such as ``{{COL_BG}}``. Adding a new theme only needs a new dict entry;
templates do not have to change.

Colors are stored as 6-digit hex without ``#``; ``derive()`` derives the CSS
(``#rrggbb``) and Hyprland (``rgba(rrggbbaa)``) forms from them.
"""

from __future__ import annotations

KEYS = (
    "BG",        # main background
    "BG_DARK",   # darker background (bar, strips)
    "SURFACE",   # surface / card background
    "FG",        # main text
    "SUBTEXT",   # secondary text
    "ACCENT",    # primary accent (active border, selection)
    "ACCENT2",   # secondary accent (gradient)
    "RED",
    "GREEN",
    "YELLOW",
    "CYAN",
)

THEMES: dict[str, dict[str, str]] = {
    "catppuccin-mocha": {
        "BG": "1e1e2e", "BG_DARK": "11111b", "SURFACE": "313244",
        "FG": "cdd6f4", "SUBTEXT": "a6adc8",
        "ACCENT": "89b4fa", "ACCENT2": "cba6f7",
        "RED": "f38ba8", "GREEN": "a6e3a1", "YELLOW": "f9e2af", "CYAN": "94e2d5",
    },
    "catppuccin-macchiato": {
        "BG": "24273a", "BG_DARK": "181926", "SURFACE": "363a4f",
        "FG": "cad3f5", "SUBTEXT": "a5adcb",
        "ACCENT": "8aadf4", "ACCENT2": "c6a0f6",
        "RED": "ed8796", "GREEN": "a6da95", "YELLOW": "eed49f", "CYAN": "8bd5ca",
    },
    "tokyo-night": {
        "BG": "1a1b26", "BG_DARK": "16161e", "SURFACE": "24283b",
        "FG": "c0caf5", "SUBTEXT": "565f89",
        "ACCENT": "7aa2f7", "ACCENT2": "bb9af7",
        "RED": "f7768e", "GREEN": "9ece6a", "YELLOW": "e0af68", "CYAN": "7dcfff",
    },
    # Light themes: values from athena-eww's theme switcher
    # (.config/eww/theme/catppuccin_latte.scss, tokyo_night_light.scss).
    "catppuccin-latte": {
        "BG": "eff1f5", "BG_DARK": "dce0e8", "SURFACE": "ccd0da",
        "FG": "4c4f69", "SUBTEXT": "6c6f85",
        "ACCENT": "1e66f5", "ACCENT2": "8839ef",
        "RED": "d20f39", "GREEN": "40a02b", "YELLOW": "df8e1d", "CYAN": "179299",
    },
    "tokyo-night-light": {
        "BG": "e6e7ed", "BG_DARK": "cdd0d8", "SURFACE": "dadce4",
        "FG": "343b58", "SUBTEXT": "5a5e6e",
        "ACCENT": "2959aa", "ACCENT2": "5a3e8e",
        "RED": "8c4351", "GREEN": "385f0d", "YELLOW": "8f5e15", "CYAN": "33635c",
    },
    "gruvbox-dark": {
        "BG": "282828", "BG_DARK": "1d2021", "SURFACE": "3c3836",
        "FG": "ebdbb2", "SUBTEXT": "928374",
        "ACCENT": "83a598", "ACCENT2": "d3869b",
        "RED": "fb4934", "GREEN": "b8bb26", "YELLOW": "fabd2f", "CYAN": "8ec07c",
    },
    "nord": {
        "BG": "2e3440", "BG_DARK": "242933", "SURFACE": "3b4252",
        "FG": "eceff4", "SUBTEXT": "4c566a",
        "ACCENT": "88c0d0", "ACCENT2": "b48ead",
        "RED": "bf616a", "GREEN": "a3be8c", "YELLOW": "ebcb8b", "CYAN": "8fbcbb",
    },
    "rose-pine": {
        "BG": "191724", "BG_DARK": "13111c", "SURFACE": "1f1d2e",
        "FG": "e0def4", "SUBTEXT": "6e6a86",
        "ACCENT": "c4a7e7", "ACCENT2": "9ccfd8",
        "RED": "eb6f92", "GREEN": "31748f", "YELLOW": "f6c177", "CYAN": "9ccfd8",
    },
    "everforest-dark": {
        "BG": "2d353b", "BG_DARK": "232a2e", "SURFACE": "343f44",
        "FG": "d3c6aa", "SUBTEXT": "859289",
        "ACCENT": "7fbbb3", "ACCENT2": "d699b6",
        "RED": "e67e80", "GREEN": "a7c080", "YELLOW": "dbbc7f", "CYAN": "83c092",
    },

    # --- gallery palettes ---------------------------------------------------
    # Derived from the reference screenshots for the profiles
    # (see docs/gallery-catalog.md). Values were sampled from the relevant UI
    # region of the source (not from the wallpaper); each palette was tuned
    # with FG/SUBTEXT contrast in mind for readability — even when the text
    # in the source image is nearly the same tone as the background.
    # The bar islands' background was measured (#1e1e2e) and written to BG: in
    # the template @bg drives the module background (see waybar/style.css.tmpl),
    # not @bg-dark, so the island color must come from BG. The accent is the
    # measured lilac tone of the active workspace pill.
    "ashen-rain": {
        "BG": "1e1e2e", "BG_DARK": "16161f", "SURFACE": "2f3042",
        "FG": "d8d8e4", "SUBTEXT": "868999",
        "ACCENT": "cdaef3", "ACCENT2": "9aa0c4",
        "RED": "d88a9a", "GREEN": "9ac8a8", "YELLOW": "d8c48a", "CYAN": "8ac0c8",
    },
    # Panel background warm black, buttons salmon, active calendar day coral.
    "ambxst-lava": {
        "BG": "1a1010", "BG_DARK": "0e0807", "SURFACE": "2c1a17",
        "FG": "f6ded3", "SUBTEXT": "a8837a",
        "ACCENT": "e8624a", "ACCENT2": "f2a68e",
        "RED": "e8483c", "GREEN": "c8a84a", "YELLOW": "f0a83c", "CYAN": "d0785a",
    },
    # Red primary, green secondary (media bar is green). Body text is light
    # grey, not red — that is how the menu and hardware info look in the source.
    "cybr-neon": {
        "BG": "0b0606", "BG_DARK": "050303", "SURFACE": "1c0e0e",
        "FG": "cfc7c7", "SUBTEXT": "7a4a48",
        "ACCENT": "e6392c", "ACCENT2": "3ce88a",
        "RED": "e6392c", "GREEN": "3ce88a", "YELLOW": "e8a83c", "CYAN": "3cc8d8",
    },
    # Flat purple desktop; UI cards darker than it, accent light lilac.
    "void-lilac": {
        "BG": "2e2545", "BG_DARK": "1a1526", "SURFACE": "3d3358",
        "FG": "ece7f5", "SUBTEXT": "9a8cb8",
        "ACCENT": "b9a3dd", "ACCENT2": "8a72b8",
        "RED": "e08aa8", "GREEN": "a8d8a0", "YELLOW": "e8c88a", "CYAN": "8ac8d8",
    },
    "cosmic-void": {
        "BG": "0a0a12", "BG_DARK": "050509", "SURFACE": "1a1a2a",
        "FG": "cfc8e8", "SUBTEXT": "6a6a8a",
        "ACCENT": "9b8ce0", "ACCENT2": "b8a8f0",
        "RED": "e08a9a", "GREEN": "8ad8a8", "YELLOW": "d8c88a", "CYAN": "8ac8e0",
    },
    # Olive-black background, cream text. Accent is GREEN: in the source the
    # bar's square brackets (#8f9977) and the notification panel's buttons
    # (#7c967a) use this tone — it is the UI's carrying color. Orange only
    # appears in media/fastfetch labels, so it is secondary.
    "sophos-ukiyo": {
        "BG": "232a1e", "BG_DARK": "151a12", "SURFACE": "333a2c",
        "FG": "e6dcc2", "SUBTEXT": "9aa085",
        "ACCENT": "8f9977", "ACCENT2": "d9a05e",
        "RED": "d4574a", "GREEN": "7c967a", "YELLOW": "e0b060", "CYAN": "6a9aa0",
    },
    # Gruvbox, but the source's focus border and power button are red — the
    # blue-grey accent (83a598) of the repo's stock "gruvbox-dark" palette did
    # not resemble that rice. The background is darker too (hard contrast variant).
    "gruvbox-ember": {
        "BG": "1d2021", "BG_DARK": "141617", "SURFACE": "32302f",
        "FG": "ebdbb2", "SUBTEXT": "928374",
        "ACCENT": "fb4934", "ACCENT2": "fe8019",
        "RED": "fb4934", "GREEN": "b8bb26", "YELLOW": "fabd2f", "CYAN": "8ec07c",
    },
    "green-mango": {
        "BG": "0f1a10", "BG_DARK": "0a140c", "SURFACE": "1c2e1c",
        "FG": "a8e07a", "SUBTEXT": "6f9159",
        "ACCENT": "7ac85a", "ACCENT2": "a8e088",
        "RED": "d86a5a", "GREEN": "7ac85a", "YELLOW": "d8d868", "CYAN": "68c8a8",
    },
    # The source really is pure black; cards are only a few shades lighter.
    "nothing-mono": {
        "BG": "000000", "BG_DARK": "000000", "SURFACE": "161616",
        "FG": "f0f0f0", "SUBTEXT": "8a8a8a",
        "ACCENT": "ffffff", "ACCENT2": "b8b8b8",
        "RED": "e05050", "GREEN": "50c050", "YELLOW": "d0d050", "CYAN": "50c0d0",
    },
    # Warm neutral UI; accent orange, secondary the teal of the armor in the
    # wallpaper — in the source these two colors sit opposite each other.
    "mando-sand": {
        "BG": "241f1a", "BG_DARK": "191512", "SURFACE": "332b24",
        "FG": "e8ddd0", "SUBTEXT": "9c8f7e",
        "ACCENT": "d99a5c", "ACCENT2": "5f8a94",
        "RED": "c86a4a", "GREEN": "8aa868", "YELLOW": "e0b860", "CYAN": "6a9aa8",
    },
    "metro-sovietpunk": {
        "BG": "3d1a1a", "BG_DARK": "2a1010", "SURFACE": "552626",
        "FG": "e8d84a", "SUBTEXT": "b09838",
        "ACCENT": "c94a3a", "ACCENT2": "e8d84a",
        "RED": "c94a3a", "GREEN": "9aa83a", "YELLOW": "e8d84a", "CYAN": "8a9a6a",
    },
    "paws-violet": {
        "BG": "1a1620", "BG_DARK": "100d14", "SURFACE": "2a2434",
        "FG": "ded8e8", "SUBTEXT": "8a84a0",
        "ACCENT": "b8a8d8", "ACCENT2": "9a8ac0",
        "RED": "d88a9a", "GREEN": "9ac8a0", "YELLOW": "d8c890", "CYAN": "8ac0d0",
    },
    "luna-mono": {
        "BG": "0e1116", "BG_DARK": "070a0e", "SURFACE": "1e242e",
        "FG": "dfe4ec", "SUBTEXT": "7a8494",
        "ACCENT": "9fb3d0", "ACCENT2": "c0cade",
        "RED": "d88a94", "GREEN": "8ac8a0", "YELLOW": "d8c890", "CYAN": "8ac0d8",
    },
    "slate-arch": {
        "BG": "1e2428", "BG_DARK": "141a1e", "SURFACE": "2e383e",
        "FG": "cdd6db", "SUBTEXT": "7a888e",
        "ACCENT": "7a9aa8", "ACCENT2": "9ab8c4",
        "RED": "c87a7a", "GREEN": "8aae88", "YELLOW": "d0b878", "CYAN": "78b0b8",
    },
    "hyper-olive": {
        "BG": "1c1e18", "BG_DARK": "121410", "SURFACE": "2c3026",
        "FG": "d8d5c8", "SUBTEXT": "8a8a78",
        "ACCENT": "9aa87a", "ACCENT2": "b8c098",
        "RED": "c87a6a", "GREEN": "9aa87a", "YELLOW": "d8c078", "CYAN": "7aa89a",
    },
    "nixos-lantern": {
        "BG": "241610", "BG_DARK": "170d09", "SURFACE": "3a251b",
        "FG": "e8c9a8", "SUBTEXT": "a07a5c",
        "ACCENT": "d4763c", "ACCENT2": "e8a068",
        "RED": "d0563c", "GREEN": "a8a058", "YELLOW": "e8a83c", "CYAN": "9a8a6a",
    },
    "cosmos-violet": {
        "BG": "151226", "BG_DARK": "0d0b18", "SURFACE": "241f3c",
        "FG": "dcd6f0", "SUBTEXT": "8580a8",
        "ACCENT": "8b7fd4", "ACCENT2": "b0a4ec",
        "RED": "e08498", "GREEN": "88d0a8", "YELLOW": "e0c488", "CYAN": "88c4e0",
    },
    "abomination-forest": {
        "BG": "16201a", "BG_DARK": "0e1510", "SURFACE": "243028",
        "FG": "d8e8d0", "SUBTEXT": "7e9078",
        "ACCENT": "a8d888", "ACCENT2": "88c0a8",
        "RED": "d08878", "GREEN": "a8d888", "YELLOW": "d8cc80", "CYAN": "80c0b0",
    },
    "miasma-khaki": {
        "BG": "222222", "BG_DARK": "161616", "SURFACE": "343430",
        "FG": "c9b98f", "SUBTEXT": "8a8168",
        "ACCENT": "bb9a5d", "ACCENT2": "a8a878",
        "RED": "c05a4a", "GREEN": "9aa860", "YELLOW": "d0b060", "CYAN": "7fa08a",
    },
    "dune-grey": {
        "BG": "26262a", "BG_DARK": "1a1a1d", "SURFACE": "36363c",
        "FG": "d0cdc8", "SUBTEXT": "85827c",
        "ACCENT": "b8907a", "ACCENT2": "9aa0a8",
        "RED": "c07868", "GREEN": "94a888", "YELLOW": "c8b080", "CYAN": "88a4a8",
    },
    "sunday-gold": {
        "BG": "14161c", "BG_DARK": "0c0d12", "SURFACE": "232630",
        "FG": "e8d9a8", "SUBTEXT": "8a8470",
        "ACCENT": "d4b96a", "ACCENT2": "9aa4c0",
        "RED": "c87868", "GREEN": "9ab080", "YELLOW": "e0c470", "CYAN": "84a8b8",
    },
    "vapenation-slim": {
        "BG": "14161a", "BG_DARK": "0d0e11", "SURFACE": "222630",
        "FG": "c8ccd0", "SUBTEXT": "78808a",
        "ACCENT": "8aa0b0", "ACCENT2": "a8bcc8",
        "RED": "c07878", "GREEN": "88ac88", "YELLOW": "c8b478", "CYAN": "78acb8",
    },
    "warm-amber": {
        "BG": "2a1f16", "BG_DARK": "1c140e", "SURFACE": "3e2f22",
        "FG": "f0dcc0", "SUBTEXT": "a89078",
        "ACCENT": "e0954a", "ACCENT2": "c8a878",
        "RED": "d06848", "GREEN": "a8a860", "YELLOW": "e8b458", "CYAN": "94a888",
    },
    "bluefin-moss": {
        "BG": "1a201c", "BG_DARK": "111612", "SURFACE": "283029",
        "FG": "cdd8ce", "SUBTEXT": "7c8a7e",
        "ACCENT": "8fb89a", "ACCENT2": "a8c4b0",
        "RED": "c08078", "GREEN": "8fb89a", "YELLOW": "c8bc80", "CYAN": "80b0b0",
    },
    "cinnamon-night": {
        "BG": "1a2430", "BG_DARK": "111820", "SURFACE": "283442",
        "FG": "c8d8e8", "SUBTEXT": "78889a",
        "ACCENT": "7ab8d8", "ACCENT2": "a0c8e8",
        "RED": "d08090", "GREEN": "88bc98", "YELLOW": "d8c080", "CYAN": "7ac8d0",
    },
    "evercal-slate": {
        "BG": "16181a", "BG_DARK": "0e1011", "SURFACE": "252829",
        "FG": "d8dcd0", "SUBTEXT": "80867c",
        "ACCENT": "b8d894", "ACCENT2": "94b8a8",
        "RED": "d08880", "GREEN": "b8d894", "YELLOW": "d8cc84", "CYAN": "88bcb0",
    },
    "bumble-violet": {
        "BG": "1a1424", "BG_DARK": "110d18", "SURFACE": "2a2038",
        "FG": "d8ccec", "SUBTEXT": "8478a0",
        "ACCENT": "b088e0", "ACCENT2": "c8a8f0",
        "RED": "e08098", "GREEN": "90cca0", "YELLOW": "d8c088", "CYAN": "88bcdc",
    },
    # Panel background dark green, text and borders bright teal.
    "persona-teal": {
        "BG": "0e3b31", "BG_DARK": "082a23", "SURFACE": "14544a",
        "FG": "dffff5", "SUBTEXT": "7bb8a8",
        "ACCENT": "2fe6ad", "ACCENT2": "6ef0d0",
        "RED": "f07080", "GREEN": "2fe6ad", "YELLOW": "e8d870", "CYAN": "60e0e0",
    },
    "void-minimal": {
        "BG": "0a0a0a", "BG_DARK": "000000", "SURFACE": "1c1c1c",
        "FG": "b8b8b8", "SUBTEXT": "6a6a6a",
        "ACCENT": "8a8a8a", "ACCENT2": "a8a8a8",
        "RED": "b06868", "GREEN": "789878", "YELLOW": "b0a070", "CYAN": "709098",
    },
    "lime-grid": {
        "BG": "000000", "BG_DARK": "000000", "SURFACE": "141814",
        "FG": "e8f0d8", "SUBTEXT": "88906c",
        "ACCENT": "c8f050", "ACCENT2": "9ad038",
        "RED": "e87868", "GREEN": "c8f050", "YELLOW": "e8e060", "CYAN": "78d0b0",
    },
    "evergreen-dusk": {
        "BG": "1a2028", "BG_DARK": "11161c", "SURFACE": "283038",
        "FG": "dce4e8", "SUBTEXT": "808c94",
        "ACCENT": "a8d878", "ACCENT2": "88b8c8",
        "RED": "d08888", "GREEN": "a8d878", "YELLOW": "d8c880", "CYAN": "80bcc8",
    },
    "pixel-cosmos": {
        "BG": "1a1a2e", "BG_DARK": "11111f", "SURFACE": "28284a",
        "FG": "d8d0e8", "SUBTEXT": "807ca0",
        "ACCENT": "e8a8c8", "ACCENT2": "a8a8e8",
        "RED": "e88098", "GREEN": "90c8a8", "YELLOW": "e0c890", "CYAN": "88c0e0",
    },
    "eclipse-round": {
        "BG": "0a0a0c", "BG_DARK": "040405", "SURFACE": "1c1c20",
        "FG": "e8e4d8", "SUBTEXT": "80807a",
        "ACCENT": "d8d0b8", "ACCENT2": "a8a89c",
        "RED": "c07870", "GREEN": "90a888", "YELLOW": "d0c088", "CYAN": "84a4a8",
    },
    "nerv-magi": {
        "BG": "16090b", "BG_DARK": "0d0506", "SURFACE": "2a1416",
        "FG": "f0e6e0", "SUBTEXT": "9a7068",
        "ACCENT": "ff6b4a", "ACCENT2": "c88ae0",
        "RED": "ff4a4a", "GREEN": "8ae078", "YELLOW": "f0c04a", "CYAN": "6ac8d8",
    },
    "aqua-split": {
        "BG": "0d2428", "BG_DARK": "07181a", "SURFACE": "16383c",
        "FG": "c8e8e0", "SUBTEXT": "6e9490",
        "ACCENT": "4ac8b0", "ACCENT2": "78d8c8",
        "RED": "d87878", "GREEN": "8ad088", "YELLOW": "d8c878", "CYAN": "4ac8b0",
    },
    "doom-rip": {
        "BG": "0d0603", "BG_DARK": "060302", "SURFACE": "241008",
        "FG": "ffb380", "SUBTEXT": "a06840",
        "ACCENT": "ff5500", "ACCENT2": "ff8840",
        "RED": "ff3820", "GREEN": "c8b040", "YELLOW": "ffa020", "CYAN": "c08858",
    },

    # --- light palettes -----------------------------------------------------
    # Here BG_DARK does not mean "dark": it is one notch DARKER than the main
    # background but still a light tone: templates use BG_DARK as the strip
    # and contrast background and do not assume it is dark.
    # FG/SUBTEXT contrast kept above WCAG AA (4.5:1).
    # The source is monochrome sepia: no colored accent, the active workspace
    # is a filled ink box. So ACCENT is not a color but the ink itself.
    "lamp-paper": {
        "BG": "ece5d4", "BG_DARK": "ddd4bf", "SURFACE": "e2dac7",
        "FG": "26221b", "SUBTEXT": "6a6152",
        "ACCENT": "3d372c", "ACCENT2": "8a7c5e",
        "RED": "a4503f", "GREEN": "5c7a4a", "YELLOW": "9a7d2e", "CYAN": "4a7a78",
    },
    "paper-mono": {
        "BG": "e8e4d8", "BG_DARK": "dbd6c7", "SURFACE": "cfc9b7",
        "FG": "2f2b24", "SUBTEXT": "635d50",
        "ACCENT": "6b6255", "ACCENT2": "857a68",
        "RED": "9c4a3c", "GREEN": "556f45", "YELLOW": "8e7228", "CYAN": "456e6d",
    },
    "blanc-mono": {
        "BG": "fafafa", "BG_DARK": "ededed", "SURFACE": "e0e0e0",
        "FG": "2a2a2a", "SUBTEXT": "5e5e5e",
        "ACCENT": "4a4a4a", "ACCENT2": "7a7a7a",
        "RED": "b03030", "GREEN": "3d7a3d", "YELLOW": "8a6e00", "CYAN": "2f6f78",
    },
    "alpine-light": {
        "BG": "e8e8e8", "BG_DARK": "dadada", "SURFACE": "cccccc",
        "FG": "2a2a2a", "SUBTEXT": "5a5a5a",
        "ACCENT": "43647f", "ACCENT2": "6b8299",
        "RED": "a83c3c", "GREEN": "3f7048", "YELLOW": "876a10", "CYAN": "2f6b73",
    },
    # --- Script Test: our own profiles (presets/profile/st-*.conf) ----------
    # green leaves + Material feel: dark green surfaces, light green accent
    "st-yaprak": {
        "BG": "151b15", "BG_DARK": "0e130e", "SURFACE": "232c23",
        "FG": "e1e8dc", "SUBTEXT": "98a694",
        "ACCENT": "a9d6a0", "ACCENT2": "c7e2a8",
        "RED": "e57f73", "GREEN": "9fcf72", "YELLOW": "e3d28c", "CYAN": "8fcfc0",
    },
    # sunset: near-black background, single-color salmon text
    "st-gunbatimi": {
        "BG": "140707", "BG_DARK": "0b0303", "SURFACE": "2b1110",
        "FG": "f08c78", "SUBTEXT": "a65a4e",
        "ACCENT": "ef7c68", "ACCENT2": "e9a08e",
        "RED": "ff5a48", "GREEN": "e0a080", "YELLOW": "f2b48e", "CYAN": "eaa09a",
    },
    # crimson: black windows, cream frames, red accent
    "st-kizil": {
        "BG": "0d0707", "BG_DARK": "060303", "SURFACE": "211010",
        "FG": "f2dcc0", "SUBTEXT": "b39a7c",
        "ACCENT": "eac59f", "ACCENT2": "d9b08a",
        "RED": "e3283a", "GREEN": "d9b48a", "YELLOW": "f1c98e", "CYAN": "e6b9a0",
    },
    # night lake: purple night, lavender accent
    "st-gecegolu": {
        "BG": "1b1531", "BG_DARK": "120d23", "SURFACE": "2b2149",
        "FG": "dad2f2", "SUBTEXT": "9a8dc2",
        "ACCENT": "b9a5f0", "ACCENT2": "8b7bd2",
        "RED": "e27c9c", "GREEN": "a2d2a2", "YELLOW": "f1c979", "CYAN": "8fc6e2",
    },
    # neon city: midnight blue-black, magenta + cyan neon
    "st-neon": {
        "BG": "0d0a18", "BG_DARK": "07050f", "SURFACE": "1c1630",
        "FG": "f2e9ff", "SUBTEXT": "9a8fbf",
        "ACCENT": "ff2bd6", "ACCENT2": "00e5ff",
        "RED": "ff3864", "GREEN": "39ff9a", "YELLOW": "ffe14d", "CYAN": "00e5ff",
    },
    # sakura: light theme, pink-cream paper, dusty rose text
    "st-sakura": {
        "BG": "fbf0f2", "BG_DARK": "f3e2e7", "SURFACE": "ead2da",
        "FG": "5b3e4b", "SUBTEXT": "8f6f7c",
        "ACCENT": "d9668c", "ACCENT2": "a77fc9",
        "RED": "c94a5f", "GREEN": "5f9a6e", "YELLOW": "b98a2f", "CYAN": "4f8f9a",
    },
    # deep ocean: navy background, turquoise + sky blue
    "st-okyanus": {
        "BG": "0c1b2b", "BG_DARK": "07121e", "SURFACE": "16304a",
        "FG": "d8ecf5", "SUBTEXT": "7fa3ba",
        "ACCENT": "4fd8c8", "ACCENT2": "5aa9f0",
        "RED": "f07a7a", "GREEN": "6ad9a0", "YELLOW": "f2d27a", "CYAN": "4fd8c8",
    },
    # ink paper: light theme, sepia paper, sumi ink, red seal
    "st-kagit": {
        "BG": "f1e9d8", "BG_DARK": "e6dcc6", "SURFACE": "d9cdb4",
        "FG": "2b2620", "SUBTEXT": "6b6152",
        "ACCENT": "a8382a", "ACCENT2": "3d3a34",
        "RED": "a8382a", "GREEN": "4f6b3a", "YELLOW": "8a6a1c", "CYAN": "3c6464",
    },
    # autumn forest: warm dark brown, mustard and rust
    "st-orman": {
        "BG": "1f1b16", "BG_DARK": "15120e", "SURFACE": "2f2922",
        "FG": "ebdbb2", "SUBTEXT": "a89984",
        "ACCENT": "e0962b", "ACCENT2": "c4572a",
        "RED": "d65d3e", "GREEN": "a7a23b", "YELLOW": "e0b23b", "CYAN": "7fa58c",
    },
    # aurora: icy midnight blue, aurora green and ice blue
    "st-kutup": {
        "BG": "1a212e", "BG_DARK": "121823", "SURFACE": "273246",
        "FG": "e5ecf4", "SUBTEXT": "8f9db3",
        "ACCENT": "7fe3b4", "ACCENT2": "86c4e8",
        "RED": "e58a96", "GREEN": "7fe3b4", "YELLOW": "ecd08f", "CYAN": "86c4e8",
    },
    # phosphor CRT: pitch-black screen, green phosphor
    "st-crt": {
        "BG": "040a05", "BG_DARK": "020502", "SURFACE": "0c1d10",
        "FG": "41ff7a", "SUBTEXT": "1f9a45",
        "ACCENT": "41ff7a", "ACCENT2": "1fbf55",
        "RED": "ff5b5b", "GREEN": "41ff7a", "YELLOW": "d7ff5b", "CYAN": "5bffd2",
    },
    # frosted glass: purple-navy, lilac and ice blue; translucent surfaces
    "st-cam": {
        "BG": "1c1735", "BG_DARK": "130f26", "SURFACE": "2c2650",
        "FG": "f0ecff", "SUBTEXT": "a59fcc",
        "ACCENT": "c3a6ff", "ACCENT2": "79d4ff",
        "RED": "ff8fab", "GREEN": "8ff0c4", "YELLOW": "ffd98f", "CYAN": "79d4ff",
    },
    # --- Script Test third party: adapted from temaornek/ references --------
    # sepia: light beige paper, dark brown ink, single color (sway monochrome)
    "st-sepya": {
        "BG": "e2d5b4", "BG_DARK": "d6c7a2", "SURFACE": "c9b98f",
        "FG": "3a2e1e", "SUBTEXT": "6e5d43",
        "ACCENT": "3a2e1e", "ACCENT2": "5b4a32",
        "RED": "8e3b2a", "GREEN": "556b3a", "YELLOW": "7d6420", "CYAN": "2f6a6a",
    },
    # green valley: soft forest green, light pistachio accent (niri style)
    "st-vadi": {
        "BG": "17221a", "BG_DARK": "0f1812", "SURFACE": "25342a",
        "FG": "e3efdc", "SUBTEXT": "93a98d",
        "ACCENT": "b6e388", "ACCENT2": "8cc9a8",
        "RED": "e08a7e", "GREEN": "b6e388", "YELLOW": "e2d68c", "CYAN": "8cc9c0",
    },
    # metro: dried-blood red background, mustard yellow text (sovietpunk)
    "st-metro": {
        "BG": "2c1212", "BG_DARK": "1f0b0b", "SURFACE": "4a1d1b",
        "FG": "e6d27a", "SUBTEXT": "b39a52",
        "ACCENT": "e6d27a", "ACCENT2": "b8403a",
        "RED": "c8463a", "GREEN": "a3a84a", "YELLOW": "e6d27a", "CYAN": "9aa77a",
    },
    # manga: white paper, black ink, grey tones (light theme)
    "st-manga": {
        "BG": "fafafa", "BG_DARK": "f0f0f0", "SURFACE": "e2e2e2",
        "FG": "1c1c1c", "SUBTEXT": "6a6a6a",
        "ACCENT": "2b2b2b", "ACCENT2": "8a8a8a",
        "RED": "c0392b", "GREEN": "3c7a4a", "YELLOW": "8a6d10", "CYAN": "2f6b7a",
    },
    # lavender: midnight navy, lavender neon tubes (i3 layout)
    "st-lavanta": {
        "BG": "161722", "BG_DARK": "0f1018", "SURFACE": "23253a",
        "FG": "cfc4ec", "SUBTEXT": "7d7aa6",
        "ACCENT": "d6b4f5", "ACCENT2": "a98be0",
        "RED": "e88aa8", "GREEN": "9fd6b4", "YELLOW": "e6cf96", "CYAN": "92c2e8",
    },
    # mint: Persona cyan — deep green-blue background, bright mint accent
    "st-nane": {
        "BG": "0a3a32", "BG_DARK": "06291f", "SURFACE": "125246",
        "FG": "e6fff7", "SUBTEXT": "86c9b6",
        "ACCENT": "34f0be", "ACCENT2": "9ff7dc",
        "RED": "ff5d6c", "GREEN": "34f0be", "YELLOW": "f2e37a", "CYAN": "6ee8e8",
    },
    # moon: pitch-black sky, moon-grey text, light blue capsules
    "st-ay": {
        "BG": "0d0f14", "BG_DARK": "07080b", "SURFACE": "1c2029",
        "FG": "e6e9ef", "SUBTEXT": "8a909c",
        "ACCENT": "b7cdfa", "ACCENT2": "f2b8d0",
        "RED": "f09aa8", "GREEN": "a8dcb8", "YELLOW": "eedba0", "CYAN": "a6d8ee",
    },
    # black: charcoal, grey tones — next to no accent
    "st-siyah": {
        "BG": "0e0e0e", "BG_DARK": "070707", "SURFACE": "1c1c1c",
        "FG": "cfcfcf", "SUBTEXT": "6f6f6f",
        "ACCENT": "9a9a9a", "ACCENT2": "5a5a5a",
        "RED": "c46a6a", "GREEN": "8fb08f", "YELLOW": "c9b77f", "CYAN": "86a8b0",
    },
    # lemon: jet-black cards, acid lemon-green accent
    "st-limon": {
        "BG": "0b0b0b", "BG_DARK": "000000", "SURFACE": "1d1f1b",
        "FG": "eef0e8", "SUBTEXT": "8d9284",
        "ACCENT": "c8f43c", "ACCENT2": "e8f8b0",
        "RED": "f0786a", "GREEN": "c8f43c", "YELLOW": "f0e06a", "CYAN": "7ad8c0",
    },
    # twilight: slate background, yellow-green active area, ice blue
    "st-alacakaranlik": {
        "BG": "1b1e26", "BG_DARK": "121419", "SURFACE": "2a2e39",
        "FG": "e4e6ec", "SUBTEXT": "8d93a3",
        "ACCENT": "e3f58c", "ACCENT2": "b7d6ff",
        "RED": "f28b82", "GREEN": "e3f58c", "YELLOW": "f6d38a", "CYAN": "b7d6ff",
    },
    # pixel galaxy: purple-navy space, pink core, lilac stars
    "st-galaksi": {
        "BG": "1d1b2d", "BG_DARK": "14121f", "SURFACE": "2c2944",
        "FG": "e6dcf2", "SUBTEXT": "8f88ad",
        "ACCENT": "f2b6d6", "ACCENT2": "a9b4f2",
        "RED": "ef8aa0", "GREEN": "9fd8b8", "YELLOW": "f2d49a", "CYAN": "8fd6ee",
    },
    # summit: misty snow grey (light theme), navy clock capsule, peach
    "st-zirve": {
        "BG": "eceded", "BG_DARK": "dfe0e2", "SURFACE": "cfd1d4",
        "FG": "24262b", "SUBTEXT": "5d6168",
        "ACCENT": "1f3a8a", "ACCENT2": "f3c3a4",
        "RED": "b03a3a", "GREEN": "3e7a4c", "YELLOW": "8f6c12", "CYAN": "2a6f80",
    },
    # black hole: soot black, glowing ring cream
    "st-karadelik": {
        "BG": "0c0b0a", "BG_DARK": "050505", "SURFACE": "1d1b19",
        "FG": "ece6da", "SUBTEXT": "8c867a",
        "ACCENT": "f2e8d2", "ACCENT2": "9c9384",
        "RED": "d07a6a", "GREEN": "a3b48e", "YELLOW": "e0c88a", "CYAN": "9ab4b8",
    },
    # nerv: dark burgundy-grey panels, coral accent, purple and green lines
    "st-nerv": {
        "BG": "1a1617", "BG_DARK": "120e0f", "SURFACE": "2a2426",
        "FG": "efe6e2", "SUBTEXT": "9a8c88",
        "ACCENT": "ff7262", "ACCENT2": "b56fd6",
        "RED": "ff5a5a", "GREEN": "8fd47a", "YELLOW": "f2c75e", "CYAN": "6fc8d6",
    },
    # frog pond: dark mud green-turquoise water, sky blue + orange
    "st-kurbaga": {
        "BG": "0e2e31", "BG_DARK": "081f22", "SURFACE": "17464a",
        "FG": "d6f2ea", "SUBTEXT": "7fb0a8",
        "ACCENT": "93d3f2", "ACCENT2": "f2b468",
        "RED": "f08a7a", "GREEN": "a6d873", "YELLOW": "f2d27a", "CYAN": "6fe0d0",
    },
    # doom: ember black, hellfire orange
    "st-doom": {
        "BG": "120804", "BG_DARK": "080302", "SURFACE": "2a1208",
        "FG": "ffb27a", "SUBTEXT": "a8673c",
        "ACCENT": "ff5a0a", "ACCENT2": "ffa13d",
        "RED": "ff3a1e", "GREEN": "d0b040", "YELLOW": "ffbf30", "CYAN": "e09a62",
    },
    # mandalorian: steel blue armor, sunset orange, sand cream
    "st-mando": {
        "BG": "1e2a31", "BG_DARK": "141d22", "SURFACE": "2c3c45",
        "FG": "f2e4c8", "SUBTEXT": "a29a88",
        "ACCENT": "eba25a", "ACCENT2": "79a7b3",
        "RED": "d9694a", "GREEN": "a4b87a", "YELLOW": "f2c86a", "CYAN": "79a7b3",
    },
    # --- personal ------------------------------------------------------------
    # tower: night line — navy-black sky, steel blue, mast-light red
    "st-kule": {
        "BG": "0f141d", "BG_DARK": "090c12", "SURFACE": "1b2230",
        "FG": "c8d0dc", "SUBTEXT": "6d788b",
        "ACCENT": "e5484d", "ACCENT2": "7d92b2",
        "RED": "e5484d", "GREEN": "7fc29b", "YELLOW": "d8b46a", "CYAN": "7fb2c8",
    },
    # Personal: Workshop 2363450232 "mountains green" — charcoal grey mist,
    # black silhouettes, neon mint moon.
    "st-gozcu": {
        "BG": "1c1c1d", "BG_DARK": "131314", "SURFACE": "2a2c2b",
        "FG": "d3dbd7", "SUBTEXT": "7c8582",
        "ACCENT": "1df5a4", "ACCENT2": "5fa889",
        "RED": "e0686c", "GREEN": "1df5a4", "YELLOW": "d6c27c", "CYAN": "1dd8c0",
    },
}

DEFAULT = "catppuccin-mocha"


def names() -> list[str]:
    return sorted(THEMES)


def parse_overrides(spec: str) -> dict[str, str]:
    """``"BG=1e1e2e;;ACCENT=89b4fa"`` → ``{"BG": "1e1e2e", ...}``

    Invalid keys and malformed hex values are silently ignored; the point is
    that a hand-edited settings.conf must not blow up the install.
    """
    result: dict[str, str] = {}
    for item in (spec or "").split(";;"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        key, _, value = item.partition("=")
        key = key.strip().upper()
        value = value.strip().lstrip("#").lower()
        if key not in KEYS or len(value) != 6:
            continue
        try:
            int(value, 16)
        except ValueError:
            continue
        result[key] = value
    return result


def resolve(theme: str, overrides: str | dict[str, str] = "") -> dict[str, str]:
    """Merges the theme palette with the user's color overrides, if any."""
    palette = dict(THEMES.get(theme) or THEMES[DEFAULT])
    if isinstance(overrides, str):
        overrides = parse_overrides(overrides)
    palette.update(overrides)
    return palette


def format_overrides(palette: dict[str, str], theme: str) -> str:
    """Returns only the colors that differ from the theme, in ``CUSTOM_COLORS`` form."""
    base = THEMES.get(theme) or THEMES[DEFAULT]
    diff = [f"{key}={palette[key]}" for key in KEYS
            if key in palette and palette[key] != base.get(key)]
    return ";;".join(diff)


def is_light(palette: dict[str, str]) -> bool:
    """Is the palette's background light? (ITU-R BT.601 perceived brightness)

    Threshold 0.55 instead of 0.5: mid-dark backgrounds like gruvbox-dark must
    not be mistaken for light, while sepia/paper palettes are reliably marked light.
    """
    value = (palette.get("BG") or "000000")[:6]
    try:
        r, g, b = (int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return False
    return (0.299 * r + 0.587 * g + 0.114 * b) > 0.55


def derive(theme: str, overrides: str | dict[str, str] = "") -> dict[str, str]:
    """Produces the template variables from a theme name.

    Produced::

        COL_BG        -> "1e1e2e"        (raw hex)
        HEX_BG        -> "#1e1e2e"       (CSS)
        RGB_BG        -> "30,30,46"      (KDE kdeglobals)
        RGBA_BG       -> "rgba(1e1e2eff)"(Hyprland)
        RGBA_BG_CC    -> "rgba(1e1e2ecc)"(semi-transparent variant)
    """
    palette = resolve(theme, overrides)
    out: dict[str, str] = {"THEME": theme if theme in THEMES else DEFAULT}
    # Light/dark is derived from the palette's background brightness; no
    # separate flag is kept, so a theme lightened via CUSTOM_COLORS also gets
    # the right GTK/icon variant.
    out["THEME_IS_LIGHT"] = "1" if is_light(palette) else ""
    for key in KEYS:
        value = palette.get(key, "000000")
        out[f"COL_{key}"] = value
        out[f"HEX_{key}"] = f"#{value}"
        out[f"RGB_{key}"] = ",".join(
            str(int(value[i:i + 2], 16)) for i in (0, 2, 4))
        out[f"RGBA_{key}"] = f"rgba({value}ff)"
        out[f"RGBA_{key}_CC"] = f"rgba({value}cc)"
        out[f"RGBA_{key}_AA"] = f"rgba({value}aa)"
        out[f"RGBA_{key}_66"] = f"rgba({value}66)"
    return out
