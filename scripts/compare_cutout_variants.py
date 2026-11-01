"""Compare two cut-out variants on the same frames: metrics and side-by-side sheets.

The reference is the current pipeline (`develop/3.2`); a candidate is any worktree or
copy of the repository with a proposed change. Every variant runs in its own process,
so two versions of ``chroma_key``/``chroma_matting`` never clash.

Metrics per frame (see ``scripts/measure_edge_quality.py`` for the definitions):
  * ``edge_w``      soft edge width, px — smaller is a tighter edge, 0 is a hard cut;
  * ``jaggy``       contour points per 100 px after 1 px simplification — lower is smoother;
  * ``thin_kept``   share of source structures <= 2 px that stay visible, %;
  * ``green``, ``blue`` share of visible edge pixels shifted towards green/blue
                    relative to the nearest opaque colour, %;
  * ``detail``      mean alpha over the source's opaque structures (thin details of the art);
  * ``kept``        visible pixels vs the reference run, %.

Usage:
    python scripts/compare_cutout_variants.py --reference REF_DIR --candidate CAND_DIR \
        [--out DIR] FRAME [FRAME ...]

``--emit DIR OUT`` is the internal per-process mode that runs the pipeline of the
repository the script is started from.

Preparing a candidate safely: copy the reference worktree with hard links
(``cp -al``) and replace only the files you change with
``cp --remove-destination`` — editing a hard-linked file in place would silently
change the reference too. A real copy (``cp -a``) is always safe, just slower.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]


def _pipeline(source):
    import chroma_key as ck
    from alpha_cleanup import DEBRIS_MIN_GAP, clean_alpha
    from chroma_matting import matte_edges
    from edge_tint import suppress_key_tint

    engine = ck.finish_rim_cleanup(
        ck.remove_chroma_key_automatic(source, "blue", subject_profile="opaque_clipart"),
        "opaque_clipart",
    )
    matted = matte_edges(source, engine, "blue")
    if matted is not engine:
        matted = suppress_key_tint(clean_alpha(matted, island_min_gap=DEBRIS_MIN_GAP, antialias=True), "blue")
    return engine, matted


def _metrics(source, result) -> dict:
    import cv2
    import chroma_key as ck

    rgb = np.asarray(source.convert("RGB"), np.float32)
    rgba = np.asarray(result.convert("RGBA")).astype(np.int16)
    alpha = rgba[..., 3]
    key = np.array(ck._measured_border_key(source), np.float32)

    solid = (alpha >= 128).astype(np.uint8)
    contours, _ = cv2.findContours(solid, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    perimeter = sum(cv2.arcLength(contour, True) for contour in contours)
    partial = int(((alpha > 0) & (alpha < 255)).sum())
    points = sum(len(cv2.approxPolyDP(contour, 1.0, True)) for contour in contours if len(contour) >= 8)

    opaque = (alpha >= 255).astype(np.uint8)
    _, labels = cv2.distanceTransformWithLabels((opaque == 0).astype(np.uint8), cv2.DIST_L2, 5,
                                                labelType=cv2.DIST_LABEL_PIXEL)
    palette = np.zeros((int(labels.max()) + 1, 3), np.int16)
    palette[labels[opaque > 0]] = rgba[..., :3][opaque > 0]
    reference = palette[labels]
    band = (alpha > 0) & (alpha < 255)
    delta = (rgba[..., :3][band].astype(np.float32) - reference[band].astype(np.float32)) if band.any() else np.zeros((1, 3))
    green = delta[:, 1] - (delta[:, 0] + delta[:, 2]) / 2
    blue = delta[:, 2] - (delta[:, 0] + delta[:, 1]) / 2

    distance_to_key = np.linalg.norm(rgb - key, axis=2)
    subject = distance_to_key > 96.0
    thickness = cv2.distanceTransform(subject.astype(np.uint8), cv2.DIST_L2, 5)
    thin = subject & (thickness <= 1.0)
    detail = subject & (alpha > 0)

    return {
        "edge_w": round(2.0 * partial / perimeter, 3) if perimeter else 0.0,
        "jaggy": round(100.0 * points / perimeter, 3) if perimeter else 0.0,
        "thin_kept": round(100.0 * int(((alpha > 128) & thin).sum()) / max(1, int(thin.sum())), 2),
        "green": round(100.0 * float((green > 12).mean()), 2),
        "blue": round(100.0 * float((blue > 12).mean()), 2),
        "detail": round(float(alpha[detail].mean()), 2) if detail.any() else 0.0,
        "visible": int((alpha > 0).sum()),
    }


def emit(repo: Path, out_dir: Path, frames: list[Path]) -> int:
    """Run this repository's pipeline on the frames and write cut-outs plus metrics."""
    sys.path.insert(0, str(repo))
    from PIL import Image

    out_dir.mkdir(parents=True, exist_ok=True)
    for path in frames:
        with Image.open(path) as opened:
            source = opened.convert("RGBA")
        _, result = _pipeline(source)
        result.save(out_dir / f"{path.stem}.png")
        (out_dir / f"{path.stem}.json").write_text(
            json.dumps(_metrics(source, result), ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{path.name}: {json.dumps(_metrics(source, result), ensure_ascii=False)}", flush=True)
    return 0


def _run_variant(repo: Path, out_dir: Path, frames: list[Path]) -> None:
    command = [sys.executable, str(Path(__file__).resolve()), "--emit", str(repo), str(out_dir),
               *[str(frame) for frame in frames]]
    result = subprocess.run(command, cwd=str(repo), capture_output=True, text=True)
    print(result.stdout.strip())
    if result.returncode:
        print(result.stderr[-2000:], file=sys.stderr)
        raise SystemExit(f"variant {repo} failed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--emit", nargs=2, metavar=("REPO", "OUT_DIR"), help=argparse.SUPPRESS)
    parser.add_argument("frames", nargs="+", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--zoom", type=int, default=4)
    args = parser.parse_args()

    frames = [frame.resolve() for frame in args.frames]
    if args.emit is not None:
        return emit(Path(args.emit[0]).resolve(), Path(args.emit[1]).resolve(), frames)
    if args.reference is None or args.candidate is None:
        parser.error("--reference and --candidate are required (or use --emit)")

    out = args.out or (REPO_ROOT / "artifacts" / "cutout-ab" / "latest")
    out.mkdir(parents=True, exist_ok=True)
    _run_variant(args.reference.resolve(), out / "reference", frames)
    _run_variant(args.candidate.resolve(), out / "candidate", frames)

    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
    table = ["| кадр | показатель | эталон | предложение | лучше/хуже |", "|---|---|---|---|---|"]
    journal = ["# Сравнение вариантов вырезки", "", f"Эталон: `{args.reference}`", f"Предложение: `{args.candidate}`", ""]
    for frame in frames:
        ref = json.loads((out / "reference" / f"{frame.stem}.json").read_text(encoding="utf-8"))
        cand = json.loads((out / "candidate" / f"{frame.stem}.json").read_text(encoding="utf-8"))
        journal.append(f"## {frame.stem}")
        journal.append("")
        journal.append("| показатель | эталон | предложение | лучше/хуже |")
        journal.append("|---|---|---|---|")
        for name, lower_is_better in (("edge_w", None), ("jaggy", True), ("thin_kept", False),
                                      ("green", True), ("blue", True), ("detail", False), ("visible", None)):
            if name not in ref or name not in cand:
                continue
            verdict = ""
            if lower_is_better is not None and abs(ref[name] - cand[name]) > 1e-9:
                improved = (cand[name] < ref[name]) if lower_is_better else (cand[name] > ref[name])
                verdict = "лучше" if improved else "**хуже**"
            journal.append(f"| {name} | {ref[name]} | {cand[name]} | {verdict} |")
        journal.append("")

        with Image.open(frame) as opened:
            source = opened.convert("RGBA")
        ref_image = Image.open(out / "reference" / f"{frame.stem}.png").convert("RGBA")
        cand_image = Image.open(out / "candidate" / f"{frame.stem}.png").convert("RGBA")
        difference = np.abs(np.asarray(ref_image).astype(np.int16) - np.asarray(cand_image).astype(np.int16)).sum(axis=2)
        difference = __import__("cv2").GaussianBlur(difference.astype(np.float32), (0, 0), 12)
        y, x = np.unravel_index(int(np.argmax(difference)), difference.shape)
        box = (max(int(x) - 70, 0), max(int(y) - 70, 0), int(x) + 70, int(y) + 70)

        def plate(image):
            crop = image.crop(box).convert("RGBA")
            canvas = Image.new("RGBA", crop.size, (255, 255, 255, 255))
            canvas.alpha_composite(crop)
            return canvas.convert("RGB").resize((crop.width * args.zoom, crop.height * args.zoom), Image.NEAREST)

        tiles = [("исходник", plate(source)), ("эталон (сейчас)", plate(ref_image)), ("предложение", plate(cand_image))]
        width = sum(tile.width for _, tile in tiles) + 20 * (len(tiles) - 1)
        height = tiles[0][1].height + 44
        sheet = Image.new("RGB", (width, height), (216, 216, 216))
        draw = ImageDraw.Draw(sheet)
        position = 0
        for title, tile in tiles:
            sheet.paste(tile, (position, 36))
            draw.text((position + 4, 4), title, fill=(20, 20, 20), font=font)
            position += tile.width + 20
        sheet.save(out / f"{frame.stem}_сравнение.png")
        journal.append(f"![{frame.stem}]({frame.stem}_сравнение.png)")
        journal.append("")

    (out / "COMPARISON.md").write_text("\n".join(journal), encoding="utf-8")
    print("\n".join(table[:2]))
    print(f"готово: {out / 'COMPARISON.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
