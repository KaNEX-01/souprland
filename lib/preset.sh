# shellcheck shell=bash
# preset.sh — presets: profiles, bar presets, widgets
#
# There are three independent axes; each in its own dir, with the same file format:
#
#     presets/profile/<name>.conf   → PRESET       (Profiles)
#     presets/bar/<name>.conf       → BAR_PRESET   (Bar Presets)
#     presets/widget/<name>.conf    → WIDGETS      (Widgets, multi-select)
#
# A preset is a plain shell file that gives curated values to settings in
# CONFIG_VARS. Precedence:
#
#     CLI options  >  user settings.conf  >  preset  >  defaults
#
# To keep this order, presets are applied after the user file is read but
# before config_defaults, and only write to variables that are **not yet
# defined** (see preset_apply).
#
# A profile only gives DEFAULTS for the bar preset and widget list: even if the
# profile says BAR_PRESET=islands, the user's choice wins if they picked a bar
# separately. The chain is resolved by preset_apply_chain:
#
#     profile  →  the bar preset it points to  →  widgets  →  defaults

[[ -n "${_PRESET_SH_LOADED:-}" ]] && return 0
_PRESET_SH_LOADED=1

PRESET_ROOT="${PRESET_ROOT:-$SETUP_ROOT/presets}"

# Settings "owned" by a bar preset. These are cleared first when the preset
# changes; otherwise values from the previous preset leak — e.g. rail's
# two-line clock (%H%n%M) would stay as-is after switching to a horizontal preset.
# The same list is repeated in python/hyprsetup/presets.py as BAR_KEYS;
# both must be updated together.
PRESET_BAR_KEYS=(
    # BAR (waybar/hyprpanel backend) is defined in some bar presets
    # (hyprpanel-*); if it is not included here, switching to a preset like
    # islands leaves a "hyprpanel" leak and no backend is picked correctly.
    BAR
    BAR_POSITION BAR_HEIGHT BAR_WIDTH BAR_MARGIN BAR_SPACING BAR_PADDING
    BAR_RADIUS BAR_OPACITY BAR_WORKSPACE_STYLE BAR_CLOCK_FORMAT
    BAR_CLOCK_FORMAT_ALT BAR_WINDOW_MAX_LENGTH
    BAR_MODULES_LEFT BAR_MODULES_CENTER BAR_MODULES_RIGHT
)

# Keys owned by a widget set: so corners and sizes do not leak from the
# previous set when the set changes (e.g. "showcase"'s seven-box bottom-right
# corner should not stay behind after switching to "media").
# shellcheck disable=SC2034  # read in another file (a sourced library)
PRESET_WIDGET_KEYS=(
    WIDGETS WIDGET_ZONE_TL WIDGET_ZONE_TC WIDGET_ZONE_TR
    WIDGET_ZONE_BL WIDGET_ZONE_BC WIDGET_ZONE_BR WIDGET_OFFSETS
    WIDGET_MARGIN WIDGET_GAP WIDGET_SCALE
)

# Keys owned by a widget STYLE (presets/widget-style/): how the widgets look,
# independent of the set's layout (same as presets.py:WIDGET_STYLE_KEYS).
# shellcheck disable=SC2034  # read in another file (a sourced library)
PRESET_WIDGET_STYLE_KEYS=(
    WIDGET_RADIUS WIDGET_OPACITY WIDGET_BOX WIDGET_SURFACE
    WIDGET_BORDER WIDGET_BORDER_TONE WIDGET_SHADOW WIDGET_BLUR
    WIDGET_METER WIDGET_MUSIC WIDGET_CLOCK
)

# Keys owned by a terminal preset (same as presets.py:TERM_KEYS).
# shellcheck disable=SC2034  # read in another file (a sourced library)
PRESET_TERM_KEYS=(
    TERM_OPACITY TERM_PADDING TERM_FONT_SIZE TERM_CURSOR_STYLE
    TERM_CURSOR_BLINK TERM_SCROLLBACK
)

# Keys owned by a launcher preset (presets.py:LAUNCHER_KEYS).
# shellcheck disable=SC2034  # read in another file (a sourced library)
PRESET_LAUNCHER_KEYS=(
    LAUNCHER_WIDTH LAUNCHER_LINES LAUNCHER_POSITION LAUNCHER_OPACITY
    LAUNCHER_ICONS LAUNCHER_ICON_SIZE LAUNCHER_PROMPT
    LAUNCHER_RADIUS LAUNCHER_BORDER
)

# If TERM_PRESET / LAUNCHER_PRESET is "auto", the preset is picked to match the
# character of the active bar preset. EXACTLY the same rules as
# python/hyprsetup/presets.py:bar_family + FAMILY_MATCH.
#     preset_match_axis terminal|launcher   → preset name
preset_match_axis() {
    local family
    family=$(awk -v r="${BAR_RADIUS:-10}" -v o="${BAR_OPACITY:-1.0}" 'BEGIN {
        r += 0; o += 0
        if (o > 0 && o < 0.7)  { print "glass"; exit }
        if (r <= 0)            { print (o > 0 ? "sharp" : "bare"); exit }
        if (r >= 12)           { print "rounded"; exit }
        print "soft" }')
    case "$1:$family" in
        terminal:glass)   echo glass ;;     launcher:glass)   echo glass ;;
        terminal:sharp)   echo classic ;;   launcher:sharp)   echo sharp ;;
        terminal:bare)    echo minimal ;;   launcher:bare)    echo minimal ;;
        terminal:rounded) echo soft ;;      launcher:rounded) echo rounded ;;
        terminal:soft)    echo minimal ;;   launcher:soft)    echo centered ;;
    esac
}

# Backward compatibility: PRESET_DIR used to be presets/, profiles now live
# in a subdir. If set from outside it is respected (tools/build-dotfiles.sh).
PRESET_DIR="${PRESET_DIR:-$PRESET_ROOT/profile}"

# Removed preset names → replacement name, keyed by "<kind>:<old>".
# When a preset is deleted, the old name may remain in the user's settings.conf;
# config_validate treats an unknown name as fatal (see lib/config.sh), so
# deleting without an alias would break existing installs.
# The same table is repeated in python/hyprsetup/presets.py as PRESET_ALIASES;
# both must be updated together.
declare -gA PRESET_ALIAS=(
    # media was a copy of islands shrunk by a few pixels and, having no CSS of
    # its own, did not even give the island look; islands already has CENTER=mpris.
    [bar:media]=islands
)

# preset_canonical <name> <kind> — if a removed name is given, prints its
# replacement. No warning here so that only the caller warns (once);
# it translates silently.
preset_canonical() {
    printf '%s' "${PRESET_ALIAS[${2:-profile}:$1]:-$1}"
}

# preset_dir <kind> — profile | bar | terminal | launcher | widget | widget-set | widget-style
preset_dir() {
    case "$1" in
        profile|"")  printf '%s' "$PRESET_DIR" ;;
        bar)         printf '%s' "$PRESET_ROOT/bar" ;;
        terminal)    printf '%s' "$PRESET_ROOT/terminal" ;;
        launcher)    printf '%s' "$PRESET_ROOT/launcher" ;;
        widget)      printf '%s' "$PRESET_ROOT/widget" ;;
        # Widget set LAYOUT: which widgets are on and in which corner.
        # Not to be confused with presets/widget/ — that is one definition
        # file PER widget (name, description), this is the whole layout.
        widget-set)  printf '%s' "$PRESET_ROOT/widget-set" ;;
        # Widget STYLE: how the widgets look (plate, border, gauges, clock).
        widget-style) printf '%s' "$PRESET_ROOT/widget-style" ;;
        # Look variants of the selected profile (same as python/hyprsetup/presets.py:
        # variants_dir): <profile>.variants/<name>.conf. The profile name is
        # validated as a file name, so it is safe to append to the path.
        variant)
            [[ -n "${PRESET:-}" && "$PRESET" != */* && "$PRESET" != .* ]] || return 1
            printf '%s' "$PRESET_DIR/${PRESET}.variants" ;;
        *)           return 1 ;;
    esac
}

# preset_kind_label <kind> — singular name; used in error and confirmation messages.
preset_kind_label() {
    case "$1" in
        bar)      printf 'Bar preset' ;;
        terminal) printf 'Terminal preset' ;;
        launcher) printf 'Launcher preset' ;;
        widget)     printf 'Widget' ;;
        widget-set) printf 'Widget set' ;;
        widget-style) printf 'Widget style' ;;
        variant)    printf 'Profile variant' ;;
        *)          printf 'Profile' ;;
    esac
}

# preset_kind_title <kind> — list heading (same as the GUI section names).
preset_kind_title() {
    case "$1" in
        bar)      printf 'Bar Presets' ;;
        terminal) printf 'Terminal Presets' ;;
        launcher) printf 'Launcher Presets' ;;
        widget)     printf 'Widgets' ;;
        widget-set) printf 'Widget Sets' ;;
        widget-style) printf 'Widget Styles' ;;
        *)          printf 'Profiles' ;;
    esac
}

# preset_file <name> [kind] — prints the <dir>/<name>.conf path (returns 1 if missing).
preset_file() {
    local name="$1" kind="${2:-profile}" dir
    [[ -n "$name" ]] || return 1
    # Prevent escaping the dir: the name may only be a file name.
    [[ "$name" == */* || "$name" == .* ]] && return 1
    dir=$(preset_dir "$kind") || return 1
    local file="$dir/${name%.conf}.conf"
    [[ -r "$file" ]] || return 1
    printf '%s' "$file"
}

# preset_names [kind]
preset_names() {
    local kind="${1:-profile}" dir file
    dir=$(preset_dir "$kind") || return 1
    [[ -d "$dir" ]] || return 0
    for file in "$dir"/*.conf; do
        [[ -r "$file" ]] || continue
        basename "$file" .conf
    done
}

# preset_meta <file> <key> — reads the "# key: value" line in the header.
# The description may span multiple lines; continuation lines are indented further:
#
#     #  desc: first line
#     #        second line
preset_meta() {
    local file="$1" key="$2"
    awk -v key="$key" '
        !/^[[:space:]]*#/ { exit }                    # header block ended
        {
            line = $0
            sub(/^[[:space:]]*#[[:space:]]?/, "", line)
            if (want) {
                if (line ~ /^  +[^ ]/) {              # indented continuation line
                    sub(/^ +/, "", line)
                    out = out " " line
                    next
                }
                print out
                want = 0        # so the END block does not print it again
                exit
            }
            if (line ~ "^[[:space:]]*" key ":") {
                sub("^[[:space:]]*" key ":[[:space:]]*", "", line)
                out = line
                want = 1
            }
        }
        END { if (want) print out }
    ' "$file"
}

# preset_title <name> [kind]
preset_title() {
    local file title
    file=$(preset_file "$1" "${2:-profile}") || return 1
    title=$(preset_meta "$file" title)
    printf '%s' "${title:-$1}"
}

# preset_list [kind] — human-readable list (--list-presets / --list-bars / …).
preset_list() {
    local kind="${1:-profile}"
    local name file title desc theme bar dir
    dir=$(preset_dir "$kind") || return 1
    printf '\n%s%s%s %s(%s/)%s\n\n' \
        "$C_BOLD" "$(preset_kind_title "$kind")" "$C_RESET" \
        "$C_DIM" "${dir#"$SETUP_ROOT/"}" "$C_RESET"
    while IFS= read -r name; do
        file=$(preset_file "$name" "$kind") || continue
        title=$(preset_meta "$file" title)
        desc=$(preset_meta "$file" desc)
        printf '  %s%-22s%s %s\n' "$C_BOLD" "$name" "$C_RESET" "${title:-}"
        printf '  %-22s   %s%s%s\n' "" "$C_DIM" "$desc" "$C_RESET"
        case "$kind" in
            profile)
                theme=$(preset_value "$file" THEME)
                bar=$(preset_value "$file" BAR_PRESET)
                printf '  %-22s   %stheme: %s · bar: %s%s\n\n' "" "$C_DIM" \
                    "${theme:-?}" "${bar:-—}" "$C_RESET"
                ;;
            *) printf '\n' ;;
        esac
    done < <(preset_names "$kind")
    # An empty list looks like "the script is broken" to the user. The profile
    # dir is intentionally empty until the profile system is rewritten
    # (see presets/profile/.gitkeep); say why and what to use instead.
    if [[ -z "$(preset_names "$kind")" ]]; then
        if [[ "$kind" == profile ]]; then
            printf '  %sNo profiles yet — the profile system is being rewritten.%s\n\n' \
                "$C_DIM" "$C_RESET"
            printf '  For now, pick the look from a color palette:\n'
            printf '    %s./install.sh --set THEME=<name>%s   (palettes: %spython3 -m hyprsetup themes%s)\n' \
                "$C_CYAN" "$C_RESET" "$C_CYAN" "$C_RESET"
            printf '  Bar/terminal/launcher presets were not removed:\n'
            printf '    %s./install.sh --list-bars --list-terminals --list-launchers%s\n\n' \
                "$C_CYAN" "$C_RESET"
        else
            printf '  %sNo presets of this kind (%s).%s\n\n' \
                "$C_DIM" "${dir#"$SETUP_ROOT/"}" "$C_RESET"
        fi
        return 0
    fi
    case "$kind" in
        profile) printf '  Usage: %s./install.sh --preset <name>%s\n\n' "$C_CYAN" "$C_RESET" ;;
        bar)     printf '  Usage: %s./install.sh --bar-preset <name>%s\n\n' "$C_CYAN" "$C_RESET" ;;
        widget)  printf '  Usage: %s./install.sh --widgets <name>[,<name>…]%s\n\n' "$C_CYAN" "$C_RESET" ;;
    esac
}

# preset_value <file> <key> — reads a single value from a preset file.
preset_value() {
    local file="$1" key="$2"
    sed -n "s/^[[:space:]]*${key}=//p" "$file" | tail -n1 | sed 's/^"//; s/"$//'
}

# preset_dump <file> — reads the file in a separate shell and prints only the
# keys in CONFIG_VARS that the preset **actually** assigned.
preset_dump() {
    local file="$1"
    (
        set +u
        # PROFILE_VARIANT is not in CONFIG_VARS (the GUI writes it to settings.conf,
        # it does not go to templates), but the profile file declares its default
        # look with it; if not dumped, the bash chain never sees the default variant.
        unset "${CONFIG_VARS[@]}" PROFILE_VARIANT 2>/dev/null || true
        # shellcheck disable=SC1090
        source "$file"
        local key
        for key in "${CONFIG_VARS[@]}" PROFILE_VARIANT; do
            [[ -v "$key" ]] && printf '%s=%s\n' "$key" "${!key}"
        done
        return 0
    )
}

# preset_apply <name> [mode] [kind] — writes preset values to variables that are
# not yet defined. This way the user's settings.conf and CLI options
# override the preset.
#
# mode values:
#   ""            only writes to undefined variables (default)
#   force         overrides everything — if the user just picked the preset in the UI
#   unless-user   overrides everything except keys the user set themselves;
#                 checks _PRESET_USER_KEYS (see preset_apply_chain)
preset_apply() {
    local name="$1" mode="${2:-}" kind="${3:-profile}"
    local file line key value applied=0
    [[ -n "$name" ]] || return 0

    if ! file=$(preset_file "$name" "$kind"); then
        die "$(preset_kind_label "$kind") not found: $name (to list: ./install.sh --list-presets)"
    fi

    while IFS= read -r line; do
        key="${line%%=*}"
        value="${line#*=}"
        [[ -z "$key" ]] && continue
        case "$mode" in
            force) ;;                          # override everything
            unless-user)
                # Do not touch keys the user set themselves; touch what the
                # profile wrote.
                [[ -n "${_PRESET_USER_KEYS[$key]:-}" ]] && continue
                ;;
            *)
                [[ -v "$key" ]] && continue    # already set by the user/CLI
                ;;
        esac
        printf -v "$key" '%s' "$value"
        export "${key?}"
        ((applied++)) || true
    done < <(preset_dump "$file")

    case "$kind" in
        profile) PRESET="$name";     export PRESET ;;
        bar)     BAR_PRESET="$name"; export BAR_PRESET ;;
    esac

    ok "$(preset_kind_label "$kind") '$name' applied ($applied settings) — $(preset_title "$name" "$kind")"
    # Widget presets carry only a header by design: their names go into the
    # WIDGETS list, they do not write values to CONFIG_VARS (see presets/widget/).
    # applied=0 is normal for them — the warning only makes sense for profile/bar,
    # otherwise every profile that declares WIDGETS rains warnings during install.
    [[ "$kind" == widget ]] || ((applied)) || \
        warn "$(preset_kind_label "$kind") changed no settings: all values come from the settings file or the command line."
    return 0
}

# preset_apply_chain [mode] — resolves the three axes in order.
#
# The profile is applied first; it may also give BAR_PRESET / WIDGETS values, but
# if the user set them separately (CLI/settings.conf) their own choice stands.
# Then the bar preset and widgets are **always applied non-force**: the lower
# links of the chain must preserve the value the user gave, not the one the
# upper link gave.
preset_apply_chain() {
    local mode="${1:-}" widget key

    # Lower-axis choices explicitly set before entering the chain. In force
    # mode the profile would override these too (the "pick a profile, then
    # change the bar" flow in the GUI/TUI would break), so they are put back
    # after the profile is applied.
    local pinned_bar="${BAR_PRESET:-}" pinned_widgets="${WIDGETS:-}"
    local pinned_widget_set="${WIDGET_SET:-}" pinned_widget_style="${WIDGET_STYLE:-}"
    local pinned_term="${TERM_PRESET:-}" pinned_launcher="${LAUNCHER_PRESET:-}"

    # Every key defined before entering the chain is the user's own value
    # (CLI --set, settings.conf). No preset overrides these.
    declare -gA _PRESET_USER_KEYS=()
    for key in "${CONFIG_VARS[@]}"; do
        [[ -v "$key" ]] && _PRESET_USER_KEYS[$key]=1
    done

    if [[ -n "${PRESET:-}" ]]; then
        preset_apply "$PRESET" "$mode" profile
        # The look variant writes ON TOP of the profile (theme, wallpaper…) but
        # does not touch values the user gave. If none is given, the profile's
        # own PROFILE_VARIANT default is used; if its file is missing
        # (old/wrong name), it silently stays with the profile itself.
        if [[ -n "${PROFILE_VARIANT:-}" ]]; then
            if preset_file "$PROFILE_VARIANT" variant >/dev/null; then
                preset_apply "$PROFILE_VARIANT" unless-user variant
            else
                warn "Profile variant not found, using the profile itself: $PROFILE_VARIANT"
            fi
        fi
        [[ -n "$pinned_bar" ]]     && { BAR_PRESET="$pinned_bar"; export BAR_PRESET; }
        [[ -n "$pinned_widgets" ]] && { WIDGETS="$pinned_widgets"; export WIDGETS; }
        [[ -n "$pinned_term" ]]    && { TERM_PRESET="$pinned_term"; export TERM_PRESET; }
        [[ -n "$pinned_launcher" ]] && { LAUNCHER_PRESET="$pinned_launcher"; export LAUNCHER_PRESET; }
    fi

    # If the user explicitly picked the bar preset, it overrides the profile's own
    # BAR_* tweaks — otherwise it would be "I picked slim but the profile's height
    # stayed". If it came from the profile it is the opposite: it only fills the
    # gaps so the profile's tweaks stay on top.
    if [[ -n "$pinned_bar" ]]; then
        # The user explicitly picked the bar: the BAR_* values left by the profile
        # are cleared so a key the preset does not define does not leak from the profile.
        # The user's own values (_PRESET_USER_KEYS) are kept.
        for key in "${PRESET_BAR_KEYS[@]}"; do
            [[ -n "${_PRESET_USER_KEYS[$key]:-}" ]] || unset "${key?}"
        done
        preset_apply "$pinned_bar" unless-user bar
    elif [[ -n "${BAR_PRESET:-}" ]]; then
        preset_apply "$BAR_PRESET" "" bar
    fi

    # Terminal and launcher presets follow exactly the same rule as the bar preset:
    # if the user picked one explicitly, the TERM_*/LAUNCHER_* values left by the
    # profile are cleared and the preset stays on top; if it came from the profile
    # it only fills the gaps.
    _preset_apply_axis() {   # <pinned> <setting name> <kind> <key array name>
        local pinned="$1" current="$2" kind="$3" keys_name="$4[@]" key
        # "auto": the bar preset is already applied; find the preset that matches it.
        # If no matching preset file exists (missing/customized presets dir)
        # it is silently skipped — the Python side also skips when find() returns None.
        if [[ "$pinned" == auto ]]; then
            pinned=$(preset_match_axis "$kind")
            preset_file "$pinned" "$kind" >/dev/null 2>&1 || pinned=""
        fi
        if [[ "$current" == auto ]]; then
            current=$(preset_match_axis "$kind")
            preset_file "$current" "$kind" >/dev/null 2>&1 || current=""
        fi
        if [[ -n "$pinned" ]]; then
            for key in "${!keys_name}"; do
                [[ -n "${_PRESET_USER_KEYS[$key]:-}" ]] || unset "${key?}"
            done
            preset_apply "$pinned" unless-user "$kind"
        elif [[ -n "$current" ]]; then
            preset_apply "$current" "" "$kind"
        fi
    }
    # If neither the user nor the profile gave a preset name, "auto": the preset
    # matching the bar preset fills the gaps (same as python/hyprsetup/presets.py:resolve_chain).
    _preset_apply_axis "$pinned_term" "${TERM_PRESET:-auto}" terminal PRESET_TERM_KEYS
    _preset_apply_axis "$pinned_launcher" "${LAUNCHER_PRESET:-auto}" launcher PRESET_LAUNCHER_KEYS

    # The widget set also writes the WIDGETS list, so it must be applied BEFORE
    # the per-widget resolution below (same order as python/hyprsetup/presets.py).
    # If the user gave WIDGETS themselves (_PRESET_USER_KEYS), the set does not
    # override it: no "I picked the set but my own list disappeared".
    _preset_apply_axis "$pinned_widget_set" "${WIDGET_SET:-}" widget-set \
        PRESET_WIDGET_KEYS
    _preset_apply_axis "$pinned_widget_style" "${WIDGET_STYLE:-}" widget-style \
        PRESET_WIDGET_STYLE_KEYS

    if [[ -n "${WIDGETS:-}" ]]; then
        # "calendar,cava" → applied one by one; an unknown name does not stop the install.
        while IFS= read -r widget; do
            [[ -n "$widget" ]] || continue
            if preset_file "$widget" widget >/dev/null; then
                preset_apply "$widget" "" widget
            else
                warn "Widget not found, skipping: $widget"
            fi
        done < <(printf '%s' "$WIDGETS" | tr ',' '\n' | sed 's/^ *//; s/ *$//')
    fi
    return 0
}
