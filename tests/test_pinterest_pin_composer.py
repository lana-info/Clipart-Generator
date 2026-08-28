from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from PIL import Image

try:
    import pinterest_pin_composer as composer
except ModuleNotFoundError:
    composer = None


def _require_composer():
    assert composer is not None, "Pinterest product composer module is missing"
    return composer


def _rgb_fixture(size: tuple[int, int] = (8, 6)) -> Image.Image:
    image = Image.new("RGB", size)
    for y in range(size[1]):
        for x in range(size[0]):
            image.putpixel((x, y), ((x * 29) % 256, (y * 47) % 256, ((x + y) * 31) % 256))
    return image


def _hard_alpha(size: tuple[int, int]) -> Image.Image:
    alpha = Image.new("L", size, 0)
    alpha.paste(255, (1, 1, size[0] - 1, size[1] - 1))
    return alpha


def _semi_alpha(size: tuple[int, int]) -> Image.Image:
    alpha = Image.new("L", size, 0)
    alpha.paste(128, (1, 1, size[0] - 1, size[1] - 1))
    return alpha


def _product_layer(source: Image.Image, alpha: Image.Image):
    module = _require_composer()
    rgba = source.convert("RGBA")
    rgba.putalpha(alpha)
    return module.ProductLayer("product.png", rgba, alpha)


def test_load_preserves_original_digest_and_uses_external_provider_as_alpha_only(tmp_path, monkeypatch):
    module = _require_composer()
    source_path = tmp_path / "private-product.png"
    source = _rgb_fixture()
    source.save(source_path, format="PNG")
    digest_before = hashlib.sha256(source_path.read_bytes()).hexdigest()
    mask = _hard_alpha(source.size)

    corrupted_provider_image = Image.new("RGBA", source.size, (255, 0, 255, 0))
    corrupted_provider_image.putalpha(mask)
    monkeypatch.setitem(module._BACKGROUND_MASK_PROVIDERS, "external", lambda image: corrupted_provider_image)

    product = module.load_product_layer(str(source_path), background_provider="external")

    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == digest_before
    assert product.source_path == str(source_path)
    assert product.alpha_mask.mode == "L"
    assert product.alpha_mask.tobytes() == mask.tobytes()
    assert product.rgba.getchannel("A").tobytes() == mask.tobytes()
    assert product.rgba.convert("RGB").tobytes() == source.tobytes()


def test_load_uses_existing_alpha_without_calling_an_unavailable_provider(tmp_path):
    module = _require_composer()
    source_path = tmp_path / "transparent-product.png"
    source = _rgb_fixture().convert("RGBA")
    alpha = _hard_alpha(source.size)
    source.putalpha(alpha)
    source.save(source_path, format="PNG")

    product = module.load_product_layer(str(source_path), background_provider="unavailable")

    assert product.rgba.convert("RGB").tobytes() == source.convert("RGB").tobytes()
    assert product.alpha_mask.tobytes() == alpha.tobytes()


def test_load_rejects_opaque_product_when_provider_is_unavailable_without_exposing_path(tmp_path):
    module = _require_composer()
    source_path = tmp_path / "private-product.png"
    _rgb_fixture().save(source_path, format="PNG")

    with pytest.raises(module.ProductLayerError, match="unavailable") as error:
        module.load_product_layer(str(source_path), background_provider="unavailable")

    assert str(source_path) not in str(error.value)


def test_load_rejects_malformed_provider_mask_without_changing_product_rgb(tmp_path, monkeypatch):
    module = _require_composer()
    source_path = tmp_path / "private-product.png"
    source = _rgb_fixture()
    source.save(source_path, format="PNG")
    malformed_mask = Image.new("L", (source.width - 1, source.height), 255)
    monkeypatch.setitem(module._BACKGROUND_MASK_PROVIDERS, "external", lambda image: malformed_mask)

    with pytest.raises(module.ProductLayerError, match="invalid alpha mask"):
        module.load_product_layer(str(source_path), background_provider="external")

    with Image.open(source_path) as unchanged:
        assert unchanged.convert("RGB").tobytes() == source.tobytes()


def test_provider_failure_is_a_sanitized_domain_error_without_a_raw_cause(tmp_path, monkeypatch):
    module = _require_composer()
    source_path = tmp_path / "private-product.png"
    _rgb_fixture().save(source_path, format="PNG")

    def failing_provider(image):
        raise RuntimeError("provider failure at /private/product.png; api_key=secret-value")

    monkeypatch.setitem(module._BACKGROUND_MASK_PROVIDERS, "external", failing_provider)

    with pytest.raises(module.ProductLayerError) as error:
        module.load_product_layer(str(source_path), background_provider="external")

    assert str(error.value) == "background removal provider failed"
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__ is True


@pytest.mark.parametrize(
    ("provider_name", "adapter_name"),
    (("local_rembg", "_alpha_with_local_rembg"), ("local_ben2", "_alpha_with_local_ben2")),
)
def test_local_background_removers_contribute_only_alpha(tmp_path, monkeypatch, provider_name, adapter_name):
    module = _require_composer()
    source_path = tmp_path / "private-product.png"
    source = _rgb_fixture()
    source.save(source_path, format="PNG")
    mask = _hard_alpha(source.size)
    provider_result = Image.new("RGBA", source.size, (255, 0, 255, 0))
    provider_result.putalpha(mask)
    monkeypatch.setattr(module, adapter_name, lambda image: provider_result, raising=False)

    product = module.load_product_layer(str(source_path), background_provider=provider_name)

    assert product.alpha_mask.tobytes() == mask.tobytes()
    assert product.rgba.convert("RGB").tobytes() == source.tobytes()


def test_product_layer_digest_is_stable_and_includes_source_rgb_and_alpha():
    module = _require_composer()
    source = _rgb_fixture()
    alpha = _hard_alpha(source.size)
    product = _product_layer(source, alpha)
    expected = hashlib.sha256(
        source.width.to_bytes(4, "big")
        + source.height.to_bytes(4, "big")
        + source.tobytes()
        + alpha.tobytes()
    ).hexdigest()
    changed_alpha = alpha.copy()
    changed_alpha.putpixel((1, 1), 0)

    assert module.product_layer_digest(product) == expected
    assert module.product_layer_digest(product) == expected
    assert module.product_layer_digest(_product_layer(source, changed_alpha)) != expected


def test_product_layer_defensive_copies_prevent_external_pillow_mutation():
    module = _require_composer()
    source = _rgb_fixture()
    alpha = _hard_alpha(source.size)
    product = _product_layer(source, alpha)
    box = (220, 350, 780, 1100)
    expected = module.composite_product(
        Image.new("RGBA", (1000, 1500), (21, 37, 53, 255)), product, box=box, add_shadow=False
    )
    digest = module.product_layer_digest(product)

    product.rgba.putpixel((3, 2), (255, 0, 255, 0))
    product.alpha_mask.putpixel((3, 2), 0)

    actual = module.composite_product(
        Image.new("RGBA", (1000, 1500), (21, 37, 53, 255)), product, box=box, add_shadow=False
    )
    assert module.product_layer_digest(product) == digest
    assert actual.tobytes() == expected.tobytes()


def test_composite_matches_deterministic_resize_reference_and_preserves_product_pixels():
    module = _require_composer()
    source = _rgb_fixture((8, 6))
    product = _product_layer(source, _hard_alpha(source.size))
    background = Image.new("RGB", (1000, 1500), (21, 37, 53))
    box = (220, 350, 780, 1100)

    result = module.composite_product(background, product, box=box, add_shadow=False)
    reference = background.convert("RGBA")
    expected_layer = product.rgba.resize((560, 750), Image.Resampling.LANCZOS)
    reference.alpha_composite(expected_layer, dest=(220, 350))

    assert result.size == (1000, 1500)
    assert "A" in result.getbands()
    assert result.tobytes() == reference.tobytes()
    module.assert_product_pixels_preserved(product.rgba, result, product_box=box)


def test_shadow_never_changes_any_alpha_bearing_product_pixel():
    module = _require_composer()
    source = _rgb_fixture((8, 6))
    product = _product_layer(source, _semi_alpha(source.size))
    box = (220, 350, 780, 1100)
    background = Image.new("RGBA", (1000, 1500), (21, 37, 53, 255))
    without_shadow = module.composite_product(background, product, box=box, add_shadow=False)
    with_shadow = module.composite_product(background, product, box=box, add_shadow=True)
    transformed_alpha = product.alpha_mask.resize((560, 750), Image.Resampling.LANCZOS)

    for y in range(transformed_alpha.height):
        for x in range(transformed_alpha.width):
            if transformed_alpha.getpixel((x, y)) > 0:
                assert with_shadow.getpixel((box[0] + x, box[1] + y)) == without_shadow.getpixel((box[0] + x, box[1] + y))


def test_fidelity_guard_reports_only_mismatch_count_and_locations():
    module = _require_composer()
    source = _rgb_fixture((8, 6))
    product = _product_layer(source, _hard_alpha(source.size))
    box = (220, 350, 780, 1100)
    result = module.composite_product(Image.new("RGB", (1000, 1500), (21, 37, 53)), product, box=box, add_shadow=False)
    result.putpixel((450, 650), (0, 0, 0, 255))

    with pytest.raises(module.ProductFidelityError) as error:
        module.assert_product_pixels_preserved(product.rgba, result, product_box=box)

    message = str(error.value)
    assert "mismatched pixels" in message
    assert "locations" in message
    assert "product.png" not in message
    assert "(450, 650)" in message


def test_fidelity_guard_detects_rgb_change_inside_a_semitransparent_product_pixel():
    module = _require_composer()
    source = _rgb_fixture((8, 6))
    product = _product_layer(source, _semi_alpha(source.size))
    box = (220, 350, 780, 1100)
    result = module.composite_product(Image.new("RGBA", (1000, 1500)), product, box=box, add_shadow=False)
    result.putpixel((450, 650), (0, 0, 0, 128))

    with pytest.raises(module.ProductFidelityError, match="mismatched pixels"):
        module.assert_product_pixels_preserved(product.rgba, result, product_box=box)


def test_fidelity_guard_detects_alpha_change_inside_a_semitransparent_product_pixel():
    module = _require_composer()
    source = _rgb_fixture((8, 6))
    product = _product_layer(source, _semi_alpha(source.size))
    box = (220, 350, 780, 1100)
    result = module.composite_product(Image.new("RGBA", (1000, 1500)), product, box=box, add_shadow=False)
    original = result.getpixel((450, 650))
    result.putpixel((450, 650), (*original[:3], original[3] - 1))

    with pytest.raises(module.ProductFidelityError, match="mismatched pixels"):
        module.assert_product_pixels_preserved(product.rgba, result, product_box=box)


def test_save_pin_exports_png_and_jpeg_with_a_white_matte(tmp_path):
    module = _require_composer()
    image = Image.new("RGBA", (1000, 1500), (12, 34, 56, 128))
    output = tmp_path / "result.png"

    saved_path = module.save_pin(image, str(output), format="PNG")

    assert Path(saved_path) == output.resolve()
    with Image.open(output) as saved:
        saved.load()
        assert saved.mode == "RGBA"
        assert saved.size == (1000, 1500)
        assert saved.getchannel("A").getextrema() == (128, 128)
    assert not list(tmp_path.glob(".result.png.*.tmp"))

    jpeg_path = tmp_path / "result.jpg"
    module.save_pin(image, str(jpeg_path), format="JPG")
    with Image.open(jpeg_path) as saved_jpeg:
        saved_jpeg.load()
        assert saved_jpeg.mode == "RGB"
        assert saved_jpeg.size == (1000, 1500)
        expected_rgb = Image.alpha_composite(
            Image.new("RGBA", image.size, (255, 255, 255, 255)), image
        ).convert("RGB").getpixel((0, 0))
        actual_rgb = saved_jpeg.getpixel((0, 0))
        assert all(abs(actual - expected) <= 1 for actual, expected in zip(actual_rgb, expected_rgb))

    unsafe_path = tmp_path / "unsafe.tiff"
    with pytest.raises(module.PinExportError, match="unsupported"):
        module.save_pin(image, str(unsafe_path), format="TIFF")
    assert not unsafe_path.exists()


@pytest.mark.parametrize("setup_step", ("resolve", "mkdir", "mkstemp", "close"))
def test_save_pin_sanitizes_filesystem_setup_failures(tmp_path, monkeypatch, setup_step):
    module = _require_composer()
    image = Image.new("RGBA", (1000, 1500), (12, 34, 56, 128))
    private_message = "/private/output/secret-product.png; provider_message=secret-value"

    def failing_setup(*args, **kwargs):
        raise OSError(private_message)

    if setup_step == "resolve":
        monkeypatch.setattr(module.Path, "resolve", failing_setup)
    elif setup_step == "mkdir":
        monkeypatch.setattr(module.Path, "mkdir", failing_setup)
    elif setup_step == "mkstemp":
        monkeypatch.setattr(module.tempfile, "mkstemp", failing_setup)
    else:
        original_close = module.os.close

        def close_then_fail(descriptor):
            original_close(descriptor)
            raise OSError(private_message)

        monkeypatch.setattr(module.os, "close", close_then_fail)

    with pytest.raises(module.PinExportError) as error:
        module.save_pin(image, str(tmp_path / "result.png"), format="PNG")

    assert str(error.value) == "Pinterest pin export failed"
    assert private_message not in str(error.value)
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__ is True


@pytest.mark.parametrize("cleanup_error", (RuntimeError, ValueError))
def test_save_pin_sanitizes_close_cleanup_failures(tmp_path, monkeypatch, cleanup_error):
    module = _require_composer()
    image = Image.new("RGBA", (1000, 1500), (12, 34, 56, 128))
    private_message = "/private/output/secret-product.png; cleanup_message=secret-value"
    original_close = module.os.close
    close_calls = 0

    def fail_setup_then_cleanup(descriptor):
        nonlocal close_calls
        close_calls += 1
        if close_calls == 1:
            raise OSError("setup close failure")
        original_close(descriptor)
        raise cleanup_error(private_message)

    monkeypatch.setattr(module.os, "close", fail_setup_then_cleanup)

    with pytest.raises(module.PinExportError) as error:
        module.save_pin(image, str(tmp_path / "result.png"), format="PNG")

    assert str(error.value) == "Pinterest pin export failed"
    assert private_message not in str(error.value)
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__ is True


@pytest.mark.parametrize("cleanup_error", (RuntimeError, ValueError))
def test_save_pin_ignores_unlink_cleanup_failures_after_atomic_export(tmp_path, monkeypatch, cleanup_error):
    module = _require_composer()
    image = Image.new("RGBA", (1000, 1500), (12, 34, 56, 128))
    output = tmp_path / "result.png"
    private_message = "/private/output/secret-product.png; cleanup_message=secret-value"

    def failing_unlink(path):
        raise cleanup_error(private_message)

    monkeypatch.setattr(module.os, "unlink", failing_unlink)

    saved_path = module.save_pin(image, str(output), format="PNG")

    assert Path(saved_path) == output.resolve()
    assert output.is_file()
