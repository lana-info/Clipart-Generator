"""Synthetic acceptance harness for shaded-key gap removal.

Ground truth is exact: the key background is uniform, the generator shades only
the narrow gaps between subject parts (ambient occlusion in a crevice), so gap
pixels are background and the drawn shapes and details are opaque subject. The
shade profile follows the one measured on rough_89 (438,946): a dark core with
a fast rim ramp plus a few levels of pixel-to-pixel variation.

Usage:
    python scripts/chroma_shaded_gap_synth.py [--baseline DIR] [--out-dir DIR]

``--baseline DIR`` points at a directory holding the pre-fix chroma_key.py and
chroma_matting.py; the run then measures both module sets in one process and
reports regressions (deviations that exist only after the fix). Without it only
the current modules are measured.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

CREAM = np.array([235, 220, 190], np.float32)
GREEN = np.array([90, 115, 45], np.float32)
DARK_STEM = np.array([60, 75, 25], np.float32)
DARK_SHADOW = np.array([22, 34, 12], np.float32)
NAVY = np.array([35, 45, 110], np.float32)
VIOLET = np.array([110, 60, 140], np.float32)

CANVAS = 360
TOP = 40
BOTTOM = 320
ELEMENTS = ("stem1", "stem2", "wisp", "navy", "violet")
DETAIL_MINIMUMS = {"stem1": 200.0, "stem2": 250.0, "navy": 250.0, "violet": 250.0}


def build(blue: int, gap_width: int, *, enclosed: bool):
    """Two paint blocks separated by a gap of ``gap_width`` px plus drawn details."""
    key = np.array([0, 2, blue], np.float32)
    rgb = np.tile(key, (CANVAS, CANVAS, 1))
    subject = np.zeros((CANVAS, CANVAS), bool)
    left_x0, left_x1 = 40, 140
    right_x0, right_x1 = left_x1 + gap_width, left_x1 + gap_width + 100
    y0 = TOP
    y1 = BOTTOM - 40 if enclosed else BOTTOM
    rgb[y0:y1, left_x0:left_x1] = GREEN
    rgb[y0:y1, right_x0:right_x1] = CREAM
    subject[y0:y1, left_x0:left_x1] = True
    subject[y0:y1, right_x0:right_x1] = True
    gap = np.zeros((CANVAS, CANVAS), bool)
    gap[y0:y1, left_x1:right_x0] = True

    details = {}
    rgb[320:355, 300:301] = DARK_STEM
    details["stem1"] = np.zeros((CANVAS, CANVAS), bool)
    details["stem1"][320:355, 300:301] = True
    rgb[320:355, 306:308] = DARK_STEM
    details["stem2"] = np.zeros((CANVAS, CANVAS), bool)
    details["stem2"][320:355, 306:308] = True
    rgb[300:360, 316:317] = CREAM
    details["wisp"] = np.zeros((CANVAS, CANVAS), bool)
    details["wisp"][300:360, 316:317] = True
    rgb[200:260, 60:80] = NAVY
    details["navy"] = np.zeros((CANVAS, CANVAS), bool)
    details["navy"][202:258, 62:78] = True
    rgb[200:260, 95:115] = VIOLET
    details["violet"] = np.zeros((CANVAS, CANVAS), bool)
    details["violet"][202:258, 97:113] = True
    subject |= details["navy"] | details["violet"]
    return key, rgb, subject, gap, details


def shade(key, rgb, subject, gap, *, strength=0.60, ramp=3.0):
    """Darken the gap the way the generator does: a dark core with a fast rim ramp.

    Measured on rough_89 (438,946): the blue channel falls from 253 in the open
    background to 117-145 over an eleven-pixel crevice, with most of the drop
    happening within three pixels of each side. Real output also varies by a few
    levels from pixel to pixel, so a low-amplitude pattern is added; a core that
    is perfectly flat would be indistinguishable from painted detail.
    """
    from scipy import ndimage

    height, width = subject.shape
    yy, xx = np.indices((height, width))
    jitter = np.rint(3.0 * np.sin(xx / 3.1) + 3.0 * np.cos(yy / 2.7))
    depth = ndimage.distance_transform_edt(~subject)
    amount = strength * np.clip(depth / ramp, 0.0, 1.0)
    shaded = (1.0 - amount[..., None]) * key + amount[..., None] * DARK_SHADOW
    rgb = rgb.copy()
    rgb[gap] = np.clip(shaded[gap] + jitter[gap, None], 0, 255)
    return rgb


def load_baseline_modules(directory: Path):
    """Import the pre-fix chroma modules from ``directory`` without disturbing the
    current ones already in sys.modules."""
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


def production(source: Image.Image, key_module, matting_module, key_color: str = "blue"):
    """Engine, then the matting/cleaning chain main.py applies to a cut-out."""
    from alpha_cleanup import DEBRIS_MIN_GAP, clean_alpha
    from edge_tint import suppress_key_tint

    engine = key_module.finish_rim_cleanup(
        key_module.remove_chroma_key_automatic(source, key_color, subject_profile="opaque_clipart"),
        "opaque_clipart",
    )
    matted = matting_module.matte_edges(source, engine, key_color)
    if matted is not engine:
        matted = suppress_key_tint(clean_alpha(matted, island_min_gap=DEBRIS_MIN_GAP), key_color)
    return source, engine, matted


def run(rgb: np.ndarray, key_color: str = "blue"):
    """Production chain with the current modules."""
    import chroma_key
    import chroma_matting

    source = Image.fromarray(np.clip(np.rint(rgb), 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    return production(source, chroma_key, chroma_matting, key_color)


def measure(rgb: np.ndarray, subject: np.ndarray, gap: np.ndarray, details: dict,
            key_color: str = "blue", modules=None):
    """Return (gap core max alpha, violating core pixels, detail min alphas, engine core, rim median, images)."""
    import cv2

    if modules is None:
        source, engine, final = run(rgb, key_color)
    else:
        source = Image.fromarray(np.clip(np.rint(rgb), 0, 255).astype(np.uint8), "RGB").convert("RGBA")
        source, engine, final = production(source, *modules, key_color)
    f_alpha = np.asarray(final)[..., 3].astype(float)
    e_alpha = np.asarray(engine)[..., 3].astype(float)
    rim = gap & (cv2.dilate(subject.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
    core = gap & ~rim
    core_max = float(f_alpha[core].max()) if core.any() else 0.0
    core_violations = int((f_alpha[core] > 10).sum()) if core.any() else 0
    values = {name: float(f_alpha[mask].min()) for name, mask in details.items()}
    rim_alpha = float(np.median(f_alpha[rim])) if rim.any() else 0.0
    engine_core = float(e_alpha[core].max()) if core.any() else 0.0
    return core_max, core_violations, values, engine_core, rim_alpha, (source, engine, final)


def violations_of(core_max: float, values: dict):
    """Scenario deviations from ground truth, as stable (kind, detail) tags."""
    found = []
    if core_max > 10:
        found.append(("gap core film", f"{core_max:.0f}"))
    for name, minimum in DETAIL_MINIMUMS.items():
        if values[name] < minimum:
            found.append((f"{name} lost", f"{values[name]:.0f}"))
    return found


def render(image: Image.Image, blue: int, width: int, out_dir: Path, tag: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    box = (125, 40, 175, 320)
    crop = image.crop(box)
    plate = Image.new("RGBA", crop.size, (255, 255, 255, 255))
    plate.alpha_composite(crop)
    plate.convert("RGB").resize((crop.width * 3, crop.height * 3), Image.NEAREST).save(
        out_dir / f"synth_{tag}_blue{blue}_gap{width}.png"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--baseline", type=Path, default=None,
                        help="directory with pre-fix chroma_key.py/chroma_matting.py to compare against")
    parser.add_argument("--out-dir", type=Path, default=None, help="write 3x zone renders here")
    args = parser.parse_args()

    fixed_modules = None  # None means "the current modules" in measure()
    baseline_modules = load_baseline_modules(args.baseline) if args.baseline is not None else None

    header = (f"{'blue':>4} {'gap':>3} {'kind':>4} {'shd':>3} | {'gapCore':>7} {'coreViol':>8} {'engCore':>7} | "
              + " ".join(f"{name:>6}" for name in ELEMENTS) + f" | {'rimMed':>6}")
    print(f"{'baseline | ' + header if baseline_modules is not None else header}")
    violations = {"fix": [], "base": []}
    for blue in (253, 150, 117, 80, 40):
        for width in (1, 2, 4, 8, 16):
            for enclosed in (False, True):
                for shaded in (False, True):
                    key, rgb, subject, gap, details = build(blue, width, enclosed=enclosed)
                    if shaded:
                        rgb = shade(key, rgb, subject, gap)
                    scenario = (blue, width, enclosed, shaded)

                    def report(tag, modules):
                        try:
                            result = measure(rgb, subject, gap, details, modules=modules)
                        except Exception as error:  # noqa: BLE001 - reported as a result
                            violations[tag].append([*scenario, f"raises {type(error).__name__}", ""])
                            return None, f"raises {type(error).__name__}"
                        core_max, core_viol, values, engine_core, rim_alpha, images = result
                        violations[tag].extend([[*scenario, kind, detail]
                                                for kind, detail in violations_of(core_max, values)])
                        line = (f"{core_max:>7.0f} {core_viol:>8d} {engine_core:>7.0f} | "
                                + " ".join(f"{values[name]:>6.0f}" for name in ELEMENTS)
                                + f" | {rim_alpha:>6.0f}")
                        return images, line

                    if baseline_modules is not None:
                        base_images, base_line = report("base", baseline_modules)
                        fix_images, fix_line = report("fix", fixed_modules)
                        if fix_line.startswith("raises") or base_line.startswith("raises"):
                            print(f"{blue:>4} {width:>3} {'encl' if enclosed else 'open':>4} {int(shaded):>3} | "
                                  f"base: {base_line}; fix: {fix_line}")
                        else:
                            print(f"{blue:>4} {width:>3} {'encl' if enclosed else 'open':>4} {int(shaded):>3} | "
                                  f"base {base_line}   fix {fix_line}")
                        if args.out_dir is not None and shaded and blue in (253, 150) and width in (4, 8):
                            render(base_images[2], blue, width, args.out_dir, "base")
                            render(fix_images[2], blue, width, args.out_dir, "fix")
                    else:
                        images, line = report("fix", fixed_modules)
                        print(f"{blue:>4} {width:>3} {'encl' if enclosed else 'open':>4} {int(shaded):>3} | {line}")
                        if args.out_dir is not None and shaded and blue in (253, 150) and width in (4, 8):
                            render(images[2], blue, width, args.out_dir, "fix")

    def tags(rows):
        return sorted({(row[0], row[1], row[2], row[3], row[4][0]) for row in rows})

    fix_tags = tags(violations["fix"])
    print(f"\nfix violations: {len(violations['fix'])} ({len(fix_tags)} distinct)")
    for row in violations["fix"][:24]:
        print("  ", row)
    if baseline_modules is not None:
        base_tags = tags(violations["base"])
        regressions = [tag for tag in fix_tags if tag not in base_tags]
        print(f"baseline violations: {len(violations['base'])} ({len(base_tags)} distinct)")
        for row in violations["base"][:24]:
            print("  ", row)
        print(f"\nregressions after the fix: {len(regressions)}")
        for tag in regressions:
            print("  ", tag)
        return 1 if regressions else 0
    return 1 if fix_tags else 0


if __name__ == "__main__":
    raise SystemExit(main())
