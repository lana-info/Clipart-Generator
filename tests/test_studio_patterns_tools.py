import math

import numpy as np
import pytest
from PIL import Image, ImageFilter

import studio_patterns_tools as tools
from studio_patterns import (
    AssetRef, PatternElement, PatternScene, PatternValidationError, RepeatMode,
    render_supertile, supertile_size,
)
from studio_patterns_tools import (
    SeamStatus, cm_to_px, export_tile, inches_to_px, layout_scene, make_seamless,
    mirror_tile, seam_report, tile_preview, wrap_resize,
)


def _identical(a, b):
    """Exact pixel equality (ImageChops getbbox only inspects alpha on RGBA)."""
    return a.size == b.size and a.mode == b.mode and a.tobytes() == b.tobytes()


def _noise(size, seed=1, mode="RGBA"):
    rng = np.random.default_rng(seed)
    channels = 4 if mode == "RGBA" else 3
    data = rng.integers(0, 256, (size[1], size[0], channels), dtype=np.uint8)
    if mode == "RGBA":
        data[..., 3] = 255
    return Image.fromarray(data, mode)


def _smooth(size, seed=2):
    return _noise(size, seed, "RGB").filter(ImageFilter.GaussianBlur(6))


def _ramp(width=200, height=60):
    row = np.linspace(0, 255, width).astype(np.uint8)
    data = np.repeat(row[None, :, None], height, axis=0).repeat(3, axis=2)
    return Image.fromarray(data, "RGB")


def _motif(tmp_path, name="motif", size=(11, 9), color=(220, 40, 90, 255)):
    path = tmp_path / f"{name}.png"
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    for x in range(1, size[0] - 1):
        for y in range(1, size[1] - 1):
            image.putpixel((x, y), color)
    image.save(path)
    return AssetRef(name, str(path))


# --- wrap-aware resampling -------------------------------------------------

@pytest.mark.parametrize("target", [(40, 30), (10, 9), (24, 18), (17, 31)])
def test_wrap_resize_matches_resize_of_a_triple_tiled_oracle(target):
    tile = _noise((24, 18), seed=7)
    # Independent oracle: resize a 3x3 tiling at the same exact scale and keep the
    # middle period, which no border clamping can reach.
    big = Image.fromarray(np.tile(np.asarray(tile), (3, 3, 1)))
    oracle = big.resize((target[0] * 3, target[1] * 3), Image.Resampling.LANCZOS).crop(
        (target[0], target[1], target[0] * 2, target[1] * 2))
    result = wrap_resize(tile, target)
    assert result.size == target
    assert _identical(result, oracle)


def test_plain_resize_breaks_the_edges_that_wrap_resize_keeps():
    tile = _noise((24, 18), seed=3)
    plain = tile.resize((40, 30), Image.Resampling.LANCZOS)
    wrapped = wrap_resize(tile, (40, 30))
    assert not _identical(plain, wrapped)
    # Away from the border the filters agree, so only the seam handling differs.
    inner = (6, 6, 34, 24)
    assert _identical(plain.crop(inner), wrapped.crop(inner))


def test_wrap_resize_validates_and_does_not_mutate():
    tile = _noise((8, 8))
    before = tile.tobytes()
    for bad in ((0, 4), (4,), (True, 4), (9000, 4), [4, 4]):
        with pytest.raises(PatternValidationError):
            wrap_resize(tile, bad)
    with pytest.raises(PatternValidationError):
        wrap_resize("not an image", (4, 4))
    wrap_resize(tile, (5, 5))
    assert tile.tobytes() == before
    assert wrap_resize(tile, (8, 8)).tobytes() == before


def test_wrap_resize_converts_other_modes():
    assert wrap_resize(Image.new("L", (6, 6), 80), (3, 3)).mode == "RGB"
    assert wrap_resize(Image.new("LA", (6, 6), (80, 128)), (3, 3)).mode == "RGBA"


# --- seam metric ------------------------------------------------------------

@pytest.mark.parametrize("mode", list(RepeatMode))
def test_exact_lattice_supertile_is_ready(tmp_path, mode):
    asset = _motif(tmp_path)
    scene = PatternScene(60, 48, (asset,), (
        PatternElement("a", asset.id, 0, 0, 1.4, 25), PatternElement("b", asset.id, 30, 20, 1.0, -10),
        PatternElement("c", asset.id, 55, 40, 0.8, 70),
    ), mode, background=(250, 245, 235, 255))
    assert seam_report(render_supertile(scene)).status is SeamStatus.READY


def test_hard_seam_fails_and_report_is_per_axis():
    report = seam_report(_ramp())
    assert report.status is SeamStatus.FAIL
    assert report.horizontal > 10 and report.vertical == 0
    assert report.score == report.horizontal
    flipped = seam_report(_ramp().transpose(Image.Transpose.TRANSPOSE))
    assert flipped.vertical > 10 and flipped.horizontal == 0


def test_flat_and_tiny_images_are_ready_without_errors():
    assert seam_report(Image.new("RGB", (30, 20), (9, 9, 9))).status is SeamStatus.READY
    assert seam_report(Image.new("RGB", (1, 1))).score == 0
    assert seam_report(Image.new("RGBA", (2, 1), (255, 0, 0, 255))).status is not None


def test_seam_report_treats_transparent_pixels_by_alpha():
    visible = Image.new("RGBA", (40, 30), (0, 0, 0, 0))
    hidden_colour = Image.new("RGBA", (40, 30), (255, 255, 255, 0))
    assert seam_report(visible).score == seam_report(hidden_colour).score == 0


# --- make seamless ----------------------------------------------------------

def test_make_seamless_fixes_a_ramp():
    ramp = _ramp()
    result = make_seamless(ramp)
    assert result.size == ramp.size and result.mode == ramp.mode
    assert seam_report(result).status is SeamStatus.READY


def test_make_seamless_improves_a_cut_texture_and_keeps_input():
    texture = _smooth((160, 120))
    before = seam_report(texture)
    assert before.status is not SeamStatus.READY
    data = texture.tobytes()
    result = make_seamless(texture, band=0.25)
    assert texture.tobytes() == data
    after = seam_report(result)
    assert after.score < before.score / 2
    assert after.status is SeamStatus.READY


def test_make_seamless_handles_alpha_and_validates():
    transparent = Image.new("RGBA", (30, 20), (255, 0, 0, 0))
    result = make_seamless(transparent)
    assert result.mode == "RGBA" and result.getchannel("A").getextrema() == (0, 0)
    opaque = Image.new("RGBA", (30, 20), (10, 20, 30, 255))
    assert make_seamless(opaque).tobytes() == opaque.tobytes()
    for bad in (0, -1, 0.51, True, "x"):
        with pytest.raises(PatternValidationError):
            make_seamless(opaque, bad)


def test_make_seamless_odd_sizes():
    result = make_seamless(_smooth((37, 29)), band=0.3)
    assert result.size == (37, 29)


# --- mirror -----------------------------------------------------------------

def test_mirror_tile_is_seamless_by_construction_and_doubles_the_size():
    tile = _smooth((50, 40))
    mirrored = mirror_tile(tile)
    assert mirrored.size == (100, 80)
    assert seam_report(mirrored).status is SeamStatus.READY
    assert _identical(mirrored.crop((0, 0, 50, 40)), tile)
    assert _identical(mirrored.crop((50, 0, 100, 40)), tile.transpose(Image.Transpose.FLIP_LEFT_RIGHT))
    assert _identical(mirrored.crop((0, 40, 50, 80)), tile.transpose(Image.Transpose.FLIP_TOP_BOTTOM))


def test_mirror_scene_is_the_mirrored_straight_cell(tmp_path):
    asset = _motif(tmp_path)
    elements = (PatternElement("a", asset.id, 4, 6, 1.2, 33), PatternElement("b", asset.id, 38, 25, 1.0, 0))
    straight = PatternScene(40, 30, (asset,), elements, RepeatMode.STRAIGHT, background=(10, 20, 30, 255))
    mirror = PatternScene(40, 30, (asset,), elements, RepeatMode.MIRROR, background=(10, 20, 30, 255))
    assert supertile_size(mirror) == (80, 60)
    cell = render_supertile(straight)
    expected = mirror_tile(cell)
    assert _identical(render_supertile(mirror), expected)
    assert PatternScene.from_json(mirror.to_json()) == mirror


# --- preview ---------------------------------------------------------------

def test_tile_preview_repeats_and_centres_the_seam():
    tile = _noise((20, 10), seed=4)
    plain = tile_preview(tile, 3, center_seam=False)
    assert plain.size == (60, 30)
    assert plain.getpixel((20, 10)) == tile.getpixel((0, 0))
    centred = tile_preview(tile, 3)
    assert centred.getpixel((0, 0)) == tile.getpixel((10, 5))
    assert tile_preview(tile, 5).size == (100, 50)


def test_tile_preview_budget_and_validation():
    tile = _noise((400, 300))
    bounded = tile_preview(tile, 3, max_pixels=90_000)
    assert bounded.width * bounded.height <= 90_000
    for bad in (dict(copies=4), dict(max_pixels=1), dict(max_pixels=tools.MAX_PREVIEW_PIXELS + 1)):
        with pytest.raises(PatternValidationError):
            tile_preview(tile, **bad)


# --- export ----------------------------------------------------------------

def test_unit_conversion():
    assert inches_to_px(12) == 3600 and inches_to_px(8) == 2400 and inches_to_px(6) == 1800
    assert cm_to_px(30.48) == 3600
    for bad in (0, -1, True, float("inf")):
        with pytest.raises(PatternValidationError):
            inches_to_px(bad)
    with pytest.raises(PatternValidationError):
        inches_to_px(1, dpi=10)


def test_png_export_has_size_dpi_and_srgb(tmp_path):
    tile = _noise((30, 20))
    result = export_tile(tile, tmp_path / "out" / "tile.png", size=(60, 40))
    assert result.size == (60, 40) and result.byte_size == result.path.stat().st_size
    with Image.open(result.path) as saved:
        assert saved.format == "PNG" and saved.size == (60, 40) and saved.mode == "RGBA"
        assert saved.info["dpi"] == pytest.approx((300, 300), abs=0.01)
        assert saved.info.get("icc_profile")
        assert _identical(saved, wrap_resize(tile, (60, 40)))
    assert [p.name for p in result.path.parent.iterdir()] == ["tile.png"]


def test_jpeg_export_flattens_alpha_and_has_dpi(tmp_path):
    tile = Image.new("RGBA", (16, 16), (255, 0, 0, 0))
    result = export_tile(tile, tmp_path / "tile.JPG", dpi=150, background=(10, 200, 30))
    with Image.open(result.path) as saved:
        assert saved.format == "JPEG" and saved.mode == "RGB"
        assert saved.info["dpi"] == pytest.approx((150, 150), abs=0.01)
        assert all(abs(a - b) <= 3 for a, b in zip(saved.getpixel((8, 8)), (10, 200, 30)))


def test_export_validation_and_failure_leave_no_partial_file(tmp_path, monkeypatch):
    tile = _noise((8, 8))
    for kwargs in (dict(path=tmp_path / "x.gif"), dict(path=tmp_path / "x.png", dpi=5),
                   dict(path=tmp_path / "x.jpg", quality=0), dict(path=tmp_path / "x.jpg", background=(1, 2)),
                   dict(path=tmp_path / "x.png", size=(0, 4))):
        with pytest.raises(PatternValidationError):
            export_tile(tile, **kwargs)
    target = tmp_path / "keep.png"
    target.write_bytes(b"previous")

    def failing_save(self, *args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Image.Image, "save", failing_save)
    with pytest.raises(OSError):
        export_tile(tile, target)
    assert target.read_bytes() == b"previous"
    assert [p.name for p in tmp_path.iterdir()] == ["keep.png"]


def test_encoded_size_hint():
    tile = _noise((20, 20))
    assert tools.encoded_size_hint(tile) > 0 and tools.encoded_size_hint(tile, "jpeg") > 0
    with pytest.raises(PatternValidationError):
        tools.encoded_size_hint(tile, "gif")


# --- layout with gaps ------------------------------------------------------

def _lattice_copies(scene, x, y, span=3):
    """Independent infinite-lattice copies of one element."""
    w, h = scene.width, scene.height
    copies = []
    for i in range(-span, span + 1):
        for j in range(-span, span + 1):
            if scene.repeat_mode is RepeatMode.MIRROR:
                copies += [(x + 2 * w * i, y + 2 * h * j), (-x + 2 * w * i, y + 2 * h * j),
                           (x + 2 * w * i, -y + 2 * h * j), (-x + 2 * w * i, -y + 2 * h * j)]
                continue
            cx, cy = x + i * w, y + j * h
            if scene.repeat_mode is RepeatMode.HALF_ROW:
                cx += (j % 2) * w / 2
            elif scene.repeat_mode is RepeatMode.HALF_COLUMN:
                cy += (i % 2) * h / 2
            copies.append((cx, cy))
    return copies


def _radius(size, element):
    return 0.5 * math.hypot(*size) * element.scale


@pytest.mark.parametrize("mode", list(RepeatMode))
def test_layout_respects_the_gap_across_the_repeat(tmp_path, mode):
    asset = _motif(tmp_path, size=(10, 8))
    scene = PatternScene(120, 100, (asset,), (), mode, seed=5)
    result, warnings = layout_scene(scene, count=14, min_gap=6)
    assert warnings == () and len(result.elements) == 14
    elements = result.elements
    for index, a in enumerate(elements):
        own = _lattice_copies(result, a.x, a.y)
        for cx, cy in own:
            if (cx, cy) == (a.x, a.y):
                continue
            assert math.hypot(cx - a.x, cy - a.y) >= 2 * _radius((10, 8), a) + 6 - 1e-6
        for b in elements[index + 1:]:
            need = _radius((10, 8), a) + _radius((10, 8), b) + 6
            assert min(math.hypot(cx - a.x, cy - a.y) for cx, cy in _lattice_copies(result, b.x, b.y)) >= need - 1e-6
    assert seam_report(render_supertile(result)).status is SeamStatus.READY


def test_layout_is_deterministic_keeps_locked_and_avoids_them(tmp_path):
    asset = _motif(tmp_path)
    locked = PatternElement("locked", asset.id, 30, 30, 1.0, 0, locked=True)
    loose = PatternElement("loose", asset.id, 1, 1)
    scene = PatternScene(100, 100, (asset,), (locked, loose), seed=11)
    first, _ = layout_scene(scene, count=6, min_gap=4)
    second, _ = layout_scene(scene, count=6, min_gap=4)
    assert first == second
    assert first.elements[0] == locked and all(e.id != "loose" for e in first.elements)
    others = first.elements[1:]
    assert len(others) == 6
    assert all(math.hypot(e.x - 30, e.y - 30) >= _radius((11, 9), locked) + _radius((11, 9), e) + 4 - 1e-6
               or math.hypot(e.x - 30, e.y - 30) >= 1 for e in others)
    assert first.seed == scene.seed and first.repeat_mode == scene.repeat_mode


def test_layout_reports_when_there_is_no_room(tmp_path):
    asset = _motif(tmp_path)
    scene = PatternScene(30, 30, (asset,), (), seed=1)
    result, warnings = layout_scene(scene, count=20, min_gap=5, max_attempts=30)
    assert 0 < len(result.elements) < 20
    assert warnings and "placed" in warnings[0]


def test_layout_asset_weights_and_validation(tmp_path):
    first, second = _motif(tmp_path, "first"), _motif(tmp_path, "second")
    scene = PatternScene(200, 200, (first, second), (), seed=3)
    result, _ = layout_scene(scene, count=10, asset_weights={"first": 0, "second": 1})
    assert {e.asset_id for e in result.elements} == {"second"}
    for kwargs in (dict(count=-1), dict(count=True), dict(count=1, min_gap=-1),
                   dict(count=1, asset_weights={"nope": 1}), dict(count=1, asset_weights={"first": 0, "second": 0}),
                   dict(count=1, asset_weights={"first": -1}), dict(count=1, scale_range=(0, 1)),
                   dict(count=1, scale_range=(2, 1)), dict(count=1, angle_range=(0, float("nan"))),
                   dict(count=1, max_attempts=0)):
        with pytest.raises(PatternValidationError):
            layout_scene(scene, **kwargs)
    with pytest.raises(PatternValidationError):
        layout_scene(PatternScene(10, 10), count=1)
    assert layout_scene(PatternScene(10, 10), count=0)[0].elements == ()
