"""Local, read-only quality checks for final transparent Clipart PNG files."""
from __future__ import annotations

from dataclasses import dataclass
from collections import deque
from pathlib import Path

from PIL import Image, ImageColor, UnidentifiedImageError

MAX_QC_PIXELS = 40_000_000
MAX_QC_BYTES = 100 * 1024 * 1024


@dataclass(frozen=True)
class AlphaQcIssue:
    code: str
    severity: str
    message: str
    action: str


@dataclass(frozen=True)
class AlphaQcReport:
    path: str
    status: str
    issues: tuple[AlphaQcIssue, ...]
    width: int = 0
    height: int = 0
    transparent_fraction: float = 0.0
    content_fraction: float = 0.0


def _issue(code: str, severity: str, message: str, action: str) -> AlphaQcIssue:
    return AlphaQcIssue(code=code, severity=severity, message=message, action=action)


def _blocked(path: Path, code: str, message: str, action: str) -> AlphaQcReport:
    return AlphaQcReport(str(path), 'block', (_issue(code, 'block', message, action),))


def _status(issues: list[AlphaQcIssue]) -> str:
    if any(issue.severity == 'block' for issue in issues):
        return 'block'
    if issues:
        return 'review'
    return 'ok'


def _parse_residue_hint(value: str | None) -> tuple[int, int, int] | None:
    if not value:
        return None
    try:
        return ImageColor.getrgb(str(value))
    except (TypeError, ValueError):
        return None


def _has_interior_opening(alpha: Image.Image) -> bool:
    """Detect meaningful central or enclosed transparent space for a wreath/frame."""
    sample = alpha.copy()
    sample.thumbnail((256, 256))
    width, height = sample.size
    if width < 3 or height < 3:
        return False
    pixels = sample.load()
    center_left, center_right = max(1, int(width * 0.35)), min(width - 1, int(width * 0.65))
    center_top, center_bottom = max(1, int(height * 0.35)), min(height - 1, int(height * 0.65))
    center_total = max(1, (center_right - center_left) * (center_bottom - center_top))
    center_transparent = sum(
        1 for y in range(center_top, center_bottom)
        for x in range(center_left, center_right) if pixels[x, y] <= 8
    )
    if center_transparent >= max(16, int(center_total * 0.25)):
        return True
    transparent = bytearray(width * height)
    for y in range(height):
        base = y * width
        for x in range(width):
            transparent[base + x] = 1 if pixels[x, y] <= 8 else 0
    outside = bytearray(width * height)
    queue = deque()
    def add(x, y):
        index = y * width + x
        if transparent[index] and not outside[index]:
            outside[index] = 1
            queue.append((x, y))
    for x in range(width):
        add(x, 0); add(x, height - 1)
    for y in range(1, height - 1):
        add(0, y); add(width - 1, y)
    while queue:
        x, y = queue.popleft()
        if x: add(x - 1, y)
        if x + 1 < width: add(x + 1, y)
        if y: add(x, y - 1)
        if y + 1 < height: add(x, y + 1)
    enclosed = sum(1 for index, value in enumerate(transparent) if value and not outside[index])
    return enclosed >= max(16, int(width * height * 0.005))


def inspect_alpha_png(path: str | Path, *, residue_hint: str | None = None,
                      expect_interior_opening: bool = False) -> AlphaQcReport:
    """Inspect one final PNG without modifying it or calling external services."""
    if type(expect_interior_opening) is not bool:
        raise ValueError('Неверный режим проверки внутреннего отверстия')
    source = Path(path)
    try:
        if not source.is_file() or source.stat().st_size > MAX_QC_BYTES:
            raise OSError('unavailable')
        with Image.open(source) as opened:
            if opened.format != 'PNG':
                return _blocked(
                    source, 'wrong_format', 'Файл результата не является PNG.',
                    'Исключите этот файл из набора или сохраните корректный PNG.',
                )
            if opened.width * opened.height > MAX_QC_PIXELS:
                return _blocked(
                    source, 'too_large', 'PNG слишком большой для безопасной проверки.',
                    'Уменьшите изображение и повторите проверку.',
                )
            had_alpha = 'A' in opened.getbands() or 'transparency' in opened.info
            image = opened.convert('RGBA')
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError, ValueError):
        return _blocked(
            source, 'unreadable', 'Файл не удалось прочитать как изображение.',
            'Повторите обработку или исключите повреждённый дизайн из набора.',
        )

    width, height = image.size
    alpha = image.getchannel('A')
    alpha_min, alpha_max = alpha.getextrema()
    if not had_alpha or alpha_min == 255:
        return AlphaQcReport(
            str(source), 'block',
            (_issue(
                'no_transparency', 'block',
                'В PNG нет прозрачного фона: изображение полностью непрозрачное.',
                'Откройте редактор прозрачности, исправьте фон или исключите дизайн.',
            ),),
            width=width, height=height, transparent_fraction=0.0, content_fraction=1.0,
        )

    # Alpha histogram keeps the check bounded even for large 4K/8K results.
    alpha_histogram = alpha.histogram()
    total = max(1, width * height)
    transparent = sum(alpha_histogram[:6])
    content = total - transparent
    semitransparent = sum(alpha_histogram[9:245])
    transparent_fraction = transparent / total
    content_fraction = content / total
    issues: list[AlphaQcIssue] = []

    # A final clipart with virtually no surviving subject is unusable even if alpha exists.
    if content <= max(4, int(total * 0.001)):
        issues.append(_issue(
            'nearly_empty', 'block',
            'Изображение почти пустое: после обработки осталось слишком мало видимого объекта.',
            'Проверьте маску. Если объект потерян, исключите дизайн или повторите обработку.',
        ))
    elif semitransparent / max(1, content) >= 0.65:
        issues.append(_issue(
            'too_translucent', 'review',
            'Большая часть видимого объекта полупрозрачная; детали могут выглядеть слишком бледными или повреждёнными.',
            'Откройте PNG на контрастном фоне и проверьте прозрачность объекта и его деталей.',
        ))

    # Clipart should retain clear margin around the subject. Ignore isolated single pixels.
    edge_points: list[tuple[int, int]] = []
    if width and height:
        edge_points.extend((x, 0) for x in range(width))
        if height > 1:
            edge_points.extend((x, height - 1) for x in range(width))
        edge_points.extend((0, y) for y in range(1, max(1, height - 1)))
        if width > 1:
            edge_points.extend((width - 1, y) for y in range(1, max(1, height - 1)))
    edge_visible = sum(1 for point in edge_points if image.getpixel(point)[3] > 16)
    if edge_visible >= max(3, int(len(edge_points) * 0.01)):
        issues.append(_issue(
            'touches_edge', 'review',
            'Видимые пиксели доходят до края холста; объект может быть обрезан или рядом остался мусор.',
            'Откройте файл и проверьте края. Исправьте изображение или исключите дизайн.',
        ))

    if expect_interior_opening and not _has_interior_opening(alpha):
        issues.append(_issue(
            'missing_interior_opening', 'review',
            'Внутреннее отверстие венка или рамки выглядит закрытым либо залитым.',
            'Проверьте центр на контрастном фоне. Очистите внутреннее пространство или исключите дизайн.',
        ))

    hint = _parse_residue_hint(residue_hint)
    if hint is not None:
        # Sample a bounded preview instead of materialising every full-resolution pixel.
        sample = image.copy()
        sample.thumbnail((512, 512))
        sample_data = (sample.get_flattened_data()
                       if hasattr(sample, 'get_flattened_data') else sample.getdata())
        threshold_sq = 55 * 55
        semi_count = 0
        hint_like = 0
        for r, g, b, sample_alpha in sample_data:
            if not 8 < sample_alpha < 245:
                continue
            semi_count += 1
            if ((r - hint[0]) ** 2 + (g - hint[1]) ** 2
                    + (b - hint[2]) ** 2 <= threshold_sq):
                hint_like += 1
        if semi_count and hint_like >= max(8, int(semi_count * 0.35)):
            issues.append(_issue(
                'color_fringe', 'review',
                'На полупрозрачных краях обнаружена заметная цветная кайма, похожая на остаток фона.',
                'Откройте редактор прозрачности и очистите края; при необходимости исключите дизайн.',
            ))

    return AlphaQcReport(
        str(source), _status(issues), tuple(issues), width=width, height=height,
        transparent_fraction=transparent_fraction, content_fraction=content_fraction,
    )
