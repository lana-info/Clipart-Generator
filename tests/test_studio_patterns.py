import json

import pytest
from PIL import Image

from studio_patterns import (
    AssetRef, MAX_JSON_BYTES, MAX_PREVIEW_PIXELS, PatternElement, PatternScene,
    PatternValidationError, RepeatMode, rebuild_layout, render_preview,
    render_supertile, supertile_size,
)


def _asset(tmp_path, name="motif.png", size=(9, 7)):
    path = tmp_path / name
    image = Image.new("RGBA", size)
    image.putpixel((0, 0), (255, 0, 0, 255))
    image.putpixel((size[0] - 1, size[1] - 1), (0, 255, 0, 180))
    image.putpixel((size[0] // 2, size[1] // 2), (0, 0, 255, 255))
    image.save(path)
    return AssetRef("motif", str(path))


def _lattice_viewport(scene, asset_path, origin, size):
    """Independent infinite-lattice oracle; it does not call renderer helpers."""
    with Image.open(asset_path) as source:
        source = source.convert("RGBA")
    output = Image.new("RGBA", size, scene.background)
    for element in sorted(scene.elements, key=lambda item: (item.z_index, item.id)):
        scaled = source.resize((round(source.width * element.scale), round(source.height * element.scale)), Image.Resampling.LANCZOS)
        motif = scaled.rotate(-element.angle, expand=True, resample=Image.Resampling.BICUBIC)
        # Deliberately broad fixed lattice around the viewport, independent of
        # production bounds calculation.  Fixtures are small enough for this.
        for row in range(-8, 9):
            for column in range(-8, 9):
                x = element.x + column * scene.width
                y = element.y + row * scene.height
                if scene.repeat_mode is RepeatMode.HALF_ROW:
                    x += (row % 2) * scene.width / 2
                elif scene.repeat_mode is RepeatMode.HALF_COLUMN:
                    y += (column % 2) * scene.height / 2
                output.alpha_composite(motif, (round(x - origin[0] - motif.width / 2),
                                               round(y - origin[1] - motif.height / 2)))
    return output


def _tile(image, copies=2):
    result = Image.new("RGBA", (image.width * copies, image.height * copies))
    for y in range(copies):
        for x in range(copies):
            result.alpha_composite(image, (x * image.width, y * image.height))
    return result


@pytest.mark.parametrize("mode", [RepeatMode.STRAIGHT, RepeatMode.HALF_ROW, RepeatMode.HALF_COLUMN])
def test_supertile_is_pixel_equivalent_to_direct_repeat(tmp_path, mode):
    asset = _asset(tmp_path)
    scene = PatternScene(21, 17, (asset,), (PatternElement("edge", asset.id, 1, 2, 1.1, 21),), mode)
    supertile = render_supertile(scene)
    reference = _lattice_viewport(scene, asset.path, (0, 0), supertile.size)
    next_period = _lattice_viewport(scene, asset.path, supertile.size, supertile.size)
    assert supertile.tobytes() == reference.tobytes()
    # A rectangular supertile must repeat as a straight lattice even for odd
    # source periods and the half-period offsets.
    assert supertile.tobytes() == next_period.tobytes()
    assert supertile.size == supertile_size(scene)


@pytest.mark.parametrize("mode", [RepeatMode.STRAIGHT, RepeatMode.HALF_ROW, RepeatMode.HALF_COLUMN])
def test_rotated_corner_element_wraps_all_corners(tmp_path, mode):
    asset = _asset(tmp_path, size=(13, 11))
    scene = PatternScene(20, 20, (asset,), (PatternElement("corner", asset.id, 0, 0, 1.4, 37),), mode,
                         background=(0, 0, 0, 0))
    tile = render_supertile(scene)
    assert tile.getbbox() is not None
    repeated = _tile(tile)
    # Each outer corner contains the same periodic continuation, not an empty crop.
    assert repeated.getpixel((0, 0))[3] > 0
    assert repeated.getpixel((tile.width, tile.height))[3] > 0


def test_seed_layout_is_deterministic_and_keeps_locks(tmp_path):
    asset = _asset(tmp_path)
    locked = PatternElement("locked", asset.id, 4, 5, 1.0, 8, locked=True)
    scene = PatternScene(50, 40, (asset,), (locked,), seed=1234)
    first = rebuild_layout(scene, element_count=3)
    second = rebuild_layout(scene, element_count=3)
    assert first == second
    assert first.elements[0] == locked
    assert len(first.elements) == 4


def test_json_roundtrip_rejects_malformed_and_limits(tmp_path):
    asset = _asset(tmp_path)
    scene = PatternScene(30, 20, (asset,), (PatternElement("a", asset.id, 2, 3),), seed=99)
    assert PatternScene.from_json(scene.to_json()) == scene
    with pytest.raises(PatternValidationError):
        PatternScene.from_json("not json")
    malformed = json.loads(scene.to_json())
    malformed["elements"][0]["asset_id"] = "missing"
    with pytest.raises(PatternValidationError):
        PatternScene.from_dict(malformed)
    malformed = json.loads(scene.to_json())
    malformed["width"] = 999999
    with pytest.raises(PatternValidationError):
        PatternScene.from_dict(malformed)


def test_preview_is_3x3_or_5x5_and_honours_pixel_bound(tmp_path):
    asset = _asset(tmp_path)
    scene = PatternScene(100, 80, (asset,), (PatternElement("a", asset.id, 5, 5),), RepeatMode.HALF_ROW)
    normal = render_preview(scene, 3)
    assert normal.size == (300, 480)
    bounded = render_preview(scene, 5, max_pixels=1_000)
    assert bounded.width * bounded.height <= 1_000
    with pytest.raises(PatternValidationError):
        render_preview(scene, 4)
    with pytest.raises(PatternValidationError):
        render_preview(scene, 3, max_pixels=1)
    with pytest.raises(PatternValidationError):
        render_preview(scene, 3, max_pixels=MAX_PREVIEW_PIXELS + 1)

    # The source period would exceed the render limit, but preview first scales
    # the scene and therefore never allocates 25 full-resolution tiles.
    giant = PatternScene(8_192, 8_192, (asset,), (PatternElement("giant", asset.id, 5, 5),), RepeatMode.HALF_ROW)
    giant_preview = render_preview(giant, 5, max_pixels=1_000)
    assert giant_preview.width * giant_preview.height <= 1_000


def test_renderer_validates_asset_existence_format_and_size(tmp_path):
    missing = AssetRef("missing", str(tmp_path / "missing.png"))
    missing_scene = PatternScene(10, 10, (missing,), (PatternElement("a", missing.id, 1, 1),))
    with pytest.raises(PatternValidationError, match="missing"):
        render_supertile(missing_scene)

    jpg_path = tmp_path / "not-png.jpg"
    Image.new("RGB", (2, 2)).save(jpg_path)
    jpeg = AssetRef("jpeg", str(jpg_path))
    jpeg_scene = PatternScene(10, 10, (jpeg,), (PatternElement("a", jpeg.id, 1, 1),))
    with pytest.raises(PatternValidationError, match="not PNG"):
        render_supertile(jpeg_scene)

    large_path = tmp_path / "large.png"
    Image.new("RGBA", (8_193, 1)).save(large_path)
    large = AssetRef("large", str(large_path))
    large_scene = PatternScene(10, 10, (large,), (PatternElement("a", large.id, 1, 1),))
    with pytest.raises(PatternValidationError, match="safe size"):
        render_supertile(large_scene)


def test_direct_constructors_and_json_are_strictly_bounded(tmp_path):
    asset = _asset(tmp_path)
    with pytest.raises(PatternValidationError):
        PatternElement("nan", asset.id, float("nan"), 1)
    with pytest.raises(PatternValidationError):
        PatternElement("bool", asset.id, True, 1)
    with pytest.raises(PatternValidationError):
        PatternScene(True, 10, (asset,))
    with pytest.raises(PatternValidationError):
        PatternScene(10, 10, [asset])
    with pytest.raises(PatternValidationError):
        PatternScene.from_json(" " * (MAX_JSON_BYTES + 1))
    too_many = {"schema_version": 1, "width": 1, "height": 1, "assets": [{}] * 501, "elements": []}
    with pytest.raises(PatternValidationError, match="exceeds"):
        PatternScene.from_dict(too_many)


def test_preview_checks_rounded_dimensions_before_allocating():
    with pytest.raises(PatternValidationError, match="rounded repeat"):
        render_preview(PatternScene(1, 2), copies=3, max_pixels=11)


def test_renderer_only_reads_referenced_assets_and_rejects_excessive_work(tmp_path):
    asset = _asset(tmp_path)
    unused_missing = AssetRef("unused", str(tmp_path / "never-read.png"))
    scene = PatternScene(20, 20, (asset, unused_missing), (PatternElement("a", asset.id, 2, 2),))
    assert render_supertile(scene).size == (20, 20)

    sprite_path = tmp_path / "sprite.png"
    Image.new("RGBA", (100, 100), (255, 0, 0, 255)).save(sprite_path)
    sprite = AssetRef("sprite", str(sprite_path))
    pathological = PatternScene(1, 1, (sprite,), (PatternElement("big", sprite.id, 0, 0, scale=32),))
    with pytest.raises(PatternValidationError, match="composite"):
        render_supertile(pathological)

    transform_path = tmp_path / "transform.png"
    Image.new("RGBA", (800, 800), (255, 0, 0, 255)).save(transform_path)
    transform = AssetRef("transform", str(transform_path))
    oversized = PatternScene(10, 10, (transform,), (PatternElement("too-big", transform.id, 1, 1, scale=32),))
    with pytest.raises(PatternValidationError, match="transformed"):
        render_supertile(oversized)
