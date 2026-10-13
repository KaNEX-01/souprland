# shellcheck shell=bash
# preflight.sh — pre-install system checks and installation of prerequisite tools

[[ -n "${_PREFLIGHT_SH_LOADED:-}" ]] && return 0
_PREFLIGHT_SH_LOADED=1

# Minimum packages the script itself needs to run.
BOOTSTRAP_PKGS=(git base-devel jq python)

preflight_check_root() {
    if [[ "$EUID" -eq 0 ]]; then
        die "This script must not be run as root. Run it as a regular user; sudo will be used where needed."
    fi
    if ! have sudo; then
        die "sudo is not installed. First install it with 'pacman -S sudo' and add your user to the wheel group."
    fi
}

preflight_check_distro() {
    local id="" id_like=""
    if [[ -r /etc/os-release ]]; then
        # shellcheck disable=SC1091
        id=$(. /etc/os-release && printf '%s' "${ID:-}")
        id_like=$(. /etc/os-release && printf '%s' "${ID_LIKE:-}")
    fi
    step "Distribution: ${id:-unknown}"
    if [[ "$id" != "arch" && "$id" != "cachyos" && "$id_like" != *arch* ]]; then
        warn "Could not detect an Arch-based system (ID=$id)."
        # --dry-run only reports: stopping here would hide the rest of the plan.
        [[ "${DRY_RUN:-0}" == 1 ]] || confirm "Continue anyway?" n || die "Installation cancelled."
    fi
    have pacman || die "pacman not found — this script is only for Arch-based systems."
}

preflight_check_network() {
    step "Checking network connection"
    if ! timeout 8 curl -fsS -o /dev/null https://archlinux.org 2>/dev/null &&
       ! timeout 8 ping -c1 -W3 archlinux.org >/dev/null 2>&1; then
        die "There seems to be no internet connection. Check the connection and try again."
    fi
    ok "Network connection available"
}

preflight_check_disk() {
    local avail_mb
    avail_mb=$(df -Pm "$HOME" | awk 'NR==2 {print $4}')
    step "Free disk space: ${avail_mb} MB"
    if (( avail_mb < 3000 )); then
        warn "Less than 3 GB of free space. AUR builds may fail."
        [[ "${DRY_RUN:-0}" == 1 ]] || confirm "Continue?" n || die "Installation cancelled."
    fi
}

preflight_check_gpu() {
    local gpu
    gpu=$(lspci 2>/dev/null | grep -iE 'vga|3d controller' || true)
    [[ -z "$gpu" ]] && return 0
    debug "GPU: $gpu"
    if grep -qi nvidia <<<"$gpu"; then
        HAS_NVIDIA=1
        warn "NVIDIA GPU detected — Hyprland needs extra environment variables."
        warn "If the 'nvidia' component is selected, the required env settings are written automatically."
    fi
    grep -qi 'amd\|radeon' <<<"$gpu" && HAS_AMD=1
    grep -qi intel      <<<"$gpu" && HAS_INTEL=1
    export HAS_NVIDIA="${HAS_NVIDIA:-0}" HAS_AMD="${HAS_AMD:-0}" HAS_INTEL="${HAS_INTEL:-0}"
}

# If another pacman/AUR operation is running, the install blows up halfway; warn first.
preflight_check_pacman_lock() {
    [[ -e /var/lib/pacman/db.lck ]] || return 0
    warn "The pacman database is locked (/var/lib/pacman/db.lck)."
    warn "Another package operation may be running (pacman, paru, pamac…)."
    if pgrep -x pacman >/dev/null 2>&1 || pgrep -x paru >/dev/null 2>&1; then
        die "A package operation is running. Wait for it to finish and try again."
    fi
    warn "No running pacman process is visible — the lock may be left over"
    warn "from an interrupted operation. If unsure, cancel."
    if confirm "Remove the lock file?" n; then
        run sudo rm -f /var/lib/pacman/db.lck || die "Could not remove the lock."
    else
        die "Installation cancelled."
    fi
}

# In virtual machines the display driver may not offer the DRM capabilities
# Hyprland expects; warn the user before they hit a black screen after install.
preflight_check_virt() {
    have systemd-detect-virt || return 0
    local virt
    # CAUTION: on bare metal systemd-detect-virt PRINTS "none" and EXITS
    # with 1. A "|| printf 'none'" here appended a second "none" to the
    # captured output, making virt="none\nnone", so the "== none" check below
    # missed: every physical machine said "virtual machine detected" and got
    # the blur/shadow warning. "|| true" adds nothing; it only keeps set -e
    # from killing the install on a failed assignment.
    virt=$(systemd-detect-virt 2>/dev/null || true)
    if [[ -z "$virt" || "$virt" == none ]]; then
        return 0
    fi

    step "Virtual machine detected: $virt"
    case "$virt" in
        oracle)
            warn "VirtualBox does not support the atomic modesetting Hyprland"
            warn "needs — the session will most likely stay on a black screen"
            warn "('getCurrentCRTC: No CRTC' errors). QEMU/KVM + virtio-gpu is recommended."
            ;;
        vmware)
            warn "The VMware svga driver is problematic with Hyprland; if you have issues,"
            warn "try software rendering: WLR_RENDERER_ALLOW_SOFTWARE=1 Hyprland"
            ;;
        kvm|qemu)
            step "QEMU/KVM: the graphics card should be 'virtio-gpu' (3D acceleration on)."
            ;;
    esac
    warn "Blur and shadows are heavy in a virtual machine; after install, turn"
    warn "them off in the settings app:  MOD+I → Decoration → Blur/Shadow"
}

# On Arch, installing packages after 'pacman -Sy' is a "partial upgrade": a
# package from the new database may not match the old libraries on the system
# and the system can break. The right way is a full upgrade (-Syu).
#
# Pending updates are counted AFTER the database is REFRESHED. It used to run
# "pacman -Qu" first, i.e. against a local database that could be days old:
# it said "0 updates" and then did -Sy + -S, silently causing a partial
# upgrade.
preflight_sync_db() {
    local updates=0
    step "Updating the package database (pacman -Sy)"
    run sudo pacman -Sy --noconfirm || warn "Could not update the package database."
    updates=$(pacman -Qu 2>/dev/null | wc -l || true)

    if ((updates > 0)); then
        warn "The system has $updates pending updates."
        warn "Updating only the database and installing packages (partial upgrade)"
        warn "is unsupported on Arch and can break the system."
        if confirm "Fully upgrade the system (pacman -Syu)?" y; then
            step "Upgrading the system (pacman -Syu) — this may take a while"
            run_visible sudo pacman -Syu --noconfirm \
                || die "Could not upgrade the system. Run 'sudo pacman -Syu' manually and try again."
            ok "System is up to date"
            return 0
        fi
        warn "Full upgrade skipped — this IS A PARTIAL UPGRADE: you may see dependency"
        warn "errors during install, and system libraries may not match."
    fi
}

preflight_bootstrap_tools() {
    local missing=()
    local pkg
    for pkg in "${BOOTSTRAP_PKGS[@]}"; do
        pacman -T "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
    done
    if ((${#missing[@]})); then
        step "Installing prerequisite packages: ${missing[*]}"
        run sudo pacman -S --needed --noconfirm "${missing[@]}" \
            || die "Could not install prerequisite packages: ${missing[*]}"
    fi
    ok "Prerequisite tools ready"
}

# Detect the AUR helper; if there is none, build paru from source.
preflight_aur_helper() {
    if [[ -n "${AUR_HELPER:-}" && "$AUR_HELPER" != auto ]]; then
        have "$AUR_HELPER" || die "The specified AUR helper was not found: $AUR_HELPER"
        ok "AUR helper: $AUR_HELPER (from config)"
        export AUR_HELPER
        return 0
    fi
    local candidate
    for candidate in paru yay pikaur trizen; do
        if have "$candidate"; then
            AUR_HELPER="$candidate"
            ok "AUR helper: $AUR_HELPER"
            export AUR_HELPER
            return 0
        fi
    done

    warn "No installed AUR helper found."
    confirm "Build and install paru from source?" y || {
        AUR_HELPER=""
        export AUR_HELPER
        warn "AUR packages will be skipped."
        return 0
    }
    local tmp
    tmp=$(mktemp -d)
    run git clone --depth=1 https://aur.archlinux.org/paru-bin.git "$tmp/paru-bin" \
        || { rm -rf "$tmp"; die "Could not clone the paru-bin repository."; }

    # As with AUR packages (lib/packages.sh:aur_helper_flags), the build script
    # is shown FIRST: paru-bin is also an unsigned AUR submission and makepkg
    # runs every line of it as your user.
    if [[ "${AUR_REVIEW:-true}" != false && "${DRY_RUN:-0}" != 1 \
          && -r "$tmp/paru-bin/PKGBUILD" ]]; then
        info "paru-bin PKGBUILD (aur.archlinux.org/packages/paru-bin):"
        sed 's/^/    /' "$tmp/paru-bin/PKGBUILD"
        confirm "You have reviewed the PKGBUILD — build and install paru?" y || {
            rm -rf "$tmp"
            AUR_HELPER=""
            export AUR_HELPER
            warn "paru not installed — AUR packages will be skipped."
            return 0
        }
    fi

    step "Building paru (this may take a few minutes)"
    # In --dry-run the clone was only printed and the dir does not exist: show without cd.
    if [[ "${DRY_RUN:-0}" == 1 ]]; then
        run makepkg -si --noconfirm
    else
        ( cd "$tmp/paru-bin" && run makepkg -si --noconfirm ) \
            || { rm -rf "$tmp"; die "Could not build paru."; }
    fi
    rm -rf "$tmp"
    AUR_HELPER=paru
    export AUR_HELPER
    ok "paru installed"
}

# Resolves HYPR_LANG=auto to conf/lua based on the installed Hyprland version.
# On the 'main' branch of Hyprland's main repo heading to 0.57, the hyprlang .conf
# parser was removed entirely (see the note in lib/config.sh); so 0.57+ and
# 'hyprland-git' builds are routed to lua.
#
# The result is written to HYPR_LANG_RESOLVED — HYPR_LANG itself is
# DELIBERATELY left untouched (since it is in CONFIG_VARS, config_save writes
# it as-is — usually 'auto' — to settings.conf; so when Hyprland is upgraded
# the next --reapply can detect it again).
# render_export_vars (lib/render.sh) passes HYPR_LANG_RESOLVED to the
# templates under the name HYPR_LANG.
preflight_detect_hypr_lang() {
    if [[ "${HYPR_LANG:-auto}" != auto ]]; then
        HYPR_LANG_RESOLVED="$HYPR_LANG"
        step "Hyprland config language: $HYPR_LANG_RESOLVED (set manually)"
        export HYPR_LANG_RESOLVED
        return 0
    fi

    local ver=""
    if have hyprctl; then
        # Without a running session 'hyprctl version' returns an error code —
        # guarded so it does not kill the script under set -e/pipefail
        # (see the same pattern in preflight_sync_db).
        ver=$(hyprctl version 2>/dev/null | awk '/^Hyprland/{print $2; exit}' || true)
    fi
    if [[ -z "$ver" ]] && have pacman; then
        if pacman -Qq hyprland-git >/dev/null 2>&1; then
            ver="99.99.99"     # git build: main branch, lua assumed mandatory
        else
            ver=$(pacman -Q hyprland 2>/dev/null | awk '{print $2}' || true)
        fi
    fi
    ver="${ver#v}"; ver="${ver%%-*}"

    if [[ -z "$ver" ]]; then
        HYPR_LANG_RESOLVED=conf
        debug "Could not detect the Hyprland version — default: HYPR_LANG=conf"
        export HYPR_LANG_RESOLVED
        return 0
    fi

    local major minor
    IFS='.' read -r major minor _ <<<"$ver"
    major="${major:-0}"; minor="${minor:-0}"
    [[ "$major" =~ ^[0-9]+$ ]] || major=0
    [[ "$minor" =~ ^[0-9]+$ ]] || minor=0

    if (( major >= 1 || (major == 0 && minor >= 57) )); then
        HYPR_LANG_RESOLVED=lua
        warn "Hyprland $ver detected — a Lua config will be generated (see README, experimental)"
    else
        HYPR_LANG_RESOLVED=conf
        step "Hyprland $ver detected — a classic .conf config will be generated"
    fi
    export HYPR_LANG_RESOLVED
}

# The install writes under these directories at the very end (configs, the
# settings app in ~/.local/bin). A directory left owned by root (e.g. created by
# an earlier "sudo" command) used to surface only as a bare "Permission denied"
# after the whole package install; catch it before anything is touched.
preflight_check_home_writable() {
    local d probe bad=()
    for d in "$HOME/.config" "$HOME/.local/bin" "$HOME/.local/share" \
             "$HOME/.local/state" "$HOME/.cache"; do
        probe="$d"
        while [[ ! -e "$probe" ]]; do probe="$(dirname -- "$probe")"; done
        [[ -w "$probe" ]] || bad+=("$probe")
    done
    ((${#bad[@]})) || return 0
    for d in "${bad[@]}"; do err "Not writable by $USER: $d (owner: $(stat -c %U -- "$d"))"; done
    err "Fix the ownership and run the installer again:"
    err "    sudo chown -R $USER: ${bad[*]}"
    [[ "${DRY_RUN:-0}" == 1 ]] && return 0
    die "Your home directory has folders you cannot write to."
}

preflight_run_all() {
    info "Preflight checks"
    preflight_check_root
    preflight_check_distro
    preflight_check_home_writable
    preflight_check_gpu
    preflight_check_virt
    preflight_detect_hypr_lang

    # In --configs-only mode no packages are installed; in that case root is
    # not needed either and sudo is never requested.
    if [[ "${SKIP_PACKAGES:-0}" == 1 ]]; then
        step "Only configs will be generated — skipping package steps and sudo"
        require_cmd jq
        require_cmd python3
        ok "Preflight checks done"
        return 0
    fi

    preflight_check_network
    preflight_check_disk
    preflight_check_pacman_lock
    sudo_init
    preflight_sync_db
    preflight_bootstrap_tools
    preflight_aur_helper
}
