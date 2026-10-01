"""Conservative white-background cutout from an independent foreground mask.

White subject pixels and white background can be identical. Colour alone cannot
prove which is which, so this module deliberately requires a foreground mask.
It never floods or globally erases white pixels. The local-model adapter reuses
an existing session; it does not create sessions, import rembg, or fetch models.
Model segmentation quality remains a limitation, especially for white petals.
"""

from __future__ import annotations

from collections.abc import Callable
from io import BytesIO

import numpy as np
from PIL import Image


class WhiteBackgroundAmbiguousError(ValueError):
    """The input or foreground mask cannot support a safe cutout."""


def _source_rgba(image: Image.Image) -> Image.Image:
    if not isinstance(image, Image.Image):
        raise TypeError("Ожидается изображение PIL")
    if min(image.size) < 2:
        raise WhiteBackgroundAmbiguousError("Недостаточный размер изображения для удаления белого фона")
    rgba = image.convert("RGBA")
    pixels = np.asarray(rgba)
    border = np.concatenate((pixels[0], pixels[-1], pixels[1:-1, 0], pixels[1:-1, -1]))
    visible = border[:, 3] > 0
    if np.any(visible):
        rgb = border[visible, :3].astype(np.int16)
        white = (rgb.min(axis=1) >= 220) & (rgb.max(axis=1) - rgb.min(axis=1) <= 24)
        if float(white.mean()) < 0.9:
            raise WhiteBackgroundAmbiguousError(
                "Внешний фон не является однородным белым или светлой бумагой; выберите другой метод"
            )
    return rgba


def remove_white_background(
    image: Image.Image,
    *,
    foreground_mask: Image.Image | None = None,
) -> Image.Image:
    """Return a defensive RGBA cutout, preserving source RGB and existing alpha.

    ``foreground_mask`` must be an independently obtained L-mode subject mask of
    the original size. Values >=128 are retained, with no erosion, dilation,
    feathering or RGB recolouring. Existing source transparency is never made
    opaque. For opaque inputs the output alpha is strictly binary; any retained
    pre-existing partial alpha remains partial. The caller owns file publication
    and must preserve ``dpi``/``icc_profile`` from the returned ``info`` on save.

    Missing, malformed, empty or all-foreground masks fail without changing the
    input. A plausible mask is not proof of correct semantic segmentation.
    """
    rgba = _source_rgba(image)
    if foreground_mask is None:
        raise WhiteBackgroundAmbiguousError(
            "Белые детали могут сливаться с фоном; нужна уже доступная локальная модель или маска объекта"
        )
    if not isinstance(foreground_mask, Image.Image) or foreground_mask.mode != "L":
        raise WhiteBackgroundAmbiguousError("Маска объекта должна быть изображением PIL в режиме L")
    if foreground_mask.size != rgba.size:
        raise WhiteBackgroundAmbiguousError("Размер маски объекта не совпадает с исходным изображением")
    keep = np.asarray(foreground_mask) >= 128
    if not np.any(keep) or np.all(keep):
        raise WhiteBackgroundAmbiguousError("Не удалось надёжно выделить объект: пустая или сплошная маска")
    alpha = np.asarray(rgba.getchannel("A"))
    result_alpha = np.where(keep, alpha, 0).astype(np.uint8)
    if not np.any(result_alpha) or np.all(result_alpha == 255):
        raise WhiteBackgroundAmbiguousError("Не удалось надёжно выделить видимый объект и прозрачный фон")
    rgba.putalpha(Image.fromarray(result_alpha))
    rgba.info = image.info.copy()
    # Palette transparency is now represented by RGBA, not a PNG palette key.
    rgba.info.pop("transparency", None)
    return rgba


def remove_white_background_with_local_model(
    image: Image.Image,
    *,
    session: object | None,
    remove: Callable | None,
) -> Image.Image:
    """Reuse a caller-supplied loaded rembg session without model preparation.

    The adapter invokes the existing ``remove(png_bytes, session=session)``
    contract and uses only the returned alpha. Model RGB changes are discarded.
    A missing session fails before inference. The caller must supply a local
    remover and an already loaded session; arbitrary callbacks are not sandboxed.
    """
    rgba = _source_rgba(image)
    if session is None or not callable(remove):
        raise WhiteBackgroundAmbiguousError(
            "Локальная модель для белого фона недоступна; загрузка модели автоматически не выполняется"
        )
    data = BytesIO()
    rgba.convert("RGB").save(data, format="PNG")
    segmented = remove(data.getvalue(), session=session)
    if isinstance(segmented, Image.Image):
        if "A" not in segmented.getbands():
            raise WhiteBackgroundAmbiguousError("Локальная модель не вернула маску прозрачности")
        mask = segmented.getchannel("A").copy()
    elif isinstance(segmented, bytes):
        try:
            with Image.open(BytesIO(segmented)) as output:
                if "A" not in output.getbands():
                    raise WhiteBackgroundAmbiguousError("Локальная модель не вернула маску прозрачности")
                if output.size != rgba.size:
                    raise WhiteBackgroundAmbiguousError("Размер результата локальной модели изменён")
                mask = output.getchannel("A").copy()
        except (OSError, SyntaxError, ValueError) as exc:
            if isinstance(exc, WhiteBackgroundAmbiguousError):
                raise
            raise WhiteBackgroundAmbiguousError("Локальная модель вернула некорректное изображение") from exc
    else:
        raise WhiteBackgroundAmbiguousError("Локальная модель вернула некорректный тип результата")
    return remove_white_background(image, foreground_mask=mask)
