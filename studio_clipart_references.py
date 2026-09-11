"""Local reference metadata and palette sampling; never uploads images."""
from copy import deepcopy
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
