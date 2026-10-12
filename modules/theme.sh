# shellcheck shell=bash
# modules/theme.sh — GTK/Qt theme, cursor and font settings

hook_gtk_theme() {
    # GTK3/GTK4 settings via gsettings (no XSettings on Wayland).
    # The same values as the generated ~/.config/gtk-3.0/settings.ini are written;
    # if the user did not set them in settings.conf they are derived from the
    # components (the same rule exists in python/hyprsetup/render.py).
    have gsettings || { warn "no gsettings, the GTK theme must be set manually."; return 0; }
    local gtk_theme="${GTK_THEME_NAME:-}" icon_theme="${ICON_THEME_NAME:-}"
    # The light/dark variant no longer comes from the theme's own colors but from
    # the independent COLOR_SCHEME setting — the same rule exists in the
    # GTK_THEME_NAME/ICON_THEME_NAME derivation in python/hyprsetup/render.py. So
    # the user can force "light" even with a dark theme selected, or vice versa.
    local light=0
    [[ "${COLOR_SCHEME:-dark}" == light ]] && light=1
    # The GTK theme is tied directly to COLOR_SCHEME: Adwaita-dark if dark,
    # otherwise Adwaita — so there is never a risk of pointing at an uninstalled
    # theme (e.g. catppuccin-gtk-theme-mocha) and GTK silently falling back to the
    # light default. The "gtk-theme" component only installs nwg-look (and the
    # Catppuccin GTK packages you can pick manually if you like); the automatic
    # choice does not depend on them — it can be overridden with GTK_THEME_NAME.
    # IMPORTANT: whether the Adwaita/Adwaita-dark names REALLY map to something
    # (i.e. whether GTK can find these names and apply the dark/light CSS)
    # depends on the gnome-themes-extra package (always installed with
    # core/hyprland, see config/components.json) — without it Arch's own gtk3
    # finds no real theme folder for either "Adwaita" or "Adwaita-dark"; both
    # silently fall back to GTK's bare/unstyled (seemingly always LIGHT) default —
    # even with COLOR_SCHEME=dark and prefer-dark-theme=1 set correctly, native
    # windows (e.g. nwg-look, the Electron menu bar) stay white. Verified on a
    # live system.
    if [[ -z "$gtk_theme" ]]; then
        ((light)) && gtk_theme="Adwaita" || gtk_theme="Adwaita-dark"
    fi
    if [[ -z "$icon_theme" ]]; then
        if in_list icon-theme "${SELECTED[@]}"; then
            ((light)) && icon_theme="Papirus-Light" || icon_theme="Papirus-Dark"
        else
            icon_theme="Adwaita"
        fi
    fi
    local schema="org.gnome.desktop.interface"
    step "Setting the GTK theme: $gtk_theme · icons: $icon_theme"
    run gsettings set "$schema" gtk-theme        "$gtk_theme"            || true
    run gsettings set "$schema" icon-theme       "$icon_theme"           || true
    run gsettings set "$schema" cursor-theme     "${CURSOR_THEME}"       || true
    run gsettings set "$schema" cursor-size      "${CURSOR_SIZE}"        || true
    run gsettings set "$schema" font-name        "${FONT_FAMILY} ${FONT_SIZE}" || true
}

# theme_apply_color_scheme — applies the org.gnome.desktop.interface
# color-scheme key, which decides whether GTK4/libadwaita apps open in dark
# or light mode, according to COLOR_SCHEME.
#
# Unlike hook_gtk_theme it does NOT depend on the component selection — it is
# called unconditionally from install.sh main() (see color_scheme_step). If it
# only ran when the "gtk-theme" component was selected, profiles without that
# component (e.g. minimal) would never write this key, and GTK4/libadwaita apps
# (AdwStyleManager reads the color from here, not from GTK3's
# gtk-application-prefer-dark-theme) would stay on the session default — usually light.
theme_apply_color_scheme() {
    have gsettings || { warn "no gsettings, the system color (dark/light) must be set manually."; return 0; }
    local scheme="prefer-dark"
    [[ "${COLOR_SCHEME:-dark}" == light ]] && scheme="prefer-light"
    step "System color: $([[ "$scheme" == prefer-dark ]] && echo "Dark" || echo "Light")"
    run gsettings set org.gnome.desktop.interface color-scheme "$scheme" || true
}

hook_qt_theme() {
    # Qt apps need an environment variable to use qt5ct/qt6ct; the env line
    # in hyprland.conf provides it. Only inform here.
    step "The Qt theme will be managed through qt5ct/qt6ct (QT_QPA_PLATFORMTHEME=qt6ct)"
    _restart_open_kde_qt_apps
}

# The kdeglobals/qt6ct color scheme is regenerated on every render; since we do
# not send KDE's live theme refresh DBus signal (KGlobalSettings), KDE/Qt apps
# that are already open never see the new colors — only a restarted instance
# reads the updated file. So the user is not expected to close and reopen them
# manually, they are automatically closed and reopened here (in the same,
# argument-less form) — restart_daemons_step (install.sh) does the same for
# waybar/mako/hyprpaper, for consistency. It runs even if FILEMANAGER=dolphin
# is not selected (even if it is merely installed) — it is called from
# hook_qt_theme (if the qt-theme component is selected) and hook_dolphin; a flag
# limits it to once if both trigger in one install run.
#
# All three are KDE Frameworks apps: they fully use the kdeglobals colors (and
# the Breeze style) only when QT_QPA_PLATFORMTHEME=kde — even if the rest of the
# desktop uses qt6ct/qt5ct (same reasoning as config/components.json →
# dolphin.exec). If they are restarted here without that same override, they
# show the old/default palette instead of the current colors.
_QT_KDE_APPS_RESTARTED=0
_restart_open_kde_qt_apps() {
    ((_QT_KDE_APPS_RESTARTED)) && return 0
    _QT_KDE_APPS_RESTARTED=1
    local app running=()
    for app in dolphin ark gwenview; do
        pgrep -x "$app" >/dev/null 2>&1 && running+=("$app")
    done
    ((${#running[@]})) || return 0
    step "Restarting open KDE/Qt apps (${running[*]}) — they will pick up the current colors"
    for app in "${running[@]}"; do
        run pkill -x "$app" || true
    done
    sleep 0.3
    for app in "${running[@]}"; do
        run env QT_QPA_PLATFORMTHEME=kde setsid -f "$app" >/dev/null 2>&1 || true
    done
}

# Cursor themes bundled with the repo (assets/cursors/<name>, e.g.
# Gozcu-Cursors — generated by tools/gozcu-cursors.py) do not come in a package;
# if selected they are copied to ~/.local/share/icons. Called even when the
# "cursor-theme" component is not selected (see install.sh:color_scheme_step),
# otherwise settings.ini and HYPRCURSOR_THEME would point at a nonexistent theme.
theme_install_bundled_cursor() {
    local src="$SETUP_ROOT/assets/cursors/${CURSOR_THEME:-}"
    local dst="$HOME/.local/share/icons/${CURSOR_THEME:-}"
    [[ -n "${CURSOR_THEME:-}" && -d "$src" ]] || return 0
    step "Installing the bundled cursor theme: $CURSOR_THEME"
    run mkdir -p "$HOME/.local/share/icons"
    run rm -rf "$dst"
    run cp -a "$src" "$dst"
}

hook_cursor_theme() {
    local dir="$HOME/.icons/default"
    theme_install_bundled_cursor
    step "Default cursor theme: $CURSOR_THEME"
    run mkdir -p "$dir"
    if [[ "${DRY_RUN:-0}" != 1 ]]; then
        printf '[Icon Theme]\nName=%s\nInherits=%s\n' "$CURSOR_THEME" "$CURSOR_THEME" \
            >"$dir/index.theme"
    fi
    # Hyprland's own cursor path (falls back to XCursor if hyprcursor cannot find it)
    run hyprctl setcursor "$CURSOR_THEME" "$CURSOR_SIZE" 2>/dev/null || true
    theme_flatpak_cursor_path
}

# In the Flatpak sandbox ~/.local/share/icons is mounted at /run/host/user-share/icons
# and /usr/share/icons at /run/host/share/icons, but since XCURSOR_PATH stays empty
# libXcursor does not look there; when the theme is not found the app
# (Zen, Vesktop, VSCodium...) falls back to the built-in default arrow.
theme_flatpak_cursor_path() {
    command -v flatpak >/dev/null 2>&1 || return 0
    run flatpak override --user \
        --env=XCURSOR_PATH=/run/host/user-share/icons:/run/host/share/icons || true
}

hook_fonts_base()  { _refresh_font_cache; }
hook_fonts_extra() { _refresh_font_cache; }

_refresh_font_cache() {
    [[ -n "${_FC_CACHE_DONE:-}" ]] && return 0
    _FC_CACHE_DONE=1
    step "Refreshing the font cache"
    run fc-cache -f || warn "Could not run fc-cache."
}
