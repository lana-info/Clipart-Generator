"""Local chroma-key removal for clipart rendered on a solid key color."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Final

import cv2
import numpy as np
from PIL import Image
from chroma_rim import ambiguous_pale_material, mixture_coverage, recolour_rim_specks, reclassify_rim, refine_edge_mixture, repair_edge_chroma, suppress_edge_key_spill
from studio_processing_api import ChromaKeyAmbiguousError, ChromaKeySubjectColorError


KEY_COLORS: Final[dict[str, tuple[int, int, int]]] = {
    "blue": (0, 0, 255),
    "red": (255, 0, 0),
    "green": (0, 255, 0),
}
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_MAX_AMBIGUOUS_COMPONENT_DENSITY: Final[float] = 0.02
_MIN_AMBIGUOUS_COMPONENT_LIMIT: Final[int] = 64
_MAX_AMBIGUOUS_KEY_DISTANCE: Final[float] = 230.0
_MIN_OPAQUE_REFERENCE_DISTANCE: Final[float] = 96.0
_MAX_ENCLOSED_TRANSITION_ROI_WORK_MULTIPLIER: Final[int] = 4
_ALPHA_NOISE_FLOOR: Final[float] = 1e-6
_SUBJECT_PROFILES: Final[frozenset[str]] = frozenset(("legacy", "opaque_clipart"))

# Shaded key pockets: the generator darkens the flat key inside narrow gaps
# between subject parts (ambient occlusion in a crevice). Such a pixel is
# numerically identical to an opaque subject colour behind partial coverage, so
# coverage alone can never classify it; only chroma direction, level and the
# local geometry of the gap can. Every threshold below is relative to the
# measured key, so the detector is independent of the image's numeric scale.
SHADED_KEY_MAX_ANGLE: Final[float] = 20.0      # degrees between the pixel chroma and the key chroma
SHADED_KEY_LEAD_FRACTION: Final[float] = 0.15  # key-channel lead over the strongest other channel, as a
#                                                share of the measured key's own lead: a shade of the key
#                                                keeps its hue however dark the key is
SHADED_KEY_MAX_LEVEL: Final[float] = 0.70      # key channel below this share of the key's level:
#                                                a crevice shadow blocks much of the light, while a
#                                                brighter key-coloured sample stays a plausible
#                                                partial coverage of paint and keeps its alpha
SHADED_KEY_KEY_DISTANCE: Final[float] = 0.18   # share of the key length that still counts as solid key
SHADED_KEY_SOLID_LEVEL: Final[float] = 0.95    # ... or this share of the key's own channel level
SHADED_KEY_BACKGROUND_CLEARANCE: Final[float] = 2.0  # px from that solid key; closer is an ordinary AA edge
SHADED_KEY_PAINT_ANGLE: Final[float] = 45.0    # degrees off the key chroma that only subject paint reaches
SHADED_KEY_MAX_GAP_WIDTH: Final[float] = 18.0  # px across the two paint walls that brace a gap (a
#                                                16 px opening spans 17 px wall to wall); a wider shade
#                                                is an area, not a gap between subject parts
SHADED_KEY_MIN_CORE: Final[float] = 1.5        # px half-width of the darkest core: a gap has one, a
#                                                one-pixel key-coloured dot is paint and has none
SHADED_KEY_MIN_EXTENT: Final[float] = 5.0      # px: a thin gap is also a long seam, not a compact dot
SHADED_KEY_MIN_RAMP: Final[float] = 0.12       # share of the key level a shade must span from mouth to
#                                                depth: a crevice ramps, a flat key-like patch does not
# A very dark crevice (a navy-black shadow under a star or a flag) has so little
# key left that its chroma angle and relative lead are noise; the level alone says
# it is shade. It is accepted on a looser hue, and only the geometry tests above
# (walls on both sides, a ramp, clearance from the open key) can promote it.
SHADED_KEY_DEEP_LEVEL: Final[float] = 0.40     # key channel below this share of the key's level
SHADED_KEY_DEEP_LEAD_FRACTION: Final[float] = 0.03  # a deep shade still leads in the key channel
SHADED_KEY_DEEP_MIN_SATURATION: Final[float] = 0.20  # key-channel lead over the pixel's own level: navy is
#                                                    saturated, a slate-grey paint line (mullion) is not
SHADED_KEY_DEEP_MAX_ANGLE: Final[float] = 60.0  # degrees off the key chroma: deep shade is nearly neutral
SHADED_KEY_DEEP_MIN_RAMP: Final[float] = 0.05  # a deep shade is nearly flat navy-black: it need not ramp much
SHADED_KEY_DEEP_MAX_GAP_WIDTH: Final[float] = 60.0  # px wall to wall: the space under a star or a bow
#                                                    is wider than a crack, yet only a deep shade has
#                                                    so little of the key left that it cannot be paint

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
        " Translucent details such as tulle, veils and glass are genuinely "
        "semi-transparent at a stable partial opacity. Whatever lies behind "
        "them — the subject or the exact chroma-key background — remains "
        "clearly visible through their entire area. The chroma-key colour "
        "seen through exposed parts matches the surrounding background "
        "continuously. Keep crisp defined edges and sparse material texture; "
        "never render translucent areas as opaque pastel, white or key-coloured "
        "shapes, haze or glow."
    ),
    "snow_ice": (
        " Snow and ice are opaque with crisp defined edges, no mist, haze, "
        "glitter particles or background-colour glow."
    ),
}


def parse_key_color(value: object) -> tuple[int, int, int]:
    """Parse a named or hex RGB key color."""
    normalized = str(value or "").strip().lower()
    if normalized in KEY_COLORS:
        return KEY_COLORS[normalized]
    if _HEX_COLOR.fullmatch(normalized):
        return tuple(int(normalized[index : index + 2], 16) for index in (1, 3, 5))
    raise ValueError("Цвет chroma key должен быть blue, red, green или #RRGGBB")


def chroma_gap(first: object, second: object) -> float:
    """Angle in degrees between two colours' chroma directions.

    Two samples of one key hue differ by this alone whatever their level, so a
    dark but saturated key still matches its requested colour.
    """
    first = np.asarray(first, dtype=np.float32)
    second = np.asarray(second, dtype=np.float32)
    left = np.array([first[0] - first[1], first[1] - first[2]], dtype=np.float32)
    right = np.array([second[0] - second[1], second[1] - second[2]], dtype=np.float32)
    scale = float(np.linalg.norm(left) * np.linalg.norm(right))
    if scale < 1e-6:
        return 90.0
    return float(np.degrees(np.arccos(np.clip(float(left @ right) / scale, -1.0, 1.0))))


def key_chroma_angle(rgb: np.ndarray, measured_key: np.ndarray) -> np.ndarray:
    """Angle in degrees between every pixel's chroma and the measured key's chroma.

    ``rgb`` and ``measured_key`` may use any common numeric range. Green and red
    keys carry the same construction, so no channel is privileged.
    """
    key_chroma = np.asarray(measured_key, dtype=np.float32)[:2] - np.asarray(
        measured_key, dtype=np.float32
    )[1:]
    pixel_chroma = np.stack(
        (rgb[..., 0] - rgb[..., 1], rgb[..., 1] - rgb[..., 2]),
        axis=-1,
    ).astype(np.float32)
    key_length = max(float(np.linalg.norm(key_chroma)), 1e-6)
    norm = np.linalg.norm(pixel_chroma, axis=-1) * key_length
    cosine = (pixel_chroma @ key_chroma) / np.maximum(norm, 1e-6)
    return np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))


def shaded_key_pocket(rgb: np.ndarray, measured_key: np.ndarray) -> np.ndarray:
    """Background that the generator shaded: dark pockets of the key's own hue in a gap.

    A shaded key sample is a mixture the key's own chromaticity cannot separate
    from an opaque subject detail seen through partial coverage, so this never
    decides on colour alone. The shade must show the key's hue at a level well
    below the key's, lie too far from the solid key to be an anti-aliased edge,
    sit between two paint walls, and ramp from its mouth to its depth: a crevice
    shadow darkens, while a patch painted in one key-like colour does not.
    """
    measured_key = np.asarray(measured_key, dtype=np.float32)
    channel = int(np.argmax(measured_key))
    others = [index for index in range(3) if index != channel]
    other = np.maximum(rgb[..., others[0]], rgb[..., others[1]])
    lead = rgb[..., channel] - other
    key_lead = float(measured_key[channel] - max(measured_key[others[0]], measured_key[others[1]]))
    angle = key_chroma_angle(rgb, measured_key)
    near_background = (
        np.linalg.norm(rgb - measured_key, axis=2)
        < SHADED_KEY_KEY_DISTANCE * max(float(np.linalg.norm(measured_key)), 1e-6)
    )
    hued_shade = (
        (lead >= SHADED_KEY_LEAD_FRACTION * key_lead)
        & (rgb[..., channel] <= SHADED_KEY_MAX_LEVEL * measured_key[channel])
        & (angle <= SHADED_KEY_MAX_ANGLE)
    )
    deep_shade = (
        (lead >= SHADED_KEY_DEEP_LEAD_FRACTION * key_lead)
        & (rgb[..., channel] <= SHADED_KEY_DEEP_LEVEL * measured_key[channel])
        & (angle <= SHADED_KEY_DEEP_MAX_ANGLE)
        & (lead >= SHADED_KEY_DEEP_MIN_SATURATION * rgb[..., channel])
    )
    shade = (hued_shade | deep_shade) & ~near_background
    if not np.any(shade):
        return shade
    # The unshaded key itself, judged against its own level so that a dark key
    # keeps working: only the flat background is an anti-aliased edge reference.
    unshaded = (rgb[..., channel] >= SHADED_KEY_SOLID_LEVEL * measured_key[channel]) & (
        angle <= SHADED_KEY_MAX_ANGLE
    )
    # Shading ramps: a crevice is darker at its deepest point than at its mouth,
    # while a patch painted in one key-like colour does not change level. A shape
    # that never ramps over its whole extent is a painted detail, not a gap.
    paint = angle >= SHADED_KEY_PAINT_ANGLE
    background_clearance = cv2.distanceTransform((~unshaded).astype(np.uint8), cv2.DIST_L2, 5)
    gap_width = _bracketing_paint_width(paint)
    # A gap is a seam: it either has a dark core, or it is a long thin channel.
    # A compact one-pixel key-coloured dot is painted detail, not a gap.
    level = rgb[..., channel]
    thickness = cv2.distanceTransform(shade.astype(np.uint8), cv2.DIST_L2, 5)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(shade.astype(np.uint8), connectivity=8)
    widest = np.zeros(count, np.float32)
    np.maximum.at(widest, labels.ravel(), thickness.ravel())
    extent = np.maximum(stats[:, cv2.CC_STAT_WIDTH], stats[:, cv2.CC_STAT_HEIGHT]).astype(np.float32)
    seam = (widest >= SHADED_KEY_MIN_CORE) | (extent >= SHADED_KEY_MIN_EXTENT)
    lowest = np.full(count, np.inf, np.float32)
    highest = np.full(count, -np.inf, np.float32)
    np.minimum.at(lowest, labels.ravel(), level.ravel())
    np.maximum.at(highest, labels.ravel(), level.ravel())
    min_ramp = np.where(deep_shade, SHADED_KEY_DEEP_MIN_RAMP, SHADED_KEY_MIN_RAMP) * measured_key[channel]
    shadow = (highest - lowest)[labels] >= min_ramp
    return (
        shade
        & seam[labels]
        & shadow
        & (background_clearance > SHADED_KEY_BACKGROUND_CLEARANCE)
        & (gap_width <= np.where(deep_shade, SHADED_KEY_DEEP_MAX_GAP_WIDTH, SHADED_KEY_MAX_GAP_WIDTH))
    )


def _bracketing_paint_width(paint: np.ndarray) -> np.ndarray:
    """Distance across the paint walls that brace every pixel, along the axes.

    A pixel inside a gap between two subject parts is close to paint on two
    opposite sides; a pixel of an anti-aliased subject contour is close on one
    side only. The smaller of the horizontal and vertical spans is returned.
    """
    height, width = paint.shape
    far = np.float32(width + height)
    columns = np.arange(width, dtype=np.float32)[None, :]
    rows = np.arange(height, dtype=np.float32)[:, None]
    to_paint_x = np.where(paint, columns, -far)
    to_paint_y = np.where(paint, rows, -far)
    left = columns - np.maximum.accumulate(to_paint_x, axis=1)
    up = rows - np.maximum.accumulate(to_paint_y, axis=0)
    from_paint_x = np.where(paint, columns, far)
    from_paint_y = np.where(paint, rows, far)
    right = np.minimum.accumulate(from_paint_x[:, ::-1], axis=1)[:, ::-1] - columns
    down = np.minimum.accumulate(from_paint_y[::-1, :], axis=0)[::-1, :] - rows
    return np.minimum(left + right, up + down)


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
    *,
    allow_enclosed_transition_recovery: bool = False,
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
        & (distance_from_key < _MAX_AMBIGUOUS_KEY_DISTANCE)
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
            if touches_subject and suspicious_edge_detail and not enclosed:
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
    # Enclosure alone also describes subpixel gaps between opaque fibres.
    # The opaque profile defers this decision to the colour-checked recovery
    # below; promoting here would erase the coverage evidence it needs.
    if not allow_enclosed_transition_recovery:
        raw_matte[protected_interior_detail] = 1.0
    del protected_interior_detail
    matte = raw_matte.copy()
    if allow_enclosed_transition_recovery:
        matte = _recover_enclosed_transition_matte(
            rgb,
            measured_key,
            raw_matte,
        )
    matte[distance_from_key >= 200.0] = 1.0
    # An enclosed shade of the key is background, not an opaque marker: it must
    # not enter the recovery, and no later stage may raise it again.
    pocket = shaded_key_pocket(rgb, measured_key)
    matte[pocket] = 0.0
    if allow_enclosed_transition_recovery:
        matte = _recover_opaque_texture_matte(rgb, measured_key, matte, background=pocket)
        matte, _ = _extend_opaque_color_runs(rgb, matte, measured_key)
        matte[pocket] = 0.0
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
        # A nearby colour is not necessarily this detail's foreground. Reject
        # unmixing unless it actually reconstructs the observed source pixel.
        predicted = local_foreground + mixture[:, None] * direction
        residual = np.linalg.norm(source_spill - predicted, axis=1)
        despilled = (
            source_spill - mixture[:, None] * measured_key[None, :]
        ) / (1.0 - mixture[:, None])
        # Match the staged solver's reconstruction tolerance for textured
        # neighbours, but never turn an impossible RGB solution into a new hue
        # by clipping its channels. One level allows source quantization.
        supported = (residual <= 18.0) & np.all(
            (despilled >= -1.0) & (despilled <= 256.0), axis=1,
        )
        corrected = source_spill.copy()
        corrected[supported] = despilled[supported]
        pixels[spill, :3] = np.rint(np.clip(corrected, 0.0, 255.0)).astype(
            np.uint8
        )
    pixels[..., 3] = np.minimum(
        pixels[..., 3],
        np.rint(matte * 255.0).astype(np.uint8),
    )
    return Image.fromarray(pixels, mode="RGBA")


def _extend_opaque_color_runs(
    rgb: np.ndarray, matte: np.ndarray, key: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Recover fixed source chroma supported by opaque subject markers.

    Fixed (R-G, G-B) allows achromatic shading, not cumulative hue drift. RGB is
    never copied from a seed. Exact-colour runs are followed first, then a
    recurring pigment may reuse a marker in the same visible subject. The ROI
    accounting cap bounds the run pass; its final traversal may precede the cap.
    """
    markers = cv2.erode((matte == 1.0).astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)
    dubious = _opaque_colors_explained_by_key_mix(rgb, matte, key)
    markers &= ~dubious
    supported = markers.copy()
    if not np.any(markers):
        return matte, supported
    # Two signed byte differences pack losslessly into a float32 integer.
    source = (rgb[..., 0]-rgb[..., 1]+255)*512
    source += rgb[..., 1]-rgb[..., 2]+255
    rows, cols = np.where((matte > 0.02) & ~markers & ~dubious)
    matches = np.isin(source[rows, cols], np.unique(source[markers]), kind='sort')
    rows, cols = rows[matches], cols[matches]
    del matches
    if not len(rows):
        return matte, supported
    matte = matte.copy()
    visited = np.zeros((matte.shape[0]+2, matte.shape[1]+2), np.uint8)
    visited[1:-1, 1:-1][dubious] = 1
    budget = matte.size * _MAX_ENCLOSED_TRANSITION_ROI_WORK_MULTIPLIER
    count = 0
    for y, x in zip(rows, cols):
        if visited[y+1, x+1]:
            continue
        _, _, _, (left, top, width, height) = cv2.floodFill(
            source, visited, (int(x), int(y)), 0,
            loDiff=0, upDiff=0,
            flags=8 | cv2.FLOODFILL_FIXED_RANGE | cv2.FLOODFILL_MASK_ONLY | (2 << 8),
        )
        budget -= width * height
        count += 1
        if budget < 0 or count > 4096:
            break
        region = np.s_[top:top+height, left:left+width]
        mask = visited[top+1:top+height+1, left+1:left+width+1]
        component = mask == 2
        if np.any(markers[region] & component):
            trusted = component & ~dubious[region]
            matte[region][trusted] = 1.0
            supported[region][trusted] = True
        mask[component] = 1
    supported &= ~dubious
    # A recurring pigment can be interrupted by another real subject colour
    # or by AA samples along a thin fibre. Exact-colour flood connectivity is
    # therefore stronger than the opaque-subject evidence requires. Reuse only
    # chroma actually present in an original eroded marker of the same visible
    # subject; never borrow from a disconnected object or infer a new colour.
    # The independent deeper-neighbour mixture veto still excludes fractional
    # openings even when their observed colour also occurs as an opaque pigment.
    del visited
    rows, cols = np.where((matte > 0.02) & (matte < 1.0) & ~dubious)
    if len(rows):
        _, subjects = cv2.connectedComponents(
            (matte > 0.02).astype(np.uint8), connectivity=8,
        )
        # The two signed byte differences occupy fewer than 2**18 values.
        # Pack only marker/candidate samples, not a full int64 image.
        palette = subjects[markers].astype(np.int64) * (1 << 18)
        palette += source[markers].astype(np.int64)
        palette = np.unique(palette)
        candidates = subjects[rows, cols].astype(np.int64) * (1 << 18)
        candidates += source[rows, cols].astype(np.int64)
        recurring = np.isin(candidates, palette, kind='sort')
        # A distant subpixel fibre can have the same observed chroma as a real
        # opaque pigment elsewhere. Reject that ambiguity against the original
        # subject palette too, beyond the local deeper-neighbour veto's reach.
        unambiguous = _unambiguous_recurring_chroma(
            palette, np.unique(candidates[recurring]), key,
            work_limit=matte.size * _MAX_ENCLOSED_TRANSITION_ROI_WORK_MULTIPLIER,
        )
        recurring &= np.isin(candidates, unambiguous, kind='sort')
        matte[rows[recurring], cols[recurring]] = 1.0
        supported[rows[recurring], cols[recurring]] = True
    return matte, supported


def _unambiguous_recurring_chroma(
    palette: np.ndarray, candidates: np.ndarray, key: np.ndarray, *, work_limit: int,
) -> np.ndarray:
    """Reject recurring pigments also explained by another pigment plus key.

    Work is bounded independently of palette complexity. Unexamined candidates
    keep their existing matte; this optional recovery never invents evidence.
    Chroma projection also allows achromatic shading, conservatively rejecting
    more possible mixtures than an RGB-only fit against one brightness sample.
    """
    key_chroma = np.array([key[0]-key[1], key[1]-key[2]], np.float32)
    accepted = []
    for candidate in candidates:
        work_limit -= len(palette)
        if work_limit < 0:
            break
        codes = palette[palette // (1 << 18) == candidate // (1 << 18)] % (1 << 18)
        direction = np.column_stack((codes // 512 - 255, codes % 512 - 255))
        direction = direction.astype(np.float32) - key_chroma
        code = candidate % (1 << 18)
        observed = np.array([code // 512 - 255, code % 512 - 255], np.float32) - key_chroma
        denominator = np.sum(direction * direction, axis=1)
        coverage = np.divide(
            direction @ observed, denominator,
            out=np.zeros_like(denominator), where=denominator > 1.0,
        )
        residual = np.linalg.norm(observed - coverage[:, None] * direction, axis=1)
        if not np.any((denominator > 1.0) & (coverage > .02)
                      & (coverage < .98) & (residual <= 3.0)):
            accepted.append(candidate)
    return np.asarray(accepted, dtype=np.int64)


def _opaque_colors_explained_by_key_mix(
    rgb: np.ndarray, matte: np.ndarray, key: np.ndarray,
) -> np.ndarray:
    """Veto shallow colour seeds using independent, deeper source neighbours.

    A fit only removes trust: key reflection on an opaque surface can have the
    same RGB as partial coverage, so this must not lower alpha by itself.
    """
    opaque = matte == 1.0
    depth = cv2.distanceTransform(opaque.astype(np.uint8), cv2.DIST_L2, 5)
    rows, cols = np.where((matte > 0.02) & (depth <= 12.0))
    dubious = np.zeros(matte.shape, bool)
    if not len(rows):
        return dubious
    _, labels = cv2.connectedComponents((matte > 0.0).astype(np.uint8), connectivity=8)
    observed = rgb[rows, cols]
    found = np.zeros(len(rows), bool)
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            yy = np.clip(rows+dy, 0, matte.shape[0]-1)
            xx = np.clip(cols+dx, 0, matte.shape[1]-1)
            direction = rgb[yy, xx]-key
            denominator = np.sum(direction*direction, axis=1)
            coverage = np.divide(
                np.sum((observed-key)*direction, axis=1), denominator,
                out=np.zeros_like(denominator), where=denominator > 1.0,
            )
            residual = np.linalg.norm(observed-(key+coverage[:, None]*direction), axis=1)
            found |= (opaque[yy, xx] & (depth[yy, xx] > depth[rows, cols]+0.5)
                      & (labels[yy, xx] == labels[rows, cols])
                      & (denominator > _MIN_OPAQUE_REFERENCE_DISTANCE**2)
                      & (coverage >= 0.1) & (coverage <= 0.95) & (residual <= 3.0))
    dubious[rows, cols] = found
    return dubious


def _recover_opaque_texture_matte(
    rgb: np.ndarray, key: np.ndarray, matte: np.ndarray,
    *, background: np.ndarray | None = None,
) -> np.ndarray:
    """Recover opaque texture markers without flattening the outer AA band.

    Only the opaque-subject profile calls this. Enclosed coverage dips, narrow
    strokes bracketed by opaque samples, and flat separated colour patches are
    foreground evidence. The actual outer band still needs a colour-mixture fit.
    ``background`` names pixels already known to be background (a shaded key
    pocket); their colour is numerically far from the key yet cannot serve as an
    opaque marker, so they are excluded from the marker and support tests while
    still counting as neighbourhood for the depth transform.
    """
    distance_squared = np.zeros(matte.shape, np.float32)
    for channel in range(3):
        delta = rgb[..., channel] - key[channel]
        distance_squared += delta * delta
    separated = distance_squared >= _MIN_OPAQUE_REFERENCE_DISTANCE ** 2
    del distance_squared, delta
    if background is None:
        background = np.zeros(matte.shape, bool)
    else:
        separated &= ~background
    support = (matte > 0.02) | separated | background
    _, subject_labels = cv2.connectedComponents(support.astype(np.uint8), connectivity=8)
    depth = cv2.distanceTransform(support.astype(np.uint8), cv2.DIST_L2, 5)
    core = (matte == 1.0) & (depth > 3.0)
    if not np.any(core):
        return matte

    def project(reference_mask, candidates):
        _, labels = cv2.distanceTransformWithLabels(
            (~reference_mask).astype(np.uint8), cv2.DIST_L2, 5,
            labelType=cv2.DIST_LABEL_PIXEL,
        )
        lookup = np.zeros((int(labels.max()) + 1, 3), np.float32)
        lookup[labels[reference_mask]] = rgb[reference_mask]
        reference = lookup[labels[candidates]]
        component_lookup = np.zeros(len(lookup), np.int32)
        component_lookup[labels[reference_mask]] = subject_labels[reference_mask]
        same_component = component_lookup[labels[candidates]] == subject_labels[candidates]
        observed = rgb[candidates]
        direction = reference - key
        denominator = np.sum(direction * direction, axis=1)
        coverage = np.divide(np.sum((observed-key)*direction, axis=1), denominator,
                             out=np.zeros_like(denominator), where=denominator > 1)
        residual = np.linalg.norm(observed-(key+coverage[:, None]*direction), axis=1)
        residual[~same_component] = np.inf
        return coverage, residual

    partial = support & (matte < 1.0)
    count, components = cv2.connectedComponents(partial.astype(np.uint8), connectivity=8)
    touches_edge = np.zeros(count, bool)
    touches_edge[np.unique(components[depth <= 3.0])] = True
    protected = partial & ~touches_edge[components] & separated
    # A flat, numerically separated colour patch is a foreground marker under
    # the opaque-subject contract. Smooth AA ramps are not such markers.
    kernel = np.ones((3, 3), np.uint8)
    flat = np.ones(matte.shape, bool)
    for channel in range(3):
        flat &= cv2.dilate(rgb[..., channel], kernel) - cv2.erode(rgb[..., channel], kernel) <= 1.0
    protected |= partial & (depth > 3.0) & separated & flat
    # Narrow texture strokes can connect an interior patch to the outer band.
    # Opaque samples on opposing sides distinguish them from a one-sided rim.
    padded = np.pad(core, 3)
    height, width = matte.shape
    bridged = np.zeros(matte.shape, bool)
    for dy, dx in ((0, 3), (3, 0), (2, 2), (2, -2)):
        bridged |= (padded[3+dy:3+dy+height, 3+dx:3+dx+width]
                    & padded[3-dy:3-dy+height, 3-dx:3-dx+width])
    protected |= partial & (depth > 3.0) & separated & bridged
    if np.any(protected):
        coverage, residual = project(core, protected)
        explained_coverage = (coverage > 0.02) & (coverage < 0.98) & (residual <= 5.0)
        retained = protected[protected]
        retained[explained_coverage] = False
        protected[protected] = retained
    if not np.any(protected):
        return matte
    matte = matte.copy()
    matte[protected] = 1.0
    # Newly established opaque colours provide references for their own AA rim.
    nearby = cv2.dilate(protected.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)
    partial &= ~protected & nearby
    coverage, residual = project(core | protected, partial)
    solved = (residual <= 5.0) & (coverage > 0.02) & (coverage <= 1.02)
    values = matte[partial]
    values[solved] = np.maximum(values[solved], np.minimum(coverage[solved], 1.0))
    matte[partial] = values
    # A closer different-colour detail must not hide an exact opaque match.
    rows, cols = np.where(partial & (matte < 1.0))
    references = core | protected
    same_colour = np.zeros(len(rows), bool)
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            yy = np.clip(rows + dy, 0, matte.shape[0]-1)
            xx = np.clip(cols + dx, 0, matte.shape[1]-1)
            same_colour |= references[yy, xx] & (
                np.max(np.abs(rgb[rows, cols] - rgb[yy, xx]), axis=1) <= 1.0
            ) & (subject_labels[yy, xx] == subject_labels[rows, cols])
    matte[rows[same_colour], cols[same_colour]] = 1.0
    return matte


def _recover_enclosed_transition_matte(
    rgb: np.ndarray,
    measured_key: np.ndarray,
    raw_matte: np.ndarray,
) -> np.ndarray:
    """Solve enclosed near-key subject regions from their local opaque colour.

    Channel dominance alone underestimates alpha for a legitimate foreground
    whose strongest channel happens to be the key channel.  A component which
    is enclosed by definite background has a different topological signal: its
    least-key-like samples provide a local foreground reference.  Only accept
    the two-colour solve when every repaired sample fits that local reference;
    otherwise retain the conservative dominance matte.  In particular, the
    reference must be at least 96 RGB units away from the key. This is a
    numerical-separation heuristic, not proof that the reference is opaque;
    opacity is the caller's profile assumption. Distance transforms run only
    on component bounding boxes, and their cumulative area is capped at four
    source-image areas; unprocessed components retain the conservative matte.
    """
    candidate = raw_matte > 0.02
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(
        candidate.astype(np.uint8),
        connectivity=8,
    )
    matte = raw_matte.copy()
    height, width = raw_matte.shape
    component_limit = max(
        _MIN_AMBIGUOUS_COMPONENT_LIMIT,
        int(height * width * _MAX_AMBIGUOUS_COMPONENT_DENSITY),
    )
    if component_count - 1 > component_limit:
        return matte
    roi_work_budget = height * width * _MAX_ENCLOSED_TRANSITION_ROI_WORK_MULTIPLIER
    roi_work = 0

    for component_id in range(1, component_count):
        left, top, component_width, component_height, area = stats[component_id]
        if area < 9:
            continue
        if (
            left == 0
            or top == 0
            or left + component_width == width
            or top + component_height == height
        ):
            continue

        region = np.s_[top : top + component_height, left : left + component_width]
        component = labels[region] == component_id
        local_matte = raw_matte[region]
        peak = float(np.max(local_matte[component]))
        if peak < 0.55 or peak >= 0.995:
            continue
        reference = component & (local_matte >= peak - 0.025)
        local_rgb = rgb[region]
        reference &= (
            np.linalg.norm(local_rgb - measured_key[None, None, :], axis=2)
            >= _MIN_OPAQUE_REFERENCE_DISTANCE
        )
        if not np.any(reference):
            continue
        roi_area = component_width * component_height
        if roi_work + roi_area > roi_work_budget:
            break
        roi_work += roi_area

        _, nearest = cv2.distanceTransformWithLabels(
            (~reference).astype(np.uint8),
            cv2.DIST_L2,
            5,
            labelType=cv2.DIST_LABEL_PIXEL,
        )
        reference_labels = nearest[reference]
        component_labels = nearest[component]
        local_foreground = np.empty(
            (int(np.count_nonzero(component)), 3),
            dtype=np.float32,
        )
        for channel in range(3):
            lookup = np.zeros(int(nearest.max()) + 1, dtype=np.float32)
            lookup[reference_labels] = local_rgb[..., channel][reference]
            local_foreground[:, channel] = lookup[component_labels]

        source_color = local_rgb[component]
        direction = local_foreground - measured_key[None, :]
        denominator = np.sum(direction * direction, axis=1)
        alpha = np.divide(
            np.sum((source_color - measured_key[None, :]) * direction, axis=1),
            denominator,
            out=np.zeros_like(denominator),
            where=denominator > 1e-6,
        )
        predicted = measured_key[None, :] + alpha[:, None] * direction
        residual = np.linalg.norm(source_color - predicted, axis=1)
        solved = (
            (alpha >= 0.04)
            & (alpha <= 1.02)
            & (residual <= 5.0)
            & (alpha >= local_matte[component] - 0.02)
        )
        if np.any(solved):
            component_matte = matte[region]
            component_matte = component_matte[component]
            component_matte[solved] = np.clip(alpha[solved], 0.0, 1.0)
            restored_region = matte[region]
            restored_region[component] = component_matte

    return matte


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


def _prefer_local_subject_reference(
    rgb: np.ndarray, subject_mask: np.ndarray, reference: np.ndarray, key: np.ndarray,
    *, validate_material_fallback: bool = False,
) -> None:
    """Prefer a nearby interior sample over an average of different materials.

    A deep Gaussian reference can blend a white petal with its yellow centre.
    Use source RGB from a two-pixel interior of the same connected subject,
    within twelve pixels only. Where that evidence is absent, retain the
    existing reference. Check the sample against actual deeper neighbours,
    allowing brightness changes, rather than against another mixed average.
    Only a three-pixel contour band can receive a different reference.
    This function changes neither source RGB nor coverage. The opaque paint
    policy also checks whether the retained fallback explains the local sample.
    """
    core = cv2.erode(subject_mask.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    if not np.any(core):
        return
    depth = cv2.distanceTransform(subject_mask.astype(np.uint8), cv2.DIST_L2, 5)
    distance, labels = cv2.distanceTransformWithLabels(
        (~core).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL,
    )
    _, components = cv2.connectedComponents(subject_mask.astype(np.uint8), connectivity=8)
    lookup = np.zeros(int(labels.max()) + 1, np.int32)
    lookup[labels[core]] = components[core]
    nearby = (distance <= 12.0) & (depth <= 3.0) & (lookup[labels] == components) & subject_mask
    if not np.any(nearby):
        return
    # Transition samples retain their existing shallow colour references.
    rows, cols = np.where(core)
    lookup[labels[core]] = rows
    sample_y = lookup[labels[nearby]].copy()
    lookup[labels[core]] = cols
    sample_x = lookup[labels[nearby]].copy()
    local = rgb[sample_y, sample_x]
    contaminated = np.zeros(len(local), bool)
    kk = float(key @ key)
    ck = local @ key
    def reject_mixture(neighbour, deeper):
        ff = np.sum(neighbour * neighbour, axis=1)
        fk = neighbour @ key
        cf = np.sum(local * neighbour, axis=1)
        determinant = ff * kk - fk * fk
        stable = determinant > 0.01 * ff * kk
        scale = np.divide(cf * kk - ck * fk, determinant,
                          out=np.zeros_like(cf), where=stable)
        mixture = np.divide(ck * ff - cf * fk, determinant,
                            out=np.zeros_like(ck), where=stable)
        residual = np.max(np.abs(local - (scale[:, None] * neighbour
                                         + mixture[:, None] * key)), axis=1)
        # Allow quantisation and mild texture, but not a different material's
        # non-key hue. A fixed large tolerance admits white petals as yellow
        # pigment plus blue; a fixed tiny tolerance misses textured key spill.
        tolerance = np.minimum(12.0, 1.0 + 0.04 * scale * np.max(neighbour, axis=1))
        recovered = (local - mixture[:, None] * key) / np.maximum(1.0 - mixture[:, None], 0.01)
        # An out-of-gamut coverage fit could also mean additive light spill,
        # but is indistinguishable here from genuine bright paint. Preserve
        # the local colour rather than subtracting key on that assumption.
        in_gamut = np.all((recovered >= -2.0) & (recovered <= 257.0), axis=1)
        return (deeper & stable & (scale > 0.0) & (mixture > 0.03)
                & (mixture < 1.0) & (residual <= tolerance) & in_gamut)

    for dy in range(-3, 4):
        for dx in range(-3, 4):
            yy = np.clip(sample_y + dy, 0, rgb.shape[0] - 1)
            xx = np.clip(sample_x + dx, 0, rgb.shape[1] - 1)
            deeper = (subject_mask[yy, xx]
                      & (depth[yy, xx] > depth[sample_y, sample_x] + 0.5)
                      & (components[yy, xx] == components[sample_y, sample_x]))
            contaminated |= reject_mixture(rgb[yy, xx], deeper)
    # A wider contaminated rim can hide the clean subject beyond the local
    # window. Check actual deeper source samples too, never a colour average.
    maximum_depth = np.zeros(int(components.max()) + 1, np.float32)
    np.maximum.at(maximum_depth, components.ravel(), depth.ravel())
    for minimum_depth in (6.0, 12.0, 24.0, 32.0, None):
        deeper_core = subject_mask & (
            depth >= maximum_depth[components] - 0.5
            if minimum_depth is None else depth > minimum_depth
        )
        if not np.any(deeper_core):
            continue
        distances, nearest = cv2.distanceTransformWithLabels(
            (~deeper_core).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL,
        )
        nearest_ids = nearest[sample_y, sample_x]
        ys, xs = np.where(deeper_core)
        positions = np.zeros(int(nearest.max()) + 1, np.int32)
        positions[nearest[deeper_core]] = ys
        yy = positions[nearest_ids].copy()
        positions[nearest[deeper_core]] = xs
        xx = positions[nearest_ids]
        deeper = ((distances[sample_y, sample_x] <= 32.0)
                  & (depth[yy, xx] > depth[sample_y, sample_x] + 0.5)
                  & (components[yy, xx] == components[sample_y, sample_x]))
        contaminated |= reject_mixture(rgb[yy, xx], deeper)
    if validate_material_fallback:
        # A deeper donor can explain the local sample without establishing that
        # the Gaussian fallback belongs to that material. Reject a local prior
        # only when the fallback itself passes the same mixture/gamut checks.
        contaminated &= reject_mixture(reference[nearby], np.ones(len(local), bool))
    values = reference[nearby]
    values[~contaminated] = local[~contaminated]
    reference[nearby] = values


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
    *, preserve_local_material: bool = False,
) -> Image.Image:
    """Recover localized key reflections inside an otherwise opaque subject.

    The opaque clipart policy checks local material before borrowing a distant
    key-poor colour. A pale petal is not spill merely because its centre is yellow.
    """
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
    del border
    if not preserve_local_material:
        del source_rgb

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

    if preserve_local_material:
        local_reference = np.zeros_like(rgb)
        local_reference[suspected_spill] = reference
        _prefer_local_subject_reference(
            source_rgb, subject, local_reference, measured_key, validate_material_fallback=True,
        )
        reference = local_reference[suspected_spill]
        del source_rgb, local_reference
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


def _refine_opaque_boundary(
    source: Image.Image,
    result: Image.Image,
    measured_key: np.ndarray,
) -> Image.Image:
    """Unmix narrow AA coverage using a nearby opaque interior reference.

    Never reinterpret fully opaque colours. Beyond the immediate rim require
    agreement between two interior depths in the same connected subject.
    This is a bounded local correction, not a material-opacity estimator.
    """
    pixels = np.asarray(result.convert("RGBA"), dtype=np.uint8)
    partial = (pixels[..., 3] > 0) & (pixels[..., 3] < 255)
    if not np.any(partial):
        return result
    core = cv2.erode(
        (pixels[..., 3] == 255).astype(np.uint8),
        np.ones((3, 3), dtype=np.uint8),
    ).astype(bool)
    if not np.any(core):
        return result
    distance, nearest = cv2.distanceTransformWithLabels(
        (~core).astype(np.uint8), cv2.DIST_L2, 5,
        labelType=cv2.DIST_LABEL_PIXEL,
    )
    source_pixels = np.asarray(source.convert("RGBA"), dtype=np.uint8)
    edge = partial & (distance <= 12.0) & (source_pixels[..., 3] == 255)
    if not np.any(edge):
        return result
    foreground = np.empty((int(np.count_nonzero(edge)), 3), dtype=np.float32)
    lookup = np.zeros(int(nearest.max()) + 1, dtype=np.float32)
    core_labels, edge_labels = nearest[core], nearest[edge]
    for channel in range(3):
        lookup[core_labels] = pixels[..., channel][core]
        foreground[:, channel] = lookup[edge_labels]
    _, components = cv2.connectedComponents((pixels[..., 3] > 0).astype(np.uint8))
    component_lookup = np.zeros(len(lookup), np.int32)
    component_lookup[core_labels] = components[core]
    supported = component_lookup[edge_labels] == components[edge]
    far = distance[edge] > 3.0
    del distance, nearest, lookup, core_labels, edge_labels, component_lookup
    if np.any(far):
        deep = cv2.erode(core.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
        if np.any(deep):
            _, labels = cv2.distanceTransformWithLabels(
                (~deep).astype(np.uint8), cv2.DIST_L2, 5,
                labelType=cv2.DIST_LABEL_PIXEL,
            )
            lookup = np.zeros((int(labels.max()) + 1, 3), np.float32)
            lookup[labels[deep]] = pixels[..., :3][deep]
            second = lookup[labels[edge][far]]
            component_lookup = np.zeros(len(lookup), np.int32)
            component_lookup[labels[deep]] = components[deep]
            supported[far] &= (
                (component_lookup[labels[edge][far]] == components[edge][far])
                & (np.max(np.abs(foreground[far] - second), axis=1) <= 6.0)
            )
            del labels, lookup, second, component_lookup
        else:
            supported[far] = False
        del deep
    del components
    observed = source_pixels[..., :3][edge].astype(np.float32)
    direction = foreground - measured_key
    denominator = np.sum(direction * direction, axis=1)
    alpha = np.divide(
        np.sum((observed - measured_key) * direction, axis=1), denominator,
        out=np.zeros_like(denominator), where=denominator > 1.0,
    )
    residual = np.linalg.norm(observed - (measured_key + alpha[:, None] * direction), axis=1)
    reliable = supported & (denominator > 2500.0) & (residual < 4.0) & (alpha > 0.02) & (alpha < 1.0)
    reliable[far] &= (denominator[far] > 96.0**2) & (residual[far] <= 3.0)
    recovered = (observed - (1.0 - alpha[:, None]) * measured_key) / np.maximum(alpha[:, None], 0.001)
    reliable[far] &= np.all((recovered[far] >= -1.0) & (recovered[far] <= 256.0), axis=1)
    # A solved shaded edge must not be projected onto the brighter core again.
    # Source consistency alone can also accept a wrong, key-tinted foreground;
    # require the existing RGB to share the reference's chromaticity as well.
    # Allow the small alpha drift from staged cleanup, then refit coverage from
    # the existing paint instead of changing its brightness or hue.
    current_rgb = pixels[edge, :3].astype(np.float32)
    current_direction = current_rgb - measured_key
    current_denominator = np.sum(current_direction * current_direction, axis=1)
    current_coverage = np.divide(
        np.sum((observed - measured_key) * current_direction, axis=1), current_denominator,
        out=np.zeros_like(current_denominator), where=current_denominator > 1.0,
    )
    current_error = np.max(np.abs(
        observed - (measured_key + current_coverage[:, None] * current_direction)
    ), axis=1)
    brightness = np.sum(current_rgb * foreground, axis=1) / np.maximum(
        np.sum(foreground * foreground, axis=1), 1.0,
    )
    shade_error = np.max(np.abs(current_rgb - brightness[:, None] * foreground), axis=1)
    explained_shade = (
        reliable & (current_denominator > 2500.0)
        & (current_coverage > 0.02) & (current_coverage < 1.0)
        & (current_error <= 2.0) & (shade_error <= 2.0)
        & (np.abs(current_coverage - pixels[edge, 3] / 255.0) <= 0.03)
    )
    if not np.any(reliable):
        return result
    corrected = pixels[edge].copy()
    corrected[reliable, :3] = np.rint(np.clip(recovered[reliable], 0.0, 255.0)).astype(np.uint8)
    corrected[reliable, 3] = np.rint(alpha[reliable] * 255.0).astype(np.uint8)
    corrected[explained_shade, :3] = pixels[edge, :3][explained_shade]
    corrected[explained_shade, 3] = np.rint(current_coverage[explained_shade] * 255.0).astype(np.uint8)
    pixels = pixels.copy()
    pixels[edge] = corrected
    return Image.fromarray(pixels, mode="RGBA")


def _preserve_fully_opaque_source_rgb(
    source: Image.Image,
    result: Image.Image,
    *,
    measured_key: np.ndarray | None = None,
) -> Image.Image:
    """Keep original colour where keying found no background contribution."""
    pixels = np.asarray(result.convert("RGBA"), dtype=np.uint8).copy()
    fully_opaque = pixels[..., 3] == 255
    if not np.any(fully_opaque):
        return result
    distance_from_edge = cv2.distanceTransform(
        fully_opaque.astype(np.uint8),
        cv2.DIST_L2,
        3,
    )
    opaque_interior = fully_opaque & (distance_from_edge > 6.0)
    source_rgb = np.asarray(source.convert("RGB"), dtype=np.uint8)
    if measured_key is not None and np.any(opaque_interior):
        opaque_interior &= ~_supported_rim_correction(
            source_rgb, pixels, measured_key, distance_from_edge,
        )
    pixels[..., :3][opaque_interior] = source_rgb[opaque_interior]
    return Image.fromarray(pixels, mode="RGBA")


def _supported_rim_correction(
    source_rgb: np.ndarray,
    cleaned: np.ndarray,
    key: np.ndarray,
    depth: np.ndarray,
) -> np.ndarray:
    """Keep an existing correction only for a bounded, edge-connected key mix.

    Colour similarity alone is not evidence for recolouring an interior detail.
    Require the source to reconstruct from the cleaned colour plus measured key,
    and the corrected region to reach the boundary. This never invents new RGB
    or alpha: it prevents source restoration from undoing supported rim cleanup.
    """
    limit = min(32.0, max(8.0, min(depth.shape) / 16.0))
    candidate = (cleaned[..., 3] > 0) & (depth <= limit)
    supported = np.zeros(depth.shape, dtype=bool)
    if not np.any(candidate):
        return supported
    foreground = cleaned[..., :3][candidate].astype(np.float32)
    observed = source_rgb[candidate].astype(np.float32)
    direction = key - foreground
    denominator = np.sum(direction * direction, axis=1)
    mixture = np.divide(
        np.sum((observed - foreground) * direction, axis=1), denominator,
        out=np.zeros_like(denominator), where=denominator > 1.0,
    )
    residual = np.linalg.norm(observed - (foreground + mixture[:, None] * direction), axis=1)
    supported[candidate] = (
        (denominator >= _MIN_OPAQUE_REFERENCE_DISTANCE ** 2)
        & (mixture >= 0.03) & (mixture <= 0.65) & (residual <= 3.0)
    )
    _, labels = cv2.connectedComponents(supported.astype(np.uint8), connectivity=8)
    boundary_labels = np.unique(labels[supported & (depth <= 2.0)])
    if not len(boundary_labels):
        return np.zeros(depth.shape, dtype=bool)
    connected = np.zeros(int(labels.max()) + 1, dtype=bool)
    connected[boundary_labels] = True
    return supported & connected[labels]


def _supported_key_edge(
    rgb: np.ndarray, alpha: np.ndarray, measured_key: np.ndarray,
) -> np.ndarray:
    """Find a narrow key-coloured rim beside a connected non-key interior.

    An enclosure is not enough to turn a solved key mixture into an opaque
    detail. Require a nearby eroded foreground reference before retaining the
    staged solution. Key-coloured subjects without this evidence are excluded.
    """
    key_channel = int(np.argmax(measured_key))
    other_channels = [channel for channel in range(3) if channel != key_channel]
    dominance = rgb[..., key_channel] - np.maximum(
        rgb[..., other_channels[0]], rgb[..., other_channels[1]],
    )
    reference = cv2.erode(
        ((alpha == 1.0) & (dominance <= 0.0)).astype(np.uint8),
        np.ones((3, 3), np.uint8),
    ).astype(bool)
    if not np.any(reference):
        return np.zeros(alpha.shape, bool)
    visible = alpha > 0.0
    # A flat, key-separated painted patch is a colour detail, even near the
    # contour. Protect its one-pixel border as well as its flat interior.
    kernel = np.ones((3, 3), np.uint8)
    flat = np.ones(alpha.shape, bool)
    for channel in range(3):
        flat &= (
            cv2.dilate(rgb[..., channel], kernel)
            - cv2.erode(rgb[..., channel], kernel) <= 1.0
        )
    key_distance = np.linalg.norm(rgb - measured_key, axis=2)
    flat &= visible & (dominance > 20.0) & (key_distance >= _MIN_OPAQUE_REFERENCE_DISTANCE)
    painted_detail = cv2.dilate(flat.astype(np.uint8), kernel).astype(bool)
    del flat
    # An enclosed dark/blue marking may have a provisional hole in its matte.
    # It is not evidence of the external key background (for example an eye).
    count, background_labels = cv2.connectedComponents(
        (~visible).astype(np.uint8), connectivity=8,
    )
    exterior_labels = np.unique(np.concatenate((
        background_labels[0], background_labels[-1],
        background_labels[:, 0], background_labels[:, -1],
    )))
    exterior = np.zeros(count, bool)
    exterior[exterior_labels] = True
    exterior[0] = False
    background = exterior[background_labels]
    del background_labels, exterior, exterior_labels
    # Real enclosed gaps can also provide background evidence if their RGB
    # matches the measured key; a dark painted mark does not satisfy this.
    background |= (~visible) & (key_distance <= 24.0)
    # A nearby painted blue mark is not a background mixture merely because
    # a pale reference exists. Require a source-colour path to actual key.
    count, key_labels = cv2.connectedComponents(
        ((dominance > 20.0) | background).astype(np.uint8), connectivity=8,
    )
    connected = np.zeros(count, bool)
    connected[np.unique(key_labels[background])] = True
    connected[0] = False
    key_connected = connected[key_labels]
    del connected, key_labels
    depth = cv2.distanceTransform((~background).astype(np.uint8), cv2.DIST_L2, 5)
    del background
    candidates = visible & (depth <= 8.0) & (dominance > 20.0) & ~painted_detail & key_connected
    del depth, dominance, painted_detail, key_distance, key_connected
    if not np.any(candidates):
        return candidates
    distance, nearest = cv2.distanceTransformWithLabels(
        (~reference).astype(np.uint8), cv2.DIST_L2, 5,
        labelType=cv2.DIST_LABEL_PIXEL,
    )
    candidates &= distance <= 8.0
    del distance
    _, components = cv2.connectedComponents(visible.astype(np.uint8), connectivity=8)
    lookup = np.zeros(int(nearest.max()) + 1, np.int32)
    lookup[nearest[reference]] = components[reference]
    candidates &= lookup[nearest] == components
    return candidates


def _remove_chroma_key_staged(
    image: Image.Image,
    key_color: object,
    *,
    opaque_subject: bool = False,
) -> Image.Image:
    """Robust fallback for detailed subjects and compressed key backgrounds."""
    requested_key = np.asarray(parse_key_color(key_color), dtype=np.float32)
    source = image.convert("RGBA")
    pixels = np.asarray(source, dtype=np.uint8).copy()
    rgb = pixels[..., :3].astype(np.float32)
    preserve_local_material = opaque_subject and bool(np.all(pixels[..., 3] == 255))
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
    # Shading inside narrow gaps is background whatever the coverage solve and the
    # texture recovery make of it; the mask is taken from the untouched source.
    pocket = shaded_key_pocket(rgb, measured_key)

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

    early_rim = np.zeros((height, width), dtype=bool)
    if opaque_subject:
        band_reference = reference[transition].copy()
        # Build the colour prior before solving the band. The shallow average
        # can itself contain key contamination on fine feathers.
        reference_ratio = np.zeros((height, width), dtype=np.float32)
        _apply_multiscale_subject_reference(
            rgb, confident_subject, key_channel, other_channels,
            reference, reference_ratio,
        )
        _prefer_local_subject_reference(
            rgb, confident_subject, reference, measured_key,
            validate_material_fallback=preserve_local_material,
        )
        reference_other = np.maximum(
            reference[..., other_channels[0]], reference[..., other_channels[1]],
        )
        reference_ratio = reference[..., key_channel] / np.maximum(reference_other, 1.0)
        depth = cv2.distanceTransform(confident_subject.astype(np.uint8), cv2.DIST_L2, 5)
        early_rim = (confident_subject & (depth <= 3.0)
                     & (pixels[..., 3] == 255)
                     & (dominant > reference_ratio * other + 24.0))
        # Colour changes perpendicular to the reference/key plane indicate a
        # different material, not background contamination.
        observed = rgb[early_rim]
        foreground = reference[early_rim]
        kk = float(measured_key @ measured_key)
        ff = np.sum(foreground * foreground, axis=1)
        fk = foreground @ measured_key
        cf = np.sum(observed * foreground, axis=1)
        ck = observed @ measured_key
        determinant = ff * kk - fk * fk
        stable = determinant > .01 * ff * kk
        scale = np.divide(cf * kk - ck * fk, determinant,
                          out=np.zeros_like(cf), where=stable)
        mixture = np.divide(ck * ff - cf * fk, determinant,
                            out=np.zeros_like(ck), where=stable)
        residual = np.max(np.abs(observed - scale[:, None] * foreground
                                 - mixture[:, None] * measured_key), axis=1)
        early_rim[early_rim] = (stable & (scale > 0.0) & (mixture > 0.0)
                                & (residual <= 24.0)
                                & ~ambiguous_pale_material(observed, mixture, measured_key))
        # Thin leaves/stems may have a different colour from the deep core of
        # their connected flower. Keep their original local band references.
        reference[transition] = band_reference
        confident_subject &= ~early_rim
        transition |= early_rim
        del reference_ratio, reference_other, depth, observed, foreground
        del ff, fk, cf, ck, determinant, stable, scale, mixture, residual
        del band_reference

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
                if opaque_subject:
                    # The foreground coefficient also contains brightness.
                    # Separate additive spill when 1-background would force
                    # impossible RGB and clip a feather into a bright fringe.
                    subject_amount = mixture_coverage(
                        source_color, subject_amount, background_amount, measured_key,
                    )
                tile_alpha = alpha[tile]
                tile_alpha[solved] = subject_amount
                foreground_signal = (
                    source_color
                    - background_amount[:, None] * measured_key[None, :]
                )
                solved_rgb = foreground_signal / np.maximum(subject_amount[:, None], 0.05)
                if opaque_subject:
                    # A valid weak coverage sample still carries its full paint
                    # colour. The 0.05 numerical floor must not darken it before
                    # later stages restore coverage. Keep the historical floor
                    # for clipped/additive fits, supplied alpha and discarded noise.
                    weak = ((subject_amount > 0.025) & (subject_amount < 0.05)
                            & (np.abs(subject_amount + background_amount - 1.0) < 1e-4)
                            & (pixels[tile][solved, 3] == 255))
                    if np.any(weak):
                        recovered = foreground_signal[weak] / subject_amount[weak, None]
                        # Subtraction/division in float32 may put valid black or
                        # saturated paint just outside the gamut. Allow only
                        # numerical roundoff, below 0.005 RGB levels in this band,
                        # and clamp it before later stages test source consistency.
                        roundoff = (4.0 * np.finfo(np.float32).eps * 255.0
                                    / subject_amount[weak, None])
                        valid = np.all(
                            np.isfinite(recovered)
                            & (recovered >= -roundoff)
                            & (recovered <= 255.0 + roundoff), axis=1,
                        )
                        indices = np.flatnonzero(weak)[valid]
                        solved_rgb[indices] = np.clip(recovered[valid], 0.0, 255.0)
                tile_rgb[solved] = solved_rgb
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
    if opaque_subject:
        _prefer_local_subject_reference(
            rgb, confident_subject, reference, measured_key,
            validate_material_fallback=preserve_local_material,
        )
        reference_other = np.maximum(
            reference[..., other_channels[0]], reference[..., other_channels[1]],
        )
        edge_reference_ratio = np.clip(
            reference[..., key_channel] / np.maximum(reference_other, 1.0), 0.05, 1.2,
        )
    del confident_subject

    if opaque_subject:
        original_rgb = pixels[..., :3].astype(np.float32)
        # Retain solved boundary mixtures before opaque texture recovery.
        # Restoring their source RGB would also restore the removed key colour.
        key_edge = _supported_key_edge(original_rgb, alpha, measured_key) | early_rim
        key_edge_rgb = rgb[key_edge].copy()
        key_edge_alpha = alpha[key_edge].copy()
        alpha[pocket] = 0.0
        recovered_alpha = _recover_opaque_texture_matte(
            original_rgb, measured_key, alpha, background=pocket,
        )
        recovered_alpha, opaque_runs = _extend_opaque_color_runs(original_rgb, recovered_alpha, measured_key)
        # A confirmed gap stays background: neither recovery may rebuild opacity on it.
        recovered_alpha[pocket] = 0.0
        changed = (recovered_alpha > alpha) & (recovered_alpha < 1.0)
        rgb[changed] = (
            original_rgb[changed] - (1-recovered_alpha[changed, None])*measured_key
        ) / recovered_alpha[changed, None]
        alpha = recovered_alpha
        opaque = alpha == 1.0
        rgb[opaque] = original_rgb[opaque]
        alpha[key_edge] = key_edge_alpha
        rgb[key_edge] = key_edge_rgb
        alpha[pocket] = 0.0
        # Transparent pixels keep the source colour, as in the precise profile; the
        # matting extends a visible neighbour colour over them.
        rgb[pocket] = original_rgb[pocket]
        del key_edge_rgb, key_edge_alpha
        del original_rgb, opaque, recovered_alpha, changed
    elif np.any(pocket):
        alpha[pocket] = 0.0

    # Float noise (~1e-8) differs between CPU SIMD paths; without snapping it flips the
    # exact `alpha > 0.0` edge test and the whole result changes from machine to machine.
    alpha[alpha < _ALPHA_NOISE_FLOOR] = 0.0
    soft_edge = (alpha > 0.0) & (alpha < 0.999)
    edge_ring = cv2.dilate(
        soft_edge.astype(np.uint8),
        np.ones((3, 3), dtype=np.uint8),
        iterations=max(8, min(height, width) // 128),
    ).astype(bool) & (alpha > 0.0)
    if opaque_subject:
        opaque_depth = cv2.distanceTransform((alpha == 1.0).astype(np.uint8), cv2.DIST_L2, 5)
        edge_ring &= opaque_depth <= 3.0
        edge_ring &= ~opaque_runs
        # Preserve established interior colours. The supported key rim is the
        # exception: its source RGB still contains background contamination.
        edge_ring &= (alpha < 1.0) | key_edge
        del opaque_depth
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
            if opaque_subject and np.any(tile_edge):
                coverage = alpha[tile][tile_edge]
                foreground = rgb[tile][tile_edge]
                reconstructed = (coverage[:, None] * foreground
                                 + (1.0 - coverage[:, None]) * measured_key)
                # The matte already unmixed these ordinary coverage samples.
                # A darker painted edge can fit the brighter core/key plane
                # again, but that is not evidence of another layer of spill.
                # Float32 unmixing can overshoot a valid RGB endpoint slightly.
                # Keep this numerical allowance below 0.005 RGB levels and only
                # for opaque source pixels; real clipped fits still get despill.
                roundoff = np.where(
                    pixels[tile][tile_edge, 3] == 255,
                    4.0 * np.finfo(np.float32).eps * 255.0 / np.maximum(coverage, 0.025),
                    0.0,
                )[:, None]
                explained = (
                    (coverage > 0.0) & (coverage < 1.0)
                    & np.all(np.isfinite(foreground)
                             & (foreground >= -roundoff)
                             & (foreground <= 255.0 + roundoff), axis=1)
                    & (np.max(np.abs(reconstructed - pixels[tile][tile_edge, :3]), axis=1) <= 2.0)
                )
                tile_edge = tile_edge.copy()
                tile_edge[tile_edge] = ~explained
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
    # Smoothing must not turn established opaque fibres/petals translucent.
    # Retain the historical matte treatment for the general-purpose profile.
    if opaque_subject:
        np.minimum(alpha, smoothed_alpha, out=alpha, where=alpha < 1.0)
    else:
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


def detect_chroma_key_color(image: Image.Image) -> str:
    """Select a supported saturated key only when the border agrees.

    Neutral/white and mixed backgrounds require explicit review, not an
    arbitrary dominant-channel guess. This does not classify subject pixels.
    """
    if not isinstance(image, Image.Image) or not all(image.size):
        raise ValueError("A nonempty image is required to detect the background")
    width, height = image.size
    frame = max(1, min(4, min(width, height) // 2))
    border = np.concatenate([
        np.asarray(image.crop(box).convert("RGB"), dtype=np.int16).reshape(-1, 3)
        for box in ((0, 0, width, frame), (0, height - frame, width, height),
                    (0, 0, frame, height), (width - frame, 0, width, height))
    ])
    median = np.median(border, axis=0)
    channel = int(np.argmax(median))
    others = [value for value in range(3) if value != channel]
    dominant = border[:, channel]
    agrees = (dominant >= 150) & (dominant - border[:, others].max(axis=1) >= 80)
    if float(np.mean(agrees)) < 0.90:
        raise ChromaKeyAmbiguousError(
            "Не удалось уверенно определить цвет фона. "
            "Авто поддерживает однородный синий, зелёный или красный фон; "
            "белый и сложный фон требуют другого метода."
        )
    return ("red", "green", "blue")[channel]


def measure_chroma_background(image: Image.Image) -> tuple[int, int, int]:
    """Report the rounded median border RGB used for removal, not generation."""
    if not isinstance(image, Image.Image) or not all(image.size):
        raise ValueError("A nonempty image is required to measure the background")
    return tuple(int(round(value)) for value in _measured_border_key(image))


def _has_enclosed_transition_solution(
    image: Image.Image,
    key_color: object,
    measured_key: np.ndarray,
) -> bool:
    """Whether precise has a reference-backed recovery unavailable to staged."""
    requested_key = np.asarray(parse_key_color(key_color), dtype=np.float32)
    key_channel = int(np.argmax(requested_key))
    other_channels = [index for index in range(3) if index != key_channel]
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    background_dominance = measured_key[key_channel] - max(
        measured_key[other_channels[0]],
        measured_key[other_channels[1]],
    )
    if background_dominance <= 0.0:
        return False
    pixel_dominance = rgb[..., key_channel] - np.maximum(
        rgb[..., other_channels[0]],
        rgb[..., other_channels[1]],
    )
    raw_matte = 1.0 - np.clip(
        pixel_dominance / background_dominance,
        0.0,
        1.0,
    )
    recovered_matte = _recover_enclosed_transition_matte(
        rgb,
        measured_key,
        raw_matte,
    )
    return bool(np.count_nonzero(recovered_matte >= raw_matte + 0.10) >= 9)


def _weak_opaque_paint_mask(source: Image.Image, provisional: Image.Image, key: np.ndarray):
    """Protect flat weak-key paint that lacks a supported local mixture.

    A dark violet stroke can have slight key-channel dominance of its own.
    Under the opaque-clipart ambiguity policy, preserve that source paint rather
    than reinterpret it using an adjacent cream material. This is not proof that
    all weak additive spill is absent.
    """
    original = np.asarray(source.convert("RGBA"), dtype=np.uint8)
    pixels = np.asarray(provisional, dtype=np.uint8)
    channel = int(np.argmax(key))
    others = [c for c in range(3) if c != channel]
    rgb = original[..., :3]
    dominance = rgb[..., channel].astype(np.int16) - np.max(rgb[..., others], axis=2).astype(np.int16)
    candidate = ((original[..., 3] == 255) & (pixels[..., 3] >= 242)
                 & (pixels[..., 3] < 255) & (dominance <= 24))
    if not np.any(candidate):
        return original, np.zeros(candidate.shape, dtype=bool)
    vertical = np.max(cv2.absdiff(rgb[1:], rgb[:-1]), axis=2) <= 1
    horizontal = np.max(cv2.absdiff(rgb[:, 1:], rgb[:, :-1]), axis=2) <= 1
    flat = np.zeros(candidate.shape, dtype=bool)
    flat[1:-1] |= vertical[:-1] & vertical[1:]
    flat[:, 1:-1] |= horizontal[:, :-1] & horizontal[:, 1:]
    candidate &= flat
    core = cv2.erode((pixels[..., 3] == 255).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    protected = np.zeros(candidate.shape, dtype=bool)
    if not np.any(candidate) or not np.any(core):
        return original, protected
    distance, labels = cv2.distanceTransformWithLabels((~core).astype(np.uint8),
        cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    candidate &= distance <= 12
    if not np.any(candidate):
        return original, protected
    lookup = np.zeros((int(labels.max()) + 1, 3), dtype=np.float32)
    lookup[labels[core]] = rgb[core]
    reference = lookup[labels[candidate]]
    observed = rgb[candidate].astype(np.float32)
    direction = reference - key
    coverage = np.clip(np.sum((observed - key) * direction, axis=1)
        / np.maximum(np.sum(direction * direction, axis=1), 1), 0, 1)
    residual = np.max(np.abs(observed - (key + coverage[:, None] * direction)), axis=1)
    protected[candidate] = residual > 5
    return original, protected


def _clean_opaque_key_boundary(
    source: Image.Image, provisional: Image.Image, measured_key: np.ndarray,
) -> Image.Image:
    """Apply the approved weak-edge delivery selection after colour recovery.

    Keep supplied alpha and coverage of at least half. Only a one-pixel source
    boundary dominated by the measured key is eligible. This deliberately loses
    some real weak AA; it is a clean-edge policy, not foreground ground truth.
    All RGB and every unselected RGBA sample remain exact.
    """
    pixels = np.asarray(provisional.convert("RGBA"), dtype=np.uint8)
    weak = (pixels[..., 3] > 0) & (pixels[..., 3] < 128)
    if not np.any(weak):
        return provisional
    original = np.asarray(source.convert("RGBA"), dtype=np.uint8)
    if np.any(original[..., 3] != 255):
        return provisional
    key_channel = int(np.argmax(measured_key))
    other_channels = [channel for channel in range(3) if channel != key_channel]
    measured_other = max(float(measured_key[channel]) for channel in other_channels)
    key_ratio = float(measured_key[key_channel]) / max(measured_other, 1.0)
    background_ratio = float(np.clip(0.80 * key_ratio, 1.70, 2.5))
    dominant = original[..., key_channel].astype(np.float32)
    other = np.maximum(original[..., other_channels[0]],
                       original[..., other_channels[1]]).astype(np.float32)
    background = (dominant >= background_ratio * other) & (dominant >= 55.0)
    boundary = background & cv2.dilate(
        (~background).astype(np.uint8), np.ones((3, 3), dtype=np.uint8),
    ).astype(bool)
    remove = boundary & weak
    if not np.any(remove):
        return provisional
    cleaned = pixels.copy()
    cleaned[..., 3][remove] = 0
    result = Image.fromarray(cleaned, mode="RGBA")
    # Optional in-memory transport for the host. NN must reconstruct colours
    # with the working matte, then receive the delivery matte after upscaling.
    # This image is never serialized as metadata or required by API1 callers.
    result.info["vibix:precleanup_alpha"] = provisional.getchannel("A")
    return result


def remove_chroma_key_automatic(
    image: Image.Image,
    key_color: object = "blue",
    *,
    subject_profile: str = "legacy",
    stage_observer: Callable[[str, Image.Image], None] | None = None,
) -> Image.Image:
    """Remove a generated key background without user-tuned thresholds.

    ``opaque_clipart`` enables a bounded recovery for an enclosed, near-key
    opaque subject when its local colour is a numerically reliable reference.
    The default ``legacy`` profile does not enable this recovery. An opaque
    near-key object and a translucent object can have identical composite
    pixels; this profile choice cannot be inferred from RGB alone.
    Opaque clipart also skips the legacy translucent-material colour heuristic:
    partial edge coverage alone does not justify neutralising foreground hues.
    Fully opaque inputs use the owner-approved final weak-edge selection: key-
    dominated boundary samples below half coverage may be discarded for a cleaner
    edge. Supplied alpha, stronger coverage and all retained RGB stay untouched
    by this final selection.

    ``stage_observer`` is an opt-in offline diagnostic hook. It receives an
    independent RGBA snapshot after each completed pixel stage; none are
    allocated in normal processing. Observer exceptions propagate to its caller.
    """
    if not isinstance(image, Image.Image):
        raise TypeError("image must be a PIL image")
    if image.width < 1 or image.height < 1:
        raise ValueError("image dimensions must be positive")
    if subject_profile not in _SUBJECT_PROFILES:
        raise ValueError("subject_profile must be 'legacy' or 'opaque_clipart'")
    if stage_observer is not None and not callable(stage_observer):
        raise TypeError("stage_observer must be callable")
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
    protected_source = None
    protected_paint = None

    def preserve_paint(result):
        if protected_paint is None:
            return result
        restored = result.copy() if result.mode == "RGBA" else result.convert("RGBA")
        pixels = restored.load()
        for x, y, rgba in protected_paint:
            pixels[x, y] = rgba
        return restored

    preserve_local_material = (
        subject_profile == "opaque_clipart"
        and np.all(np.asarray(image.convert("RGBA"))[..., 3] == 255)
    )
    prefer_precise = measured_other <= 36.0
    if subject_profile == "opaque_clipart":
        prefer_precise |= _has_enclosed_transition_solution(
            image,
            key_color,
            measured_key,
        )
    if prefer_precise:
        try:
            result = _remove_chroma_key_precise(
                image,
                key_color,
                allow_enclosed_transition_recovery=(
                    subject_profile == "opaque_clipart"
                ),
            )
        except ChromaKeySubjectColorError:
            raise
        except ChromaKeyAmbiguousError:
            pass
        else:
            if subject_profile == "opaque_clipart":
                protected_source, candidate_paint = _weak_opaque_paint_mask(image, result, measured_key)
                if np.any(candidate_paint):
                    rows, columns = np.nonzero(candidate_paint)
                    protected_paint = [
                        (int(x), int(y), tuple(int(c) for c in protected_source[y, x]))
                        for y, x in zip(rows, columns)
                    ]
                    protected_source = None
                    result = preserve_paint(result)
                else:
                    protected_source = None
            if stage_observer is not None:
                stage_observer("precise_result", result.copy())
            result = _neutralize_opaque_key_spill(
                image, result, key_color, preserve_local_material=preserve_local_material,
            )
            result = preserve_paint(result)
            if stage_observer is not None:
                stage_observer("opaque_spill", result.copy())
            if subject_profile == "legacy":
                result = _neutralize_translucent_complement(image, result, key_color)
                result = preserve_paint(result)
                if stage_observer is not None:
                    stage_observer("translucent_complement", result.copy())
            result = _preserve_fully_opaque_source_rgb(
                image, result,
                measured_key=measured_key if subject_profile == "opaque_clipart" else None,
            )
            result = preserve_paint(result)
            if stage_observer is not None:
                stage_observer("source_rgb_restore", result.copy())
            if subject_profile == "opaque_clipart":
                result = _refine_opaque_boundary(image, result, measured_key)
                result = preserve_paint(result)
                if stage_observer is not None:
                    stage_observer("opaque_boundary", result.copy())
                result = reclassify_rim(image, result, measured_key)
                result = preserve_paint(result)
                if stage_observer is not None:
                    stage_observer("rim_reclassification", result.copy())
                result = refine_edge_mixture(image, result, measured_key)
                result = preserve_paint(result)
                if stage_observer is not None:
                    stage_observer("edge_mixture", result.copy())
                result = suppress_edge_key_spill(image, result, measured_key)
                result = preserve_paint(result)
                if stage_observer is not None:
                    stage_observer("edge_key_spill", result.copy())
                result = repair_edge_chroma(image, result, measured_key)
                result = preserve_paint(result)
                if stage_observer is not None:
                    stage_observer("edge_chroma_repair", result.copy())
                result = _clean_opaque_key_boundary(image, result, measured_key)
                if stage_observer is not None:
                    snapshot = result.copy()
                    snapshot.info.pop("vibix:precleanup_alpha", None)
                    stage_observer("opaque_edge_cleanup", snapshot)
            return result
    result = _remove_chroma_key_staged(
        image, key_color, opaque_subject=(subject_profile == "opaque_clipart"),
    )
    if stage_observer is not None:
        stage_observer("staged_result", result.copy())
    result = _neutralize_opaque_key_spill(
        image, result, key_color, preserve_local_material=preserve_local_material,
    )
    result = preserve_paint(result)
    if stage_observer is not None:
        stage_observer("opaque_spill", result.copy())
    if subject_profile == "legacy":
        result = _neutralize_translucent_complement(image, result, key_color)
        result = preserve_paint(result)
        if stage_observer is not None:
            stage_observer("translucent_complement", result.copy())
    result = _preserve_fully_opaque_source_rgb(
        image, result,
        measured_key=measured_key if subject_profile == "opaque_clipart" else None,
    )
    result = preserve_paint(result)
    if stage_observer is not None:
        stage_observer("source_rgb_restore", result.copy())
    if subject_profile == "opaque_clipart":
        result = _refine_opaque_boundary(image, result, measured_key)
        result = preserve_paint(result)
        if stage_observer is not None:
            stage_observer("opaque_boundary", result.copy())
        result = reclassify_rim(image, result, measured_key)
        result = preserve_paint(result)
        if stage_observer is not None:
            stage_observer("rim_reclassification", result.copy())
        result = refine_edge_mixture(image, result, measured_key)
        result = preserve_paint(result)
        if stage_observer is not None:
            stage_observer("edge_mixture", result.copy())
        result = suppress_edge_key_spill(image, result, measured_key)
        result = preserve_paint(result)
        if stage_observer is not None:
            stage_observer("edge_key_spill", result.copy())
        result = repair_edge_chroma(image, result, measured_key)
        result = preserve_paint(result)
        if stage_observer is not None:
            stage_observer("edge_chroma_repair", result.copy())
        result = _clean_opaque_key_boundary(image, result, measured_key)
        if stage_observer is not None:
            snapshot = result.copy()
            snapshot.info.pop("vibix:precleanup_alpha", None)
            stage_observer("opaque_edge_cleanup", snapshot)
    return result


def finish_rim_cleanup(result: Image.Image, subject_profile: str = "opaque_clipart") -> Image.Image:
    """Production step after remove_chroma_key_automatic: recolour saturated rim specks.

    It recolours opaque pixels, which remove_chroma_key_automatic promises never
    to do, so it is a separate step on top of it. It also replaces the colour
    hidden under alpha == 0 (despilled key, noise) with one flat subject colour,
    so no later brush, upscaler or external editor can reveal it as odd patches.
    """
    from foreground_colour import with_clean_hidden_rgb

    if subject_profile == "opaque_clipart":
        result = recolour_rim_specks(result)
    return with_clean_hidden_rgb(result)


def remove_chroma_key_with_rim_cleanup(image: Image.Image, key_color: str, **kwargs) -> Image.Image:
    result = remove_chroma_key_automatic(image, key_color, **kwargs)
    return finish_rim_cleanup(result, kwargs.get("subject_profile", "opaque_clipart"))


EDGE_SILHOUETTE_STANDARD = (
    "Crisply resolved forms: every element, including small secondary "
    "details and repeated motifs, stays individually recognisable and "
    "cleanly drawn, never merged into blotches or mush. The subject holds "
    "one continuous closed silhouette that separates cleanly from the "
    "flat background. Fur, down and feather tips keep their natural soft, "
    "fluffy edge: fine individual hairs and wisps, each drawn sharply "
    "against the flat background, with a gentle feathered outline and "
    "no jagged saw-tooth steps, no watercolor bleed, no halo, glow or "
    "pale rim reaching into the background, and no specks or dots "
    "detached from the subject. "
)


def chroma_key_prompt_block(
    key_color: object = "blue",
    *,
    watercolor: bool = False,
    materials: Iterable[object] = (),
    edge_quality: bool = False,
) -> str:
    """Return a provider-ready prompt suffix for a removable flat background.

    ``edge_quality`` enables the clipart silhouette standard. Only the Auto
    Clipart module attaches it; other generators must keep prompts free of
    those requirements.
    """
    rgb = parse_key_color(key_color)
    color_name = next((name for name, value in KEY_COLORS.items() if value == rgb), None)
    label = color_name or "custom"
    hex_color = "#%02X%02X%02X" % rgb
    block = (
        f"Isolated on a completely flat, uniform, solid pure {label} "
        f"({hex_color}) digital chroma-key background. The background fills "
        "the image edge to edge with no gradient and stays fully bright inside "
        "every gap and opening: the space between parts of the subject shows "
        "the same bright key color as the rest of the background, never a "
        "darker or black shade. No reflection, tint, shadow, contact "
        "shadow, ambient-occlusion shading, glow, haze or "
        "color spill on the subject. No white or cream backing, halo, sticker "
        "outline or white patches behind or between flowers, leaves and twigs. "
        "The subject is fully opaque and solid: "
        "no transparency, translucency, semi-transparent materials, glass, "
        "tulle, lace mesh, veil, smoke, mist, haze or see-through parts. "
    )
    if edge_quality:
        block += EDGE_SILHOUETTE_STANDARD
    block += (
        "The complete subject centered with at least 10% empty "
        "margin, nothing cropped, no text, no watermark, no stray fragments."
    )
    selected = {str(item).strip().casefold() for item in materials}
    if watercolor:
        selected.add("watercolor")
    for material in MATERIAL_PROMPT_CLAUSES:
        if material == "transparent_details":
            # Opaque clipart mode deliberately rejects this material class;
            # never append a contradictory instruction to the provider prompt.
            continue
        if material in selected:
            block += MATERIAL_PROMPT_CLAUSES[material]
    return block


__all__ = [
    "ChromaKeyAmbiguousError",
    "ChromaKeySubjectColorError",
    "EDGE_SILHOUETTE_STANDARD",
    "KEY_COLORS",
    "MATERIAL_PROMPT_CLAUSES",
    "chroma_key_prompt_block",
    "detect_chroma_key_color",
    "measure_chroma_background",
    "parse_key_color",
    "remove_chroma_key",
    "remove_chroma_key_automatic",
]
