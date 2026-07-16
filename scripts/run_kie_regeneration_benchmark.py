"""Run the bounded Task 39 KIE whole-image regeneration benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TASK33_PRIOR_PROVIDER_ATTEMPTS = 3
TASK39_COMPLETED_GENERATION_ATTEMPTS = 2
TOTAL_AUTHORIZED_PROVIDER_ATTEMPTS = 5
BOARD_SIZE = 1024
MODEL_CONFIG = {
    "gpt-image-2-image-to-image": {
        "listed_credits": 6,
        "listed_cost_usd": 0.03,
        "input": {"aspect_ratio": "1:1", "resolution": "1K"},
    },
    "flux-2/pro-image-to-image": {
        "listed_credits": 5,
        "listed_cost_usd": 0.025,
        "input": {"aspect_ratio": "1:1", "resolution": "1K", "nsfw_checker": True},
    },
}
PROMPT = (
    "Re-render the entire reference board as a clean new image while preserving its visible "
    "content and six-tile layout. Preserve the photographic scene, the person's exact face "
    "and expression, the illustration, the isolated clipart, all color swatches, fine lines, "
    "and every text character and number exactly. Preserve transparency where supported. "
    "Do not add logos, signatures, borders, captions, or visible watermarks. Use only the "
    "reference image as content and return the complete square board."
)


def _font(size: int, *, bold: bool = False):
    filename = "arialbd.ttf" if bold else "arial.ttf"
    candidates = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / filename]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def _cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    image = image.convert("RGBA")
    target_width, target_height = size
    scale = max(target_width / image.width, target_height / image.height)
    resized = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        Image.Resampling.LANCZOS,
    )
    left = (resized.width - target_width) // 2
    top = (resized.height - target_height) // 2
    return resized.crop((left, top, left + target_width, top + target_height))


def _label_tile(tile: Image.Image, label: str) -> Image.Image:
    result = tile.convert("RGBA")
    draw = ImageDraw.Draw(result)
    draw.rectangle((0, 0, result.width, 38), fill=(20, 24, 30, 255))
    draw.text((12, 8), label, fill=(255, 255, 255, 255), font=_font(20, bold=True))
    return result


def _illustration_tile(size: tuple[int, int]) -> Image.Image:
    width, height = size
    image = Image.new("RGBA", size, (238, 246, 250, 255))
    draw = ImageDraw.Draw(image)
    draw.ellipse((width * 0.66, 62, width * 0.91, 62 + width * 0.25), fill=(255, 197, 72, 255))
    draw.polygon(
        [(0, height), (0, height * 0.58), (width * 0.36, height * 0.29), (width * 0.66, height * 0.64), (width, height * 0.38), (width, height)],
        fill=(62, 111, 125, 255),
    )
    draw.polygon(
        [(0, height), (0, height * 0.76), (width * 0.31, height * 0.53), (width * 0.52, height * 0.76), (width * 0.76, height * 0.55), (width, height * 0.70), (width, height)],
        fill=(96, 151, 119, 255),
    )
    draw.line((24, height - 42, width - 24, height - 42), fill=(231, 112, 80, 255), width=5)
    return _label_tile(image, "ILLUSTRATION")


def _clipart_tile(size: tuple[int, int]) -> Image.Image:
    width, height = size
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    center = (width // 2, int(height * 0.56))
    for angle in range(0, 360, 45):
        radians = np.deg2rad(angle)
        x = center[0] + int(np.cos(radians) * 72)
        y = center[1] + int(np.sin(radians) * 72)
        draw.ellipse((x - 45, y - 32, x + 45, y + 32), fill=(248, 164, 177, 245), outline=(143, 71, 96, 255), width=3)
    draw.ellipse((center[0] - 42, center[1] - 42, center[0] + 42, center[1] + 42), fill=(255, 211, 85, 255), outline=(128, 93, 31, 255), width=4)
    draw.line((center[0], center[1] + 42, center[0], height - 36), fill=(50, 126, 85, 255), width=12)
    draw.ellipse((center[0] - 74, height - 106, center[0] - 4, height - 58), fill=(91, 169, 111, 245), outline=(39, 99, 63, 255), width=3)
    return _label_tile(image, "CLIPART + ALPHA")


def _text_tile(size: tuple[int, int]) -> Image.Image:
    image = Image.new("RGBA", size, (251, 249, 243, 255))
    draw = ImageDraw.Draw(image)
    lines = [
        ("TEXT PRESERVATION", 24, True),
        ("ALPHA-2026", 28, True),
        ("1234567890", 27, False),
        ("Price: $12.50", 24, False),
        ("ABC xyz / 7+5=12", 21, False),
        ("Small text: edge & color", 16, False),
    ]
    y = 62
    for text, size_px, bold in lines:
        draw.text((18, y), text, fill=(22, 35, 47, 255), font=_font(size_px, bold=bold))
        y += size_px + 22
    draw.rectangle((18, y + 12, image.width - 18, y + 18), fill=(225, 65, 74, 255))
    draw.rectangle((18, y + 28, image.width - 18, y + 34), fill=(38, 132, 166, 255))
    return _label_tile(image, "TEXT-HEAVY")


def _control_tile(size: tuple[int, int]) -> Image.Image:
    width, height = size
    image = Image.new("RGBA", size, (245, 247, 250, 255))
    draw = ImageDraw.Draw(image)
    colors = [
        (225, 56, 68), (242, 147, 45), (249, 210, 71), (73, 164, 94),
        (45, 139, 186), (75, 90, 190), (137, 75, 173), (226, 104, 162),
        (25, 29, 36), (98, 108, 119), (207, 214, 222), (255, 255, 255),
    ]
    swatch_width = (width - 40) // 4
    for index, color in enumerate(colors):
        row, col = divmod(index, 4)
        x = 20 + col * swatch_width
        y = 64 + row * 62
        draw.rectangle((x, y, x + swatch_width - 8, y + 46), fill=(*color, 255), outline=(20, 24, 30, 255), width=2)
    for offset in range(0, width - 40, 8):
        draw.line((20 + offset, height - 130, 20 + offset, height - 40), fill=(34, 52, 70, 255), width=1)
    for offset in range(0, 91, 8):
        draw.line((20, height - 130 + offset, width - 20, height - 130 + offset), fill=(34, 52, 70, 255), width=1)
    return _label_tile(image, "COLOR + FINE GRID")


def build_fixture_board(photo_path: Path, face_path: Path) -> tuple[Image.Image, dict[str, object]]:
    with Image.open(photo_path) as photo_source:
        photo = photo_source.convert("RGBA")
    with Image.open(face_path) as face_source:
        face = face_source.convert("RGBA")

    margin, gap = 24, 12
    tile_width = (BOARD_SIZE - margin * 2 - gap * 2) // 3
    tile_height = (BOARD_SIZE - margin * 2 - gap) // 2
    x_positions = [margin + index * (tile_width + gap) for index in range(3)]
    y_positions = [margin, margin + tile_height + gap]
    board = Image.new("RGBA", (BOARD_SIZE, BOARD_SIZE), (0, 0, 0, 0))

    tile_specs = [
        ("photo", _label_tile(_cover(photo, (tile_width, tile_height)), "PHOTO"), (x_positions[0], y_positions[0])),
        ("face", _label_tile(_cover(face, (tile_width, tile_height)), "FACE"), (x_positions[1], y_positions[0])),
        ("illustration", _illustration_tile((tile_width, tile_height)), (x_positions[2], y_positions[0])),
        ("clipart", _clipart_tile((tile_width, tile_height)), (x_positions[0], y_positions[1])),
        ("text_heavy", _text_tile((tile_width, tile_height)), (x_positions[1], y_positions[1])),
        ("controls", _control_tile((tile_width, tile_height)), (x_positions[2], y_positions[1])),
    ]
    tiles = []
    for name, tile, (x, y) in tile_specs:
        board.alpha_composite(tile, (x, y))
        tiles.append({"name": name, "bbox": [x, y, x + tile_width, y + tile_height]})

    fixture = {
        "size": [BOARD_SIZE, BOARD_SIZE],
        "classes": ["photo", "face", "illustration", "clipart", "text_heavy"],
        "tiles": tiles,
        "input_has_alpha": True,
        "input_transparent_pixels": int(np.count_nonzero(np.asarray(board.getchannel("A")) < 255)),
        "source_hashes": {
            "photo": hashlib.sha256(photo_path.read_bytes()).hexdigest(),
            "face": hashlib.sha256(face_path.read_bytes()).hexdigest(),
        },
    }
    return board, fixture


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temp_path = Path(handle.name)
        json.dump(payload, handle, ensure_ascii=True, indent=2)
        handle.write("\n")
    os.replace(temp_path, path)


def ensure_live_generation_budget() -> int:
    used_attempts = TASK33_PRIOR_PROVIDER_ATTEMPTS + TASK39_COMPLETED_GENERATION_ATTEMPTS
    if used_attempts >= TOTAL_AUTHORIZED_PROVIDER_ATTEMPTS:
        raise RuntimeError("Task 39 live generation budget is exhausted")
    return TASK39_COMPLETED_GENERATION_ATTEMPTS + 1


def _global_ssim(left: np.ndarray, right: np.ndarray) -> float:
    left = left.astype(np.float64)
    right = right.astype(np.float64)
    mean_left, mean_right = float(left.mean()), float(right.mean())
    var_left, var_right = float(left.var()), float(right.var())
    covariance = float(np.mean((left - mean_left) * (right - mean_right)))
    c1, c2 = 6.5025, 58.5225
    denominator = (mean_left**2 + mean_right**2 + c1) * (var_left + var_right + c2)
    if denominator == 0:
        return 1.0
    return float(((2 * mean_left * mean_right + c1) * (2 * covariance + c2)) / denominator)


def _checker_preview(image: Image.Image) -> Image.Image:
    image = image.convert("RGBA")
    checker = Image.new("RGB", image.size, (235, 235, 235))
    draw = ImageDraw.Draw(checker)
    step = 24
    for y in range(0, image.height, step):
        for x in range(0, image.width, step):
            if (x // step + y // step) % 2:
                draw.rectangle((x, y, x + step - 1, y + step - 1), fill=(205, 205, 205))
    checker.paste(image.convert("RGB"), mask=image.getchannel("A"))
    return checker


def analyze_result(
    source_path: Path,
    result_path: Path,
    fixture: dict[str, object],
    comparison_path: Path,
) -> dict[str, object]:
    sys.path.insert(0, str(PROJECT_ROOT))
    from metadata_inspector import inspect_image_metadata
    from watermark_status import (
        FileHintStatus,
        PixelMarkerType,
        PixelProcessingStatus,
        create_pixel_watermark_status,
    )

    with Image.open(source_path) as source_image:
        source = source_image.convert("RGBA")
    with Image.open(result_path) as provider_image:
        provider_image.load()
        provider_size = list(provider_image.size)
        provider_mode = provider_image.mode
        provider_format = provider_image.format
        provider_has_alpha = "A" in provider_image.getbands() or "transparency" in provider_image.info
        provider_info_keys = sorted(str(key) for key in provider_image.info)
        normalized = provider_image.convert("RGBA").resize(source.size, Image.Resampling.LANCZOS)

    source_array = np.asarray(source, dtype=np.int16)
    output_array = np.asarray(normalized, dtype=np.int16)
    rgb_absolute_delta = np.abs(output_array[:, :, :3] - source_array[:, :, :3])
    rgb_delta = np.max(rgb_absolute_delta, axis=2)
    alpha_delta = np.abs(output_array[:, :, 3] - source_array[:, :, 3])
    source_gray = np.asarray(source.convert("L"), dtype=np.float64)
    output_gray = np.asarray(normalized.convert("L"), dtype=np.float64)

    tile_metrics = []
    for tile in fixture["tiles"]:
        left, top, right, bottom = tile["bbox"]
        tile_delta = rgb_delta[top:bottom, left:right]
        tile_absolute_delta = rgb_absolute_delta[top:bottom, left:right]
        tile_metrics.append(
            {
                "name": tile["name"],
                "changed_pixel_ratio_gt2": round(float(np.mean(tile_delta > 2)), 6),
                "mean_abs_rgb_delta": round(float(tile_absolute_delta.mean()), 4),
                "global_ssim": round(
                    _global_ssim(
                        source_gray[top:bottom, left:right],
                        output_gray[top:bottom, left:right],
                    ),
                    6,
                ),
            }
        )

    metadata = inspect_image_metadata(result_path)
    categories = metadata.get("categories") or {}
    metadata_present = any(bool(item.get("present")) for item in categories.values())
    if metadata.get("status") == "ok":
        metadata_hint = FileHintStatus.PRESENT if metadata_present else FileHintStatus.NOT_PRESENT
    else:
        metadata_hint = FileHintStatus.UNKNOWN
    c2pa_presence = str((metadata.get("c2pa") or {}).get("presence", "unknown"))
    c2pa_hint = {
        "present": FileHintStatus.PRESENT,
        "not_present": FileHintStatus.NOT_PRESENT,
    }.get(c2pa_presence, FileHintStatus.UNKNOWN)

    comparison = Image.new("RGB", (BOARD_SIZE * 2, BOARD_SIZE + 42), "white")
    comparison.paste(_checker_preview(source), (0, 42))
    comparison.paste(_checker_preview(normalized), (BOARD_SIZE, 42))
    draw = ImageDraw.Draw(comparison)
    draw.text((12, 9), "BEFORE", fill=(20, 24, 30), font=_font(22, bold=True))
    draw.text((BOARD_SIZE + 12, 9), "AFTER", fill=(20, 24, 30), font=_font(22, bold=True))
    comparison.save(comparison_path, format="PNG")

    return {
        "provider_output": {
            "format": provider_format,
            "mode": provider_mode,
            "size": provider_size,
            "has_alpha": provider_has_alpha,
            "info_keys": provider_info_keys,
        },
        "normalized_size": list(source.size),
        "rgb_changed_pixel_ratio_gt2": round(float(np.mean(rgb_delta > 2)), 6),
        "rgb_mean_abs_delta": round(float(rgb_absolute_delta.mean()), 4),
        "global_ssim": round(_global_ssim(source_gray, output_gray), 6),
        "alpha_changed_pixel_ratio": round(float(np.mean(alpha_delta > 0)), 6),
        "normalized_output_transparent_pixels": int(np.count_nonzero(output_array[:, :, 3] < 255)),
        "tiles": tile_metrics,
        "text_accuracy": "manual_review_required",
        "metadata_inspection": metadata,
        "pixel_watermark_status": {
            "synthid": create_pixel_watermark_status(
                marker_type=PixelMarkerType.SYNTHID,
                processing_status=PixelProcessingStatus.SUCCEEDED,
                metadata_hint=metadata_hint,
                c2pa_hint=c2pa_hint,
            ),
            "unknown": create_pixel_watermark_status(
                marker_type=PixelMarkerType.UNKNOWN,
                processing_status=PixelProcessingStatus.SUCCEEDED,
                metadata_hint=metadata_hint,
                c2pa_hint=c2pa_hint,
            ),
        },
        "comparison": str(comparison_path),
    }


def _run_live(
    model: str,
    source_path: Path,
    output_path: Path,
    audit: dict[str, bool],
) -> float:
    sys.path.insert(0, str(PROJECT_ROOT))
    import main as app

    config = json.loads(Path(app.CONFIG_FILE).read_text(encoding="utf-8"))
    api_key = str(config.get("kie_api_key", "")).strip()
    if not api_key:
        raise ValueError("KIE API key is not configured")
    config = dict(config)
    config.update(
        {
            "timeout": 60,
            "retries": 2,
            "generation_wait_timeout": 900,
            "status_poll_interval": 10,
            "export_300_dpi": False,
        }
    )
    worker = app.WorkerThread("process", str(output_path.parent), config)

    def inspect_progress(message: object) -> None:
        if api_key and api_key in str(message):
            audit["api_key_logged"] = True

    worker.progress.connect(inspect_progress)
    source_url = worker._kie_upload_file(str(source_path))
    payload = {"prompt": PROMPT, "input_urls": [source_url], **MODEL_CONFIG[model]["input"]}
    started = time.perf_counter()
    task_id = worker._kie_create_task(model, payload)
    result_url = worker._kie_wait_result(task_id)
    worker._download_file(result_url, str(output_path))
    return time.perf_counter() - started


def main() -> int:
    parser = argparse.ArgumentParser(description="Task 39 KIE whole-image regeneration benchmark")
    parser.add_argument("--photo", type=Path, required=True)
    parser.add_argument("--face", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", choices=sorted(MODEL_CONFIG), default="gpt-image-2-image-to-image")
    parser.add_argument("--existing-result", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--allow-paid", action="store_true")
    args = parser.parse_args()

    for source in (args.photo, args.face):
        if not source.is_file():
            raise FileNotFoundError(source)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    board, fixture = build_fixture_board(args.photo, args.face)
    board_path = args.output_dir / "input-board.png"
    board.save(board_path, format="PNG")
    _atomic_json(args.output_dir / "fixture.json", fixture)
    if args.prepare_only:
        print(json.dumps({"prepared": str(board_path), "fixture": fixture}, ensure_ascii=True, indent=2))
        return 0

    model_slug = args.model.replace("/", "_")
    # A non-image suffix makes the app downloader preserve provider bytes exactly.
    output_path = args.output_dir / f"output-{model_slug}.provider"
    elapsed_seconds = None
    audit = {"api_key_logged": False}
    attempt_number = None
    if args.existing_result is not None:
        if not args.existing_result.is_file():
            raise FileNotFoundError(args.existing_result)
        output_path = args.existing_result.resolve()
        analysis_mode = "existing_result"
    else:
        if not args.allow_paid:
            parser.error("--allow-paid is required for a live generation")
        attempt_number = ensure_live_generation_budget()
        analysis_mode = "live_paid"
        try:
            elapsed_seconds = _run_live(args.model, board_path, output_path, audit)
        except Exception as error:
            failure = {
                "schema": 1,
                "analysis_mode": analysis_mode,
                "model": args.model,
                "generation_attempt": attempt_number,
                "processing_status": "failed",
                "error_type": type(error).__name__,
                "api_key_logged": audit["api_key_logged"],
            }
            _atomic_json(args.output_dir / f"failure-{model_slug}.json", failure)
            raise

    comparison_path = args.output_dir / f"comparison-{model_slug}.png"
    metrics = analyze_result(board_path, output_path, fixture, comparison_path)
    report = {
        "schema": 1,
        "analysis_mode": analysis_mode,
        "model": args.model,
        "generation_attempt": attempt_number,
        "listed_credits_snapshot": MODEL_CONFIG[args.model]["listed_credits"],
        "listed_cost_usd_snapshot": MODEL_CONFIG[args.model]["listed_cost_usd"],
        "cost_note": "listed model credits and price, not billing evidence",
        "elapsed_seconds": round(elapsed_seconds, 3) if elapsed_seconds is not None else None,
        "fixture": fixture,
        "metrics": metrics,
        "output": str(output_path),
        "api_key_logged": audit["api_key_logged"],
    }
    serialized = json.dumps(report, ensure_ascii=True, indent=2)
    config_text = Path(os.environ.get("LOCALAPPDATA", ""), "Clipart Generator", "config.json")
    if config_text.is_file():
        key = str(json.loads(config_text.read_text(encoding="utf-8")).get("kie_api_key", "")).strip()
        if key and key in serialized:
            raise RuntimeError("API key reached the benchmark report")
    report_path = args.output_dir / f"benchmark-{model_slug}.json"
    report_path.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
