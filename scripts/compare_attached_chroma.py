"""Offline comparison with an explicitly supplied, reviewed research ZIP.

Executes the ZIP's Python module: only use trusted/reviewed research inputs.
Never imports this candidate into the application or submits provider requests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import types
import zipfile

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from chroma_benchmark import load_manifest, load_golden_fixture
from chroma_key import remove_chroma_key_automatic
from chroma_quality import reference_quality


def compare(archive: Path, destination: Path):
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive) as bundle:
        source = bundle.read("clipart_pipeline.py")
        tests = bundle.read("test_clipart_pipeline.py")
    candidate = types.ModuleType("clipart_pipeline")
    sys.modules[candidate.__name__] = candidate
    exec(compile(source, "attached/clipart_pipeline.py", "exec"), candidate.__dict__)
    namespace = {}
    exec(compile(tests, "attached/test_clipart_pipeline.py", "exec"), namespace)
    checks = {}
    for name, check in namespace.items():
        if name.startswith("test_"):
            try:
                check()
                checks[name] = "passed"
            except Exception as error:
                checks[name] = type(error).__name__
    report = {"candidate_sha256": hashlib.sha256(source).hexdigest(),
              "current_sha256": hashlib.sha256((ROOT / "chroma_key.py").read_bytes()).hexdigest(),
              "scope": "offline synthetic references; not real-image acceptance",
              "supplied_tests": checks, "cases": []}
    manifest = load_manifest(ROOT / "benchmarks/chroma/manifest.json")
    board = Image.new("RGB", (768, 280 * len(manifest["cases"])), "#dddddd")
    draw = ImageDraw.Draw(board)
    for index, case in enumerate(manifest["cases"]):
        fixture = load_golden_fixture(manifest, case)
        truth = fixture.expected_foreground.convert("RGBA")
        truth.putalpha(fixture.expected_mask)
        current = remove_chroma_key_automatic(fixture.input_image, fixture.key_color,
                                              subject_profile="opaque_clipart")
        result, qc = candidate.remove_solid_background(
            fixture.input_image, candidate.KeyerConfig(trim=False))
        record = {"id": fixture.case_id, "candidate_qc_ok": qc.ok,
                  "current": reference_quality(current, truth),
                  "candidate": reference_quality(result, truth)}
        report["cases"].append(record)
        for col, (label, image) in enumerate((("truth", truth), ("current", current), ("candidate", result))):
            black = Image.new("RGBA", image.size, "black")
            black.alpha_composite(image.convert("RGBA"))
            board.paste(black.convert("RGB").resize((256, 256)), (col * 256, index * 280 + 24))
            draw.text((col * 256 + 4, index * 280 + 4), fixture.case_id + " " + label, fill="black")
    # An object touching the frame puts connectedComponents label 0 on its border.
    rgb = np.full((64, 64, 3), (0, 0, 255), dtype=np.uint8)
    rgb[:40, 20:44] = (220, 80, 100)
    cropped, qc = candidate.remove_solid_background(Image.fromarray(rgb), candidate.KeyerConfig(trim=False))
    report["frame_contact"] = {"opaque_pixels": int(np.count_nonzero(np.asarray(cropped)[..., 3] == 255)), "qc_ok": qc.ok}
    # A pre-existing transparent hole must not become opaque after RGB conversion.
    rgba = np.full((64, 64, 4), (0, 0, 255, 255), dtype=np.uint8)
    rgba[12:52, 12:52] = (220, 80, 100, 255)
    rgba[28:36, 28:36, 3] = 0
    cut, _ = candidate.remove_solid_background(Image.fromarray(rgba), candidate.KeyerConfig(trim=False))
    report["existing_alpha_hole"] = {"input": 0, "candidate_center": cut.getpixel((32, 32))[3]}
    with (destination / "report.json").open("x") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    board.save(destination / "comparison.png")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    report = compare(args.archive, args.destination)
    print("Supplied tests:", report["supplied_tests"])
    for case in report["cases"]:
        print(case["id"], "black partial p95:",
              case["current"]["composites"]["black"]["partial"]["p95"],
              case["candidate"]["composites"]["black"]["partial"]["p95"],
              "candidate QC", case["candidate_qc_ok"])
    print("Frame:", report["frame_contact"], "Alpha hole:", report["existing_alpha_hole"])
