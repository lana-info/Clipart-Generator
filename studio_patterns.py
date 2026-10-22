"""Pure local scene and renderer primitives for the future Patterns module.

The module deliberately has no Qt or provider dependency.  A UI can keep a
``PatternScene`` as JSON, call :func:`render_supertile` for export, and call
:func:`render_preview` for a bounded 3x3 or 5x5 repeat preview.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import math
from pathlib import Path
import random
from typing import Any, Iterable

from PIL import Image


SCHEMA_VERSION = 1
MAX_DIMENSION = 8_192
MAX_ASSETS = 500
MAX_ELEMENTS = 1_000
MAX_PREVIEW_PIXELS = 16_000_000
MAX_ASSET_PIXELS = 16_000_000
MAX_TOTAL_DECODED_PIXELS = 32_000_000
MAX_TRANSFORM_PIXELS = 16_000_000
MAX_RENDER_PIXELS = 64_000_000
MAX_COMPOSITES = 100_000
MAX_JSON_BYTES = 1_000_000


class PatternValidationError(ValueError):
    """Raised when a scene is malformed or exceeds safe local limits."""


class RepeatMode(str, Enum):
    """Repeat geometry.  Shifted modes use one half of the base period."""

    STRAIGHT = "straight"
    HALF_ROW = "half_row"
    HALF_COLUMN = "half_column"
    MIRROR = "mirror"


@dataclass(frozen=True)
class AssetRef:
    """Stable asset identity and a local PNG path; image bytes are not embedded."""

    id: str
    path: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise PatternValidationError("asset.id must be a non-empty string")
        if not isinstance(self.path, str) or not self.path:
            raise PatternValidationError("asset.path must be a non-empty string")

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "path": self.path}

    @classmethod
    def from_dict(cls, value: Any) -> "AssetRef":
        if not isinstance(value, dict):
            raise PatternValidationError("asset must be an object")
        asset_id, path = value.get("id"), value.get("path")
        if not isinstance(asset_id, str) or not asset_id:
            raise PatternValidationError("asset.id must be a non-empty string")
        if not isinstance(path, str) or not path:
            raise PatternValidationError("asset.path must be a non-empty string")
        return cls(asset_id, path)


@dataclass(frozen=True)
class PatternElement:
    """One logical element.  Boundary copies are produced only at render time."""

    id: str
    asset_id: str
    x: float
    y: float
    scale: float = 1.0
    angle: float = 0.0
    locked: bool = False
    z_index: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id or not isinstance(self.asset_id, str) or not self.asset_id:
            raise PatternValidationError("element id and asset_id must be non-empty strings")
        numeric = (self.x, self.y, self.scale, self.angle)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in numeric):
            raise PatternValidationError("element numeric fields must be finite numbers")
        if not 0 < self.scale <= 32:
            raise PatternValidationError("element.scale must be in (0, 32]")
        if not isinstance(self.locked, bool):
            raise PatternValidationError("element.locked must be boolean")
        if isinstance(self.z_index, bool) or not isinstance(self.z_index, int):
            raise PatternValidationError("element.z_index must be an integer")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "asset_id": self.asset_id, "x": self.x, "y": self.y,
            "scale": self.scale, "angle": self.angle, "locked": self.locked,
            "z_index": self.z_index,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "PatternElement":
        if not isinstance(value, dict):
            raise PatternValidationError("element must be an object")
        required_strings = ("id", "asset_id")
        if any(not isinstance(value.get(key), str) or not value[key] for key in required_strings):
            raise PatternValidationError("element id and asset_id must be non-empty strings")
        try:
            return cls(
                id=value["id"], asset_id=value["asset_id"], x=value["x"], y=value["y"],
                scale=value.get("scale", 1.0), angle=value.get("angle", 0.0),
                locked=value.get("locked", False), z_index=value.get("z_index", 0),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PatternValidationError("element has invalid numeric fields") from exc


@dataclass(frozen=True)
class PatternScene:
    """Versioned portable Pattern scene; assets remain references to local files."""

    width: int
    height: int
    assets: tuple[AssetRef, ...] = field(default_factory=tuple)
    elements: tuple[PatternElement, ...] = field(default_factory=tuple)
    repeat_mode: RepeatMode = RepeatMode.STRAIGHT
    seed: int = 0
    background: tuple[int, int, int, int] = (255, 255, 255, 255)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validate_scene(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "width": self.width, "height": self.height,
            "assets": [asset.to_dict() for asset in self.assets],
            "elements": [element.to_dict() for element in self.elements],
            "repeat_mode": self.repeat_mode.value, "seed": self.seed,
            "background": list(self.background),
        }

    def to_json(self) -> str:
        """Serialize the scene without reading its referenced assets."""
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, value: Any) -> "PatternScene":
        if not isinstance(value, dict):
            raise PatternValidationError("scene must be an object")
        if value.get("schema_version") != SCHEMA_VERSION:
            raise PatternValidationError("unsupported scene schema_version")
        try:
            mode = RepeatMode(value.get("repeat_mode", RepeatMode.STRAIGHT.value))
            assets_raw, elements_raw = value.get("assets", []), value.get("elements", [])
            if not isinstance(assets_raw, list) or not isinstance(elements_raw, list):
                raise PatternValidationError("assets and elements must be arrays")
            if len(assets_raw) > MAX_ASSETS or len(elements_raw) > MAX_ELEMENTS:
                raise PatternValidationError("scene exceeds asset or element limit")
            assets = tuple(AssetRef.from_dict(item) for item in assets_raw)
            elements = tuple(PatternElement.from_dict(item) for item in elements_raw)
            background_raw = value.get("background", [255, 255, 255, 255])
            if not isinstance(background_raw, list):
                raise PatternValidationError("background must be an array")
            background = tuple(background_raw)
            return cls(value["width"], value["height"], assets, elements, mode,
                       value.get("seed", 0), background, value["schema_version"])
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, PatternValidationError):
                raise
            raise PatternValidationError("scene has invalid fields") from exc

    @classmethod
    def from_json(cls, source: str | bytes) -> "PatternScene":
        if not isinstance(source, (str, bytes)):
            raise PatternValidationError("scene JSON must be text or bytes")
        source_size = len(source.encode("utf-8")) if isinstance(source, str) else len(source)
        if source_size > MAX_JSON_BYTES:
            raise PatternValidationError("scene JSON exceeds safe size")
        try:
            return cls.from_dict(json.loads(source))
        except (TypeError, RecursionError, json.JSONDecodeError) as exc:
            raise PatternValidationError("scene JSON is invalid") from exc


def _validate_scene(scene: PatternScene) -> None:
    if (isinstance(scene.width, bool) or isinstance(scene.height, bool) or not isinstance(scene.width, int)
            or not isinstance(scene.height, int) or not (0 < scene.width <= MAX_DIMENSION and 0 < scene.height <= MAX_DIMENSION)):
        raise PatternValidationError(f"scene dimensions must be integers in 1..{MAX_DIMENSION}")
    if not isinstance(scene.assets, tuple) or not isinstance(scene.elements, tuple):
        raise PatternValidationError("assets and elements must be tuples")
    if any(not isinstance(asset, AssetRef) for asset in scene.assets) or any(not isinstance(element, PatternElement) for element in scene.elements):
        raise PatternValidationError("assets and elements contain invalid objects")
    if len(scene.assets) > MAX_ASSETS or len(scene.elements) > MAX_ELEMENTS:
        raise PatternValidationError("scene exceeds asset or element limit")
    if scene.schema_version != SCHEMA_VERSION:
        raise PatternValidationError("unsupported scene schema_version")
    if not isinstance(scene.repeat_mode, RepeatMode):
        raise PatternValidationError("repeat_mode is invalid")
    if isinstance(scene.seed, bool) or not isinstance(scene.seed, int):
        raise PatternValidationError("seed must be an integer")
    if (not isinstance(scene.background, tuple) or len(scene.background) != 4
            or any(isinstance(channel, bool) or not isinstance(channel, int) or not 0 <= channel <= 255 for channel in scene.background)):
        raise PatternValidationError("background must be four 0..255 integers")
    asset_ids = [asset.id for asset in scene.assets]
    if len(set(asset_ids)) != len(asset_ids):
        raise PatternValidationError("asset ids must be unique")
    element_ids = [element.id for element in scene.elements]
    if len(set(element_ids)) != len(element_ids):
        raise PatternValidationError("element ids must be unique")
    if any(element.asset_id not in set(asset_ids) for element in scene.elements):
        raise PatternValidationError("element refers to an unknown asset")


def supertile_size(scene: PatternScene) -> tuple[int, int]:
    """Return the normal-grid period needed to represent the scene exactly."""
    if scene.repeat_mode is RepeatMode.HALF_ROW:
        return scene.width, scene.height * 2
    if scene.repeat_mode is RepeatMode.HALF_COLUMN:
        return scene.width * 2, scene.height
    if scene.repeat_mode is RepeatMode.MIRROR:
        return scene.width * 2, scene.height * 2
    return scene.width, scene.height


def render_supertile(scene: PatternScene) -> Image.Image:
    """Render the rectangular full period, wrapping rotated boundary elements."""
    width, height = supertile_size(scene)
    if width * height > MAX_RENDER_PIXELS:
        raise PatternValidationError("supertile exceeds safe render size")
    if scene.repeat_mode is RepeatMode.MIRROR:
        return _mirror_supertile(scene)
    assets = _inspect_referenced_assets(scene)
    plans = [(element, _transform_size(assets[element.asset_id][1], element))
             for element in sorted(scene.elements, key=lambda item: (item.z_index, item.id))]
    composite_count = sum(_copy_count(scene, element, image_size, width, height)
                          for element, image_size in plans)
    if composite_count > MAX_COMPOSITES:
        raise PatternValidationError("scene exceeds safe composite count")
    canvas = Image.new("RGBA", (width, height), scene.background)
    for element, image_size in plans:
        image = _load_and_transform(assets[element.asset_id], element, image_size)
        min_i, max_i, min_j, max_j = _copy_bounds(scene, element, image_size, width, height)
        for row in range(min_j, max_j + 1):
            for column in range(min_i, max_i + 1):
                center_x, center_y = _copy_center(scene, element, column, row)
                _alpha_center(canvas, image, center_x, center_y)
        # Do not retain transformed images from prior elements while preparing
        # the next one; scenes may contain many distinct scales/rotations.
        del image
    return canvas


def _mirror_supertile(scene: PatternScene) -> Image.Image:
    """Mirror one rendered cell into a 2x2 period; opposite edges meet by reflection."""
    cell = render_supertile(PatternScene(
        scene.width, scene.height, scene.assets, scene.elements, RepeatMode.STRAIGHT,
        scene.seed, scene.background, scene.schema_version))
    output = Image.new("RGBA", (cell.width * 2, cell.height * 2))
    output.paste(cell, (0, 0))
    output.paste(cell.transpose(Image.Transpose.FLIP_LEFT_RIGHT), (cell.width, 0))
    output.paste(cell.transpose(Image.Transpose.FLIP_TOP_BOTTOM), (0, cell.height))
    output.paste(cell.transpose(Image.Transpose.ROTATE_180), (cell.width, cell.height))
    return output


def render_preview(scene: PatternScene, copies: int = 3, max_pixels: int = MAX_PREVIEW_PIXELS) -> Image.Image:
    """Render a 3x3/5x5 local repeat preview, reducing resolution if bounded."""
    if copies not in (3, 5):
        raise PatternValidationError("preview copies must be 3 or 5")
    if isinstance(max_pixels, bool) or not isinstance(max_pixels, int) or not copies * copies <= max_pixels <= MAX_PREVIEW_PIXELS:
        raise PatternValidationError(f"max_pixels must be in {copies * copies}..{MAX_PREVIEW_PIXELS}")
    tile_width, tile_height = supertile_size(scene)
    width, height = tile_width * copies, tile_height * copies
    if width * height <= max_pixels:
        tile = render_supertile(scene)
        output = Image.new("RGBA", (width, height))
        for y in range(copies):
            for x in range(copies):
                output.alpha_composite(tile, (x * tile.width, y * tile.height))
        return output
    factor = math.sqrt(max_pixels / (width * height))
    scaled_scene = _scaled_scene(scene, factor)
    scaled_width, scaled_height = supertile_size(scaled_scene)
    if scaled_width * scaled_height * copies * copies > max_pixels:
        # Integer rounding and shifted periods can make a nominal scale exceed
        # the budget. Reject before allocating rather than silently overriding it.
        raise PatternValidationError("preview budget cannot fit the rounded repeat period")
    tile = render_supertile(scaled_scene)
    output = Image.new("RGBA", (tile.width * copies, tile.height * copies))
    for y in range(copies):
        for x in range(copies):
            output.alpha_composite(tile, (x * tile.width, y * tile.height))
    return output


def rebuild_layout(scene: PatternScene, *, element_count: int | None = None,
                   fixed_elements: Iterable[PatternElement] = ()) -> PatternScene:
    """Deterministically replace unlocked elements while retaining locked/fixed ones.

    This intentionally simple local layout is a reproducible starting point for
    a future editor, not a collision solver.  It never accesses asset files.
    """
    fixed = tuple(fixed_elements)
    if any(item.asset_id not in {asset.id for asset in scene.assets} for item in fixed):
        raise PatternValidationError("fixed element refers to an unknown asset")
    retained = tuple(item for item in scene.elements if item.locked) + fixed
    requested = len([item for item in scene.elements if not item.locked]) if element_count is None else element_count
    if not isinstance(requested, int) or requested < 0 or len(retained) + requested > MAX_ELEMENTS:
        raise PatternValidationError("element_count is outside supported limits")
    if not scene.assets and requested:
        raise PatternValidationError("cannot layout elements without assets")
    rng = random.Random(scene.seed)
    assets = tuple(sorted(scene.assets, key=lambda item: item.id))
    generated = tuple(PatternElement(
        id=f"layout-{index:04d}", asset_id=rng.choice(assets).id,
        x=rng.uniform(0, scene.width), y=rng.uniform(0, scene.height),
        scale=rng.uniform(0.75, 1.25), angle=rng.uniform(-30, 30), z_index=index,
    ) for index in range(requested))
    # Avoid generated IDs colliding with preserved IDs deterministically.
    existing = {item.id for item in retained}
    generated = tuple(item if item.id not in existing else PatternElement(
        id=f"generated-{index:04d}", asset_id=item.asset_id, x=item.x, y=item.y,
        scale=item.scale, angle=item.angle, z_index=item.z_index,
    ) for index, item in enumerate(generated))
    return PatternScene(scene.width, scene.height, scene.assets, retained + generated,
                        scene.repeat_mode, scene.seed, scene.background, scene.schema_version)


def _inspect_referenced_assets(scene: PatternScene) -> dict[str, tuple[AssetRef, tuple[int, int]]]:
    """Check only assets used by elements, without retaining decoded images."""
    references = {asset.id: asset for asset in scene.assets}
    required = {element.asset_id for element in scene.elements}
    inspected: dict[str, tuple[AssetRef, tuple[int, int]]] = {}
    total_pixels = 0
    for asset_id in required:
        asset = references[asset_id]
        path = Path(asset.path)
        if not path.is_file():
            raise PatternValidationError(f"asset file is missing: {asset.id}")
        try:
            with Image.open(path) as image:
                if image.format != "PNG":
                    raise PatternValidationError(f"asset image is not PNG: {asset.id}")
                pixels = image.width * image.height
                if (image.width > MAX_DIMENSION or image.height > MAX_DIMENSION or pixels > MAX_ASSET_PIXELS):
                    raise PatternValidationError(f"asset image exceeds safe size: {asset.id}")
                total_pixels += pixels
                if total_pixels > MAX_TOTAL_DECODED_PIXELS:
                    raise PatternValidationError("referenced assets exceed safe decoded size")
                inspected[asset.id] = (asset, image.size)
        except PatternValidationError:
            raise
        except (OSError, ValueError) as exc:
            raise PatternValidationError(f"asset image is unreadable: {asset.id}") from exc
    return inspected


def _scaled_scene(scene: PatternScene, factor: float) -> PatternScene:
    """Make a temporary preview-only coordinate scale without changing scene data."""
    return PatternScene(
        max(1, round(scene.width * factor)), max(1, round(scene.height * factor)), scene.assets,
        tuple(PatternElement(item.id, item.asset_id, item.x * factor, item.y * factor,
                             item.scale * factor, item.angle, item.locked, item.z_index)
              for item in scene.elements),
        scene.repeat_mode, scene.seed, scene.background, scene.schema_version,
    )


def _transform_size(source_size: tuple[int, int], element: PatternElement) -> tuple[int, int]:
    scaled_width = max(1, round(source_size[0] * element.scale))
    scaled_height = max(1, round(source_size[1] * element.scale))
    radians = math.radians(element.angle % 360)
    width = math.ceil(abs(scaled_width * math.cos(radians)) + abs(scaled_height * math.sin(radians))) + 2
    height = math.ceil(abs(scaled_width * math.sin(radians)) + abs(scaled_height * math.cos(radians))) + 2
    if width * height > MAX_TRANSFORM_PIXELS:
        raise PatternValidationError("transformed element exceeds safe size")
    return width, height


def _load_and_transform(asset_data: tuple[AssetRef, tuple[int, int]], element: PatternElement,
                        expected_size: tuple[int, int]) -> Image.Image:
    asset, inspected_size = asset_data
    try:
        with Image.open(asset.path) as source:
            if (source.format != "PNG" or source.size != inspected_size
                    or source.width * source.height > MAX_ASSET_PIXELS):
                raise PatternValidationError(f"asset image changed or is invalid: {asset.id}")
            image = source.convert("RGBA")
    except PatternValidationError:
        raise
    except (OSError, ValueError) as exc:
        raise PatternValidationError(f"asset image is unreadable: {asset.id}") from exc
    size = (max(1, round(image.width * element.scale)), max(1, round(image.height * element.scale)))
    scaled = image.resize(size, Image.Resampling.LANCZOS) if size != image.size else image
    transformed = scaled.rotate(-element.angle, expand=True, resample=Image.Resampling.BICUBIC)
    if (transformed.width * transformed.height > MAX_TRANSFORM_PIXELS
            or transformed.width > expected_size[0] or transformed.height > expected_size[1]):
        raise PatternValidationError("transformed element exceeds safe size")
    if scaled is not image:
        del scaled
    del image
    return transformed


def _copy_bounds(scene: PatternScene, element: PatternElement, image_size: tuple[int, int],
                 width: int, height: int) -> tuple[int, int, int, int]:
    bleed_x = math.ceil(image_size[0] / 2) + scene.width
    bleed_y = math.ceil(image_size[1] / 2) + scene.height
    min_i = math.floor((-bleed_x - element.x) / scene.width)
    max_i = math.ceil((width + bleed_x - element.x) / scene.width)
    min_j = math.floor((-bleed_y - element.y) / scene.height)
    max_j = math.ceil((height + bleed_y - element.y) / scene.height)
    return min_i, max_i, min_j, max_j


def _copy_count(scene: PatternScene, element: PatternElement, image_size: tuple[int, int],
                width: int, height: int) -> int:
    min_i, max_i, min_j, max_j = _copy_bounds(scene, element, image_size, width, height)
    return (max_i - min_i + 1) * (max_j - min_j + 1)


def _copy_center(scene: PatternScene, element: PatternElement, column: int, row: int) -> tuple[float, float]:
    x, y = element.x + column * scene.width, element.y + row * scene.height
    if scene.repeat_mode is RepeatMode.HALF_ROW:
        x += (row % 2) * scene.width / 2
    elif scene.repeat_mode is RepeatMode.HALF_COLUMN:
        y += (column % 2) * scene.height / 2
    return x, y


def _alpha_center(canvas: Image.Image, image: Image.Image, x: float, y: float) -> None:
    canvas.alpha_composite(image, (round(x - image.width / 2), round(y - image.height / 2)))
