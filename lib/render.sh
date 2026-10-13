# shellcheck shell=bash
# render.sh — renders the templates and installs them under ~/.config (existing files are backed up)

[[ -n "${_RENDER_SH_LOADED:-}" ]] && return 0
_RENDER_SH_LOADED=1

RENDER_STAGE=""

# Runs the Python template engine and writes the result to a staging dir.
render_stage() {
    RENDER_STAGE="$STATE_DIR/render"
    rm -rf "$RENDER_STAGE"
    mkdir -p "$RENDER_STAGE"

    local vars_file="$STATE_DIR/render-vars.env"
    render_export_vars >"$vars_file"

    step "Generating config files"
    PYTHONPATH="$SETUP_ROOT/python" python3 -m hyprsetup render \
        --catalog   "$CATALOG" \
        --templates "$SETUP_ROOT/templates" \
        --vars      "$vars_file" \
        --selected  "$(join_by , "${SELECTED[@]}")" \
        --keybinds  "$SETUP_ROOT/config/keybinds.json" \
        --out       "$RENDER_STAGE" \
        || die "Could not render the templates."

    local count
    count=$(find "$RENDER_STAGE" -type f | wc -l)
    ok "$count config files prepared"

    if ((${#RENDER_SKIPPED_COMPONENTS[@]})); then
        warn "${#RENDER_SKIPPED_COMPONENTS[@]} components' packages are not installed, their keybindings were not generated:"
        local id
        for id in "${RENDER_SKIPPED_COMPONENTS[@]}"; do
            printf '      %s (%s)\n' "$(catalog_title "$id")" "$id"
        done
        info "To install the packages and add the keybindings, run the installer again: ./install.sh"
    fi
}

# Are a component's packages actually installed? (just being "selected" is not enough)
# Under DRY_RUN no package is really installed, so the check is skipped —
# otherwise the preview shows every component as "missing". Without pacman
# (non-Arch/test environment) it cannot be verified either; the selection is taken as-is.
#
# RENDER_ASSUME_INSTALLED=1: the output is generated for distribution, not for
# THIS machine (tools/build-dotfiles.sh). In that case the check must NOT run —
# otherwise the distributed dotfiles are shaped by whatever packages happen to be
# installed on the building machine: the same repo yields two different dotfiles
# trees on two machines, and config files for uninstalled components are never
# generated. See render.py:PORTABLE_OUTPUT (the display-name form of the same problem).
_render_component_installed() {
    local id="$1" pkg
    [[ "${DRY_RUN:-0}" == 1 ]] && return 0
    [[ "${RENDER_ASSUME_INSTALLED:-0}" == 1 ]] && return 0
    have pacman || return 0
    while IFS= read -r pkg; do
        [[ -n "$pkg" ]] || continue
        pkg_installed "$pkg" || return 1
    done < <(catalog_field "$id" repo; catalog_field "$id" aur)
    return 0
}

# Writes the variables passed to the templates as KEY=VALUE.
# The CONFIG_VARS list in lib/config.sh is the single source of truth; every
# setting added there automatically reaches the templates here.
render_export_vars() {
    local var
    for var in "${CONFIG_VARS[@]}" HAS_NVIDIA HAS_AMD HAS_INTEL; do
        printf '%s=%s\n' "$var" "${!var-}"
    done
    # HYPR_LANG (probably 'auto' above) is overridden with a concrete value for
    # the templates; preflight_detect_hypr_lang writes it to HYPR_LANG_RESOLVED.
    # It does not affect the value going to settings.conf (config_save uses
    # CONFIG_VARS, i.e. the raw HYPR_LANG) — see lib/preflight.sh.
    printf 'HYPR_LANG=%s\n' "${HYPR_LANG_RESOLVED:-${HYPR_LANG:-conf}}"
    # Hyprland add-ons of the active rice (same as python/hyprsetup/apply.py).
    [[ -f "$HOME/.config/hypr/rice.conf" ]] && printf 'RICE_HYPR=1\n' || printf 'RICE_HYPR=\n'
    [[ -f "$HOME/.config/hypr/rice.lua" ]] && printf 'RICE_HYPR_LUA=1\n' || printf 'RICE_HYPR_LUA=\n'
    # Mix parts (python/hyprsetup/mix.py): startup lines and commands bound
    # to the user's keys (MIX_OVERRIDE_*).
    [[ -f "$HOME/.config/hypr/mix.conf" ]] && printf 'MIX_HYPR=1\n' || printf 'MIX_HYPR=\n'
    [[ -f "$HOME/.config/hypr/mix.lua" ]] && printf 'MIX_HYPR_LUA=1\n' || printf 'MIX_HYPR_LUA=\n'
    if [[ -r "$HOME/.config/hyprsetup/mix.json" ]] && have jq; then
        jq -r '(.installed.commands // {}) | to_entries[] | "MIX_OVERRIDE_\(.key)=\(.value)"' \
            "$HOME/.config/hyprsetup/mix.json" 2>/dev/null
    fi
    # hyprpaper 0.8 changed its syntax (same rule as apply.py:_hyprpaper_legacy).
    local hp_ver
    hp_ver=$(pacman -Q hyprpaper 2>/dev/null | awk '{print $2}' || true)
    hp_ver="${hp_ver#*:}"; hp_ver="${hp_ver%%-*}"
    if [[ "$hp_ver" =~ ^0\.([0-7])(\.|$) ]]; then
        printf 'HYPRPAPER_LEGACY=1\n'
    else
        printf 'HYPRPAPER_LEGACY=\n'
    fi
    # Component ids may contain dashes; template variable names use underscores.
    # E.g. "qt-theme" -> HAS_QT_THEME / EXEC_QT_THEME
    # HAS_*/EXEC_* are never written for a component whose package could not be
    # installed: otherwise a keybinding tied to that component via "require"
    # (e.g. audio-mixer, night-mode) is bound to a command that will not actually
    # work and — since Hyprland silently resolves a second bind on the same key
    # by the last line — may also take over another keybinding.
    RENDER_SKIPPED_COMPONENTS=()
    local id key exec_cmd cat_id
    # Categories the active rice brings itself (rice.json "provides"): this
    # project's component in that category is not started.
    local rice_provides=()
    if [[ -r "$HOME/.config/hyprsetup/rice.json" ]] && have jq; then
        mapfile -t rice_provides < <(jq -r '.provides[]?' "$HOME/.config/hyprsetup/rice.json" 2>/dev/null)
    fi
    # Also what the mix parts bring (mix.json → installed.provides).
    if [[ -r "$HOME/.config/hyprsetup/mix.json" ]] && have jq; then
        mapfile -t -O "${#rice_provides[@]}" rice_provides < <(jq -r '.installed.provides[]?' "$HOME/.config/hyprsetup/mix.json" 2>/dev/null)
    fi
    for id in "${SELECTED[@]}"; do
        if ((${#rice_provides[@]})); then
            cat_id=$(jq -r --arg id "$id" '.categories[] | select(.components[].id == $id) | .id' "$CATALOG" | head -1)
            in_list "$cat_id" "${rice_provides[@]}" && continue
        fi
        if ! _render_component_installed "$id"; then
            RENDER_SKIPPED_COMPONENTS+=("$id")
            continue
        fi
        key="${id//-/_}"
        key="${key^^}"
        exec_cmd=$(catalog_field "$id" exec)
        [[ -n "$exec_cmd" ]] && printf 'EXEC_%s=%s\n' "$key" "$exec_cmd"
        printf 'HAS_%s=1\n' "$key"
    done
}

# Copies the files in the staging dir under ~/.config, backing them up first.
render_install() {
    [[ -d "$RENDER_STAGE" ]] || return 0
    local target_root="$HOME/.config"
    local rel src dst owner owned_path

    # Paths owned by the active rice (python/hyprsetup/rice.py) are the
    # author's files; template output is not written over them.
    local rice_owned=()
    if [[ -r "$target_root/hyprsetup/rice.json" ]] && have jq; then
        mapfile -t rice_owned < <(jq -r '.owned[]?' "$target_root/hyprsetup/rice.json" 2>/dev/null)
    fi
    if [[ -r "$target_root/hyprsetup/mix.json" ]] && have jq; then
        mapfile -t -O "${#rice_owned[@]}" rice_owned < <(jq -r '.installed.owned[]?' "$target_root/hyprsetup/mix.json" 2>/dev/null)
    fi

    info "Installing configs → $target_root"
    while IFS= read -r -d '' src; do
        rel="${src#"$RENDER_STAGE"/}"
        dst="$target_root/$rel"

        for owned_path in "${rice_owned[@]+"${rice_owned[@]}"}"; do
            if [[ "$dst" == "$owned_path" || "$dst" == "$owned_path"/* ]]; then
                debug "rice's file, skipping: $dst"
                continue 2
            fi
        done

        # A display file generated by another tool (nwg-displays) is NEVER
        # overwritten: if it were, the display layout the user made there would
        # be silently wiped. config_adopt_foreign_monitors already keeps these
        # files from being GENERATED in conf mode; this is the safety belt
        # covering lua mode and cases the detection misses.
        if in_list "$rel" "${PROTECTED_TARGETS[@]}"; then
            owner=$(foreign_config_owner "$dst")
            if [[ -n "$owner" ]]; then
                # shellcheck disable=SC2088  # deliberately literal ~ (path shown to the user / portable output)
                warn "~/.config/$rel was generated by '$owner' — not overwritten."
                continue
            fi
        fi

        if [[ ! -e "$dst" && ! -L "$dst" ]]; then
            backup_record_created "$dst"
        else
            if [[ "${OVERWRITE_CONFIGS:-ask}" == never ]]; then
                debug "exists, skipping: $dst"
                continue
            fi
            if [[ "${OVERWRITE_CONFIGS:-ask}" == ask ]] && ! confirm "Overwrite the existing file: ~/.config/$rel ?" y; then
                step "skipped: $rel"
                continue
            fi
            backup_path "$dst"
        fi

        run mkdir -p "$(dirname "$dst")"
        if [[ "${DRY_RUN:-0}" == 1 ]]; then
            printf '%s  [dry-run]%s write: %s\n' "$C_DIM" "$C_RESET" "$dst"
        else
            # Permissions come from the template ({{! mode: 755 }} makes scripts 755).
            install -D -m "$(stat -c %a "$src")" "$src" "$dst"
            step "written: ~/.config/$rel"
        fi
    done < <(find "$RENDER_STAGE" -type f -print0)

    # Hyprland 0.56 already prefers hyprland.lua over hyprland.conf: a Lua
    # config this project generated earlier (HYPR_LANG=lua) would keep being
    # loaded and the .conf just written would be ignored. Same rule as
    # apply.py:_retire_generated_lua — an author's (rice) hyprland.lua stays.
    local lua="$target_root/hypr/hyprland.lua"
    if [[ "${HYPR_LANG_RESOLVED:-${HYPR_LANG:-conf}}" == conf && -f "$lua" ]] \
        && head -c 512 "$lua" | grep -q 'generated by hyprsetup (Lua config)'; then
        for owned_path in "${rice_owned[@]+"${rice_owned[@]}"}"; do
            [[ "$lua" == "$owned_path" || "$lua" == "$owned_path"/* ]] && lua=""
        done
        if [[ -n "$lua" ]]; then
            backup_path "$lua"
            run rm -f "$lua"
            step "removed the old generated hyprland.lua (conf mode)"
        fi
    fi

    ok "Configs installed"
    [[ -d "$BACKUP_DIR" ]] && info "Backup of old files: $BACKUP_DIR"
    return 0
}

render_run() {
    [[ "${SKIP_CONFIGS:-0}" == 1 ]] && { warn "Config generation skipped (--packages-only)"; return 0; }
    render_stage
    render_install
    install_kde_color_scheme
}

# The [Colors:*]/[ColorEffects:*] groups embedded in kdeglobals are not enough on
# their own: the Breeze style in KDE Frameworks 6 reads the active colors not from
# the raw groups in kdeglobals but from the ~/.local/share/color-schemes/<name>.colors
# file pointed to by [General] ColorScheme=<name>. If that file is missing, Breeze
# silently falls back to its own default (BreezeLight/Dark) and no theme color is
# applied — that was the real reason Dolphin/Ark/Gwenview got no colors.
# Real /usr/share/color-schemes/*.colors files carry the same set of groups as
# kdeglobals, so copying the generated kdeglobals verbatim to a .colors file
# matching its name is enough.
install_kde_color_scheme() {
    local kdeglobals="$HOME/.config/kdeglobals"
    [[ -f "$kdeglobals" ]] || return 0
    local scheme_name
    scheme_name=$(sed -n 's/^ColorScheme=//p' "$kdeglobals" | head -1)
    [[ -n "$scheme_name" ]] || return 0

    local dest_dir="$HOME/.local/share/color-schemes"
    local dest="$dest_dir/${scheme_name}.colors"
    if [[ "${DRY_RUN:-0}" == 1 ]]; then
        printf '%s  [dry-run]%s write: %s\n' "$C_DIM" "$C_RESET" "$dest"
        return 0
    fi
    run mkdir -p "$dest_dir"
    cp -f "$kdeglobals" "$dest"
    step "KDE color scheme saved: $dest"

    _sync_kdedefaults "$scheme_name"
}

# ~/.config/kdedefaults/kdeglobals — a separate kdeglobals copied from /etc/skel
# when the account is created, carrying the distro "spin" defaults.
# It comes BEFORE ~/.config/kdeglobals in the KConfig cascade: its
# ColorScheme=BreezeLight REALLY OVERRIDES the ColorScheme we write to
# kdeglobals — that was the real reason Dolphin stayed frozen on BreezeLight
# whatever the theme (kdeglobals itself was correct, this file was invisibly
# in front of it). If kwriteconfig6 is missing (kde-cli-tools not installed),
# we change the relevant keys directly with sed.
_sync_kdedefaults() {
    local scheme_name="$1"
    local kdedefaults="$HOME/.config/kdedefaults/kdeglobals"
    [[ -f "$kdedefaults" ]] || return 0

    if have kwriteconfig6; then
        run kwriteconfig6 --file "$kdedefaults" --group General --key ColorScheme "$scheme_name"
        run kwriteconfig6 --file "$kdedefaults" --group KDE --key widgetStyle Breeze
    else
        backup_path "$kdedefaults"
        if [[ "${DRY_RUN:-0}" != 1 ]]; then
            grep -q '^\[General\]' "$kdedefaults" || printf '[General]\n' >>"$kdedefaults"
            if grep -q '^ColorScheme=' "$kdedefaults"; then
                sed -i "s/^ColorScheme=.*/ColorScheme=$scheme_name/" "$kdedefaults"
            else
                sed -i "/^\[General\]/a ColorScheme=$scheme_name" "$kdedefaults"
            fi
        fi
    fi
    step "kdedefaults/kdeglobals synced (the old ColorScheme was overriding kdeglobals)"
}
