#!/usr/bin/env bash
#
# Souprland — Hyprland installer, CachyOS / Arch Linux
#
# Installs a default Hyprland desktop: installs the packages, generates the
# config files from templates, enables services and installs the settings
# app (souprland) on the system.
#
# This script is run ONCE and asks nothing. Every settings change after the
# install is made from the settings app:
#
#     MOD + I     or     souprland
#
# Every setting you change there is applied instantly; you do not need to run
# this script again (see python/hyprsetup/apply.py).
#
# If Souprland is already installed, it UPDATES instead of installing: the new
# version is downloaded (git pull if it is a git clone), new packages are
# installed, the settings app is refreshed and your settings (settings.conf) are kept and reapplied.
#
# Usage:     ./install.sh [--dry-run] [--yes] [--doctor] [--update|--reinstall]
# Help:      ./install.sh --help
#
set -Eeuo pipefail

SETUP_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export SETUP_ROOT

# -------------------------------------------------------------- libraries --
# shellcheck source=lib/core.sh
source "$SETUP_ROOT/lib/core.sh"
# shellcheck source=lib/config.sh
source "$SETUP_ROOT/lib/config.sh"
# The profile axis was removed, but bar/terminal/launcher presets remain:
# config_validate needs preset_file to validate their names, and config_load
# needs preset_apply_chain if a name like BAR_PRESET is given (the settings
# app can write these names to settings.conf).
# shellcheck source=lib/preset.sh
source "$SETUP_ROOT/lib/preset.sh"
# shellcheck source=lib/preflight.sh
source "$SETUP_ROOT/lib/preflight.sh"
# shellcheck source=lib/chaotic.sh
source "$SETUP_ROOT/lib/chaotic.sh"
# shellcheck source=lib/packages.sh
source "$SETUP_ROOT/lib/packages.sh"
# shellcheck source=lib/render.sh
source "$SETUP_ROOT/lib/render.sh"
# shellcheck source=lib/doctor.sh
source "$SETUP_ROOT/lib/doctor.sh"

# Modules: component-specific post-install steps (hook_<component-id>)
for _mod in "$SETUP_ROOT"/modules/*.sh; do
    [[ -r "$_mod" ]] || continue
    # shellcheck disable=SC1090
    source "$_mod"
done
unset _mod

STATE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/hyprsetup"
mkdir -p "$STATE_DIR"

# The user's settings. The settings app reads/writes the same file
# (python/hyprsetup/gui/app.py:_conf_path) — this is the single source of truth.
# ~/.config, not ~/.cache: a cache-cleaning tool must not delete the settings.
SETTINGS_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/hyprsetup/settings.conf"

HYPRSETUP_VERSION="2.0.0"

# ---------------------------------------------------------------- update ----
# GitHub repo the new version is downloaded from when this folder is not a git
# clone (a git clone updates itself with git pull). Set it to empty to always
# install the version in this folder.
SOUPRLAND_REPO="${SOUPRLAND_REPO-https://github.com/KaNEX-01/souprland}"
SOUPRLAND_BRANCH="${SOUPRLAND_BRANCH:-master}"
# Permanent location of the downloaded version (the settings app's .source points here).
SOUPRLAND_SRC="${XDG_DATA_HOME:-$HOME/.local/share}/souprland-src"
APP_SHARE="${XDG_DATA_HOME:-$HOME/.local/share}/hyprsetup"
# auto: update if installed, otherwise install · update · install
RUN_MODE=auto
NO_FETCH=0
ORIG_ARGS=("$@")

# ------------------------------------------------------- default desktop ----
# COMPONENTS TO INSTALL. This is the single source of truth: the install no
# longer asks for a profile or opens a wizard. To add something, write its id
# here (valid ids: config/components.json).
#
# CAUTION: the settings app does NOT install packages — a deliberate choice,
# because moving a slider should not ask for the root password. As a result,
# a program you do not list here cannot be added from the UI later; it needs a
# manual "sudo pacman -S <package>" (the settings app gives the command ready-made).
# So review the list before installing.
DEFAULT_COMPONENTS=(
    hyprland portal polkit        # core: compositor, portal, authorization
    waybar                        # status bar
    kitty                         # terminal   (standard default)
    wofi                          # application launcher
    mako                          # notification server
    hyprpaper                     # wallpaper
    pipewire                      # audio server
    networkmanager                # network
    clipboard                     # clipboard history
    screenshot-base               # grim + slurp
    fonts-base                    # base fonts (Nerd Font included)
    xdg-dirs                      # ~/Documents, ~/Downloads…
)

CONFIG_FILE=""
DRY_RUN=0
ASSUME_YES=0
VERBOSE=0
# The three below are read by lib/; always 0 in the installer, but leaving
# them undefined errors under "set -u".
SKIP_PACKAGES=0
SKIP_CONFIGS=0
USE_TUI=0

# ------------------------------------------------------------------- help ---
usage() {
    cat <<EOF
${C_BOLD}souprland${C_RESET} — Hyprland installer (CachyOS / Arch Linux)

${C_BOLD}Usage${C_RESET}
    ./install.sh                Install the default desktop
    ./install.sh --dry-run      Show what would be done, touch nothing
    ./install.sh --doctor       Check the existing install (read-only)
    ./install.sh --plymouth bgrt  Only install/change the boot animation
    ./install.sh --update       Update the installed Souprland (settings are kept)
    ./install.sh --reinstall    Install from scratch even if installed (settings are reset)

${C_BOLD}Options${C_RESET}
    -n, --dry-run     Make no changes, only describe
    -y, --yes         Do not ask for confirmation (for scripted use)
    -v, --verbose     Verbose log
        --compile MOD Build AUR packages: ask | never | always
        --skip-pkg P  Never install these packages (comma-separated)
        --doctor      Check the install and exit
        --plymouth T  Only run the Plymouth step with theme T and exit
                      (the settings app's Login Screen page calls this)
        --update      Force update mode (already the default if installed)
        --reinstall   Install from scratch even if installed; settings.conf goes back to defaults
        --no-fetch    When updating, do not download a new version, use the one in this folder
    -V, --version     Version
    -h, --help        This help

${C_BOLD}After installing${C_RESET}
    Settings are no longer made from this script but from the settings app:

        ${C_CYAN}MOD + I${C_RESET}   or   ${C_CYAN}souprland${C_RESET}

    Everything you change there (theme, gaps, bar, keybindings, displays)
    is applied instantly — you never need to run this script again.

${C_BOLD}What gets installed${C_RESET}
    ${DEFAULT_COMPONENTS[*]}

    This list is the DEFAULT_COMPONENTS array at the top of install.sh; you can
    edit it before installing. The settings app does not install packages, so
    a program you do not list here has to be installed manually later.
EOF
}

# -------------------------------------------------------------- arguments ---
parse_args() {
    while (($#)); do
        case "$1" in
            -c|--config)    CONFIG_FILE="$2"; shift 2 ;;
            --config=*)     CONFIG_FILE="${1#*=}"; shift ;;
            --compile)      CLI_COMPILE="$2"; shift 2 ;;
            --compile=*)    CLI_COMPILE="${1#*=}"; shift ;;
            --skip-pkg)     CLI_PKG_SKIP="$2"; shift 2 ;;
            --skip-pkg=*)   CLI_PKG_SKIP="${1#*=}"; shift ;;
            -n|--dry-run)   DRY_RUN=1; shift ;;
            -y|--yes)       ASSUME_YES=1; shift ;;
            -v|--verbose)   VERBOSE=1; shift ;;
            --doctor)       DO_DOCTOR=1; shift ;;
            --update)       RUN_MODE=update; shift ;;
            --reinstall)    RUN_MODE=install; shift ;;
            --no-fetch)     NO_FETCH=1; shift ;;
            --plymouth)     CLI_PLYMOUTH="$2"; shift 2 ;;
            --plymouth=*)   CLI_PLYMOUTH="${1#*=}"; shift ;;
            -V|--version)   printf 'hyprsetup %s\n' "$HYPRSETUP_VERSION"; exit 0 ;;
            -h|--help)      usage; exit 0 ;;
            *)              err "Unknown option: $1"; echo; usage; exit 2 ;;
        esac
    done
}

# ------------------------------------------------------------------ steps ---
plymouth_only_step() {
    config_load "$CONFIG_FILE"
    PLYMOUTH_THEME="$CLI_PLYMOUTH"
    info "Plymouth boot animation: $PLYMOUTH_THEME"
    if ! have plymouth-set-default-theme; then
        confirm "plymouth is not installed. Install it from the repo?" y \
            || { warn "Cancelled."; return 0; }
        run sudo pacman -S --needed plymouth || { err "Could not install plymouth."; return 1; }
    fi
    hook_plymouth
    regenerate_initramfs_if_needed
}

install_packages_step() {
    if [[ "$SKIP_PACKAGES" == 1 ]]; then
        warn "Package installation skipped (--configs-only)"
        return 0
    fi
    info "Package installation"

    local repo_pkgs aur_pkgs
    mapfile -t repo_pkgs < <(collect_packages repo "${SELECTED[@]}")
    mapfile -t aur_pkgs  < <(collect_packages aur  "${SELECTED[@]}")

    # Chaotic-AUR is only set up if there are packages coming from the AUR and
    # the user explicitly asked; if set up, part of the AUR list below comes from
    # the repo as signed binaries (see lib/chaotic.sh, install_aur_packages).
    if ((${#aur_pkgs[@]})); then chaotic_setup || true; fi

    step "Repo packages: ${#repo_pkgs[@]} · AUR packages: ${#aur_pkgs[@]}"
    if ((${#repo_pkgs[@]})); then install_repo_packages "${repo_pkgs[@]}"; fi
    if ((${#aur_pkgs[@]}));  then install_aur_packages  "${aur_pkgs[@]}";  fi
    return 0
}

run_hooks_step() {
    info "Component-specific steps"
    local id fn ran=0
    for id in "${SELECTED[@]}"; do
        fn="hook_${id//-/_}"
        if declare -F "$fn" >/dev/null; then
            step "$id → $fn"
            "$fn" || warn "$fn failed (the install continues)"
            ran=1
        fi
    done
    ((ran)) || step "No component-specific steps to run"
    return 0
}

# The system color (dark/light) is always applied — unlike hook_gtk_theme it
# does not require the "gtk-theme" component to be selected; see
# modules/theme.sh:theme_apply_color_scheme.
color_scheme_step() {
    [[ "${SKIP_CONFIGS:-0}" == 1 ]] && return 0
    info "System color"
    theme_apply_color_scheme
    theme_install_bundled_cursor
    theme_flatpak_cursor_path
    return 0
}

# Wallpaper: WALLPAPER_IMAGE is tried first — this is NOT the reference rice
# itself but an image pre-generated from the palette to evoke its composition
# (wallpapers/<profile>.png, shipped with the repo; see
# python/hyprsetup/wallpaper.py). Otherwise, if WALLPAPER_STYLE is set, the same
# generator runs on the spot (see presets/profile/*.conf).
#
# An existing file is not overwritten — BUT only if that file is NOT one of
# the wallpapers/*.png we generate (see _wallpaper_is_ours).
# Otherwise, when switching from one profile to another, WALLPAPER_PATH always
# looks "already present" and no profile's wallpaper is ever applied again — the
# image first installed with profile A would forever be taken for a "protected
# user file" even after picking profile B. A file that was really put there by
# hand and matches none of ours is still preserved untouched.
#
# IMPORTANT — ORDERING: main() calls this step BEFORE run_hooks_step.
# hook_hyprpaper/hook_swww (modules/hypr.sh:_ensure_wallpaper) generate a generic
# gradient from the theme's three colors if the file is missing; if this step
# does not run EARLIER and fill WALLPAPER_PATH, _ensure_wallpaper leaves the
# generic gradient and the real image/pattern is never applied. Do not change
# the order.

# Does the existing WALLPAPER_PATH file match one of the wallpapers/*.png (any
# profile's image) by content? If so the file was placed automatically by the
# script, and overwriting it is safe.
_wallpaper_is_ours() {
    local existing="$1" size sum="" candidate
    # A pattern generated earlier (python/hyprsetup/wallpaper.py GENERATED_MARK).
    head -c 128 -- "$existing" 2>/dev/null | grep -aq 'souprland-pattern' && return 0
    have md5sum || return 1
    size=$(stat -c %s -- "$existing" 2>/dev/null) || return 1
    # Size first: only the candidates matching in size among the repo's ~75 MB are read.
    for candidate in "$SETUP_ROOT"/wallpapers/*.png; do
        [[ -f "$candidate" && "$(stat -c %s -- "$candidate")" == "$size" ]] || continue
        [[ -n "$sum" ]] || sum=$(md5sum < "$existing" | cut -d' ' -f1)
        [[ "$(md5sum < "$candidate" | cut -d' ' -f1)" == "$sum" ]] && return 0
    done
    return 1
}

wallpaper_step() {
    [[ "${SKIP_CONFIGS:-0}" == 1 ]] && return 0

    # WALLPAPER_PATH may start with a literal "~" (see lib/core.sh:expand_tilde);
    # every operation here must use the real file path.
    local wp
    wp=$(wallpaper_file)

    if [[ -n "${WALLPAPER_IMAGE:-}" ]]; then
        local src="$SETUP_ROOT/$WALLPAPER_IMAGE"
        # Wallhaven images are not in the repo (sources.json): downloaded, or else
        # the profile's old generated wallpaper (python/hyprsetup/wallhaven.py).
        if [[ ! -r "$src" && "$WALLPAPER_IMAGE" == wallpapers/wallhaven/* \
              && "${DRY_RUN:-0}" != 1 ]]; then
            src=$(PYTHONPATH="$SETUP_ROOT/python" python3 -c \
                'import sys; from pathlib import Path; from hyprsetup import wallhaven
p = wallhaven.ensure(Path(sys.argv[1]), sys.argv[2]); print(p or "")' \
                "$SETUP_ROOT" "$WALLPAPER_IMAGE" 2>/dev/null)
            [[ -n "$src" ]] || src="$SETUP_ROOT/$WALLPAPER_IMAGE"
        fi
        if [[ -r "$src" ]]; then
            if [[ -e "$wp" ]] && ! _wallpaper_is_ours "$wp"; then
                step "Wallpaper already exists (looks like your own image), keeping it: $wp"
                return 0
            fi
            step "Copying the wallpaper (pre-generated): $wp"
            if [[ "${DRY_RUN:-0}" == 1 ]]; then
                printf '%s  [dry-run]%s copy: %s -> %s\n' "$C_DIM" "$C_RESET" "$src" "$wp"
                return 0
            fi
            run mkdir -p "$(dirname "$wp")"
            if run cp "$src" "$wp"; then
                ok "Wallpaper ready: $wp"
            else
                warn "Could not copy the wallpaper (the install continues)."
            fi
            return 0
        fi
        warn "WALLPAPER_IMAGE not found: $src — falling back to WALLPAPER_STYLE."
    fi

    [[ -n "${WALLPAPER_STYLE:-}" ]] || return 0

    if [[ -e "$wp" ]] && ! _wallpaper_is_ours "$wp"; then
        step "Wallpaper already exists (looks like your own image), keeping it: $wp"
        return 0
    fi
    if ! have python3; then
        warn "No python3, could not generate the wallpaper."
        return 0
    fi

    step "Generating the wallpaper: $WALLPAPER_STYLE pattern · $THEME palette"
    if [[ "${DRY_RUN:-0}" == 1 ]]; then
        printf '%s  [dry-run]%s generate: %s\n' "$C_DIM" "$C_RESET" "$wp"
        return 0
    fi
    run mkdir -p "$(dirname "$wp")"
    if PYTHONPATH="$SETUP_ROOT/python" python3 -m hyprsetup wallpaper \
            --theme "$THEME" --style "$WALLPAPER_STYLE" \
            --colors "${CUSTOM_COLORS:-}" --out "$wp" >/dev/null; then
        ok "Wallpaper ready: $wp"
    else
        warn "Could not generate the wallpaper (the install continues)."
    fi
    return 0
}

services_step() {
    if [[ "$SKIP_PACKAGES" == 1 ]]; then return 0; fi
    info "Services"
    enable_component_services "${SELECTED[@]}"
    return 0
}

# If the install was done from inside a running Hyprland session, the new config
# only shows after a reload; let's not force the user to log out.
# Derives the variables of single-choice categories (TERMINAL, BAR, LAUNCHER,
# NOTIFIER, FILEMANAGER, WALLPAPER_DAEMON, LOGIN_MANAGER) from SELECTED: the first
# selected component in catalog order wins. It used to live in
# lib/select.sh; that file (TUI + profile + --only/--skip) was removed, and
# this is the only piece still needed.
selection_resolve_primaries() {
    local cat var id first
    while IFS= read -r cat; do
        var=$(catalog_category_var "$cat")
        [[ -z "$var" ]] && continue
        first=""
        while IFS= read -r id; do
            in_list "$id" "${SELECTED[@]}" || continue
            first="$id"
            break
        done < <(jq -r --arg c "$cat" '.categories[] | select(.id == $c) | .components[].id' "$CATALOG")
        if [[ -n "$first" ]]; then
            printf -v "$var" '%s' "$first"
            export "${var?}"
            debug "$var=$first"
        fi
    done < <(catalog_category_ids)
}

selection_summary() {
    local id cat last_cat="" title
    info "Components to install (${#SELECTED[@]})"
    for id in "${SELECTED[@]}"; do
        cat=$(catalog_category_of "$id")
        if [[ "$cat" != "$last_cat" ]]; then
            printf '  %s%s%s\n' "$C_BOLD" \
                "$(jq -r --arg c "$cat" '.categories[]|select(.id==$c)|.title' "$CATALOG")" \
                "$C_RESET"
            last_cat="$cat"
        fi
        title=$(catalog_title "$id")
        printf '    · %s %s(%s)%s\n' "$title" "$C_DIM" "$id" "$C_RESET"
    done
    echo
}

# Installs the settings app on the system.
#
# WHY: the MOD+I keybinding used to run the UI from the REPO PATH stored in
# ~/.cache/hyprsetup/setup_root. Deleting or moving the folder you downloaded
# the repo into destroyed the settings app — unacceptable for a system settings
# app. Now everything needed is copied under ~/.local and the repo folder can
# be deleted entirely.
install_app_step() {
    local share="$HOME/.local/share/hyprsetup"
    local bindir="$HOME/.local/bin"
    local desktop_dir="$HOME/.local/share/applications"

    local icon_dir="$HOME/.local/share/icons/hicolor/scalable/apps"

    step "Installing the settings app → $bindir/souprland"
    if [[ "${DRY_RUN:-0}" == 1 ]]; then
        printf '%s  [dry-run]%s copy: python/, templates/, config/, assets/ -> %s\n' \
            "$C_DIM" "$C_RESET" "$share"
        printf '%s  [dry-run]%s write: %s/souprland (+ hyprsetup link)\n' \
            "$C_DIM" "$C_RESET" "$bindir"
        printf '%s  [dry-run]%s write: %s/souprland.desktop\n' \
            "$C_DIM" "$C_RESET" "$desktop_dir"
        return 0
    fi

    run mkdir -p "$share" "$bindir" "$desktop_dir" "$icon_dir"
    # Clean the old copy: a deleted template must not linger.
    run rm -rf "$share/python" "$share/templates" "$share/config" \
        "$share/presets" "$share/wallpapers" "$share/assets"
    run cp -a "$SETUP_ROOT/python"     "$share/python"
    run cp -a "$SETUP_ROOT/templates"  "$share/templates"
    run cp -a "$SETUP_ROOT/config"     "$share/config"
    run cp -a "$SETUP_ROOT/presets"    "$share/presets"
    run cp -a "$SETUP_ROOT/wallpapers" "$share/wallpapers"
    run cp -a "$SETUP_ROOT/assets"     "$share/assets"
    run install -m 644 "$SETUP_ROOT/assets/souprland.svg" "$icon_dir/souprland.svg"
    # Location of the source repo: the settings app refreshes the copy from here
    # with "Update", and an "apply" made from the repo syncs the copy too (selfupdate.py).
    printf '%s\n' "$SETUP_ROOT" >"$share/.source"

    # A real file left over from an old install: it is replaced with a link below.
    [[ -L "$bindir/hyprsetup" ]] || run rm -f "$bindir/hyprsetup"

    cat >"$bindir/souprland" <<EOF
#!/usr/bin/env bash
# souprland — Hyprland settings app (installed by install.sh)
#
# Called without arguments it opens the settings app (the "gui" subcommand is the
# default and flags like --quick go to it). If called with a known subcommand
# name, that is run: this is how the MOD+/ keybinding can open the keybinding
# card from the installed copy (hypr/scripts/keybind-help.sh).
export PYTHONPATH="$share/python\${PYTHONPATH:+:\$PYTHONPATH}"

case "\${1:-}" in
    cheatsheet|switcher)
        cmd="\$1"; shift
        exec python3 -m hyprsetup "\$cmd" \
            --root "$share" \
            --catalog "$share/config/components.json" "\$@"
        ;;
    self-update)
        # Refresh the installed copy from the source repo (--pull: git pull first).
        shift
        exec python3 -m hyprsetup self-update --root "$share" "\$@"
        ;;
    share|theme-schedule)
        # Export the desktop to a file / import from a file; day/night theme.
        cmd="\$1"; shift
        exec python3 -m hyprsetup "\$cmd" --root "$share" "\$@"
        ;;
    wallcolors)
        # Wallpaper colors: wallpaper.sh calls "follow" on every change.
        shift
        exec python3 -m hyprsetup wallcolors "\$@" --root "$share"
        ;;
esac

exec python3 -m hyprsetup gui \
    --root "$share" \
    --catalog "$share/config/components.json" \
    --templates "$share/templates" "\$@"
EOF
    run chmod 755 "$bindir/souprland"
    # Old name: installed profiles' MOD+I scripts (hypr/scripts/settings.sh)
    # and muscle memory still call "hyprsetup".
    run ln -sfn souprland "$bindir/hyprsetup"

    # Launcher entry (souprland.desktop; also removes the old hyprsetup.desktop):
    # the settings app checks it with the same module on every start.
    PYTHONPATH="$share/python" run python3 -c \
        'import sys; from pathlib import Path; from hyprsetup import desktop_entry; desktop_entry.ensure(Path(sys.argv[1]))' \
        "$SETUP_ROOT" || warn "Could not write the launcher entry."
    have gtk-update-icon-cache && \
        run gtk-update-icon-cache -qtf "$HOME/.local/share/icons/hicolor" || true

    # If ~/.local/bin is not in PATH, the user cannot find "souprland" when typing it.
    case ":$PATH:" in
        *":$bindir:"*) ;;
        *) warn "$bindir is not in your PATH — the 'souprland' command may not be found."
           warn "  Add to your shell:  export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
    esac
    ok "Settings app installed — open it with MOD+I or from the app menu"
}

# The default CURSOR_THEME (Bibata) comes from the cursor-theme component, which
# is not in DEFAULT_COMPONENTS. Pointing GTK/Hyprland at a missing theme leaves
# the cursor invisible or inconsistent, so fall back to Adwaita (always present
# with gtk) — the same idea as the GTK/icon theme derivation in render.py.
cursor_theme_fallback() {
    local c="${CURSOR_THEME:-}" d
    [[ -n "$c" ]] || return 0
    for d in "/usr/share/icons/$c" "$HOME/.icons/$c" "$HOME/.local/share/icons/$c" \
             "$SETUP_ROOT/assets/cursors/$c"; do
        [[ -d "$d" ]] && return 0
    done
    # In --dry-run the package step installed nothing; the theme may arrive later.
    if [[ "${DRY_RUN:-0}" == 1 ]] && in_list cursor-theme "${SELECTED[@]}"; then
        return 0
    fi
    warn "Cursor theme '$c' is not installed — using Adwaita instead."
    CURSOR_THEME="Adwaita"
}

summary_step() {
    echo
    info "Summary"
    printf '  Components        : %s\n' "${#SELECTED[@]}"
    printf '  Packages installed: %s\n' "${#INSTALLED_PKGS[@]}"
    printf '  Already installed : %s\n' "${#SKIPPED_PKGS[@]}"
    printf '  Theme             : %s\n' "$THEME"
    printf '  Terminal/Bar/Menu : %s / %s / %s\n' "${TERMINAL:--}" "${BAR:--}" "${LAUNCHER:--}"
    printf '  Log               : %s\n' "$LOG_FILE"
    # Note: the "condition && printf" form ends the list with 1 when the condition
    # is false and kills the install at the last step under set -e; hence the explicit if.
    if [[ -d "$BACKUP_DIR" ]]; then
        printf '  Backups           : %s\n' "$BACKUP_DIR"
    fi

    if ((${#EXCLUDED_PKGS[@]})); then
        printf '  Excluded (PKG_SKIP): %s\n' "${#EXCLUDED_PKGS[@]}"
    fi
    if ((${#NOT_COMPILED_PKGS[@]})); then
        printf '  Not built         : %s\n' "${#NOT_COMPILED_PKGS[@]}"
    fi
    if ((${#NOT_COMPILED_PKGS[@]})); then
        echo
        warn "Packages not built (${#NOT_COMPILED_PKGS[@]}): ${NOT_COMPILED_PKGS[*]}"
        warn "These were skipped because of COMPILE=${COMPILE}; these components may work incompletely."
        warn "For signed binaries: CHAOTIC_AUR=true · to build: --compile always"
    fi
    if ((${#EXCLUDED_PKGS[@]})); then
        echo
        warn "Packages excluded with PKG_SKIP (${#EXCLUDED_PKGS[@]}): ${EXCLUDED_PKGS[*]}"
    fi
    if ((${#FAILED_PKGS[@]})); then
        echo
        warn "Packages that could not be installed (${#FAILED_PKGS[@]}): ${FAILED_PKGS[*]}"
        warn "You can try them manually: ${AUR_HELPER:-pacman} -S <package>"
    fi

    cat <<EOF

${C_BOLD}Next steps${C_RESET}
  1. Log out and pick the ${C_CYAN}Hyprland${C_RESET} session on the login screen.
     (If you did not install a login manager, from a TTY: ${C_CYAN}Hyprland${C_RESET})
  2. To see the keybindings: ${C_CYAN}${MOD_KEY} + F1${C_RESET}
  3. ${C_BOLD}For settings:${C_RESET} ${C_CYAN}${MOD_KEY} + I${C_RESET}  (or ${C_CYAN}souprland${C_RESET})
     Theme, gaps, bar, keybindings, displays — all change from there and are
     ${C_BOLD}applied instantly${C_RESET}. You do not need to run this script again.
     Your settings: ${C_CYAN}${SETTINGS_FILE}${C_RESET}
  4. You can put your wallpaper here: ${C_CYAN}${WALLPAPER_PATH}${C_RESET}

  Note: the settings app does not install packages. An option that is not installed
  (e.g. another status bar) appears dimmed in the UI with a ${C_CYAN}pacman${C_RESET} command next to it.
EOF
}

# ---------------------------------------------------------------- update ----
# Has Souprland been installed before: the settings app's copy and the settings file.
souprland_installed() {
    [[ -d "$APP_SHARE/python/hyprsetup" && -f "$SETTINGS_FILE" ]]
}

# Replaces this folder with the new version and restarts install.sh from there.
# If there is no new version or it cannot be downloaded it returns silently: the
# update continues with the version in this folder.
update_fetch_source() {
    if [[ "$NO_FETCH" == 1 ]]; then
        return 0
    fi
    if [[ "${DRY_RUN:-0}" == 1 ]]; then
        printf '%s  [dry-run]%s checking for a new version (git pull / GitHub)\n' "$C_DIM" "$C_RESET"
        return 0
    fi

    # Git clone: pull new remote commits.
    if [[ -d "$SETUP_ROOT/.git" ]] && have git; then
        step "Checking for a new version (git)"
        local before after
        before=$(git -C "$SETUP_ROOT" rev-parse HEAD 2>/dev/null || true)
        if ! git -C "$SETUP_ROOT" pull --ff-only --quiet; then
            warn "git pull failed (local changes or network) — continuing with this version."
            return 0
        fi
        after=$(git -C "$SETUP_ROOT" rev-parse HEAD 2>/dev/null || true)
        if [[ "$before" == "$after" ]]; then
            ok "The repo is already up to date"
            return 0
        fi
        ok "New version pulled (${before:0:8} → ${after:0:8}); restarting the installer"
        exec bash "$SETUP_ROOT/install.sh" "${ORIG_ARGS[@]}" --update --no-fetch
    fi

    if [[ -z "$SOUPRLAND_REPO" ]]; then
        step "No download URL (SOUPRLAND_REPO) set — installing the version in this folder"
        return 0
    fi
    if ! have curl || ! have tar; then
        warn "No curl/tar — could not download a new version, installing the version in this folder."
        return 0
    fi

    step "Checking for a new version: $SOUPRLAND_REPO ($SOUPRLAND_BRANCH)"
    rm -rf -- "$SOUPRLAND_SRC.old" "$SOUPRLAND_SRC.new"
    mkdir -p -- "$SOUPRLAND_SRC.new"
    local url="${SOUPRLAND_REPO%/}/archive/refs/heads/$SOUPRLAND_BRANCH.tar.gz"
    if ! curl -fsSL --connect-timeout 15 "$url" \
            | tar -xz -C "$SOUPRLAND_SRC.new" --strip-components=1 \
       || [[ ! -f "$SOUPRLAND_SRC.new/install.sh" ]]; then
        warn "Could not download ($url) — installing the version in this folder."
        rm -rf -- "$SOUPRLAND_SRC.new"
        return 0
    fi
    if diff -rq --exclude=.git "$SOUPRLAND_SRC.new" "$SETUP_ROOT" >/dev/null 2>&1; then
        ok "This folder is already the latest version"
        rm -rf -- "$SOUPRLAND_SRC.new"
        return 0
    fi
    if ! confirm "A newer version is available on GitHub. Download and install it?" y; then
        rm -rf -- "$SOUPRLAND_SRC.new"
        return 0
    fi
    # The running script may be inside $SOUPRLAND_SRC: it is moved aside first,
    # bash keeps reading from the open file, and exec switches to the new one right away.
    [[ -e "$SOUPRLAND_SRC" ]] && mv -- "$SOUPRLAND_SRC" "$SOUPRLAND_SRC.old"
    mv -- "$SOUPRLAND_SRC.new" "$SOUPRLAND_SRC"
    ok "New version downloaded → $SOUPRLAND_SRC"
    exec bash "$SOUPRLAND_SRC/install.sh" "${ORIG_ARGS[@]}" --update --no-fetch
}

# Updates the installed Souprland: the user's settings are kept.
update_run() {
    banner
    info "Souprland is already installed — update mode (your settings are kept)"
    step "To install from scratch: ./install.sh --reinstall"
    if [[ "$DRY_RUN" == 1 ]]; then
        warn "DRY-RUN mode: no changes will be made."
    fi
    rm -rf -- "$SOUPRLAND_SRC.old" 2>/dev/null || true

    update_fetch_source

    if [[ "$DRY_RUN" != 1 ]] && ! confirm "Start the update?" y; then
        warn "Cancelled by the user."
        exit 0
    fi

    # The user's settings are read (PKG_SKIP, COMPILE, CHAOTIC_AUR…);
    # they are not overridden by the defaults.
    config_load "$SETTINGS_FILE"
    [[ -n "${CLI_COMPILE:-}" ]] && COMPILE="$CLI_COMPILE"
    [[ -n "${CLI_PKG_SKIP:-}" ]] && PKG_SKIP="${PKG_SKIP:+$PKG_SKIP,}$CLI_PKG_SKIP"

    preflight_run_all

    # Packages added to the default list in the new version are installed;
    # installed ones are skipped with --needed, so usually nothing is downloaded.
    SELECTED=("${DEFAULT_COMPONENTS[@]}")
    [[ "${HAS_NVIDIA:-0}" == 1 ]] && SELECTED+=("nvidia")
    install_packages_step

    # The settings app's copy is refreshed (python/, templates, profiles…).
    install_app_step

    # The new templates are regenerated with the user's OWN settings — the same
    # path as the settings app's "apply" (hyprsetup reapply).
    if [[ "$DRY_RUN" != 1 ]]; then
        step "Reapplying your settings with the new version"
        if PYTHONPATH="$APP_SHARE/python" python3 -m hyprsetup reapply \
                --root "$APP_SHARE" 2>&1 | tee -a "$LOG_FILE"; then
            :
        else
            warn "Reapplying failed — opening the settings app and changing a setting also reapplies."
        fi
    fi

    if ((${#FAILED_PKGS[@]})); then
        warn "Packages that could not be installed (${#FAILED_PKGS[@]}): ${FAILED_PKGS[*]}"
    fi
    ok "Update complete. No need to restart Hyprland; bar/keybinding changes take effect immediately."
}

# --------------------------------------------------------------- main -------
main() {
    parse_args "$@"

    CATALOG="$SETUP_ROOT/config/components.json"
    if have jq; then catalog_validate; fi

    # The health check changes nothing; it also skips the preflight checks.
    if [[ -n "${DO_DOCTOR:-}" ]]; then
        doctor_status=0
        doctor_run || doctor_status=$?
        exit "$doctor_status"
    fi

    # Boot animation only: the settings app does not run the root step itself,
    # it calls this option in a terminal. It does not touch the desktop, the
    # package list or the settings file; only hook_plymouth and (if needed) a
    # one-time initramfs generation.
    if [[ -n "${CLI_PLYMOUTH:-}" ]]; then
        plymouth_only_step
        exit $?
    fi

    # If installed before, update instead of installing from scratch: running
    # it again used to overwrite settings.conf with the defaults.
    if [[ "$RUN_MODE" == auto ]]; then
        if souprland_installed; then RUN_MODE=update; else RUN_MODE=install; fi
    fi
    if [[ "$RUN_MODE" == update ]]; then
        if ! souprland_installed; then
            err "Souprland is not installed; install it first with ./install.sh."
            exit 1
        fi
        update_run
        exit 0
    fi

    banner
    if [[ "$DRY_RUN" == 1 ]]; then
        warn "DRY-RUN mode: no changes will be made."
    fi

    # All settings come from the defaults in lib/config.sh. The install no
    # longer asks for any setting: look/behavior are changed AFTER the install
    # from the settings app and applied instantly there. CONFIG_FILE only
    # remains for those who want to script the install (-c).
    config_load "$CONFIG_FILE"
    [[ -n "${CLI_COMPILE:-}" ]] && COMPILE="$CLI_COMPILE"
    # --skip-pkg does not override PKG_SKIP from the settings file, it ADDS to it:
    # both say "I do not want this package", one must not silently cancel the other.
    [[ -n "${CLI_PKG_SKIP:-}" ]] && PKG_SKIP="${PKG_SKIP:+$PKG_SKIP,}$CLI_PKG_SKIP"
    # The install overwrites the existing config; a copy of every file is
    # taken under ~/.config/hyprsetup-backups/ (see lib/core.sh:backup_path).
    OVERWRITE_CONFIGS=always
    config_validate

    preflight_run_all
    catalog_validate
    # If a tool like nwg-displays generates monitors.conf itself, the setting is
    # left to it. AFTER preflight: the decision looks at HYPR_LANG_RESOLVED.
    config_adopt_foreign_monitors

    # The component list is fixed (DEFAULT_COMPONENTS). The only exception is
    # the GPU driver: since installing the wrong driver can black out the
    # screen, it is decided by the hardware, not asked from the user.
    SELECTED=("${DEFAULT_COMPONENTS[@]}")
    if [[ "${HAS_NVIDIA:-0}" == 1 ]]; then
        info "NVIDIA GPU found — adding the nvidia component"
        SELECTED+=("nvidia")
    fi
    # The single-choice categories' variables (TERMINAL, BAR, LAUNCHER…)
    # are derived from SELECTED; render_export_vars expects them ready.
    selection_resolve_primaries
    selection_summary

    # This is the only question. In --dry-run nothing changes, so it is not
    # asked either: keeping someone who said "show me what it does" waiting on a question is pointless.
    if [[ "$DRY_RUN" != 1 ]] && ! confirm "Start the installation?" y; then
        warn "Cancelled by the user."
        exit 0
    fi

    install_packages_step
    cursor_theme_fallback
    wallpaper_step
    run_hooks_step
    # The nvidia and plymouth hooks may touch mkinitcpio.conf separately; if
    # each did its own generation, the initramfs would be generated twice (each
    # takes minutes). Hooks only mark it, and generation is done once here
    # — see lib/core.sh:mark_initramfs_dirty.
    regenerate_initramfs_if_needed || true
    color_scheme_step
    render_run
    # AFTER render_run: the systemd unit files are only written at this point;
    # called earlier, systemctl could never see the unit.
    enable_wallpaper_rotation
    # The Firefox theme also depends on render: the source userChrome.css is only
    # generated here, and copying it into the profile dir can only happen after that.
    install_firefox_theme
    # Default apps: mimeapps.list / xdg-terminals.list were written in render_run;
    # here we only refresh the desktop's cache and align the xdg-settings
    # record (see modules/desktop.sh).
    apply_default_apps
    apply_default_browser
    services_step
    # Install the settings app on the system: MOD+I keeps working even if the repo folder is deleted.
    install_app_step

    # In --dry-run no real file changes; overwriting the real settings file here
    # must follow the same rule — otherwise "trying it" would save a config
    # that was never applied as if it were "current".
    if [[ "${DRY_RUN:-0}" != 1 ]]; then
        config_save "$SETTINGS_FILE"
        # Prune old backups: the first (pre-hyprsetup) backup always stays, then
        # the newest 5 install + 10 settings app backups (see backups.py).
        PYTHONPATH="$SETUP_ROOT/python" python3 -m hyprsetup backups prune \
            >>"$LOG_FILE" 2>&1 || debug "backup pruning failed"
    fi
    summary_step
    ok "Installation complete"
}

main "$@"
