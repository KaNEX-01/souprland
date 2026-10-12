#!/usr/bin/env bash
#
# install-dotfiles.sh — copies a prebuilt preset's config files under
# ~/.config. It does NOT install packages; it only places the files.
#
# Usage:
#     ./install-dotfiles.sh                  # list presets
#     ./install-dotfiles.sh nord-frost             # install the nord files
#     ./install-dotfiles.sh nord-frost --packages  # also install the needed programs
#     ./install-dotfiles.sh --only-packages  # install only the programs
#     ./install-dotfiles.sh nord-frost --dry-run   # show what it would do
#     ./install-dotfiles.sh nord-frost --force     # overwrite without asking
#
# Existing files are backed up under ~/.config/hyprsetup-backups/<date-time>/.
# This script is independent of the repo: you can copy the dotfiles/ dir as-is
# and run it on another machine too.
#
set -Eeuo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${XDG_CONFIG_HOME:-$HOME/.config}"
BACKUP_DIR="$TARGET/hyprsetup-backups/$(date +%Y%m%d-%H%M%S)"

PRESET=""
DRY_RUN=0
FORCE=0
WITH_PACKAGES=0
ONLY_PACKAGES=0
PACKAGE_LIST="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/packages.txt"

C_RESET=''; C_BOLD=''; C_DIM=''; C_CYAN=''; C_YELLOW=''; C_GREEN=''
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
    C_CYAN=$'\033[36m'; C_YELLOW=$'\033[33m'; C_GREEN=$'\033[32m'
fi

step() { printf '%s  ->%s %s\n' "$C_CYAN" "$C_RESET" "$*"; }
ok()   { printf '%s  ok%s %s\n' "$C_GREEN" "$C_RESET" "$*"; }
warn() { printf '%s  !!%s %s\n' "$C_YELLOW$C_BOLD" "$C_RESET" "$*" >&2; }
die()  { printf '  XX %s\n' "$*" >&2; exit 1; }

presets() {
    local dir
    for dir in "$HERE"/*/; do
        [[ -d "$dir" ]] || continue
        basename "$dir"
    done
}

list_presets() {
    printf '\n%sPrebuilt dotfile sets%s\n\n' "$C_BOLD" "$C_RESET"
    local name count
    # If the dir is empty, say why instead of printing a silent list: the sets
    # are generated from presets/profile/*.conf, and that dir is currently
    # intentionally empty (see dotfiles/README.md). A list that "prints nothing"
    # would give the impression that the script is broken.
    if [[ -z "$(presets)" ]]; then
        printf '  %sNo sets yet.%s\n\n' "$C_DIM" "$C_RESET"
        printf '  Sets are generated from the profile presets:\n'
        printf '    %s./tools/build-dotfiles.sh%s\n' "$C_CYAN" "$C_RESET"
        printf '  If presets/profile/ is empty, there is nothing to generate.\n\n'
        return 0
    fi
    while IFS= read -r name; do
        count=$(find "$HERE/$name" -type f | wc -l)
        printf '  %s%-22s%s %s%s files%s\n' \
            "$C_BOLD" "$name" "$C_RESET" "$C_DIM" "$count" "$C_RESET"
    done < <(presets)
    printf '\n  To install: %s./install-dotfiles.sh <name>%s\n\n' "$C_CYAN" "$C_RESET"
}

while (($#)); do
    case "$1" in
        -n|--dry-run) DRY_RUN=1; shift ;;
        -f|--force)   FORCE=1; shift ;;
        -t|--target)  TARGET="$2"; shift 2 ;;
        -p|--packages) WITH_PACKAGES=1; shift ;;
        --only-packages) ONLY_PACKAGES=1; WITH_PACKAGES=1; shift ;;
        -l|--list)    list_presets; exit 0 ;;
        -h|--help)    sed -n '3,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        -*)           die "Unknown option: $1" ;;
        *)            PRESET="$1"; shift ;;
    esac
done

# ------------------------------------------------------------- packages -----
# Reads one of the packages.txt sections: repo | aur | service
read_section() {
    local section="$1"
    [[ -r "$PACKAGE_LIST" ]] || return 0
    awk -v want="[$section]" '
        /^\[/ { inside = ($0 == want); next }
        inside && NF && $0 !~ /^#/ { print }
    ' "$PACKAGE_LIST"
}

aur_helper() {
    local helper
    for helper in paru yay pikaur; do
        if command -v "$helper" >/dev/null 2>&1; then
            printf '%s' "$helper"
            return 0
        fi
    done
    return 1
}

install_packages() {
    [[ -r "$PACKAGE_LIST" ]] || die "No package list: $PACKAGE_LIST"

    local svc
    local -a repo=() aur=() services=()
    mapfile -t repo     < <(read_section repo)
    mapfile -t aur      < <(read_section aur)
    mapfile -t services < <(read_section service)

    printf '\n%sPackages%s  ·  %s repo, %s AUR, %s services\n\n' \
        "$C_BOLD" "$C_RESET" "${#repo[@]}" "${#aur[@]}" "${#services[@]}"

    if ((DRY_RUN)); then
        printf '%s  [dry-run]%s sudo pacman -S --needed %s\n' \
            "$C_DIM" "$C_RESET" "${repo[*]}"
        if ((${#aur[@]})); then
            printf '%s  [dry-run]%s <aur-helper> -S --needed %s\n' \
                "$C_DIM" "$C_RESET" "${aur[*]}"
        fi
        for svc in "${services[@]}"; do
            printf '%s  [dry-run]%s sudo systemctl enable --now %s\n' \
                "$C_DIM" "$C_RESET" "$svc"
        done
        return 0
    fi

    command -v pacman >/dev/null 2>&1 ||
        die "pacman not found — this step only works on Arch derivatives."

    if ((${#repo[@]})); then
        step "Installing repo packages (already installed ones are skipped)"
        sudo pacman -S --needed "${repo[@]}" || warn "Some repo packages could not be installed."
    fi

    if ((${#aur[@]})); then
        local helper=""
        helper=$(aur_helper) || true
        if [[ -n "$helper" ]]; then
            step "Installing AUR packages ($helper)"
            "$helper" -S --needed "${aur[@]}" || warn "Some AUR packages could not be installed."
        else
            warn "No AUR helper (paru/yay/pikaur). Install these manually:"
            warn "  ${aur[*]}"
        fi
    fi

    for svc in "${services[@]}"; do
        [[ -n "$svc" ]] || continue
        step "systemd service: $svc"
        sudo systemctl enable --now "$svc" || warn "Could not enable $svc."
    done
    ok "Package step done"
}

if ((ONLY_PACKAGES)); then
    install_packages
    exit 0
fi

if [[ -z "$PRESET" ]]; then
    list_presets
    exit 0
fi
[[ -d "$HERE/$PRESET" ]] || die "No such set: $PRESET (to list: --list)"

printf '\n%sPrebuilt dotfile install%s  ·  %s → %s\n\n' \
    "$C_BOLD" "$C_RESET" "$PRESET" "$TARGET"
if ((DRY_RUN)); then
    warn "DRY-RUN: no files will be written"
fi

if ((WITH_PACKAGES)); then
    install_packages
    echo
fi

written=0
skipped=0
backed_up=0

while IFS= read -r -d '' src; do
    rel="${src#"$HERE/$PRESET"/}"
    dst="$TARGET/$rel"

    if [[ -e "$dst" ]]; then
        if ((!FORCE)) && [[ -t 0 ]]; then
            read -r -p "$(printf '%s??%s Overwrite: %s [Y/n] ' \
                "$C_YELLOW$C_BOLD" "$C_RESET" "$rel")" reply
            reply="${reply:-y}"
            if [[ ! "${reply,,}" =~ ^(y|yes)$ ]]; then
                step "skipped: $rel"
                skipped=$((skipped + 1))
                continue
            fi
        fi
        if ((DRY_RUN)); then
            printf '%s  [dry-run]%s back up: %s\n' "$C_DIM" "$C_RESET" "$dst"
        else
            mkdir -p "$(dirname "$BACKUP_DIR/$rel")"
            cp -a "$dst" "$BACKUP_DIR/$rel"
        fi
        backed_up=$((backed_up + 1))
    fi

    if ((DRY_RUN)); then
        printf '%s  [dry-run]%s write: %s\n' "$C_DIM" "$C_RESET" "$dst"
    else
        install -D -m 644 "$src" "$dst"
        # Helper scripts must be executable (SUPER+F1 calls this).
        if [[ "$rel" == *.sh ]]; then
            chmod 755 "$dst"
        fi
    fi
    written=$((written + 1))
done < <(find "$HERE/$PRESET" -type f -print0 | sort -z)

# hyprland.conf sources custom.conf at the very end; if the file is missing,
# Hyprland errors. Created once, an existing one is never touched.
custom="$TARGET/hypr/custom.conf"
if [[ ! -e "$custom" ]] && ((!DRY_RUN)); then
    mkdir -p "$(dirname "$custom")"
    cat >"$custom" <<'EOF'
# Your personal Hyprland settings.
# This file is not overwritten even if the prebuilt dotfiles are reinstalled,
# and since it is read at the very end of hyprland.conf it can override the generated settings.
#
# Example:
#   bind = SUPER, G, exec, steam
#   windowrule = workspace 3 silent, match:class ^(discord)$
EOF
    step "created: hypr/custom.conf"
fi

echo
ok "$written files written · $skipped skipped · $backed_up backed up"
if ((backed_up)) && ((!DRY_RUN)); then
    step "Your old files: $BACKUP_DIR"
fi

wallpaper="$HOME/Pictures/wallpapers/wallpaper.png"
if [[ ! -f "$wallpaper" ]]; then
    warn "No wallpaper: $wallpaper — hyprpaper and hyprlock expect this path."
fi

cat <<EOF

${C_BOLD}Next steps${C_RESET}
  1. The needed programs (waybar, kitty, wofi, mako, hyprpaper, hyprlock,
     hypridle, dolphin, cliphist, grim/slurp/swappy, brightnessctl, pavucontrol,
     nm-applet, blueman, fonts…) are listed in ${C_CYAN}packages.txt${C_RESET}:
       ${C_CYAN}./install-dotfiles.sh $PRESET --packages${C_RESET}
     If you want to choose the packages yourself, use the installer in the repo:
       ${C_CYAN}./install.sh${C_RESET}   (what gets installed: DEFAULT_COMPONENTS in install.sh)
  2. Log out and log in with Hyprland (or ${C_CYAN}SUPER + SHIFT + R${C_RESET}).
  3. Keybinding list: ${C_CYAN}SUPER + F1${C_RESET}
  4. For your own additions: ${C_CYAN}~/.config/hypr/custom.conf${C_RESET}
     (read last, overrides every setting in these files)
EOF
