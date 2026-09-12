"""Local reference metadata, palette sampling and explicit model handoff helpers."""
from copy import deepcopy
from io import BytesIO
import base64
import hashlib
from pathlib import Path
from PIL import Image, ImageOps

REFERENCE_ROLES = {
    "technique": "Техника / стиль", "palette": "Палитра", "mood": "Настроение",
    "subject": "Предмет", "character": "Персонаж", "pose": "Поза",
    "composition": "Композиция",
}


def validate_references(value):
    if not isinstance(value, list) or len(value) > 20:
        raise ValueError("Можно добавить до 20 референсов")
    for item in value:
        if not isinstance(item, dict) or set(item) != {"path", "roles", "notes"}:
            raise ValueError("Повреждённый референс")
        if not isinstance(item['path'], str) or not 1 <= len(item['path']) <= 4000:
            raise ValueError("Неверный путь референса")
        roles = item['roles']
        if (not isinstance(roles, list) or any(not isinstance(r, str) or r not in REFERENCE_ROLES for r in roles)
                or len(roles) != len(set(roles))):
            raise ValueError("Неизвестная или повторяющаяся роль референса")
        if not isinstance(item['notes'], str) or len(item['notes']) > 4000:
            raise ValueError("Описание референса превышает 4000 символов")
    return deepcopy(value)


MAX_LOCAL_REFERENCE_BYTES = 25 * 1024 * 1024


def reference_file_info(path):
    """Read bounded local metadata without applying the stricter AI-upload limit."""
    source = Path(path)
    try:
        size = source.stat().st_size
    except OSError as error:
        raise ValueError("Референс недоступен") from error
    if size > MAX_LOCAL_REFERENCE_BYTES:
        raise ValueError("Референс превышает 25 МБ")
    try:
        opened = Image.open(source)
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError("Референс недоступен или повреждён") from error
    with opened as image:
        if image.format not in {"PNG", "JPEG", "WEBP"}:
            raise ValueError("Поддерживаются PNG, JPEG и WebP")
        if image.width * image.height > 40_000_000:
            raise ValueError("Референс превышает 40 мегапикселей")
        mime = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[image.format]
        return {"mime_type": mime, "size": size, "width": image.width, "height": image.height}


MAX_MODEL_REFERENCE_BYTES = 10 * 1024 * 1024


def _read_model_reference(path):
    """Read and validate the exact bytes that may be handed to a model."""
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as error:
        raise ValueError("Референс недоступен") from error
    if len(raw) > MAX_MODEL_REFERENCE_BYTES:
        raise ValueError("Референс для AI превышает 10 МБ")
    try:
        with Image.open(BytesIO(raw)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"}:
                raise ValueError
            if image.width * image.height > 40_000_000:
                raise ValueError
            mime = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[image.format]
            width, height = image.width, image.height
            image.verify()
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as error:
        raise ValueError("Референс недоступен или повреждён") from error
    return ({
        "mime_type": mime,
        "size": len(raw),
        "width": width,
        "height": height,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }, raw)


def reference_image_upload_info(path):
    """Validate one local image before consented model handoff; return no path."""
    info, _ = _read_model_reference(path)
    return info


def prepare_reference_image_for_model(path, *, expected_sha256=None):
    """Return validated base64 bytes without exposing the local filename/path."""
    info, raw = _read_model_reference(path)
    if expected_sha256 is not None:
        expected = str(expected_sha256).strip().casefold()
        if len(expected) != 64 or info['sha256'].casefold() != expected:
            raise ValueError("Референс изменился. Выберите его заново")
    return {
        "mime_type": info['mime_type'],
        "size": info['size'],
        "width": info['width'],
        "height": info['height'],
        "data_url": f"data:{info['mime_type']};base64,{base64.b64encode(raw).decode('ascii')}",
    }


def reference_thumbnail(path):
    """Bound decoding and preserve original file. Missing inputs fail only on use."""
    source = Path(path)
    if source.stat().st_size > 25 * 1024 * 1024:
        raise ValueError("Референс превышает 25 МБ")
    try:
        opened = Image.open(source)
    except Image.DecompressionBombError as error:
        raise ValueError("Референс превышает допустимый размер") from error
    with opened as image:
        if image.format not in {"PNG", "JPEG", "WEBP"}:
            raise ValueError("Поддерживаются PNG, JPEG и WebP")
        if image.width * image.height > 40_000_000:
            raise ValueError("Референс превышает 40 мегапикселей")
        image = ImageOps.exif_transpose(image)
        image.thumbnail((480, 320))
        return image.convert('RGBA')


def extract_palette(path):
    image = reference_thumbnail(path)
    # Ignore transparent padding instead of turning it into black/white swatches.
    data = image.get_flattened_data() if hasattr(image, 'get_flattened_data') else image.getdata()
    pixels = [p[:3] for p in data if p[3] >= 128]
    if not pixels:
        raise ValueError("В референсе нет достаточно непрозрачных цветов")
    sample = Image.new('RGB', (len(pixels), 1))
    sample.putdata(pixels)
    quantized = sample.quantize(colors=5)
    palette = quantized.getpalette()
    colors = sorted(quantized.getcolors(), reverse=True)
    return ['#%02X%02X%02X' % tuple(palette[i * 3:i * 3 + 3]) for _, i in colors]
