"""Offline, reproducible primary-key sweep for the selector regression.

Run from the worktree: python scripts/benchmark_chroma_selector.py --output PATH
No external images, credentials, network, or paid processing are used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from chroma_key import ChromaKeyAmbiguousError, remove_chroma_key_automatic
from chroma_quality import reference_quality, geometry_topology_quality, measure_alpha_profile
from chroma_benchmark import load_manifest, load_golden_fixture
from chroma_diagnostics import diagnose_chroma_key


def run(subject_profile="legacy", include_goldens=False, trace_stages=False):
    if trace_stages and not include_goldens:
        raise ValueError("Stage diagnostics require include_goldens")
    cases = []
    # Channel permutations keep the same independent ground-truth construction.
    for name, order in (("blue", [0, 1, 2]), ("green", [0, 2, 1]),
                        ("red", [2, 1, 0])):
        for secondary in range(30, 43):
            fg = np.array([120, 80, 180], dtype=np.float32)[order]
            key = np.array([2, secondary, 250], dtype=np.float32)[order]
            coverage = np.zeros((96, 96), dtype=np.float32)
            coverage[20:76, 20:76] = 1
            coverage[20, 20:76] = .5
            rgb = coverage[..., None] * fg + (1 - coverage[..., None]) * key
            source = Image.fromarray(np.rint(rgb).astype(np.uint8))
            truth = np.empty((96, 96, 4), dtype=np.uint8)
            truth[..., :3] = fg
            truth[..., 3] = np.rint(coverage * 255).astype(np.uint8)
            record = {
                "key": name, "observed_secondary": secondary,
                "source_rgb_sha256": hashlib.sha256(source.tobytes()).hexdigest(),
                "truth_rgba_sha256": hashlib.sha256(truth.tobytes()).hexdigest(),
            }
            try:
                result = remove_chroma_key_automatic(source, name, subject_profile=subject_profile)
            except ChromaKeyAmbiguousError as error:
                record.update(status="review", reason=type(error).__name__)
            else:
                record.update(status="processed", center=result.getpixel((48, 48)),
                              edge=result.getpixel((48, 20)),
                              quality=reference_quality(result, Image.fromarray(truth)))
                record["geometry"] = geometry_topology_quality(result, Image.fromarray(truth))
                # This fixture's top edge is straight: x=48 gives an explicit
                # normal, safely away from corners. Not a whole-image AA claim.
                record["top_edge_profile"] = measure_alpha_profile(
                    np.asarray(result.getchannel("A"))[16:25, 48] / 255.0
                )
            cases.append(record)
    report = {
        "schema_version": 1,
        "subject_profile": subject_profile,
        "scope": "synthetic selector sweep only; not production acceptance",
        "engine_sha256": hashlib.sha256((ROOT / "chroma_key.py").read_bytes()).hexdigest(),
        "fixture": "opaque square 20:76, half-coverage top row, 96x96, RGB channel permutations",
        "cases": cases,
    }
    if include_goldens:
        manifest = load_manifest(ROOT / "benchmarks" / "chroma" / "manifest.json")
        report["goldens"] = []
        for case in manifest["cases"]:
            fixture = load_golden_fixture(manifest, case)
            truth_image = fixture.expected_foreground.convert("RGBA")
            truth_image.putalpha(fixture.expected_mask)
            stage_report = None
            if trace_stages:
                stage_report, result = diagnose_chroma_key(
                    fixture.input_image, fixture.key_color,
                    subject_profile=subject_profile, truth=truth_image,
                )
            else:
                result = remove_chroma_key_automatic(
                    fixture.input_image, fixture.key_color, subject_profile=subject_profile
                )
            record = {
                "id": fixture.case_id,
                "status": "processed" if result is not None else "review",
            }
            if result is not None:
                record.update(quality=reference_quality(result, truth_image),
                              geometry=geometry_topology_quality(result, truth_image))
            if stage_report is not None:
                record["stage_diagnostics"] = stage_report
            report["goldens"].append(record)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--subject-profile", choices=("legacy", "opaque_clipart"), default="legacy")
    parser.add_argument("--include-goldens", action="store_true")
    parser.add_argument("--trace-stages", action="store_true",
                        help="Add opt-in completed-stage diagnostics for the goldens")
    args = parser.parse_args()
    # Refuse accidental overwriting of prior evidence or user files.
    if args.output.exists():
        parser.error("Output already exists; choose a new report path")
    if args.trace_stages and not args.include_goldens:
        parser.error("--trace-stages requires --include-goldens")
    report = run(args.subject_profile, args.include_goldens, args.trace_stages)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(f"Recorded {len(report['cases'])} cases in {args.output}")
