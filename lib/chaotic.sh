# shellcheck shell=bash
# ---------------------------------------------------------------------------
#  chaotic.sh — sets up the Chaotic-AUR repository with LIMITED trust (optional)
#
#  Why it exists: some components, like HyprPanel, are in no signed repository,
#  only in the AUR. AUR packages are built on your machine; ags-hyprpanel-git's
#  PKGBUILD runs `npm install` during the build, i.e. it downloads and runs
#  arbitrary JavaScript dependencies. Chaotic-AUR ships the same package
#  prebuilt and SIGNED — that npm step runs on their machine, not yours.
#
#  In exchange you lose something: you no longer see the PKGBUILD. Chaotic
#  builds packages from the AUR AUTOMATICALLY, with no real human review. So
#  source trust is the same as the AUR; what you hand off is the review step.
#
#  That is why there are two safeguards here:
#    1. Setup asks for explicit consent (CHAOTIC_AUR=true + confirm).
#    2. The repo is added with "Usage = Sync Search Install" — NO Upgrade.
#       So a package is installed when explicitly requested, but the repo is
#       never a source during `pacman -Syu` and cannot override official
#       packages. Giving a third-party repo full system trust by default would
#       widen the blast radius from "one package" to "every package".
# ---------------------------------------------------------------------------

# Chaotic-AUR's primary trust key. The FULL fingerprint is used: short key
# IDs (3056513887B78AEB) can be collided, a full fingerprint cannot. The
# value is taken from the keyring package's own "chaotic-trusted" file
# (usr/share/pacman/keyrings/chaotic-trusted).
CHAOTIC_KEY_FPR="EF925EA60F33D0CB85C44AD13056513887B78AEB"
CHAOTIC_KEYSERVER="keyserver.ubuntu.com"
CHAOTIC_CDN="https://cdn-mirror.chaotic.cx/chaotic-aur"

# Is the repo already defined in pacman.conf?
chaotic_configured() {
    grep -qE '^\s*\[chaotic-aur\]' /etc/pacman.conf 2>/dev/null
}

# Can a package currently be installed from one of the configured repos?
# (Once chaotic-aur is added, its packages show up here too.)
repo_has_package() {  # <package>
    pacman -Si "$1" >/dev/null 2>&1
}

# chaotic_setup — sets up the repo. Does nothing if it is already set up.
# Does not run at all unless CHAOTIC_AUR=true.
chaotic_setup() {
    [[ "${CHAOTIC_AUR:-false}" == true ]] || return 0

    if chaotic_configured; then
        ok "Chaotic-AUR is already configured"
        return 0
    fi

    warn "Chaotic-AUR is a third-party repository (chaotic.cx / Garuda Linux)."
    warn "Its packages are built automatically from the AUR; NO PKGBUILD review."
    warn "If added, /etc/pacman.conf is modified and a GPG key is locally"
    warn "signed into your pacman keyring."
    step "The repo will be added with 'Usage = Sync Search Install' — it will not"
    step "be a source during system upgrades (-Syu) and cannot override official packages."
    confirm "Add Chaotic-AUR?" n || {
        warn "Chaotic-AUR skipped — AUR packages will be built locally."
        return 0
    }

    step "Fetching the Chaotic-AUR key ($CHAOTIC_KEY_FPR)"
    run sudo pacman-key --recv-key "$CHAOTIC_KEY_FPR" \
        --keyserver "$CHAOTIC_KEYSERVER" \
        || { warn "Could not fetch the key — skipping Chaotic-AUR."; return 1; }
    run sudo pacman-key --lsign-key "$CHAOTIC_KEY_FPR" \
        || { warn "Could not sign the key — skipping Chaotic-AUR."; return 1; }

    # The keyring/mirrorlist packages are signed and verified with the key
    # trusted above. If verification fails, pacman rejects them anyway.
    step "Installing chaotic-keyring and chaotic-mirrorlist"
    run sudo pacman -U --noconfirm \
        "$CHAOTIC_CDN/chaotic-keyring.pkg.tar.zst" \
        "$CHAOTIC_CDN/chaotic-mirrorlist.pkg.tar.zst" \
        || { warn "Could not install the Chaotic packages — skipping."; return 1; }

    step "Adding a limited repo definition to /etc/pacman.conf"
    # Backup: so the user has the previous version of the file if they want to revert.
    run sudo cp -a /etc/pacman.conf "/etc/pacman.conf.hyprsetup.bak"
    printf '\n[chaotic-aur]\n# Added by hyprsetup. "Upgrade" is intentionally ABSENT:\n# the repo is only used for explicitly requested packages and cannot\n# override official packages during -Syu. Delete this block to remove it.\nUsage = Sync Search Install\nInclude = /etc/pacman.d/chaotic-mirrorlist\n' \
        | run sudo tee -a /etc/pacman.conf >/dev/null \
        || { warn "Could not write pacman.conf."; return 1; }

    run sudo pacman -Sy || warn "Could not refresh the repo database."
    ok "Chaotic-AUR added (limited trust). Backup: /etc/pacman.conf.hyprsetup.bak"
}

# ------------------------------------------------------------ trust check
# Shows trust signals for packages to be installed from the AUR BEFORE installing.
# The goal is not to block but to let the user see what they are saying yes to:
# an orphaned package, an "out of date" flag and near-zero popularity are real warnings.
aur_trust_report() {  # <package...>
    (($# == 0)) && return 0
    have curl || return 0

    local query="" pkg
    for pkg in "$@"; do query+="&arg[]=$pkg"; done

    local json
    json=$(curl -sf --max-time 10 \
        "https://aur.archlinux.org/rpc/v5/info?${query#&}" 2>/dev/null) || {
        debug "AUR trust query failed (network?) — skipping"
        return 0
    }

    local report
    report=$(printf '%s' "$json" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for r in data.get("results", []):
    name = r.get("Name", "?")
    flags = []
    if not r.get("Maintainer"):
        flags.append("ORPHANED (no maintainer)")
    if r.get("OutOfDate"):
        flags.append("flagged OUT OF DATE")
    pop = r.get("Popularity") or 0
    votes = r.get("NumVotes") or 0
    if pop < 0.5:
        flags.append("very low usage (popularity %.2f, %d votes)" % (pop, votes))
    if name.endswith("-git"):
        flags.append("-git: not a fixed release, builds the latest code at that moment")
    if flags:
        print(name + ": " + "; ".join(flags))
' 2>/dev/null)

    if [[ -n "$report" ]]; then
        warn "AUR trust warnings:"
        while IFS= read -r line; do
            [[ -n "$line" ]] && warn "  · $line"
        done <<<"$report"
    fi
}
