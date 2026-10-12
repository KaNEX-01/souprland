# shellcheck shell=bash
# packages.sh — catalog queries and package install helpers

[[ -n "${_PACKAGES_SH_LOADED:-}" ]] && return 0
_PACKAGES_SH_LOADED=1

CATALOG="${CATALOG:-$SETUP_ROOT/config/components.json}"

FAILED_PKGS=()
INSTALLED_PKGS=()
SKIPPED_PKGS=()
# Packages the user excluded with PKG_SKIP.
EXCLUDED_PKGS=()
# Packages not built because of the COMPILE policy.
NOT_COMPILED_PKGS=()

# ------------------------------------------------------------- catalog ------
catalog_query() { jq -r "$1" "$CATALOG"; }

catalog_validate() {
    [[ -r "$CATALOG" ]] || die "Could not read the component catalog: $CATALOG"
    jq -e . "$CATALOG" >/dev/null 2>&1 || die "The component catalog is not valid JSON: $CATALOG"
}

catalog_category_ids() { catalog_query '.categories[].id'; }

catalog_field() {  # <id> <field> -> plain text (line by line if an array)
    jq -r --arg id "$1" --arg f "$2" '
        .categories[].components[]
        | select(.id == $id)
        | .[$f]
        | if type == "array" then .[] elif . == null then empty else . end
    ' "$CATALOG"
}

catalog_title() { catalog_field "$1" title; }

# The component's .desktop entry (e.g. dolphin -> org.kde.dolphin.desktop).
# This is the single source for default app assignment; it returns empty
# for tools that run in a terminal (yazi). See python/hyprsetup/render.py →
# DEFAULT_APP_ROLES and modules/desktop.sh → apply_default_browser.
catalog_desktop() {
    [[ -n "${1:-}" ]] || return 0   # empty id: empty output too, not an error
    catalog_field "$1" desktop
}

catalog_exists() {
    jq -e --arg id "$1" 'any(.categories[].components[]; .id == $id)' "$CATALOG" >/dev/null 2>&1
}

catalog_profile_ids() {  # <profile name>
    jq -r --arg p "$1" '.profiles[$p] // empty | .[]' "$CATALOG"
}


# If the category is single-choice, gives the variable to write to (e.g. TERMINAL)
catalog_category_var() {  # <category id>
    jq -r --arg c "$1" '.categories[] | select(.id == $c) | .var // empty' "$CATALOG"
}

catalog_category_of() {  # <component id> -> category id
    jq -r --arg id "$1" \
        '.categories[] | select(any(.components[]; .id == $id)) | .id' "$CATALOG"
}

# ------------------------------------------------------ install state -------
# pacman -T (deptest) also counts "provides": renamed packages provide the old
# name (awww → swww, 7zip → p7zip). "pacman -Qq <name>" only finds the real
# package name, and such a component would look "not installed" forever.
pkg_installed() { pacman -T "$1" >/dev/null 2>&1; }

# ------------------------------------------ package exclusion / building ----
# PKG_SKIP may be separated by commas or spaces; we accept both.
pkg_skip_list() {
    [[ -n "${PKG_SKIP:-}" ]] || return 0
    printf '%s\n' "${PKG_SKIP//,/ }" | tr ' ' '\n' | awk 'NF'
}

pkg_is_excluded() {  # <package>
    local want="$1" entry
    while IFS= read -r entry; do
        [[ "$entry" == "$want" ]] && return 0
    done < <(pkg_skip_list)
    return 1
}

# Removes the PKG_SKIP entries from the list; records the excluded ones in EXCLUDED_PKGS.
filter_excluded_packages() {  # <package...> -> prints the remaining ones line by line
    local pkg
    for pkg in "$@"; do
        if pkg_is_excluded "$pkg"; then
            in_list "$pkg" "${EXCLUDED_PKGS[@]+"${EXCLUDED_PKGS[@]}"}" \
                || EXCLUDED_PKGS+=("$pkg")
        else
            printf '%s\n' "$pkg"
        fi
    done
}

# Can the package be installed WITHOUT BUILDING on this machine?
#   - AUR packages ending in "-bin" package a prebuilt binary, no build.
#   - If it is in a configured repo (e.g. if Chaotic-AUR was added), it comes
#     as a signed binary.
pkg_is_binary() {  # <package>
    [[ "$1" == *-bin ]] && return 0
    declare -F repo_has_package >/dev/null && repo_has_package "$1"
}

# Will the package be built from source? (installed ones do not count)
pkg_builds_from_source() {  # <package>
    pkg_installed "$1" && return 1
    pkg_is_binary "$1" && return 1
    return 0
}

# Signals to watch for during the build — they go into the report.
pkg_build_note() {  # <package>
    if [[ "$1" == *-bin ]]; then
        printf 'binary — no build'
    elif pkg_installed "$1"; then
        printf 'already installed'
    elif declare -F repo_has_package >/dev/null && repo_has_package "$1"; then
        printf 'signed binary in a repo — no build'
    elif [[ "$1" == *-git ]]; then
        printf -- '-git: not a fixed release, builds the latest code at that moment'
    else
        printf 'will be built from source'
    fi
}

# Collects the repo/aur package lists from the selected components.
collect_packages() {  # <field: repo|aur> <component id...>
    local field="$1"; shift
    local id pkg
    for id in "$@"; do
        while IFS= read -r pkg; do
            [[ -n "$pkg" ]] && printf '%s\n' "$pkg"
        done < <(catalog_field "$id" "$field")
    done | awk 'NF && !seen[$0]++'
}

# ---------------------------------------------------------- install ---------
# install_repo_packages <package...>
install_repo_packages() {
    (($# == 0)) && return 0
    local todo=() pkg
    # Packages the user excluded with PKG_SKIP are never tried.
    local kept=()
    mapfile -t kept < <(filter_excluded_packages "$@")
    set -- ${kept[0]+"${kept[@]}"}
    (($# == 0)) && { ok "All repo packages were excluded with PKG_SKIP"; return 0; }
    for pkg in "$@"; do
        if pkg_installed "$pkg"; then
            SKIPPED_PKGS+=("$pkg")
            debug "already installed: $pkg"
        else
            todo+=("$pkg")
        fi
    done
    if ((${#todo[@]} == 0)); then
        ok "All repo packages are already installed (${#SKIPPED_PKGS[@]} packages skipped)"
        return 0
    fi

    step "Installing repo packages (${#todo[@]}): ${todo[*]}"
    if run_visible sudo pacman -S --needed --noconfirm "${todo[@]}"; then
        INSTALLED_PKGS+=("${todo[@]}")
        ok "Repo packages installed"
        return 0
    fi

    # If the bulk install failed, try one by one; one package should not
    # stop the whole install.
    warn "Bulk install failed — packages will be tried one by one."
    for pkg in "${todo[@]}"; do
        if run sudo pacman -S --needed --noconfirm "$pkg"; then
            INSTALLED_PKGS+=("$pkg")
        else
            FAILED_PKGS+=("$pkg")
            warn "Could not install: $pkg"
        fi
    done
}

# Extra flags to pass to the AUR helper.
#
# "--skipreview" is PARU-SPECIFIC. It used to be passed unconditionally here, and
# since yay does not know it, yay said `invalid option 'skipreview'` and exited 1 —
# so on every system using yay, NONE of the AUR packages could be installed
# (that was the source of HyprPanel's "the panel never shows up" complaint: the
# package was never installed, so the exec-once command went nowhere).
#
# Also, review is now ON BY DEFAULT: the AUR hosts unsigned, community-
# submitted build scripts; building without seeing the PKGBUILD means
# accepting everything that script does without seeing it
# (e.g. ags-hyprpanel-git runs `npm install` during the build).
# AUR_REVIEW=false restores the old behavior.
aur_helper_flags() {  # <helper>
    local helper="$1"
    [[ "${AUR_REVIEW:-true}" != false ]] && return 0
    case "$helper" in
        paru)  printf '%s\n' --skipreview ;;
        yay)   printf '%s\n' --answerdiff=None --answeredit=None ;;
        *)     : ;;   # pikaur/trizen: no equivalent flag
    esac
}

# install_aur_packages <package...>
install_aur_packages() {
    (($# == 0)) && return 0
    if [[ -z "${AUR_HELPER:-}" ]]; then
        warn "No AUR helper — skipping these packages: $*"
        FAILED_PKGS+=("$@")
        return 0
    fi
    local kept=()
    mapfile -t kept < <(filter_excluded_packages "$@")
    set -- ${kept[0]+"${kept[@]}"}
    (($# == 0)) && { ok "All AUR packages were excluded with PKG_SKIP"; return 0; }

    local todo=() from_repo=() pkg
    for pkg in "$@"; do
        if pkg_installed "$pkg"; then
            SKIPPED_PKGS+=("$pkg")
        elif declare -F repo_has_package >/dev/null && repo_has_package "$pkg"; then
            # The package was found in a configured repo (e.g. in Chaotic-AUR
            # if it was added). Installing the signed binary is preferred over
            # building locally: the PKGBUILD's build step (`npm install` in
            # ags-hyprpanel-git) never runs on this machine.
            from_repo+=("$pkg")
        else
            todo+=("$pkg")
        fi
    done

    if ((${#from_repo[@]})); then
        step "Will be installed from a repo (instead of the AUR): ${from_repo[*]}"
        install_repo_packages "${from_repo[@]}"
    fi

    ((${#todo[@]} == 0)) && { ok "All AUR packages are already installed or came from a repo"; return 0; }

    # COMPILE policy — packages to be built from source are filtered here. "-bin"
    # and signed binaries from a repo do not count as builds and skip this gate.
    local build_ok=()
    for pkg in "${todo[@]}"; do
        if pkg_is_binary "$pkg"; then
            build_ok+=("$pkg")
            continue
        fi
        case "${COMPILE:-ask}" in
            always) build_ok+=("$pkg") ;;
            never)
                NOT_COMPILED_PKGS+=("$pkg")
                warn "COMPILE=never — not built: $pkg" ;;
            ask)
                # The note is only added if it carries extra info; repeating the
                # general "will be built from source" label from the report is pointless.
                local note=""
                [[ "$pkg" == *-git ]] && \
                    note=" — -git: not a fixed release, builds the latest code at that moment"
                warn "$pkg WILL BE BUILT from source on this machine$note"
                if confirm "Build $pkg?" y; then
                    build_ok+=("$pkg")
                else
                    NOT_COMPILED_PKGS+=("$pkg")
                    warn "Skipped (not built): $pkg"
                fi ;;
        esac
    done
    todo=(${build_ok[0]+"${build_ok[@]}"})
    if ((${#todo[@]} == 0)); then
        warn "No packages left to build — COMPILE=${COMPILE:-ask}"
        ((${#NOT_COMPILED_PKGS[@]})) && \
            warn "For signed binaries you can try CHAOTIC_AUR=true."
        return 0
    fi

    local extra=()
    mapfile -t extra < <(aur_helper_flags "$AUR_HELPER")

    step "Installing AUR packages (${#todo[@]}): ${todo[*]}"
    # Trust signals are shown BEFORE installing (see lib/chaotic.sh).
    declare -F aur_trust_report >/dev/null && aur_trust_report "${todo[@]}"
    if [[ "${AUR_REVIEW:-true}" != false ]]; then
        warn "These packages will be built from the AUR — unsigned, community submissions."
        warn "If your helper shows the PKGBUILD, do not approve it without reading."
    fi
    for pkg in "${todo[@]}"; do
        if run_visible "$AUR_HELPER" -S --needed --noconfirm \
                       ${extra[0]+"${extra[@]}"} "$pkg"; then
            INSTALLED_PKGS+=("$pkg")
            ok "AUR: $pkg"
        else
            FAILED_PKGS+=("$pkg")
            warn "Could not install AUR package: $pkg"
        fi
    done
}

# ------------------------------------------------------------- report -------
# packages_report — shows the selected components' packages BEFORE installing:
# which come from a signed repo, which will be built on this machine. The goal
# is to make the list behind the "20 repo · 3 AUR" count visible, so what is
# being said yes to can be read before making the build decision (COMPILE).
packages_report() {  # <component id...>
    local repo_pkgs=() aur_pkgs=() pkg
    mapfile -t repo_pkgs < <(collect_packages repo "$@")
    mapfile -t aur_pkgs  < <(collect_packages aur  "$@")

    local n_repo=0 n_src=0 n_excl=0 n_have=0

    printf '\n%sREPO (signed binaries)%s\n' "$C_BOLD" "$C_RESET"
    if ((${#repo_pkgs[@]} == 0)); then
        printf '  (none)\n'
    fi
    for pkg in ${repo_pkgs[0]+"${repo_pkgs[@]}"}; do
        if pkg_is_excluded "$pkg"; then
            printf '  %s%-28s excluded with PKG_SKIP%s\n' "$C_DIM" "$pkg" "$C_RESET"
            n_excl=$((n_excl + 1)); continue
        fi
        n_repo=$((n_repo + 1))
        if pkg_installed "$pkg"; then
            printf '  %-28s %salready installed%s\n' "$pkg" "$C_DIM" "$C_RESET"
            n_have=$((n_have + 1))
        else
            printf '  %-28s will be installed\n' "$pkg"
        fi
    done

    printf '\n%sAUR%s\n' "$C_BOLD" "$C_RESET"
    if ((${#aur_pkgs[@]} == 0)); then
        printf '  (none)\n'
    fi
    for pkg in ${aur_pkgs[0]+"${aur_pkgs[@]}"}; do
        if pkg_is_excluded "$pkg"; then
            printf '  %s%-28s excluded with PKG_SKIP%s\n' "$C_DIM" "$pkg" "$C_RESET"
            n_excl=$((n_excl + 1)); continue
        fi
        local note; note="$(pkg_build_note "$pkg")"
        if pkg_installed "$pkg"; then
            printf '  %-28s %s%s%s\n' "$pkg" "$C_DIM" "$note" "$C_RESET"
            n_have=$((n_have + 1))
        elif pkg_builds_from_source "$pkg"; then
            printf '  %-28s %s%s%s\n' "$pkg" "$C_YELLOW" "$note" "$C_RESET"
            n_src=$((n_src + 1))
        else
            printf '  %-28s %s\n' "$pkg" "$note"
        fi
    done

    printf '\n%sSummary%s\n' "$C_BOLD" "$C_RESET"
    printf '  From repos          : %s\n' "$n_repo"
    printf '  Already installed   : %s\n' "$n_have"
    printf '  Built from source   : %s\n' "$n_src"
    if ((n_excl)); then printf '  Excluded (PKG_SKIP) : %s\n' "$n_excl"; fi
    printf '  Build policy        : COMPILE=%s\n' "${COMPILE:-ask}"
    if ((n_src)); then
        printf '\n'
        warn "$n_src packages will be built from source — their PKGBUILDs run on this machine."
        warn "To install without building: CHAOTIC_AUR=true (signed binaries) or COMPILE=never"
        # If there is network, the AUR's own trust signals are shown too.
        declare -F aur_trust_report >/dev/null && aur_trust_report "${aur_pkgs[@]}"
    fi
    printf '\n'
}

# --------------------------------------------------------- services ---------
# Modules may add a service name here if they detect a conflict.
SKIP_SERVICES=()

enable_system_service() {
    local svc="$1"
    [[ "${ENABLE_SERVICES:-1}" == 1 ]] || { debug "service skipped (ENABLE_SERVICES=0): $svc"; return 0; }
    if in_list "$svc" "${SKIP_SERVICES[@]+"${SKIP_SERVICES[@]}"}"; then
        warn "Skipping service (conflict detected): $svc"
        return 0
    fi
    if systemctl list-unit-files "$svc" >/dev/null 2>&1 &&
       [[ -n "$(systemctl list-unit-files --no-legend "$svc" 2>/dev/null)" ]]; then
        step "Enabling system service: $svc"
        run sudo systemctl enable "$svc" || warn "Could not enable: $svc"
    else
        debug "no service unit, skipping: $svc"
    fi
}

enable_user_service() {
    local svc="$1"
    [[ "${ENABLE_SERVICES:-1}" == 1 ]] || return 0
    if [[ -n "$(systemctl --user list-unit-files --no-legend "$svc" 2>/dev/null)" ]]; then
        step "Enabling user service: $svc"
        run systemctl --user enable "$svc" || warn "Could not enable: $svc"
    else
        debug "no user service unit, skipping: $svc"
    fi
}

# Enables the services defined in the catalog for the selected components.
enable_component_services() {  # <component id...>
    local id svc
    for id in "$@"; do
        while IFS= read -r svc; do
            [[ -n "$svc" ]] && enable_system_service "$svc"
        done < <(catalog_field "$id" services)
        while IFS= read -r svc; do
            [[ -n "$svc" ]] && enable_user_service "$svc"
        done < <(catalog_field "$id" user_services)
    done
}
