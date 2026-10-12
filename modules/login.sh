# shellcheck shell=bash
# modules/login.sh — login managers
#
# Caution: these steps affect graphical login. Since a wrong config can lock you
# out of the desktop, the defaults are deliberately kept conservative.

# Find the active display manager via /etc/systemd/system/display-manager.service.
_current_dm() {
    local link="/etc/systemd/system/display-manager.service"
    [[ -L "$link" ]] || return 0
    basename "$(readlink -f "$link")"
}

_warn_existing_dm() {
    local new="$1" current
    current=$(_current_dm)
    [[ -z "$current" || "$current" == "$new" ]] && return 0
    warn "A login manager is already active: $current"
    warn "If $new is enabled, $current will be disabled."
    if ! confirm "Continue?" n; then
        SKIP_SERVICES+=("$new")
        warn "$new will not be enabled."
    fi
}

# The config of login managers like ly/greetd/sddm lives under /etc, not
# ~/.config; it does not go through the normal template pipeline (render.sh →
# ~/.config). So we fetch the raw theme (COL_*) directly from Python and write
# it with sudo inside the hook — the same pattern as in _ensure_wallpaper.
# Output: "BG FG ACCENT ACCENT2 RED GREEN YELLOW CYAN" (raw hex, space-separated).
_login_theme_hex() {
    local out
    out=$(PYTHONPATH="$SETUP_ROOT/python" \
        HYPRSETUP_THEME="${THEME:-}" HYPRSETUP_CUSTOM_COLORS="${CUSTOM_COLORS:-}" \
        HYPRSETUP_WALLPAPER="$(wallpaper_file)" \
        HYPRSETUP_SCHEME="${COLOR_SCHEME:-dark}" \
        HYPRSETUP_BACKEND="${PALETTE_BACKEND:-auto}" \
        python3 -c "
import os
from hyprsetup import themes

theme = os.environ.get('HYPRSETUP_THEME', '')
overrides = os.environ.get('HYPRSETUP_CUSTOM_COLORS', '')

# With THEME='auto' the palette is extracted from the wallpaper (see palette.py).
# Without this branch the login screen would stay on the default theme's colors
# while the desktop is colored from the wallpaper — the two would not match.
if theme.strip().lower() == 'auto':
    from hyprsetup import palette
    extracted = palette.extract(
        os.environ.get('HYPRSETUP_WALLPAPER', ''),
        dark=(os.environ.get('HYPRSETUP_SCHEME', 'dark') != 'light'),
        backend=os.environ.get('HYPRSETUP_BACKEND', 'auto') or 'auto')
    if extracted:
        extracted.update(themes.parse_overrides(overrides))
        c = themes.derive(themes.DEFAULT, extracted)
    else:
        c = themes.derive(themes.DEFAULT, overrides)
else:
    c = themes.derive(theme, overrides)

print(c['COL_BG'], c['COL_FG'], c['COL_ACCENT'], c['COL_ACCENT2'], c['COL_RED'], c['COL_GREEN'], c['COL_YELLOW'], c['COL_CYAN'])
" 2>/dev/null) || out="1e1e2e cdd6f4 89b4fa cba6f7 f38ba8 a6e3a1 f9e2af 94e2d5"
    printf '%s\n' "$out"
}

# Copies the wallpaper system-wide for the login screen background.
#
# The SDDM greeter runs as the 'sddm' user and CANNOT READ under
# /home/<user> (permissions, and an encrypted home dir on some setups). Writing
# the wallpaper directly into the theme config therefore silently gives a black
# screen. The image must be copied to a world-readable path.
#
# Prints the copied path to stdout; prints nothing on failure.
_stage_login_background() {
    local dest_dir="$1" src
    src=$(wallpaper_file)
    [[ -r "$src" ]] || return 0

    local dest="$dest_dir/hyprsetup-background.${src##*.}"
    run sudo install -Dm644 "$src" "$dest" || return 0
    printf '%s' "$dest"
}

# SDDM has no color customization of its own (it is QML-based); so we go with
# sddm-astronaut-theme (aur, see components.json) — a popular theme that accepts
# its own theme.conf file, with ~25 color fields in plain "Key=#hex" form. We
# link the Themes/hyprsetup.conf we generate to the ConfigFile field of
# metadata.desktop.
#
# Known limitation: when this AUR package updates it may overwrite metadata.desktop
# with its own default (an issue documented upstream) — in that case
# re-applying with ./install.sh --reapply is enough.
_apply_sddm_theme() {
    local theme_dir="/usr/share/sddm/themes/sddm-astronaut-theme"
    [[ -d "$theme_dir" ]] || { warn "sddm-astronaut-theme is not installed — SDDM will keep the default (unthemed) look."; return 0; }
    confirm "Paint the SDDM login screen with your theme's colors? (sddm-astronaut-theme)" y || return 0

    local bg fg accent accent2 red green
    # The last two fields (yellow, cyan) are not used in the SDDM theme.
    read -r bg fg accent accent2 red green _ _ <<<"$(_login_theme_hex)"

    # Let the login screen show the same wallpaper as the desktop. The image is
    # copied system-wide (the greeter cannot read the home dir — see
    # _stage_login_background). If it cannot be copied, the background falls back to the plain theme.
    local bg_line="" background=""
    if [[ "${SDDM_BACKGROUND:-wallpaper}" == "wallpaper" ]]; then
        background=$(_stage_login_background "$theme_dir/Backgrounds")
    fi
    if [[ -n "$background" ]]; then
        # Relative path: SDDM resolves the theme file relative to the theme dir.
        bg_line="Background=\"Backgrounds/$(basename "$background")\"
ScreenWidth=\"\"
PartialBlur=\"true\"
FullBlur=\"false\"
BlurRadius=\"25\""
        step "Login screen background: wallpaper"
    else
        bg_line="Background=\"\"
FullBlur=\"false\"
PartialBlur=\"false\""
    fi

    step "Writing the SDDM theme: $theme_dir/Themes/hyprsetup.conf"
    backup_path "$theme_dir/Themes/hyprsetup.conf"
    run sudo install -Dm644 /dev/stdin "$theme_dir/Themes/hyprsetup.conf" <<EOF
[General]
$bg_line
HeaderTextColor="#$fg"
DateTextColor="#$fg"
TimeTextColor="#$fg"
FormBackgroundColor="#$bg"
BackgroundColor="#$bg"
DimBackgroundColor="#$bg"
LoginFieldBackgroundColor="#$bg"
PasswordFieldBackgroundColor="#$bg"
LoginFieldTextColor="#$fg"
PasswordFieldTextColor="#$fg"
UserIconColor="#$fg"
PasswordIconColor="#$fg"
PlaceholderTextColor="#$fg"
WarningColor="#$red"
LoginButtonTextColor="#$bg"
LoginButtonBackgroundColor="#$accent"
SystemButtonsIconsColor="#$fg"
SessionButtonTextColor="#$fg"
VirtualKeyboardButtonTextColor="#$fg"
DropdownTextColor="#$fg"
DropdownSelectedBackgroundColor="#$accent"
DropdownBackgroundColor="#$bg"
HighlightTextColor="#$bg"
HighlightBackgroundColor="#$accent"
HighlightBorderColor="#$accent"
HoverUserIconColor="#$accent"
HoverPasswordIconColor="#$accent"
HoverSystemButtonsIconsColor="#$accent"
HoverSessionButtonTextColor="#$accent"
HoverVirtualKeyboardButtonTextColor="#$accent"
EOF

    backup_path "$theme_dir/metadata.desktop"
    run sudo sed -i 's|^ConfigFile=.*|ConfigFile=Themes/hyprsetup.conf|' "$theme_dir/metadata.desktop"

    backup_path /etc/sddm.conf.d/20-theme.conf
    run sudo install -Dm644 /dev/stdin /etc/sddm.conf.d/20-theme.conf <<'EOF'
[Theme]
Current=sddm-astronaut-theme
EOF
    ok "SDDM theme applied: sddm-astronaut-theme (hyprsetup.conf)"
}

hook_sddm() {
    root_ops_allowed || { debug "SDDM theme skipped (--configs-only) — needs sudo"; return 0; }
    _warn_existing_dm "sddm.service"
    system_snapshot "login manager (SDDM)"
    # If the theme was applied from the settings app's Login Screen page (community
    # theme + edits, python/hyprsetup/login.py), --reapply must not turn it
    # back into astronaut.
    if grep -qs '"applied"' "${XDG_CONFIG_HOME:-$HOME/.config}/hyprsetup/login.json"; then
        step "The SDDM theme is managed from the Login Screen page — left untouched"
    else
        _apply_sddm_theme
    fi

    # Running SDDM on Wayland needs a separate compositor (kwin_wayland/weston).
    # If it is not installed SDDM never starts — so we only set it up if one is
    # available and the user explicitly asks.
    local compositor=""
    have kwin_wayland && compositor="kwin_wayland --no-lockscreen --no-global-shortcuts --locale1"
    [[ -z "$compositor" ]] && have weston && compositor="weston --shell=kiosk"
    [[ -z "$compositor" ]] && { step "SDDM left in the default (X11) mode"; return 0; }

    confirm "Run SDDM in Wayland mode? (compositor: ${compositor%% *})" n || return 0
    backup_path /etc/sddm.conf.d/10-wayland.conf
    run sudo install -Dm644 /dev/stdin /etc/sddm.conf.d/10-wayland.conf <<EOF
[General]
DisplayServer=wayland
GreeterEnvironment=QT_WAYLAND_SHELL_INTEGRATION=layer-shell

[Wayland]
CompositorCommand=$compositor
EOF
}

hook_ly() {
    root_ops_allowed || { debug "ly colors skipped (--configs-only) — needs sudo"; return 0; }
    _warn_existing_dm "ly.service"
    system_snapshot "login manager (ly)"

    # Colors are generated from raw hex in ly's own 0xSSRRGGBB (style+RGB)
    # format — settings left out stay at ly's own defaults (Config.zig already
    # has a default for every field, so a partial file is not a problem).
    local bg fg accent accent2 red green
    # The last two fields (yellow, cyan) are not used in the ly colors.
    read -r bg fg accent accent2 red green _ _ <<<"$(_login_theme_hex)"

    step "Writing ly login screen colors: /etc/ly/config.ini"
    backup_path /etc/ly/config.ini
    run sudo install -Dm644 /dev/stdin /etc/ly/config.ini <<EOF
bg = 0x00$bg
fg = 0x00$fg
border_fg = 0x00$accent
error_bg = 0x00$bg
error_fg = 0x01$red
full_color = true
EOF
}

hook_greetd() {
    root_ops_allowed || { debug "greetd config skipped (--configs-only) — needs sudo"; return 0; }
    _warn_existing_dm "greetd.service"
    system_snapshot "login manager (greetd)"
    have tuigreet || { warn "tuigreet could not be installed — skipping the greetd config."; return 0; }

    # tuigreet --theme expects a spec of the form "component=color;..."; the color
    # value goes to ratatui's Color::from_str, which accepts "#rrggbb" hex directly
    # (source: tuigreet src/ui/common/style.rs). Since the spec has no spaces it
    # needs no extra quoting on the command line in config.toml.
    local bg fg accent accent2 red green theme_spec
    # The last two fields (yellow, cyan) are not used in the greetd theme.
    read -r bg fg accent accent2 red green _ _ <<<"$(_login_theme_hex)"
    theme_spec="container=#$bg;text=#$fg;border=#$accent;title=#$accent2;prompt=#$accent;input=#$fg;action=#$green"

    backup_path /etc/greetd/config.toml
    step "Writing the greetd config (tuigreet, themed)"
    run sudo install -Dm644 /dev/stdin /etc/greetd/config.toml <<EOF
[terminal]
vt = 1

[default_session]
command = "tuigreet --time --remember --remember-session --theme $theme_spec --cmd Hyprland"
user = "greeter"
EOF
    ok "greetd configured (autologin off)"
}
