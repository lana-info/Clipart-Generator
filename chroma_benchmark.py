"""Deterministic quality benchmark for local chroma-key removal."""

from __future__ import annotations

import json
import hashlib
import math
import multiprocessing
import os
import platform
import re
import statistics
import subprocess
import sys
import time
import tracemalloc
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, __version__ as PILLOW_VERSION

from chroma_key import KEY_COLORS


SUPPORTED_CASE_KINDS = {
    "clean_edge",
    "soft_edge",
    "thin_lines",
    "openings",
    "partial_alpha",
    "color_spill",
}
SAFE_CASE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
QUALITY_GATE_KEYS = {
    "minimum_mean_alpha_mae_improvement",
    "minimum_improved_cases",
    "maximum_clean_iou_regression",
    "maximum_opaque_subject_loss_regression",
    "maximum_opaque_rgb_mae_regression",
    "maximum_partial_rgb_mae_regression",
    "maximum_background_leakage_regression",
    "maximum_runtime_multiplier",
    "maximum_runtime_seconds",
    "maximum_peak_memory_mib",
    "maximum_improvement_cycles",
}


class BenchmarkManifestError(ValueError):
    """Raised when a chroma benchmark manifest is incomplete or ambiguous."""


@dataclass(frozen=True)
class BenchmarkFixture:
    case_id: str
    kind: str
    key_color: str
    risk: str
    input_image: Image.Image
    expected_mask: Image.Image
    expected_foreground: Image.Image


def load_manifest(path: str | Path) -> dict[str, Any]:
    """Load and validate a versioned benchmark manifest."""
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BenchmarkManifestError(f"Не удалось прочитать benchmark manifest: {error}") from error
    normalized = validate_manifest(payload)
    golden_relative = Path(str(payload.get("golden_dir", "golden")))
    if golden_relative.is_absolute() or ".." in golden_relative.parts:
        raise BenchmarkManifestError("golden_dir должен находиться рядом с manifest")
    normalized["_golden_dir"] = str(source.parent / golden_relative)
    return normalized


def validate_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a normalized manifest or reject unsafe/ambiguous cases."""
    if payload.get("schema_version") != 1:
        raise BenchmarkManifestError("Поддерживается только schema_version 1")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise BenchmarkManifestError("Benchmark должен содержать непустой список cases")
    normalized_cases: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_case in raw_cases:
        if not isinstance(raw_case, Mapping):
            raise BenchmarkManifestError("Каждый benchmark case должен быть объектом")
        normalized_case = _normalize_case(raw_case)
        case_id = normalized_case["id"]
        if case_id in seen:
            raise BenchmarkManifestError("Benchmark case id должен быть уникальным")
        seen.add(case_id)
        normalized_cases.append(normalized_case)
    raw_gates = payload.get("quality_gates")
    if not isinstance(raw_gates, Mapping):
        raise BenchmarkManifestError("quality_gates должен быть объектом")
    gate_keys = set(raw_gates)
    if gate_keys != QUALITY_GATE_KEYS:
        missing = sorted(QUALITY_GATE_KEYS - gate_keys)
        unknown = sorted(gate_keys - QUALITY_GATE_KEYS)
        raise BenchmarkManifestError(
            f"Некорректные quality_gates; missing={missing}, unknown={unknown}"
        )
    normalized_gates = _validate_quality_gates(raw_gates, len(normalized_cases))
    normalized = dict(payload)
    normalized["cases"] = normalized_cases
    normalized["quality_gates"] = normalized_gates
    normalized["fixture_size"] = _positive_int(payload.get("fixture_size", 256), "fixture_size")
    normalized["performance_size"] = _positive_int(
        payload.get("performance_size", 2048), "performance_size"
    )
    return normalized


def _normalize_case(raw_case: Mapping[str, Any]) -> dict[str, str]:
    case_id = str(raw_case.get("id", "")).strip()
    kind = str(raw_case.get("kind", "")).strip()
    key_color = str(raw_case.get("key_color", "")).strip().casefold()
    risk = str(raw_case.get("risk", "")).strip()
    if not SAFE_CASE_ID.fullmatch(case_id):
        raise BenchmarkManifestError(
            "Benchmark case id должен содержать только a-z, 0-9 и одиночные дефисы"
        )
    if kind not in SUPPORTED_CASE_KINDS:
        raise BenchmarkManifestError(f"Неизвестный benchmark kind: {kind}")
    if key_color not in KEY_COLORS:
        raise BenchmarkManifestError(f"Неизвестный chroma key color: {key_color}")
    if not risk:
        raise BenchmarkManifestError(f"Для case {case_id} не описан expected risk")
    return {"id": case_id, "kind": kind, "key_color": key_color, "risk": risk}


def _validate_quality_gates(
    raw_gates: Mapping[str, Any],
    case_count: int,
) -> dict[str, float | int]:
    gates: dict[str, float | int] = {}
    integer_keys = {"minimum_improved_cases", "maximum_improvement_cycles"}
    for key in QUALITY_GATE_KEYS:
        value = raw_gates[key]
        if key in integer_keys:
            if type(value) is not int or value < 1:
                raise BenchmarkManifestError(f"Quality gate {key} должен быть целым >= 1")
            gates[key] = value
        else:
            if type(value) not in {int, float} or float(value) < 0:
                raise BenchmarkManifestError(f"Quality gate {key} должен быть числом >= 0")
            gates[key] = float(value)
    if int(gates["minimum_improved_cases"]) > case_count:
        raise BenchmarkManifestError("minimum_improved_cases больше числа cases")
    if float(gates["maximum_runtime_multiplier"]) <= 0:
        raise BenchmarkManifestError("maximum_runtime_multiplier должен быть > 0")
    return gates


def _positive_int(value: object, label: str) -> int:
    if type(value) is not int or value < 32:
        raise BenchmarkManifestError(f"{label} должен быть целым числом не меньше 32")
    return value


def generate_fixture(case: Mapping[str, Any], *, size: int) -> BenchmarkFixture:
    """Generate one exact synthetic ground-truth fixture from a manifest case."""
    normalized = _normalize_case(case)
    size = _positive_int(size, "size")
    mask = _mask_for_kind(normalized["kind"], size)
    foreground = _foreground_for_kind(normalized["kind"], size, normalized["key_color"])
    key_rgb = np.asarray(KEY_COLORS[normalized["key_color"]], dtype=np.float32)
    alpha = np.asarray(mask, dtype=np.float32)[..., None] / 255.0
    foreground_array = np.asarray(foreground, dtype=np.float32)
    flattened = np.rint(foreground_array * alpha + key_rgb * (1.0 - alpha)).astype(
        np.uint8
    )
    if normalized["kind"] == "color_spill":
        filter_size = max(3, (size // 16) | 1)
        eroded = np.asarray(mask.filter(ImageFilter.MinFilter(filter_size)), dtype=np.float32)
        edge_band = np.clip((np.asarray(mask, dtype=np.float32) - eroded) / 255.0, 0.0, 1.0)
        spill_strength = (edge_band * 0.35)[..., None]
        flattened = np.rint(
            flattened.astype(np.float32) * (1.0 - spill_strength)
            + key_rgb * spill_strength
        ).astype(np.uint8)
    opaque_alpha = np.full((size, size, 1), 255, dtype=np.uint8)
    input_image = Image.fromarray(
        np.concatenate((flattened, opaque_alpha), axis=2),
        mode="RGBA",
    )
    return BenchmarkFixture(
        case_id=normalized["id"],
        kind=normalized["kind"],
        key_color=normalized["key_color"],
        risk=normalized["risk"],
        input_image=input_image,
        expected_mask=mask,
        expected_foreground=foreground,
    )


def load_golden_fixture(
    manifest: Mapping[str, Any],
    case: Mapping[str, Any],
) -> BenchmarkFixture:
    """Load one immutable golden fixture after verifying every committed hash."""
    normalized = _normalize_case(case)
    golden_dir = Path(str(manifest.get("_golden_dir", "")))
    hashes = manifest.get("golden_sha256", {}).get(normalized["id"], {})
    expected_hash_keys = {"input", "expected_mask", "expected_foreground"}
    if not golden_dir or set(hashes) != expected_hash_keys:
        raise BenchmarkManifestError(f"Для case {normalized['id']} не зафиксированы golden hashes")
    paths = {
        "input": golden_dir / "input" / f"{normalized['id']}.png",
        "expected_mask": golden_dir / "expected-mask" / f"{normalized['id']}.png",
        "expected_foreground": golden_dir
        / "expected-foreground"
        / f"{normalized['id']}.png",
    }
    loaded: dict[str, Image.Image] = {}
    for name, path in paths.items():
        try:
            payload = path.read_bytes()
        except OSError as error:
            raise BenchmarkManifestError(f"Не удалось прочитать golden fixture {path.name}") from error
        if hashlib.sha256(payload).hexdigest() != hashes[name]:
            raise BenchmarkManifestError(f"Golden fixture hash mismatch: {path.name}")
        try:
            with Image.open(path) as image:
                loaded[name] = image.copy()
        except OSError as error:
            raise BenchmarkManifestError(f"Golden fixture не является PNG: {path.name}") from error
    input_image = loaded["input"].convert("RGBA")
    expected_mask = loaded["expected_mask"].convert("L")
    expected_foreground = loaded["expected_foreground"].convert("RGB")
    if not (
        input_image.size == expected_mask.size == expected_foreground.size
        and input_image.size == (int(manifest["fixture_size"]), int(manifest["fixture_size"]))
    ):
        raise BenchmarkManifestError(f"Golden fixture size mismatch: {normalized['id']}")
    return BenchmarkFixture(
        case_id=normalized["id"],
        kind=normalized["kind"],
        key_color=normalized["key_color"],
        risk=normalized["risk"],
        input_image=input_image,
        expected_mask=expected_mask,
        expected_foreground=expected_foreground,
    )


def _mask_for_kind(kind: str, size: int) -> Image.Image:
    if kind == "clean_edge":
        mask = Image.new("L", (size, size), 0)
        inset = max(4, size // 6)
        ImageDraw.Draw(mask).rounded_rectangle(
            (inset, inset, size - inset - 1, size - inset - 1),
            radius=max(2, size // 12),
            fill=255,
        )
        return mask

    scale = 4
    large = Image.new("L", (size * scale, size * scale), 0)
    draw = ImageDraw.Draw(large)
    center = size * scale // 2
    if kind in {"soft_edge", "color_spill"}:
        inset = size * scale // 7
        draw.ellipse((inset, inset, size * scale - inset, size * scale - inset), fill=255)
        if kind == "soft_edge":
            large = large.filter(ImageFilter.GaussianBlur(max(2, size * scale // 40)))
    elif kind == "thin_lines":
        width = max(3, scale * 2)
        draw.line((center, size * scale - scale * 8, center, scale * 12), fill=255, width=width)
        for offset in (-1, 1):
            draw.line(
                (
                    center,
                    center,
                    center + offset * size * scale // 3,
                    scale * 12,
                ),
                fill=255,
                width=width,
            )
            draw.line(
                (
                    center,
                    center + scale * 10,
                    center + offset * size * scale // 3,
                    size * scale - scale * 14,
                ),
                fill=255,
                width=width,
            )
    elif kind == "openings":
        inset = size * scale // 10
        draw.ellipse((inset, inset, size * scale - inset, size * scale - inset), fill=255)
        hole_radius = size * scale // 8
        for x, y in (
            (center, center),
            (center - hole_radius * 2, center),
            (center + hole_radius * 2, center),
        ):
            draw.ellipse(
                (x - hole_radius, y - hole_radius, x + hole_radius, y + hole_radius),
                fill=0,
            )
    elif kind == "partial_alpha":
        radius = size * scale // 3
        draw.ellipse(
            (center - radius, center - radius, center + radius, center + radius),
            fill=128,
        )
        inner = radius // 2
        draw.ellipse(
            (center - inner, center - inner, center + inner, center + inner),
            fill=220,
        )
    else:  # validated before this point
        raise BenchmarkManifestError(f"Неизвестный benchmark kind: {kind}")
    return large.resize((size, size), Image.Resampling.LANCZOS)


def _foreground_for_kind(kind: str, size: int, key_color: str) -> Image.Image:
    palettes = {
        "blue": ((238, 150, 60), (245, 228, 170)),
        "green": ((182, 74, 210), (250, 190, 225)),
        "red": ((45, 155, 220), (190, 235, 250)),
    }
    first, second = palettes[key_color]
    array = np.empty((size, size, 3), dtype=np.uint8)
    for y in range(size):
        blend = y / max(1, size - 1)
        color = tuple(round(a * (1 - blend) + b * blend) for a, b in zip(first, second))
        array[y, :, :] = color
    stripe = max(3, size // 16)
    array[:, :: stripe, :] = np.clip(array[:, :: stripe, :].astype(int) + 12, 0, 255)
    return Image.fromarray(array, mode="RGB")


def score_result(
    result: Image.Image,
    expected_mask: Image.Image,
    expected_foreground: Image.Image,
) -> dict[str, float]:
    """Measure alpha accuracy and RGB damage against independent ground truth."""
    if result.size != expected_mask.size or result.size != expected_foreground.size:
        raise ValueError("Размер результата не совпадает с benchmark fixture")
    result_array = np.asarray(result.convert("RGBA"), dtype=np.float32)
    expected_alpha = np.asarray(expected_mask.convert("L"), dtype=np.float32) / 255.0
    predicted_alpha = result_array[..., 3] / 255.0
    alpha_mae = float(np.mean(np.abs(predicted_alpha - expected_alpha)))
    expected_binary = expected_alpha >= 0.5
    predicted_binary = predicted_alpha >= 0.5
    union = int(np.count_nonzero(expected_binary | predicted_binary))
    intersection = int(np.count_nonzero(expected_binary & predicted_binary))
    alpha_iou = 1.0 if union == 0 else intersection / union

    expected_rgb = np.asarray(expected_foreground.convert("RGB"), dtype=np.float32)
    result_rgb = result_array[..., :3]
    opaque = expected_alpha >= 0.98
    partial = (expected_alpha > 0.0) & (expected_alpha < 0.98)
    background = expected_alpha == 0.0
    return {
        "alpha_mae": alpha_mae,
        "alpha_iou": float(alpha_iou),
        "opaque_rgb_mae": _masked_rgb_mae(result_rgb, expected_rgb, opaque),
        "partial_rgb_mae": _masked_rgb_mae(result_rgb, expected_rgb, partial),
        "background_leakage": _masked_mean(predicted_alpha, background),
        "opaque_subject_loss": _masked_mean(1.0 - predicted_alpha, opaque),
    }


def _masked_rgb_mae(actual: np.ndarray, expected: np.ndarray, mask: np.ndarray) -> float:
    if not np.any(mask):
        return 0.0
    return float(np.mean(np.abs(actual[mask] - expected[mask])) / 255.0)


def _masked_mean(values: np.ndarray, mask: np.ndarray) -> float:
    if not np.any(mask):
        return 0.0
    return float(np.mean(values[mask]))


def run_benchmark(
    manifest: Mapping[str, Any] | str | Path,
    algorithm: Callable[[Image.Image, str], Image.Image],
    output_dir: str | Path,
    *,
    algorithm_name: str,
) -> dict[str, Any]:
    """Run all deterministic cases and write metrics plus a visual contact sheet."""
    normalized = (
        load_manifest(manifest)
        if isinstance(manifest, (str, Path))
        else validate_manifest(manifest)
    )
    destination = Path(output_dir)
    input_dir = destination / "fixtures" / "input"
    mask_dir = destination / "fixtures" / "expected-mask"
    foreground_dir = destination / "fixtures" / "expected-foreground"
    for directory in (input_dir, mask_dir, foreground_dir):
        directory.mkdir(parents=True, exist_ok=True)

    case_reports: list[dict[str, Any]] = []
    contact_rows: list[tuple[BenchmarkFixture, Image.Image]] = []
    for case in normalized["cases"]:
        fixture = (
            load_golden_fixture(normalized, case)
            if normalized.get("_golden_dir") and normalized.get("golden_sha256")
            else generate_fixture(case, size=normalized["fixture_size"])
        )
        fixture.input_image.save(input_dir / f"{fixture.case_id}.png")
        fixture.expected_mask.save(mask_dir / f"{fixture.case_id}.png")
        fixture.expected_foreground.save(foreground_dir / f"{fixture.case_id}.png")
        result = algorithm(fixture.input_image.copy(), fixture.key_color)
        if not isinstance(result, Image.Image):
            raise TypeError("Chroma algorithm должен вернуть PIL.Image")
        result = result.convert("RGBA")
        metrics = score_result(result, fixture.expected_mask, fixture.expected_foreground)
        case_reports.append(
            {
                "id": fixture.case_id,
                "kind": fixture.kind,
                "key_color": fixture.key_color,
                "risk": fixture.risk,
                **metrics,
            }
        )
        contact_rows.append((fixture, result))

    performance_case = generate_fixture(
        normalized["cases"][-1],
        size=normalized["performance_size"],
    )
    performance = _measure_performance_isolated(
        algorithm,
        performance_case,
        warmup_count=1,
        sample_count=3,
        timeout_seconds=180,
    )
    summary_keys = (
        "alpha_mae",
        "alpha_iou",
        "opaque_rgb_mae",
        "partial_rgb_mae",
        "background_leakage",
        "opaque_subject_loss",
    )
    report: dict[str, Any] = {
        "schema_version": 1,
        "algorithm": algorithm_name,
        "fixture_size": normalized["fixture_size"],
        "environment": _environment_metadata(),
        "summary": {
            key: float(np.mean([case[key] for case in case_reports]))
            for key in summary_keys
        },
        "performance": {
            "size": normalized["performance_size"],
            **performance,
        },
        "quality_gates": normalized.get("quality_gates", {}),
        "cases": case_reports,
    }
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "baseline_metrics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _build_contact_sheet(contact_rows).save(destination / "baseline-contact-sheet.png")
    return report


REPORT_SUMMARY_KEYS = (
    "alpha_mae",
    "alpha_iou",
    "opaque_rgb_mae",
    "partial_rgb_mae",
    "background_leakage",
    "opaque_subject_loss",
)


def _validated_report_cases(
    report: Mapping[str, Any],
    *,
    label: str,
) -> dict[str, Mapping[str, Any]]:
    """Validate one persisted report before it participates in a comparison."""
    if report.get("schema_version") != 1:
        raise BenchmarkManifestError(f"{label}: поддерживается только schema_version 1")
    for size_key in ("fixture_size",):
        value = report.get(size_key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise BenchmarkManifestError(f"{label}: {size_key} должен быть положительным целым")

    performance = report.get("performance")
    if not isinstance(performance, Mapping):
        raise BenchmarkManifestError(f"{label}: отсутствует performance")
    performance_size = performance.get("size")
    if (
        isinstance(performance_size, bool)
        or not isinstance(performance_size, int)
        or performance_size <= 0
    ):
        raise BenchmarkManifestError(
            f"{label}: performance.size должен быть положительным целым"
        )
    for key in ("elapsed_seconds", "peak_memory_mib"):
        try:
            value = float(performance[key])
        except (KeyError, TypeError, ValueError) as error:
            raise BenchmarkManifestError(f"{label}: некорректный performance.{key}") from error
        if not math.isfinite(value) or value <= 0:
            raise BenchmarkManifestError(f"{label}: некорректный performance.{key}")

    raw_cases = report.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise BenchmarkManifestError(f"{label}: отсутствуют benchmark cases")
    cases: dict[str, Mapping[str, Any]] = {}
    for raw_case in raw_cases:
        if not isinstance(raw_case, Mapping):
            raise BenchmarkManifestError(f"{label}: benchmark case должен быть объектом")
        case_id = raw_case.get("id")
        kind = raw_case.get("kind")
        key_color = raw_case.get("key_color")
        if not isinstance(case_id, str) or not SAFE_CASE_ID.fullmatch(case_id):
            raise BenchmarkManifestError(f"{label}: некорректный benchmark case id")
        if case_id in cases:
            raise BenchmarkManifestError(f"{label}: benchmark case id должен быть уникальным")
        if kind not in SUPPORTED_CASE_KINDS:
            raise BenchmarkManifestError(f"{label}: неизвестный benchmark case kind")
        if key_color not in KEY_COLORS:
            raise BenchmarkManifestError(f"{label}: неизвестный benchmark key_color")
        for metric_key in REPORT_SUMMARY_KEYS:
            try:
                metric_value = float(raw_case[metric_key])
            except (KeyError, TypeError, ValueError) as error:
                raise BenchmarkManifestError(
                    f"{label}: некорректная метрика {metric_key} в case {case_id}"
                ) from error
            if not math.isfinite(metric_value) or not 0.0 <= metric_value <= 1.0:
                raise BenchmarkManifestError(
                    f"{label}: некорректная метрика {metric_key} в case {case_id}"
                )
        cases[case_id] = raw_case

    summary = report.get("summary")
    if not isinstance(summary, Mapping):
        raise BenchmarkManifestError(f"{label}: отсутствует summary")
    for metric_key in REPORT_SUMMARY_KEYS:
        expected = statistics.fmean(float(case[metric_key]) for case in cases.values())
        try:
            actual = float(summary[metric_key])
        except (KeyError, TypeError, ValueError) as error:
            raise BenchmarkManifestError(
                f"{label}: некорректная сводная метрика {metric_key}"
            ) from error
        if not math.isfinite(actual) or not math.isclose(
            actual,
            expected,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise BenchmarkManifestError(
                f"{label}: сводная метрика {metric_key} не совпадает с cases"
            )
    return cases


def evaluate_candidate(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    gates: Mapping[str, Any],
    *,
    cycle_number: int,
) -> dict[str, Any]:
    """Apply the manifest's objective continue/stop gates to one candidate."""
    baseline_cases = _validated_report_cases(baseline, label="Baseline")
    candidate_cases = _validated_report_cases(candidate, label="Candidate")
    if baseline.get("fixture_size") != candidate.get("fixture_size"):
        raise BenchmarkManifestError(
            "Baseline и candidate должны использовать одинаковый fixture_size"
        )
    if baseline["performance"]["size"] != candidate["performance"]["size"]:
        raise BenchmarkManifestError(
            "Baseline и candidate должны использовать одинаковый performance.size"
        )
    if baseline_cases.keys() != candidate_cases.keys():
        raise BenchmarkManifestError(
            "Baseline и candidate должны содержать одинаковые benchmark cases"
        )
    for case_id, baseline_case in baseline_cases.items():
        candidate_case = candidate_cases[case_id]
        if (
            baseline_case["kind"] != candidate_case["kind"]
            or baseline_case["key_color"] != candidate_case["key_color"]
        ):
            raise BenchmarkManifestError(
                "Baseline и candidate должны сравнивать одинаковые kind и key_color"
            )
    baseline_mae = float(baseline["summary"]["alpha_mae"])
    candidate_mae = float(candidate["summary"]["alpha_mae"])
    mae_improvement = (
        (baseline_mae - candidate_mae) / baseline_mae
        if baseline_mae > 0
        else 0.0
    )
    improved_cases = sum(
        float(candidate_cases[case_id]["alpha_mae"])
        < float(baseline_case["alpha_mae"])
        for case_id, baseline_case in baseline_cases.items()
    )
    clean_iou_regression = max(
        (
            float(baseline_case["alpha_iou"])
            - float(candidate_cases[case_id]["alpha_iou"])
            for case_id, baseline_case in baseline_cases.items()
            if baseline_case.get("kind") == "clean_edge"
        ),
        default=0.0,
    )
    subject_loss_regression = (
        float(candidate["summary"]["opaque_subject_loss"])
        - float(baseline["summary"]["opaque_subject_loss"])
    )
    opaque_rgb_regression = (
        float(candidate["summary"]["opaque_rgb_mae"])
        - float(baseline["summary"]["opaque_rgb_mae"])
    )
    partial_rgb_regression = (
        float(candidate["summary"]["partial_rgb_mae"])
        - float(baseline["summary"]["partial_rgb_mae"])
    )
    background_leakage_regression = (
        float(candidate["summary"]["background_leakage"])
        - float(baseline["summary"]["background_leakage"])
    )
    baseline_seconds = float(baseline["performance"]["elapsed_seconds"])
    candidate_seconds = float(candidate["performance"]["elapsed_seconds"])
    runtime_multiplier = (
        candidate_seconds / baseline_seconds if baseline_seconds > 0 else float("inf")
    )
    peak_memory = float(candidate["performance"]["peak_memory_mib"])

    def check(actual: float | int, limit: float | int, passed: bool) -> dict[str, Any]:
        return {"actual": actual, "limit": limit, "passed": bool(passed)}

    checks = {
        "mean_alpha_mae_improvement": check(
            mae_improvement,
            float(gates["minimum_mean_alpha_mae_improvement"]),
            mae_improvement >= float(gates["minimum_mean_alpha_mae_improvement"]),
        ),
        "improved_cases": check(
            improved_cases,
            int(gates["minimum_improved_cases"]),
            improved_cases >= int(gates["minimum_improved_cases"]),
        ),
        "clean_iou_regression": check(
            clean_iou_regression,
            float(gates["maximum_clean_iou_regression"]),
            clean_iou_regression <= float(gates["maximum_clean_iou_regression"]),
        ),
        "opaque_subject_loss_regression": check(
            subject_loss_regression,
            float(gates["maximum_opaque_subject_loss_regression"]),
            subject_loss_regression
            <= float(gates["maximum_opaque_subject_loss_regression"]),
        ),
        "opaque_rgb_mae_regression": check(
            opaque_rgb_regression,
            float(gates["maximum_opaque_rgb_mae_regression"]),
            opaque_rgb_regression <= float(gates["maximum_opaque_rgb_mae_regression"]),
        ),
        "partial_rgb_mae_regression": check(
            partial_rgb_regression,
            float(gates["maximum_partial_rgb_mae_regression"]),
            partial_rgb_regression <= float(gates["maximum_partial_rgb_mae_regression"]),
        ),
        "background_leakage_regression": check(
            background_leakage_regression,
            float(gates["maximum_background_leakage_regression"]),
            background_leakage_regression
            <= float(gates["maximum_background_leakage_regression"]),
        ),
        "runtime_multiplier": check(
            runtime_multiplier,
            float(gates["maximum_runtime_multiplier"]),
            runtime_multiplier <= float(gates["maximum_runtime_multiplier"]),
        ),
        "runtime_absolute": check(
            candidate_seconds,
            float(gates["maximum_runtime_seconds"]),
            candidate_seconds <= float(gates["maximum_runtime_seconds"]),
        ),
        "peak_memory": check(
            peak_memory,
            float(gates["maximum_peak_memory_mib"]),
            peak_memory <= float(gates["maximum_peak_memory_mib"]),
        ),
        "cycle_limit": check(
            cycle_number,
            int(gates["maximum_improvement_cycles"]),
            1 <= cycle_number <= int(gates["maximum_improvement_cycles"]),
        ),
    }
    return {
        "continue": all(item["passed"] for item in checks.values()),
        "cycle_number": cycle_number,
        "checks": checks,
    }


def _measure_performance_isolated(
    algorithm: Callable[[Image.Image, str], Image.Image],
    fixture: BenchmarkFixture,
    *,
    warmup_count: int,
    sample_count: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(
        target=_performance_worker,
        args=(child, algorithm, fixture, warmup_count, sample_count),
    )
    process.start()
    child.close()
    if not parent.poll(timeout_seconds):
        process.terminate()
        process.join(timeout=5)
        raise TimeoutError("Chroma performance benchmark превысил лимит времени")
    payload = parent.recv()
    process.join(timeout=5)
    if process.is_alive():
        process.terminate()
        process.join(timeout=5)
    if process.exitcode != 0 or "error" in payload:
        raise RuntimeError(payload.get("error", "Chroma performance worker завершился с ошибкой"))
    samples = [float(value) for value in payload["elapsed_samples_seconds"]]
    return {
        "elapsed_seconds": round(statistics.median(samples), 6),
        "elapsed_samples_seconds": samples,
        "sample_count": sample_count,
        "warmup_count": warmup_count,
        "peak_memory_mib": float(payload["peak_memory_mib"]),
        "memory_measurement": str(payload["memory_measurement"]),
    }


def _performance_worker(
    connection,
    algorithm: Callable[[Image.Image, str], Image.Image],
    fixture: BenchmarkFixture,
    warmup_count: int,
    sample_count: int,
) -> None:
    native_memory = _native_peak_memory_mib()
    tracing = native_memory is None
    if tracing:
        tracemalloc.start()
    try:
        for _ in range(warmup_count):
            result = algorithm(fixture.input_image.copy(), fixture.key_color)
            if not isinstance(result, Image.Image):
                raise TypeError("Chroma algorithm должен вернуть PIL.Image")
        samples: list[float] = []
        for _ in range(sample_count):
            started = time.perf_counter()
            result = algorithm(fixture.input_image.copy(), fixture.key_color)
            samples.append(round(time.perf_counter() - started, 6))
            if not isinstance(result, Image.Image):
                raise TypeError("Chroma algorithm должен вернуть PIL.Image")
        native_memory = _native_peak_memory_mib()
        if native_memory is not None:
            memory_mib, method = native_memory
        else:
            _, peak = tracemalloc.get_traced_memory()
            memory_mib = peak / (1024 * 1024)
            method = "isolated_python_tracemalloc_fallback"
        connection.send(
            {
                "elapsed_samples_seconds": samples,
                "peak_memory_mib": round(memory_mib, 3),
                "memory_measurement": method,
            }
        )
    except Exception as error:
        connection.send({"error": f"{type(error).__name__}: {error}"})
    finally:
        if tracing:
            tracemalloc.stop()
        connection.close()


def _native_peak_memory_mib() -> tuple[float, str] | None:
    try:
        import resource

        peak = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        peak_mib = peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024
        return peak_mib, "isolated_process_peak_rss"
    except (ImportError, AttributeError):
        pass
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        process = ctypes.windll.kernel32.GetCurrentProcess()
        if not ctypes.windll.psapi.GetProcessMemoryInfo(
            process,
            ctypes.byref(counters),
            counters.cb,
        ):
            return None
        return (
            counters.PeakWorkingSetSize / (1024 * 1024),
            "isolated_windows_peak_working_set",
        )
    except (AttributeError, OSError):
        return None


def _environment_metadata() -> dict[str, Any]:
    commit = "unknown"
    dirty: bool | None = None
    try:
        completed = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        commit = completed.stdout.strip()
        dirty_check = subprocess.run(
            ("git", "status", "--porcelain", "--untracked-files=normal"),
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        dirty = bool(dirty_check.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "pillow": PILLOW_VERSION,
        "numpy": np.__version__,
        "git_commit": commit,
        "git_dirty": dirty,
    }


def _build_contact_sheet(rows: list[tuple[BenchmarkFixture, Image.Image]]) -> Image.Image:
    if not rows:
        raise ValueError("Для contact sheet нужен хотя бы один case")
    tile_size = rows[0][0].input_image.width
    label_height = 22
    columns = 6
    sheet = Image.new(
        "RGB",
        (tile_size * columns, (tile_size + label_height) * len(rows)),
        "white",
    )
    labels = ("input", "expected", "checker", "black", "white", "magenta")
    draw = ImageDraw.Draw(sheet)
    for row_index, (fixture, result) in enumerate(rows):
        expected = fixture.expected_foreground.convert("RGBA")
        expected.putalpha(fixture.expected_mask)
        tiles = (
            fixture.input_image.convert("RGB"),
            _composite(expected, "checker"),
            _composite(result, "checker"),
            _composite(result, "black"),
            _composite(result, "white"),
            _composite(result, "magenta"),
        )
        y = row_index * (tile_size + label_height)
        for column, (label, tile) in enumerate(zip(labels, tiles)):
            x = column * tile_size
            display_label = f"{fixture.case_id}: {label}" if column == 0 else label
            draw.text((x + 4, y + 4), display_label, fill="black")
            sheet.paste(tile, (x, y + label_height))
    return sheet


def _composite(image: Image.Image, background: str) -> Image.Image:
    rgba = image.convert("RGBA")
    if background == "checker":
        tile = max(4, rgba.width // 16)
        canvas = Image.new("RGB", rgba.size, "#eef1f4")
        draw = ImageDraw.Draw(canvas)
        for y in range(0, rgba.height, tile):
            for x in range(0, rgba.width, tile):
                if (x // tile + y // tile) % 2 == 0:
                    draw.rectangle((x, y, x + tile - 1, y + tile - 1), fill="#c8ced4")
    else:
        colors = {"black": "#080b10", "white": "#ffffff", "magenta": "#ff1493"}
        canvas = Image.new("RGB", rgba.size, colors[background])
    canvas.paste(rgba, mask=rgba.getchannel("A"))
    return canvas


__all__ = [
    "BenchmarkFixture",
    "BenchmarkManifestError",
    "evaluate_candidate",
    "generate_fixture",
    "load_manifest",
    "run_benchmark",
    "score_result",
    "validate_manifest",
]
