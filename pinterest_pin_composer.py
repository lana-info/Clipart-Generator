"""Protected, deterministic compositing for Pinterest product pins."""

from __future__ import annotations

import os
import tempfile
import hashlib
from io import BytesIO
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageFilter


PIN_SIZE = (1000, 1500)


class ProductLayerError(RuntimeError):
    """The product image cannot be safely turned into a protected layer."""


class ProductFidelityError(RuntimeError):
    """The composited result no longer contains the protected product pixels."""


class PinExportError(RuntimeError):
    """The requested export cannot preserve the protected RGBA pin."""


@dataclass(frozen=True, slots=True)
class ProductLayer:
    source_path: str
    rgba: Image.Image
    alpha_mask: Image.Image


BackgroundMaskProvider = Callable[[Image.Image], Image.Image]
_BACKGROUND_MASK_PROVIDERS: dict[str, BackgroundMaskProvider] = {}


def _alpha_from_provider_result(value: Image.Image, expected_size: tuple[int, int]) -> Image.Image:
    if not isinstance(value, Image.Image):
        raise ProductLayerError("background removal returned an invalid alpha mask")
    if value.size != expected_size:
        raise ProductLayerError("background removal returned an invalid alpha mask")
    if value.mode == "L":
        return value.copy()
    if "A" in value.getbands():
        return value.getchannel("A").copy()
    raise ProductLayerError("background removal returned an invalid alpha mask")


def _mask_from_provider(source: Image.Image, provider_name: str) -> Image.Image:
    if provider_name == "local_rembg":
        provider = _alpha_with_local_rembg
    elif provider_name == "local_ben2":
        provider = _alpha_with_local_ben2
    else:
        provider = _BACKGROUND_MASK_PROVIDERS.get(provider_name)
        if provider is None:
            raise ProductLayerError("background removal provider unavailable")
    try:
        return _alpha_from_provider_result(provider(source.copy()), source.size)
    except ProductLayerError:
        raise
    except Exception as exc:
        raise ProductLayerError("background removal provider failed") from exc


def _alpha_with_local_rembg(source: Image.Image) -> Image.Image:
    try:
        from rembg import new_session, remove
    except (ImportError, OSError) as exc:
        raise ProductLayerError("background removal provider unavailable") from exc
    payload = BytesIO()
    source.save(payload, format="PNG")
    result = remove(payload.getvalue(), session=new_session())
    if isinstance(result, Image.Image):
        return result.copy()
    if not isinstance(result, bytes):
        raise ProductLayerError("background removal returned an invalid alpha mask")
    try:
        with Image.open(BytesIO(result)) as image:
            image.load()
            return image.copy()
    except (OSError, ValueError) as exc:
        raise ProductLayerError("background removal returned an invalid alpha mask") from exc


def _alpha_with_local_ben2(source: Image.Image) -> Image.Image:
    try:
        from main import load_local_ben2_model
    except (ImportError, OSError) as exc:
        raise ProductLayerError("background removal provider unavailable") from exc
    model = load_local_ben2_model()
    try:
        return model.inference(source.convert("RGB"))
    except TypeError:
        return model.inference(source.convert("RGB"), refine_foreground=False)


def load_product_layer(path: str, *, background_provider: str = "local_rembg") -> ProductLayer:
    """Load source RGB once and obtain only an alpha mask from a remover."""

    try:
        with Image.open(path) as image:
            image.load()
            source_rgb = image.convert("RGB")
            source_alpha = image.getchannel("A").copy() if "A" in image.getbands() else None
    except (OSError, ValueError) as exc:
        raise ProductLayerError("product image could not be loaded") from exc

    alpha = source_alpha if source_alpha is not None and source_alpha.getextrema()[0] < 255 else None
    if alpha is None:
        alpha = _mask_from_provider(source_rgb, background_provider)

    rgba = source_rgb.convert("RGBA")
    rgba.putalpha(alpha)
    return ProductLayer(source_path=str(path), rgba=rgba, alpha_mask=alpha)


def product_layer_digest(product: ProductLayer) -> str:
    """Return a stable digest of the protected source RGB pixels and alpha mask."""

    rgba = _protected_rgba(product)
    digest = hashlib.sha256()
    digest.update(rgba.width.to_bytes(4, "big"))
    digest.update(rgba.height.to_bytes(4, "big"))
    digest.update(rgba.convert("RGB").tobytes())
    digest.update(rgba.getchannel("A").tobytes())
    return digest.hexdigest()


def _validate_product_box(box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    if len(box) != 4:
        raise ValueError("product box must contain four coordinates")
    left, top, right, bottom = box
    if not all(isinstance(value, int) for value in box):
        raise ValueError("product box coordinates must be integers")
    if not (0 <= left < right <= PIN_SIZE[0] and 0 <= top < bottom <= PIN_SIZE[1]):
        raise ValueError("product box must fit the Pinterest canvas")
    return left, top, right, bottom


def _protected_rgba(product: ProductLayer) -> Image.Image:
    if product.rgba.size != product.alpha_mask.size:
        raise ProductLayerError("product layer alpha mask does not match its RGB layer")
    rgb = product.rgba.convert("RGB")
    rgba = rgb.convert("RGBA")
    rgba.putalpha(_alpha_from_provider_result(product.alpha_mask, rgb.size))
    return rgba


def composite_product(
    background: Image.Image,
    product: ProductLayer,
    *,
    box: tuple[int, int, int, int],
    add_shadow: bool = True,
) -> Image.Image:
    """Resize the protected source layer and alpha-composite it onto a pin."""

    if background.size != PIN_SIZE:
        raise ValueError("Pinterest background must be 1000×1500 pixels")
    left, top, right, bottom = _validate_product_box(box)
    product_rgba = _protected_rgba(product).resize(
        (right - left, bottom - top),
        Image.Resampling.LANCZOS,
    )
    result = background.convert("RGBA")
    if add_shadow:
        shadow_alpha = product_rgba.getchannel("A").filter(ImageFilter.GaussianBlur(radius=10))
        shadow = Image.new("RGBA", product_rgba.size, (0, 0, 0, 0))
        shadow.putalpha(shadow_alpha.point(lambda value: value * 72 // 255))
        result.alpha_composite(shadow, dest=(left + 8, top + 10))
    result.alpha_composite(product_rgba, dest=(left, top))
    return result


def assert_product_pixels_preserved(
    source: Image.Image,
    result: Image.Image,
    *,
    product_box: tuple[int, int, int, int],
) -> None:
    """Check opaque protected pixels without exposing source image data."""

    left, top, right, bottom = _validate_product_box(product_box)
    if result.size != PIN_SIZE:
        raise ProductFidelityError("Product fidelity guard: result has an invalid canvas size")
    expected = source.convert("RGBA").resize(
        (right - left, bottom - top),
        Image.Resampling.LANCZOS,
    )
    actual = result.convert("RGBA").crop((left, top, right, bottom))
    mismatches = 0
    locations: list[tuple[int, int]] = []
    for y in range(expected.height):
        for x in range(expected.width):
            if expected.getpixel((x, y))[3] != 255:
                continue
            if expected.getpixel((x, y))[:3] != actual.getpixel((x, y))[:3]:
                mismatches += 1
                if len(locations) < 5:
                    locations.append((left + x, top + y))
    if mismatches:
        raise ProductFidelityError(
            f"Product fidelity guard: {mismatches} mismatched pixels; locations={locations}"
        )


def save_pin(image: Image.Image, path: str, *, format: str) -> str:
    """Atomically save an alpha-preserving Pinterest pin export."""

    normalized_format = str(format).upper()
    if normalized_format not in {"PNG", "WEBP"}:
        raise PinExportError(f"{normalized_format or 'requested'} format does not preserve alpha")
    if image.size != PIN_SIZE:
        raise PinExportError("Pinterest pin export must be 1000×1500 pixels")

    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    os.close(descriptor)
    try:
        image.convert("RGBA").save(temporary_name, format=normalized_format)
        with Image.open(temporary_name) as verification:
            verification.load()
            if verification.size != PIN_SIZE or "A" not in verification.getbands():
                raise PinExportError("export did not preserve the protected alpha channel")
        os.replace(temporary_name, target)
    except PinExportError:
        raise
    except (OSError, ValueError) as exc:
        raise PinExportError("Pinterest pin export failed") from exc
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        except OSError:
            pass
    return str(target)
