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
import hashlib
import importlib.util
import os
from pathlib import Path

import numpy as np
from PIL import Image


class WhiteBackgroundAmbiguousError(ValueError):
    """The input or foreground mask cannot support a safe cutout."""


U2NET_MODEL_MD5 = "60024c5c889badc19c04ad937298a77b"


def cached_u2net_model_path() -> Path | None:
    """Find existing rembg caches without importing it or fetching anything.

    Support both the legacy flat layout and the current per-model layout.
    Existence is a UI readiness hint; integrity is checked before model loading.
    """
    xdg = os.environ.get("XDG_DATA_HOME")
    legacy = Path(os.environ.get("U2NET_HOME") or str(Path(xdg or "~") / ".u2net")).expanduser()
    root = legacy if os.environ.get("U2NET_HOME") else Path(
        os.environ.get("REMBG_HOME") or str(Path(xdg) / "rembg" if xdg else Path("~/.rembg"))
    ).expanduser()
    for path in (root / "models/u2net/u2net.onnx", legacy / "u2net.onnx"):
        try:
            if path.is_file() and path.stat().st_size > 0:
                return path
        except OSError:
            continue
    return None


def white_background_available() -> bool:
    """Cheap UI check; no imports of rembg/ONNX, sessions or model downloads."""
    if cached_u2net_model_path() is None:
        return False
    try:
        return all(importlib.util.find_spec(name) is not None for name in ("rembg", "onnxruntime"))
    except (ImportError, ValueError):
        return False


def load_cached_white_background_model() -> tuple[object, Callable]:
    """Load verified cached U2Net; bypass every rembg download code path."""
    path = cached_u2net_model_path()
    if path is None:
        raise WhiteBackgroundAmbiguousError(
            "Локальная модель U2Net не установлена; загрузка автоматически не выполняется"
        )
    try:
        with path.open("rb") as stream:
            checksum = hashlib.file_digest(stream, "md5").hexdigest()
        if checksum != U2NET_MODEL_MD5:
            raise WhiteBackgroundAmbiguousError("Локальная модель U2Net повреждена или не поддерживается")
        from rembg import remove
        from rembg.sessions.u2net import U2netSession
        from onnxruntime import SessionOptions

        class CachedU2netSession(U2netSession):
            @classmethod
            def download_models(cls, *args, **kwargs):
                return str(path)

        options = SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        return CachedU2netSession("u2net", options, providers=["CPUExecutionProvider"]), remove
    except WhiteBackgroundAmbiguousError:
        raise
    except Exception as exc:
        raise WhiteBackgroundAmbiguousError("Не удалось загрузить установленную локальную модель U2Net") from exc


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
