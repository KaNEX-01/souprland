"""Icon sets for the Waybar modules (BAR_ICON_STYLE).

The template (templates/waybar/config.jsonc.tmpl) and mic.sh used to hard-code
Material Design glyphs, so the bar's icon language could not be changed. Now every
glyph is a slot (``CPU``, ``VOL``…) and every set fills those slots.
``template_vars()`` gives the template:

* ``BAR_I_<SLOT>``    a single glyph (safe to write inside a JSON string),
* ``BAR_I_<SLOT>_P``  glyph + space; empty if the glyph is empty — so the
  "{{..._P}}{usage}%" form leaves no leading space in an icon-less set,
* list slots (temperature, brightness, volume, battery levels) as a ready JSON array.

Nerd Font code points were verified by name against glyphnames.json (nerd-fonts
master, 2026-10); the names are in the comments.
"""

from __future__ import annotations

import json

DEFAULT = "material"

#: Expected length of each leveled (list) slot.
LISTS = {"TEMP": 3, "BRIGHT": 3, "VOL": 3, "BAT": 5, "WIFI_LEVELS": 4}


def _c(*codes: int) -> str:
    return "".join(chr(c) for c in codes)


STYLES: dict[str, dict[str, object]] = {
    # Material Design (nf-md) — the set the project has used since day one.
    "material": {
        "CPU": _c(0xF0EE0),            # md-cpu_64_bit
        "MEM": _c(0xF035B),            # md-memory
        "DISK": _c(0xF02CA),           # md-harddisk
        "TEMP": [_c(0xF10C3), _c(0xF050F), _c(0xF10C2)],   # thermometer_low/-/high
        "BRIGHT": [_c(0xF00DE), _c(0xF00DF), _c(0xF00E0)],  # brightness_5/6/7
        "VOL": [_c(0xF057F), _c(0xF0580), _c(0xF057E)],     # volume_low/medium/high
        "VOL_MUTE": _c(0xF075F),       # md-volume_mute
        "HEADPHONE": _c(0xF02CB),      # md-headphones
        "HEADSET": _c(0xF02CE),        # md-headset
        "BT": _c(0xF00AF),             # md-bluetooth
        "BT_OFF": _c(0xF00B2),         # md-bluetooth_off
        "BT_CONN": _c(0xF00B1),        # md-bluetooth_connect
        "WIFI": _c(0xF0928),           # md-wifi_strength_4
        # By signal strength (waybar format-icons, weakest to strongest).
        "WIFI_LEVELS": [_c(0xF091F), _c(0xF0922), _c(0xF0925), _c(0xF0928)],
        # Wired connection: a globe (md-web) instead of the old ethernet port; the
        # "connected" text was dropped too, details are in the tooltip (2026-10-04).
        "ETH": _c(0xF059F),            # md-web
        "NET_OFF": _c(0xF092D),        # md-wifi_strength_off
        "BAT": [_c(0xF007A), _c(0xF007D), _c(0xF0080), _c(0xF0082), _c(0xF0079)],
        "BAT_CHG": _c(0xF0084),        # md-battery_charging
        "BAT_PLUG": _c(0xF06A5),       # md-power_plug
        "IDLE_ON": _c(0xF0176),        # md-coffee
        "IDLE_OFF": _c(0xF0FAA),       # md-coffee_off
        "CLOCK": _c(0xF0954),          # md-clock
        "CAL": _c(0xF00ED),            # md-calendar
        "POWER": _c(0xF0425),          # md-power
        "MIC": _c(0xF036C),            # md-microphone
        "MIC_OFF": _c(0xF036D),        # md-microphone_off
    },
    # Font Awesome (nf-fa) — classic, bolder strokes.
    "fontawesome": {
        "CPU": _c(0xF2DB),             # fa-microchip
        "MEM": _c(0xEFC5),             # fa-memory
        "DISK": _c(0xF0A0),            # fa-hard_drive
        "TEMP": [_c(0xF2CB), _c(0xF2C9), _c(0xF2C7)],       # thermometer empty/half/full
        "BRIGHT": [_c(0xF186), _c(0xF0EB), _c(0xF185)],     # moon / lightbulb / sun
        "VOL": [_c(0xF026), _c(0xF027), _c(0xF028)],        # volume off/down/up
        "VOL_MUTE": _c(0xEEE8),        # fa-volume_xmark
        "HEADPHONE": _c(0xF025),       # fa-headphones
        "HEADSET": _c(0xF025),
        "BT": _c(0xF293),              # fa-bluetooth
        "BT_OFF": _c(0xF05E),          # fa-ban
        "BT_CONN": _c(0xF294),         # fa-bluetooth_b
        "WIFI": _c(0xF1EB),            # fa-wifi
        "WIFI_LEVELS": [_c(0xF1EB)] * 4,
        "ETH": _c(0xF0AC),             # fa-globe
        "NET_OFF": _c(0xF127),         # fa-link_slash
        "BAT": [_c(0xF244), _c(0xF243), _c(0xF242), _c(0xF241), _c(0xF240)],
        "BAT_CHG": _c(0xF0E7),         # fa-bolt
        "BAT_PLUG": _c(0xF1E6),        # fa-plug
        "IDLE_ON": _c(0xF0F4),         # fa-coffee
        "IDLE_OFF": _c(0xF186),        # fa-moon
        "CLOCK": _c(0xF017),           # fa-clock
        "CAL": _c(0xF073),             # fa-calendar
        "POWER": _c(0xF011),           # fa-power_off
        "MIC": _c(0xF130),             # fa-microphone
        "MIC_OFF": _c(0xF131),         # fa-microphone_slash
    },
    # Octicons (GitHub) — thin, single stroke; missing ones come from Codicons/FA.
    "octicons": {
        "CPU": _c(0xF4BC),             # oct-cpu
        "MEM": _c(0xF463),             # oct-meter
        "DISK": _c(0xF472),            # oct-database
        "TEMP": [_c(0xF490)] * 3,      # oct-flame
        "BRIGHT": [_c(0xF4EE), _c(0xF400), _c(0xF522)],     # moon / light_bulb / sun
        "VOL": [_c(0xF485)] * 3,       # oct-unmute
        "VOL_MUTE": _c(0xF466),        # oct-mute
        "HEADPHONE": _c(0xF025),       # fa-headphones
        "HEADSET": _c(0xF025),
        "BT": _c(0xF294),              # fa-bluetooth_b
        "BT_OFF": _c(0xF468),          # oct-circle_slash
        "BT_CONN": _c(0xF294),
        "WIFI": _c(0xF43C),            # oct-broadcast
        "WIFI_LEVELS": [_c(0xF43C)] * 4,
        "ETH": _c(0xF484),             # oct-globe
        "NET_OFF": _c(0xF529),         # oct-unlink
        "BAT": [_c(0xF244), _c(0xF243), _c(0xF242), _c(0xF241), _c(0xF240)],
        "BAT_CHG": _c(0x26A1),         # oct-zap
        "BAT_PLUG": _c(0xF492),        # oct-plug
        "IDLE_ON": _c(0xF441),         # oct-eye
        "IDLE_OFF": _c(0xF4C5),        # oct-eye_closed
        "CLOCK": _c(0xF43A),           # oct-clock
        "CAL": _c(0xF455),             # oct-calendar
        "POWER": _c(0xF011),           # fa-power_off
        "MIC": _c(0xEC12),             # cod-mic
        "MIC_OFF": _c(0xF131),         # fa-microphone_slash
    },
    # Color emoji — no Nerd Font needed (noto-fonts-emoji is enough).
    "emoji": {
        "CPU": "💻", "MEM": "🧠", "DISK": "💽",
        "TEMP": ["🧊", "🌡️", "🔥"],
        "BRIGHT": ["🔅", "🔆", "☀️"],
        "VOL": ["🔈", "🔉", "🔊"], "VOL_MUTE": "🔇",
        "HEADPHONE": "🎧", "HEADSET": "🎧",
        "BT": "🔵", "BT_OFF": "⚫", "BT_CONN": "🔵",
        "WIFI": "📶", "WIFI_LEVELS": ["📶"] * 4, "ETH": "🌐", "NET_OFF": "🚫",
        "BAT": ["🪫", "🪫", "🔋", "🔋", "🔋"], "BAT_CHG": "⚡", "BAT_PLUG": "🔌",
        "IDLE_ON": "☕", "IDLE_OFF": "😴",
        "CLOCK": "🕒", "CAL": "📅", "POWER": "⏻",
        "MIC": "🎙️", "MIC_OFF": "🔇",
    },
    # Text — short labels instead of icons (terminal feel, works with any font).
    "text": {
        "CPU": "CPU", "MEM": "RAM", "DISK": "DSK",
        "TEMP": ["TMP"] * 3, "BRIGHT": ["LUM"] * 3,
        "VOL": ["VOL"] * 3, "VOL_MUTE": "VOL",
        "HEADPHONE": "VOL", "HEADSET": "VOL",
        "BT": "BT", "BT_OFF": "BT-", "BT_CONN": "BT+",
        "WIFI": "WIFI", "WIFI_LEVELS": ["WIFI"] * 4, "ETH": "ETH", "NET_OFF": "NET",
        "BAT": ["BAT"] * 5, "BAT_CHG": "CHG", "BAT_PLUG": "AC",
        "IDLE_ON": "WAKE", "IDLE_OFF": "IDLE",
        "CLOCK": "", "CAL": "", "POWER": "⏻",
        "MIC": "MIC", "MIC_OFF": "MIC-",
    },
}

#: Setting choices: (value, label). The sample glyphs in the label are drawn with
#: the Nerd Font fallback in the GUI — so the set's look shows before picking it.
CHOICES: list[tuple[str, str]] = [
    (key, f"{label} — " + " ".join(
        str(STYLES[key][slot] if not isinstance(STYLES[key][slot], list)
            else STYLES[key][slot][-1])
        for slot in ("CPU", "MEM", "VOL", "WIFI", "BAT", "POWER")))
    for key, label in (("material", "Material (default)"),
                       ("fontawesome", "Font Awesome"),
                       ("octicons", "Thin line (Octicons)"),
                       ("emoji", "Color emoji"),
                       ("text", "Text"))
]


def _inline(text: str) -> str:
    """Form to write INSIDE a JSON string (without quotes)."""
    return json.dumps(text, ensure_ascii=False)[1:-1]


def template_vars(style: str) -> dict[str, str]:
    icons = STYLES.get((style or "").strip(), STYLES[DEFAULT])
    out: dict[str, str] = {}
    for slot, value in icons.items():
        if isinstance(value, list):
            out[f"BAR_I_{slot}"] = json.dumps(value, ensure_ascii=False)
            continue
        out[f"BAR_I_{slot}"] = _inline(value)
        out[f"BAR_I_{slot}_P"] = _inline(value + " ") if value else ""
    return out
