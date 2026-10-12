# shellcheck shell=bash
# core.sh — shared helpers: colors, logging, error handling, backups, dry-run
# This file is not run directly; install.sh sources it.

[[ -n "${_CORE_SH_LOADED:-}" ]] && return 0
_CORE_SH_LOADED=1

# ----------------------------------------------------------------- colors ---
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
    C_RED=$'\033[31m';  C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
    C_BLUE=$'\033[34m'; C_MAGENTA=$'\033[35m'; C_CYAN=$'\033[36m'
else
    C_RESET=''; C_BOLD=''; C_DIM=''
    C_RED=''; C_GREEN=''; C_YELLOW=''; C_BLUE=''; C_MAGENTA=''; C_CYAN=''
fi

# ------------------------------------------------------------------- log ----
# The log lives in the user's own state dir: /tmp is world-accessible and
# the log contains home dir paths, the package list and command output.
# Only the owner can read it (umask 077); the newest 10 logs are kept.
if [[ -z "${LOG_FILE:-}" ]]; then
    _log_dir="${XDG_STATE_HOME:-$HOME/.local/state}/hyprsetup/logs"
    if mkdir -p "$_log_dir" 2>/dev/null; then
        LOG_FILE="$_log_dir/install-$(date +%Y%m%d-%H%M%S).log"
        # shellcheck disable=SC2012  # names are timestamps; ls ordering is enough
        ls -1t "$_log_dir"/install-*.log 2>/dev/null | tail -n +10 \
            | while IFS= read -r _old; do rm -f -- "$_old"; done || true
    else
        LOG_FILE="$(mktemp -t hyprsetup-XXXXXX.log)"
    fi
    unset _log_dir _old
fi
( umask 077; : >>"$LOG_FILE" ) 2>/dev/null || true

_log_raw() { printf '%s\n' "$*" >>"$LOG_FILE" 2>/dev/null || true; }

log()      { printf '%s\n' "$*";                      _log_raw "[ ] $*"; }
info()     { printf '%s==>%s %s\n'  "$C_BLUE$C_BOLD" "$C_RESET" "$*";     _log_raw "[i] $*"; }
step()     { printf '%s  ->%s %s\n' "$C_CYAN" "$C_RESET" "$*";            _log_raw "[>] $*"; }
ok()       { printf '%s  ok%s %s\n' "$C_GREEN" "$C_RESET" "$*";           _log_raw "[+] $*"; }
warn()     { printf '%s  !!%s %s\n' "$C_YELLOW$C_BOLD" "$C_RESET" "$*" >&2; _log_raw "[!] $*"; }
err()      { printf '%s  XX%s %s\n' "$C_RED$C_BOLD" "$C_RESET" "$*" >&2;  _log_raw "[x] $*"; }
debug()    { [[ "${VERBOSE:-0}" == 1 ]] && printf '%s  ..%s %s\n' "$C_DIM" "$C_RESET" "$*" >&2; _log_raw "[d] $*"; return 0; }

die() { err "$*"; err "Detailed log: $LOG_FILE"; exit 1; }

banner() {
    # Souprland logo: a steaming bowl (see assets/souprland.svg).
    printf '\n'
    printf '%s         (   %s(%s   (%s\n'  "$C_MAGENTA" "$C_CYAN" "$C_MAGENTA" "$C_RESET"
    printf '%s          )   %s)%s   )%s\n' "$C_MAGENTA" "$C_CYAN" "$C_MAGENTA" "$C_RESET"
    printf '%s     .~~~~~~~~~~~~~~~~.%s    %ssouprland%s\n' \
        "$C_YELLOW" "$C_RESET" "$C_MAGENTA$C_BOLD" "$C_RESET"
    printf '%s      \\  %s▪   ▪   ▪%s   /%s    %sHyprland, served hot%s\n' \
        "$C_YELLOW" "$C_CYAN" "$C_YELLOW" "$C_RESET" "$C_DIM" "$C_RESET"
    printf '%s       \\____________/%s     %sCachyOS / Arch Linux%s\n' \
        "$C_YELLOW" "$C_RESET" "$C_DIM" "$C_RESET"
    printf '%s         `--------´%s\n\n' "$C_YELLOW" "$C_RESET"
}

# On unexpected errors, exit with the line number.
_on_error() {
    local exit_code=$? line=$1
    err "Unexpected error (line $line, exit code $exit_code)."
    err "Detailed log: $LOG_FILE"
    exit "$exit_code"
}
trap '_on_error $LINENO' ERR

# --------------------------------------------------------------- dry-run ----
# run <command...>  → only prints when DRY_RUN=1, otherwise runs it.
run() {
    if [[ "${DRY_RUN:-0}" == 1 ]]; then
        printf '%s  [dry-run]%s %s\n' "$C_DIM" "$C_RESET" "$*"
        _log_raw "[dry] $*"
        return 0
    fi
    debug "\$ $*"
    _log_raw "[run] $*"
    "$@" >>"$LOG_FILE" 2>&1
}

# run_visible — for commands whose output should also be shown to the user.
run_visible() {
    if [[ "${DRY_RUN:-0}" == 1 ]]; then
        printf '%s  [dry-run]%s %s\n' "$C_DIM" "$C_RESET" "$*"
        return 0
    fi
    _log_raw "[run] $*"
    "$@" 2>&1 | tee -a "$LOG_FILE"
    return "${PIPESTATUS[0]}"
}

# ------------------------------------------------------------------ sudo ----
SUDO_KEEPALIVE_PID=""

sudo_init() {
    [[ "${DRY_RUN:-0}" == 1 ]] && return 0
    if ! sudo -v; then
        # The most common cause is NOT a wrong password: it is the script
        # having no terminal attached. When run from an editor/IDE panel, a
        # script or a file manager, sudo cannot ask for the password and says
        # "a terminal is required to read the password". If we do not say so,
        # the user thinks they mistyped their password.
        if [[ ! -t 0 ]]; then
            err "sudo could not ask for a password: this session has no terminal."
            err "Run the installer in a real terminal window:"
            err "    cd ${SETUP_ROOT:-.} && ./install.sh"
        fi
        die "Could not get sudo privileges."
    fi
    # Keep the sudo session alive during long installs.
    ( while true; do sudo -n true 2>/dev/null; sleep 50; kill -0 "$$" 2>/dev/null || exit; done ) &
    SUDO_KEEPALIVE_PID=$!
}

sudo_stop() {
    [[ -n "$SUDO_KEEPALIVE_PID" ]] && kill "$SUDO_KEEPALIVE_PID" 2>/dev/null || true
    SUDO_KEEPALIVE_PID=""
}
trap sudo_stop EXIT

# -------------------------------------------------------------- prompts ----
# confirm "question" [default: y|n]
confirm() {
    local prompt="$1" default="${2:-y}" reply hint
    [[ "${ASSUME_YES:-0}" == 1 ]] && return 0
    # --dry-run asks nothing: the question is printed, the default answer is taken.
    # (On a system without an AUR helper, "install paru?" used to keep
    # the user waiting here.)
    if [[ "${DRY_RUN:-0}" == 1 ]]; then
        printf '%s??%s %s %s[dry-run: %s]%s\n' "$C_YELLOW$C_BOLD" "$C_RESET" \
            "$prompt" "$C_DIM" "$([[ "$default" == y ]] && echo yes || echo no)" "$C_RESET"
        [[ "$default" == y ]]
        return $?
    fi
    [[ ! -t 0 ]] && { [[ "$default" == y ]]; return $?; }
    hint=$([[ "$default" == y ]] && echo "[Y/n]" || echo "[y/N]")
    read -r -p "$(printf '%s??%s %s %s ' "$C_YELLOW$C_BOLD" "$C_RESET" "$prompt" "$hint")" reply
    reply="${reply:-$default}"
    [[ "${reply,,}" =~ ^(y|yes)$ ]]
}

# --------------------------------------------------------------- backup -----
BACKUP_DIR="${BACKUP_DIR:-$HOME/.config/hyprsetup-backups/$(date +%Y%m%d-%H%M%S)}"

# Marks this run's backup dir as "install" (see
# python/hyprsetup/backups.py). restore.sh picks the latest INSTALL backup
# by default; the settings app's session backups are marked "live".
_backup_dir_init() {
    [[ -d "$BACKUP_DIR" ]] || mkdir -p "$BACKUP_DIR"
    [[ -e "$BACKUP_DIR/_kind" ]] || printf 'install\n' >"$BACKUP_DIR/_kind"
}

# backup_record_created <path> — records a file created where there was NONE
# before; restore.sh deletes these on revert (otherwise "revert" would only
# bring back overwritten files and added files would remain).
backup_record_created() {
    [[ "${DRY_RUN:-0}" == 1 ]] && return 0
    _backup_dir_init 2>/dev/null || return 0
    printf '%s\n' "$1" >>"$BACKUP_DIR/_created.txt" 2>/dev/null || true
}

# backup_path <path> — if the file/dir exists, copies (not moves) it under BACKUP_DIR.
backup_path() {
    local target="$1"
    [[ -e "$target" || -L "$target" ]] || return 0
    # Things inside the home dir go relative, things outside (e.g. /etc/...) under "_root".
    local rel="${target#"$HOME"/}"
    [[ "$rel" == /* ]] && rel="_root$rel"
    local dest="$BACKUP_DIR/$rel"
    run mkdir -p "$(dirname "$dest")"
    if [[ "${DRY_RUN:-0}" == 1 ]]; then
        printf '%s  [dry-run]%s backup: %s -> %s\n' "$C_DIM" "$C_RESET" "$target" "$dest"
        return 0
    fi
    _backup_dir_init
    cp -a "$target" "$dest" 2>>"$LOG_FILE" || { warn "Could not back up: $target"; return 0; }
    debug "backed up: $target -> $dest"
    # A record of what was backed up (restore.sh does not read it, it is for humans).
    printf '%s\n' "$target" >>"$BACKUP_DIR/_manifest.txt" 2>/dev/null || true
}

# ------------------------------------------------------- foreign configs ----
# Ownership mark placed in the display/workspace files we generate ourselves.
# If the mark is present the file is ours; when nwg-displays rewrites the file
# the mark is lost too, so ownership changes hands on its own.
OWNER_MARK="hyprsetup:managed"

# Targets whose ownership is RESPECTED (relative to ~/.config). Keeping the list
# broad would be wrong: other tools that later touch a file they generated
# (like waypaper) would silently freeze the configuration.
# Same list as python/hyprsetup/apply.py:PROTECTED_TARGETS.
# shellcheck disable=SC2034  # read in another file (a sourced library)
PROTECTED_TARGETS=(
    "hypr/monitors.conf" "hypr/workspaces.conf"
    "hypr/hyprland/monitors.lua" "hypr/hyprland/workspaces.lua"
)

# foreign_config_owner <file> — prints the tool's name if ANOTHER tool generated the file.
#
# nwg-displays puts this line at the top of the file it generates:
#   "# Generated by nwg-displays on 2026-09-23 at 10:50:44. Do not edit manually."
# Overwriting such a file silently wipes the display layout the user made with
# that tool — that was exactly the source of the "my display settings reset on
# every settings change" complaint.
#
# Applies the SAME rule as python/hyprsetup/apply.py:foreign_owner; if one
# changes the other must too (tools/test.sh compares them).
foreign_config_owner() {
    local file="$1" head name
    [[ -f "$file" ]] || return 0
    head=$(head -c 4096 "$file" 2>/dev/null) || return 0
    [[ "$head" == *"$OWNER_MARK"* ]] && return 0
    name=$(printf '%s\n' "$head" \
        | grep -im1 -oE 'generated by[[:space:]]+[A-Za-z0-9][A-Za-z0-9._+-]*' \
        | awk '{print $3}')
    [[ -z "$name" ]] && return 0
    [[ "${name,,}" == hyprsetup* ]] && return 0
    printf '%s\n' "$name"
}

# ---------------------------------------------------------------- helpers --
have()        { command -v "$1" >/dev/null 2>&1; }

# -------------------------------------------------------------- initramfs --
# Regenerating the initramfs takes minutes. More than one component
# (nvidia, plymouth) may touch mkinitcpio.conf; if each made its own
# "mkinitcpio -P" call, the same work would be done twice. Instead the
# hooks only mark it "dirty", and generation runs ONCE at the very end.
INITRAMFS_DIRTY=0
INITRAMFS_REASONS=()

# The system's initramfs tool: mkinitcpio (Arch default) or dracut
# (selectable on CachyOS). If both are installed, check which config is
# in use: dracut installs usually have no mkinitcpio.conf.
initramfs_tool() {
    if have mkinitcpio && [[ -f /etc/mkinitcpio.conf ]]; then
        printf 'mkinitcpio'
    elif have dracut; then
        printf 'dracut'
    fi
}

# system_snapshot <reason> — a filesystem snapshot taken once, BEFORE the first
# touch of system files (snapper root config or timeshift).
# The NVIDIA/Plymouth/initramfs/login manager steps can break booting; the
# snapshot allows going back from the boot loader menu or with "snapper rollback".
# Skipped if no tool is available or SNAPSHOT_BEFORE_SYSTEM=false;
# the install does not stop if it fails. (Python counterpart: snapshot.py)
SNAPSHOT_TAKEN=0
system_snapshot() {
    ((SNAPSHOT_TAKEN)) && return 0
    [[ "${SNAPSHOT_BEFORE_SYSTEM:-auto}" == false ]] && return 0
    root_ops_allowed || return 0
    SNAPSHOT_TAKEN=1
    local desc="Souprland: $1" cmd=()
    if have snapper && [[ -e /etc/snapper/configs/root ]]; then
        cmd=(snapper -c root create -t single -c number -d "$desc")
    elif have timeshift; then
        cmd=(timeshift --create --scripted --comments "$desc")
    else
        debug "no snapshot tool (snapper/timeshift) — skipped"
        return 0
    fi
    step "Snapshot before the system changes (${cmd[0]}): $1"
    run sudo "${cmd[@]}" || warn "Could not take a snapshot; the install continues."
    return 0
}

mark_initramfs_dirty() {   # <reason>
    INITRAMFS_DIRTY=1
    INITRAMFS_REASONS+=("$1")
}

regenerate_initramfs_if_needed() {
    ((INITRAMFS_DIRTY)) || return 0
    root_ops_allowed || { warn "initramfs not regenerated (--configs-only)"; return 0; }

    info "Regenerating initramfs"
    local reason
    for reason in "${INITRAMFS_REASONS[@]}"; do
        step "reason: $reason"
    done
    step "This may take a few minutes"
    local tool cmd=()
    tool=$(initramfs_tool)
    case "$tool" in
        mkinitcpio) cmd=(mkinitcpio -P) ;;
        dracut)     cmd=(dracut --regenerate-all --force) ;;
        *)
            warn "No initramfs tool found (mkinitcpio/dracut) — regenerate it manually."
            return 1 ;;
    esac
    if ! run sudo "${cmd[@]}"; then
        err "$tool failed."
        warn "IMPORTANT: Run it manually and fix the error BEFORE rebooting:"
        warn "    sudo ${cmd[*]}"
        return 1
    fi
    # limine-entry-tool (CachyOS's limine setup) COPIES the kernel and initramfs
    # to the EFI partition and reads the command line from /etc/default/limine;
    # the new initramfs and cmdline only reach the boot after that. It must run
    # AFTER generation; if it runs before, the old initramfs is copied.
    if have limine-update; then
        step "Updating limine entries (limine-update)"
        run sudo limine-update || warn "limine-update failed — run it manually: sudo limine-update"
    fi
    ok "initramfs updated"
    warn "A reboot is required for the changes to take effect."
    return 0
}

# expand_tilde <path> — replaces a leading "~" with $HOME, prints the result.
#
# Bash does not expand a tilde inside quotes: a file operation on
# "~/Pictures/x.png" creates a real folder NAMED "~" in the working dir
# (that is exactly what the ./~/Pictures/wallpapers/ leftover in the repo was).
#
# config_load expands the value from the settings file once, but that is not
# enough: tools/build-dotfiles.sh deliberately assigns a literal "~" AFTER
# config_load so the building machine's home dir is not baked into the output
# files. That value must reach the templates (hyprpaper/hyprlock expand the
# tilde themselves), but must never enter a file operation raw. So expansion
# happens not in one place but EVERYWHERE WALLPAPER_PATH is actually used as a file.
expand_tilde() {
    local path="$1"
    # shellcheck disable=SC2088  # pattern: recognize a path starting with a literal ~
    case "$path" in
        "~"|"~/"*) printf '%s' "$HOME${path#\~}" ;;
        *)         printf '%s' "$path" ;;
    esac
}

# wallpaper_file — the form of WALLPAPER_PATH to use in file operations.
wallpaper_file() {
    expand_tilde "${WALLPAPER_PATH:-$HOME/Pictures/wallpapers/wallpaper.png}"
}

# Steps that need root are not run in --configs-only mode.
root_ops_allowed() { [[ "${SKIP_PACKAGES:-0}" != 1 ]]; }
require_cmd() { have "$1" || die "Required command not found: $1"; }

# in_list <needle> <list...>
in_list() {
    local needle="$1"; shift
    local item
    for item in "$@"; do [[ "$item" == "$needle" ]] && return 0; done
    return 1
}

# join_by <separator> <items...>
join_by() {
    local sep="$1"; shift
    local out=""
    (($# == 0)) && return 0
    out="$1"; shift
    for item in "$@"; do out+="$sep$item"; done
    printf '%s' "$out"
}
