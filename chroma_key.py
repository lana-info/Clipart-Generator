"""Local chroma-key removal for clipart rendered on a solid key color."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Final

import cv2
import numpy as np
from PIL import Image


KEY_COLORS: Final[dict[str, tuple[int, int, int]]] = {
    "blue": (0, 0, 255),
    "red": (255, 0, 0),
    "green": (0, 255, 0),
}
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_MAX_AMBIGUOUS_COMPONENT_DENSITY: Final[float] = 0.02
_MIN_AMBIGUOUS_COMPONENT_LIMIT: Final[int] = 64

MATERIAL_PROMPT_CLAUSES: Final[dict[str, str]] = {
    "watercolor": (
        " Watercolor texture belongs to the subject only; the background "
        "has no paper texture, paper grain, wash or painted variation."
    ),
    "thin_leaves": (
        " Leaves are thick flat blades with rounded tips, solid and opaque, "
        "never hair-thin, wispy or feathery."
    ),
    "conifer_needles": (
        " Needles are short, broad and thick, each a solid opaque blade with "
        "a blunt rounded tip, never fine or feathery."
    ),
    "metal": (
        " Metal elements are matte brushed metal with a soft satin finish, "
        "no mirror reflections or background-colour glints."
    ),
    "ribbon_satin": (
        " Ribbon is matte woven fabric with crisp folded edges and no sheen "
        "or reflection."
    ),
    "transparent_details": (
        " Translucent details have crisp defined edges, no background-colour "
        "reflection, tint or glow."
    ),
    "snow_ice": (
        " Snow and ice are opaque with crisp defined edges, no mist, haze, "
        "glitter particles or background-colour glow."
    ),
}


class ChromaKeyAmbiguousError(ValueError):
    """Raised when the image border is not a safe match for the selected key."""


def parse_key_color(value: object) -> tuple[int, int, int]:
    """Parse a named or hex RGB key color."""
    normalized = str(value or "").strip().lower()
    if normalized in KEY_COLORS:
        return KEY_COLORS[normalized]
    if _HEX_COLOR.fullmatch(normalized):
        return tuple(int(normalized[index : index + 2], 16) for index in (1, 3, 5))
    raise ValueError("Цвет chroma key должен быть blue, red, green или #RRGGBB")


def remove_chroma_key(
    image: Image.Image,
    key_color: object = "blue",
    *,
    tolerance: int = 32,
    softness: int = 8,
) -> Image.Image:
    """Return RGBA with pixels close to ``key_color`` made transparent.

    This is deliberately deterministic and CPU-only. RGB values are copied
    from the source; only alpha is calculated, including semi-transparent
    transition pixels. Existing alpha is respected.
    """
    if not isinstance(image, Image.Image):
        raise TypeError("image must be a PIL image")
    if type(tolerance) is not int or not 0 <= tolerance <= 255:
        raise ValueError("tolerance must be between 0 and 255")
    if type(softness) is not int or not 0 <= softness <= 255:
        raise ValueError("softness must be between 0 and 255")
    red, green, blue = parse_key_color(key_color)
    source = image.convert("RGBA")
    pixels = source.load()
    for y in range(source.height):
        for x in range(source.width):
            src_red, src_green, src_blue, src_alpha = pixels[x, y]
            distance = (
                (src_red - red) ** 2
                + (src_green - green) ** 2
                + (src_blue - blue) ** 2
            ) ** 0.5
            if distance <= tolerance:
                alpha = 0
            elif softness and distance < tolerance + softness:
                alpha = round(255 * (distance - tolerance) / softness)
            else:
                alpha = 255
            pixels[x, y] = (src_red, src_green, src_blue, min(src_alpha, alpha))
    return source


def _remove_chroma_key_precise(
    image: Image.Image,
    key_color: object = "blue",
) -> Image.Image:
    """Remove a generated solid background using its measured border color."""
    if not isinstance(image, Image.Image):
        raise TypeError("image must be a PIL image")
    if image.width < 1 or image.height < 1:
        raise ValueError("image dimensions must be positive")
    requested_key = np.asarray(parse_key_color(key_color), dtype=np.float32)
    source = image.convert("RGBA")
    pixels = np.asarray(source, dtype=np.uint8).copy()
    rgb = pixels[..., :3].astype(np.float32)
    border = np.concatenate(
        (rgb[0, :, :], rgb[-1, :, :], rgb[:, 0, :], rgb[:, -1, :]),
        axis=0,
    )
    measured_key = np.median(border, axis=0)
    key_channel = int(np.argmax(requested_key))
    other_channels = [index for index in range(3) if index != key_channel]
    measured_dominance = measured_key[key_channel] - max(
        measured_key[other_channels[0]],
        measured_key[other_channels[1]],
    )
    border_spread = float(
        np.percentile(np.linalg.norm(border - measured_key, axis=1), 90)
    )
    if (
        float(np.linalg.norm(measured_key - requested_key)) > 120.0
        or measured_dominance < 40.0
        or border_spread > 30.0
    ):
        raise ChromaKeyAmbiguousError(
            "Фон по краям не совпадает с выбранным Chroma Key цветом"
        )
    background_dominance = measured_key[key_channel] - max(
        measured_key[other_channels[0]],
        measured_key[other_channels[1]],
    )
    border_dominance = border[:, key_channel] - np.maximum(
        border[:, other_channels[0]],
        border[:, other_channels[1]],
    )
    border_residual_alpha = 1.0 - np.clip(
        border_dominance / background_dominance,
        0.0,
        1.0,
    )
    if float(np.percentile(border_residual_alpha, 95)) > 0.02:
        raise ChromaKeyAmbiguousError(
            "Chroma Key фон неоднородный; нужен ровный однотонный фон"
        )
    pixel_dominance = rgb[..., key_channel] - np.maximum(
        rgb[..., other_channels[0]],
        rgb[..., other_channels[1]],
    )
    background_fraction = np.clip(
        pixel_dominance / background_dominance,
        0.0,
        1.0,
    )
    raw_matte = 1.0 - background_fraction
    distance_from_key = np.linalg.norm(rgb - measured_key, axis=2)

    probable_background = distance_from_key < 120.0
    _, background_labels = cv2.connectedComponents(
        probable_background.astype(np.uint8),
        connectivity=8,
    )
    border_labels = np.concatenate(
        (
            background_labels[0, :],
            background_labels[-1, :],
            background_labels[:, 0],
            background_labels[:, -1],
        )
    )
    border_label_counts = np.bincount(border_labels)
    if len(border_label_counts) <= 1:
        raise ChromaKeyAmbiguousError(
            "Chroma Key фон неоднородный; нужен ровный однотонный фон"
        )
    background_label = int(np.argmax(border_label_counts[1:]) + 1)
    connected_background = background_labels == background_label
    nonuniform_fraction = float(
        np.count_nonzero(connected_background & (raw_matte > 0.02))
        / max(1, np.count_nonzero(connected_background))
    )
    if nonuniform_fraction > 0.30:
        raise ChromaKeyAmbiguousError(
            "Chroma Key фон неоднородный; нужен ровный однотонный фон"
        )
    del (
        probable_background,
        background_labels,
        border_labels,
        border_label_counts,
        background_label,
        connected_background,
        nonuniform_fraction,
    )

    ambiguous_band = (
        (raw_matte > 0.05)
        & (raw_matte < 0.95)
        & (distance_from_key < 200.0)
    )
    protected_interior_detail = np.zeros(raw_matte.shape, dtype=bool)
    if np.any(ambiguous_band):
        component_count, labels, stats, _ = cv2.connectedComponentsWithStats(
            ambiguous_band.astype(np.uint8),
            connectivity=8,
        )
        component_limit = max(
            _MIN_AMBIGUOUS_COMPONENT_LIMIT,
            int(image.width * image.height * _MAX_AMBIGUOUS_COMPONENT_DENSITY),
        )
        if component_count - 1 > component_limit:
            raise ChromaKeyAmbiguousError(
                "Chroma Key фон слишком неоднородный; нужен ровный однотонный фон"
            )
        hard_background = raw_matte <= 0.02
        confident_subject = raw_matte >= 0.995
        distance_to_background = cv2.distanceTransform(
            (~hard_background).astype(np.uint8),
            cv2.DIST_L2,
            3,
        )
        kernel = np.ones((3, 3), dtype=np.uint8)
        for component_id in range(1, component_count):
            left, top, width, height, _ = stats[component_id]
            x0 = max(0, left - 1)
            y0 = max(0, top - 1)
            x1 = min(image.width, left + width + 1)
            y1 = min(image.height, top + height + 1)
            component = labels[y0:y1, x0:x1] == component_id
            ring = cv2.dilate(component.astype(np.uint8), kernel).astype(bool)
            ring &= ~component
            local_subject = confident_subject[y0:y1, x0:x1]
            local_raw_matte = raw_matte[y0:y1, x0:x1]
            local_distance = distance_to_background[y0:y1, x0:x1]
            enclosed = float(np.min(local_distance[component])) > 3.0
            component_range = float(np.ptp(local_raw_matte[component]))
            suspicious_edge_detail = (
                stats[component_id, cv2.CC_STAT_AREA] >= 9
                and component_range < 0.1
            )
            touches_subject = np.any(local_subject & ring)
            local_protected = protected_interior_detail[y0:y1, x0:x1]
            if touches_subject and suspicious_edge_detail:
                raise ChromaKeyAmbiguousError(
                    "Предмет содержит выбранный Chroma Key цвет; выберите другой цвет фона"
                )
            if touches_subject and enclosed:
                local_protected[component] = True
        del (
            component_count,
            labels,
            stats,
            hard_background,
            confident_subject,
            distance_to_background,
            kernel,
            component,
            ring,
            local_subject,
            local_raw_matte,
            local_distance,
            component_range,
            suspicious_edge_detail,
            touches_subject,
            local_protected,
        )
    del ambiguous_band
    raw_matte[protected_interior_detail] = 1.0
    del protected_interior_detail
    matte = raw_matte.copy()
    matte[distance_from_key >= 200.0] = 1.0
    visible = matte > (1.0 / 255.0)
    if np.any(visible):
        recovered = (
            rgb[visible]
            - (1.0 - matte[visible, None]) * measured_key[None, :]
        ) / matte[visible, None]
        pixels[visible, :3] = np.rint(np.clip(recovered, 0.0, 255.0)).astype(
            np.uint8
        )
    spill = (distance_from_key >= 200.0) & (raw_matte < 0.995) & (raw_matte > 0.0)
    core = raw_matte >= 0.995
    if np.any(spill) and np.any(core):
        eroded_core = cv2.erode(
            core.astype(np.uint8),
            np.ones((3, 3), dtype=np.uint8),
            iterations=max(1, min(source.size) // 128),
        ).astype(bool)
        if np.any(eroded_core):
            core = eroded_core
        distance_map, nearest = cv2.distanceTransformWithLabels(
            (~core).astype(np.uint8),
            cv2.DIST_L2,
            5,
            labelType=cv2.DIST_LABEL_PIXEL,
        )
        del distance_map
        core_labels = nearest[core]
        spill_labels = nearest[spill]
        local_foreground = np.empty((int(np.count_nonzero(spill)), 3), dtype=np.float32)
        for channel in range(3):
            reference_channel = np.zeros(int(nearest.max()) + 1, dtype=np.float32)
            reference_channel[core_labels] = rgb[..., channel][core]
            local_foreground[:, channel] = reference_channel[spill_labels]
        source_spill = rgb[spill]
        direction = measured_key[None, :] - local_foreground
        denominator = np.sum(direction * direction, axis=1)
        mixture = np.divide(
            np.sum((source_spill - local_foreground) * direction, axis=1),
            denominator,
            out=np.zeros_like(denominator),
            where=denominator > 1e-6,
        )
        mixture = np.clip(mixture, 0.0, 0.95)
        despilled = (
            source_spill - mixture[:, None] * measured_key[None, :]
        ) / (1.0 - mixture[:, None])
        pixels[spill, :3] = np.rint(np.clip(despilled, 0.0, 255.0)).astype(
            np.uint8
        )
    pixels[..., 3] = np.minimum(
        pixels[..., 3],
        np.rint(matte * 255.0).astype(np.uint8),
    )
    return Image.fromarray(pixels, mode="RGBA")


def _blurred_subject_reference(
    rgb: np.ndarray,
    subject_mask: np.ndarray,
    sigma: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Return locally averaged subject RGB and its usable reference weight."""
    mask = subject_mask.astype(np.float32)
    weight = cv2.GaussianBlur(
        mask,
        (0, 0),
        sigma,
        borderType=cv2.BORDER_REFLECT,
    )
    reference = np.zeros(rgb.shape, dtype=np.float32)
    usable = weight > 1e-6
    for channel in range(3):
        numerator = cv2.GaussianBlur(
            rgb[..., channel] * mask,
            (0, 0),
            sigma,
            borderType=cv2.BORDER_REFLECT,
        )
        np.divide(
            numerator,
            weight,
            out=reference[..., channel],
            where=usable,
        )
    return reference, weight


def _fill_far_subject_reference(
    rgb: np.ndarray,
    subject_mask: np.ndarray,
    reference: np.ndarray,
    reference_weight: np.ndarray,
) -> None:
    """Fill pixels without a nearby foreground sample using a wider blur."""
    use_far = reference_weight < 0.02
    if not np.any(use_far):
        return
    mask = subject_mask.astype(np.float32)
    far_weight = cv2.GaussianBlur(
        mask,
        (0, 0),
        11.0,
        borderType=cv2.BORDER_REFLECT,
    )
    usable = far_weight > 1e-6
    for channel in range(3):
        numerator = cv2.GaussianBlur(
            rgb[..., channel] * mask,
            (0, 0),
            11.0,
            borderType=cv2.BORDER_REFLECT,
        )
        np.divide(numerator, far_weight, out=numerator, where=usable)
        np.copyto(reference[..., channel], numerator, where=use_far)
    np.copyto(reference_weight, far_weight, where=use_far)


def _apply_multiscale_subject_reference(
    rgb: np.ndarray,
    subject_mask: np.ndarray,
    key_channel: int,
    other_channels: list[int],
    reference: np.ndarray,
    ratio: np.ndarray,
) -> None:
    """Replace edge references with the deepest available subject samples."""
    interior_depth = cv2.distanceTransform(
        subject_mask.astype(np.uint8),
        cv2.DIST_L2,
        3,
    )
    has_deep_reference = np.zeros(subject_mask.shape, dtype=bool)
    for depth in (12.0, 6.0, 3.0, 2.0):
        deep_mask = (interior_depth > depth).astype(np.float32)
        if not np.any(deep_mask):
            continue
        weight = cv2.GaussianBlur(
            deep_mask,
            (0, 0),
            10.0,
            borderType=cv2.BORDER_REFLECT,
        )
        usable = (weight >= 0.005) & ~has_deep_reference
        if not np.any(usable):
            continue

        for channel in range(3):
            channel_reference = rgb[..., channel] * deep_mask
            cv2.GaussianBlur(
                channel_reference,
                (0, 0),
                10.0,
                dst=channel_reference,
                borderType=cv2.BORDER_REFLECT,
            )
            np.divide(
                channel_reference,
                weight,
                out=channel_reference,
                where=weight > 1e-6,
            )
            np.copyto(reference[..., channel], channel_reference, where=usable)
            del channel_reference

        reference_other = np.maximum(
            reference[..., other_channels[0]],
            reference[..., other_channels[1]],
        )
        np.copyto(deep_mask, reference[..., key_channel], where=usable)
        np.divide(
            deep_mask,
            np.maximum(reference_other, 1.0),
            out=deep_mask,
        )
        np.clip(deep_mask, 0.05, 1.2, out=deep_mask)
        np.copyto(ratio, deep_mask, where=usable)
        has_deep_reference |= usable


def _neutralize_opaque_key_spill(
    source: Image.Image,
    result: Image.Image,
    key_color: object,
) -> Image.Image:
    """Recover localized key reflections inside an otherwise opaque subject."""
    requested_key = np.asarray(parse_key_color(key_color), dtype=np.float32)
    key_channel = int(np.argmax(requested_key))
    other_channels = [index for index in range(3) if index != key_channel]
    source_rgb = np.asarray(source.convert("RGB"), dtype=np.float32)
    frame = max(4, int(0.02 * min(source.size)))
    border = np.concatenate(
        (
            source_rgb[:frame, :, :].reshape(-1, 3),
            source_rgb[-frame:, :, :].reshape(-1, 3),
            source_rgb[:, :frame, :].reshape(-1, 3),
            source_rgb[:, -frame:, :].reshape(-1, 3),
        ),
        axis=0,
    )
    measured_key = np.median(border, axis=0)
    del source_rgb, border

    pixels = np.asarray(result.convert("RGBA"), dtype=np.uint8).copy()
    rgb = pixels[..., :3].astype(np.float32)
    subject = pixels[..., 3] >= 250
    other = np.maximum(
        rgb[..., other_channels[0]],
        rgb[..., other_channels[1]],
    )
    clean_reference = subject & (
        rgb[..., key_channel] <= 0.86 * other + 5.0
    )
    suspected_spill = subject & (
        rgb[..., key_channel] >= 0.90 * other + 5.0
    )
    if not np.any(clean_reference) or not np.any(suspected_spill):
        return result

    distance, nearest = cv2.distanceTransformWithLabels(
        (~clean_reference).astype(np.uint8),
        cv2.DIST_L2,
        5,
        labelType=cv2.DIST_LABEL_PIXEL,
    )
    reference_labels = nearest[clean_reference]
    spill_labels = nearest[suspected_spill]
    reference = np.empty(
        (int(np.count_nonzero(suspected_spill)), 3),
        dtype=np.float32,
    )
    for channel in range(3):
        lookup = np.zeros(int(nearest.max()) + 1, dtype=np.float32)
        lookup[reference_labels] = rgb[..., channel][clean_reference]
        reference[:, channel] = lookup[spill_labels]

    source_spill = rgb[suspected_spill]
    direction = measured_key[None, :] - reference
    denominator = np.sum(direction * direction, axis=1)
    mixture = np.divide(
        np.sum((source_spill - reference) * direction, axis=1),
        denominator,
        out=np.zeros_like(denominator),
        where=denominator > 1e-6,
    )
    predicted = (
        (1.0 - mixture[:, None]) * reference
        + mixture[:, None] * measured_key[None, :]
    )
    residual = np.linalg.norm(source_spill - predicted, axis=1)
    max_distance = max(48.0, min(source.size) / 16.0)
    correct = (
        (mixture >= 0.04)
        & (mixture <= 0.60)
        & (residual <= 8.0)
        & (distance[suspected_spill] <= max_distance)
    )
    if np.any(correct):
        recovered = (
            source_spill[correct]
            - mixture[correct, None] * measured_key[None, :]
        ) / (1.0 - mixture[correct, None])
        corrected = source_spill.copy()
        corrected[correct] = recovered
        rgb[suspected_spill] = corrected
        pixels[..., :3] = np.rint(np.clip(rgb, 0.0, 255.0)).astype(np.uint8)
        return Image.fromarray(pixels, mode="RGBA")
    return result


def _neutralize_translucent_complement(
    source: Image.Image,
    result: Image.Image,
    key_color: object,
) -> Image.Image:
    """Remove complementary colour created by over-subtracting a key channel."""
    requested_key = np.asarray(parse_key_color(key_color), dtype=np.float32)
    key_channel = int(np.argmax(requested_key))
    other_channels = [index for index in range(3) if index != key_channel]
    source_rgb = np.asarray(source.convert("RGB"), dtype=np.float32)
    pixels = np.asarray(result.convert("RGBA"), dtype=np.uint8).copy()
    rgb = pixels[..., :3].astype(np.float32)
    alpha = pixels[..., 3]
    other_floor = np.minimum(
        rgb[..., other_channels[0]],
        rgb[..., other_channels[1]],
    )
    source_other = np.maximum(
        source_rgb[..., other_channels[0]],
        source_rgb[..., other_channels[1]],
    )
    over_removed_key = (
        source_rgb[..., key_channel] >= rgb[..., key_channel] + 20.0
    )
    severe_complement = rgb[..., key_channel] < 0.90 * other_floor
    source_still_key_dominant = (
        source_rgb[..., key_channel] >= source_other + 8.0
    )
    mild_complement_from_key = source_still_key_dominant & (
        rgb[..., key_channel] < 1.05 * other_floor
    )
    translucent = (alpha > 0) & (alpha < 255)
    wide_translucent_core = cv2.erode(
        translucent.astype(np.uint8),
        np.ones((9, 9), dtype=np.uint8),
        iterations=1,
    ).astype(bool)
    translucent_neighborhood = cv2.dilate(
        wide_translucent_core.astype(np.uint8),
        np.ones((25, 25), dtype=np.uint8),
        iterations=1,
    ).astype(bool)
    visible = alpha > 0
    repair = (
        over_removed_key
        & (severe_complement | mild_complement_from_key)
        & translucent_neighborhood
        & visible
    )
    if not np.any(repair):
        return result

    restored_key = other_floor
    np.copyto(rgb[..., key_channel], restored_key, where=repair)
    pixels[..., :3] = np.rint(np.clip(rgb, 0.0, 255.0)).astype(np.uint8)
    return Image.fromarray(pixels, mode="RGBA")


def _remove_chroma_key_staged(
    image: Image.Image,
    key_color: object,
) -> Image.Image:
    """Robust fallback for detailed subjects and compressed key backgrounds."""
    requested_key = np.asarray(parse_key_color(key_color), dtype=np.float32)
    source = image.convert("RGBA")
    pixels = np.asarray(source, dtype=np.uint8).copy()
    rgb = pixels[..., :3].astype(np.float32)
    height, width = rgb.shape[:2]
    frame = max(4, int(0.02 * min(width, height)))
    sides = (
        rgb[:frame, :, :].reshape(-1, 3),
        rgb[-frame:, :, :].reshape(-1, 3),
        rgb[:, :frame, :].reshape(-1, 3),
        rgb[:, -frame:, :].reshape(-1, 3),
    )
    measured_key = np.median(np.concatenate(sides, axis=0), axis=0)
    key_channel = int(np.argmax(requested_key))
    if int(np.argmax(measured_key)) != key_channel:
        raise ChromaKeyAmbiguousError(
            "Фон по краям не совпадает с выбранным Chroma Key цветом"
        )
    other_channels = [index for index in range(3) if index != key_channel]
    measured_other = max(
        measured_key[other_channels[0]],
        measured_key[other_channels[1]],
    )
    if measured_key[key_channel] - measured_other < 40.0:
        raise ChromaKeyAmbiguousError(
            "Фон по краям не совпадает с выбранным Chroma Key цветом"
        )
    side_medians = np.stack([np.median(side, axis=0) for side in sides])
    if float(np.max(np.linalg.norm(side_medians - measured_key, axis=1))) > 30.0:
        raise ChromaKeyAmbiguousError(
            "Chroma Key фон неоднородный; нужен ровный однотонный фон"
        )
    del sides, side_medians, requested_key

    dominant = rgb[..., key_channel]
    other = np.maximum(
        rgb[..., other_channels[0]],
        rgb[..., other_channels[1]],
    )
    key_ratio = measured_key[key_channel] / max(measured_other, 1.0)
    background_ratio = float(np.clip(0.80 * key_ratio, 1.70, 2.5))
    hard_background = (dominant >= background_ratio * other) & (dominant >= 55.0)
    edge_background = hard_background & cv2.dilate(
        (~hard_background).astype(np.uint8),
        np.ones((3, 3), dtype=np.uint8),
        iterations=1,
    ).astype(bool)
    hard_background &= ~edge_background
    confident_subject = (~hard_background) & (dominant <= 1.15 * other + 8.0)
    transition = ~hard_background & ~confident_subject

    distance_from_background = cv2.distanceTransform(
        (~hard_background).astype(np.uint8),
        cv2.DIST_L2,
        3,
    )
    promoted = (
        transition
        & (distance_from_background > 6.0)
        & (dominant <= 1.6 * other + 8.0)
    )
    confident_subject |= promoted
    del distance_from_background, promoted

    bright_background = hard_background & (dominant >= 150.0)
    background_density = cv2.blur(
        bright_background.astype(np.float32),
        (41, 41),
    )
    dark_detail = (
        (np.max(rgb, axis=2) < 58.0)
        & ~confident_subject
        & (background_density > 0.35)
    )
    dark_halo = None
    if np.any(dark_detail):
        confident_subject |= dark_detail
        dark_halo = cv2.dilate(
            dark_detail.astype(np.uint8),
            np.ones((3, 3), dtype=np.uint8),
            iterations=2,
        ).astype(bool)
        hard_background &= ~dark_halo
    transition = ~hard_background & ~confident_subject
    del bright_background, background_density, dark_detail
    if dark_halo is not None:
        del dark_halo

    if not np.any(confident_subject):
        background_distance = np.linalg.norm(rgb - measured_key, axis=2)
        if float(np.percentile(background_distance, 90)) > 15.0:
            raise ChromaKeyAmbiguousError(
                "Chroma Key фон неоднородный; нужен ровный однотонный фон"
            )

    del hard_background
    reference, reference_weight = _blurred_subject_reference(
        rgb,
        confident_subject,
        3.0,
    )
    _fill_far_subject_reference(
        rgb,
        confident_subject,
        reference,
        reference_weight,
    )
    has_reference = reference_weight >= 0.005

    alpha = np.zeros((height, width), dtype=np.float32)
    alpha[confident_subject] = 1.0
    key_length = float(np.dot(measured_key, measured_key))
    key_separation = max(measured_key[key_channel] - measured_other, 1.0)
    tile_size = 512
    for y0 in range(0, height, tile_size):
        y1 = min(y0 + tile_size, height)
        for x0 in range(0, width, tile_size):
            x1 = min(x0 + tile_size, width)
            tile = np.s_[y0:y1, x0:x1]
            tile_transition = transition[tile]
            solved = tile_transition & has_reference[tile]
            if np.any(solved):
                tile_rgb = rgb[tile]
                tile_reference = reference[tile]
                source_color = tile_rgb[solved]
                foreground_color = tile_reference[solved]
                foreground_length = np.sum(
                    foreground_color * foreground_color,
                    axis=1,
                )
                foreground_key = foreground_color @ measured_key
                source_foreground = np.sum(
                    source_color * foreground_color,
                    axis=1,
                )
                source_key = source_color @ measured_key
                determinant = (
                    foreground_length * key_length
                    - foreground_key * foreground_key
                )
                stable = determinant > 1e-3 * (
                    foreground_length * key_length + 1e-6
                )
                subject_amount = np.empty(len(source_color), dtype=np.float32)
                background_amount = np.empty(len(source_color), dtype=np.float32)
                subject_amount[stable] = (
                    source_foreground[stable] * key_length
                    - source_key[stable] * foreground_key[stable]
                ) / determinant[stable]
                background_amount[stable] = (
                    source_key[stable] * foreground_length[stable]
                    - source_foreground[stable] * foreground_key[stable]
                ) / determinant[stable]
                dominance_alpha = 1.0 - np.clip(
                    (
                        source_color[:, key_channel]
                        - np.maximum(
                            source_color[:, other_channels[0]],
                            source_color[:, other_channels[1]],
                        )
                    )
                    / key_separation,
                    0.0,
                    1.0,
                )
                subject_amount[~stable] = dominance_alpha[~stable]
                background_amount[~stable] = 1.0 - subject_amount[~stable]
                np.clip(subject_amount, 0.0, 1.0, out=subject_amount)
                np.clip(background_amount, 0.0, 1.5, out=background_amount)
                tile_alpha = alpha[tile]
                tile_alpha[solved] = subject_amount
                tile_rgb[solved] = (
                    source_color
                    - background_amount[:, None] * measured_key[None, :]
                ) / np.maximum(subject_amount[:, None], 0.05)
            unsolved = tile_transition & ~has_reference[tile]
            if np.any(unsolved):
                tile_alpha = alpha[tile]
                tile_dominant = dominant[tile]
                tile_other = other[tile]
                tile_alpha[unsolved] = 1.0 - np.clip(
                    (tile_dominant[unsolved] - tile_other[unsolved])
                    / key_separation,
                    0.0,
                    1.0,
                )
    del transition, has_reference, reference_weight, dominant, other

    reference_other = np.maximum(
        reference[..., other_channels[0]],
        reference[..., other_channels[1]],
    )
    edge_reference_ratio = reference[..., key_channel].copy()
    np.divide(
        edge_reference_ratio,
        np.maximum(reference_other, 1.0),
        out=edge_reference_ratio,
    )
    np.clip(edge_reference_ratio, 0.05, 1.2, out=edge_reference_ratio)
    del reference_other
    _apply_multiscale_subject_reference(
        rgb,
        confident_subject,
        key_channel,
        other_channels,
        reference,
        edge_reference_ratio,
    )
    del confident_subject

    soft_edge = (alpha > 0.0) & (alpha < 0.999)
    edge_ring = cv2.dilate(
        soft_edge.astype(np.uint8),
        np.ones((3, 3), dtype=np.uint8),
        iterations=max(8, min(height, width) // 128),
    ).astype(bool) & (alpha > 0.0)
    del soft_edge
    key_luminance = float(
        0.299 * measured_key[0]
        + 0.587 * measured_key[1]
        + 0.114 * measured_key[2]
    )
    key_strength = max(float(measured_key[key_channel]), 1.0)
    for y0 in range(0, height, tile_size):
        y1 = min(y0 + tile_size, height)
        for x0 in range(0, width, tile_size):
            x1 = min(x0 + tile_size, width)
            tile = np.s_[y0:y1, x0:x1]
            tile_edge = edge_ring[tile]
            if not np.any(tile_edge):
                continue
            reference_ratio = edge_reference_ratio[tile]
            tile_rgb = rgb[tile]
            tile_reference = reference[tile]
            current_other = np.maximum(
                tile_rgb[..., other_channels[0]],
                tile_rgb[..., other_channels[1]],
            )
            excess = np.maximum(
                tile_rgb[..., key_channel]
                - (reference_ratio * current_other + 4.0),
                0.0,
            )
            mixture = excess / key_strength
            neutral_luminance = 0.5 * mixture * key_luminance
            corrected = tile_rgb.copy()
            for channel in range(3):
                correction = (
                    -mixture * measured_key[channel]
                    + neutral_luminance
                )
                corrected[..., channel] += correction

            direction = measured_key[None, None, :] - tile_reference
            denominator = np.sum(direction * direction, axis=2)
            projected_mix = np.divide(
                np.sum((tile_rgb - tile_reference) * direction, axis=2),
                denominator,
                out=np.zeros(denominator.shape, dtype=np.float32),
                where=denominator > 1e-6,
            )
            projected_mix = np.clip(projected_mix, 0.0, 0.70)
            predicted = (
                (1.0 - projected_mix[..., None]) * tile_reference
                + projected_mix[..., None] * measured_key[None, None, :]
            )
            projection_residual = np.linalg.norm(tile_rgb - predicted, axis=2)
            use_projection = (
                tile_edge
                & (projected_mix >= 0.025)
                & (projection_residual <= 18.0)
            )
            projected = (
                tile_rgb
                - projected_mix[..., None] * measured_key[None, None, :]
            ) / np.maximum(1.0 - projected_mix[..., None], 0.30)
            corrected[use_projection] = projected[use_projection]
            tile_rgb[tile_edge] = corrected[tile_edge]
    del edge_ring, edge_reference_ratio, reference

    alpha = np.where(alpha < 0.025, 0.0, (alpha - 0.025) / 0.975)
    alpha = np.clip(alpha, 0.0, 1.0)
    smoothed_alpha = cv2.GaussianBlur(
        alpha,
        (0, 0),
        0.36,
        borderType=cv2.BORDER_REFLECT,
    )
    np.minimum(alpha, smoothed_alpha, out=alpha)
    del smoothed_alpha
    pixels[..., :3] = np.rint(np.clip(rgb, 0.0, 255.0)).astype(np.uint8)
    pixels[..., 3] = np.minimum(
        pixels[..., 3],
        np.rint(alpha * 255.0).astype(np.uint8),
    )
    return Image.fromarray(pixels, mode="RGBA")


def _measured_border_key(image: Image.Image) -> np.ndarray:
    """Measure the actual rendered key from the outer two-percent frame."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    height, width = rgb.shape[:2]
    frame = max(4, int(0.02 * min(width, height)))
    border = np.concatenate(
        (
            rgb[:frame, :, :].reshape(-1, 3),
            rgb[-frame:, :, :].reshape(-1, 3),
            rgb[:, :frame, :].reshape(-1, 3),
            rgb[:, -frame:, :].reshape(-1, 3),
        ),
        axis=0,
    )
    return np.median(border, axis=0).astype(np.float32)


def remove_chroma_key_automatic(
    image: Image.Image,
    key_color: object = "blue",
) -> Image.Image:
    """Remove a generated key background without user-tuned thresholds."""
    if not isinstance(image, Image.Image):
        raise TypeError("image must be a PIL image")
    if image.width < 1 or image.height < 1:
        raise ValueError("image dimensions must be positive")
    requested_key = np.asarray(parse_key_color(key_color), dtype=np.float32)
    key_channel = int(np.argmax(requested_key))
    measured_key = _measured_border_key(image)
    if int(np.argmax(measured_key)) != key_channel:
        raise ChromaKeyAmbiguousError(
            "Фон по краям не совпадает с выбранным Chroma Key цветом"
        )
    other_channels = [index for index in range(3) if index != key_channel]
    measured_other = max(
        measured_key[other_channels[0]],
        measured_key[other_channels[1]],
    )
    if measured_other <= 36.0:
        try:
            result = _remove_chroma_key_precise(image, key_color)
        except ChromaKeyAmbiguousError:
            pass
        else:
            result = _neutralize_opaque_key_spill(image, result, key_color)
            return _neutralize_translucent_complement(image, result, key_color)
    result = _remove_chroma_key_staged(image, key_color)
    result = _neutralize_opaque_key_spill(image, result, key_color)
    return _neutralize_translucent_complement(image, result, key_color)


def chroma_key_prompt_block(
    key_color: object = "blue",
    *,
    watercolor: bool = False,
    materials: Iterable[object] = (),
) -> str:
    """Return a provider-ready prompt suffix for a removable flat background."""
    rgb = parse_key_color(key_color)
    color_name = next((name for name, value in KEY_COLORS.items() if value == rgb), None)
    label = color_name or "custom"
    hex_color = "#%02X%02X%02X" % rgb
    block = (
        f"Isolated on a completely flat, uniform, solid pure {label} "
        f"({hex_color}) digital chroma-key background. The background fills "
        "the image edge to edge with no gradient and stays fully bright inside "
        "every gap and opening. No reflection, tint, shadow, glow, haze or "
        "color spill on the subject. Crisp hard edges, everything in sharp "
        "focus, the complete subject centered with at least 10% empty margin, "
        "nothing cropped, no text, no watermark, no stray fragments."
    )
    selected = {str(item).strip().casefold() for item in materials}
    if watercolor:
        selected.add("watercolor")
    for material in MATERIAL_PROMPT_CLAUSES:
        if material in selected:
            block += MATERIAL_PROMPT_CLAUSES[material]
    return block


__all__ = [
    "ChromaKeyAmbiguousError",
    "KEY_COLORS",
    "MATERIAL_PROMPT_CLAUSES",
    "chroma_key_prompt_block",
    "parse_key_color",
    "remove_chroma_key",
    "remove_chroma_key_automatic",
]
