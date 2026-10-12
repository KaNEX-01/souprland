# shellcheck shell=bash
# modules/desktop.sh — steps specific to desktop applications

hook_waybar() {
    # Waybar 0.10+ reads config.jsonc; warn if an old config file exists.
    if [[ -f "$HOME/.config/waybar/config" && ! -L "$HOME/.config/waybar/config" ]]; then
        warn "Found an old ~/.config/waybar/config; new settings will be written to config.jsonc."
        warn "If both exist, Waybar prefers the 'config' file."
        if confirm "Back up and remove the old file?" y; then
            backup_path "$HOME/.config/waybar/config"
            run rm -f "$HOME/.config/waybar/config"
        fi
    fi
}

hook_hyprpanel() {
    # Older AGS v1-based HyprPanel versions wrote under ~/.config/ags; the
    # current version uses ~/.config/hyprpanel/config.json. Having both around
    # is confusing.
    if [[ -d "$HOME/.config/ags" ]]; then
        warn "Found an old ~/.config/ags dir; current HyprPanel uses ~/.config/hyprpanel."
        if confirm "Back up and remove the old dir?" y; then
            backup_path "$HOME/.config/ags"
            run rm -rf "$HOME/.config/ags"
        fi
    fi
    # HyprPanel only supports top/bottom bar positions; if a vertical preset like
    # "rail" is selected, render.py silently falls back to the top — inform the user.
    # (Since hooks run before render, BAR_POSITION is checked directly here;
    # the HYPRPANEL_RAIL_FALLBACK produced by render.py does not exist yet at this point.)
    if [[ "${BAR_POSITION:-top}" == "left" || "${BAR_POSITION:-top}" == "right" ]]; then
        warn "The selected bar preset wants a vertical (left/right) bar; since HyprPanel does"
        warn "not support that, the bar will open at the top. For a vertical look, try BAR=waybar."
    fi
}

# Walker's search providers (apps, calculator, clipboard etc.) are fed by a
# separate "elephant" service; if it is not installed Walker opens but lists
# no results. Since the package name differs per distro, no automatic install
# is attempted here, only a warning.
# SwayOSD: volume/brightness indicator. The part bound to keybindings (swayosd-client)
# needs no extra setup — the server starts from autostart (see render.py
# _autostart_entries). But the CapsLock/NumLock/ScrollLock indicator works
# differently: these cannot be bound to a keybinding; they need a separate
# system service listening to libinput events, and that service can only read
# keyboard devices if the user is in the 'input' group. Without this step the
# volume/brightness indicator works but nothing shows on CapsLock — a silent half-install.
hook_swayosd() {
    have swayosd-server || return 0

    if [[ -n "$(systemctl list-unit-files --no-legend swayosd-libinput-backend.service 2>/dev/null)" ]]; then
        if root_ops_allowed; then
            step "Enabling the swayosd libinput backend (CapsLock indicator)"
            run sudo systemctl enable --now swayosd-libinput-backend.service \
                || warn "Could not enable swayosd-libinput-backend — the CapsLock indicator may not work."
        else
            step "swayosd libinput backend skipped (--configs-only)"
        fi
    fi

    # 'input' group membership takes effect in a new session; the user must be
    # told, otherwise "I installed it but there is no CapsLock indicator" stays unexplained.
    if ! grep -qx input <<<"$(id -nG "$USER" 2>/dev/null | tr ' ' '\n')"; then
        if root_ops_allowed && confirm "Add user '$USER' to the 'input' group for SwayOSD's CapsLock indicator?" y; then
            run sudo usermod -aG input "$USER" \
                && warn "You were added to the 'input' group — log out and back in for it to take effect."
        else
            warn "For the CapsLock indicator: sudo usermod -aG input $USER (then log in again)"
        fi
    fi
}

hook_walker() {
    have elephant && return 0
    warn "Walker is selected but the 'elephant' service was not found — search may return no results."
    warn "You need to install and enable elephant from your distro's package source."
}

# ---------------------------------------------------------- default apps
# The assignment ITSELF is no longer done here: ~/.config/mimeapps.list and
# ~/.config/xdg-terminals.list are generated from templates (templates/xdg/, table
# in python/hyprsetup/render.py → DEFAULT_APP_ROLES). Previously each file manager
# component's own hook called "xdg-mime default … inode/directory";
# it had three problems:
#   · the hook ONLY fires when that component is installed in that run, so
#     --reapply never repaired the assignment;
#   · xdg-mime writes to the same mimeapps.list, so it raced with the
#     generated file — which one won depended on run order;
#   · only inode/directory was assigned, every other type was left open.
# One job remains: refreshing the desktop's .desktop cache, otherwise newly
# written assignments do not show up until the session restarts.
apply_default_apps() {
    [[ "${SKIP_CONFIGS:-0}" == 1 ]] && return 0
    have update-desktop-database || return 0
    local dir="$HOME/.local/share/applications"
    [[ -d "$dir" ]] || return 0
    step "Refreshing the default application cache"
    run update-desktop-database "$dir" \
        || warn "update-desktop-database failed — defaults take effect in a new session."
}

hook_dolphin() {
    # Dolphin is a KDE Frameworks app: it fully uses the generated ~/.config/kdeglobals
    # color scheme (and the Breeze widget style) only when QT_QPA_PLATFORMTHEME
    # =kde — even if the rest of the desktop uses qt6ct/qt5ct.
    # Previously a confirmation suggested switching the GLOBAL QT_PLATFORM_THEME
    # variable to "kde" for this; if the user said "no" (or the prompt was never
    # asked), Dolphin silently stayed on the default/qt6ct palette — that was why
    # Dolphin launched from a keybinding always opened "in the default colors".
    # config/components.json → dolphin.exec solves this FOR the MOD+E file manager
    # keybinding — but ALL other paths, like the launcher (wofi/rofi "drun"), a
    # panel/taskbar click, right-click "Open with File Manager", read the system's
    # own .desktop file (a plain "Exec=dolphin %u", no wrapper) — so Dolphin opened
    # from those paths still kept the default colors.
    # _dolphin_desktop_override solves this comprehensively.
    _dolphin_desktop_override
    _restart_open_kde_qt_apps
}

# Puts an override copy under ~/.local/share/applications/ with only the Exec=
# line wrapped in "env QT_QPA_PLATFORMTHEME=kde" (the XDG search order scans the
# user dir before /usr/share/applications/) — so EVERY path that opens Dolphin
# (launcher, panel, "Open with File Manager") sees the same kdeglobals color
# scheme, not just the MOD+E keybinding. The rest of the file, including
# MimeType=inode/directory, is copied as-is — otherwise xdg-mime's default file
# manager assignment breaks.
_dolphin_desktop_override() {
    local src="" candidate dst
    for candidate in /usr/share/applications/org.kde.dolphin.desktop \
                     /usr/share/applications/dolphin.desktop; do
        [[ -f "$candidate" ]] && { src="$candidate"; break; }
    done
    if [[ -z "$src" ]]; then
        warn "Dolphin .desktop file not found — Dolphin opened from the launcher may keep the default colors."
        return 0
    fi

    dst="$HOME/.local/share/applications/$(basename "$src")"
    step "Updating the Dolphin launcher entry (open with QT_QPA_PLATFORMTHEME=kde everywhere): $dst"
    if [[ "${DRY_RUN:-0}" == 1 ]]; then
        printf '%s  [dry-run]%s write: %s\n' "$C_DIM" "$C_RESET" "$dst"
        return 0
    fi
    mkdir -p "$(dirname "$dst")"
    sed -E 's/^Exec=(.*)$/Exec=env QT_QPA_PLATFORMTHEME=kde \1/' "$src" >"$dst"
    have update-desktop-database && update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1
}

# Firefox UI theme. The template engine cannot write this file directly to its
# target: the profile dir has a random prefix (e.g. "a1b2c3d4.default-release")
# and there may be more than one profile. So userChrome.css is first generated
# under ~/.config/hyprsetup/firefox/ and copied from there.
#
# IMPORTANT — ORDERING: hooks run BEFORE render_run, so the source file does
# NOT EXIST YET at that point. So the copying is done not in a hook but in
# install_firefox_theme(), which install.sh calls after render
# (same reasoning as enable_wallpaper_rotation).
install_firefox_theme() {
    in_list "firefox-theme" "${SELECTED[@]}" || return 0
    [[ "${SKIP_CONFIGS:-0}" == 1 ]] && return 0

    local src="$HOME/.config/hyprsetup/firefox/userChrome.css"
    [[ -r "$src" ]] || { debug "userChrome.css not generated, skipping"; return 0; }

    local ini="$HOME/.mozilla/firefox/profiles.ini"
    if [[ ! -r "$ini" ]]; then
        warn "No Firefox profile found — open the browser once and rerun the installer."
        warn "  ./install.sh"
        return 0
    fi

    # The Path= lines in profiles.ini give the profile dirs.
    # If IsRelative=1 the path is relative to ~/.mozilla/firefox (the typical case).
    local applied=0 path dir
    while IFS= read -r path; do
        [[ -n "$path" ]] || continue
        if [[ "$path" == /* ]]; then dir="$path"; else dir="$HOME/.mozilla/firefox/$path"; fi
        [[ -d "$dir" ]] || continue

        run mkdir -p "$dir/chrome"
        [[ -e "$dir/chrome/userChrome.css" ]] && backup_path "$dir/chrome/userChrome.css"
        if run cp "$src" "$dir/chrome/userChrome.css"; then
            applied=$((applied + 1))
        fi

        # userChrome.css has been IGNORED BY DEFAULT since Firefox 69;
        # without enabling this setting the file does nothing and the user says
        # "the theme was not applied". user.js is merged into prefs.js when the profile opens.
        local userjs="$dir/user.js"
        if ! grep -qF 'legacyUserProfileCustomizations' "$userjs" 2>/dev/null; then
            [[ -e "$userjs" ]] && backup_path "$userjs"
            if [[ "${DRY_RUN:-0}" != 1 ]]; then
                printf '\n// hyprsetup: read userChrome.css\nuser_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);\n' \
                    >>"$userjs"
            fi
        fi
    done < <(sed -n 's/^Path=//p' "$ini")

    if ((applied)); then
        ok "Firefox theme applied to $applied profile(s) — restart Firefox."
    else
        warn "The Firefox theme could not be applied to any profile."
    fi
    return 0
}

hook_discord_theme() {
    # quickCss.css is written from the template under ~/.config/Vencord/settings/;
    # here we only remind the user of the single manual step needed.
    step "Discord theme: 'Enable Custom CSS' must be on in the Vencord settings"
}

hook_spicetify() {
    have spicetify || { warn "spicetify-cli could not be installed — skipping the Spotify theme."; return 0; }
    # spicetify writes to Spotify's install dir and can only do so while
    # Spotify is installed.
    have spotify || { warn "Spotify is not installed — the spicetify theme was not applied."; return 0; }
    step "Applying the Spotify theme (spicetify)"
    run spicetify config current_theme hyprsetup color_scheme base \
        || { warn "Could not configure spicetify."; return 0; }
    run spicetify apply \
        || warn "spicetify apply failed — try 'spicetify backup apply'."
    warn "The theme resets every time Spotify updates; 'spicetify apply' is needed again."
}

# The browser assignment now also comes from mimeapps.list (BROWSER variable →
# the component's "desktop" field). Here only xdg-settings' own record is
# aligned: some GTK apps ask xdg-settings directly instead of the http
# x-scheme-handler. Writing a fixed "firefox.desktop" was wrong — when
# BROWSER was set to another browser it silently reverted to Firefox.
apply_default_browser() {
    [[ "${SKIP_CONFIGS:-0}" == 1 ]] && return 0
    have xdg-settings || return 0
    local desktop
    desktop=$(catalog_desktop "${BROWSER:-}")
    [[ -n "$desktop" ]] || return 0
    step "Default browser: $desktop"
    run xdg-settings set default-web-browser "$desktop" \
        || warn "Could not set xdg-settings — the browser assignment will be read from mimeapps.list."
}

hook_swaync() {
    # Cannot run at the same time as mako/dunst.
    local other
    for other in mako dunst; do
        if in_list "$other" "${SELECTED[@]}"; then
            warn "Both swaync and $other are selected — only one can run at a time."
            warn "Autostart will follow NOTIFIER=$NOTIFIER."
        fi
    done
}

# The same warning as hook_swaync, produced symmetrically from the mako/dunst
# side too — the "notify" category is normally single-choice (config/components.json
# → select:single), so these three can never be selected together from the GUI/TUI,
# but a command line call like --only mako,dunst can bypass the category restriction;
# previously the warning only appeared if swaync was selected, and a mako+dunst pair
# was never warned about.
hook_mako() {
    local other
    for other in dunst swaync; do
        if in_list "$other" "${SELECTED[@]}"; then
            warn "Both mako and $other are selected — only one can run at a time."
            warn "Autostart will follow NOTIFIER=$NOTIFIER."
        fi
    done
}

hook_dunst() {
    local other
    for other in mako swaync; do
        if in_list "$other" "${SELECTED[@]}"; then
            warn "Both dunst and $other are selected — only one can run at a time."
            warn "Autostart will follow NOTIFIER=$NOTIFIER."
        fi
    done
}

# --- community projects ----------------------------------------------------

# nwg-displays generates monitors.conf and workspaces.conf itself; if two
# tools manage the same file, one overwrites the other's output.
hook_nwg_displays() {
    if [[ "${MANAGE_MONITORS:-1}" == 1 || -n "${WORKSPACE_MONITOR_MAP:-}" ]]; then
        warn "nwg-displays generates monitors.conf and workspaces.conf itself."
        warn "The script manages the same files too — the two conflict."
        if confirm "Leave these files to nwg-displays (recommended)?" y; then
            MANAGE_MONITORS=0
            WORKSPACE_MONITOR_MAP=""
            export MANAGE_MONITORS WORKSPACE_MONITOR_MAP
            ok "MANAGE_MONITORS=0 — set up the display layout with 'nwg-displays'"
        fi
    fi
}

# https://github.com/Almamu/linux-wallpaperengine
# Needs the assets of Wallpaper Engine purchased on Steam.
hook_wallpaperengine() {
    local found="" dir
    for dir in "$HOME/.steam/steam/steamapps/common/wallpaper_engine" \
               "$HOME/.local/share/Steam/steamapps/common/wallpaper_engine" \
               "$HOME/.var/app/com.valvesoftware.Steam/.local/share/Steam/steamapps/common/wallpaper_engine"; do
        [[ -d "$dir" ]] && { found="$dir"; break; }
    done

    if [[ -z "$found" ]]; then
        warn "Wallpaper Engine assets not found."
        warn "linux-wallpaperengine requires Wallpaper Engine purchased on Steam"
        warn "to be installed. After installing it, run:"
        warn "  linux-wallpaperengine --assets-dir /path/wallpaper_engine --bg <ID>"
        return 0
    fi
    ok "Wallpaper Engine assets: $found"

    local workshop="$HOME/.steam/steam/steamapps/workshop/content/431960"
    if [[ -z "${WPENGINE_ID:-}" && -d "$workshop" ]]; then
        warn "WPENGINE_ID is not set — the wallpaper will not start automatically."
        step "Available wallpaper IDs (first 5):"
        find "$workshop" -mindepth 1 -maxdepth 1 -type d -printf '        %f\n' 2>/dev/null | head -5
        warn "Pick one and write WPENGINE_ID=\"<id>\" into settings.conf."
    fi
}

hook_hyprmod() {
    step "HyprMod: a GTK4 Hyprland settings app — start it with 'hyprmod'"
    warn "Note: ML4W Hyprland Settings (mylinuxforwork/hyprland-settings) was archived"
    warn "in 2026-05; HyprMod is its recommended successor and is still a new package."
}

hook_wayle() {
    step "Wayle installed — ~/.config/wayle/config.toml generated."
    step "Settings window: wayle panel settings · CLI: wayle config"
    step "Control: wayle panel status | restart | stop"
    # Wayle is a "full shell": besides the bar, the notification center, OSD and
    # wallpaper management are also INSIDE it. Installing these separately means
    # two notification servers / two OSDs / two wallpaper processes; both run
    # and the user does not understand why they see double.
    local clash=()
    for c in mako swaync swayosd swww hyprpaper waypaper; do
        in_list "$c" "${SELECTED[@]+"${SELECTED[@]}"}" && clash+=("$c")
    done
    if ((${#clash[@]})); then
        warn "Wayle carries notifications, OSD and wallpaper within itself."
        warn "These are also selected and may conflict: ${clash[*]}"
        warn "If you see double notifications/OSD, remove these from the component list."
    fi
}

hook_quickshell() {
    step "Quickshell installed — ~/.config/quickshell/shell.qml generated."
    step "Docs: https://quickshell.outfoxxed.me"
    # Note: this message used to say "no config is generated"; now
    # templates/quickshell/shell.qml.tmpl generates both the bar and the widgets.
    #
    # The command DELIBERATELY uses "-p". "-c" expects a config *name* and
    # looks for ~/.config/quickshell/<name>/shell.qml; given a path, Quickshell
    # cannot find the config and the bar never opens. Our file sits in the base
    # folder (~/.config/quickshell/shell.qml), so the right flag is "-p".
    step "To start manually: quickshell -p ~/.config/quickshell/shell.qml"
}

# The cli-tools packages (zoxide, fzf, eza, bat) are nearly useless without
# shell integration: no "z" command, CTRL+R search or aliases.
# The generated ~/.config/hyprsetup/shell.sh sets these up; all that is left is
# reading it from the shell startup file.
hook_cli_tools() {
    # Note: hooks run before templates; the file may not be generated yet.
    # The added line does its own "read if present" check, so that is not a problem.
    #
    # fish is handled SEPARATELY: it is not POSIX-compatible ("[ ... ] && . file"
    # is a syntax error there), so it needs both a different source file
    # (shell.fish) and a different line to add. Writing only to .bashrc/.zshrc
    # when the user's login shell is fish meant the setup silently did
    # nothing at all.
    local posix_line='[ -f ~/.config/hyprsetup/shell.sh ] && . ~/.config/hyprsetup/shell.sh'
    local fish_line='test -f ~/.config/hyprsetup/shell.fish; and source ~/.config/hyprsetup/shell.fish'

    local rc line added=0 marker
    for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.config/fish/config.fish"; do
        if [[ "$rc" == *fish* ]]; then
            line="$fish_line"; marker='hyprsetup/shell.fish'
        else
            line="$posix_line"; marker='hyprsetup/shell.sh'
        fi

        # The fish config may not exist by default; if the user's login shell
        # is fish, creating the dir and the file is the right behavior.
        if [[ ! -f "$rc" ]]; then
            [[ "$rc" == *fish* && "${SHELL:-}" == *fish* ]] || continue
        fi

        if [[ -f "$rc" ]] && grep -qF "$marker" "$rc" 2>/dev/null; then
            debug "shell integration already present: $rc"
            added=1
            continue
        fi

        if confirm "Add the terminal tools to ${rc/#$HOME/\~} (z, CTRL+R, ls aliases)?" y; then
            [[ -f "$rc" ]] && backup_path "$rc"
            if [[ "${DRY_RUN:-0}" != 1 ]]; then
                mkdir -p "$(dirname "$rc")"
                printf '\n# hyprsetup terminal tools\n%s\n' "$line" >>"$rc"
            fi
            ok "Added: $rc"
            added=1
        fi
    done

    if ((added == 0)); then
        step "To add it manually, put this in your shell file:"
        printf '        %s   %s(bash/zsh)%s\n' "$posix_line" "$C_DIM" "$C_RESET"
        printf '        %s   %s(fish)%s\n' "$fish_line" "$C_DIM" "$C_RESET"
    fi
}

# The starship config comes from a template; here we only make sure the shell
# integration is set up (shell.sh/shell.fish starts it — see
# templates/hyprsetup/). If cli-tools is not selected those files are never
# generated, and starship does not kick in even if installed.
hook_starship() {
    if ! in_list "cli-tools" "${SELECTED[@]}"; then
        warn "starship installed but 'cli-tools' is not selected — no shell integration is generated."
        warn "Manually: add  eval \"\$(starship init bash)\"  to your shell file."
    fi
}

hook_dev_tools() {
    # Make neovim the default editor (with the user's consent).
    have nvim || return 0
    if confirm "Set the EDITOR variable to nvim (~/.profile)?" n; then
        local line='export EDITOR=nvim'
        if ! grep -qxF "$line" "$HOME/.profile" 2>/dev/null; then
            backup_path "$HOME/.profile"
            [[ "${DRY_RUN:-0}" == 1 ]] || printf '%s\n' "$line" >>"$HOME/.profile"
        fi
    fi
}
