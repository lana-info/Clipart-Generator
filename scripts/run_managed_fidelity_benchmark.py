"""Run the bounded Task 41 managed image-editing fidelity benchmark."""

from __future__ import annotations

import argparse
import base64
import binascii
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import warnings
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import run_kie_regeneration_benchmark as common
from scripts import run_openrouter_regeneration_benchmark as openrouter


SNAPSHOT_DATE = "2026-07-16"
TOTAL_TEST_BUDGET_USD = Decimal("0.300")
TASK40_REPORTED_SPEND_USD = Decimal("0.035")
MAX_SOURCE_IMAGE_BYTES = 20 * 1024 * 1024
MAX_SOURCE_IMAGE_PIXELS = 20_000_000
MAX_SOURCE_IMAGE_SIDE = 8192
OPENROUTER_HOST = "openrouter.ai"
OPENROUTER_KEY_ENDPOINT = "https://openrouter.ai/api/v1/key"
TASK41_AUTHORIZED_CANDIDATES: tuple[str, ...] = ()
FIDELITY_PROMPT = (
    "Edit image 1 as a fidelity-preserving reconstruction. Re-render the complete image "
    "with the smallest perceptible change so its pixels are newly reconstructed, but do "
    "not alter its visible content. Preserve the exact same subject identity and face, "
    "expression, pose, object count, geometry, composition, crop, aspect ratio, lighting, "
    "colors, textures, illustration style, transparent regions, fine lines, grid, color "
    "swatches, and every text character and number. Do not add, remove, replace, move, or "
    "redesign anything. Do not invent a new scene. Return one complete square image and "
    "preserve transparency where the model supports it."
)

CANDIDATES: dict[str, dict[str, Any]] = {
    "seedream-4.5": {
        "model": "bytedance-seed/seedream-4.5",
        "provider": "seed",
        "listed_cost_usd": Decimal("0.040"),
        "reservation_cost_usd": Decimal("0.040"),
        "request_options": {"resolution": "1K", "aspect_ratio": "1:1"},
        "input_mode": "native",
        "price_unit": "image",
        "price_variant": None,
        "sources": {
            "model": "https://seed.bytedance.com/en/seedream4_5",
            "endpoint": (
                "https://openrouter.ai/api/v1/images/models/"
                "bytedance-seed/seedream-4.5/endpoints"
            ),
        },
    },
    "seedream-4.5-rgb-defaults": {
        "model": "bytedance-seed/seedream-4.5",
        "provider": "seed",
        "listed_cost_usd": Decimal("0.040"),
        "reservation_cost_usd": Decimal("0.040"),
        "request_options": {},
        "input_mode": "RGB",
        "price_unit": "image",
        "price_variant": None,
        "sources": {
            "model": "https://seed.bytedance.com/en/seedream4_5",
            "endpoint": (
                "https://openrouter.ai/api/v1/images/models/"
                "bytedance-seed/seedream-4.5/endpoints"
            ),
        },
    },
    "riverflow-v2.5-pro": {
        "model": "sourceful/riverflow-v2.5-pro",
        "provider": "sourceful",
        "listed_cost_usd": Decimal("0.130"),
        "reservation_cost_usd": Decimal("0.130"),
        "request_options": {"resolution": "1K", "output_format": "png"},
        "input_mode": "RGB",
        "price_unit": "image",
        "price_variant": None,
        "sources": {
            "model": "https://www.riverflow.ai/research/introducing-riverflow-2-0",
            "endpoint": (
                "https://openrouter.ai/api/v1/images/models/"
                "sourceful/riverflow-v2.5-pro/endpoints"
            ),
        },
    },
}


class ManagedFidelityBenchmarkError(RuntimeError):
    """A secret-safe Task 41 benchmark failure."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        provider_error: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.provider_error = provider_error


def _money(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ManagedFidelityBenchmarkError("Task 41 budget state is invalid")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ManagedFidelityBenchmarkError("Task 41 budget state is invalid") from error
    if not amount.is_finite() or amount < 0:
        raise ManagedFidelityBenchmarkError("Task 41 budget state is invalid")
    return amount


def _money_text(value: Decimal) -> str:
    whole, dot, fraction = format(value, "f").partition(".")
    if not dot:
        return f"{whole}.000"
    fraction = fraction.rstrip("0")
    return f"{whole}.{fraction.ljust(3, '0')}"


def default_budget_state_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise ManagedFidelityBenchmarkError("LOCALAPPDATA is unavailable")
    return (
        Path(local_app_data)
        / "Clipart Generator"
        / "benchmarks"
        / "task41-managed-fidelity-budget-state.json"
    )


def ensure_candidate_authorized(
    candidate_id: str,
    *,
    authorized_candidates: tuple[str, ...] = TASK41_AUTHORIZED_CANDIDATES,
) -> None:
    if candidate_id not in CANDIDATES:
        raise ManagedFidelityBenchmarkError("Unknown Task 41 candidate")
    if candidate_id not in authorized_candidates:
        raise ManagedFidelityBenchmarkError(
            "Task 41 paid generation is closed for this candidate"
        )


def _empty_budget_state() -> dict[str, Any]:
    return {
        "schema": 1,
        "total_budget_usd": _money_text(TOTAL_TEST_BUDGET_USD),
        "prior_task40_spend_usd": _money_text(TASK40_REPORTED_SPEND_USD),
        "reservations": {},
    }


def _load_budget_state(state_path: Path) -> dict[str, Any]:
    if not state_path.is_file():
        return _empty_budget_state()
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ManagedFidelityBenchmarkError("Task 41 budget state is invalid") from error
    if (
        not isinstance(state, dict)
        or state.get("schema") != 1
        or _money(state.get("total_budget_usd")) != TOTAL_TEST_BUDGET_USD
        or _money(state.get("prior_task40_spend_usd")) != TASK40_REPORTED_SPEND_USD
        or not isinstance(state.get("reservations"), dict)
    ):
        raise ManagedFidelityBenchmarkError("Task 41 budget state is invalid")
    attempt_numbers = set()
    for candidate_id, reservation in state["reservations"].items():
        if candidate_id not in CANDIDATES or not isinstance(reservation, dict):
            raise ManagedFidelityBenchmarkError("Task 41 budget state is invalid")
        if (
            _money(reservation.get("reserved_usd"))
            != CANDIDATES[candidate_id]["reservation_cost_usd"]
        ):
            raise ManagedFidelityBenchmarkError("Task 41 budget state is invalid")
        attempt_number = reservation.get("attempt_number")
        if (
            not isinstance(attempt_number, int)
            or isinstance(attempt_number, bool)
            or attempt_number <= 0
            or attempt_number in attempt_numbers
        ):
            raise ManagedFidelityBenchmarkError("Task 41 budget state is invalid")
        attempt_numbers.add(attempt_number)
        actual = reservation.get("actual_usd")
        if actual is not None:
            _money(actual)
        if reservation.get("status") not in {"reserved", "completed", "failed"}:
            raise ManagedFidelityBenchmarkError("Task 41 budget state is invalid")
    if attempt_numbers != set(range(1, len(attempt_numbers) + 1)):
        raise ManagedFidelityBenchmarkError("Task 41 budget state is invalid")
    return state


def _counted_spend(state: dict[str, Any]) -> Decimal:
    spend = TASK40_REPORTED_SPEND_USD
    for reservation in state["reservations"].values():
        actual = reservation.get("actual_usd")
        spend += _money(actual if actual is not None else reservation["reserved_usd"])
    return spend


def budget_snapshot(state_path: Path | None = None) -> dict[str, Any]:
    state_path = state_path or default_budget_state_path()
    state = _load_budget_state(state_path)
    counted = _counted_spend(state)
    return {
        "total_budget_usd": _money_text(TOTAL_TEST_BUDGET_USD),
        "prior_task40_spend_usd": _money_text(TASK40_REPORTED_SPEND_USD),
        "counted_spend_usd": _money_text(counted),
        "remaining_budget_usd": _money_text(TOTAL_TEST_BUDGET_USD - counted),
        "attempted_candidates": list(state["reservations"]),
    }


def _locked_state_path(state_path: Path) -> tuple[int, Path]:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except (FileExistsError, PermissionError) as error:
        raise ManagedFidelityBenchmarkError("Task 41 budget state is locked") from error
    return lock_fd, lock_path


def _release_state_lock(lock_path: Path, *, preserve_active_error: bool) -> None:
    try:
        lock_path.unlink(missing_ok=True)
    except OSError as error:
        if preserve_active_error:
            return
        raise ManagedFidelityBenchmarkError(
            "Task 41 budget state lock could not be released"
        ) from error


def reserve_candidate(
    candidate_id: str,
    state_path: Path | None = None,
    *,
    authorized_candidates: tuple[str, ...] = TASK41_AUTHORIZED_CANDIDATES,
) -> int:
    """Reserve a candidate and its worst-case listed cost before the paid POST."""
    ensure_candidate_authorized(
        candidate_id, authorized_candidates=authorized_candidates
    )
    state_path = state_path or default_budget_state_path()
    lock_fd, lock_path = _locked_state_path(state_path)
    try:
        os.close(lock_fd)
        state = _load_budget_state(state_path)
        if candidate_id in state["reservations"]:
            raise ManagedFidelityBenchmarkError(
                "Task 41 candidate request was already consumed"
            )
        candidate = CANDIDATES[candidate_id]
        projected = _counted_spend(state) + candidate["reservation_cost_usd"]
        if projected > TOTAL_TEST_BUDGET_USD:
            raise ManagedFidelityBenchmarkError("Task 41 total test budget is exhausted")
        attempt_number = len(state["reservations"]) + 1
        state["reservations"][candidate_id] = {
            "attempt_number": attempt_number,
            "reserved_usd": _money_text(candidate["reservation_cost_usd"]),
            "actual_usd": None,
            "status": "reserved",
        }
        common._atomic_json(state_path, state)
        return attempt_number
    finally:
        _release_state_lock(
            lock_path, preserve_active_error=sys.exc_info()[0] is not None
        )


def mark_candidate_result(
    candidate_id: str,
    *,
    actual_cost_usd: float | None,
    status: str,
    state_path: Path | None = None,
) -> None:
    if status not in {"completed", "failed"}:
        raise ManagedFidelityBenchmarkError("Task 41 result status is invalid")
    state_path = state_path or default_budget_state_path()
    lock_fd, lock_path = _locked_state_path(state_path)
    try:
        os.close(lock_fd)
        state = _load_budget_state(state_path)
        reservation = state["reservations"].get(candidate_id)
        if not isinstance(reservation, dict) or reservation.get("status") != "reserved":
            raise ManagedFidelityBenchmarkError("Task 41 reservation is unavailable")
        cost_violation = None
        if actual_cost_usd is not None:
            actual = _money(actual_cost_usd)
            reservation["actual_usd"] = _money_text(actual)
            if actual > _money(reservation["reserved_usd"]):
                cost_violation = "Provider cost exceeded the Task 41 reservation"
        reservation["status"] = status
        common._atomic_json(state_path, state)
        if _counted_spend(state) > TOTAL_TEST_BUDGET_USD:
            cost_violation = "Provider cost exceeded the Task 41 total budget"
        if cost_violation is not None:
            raise ManagedFidelityBenchmarkError(cost_violation)
    finally:
        _release_state_lock(
            lock_path, preserve_active_error=sys.exc_info()[0] is not None
        )


def _read_validated_image(
    path: Path,
    *,
    max_bytes: int = MAX_SOURCE_IMAGE_BYTES,
    max_pixels: int = MAX_SOURCE_IMAGE_PIXELS,
) -> bytes:
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.stat().st_size > max_bytes:
        raise ManagedFidelityBenchmarkError("Task 41 source image exceeds the size limit")
    data = path.read_bytes()
    if not data or len(data) > max_bytes:
        raise ManagedFidelityBenchmarkError("Task 41 source image exceeds the size limit")
    _validate_image_bytes(data, max_bytes=max_bytes, max_pixels=max_pixels)
    return data


def _validate_image_bytes(
    data: bytes,
    *,
    max_bytes: int,
    max_pixels: int,
) -> None:
    if not data or len(data) > max_bytes:
        raise ManagedFidelityBenchmarkError("Task 41 image exceeds the size limit")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                width, height = image.size
                if (
                    width <= 0
                    or height <= 0
                    or width > MAX_SOURCE_IMAGE_SIDE
                    or height > MAX_SOURCE_IMAGE_SIDE
                    or width * height > max_pixels
                ):
                    raise ManagedFidelityBenchmarkError(
                        "Task 41 image exceeds the pixel limit"
                    )
                image.verify()
    except ManagedFidelityBenchmarkError:
        raise
    except Exception as error:
        raise ManagedFidelityBenchmarkError("Task 41 image is invalid") from error


def _validate_source_image(path: Path) -> None:
    _read_validated_image(path)


def _input_reference(path: Path, *, input_mode: str) -> str:
    source_bytes = _read_validated_image(path)
    if input_mode == "native":
        provider_bytes = source_bytes
    elif input_mode == "RGB":
        with Image.open(io.BytesIO(source_bytes)) as image:
            converted = image.convert("RGB")
            buffer = io.BytesIO()
            converted.save(buffer, format="PNG")
            provider_bytes = buffer.getvalue()
        _validate_image_bytes(
            provider_bytes,
            max_bytes=MAX_SOURCE_IMAGE_BYTES,
            max_pixels=MAX_SOURCE_IMAGE_PIXELS,
        )
    else:
        raise ManagedFidelityBenchmarkError("Task 41 input mode is invalid")
    encoded = base64.b64encode(provider_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def build_request_payload(candidate_id: str, source_path: Path) -> dict[str, Any]:
    candidate = CANDIDATES[candidate_id]
    return {
        "model": candidate["model"],
        "prompt": FIDELITY_PROMPT,
        "n": 1,
        "input_references": [
            {
                "type": "image_url",
                "image_url": {
                    "url": _input_reference(
                        source_path,
                        input_mode=candidate["input_mode"],
                    )
                },
            }
        ],
        **candidate["request_options"],
        "provider": {
            "only": [candidate["provider"]],
            "allow_fallbacks": False,
        },
    }


def parse_endpoint_snapshot(candidate_id: str, payload: object) -> dict[str, Any]:
    candidate = CANDIDATES[candidate_id]
    if not isinstance(payload, dict) or payload.get("id") != candidate["model"]:
        raise ManagedFidelityBenchmarkError("OpenRouter endpoint snapshot is invalid")
    endpoints = payload.get("endpoints")
    if not isinstance(endpoints, list):
        raise ManagedFidelityBenchmarkError("OpenRouter endpoint snapshot is invalid")
    matching_endpoints = [
        value
        for value in endpoints
        if isinstance(value, dict)
        and value.get("provider_tag") == candidate["provider"]
    ]
    if not matching_endpoints:
        raise ManagedFidelityBenchmarkError("Pinned OpenRouter provider is unavailable")
    if len(matching_endpoints) != 1:
        raise ManagedFidelityBenchmarkError(
            "Pinned OpenRouter provider endpoint is ambiguous"
        )
    endpoint = matching_endpoints[0]
    if endpoint.get("provider_slug") != candidate["provider"]:
        raise ManagedFidelityBenchmarkError("Pinned OpenRouter provider is invalid")
    parameters = endpoint.get("supported_parameters")
    if not isinstance(parameters, dict):
        raise ManagedFidelityBenchmarkError("Pinned provider capabilities are invalid")
    input_references = parameters.get("input_references")
    if (
        not isinstance(input_references, dict)
        or input_references.get("type") != "range"
        or not isinstance(input_references.get("min"), (int, float))
        or isinstance(input_references.get("min"), bool)
        or not isinstance(input_references.get("max"), (int, float))
        or isinstance(input_references.get("max"), bool)
        or input_references["min"] > 1
        or input_references["max"] < 1
    ):
        raise ManagedFidelityBenchmarkError("Pinned provider no longer accepts image input")
    output_count = parameters.get("n")
    if (
        not isinstance(output_count, dict)
        or output_count.get("type") != "range"
        or not isinstance(output_count.get("min"), (int, float))
        or isinstance(output_count.get("min"), bool)
        or not isinstance(output_count.get("max"), (int, float))
        or isinstance(output_count.get("max"), bool)
        or output_count["min"] > 1
        or output_count["max"] < 1
    ):
        raise ManagedFidelityBenchmarkError("Pinned provider cannot return one image")
    for name, requested_value in candidate["request_options"].items():
        descriptor = parameters.get(name)
        if (
            not isinstance(descriptor, dict)
            or descriptor.get("type") != "enum"
            or not isinstance(descriptor.get("values"), list)
            or requested_value not in descriptor["values"]
        ):
            raise ManagedFidelityBenchmarkError(
                "Pinned provider no longer accepts a required option"
            )
    matching_prices = []
    for price in endpoint.get("pricing", []):
        if (
            isinstance(price, dict)
            and price.get("billable") == "output_image"
            and price.get("unit") == candidate["price_unit"]
            and price.get("variant") == candidate["price_variant"]
        ):
            matching_prices.append(_money(price.get("cost_usd")))
    if len(matching_prices) != 1:
        raise ManagedFidelityBenchmarkError("Pinned provider price is unavailable")
    live_cost = matching_prices[0]
    if live_cost > candidate["reservation_cost_usd"]:
        raise ManagedFidelityBenchmarkError("Pinned provider price exceeds the reservation")
    return {
        "provider": candidate["provider"],
        "cost_usd": _money_text(live_cost),
        "unit": candidate["price_unit"],
        "required_options_supported": True,
        "checked_on": SNAPSHOT_DATE,
    }


class _RejectRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open_pinned_openrouter_request(
    request: urllib.request.Request, *, timeout: float
):
    parsed = urllib.parse.urlsplit(request.full_url)
    if parsed.scheme != "https" or parsed.hostname != OPENROUTER_HOST:
        raise ManagedFidelityBenchmarkError("OpenRouter request target is not allowed")
    opener = urllib.request.build_opener(_RejectRedirectHandler())
    return opener.open(request, timeout=timeout)


def fetch_endpoint_snapshot(candidate_id: str) -> dict[str, Any]:
    request = urllib.request.Request(
        CANDIDATES[candidate_id]["sources"]["endpoint"], method="GET"
    )
    try:
        with _open_pinned_openrouter_request(request, timeout=30) as response:
            response_bytes = response.read(1024 * 1024 + 1)
    except urllib.error.HTTPError as error:
        raise ManagedFidelityBenchmarkError(
            "OpenRouter price preflight failed", status_code=error.code
        ) from None
    except (urllib.error.URLError, TimeoutError):
        raise ManagedFidelityBenchmarkError("OpenRouter price preflight failed") from None
    if len(response_bytes) > 1024 * 1024:
        raise ManagedFidelityBenchmarkError("OpenRouter price preflight was invalid")
    try:
        payload = json.loads(response_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ManagedFidelityBenchmarkError("OpenRouter price preflight was invalid") from None
    return parse_endpoint_snapshot(candidate_id, payload)


def parse_key_budget_snapshot(
    candidate_id: str,
    payload: object,
) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        raise ManagedFidelityBenchmarkError("OpenRouter key budget response is invalid")
    data = payload["data"]
    limit_value = data.get("limit")
    remaining_value = data.get("limit_remaining")
    if limit_value is None and remaining_value is None:
        raise ManagedFidelityBenchmarkError(
            "OpenRouter key must have a hard spending limit"
        )
    if limit_value is None or remaining_value is None:
        raise ManagedFidelityBenchmarkError("OpenRouter key budget response is invalid")
    limit = _money(limit_value)
    remaining = _money(remaining_value)
    if limit <= 0 or limit > TOTAL_TEST_BUDGET_USD:
        raise ManagedFidelityBenchmarkError(
            "OpenRouter key spending limit exceeds the Task 41 budget"
        )
    required = CANDIDATES[candidate_id]["reservation_cost_usd"]
    if remaining < required:
        raise ManagedFidelityBenchmarkError(
            "OpenRouter key remaining limit is insufficient for this candidate"
        )
    return {
        "hard_limit_usd": _money_text(limit),
        "remaining_before_request_usd": _money_text(remaining),
        "local_budget_only": False,
    }


def fetch_key_budget_snapshot(
    candidate_id: str,
    api_key: str,
) -> dict[str, Any]:
    request = urllib.request.Request(
        OPENROUTER_KEY_ENDPOINT,
        method="GET",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        with _open_pinned_openrouter_request(request, timeout=30) as response:
            response_bytes = response.read(1024 * 1024 + 1)
    except urllib.error.HTTPError as error:
        raise ManagedFidelityBenchmarkError(
            "OpenRouter key budget preflight failed", status_code=error.code
        ) from None
    except (urllib.error.URLError, TimeoutError):
        raise ManagedFidelityBenchmarkError(
            "OpenRouter key budget preflight failed"
        ) from None
    if len(response_bytes) > 1024 * 1024:
        raise ManagedFidelityBenchmarkError("OpenRouter key budget response is invalid")
    try:
        payload = json.loads(response_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ManagedFidelityBenchmarkError(
            "OpenRouter key budget response is invalid"
        ) from None
    return parse_key_budget_snapshot(candidate_id, payload)


def parse_provider_response(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ManagedFidelityBenchmarkError("OpenRouter returned an invalid response")
    data = payload.get("data")
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
        raise ManagedFidelityBenchmarkError("OpenRouter returned an invalid image list")
    encoded = data[0].get("b64_json")
    if not isinstance(encoded, str) or not encoded:
        raise ManagedFidelityBenchmarkError("OpenRouter returned no image bytes")
    max_encoded_length = ((openrouter.MAX_PROVIDER_IMAGE_BYTES + 2) // 3) * 4 + 8
    if len(encoded) > max_encoded_length:
        raise ManagedFidelityBenchmarkError("OpenRouter image exceeds the size limit")
    try:
        provider_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ManagedFidelityBenchmarkError(
            "OpenRouter returned invalid base64 image data"
        ) from error
    _validate_image_bytes(
        provider_bytes,
        max_bytes=openrouter.MAX_PROVIDER_IMAGE_BYTES,
        max_pixels=MAX_SOURCE_IMAGE_PIXELS,
    )

    media_type = data[0].get("media_type")
    if media_type is not None and not isinstance(media_type, str):
        media_type = None
    billed_cost = None
    usage = payload.get("usage")
    if isinstance(usage, dict) and usage.get("cost") is not None:
        try:
            billed_cost = float(_money(usage["cost"]))
        except ManagedFidelityBenchmarkError:
            billed_cost = None
    return {
        "provider_bytes": provider_bytes,
        "media_type": media_type,
        "billed_cost_usd": billed_cost,
    }


def _safe_provider_error(error: urllib.error.HTTPError) -> str | None:
    try:
        response_bytes = error.read(64 * 1024 + 1)
    except OSError:
        return None
    if not response_bytes or len(response_bytes) > 64 * 1024:
        return None
    try:
        payload = json.loads(response_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    details = payload.get("error") if isinstance(payload, dict) else None
    message = details.get("message") if isinstance(details, dict) else None
    if not isinstance(message, str) or not message.strip():
        return None
    sanitized = re.sub(
        r"data:image/[^;\s]+;base64,[A-Za-z0-9+/=]+",
        "[image-data]",
        message,
        flags=re.IGNORECASE,
    )
    sanitized = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "[redacted-key]", sanitized)
    sanitized = " ".join(sanitized.split())
    return sanitized[:500] or None


def _request_image(
    candidate_id: str, source_path: Path, api_key: str
) -> tuple[dict[str, Any], float]:
    body = json.dumps(
        build_request_payload(candidate_id, source_path), separators=(",", ":")
    ).encode("utf-8")
    request = urllib.request.Request(
        openrouter.OPENROUTER_IMAGE_ENDPOINT,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    started = time.perf_counter()
    try:
        with _open_pinned_openrouter_request(request, timeout=600) as response:
            response_bytes = response.read(openrouter.MAX_PROVIDER_IMAGE_BYTES * 2 + 1)
    except urllib.error.HTTPError as error:
        raise ManagedFidelityBenchmarkError(
            "OpenRouter generation failed",
            status_code=error.code,
            provider_error=_safe_provider_error(error),
        ) from None
    except (urllib.error.URLError, TimeoutError):
        raise ManagedFidelityBenchmarkError("OpenRouter generation failed") from None
    if len(response_bytes) > openrouter.MAX_PROVIDER_IMAGE_BYTES * 2:
        raise ManagedFidelityBenchmarkError("OpenRouter generation response is too large")
    elapsed_seconds = time.perf_counter() - started
    try:
        payload = json.loads(response_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ManagedFidelityBenchmarkError("OpenRouter returned invalid JSON") from None
    return parse_provider_response(payload), elapsed_seconds


def run_live_generation(
    candidate_id: str,
    source_path: Path,
    output_path: Path,
    *,
    state_path: Path | None = None,
    authorized_candidates: tuple[str, ...] = TASK41_AUTHORIZED_CANDIDATES,
) -> tuple[
    int,
    float,
    float | None,
    str | None,
    dict[str, Any],
    dict[str, Any],
]:
    ensure_candidate_authorized(
        candidate_id, authorized_candidates=authorized_candidates
    )
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise ManagedFidelityBenchmarkError("OPENROUTER_API_KEY is not configured")
    _validate_source_image(source_path)
    endpoint_snapshot = fetch_endpoint_snapshot(candidate_id)
    key_budget_snapshot = fetch_key_budget_snapshot(candidate_id, api_key)
    attempt_number = reserve_candidate(
        candidate_id,
        state_path,
        authorized_candidates=authorized_candidates,
    )
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    parsed = None
    try:
        parsed, elapsed_seconds = _request_image(candidate_id, source_path, api_key)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_bytes(parsed["provider_bytes"])
        os.replace(temporary_path, output_path)
    except Exception:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            mark_candidate_result(
                candidate_id,
                actual_cost_usd=(
                    parsed["billed_cost_usd"] if parsed is not None else None
                ),
                status="failed",
                state_path=state_path,
            )
        except Exception:
            # Preserve the original provider or filesystem failure. The reserved
            # state remains fail-closed if recording the secondary failure fails.
            pass
        raise
    mark_candidate_result(
        candidate_id,
        actual_cost_usd=parsed["billed_cost_usd"],
        status="completed",
        state_path=state_path,
    )
    return (
        attempt_number,
        elapsed_seconds,
        parsed["billed_cost_usd"],
        parsed["media_type"],
        endpoint_snapshot,
        key_budget_snapshot,
    )


def serialize_report(report: dict[str, Any], *, api_key: str = "") -> str:
    serialized = json.dumps(report, ensure_ascii=True, indent=2)
    if api_key and api_key in serialized:
        raise ManagedFidelityBenchmarkError("API key reached the Task 41 report")
    return serialized


def _safe_candidate_snapshot(candidate_id: str) -> dict[str, Any]:
    candidate = CANDIDATES[candidate_id]
    return {
        "model": candidate["model"],
        "provider": candidate["provider"],
        "listed_cost_usd": _money_text(candidate["listed_cost_usd"]),
        "reservation_cost_usd": _money_text(candidate["reservation_cost_usd"]),
        "request_options": candidate["request_options"],
        "input_mode": candidate["input_mode"],
        "provider_pixel_watermark_policy": "not_documented",
        "pixel_watermark_removal_claim": "not_claimed",
        "sources": candidate["sources"],
        "checked_on": SNAPSHOT_DATE,
    }


def _write_failure(output_dir: Path, candidate_id: str, error: Exception) -> None:
    failure = {
        "schema": 1,
        "analysis_mode": "live_paid",
        "candidate": candidate_id,
        "model": CANDIDATES[candidate_id]["model"],
        "processing_status": "failed",
        "error_type": type(error).__name__,
        "status_code": getattr(error, "status_code", None),
        "provider_error": getattr(error, "provider_error", None),
        "api_key_logged": False,
    }
    common._atomic_json(output_dir / f"failure-{candidate_id}.json", failure)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Task 41 bounded managed image-editing fidelity benchmark"
    )
    parser.add_argument("--photo", type=Path, required=True)
    parser.add_argument("--face", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--candidate", choices=sorted(CANDIDATES), required=True)
    parser.add_argument("--existing-result", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--allow-paid", action="store_true")
    args = parser.parse_args()

    for source in (args.photo, args.face):
        _validate_source_image(source)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    board, fixture = common.build_fixture_board(args.photo, args.face)
    board_path = args.output_dir / "input-board.png"
    board.save(board_path, format="PNG")
    common._atomic_json(args.output_dir / "fixture.json", fixture)
    common._atomic_json(
        args.output_dir / f"candidate-{args.candidate}.json",
        _safe_candidate_snapshot(args.candidate),
    )
    if args.prepare_only:
        print(
            serialize_report(
                {
                    "prepared": str(board_path),
                    "candidate": _safe_candidate_snapshot(args.candidate),
                    "budget": budget_snapshot(),
                    "live_generation_authorized": False,
                }
            )
        )
        return 0

    output_path = args.output_dir / f"output-{args.candidate}.provider"
    attempt_number = None
    elapsed_seconds = None
    billed_cost_usd = None
    media_type = None
    endpoint_snapshot = None
    key_budget_snapshot = None
    if args.existing_result is not None:
        _read_validated_image(
            args.existing_result,
            max_bytes=openrouter.MAX_PROVIDER_IMAGE_BYTES,
            max_pixels=MAX_SOURCE_IMAGE_PIXELS,
        )
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
                endpoint_snapshot,
                key_budget_snapshot,
            ) = run_live_generation(args.candidate, board_path, output_path)
        except Exception as error:
            _write_failure(args.output_dir, args.candidate, error)
            raise

    comparison_path = args.output_dir / f"comparison-{args.candidate}.png"
    metrics = common.analyze_result(board_path, output_path, fixture, comparison_path)
    report = {
        "schema": 1,
        "analysis_mode": analysis_mode,
        "candidate": _safe_candidate_snapshot(args.candidate),
        "generation_attempt": attempt_number,
        "billed_cost_usd_response": (
            round(float(billed_cost_usd), 6) if billed_cost_usd is not None else None
        ),
        "cost_note": "response cost is billing evidence; otherwise the reservation is counted",
        "elapsed_seconds": (
            round(elapsed_seconds, 3) if elapsed_seconds is not None else None
        ),
        "response_media_type": media_type,
        "endpoint_preflight": endpoint_snapshot,
        "key_budget_preflight": key_budget_snapshot,
        "budget": budget_snapshot(),
        "fixture": fixture,
        "metrics": metrics,
        "provider_container": openrouter.inspect_provider_container(output_path),
        "output": str(output_path),
        "api_key_logged": False,
    }
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    serialized = serialize_report(report, api_key=api_key)
    report_path = args.output_dir / f"benchmark-{args.candidate}.json"
    report_path.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
