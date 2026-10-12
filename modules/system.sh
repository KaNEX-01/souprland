# shellcheck shell=bash
# modules/system.sh — hardware, audio, network and system-level settings

hook_nvidia() {
    root_ops_allowed || { warn "NVIDIA kernel settings skipped (--configs-only)"; return 0; }
    warn "NVIDIA + Wayland needs kernel module settings."
    if confirm "Set nvidia_drm.modeset=1 and the mkinitcpio modules?" y; then
        system_snapshot "NVIDIA kernel settings"
        # Without DRM KMS, Hyprland does not start on NVIDIA.
        run sudo install -Dm644 /dev/stdin /etc/modprobe.d/nvidia.conf <<<'options nvidia_drm modeset=1 fbdev=1'

        if [[ "$(initramfs_tool)" == dracut ]]; then
            # dracut: the modules are added to the initramfs with a drop-in.
            if [[ ! -f /etc/dracut.conf.d/hyprsetup-nvidia.conf ]]; then
                step "Adding the nvidia modules to dracut"
                run sudo install -Dm644 /dev/stdin /etc/dracut.conf.d/hyprsetup-nvidia.conf \
                    <<<'add_drivers+=" nvidia nvidia_modeset nvidia_uvm nvidia_drm "'
                mark_initramfs_dirty "NVIDIA kernel modules"
            fi
        elif [[ -f /etc/mkinitcpio.conf ]] && ! grep -q 'nvidia_drm' /etc/mkinitcpio.conf; then
            backup_path /etc/mkinitcpio.conf
            step "Adding the nvidia modules to the mkinitcpio MODULES line"
            run sudo sed -i -E \
                's/^MODULES=\((.*)\)/MODULES=(\1 nvidia nvidia_modeset nvidia_uvm nvidia_drm)/' \
                /etc/mkinitcpio.conf
            run sudo sed -i -E 's/MODULES=\( +/MODULES=(/' /etc/mkinitcpio.conf
            # Generation does not happen here but once after all hooks are
            # done — plymouth may touch the same file too, and generating the
            # initramfs twice would waste minutes (see lib/core.sh).
            mark_initramfs_dirty "NVIDIA kernel modules"
        fi
    fi
}

# --------------------------------------------------------------- plymouth --
# Boot animation. It touches three separate places and ALL THREE are needed;
# if one is missing nothing shows up and the reason is written nowhere:
#
#   1. "plymouth" in mkinitcpio HOOKS — puts the animation into the initramfs
#   2. "quiet splash" on the kernel command line — hides kernel messages
#   3. plymouth-set-default-theme — which theme to draw
#
# The kernel command line DEPENDS ON THE BOOTLOADER and this is the risky part:
# a wrong edit can leave the machine unbootable. So only bootloaders that are
# recognized for sure are edited; for an unrecognized one the manual steps are
# printed and no file is touched.

_plymouth_add_hook() {
    if [[ "$(initramfs_tool)" == dracut ]]; then
        # dracut: the plymouth module is added with a drop-in.
        if [[ -f /etc/dracut.conf.d/hyprsetup-plymouth.conf ]]; then
            step "dracut already includes the plymouth module"
            return 0
        fi
            step "Adding the plymouth module to dracut"
        run sudo install -Dm644 /dev/stdin /etc/dracut.conf.d/hyprsetup-plymouth.conf \
            <<<'add_dracutmodules+=" plymouth "'
        mark_initramfs_dirty "Plymouth boot animation"
        return 0
    fi
    [[ -f /etc/mkinitcpio.conf ]] || { warn "no mkinitcpio.conf — could not add the plymouth hook."; return 1; }
    if grep -qE '^HOOKS=.*\bplymouth\b' /etc/mkinitcpio.conf; then
        step "mkinitcpio HOOKS already includes plymouth"
        return 0
    fi

    backup_path /etc/mkinitcpio.conf
    # plymouth must come AFTER device management. If the install uses a
    # systemd-based initramfs it is added after the "systemd" hook, if classic
    # after "udev"; if neither is present it is not safe to touch.
    if grep -qE '^HOOKS=.*\bsystemd\b' /etc/mkinitcpio.conf; then
        step "mkinitcpio HOOKS: adding plymouth after systemd"
        run sudo sed -i -E 's/^(HOOKS=\(.*\bsystemd\b)/\1 plymouth/' /etc/mkinitcpio.conf
    elif grep -qE '^HOOKS=.*\budev\b' /etc/mkinitcpio.conf; then
        step "mkinitcpio HOOKS: adding plymouth after udev"
        run sudo sed -i -E 's/^(HOOKS=\(.*\budev\b)/\1 plymouth/' /etc/mkinitcpio.conf
    else
        warn "systemd/udev not found in the HOOKS line — plymouth must be added manually:"
        warn "    /etc/mkinitcpio.conf → HOOKS=(... udev plymouth ...)"
        return 1
    fi
    mark_initramfs_dirty "Plymouth boot animation"
    return 0
}

# Adds "quiet splash" to the kernel command line. Returns 0 on success.
_plymouth_add_cmdline() {
    local params="quiet splash"

    # --- GRUB ---------------------------------------------------------
    if [[ -f /etc/default/grub ]] && have grub-mkconfig; then
        if grep -qE '^GRUB_CMDLINE_LINUX_DEFAULT=.*\bsplash\b' /etc/default/grub; then
            step "The GRUB command line already includes 'splash'"
            return 0
        fi
        backup_path /etc/default/grub
            step "Adding '$params' to GRUB_CMDLINE_LINUX_DEFAULT"
        # Appended to the end of the existing value; existing parameters are kept.
        #
        # The quote type may be SINGLE or DOUBLE — CachyOS's default
        # /etc/default/grub uses single quotes. An expression that only
        # matches double quotes silently does nothing on such a system, then
        # grub-mkconfig runs for nothing and the animation never shows up. The
        # opening quote is bound to \2 and matched with a backreference at the
        # end, so the type is preserved and mixed quotes do not match.
        run sudo sed -i -E \
            "s/^(GRUB_CMDLINE_LINUX_DEFAULT=([\"']))(.*)\\2\$/\\1\\3 $params\\2/" \
            /etc/default/grub
        # If the value was empty, strip the extra leading space.
        run sudo sed -i -E \
            "s/^(GRUB_CMDLINE_LINUX_DEFAULT=([\"']))  */\\1/" \
            /etc/default/grub

        local cfg=/boot/grub/grub.cfg
        [[ -f /boot/grub2/grub.cfg ]] && cfg=/boot/grub2/grub.cfg
        step "Regenerating the GRUB config: $cfg"
        if ! run sudo grub-mkconfig -o "$cfg"; then
            err "grub-mkconfig failed — /etc/default/grub must be restored from the backup."
            warn "Backup: $BACKUP_DIR"
            return 1
        fi
        return 0
    fi

    # --- limine (limine-entry-tool: CachyOS's default) ------------------
    # limine.conf is GENERATED by this tool; manual edits are wiped on the first
    # kernel update. The command line is read from /etc/default/limine:
    # "KERNEL_CMDLINE[default]+=" appends to the END of the existing parameters
    # and changes nothing. The entries are refreshed with limine-update after
    # initramfs generation (see lib/core.sh:regenerate_initramfs_if_needed).
    if have limine-update; then
        local limine_default=/etc/default/limine
        if grep -qE '^KERNEL_CMDLINE\[default\].*\bsplash\b' "$limine_default" 2>/dev/null \
                || grep -qw splash /proc/cmdline 2>/dev/null; then
            step "The limine command line already includes 'splash'"
            return 0
        fi
        [[ -f "$limine_default" ]] && backup_path "$limine_default"
        step "$limine_default: adding '$params' to KERNEL_CMDLINE[default]"
        printf '\n# hyprsetup: Plymouth boot animation\nKERNEL_CMDLINE[default]+=%s\n' "$params" \
            | run sudo tee -a "$limine_default" >/dev/null \
            || { warn "Could not write $limine_default."; return 1; }
        mark_initramfs_dirty "kernel command line (limine)"
        return 0
    fi

    # --- systemd-boot -------------------------------------------------
    # CachyOS's systemd-boot-manager REGENERATES the entries from LINUX_OPTIONS
    # in /etc/sdboot-manage.conf: editing the entry files manually would be
    # wiped on the first kernel update.
    if [[ -f /etc/sdboot-manage.conf ]] && have sdboot-manage; then
        if grep -qE '^LINUX_OPTIONS=.*\bsplash\b' /etc/sdboot-manage.conf; then
            step "sdboot-manage LINUX_OPTIONS already includes 'splash'"
            return 0
        fi
        backup_path /etc/sdboot-manage.conf
        step "Adding '$params' to sdboot-manage LINUX_OPTIONS"
        run sudo sed -i -E \
            "s/^(LINUX_OPTIONS=([\"']))(.*)\\2\$/\\1\\3 $params\\2/" \
            /etc/sdboot-manage.conf
        if ! grep -qE '^LINUX_OPTIONS=' /etc/sdboot-manage.conf; then
            printf 'LINUX_OPTIONS="%s"\n' "$params" \
                | run sudo tee -a /etc/sdboot-manage.conf >/dev/null
        fi
        run sudo sdboot-manage gen || warn "sdboot-manage gen failed — run it manually."
        return 0
    fi

    # If /etc/kernel/cmdline is the single source (UKI setups), it is edited there.
    if [[ -f /etc/kernel/cmdline ]]; then
        if grep -q '\bsplash\b' /etc/kernel/cmdline; then
            step "/etc/kernel/cmdline already includes 'splash'"
            return 0
        fi
        backup_path /etc/kernel/cmdline
        step "Adding '$params' to /etc/kernel/cmdline"
        run sudo sed -i -E "s/\$/ $params/" /etc/kernel/cmdline
        mark_initramfs_dirty "kernel command line (UKI)"
        return 0
    fi

    # systemd-boot entries: the "options" line in each .conf.
    if [[ -d /boot/loader/entries ]]; then
        local entry touched=0
        for entry in /boot/loader/entries/*.conf; do
            [[ -f "$entry" ]] || continue
            grep -q '^options' "$entry" || continue
            grep -qE '^options.*\bsplash\b' "$entry" && continue
            backup_path "$entry"
            run sudo sed -i -E "s/^(options.*)\$/\1 $params/" "$entry"
            touched=1
        done
        if ((touched)); then
            step "Added '$params' to the systemd-boot entries"
        else
            step "The systemd-boot entries already include 'splash'"
        fi
        return 0
    fi

    # --- unrecognized --------------------------------------------------
    warn "Bootloader not recognized — the kernel command line was NOT TOUCHED."
    warn "For the boot animation to show, add this manually: $params"
    warn "  limine  : /etc/default/limine → KERNEL_CMDLINE[default]+=$params"
    warn "            (without limine-entry-tool: the 'cmdline' line in /boot/limine.conf)"
    warn "  rEFInd  : /boot/refind_linux.conf"
    return 1
}

hook_plymouth() {
    root_ops_allowed || { warn "Plymouth settings skipped (--configs-only) — needs sudo"; return 0; }
    have plymouth-set-default-theme || { warn "plymouth could not be installed — skipping."; return 0; }

    warn "Plymouth touches the boot process (initramfs and kernel command line)."
    confirm "Install the boot animation?" y || { step "Plymouth skipped"; return 0; }
    system_snapshot "Plymouth boot animation"

    _plymouth_add_hook || return 0

    local theme="${PLYMOUTH_THEME:-spinner}" themes
    # The list is captured into a variable first: "--list | grep -q" under
    # pipefail counted as a failure with SIGPIPE (141) when grep exited early,
    # and every installed theme fell back to spinner as "not found".
    themes=$(plymouth-set-default-theme --list 2>/dev/null)
    if ! grep -qx -- "$theme" <<<"$themes"; then
        warn "Plymouth theme not found: $theme — falling back to 'spinner'."
        warn "Installed themes: $(tr '\n' ' ' <<<"$themes")"
        theme="spinner"
    fi
    step "Plymouth theme: $theme"
    # -R regenerates the initramfs itself; since we manage the one-time
    # generation ourselves, -R is NOT USED (otherwise it would be generated twice).
    run sudo plymouth-set-default-theme "$theme" \
        || warn "Could not set the theme: $theme"
    mark_initramfs_dirty "Plymouth theme ($theme)"

    _plymouth_add_cmdline || true
    return 0
}

hook_pipewire() {
    # PipeWire units are socket-activated; check for a PulseAudio conflict
    # that may need to be disabled.
    if systemctl --user is-enabled pulseaudio.service >/dev/null 2>&1; then
        warn "pulseaudio.service is enabled — it conflicts with PipeWire."
        if confirm "Disable pulseaudio?" y; then
            run systemctl --user disable --now pulseaudio.service pulseaudio.socket || true
        fi
    fi
    enable_user_service "pipewire.service"
    enable_user_service "pipewire-pulse.service"
    enable_user_service "wireplumber.service"
}

hook_bluetooth() {
    # Without Bluetooth hardware there is no point enabling the service.
    if ! grep -qi bluetooth <<<"$(lsusb 2>/dev/null)" && [[ ! -d /sys/class/bluetooth ]]; then
        warn "No Bluetooth hardware found, the service will be enabled anyway."
    fi
}

hook_xdg_dirs() {
    step "Creating XDG user directories"
    run xdg-user-dirs-update || warn "Could not run xdg-user-dirs-update."
}

hook_clipboard() {
    :  # cliphist is started via exec-once in hyprland.conf
}

hook_power() {
    # On CachyOS, if TLP is installed it conflicts with power-profiles-daemon.
    if systemctl is-enabled tlp.service >/dev/null 2>&1; then
        warn "tlp.service is enabled — it conflicts with power-profiles-daemon."
        SKIP_SERVICES+=("power-profiles-daemon.service")
    fi
}
