#!/usr/bin/env bash
#
# restore.sh — roll back from the backups taken by install.sh
#
# install.sh copies every file it overwrites to
#   ~/.config/hyprsetup-backups/<timestamp>/<relative-path>
# This script restores one of those backups.
#
set -Eeuo pipefail

SETUP_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export SETUP_ROOT
# shellcheck source=lib/core.sh
source "$SETUP_ROOT/lib/core.sh"

BACKUP_ROOT="$HOME/.config/hyprsetup-backups"
DRY_RUN=0

usage() {
    cat <<'EOF'
Usage: ./restore.sh [options] [backup-dir]

Without a backup dir, the latest INSTALL backup (install.sh) is used.
The settings app's session backups ("live") are only selected by name.

OPTIONS
    -l, --list      List available backups and exit
    -f, --first     Use the first backup (the original state before hyprsetup)
    -n, --dry-run   Only show what would be done
    -y, --yes       Do not ask for confirmation
    -h, --help      This help
EOF
}

list_backups() {
    [[ -d "$BACKUP_ROOT" ]] || { warn "No backups: $BACKUP_ROOT"; return 0; }
    local dir count first=1 note
    info "Available backups ($BACKUP_ROOT)"
    while IFS= read -r dir; do
        count=$(find "$dir" -type f -not -name '_*' | wc -l)
        note=""
        ((first)) && note="  ← first backup (before hyprsetup)"
        first=0
        printf '  %s  %-7s %s(%s files)%s%s\n' "$(basename "$dir")" \
            "$(backup_kind "$dir")" "$C_DIM" "$count" "$C_RESET" "$note"
    done < <(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d | sort)
}

# Backup kind: install (install.sh) | live (settings app). For old backups
# without a _kind file, only install.sh writes _manifest.txt.
# Same rule as python/hyprsetup/backups.py:kind_of.
backup_kind() {  # <dir>
    local kind=""
    [[ -r "$1/_kind" ]] && kind=$(<"$1/_kind")
    case "$kind" in
        install|live) printf '%s' "$kind" ;;
        *) [[ -e "$1/_manifest.txt" ]] && printf 'install' || printf 'live' ;;
    esac
}

main() {
    local target="" first=0
    while (($#)); do
        case "$1" in
            -l|--list)    list_backups; exit 0 ;;
            -f|--first)   first=1; shift ;;
            -n|--dry-run) DRY_RUN=1; shift ;;
            -y|--yes)     ASSUME_YES=1; shift ;;
            -h|--help)    usage; exit 0 ;;
            -*)           err "Unknown option: $1"; usage; exit 2 ;;
            *)            target="$1"; shift ;;
        esac
    done

    [[ -d "$BACKUP_ROOT" ]] || die "No backups found: $BACKUP_ROOT"

    if [[ -z "$target" ]]; then
        local dir
        if ((first)); then
            target=$(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d | sort | head -1)
        else
            # The latest INSTALL backup. It used to pick the latest dir; since the
            # settings app opens a new dir every session, that was the previous
            # small change rather than the pre-install state.
            while IFS= read -r dir; do
                [[ "$(backup_kind "$dir")" == install ]] && target="$dir"
            done < <(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d | sort)
        fi
        [[ -n "$target" ]] || die "No backup dir found (check with --list)."
    fi
    [[ -d "$target" ]] || target="$BACKUP_ROOT/$target"
    [[ -d "$target" ]] || die "Backup dir does not exist: $target"

    banner
    info "Backup to restore: $target"
    local count
    count=$(find "$target" -mindepth 1 -type f -not -path "$target/_root/*" \
                 -not -path "$target/_*" | wc -l)
    step "$count files will be restored (under \$HOME, by relative path)"

    # Files created from scratch in that run: reverting means deleting
    # them. Only those under $HOME that still exist.
    local created=() path
    if [[ -r "$target/_created.txt" ]]; then
        while IFS= read -r path; do
            [[ "$path" == "$HOME"/* && -e "$path" ]] && created+=("$path")
        done <"$target/_created.txt"
    fi
    ((${#created[@]})) && step "${#created[@]} files were newly created by that install — they will be deleted"

    # --dry-run lists what would happen below; the default "no" here used to
    # end it before a single file was shown.
    [[ "$DRY_RUN" == 1 ]] || confirm "Continue? Existing files will be overwritten." n ||
        { warn "Cancelled."; exit 0; }

    # System files (e.g. /etc/...) are kept under "_root"; since they need root
    # they are not restored automatically, only listed.
    if [[ -d "$target/_root" ]]; then
        warn "There are system file backups — you need to restore these manually:"
        find "$target/_root" -type f -printf '        sudo cp -a %p /%P\n'
    fi

    local src rel dst restored=0
    while IFS= read -r -d '' src; do
        rel="${src#"$target"/}"
        # _manifest.txt / _kind / _created.txt are the backup's own records.
        [[ "$rel" == _* ]] && continue
        dst="$HOME/$rel"
        if [[ "$DRY_RUN" == 1 ]]; then
            printf '%s  [dry-run]%s restore: %s\n' "$C_DIM" "$C_RESET" "$dst"
        else
            mkdir -p "$(dirname "$dst")"
            cp -a "$src" "$dst"
            step "restored: ~/$rel"
        fi
        ((restored++)) || true
    done < <(find "$target" -type f -print0)

    ok "$restored files restored."

    for path in "${created[@]+"${created[@]}"}"; do
        if [[ "$DRY_RUN" == 1 ]]; then
            printf '%s  [dry-run]%s delete: %s\n' "$C_DIM" "$C_RESET" "$path"
        else
            rm -f -- "$path" && step "deleted (added during install): ${path/#$HOME/\~}"
        fi
    done
    warn "If Hyprland is running, to apply the changes: hyprctl reload"
}

main "$@"
