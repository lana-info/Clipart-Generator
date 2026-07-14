"""Run an isolated visible-mark detector evaluation.

This script intentionally imports the separately installed remove-ai-watermarks
package. It is an evaluation harness, not an application dependency.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe visible AI-mark detection")
    parser.add_argument("--manifest", type=Path, required=True, help="JSON fixture manifest")
    parser.add_argument("--output", type=Path, required=True, help="JSON result path")
    parser.add_argument("--mask-dir", type=Path, help="Optional directory for binary masks")
    return parser.parse_args()


def _probe(path: Path, expected: list[str], mask_dir: Path | None) -> dict[str, Any]:
    import cv2
    import numpy as np
    from remove_ai_watermarks import image_io, watermark_registry

    started = time.perf_counter()
    image, _alpha = image_io.read_bgr_and_alpha(path)
    if image is None:
        raise ValueError(f"Could not decode fixture: {path}")
    detections = watermark_registry.detect_marks(image, include_explicit=True)
    rows: list[dict[str, Any]] = []
    for detection in detections:
        row: dict[str, Any] = {
            "key": detection.key,
            "detected": bool(detection.detected),
            "confidence": round(float(detection.confidence), 6),
            "location": detection.location,
            "region": list(detection.region),
        }
        if detection.detected and mask_dir is not None:
            localization = watermark_registry.get_mark(detection.key).localize(image)
            mask = localization.mask
            if mask is not None:
                mask_path = mask_dir / f"{path.stem}__{detection.key}.png"
                mask_path.parent.mkdir(parents=True, exist_ok=True)
                if not cv2.imwrite(str(mask_path), mask):
                    raise OSError(f"Could not write mask: {mask_path}")
                row["mask"] = {
                    "path": str(mask_path),
                    "pixels": int(np.count_nonzero(mask)),
                }
        rows.append(row)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    detected = {row["key"] for row in rows if row["detected"]}
    return {
        "file": str(path),
        "expected": expected,
        "detected": sorted(detected),
        "rows": rows,
        "elapsed_ms": round(elapsed_ms, 3),
        "true_positive": sorted(detected & set(expected)),
        "missed": sorted(set(expected) - detected),
        "false_positive": sorted(detected - set(expected)),
    }


def main() -> int:
    args = _parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    fixtures = manifest.get("fixtures")
    if not isinstance(fixtures, list) or not fixtures:
        raise ValueError("Manifest must contain a non-empty fixtures list")
    results = []
    for fixture in fixtures:
        path = Path(fixture["path"]).expanduser()
        expected = fixture.get("expected", [])
        if not path.is_file():
            raise FileNotFoundError(path)
        results.append(_probe(path, list(expected), args.mask_dir))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "schema": 1,
                "package": "remove-ai-watermarks",
                "fixtures": results,
            },
            ensure_ascii=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # concise CLI failure without changing app logging
        print(f"probe_visible_marks: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
