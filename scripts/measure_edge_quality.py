"""Measure the cut-out edge quality of the production chain on owner frames.

Control set for AC-C2/AC-C3 (owner 2026-10-29: «края ровные, без зубцов и размытия,
цвет сохраняется»; тонкие детали не рвутся и не темнеют). The frames come from the
owner's own archives (rough_01…rough_05): flowers, leaves, stems, thin details.

For every frame the script runs the real pipeline (engine -> matting -> clean/tint)
and measures on the picture itself:

  * soft edge width in px: 2 * (partial-alpha pixels) / (contour length of a>=128);
    a smooth disc of the same scale with a 1.2 px blur measures about 23 px through
    this formula, so small numbers mean a tight edge;
  * jaggedness: contour points per 100 px after Douglas-Peucker with eps=1 px — a
    smooth curve needs about 1.4, a staircase needs many more;
  * thin details: source structures whose subject width is <= 2 px (stems, hairs,
    antennae) and how many of them stay visible (alpha > 128) after the cut-out;
  * key tint at the edge: partial pixels whose colour still lies on the key's chroma
    axis, as a share of the band at three alpha levels.

Usage: python scripts/measure_edge_quality.py FRAME [FRAME ...] [--out DIR]

Cut-outs of the frames are written to ``--out`` (default:
``artifacts/edge-control-20261029/out``).
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import chroma_key as ck  # noqa: E402
from alpha_cleanup import DEBRIS_MIN_GAP, clean_alpha  # noqa: E402
from chroma_matting import matte_edges  # noqa: E402
from edge_tint import suppress_key_tint  # noqa: E402


def cutout(source: Image.Image) -> tuple[Image.Image, Image.Image]:
    engine = ck.finish_rim_cleanup(
        ck.remove_chroma_key_automatic(source, "blue", subject_profile="opaque_clipart"),
        "opaque_clipart",
    )
    matted = matte_edges(source, engine, "blue")
    if matted is not engine:
        matted = suppress_key_tint(clean_alpha(matted, island_min_gap=DEBRIS_MIN_GAP), "blue")
    return engine, matted


def measure(source: Image.Image, result: Image.Image) -> dict:
    rgb = np.asarray(source.convert("RGB"), np.float32)
    alpha = np.asarray(result.convert("RGBA"))[..., 3]
    key = np.array(ck._measured_border_key(source), np.float32)

    solid = (alpha >= 128).astype(np.uint8)
    contours, _ = cv2.findContours(solid, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    perimeter = sum(cv2.arcLength(contour, True) for contour in contours)
    partial = int(((alpha > 0) & (alpha < 255)).sum())
    edge_width = (2.0 * partial / perimeter) if perimeter else 0.0

    points = sum(len(cv2.approxPolyDP(contour, 1.0, True)) for contour in contours if len(contour) >= 8)
    jaggedness = (100.0 * points / perimeter) if perimeter else 0.0

    distance_to_key = np.linalg.norm(rgb - key, axis=2)
    subject = distance_to_key > 96.0
    thickness = cv2.distanceTransform(subject.astype(np.uint8), cv2.DIST_L2, 5)
    thin = subject & (thickness <= 1.0)
    thin_total = int(thin.sum())
    thin_kept = int(((alpha > 128) & thin).sum())

    # The rim tint is measured twice: on the source (how much key the blend carries) and on
    # the result (what actually ships). The second number is the one that matters for the
    # owner's "лиловая кайма" complaint; the first only describes the input (review R5).
    angle = ck.key_chroma_angle(rgb, key)
    result_rgb = np.asarray(result.convert("RGB"), np.float32)
    result_angle = ck.key_chroma_angle(result_rgb, key)
    tint, tint_out = {}, {}
    for level in (0, 64, 128):
        band = (alpha > level) & (alpha < 255)
        total = int(band.sum())
        tint[level] = (100.0 * int((band & (angle <= 20.0) & (rgb[..., 2] <= 0.95 * key[2])).sum()) / total) if total else 0.0
        tint_out[level] = (100.0 * int((band & (result_angle <= 20.0)
                                        & (result_rgb[..., 2] <= 0.95 * key[2])).sum()) / total) if total else 0.0
    return {
        "size": source.size,
        "edge_width_px": edge_width,
        "jagged_points_per_100px": jaggedness,
        "thin_total": thin_total,
        "thin_kept_pct": (100.0 * thin_kept / thin_total) if thin_total else float("nan"),
        "tint_pct": tint,
        "tint_out_pct": tint_out,
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("frames", nargs="+", type=Path)
    parser.add_argument("--out", type=Path,
                        default=REPO_ROOT / "artifacts" / "edge-control-20261029" / "out")
    args = parser.parse_args()
    import chroma_key
    print("chroma_key:", chroma_key.__file__, flush=True)
    print(f"{'frame':<28} {'edgeW':>6} {'jaggy':>6} {'thinN':>6} {'thin%':>6} "
          f"{'in>64':>7} {'out>64':>8} {'out>128':>9}")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for path in args.frames:
        with Image.open(path) as opened:
            source = opened.convert("RGBA")
        _, result = cutout(source)
        values = measure(source, result)
        result.save(out / f"{path.stem}_cutout.png")
        tint, tint_out = values["tint_pct"], values["tint_out_pct"]
        print(f"{path.name:<28} {values['edge_width_px']:>6.2f} {values['jagged_points_per_100px']:>6.2f} "
              f"{values['thin_total']:>6d} {values['thin_kept_pct']:>6.1f} "
              f"{tint[64]:>6.1f}% {tint_out[64]:>7.1f}% {tint_out[128]:>8.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
