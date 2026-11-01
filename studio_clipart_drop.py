"""Перетаскивание PNG из проводника — приём файлов и копия в папку результата.

Правило владелицы (2026-11-01): бросок из папки ДОБАВЛЯЕТ новую позицию в набор. Заменить
картинку существующей позиции можно только явно — Shift + бросок точно на неё (макет
drag-drop-png-20261030 описывал замену по имени `_NN_ready` и диалог «Куда поставить» —
отменено). Перетащенный файл копируется в папку результата под шаблон «<stem>_<NN>_ready.png»;
позиция получает метку «Не проверено» (review_mark="ok", review_checked=False), «Ок» владелец
ставит сама; платных запросов нет.

Правила приёмки одного дропа: только PNG (расширение + сигнатура, как _safe_png), не симлинки/
ярлыки, ≤ 64 МБ, ≤ 8 файлов за раз, папки — отказ; каждый отказ возвращается конкретной причиной.
"""
from __future__ import annotations

import re
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QEvent, QObject

from output_naming import _budgeted_filename
from studio_clipart_recovery import PNG_SIGNATURE

# Лимиты дропа (макет 2026-10-30; размер — как MAX_PREVIEW_BYTES в v3_run_queue).
MAX_DROP_FILES = 8
MAX_DROP_BYTES = 64 * 1024 * 1024
DROP_MB_LIMIT = MAX_DROP_BYTES // (1024 * 1024)

# Символы, запрещённые в именах файлов Windows; остальное (кириллица) сохраняется.
_FORBIDDEN_NAME_CHARS = re.compile(r"[<>:\"/\\|?*\x00-\x1f]")


@dataclass(frozen=True)
class DropVerdict:
    """Решение по одному файлу дропа; отказ всегда с конкретной причиной из макета."""

    path: Path
    accepted: bool
    reason: str = ""


def _reject(path: Path, reason: str) -> DropVerdict:
    return DropVerdict(path=path, accepted=False, reason=reason)


def _unavailable(path: Path) -> DropVerdict:
    return _reject(path, f"{path.name} недоступен (ярлык или ссылка)")


def _file_verdict(path: Path, *, max_bytes: int) -> DropVerdict:
    name = path.name
    try:
        if path.is_symlink():
            return _unavailable(path)
        if path.is_dir():
            return _reject(path, "Папки не принимаются — перетащите PNG-файлы")
        if not path.is_file():
            return _unavailable(path)
        if path.suffix.lower() != ".png":
            return _reject(path, f"{name} — это не PNG. Перетащите файл с расширением .png")
        size = path.stat().st_size
        if size > max_bytes:
            megabytes = max(1, (size + (1024 * 1024) - 1) // (1024 * 1024))
            return _reject(path, f"{name} слишком большой ({megabytes} МБ) — лимит {DROP_MB_LIMIT} МБ")
        with open(path, "rb") as handle:
            if handle.read(len(PNG_SIGNATURE)) != PNG_SIGNATURE:
                return _reject(path, f"{name} — внутри не PNG (переименованный другой файл)")
    except OSError:
        return _unavailable(path)
    return DropVerdict(path=path, accepted=True)


def validate_dropped_files(
    paths: Iterable, *, max_files: int = MAX_DROP_FILES, max_bytes: int = MAX_DROP_BYTES
) -> tuple[list[Path], list[str]]:
    """Отвалидировать один дроп: (принятые файлы по порядку, причины отказов).

    Каждый не-PNG, ярлык, папка и слишком большой файл дают свою конкретную причину
    (тексты макета). Файлы сверх лимита «за раз» отклоняются одной групповой причиной,
    поставленной по порядку дропа — на месте первого лишнего файла.
    """
    entries = [_file_verdict(Path(raw), max_bytes=max_bytes) for raw in paths]
    accepted = [verdict.path for verdict in entries if verdict.accepted]
    seen_accepted = 0
    first_extra_at: int | None = None
    for index, verdict in enumerate(entries):
        if not verdict.accepted:
            continue
        seen_accepted += 1
        if seen_accepted == max_files + 1:
            first_extra_at = index
            break
    reasons = [verdict.reason for verdict in entries if not verdict.accepted]
    if first_extra_at is not None:
        accepted = accepted[:max_files]
        # seen_accepted остановился на первом лишнем файле — считаем лишние по всем записям.
        extras = sum(1 for verdict in entries if verdict.accepted) - max_files
        # Причина лимита встаёт среди остальных по порядку дропа — на месте
        # первого лишнего файла (причины файлов до него — раньше, после — позже).
        insert_at = sum(1 for verdict in entries[:first_extra_at] if not verdict.accepted)
        reasons.insert(insert_at, f"За раз можно {max_files} файлов — лишние ({extras}) не приняты")
    return accepted, reasons


def same_file_content(first: Path, second: Path, *, chunk: int = 1 << 20) -> bool:
    """Один и тот же файл (путь или байты): дубликат «позиция уже показывает этот файл»."""
    first, second = Path(first), Path(second)
    try:
        if first.resolve(strict=False) == second.resolve(strict=False) and first.exists():
            return True
        if first.stat().st_size != second.stat().st_size:
            return False
        with open(first, "rb") as one, open(second, "rb") as other:
            while True:
                block_one = one.read(chunk)
                block_other = other.read(chunk)
                if block_one != block_other:
                    return False
                if not block_one:
                    return True
    except OSError:
        return False


def _position_stem(source_name: str) -> str:
    """Stem файла без запрещённых символов; кириллица сохраняется (README «Чужие имена»).

    Дроп приходит как ИМЯ файла — «мусорные» разделители в нём («утка: "золотая"/осень?»)
    это часть имени, а не путь, поэтому Path здесь не используется: он бы разрезал
    имя по «/» и потерял начало. Расширение .png снимается только в конце (шаблон
    «<stem>_<NN>_ready.png» не должен получить двойное расширение).
    """
    name = str(source_name)
    if name.lower().endswith(".png"):
        name = name[:-4]
    cleaned = _FORBIDDEN_NAME_CHARS.sub(" ", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or "clipart"


def copy_for_position(source, output_dir, number: int) -> Path:
    """Копия перетащенного файла в папке результата под шаблон позиции.

    Коллизия имени — суффикс «_2», как reserve_processed/reserve_generated в
    output_naming; файл-источник при дропе никогда не изменяется (README).
    """
    output_dir = Path(output_dir)
    base = f"{_position_stem(Path(source).name)}_{max(1, int(number)):02d}_ready"
    destination = output_dir / _budgeted_filename(base, ".png")
    suffix = 2
    while destination.exists():
        destination = output_dir / _budgeted_filename(base, f"_{suffix}.png")
        suffix += 1
    shutil.copy2(source, destination)
    return destination


DROPPED_MARK = "dropped"


def _is_dropped(item):
    return isinstance(item.payload, dict) and item.payload.get(DROPPED_MARK) is True


NO_PROMPT_TEXT = "У добавленной картинки нет промта — переделать нельзя."


def _dropped_for_path(session, path):
    """Брошенная позиция с этим файлом (у неё нет промта, переделывать нечего)."""
    target = str(Path(path).resolve())
    return any(_is_dropped(item) and item.output_path and str(Path(item.output_path).resolve()) == target
               for item in session.items)


class FileDropFilter(QObject):
    """Один механизм приёма файлов из папки для страниц «Результаты» и «Наборы» (и панели проверки PNG).

    Ставится на виджет страницы; любые локальные файлы принимаются, причины отказов (не PNG, папка,
    слишком большой) называет `validate_dropped_files` в обработчике `on_drop(paths)`.
    """

    def __init__(self, widget, on_drop):
        super().__init__(widget)
        self._on_drop = on_drop
        widget.setAcceptDrops(True)
        widget.installEventFilter(self)

    @staticmethod
    def _local_paths(event):
        return [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
            if self._local_paths(event):
                event.acceptProposedAction()
            else:
                event.ignore()
            return True
        if kind == QEvent.Type.Drop:
            paths = self._local_paths(event)
            if not paths:
                event.ignore()
                return True
            event.acceptProposedAction()
            self._on_drop(paths)
            return True
        return False
