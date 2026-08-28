"""Protected, deterministic compositing for Pinterest product pins."""

from __future__ import annotations

import hashlib
import os
import tempfile
from io import BytesIO
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageChops, ImageFilter


PIN_SIZE = (1000, 1500)


class ProductLayerError(RuntimeError):
    """The product image cannot be safely turned into a protected layer."""


class ProductFidelityError(RuntimeError):
    """The composited result no longer contains the protected product pixels."""


class PinExportError(RuntimeError):
    """The requested export cannot preserve the protected RGBA pin."""


@dataclass(frozen=True, slots=True, init=False)
class ProductLayer:
    source_path: str
    _size: tuple[int, int]
    _rgb_bytes: bytes
    _alpha_bytes: bytes

    def __init__(self, source_path: str, rgba: Image.Image, alpha_mask: Image.Image):
        rgba_image = rgba.convert("RGBA")
        alpha = _alpha_from_provider_result(alpha_mask, rgba_image.size)
        object.__setattr__(self, "source_path", str(source_path))
        object.__setattr__(self, "_size", rgba_image.size)
        object.__setattr__(self, "_rgb_bytes", rgba_image.convert("RGB").tobytes())
        object.__setattr__(self, "_alpha_bytes", alpha.tobytes())

    @property
    def rgba(self) -> Image.Image:
        rgba = Image.frombytes("RGB", self._size, self._rgb_bytes).convert("RGBA")
        rgba.putalpha(self.alpha_mask)
        return rgba

    @property
    def alpha_mask(self) -> Image.Image:
        return Image.frombytes("L", self._size, self._alpha_bytes)


@dataclass(frozen=True, slots=True)
class _FidelityReference:
    source_digest: str
    product_box: tuple[int, int, int, int]
    region_rgba: bytes


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
        provider_result = provider(source.copy())
    except ProductLayerError as error:
        if str(error) == "background removal provider unavailable":
            raise ProductLayerError("background removal provider unavailable") from None
        raise ProductLayerError("background removal provider failed") from None
    except Exception:
        raise ProductLayerError("background removal provider failed") from None
    return _alpha_from_provider_result(provider_result, source.size)


def _alpha_with_local_rembg(source: Image.Image) -> Image.Image:
    try:
        from rembg import new_session, remove
    except (ImportError, OSError):
        raise ProductLayerError("background removal provider unavailable") from None
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
    except (OSError, ValueError):
        raise ProductLayerError("background removal returned an invalid alpha mask") from None


def _alpha_with_local_ben2(source: Image.Image) -> Image.Image:
    try:
        from main import load_local_ben2_model
    except (ImportError, OSError):
        raise ProductLayerError("background removal provider unavailable") from None
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
    except (OSError, ValueError):
        raise ProductLayerError("product image could not be loaded") from None

    alpha = source_alpha if source_alpha is not None and source_alpha.getextrema()[0] < 255 else None
    if alpha is None:
        alpha = _mask_from_provider(source_rgb, background_provider)

    rgba = source_rgb.convert("RGBA")
    rgba.putalpha(alpha)
    return ProductLayer(source_path=str(path), rgba=rgba, alpha_mask=alpha)


def product_layer_digest(product: ProductLayer) -> str:
    """Return a stable digest of the protected source RGB pixels and alpha mask."""

    digest = hashlib.sha256()
    digest.update(product._size[0].to_bytes(4, "big"))
    digest.update(product._size[1].to_bytes(4, "big"))
    digest.update(product._rgb_bytes)
    digest.update(product._alpha_bytes)
    return digest.hexdigest()


def _image_digest(image: Image.Image) -> str:
    rgba = image.convert("RGBA")
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
    rgba = Image.frombytes("RGB", product._size, product._rgb_bytes).convert("RGBA")
    rgba.putalpha(Image.frombytes("L", product._size, product._alpha_bytes))
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
    protected_source = _protected_rgba(product)
    product_rgba = protected_source.resize(
        (right - left, bottom - top),
        Image.Resampling.LANCZOS,
    )
    result = background.convert("RGBA")
    if add_shadow:
        shadow_alpha = product_rgba.getchannel("A").filter(ImageFilter.GaussianBlur(radius=10))
        shadow_canvas = Image.new("L", PIN_SIZE, 0)
        shadow_canvas.paste(shadow_alpha.point(lambda value: value * 72 // 255), (left + 8, top + 10))
        product_occupancy = Image.new("L", PIN_SIZE, 0)
        product_occupancy.paste(
            product_rgba.getchannel("A").point(lambda value: 255 if value else 0),
            (left, top),
        )
        outside_product = product_occupancy.point(lambda value: 0 if value else 255)
        shadow = Image.new("RGBA", PIN_SIZE, (0, 0, 0, 0))
        shadow.putalpha(ImageChops.multiply(shadow_canvas, outside_product))
        result.alpha_composite(shadow)
    result.alpha_composite(product_rgba, dest=(left, top))
    result.info["_vibix_pinterest_product_fidelity"] = _FidelityReference(
        source_digest=_image_digest(protected_source),
        product_box=(left, top, right, bottom),
        region_rgba=result.crop((left, top, right, bottom)).tobytes(),
    )
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
    reference = result.info.get("_vibix_pinterest_product_fidelity")
    if not isinstance(reference, _FidelityReference):
        raise ProductFidelityError("Product fidelity guard: protected composition reference is unavailable")
    if reference.product_box != (left, top, right, bottom):
        raise ProductFidelityError("Product fidelity guard: product box does not match protected composition")
    if reference.source_digest != _image_digest(source):
        raise ProductFidelityError("Product fidelity guard: source does not match protected composition")
    expected_alpha = source.convert("RGBA").resize(
        (right - left, bottom - top),
        Image.Resampling.LANCZOS,
    ).getchannel("A")
    actual = result.convert("RGBA").crop((left, top, right, bottom)).tobytes()
    mismatches = 0
    locations: list[tuple[int, int]] = []
    for y in range(expected_alpha.height):
        for x in range(expected_alpha.width):
            if expected_alpha.getpixel((x, y)) == 0:
                continue
            offset = (y * expected_alpha.width + x) * 4
            if reference.region_rgba[offset:offset + 4] != actual[offset:offset + 4]:
                mismatches += 1
                if len(locations) < 5:
                    locations.append((left + x, top + y))
    if mismatches:
        raise ProductFidelityError(
            f"Product fidelity guard: {mismatches} mismatched pixels; locations={locations}"
        )


def save_pin(image: Image.Image, path: str, *, format: str) -> str:
    """Atomically save a Pinterest pin as PNG or white-matted JPEG."""

    normalized_format = str(format).upper()
    export_format = {"PNG": "PNG", "JPG": "JPEG", "JPEG": "JPEG"}.get(normalized_format)
    if export_format is None:
        raise PinExportError("unsupported Pinterest pin export format")
    if image.size != PIN_SIZE:
        raise PinExportError("Pinterest pin export must be 1000×1500 pixels")

    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    os.close(descriptor)
    try:
        rgba = image.convert("RGBA")
        if export_format == "JPEG":
            flattened = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            flattened.alpha_composite(rgba)
            flattened.convert("RGB").save(
                temporary_name,
                format="JPEG",
                quality=100,
                subsampling=0,
            )
        else:
            rgba.save(temporary_name, format="PNG")
        with Image.open(temporary_name) as verification:
            verification.load()
            if verification.size != PIN_SIZE:
                raise PinExportError("Pinterest pin export has an invalid canvas size")
            if export_format == "PNG" and "A" not in verification.getbands():
                raise PinExportError("export did not preserve the protected alpha channel")
            if export_format == "JPEG" and verification.mode != "RGB":
                raise PinExportError("JPEG export has an invalid color mode")
        os.replace(temporary_name, target)
    except PinExportError:
        raise
    except (OSError, ValueError):
        raise PinExportError("Pinterest pin export failed") from None
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        except OSError:
            pass
    return str(target)
