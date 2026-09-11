"""Reference-only quality measurements; never used to infer live-image truth.

Errors use normalized 0..1 units. ROI counts accompany every statistic so an
empty region cannot masquerade as evidence of quality. This is offline QA.

The geometry helpers below compare a result with known RGBA truth.  They do not
infer a mask, decide that an image is production-ready, or certify AA width on
an arbitrary image.  In particular, ``measure_alpha_profile`` only measures a
caller-supplied, explicit normal profile.
"""
from __future__ import annotations

from collections.abc import Iterable
from itertools import islice

import cv2
import numpy as np
from PIL import Image


_DEFAULT_MAX_PIXELS = 16_000_000
_DEFAULT_SUPPORT_ALPHA = 1 / 255
_DEFAULT_MAX_REGIONS = 100_000
_DEFAULT_MAX_PROFILE_SAMPLES = 4_096


def _stats(values: np.ndarray) -> dict:
    """Return null-valued stats when there is no measurement evidence."""
    values = np.asarray(values, dtype=np.float64)
    return {
        "count": int(values.size),
        "mean": float(values.mean()) if values.size else None,
        "p95": float(np.percentile(values, 95)) if values.size else None,
        "max": float(values.max()) if values.size else None,
    }


def _validate_pair(result: Image.Image, truth: Image.Image, max_pixels: int) -> None:
    if result.size != truth.size or not all(result.size):
        raise ValueError("Quality comparison requires equal nonempty dimensions")
    if not isinstance(max_pixels, int) or max_pixels <= 0:
        raise ValueError("max_pixels must be a positive integer")
    if result.size[0] * result.size[1] > max_pixels:
        raise ValueError("Quality comparison exceeds max_pixels")


def _validate_positive_int(value: int, name: str) -> None:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _support_mask(image: Image.Image, threshold: float) -> np.ndarray:
    alpha = np.asarray(image.convert("RGBA"), dtype=np.uint8)[..., 3]
    # ``>= 1/255`` deliberately preserves the least-visible valid 8-bit cover.
    return alpha >= int(np.ceil(threshold * 255))


def _components(mask: np.ndarray, connectivity: int,
                max_regions: int) -> tuple[np.ndarray, int, np.ndarray]:
    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        np.ascontiguousarray(mask, dtype=np.uint8), connectivity=connectivity
    )
    # OpenCV reserves label zero for the background. Reject before materializing
    # Python region records or overlap sets for pathological masks.
    component_count = int(count - 1)
    if component_count > max_regions:
        raise ValueError("Component count exceeds max_regions")
    return labels, component_count, stats[1:, cv2.CC_STAT_AREA].astype(np.int64, copy=False)


def _holes(foreground: np.ndarray, max_regions: int) -> tuple[np.ndarray, int, np.ndarray]:
    """Label holes using the 4-connected dual of 8-connected foreground."""
    padded_background = np.pad(~foreground, 1, constant_values=True)
    count, padded_labels, stats, _centroids = cv2.connectedComponentsWithStats(
        np.ascontiguousarray(padded_background, dtype=np.uint8), connectivity=4
    )
    exterior_label = int(padded_labels[0, 0])
    hole_count = int(count - 2)  # label 0 is foreground; one label is exterior.
    if hole_count > max_regions:
        raise ValueError("Hole count exceeds max_regions")

    # Relabel every pixel once through a lookup table. The old implementation
    # performed a full-image equality comparison once per hole.
    old_labels = np.arange(1, count, dtype=np.int32)
    old_labels = old_labels[old_labels != exterior_label]
    lookup = np.zeros(count, dtype=np.int32)
    lookup[old_labels] = np.arange(1, hole_count + 1, dtype=np.int32)
    hole_labels = lookup[padded_labels[1:-1, 1:-1]]
    areas = stats[old_labels, cv2.CC_STAT_AREA].astype(np.int64, copy=False)
    return hole_labels, hole_count, areas


def _boundary(mask: np.ndarray) -> np.ndarray:
    if not mask.any():
        return np.zeros_like(mask, dtype=bool)
    eroded = cv2.erode(
        np.ascontiguousarray(mask, dtype=np.uint8),
        np.ones((3, 3), dtype=np.uint8),
        borderType=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    return mask & ~eroded.astype(bool)


def _boundary_distances(source: np.ndarray, target: np.ndarray) -> dict:
    """Distance from source boundary pixels to target using precise L2 CV2 DT."""
    if not source.any() or not target.any():
        return {"evidence": False, "pixels": _stats(np.empty(0, dtype=np.float64))}
    # DIST_MASK_PRECISE selects OpenCV's exact L2 transform, rather than a
    # chamfer approximation. Zeros are the target boundary.
    distance_input = np.ones(target.shape, dtype=np.uint8)
    distance_input[target] = 0
    distances = cv2.distanceTransform(distance_input, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    return {"evidence": True, "pixels": _stats(distances[source])}


def _overlap_matches(reference_labels: np.ndarray, actual_labels: np.ndarray,
                     reference_count: int, actual_count: int) -> dict:
    """Match labelled regions by direct support overlap, never by count alone."""
    reference_to_actual = [set() for _ in range(reference_count + 1)]
    actual_to_reference = [set() for _ in range(actual_count + 1)]
    both = (reference_labels > 0) & (actual_labels > 0)
    if both.any():
        pairs = np.unique(
            np.stack((reference_labels[both], actual_labels[both]), axis=1), axis=0
        )
        for reference_label, actual_label in pairs:
            reference_to_actual[int(reference_label)].add(int(actual_label))
            actual_to_reference[int(actual_label)].add(int(reference_label))

    lost_reference = [label for label in range(1, reference_count + 1)
                      if not reference_to_actual[label]]
    unmatched_actual = [label for label in range(1, actual_count + 1)
                        if not actual_to_reference[label]]
    split_reference = [label for label in range(1, reference_count + 1)
                       if len(reference_to_actual[label]) > 1]
    merged_actual = [label for label in range(1, actual_count + 1)
                     if len(actual_to_reference[label]) > 1]
    return {
        "method": "direct_support_overlap",
        "lost_reference_labels": lost_reference,
        "lost_reference_count": len(lost_reference),
        "unmatched_actual_labels": unmatched_actual,
        "unmatched_actual_count": len(unmatched_actual),
        "split_reference_labels": split_reference,
        "split_reference_count": len(split_reference),
        "merged_actual_labels": merged_actual,
        "merged_actual_count": len(merged_actual),
    }


def _support_overlap(reference: np.ndarray, actual: np.ndarray) -> dict:
    intersection = int(np.count_nonzero(reference & actual))
    reference_pixels = int(np.count_nonzero(reference))
    actual_pixels = int(np.count_nonzero(actual))
    union = reference_pixels + actual_pixels - intersection
    return {
        "intersection_pixels": intersection,
        "reference_pixels": reference_pixels,
        "actual_pixels": actual_pixels,
        "reference_recall": intersection / reference_pixels if reference_pixels else None,
        "actual_precision": intersection / actual_pixels if actual_pixels else None,
        "iou": intersection / union if union else None,
    }


def reference_quality(result: Image.Image, truth: Image.Image) -> dict:
    if result.size != truth.size or not all(result.size):
        raise ValueError("Quality comparison requires equal nonempty dimensions")
    actual = np.asarray(result.convert("RGBA"), dtype=np.float32) / 255.0
    expected = np.asarray(truth.convert("RGBA"), dtype=np.float32) / 255.0
    alpha = expected[..., 3]
    regions = {
        "opaque": alpha == 1,
        "partial": (alpha > 0) & (alpha < 1),
        "background": alpha == 0,
    }
    alpha_error = np.abs(actual[..., 3] - alpha)
    rgb_error = np.max(np.abs(actual[..., :3] - expected[..., :3]), axis=2)

    def stats(values, mask):
        selected = values[mask]
        return {
            "count": int(selected.size),
            "mean": float(selected.mean()) if selected.size else None,
            "p95": float(np.percentile(selected, 95)) if selected.size else None,
            "max": float(selected.max()) if selected.size else None,
        }

    report = {"schema_version": 1, "units": "normalized_0_1", "regions": {}}
    for name, mask in regions.items():
        record = {"alpha": stats(alpha_error, mask)}
        # RGB under fully transparent truth is not a defined visible target.
        if name != "background":
            record["rgb_max_channel"] = stats(rgb_error, mask)
        report["regions"][name] = record
    report["composites"] = {}
    for name, background in (("black", (0, 0, 0)), ("white", (1, 1, 1)),
                             ("magenta", (1, 0, 1))):
        bg = np.asarray(background, dtype=np.float32)
        got = actual[..., :3] * actual[..., 3:] + bg * (1 - actual[..., 3:])
        want = expected[..., :3] * expected[..., 3:] + bg * (1 - expected[..., 3:])
        error = np.max(np.abs(got - want), axis=2)
        report["composites"][name] = {
            region: stats(error, mask) for region, mask in regions.items()
        }
    return report


def geometry_topology_quality(
    result: Image.Image,
    truth: Image.Image,
    *,
    support_alpha: float = _DEFAULT_SUPPORT_ALPHA,
    max_pixels: int = _DEFAULT_MAX_PIXELS,
    max_regions: int = _DEFAULT_MAX_REGIONS,
) -> dict:
    """Compare reference alpha support, topology, and boundary displacement.

    A pixel is supporting foreground at ``support_alpha`` or above. The default
    is one 8-bit alpha unit, so a valid low-alpha branch remains evidence rather
    than being silently classified as absent.  Components are 8-connected and
    holes use the 4-connected dual background. Matching is based on direct
    support overlap, while boundary distance is separately reported in both
    directions using OpenCV's precise Euclidean distance transform.

    ``max_regions`` bounds component/hole report records before overlap
    bookkeeping. This bounded offline diagnostic is not a release gate and has
    no claim about genuine images without a supplied reference RGBA truth image.
    """
    _validate_pair(result, truth, max_pixels)
    _validate_positive_int(max_regions, "max_regions")
    if not np.isfinite(support_alpha) or not 0 < support_alpha <= 1:
        raise ValueError("support_alpha must be in (0, 1]")

    reference_support = _support_mask(truth, float(support_alpha))
    actual_support = _support_mask(result, float(support_alpha))
    reference_components, reference_component_count, reference_component_areas = _components(
        reference_support, connectivity=8, max_regions=max_regions
    )
    actual_components, actual_component_count, actual_component_areas = _components(
        actual_support, connectivity=8, max_regions=max_regions
    )
    reference_holes, reference_hole_count, reference_hole_areas = _holes(
        reference_support, max_regions=max_regions
    )
    actual_holes, actual_hole_count, actual_hole_areas = _holes(
        actual_support, max_regions=max_regions
    )
    reference_boundary = _boundary(reference_support)
    actual_boundary = _boundary(actual_support)

    return {
        "schema_version": 1,
        "units": {"alpha": "normalized_0_1", "boundary_distance": "pixels"},
        "reference_only": True,
        "support_alpha": float(support_alpha),
        "limits": {"max_pixels": max_pixels, "max_regions": max_regions},
        "connectivity": {"foreground_components": 8, "background_holes": 4},
        "support": _support_overlap(reference_support, actual_support),
        "components": {
            "reference": {
                "count": reference_component_count,
                "areas_pixels": reference_component_areas.tolist(),
            },
            "actual": {
                "count": actual_component_count,
                "areas_pixels": actual_component_areas.tolist(),
            },
            "overlap": _overlap_matches(
                reference_components, actual_components,
                reference_component_count, actual_component_count,
            ),
        },
        "holes": {
            "reference": {
                "count": reference_hole_count,
                "areas_pixels": reference_hole_areas.tolist(),
            },
            "actual": {
                "count": actual_hole_count,
                "areas_pixels": actual_hole_areas.tolist(),
            },
            "overlap": _overlap_matches(
                reference_holes, actual_holes,
                reference_hole_count, actual_hole_count,
            ),
        },
        "boundary_distance": {
            "method": "cv2.DIST_L2/DIST_MASK_PRECISE",
            "reference_to_actual": _boundary_distances(reference_boundary, actual_boundary),
            "actual_to_reference": _boundary_distances(actual_boundary, reference_boundary),
        },
    }


def measure_alpha_profile(
    samples: Iterable[float], spacing: float = 1.0, *,
    max_samples: int = _DEFAULT_MAX_PROFILE_SAMPLES,
) -> dict:
    """Measure 5%-to-95% width along one explicit, caller-selected normal.

    ``samples`` must be in their spatial order on one normal profile; the
    function deliberately does not derive normals from a whole image. A single
    monotonic transition is required. Reversed profiles are valid and reported
    as ``decreasing``. A non-monotonic profile is ambiguous, not a width.
    Missing threshold crossings are reported as no evidence. ``max_samples``
    bounds even generator input. Neither outcome is an AA certification for the
    full contour.
    """
    _validate_positive_int(max_samples, "max_samples")
    # islice bounds work for lists, generators, and even accidentally infinite
    # iterators; no full iterable is materialized before the limit is checked.
    sample_list = list(islice(samples, max_samples + 1))
    if len(sample_list) > max_samples:
        raise ValueError("Profile sample count exceeds max_samples")
    values = np.asarray(sample_list, dtype=np.float64)
    if values.ndim != 1:
        raise ValueError("samples must be one-dimensional")
    if not np.isfinite(values).all() or np.any((values < 0) | (values > 1)):
        raise ValueError("samples must be finite alpha values in [0, 1]")
    if not np.isfinite(spacing) or spacing <= 0:
        raise ValueError("spacing must be a positive finite number")

    report = {
        "method": "explicit_normal_profile_linear_crossings_0.05_0.95",
        "sample_count": int(values.size),
        "max_samples": max_samples,
        "spacing_pixels": float(spacing),
        "status": "no_evidence",
        "direction": None,
        "crossing_05_pixels": None,
        "crossing_95_pixels": None,
        "width_05_95_pixels": None,
    }
    if values.size < 2:
        return report
    deltas = np.diff(values)
    if np.all(deltas >= 0):
        increasing = values
        report["direction"] = "increasing"
    elif np.all(deltas <= 0):
        increasing = values[::-1]
        report["direction"] = "decreasing"
    else:
        report["status"] = "ambiguous"
        return report
    if increasing[0] > 0.05 or increasing[-1] < 0.95:
        return report

    def crossing(threshold: float) -> float:
        index = int(np.searchsorted(increasing, threshold, side="left"))
        if index == 0:
            return 0.0
        before, after = increasing[index - 1], increasing[index]
        # Repeated values can only happen outside a threshold crossing; the
        # exact-value branch is retained for clarity and numerical safety.
        offset = 0.0 if after == before else (threshold - before) / (after - before)
        return (index - 1 + offset) * float(spacing)

    low = float(crossing(0.05))
    high = float(crossing(0.95))
    report.update({
        "status": "ok",
        "crossing_05_pixels": low,
        "crossing_95_pixels": high,
        "width_05_95_pixels": high - low,
    })
    return report
