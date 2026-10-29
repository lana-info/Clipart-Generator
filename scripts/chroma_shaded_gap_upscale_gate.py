"""End-to-end gate for the post-upscale delivery alpha on a synthetic shaded gap.

Runs the real worker pipeline (real local chroma engine, real matting) with a
fake local Real-ESRGAN: nearest-neighbour colour plus the real
``_restore_upscaled_alpha``, which is exactly the contract pinned by
tests/test_chroma_nn_working_alpha.py. Reports the gap core alpha and the detail
alphas of the final PNG.

Usage:
    python scripts/chroma_shaded_gap_upscale_gate.py [--baseline DIR]

``--baseline DIR`` holds the pre-fix chroma_key.py and chroma_matting.py.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def forbid_providers(worker) -> None:
    def reject(*_args, **_kwargs):
        raise AssertionError("Network/provider call forbidden in this offline check")

    worker._kie_upload_file = reject
    worker._download_file = reject
    worker._fal_source_url = reject
    worker._download_precleanup_result = reject


def run_case(synth, blue: int, width: int, scale: int = 2):
    import main

    key, rgb, subject, gap, details = synth.build(blue, width, enclosed=True)
    rgb = synth.shade(key, rgb, subject, gap)
    with tempfile.TemporaryDirectory() as tmp:
        raw = os.path.join(tmp, "raw")
        os.mkdir(raw)
        source_path = os.path.join(tmp, "source.png")
        Image.fromarray(np.clip(np.rint(rgb), 0, 255).astype(np.uint8), "RGB").save(source_path)
        worker = main.WorkerThread("mode2_process", tmp, {
            "upscale": False,
            "remove_bg": True, "remove_bg_provider": "local_chroma_key", "chroma_key_color": "blue",
            "upscale_after": True, "upscale_after_provider": "local_realesrgan",
            "local_realesrgan_after_scale": scale, "trim_enabled": False, "trim_mode": "alpha",
        })
        forbid_providers(worker)
        run_scale = scale

        def upscale(input_path, output_path, scale):
            assert scale == run_scale, scale
            with Image.open(input_path) as opened:
                actual_input = opened.convert("RGBA")
            size = (actual_input.width * scale, actual_input.height * scale)
            Image.new("RGB", size, (101, 121, 141)).save(output_path)
            worker._restore_upscaled_alpha(output_path, actual_input.getchannel("A"))

        worker._run_local_realesrgan = upscale
        result_path = worker._run_processing_pipeline(
            source_path, None, raw, 1, "case", chroma_key_color="blue", result_kind="clipart",
        )
        with Image.open(result_path) as opened:
            final = opened.convert("RGBA")
        assert final.size == (synth.CANVAS * scale, synth.CANVAS * scale), final.size
        alpha = np.asarray(final)[..., 3].astype(float)

        # Gap core: strictly interior columns and rows, at least 2 source px from paint.
        left_x1, right_x0 = 140, 140 + width
        y0, y1 = synth.TOP, synth.BOTTOM - 40
        core = np.zeros((final.height, final.width), bool)
        core[y0 * scale + 2: y1 * scale - 2, (left_x1 + 2) * scale: (right_x0 - 2) * scale] = True
        core_alpha = alpha[core] if core.any() else np.zeros(1)

        detail_values = {}
        for name, mask in details.items():
            big = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).resize(
                final.size, Image.Resampling.NEAREST)) > 0
            patch = alpha[big]
            detail_values[name] = (float(patch.min()), float(np.median(patch)))
        return float(core_alpha.max()), int((core_alpha > 10).sum()), detail_values, final


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--baseline", type=Path, default=None,
                        help="directory with pre-fix chroma_key.py/chroma_matting.py to compare against")
    parser.add_argument("--out-dir", type=Path, default=None, help="write the final PNGs here")
    args = parser.parse_args()
    if args.baseline is not None:
        sys.path.insert(0, str(args.baseline))

    import chroma_key
    from scripts import chroma_shaded_gap_synth as synth

    tag = "base" if args.baseline is not None else "fix"
    print(f"mode={tag} chroma_key={chroma_key.__file__}", flush=True)
    print(f"{'blue':>4} {'gap':>3} | {'gapCoreMax':>10} {'gapViol':>7} | "
          + " ".join(f"{n:>14}" for n in synth.ELEMENTS))
    bad = 0
    for blue in (253, 150):
        for width in (4, 8):
            core_max, core_viol, details, final = run_case(synth, blue, width)
            print(f"{blue:>4} {width:>3} | {core_max:>10.0f} {core_viol:>7d} | "
                  + " ".join(f"{v[0]:>6.0f}/{v[1]:>6.0f}" for v in details.values()))
            if core_max > 10:
                bad += 1
            if details["stem1"][0] <= 0 and details["stem2"][0] <= 0:
                bad += 1
            if args.out_dir is not None:
                args.out_dir.mkdir(parents=True, exist_ok=True)
                final.save(args.out_dir / f"upscale_{tag}_blue{blue}_gap{width}.png")
    print(f"\nviolations: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
