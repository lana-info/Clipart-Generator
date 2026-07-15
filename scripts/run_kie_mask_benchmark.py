"""Run or re-analyze one explicitly authorized KIE masked-edit benchmark.

The script is intentionally separate from the application. It reads the existing
desktop config only for a live run, never prints the API key, and hard-limits paid
generation calls. Existing results can be analyzed without another API request.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageStat


MAX_PAID_REQUESTS = 5
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPT = (
    "Remove only the small white four-point sparkle overlay inside the black mask. "
    "Reconstruct the blue shirt fabric naturally. Do not change anything outside "
    "the masked area. Preserve the person, face, clothing, colors, lighting, "
    "composition, and photographic style exactly. Return the complete image."
)


def _prepare_fixture(source_path: Path, work_dir: Path) -> tuple[Path, Path, dict[str, object]]:
    from remove_ai_watermarks import image_io, watermark_registry

    bgr, _alpha = image_io.read_bgr_and_alpha(source_path)
    if bgr is None:
        raise ValueError(f"Could not decode source: {source_path}")
    localization = watermark_registry.get_mark("gemini").localize(bgr)
    if not localization.detected or localization.mask is None:
        raise ValueError("Visible Gemini mark was not detected")

    source = Image.open(source_path).convert("RGB")
    source_width, source_height = source.size
    target_width = source_width
    target_height = max(source_height, round(target_width * 3 / 2))
    if target_height * 2 != target_width * 3:
        target_width = max(source_width, round(source_height * 2 / 3))
        target_height = round(target_width * 3 / 2)
    left = (target_width - source_width) // 2
    top = (target_height - source_height) // 2
    border = ImageStat.Stat(source).median
    fill = tuple(int(value) for value in border[:3])

    padded = Image.new("RGB", (target_width, target_height), fill)
    padded.paste(source, (left, top))
    kie_mask = Image.new("L", (target_width, target_height), 255)
    # KIE edits black and preserves white; the localizer uses the inverse convention.
    local_mask = Image.fromarray(localization.mask, mode="L")
    inverted = local_mask.point(lambda value: 0 if value else 255)
    kie_mask.paste(inverted, (left, top))

    prepared_source = work_dir / "source_2x3.png"
    prepared_mask = work_dir / "mask_2x3.png"
    padded.save(prepared_source, format="PNG")
    kie_mask.save(prepared_mask, format="PNG")
    return prepared_source, prepared_mask, {
        "source_size": [source_width, source_height],
        "prepared_size": [target_width, target_height],
        "content_offset": [left, top],
        "mask_region": list(localization.region),
        "mask_pixels": int(np.count_nonzero(localization.mask)),
    }


def _compare(source_path: Path, mask_path: Path, result_path: Path, fixture: dict[str, object]) -> dict[str, object]:
    source = Image.open(source_path).convert("RGB")
    mask = Image.open(mask_path).convert("L")
    with Image.open(result_path) as provider_image:
        provider_output_size = list(provider_image.size)
        output_metadata = {
            "format": provider_image.format,
            "mode": provider_image.mode,
            "has_alpha": "A" in provider_image.getbands(),
            "info_keys": sorted(str(key) for key in provider_image.info),
            "has_icc_profile": bool(provider_image.info.get("icc_profile")),
            "has_exif": bool(provider_image.getexif()),
            "dpi": list(provider_image.info["dpi"]) if provider_image.info.get("dpi") else None,
        }
        provider_size = provider_image.size
        result = provider_image.convert("RGB").resize(source.size, Image.Resampling.LANCZOS)

    normalization_baseline = source.resize(provider_size, Image.Resampling.LANCZOS).resize(
        source.size,
        Image.Resampling.LANCZOS,
    )
    source_array = np.asarray(source, dtype=np.int16)
    result_array = np.asarray(result, dtype=np.int16)
    baseline_array = np.asarray(normalization_baseline, dtype=np.int16)
    edit_area = np.asarray(mask) == 0
    delta = np.max(np.abs(result_array - source_array), axis=2)
    baseline_delta = np.max(np.abs(baseline_array - source_array), axis=2)
    changed = delta > 2
    baseline_changed = baseline_delta > 2
    outside = ~edit_area
    left, top = fixture["content_offset"]
    width, height = fixture["source_size"]
    content = np.zeros(edit_area.shape, dtype=bool)
    content[top : top + height, left : left + width] = True
    outside_content = outside & content
    outside_count = max(1, int(np.count_nonzero(outside_content)))
    return {
        "provider_output_size": provider_output_size,
        "normalized_size": list(source.size),
        "output_metadata": output_metadata,
        "changed_pixels_inside_mask": int(np.count_nonzero(changed & edit_area)),
        "changed_pixels_outside_mask": int(np.count_nonzero(changed & outside_content)),
        "outside_mask_pixels": outside_count,
        "outside_mask_changed_ratio": round(
            float(np.count_nonzero(changed & outside_content) / outside_count), 6
        ),
        "outside_mask_mean_abs_delta": round(float(np.mean(delta[outside_content])), 4),
        "normalization_baseline_changed_ratio": round(
            float(np.count_nonzero(baseline_changed & outside_content) / outside_count),
            6,
        ),
        "normalization_baseline_mean_abs_delta": round(float(np.mean(baseline_delta[outside_content])), 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Authorized KIE mask-edit benchmark")
    parser.add_argument("source", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--existing-result", type=Path)
    parser.add_argument("--allow-paid", action="store_true")
    parser.add_argument("--max-requests", type=int, default=1)
    args = parser.parse_args()
    if not 1 <= args.max_requests <= MAX_PAID_REQUESTS:
        raise ValueError(f"max-requests must be 1..{MAX_PAID_REQUESTS}")
    if args.existing_result is None and not args.allow_paid:
        parser.error("--allow-paid is required unless --existing-result is supplied")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    previous_report_path = args.output_dir / "benchmark.json"
    previous_report = (
        json.loads(previous_report_path.read_text(encoding="utf-8"))
        if previous_report_path.exists()
        else {}
    )
    api_key = ""
    key_seen_in_progress = [False]
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="clipart-kie-mask-") as temp_name:
        temp_dir = Path(temp_name)
        source, mask, fixture = _prepare_fixture(args.source, temp_dir)
        if args.existing_result is not None:
            provider_output = args.existing_result.resolve()
            if not provider_output.is_file():
                raise FileNotFoundError(f"Existing result not found: {provider_output}")
        else:
            sys.path.insert(0, str(PROJECT_ROOT))
            import main as app

            config_path = Path(app.CONFIG_FILE)
            config = json.loads(config_path.read_text(encoding="utf-8"))
            api_key = str(config.get("kie_api_key", "")).strip()
            if not api_key:
                raise ValueError("KIE API key is not configured")

            messages: list[str] = []
            worker = app.WorkerThread("process", str(args.output_dir), config)

            def record_progress(message: object) -> None:
                raw_message = str(message)
                if api_key in raw_message:
                    key_seen_in_progress[0] = True
                messages.append(raw_message.replace(api_key, "[REDACTED]"))

            worker.progress.connect(record_progress)
            source_url = worker._kie_upload_file(str(source))
            mask_url = worker._kie_upload_file(str(mask))
            prompt = (
                PROMPT
                + " The first input is the source image. The second input is a binary mask: "
                "edit only its black region and preserve its white region."
            )
            payload = {
                "input_urls": [source_url, mask_url],
                "prompt": prompt,
                "aspect_ratio": "2:3",
                "quality": "medium",
            }
            task_id = worker._kie_create_task("gpt-image/1.5-image-to-image", payload)
            result_url = worker._kie_wait_result(task_id)
            provider_output = args.output_dir / "kie_mask_edit.png"
            worker._download_file(result_url, str(provider_output))
        metrics = _compare(source, mask, provider_output, fixture)

    live_run = args.existing_result is None
    report = {
        "schema": 1,
        "analysis_mode": "live_paid" if live_run else "existing_result",
        "paid_generation_requests": 1 if live_run else previous_report.get("paid_generation_requests", 0),
        "authorized_request_limit": args.max_requests if live_run else previous_report.get("authorized_request_limit"),
        "provider_mode": "gpt-image/1.5-image-to-image with explicit mask reference",
        "listed_cost_usd_per_one_image_call": 0.02,
        "elapsed_seconds": (
            round(time.perf_counter() - started, 3) if live_run else previous_report.get("elapsed_seconds")
        ),
        "fixture": fixture,
        "metrics": metrics,
        "output": str(provider_output),
        "api_key_logged": key_seen_in_progress[0] if live_run else previous_report.get("api_key_logged", False),
        "provider_errors": previous_report.get("provider_errors", []),
    }
    report_path = args.output_dir / "benchmark.json"
    serialized_report = json.dumps(report, ensure_ascii=True, indent=2)
    if api_key and api_key in serialized_report:
        raise RuntimeError("API key reached the benchmark report")
    report_path.write_text(serialized_report + "\n", encoding="utf-8")
    print(serialized_report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
