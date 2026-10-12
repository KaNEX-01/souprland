"""Edited copies of Wallpaper Engine scenes (profile recipes).

Some profiles play a Workshop scene not as-is but in a modified form (e.g. st-gozcu:
ash/fog off, the tower's smoke as a separate bright, rippling layer, and a pulsing
glow on the moon/river/smoke). Workshop content is someone else's work, so it is
NOT copied into the repo; only the recipe lives here. The recipe produces a copy
from the user's own Workshop download under
``~/.local/share/hyprsetup-wallpapers/<id>/``; if that folder exists,
``hypr/scripts/wallpaperengine.sh`` plays it instead of the Workshop one. The
original is untouched; deleting the folder brings back the Workshop version.

Formats (verified with linux-wallpaperengine):
  * scene.pkg — "PKGV0011": version string, file count, (name, offset, size)
    entries, then the data. Strings are uint32 length-prefixed.
  * .tex — TEXV0005/TEXI0001 header + TEXB0003: image count, FreeImage format
    (2 = JPEG, 13 = PNG), mipmap count, and for each mipmap
    (width, height, compression, uncompressed size, size, data).
  * linux-wallpaperengine looks up effect materials/shaders at the package ROOT,
    not in the effect folder (materials/effects/X.json, shaders/effects/X.*); the
    files of the effects used are added to the package.

Recipes need numpy, Pillow and OpenCV (python-opencv); if any is missing, no copy
is made and the original Workshop scene plays.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import struct
from pathlib import Path

WORKSHOP_APP = "431960"
STAMP = ".hyprsetup-recipe"


# ------------------------------------------------------------- paths ------
def _steam_roots() -> list[Path]:
    home = Path.home()
    return [home / ".local/share/Steam", home / ".steam/steam",
            home / ".var/app/com.valvesoftware.Steam/.local/share/Steam"]


def workshop_dir(ident: str) -> Path | None:
    for root in _steam_roots():
        path = root / "steamapps/workshop/content" / WORKSHOP_APP / ident
        if (path / "project.json").is_file():
            return path
    return None


def assets_dir() -> Path | None:
    for root in _steam_roots():
        path = root / "steamapps/common/wallpaper_engine/assets"
        if path.is_dir():
            return path
    return None


def edited_root() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local/share")
    return Path(base) / "hyprsetup-wallpapers"


# --------------------------------------------------------- scene.pkg ------
def _rstr(buf: io.BytesIO) -> str:
    (length,) = struct.unpack("<I", buf.read(4))
    return buf.read(length).decode()


def read_pkg(path: Path) -> tuple[str, dict[str, bytes]]:
    raw = Path(path).read_bytes()
    buf = io.BytesIO(raw)
    version = _rstr(buf)
    (count,) = struct.unpack("<I", buf.read(4))
    entries = [(_rstr(buf), *struct.unpack("<II", buf.read(8))) for _ in range(count)]
    base = buf.tell()
    return version, {name: raw[base + off:base + off + size] for name, off, size in entries}


def write_pkg(path: Path, version: str, files: dict[str, bytes]) -> None:
    out = io.BytesIO()

    def wstr(text: str) -> None:
        data = text.encode()
        out.write(struct.pack("<I", len(data)) + data)

    wstr(version)
    out.write(struct.pack("<I", len(files)))
    offset = 0
    for name, blob in files.items():
        wstr(name)
        out.write(struct.pack("<II", offset, len(blob)))
        offset += len(blob)
    for blob in files.values():
        out.write(blob)
    Path(path).write_bytes(out.getvalue())


# --------------------------------------------------------------- .tex -----
def tex_first_image(tex: bytes) -> bytes:
    """Embedded JPEG/PNG data of the largest mipmap."""
    i = tex.index(b"TEXB0003") + 9
    _count, _fif, _mips = struct.unpack_from("<III", tex, i)
    _w, _h, _comp, _usz, size = struct.unpack_from("<IIIII", tex, i + 12)
    start = i + 32
    return tex[start:start + size]


def make_tex(header_from: bytes, image, fmt: str) -> bytes:
    """A new 10-mipmap texture from ``image`` (PIL) with ``header_from``'s TEXV/TEXI
    header. The dimensions must match the header's."""
    from PIL import Image

    fif = {"JPEG": 2, "PNG": 13}[fmt]
    sizes = [image.size]
    while len(sizes) < 10:
        w, h = sizes[-1]
        sizes.append((max(1, w // 2), max(1, h // 2)))
    body = b"TEXB0003\0" + struct.pack("<III", 1, fif, len(sizes))
    for w, h in sizes:
        buf = io.BytesIO()
        mip = image if (w, h) == image.size else image.resize((w, h), Image.LANCZOS)
        if fmt == "JPEG":
            mip.convert("RGB").save(buf, "JPEG", quality=95, subsampling=0)
        else:
            mip.save(buf, "PNG", optimize=True)
        blob = buf.getvalue()
        body += struct.pack("<IIIII", w, h, 0, 0, len(blob)) + blob
    return header_from[:header_from.index(b"TEXB0003")] + body


def _layer(base: dict, name: str, ident: int, effects: list) -> dict:
    return {"alignment": "center", "alpha": 1.0, "angles": "0.00000 0.00000 0.00000",
            "brightness": 1.0, "color": "1.00000 1.00000 1.00000", "colorBlendMode": 0,
            "copybackground": False, "id": ident, "image": f"models/{name}.json",
            "ledsource": False, "locktransforms": True, "name": name,
            "origin": base["origin"], "parallaxDepth": "1.00000 1.00000",
            "perspective": False, "scale": "1.00000 1.00000 1.00000",
            "size": base["size"], "solid": False, "visible": True, "effects": effects}


def _effect(name: str, ident: int, combos: dict, values: dict) -> dict:
    return {"file": f"effects/{name}/effect.json", "id": ident, "name": "",
            "passes": [{"combos": combos, "constantshadervalues": values, "id": ident + 1}],
            "visible": True}


def _image_material(files: dict[str, bytes], name: str, blending: str) -> None:
    files[f"materials/{name}.json"] = json.dumps({"passes": [{
        "blending": blending, "combos": {"version": 2}, "cullmode": "nocull",
        "depthtest": "disabled", "depthwrite": "disabled",
        "shader": "genericimage2", "textures": [name]}]}, indent=1).encode()
    files[f"models/{name}.json"] = json.dumps(
        {"autosize": True, "material": f"materials/{name}.json"}).encode()


def _bundle_effects(files: dict[str, bytes], names: tuple[str, ...]) -> None:
    assets = assets_dir()
    if assets is None:
        raise RuntimeError("Wallpaper Engine assets folder not found")
    for name in names:
        root = assets / "effects" / name
        for path in root.rglob("*"):
            rel = path.relative_to(root)
            if path.is_file() and rel.parts[0] in ("materials", "shaders"):
                files[rel.as_posix()] = path.read_bytes()


# ----------------------------------------------------------- recipes ----
def _mountains_green(src: Path, dst: Path) -> None:
    """Workshop 2363450232 "mountains green" → the st-gozcu version.

    * Ash and Fog 1 particles are off.
    * The green smoke painted into the image is removed (inpaint) and put back as
      a separate bright, rippling, pulsing layer.
    * An additive glow layer for the moon, river and smoke brightens and fades on a
      ~5-6 s cycle (never disappears even at its dimmest).
    * The moon's own green is dimmed 28%; bloom on (1.0 / 0.65).
    """
    import cv2
    import numpy as np
    from PIL import Image

    version, files = read_pkg(src / "scene.pkg")
    tex_name = "materials/mountains green.tex"
    tex = files[tex_name]
    orig = cv2.imdecode(np.frombuffer(tex_first_image(tex), np.uint8), cv2.IMREAD_COLOR)
    height, width = orig.shape[:2]
    of = orig.astype(np.float32)
    b, g, r = of[..., 0], of[..., 1], of[..., 2]

    # The tower's smoke: green mask → erase from the image.
    y0, y1, x0, x1 = 300, 652, 1860, 2060
    green = (g.astype(int) - r.astype(int) > 10) & (g.astype(int) - b.astype(int) > 0)
    mask = np.zeros((height, width), np.uint8)
    mask[y0:y1, x0:x1] = green[y0:y1, x0:x1].astype(np.uint8) * 255
    mask = cv2.dilate(mask, np.ones((9, 9), np.uint8))
    clean = cv2.inpaint(orig, mask, 12, cv2.INPAINT_TELEA).astype(np.float32)
    weight = cv2.GaussianBlur(mask, (15, 15), 0)[..., None] / 255.0
    clean += np.random.default_rng(1).normal(0, 1.6, clean.shape) * weight

    # Dim the moon's green (excluding the river and tower).
    moon = ((clean[..., 1] - clean[..., 2]) > 40).astype(np.float32)
    moon[880:] = 0
    moon[:, 1850:] = 0
    moon = cv2.GaussianBlur(moon, (0, 0), 1.5)[..., None]
    grey = np.array([34, 33, 34], np.float32)
    clean = clean * (1 - moon) + (grey + (clean - grey) * 0.72) * moon
    clean = np.clip(clean, 0, 255).astype(np.uint8)

    # Smoke layer: original trace, light mint, soft edge.
    greenness = np.clip((g - r - 6) / 120.0, 0, 1)
    smoke = np.zeros((height, width), np.float32)
    smoke[y0:y1, x0:x1] = greenness[y0:y1, x0:x1]
    smoke = np.clip(cv2.GaussianBlur(smoke, (0, 0), 2.5) * 1.6, 0, 1)
    alpha = np.clip(np.maximum(smoke, cv2.GaussianBlur(smoke, (0, 0), 14) * 0.9), 0, 1)
    core = np.array([170, 255, 200], np.float32)        # RGB
    mint = np.array([40, 245, 150], np.float32)
    colour = mint * (1 - smoke[..., None]) + core * smoke[..., None]
    smoke_rgba = np.dstack([colour * 0.75, alpha * 0.6 * 255]).astype(np.uint8)

    # Glow layer: moon (dimmed) + river (strong) + smoke.
    bright = np.clip((g - r - 40) / 100.0, 0, 1) * (g > 120)
    bright = np.maximum(bright, smoke * 0.8)
    bright[:880, :1850] *= 0.6
    glow = (cv2.GaussianBlur(bright, (0, 0), 10) * 0.9
            + cv2.GaussianBlur(bright, (0, 0), 38) * 1.4
            + cv2.GaussianBlur(bright, (0, 0), 90) * 1.2)
    river = bright.copy()
    river[:880] = 0
    glow += cv2.GaussianBlur(river, (0, 0), 8) * 2.2 + cv2.GaussianBlur(river, (0, 0), 28) * 2.6
    glow = np.clip(glow, 0, 1)
    glow_rgb = np.array([60, 255, 170], np.float32) * glow[..., None]
    glow_rgba = np.dstack([glow_rgb * 0.4, glow * 0.4 * 255]).astype(np.uint8)

    files[tex_name] = make_tex(tex, Image.fromarray(clean[..., ::-1]), "JPEG")
    files["materials/hs smoke.tex"] = make_tex(tex, Image.fromarray(smoke_rgba, "RGBA"), "PNG")
    files["materials/hs glow.tex"] = make_tex(tex, Image.fromarray(glow_rgba, "RGBA"), "PNG")
    _image_material(files, "hs smoke", "translucent")
    _image_material(files, "hs glow", "additive")
    _bundle_effects(files, ("waterwaves", "pulse"))

    scene = json.loads(files["scene.json"])
    base = next(o for o in scene["objects"] if o.get("name") == "mountains green")
    for obj in scene["objects"]:
        if obj.get("name") in ("Ash", "Fog 1"):
            obj["visible"] = False
    scene["objects"] = [o for o in scene["objects"]
                        if o.get("name") not in ("hs smoke", "hs glow")]
    scene["objects"] += [
        _layer(base, "hs smoke", 100, [
            _effect("waterwaves", 101, {}, {"speed": 1.6, "scale": 60.0,
                                            "strength": 0.025, "exponent": 1.0}),
            _effect("pulse", 103, {"PULSEALPHA": 1, "PULSECOLOR": 0},
                    {"speed": 1.1, "amount": 0.75, "bounds": "-1.0 1.0",
                     "phase": 0.0, "power": 1.0})]),
        _layer(base, "hs glow", 110, [
            _effect("pulse", 105, {"PULSEALPHA": 1, "PULSECOLOR": 0},
                    {"speed": 1.1, "amount": 0.75, "bounds": "-0.4 1.0",
                     "phase": 0.0, "power": 1.0})]),
    ]
    general = scene["general"]
    general.update(bloom=True, bloomstrength=1.0, bloomthreshold=0.65)
    files["scene.json"] = json.dumps(scene, indent=1).encode()

    dst.mkdir(parents=True, exist_ok=True)
    write_pkg(dst / "scene.pkg", version, files)
    project = json.loads((src / "project.json").read_text(encoding="utf-8"))
    project["title"] = f"{project.get('title', '')} (glowing moon, river and smoke)"
    (dst / "project.json").write_text(json.dumps(project, indent=1, ensure_ascii=False),
                                      encoding="utf-8")
    Image.fromarray(clean[..., ::-1]).resize((976, 549)).save(dst / "preview.jpg", quality=90)


#: Workshop id → recipe. When a recipe (its source code) changes, the copy is rebuilt.
RECIPES = {"2363450232": _mountains_green}


def _recipe_stamp(ident: str) -> str:
    import inspect

    source = inspect.getsource(RECIPES[ident]) + inspect.getsource(make_tex)
    return hashlib.sha256(source.encode()).hexdigest()[:16]


def ensure(ident: str) -> tuple[Path | None, str]:
    """Keeps the edited copy of a scene that has a recipe up to date.

    Returns: (copy folder or None, note). None if there is no recipe, no Workshop
    download or a missing dependency — the original plays then.
    """
    ident = (ident or "").strip()
    if ident not in RECIPES:
        return None, ""
    dst = edited_root() / ident
    stamp = _recipe_stamp(ident)
    if (dst / STAMP).is_file() and (dst / STAMP).read_text().strip() == stamp \
            and (dst / "scene.pkg").is_file():
        return dst, "ready"
    src = workshop_dir(ident)
    if src is None:
        return None, f"Workshop {ident} not downloaded (Steam → Wallpaper Engine)"
    try:
        RECIPES[ident](src, dst)
    except ImportError as exc:
        return None, f"editing needs {exc.name} (python-opencv/numpy/pillow)"
    except (OSError, ValueError, KeyError, RuntimeError, StopIteration) as exc:
        return None, f"could not edit: {exc}"
    (dst / STAMP).write_text(stamp + "\n")
    return dst, "generated"


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python -m hyprsetup.wpedit <workshop-id>…  "
              f"(recipes: {', '.join(RECIPES)})")
        return 2
    status = 0
    for ident in argv:
        path, note = ensure(ident)
        print(f"{ident}: {path or '—'} ({note or 'no recipe'})")
        status |= path is None
    return status


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))
