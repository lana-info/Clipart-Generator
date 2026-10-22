"""Local seamless-tile tools for the Patterns module: resampling, QC, export.

Pure Pillow/numpy helpers with no Qt, provider or network dependency.  They work
on plain PIL images (one period of a straight repeat lattice) and on the scenes
from :mod:`studio_patterns`.  A *tile* is always the rectangular full period, so
every function here assumes a straight lattice; shifted repeats are expressed by
the supertile of :func:`studio_patterns.render_supertile`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
import io
import math
import os
from pathlib import Path
import random
from typing import Mapping

import numpy as np
from PIL import Image, ImageCms

from studio_patterns import (
    MAX_DIMENSION, MAX_ELEMENTS, MAX_PREVIEW_PIXELS, MAX_RENDER_PIXELS,
    PatternElement, PatternScene, PatternValidationError, RepeatMode,
    _inspect_referenced_assets,
)


# Provisional until calibrated on the owner's good/bad examples (TASKS T1.4).
SEAM_READY_MAX = 1.5
SEAM_REVIEW_MAX = 3.0
_SEAM_FLOOR = 1.0
_SEAM_PERCENTILE = 95
_BLOCK_ROWS = 256
_SUPPORTED_DPI = (72, 1200)


class SeamStatus(str, Enum):
    READY = "ready"
    REVIEW = "review"
    FAIL = "fail"


@dataclass(frozen=True)
class SeamReport:
    """Seam continuity relative to the tile's own inner transitions (1.0 = invisible)."""

    horizontal: float
    vertical: float
    status: SeamStatus

    @property
    def score(self) -> float:
        return max(self.horizontal, self.vertical)


@dataclass(frozen=True)
class ExportResult:
    path: Path
    size: tuple[int, int]
    byte_size: int


def inches_to_px(inches: float, dpi: int = 300) -> int:
    _check_dpi(dpi)
    if isinstance(inches, bool) or not isinstance(inches, (int, float)) or not 0 < inches < math.inf:
        raise PatternValidationError("inches must be a positive finite number")
    return max(1, round(inches * dpi))


def cm_to_px(cm: float, dpi: int = 300) -> int:
    _check_dpi(dpi)
    if isinstance(cm, bool) or not isinstance(cm, (int, float)) or not 0 < cm < math.inf:
        raise PatternValidationError("cm must be a positive finite number")
    return max(1, round(cm / 2.54 * dpi))


def _check_dpi(dpi: int) -> None:
    if isinstance(dpi, bool) or not isinstance(dpi, int) or not _SUPPORTED_DPI[0] <= dpi <= _SUPPORTED_DPI[1]:
        raise PatternValidationError(f"dpi must be an integer in {_SUPPORTED_DPI[0]}..{_SUPPORTED_DPI[1]}")


def _check_size(size: tuple[int, int], limit: int = MAX_RENDER_PIXELS) -> tuple[int, int]:
    if (not isinstance(size, tuple) or len(size) != 2
            or any(isinstance(v, bool) or not isinstance(v, int) or not 0 < v <= MAX_DIMENSION for v in size)):
        raise PatternValidationError(f"size must be two integers in 1..{MAX_DIMENSION}")
    if size[0] * size[1] > limit:
        raise PatternValidationError("size exceeds safe pixel budget")
    return size


def _working_image(image: Image.Image) -> Image.Image:
    if not isinstance(image, Image.Image):
        raise PatternValidationError("image must be a PIL image")
    if image.width > MAX_DIMENSION or image.height > MAX_DIMENSION or image.width * image.height > MAX_RENDER_PIXELS:
        raise PatternValidationError("image exceeds safe size")
    if image.mode in ("RGB", "RGBA"):
        return image
    has_alpha = image.mode in ("LA", "PA", "RGBa", "La") or "transparency" in image.info
    return image.convert("RGBA" if has_alpha else "RGB")


def wrap_resize(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Resize one tile period without creating a seam.

    A plain resize clamps the filter at the image border, so opposite edges stop
    matching.  Here the tile is padded with its own periodic continuation first
    and the filter reads that padding, so the result is again one exact period.
    """
    width, height = _check_size(size)
    source = _working_image(image)
    if source.size == (width, height):
        return source.copy()
    # Pillow clamps the filter at the ``box`` edge, so the box itself must reach
    # past the cropped period by more than the filter support.  The output is
    # padded by ``out_*`` pixels, the box by exactly the same span in source
    # pixels, which keeps the scale (and so the periodicity) exact; then crop.
    scale_x, scale_y = source.width / width, source.height / height
    out_x = math.ceil(3 * max(1.0, scale_x) / scale_x) + 2
    out_y = math.ceil(3 * max(1.0, scale_y) / scale_y) + 2
    reach_x, reach_y = out_x * scale_x, out_y * scale_y
    pad_x, pad_y = math.ceil(reach_x), math.ceil(reach_y)
    padded = Image.fromarray(np.pad(np.asarray(source), ((pad_y, pad_y), (pad_x, pad_x), (0, 0)), mode="wrap"))
    box = (pad_x - reach_x, pad_y - reach_y, pad_x + source.width + reach_x, pad_y + source.height + reach_y)
    resized = padded.resize((width + 2 * out_x, height + 2 * out_y), Image.Resampling.LANCZOS, box=box)
    return resized.crop((out_x, out_y, out_x + width, out_y + height))


def seam_report(image: Image.Image) -> SeamReport:
    """Measure how visible the repeat seam of ``image`` is.

    For each axis the jump across the wrap-around border (last column to first,
    last row to first) is divided by the largest typical jump between adjacent
    columns/rows inside the tile (95th percentile).  A tile cut from an exact
    lattice scores at most about 1; a hard seam scores far above.  Opposite edges
    are *not* required to be equal, only continuous.
    """
    source = _working_image(image)
    array = np.asarray(source)
    height, width = array.shape[:2]
    column_sums = np.zeros(max(width - 1, 0), dtype=np.float64)
    row_means = np.zeros(max(height - 1, 0), dtype=np.float64)
    wrap_columns = np.zeros(2, dtype=np.float64)
    channels = array.shape[2]
    first_row = last_row = None
    for start in range(0, height, _BLOCK_ROWS):
        block = _premultiplied(array[start:min(start + _BLOCK_ROWS, height)])
        if width > 1:
            column_sums += np.abs(block[:, 1:] - block[:, :-1]).sum(axis=(0, 2))
        wrap_columns[0] += np.abs(block[:, 0] - block[:, -1]).sum()
        wrap_columns[1] += block.shape[0]
        if first_row is None:
            first_row = block[0].copy()
        if last_row is not None:
            row_means[start - 1] = np.abs(block[0] - last_row).mean()
        for offset in range(block.shape[0] - 1):
            row_means[start + offset] = np.abs(block[offset + 1] - block[offset]).mean()
        last_row = block[-1].copy()
    horizontal = _ratio(wrap_columns[0] / (wrap_columns[1] * channels),
                        column_sums / (height * channels))
    vertical = _ratio(float(np.abs(first_row - last_row).mean()), row_means)
    score = max(horizontal, vertical)
    status = (SeamStatus.READY if score <= SEAM_READY_MAX
              else SeamStatus.REVIEW if score <= SEAM_REVIEW_MAX else SeamStatus.FAIL)
    return SeamReport(horizontal, vertical, status)


def _premultiplied(block: np.ndarray) -> np.ndarray:
    data = block.astype(np.float32)
    if data.shape[2] == 4:
        data[..., :3] *= data[..., 3:4] / 255.0
    return data


def _ratio(wrap_jump: float, inner: np.ndarray) -> float:
    if inner.size == 0:
        return 0.0
    reference = max(float(np.percentile(inner, _SEAM_PERCENTILE)), _SEAM_FLOOR)
    return float(wrap_jump) / reference


def make_seamless(image: Image.Image, band: float = 0.2) -> Image.Image:
    """Turn an ordinary picture into a straight-repeat tile (mode B), same size.

    The picture is blended with a copy shifted by half a period.  The shifted
    copy is continuous across the original border, the original is continuous in
    its middle, and a smooth weight hands over from one to the other within
    ``band`` (fraction of the size) from the border.  Detailed pictures can show
    ghosting in that band, so the result must be judged with :func:`seam_report`.
    """
    if isinstance(band, bool) or not isinstance(band, (int, float)) or not 0 < band <= 0.5:
        raise PatternValidationError("band must be in (0, 0.5]")
    source = _working_image(image)
    array = np.asarray(source)
    height, width = array.shape[:2]
    shifted = np.roll(array, (height // 2, width // 2), axis=(0, 1))
    weight_x = _edge_weight(width, band)
    weight_y = _edge_weight(height, band)
    result = np.empty_like(array)
    for start in range(0, height, _BLOCK_ROWS):
        stop = min(start + _BLOCK_ROWS, height)
        weight = (weight_y[start:stop, None] * weight_x[None, :])[..., None]
        original, other = _premultiplied(array[start:stop]), _premultiplied(shifted[start:stop])
        blended = other + weight * (original - other)
        if blended.shape[2] == 4:
            alpha = blended[..., 3:4]
            safe = np.where(alpha > 0, alpha, 1.0)
            blended[..., :3] = np.where(alpha > 0, blended[..., :3] * 255.0 / safe, 0.0)
        result[start:stop] = np.clip(np.rint(blended), 0, 255).astype(np.uint8)
    return Image.fromarray(result, source.mode)


def _edge_weight(length: int, band: float) -> np.ndarray:
    """0 on the border pixels, smoothly rising to 1 at ``band * length`` inside."""
    reach = max(band * length, 1.0)
    distance = np.minimum(np.arange(length), np.arange(length)[::-1]) / reach
    t = np.clip(distance, 0.0, 1.0)
    return (t * t * (3.0 - 2.0 * t)).astype(np.float32)


def mirror_tile(image: Image.Image) -> Image.Image:
    """Return the 2x2 mirrored period of ``image``; seamless by construction."""
    source = _working_image(image)
    _check_size((source.width * 2, source.height * 2))
    array = np.asarray(source)
    top = np.concatenate([array, array[:, ::-1]], axis=1)
    return Image.fromarray(np.concatenate([top, top[::-1]], axis=0), source.mode)


def tile_preview(image: Image.Image, copies: int = 3, max_pixels: int = MAX_PREVIEW_PIXELS,
                 center_seam: bool = True) -> Image.Image:
    """Repeat a tile ``copies`` x ``copies`` (3 or 5) within a pixel budget.

    With ``center_seam`` the repeat is shifted by half a period so that a seam
    would run through the middle of the preview instead of hiding at its edges.
    """
    if copies not in (3, 5):
        raise PatternValidationError("preview copies must be 3 or 5")
    if isinstance(max_pixels, bool) or not isinstance(max_pixels, int) or not copies * copies <= max_pixels <= MAX_PREVIEW_PIXELS:
        raise PatternValidationError(f"max_pixels must be in {copies * copies}..{MAX_PREVIEW_PIXELS}")
    tile = _working_image(image)
    if tile.width * tile.height * copies * copies > max_pixels:
        factor = math.sqrt(max_pixels / (tile.width * tile.height * copies * copies))
        target = (max(1, math.floor(tile.width * factor)), max(1, math.floor(tile.height * factor)))
        if target[0] * target[1] * copies * copies > max_pixels:
            raise PatternValidationError("preview budget cannot fit the rounded repeat period")
        tile = wrap_resize(tile, target)
    array = np.tile(np.asarray(tile), (copies, copies, 1))
    if center_seam:
        array = np.roll(array, (tile.height // 2, tile.width // 2), axis=(0, 1))
    return Image.fromarray(array, tile.mode)


@lru_cache(maxsize=1)
def _srgb_profile() -> bytes:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def export_tile(image: Image.Image, path: str | os.PathLike, *, size: tuple[int, int] | None = None,
                dpi: int = 300, background: tuple[int, int, int] = (255, 255, 255),
                quality: int = 95) -> ExportResult:
    """Write a PNG or JPG (chosen by suffix) at ``dpi`` with an embedded sRGB profile.

    ``size`` resamples through :func:`wrap_resize`, so the exported file still
    repeats seamlessly.  JPG has no alpha: transparency is flattened onto
    ``background``.  DPI is metadata only and adds no detail.  The file appears
    under its final name only when fully written.
    """
    _check_dpi(dpi)
    target = Path(path)
    kind = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG"}.get(target.suffix.lower())
    if kind is None:
        raise PatternValidationError("export path must end in .png, .jpg or .jpeg")
    if (not isinstance(quality, int) or isinstance(quality, bool) or not 1 <= quality <= 100):
        raise PatternValidationError("quality must be an integer in 1..100")
    if (not isinstance(background, tuple) or len(background) != 3
            or any(isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 255 for v in background)):
        raise PatternValidationError("background must be three 0..255 integers")
    tile = _working_image(image)
    if size is not None:
        tile = wrap_resize(tile, size)
    if kind == "JPEG":
        base = Image.new("RGBA", tile.size, (*background, 255))
        base.alpha_composite(tile.convert("RGBA"))
        tile = base.convert("RGB")
        options = {"quality": quality, "subsampling": 0, "optimize": True}
    else:
        options = {}
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        tile.save(temporary, format=kind, dpi=(dpi, dpi), icc_profile=_srgb_profile(), **options)
        byte_size = temporary.stat().st_size
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return ExportResult(target, tile.size, byte_size)


def layout_scene(scene: PatternScene, *, count: int, min_gap: float = 0.0,
                 asset_weights: Mapping[str, float] | None = None,
                 scale_range: tuple[float, float] = (0.75, 1.25),
                 angle_range: tuple[float, float] = (-30.0, 30.0),
                 max_attempts: int = 60) -> tuple[PatternScene, tuple[str, ...]]:
    """Place ``count`` new elements with a minimum gap, measured on the repeat.

    Unlocked elements are replaced; locked ones stay and act as obstacles.  Each
    element is treated as a circle around its rotated bounding box, so the gap is
    conservative.  Distances use the periodic lattice (including shifted and
    mirrored images), so elements do not crowd each other across the seam.  The
    search is bounded; when it cannot place everything the second return value
    explains how many were placed.  Deterministic for a given ``scene.seed``.
    """
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise PatternValidationError("count must be a non-negative integer")
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= 10_000:
        raise PatternValidationError("max_attempts must be in 1..10000")
    if not _finite_number(min_gap) or min_gap < 0:
        raise PatternValidationError("min_gap must be a non-negative finite number")
    for pair, name in ((scale_range, "scale_range"), (angle_range, "angle_range")):
        if (not isinstance(pair, tuple) or len(pair) != 2 or not all(_finite_number(v) for v in pair)
                or pair[0] > pair[1]):
            raise PatternValidationError(f"{name} must be an ordered pair of finite numbers")
    if not (0 < scale_range[0] and scale_range[1] <= 32):
        raise PatternValidationError("scale_range must stay within (0, 32]")
    if not scene.assets and count:
        raise PatternValidationError("cannot layout elements without assets")
    retained = tuple(item for item in scene.elements if item.locked)
    if len(retained) + count > MAX_ELEMENTS:
        raise PatternValidationError("count is outside supported limits")
    asset_ids = sorted(asset.id for asset in scene.assets)
    weights = {asset_id: 1.0 for asset_id in asset_ids}
    if asset_weights is not None:
        if set(asset_weights) - set(asset_ids):
            raise PatternValidationError("asset_weights refers to an unknown asset")
        for asset_id, value in asset_weights.items():
            if not _finite_number(value) or value < 0:
                raise PatternValidationError("asset weights must be non-negative finite numbers")
            weights[asset_id] = float(value)
    if count and not any(weights.values()):
        raise PatternValidationError("asset weights must not all be zero")

    sizes = _asset_sizes(scene)
    rng = random.Random(scene.seed)
    placed = [(item.x, item.y, _radius(sizes[item.asset_id], item.scale)) for item in retained]
    used_ids = {item.id for item in retained}
    generated: list[PatternElement] = []
    for _ in range(count):
        for _attempt in range(max_attempts):
            asset_id = rng.choices(asset_ids, [weights[a] for a in asset_ids])[0]
            scale = rng.uniform(*scale_range)
            candidate = (rng.uniform(0, scene.width), rng.uniform(0, scene.height),
                         _radius(sizes[asset_id], scale))
            angle = rng.uniform(*angle_range)
            if _fits(scene, candidate, placed, min_gap):
                placed.append(candidate)
                index = len(generated)
                element_id = f"layout-{index:04d}"
                while element_id in used_ids:
                    element_id = f"layout-{index:04d}-{len(used_ids)}"
                used_ids.add(element_id)
                generated.append(PatternElement(element_id, asset_id, candidate[0], candidate[1],
                                                scale, angle, z_index=index))
                break
    warnings = ()
    if len(generated) < count:
        warnings = (f"placed {len(generated)} of {count} elements: no room left for the requested gap",)
    result = PatternScene(scene.width, scene.height, scene.assets, retained + tuple(generated),
                          scene.repeat_mode, scene.seed, scene.background, scene.schema_version)
    return result, warnings


def _finite_number(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _asset_sizes(scene: PatternScene) -> dict[str, tuple[int, int]]:
    probe = PatternScene(1, 1, scene.assets, tuple(
        PatternElement(f"probe-{index}", asset.id, 0, 0) for index, asset in enumerate(scene.assets)))
    return {asset_id: size for asset_id, (_, size) in _inspect_referenced_assets(probe).items()}


def _radius(size: tuple[int, int], scale: float) -> float:
    return 0.5 * math.hypot(*size) * scale


def _period(scene: PatternScene) -> tuple[int, int]:
    width, height = scene.width, scene.height
    if scene.repeat_mode is RepeatMode.HALF_ROW:
        return width, height * 2
    if scene.repeat_mode is RepeatMode.HALF_COLUMN:
        return width * 2, height
    if scene.repeat_mode is RepeatMode.MIRROR:
        return width * 2, height * 2
    return width, height


def _images(scene: PatternScene, x: float, y: float) -> list[tuple[float, float]]:
    """All positions of one element inside the supertile."""
    width, height = scene.width, scene.height
    mode = scene.repeat_mode
    if mode is RepeatMode.HALF_ROW:
        return [(x, y), (x + width / 2, y + height)]
    if mode is RepeatMode.HALF_COLUMN:
        return [(x, y), (x + width, y + height / 2)]
    if mode is RepeatMode.MIRROR:
        return [(x, y), (2 * width - x, y), (x, 2 * height - y), (2 * width - x, 2 * height - y)]
    return [(x, y)]


def _torus_distance(scene: PatternScene, a: tuple[float, float], b: tuple[float, float]) -> float:
    period_x, period_y = _period(scene)
    dx = abs(a[0] - b[0]) % period_x
    dy = abs(a[1] - b[1]) % period_y
    return math.hypot(min(dx, period_x - dx), min(dy, period_y - dy))


def _fits(scene: PatternScene, candidate: tuple[float, float, float],
          placed: list[tuple[float, float, float]], min_gap: float) -> bool:
    x, y, radius = candidate
    own = _images(scene, x, y)
    for image in own[1:]:  # an element must also clear its own repeats
        if _torus_distance(scene, (x, y), image) < 2 * radius + min_gap:
            return False
    for other_x, other_y, other_radius in placed:
        need = radius + other_radius + min_gap
        if any(_torus_distance(scene, (x, y), image) < need for image in _images(scene, other_x, other_y)):
            return False
    return True


def encoded_size_hint(image: Image.Image, fmt: str = "PNG") -> int:
    """Encode ``image`` in memory and return the byte size (a hint before export)."""
    if fmt.upper() not in ("PNG", "JPEG"):
        raise PatternValidationError("fmt must be PNG or JPEG")
    tile = _working_image(image)
    if fmt.upper() == "JPEG":
        tile = tile.convert("RGB")
    buffer = io.BytesIO()
    tile.save(buffer, format=fmt.upper(), **({"quality": 95} if fmt.upper() == "JPEG" else {}))
    return buffer.tell()
