"""Palette extraction from a wallpaper — used by ``THEME="auto"``.

The project's flow is normally **theme → wallpaper**: a palette is picked and the
image is generated from it (see wallpaper.py). This module adds the reverse
direction: it extracts the 11 semantic colors from the user's own image, so the
bar, terminal, GTK and Hyprland borders match the wallpaper.

Three backends, tried in order:

1. ``matugen``  — Material You (best result, AUR package)
2. ``magick``   — ImageMagick histogram (reads any format)
3. pure Python  — PNG decoder (no dependencies; the repo's own wallpapers are PNG)

Color roles are NOT taken RAW from the image. Only *hue* and *saturation* come
from the image; lightness is forced onto a fixed scale per role (see _TARGETS).
pywal and wallust do the same, for this reason: using the dominant colors
directly as background/text produces an unreadable desktop on low-contrast
images. Hue from the image, readability from us.

The output has exactly the same 11 keys as themes.KEYS; themes.resolve() accepts
it as an override layer, like CUSTOM_COLORS.
"""

from __future__ import annotations

import colorsys
import json
import shutil
import struct
import subprocess
import zlib
from pathlib import Path

from . import themes

#: Role → (target lightness L, target saturation S multiplier, hue source)
#: Hue sources: "base" the image's dominant hue · "accent" accent hue ·
#: "fixed:<degrees>" fixed hue (for red/green/yellow/cyan).
_TARGETS_DARK: dict[str, tuple[float, float, str]] = {
    "BG":      (0.085, 0.35, "base"),
    "BG_DARK": (0.050, 0.30, "base"),
    "SURFACE": (0.185, 0.30, "base"),
    "FG":      (0.900, 0.10, "base"),
    "SUBTEXT": (0.680, 0.12, "base"),
    "ACCENT":  (0.700, 1.00, "accent"),
    "ACCENT2": (0.720, 0.90, "accent2"),
    "RED":     (0.700, 0.75, "fixed:2"),
    "GREEN":   (0.720, 0.55, "fixed:120"),
    "YELLOW":  (0.760, 0.70, "fixed:45"),
    "CYAN":    (0.740, 0.55, "fixed:180"),
}

_TARGETS_LIGHT: dict[str, tuple[float, float, str]] = {
    "BG":      (0.960, 0.20, "base"),
    "BG_DARK": (0.900, 0.22, "base"),
    "SURFACE": (0.870, 0.25, "base"),
    "FG":      (0.170, 0.25, "base"),
    "SUBTEXT": (0.400, 0.20, "base"),
    "ACCENT":  (0.430, 1.00, "accent"),
    "ACCENT2": (0.460, 0.90, "accent2"),
    "RED":     (0.450, 0.80, "fixed:2"),
    "GREEN":   (0.380, 0.60, "fixed:120"),
    "YELLOW":  (0.420, 0.80, "fixed:45"),
    "CYAN":    (0.400, 0.60, "fixed:180"),
}

#: At least this contrast ratio between FG/BG is guaranteed (WCAG AA body text).
_MIN_CONTRAST = 4.5
#: Slightly looser for SUBTEXT (secondary text, WCAG AA large text).
_MIN_CONTRAST_SUB = 3.0


# ---------------------------------------------------------- color helpers --
def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def _luminance(rgb: tuple[int, int, int]) -> float:
    """WCAG relative luminance."""
    def channel(value: float) -> float:
        value /= 255
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def lab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    """CIE L*a*b* (D65; channels 0–255) — for perceptual color distance."""
    def channel(value: float) -> float:
        value /= 255
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    r, g, b = (channel(c) for c in rgb)
    fx = f((0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047)
    fy = f(0.2126 * r + 0.7152 * g + 0.0722 * b)
    fz = f((0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def hex_lab(value: str) -> tuple[float, float, float]:
    return lab(_hex_to_rgb(value))


def hex_luminance(value: str) -> float:
    return _luminance(_hex_to_rgb(value))


def _contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = _luminance(a), _luminance(b)
    if la < lb:
        la, lb = lb, la
    return (la + 0.05) / (lb + 0.05)


def _build(hue: float, sat: float, light: float) -> str:
    """HSL → hex. hue in degrees (0-360), sat/light 0-1."""
    r, g, b = colorsys.hls_to_rgb((hue % 360) / 360.0,
                                  max(0.0, min(1.0, light)),
                                  max(0.0, min(1.0, sat)))
    return _rgb_to_hex((r * 255, g * 255, b * 255))


def _hsl(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """RGB → (hue degrees, sat 0-1, light 0-1)."""
    h, light, sat = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    return h * 360.0, sat, light


def _ensure_contrast(fg_hex: str, bg_hex: str, minimum: float) -> str:
    """Lightens/darkens fg until it is readable against bg.

    Hue and saturation are kept, only lightness is shifted — so readability is
    guaranteed without changing the color's identity. If the target can never
    be reached (very rare) it falls back to plain white/black.
    """
    bg = _hex_to_rgb(bg_hex)
    hue, sat, light = _hsl(_hex_to_rgb(fg_hex))
    # Dark background: move toward lighter text; light background: toward darker.
    step = 0.02 if _luminance(bg) < 0.18 else -0.02
    for _ in range(50):
        candidate = _build(hue, sat, light)
        if _contrast(_hex_to_rgb(candidate), bg) >= minimum:
            return candidate
        light += step
        if not 0.0 <= light <= 1.0:
            break
    return "ffffff" if _luminance(bg) < 0.18 else "000000"


# -------------------------------------------------------- backend: matugen --
#: Material You role → our key. matugen's JSON uses these names.
_MATUGEN_ROLES = {
    "BG": ("surface", "background"),
    "BG_DARK": ("surface_container_lowest", "surface_dim", "background"),
    "SURFACE": ("surface_container", "surface_variant"),
    "FG": ("on_surface", "on_background"),
    "SUBTEXT": ("on_surface_variant", "outline"),
    "ACCENT": ("primary",),
    "ACCENT2": ("tertiary", "secondary"),
    "RED": ("error",),
}


def _from_matugen(image: Path, dark: bool) -> dict[str, str] | None:
    if not shutil.which("matugen"):
        return None
    mode = "dark" if dark else "light"
    try:
        proc = subprocess.run(
            ["matugen", "image", str(image), "--json", "hex", "--mode", mode],
            capture_output=True, text=True, timeout=60, check=True)
        data = json.loads(proc.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return None

    # The wrapping varies between matugen versions: {"colors": {"dark":
    # {...}}} or directly {"dark": {...}}. Accept both.
    colors = data.get("colors", data)
    scheme = colors.get(mode, colors)
    if not isinstance(scheme, dict):
        return None

    raw: dict[str, str] = {}
    for key, candidates in _MATUGEN_ROLES.items():
        for role in candidates:
            value = scheme.get(role)
            if isinstance(value, str) and value.strip().lstrip("#"):
                raw[key] = value.strip().lstrip("#")[:6]
                break
    if "ACCENT" not in raw:
        return None
    return raw


# ---------------------------------------------------- backend: ImageMagick --
def _from_magick(image: Path) -> list[tuple[tuple[int, int, int], int]] | None:
    """Returns the dominant colors as (rgb, weight)."""
    binary = shutil.which("magick") or shutil.which("convert")
    if not binary:
        return None
    try:
        proc = subprocess.run(
            [binary, str(image), "-resize", "200x200", "-colors", "32",
             "-format", "%c", "histogram:info:-"],
            capture_output=True, text=True, timeout=60, check=True)
    except (subprocess.SubprocessError, OSError):
        return None

    out: list[tuple[tuple[int, int, int], int]] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if ":" not in line or "#" not in line:
            continue
        try:
            count = int(line.split(":", 1)[0])
            token = line.split("#", 1)[1].split()[0]
            out.append((_hex_to_rgb(token[:6]), count))
        except (ValueError, IndexError):
            continue
    return out or None


# --------------------------------------------------- backend: pure Python ----
def _png_pixels(path: Path, step: int = 4) -> list[tuple[int, int, int]] | None:
    """Decodes a PNG with zlib and returns a sampled pixel list.

    Only supports the common cases: 8/16-bit depth, color type 0/2/3/4/6,
    non-interlaced. On an unsupported file it returns None and the caller
    falls back to the other backends / the theme.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None

    pos = 8
    width = height = depth = ctype = interlace = 0
    idat = bytearray()
    palette: bytes = b""
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length          # 4 length + 4 type + data + 4 CRC
        if kind == b"IHDR":
            width, height, depth, ctype, _, _, interlace = struct.unpack(
                ">IIBBBBB", body[:13])
        elif kind == b"PLTE":
            palette = bytes(body)
        elif kind == b"IDAT":
            idat += body
        elif kind == b"IEND":
            break

    if not width or not height or interlace:
        return None
    if depth not in (8, 16) and not (depth == 8 and ctype == 3):
        if ctype != 3:
            return None
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ctype)
    if channels is None:
        return None

    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error:
        return None

    bpp = max(1, channels * (depth // 8))
    stride = (width * channels * depth + 7) // 8
    if len(raw) < (stride + 1) * height:
        return None

    pixels: list[tuple[int, int, int]] = []
    previous = bytearray(stride)
    offset = 0
    for row in range(height):
        filter_type = raw[offset]
        line = bytearray(raw[offset + 1:offset + 1 + stride])
        offset += 1 + stride
        # PNG scanline filters (spec 9.2) — must be undone.
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = previous[i]
            c = previous[i - bpp] if i >= bpp else 0
            if filter_type == 1:
                line[i] = (line[i] + a) & 0xFF
            elif filter_type == 2:
                line[i] = (line[i] + b) & 0xFF
            elif filter_type == 3:
                line[i] = (line[i] + (a + b) // 2) & 0xFF
            elif filter_type == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 0xFF
        previous = line

        if row % step:
            continue
        size = depth // 8 or 1
        for col in range(0, width, step):
            base = col * channels * size
            if base + channels * size > len(line):
                break
            if ctype == 3:
                index = line[base] * 3
                if index + 3 <= len(palette):
                    pixels.append((palette[index], palette[index + 1],
                                   palette[index + 2]))
            elif ctype in (0, 4):
                grey = line[base]
                pixels.append((grey, grey, grey))
            else:
                pixels.append((line[base], line[base + size],
                               line[base + 2 * size]))
    return pixels or None


def _quantize(pixels: list[tuple[int, int, int]],
              bits: int = 6) -> list[tuple[tuple[int, int, int], int]]:
    """Coarse 3D histogram; returns a list of (mean color, count) sorted by weight."""
    shift = 8 - bits
    buckets: dict[int, list[int]] = {}
    for r, g, b in pixels:
        key = ((r >> shift) << (bits * 2)) | ((g >> shift) << bits) | (b >> shift)
        acc = buckets.get(key)
        if acc is None:
            buckets[key] = [r, g, b, 1]
        else:
            acc[0] += r; acc[1] += g; acc[2] += b; acc[3] += 1
    out = [((a[0] // a[3], a[1] // a[3], a[2] // a[3]), a[3])
           for a in buckets.values()]
    out.sort(key=lambda item: item[1], reverse=True)
    return out


# ------------------------------------------------------- role assignment ---
def _pick_hues(dominant: list[tuple[tuple[int, int, int], int]]
               ) -> tuple[float, float, float, float]:
    """(base hue, base saturation, accent hue, accent saturation)."""
    import math

    total = sum(weight for _, weight in dominant) or 1

    # Base: hue average of the heaviest colors — the image's "mood".
    #
    # Hue is a CIRCULAR quantity: the arithmetic mean of 350° and 10° is
    # 180° (cyan), while the right answer is 0° (red). So hues are summed as
    # unit vectors and converted back to an angle. The weight is pixel count
    # × saturation: grey pixels should not decide the image's hue.
    x = y = 0.0
    base_sat, seen = 0.0, 0.0
    for rgb, weight in dominant[:32]:
        hue, sat, _ = _hsl(rgb)
        influence = weight * sat
        x += math.cos(math.radians(hue)) * influence
        y += math.sin(math.radians(hue)) * influence
        base_sat += sat * weight
        seen += weight
    base_hue = math.degrees(math.atan2(y, x)) % 360 if (x or y) else 0.0
    if seen:
        base_sat /= seen

    # Accent: the most COLORFUL bucket. An accent is low-weight by definition
    # (it covers a small part of the image), so looking only at the first N
    # buckets by weight would never see it — all buckets are scanned and
    # saturation dominates the score (sat², weight is only a weak factor).
    # Otherwise the ground's grey-green was picked instead of gruvbox's orange accent.
    best, best_score = None, -1.0
    for rgb, weight in dominant:
        hue, sat, light = _hsl(rgb)
        if not 0.10 < light < 0.95:
            continue
        score = (sat ** 2) * ((weight / total) ** 0.15)
        if score > best_score:
            best, best_score = (hue, sat), score

    if best is None:
        return base_hue, base_sat, base_hue, max(base_sat, 0.55)
    accent_hue, accent_sat = best
    # The generated color must be vivid: 0.35 saturation at 0.70 lightness in HSL
    # is a washed-out pastel. The image's own saturation is kept but floored.
    return base_hue, base_sat, accent_hue, max(accent_sat, 0.55)


def _compose(base_hue: float, base_sat: float, accent_hue: float,
             accent_sat: float, dark: bool) -> dict[str, str]:
    """Builds the 11 semantic colors from hue/saturation."""
    targets = _TARGETS_DARK if dark else _TARGETS_LIGHT
    # Second accent: differ in hue from the first so the gradient border
    # (col.active_border) does not look like a single color.
    accent2_hue = accent_hue + (50 if accent_sat > 0.25 else 180)

    palette: dict[str, str] = {}
    for key, (light, sat_mul, source) in targets.items():
        if source == "base":
            hue, sat = base_hue, base_sat * sat_mul
        elif source == "accent":
            hue, sat = accent_hue, accent_sat * sat_mul
        elif source == "accent2":
            hue, sat = accent2_hue, accent_sat * sat_mul
        else:                                   # "fixed:<degrees>"
            hue = float(source.split(":", 1)[1])
            # Fixed-hue colors follow the palette's overall vividness, but a
            # minimum saturation is kept so they never wash out completely.
            sat = max(0.45, accent_sat) * sat_mul
        palette[key] = _build(hue, sat, light)
    return palette


def _enforce_readability(palette: dict[str, str]) -> dict[str, str]:
    """Makes text colors readable against the background."""
    palette["FG"] = _ensure_contrast(palette["FG"], palette["BG"], _MIN_CONTRAST)
    palette["SUBTEXT"] = _ensure_contrast(palette["SUBTEXT"], palette["BG"],
                                          _MIN_CONTRAST_SUB)
    # The accent color must be visible on the background in the bar/borders.
    palette["ACCENT"] = _ensure_contrast(palette["ACCENT"], palette["BG"], 3.0)
    palette["ACCENT2"] = _ensure_contrast(palette["ACCENT2"], palette["BG"], 3.0)
    return palette


# --------------------------------------------------------------- public ----
def extract(image: str | Path, dark: bool = True,
            backend: str = "auto") -> dict[str, str] | None:
    """Builds an 11-key palette from an image; None on failure.

    ``backend``: ``auto`` (try in order) · ``matugen`` · ``magick`` · ``python``
    """
    path = Path(image).expanduser()
    if not path.is_file():
        return None

    if backend in ("auto", "matugen"):
        raw = _from_matugen(path, dark)
        if raw:
            # matugen already gives a consistent scheme; we only fill in the
            # missing colors (GREEN/YELLOW/CYAN — no Material You equivalents)
            # by toning them, and verify readability.
            # Hue comes from the target table; only saturation is taken from here.
            _hue, sat, _ = _hsl(_hex_to_rgb(raw["ACCENT"]))
            targets = _TARGETS_DARK if dark else _TARGETS_LIGHT
            for key in ("GREEN", "YELLOW", "CYAN", "RED"):
                if key in raw:
                    continue
                light, sat_mul, source = targets[key]
                raw[key] = _build(float(source.split(":", 1)[1]),
                                  max(0.45, sat) * sat_mul, light)
            for key in themes.KEYS:
                raw.setdefault(key, themes.THEMES[themes.DEFAULT][key])
            return _enforce_readability(raw)
        if backend == "matugen":
            return None

    dominant: list[tuple[tuple[int, int, int], int]] | None = None
    if backend in ("auto", "magick"):
        dominant = _from_magick(path)
        if backend == "magick" and not dominant:
            return None
    if dominant is None and backend in ("auto", "python"):
        pixels = _png_pixels(path)
        dominant = _quantize(pixels) if pixels else None
    if not dominant:
        return None

    base_hue, base_sat, accent_hue, accent_sat = _pick_hues(dominant)
    return _enforce_readability(
        _compose(base_hue, base_sat, accent_hue, accent_sat, dark))


def backends_available() -> list[str]:
    """Backends available on this machine — shown by doctor/GUI."""
    found = []
    if shutil.which("matugen"):
        found.append("matugen")
    if shutil.which("magick") or shutil.which("convert"):
        found.append("magick")
    found.append("python")      # always available (PNG only)
    return found


# ------------------------------------------------------------ manual tone --
#: Hue rotation applies only to these. RED/GREEN/YELLOW/CYAN carry meaning
#: (error, success, warning): a "red" battery warning rotated 120° would look
#: green. Saturation is still applied to all of them.
TONE_KEYS = ("BG", "BG_DARK", "SURFACE", "FG", "SUBTEXT", "ACCENT", "ACCENT2")
_BACKGROUND_KEYS = ("BG", "BG_DARK", "SURFACE")


def tone_from(values: dict[str, str]) -> tuple[float, float, float]:
    """Reads (hue °, saturation %, background lightness %) from the settings."""
    def number(key: str) -> float:
        try:
            return float(values.get(key, "") or 0)
        except ValueError:
            return 0.0
    return (number("PALETTE_HUE"), number("PALETTE_SATURATION"),
            number("PALETTE_LIGHTNESS"))


def adjust(palette: dict[str, str], hue: float = 0, saturation: float = 0,
           lightness: float = 0,
           hue_keys: tuple[str, ...] | None = TONE_KEYS) -> dict[str, str]:
    """Shifts the whole palette by hand: hue rotation, saturation, lightness.

    Applied the same way to a wallpaper-extracted palette and to a built-in
    theme — so the user can say "nice colors, but a bit bluer". Afterwards
    text/accent readability is restored: someone lightening the background
    does not expect white text to vanish. If all are zero the palette is
    returned unchanged. ``hue_keys=None`` applies the hue to every color
    (for colors with no role, e.g. the wallpaper's Vibrant/Muted samples).
    """
    if not (hue or saturation or lightness):
        return palette
    out = dict(palette)
    factor = max(-1.0, min(1.0, saturation / 100.0))
    shift = max(-0.5, min(0.5, lightness / 100.0))
    for key, value in palette.items():
        try:
            rgb = _hex_to_rgb(value)
        except ValueError:
            continue
        h, s, light = _hsl(rgb)
        if hue_keys is None or key in hue_keys:
            h += hue
        # Negative: toward grey; positive: that fraction of the remaining saturation.
        s = s * (1 + factor) if factor < 0 else s + (1 - s) * factor
        if key in _BACKGROUND_KEYS:
            light += shift
        out[key] = _build(h, s, light)
    if all(key in out for key in ("BG", "FG", "SUBTEXT", "ACCENT", "ACCENT2")):
        _enforce_readability(out)
    return out
