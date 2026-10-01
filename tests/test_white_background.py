"""Known-truth mask fixtures; these do not establish neural-model accuracy."""

from io import BytesIO
from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image, ImageDraw

from white_background import (
    WhiteBackgroundAmbiguousError,
    remove_white_background,
    remove_white_background_with_local_model,
)


def subject_fixture(*, paper=False):
    size = (73, 61)
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((20, 16, 50, 46), fill=255)
    # White petals connect directly to an indistinguishable white canvas.
    draw.rectangle((33, 6, 36, 22), fill=255)
    draw.rectangle((46, 30, 66, 30), fill=255)  # One-pixel tip.
    draw.rectangle((29, 43, 29, 54), fill=255)  # One-pixel stem.
    draw.rectangle((31, 30, 35, 34), fill=0)  # Genuine opening.
    if paper:
        rng = np.random.default_rng(942)
        grain = rng.integers(230, 256, (size[1], size[0], 1), dtype=np.uint8)
        pixels = np.repeat(grain, 3, axis=2)
        pixels[:, :, 2] = np.maximum(pixels[:, :, 2], 233)
        image = Image.fromarray(pixels)
    else:
        image = Image.new("RGB", size, "white")
    painted = Image.new("RGB", size, (100, 90, 65))
    painted_draw = ImageDraw.Draw(painted)
    painted_draw.rectangle((33, 6, 36, 22), fill="white")
    painted_draw.rectangle((46, 30, 66, 30), fill=(251, 249, 245))
    painted_draw.ellipse((22, 23, 27, 28), fill="white")
    image.paste(painted, mask=mask)
    return image, mask


@pytest.mark.parametrize("paper", [False, True])
def test_known_truth_white_petals_highlight_thin_tips_and_opening(paper):
    source, truth = subject_fixture(paper=paper)
    original = source.tobytes()
    original_mask = truth.tobytes()
    result = remove_white_background(source, foreground_mask=truth)
    assert result.getchannel("A").tobytes() == truth.tobytes()
    assert result.convert("RGB").tobytes() == original
    assert result.getpixel((34, 9)) == (255, 255, 255, 255)
    assert result.getpixel((25, 25)) == (255, 255, 255, 255)
    assert result.getpixel((66, 30))[3] == 255
    assert result.getpixel((29, 54))[3] == 255
    assert result.getpixel((33, 32))[3] == 0
    assert source.tobytes() == original
    assert truth.tobytes() == original_mask


def test_missing_mask_rejects_even_outlined_subject_instead_of_guessing():
    source, _ = subject_fixture()
    original = source.tobytes()
    with pytest.raises(WhiteBackgroundAmbiguousError, match="Белые детали"):
        remove_white_background(source)
    assert source.tobytes() == original


def test_input_alpha_is_never_resurrected_or_strengthened():
    source, truth = subject_fixture()
    source = source.convert("RGBA")
    source.putpixel((34, 9), (255, 255, 255, 0))
    source.putpixel((25, 25), (255, 255, 255, 97))
    original = source.tobytes()
    result = remove_white_background(source, foreground_mask=truth)
    assert result.getpixel((34, 9))[3] == 0
    assert result.getpixel((25, 25))[3] == 97
    assert np.all(np.asarray(result.getchannel("A")) <= np.asarray(source.getchannel("A")))
    assert result.convert("RGB").tobytes() == source.convert("RGB").tobytes()
    assert source.tobytes() == original


def test_threshold_removes_soft_shadow_without_eroding_supported_thin_tip():
    source, truth = subject_fixture()
    source_draw = ImageDraw.Draw(source)
    source_draw.rectangle((18, 48, 55, 50), fill=(230, 230, 230))
    model_mask = truth.copy()
    ImageDraw.Draw(model_mask).rectangle((18, 48, 55, 50), fill=65)
    model_mask.putpixel((66, 30), 128)
    result = remove_white_background(source, foreground_mask=model_mask)
    assert result.getpixel((55, 49))[3] == 0
    assert result.getpixel((66, 30))[3] == 255
    assert set(np.unique(np.asarray(result.getchannel("A")))) == {0, 255}


@pytest.mark.parametrize("bad_mask", [
    None, "mask", Image.new("RGB", (73, 61)), Image.new("1", (73, 61)),
    Image.new("L", (72, 61)), Image.new("L", (73, 61), 0),
    Image.new("L", (73, 61), 127), Image.new("L", (73, 61), 128),
    Image.new("L", (73, 61), 255),
])
def test_invalid_mask_rejects_without_source_mutation(bad_mask):
    source, _ = subject_fixture()
    original = source.tobytes()
    with pytest.raises(WhiteBackgroundAmbiguousError):
        remove_white_background(source, foreground_mask=bad_mask)
    assert source.tobytes() == original


def test_no_visible_subject_after_intersecting_existing_alpha_rejects():
    source, truth = subject_fixture()
    source = source.convert("RGBA")
    source.putalpha(Image.new("L", source.size, 0))
    with pytest.raises(WhiteBackgroundAmbiguousError, match="видимый объект"):
        remove_white_background(source, foreground_mask=truth)


@pytest.mark.parametrize("background", [(0, 0, 255), (190, 190, 190), (250, 221, 220)])
def test_nonwhite_background_rejects_before_local_inference(background):
    source = Image.new("RGB", (73, 61), background)
    remover = Mock()
    with pytest.raises(WhiteBackgroundAmbiguousError, match="Внешний фон"):
        remove_white_background_with_local_model(source, session=object(), remove=remover)
    remover.assert_not_called()


@pytest.mark.parametrize("session,remover", [(None, Mock()), (object(), None), (object(), "remove")])
def test_adapter_requires_existing_session_and_callable(session, remover):
    source, _ = subject_fixture()
    with pytest.raises(WhiteBackgroundAmbiguousError, match="недоступна"):
        remove_white_background_with_local_model(source, session=session, remove=remover)
    if isinstance(remover, Mock):
        remover.assert_not_called()


@pytest.mark.parametrize("as_bytes", [False, True])
def test_adapter_reuses_existing_session_and_ignores_model_rgb(as_bytes):
    source, truth = subject_fixture(paper=True)
    source.info.update(dpi=(300, 300), icc_profile=b"test-icc-profile")
    original = source.tobytes()
    segmented = Image.new("RGBA", source.size, (20, 230, 40, 0))
    segmented.putalpha(truth)
    data = BytesIO()
    segmented.save(data, format="PNG")
    model_result = data.getvalue() if as_bytes else segmented
    session = object()
    def existing_remove(png_bytes, *, session):
        with Image.open(BytesIO(png_bytes)) as model_input:
            assert model_input.mode == "RGB"
            assert model_input.tobytes() == original
        return model_result
    remover = Mock(side_effect=existing_remove)
    result = remove_white_background_with_local_model(source, session=session, remove=remover)
    remover.assert_called_once()
    assert remover.call_args.kwargs["session"] is session
    assert result.getchannel("A").tobytes() == truth.tobytes()
    assert result.convert("RGB").tobytes() == original
    assert result.info == source.info
    assert source.tobytes() == original


@pytest.mark.parametrize("model_result", [
    b"not an image", b"\x89PNG\r\n\x1a\n", 42,
    Image.new("RGB", (73, 61)), Image.new("RGBA", (12, 12)),
    Image.new("RGBA", (73, 61), (30, 40, 50, 0)),
    Image.new("RGBA", (73, 61), (30, 40, 50, 255)),
])
def test_adapter_invalid_result_rejects(model_result):
    source, _ = subject_fixture()
    original = source.tobytes()
    with pytest.raises(WhiteBackgroundAmbiguousError):
        remove_white_background_with_local_model(source, session=object(), remove=lambda *a, **kw: model_result)
    assert source.tobytes() == original


def test_actual_png_save_reopen_preserves_pixels_dpi_icc_and_source_bytes(tmp_path):
    source, truth = subject_fixture(paper=True)
    source_path = tmp_path / "source.png"
    output_path = tmp_path / "cutout.png"
    source.save(source_path, dpi=(300, 300), icc_profile=b"known-test-profile")
    original_bytes = source_path.read_bytes()
    with Image.open(source_path) as loaded:
        result = remove_white_background(loaded, foreground_mask=truth)
    result.save(output_path, dpi=result.info["dpi"], icc_profile=result.info["icc_profile"])
    with Image.open(output_path) as reopened:
        assert reopened.mode == "RGBA"
        assert reopened.size == source.size
        assert reopened.tobytes() == result.tobytes()
        assert reopened.info["dpi"] == pytest.approx((300, 300), abs=0.01)
        assert reopened.info["icc_profile"] == b"known-test-profile"
    assert source_path.read_bytes() == original_bytes


def test_paletted_source_preserves_existing_transparency():
    source, truth = subject_fixture()
    source = source.quantize(colors=8)
    transparent_index = source.getpixel((34, 9))
    source.info["transparency"] = transparent_index
    expected_rgb = source.convert("RGBA").convert("RGB").tobytes()
    result = remove_white_background(source, foreground_mask=truth)
    assert result.getpixel((34, 9))[3] == 0
    assert result.convert("RGB").tobytes() == expected_rgb
    assert "transparency" not in result.info


def test_invalid_source_and_tiny_canvas_reject():
    with pytest.raises(TypeError):
        remove_white_background("image")
    with pytest.raises(WhiteBackgroundAmbiguousError, match="Недостаточный размер"):
        remove_white_background(Image.new("RGB", (1, 8), "white"))
