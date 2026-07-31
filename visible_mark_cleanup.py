"""Bounded local removal of small visible generator marks."""

from dataclasses import dataclass
import os
import tempfile

import cv2
import numpy as np
from PIL import Image

from third_party.remove_ai_watermarks_gemini import GeminiEngine


GEMINI_MIN_CONFIDENCE = 0.5
MAX_CONFIRMED_REGION_FRACTION = 0.15
GEMINI_ALPHA_MIN = 0.005
CONFIRMED_GLYPH_MIN_PIXELS = 20
CONFIRMED_GLYPH_MAX_SATURATION = 55
CONFIRMED_GLYPH_MIN_LUMA = 150
CONFIRMED_GLYPH_TOPHAT_DELTA = 12


class VisibleMarkCleanupError(RuntimeError):
    pass


class VisibleMarkCleanupCancelled(VisibleMarkCleanupError):
    pass


@dataclass(frozen=True)
class VisibleMarkCleanupResult:
    changed: bool
    confidence: float = 0.0
    region: tuple[int, int, int, int] | None = None
    changed_pixels_inside_mask: int = 0
    changed_pixels_outside_mask: int = 0


def visible_mark_region_key(path):
    return os.path.normcase(os.path.realpath(os.path.abspath(os.fspath(path))))


def normalize_confirmed_region(region, image_size):
    if not isinstance(region, (tuple, list)) or len(region) != 4:
        raise VisibleMarkCleanupError("Область метки должна содержать x, y, ширину и высоту")

    width, height = image_size
    try:
        x, y, region_width, region_height = (int(value) for value in region)
    except (TypeError, ValueError) as error:
        raise VisibleMarkCleanupError("Область метки содержит некорректные координаты") from error

    x1 = max(0, min(width, x))
    y1 = max(0, min(height, y))
    x2 = max(0, min(width, x + region_width))
    y2 = max(0, min(height, y + region_height))
    if x2 <= x1 or y2 <= y1:
        raise VisibleMarkCleanupError("Область метки пуста или находится вне изображения")

    normalized = (x1, y1, x2 - x1, y2 - y1)
    if normalized[2] * normalized[3] > width * height * MAX_CONFIRMED_REGION_FRACTION:
        percentage = round(MAX_CONFIRMED_REGION_FRACTION * 100)
        raise VisibleMarkCleanupError(
            f"Область метки слишком большая; выберите не более {percentage}% изображения"
        )
    return normalized


def _gemini_reverse_alpha(bgr, engine, region):
    x, y, width, height = region
    alpha = np.asarray(engine.get_interpolated_alpha(width), dtype=np.float32)
    if alpha.shape != (height, width):
        alpha = cv2.resize(alpha, (width, height), interpolation=cv2.INTER_LINEAR)
    alpha = np.clip(alpha, 0.0, 0.95)
    active = alpha > GEMINI_ALPHA_MIN
    if not np.any(active):
        raise VisibleMarkCleanupError("Маска восстановления Gemini пуста")

    source_roi = bgr[y : y + height, x : x + width].astype(np.float32)
    alpha_3d = alpha[..., None]
    recovered = np.clip(
        (source_roi - alpha_3d * float(engine.logo_value)) / (1.0 - alpha_3d),
        0,
        255,
    ).astype(np.uint8)
    result = bgr.copy()
    result_roi = result[y : y + height, x : x + width]
    result_roi[active] = recovered[active]
    result[y : y + height, x : x + width] = result_roi

    mask = np.zeros(bgr.shape[:2], dtype=np.uint8)
    mask_roi = mask[y : y + height, x : x + width]
    mask_roi[active] = 255
    mask[y : y + height, x : x + width] = mask_roi
    return result, mask


def _confirmed_region_mask(bgr, region):
    x, y, width, height = region
    fallback = np.zeros(bgr.shape[:2], dtype=np.uint8)
    fallback[y : y + height, x : x + width] = 255
    if width < 16 or height < 16:
        return fallback

    roi = bgr[y : y + height, x : x + width].astype(np.float32)
    luma = roi.mean(axis=2)
    saturation = roi.max(axis=2) - roi.min(axis=2)
    sigma = max(4.0, height * 0.4)
    local_background = cv2.GaussianBlur(luma, (0, 0), sigmaX=sigma, sigmaY=sigma)
    glyph = (
        (saturation < CONFIRMED_GLYPH_MAX_SATURATION)
        & ((luma - local_background) > CONFIRMED_GLYPH_TOPHAT_DELTA)
        & (luma > CONFIRMED_GLYPH_MIN_LUMA)
    ).astype(np.uint8) * 255
    kernel = np.ones((5, 5), dtype=np.uint8)
    glyph = cv2.morphologyEx(glyph, cv2.MORPH_CLOSE, kernel)
    glyph = cv2.morphologyEx(glyph, cv2.MORPH_OPEN, kernel)
    glyph_y, glyph_x = np.where(glyph > 0)
    if glyph_x.size < CONFIRMED_GLYPH_MIN_PIXELS:
        return fallback

    padding = max(4, int(0.10 * height))
    left = max(x, x + int(glyph_x.min()) - padding)
    top = max(y, y + int(glyph_y.min()) - padding)
    right = min(x + width, x + int(glyph_x.max()) + 1 + padding)
    bottom = min(y + height, y + int(glyph_y.max()) + 1 + padding)
    mask = np.zeros(bgr.shape[:2], dtype=np.uint8)
    mask[top:bottom, left:right] = 255
    dilation = max(3, int(0.02 * width))
    ellipse = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (dilation * 2 + 1, dilation * 2 + 1),
    )
    mask = cv2.dilate(mask, ellipse)
    confirmed_bounds = fallback > 0
    mask[~confirmed_bounds] = 0
    return mask


def _feather_inside_mask(source, generated, mask):
    mask_pixels = mask > 0
    if not np.any(mask_pixels):
        return source.copy()
    mask_y, mask_x = np.where(mask_pixels)
    shortest_side = min(
        int(mask_x.max() - mask_x.min() + 1),
        int(mask_y.max() - mask_y.min() + 1),
    )
    feather = max(2, min(12, int(round(shortest_side * 0.09))))
    distance = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    weight = np.clip(distance / float(feather), 0.0, 1.0)[..., None]
    result = np.clip(
        source.astype(np.float32) * (1.0 - weight)
        + generated.astype(np.float32) * weight,
        0,
        255,
    ).astype(np.uint8)
    result[~mask_pixels] = source[~mask_pixels]
    return result


def _fallback_inpaint_bgr(image_bgr, mask):
    """Use OpenCV when the optional ONNX backend is unavailable."""
    return cv2.inpaint(image_bgr, mask, 3, cv2.INPAINT_NS)


def cleanup_visible_mark(
    input_path,
    output_path,
    mode,
    confirmed_region=None,
    engine=None,
    cancelled=None,
):
    input_path = os.path.abspath(os.fspath(input_path))
    output_path = os.path.abspath(os.fspath(output_path))
    if input_path == output_path:
        raise VisibleMarkCleanupError("Результат удаления метки не должен перезаписывать исходник")
    if not os.path.isfile(input_path):
        raise VisibleMarkCleanupError(f"Исходное изображение не найдено: {input_path}")

    def check_cancelled():
        if cancelled is not None and cancelled():
            raise VisibleMarkCleanupCancelled("Удаление видимой метки отменено")

    check_cancelled()
    try:
        with Image.open(input_path) as source:
            if int(getattr(source, "n_frames", 1) or 1) != 1:
                raise VisibleMarkCleanupError("Удаление видимой метки поддерживает только однокадровые изображения")
            source.load()
            has_alpha = "A" in source.getbands() or "transparency" in source.info
            normalized_mode = "RGBA" if has_alpha else "RGB"
            normalized = source.convert(normalized_mode)
            source_size = normalized.size
            source_info = dict(source.info)
            rgb = np.asarray(normalized.convert("RGB"), dtype=np.uint8)
            alpha = np.asarray(normalized.getchannel("A"), dtype=np.uint8).copy() if has_alpha else None
    except VisibleMarkCleanupError:
        raise
    except Exception as error:
        raise VisibleMarkCleanupError(f"Не удалось прочитать исходное изображение: {error}") from error

    if rgb.size == 0 or rgb.shape[0] <= 0 or rgb.shape[1] <= 0:
        raise VisibleMarkCleanupError("Исходное изображение не содержит пикселей")

    check_cancelled()
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    mode_value = str(mode or "gemini_auto").strip().lower()
    confidence = 0.0

    if mode_value == "gemini_auto":
        detector = engine or GeminiEngine()
        try:
            detection = detector.detect_watermark(bgr)
            confidence = float(getattr(detection, "confidence", 0.0) or 0.0)
            if not bool(getattr(detection, "detected", False)) or confidence < GEMINI_MIN_CONFIDENCE:
                return VisibleMarkCleanupResult(changed=False, confidence=confidence)
            region = normalize_confirmed_region(getattr(detection, "region", None), source_size)
            cleaned_bgr, mask = _gemini_reverse_alpha(bgr, detector, region)
        except VisibleMarkCleanupError:
            raise
        except Exception as error:
            raise VisibleMarkCleanupError(f"Не удалось определить метку Gemini: {error}") from error
        if mask is None or mask.shape != bgr.shape[:2] or not np.any(mask):
            raise VisibleMarkCleanupError("Метка Gemini найдена, но маска удаления пуста")
        mask = np.where(mask > 0, 255, 0).astype(np.uint8)
    elif mode_value == "confirmed_area":
        region = normalize_confirmed_region(confirmed_region, source_size)
        mask = _confirmed_region_mask(bgr, region)
    else:
        raise VisibleMarkCleanupError(f"Неподдерживаемый режим удаления видимой метки: {mode_value}")

    check_cancelled()
    if mode_value == "confirmed_area":
        try:
            from third_party.migan import inpaint_bgr

            generated_bgr = inpaint_bgr(bgr, mask)
            cleaned_bgr = _feather_inside_mask(bgr, generated_bgr, mask)
        except Exception:
            generated_bgr = _fallback_inpaint_bgr(bgr, mask)
            cleaned_bgr = _feather_inside_mask(bgr, generated_bgr, mask)

    changed_mask = np.any(cleaned_bgr != bgr, axis=2)
    inside = mask > 0
    changed_inside = int(np.count_nonzero(changed_mask & inside))
    changed_outside = int(np.count_nonzero(changed_mask & ~inside))
    if changed_outside:
        raise VisibleMarkCleanupError("Удаление метки изменило пиксели вне подтвержденной области")
    if changed_inside == 0:
        return VisibleMarkCleanupResult(
            changed=False,
            confidence=confidence,
            region=region,
        )

    check_cancelled()
    cleaned_rgb = cv2.cvtColor(cleaned_bgr, cv2.COLOR_BGR2RGB)
    result_image = Image.fromarray(cleaned_rgb, mode="RGB")
    if alpha is not None:
        result_image.putalpha(Image.fromarray(alpha, mode="L"))

    output_dir = os.path.dirname(output_path)
    os.makedirs(output_dir, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=".visible-mark-",
            suffix=".tmp.png",
            dir=output_dir,
            delete=False,
        ) as temp_file:
            temp_path = temp_file.name

        save_kwargs = {}
        raw_icc = source_info.get("icc_profile")
        if isinstance(raw_icc, bytes) and raw_icc:
            save_kwargs["icc_profile"] = raw_icc
        raw_dpi = source_info.get("dpi")
        if isinstance(raw_dpi, (tuple, list)) and len(raw_dpi) >= 2:
            save_kwargs["dpi"] = (raw_dpi[0], raw_dpi[1])
        result_image.save(temp_path, format="PNG", **save_kwargs)

        check_cancelled()
        if os.path.getsize(temp_path) <= 0:
            raise VisibleMarkCleanupError("Результат удаления метки пуст")
        with Image.open(temp_path) as verification:
            verification.load()
            if verification.size != source_size:
                raise VisibleMarkCleanupError("Размер результата удаления метки неожиданно изменился")
            if verification.mode != normalized_mode:
                raise VisibleMarkCleanupError("Цветовой режим результата удаления метки неожиданно изменился")
            if np.asarray(verification).size == 0:
                raise VisibleMarkCleanupError("Результат удаления метки не содержит пикселей")
            if alpha is not None and not np.array_equal(np.asarray(verification.getchannel("A")), alpha):
                raise VisibleMarkCleanupError("Alpha-канал результата удаления метки неожиданно изменился")

        os.replace(temp_path, output_path)
        temp_path = None
    except VisibleMarkCleanupError:
        raise
    except Exception as error:
        raise VisibleMarkCleanupError(f"Не удалось сохранить результат удаления метки: {error}") from error
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

    return VisibleMarkCleanupResult(
        changed=True,
        confidence=confidence,
        region=region,
        changed_pixels_inside_mask=changed_inside,
        changed_pixels_outside_mask=changed_outside,
    )
