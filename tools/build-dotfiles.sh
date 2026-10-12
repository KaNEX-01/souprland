#!/usr/bin/env bash
#
# build-dotfiles.sh — generates a prebuilt dotfile tree from each preset.
#
# The dotfiles/<preset>/ dirs in the repo are this script's output: a user who
# does not want to run the installer at all can copy these files directly
# under ~/.config (see dotfiles/install-dotfiles.sh).
#
# Usage:
#     ./tools/build-dotfiles.sh                 # regenerate all
#     ./tools/build-dotfiles.sh nord tokyo-night
#     ./tools/build-dotfiles.sh --check         # report differences without generating
#     ./tools/build-dotfiles.sh --out /tmp/df   # generate into another dir
#
# --check tells whether the committed dotfiles/ matches what the templates
# generate; run it after changing a template or preset.
#
set -Eeuo pipefail

SETUP_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export SETUP_ROOT

# shellcheck source=../lib/core.sh
source "$SETUP_ROOT/lib/core.sh"
# shellcheck source=../lib/config.sh
source "$SETUP_ROOT/lib/config.sh"
# shellcheck source=../lib/preset.sh
source "$SETUP_ROOT/lib/preset.sh"
# shellcheck source=../lib/packages.sh
source "$SETUP_ROOT/lib/packages.sh"
# shellcheck source=../lib/render.sh
source "$SETUP_ROOT/lib/render.sh"

CATALOG="$SETUP_ROOT/config/components.json"
OUT_DIR="$SETUP_ROOT/dotfiles"
CHECK=0
STATE_DIR="$(mktemp -d)"
trap 'rm -rf "$STATE_DIR"' EXIT

# Prebuilt dotfiles are generated for this component set. The components of
# the standard profile that have config files: hyprland + waybar + kitty + wofi +
# mako + hyprpaper + hyprlock + hypridle and what the bar modules require.
DOTFILES_PROFILE="${DOTFILES_PROFILE:-standard}"

usage() {
    sed -n '3,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

PRESET_ARGS=()
while (($#)); do
    case "$1" in
        --check)   CHECK=1; shift ;;
        --out)     OUT_DIR="$2"; shift 2 ;;
        --out=*)   OUT_DIR="${1#*=}"; shift ;;
        -h|--help) usage; exit 0 ;;
        -*)        die "Unknown option: $1" ;;
        *)         PRESET_ARGS+=("$1"); shift ;;
    esac
done

require_cmd jq
require_cmd python3

# The generated tree will be distributed: which component's config gets written
# must not depend on whether that package is installed on the BUILDING machine
# (see lib/render.sh:_render_component_installed). Otherwise the same repo
# produces two different dotfiles trees on two different machines.
RENDER_ASSUME_INSTALLED=1
export RENDER_ASSUME_INSTALLED

# List of presets to generate
if ((${#PRESET_ARGS[@]})); then
    PRESET_LIST=("${PRESET_ARGS[@]}")
else
    mapfile -t PRESET_LIST < <(preset_names)
fi
# Rice profiles (<name>.rice.toml) install the author's own files, not this
# project's config (python -m hyprsetup rice install); there is no dotfile
# tree to generate from them.
_kept=()
for _p in "${PRESET_LIST[@]}"; do
    [[ -f "$PRESET_DIR/$_p.rice.toml" ]] || _kept+=("$_p")
done
PRESET_LIST=("${_kept[@]}")
# An empty profile set is not an error (all profiles may be rices).
# Exiting with die() would break the test/CI that runs --check.
if ((${#PRESET_LIST[@]} == 0)); then
    warn "No profiles to generate a dotfile tree from ($PRESET_DIR: all are rices) — skipping."
    exit 0
fi

# Component list: the profile + primary tools of single-choice categories
mapfile -t SELECTED < <(catalog_profile_ids "$DOTFILES_PROFILE")
((${#SELECTED[@]})) || die "Empty profile: $DOTFILES_PROFILE"

# <category> <component id> — keeps only the wanted one from that category in SELECTED.
# Since the HAS_<NAME> flags are generated only from SELECTED (see
# lib/render.sh:render_export_vars), if a backend is not in SELECTED its
# template's {{! require: HAS_… }} line skips the whole file and that profile's
# bar is never generated.
selected_set_category() {
    local cat="$1" want="$2" id kept=()
    for id in "${SELECTED[@]}"; do
        [[ "$(catalog_category_of "$id")" == "$cat" ]] && continue
        kept+=("$id")
    done
    SELECTED=("${kept[@]}" "$want")
}

# render_export_vars expects variables like TERMINAL/BAR/LAUNCHER to be ready
# for single-choice categories; we use the first component in profile order.
#
# IMPORTANT: if the preset already picked this category's tool (as when a bar
# preset writes BAR="hyprpanel" or BAR="quickshell-bar"), that choice is
# PRESERVED. There used to be an unconditional assignment here, and the first bar
# component in the package profile (waybar) overrode the preset's choice: three
# profiles using hyprpanel were generated under dotfiles/ with a waybar config
# (dotfiles/warm-amber → waybar/config.jsonc, exec-once = waybar). Also, since the
# wanted backend was not added to SELECTED, HAS_<NAME> was never written and its template was skipped.
resolve_primaries() {
    local cat var id
    while IFS= read -r cat; do
        var=$(catalog_category_var "$cat")
        [[ -z "$var" ]] && continue
        # If the preset/settings file already set this category, follow it; only
        # move the component into SELECTED so the HAS_/EXEC_ variables are generated.
        if [[ -n "${!var:-}" ]] && catalog_exists "${!var}" &&
           [[ "$(catalog_category_of "${!var}")" == "$cat" ]]; then
            in_list "${!var}" "${SELECTED[@]}" || selected_set_category "$cat" "${!var}"
            export "${var?}"
            continue
        fi
        while IFS= read -r id; do
            if in_list "$id" "${SELECTED[@]}"; then
                printf -v "$var" '%s' "$id"
                export "${var?}"
                break
            fi
        done < <(jq -r --arg c "$cat" '.categories[]|select(.id==$c)|.components[].id' "$CATALOG")
    done < <(catalog_category_ids)
}

# Generates a single preset: <preset> <target dir>
build_one() {
    local preset="$1" dest="$2"
    (
        # Subshell: every preset starts with a clean settings set.
        set -Eeuo pipefail
        unset "${CONFIG_VARS[@]}" 2>/dev/null || true
        # shellcheck disable=SC2034  # read in another file (a sourced library)
        CLI_PRESET="$preset"
        config_load "" >/dev/null
        config_validate
        resolve_primaries

        # Prebuilt dotfiles assume a generic single-display machine.
        # shellcheck disable=SC2034  # read in another file (a sourced library)
        MONITOR_SPEC=",preferred,auto,1"
        # shellcheck disable=SC2034  # read in another file (a sourced library)
        WORKSPACE_MONITOR_MAP=""
        # The dotfiles/ tree is only generated in classic .conf format for now,
        # whatever Hyprland version is installed on the building machine (auto is
        # not resolved here since it does not go through preflight_detect_hypr_lang).
        # Anyone wanting Lua output should run ./install.sh directly with HYPR_LANG=lua.
        # shellcheck disable=SC2034  # read in another file (a sourced library)
        HYPR_LANG="conf"
        # Do not bake the building machine's home dir into the files: hyprpaper
        # and hyprlock expand paths starting with '~' themselves.
        # shellcheck disable=SC2034,SC2088  # read in another file (a sourced library); deliberately literal ~ (path shown to the user / portable output)
        WALLPAPER_PATH="~/Pictures/wallpapers/wallpaper.png"

        local vars="$STATE_DIR/$preset.env"
        render_export_vars >"$vars"
        # The output will be distributed: render must not look at the BUILDING
        # machine's live config (e.g. real display names in
        # ~/.config/hypr/workspaces.conf). Not in CONFIG_VARS — it is not a user
        # setting to write to settings.conf, only a flag for this generation mode.
        printf 'PORTABLE_OUTPUT=1\n' >>"$vars"

        rm -rf "$dest"
        mkdir -p "$dest"
        PYTHONPATH="$SETUP_ROOT/python" python3 -m hyprsetup render \
            --catalog   "$CATALOG" \
            --templates "$SETUP_ROOT/templates" \
            --vars      "$vars" \
            --selected  "$(join_by , "${SELECTED[@]}")" \
            --keybinds  "$SETUP_ROOT/config/keybinds.json" \
            --out       "$dest" >/dev/null
    )
}

# dotfiles/packages.txt — the packages the prebuilt files need to work.
# The component set is the same for all presets, so a single list is enough.
write_package_list() {
    local out="$1" id svc
    local -a repo_pkgs=() aur_pkgs=() services=()
    mapfile -t repo_pkgs < <(collect_packages repo "${SELECTED[@]}")
    mapfile -t aur_pkgs  < <(collect_packages aur  "${SELECTED[@]}")
    for id in "${SELECTED[@]}"; do
        while IFS= read -r svc; do
            if [[ -n "$svc" ]]; then services+=("$svc"); fi
        done < <(catalog_field "$id" services)
    done

    {
        printf '# hyprsetup — packages required by the prebuilt dotfiles\n'
        printf '# Generated by: tools/build-dotfiles.sh (profile: %s)\n' "$DOTFILES_PROFILE"
        printf '# To install: ./dotfiles/install-dotfiles.sh <preset> --packages\n'
        printf '#\n'
        printf '# [repo] official repo · [aur] needs an AUR helper · [service] systemd\n\n'
        printf '[repo]\n'
        printf '%s\n' "${repo_pkgs[@]}"
        printf '\n[aur]\n'
        if ((${#aur_pkgs[@]})); then printf '%s\n' "${aur_pkgs[@]}"; fi
        printf '\n[service]\n'
        if ((${#services[@]})); then
            printf '%s\n' "${services[@]}" | awk 'NF && !seen[$0]++'
        fi
    } >"$out"
    ok "package list: $(basename "$out") (${#repo_pkgs[@]} repo, ${#aur_pkgs[@]} AUR)"
}

resolve_primaries

info "Prebuilt dotfile generation (${#PRESET_LIST[@]} presets · profile: $DOTFILES_PROFILE)"
step "Components: ${#SELECTED[@]} · terminal=${TERMINAL:-?} bar=${BAR:-?} launcher=${LAUNCHER:-?} notifier=${NOTIFIER:-?}"

differences=0
for preset in "${PRESET_LIST[@]}"; do
    preset_file "$preset" >/dev/null || die "Preset not found: $preset"

    if ((CHECK)); then
        tmp="$STATE_DIR/check/$preset"
        build_one "$preset" "$tmp"
        if diff -ru "$OUT_DIR/$preset" "$tmp" >"$STATE_DIR/$preset.diff" 2>&1; then
            ok "$preset — up to date"
        else
            warn "$preset — DIFFERENT (dotfiles/ must be regenerated)"
            sed -n '1,40p' "$STATE_DIR/$preset.diff"
            differences=$((differences + 1))
        fi
        continue
    fi

    build_one "$preset" "$OUT_DIR/$preset"
    count=$(find "$OUT_DIR/$preset" -type f | wc -l)
    # The template engine preserves permissions; still, make sure scripts stay
    # executable (some filesystems drop permissions).
    find "$OUT_DIR/$preset" -name '*.sh' -exec chmod 755 {} +
    ok "$preset — $count files → dotfiles/$preset/"
done

if ((CHECK)); then
    write_package_list "$STATE_DIR/packages.txt" >/dev/null
    if diff -u "$OUT_DIR/packages.txt" "$STATE_DIR/packages.txt" >/dev/null 2>&1; then
        ok "packages.txt — up to date"
    else
        warn "packages.txt — DIFFERENT"
        differences=$((differences + 1))
    fi
else
    write_package_list "$OUT_DIR/packages.txt"
fi

if ((CHECK)); then
    if ((differences)); then
        die "$differences presets out of date: regenerate with ./tools/build-dotfiles.sh."
    fi
    ok "All prebuilt dotfiles match the templates exactly."
else
    ok "Done — dotfiles/ updated."
fi
