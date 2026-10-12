"""Import from a link: generates a profile manifest from a dotfiles repo.

``python -m hyprsetup rice import https://github.com/owner/repo`` fetches the repo
PINNED to the current commit, recognizes its layout, and writes the manifest that
``rice.py`` reads (``<name>.rice.toml``) + the gallery card (``<name>.conf``) under
``~/.config/hyprsetup/imported/``. From then on installation takes the same path as
hand-written profiles (``rice install <name>``): backup, revert, syntax migration,
keybinding overlay, mix parts.

Recognized layouts:

* home directory copy — ``.config/<app>`` (at the root or in a subfolder like
  ``dotfiles/``, ``configs/``);
* GNU stow — each package is ``<package>/.config/<app>``;
* flat — known app folders next to ``hypr/hyprland.conf``;
* Quickshell shell only — ``shell.qml`` at the root.

The author's install script is NEVER RUN. Commands run at startup (exec-once) are
listed one by one in the report; lines that ask for privileges, download and run
scripts from the internet, or delete files are flagged. Automatic detection may not
be as accurate as a hand-written manifest: unrecognized folders go into the "extra"
group (not installed by default), and the report says what is missing.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from . import rice as rice_mod

#: Apps that count as part of the desktop (``core`` group, installed by default).
CORE_APPS = {
    "hypr", "waybar", "rofi", "wofi", "dunst", "mako", "swaync", "kitty", "foot",
    "alacritty", "ghostty", "wezterm", "eww", "quickshell", "ags", "hyprpanel",
    "wlogout", "fuzzel", "walker", "tofi", "anyrun", "cava", "fastfetch", "neofetch",
    "btop", "swaylock", "matugen", "wallust", "wal", "yazi", "ranger", "lf", "zathura",
    "mpv", "gtk-3.0", "gtk-4.0", "qt5ct", "qt6ct", "Kvantum", "swayosd",
    "nwg-dock-hyprland", "nwg-drawer", "nwg-look", "waypaper", "hyprshell",
    "hyprswitch", "uwsm", "spicetify", "gammastep", "swappy", "satty",
}
#: Optional groups: the user's shell and editor are a big deal, never overwritten unasked.
GROUP_OF = {"fish": "shell", "zsh": "shell", "nushell": "shell", "starship": "shell",
            "starship.toml": "shell", ".zshrc": "shell", ".bashrc": "shell",
            ".zshenv": "shell", ".p10k.zsh": "shell", "bash": "shell",
            "tmux": "shell", "nvim": "editor", "helix": "editor", "micro": "editor", "doom": "editor"}
#: Not copied: app data or personal stuff.
SKIP_CONFIG = {"Code", "Code - OSS", "VSCodium", "discord", "vesktop", "BraveSoftware",
               "chromium", "google-chrome", "mozilla", "obsidian", "Slack", "spotify",
               "pulse", "dconf", "systemd", "autostart", "session", "user-dirs.dirs",
               "user-dirs.locale", "mimeapps.list", "github-copilot", "gh", "git"}

#: Binary of a startup command → Arch package.
BINARY_PACKAGE = {
    "swww": "awww", "swww-daemon": "awww", "awww": "awww", "awww-daemon": "awww",
    "hyprpaper": "hyprpaper", "hypridle": "hypridle", "hyprlock": "hyprlock",
    "hyprsunset": "hyprsunset", "hyprpolkitagent": "hyprpolkitagent",
    "waybar": "waybar", "dunst": "dunst", "mako": "mako", "swaync": "swaync",
    "eww": "eww", "qs": "quickshell", "quickshell": "quickshell",
    "nm-applet": "network-manager-applet", "blueman-applet": "blueman",
    "wl-paste": "wl-clipboard", "cliphist": "cliphist", "wl-clip-persist": "wl-clip-persist",
    "udiskie": "udiskie", "swayosd-server": "swayosd", "easyeffects": "easyeffects",
    "gnome-keyring-daemon": "gnome-keyring", "playerctld": "playerctl",
    "waypaper": "waypaper", "mpvpaper": "mpvpaper", "matugen": "matugen",
    "wallust": "wallust", "wal": "python-pywal", "rofi": "rofi", "wofi": "wofi",
    "fuzzel": "fuzzel", "kitty": "kitty", "foot": "foot", "alacritty": "alacritty",
    "cava": "cava", "fastfetch": "fastfetch", "swaylock": "swaylock",
    "wlogout": "wlogout", "nwg-dock-hyprland": "nwg-dock-hyprland",
    "hyprswitch": "hyprswitch", "copyq": "copyq", "kdeconnectd": "kdeconnect",
}
#: App folder → required package (if the folder exists, the program is in use).
APP_PACKAGE = {"waybar": "waybar", "rofi": "rofi", "wofi": "wofi", "dunst": "dunst",
               "mako": "mako", "swaync": "swaync", "kitty": "kitty", "foot": "foot",
               "alacritty": "alacritty", "eww": "eww", "quickshell": "quickshell",
               "fuzzel": "fuzzel", "wlogout": "wlogout", "cava": "cava",
               "fastfetch": "fastfetch", "swaylock": "swaylock", "matugen": "matugen",
               "wallust": "wallust", "swayosd": "swayosd"}
#: Commands that are not packages (shell builtins, session tools).
_NOT_PACKAGES = {"bash", "sh", "zsh", "fish", "sleep", "hyprctl", "systemctl", "echo",
                 "dbus-update-activation-environment", "gsettings", "export", "env",
                 "pkill", "killall", "uwsm", "uwsm-app", "app2unit", "exec", "true",
                 "notify-send", "xrdb", "cd", "source", "python", "python3", "hyprpm"}

#: Suspicious command patterns → explanation.
_FLAGS = (
    (re.compile(r"\b(sudo|pkexec|doas)\b"), "asks for root privileges"),
    (re.compile(r"\b(curl|wget)\b[^|]*\|\s*(ba|z|fi)?sh\b"),
     "downloads and runs a script from the internet"),
    (re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f?\s+(~|/|\$HOME)"), "deletes files"),
    (re.compile(r"\bbase64\s+(-d|--decode)"), "decodes an obfuscated command"),
    (re.compile(r"\bsystemctl\s+(?!--user)(enable|start|disable|mask)"),
     "changes a system service"),
    (re.compile(r"\b(nc|ncat|socat)\b.*-e\b"), "opens a shell to the network"),
    (re.compile(r"\beval\b"), "builds commands with eval"),
)

_IMAGE = {".png", ".jpg", ".jpeg", ".webp"}
_WALL_DIR = re.compile(r"(^|/)(wall(paper)?s?|backgrounds?|bg)(/|$)", re.I)
MAX_VARIANTS = 8


imported_dir = rice_mod.imported_dir


# ----------------------------------------------------------------- address ---
@dataclass
class Source:
    url: str                 # git clone URL
    owner: str = ""
    repo: str = ""
    ref: str = ""            # branch/tag/commit (empty = default branch)
    subdir: str = ""         # github.com/.../tree/<branch>/<subfolder>

    @property
    def is_github(self) -> bool:
        return "github.com" in self.url


def parse_url(text: str) -> Source:
    """``owner/repo``, ``https://github.com/owner/repo(.git)``,
    ``.../tree/<branch>/<subfolder>`` or any git URL."""
    text = text.strip().rstrip("/")
    if re.fullmatch(r"[\w.-]+/[\w.-]+", text):
        text = f"https://github.com/{text}"
    match = re.match(r"^(?:https?://|git@)(?:www\.)?github\.com[/:]([\w.-]+)/([\w.-]+?)"
                     r"(?:\.git)?(?:/(?:tree|blob)/([^/]+)(?:/(.*))?)?$", text)
    if match:
        owner, repo, ref, subdir = match.groups()
        return Source(f"https://github.com/{owner}/{repo}", owner, repo,
                      ref or "", (subdir or "").strip("/"))
    if re.match(r"^(https?://|git@|ssh://|file://|/)", text):
        name = re.sub(r"\.git$", "", text.rstrip("/").rsplit("/", 1)[-1])
        return Source(text, "", name)
    raise ValueError(f"could not understand the repo address: {text}")


def slug(source: Source) -> str:
    base = f"{source.owner}-{source.repo}" if source.owner else source.repo
    base = re.sub(r"(?i)[-_.]?(dot-?files|dots|config|configs|rice)$", "", base) or base
    return re.sub(r"[^a-z0-9-]+", "-", base.lower()).strip("-") or "imported"


# --------------------------------------------------------------------- git ---
def _git(repo: Path, *args: str, check: bool = True) -> str:
    out = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True,
                         check=False, timeout=900)
    if check and out.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {out.stderr.strip()[-300:]}")
    return out.stdout


def fetch(source: Source, repo: Path, commit: str = "") -> str:
    """Fetches the repo (blobless); returns the full SHA of the pinned commit."""
    if not (repo / ".git").is_dir():
        repo.parent.mkdir(parents=True, exist_ok=True)
        # Text files are downloaded right away, large files (wallpaper
        # collections) only when needed.
        _git(repo.parent, "clone", "--filter=blob:limit=1m", "--no-checkout", source.url,
             str(repo))
    wanted = commit or source.ref
    if wanted:
        present = subprocess.run(["git", "cat-file", "-e", f"{wanted}^{{commit}}"], cwd=repo,
                                 capture_output=True, check=False).returncode == 0
        if present:
            return _git(repo, "rev-parse", f"{wanted}^{{commit}}").strip()
        _git(repo, "fetch", "origin", wanted)
        return _git(repo, "rev-parse", "FETCH_HEAD").strip()
    _git(repo, "fetch", "origin")
    for ref in ("origin/HEAD", "HEAD"):
        out = subprocess.run(["git", "rev-parse", ref], cwd=repo, capture_output=True,
                             text=True, check=False)
        if out.returncode == 0:
            return out.stdout.strip()
    raise RuntimeError("could not find the repo's default branch")


class Tree:
    """Files in a commit; contents are read one by one when needed."""

    def __init__(self, repo: Path, commit: str, subdir: str = ""):
        self.repo, self.commit = repo, commit
        prefix = subdir.strip("/") + "/" if subdir else ""
        out = _git(repo, "ls-tree", "-r", "--full-tree", "-z", commit)
        self.prefix = prefix
        entries = [line.split("\t", 1) for line in out.split("\0") if "\t" in line]
        self.files = sorted(path for _meta, path in entries if path.startswith(prefix))
        #: Symlinks (mode 120000): fixes are applied to the link's target.
        self.links = {path for meta, path in entries if meta.startswith("120000")}
        self._cache: dict[str, str] = {}

    def read(self, path: str) -> str:
        if path not in self._cache:
            out = subprocess.run(["git", "show", f"{self.commit}:{path}"], cwd=self.repo,
                                 capture_output=True, check=False, timeout=300)
            self._cache[path] = out.stdout.decode("utf-8", "replace") if out.returncode == 0 else ""
        return self._cache[path]

    def children(self, directory: str) -> set[str]:
        base = directory.rstrip("/") + "/" if directory else ""
        return {p[len(base):].split("/", 1)[0] for p in self.files if p.startswith(base)}

    def is_dir(self, path: str) -> bool:
        base = path.rstrip("/") + "/"
        return any(p.startswith(base) for p in self.files)

    def under(self, directory: str) -> list[str]:
        base = directory.rstrip("/") + "/"
        return [p for p in self.files if p.startswith(base)]


# ---------------------------------------------------------------- report ---
@dataclass
class Install:
    src: str
    dest: str
    group: str = "core"
    mode: str = "replace"


@dataclass
class Report:
    name: str
    source: Source
    commit: str
    layout: str = ""
    installs: list[Install] = field(default_factory=list)
    hypr_entry: str = ""
    hypr_lang: str = ""
    execs: list[str] = field(default_factory=list)
    binds: list[str] = field(default_factory=list)
    flagged: list[tuple[str, str]] = field(default_factory=list)
    packages_repo: list[str] = field(default_factory=list)
    packages_aur: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    variants: list[dict] = field(default_factory=list)
    parts: list[dict] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    #: (link, target): if the repo is installed under ~/<name> and linked into ~/.config.
    links: list[tuple[str, str]] = field(default_factory=list)
    #: Automatic fixes (dicts in rice.Fix form).
    fixes: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    verify_errors: list[str] = field(default_factory=list)
    license: str = ""


# ------------------------------------------------------------ detection ---
def detect_layout(tree: Tree) -> tuple[str, list[Install], list[str]]:
    """(layout name, installs, skipped)."""
    files = tree.files
    installs: list[Install] = []
    skipped: list[str] = []
    seen: set[str] = set()

    def add(src: str, dest: str, name: str, known: bool) -> None:
        if dest in seen:
            return
        group = GROUP_OF.get(name) or ("core" if known else "extra")
        seen.add(dest)
        installs.append(Install(src, dest, group))

    # 1) home directory copy / stow: roots that contain ".config/".
    homes = sorted({p[: p.index(".config/")] for p in files if ".config/" in p
                    and (p.index(".config/") == len(tree.prefix)
                         or p[p.index(".config/") - 1] == "/")})
    if homes:
        stow = len(homes) > 1 and all(h.count("/") - tree.prefix.count("/") == 1 for h in homes
                                      if h != tree.prefix)
        for home in homes:
            for name in sorted(tree.children(home + ".config")):
                src = f"{home}.config/{name}"
                if name in SKIP_CONFIG:
                    skipped.append(f"{src} (app data/personal)")
                    continue
                add(src, f"~/.config/{name}", name, name in CORE_APPS)
            for name in sorted(tree.children(home.rstrip("/")) if home else tree.children("")):
                if name in GROUP_OF and not tree.is_dir(home + name):
                    add(home + name, f"~/{name}", name, True)
            for sub in ("bin", "share/fonts", "share/icons", "share/applications"):
                path = f"{home}.local/{sub}"
                if tree.is_dir(path):
                    installs.append(Install(path, f"~/.local/{sub}", "core", "merge"))
        return ("stow" if stow else "home"), installs, skipped

    # 2) flat: known app folders sit in a "config root" — next to hypr/
    # (hypr/hyprland.conf) or in a folder named "config/". If the Hyprland
    # config lives in a differently named folder (serpantinum:
    # compositors/hyprland), that folder becomes ~/.config/hypr.
    anchors = sorted({p.rsplit("/", 1)[0] if "/" in p else "" for p in files
                      if re.search(r"(^|/)hyprland\.(conf|lua)$", p)
                      and "/templates/" not in p and "/examples/" not in p},
                     key=lambda d: (d.count("/"), d))
    dirs = {p.rsplit("/", 1)[0] for p in files if "/" in p}
    dirs |= {d.rsplit("/", i)[0] for d in list(dirs) for i in range(1, d.count("/") + 1)}
    bases: list[str] = []
    hypr_elsewhere = ""
    if anchors:
        anchor = anchors[0]
        if anchor.rsplit("/", 1)[-1] == "hypr":
            bases.append(anchor.rsplit("/", 1)[0] + "/" if "/" in anchor else tree.prefix)
        else:
            hypr_elsewhere = anchor
    for directory in sorted(dirs, key=lambda d: d.count("/")):
        if directory.rsplit("/", 1)[-1] == "config" and directory.count("/") <= 2 \
                and tree.children(directory) & CORE_APPS:
            bases.append(directory + "/")
    if bases or hypr_elsewhere:
        if hypr_elsewhere:
            add(hypr_elsewhere, "~/.config/hypr", "hypr", True)
        for base in dict.fromkeys(bases):
            for name in sorted(tree.children(base.rstrip("/"))):
                path = base + name
                if not tree.is_dir(path):
                    continue
                if name in CORE_APPS or name in GROUP_OF:
                    add(path, f"~/.config/{name}", name, True)
                elif not name.startswith("."):
                    skipped.append(f"{path}/ (unrecognized folder)")
        return "flat", installs, skipped

    # 3) Quickshell shell only. The shell's name (qs -c <name>) is read from the
    # author's scripts; it does not work outside ~/.config/quickshell/<name>.
    shells = sorted({p[: -len("shell.qml")] for p in files if p.endswith("shell.qml")}, key=len)
    if shells:
        base = shells[0].rstrip("/")
        name = ""
        # First the launch scripts that actually run, then the shell itself, docs
        # last (vantage: the README says "vantage", launch.sh says "rice").
        def rank(path: str) -> int:
            return (0 if path.endswith((".sh", ".fish")) else
                    1 if path.endswith("shell.qml") else 2)
        for path in sorted(files[:400], key=rank):
            if path.endswith((".sh", ".md", ".fish", ".conf", ".lua", ".qml")) \
                    and path.count("/") <= base.count("/") + 2:
                match = re.search(r"\b(?:qs|quickshell)\s+(?:-c|--config)\s+([\w-]+)",
                                  tree.read(path))
                if match:
                    name = match.group(1)
                    break
        name = name or re.sub(r"[^a-z0-9-]+", "-", (base.rsplit("/", 1)[-1] if base
                                                    else tree.repo.name).lower()) or "shell"
        installs.append(Install(base or ".", f"~/.config/quickshell/{name}"))
        return "quickshell", installs, skipped
    return "", installs, skipped


_CONFIG_REF = re.compile(r"(?:~|\$HOME|\$\{HOME\}|/home/[\w.-]+)/\.config/([\w.-]+)")
_AUTHOR_HOME = re.compile(r"/home/([a-z_][\w.-]*)/")
#: User names used as examples in docs — not counted as the author's name.
_PLACEHOLDER_USERS = {"user", "username", "you", "yourname", "name", "me", "USER"}
_TEXT_EXT = (".conf", ".lua", ".sh", ".jsonc", ".json", ".css", ".rasi", ".py", ".fish",
             ".toml", ".ini", ".yuck", ".qml", "config")


def add_referenced(tree: Tree, report: Report) -> None:
    """The ~/.config/<name> folders the config calls into are installed too.

    Authors often keep their scripts in a separate folder (~/.config/scripts) and
    Hyprland/the bar calls them from there; since the folder is not a known app, it
    was skipped in the flat layout.
    """
    installed = {i.dest for i in report.installs}
    by_src = {(i.src.rsplit("/", 1)[0] if "/" in i.src else "") for i in report.installs
              if i.dest.startswith("~/.config/")}
    texts = [tree.read(p) for i in report.installs if i.group == "core"
             for p in tree.under(i.src)[:500] if p.endswith(_TEXT_EXT)]
    # READMEs and install scripts often say what goes where
    # (they are read, never run).
    texts += [tree.read(p) for p in tree.files
              if p.count("/") - tree.prefix.count("/") <= 1
              and re.search(r"(?i)(readme[^/]*|install[^/]*\.sh|setup[^/]*\.sh)$", p)]
    for name in sorted({m for t in texts for m in _CONFIG_REF.findall(t)}):
        dest = f"~/.config/{name}"
        if dest in installed or name in SKIP_CONFIG:
            continue
        for base in by_src:
            path = f"{base}/{name}" if base else name
            if tree.is_dir(path) or path in tree.files:
                report.installs.append(Install(path, dest, GROUP_OF.get(name, "core")))
                installed.add(dest)
                break


def author_home_fixes(tree: Tree, report: Report) -> None:
    """Absolute paths into the author's own home directory (/home/igris/...) are
    rewritten to your home directory on install ([[fix]] replace, {home})."""
    for item in report.installs:
        if item.group != "core":
            continue
        base = item.src.rstrip("/")
        paths = [item.src] if item.src in tree.files else tree.under(item.src)[:500]
        for path in paths:
            if not path.endswith(_TEXT_EXT) or path in tree.links:
                continue
            users = {u for u in _AUTHOR_HOME.findall(tree.read(path))
                     if u not in _PLACEHOLDER_USERS}
            if not users:
                continue
            rel = path[len(base):].lstrip("/")
            dest = f"{item.dest}/{rel}" if rel else item.dest
            report.fixes.append({
                "file": dest,
                "replace": [x for u in sorted(users) for x in (f"/home/{u}/", "{home}/")],
                "why": "absolute path into the author's home (" + ", ".join(sorted(users)) + ")"})
            if len(report.fixes) >= 80:
                return


def detect_repo_home(tree: Tree, report: Report) -> None:
    """If the repo expects to live at a specific place in the home directory
    (~/Arch-dotfiles, ~/.dotfiles), it is installed there and ~/.config/<app> is
    linked to it.

    The author's scripts call their own folder path (~/Arch-dotfiles/rofi/...); when
    the folders were copied straight into ~/.config, those paths pointed nowhere.
    """
    texts = [tree.read(p) for i in report.installs if i.group == "core"
             for p in tree.under(i.src)[:500] if p.endswith(_TEXT_EXT)]
    blob = "\n".join(texts)
    candidates = [report.source.repo, ".dotfiles", "dotfiles", ".dots", "dots"]
    home_name = next((c for c in candidates
                      if re.search(r"(?:~|\$HOME|\$\{HOME\})/" + re.escape(c) + r"/", blob)),
                     "")
    if not home_name:
        return
    base = tree.prefix.rstrip("/") or "."
    kept: list[Install] = [Install(base, f"~/{home_name}")]
    for item in report.installs:
        if item.group == "core" and item.dest.startswith("~/.config/") and item.mode == "replace":
            rel = item.src[len(tree.prefix):] if item.src.startswith(tree.prefix) else item.src
            report.links.append((item.dest, f"~/{home_name}/{rel}"))
        else:
            kept.append(item)
    report.installs = kept
    report.layout += f" → ~/{home_name}"


def _hypr_src(installs: list[Install]) -> str | None:
    for item in installs:
        if item.dest == "~/.config/hypr":
            return item.src
    return None


_EXEC = re.compile(r"^\s*exec(?:-once)?\s*=\s*(.+)$", re.M)
_BIND_EXEC = re.compile(r"^\s*bind[a-z]*\s*=\s*[^,\n]*,[^,\n]*,\s*exec\s*,\s*(.+)$", re.M)
_LUA_EXEC = re.compile(r"""hl\.exec_cmd\(\s*(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')""")
_VAR = re.compile(r"^\s*\$([A-Za-z_]\w*)\s*=\s*(.*)$", re.M)


def scan_hypr(tree: Tree, report: Report) -> None:
    hypr = _hypr_src(report.installs)
    if hypr is None:
        return
    confs = [p for p in tree.under(hypr) if p.endswith(".conf")]
    luas = [p for p in tree.under(hypr) if p.endswith(".lua")]
    if f"{hypr}/hyprland.lua" in luas and f"{hypr}/hyprland.conf" not in confs:
        report.hypr_lang = "lua"
    elif f"{hypr}/hyprland.conf" in confs:
        report.hypr_lang = "conf"
    elif confs:
        # Main file under another name (hypr.conf): the one with the most source lines.
        best = max(confs, key=lambda p: tree.read(p).count("source"))
        report.hypr_lang = "conf"
        report.hypr_entry = best[len(hypr) + 1:]
    variables: dict[str, str] = {}
    texts = [tree.read(p) for p in confs]
    for text in texts:
        for name, value in _VAR.findall(text):
            variables[name] = value.split(" #", 1)[0].strip()

    def expand(command: str) -> str:
        for name in sorted(variables, key=len, reverse=True):
            command = command.replace("$" + name, variables[name])
        return command.split(" #", 1)[0].strip()

    for text in texts:
        report.execs += [expand(c) for c in _EXEC.findall(text)]
        report.binds += [expand(c) for c in _BIND_EXEC.findall(text)]
    for path in luas:
        report.execs += [a or b for a, b in _LUA_EXEC.findall(tree.read(path))]
    report.execs = list(dict.fromkeys(c for c in report.execs if c))
    report.binds = list(dict.fromkeys(report.binds))
    for command in report.execs + report.binds:
        for pattern, why in _FLAGS:
            if pattern.search(command):
                report.flagged.append((command, why))
                break
    monitors = [line.strip() for text in texts
                for line in text.splitlines() if re.match(r"^\s*monitor\s*=\s*[^,\s]+,", line)]
    if monitors:
        report.warnings.append("the author hard-codes their displays (your display layout "
                               "may change): "
                               + " · ".join(monitors[:3]))


def scan_packages(report: Report) -> None:
    from . import deps as deps_mod

    names: list[str] = []
    for command in report.execs:
        for binary in rice_mod._command_binaries(command):        # noqa: SLF001
            if (binary in _NOT_PACKAGES or "/" in binary or binary.startswith(("~", "$", "["))
                    or re.search(r"\.(sh|py|fish|pl|js)$", binary)):
                continue
            names.append(BINARY_PACKAGE.get(binary, binary))
    for item in report.installs:
        app = item.dest.rsplit("/", 1)[-1]
        if item.group == "core" and app in APP_PACKAGE:
            names.append(APP_PACKAGE[app])
    if report.hypr_lang:
        names.append("hyprland")
    names = list(dict.fromkeys(names))
    in_repo = deps_mod.in_sync_repos(names)
    for name in names:
        if name in in_repo:
            report.packages_repo.append(name)
        elif shutil.which(name):
            continue                     # installed (local package or script)
        else:
            report.unknown.append(name)


def _raw_url(source: Source, commit: str, path: str) -> str:
    return (f"https://raw.githubusercontent.com/{source.owner}/{source.repo}/"
            f"{commit}/{quote(path)}")


def scan_wallpapers(tree: Tree, report: Report) -> None:
    """Wallpapers in the repo → variants (at most MAX_VARIANTS).

    If the image is inside an installed folder it is used in place (~/...),
    otherwise from the pinned commit's raw URL. The command that applies the variant
    is written for the author's wallpaper program (hyprpaper or swww/awww).
    """
    images = [p for p in tree.files if Path(p).suffix.lower() in _IMAGE
              and _WALL_DIR.search(p[len(tree.prefix):])]
    if not images:
        return
    execs = " ".join(report.execs)
    uses_swww = bool(re.search(r"\b(swww|awww)", execs))
    hypr = _hypr_src(report.installs)
    hyprpaper = "~/.config/hypr/hyprpaper.conf"
    for path in images[:MAX_VARIANTS]:
        # "duvar" ("wall"): Turkish-looking default variant id, kept as-is.
        name = re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]+", "-", Path(path).stem.lower())).strip("-")[:24] or "duvar"
        if any(v["name"] == name for v in report.variants):
            name = f"{name}-{len(report.variants) + 1}"
        inside = next((i for i in report.installs if path.startswith(i.src.rstrip("/") + "/")),
                      None)
        if inside is not None:
            wallpaper, dest = inside.dest + path[len(inside.src.rstrip("/")):], ""
        elif report.source.is_github:
            wallpaper = _raw_url(report.source, report.commit, path)
            dest = f"~/Pictures/Wallpapers/{report.name}/{Path(path).name}"
        else:
            continue
        if uses_swww:
            apply = ["awww img {wallpaper} 2>/dev/null || swww img {wallpaper}"]
        elif hypr is not None:
            apply = ["printf 'wallpaper {\\n    monitor =\\n    path = %s\\n    fit_mode = cover\\n}"
                     "\\nsplash = false\\nipc = on\\n' {wallpaper} > " + hyprpaper,
                     "pkill -x hyprpaper; sleep 0.3; hyprpaper >/dev/null 2>&1 &"]
        else:
            apply = []
        report.variants.append({"name": name, "title": Path(path).stem.replace("_", " "),
                                "wallpaper": wallpaper, "wallpaper_dest": dest,
                                "apply": apply, "credit": f"{report.source.url} — {path}"})
    if len(images) > MAX_VARIANTS:
        report.warnings.append(f"the repo has {len(images)} wallpapers; the first "
                               f"{MAX_VARIANTS} were added as variants")


_LAUNCH_HINT = re.compile(r"(rofi|wofi|fuzzel|walker|tofi|anyrun)\b[^;&|]*")


def scan_parts(tree: Tree, report: Report) -> None:
    """Parts that can be taken on their own in a mix (mix.py)."""
    dests = {i.dest.rsplit("/", 1)[-1]: i for i in report.installs
             if i.dest.startswith("~/.config/")}
    execs = " ".join(report.execs)

    def launcher_cmd(tool: str, default: str) -> str:
        for command in report.binds:
            if tool in command and ("drun" in command or "launcher" in command.lower()):
                return command
        return default

    if "waybar" in dests:
        report.parts.append({"slot": "bar", "title": "Waybar",
                             "paths": ["~/.config/waybar"], "start": "waybar",
                             "provides": ["bar"], "packages": ["waybar"]})
    if "eww" in dests:
        report.parts.append({"slot": "bar", "id": "eww", "title": "Eww",
                             "paths": ["~/.config/eww"],
                             "start": next((c for c in report.execs if "eww open" in c),
                                           "eww daemon"),
                             "provides": ["bar"], "packages": ["eww"]})
    for tool, default in (("rofi", "rofi -show drun"), ("wofi", "wofi --show drun"),
                          ("fuzzel", "fuzzel")):
        if tool in dests:
            report.parts.append({"slot": "launcher", "id": tool, "title": tool.capitalize(),
                                 "paths": [f"~/.config/{tool}"],
                                 "commands": {"CMD_LAUNCHER": launcher_cmd(tool, default)},
                                 "packages": [tool]})
    for tool in ("dunst", "mako", "swaync"):
        if tool in dests:
            report.parts.append({"slot": "notify", "id": tool, "title": tool.capitalize(),
                                 "paths": [f"~/.config/{tool}"], "start": tool,
                                 "provides": ["notify"], "packages": [tool]})
    for tool in ("kitty", "foot", "alacritty", "ghostty"):
        if tool in dests:
            report.parts.append({"slot": "terminal", "id": tool, "title": tool.capitalize(),
                                 "paths": [f"~/.config/{tool}"],
                                 "commands": {"CMD_TERMINAL": tool}, "packages": [tool]})
    hypr = _hypr_src(report.installs)
    if hypr is not None and f"{hypr}/hyprlock.conf" in tree.files:
        report.parts.append({"slot": "lock", "title": "Hyprlock",
                             "paths": ["~/.config/hypr/hyprlock.conf"], "wallpaper_lines": True,
                             "commands": {"LOCK_CMD": "hyprlock"}, "packages": ["hyprlock"]})
    if "quickshell" in execs or "qs " in execs:
        report.warnings.append("the Quickshell shell is a single piece: to split it in Soup "
                               "Maker, write its components into the manifest by hand "
                               "([[part]] entry/modules)")


def _license(tree: Tree) -> str:
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"):
        path = tree.prefix + name
        if path in tree.files:
            text = tree.read(path)[:400]
            for key, spdx in (("MIT License", "MIT"), ("GNU GENERAL PUBLIC LICENSE", "GPL-3.0"),
                              ("Apache License", "Apache-2.0"), ("BSD", "BSD"),
                              ("Unlicense", "Unlicense")):
                if key.lower() in text.lower():
                    return spdx
            return "present (type not recognized)"
    return ""


# ------------------------------------------------------------- writing ---
def _t(value) -> str:
    """TOML value (JSON string escapes are compatible with TOML basic strings)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k} = {_t(v)}" for k, v in value.items()) + " }"
    if isinstance(value, list):
        return "[" + ", ".join(_t(v) for v in value) + "]"
    return json.dumps(str(value), ensure_ascii=False)


def to_toml(report: Report) -> str:
    notes = [f"Imported from a link ({datetime.now():%Y-%m-%d}); layout: {report.layout}. "
             "Detected automatically — edit this file if needed."]
    notes += [f"{why}: {cmd}" for cmd, why in report.flagged]
    notes += report.warnings
    if report.unknown:
        notes.append("Programs not found in the repos (may be AUR): "
                     + ", ".join(report.unknown))
    lines = [f"# {report.name} — {report.source.url}",
             "# Generated by python -m hyprsetup rice import. "
             "The author's install script was not run.",
             ""]
    if report.variants:
        lines.append(f"default_variant = {_t(report.variants[0]['name'])}")
    if report.hypr_entry:
        lines.append(f"hypr_entry = {_t(report.hypr_entry)}")
    lines.append("notes = [")
    lines += [f"  {_t(n)}," for n in notes]
    lines += ["]", "", "[source]", f"repo = {_t(report.source.url)}",
              f"commit = {_t(report.commit)}", f"license = {_t(report.license)}", ""]
    base = report.source.subdir.strip("/") + "/" if report.source.subdir else ""
    for item in report.installs:
        src = item.src[len(base):] if base and item.src.startswith(base) else item.src
        lines += ["[[install]]", f"from = {_t(src or '.')}", f"to = {_t(item.dest)}"]
        if item.group != "core":
            lines.append(f"group = {_t(item.group)}")
        if item.mode != "replace":
            lines.append(f"mode = {_t(item.mode)}")
        lines.append("")
    for fix in report.fixes:
        lines.append("[[fix]]")
        lines += [f"{key} = {_t(value)}" for key, value in fix.items()]
        lines.append("")
    for link_to, target in report.links:
        lines += ["[[link]]", f"to = {_t(link_to)}", f"target = {_t(target)}", ""]
    lines += ["[packages]", f"repo = {_t(report.packages_repo)}",
              f"aur = {_t(report.packages_aur)}", ""]
    for variant in report.variants:
        lines.append(f"[variants.{_t(variant['name'])}]")
        for key in ("title", "wallpaper", "wallpaper_dest", "apply", "credit"):
            if variant.get(key):
                lines.append(f"{key} = {_t(variant[key])}")
        lines.append("")
    for part in report.parts:
        lines.append("[[part]]")
        lines += [f"{key} = {_t(value)}" for key, value in part.items()]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def to_card(report: Report) -> str:
    return (f"# ---------------------------------------------------------------------------\n"
            f"#  preset: {report.name}\n"
            f"#  title: {report.source.owner or report.source.repo} — {report.source.repo}\n"
            f"#  desc: {report.source.url} (imported from a link, {report.commit[:8]}).\n"
            f"# ---------------------------------------------------------------------------\n\n"
            'THEME="auto"\n')


# ----------------------------------------------------------------- main ---
def analyze(url: str, name: str = "", commit: str = "", repo_dir: Path | None = None,
            home: Path | None = None) -> Report:
    source = parse_url(url)
    name = name or slug(source)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        raise ValueError(f"invalid name: {name} (lowercase letters, digits and hyphens)")
    repo = repo_dir or rice_mod.cache_dir(name, home)
    sha = fetch(source, repo, commit)
    tree = Tree(repo, sha, source.subdir)
    if not tree.files:
        raise RuntimeError("the repo is empty or the subfolder was not found")
    report = Report(name=name, source=source, commit=sha)
    report.layout, report.installs, report.skipped = detect_layout(tree)
    if not report.installs:
        raise RuntimeError("no recognized dotfiles layout: no .config/, stow packages, "
                           "hypr/hyprland.conf or shell.qml found")
    if report.layout in ("flat", "home", "stow"):
        add_referenced(tree, report)
    author_home_fixes(tree, report)
    report.license = _license(tree)
    if not report.license:
        report.warnings.append("the repo has no license: it may not be redistributed without "
                               "the author's permission (use it on your own machine only)")
    scan_hypr(tree, report)
    if report.hypr_lang == "":
        report.warnings.append("no Hyprland config: only the apps are installed, your window "
                               "manager settings stay as they are")
    scan_packages(report)
    scan_wallpapers(tree, report)
    scan_parts(tree, report)
    # Last: the steps above look at the ~/.config/<app> targets.
    if report.layout in ("flat", "home", "stow"):
        detect_repo_home(tree, report)
    return report


def write(report: Report, home: Path | None = None) -> Path:
    directory = imported_dir(home)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{report.name}{rice_mod.SUFFIX}"
    path.write_text(to_toml(report), encoding="utf-8")
    (directory / f"{report.name}.conf").write_text(to_card(report), encoding="utf-8")
    return path


def describe(report: Report) -> list[str]:
    """Report shown before installing."""
    out = [f"{report.name}: {report.source.url} @ {report.commit[:10]} "
           f"(layout: {report.layout or '?'}, license: {report.license or 'none'})"]
    groups: dict[str, list[str]] = {}
    for item in report.installs:
        groups.setdefault(item.group, []).append(f"{item.src or '.'} → {item.dest}")
    labels = {"core": "to install", "shell": "shell (optional: --group shell)",
              "editor": "editor (optional: --group editor)",
              "extra": "unrecognized (optional: --group extra)"}
    for group in ("core", "shell", "editor", "extra"):
        if groups.get(group):
            out.append(f"  {labels[group]}:")
            out += [f"    {line}" for line in groups[group]]
    if report.links:
        out.append("  links:")
        out += [f"    {a} → {b}" for a, b in report.links]
    if report.hypr_lang:
        entry = report.hypr_entry or f"hyprland.{report.hypr_lang}"
        out.append(f"  Hyprland: {entry} ({report.hypr_lang})")
    if report.execs:
        out.append(f"  commands run at startup ({len(report.execs)}):")
        out += [f"    {c}" for c in report.execs]
    if report.flagged:
        out.append("  WARNING — suspicious lines:")
        out += [f"    ! {why}: {cmd}" for cmd, why in report.flagged]
    if report.packages_repo:
        out.append("  packages: " + " ".join(report.packages_repo))
    if report.unknown:
        out.append("  not in the repos (may be AUR): " + " ".join(report.unknown))
    if report.variants:
        out.append(f"  variants (wallpapers): {', '.join(v['name'] for v in report.variants)}")
    if report.parts:
        out.append("  mix parts: " + ", ".join(
            f"{p['slot']}:{p.get('id', p['slot'])}" for p in report.parts))
    if report.fixes:
        out.append(f"  fixes: the author's /home/<name>/ paths in {len(report.fixes)} files "
                   "will be rewritten to your home directory")
    for line in report.skipped:
        out.append(f"  skipped: {line}")
    for warning in report.warnings:
        out.append(f"  note: {warning}")
    for error in report.verify_errors:
        out.append(f"  Hyprland verification: {error}")
    return out


def verify(root: Path, report: Report) -> None:
    """Tests the written manifest with Hyprland's verifier (temporary home directory)."""
    if not report.hypr_lang or shutil.which("Hyprland") is None:
        return
    try:
        report.verify_errors = rice_mod.verify(root, report.name)
    except Exception as exc:                                       # noqa: BLE001
        report.verify_errors = [f"could not test: {exc}"]
    if not report.verify_errors:
        report.verify_errors = []


def remove(name: str, home: Path | None = None) -> bool:
    from . import mix as mix_mod

    directory = imported_dir(home)
    if home is None:
        mix_mod.forget_imported(name)
    found = False
    for suffix in (rice_mod.SUFFIX, ".conf"):
        path = directory / f"{name}{suffix}"
        if path.exists():
            path.unlink()
            found = True
    return found

