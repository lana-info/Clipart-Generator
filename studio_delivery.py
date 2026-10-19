"""Backend helpers for naming generated clipart and making contact sheets."""

from __future__ import annotations

import os
import re
import tempfile
import unicodedata
from itertools import islice
import math
from pathlib import Path
from typing import Iterable, Iterator, Sequence


MAX_TITLE_WORDS = 3
MAX_SLUG_LENGTH = 80
MAX_CONTACT_SHEET_IMAGES = 10_000
MAX_IMAGE_DIMENSION = 20_000
MAX_IMAGE_PIXELS = 100_000_000

_WORD_RE = re.compile(r"[\w]+", re.UNICODE)
_WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


_RU_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def transliterate_ru(text: str) -> str:
    """Letter-by-letter Russian -> Latin (owner rule: transliterate, never translate)."""
    result = []
    for char in text:
        mapped = _RU_TRANSLIT.get(char.lower())
        if mapped is None:
            result.append(char)
        else:
            result.append(mapped.capitalize() if char.isupper() else mapped)
    return "".join(result)


def slug_from_title(title: str, *, max_words: int = MAX_TITLE_WORDS) -> str:
    """Return a filesystem-safe, short slug from a user-facing short title."""
    if not isinstance(title, str):
        raise TypeError("title must be a string")
    if not 1 <= max_words <= 10:
        raise ValueError("max_words must be between 1 and 10")
    normalized = transliterate_ru(unicodedata.normalize("NFKC", title)).replace("_", " ")
    words = _WORD_RE.findall(normalized)
    words = [word.casefold() for word in words[:max_words] if word.strip()]
    slug = "-".join(words)[:MAX_SLUG_LENGTH].strip("-.")
    if not slug:
        slug = "clipart"
    if slug.split("-")[0] in _WINDOWS_RESERVED:
        slug = f"item-{slug}"
    return slug


def output_filename(
    ordinal: int,
    title: str,
    *,
    variant: str | int | None = None,
    extension: str = ".png",
    existing_names: Iterable[str | os.PathLike[str]] = (),
) -> str:
    """Build a stable generated filename; ordinal is assigned by the caller's input order."""
    if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 1:
        raise ValueError("ordinal must be a positive integer")
    extension = str(extension)
    if not extension.startswith(".") or not re.fullmatch(r"\.[A-Za-z0-9]{1,8}", extension):
        raise ValueError("extension must be a simple file extension")
    slug = slug_from_title(title)
    variant_slug = ""
    if variant is not None:
        variant_slug = slug_from_title(str(variant), max_words=3)
        variant_slug = f"-{variant_slug}"
    base = f"{ordinal:03d}_{slug}{variant_slug}"
    # Keep the suffix and ordinal intact even for unusually long titles.
    base = base[: 150 - len(extension)]
    candidate = f"{base}{extension.lower()}"
    used = {Path(str(name)).name.casefold() for name in existing_names}
    if candidate.casefold() not in used:
        return candidate
    number = 2
    while True:
        suffix = f"-{number}"
        trimmed = base[: 150 - len(extension) - len(suffix)]
        candidate = f"{trimmed}{suffix}{extension.lower()}"
        if candidate.casefold() not in used:
            return candidate
        number += 1


def assign_output_names(titles: Sequence[str], *, variant: str | int | None = None) -> list[str]:
    """Assign names from prompt ordinal, independent of completion order."""
    if len(titles) > MAX_CONTACT_SHEET_IMAGES:
        raise ValueError("too many titles")
    names: list[str] = []
    for ordinal, title in enumerate(titles, 1):
        names.append(output_filename(ordinal, title, variant=variant, existing_names=names))
    return names


def _iter_pages(items: Sequence[Path], per_page: int) -> Iterator[Sequence[Path]]:
    for start in range(0, len(items), per_page):
        yield items[start : start + per_page]


def create_contact_sheet_pdf(
    image_paths: Iterable[str | os.PathLike[str]],
    output_path: str | os.PathLike[str],
    *,
    columns: int = 5,
    rows: int = 6,
    margin: float = 24.0,
    gap: float = 8.0,
    checkerboard: bool = False,
    overwrite: bool = False,
    title: str | None = None,
) -> Path:
    """Create a Letter contact sheet without retaining all decoded images in memory.

    With ``title`` every page gets a header "<title> — N шт." (N = whole set).
    """
    from PIL import Image
    from PyQt6.QtCore import QRect, QRectF, QMarginsF, Qt
    from PyQt6.QtGui import QFont, QFontMetrics, QGuiApplication, QImage, QPainter, QPdfWriter, QPageSize, QTextOption

    # QPdfWriter is a GUI paint device and requires an application object even
    # though no window is shown.  Keep it local/global-safe for library callers.
    app = QGuiApplication.instance()
    if app is None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QGuiApplication([])

    paths = [Path(p) for p in islice(image_paths, MAX_CONTACT_SHEET_IMAGES + 1)]
    destination = Path(output_path)
    if isinstance(columns, bool) or isinstance(rows, bool) or not isinstance(columns, int) or not isinstance(rows, int) or not 1 <= columns <= 10 or not 1 <= rows <= 10:
        raise ValueError("columns and rows must be between 1 and 10")
    if not all(isinstance(value, (int, float)) and math.isfinite(value) and value >= 0 for value in (margin, gap)):
        raise ValueError("margin and gap must be finite non-negative numbers")
    if not paths or len(paths) > MAX_CONTACT_SHEET_IMAGES:
        raise ValueError("image_paths must contain between 1 and 10000 images")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination_resolved = destination.resolve()
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.resolve() == destination_resolved:
            raise ValueError("contact sheet cannot overwrite a source image")
        with Image.open(path) as image:
            if image.width < 1 or image.height < 1 or max(image.size) > MAX_IMAGE_DIMENSION or image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError(f"unsupported image dimensions: {path}")
            image.verify()
    if destination.exists() and not overwrite:
        raise FileExistsError(destination)

    # Keep a PDF suffix because QPdfWriter uses the suffix when selecting its
    # paint engine; the final destination is still replaced atomically.
    fd, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".pdf", dir=destination.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    temporary.unlink()
    try:
        writer = QPdfWriter(str(temporary))
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.Letter))
        writer.setResolution(72)
        writer.setPageMargins(QMarginsF(0, 0, 0, 0))
        painter = QPainter(writer)
        if not painter.isActive():
            raise RuntimeError("QPdfWriter could not start painting")
        page_width, page_height = 612.0, 792.0
        cell_width = (page_width - 2 * margin - (columns - 1) * gap) / columns
        footer_height = 20.0
        header_text = f"{' '.join(title.split())} — {len(paths)} шт." if title and title.strip() else ""
        header_height = 36.0 if header_text else 0.0
        cell_height = (page_height - 2 * margin - header_height - footer_height - (rows - 1) * gap) / rows
        label_height = min(34.0, cell_height * 0.25)
        if cell_width < 24 or label_height < 8 or cell_height - label_height - 4 <= 0:
            raise ValueError("margin and gap leave no readable contact-sheet cells")
        font = QFont("Sans Serif", 8)
        painter.setFont(font)
        for page_number, page_paths in enumerate(_iter_pages(paths, columns * rows), 1):
            if page_number > 1:
                if not writer.newPage():
                    raise RuntimeError("QPdfWriter could not start a new page")
            if header_text:
                header_font = QFont(font)
                header_font.setPointSize(16)
                header_font.setBold(True)
                header_metrics = QFontMetrics(header_font)
                title_part = header_text[: header_text.rfind(" — ")]
                suffix = header_text[header_text.rfind(" — "):]
                shown = header_text
                while title_part and header_metrics.horizontalAdvance(shown) > page_width - 2 * margin:
                    title_part = title_part[:-1].rstrip()
                    shown = f"{title_part}…{suffix}"
                painter.setFont(header_font)
                painter.drawText(
                    QRectF(margin, margin, page_width - 2 * margin, header_height - 6),
                    int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter), shown)
                painter.setFont(font)
            for index, path in enumerate(page_paths):
                col, row = index % columns, index // columns
                x = margin + col * (cell_width + gap)
                y = margin + header_height + row * (cell_height + gap)
                image_box = (x, y, cell_width, cell_height - label_height - 4)
                if image_box[2] <= 0 or image_box[3] <= 0:
                    raise ValueError("margin and gap leave no room for images")
                with Image.open(path) as source:
                    rgba = source.convert("RGBA")
                    # Retain 3x display resolution so the PDF stays useful when zoomed.
                    rgba.thumbnail((max(1, int(image_box[2] * 3)), max(1, int(image_box[3] * 3))), Image.Resampling.LANCZOS)
                    if checkerboard:
                        background = Image.new("RGBA", rgba.size, "white")
                        tile = 16
                        for ty in range(0, rgba.height, tile):
                            for tx in range(0, rgba.width, tile):
                                if ((tx // tile) + (ty // tile)) % 2:
                                    background.paste((238, 238, 238, 255), (tx, ty, min(tx + tile, rgba.width), min(ty + tile, rgba.height)))
                        background.alpha_composite(rgba)
                        rgba = background
                    else:
                        background = Image.new("RGBA", rgba.size, "white")
                        background.alpha_composite(rgba)
                        rgba = background
                    data = rgba.tobytes("raw", "RGBA")
                    qimage = QImage(data, rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888).copy()
                scale = min(image_box[2] / qimage.width(), image_box[3] / qimage.height())
                display_width, display_height = qimage.width() * scale, qimage.height() * scale
                ix = x + (cell_width - display_width) / 2
                iy = y + (image_box[3] - display_height) / 2
                painter.drawImage(QRectF(ix, iy, display_width, display_height), qimage)
                label_rect = QRect(int(x), int(y + cell_height - label_height), int(cell_width), int(label_height))
                option = QTextOption()
                option.setWrapMode(QTextOption.WrapMode.WrapAnywhere)
                # Find a readable fit before eliding exceptionally long imported names.
                label_font = QFont(font)
                flags = int(Qt.TextFlag.TextWrapAnywhere)
                for size in (8, 7, 6):
                    label_font.setPointSize(size)
                    metrics = QFontMetrics(label_font)
                    if metrics.boundingRect(label_rect, flags, path.name).height() <= label_rect.height():
                        break
                label = path.name
                while len(label) > 1 and metrics.boundingRect(label_rect, flags, label).height() > label_rect.height():
                    label = label[:-2].rstrip("…") + "…"
                painter.setFont(label_font)
                painter.drawText(QRectF(label_rect), label, option)
                painter.setFont(font)
            footer = f"Page {page_number}"
            painter.drawText(QRect(0, int(page_height - margin - 18), int(page_width), 18), Qt.AlignmentFlag.AlignHCenter, footer)
        painter.end()
        if painter.isActive():
            raise RuntimeError("PDF painter did not close")
        del painter
        del writer
        if overwrite:
            os.replace(temporary, destination)
        else:
            # Atomic no-clobber publication, including a concurrent exporter.
            os.link(temporary, destination)
        return destination
    finally:
        if "painter" in locals() and painter.isActive():
            painter.end()
        if "painter" in locals():
            del painter
        if "writer" in locals():
            del writer
        if temporary.exists():
            temporary.unlink()


# Compatibility aliases for callers that prefer verb-style names.
make_contact_sheet_pdf = create_contact_sheet_pdf
build_output_filename = output_filename
