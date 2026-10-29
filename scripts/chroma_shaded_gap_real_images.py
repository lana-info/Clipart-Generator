"""Measure the shaded-gap film on real generated frames (engine -> matting -> clean).

For every input frame the script runs the production chain and reports the
control point, the strict film mask over the gaps, visible/opaque pixel counts,
the alpha sum, and — when a pre-fix baseline is given — the pixels the baseline
showed opaque that the fix no longer does, split into key-aligned and paint
pixels. Optionally renders composites and zoom strips for visual review.

Usage:
    python scripts/chroma_shaded_gap_real_images.py NAME=PATH [...] \
        [--baseline DIR] [--control NAME=X,Y] [--zoom NAME=X0,Y0,X1,Y1] [--out-dir DIR]

``--baseline DIR`` holds the pre-fix chroma_key.py and chroma_matting.py.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

BACKGROUNDS = {"white": (255, 255, 255), "black": (0, 0, 0),
               "magenta": (255, 0, 255), "cyan": (0, 255, 255)}


def chroma_angle(rgb: np.ndarray, key: np.ndarray) -> np.ndarray:
    """Degrees between every pixel's chroma and the key's, computed locally so the
    strict film mask is identical whether the pre-fix or the fixed modules run."""
    key_chroma = np.array([key[0] - key[1], key[1] - key[2]], np.float32)
    pixel_chroma = np.stack((rgb[..., 0] - rgb[..., 1], rgb[..., 1] - rgb[..., 2]), axis=-1).astype(np.float32)
    norm = np.linalg.norm(pixel_chroma, axis=-1) * max(float(np.linalg.norm(key_chroma)), 1e-6)
    cosine = (pixel_chroma @ key_chroma) / np.maximum(norm, 1e-6)
    return np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))


def key_aligned(rgb: np.ndarray, key: np.ndarray) -> np.ndarray:
    other = np.maximum(rgb[..., 0], rgb[..., 1])
    lead = rgb[..., 2] - other
    return (chroma_angle(rgb, key) <= 20.0) & (lead >= 30.0)


def film_mask(rgb: np.ndarray, key: np.ndarray) -> np.ndarray:
    """Strict shaded-key film: key-hued, well below the key level, away from both
    solid paint and the plain background."""
    angle = chroma_angle(rgb, key)
    near = np.linalg.norm(rgb - key, axis=2) < 0.18 * np.linalg.norm(key)
    candidate = key_aligned(rgb, key) & (rgb[..., 2] < 0.95 * key[2]) & ~near
    paint = angle >= 45.0
    clearance = cv2.distanceTransform((~near).astype(np.uint8), cv2.DIST_L2, 5)
    paint_clearance = cv2.distanceTransform((~paint).astype(np.uint8), cv2.DIST_L2, 5)
    return candidate & (clearance > 2) & (paint_clearance > 2)


def production(source: Image.Image, key_module, matting_module, key_color: str = "blue"):
    engine = key_module.finish_rim_cleanup(
        key_module.remove_chroma_key_automatic(source, key_color, subject_profile="opaque_clipart"),
        "opaque_clipart",
    )
    matted = matting_module.matte_edges(source, engine, key_color)
    if matted is not engine:
        from alpha_cleanup import DEBRIS_MIN_GAP, clean_alpha
        from edge_tint import suppress_key_tint

        matted = suppress_key_tint(clean_alpha(matted, island_min_gap=DEBRIS_MIN_GAP), key_color)
    return engine, matted


def load_baseline_modules(directory: Path):
    """Import the pre-fix chroma modules from ``directory`` without disturbing the
    fixed ones already in sys.modules."""
    saved = sys.path[:]
    for name in ("chroma_key", "chroma_matting"):
        sys.modules.pop(name, None)
    sys.path.insert(0, str(directory))
    try:
        import chroma_key as base_key
        import chroma_matting as base_matting
    finally:
        sys.path[:] = saved
        for name in ("chroma_key", "chroma_matting"):
            sys.modules.pop(name, None)
    return base_key, base_matting


def plate(image: Image.Image, colour, scale: int = 1) -> Image.Image:
    out = Image.new("RGBA", image.size, colour + (255,))
    out.alpha_composite(image)
    out = out.convert("RGB")
    if scale != 1:
        out = out.resize((out.width * scale, out.height * scale), Image.NEAREST)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("images", nargs="+", metavar="NAME=PATH", help="frame to measure")
    parser.add_argument("--baseline", type=Path, default=None,
                        help="directory with pre-fix chroma_key.py/chroma_matting.py to compare against")
    parser.add_argument("--control", action="append", default=[], metavar="NAME=X,Y",
                        help="control point of an image to report (repeatable)")
    parser.add_argument("--zoom", action="append", default=[], metavar="NAME=X0,Y0,X1,Y1",
                        help="crevice zoom strip of a composite (repeatable)")
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="write composites on white/black/magenta/cyan and zoom strips here")
    args = parser.parse_args()

    import chroma_key as fixed_key
    import chroma_matting as fixed_matting

    controls = {}
    for entry in args.control:
        name, _, point = entry.partition("=")
        x, y = (int(part) for part in point.split(","))
        controls[name] = (x, y)
    zooms = {}
    for entry in args.zoom:
        name, _, box = entry.partition("=")
        zooms[name] = tuple(int(part) for part in box.split(","))

    baseline_modules = load_baseline_modules(args.baseline) if args.baseline is not None else None
    print(f"fixed    : {fixed_key.__file__}")
    if baseline_modules is not None:
        print(f"baseline : {baseline_modules[0].__file__}")

    for entry in args.images:
        name, _, raw_path = entry.partition("=")
        if not raw_path:
            parser.error(f"expected NAME=PATH, got {entry!r}")
        source = Image.open(raw_path).convert("RGBA")
        rgb = np.asarray(source)[..., :3].astype(np.float32)
        key = fixed_key._measured_border_key(source)
        film = film_mask(rgb, key)
        fix_engine, fix_final = production(source, fixed_key, fixed_matting)
        fix_alpha = np.asarray(fix_final)[..., 3].astype(int)
        base_final = base_alpha = None
        if baseline_modules is not None:
            _, base_final = production(source, *baseline_modules)
            base_alpha = np.asarray(base_final)[..., 3].astype(int)
        print(f"== {name} ({raw_path})")
        control = controls.get(name)
        if control is not None:
            x, y = control
            if base_alpha is None:
                print(f"   control ({x},{y}): final={fix_alpha[y, x]}")
            else:
                print(f"   control ({x},{y}): baseline={base_alpha[y, x]} -> fix={fix_alpha[y, x]}")
        if base_alpha is None:
            print(f"   strict film: engine {int((film & (np.asarray(fix_engine)[..., 3] > 0)).sum())}"
                  f" -> final {int((film & (fix_alpha > 0)).sum())}")
        else:
            print(f"   strict film: baseline {int((film & (base_alpha > 0)).sum())}"
                  f" -> fix {int((film & (fix_alpha > 0)).sum())}"
                  f" (fix engine {int((film & (np.asarray(fix_engine)[..., 3] > 0)).sum())})")
        print(f"   visible px: {int((fix_alpha > 0).sum())}; opaque px: {int((fix_alpha == 255).sum())}; "
              f"sum alpha: {fix_alpha.sum() / 1e6:.3f}M")
        if base_alpha is not None:
            changed = (base_alpha == 255) & (fix_alpha < 255)
            aligned = key_aligned(rgb, key)
            print(f"   baseline-opaque -> fix-not-opaque: {int(changed.sum())} "
                  f"(key-aligned {int((changed & aligned).sum())}, paint {int((changed & ~aligned).sum())}); "
                  f"new opaque: {int(((base_alpha < 255) & (fix_alpha == 255)).sum())}")
        if args.out_dir is not None:
            args.out_dir.mkdir(parents=True, exist_ok=True)
            for colour_name, colour in BACKGROUNDS.items():
                plate(fix_final, colour).save(args.out_dir / f"{name}_fixed_on_{colour_name}.png")
            if base_final is not None:
                for colour_name, colour in BACKGROUNDS.items():
                    plate(base_final, colour).save(args.out_dir / f"{name}_baseline_on_{colour_name}.png")
            box = zooms.get(name)
            if box is not None and base_final is not None:
                tiles = [Image.fromarray(np.asarray(source)[box[1]:box[3], box[0]:box[2], :3]).convert("RGB"),
                         plate(base_final.crop(box), (255, 255, 255)),
                         plate(fix_final.crop(box), (255, 255, 255))]
                width, height = tiles[0].size
                strip = Image.new("RGB", (width * 3 + 20, height), (190, 190, 190))
                for index, tile in enumerate(tiles):
                    strip.paste(tile.resize((width, height), Image.NEAREST), (index * (width + 10), 0))
                strip.save(args.out_dir / f"{name}_zoom_source_baseline_fixed.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
