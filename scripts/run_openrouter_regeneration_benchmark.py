"""Prepare and analyze the isolated Task 40 OpenRouter benchmark."""

from __future__ import annotations

import argparse
import base64
import binascii
import io
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import run_kie_regeneration_benchmark as common


OPENROUTER_IMAGE_ENDPOINT = "https://openrouter.ai/api/v1/images"
MODEL_ID = "recraft/recraft-v4.1-utility"
PROVIDER_ID = "recraft"
LISTED_COST_USD = 0.035
TASK40_AUTHORIZED_GENERATION_ATTEMPTS = 0
MAX_PROVIDER_IMAGE_BYTES = 50 * 1024 * 1024
MAX_WEBP_CHUNKS = 128
SNAPSHOT_DATE = "2026-07-16"
CANDIDATE_SNAPSHOT = {
    "model": MODEL_ID,
    "provider": PROVIDER_ID,
    "listed_cost_usd_per_output_image": LISTED_COST_USD,
    "input_references": {"min": 0, "max": 1},
    "output_resolution": "approximately 1K",
    "documented_typical_latency_seconds": 6,
    "provider_watermark_policy": "not_documented",
    "pixel_watermark_removal_claim": "not_claimed",
    "sources": {
        "image_api": "https://openrouter.ai/docs/guides/overview/multimodal/image-generation",
        "model": "https://openrouter.ai/recraft/recraft-v4.1-utility",
        "endpoints": (
            "https://openrouter.ai/api/v1/images/models/"
            "recraft/recraft-v4.1-utility/endpoints"
        ),
    },
    "checked_on": SNAPSHOT_DATE,
}


class OpenRouterBenchmarkError(RuntimeError):
    """A secret-safe benchmark failure."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def default_attempt_state_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise OpenRouterBenchmarkError("LOCALAPPDATA is unavailable")
    return (
        Path(local_app_data)
        / "Clipart Generator"
        / "benchmarks"
        / "task40-openrouter-request-state.json"
    )


def ensure_live_authorization_available(
    authorized_attempts: int = TASK40_AUTHORIZED_GENERATION_ATTEMPTS,
) -> None:
    if authorized_attempts <= 0:
        raise OpenRouterBenchmarkError(
            "Task 40 live generation is closed pending separate user authorization"
        )


def reserve_live_attempt(
    state_path: Path | None = None,
    *,
    authorized_attempts: int = TASK40_AUTHORIZED_GENERATION_ATTEMPTS,
) -> int:
    """Reserve one attempt globally before network I/O, failing closed."""
    ensure_live_authorization_available(authorized_attempts)
    state_path = state_path or default_attempt_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise OpenRouterBenchmarkError("Task 40 attempt state is locked") from error

    try:
        os.close(lock_fd)
        used_attempts = 0
        if state_path.is_file():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
                used_attempts = int(state["used_attempts"])
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                raise OpenRouterBenchmarkError("Task 40 attempt state is invalid") from error
            if used_attempts < 0:
                raise OpenRouterBenchmarkError("Task 40 attempt state is invalid")
        if used_attempts >= authorized_attempts:
            raise OpenRouterBenchmarkError("Task 40 live generation budget is exhausted")
        attempt_number = used_attempts + 1
        common._atomic_json(
            state_path,
            {
                "schema": 1,
                "used_attempts": attempt_number,
                "authorized_attempts": authorized_attempts,
            },
        )
        return attempt_number
    finally:
        lock_path.unlink(missing_ok=True)


def _input_reference(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def build_request_payload(source_path: Path) -> dict[str, Any]:
    return {
        "model": MODEL_ID,
        "prompt": common.PROMPT,
        "n": 1,
        "input_references": [
            {
                "type": "image_url",
                "image_url": {"url": _input_reference(source_path)},
            }
        ],
        "provider": {"only": [PROVIDER_ID], "allow_fallbacks": False},
    }


def parse_provider_response(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise OpenRouterBenchmarkError("OpenRouter returned an invalid response")
    data = payload.get("data")
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
        raise OpenRouterBenchmarkError("OpenRouter returned an invalid image list")
    encoded = data[0].get("b64_json")
    if not isinstance(encoded, str) or not encoded:
        raise OpenRouterBenchmarkError("OpenRouter returned no image bytes")
    if len(encoded) > ((MAX_PROVIDER_IMAGE_BYTES + 2) // 3) * 4 + 8:
        raise OpenRouterBenchmarkError("OpenRouter image exceeds the size limit")
    try:
        provider_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise OpenRouterBenchmarkError("OpenRouter returned invalid base64 image data") from error
    if not provider_bytes or len(provider_bytes) > MAX_PROVIDER_IMAGE_BYTES:
        raise OpenRouterBenchmarkError("OpenRouter image exceeds the size limit")
    try:
        with Image.open(io.BytesIO(provider_bytes)) as image:
            image.verify()
    except Exception as error:
        raise OpenRouterBenchmarkError("OpenRouter returned invalid image bytes") from error

    media_type = data[0].get("media_type")
    if media_type is not None and not isinstance(media_type, str):
        media_type = None
    usage = payload.get("usage")
    billed_cost = usage.get("cost") if isinstance(usage, dict) else None
    if (
        isinstance(billed_cost, bool)
        or not isinstance(billed_cost, (int, float))
        or not math.isfinite(float(billed_cost))
        or float(billed_cost) < 0
    ):
        billed_cost = None
    return {
        "provider_bytes": provider_bytes,
        "media_type": media_type,
        "billed_cost_usd": float(billed_cost) if billed_cost is not None else None,
    }


def inspect_provider_container(path: Path) -> dict[str, Any]:
    """Record bounded WebP chunk evidence without serializing provider values."""
    if path.stat().st_size > MAX_PROVIDER_IMAGE_BYTES:
        raise OpenRouterBenchmarkError("Provider image exceeds the size limit")
    data = path.read_bytes()
    if len(data) > MAX_PROVIDER_IMAGE_BYTES:
        raise OpenRouterBenchmarkError("Provider image exceeds the size limit")
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return {"format": "other", "status": "not_webp"}
    declared_size = int.from_bytes(data[4:8], "little") + 8
    if declared_size != len(data):
        raise OpenRouterBenchmarkError("Provider WebP RIFF size does not match the file")

    known_chunk_types = {
        b"VP8 ": "VP8",
        b"VP8L": "VP8L",
        b"VP8X": "VP8X",
        b"ALPH": "ALPH",
        b"ANIM": "ANIM",
        b"ANMF": "ANMF",
        b"ICCP": "ICCP",
        b"EXIF": "EXIF",
        b"XMP ": "XMP",
        b"CRFT": "CRFT",
    }
    chunks: list[dict[str, Any]] = []
    recraft_signature: dict[str, Any] | None = None
    position = 12
    while position + 8 <= len(data):
        if len(chunks) >= MAX_WEBP_CHUNKS:
            raise OpenRouterBenchmarkError("Provider WebP contains too many chunks")
        chunk_type = data[position : position + 4]
        chunk_size = int.from_bytes(data[position + 4 : position + 8], "little")
        payload_start = position + 8
        payload_end = payload_start + chunk_size
        if payload_end > len(data):
            raise OpenRouterBenchmarkError("Provider WebP contains a truncated chunk")
        safe_type = known_chunk_types.get(chunk_type, "other")
        chunks.append({"type": safe_type, "size_bytes": chunk_size})
        if chunk_type == b"CRFT":
            try:
                value = json.loads(data[payload_start:payload_end])
            except (UnicodeDecodeError, json.JSONDecodeError):
                value = None
            if isinstance(value, dict):
                algorithm = value.get("signing_algo")
                recraft_signature = {
                    "signed_by_matches_expected_provider": value.get("signed_by") == PROVIDER_ID,
                    "signature_present": isinstance(value.get("signature_b64"), str)
                    and bool(value["signature_b64"]),
                    "signing_algorithm": "Ed25519" if algorithm == "Ed25519" else "other",
                    "identifier_present": isinstance(value.get("identifier"), str)
                    and bool(value["identifier"]),
                    "generation_timestamp_present": isinstance(
                        value.get("generation_timestamp"), (int, float)
                    )
                    and not isinstance(value.get("generation_timestamp"), bool),
                }
            else:
                recraft_signature = {"present": True, "parsed": False}
        next_position = payload_end + (chunk_size & 1)
        if next_position > len(data):
            raise OpenRouterBenchmarkError("Provider WebP contains truncated padding")
        position = next_position

    return {
        "format": "WEBP",
        "status": "inspected",
        "file_size_bytes": len(data),
        "declared_size_matches": True,
        "trailing_bytes": len(data) - position,
        "chunks": chunks,
        "recraft_signature": recraft_signature,
        "c2pa_validation": "not_performed",
    }


def _request_image(source_path: Path, api_key: str) -> tuple[dict[str, Any], float]:
    body = json.dumps(build_request_payload(source_path), separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        OPENROUTER_IMAGE_ENDPOINT,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            response_bytes = response.read(MAX_PROVIDER_IMAGE_BYTES * 2)
    except urllib.error.HTTPError as error:
        raise OpenRouterBenchmarkError(
            "OpenRouter request failed", status_code=error.code
        ) from None
    except (urllib.error.URLError, TimeoutError):
        raise OpenRouterBenchmarkError("OpenRouter request failed") from None
    elapsed_seconds = time.perf_counter() - started
    try:
        payload = json.loads(response_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise OpenRouterBenchmarkError("OpenRouter returned invalid JSON") from None
    return parse_provider_response(payload), elapsed_seconds


def run_live_generation(
    source_path: Path,
    output_path: Path,
    *,
    state_path: Path | None = None,
    authorized_attempts: int = TASK40_AUTHORIZED_GENERATION_ATTEMPTS,
) -> tuple[int, float, float | None, str | None]:
    ensure_live_authorization_available(authorized_attempts)
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise OpenRouterBenchmarkError("OPENROUTER_API_KEY is not configured")
    attempt_number = reserve_live_attempt(
        state_path, authorized_attempts=authorized_attempts
    )
    parsed, elapsed_seconds = _request_image(source_path, api_key)
    output_path.write_bytes(parsed["provider_bytes"])
    return (
        attempt_number,
        elapsed_seconds,
        parsed["billed_cost_usd"],
        parsed["media_type"],
    )


def serialize_report(report: dict[str, Any], *, api_key: str = "") -> str:
    serialized = json.dumps(report, ensure_ascii=True, indent=2)
    if api_key and api_key in serialized:
        raise OpenRouterBenchmarkError("API key reached the benchmark report")
    return serialized


def _write_failure(output_dir: Path, error: Exception) -> None:
    failure = {
        "schema": 1,
        "analysis_mode": "live_paid",
        "model": MODEL_ID,
        "processing_status": "failed",
        "error_type": type(error).__name__,
        "status_code": getattr(error, "status_code", None),
        "api_key_logged": False,
    }
    common._atomic_json(output_dir / "failure-openrouter.json", failure)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Task 40 isolated OpenRouter whole-image regeneration benchmark"
    )
    parser.add_argument("--photo", type=Path, required=True)
    parser.add_argument("--face", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--existing-result", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--allow-paid", action="store_true")
    args = parser.parse_args()

    for source in (args.photo, args.face):
        if not source.is_file():
            raise FileNotFoundError(source)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    board, fixture = common.build_fixture_board(args.photo, args.face)
    board_path = args.output_dir / "input-board.png"
    board.save(board_path, format="PNG")
    common._atomic_json(args.output_dir / "fixture.json", fixture)
    common._atomic_json(args.output_dir / "candidate-snapshot.json", CANDIDATE_SNAPSHOT)
    if args.prepare_only:
        print(
            serialize_report(
                {
                    "prepared": str(board_path),
                    "candidate": CANDIDATE_SNAPSHOT,
                    "live_generation_authorized": False,
                }
            )
        )
        return 0

    output_path = args.output_dir / "output-openrouter-recraft-v4.1-utility.provider"
    attempt_number = None
    elapsed_seconds = None
    billed_cost_usd = None
    media_type = None
    if args.existing_result is not None:
        if not args.existing_result.is_file():
            raise FileNotFoundError(args.existing_result)
        output_path = args.existing_result.resolve()
        analysis_mode = "existing_result"
    else:
        if not args.allow_paid:
            parser.error("--allow-paid is required for a live generation")
        analysis_mode = "live_paid"
        try:
            (
                attempt_number,
                elapsed_seconds,
                billed_cost_usd,
                media_type,
            ) = run_live_generation(board_path, output_path)
        except Exception as error:
            _write_failure(args.output_dir, error)
            raise

    comparison_path = args.output_dir / "comparison-openrouter-recraft-v4.1-utility.png"
    metrics = common.analyze_result(board_path, output_path, fixture, comparison_path)
    report = {
        "schema": 1,
        "analysis_mode": analysis_mode,
        "model": MODEL_ID,
        "provider": PROVIDER_ID,
        "generation_attempt": attempt_number,
        "listed_cost_usd_snapshot": LISTED_COST_USD,
        "billed_cost_usd_response": billed_cost_usd,
        "cost_note": "listed price is a snapshot; response cost is billing evidence when present",
        "elapsed_seconds": round(elapsed_seconds, 3) if elapsed_seconds is not None else None,
        "response_media_type": media_type,
        "fixture": fixture,
        "metrics": metrics,
        "provider_container": inspect_provider_container(output_path),
        "output": str(output_path),
        "api_key_logged": False,
    }
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    serialized = serialize_report(report, api_key=api_key)
    (args.output_dir / "benchmark-openrouter-recraft-v4.1-utility.json").write_text(
        serialized + "\n", encoding="utf-8"
    )
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
