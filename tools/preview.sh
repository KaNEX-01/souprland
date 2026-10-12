#!/usr/bin/env bash
# preview.sh — builds a single-file HTML preview of the profile / bar preset gallery.
#
#     ./tools/preview.sh                  # docs/preview.html
#     ./tools/preview.sh -o /tmp/x.html   # somewhere else
#
# No values are hand-written: every profile is resolved with preset_apply_chain
# from lib/preset.sh, so the preview shows the same data the installer produces.
# Palettes are read from the THEMES dict in python/hyprsetup/themes.py.
#
# Dependencies: bash + awk. python3 is not required (on purpose: the preview
# should be viewable outside Arch, on a machine where nothing is installed).

set -euo pipefail

SETUP_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$SETUP_ROOT/docs/preview.html"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -o|--out) OUT="$2"; shift 2 ;;
        -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
        *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
    esac
done

# lib/core.sh provides colored output and die/ok/warn; preset.sh relies on them.
# shellcheck source=../lib/core.sh
source "$SETUP_ROOT/lib/core.sh" 2>/dev/null || true
# shellcheck source=../lib/config.sh
source "$SETUP_ROOT/lib/config.sh"
# shellcheck source=../lib/preset.sh
source "$SETUP_ROOT/lib/preset.sh"

THEMES_PY="$SETUP_ROOT/python/hyprsetup/themes.py"
[[ -r "$THEMES_PY" ]] || { printf 'cannot read themes.py: %s\n' "$THEMES_PY" >&2; exit 1; }

# ---------------------------------------------------------------- palettes ---
# Flattens the THEMES dict into "theme KEY hex" lines. Format dependency:
# theme name indented 4 spaces as `"name": {`, colors as `"KEY": "hex"` pairs.
palette_table() {
    awk '
        /^[[:space:]]{4}"[a-z0-9-]+":[[:space:]]*\{/ {
            match($0, /"[a-z0-9-]+"/)
            theme = substr($0, RSTART + 1, RLENGTH - 2)
            next
        }
        /^[[:space:]]{4}\},/ { theme = ""; next }
        theme != "" {
            line = $0
            while (match(line, /"[A-Z_0-9]+":[[:space:]]*"[0-9a-fA-F]{6}"/)) {
                pair = substr(line, RSTART, RLENGTH)
                line = substr(line, RSTART + RLENGTH)
                split(pair, p, "\"")
                print theme, p[2], p[4]
            }
        }
    ' "$THEMES_PY"
}

declare -A PAL
while read -r theme key hex; do
    [[ -n "$theme" ]] && PAL["$theme:$key"]="$hex"
done < <(palette_table)

col() {  # col <theme> <KEY> [fallback]
    local v="${PAL[$1:$2]:-}"
    printf '#%s' "${v:-${3:-808080}}"
}

# BT.601 luminance — same threshold (0.55) as themes.py:is_light.
is_light_theme() {
    local hex="${PAL[$1:BG]:-000000}"
    awk -v h="$hex" 'BEGIN{
        r=strtonum("0x" substr(h,1,2))/255
        g=strtonum("0x" substr(h,3,2))/255
        b=strtonum("0x" substr(h,5,2))/255
        exit !((0.299*r + 0.587*g + 0.114*b) > 0.55)
    }'
}

html_escape() { sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g'; }

# ---------------------------------------------------------- wallpaper -----
# Renders the profile's wallpaper at a small size and embeds it as a data: URI,
# so the page stays a single file. Without python3 this is silently skipped and
# the mockup is drawn in a flat color — running without python3 is intentional
# (see the header).
WP_CACHE="${TMPDIR:-/tmp}/hyprsetup-preview-wp"
HAVE_PY=0
command -v python3 >/dev/null 2>&1 && HAVE_PY=1

wallpaper_datauri() {
    local theme="$1" style="$2"
    [[ "$HAVE_PY" == 1 && -n "$style" ]] || return 0
    mkdir -p "$WP_CACHE"
    local png="$WP_CACHE/$theme-$style.png"
    if [[ ! -s "$png" ]]; then
        PYTHONPATH="$SETUP_ROOT/python" python3 -m hyprsetup wallpaper \
            --theme "$theme" --style "$style" --out "$png" \
            --width 384 --height 216 >/dev/null 2>&1 || return 0
    fi
    printf 'data:image/png;base64,%s' "$(base64 -w0 <"$png" 2>/dev/null || base64 <"$png" | tr -d '\n')"
}

# --------------------------------------------------------- mini desktop -----
# Builds a screen mockup from the resolved values of a profile / bar preset.
# Scaling happens in CSS: values are passed as raw pixels and multiplied by --scale.
screen_markup() {
    local theme="$1" pos="$2" h="$3" w="$4" margin="$5" radius="$6" opacity="$7"
    local gi="$8" go="$9" rn="${10}" bs="${11}" layout="${12}" ws="${13}"
    local style="${14:-}"
    local dots="" i wp=""

    wp=$(wallpaper_datauri "$theme" "$style")


    # Workspace indicator: the active one in the accent color.
    for i in 1 2 3 4; do
        if [[ "$i" == 2 ]]; then dots+='<i class="ws ws--on"></i>'
        else dots+='<i class="ws"></i>'; fi
    done

    printf '<div class="screen %s" style="--bg:%s;--bar:%s;--surf:%s;--acc:%s;--fg:%s;--bar-h:%s;--bar-w:%s;--bar-m:%s;--bar-r:%s;--bar-o:%s;--gi:%s;--go:%s;--rn:%s;--bs:%s%s">' \
        "screen--$pos" \
        "$(col "$theme" BG)" "$(col "$theme" BG_DARK)" "$(col "$theme" SURFACE)" \
        "$(col "$theme" ACCENT)" "$(col "$theme" FG)" \
        "$h" "$w" "$margin" "$radius" "$opacity" "$gi" "$go" "$rn" "$bs" \
        "${wp:+;background-image:url($wp);background-size:cover}"

    printf '<div class="bar" data-ws="%s">%s<i class="fill"></i><i class="chip"></i><i class="chip chip--sm"></i></div>' \
        "$ws" "$dots"

    printf '<div class="tiles tiles--%s"><i class="win win--a"></i><i class="win win--b"></i><i class="win win--c"></i></div>' \
        "$layout"

    printf '</div>'
}

# -------------------------------------------------------------- output -------
mkdir -p "$(dirname "$OUT")"
exec 3>"$OUT"

profile_count=$(find "$SETUP_ROOT/presets/profile" -maxdepth 1 -name '*.conf' | wc -l | tr -d ' ')
bar_count=$(find "$SETUP_ROOT/presets/bar" -name '*.conf' | wc -l | tr -d ' ')
theme_count=$(palette_table | awk '{print $1}' | sort -u | wc -l | tr -d ' ')

cat >&3 <<'HTML_HEAD'
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Souprland — gallery preview</title>
<style>
:root {
  --ground: #f6f7f9;
  --panel: #ffffff;
  --ink: #16191d;
  --muted: #5d6673;
  --faint: #8b95a3;
  --line: rgba(22, 25, 29, 0.12);
  --line-soft: rgba(22, 25, 29, 0.06);
  --accent: #2f7f92;
  --accent-ink: #ffffff;
  --chip: rgba(47, 127, 146, 0.10);
  --warm-chip: rgba(169, 120, 26, 0.14);
  --warm-ink: #8a6111;
  --shadow: 0 1px 2px rgba(16,19,23,.06), 0 8px 24px rgba(16,19,23,.06);
  --scale: 0.235;
  /* Bar thickness is given as a PERCENTAGE of the mockup box, not in raw
   * pixels: the box represents 1920x1080, so a bar covers the same share of
   * the mockup as it does of the real screen. The raw pixel multiplier
   * (--scale * 2.2) was ~3x the true scale; a horizontal bar merely looked
   * "a bit thick", but a 44-52 px vertical rail ate 8% of the card width
   * and stood there like a thick column.
   * --bar-boost is a measured exaggeration so thin bars (minimal, 18px) do
   * not vanish; it is applied equally to both axes, so proportions hold.
   * At 1.6 the bars looked too skinny, so it was raised to 2.0: on a ~300 px
   * card the vertical rail comes out 12-16 px, a horizontal bar 6-15 px. */
  --bar-boost: 2.0;
  --display: "Segoe UI Variable Display", "Segoe UI", ui-sans-serif, system-ui, sans-serif;
  --mono: "Cascadia Code", "Cascadia Mono", ui-monospace, Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    --ground: #101317; --panel: #171b21; --ink: #e8ecf1;
    --muted: #98a3b2; --faint: #6f7b8a;
    --line: rgba(232, 236, 241, 0.14); --line-soft: rgba(232, 236, 241, 0.07);
    --accent: #5fb3c4; --accent-ink: #0d1114;
    --chip: rgba(95, 179, 196, 0.14);
    --warm-chip: rgba(230, 190, 110, 0.16);
    --warm-ink: #e0be74;
    --shadow: 0 1px 2px rgba(0,0,0,.4), 0 10px 30px rgba(0,0,0,.35);
  }
}
:root[data-theme="dark"] {
  --ground: #101317; --panel: #171b21; --ink: #e8ecf1;
  --muted: #98a3b2; --faint: #6f7b8a;
  --line: rgba(232, 236, 241, 0.14); --line-soft: rgba(232, 236, 241, 0.07);
  --accent: #5fb3c4; --accent-ink: #0d1114;
  --chip: rgba(95, 179, 196, 0.14);
  --warm-chip: rgba(230, 190, 110, 0.16);
  --warm-ink: #e0be74;
  --shadow: 0 1px 2px rgba(0,0,0,.4), 0 10px 30px rgba(0,0,0,.35);
}
:root[data-theme="light"] {
  --ground: #f6f7f9; --panel: #ffffff; --ink: #16191d;
  --muted: #5d6673; --faint: #8b95a3;
  --line: rgba(22, 25, 29, 0.12); --line-soft: rgba(22, 25, 29, 0.06);
  --accent: #2f7f92; --accent-ink: #ffffff;
  --chip: rgba(47, 127, 146, 0.10);
  --warm-chip: rgba(169, 120, 26, 0.14);
  --warm-ink: #8a6111;
  --shadow: 0 1px 2px rgba(16,19,23,.06), 0 8px 24px rgba(16,19,23,.06);
}

* { box-sizing: border-box; }
body {
  margin: 0; background: var(--ground); color: var(--ink);
  font-family: var(--display); font-size: 15px; line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 1420px; margin: 0 auto; padding: 0 24px 96px; }

/* ---------------------------------------------------------------- header -- */
header { padding: 56px 0 28px; border-bottom: 1px solid var(--line); }
h1 {
  font-size: clamp(28px, 4vw, 40px); font-weight: 650; margin: 0 0 10px;
  letter-spacing: -0.02em; text-wrap: balance;
}
.lede { margin: 0; color: var(--muted); max-width: 62ch; }
.counts {
  display: flex; flex-wrap: wrap; gap: 28px; margin: 26px 0 0;
  padding: 0; list-style: none;
}
.counts b {
  display: block; font-family: var(--mono); font-size: 26px; font-weight: 600;
  letter-spacing: -0.02em; font-variant-numeric: tabular-nums;
}
.counts span {
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.09em;
  color: var(--faint);
}

/* ---------------------------------------------------------------- filter -- */
.bar-tools {
  position: sticky; top: 0; z-index: 20; background: var(--ground);
  border-bottom: 1px solid var(--line); padding: 14px 0;
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
}
.bar-tools .label {
  font-size: 11px; text-transform: uppercase; letter-spacing: 0.09em;
  color: var(--faint); margin-right: 4px;
}
button.f {
  font: 500 12px/1 var(--mono); color: var(--muted); cursor: pointer;
  background: transparent; border: 1px solid var(--line);
  border-radius: 2px; padding: 7px 11px; transition: none;
}
button.f:hover { border-color: var(--accent); color: var(--ink); }
button.f[aria-pressed="true"] {
  background: var(--accent); border-color: var(--accent); color: var(--accent-ink);
}
button.f:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.spacer { flex: 1 1 auto; }

/* --------------------------------------------------------------- section -- */
section { padding-top: 44px; }
h2 {
  font-size: 13px; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.11em; color: var(--faint); margin: 0 0 4px;
}
.sec-note { margin: 0 0 22px; color: var(--muted); font-size: 14px; max-width: 68ch; }

.grid {
  display: grid; gap: 18px;
  grid-template-columns: repeat(auto-fill, minmax(272px, 1fr));
}
.grid--bars { grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); }

/* ----------------------------------------------------------------- card --- */
.card {
  background: var(--panel); border: 1px solid var(--line); border-radius: 3px;
  overflow: hidden; box-shadow: var(--shadow);
  display: flex; flex-direction: column;
}
.card[hidden] { display: none; }
.card-head {
  display: flex; align-items: baseline; gap: 8px;
  padding: 12px 14px 9px;
}
.card-head h3 {
  margin: 0; font-size: 14px; font-weight: 600; letter-spacing: -0.01em;
}
.slug {
  font-family: var(--mono); font-size: 11px; color: var(--faint);
  margin-left: auto; white-space: nowrap;
}
.tag {
  font-family: var(--mono); font-size: 10px; letter-spacing: 0.04em;
  padding: 2px 6px; border-radius: 2px; background: var(--chip);
  color: var(--accent); white-space: nowrap;
}
.tag--light { background: var(--warm-chip); color: var(--warm-ink); }
.desc {
  margin: 0; padding: 0 14px 12px; font-size: 12.5px; color: var(--muted);
  line-height: 1.45;
}

/* -------------------------------------------------------- mini desktop ---- */
.screen {
  position: relative; aspect-ratio: 16 / 10; width: 100%;
  background: var(--bg); overflow: hidden;
  border-top: 1px solid var(--line-soft); border-bottom: 1px solid var(--line-soft);
  display: flex;
}
.screen--top { flex-direction: column; }
.screen--bottom { flex-direction: column-reverse; }
.screen--left { flex-direction: row; }
.screen--right { flex-direction: row-reverse; }

.bar {
  flex: 0 0 auto; display: flex; align-items: center;
  gap: calc(4px * var(--scale) * 3);
  background: color-mix(in srgb, var(--bar) calc(var(--bar-o) * 100%), transparent);
  border-radius: calc(var(--bar-r) * 1px * var(--scale) * 2.2);
  padding: 0 calc(6px * var(--scale) * 4);
}
/* A horizontal bar is scaled against 1080, a vertical one against 1920 —
 * each against the real size of its own axis. Being a percentage, it does
 * not depend on the card width.
 *
 * Careful: in CSS a percentage margin resolves against the container's
 * WIDTH, even on the VERTICAL axis. So the top/bottom margin of a horizontal
 * bar is divided by 1728 (= 1080 x 16/10, the box aspect ratio) rather than
 * 1080; otherwise the margin would come out thicker than the bar itself. */
.screen--top .bar, .screen--bottom .bar {
  height: calc(var(--bar-h) * var(--bar-boost) * 100% / 1080);
  margin: calc(var(--bar-m) * var(--bar-boost) * 100% / 1728)
          calc(var(--bar-m) * var(--bar-boost) * 100% / 1920 + 3px);
}
.screen--left .bar, .screen--right .bar {
  width: calc(var(--bar-w) * var(--bar-boost) * 100% / 1920);
  flex-direction: column; justify-content: flex-start;
  padding: calc(6px * var(--scale) * 4) 0;
  margin: 3px calc(var(--bar-m) * var(--bar-boost) * 100% / 1920);
}
.ws {
  width: 4px; height: 4px; border-radius: 50%;
  background: var(--fg); opacity: .34; flex: 0 0 auto;
}
.ws--on { background: var(--acc); opacity: 1; width: 9px; border-radius: 3px; }
.screen--left .ws--on, .screen--right .ws--on { width: 4px; height: 9px; }
.bar[data-ws="numbers"] .ws, .bar[data-ws="roman"] .ws,
.bar[data-ws="named"] .ws { border-radius: 1px; width: 5px; }
.bar[data-ws="underline"] .ws--on { border-radius: 0; height: 2px; width: 7px; }
.bar[data-ws="occupied-only"] .ws { opacity: 0; }
.bar[data-ws="occupied-only"] .ws--on { opacity: 1; }
.fill { flex: 1 1 auto; }
.chip {
  height: 4px; width: 16px; border-radius: 2px;
  background: var(--fg); opacity: .42; flex: 0 0 auto;
}
.chip--sm { width: 9px; opacity: .3; }
.screen--left .chip, .screen--right .chip { width: 4px; height: 12px; }
.screen--left .chip--sm, .screen--right .chip--sm { height: 7px; }

/* Three-window tiling. The column ratio tells the layout engines apart:
 * dwindle makes the first split down the middle (50/50) and splits the right
 * half again; master keeps the main window at MASTER_MFACT (0.55) width. */
.tiles {
  flex: 1 1 auto; min-height: 0; min-width: 0;
  display: grid; grid-template-rows: 1fr 1fr;
  padding: calc(var(--go) * 1px * var(--scale) * 2.2);
  gap: calc(var(--gi) * 1px * var(--scale) * 2.2);
}
.tiles--dwindle { grid-template-columns: 1fr 1fr; }
.tiles--master  { grid-template-columns: 1.22fr 1fr; }
.win {
  background: var(--surf); min-width: 0; min-height: 0;
  border-radius: calc(var(--rn) * 1px * var(--scale) * 2.2);
  border: calc(var(--bs) * 1px * var(--scale) * 2.2) solid transparent;
}
.win--a { grid-row: 1 / span 2; border-color: var(--acc); }

/* ----------------------------------------------------------- palette ------ */
.pal { display: flex; height: 16px; }
.pal i { flex: 1 1 0; }
.pal i:first-child { flex: 1.6 1 0; }

/* -------------------------------------------------------------- specs ----- */
dl.spec {
  margin: 0; padding: 11px 14px 13px; display: grid;
  grid-template-columns: auto 1fr; gap: 3px 12px;
  font-family: var(--mono); font-size: 11px; border-top: 1px solid var(--line-soft);
}
dl.spec dt { color: var(--faint); }
dl.spec dd {
  margin: 0; color: var(--ink); text-align: right;
  font-variant-numeric: tabular-nums; overflow-wrap: anywhere;
}
dl.spec dd.ref { color: var(--muted); }

.empty {
  padding: 40px 0; color: var(--faint); font-family: var(--mono); font-size: 13px;
}
footer {
  margin-top: 64px; padding-top: 20px; border-top: 1px solid var(--line);
  color: var(--faint); font-size: 12.5px; max-width: 74ch;
}
footer code { font-family: var(--mono); color: var(--muted); }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>

<div class="wrap">
<header>
  <h1>hyprsetup gallery preview</h1>
  <p class="lede">
    Every card is drawn from the values the installer produces for that profile:
    the bar's position, height, margin, rounding and opacity;
    the window layout, gaps, border size and palette. Values are resolved
    with <code>preset_apply_chain</code>, not written by hand.
  </p>
HTML_HEAD

{
printf '  <ul class="counts">'
printf '<li><b>%s</b><span>profiles</span></li>' "$profile_count"
printf '<li><b>%s</b><span>bar presets</span></li>' "$bar_count"
printf '<li><b>%s</b><span>palettes</span></li>' "$theme_count"
printf '</ul>\n</header>\n'
} >&3

# ------------------------------------------------------------- filter bar ---
{
printf '<div class="bar-tools">\n'
printf '  <span class="label">Bar preset</span>\n'
printf '  <button class="f" data-filter="all" aria-pressed="true">all</button>\n'
while IFS= read -r b; do
    printf '  <button class="f" data-filter="%s" aria-pressed="false">%s</button>\n' "$b" "$b"
done < <(preset_names bar)
printf '  <span class="spacer"></span>\n'
printf '  <button class="f" id="themeToggle" aria-pressed="false">light / dark</button>\n'
printf '</div>\n'
} >&3

# ---------------------------------------------------------------- profiles ---
{
printf '<section>\n<h2>Profiles</h2>\n'
printf '<p class="sec-note">A profile sets the palette, the window layout and the default bar preset together. A bar preset picked separately by the user overrides the one from the profile.</p>\n'
printf '<div class="grid" id="profiles">\n'
} >&3

while IFS= read -r name; do
    file=$(preset_file "$name" profile) || continue
    title=$(preset_meta "$file" title)
    desc=$(preset_meta "$file" desc)

    # Resolve the profile through the real chain — same result as install.sh.
    eval "$(
        (
            set +u
            # shellcheck disable=SC2034  # read in another file (the sourced library)
            PRESET="$name"
            preset_apply_chain >/dev/null 2>&1
            config_defaults >/dev/null 2>&1
            for v in THEME BAR_PRESET BAR_POSITION BAR_HEIGHT BAR_WIDTH BAR_MARGIN \
                     BAR_RADIUS BAR_OPACITY BAR_WORKSPACE_STYLE LAYOUT GAPS_IN \
                     GAPS_OUT ROUNDING BORDER_SIZE FONT_FAMILY WALLPAPER_STYLE; do
                printf 'R_%s=%q\n' "$v" "${!v:-}"
            done
        )
    )"

    # "Referans" is the legacy Turkish header from pre-English installs.
    ref=$(sed -n 's/^#  \(Reference\|Referans\): \(.*\) (docs.*/\2/p' "$file")
    light=""; is_light_theme "$R_THEME" && light=1

    {
    printf '<article class="card" data-bar="%s">' "$R_BAR_PRESET"
    printf '<div class="card-head"><h3>%s</h3>' "$(printf '%s' "$title" | html_escape)"
    [[ -n "$light" ]] && printf '<span class="tag tag--light">light</span>'
    printf '<span class="slug">%s</span></div>' "$name"
    printf '<p class="desc">%s</p>' "$(printf '%s' "$desc" | html_escape)"

    screen_markup "$R_THEME" "$R_BAR_POSITION" "$R_BAR_HEIGHT" "$R_BAR_WIDTH" \
        "$R_BAR_MARGIN" "$R_BAR_RADIUS" "$R_BAR_OPACITY" "$R_GAPS_IN" \
        "$R_GAPS_OUT" "$R_ROUNDING" "$R_BORDER_SIZE" "$R_LAYOUT" \
        "$R_BAR_WORKSPACE_STYLE" "$R_WALLPAPER_STYLE"

    printf '<div class="pal">'
    for k in BG BG_DARK SURFACE FG SUBTEXT ACCENT ACCENT2 RED GREEN YELLOW CYAN; do
        printf '<i style="background:%s" title="%s %s"></i>' \
            "$(col "$R_THEME" "$k")" "$k" "$(col "$R_THEME" "$k")"
    done
    printf '</div>'

    printf '<dl class="spec">'
    printf '<dt>palette</dt><dd>%s</dd>' "$R_THEME"
    printf '<dt>bar</dt><dd>%s · %s</dd>' "$R_BAR_PRESET" "$R_BAR_POSITION"
    if [[ "$R_BAR_POSITION" == left || "$R_BAR_POSITION" == right ]]; then
        printf '<dt>width</dt><dd>%spx</dd>' "$R_BAR_WIDTH"
    else
        printf '<dt>height</dt><dd>%spx</dd>' "$R_BAR_HEIGHT"
    fi
    printf '<dt>workspace</dt><dd>%s</dd>' "$R_BAR_WORKSPACE_STYLE"
    printf '<dt>layout</dt><dd>%s · gaps %s/%s</dd>' "$R_LAYOUT" "$R_GAPS_IN" "$R_GAPS_OUT"
    printf '<dt>wallpaper</dt><dd>%s</dd>' "${R_WALLPAPER_STYLE:-—}"
    printf '<dt>rounding</dt><dd>%s · border %s</dd>' "$R_ROUNDING" "$R_BORDER_SIZE"
    [[ -n "$ref" ]] && printf '<dt>reference</dt><dd class="ref">%s</dd>' \
        "$(printf '%s' "$ref" | html_escape)"
    printf '</dl></article>\n'
    } >&3
done < <(preset_names profile)

printf '</div>\n<p class="empty" id="noneP" hidden>No profile uses this bar preset.</p>\n</section>\n' >&3

# ------------------------------------------------------------- bar presets --
{
printf '<section>\n<h2>Bar Presets</h2>\n'
printf '<p class="sec-note">Bar presets define no colors — all of them are drawn here with a single reference palette (catppuccin-mocha) so that what you compare is layout, not color. Every preset works with every theme.</p>\n'
printf '<div class="grid grid--bars">\n'
} >&3

REF_THEME="catppuccin-mocha"
while IFS= read -r name; do
    file=$(preset_file "$name" bar) || continue
    title=$(preset_meta "$file" title)
    desc=$(preset_meta "$file" desc)

    eval "$(
        (
            set +u
            # shellcheck disable=SC2034  # read in another file (the sourced library)
            BAR_PRESET="$name"
            preset_apply_chain >/dev/null 2>&1
            config_defaults >/dev/null 2>&1
            for v in BAR_POSITION BAR_HEIGHT BAR_WIDTH BAR_MARGIN BAR_RADIUS \
                     BAR_OPACITY BAR_WORKSPACE_STYLE BAR_MODULES_LEFT \
                     BAR_MODULES_CENTER BAR_MODULES_RIGHT LAYOUT GAPS_IN \
                     GAPS_OUT ROUNDING BORDER_SIZE; do
                printf 'B_%s=%q\n' "$v" "${!v:-}"
            done
        )
    )"

    {
    printf '<article class="card">'
    printf '<div class="card-head"><h3>%s</h3><span class="slug">%s</span></div>' \
        "$(printf '%s' "$title" | html_escape)" "$name"
    printf '<p class="desc">%s</p>' "$(printf '%s' "$desc" | html_escape)"

    screen_markup "$REF_THEME" "$B_BAR_POSITION" "$B_BAR_HEIGHT" "$B_BAR_WIDTH" \
        "$B_BAR_MARGIN" "$B_BAR_RADIUS" "$B_BAR_OPACITY" "$B_GAPS_IN" \
        "$B_GAPS_OUT" "$B_ROUNDING" "$B_BORDER_SIZE" "$B_LAYOUT" \
        "$B_BAR_WORKSPACE_STYLE"

    printf '<dl class="spec">'
    printf '<dt>position</dt><dd>%s</dd>' "$B_BAR_POSITION"
    if [[ "$B_BAR_POSITION" == left || "$B_BAR_POSITION" == right ]]; then
        printf '<dt>width</dt><dd>%spx</dd>' "$B_BAR_WIDTH"
    else
        printf '<dt>height</dt><dd>%spx</dd>' "$B_BAR_HEIGHT"
    fi
    printf '<dt>margin / corner</dt><dd>%s · %s</dd>' "$B_BAR_MARGIN" "$B_BAR_RADIUS"
    printf '<dt>opacity</dt><dd>%s</dd>' "$B_BAR_OPACITY"
    printf '<dt>workspace</dt><dd>%s</dd>' "$B_BAR_WORKSPACE_STYLE"
    printf '<dt>left</dt><dd class="ref">%s</dd>' "$(printf '%s' "${B_BAR_MODULES_LEFT:---}" | html_escape)"
    printf '<dt>center</dt><dd class="ref">%s</dd>' "$(printf '%s' "${B_BAR_MODULES_CENTER:---}" | html_escape)"
    printf '<dt>right</dt><dd class="ref">%s</dd>' "$(printf '%s' "${B_BAR_MODULES_RIGHT:---}" | html_escape)"
    printf '</dl></article>\n'
    } >&3
done < <(preset_names bar)

printf '</div>\n</section>\n' >&3

# ------------------------------------------------------------------ widget --
{
printf '<section>\n<h2>Widgets</h2>\n'
if [[ -n "$(preset_names widget)" ]]; then
    printf '<div class="grid">\n'
    while IFS= read -r name; do
        file=$(preset_file "$name" widget) || continue
        printf '<article class="card"><div class="card-head"><h3>%s</h3><span class="slug">%s</span></div><p class="desc">%s</p></article>\n' \
            "$(preset_meta "$file" title | html_escape)" "$name" \
            "$(preset_meta "$file" desc | html_escape)"
    done < <(preset_names widget)
    printf '</div>\n'
else
    printf '<p class="sec-note">The widget axis and engine choice are in place (<code>WIDGET_ENGINE</code>, <code>WIDGETS</code>), but <code>presets/widget/</code> is still empty — the eww templates have not been written yet. This section fills itself once files are added.</p>\n'
fi
printf '</section>\n'
} >&3

cat >&3 <<HTML_FOOT
<footer>
  <p>
    Generated by <code>tools/preview.sh</code> · data sources
    <code>presets/profile/</code>, <code>presets/bar/</code> and
    <code>python/hyprsetup/themes.py</code>.
    Bar thickness is drawn at its real proportion of the screen; thin bars
    are exaggerated 2x so they do not vanish, but since the exaggeration
    applies equally to both axes, horizontal bars and vertical rails stay comparable.
    The wallpaper is the profile's own generated image; fonts and blur are
    not in the mockups, and the real look changes with them.
    The <code>dock</code> preset's bottom bar and the widget layer are not
    generated yet, so they do not appear in the mockups.
  </p>
</footer>
</div>
<script>
(function () {
  var toggle = document.getElementById("themeToggle");
  toggle.addEventListener("click", function () {
    var root = document.documentElement;
    var dark = root.getAttribute("data-theme") === "dark" ||
      (!root.hasAttribute("data-theme") &&
        window.matchMedia("(prefers-color-scheme: dark)").matches);
    root.setAttribute("data-theme", dark ? "light" : "dark");
    toggle.setAttribute("aria-pressed", String(!dark));
  });

  var buttons = document.querySelectorAll(".f[data-filter]");
  var cards = document.querySelectorAll("#profiles .card");
  var none = document.getElementById("noneP");
  buttons.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var want = btn.getAttribute("data-filter");
      buttons.forEach(function (b) {
        b.setAttribute("aria-pressed", String(b === btn));
      });
      var shown = 0;
      cards.forEach(function (card) {
        var ok = want === "all" || card.getAttribute("data-bar") === want;
        card.hidden = !ok;
        if (ok) shown++;
      });
      none.hidden = shown !== 0;
    });
  });
})();
</script>
HTML_FOOT

exec 3>&-
printf 'Preview written: %s (%s profiles, %s bar presets)\n' "$OUT" "$profile_count" "$bar_count"
