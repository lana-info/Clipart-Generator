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


def test_save_pin_exports_atomically_with_alpha_and_rejects_jpeg(tmp_path):
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

    unsafe_path = tmp_path / "unsafe.jpg"
    with pytest.raises(module.PinExportError, match="does not preserve alpha"):
        module.save_pin(image, str(unsafe_path), format="JPEG")
    assert not unsafe_path.exists()
