"""Conservative preservation of supplied alpha, without inferred quality claims."""
from PIL import Image


def preserve_native_alpha(image: Image.Image) -> Image.Image:
    """Keep coverage and visible RGB exact; clear RGB only where alpha is zero.

    This is not a cutout quality certificate, sharpening or halo removal.
    Reject empty output instead of publishing an invisible successful result.
    """
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    if alpha.getextrema()[1] == 0:
        raise ValueError("Изображение полностью прозрачное: видимый предмет отсутствует")
    hidden = alpha.point(lambda value: 255 if value == 0 else 0)
    rgba.paste((0, 0, 0, 0), mask=hidden)
    return rgba
