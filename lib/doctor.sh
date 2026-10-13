# shellcheck shell=bash
# doctor.sh — post-install health check (./install.sh --doctor)
#
# Diagnoses "I installed it but X does not work" cases with one command: missing
# package, disabled service, wrong config, missing font/cursor/wallpaper,
# conflicting keybinding. Changes nothing; it only looks and says what to do.

[[ -n "${_DOCTOR_SH_LOADED:-}" ]] && return 0
_DOCTOR_SH_LOADED=1

DOCTOR_FAIL=0
DOCTOR_WARN=0

_d_ok()   { printf '  %s✓%s %s\n' "$C_GREEN" "$C_RESET" "$*"; }
_d_warn() { printf '  %s!%s %s\n' "$C_YELLOW$C_BOLD" "$C_RESET" "$*"; DOCTOR_WARN=$((DOCTOR_WARN + 1)); }
_d_fail() { printf '  %s✗%s %s\n' "$C_RED$C_BOLD" "$C_RESET" "$*"; DOCTOR_FAIL=$((DOCTOR_FAIL + 1)); }
_d_hint() { printf '    %s→ %s%s\n' "$C_DIM" "$*" "$C_RESET"; }
_d_head() { printf '\n%s%s%s\n' "$C_BOLD" "$*" "$C_RESET"; }

# Settings saved during install; the component list is read from here.
_doctor_load_state() {
    local saved="${SETTINGS_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/hyprsetup/settings.conf}"
    if [[ -r "$saved" ]]; then
        # shellcheck disable=SC1090
        source "$saved"
        DOCTOR_STATE="$saved"
    else
        DOCTOR_STATE=""
    fi
    config_defaults
    DOCTOR_COMPONENTS=()
    if [[ -n "${COMPONENTS:-}" ]]; then
        IFS=',' read -r -a DOCTOR_COMPONENTS <<<"$COMPONENTS"
    fi
    # HYPR_LANG (auto/conf/lua) determines which file set this install generated;
    # _doctor_configs uses it.
    declare -F preflight_detect_hypr_lang >/dev/null && preflight_detect_hypr_lang
}

_doctor_has_component() { in_list "$1" "${DOCTOR_COMPONENTS[@]+"${DOCTOR_COMPONENTS[@]}"}"; }

# ------------------------------------------------------------------ checks --
_doctor_session() {
    _d_head "Session"

    if have hyprctl && [[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]]; then
        local version
        version=$(hyprctl version 2>/dev/null | head -1 || true)
        _d_ok "Hyprland is running — ${version:-could not read version}"

        local errors
        errors=$(hyprctl configerrors 2>/dev/null || true)
        # "Hata yok" is Turkish for "no errors"; still accepted as a clean result.
        if [[ -z "$errors" || "$errors" == *"no errors"* || "$errors" == *"Hata yok"* ]]; then
            _d_ok "No errors in the configuration"
        else
            _d_fail "Hyprland reports configuration errors:"
            printf '%s\n' "$errors" | sed 's/^/      /' | head -20
            _d_hint "Fix the errors, then: hyprctl reload"
        fi

        local monitors
        monitors=$(hyprctl monitors -j 2>/dev/null | grep -c '"name"' || echo 0)
        if ((monitors > 0)); then
            _d_ok "$monitors display(s) active"
        else
            _d_warn "Could not read active displays"
        fi
    elif have hyprctl; then
        _d_warn "Hyprland is not running right now (some checks will be skipped)"
        _d_hint "Log in to a Hyprland session and run again"
    else
        _d_fail "hyprctl not found — Hyprland is not installed"
        _d_hint "./install.sh"
    fi

    case "${HYPR_LANG_RESOLVED:-conf}" in
        lua)  _d_warn "Config language: Lua (HYPR_LANG=${HYPR_LANG:-auto} → lua) — experimental, generated against the unreleased Hyprland 0.57+ API" ;;
        conf) _d_ok   "Config language: classic .conf (HYPR_LANG=${HYPR_LANG:-auto} → conf)" ;;
    esac

    if [[ "${XDG_CURRENT_DESKTOP:-}" == "Hyprland" ]]; then
        _d_ok "XDG_CURRENT_DESKTOP=Hyprland"
    elif [[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]]; then
        _d_warn "XDG_CURRENT_DESKTOP='${XDG_CURRENT_DESKTOP:-empty}' — portals and theme tools may get confused"
        _d_hint "Was the 'env = XDG_CURRENT_DESKTOP,Hyprland' line in env.conf read?"
    fi
}

_doctor_configs() {
    _d_head "Config files"
    local base="$HOME/.config"
    # While a ready-made profile (rice) is installed, ~/.config/hypr is the
    # author's: our split files are not there by design, and "./install.sh"
    # would overwrite the profile. Its config is checked by "rice verify".
    local rice_state="$base/hyprsetup/rice.json" rice_name=""
    if [[ -r "$rice_state" ]] && have jq &&
       jq -e --arg d "$base/hypr" '.owned | index($d)' "$rice_state" >/dev/null 2>&1; then
        rice_name=$(jq -r '.profile // "?"' "$rice_state" 2>/dev/null)
    fi

    if [[ -n "$rice_name" ]]; then
        _d_ok "Hyprland config belongs to the installed profile '$rice_name'"
        _d_hint "Check it with: PYTHONPATH=python python3 -m hyprsetup rice verify $rice_name   (in the repo folder)"
    elif [[ "${MANAGE_HYPR_CONFIGS:-1}" == 0 ]]; then
        _d_ok "Hyprland config is not managed by this tool (MANAGE_HYPR_CONFIGS=0)"
    elif [[ "${HYPR_LANG_RESOLVED:-conf}" == lua ]]; then
        local file
        for file in hyprland.lua hyprland/keybinds.lua hyprland/windowrules.lua \
                    hyprland/env.lua hyprland/autostart.lua; do
            if [[ -r "$base/hypr/$file" ]]; then
                _d_ok "hypr/$file"
            else
                _d_fail "Missing: ~/.config/hypr/$file"
                _d_hint "./install.sh   (or change and apply any setting in the settings app)"
            fi
        done

        # hyprland.lua calls require("custom") at the very end; if the file is
        # missing, Hyprland errors on startup.
        if [[ -r "$base/hypr/custom.lua" ]]; then
            _d_ok "hypr/custom.lua (your personal settings are preserved)"
        else
            _d_fail "Missing: ~/.config/hypr/custom.lua — hyprland.lua require()s it"
            _d_hint "touch ~/.config/hypr/custom.lua"
        fi
    else
        local file
        for file in hyprland.conf keybinds.conf windowrules.conf env.conf autostart.conf; do
            if [[ -r "$base/hypr/$file" ]]; then
                _d_ok "hypr/$file"
            else
                _d_fail "Missing: ~/.config/hypr/$file"
                _d_hint "./install.sh   (or change and apply any setting in the settings app)"
            fi
        done

        # hyprland.conf sources custom.conf at the very end; if the file is missing,
        # Hyprland errors on startup.
        if [[ -r "$base/hypr/custom.conf" ]]; then
            _d_ok "hypr/custom.conf (your personal settings are preserved)"
        else
            _d_fail "Missing: ~/.config/hypr/custom.conf — hyprland.conf sources this file"
            _d_hint "touch ~/.config/hypr/custom.conf"
        fi
    fi

    # Who owns the display files? The "my display layout resets every time I
    # change settings" complaint is read from here: if nwg-displays generated
    # the file, the script does not touch it, even if MANAGE_MONITORS=1 remains.
    local mon_file mon_owner
    for mon_file in monitors.conf workspaces.conf; do
        [[ -e "$base/hypr/$mon_file" ]] || continue
        mon_owner=$(foreign_config_owner "$base/hypr/$mon_file")
        if [[ -n "$mon_owner" ]]; then
            _d_ok "hypr/$mon_file — managed by '$mon_owner', the script does not touch it"
        elif [[ "$mon_file" == monitors.conf && "${MANAGE_MONITORS:-1}" == 0 ]]; then
            _d_warn "MANAGE_MONITORS=0 but hypr/monitors.conf has no other tool's signature"
            _d_hint "If you want the script to manage the display layout: MANAGE_MONITORS=1"
        fi
    done

    local tool
    for tool in "${BAR:-}" "${TERMINAL:-}" "${LAUNCHER:-}" "${NOTIFIER:-}"; do
        [[ -z "$tool" ]] && continue
        local dir="$base/$tool"
        [[ "$tool" == "waybar" ]] && dir="$base/waybar"
        if [[ -d "$dir" ]]; then
            _d_ok "$tool config present"
        else
            _d_warn "$tool: no config in ~/.config/$tool"
        fi
    done

    if [[ -r "$base/gtk-3.0/settings.ini" ]]; then
        _d_ok "GTK3 settings"
    else
        # shellcheck disable=SC2088  # deliberately literal ~ (path shown to the user / portable output)
        _d_warn "~/.config/gtk-3.0/settings.ini missing — GTK apps stay unthemed"
    fi
    if [[ -r "$base/gtk-3.0/gtk.css" ]]; then
        _d_ok "GTK3 / Adwaita accent colors"
    else
        # shellcheck disable=SC2088  # deliberately literal ~ (path shown to the user / portable output)
        _d_warn "~/.config/gtk-3.0/gtk.css missing — GTK3 apps use Adwaita's default (blue/gray) color instead of THEME"
    fi
    if [[ -r "$base/gtk-4.0/gtk.css" ]]; then
        _d_ok "GTK4 / libadwaita colors"
    else
        # shellcheck disable=SC2088  # deliberately literal ~ (path shown to the user / portable output)
        _d_warn "~/.config/gtk-4.0/gtk.css missing — GTK4 apps keep the default colors"
    fi
}

_doctor_packages() {
    _d_head "Packages"
    if ! have pacman; then
        _d_warn "no pacman — package check skipped"
        return 0
    fi
    if ((${#DOCTOR_COMPONENTS[@]} == 0)); then
        _d_warn "No saved component list (${SETTINGS_FILE:-~/.config/hyprsetup/settings.conf})"
        _d_hint "This list is created after running the installer once"
        return 0
    fi

    local id pkg missing=()
    for id in "${DOCTOR_COMPONENTS[@]}"; do
        [[ -z "$id" ]] && continue
        catalog_exists "$id" || continue
        while IFS= read -r pkg; do
            [[ -z "$pkg" ]] && continue
            # -T: "provides" counts too (see lib/packages.sh:pkg_installed).
            pacman -T "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
        done < <(catalog_field "$id" repo; catalog_field "$id" aur)
    done

    if ((${#missing[@]} == 0)); then
        _d_ok "All packages of the selected components are installed (${#DOCTOR_COMPONENTS[@]} components)"
    else
        _d_fail "${#missing[@]} package(s) missing: ${missing[*]}"
        _d_hint "sudo pacman -S --needed <missing packages>   (the settings app does not install packages)"
    fi
}

_doctor_services() {
    _d_head "Services"
    have systemctl || { _d_warn "no systemctl — service check skipped"; return 0; }

    local svc
    for svc in NetworkManager.service bluetooth.service power-profiles-daemon.service \
               sddm.service ly.service greetd.service; do
        systemctl list-unit-files "$svc" >/dev/null 2>&1 || continue
        if ! systemctl cat "$svc" >/dev/null 2>&1; then continue; fi
        if systemctl is-enabled "$svc" >/dev/null 2>&1; then
            _d_ok "$svc enabled"
        elif [[ "$svc" == sddm.service || "$svc" == ly.service || "$svc" == greetd.service ]]; then
            : # only one of the login managers is enabled
        else
            _d_warn "$svc is installed but not enabled"
            _d_hint "sudo systemctl enable --now $svc"
        fi
    done

    for svc in pipewire.service wireplumber.service; do
        if systemctl --user is-active "$svc" >/dev/null 2>&1; then
            _d_ok "$svc running"
        else
            _d_warn "$svc not running — there may be no sound"
            _d_hint "systemctl --user enable --now $svc"
        fi
    done

    if _doctor_has_component polkit; then
        if pgrep -f hyprpolkitagent >/dev/null 2>&1; then
            _d_ok "Polkit agent running"
        else
            _d_warn "Polkit agent not running — apps that ask for privileges will hang"
            _d_hint "systemctl --user start hyprpolkitagent.service"
        fi
    fi
}

_doctor_portal() {
    _d_head "Screen sharing (portal)"
    if ! _doctor_has_component portal && [[ ! -x /usr/lib/xdg-desktop-portal-hyprland ]]; then
        _d_warn "portal component not selected — screen sharing will not work"
        return 0
    fi

    if [[ -r "$HOME/.config/xdg-desktop-portal/hyprland-portals.conf" ]]; then
        _d_ok "hyprland-portals.conf present (the right backend will be picked)"
    else
        # shellcheck disable=SC2088  # deliberately literal ~ (path shown to the user / portable output)
        _d_warn "~/.config/xdg-desktop-portal/hyprland-portals.conf missing"
        _d_hint "If more than one portal is installed, screen sharing may be empty/black"
    fi

    if pgrep -f xdg-desktop-portal-hyprland >/dev/null 2>&1; then
        _d_ok "xdg-desktop-portal-hyprland running"
    else
        _d_warn "xdg-desktop-portal-hyprland not running"
        _d_hint "Log in again; if it persists: systemctl --user restart xdg-desktop-portal"
    fi
}

_doctor_theme_assets() {
    _d_head "Appearance assets"

    if have fc-list; then
        local family="${FONT_FAMILY:-Noto Sans}"
        # NO pipeline: "fc-list | grep -q" failed every time under pipefail —
        # when grep exited on the first match, fc-list's large output got
        # SIGPIPE (141) and an installed font was reported "missing".
        # The family name is given to fc-list as a pattern; only that family is listed.
        if [[ -n "$(fc-list "$family" family 2>/dev/null)" ]]; then
            _d_ok "Font found: $family"
        else
            _d_fail "Font missing: $family — icons in the bar show as boxes"
            _d_hint "sudo pacman -S noto-fonts ttf-jetbrains-mono-nerd"
        fi
    fi

    local cursor="${CURSOR_THEME:-Bibata-Modern-Ice}"
    if [[ -d "/usr/share/icons/$cursor" || -d "$HOME/.icons/$cursor" || -d "$HOME/.local/share/icons/$cursor" ]]; then
            _d_ok "Cursor theme: $cursor"
    else
        _d_warn "Cursor theme not found: $cursor — the cursor may be invisible"
        _d_hint "Install the cursor-theme component or change CURSOR_THEME"
    fi

    # THEME="auto" extracts the palette from the wallpaper; which backend is
    # used directly determines the quality of the result.
    if [[ "${THEME:-}" == "auto" ]]; then
        local backends
        backends=$(PYTHONPATH="${SETUP_ROOT:-.}/python" python3 -c \
            "from hyprsetup import palette; print(' '.join(palette.backends_available()))" \
            2>/dev/null || echo "")
        if [[ "$backends" == *matugen* ]]; then
            _d_ok "Palette extraction: matugen (Material You)"
        elif [[ "$backends" == *magick* ]]; then
            _d_ok "Palette extraction: ImageMagick histogram"
            _d_hint "For better results: install the matugen component (AUR)"
        else
            _d_warn "Palette extraction only possible with the built-in PNG decoder"
            _d_hint "If you use JPEG/WebP wallpapers, install matugen or imagemagick"
        fi
    fi

    local wallpaper
    wallpaper=$(wallpaper_file)
    if [[ -f "$wallpaper" ]]; then
        _d_ok "Wallpaper: $wallpaper"
    else
        _d_warn "No wallpaper: $wallpaper"
        _d_hint "Put an image there or run the installer again (a fallback image is generated)"
    fi

    if _doctor_has_component hyprlock; then
        if [[ -f /etc/pam.d/hyprlock ]]; then
            _d_ok "hyprlock PAM rule present"
        else
            _d_fail "/etc/pam.d/hyprlock missing — the lock screen cannot verify the password"
            _d_hint "echo 'auth include system-auth' | sudo tee /etc/pam.d/hyprlock"
        fi
    fi
}

# keybind_conflicts_report — runs the python check and returns the result in one
# of three ways (used by both doctor and the normal install flow):
#   0  → conflict lines on stdout (CONFLICT ...)
#   1  → no conflicts
#   2  → the check could not run (no python3/keybinds.json, or an error),
#        last lines of the raw output on stdout
keybind_conflicts_report() {
    local json="$SETUP_ROOT/config/keybinds.json"
    if ! have python3 || [[ ! -r "$json" ]]; then
        return 2
    fi
    local output status=0
    output=$(PYTHONPATH="$SETUP_ROOT/python" python3 -m hyprsetup keybinds \
        --keybinds "$json" --overrides "${KEYBINDS:-}" --mod "${MOD_KEY:-SUPER}" 2>&1) || status=$?

    # The command returns 1 when it finds a conflict, but also when it cannot run.
    # The output is checked to tell them apart, otherwise it falsely reports "conflict".
    # ÇAKIŞMA: legacy Turkish marker from the pre-English keybinds command output.
    if grep -qE "CONFLICT|ÇAKIŞMA" <<<"$output"; then
        grep -E "CONFLICT|ÇAKIŞMA" <<<"$output"
        return 0
    elif ((status == 0)); then
        return 1
    else
        printf '%s\n' "$output" | tail -3
        return 2
    fi
}

_doctor_keybinds() {
    _d_head "Keybindings"
    local output status=0
    output=$(keybind_conflicts_report) || status=$?
    case "$status" in
        0) _d_warn "Conflicting keybindings:"
           sed 's/^/      /' <<<"$output"
           _d_hint "Edit keybindings in the settings app: MOD+I → Keybindings" ;;
        1) _d_ok "No conflicting keybindings" ;;
        *) _d_warn "Keybinding check could not run"
           sed 's/^/      /' <<<"$output" ;;
    esac
}

# ---------------------------------------------------------------- plugins ---
# hyprpm plugins are built from source against the installed Hyprland's
# headers. If they are not rebuilt after a Hyprland update, Hyprland does NOT
# LOAD them and silently starts without plugins — to the user this looks like
# "my hy3 layout suddenly became dwindle" or "window titles disappeared", and
# the reason is written nowhere. That is exactly the case doctor must
# catch.
_doctor_plugins() {
    have hyprpm || return 0

    local list
    list=$(hyprpm list 2>/dev/null) || return 0
    # If no plugins were added, this section does not concern the user.
    grep -q 'Plugin' <<<"$list" 2>/dev/null || return 0

    _d_head "Hyprland plugins"

    # hyprpm reports mismatched headers in its own output.
    if grep -qiE 'headers.*(outdated|mismatch)|need.*update' <<<"$(hyprpm list 2>&1)"; then
        _d_fail "Plugin headers are out of date — plugins may not be loading"
        _d_hint "To fix: hyprpm update && hyprpm reload"
    fi

    local name enabled=0 disabled=0
    while IFS= read -r name; do
        [[ -n "$name" ]] || continue
        if grep -A2 "Plugin $name" <<<"$list" | grep -qi 'enabled.*true\|→ enabled'; then
            enabled=$((enabled + 1))
        else
            disabled=$((disabled + 1))
            _d_warn "Plugin not enabled: $name"
            _d_hint "hyprpm enable $name"
        fi
    done < <(grep -oP 'Plugin \K[a-zA-Z0-9_+-]+' <<<"$list" | sort -u)

    ((enabled)) && _d_ok "$enabled plugin(s) enabled"
    ((disabled)) || _d_ok "No disabled plugins"

    # If hy3 is selected, LAYOUT must be hy3 too; otherwise the plugin loads but
    # has no effect.
    if _doctor_has_component hy3 && [[ "${LAYOUT:-dwindle}" != "hy3" ]]; then
        _d_warn "hy3 is installed but LAYOUT=\"${LAYOUT:-dwindle}\" — the layout engine is not used"
        _d_hint "In the settings app: MOD+I → Layout → Layout engine = hy3"
    fi
    return 0
}

doctor_run() {
    banner
    info "Health check"
    _doctor_load_state
    if [[ -n "$DOCTOR_STATE" ]]; then
        step "Saved settings read: $DOCTOR_STATE"
    else
        warn "No saved settings file — checks will use the defaults."
    fi

    _doctor_session
    _doctor_configs
    if have jq && [[ -r "${CATALOG:-}" ]]; then
        _doctor_packages
    fi
    _doctor_services
    _doctor_portal
    _doctor_theme_assets
    _doctor_plugins
    _doctor_keybinds

    printf '\n%sSummary%s  ·  %s%s errors%s · %s%s warnings%s\n\n' \
        "$C_BOLD" "$C_RESET" \
        "$C_RED$C_BOLD" "$DOCTOR_FAIL" "$C_RESET" \
        "$C_YELLOW$C_BOLD" "$DOCTOR_WARN" "$C_RESET"

    if ((DOCTOR_FAIL == 0 && DOCTOR_WARN == 0)); then
        ok "Everything looks fine."
    else
        printf '  Most problems are fixed by running the installer again:\n'
        printf '    %s./install.sh%s\n\n' "$C_CYAN" "$C_RESET"
    fi
    return $((DOCTOR_FAIL > 0 ? 1 : 0))
}
