"""Opt-in, offline stage diagnostics. No files, network or live quality claims.

This traces completed removal/despill/restore stages, not the internal matte
classifier, references or confidence. It is a partial CK-04 diagnostic surface.
Reports retain hashes/counts/metrics, never image pixels, filenames or prompts.
"""
from __future__ import annotations

import hashlib

import numpy as np
from PIL import Image

from chroma_key import ChromaKeyAmbiguousError, parse_key_color, remove_chroma_key_automatic
from chroma_quality import reference_quality

MAX_DIAGNOSTIC_PIXELS = 4 * 1024 * 1024


def _digest(image: Image.Image) -> str:
    return hashlib.sha256(image.tobytes()).hexdigest()


def diagnose_chroma_key(image: Image.Image, key_color: object = "blue", *,
                        subject_profile: str = "opaque_clipart",
                        truth: Image.Image | None = None,
                        max_pixels: int = MAX_DIAGNOSTIC_PIXELS) -> tuple[dict, Image.Image | None]:
    """Return a bounded diagnostic report and unchanged engine output.

    Truth is optional caller-supplied reference RGBA, never inferred from input.
    An ambiguous key returns Review with a safe exception type and no result;
    invalid arguments or unexpected implementation errors still raise.
    ``max_pixels`` can lower, but cannot raise, the offline memory bound.
    """
    if type(max_pixels) is not int or not 0 < max_pixels <= MAX_DIAGNOSTIC_PIXELS:
        raise ValueError("Invalid diagnostic pixel limit")
    if not isinstance(image, Image.Image) or not all(image.size):
        raise ValueError("A nonempty source image is required")
    if image.width * image.height > max_pixels:
        raise ValueError("Image exceeds diagnostic pixel limit")
    if truth is not None and (not isinstance(truth, Image.Image) or truth.size != image.size):
        raise ValueError("Truth must have the same dimensions as source")
    source = image.convert("RGBA")
    expected = truth.convert("RGBA") if truth is not None else None
    report = {
        "schema_version": 1,
        "scope": "offline_completed_pixel_stages_only",
        "subject_profile": subject_profile,
        "requested_background": "#%02X%02X%02X" % parse_key_color(key_color),
        "pixel_format": "RGBA8",
        "dimensions": list(source.size),
        "source_pixels_sha256": _digest(source),
        "quality_status": "reference_comparison" if expected is not None else "not_evaluated",
        "stages": [],
    }
    if expected is not None:
        report["truth_pixels_sha256"] = _digest(expected)
    previous = np.asarray(source).copy()

    def observe(stage: str, snapshot: Image.Image) -> None:
        nonlocal previous
        pixels = np.asarray(snapshot)
        alpha = pixels[..., 3]
        record = {
            "stage": stage,
            "pixels_sha256": _digest(snapshot),
            "changed_rgb_pixels": int(np.count_nonzero(np.any(pixels[..., :3] != previous[..., :3], axis=2))),
            "changed_alpha_pixels": int(np.count_nonzero(alpha != previous[..., 3])),
            "transparent_pixels": int(np.count_nonzero(alpha == 0)),
            "partial_pixels": int(np.count_nonzero((alpha > 0) & (alpha < 255))),
            "opaque_pixels": int(np.count_nonzero(alpha == 255)),
        }
        if expected is not None:
            record["quality"] = reference_quality(snapshot, expected)
            expected_alpha = np.asarray(expected)[..., 3]
            record["reference_partial_made_opaque_pixels"] = int(np.count_nonzero(
                (expected_alpha > 0) & (expected_alpha < 255) & (alpha == 255)
            ))
        report["stages"].append(record)
        previous = pixels.copy()

    try:
        result = remove_chroma_key_automatic(
            source, key_color, subject_profile=subject_profile, stage_observer=observe,
        )
    except ChromaKeyAmbiguousError as error:
        report.update(status="review", reason=type(error).__name__)
        return report, None
    report.update(status="processed", result_pixels_sha256=_digest(result))
    return report, result
