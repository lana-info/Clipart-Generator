"""Benchmark local fills for already-confirmed visible-mark masks.

The external remove-ai-watermarks package is loaded only in this benchmark. The
script never overwrites an input and reports changed pixels outside each mask.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark visible-mark inpainting")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backends", nargs="+", default=["cv2"], choices=("cv2", "migan", "lama"))
    args = parser.parse_args()

    import numpy as np
    from remove_ai_watermarks import image_io, watermark_registry

    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    rows: list[dict[str, Any]] = []
    for fixture in manifest.get("fixtures", []):
        path = Path(fixture["path"])
        mark_key = fixture.get("mark")
        if not mark_key:
            continue
        image, alpha = image_io.read_bgr_and_alpha(path)
        if image is None:
            raise ValueError(f"Could not decode fixture: {path}")
        mark = watermark_registry.get_mark(mark_key)
        localization = mark.localize(image)
        if localization.mask is None:
            raise ValueError(f"No automatic mask for {mark_key}: {path}")
        auto_mask = localization.mask
        x, y, width, height = localization.region
        rect_mask = np.zeros(auto_mask.shape, dtype=np.uint8)
        rect_mask[max(0, y):min(image.shape[0], y + height), max(0, x):min(image.shape[1], x + width)] = 255
        for mask_name, mask in (("automatic", auto_mask), ("rectangle", rect_mask)):
            for backend in args.backends:
                started = time.perf_counter()
                try:
                    output = watermark_registry.fill(image, mask, backend=backend)
                    status = "ok"
                    outside = mask == 0
                    changed = np.any(output != image, axis=2)
                    changed_outside = int(np.count_nonzero(changed & outside))
                    changed_inside = int(np.count_nonzero(changed & ~outside))
                    error = None
                except Exception as exc:  # optional backend or model is unavailable
                    status = "unavailable"
                    changed_outside = None
                    changed_inside = None
                    error = type(exc).__name__
                rows.append({
                    "file": str(path),
                    "mark": mark_key,
                    "mask": mask_name,
                    "backend": backend,
                    "status": status,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
                    "changed_pixels_outside_mask": changed_outside,
                    "changed_pixels_inside_mask": changed_inside,
                    "error_type": error,
                    "source_alpha_preserved": alpha is not None,
                })
                if status == "ok":
                    del output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"schema": 1, "results": rows}, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
