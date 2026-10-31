"""Перетаскивание PNG из проводника — приём файла и подготовка его к позиции запуска.

Одобренный владельцем макет: docs/ui/3.2/drag-drop-png-20261030/ (README — контракт семантики).
Перетащенный файл копируется в папку результата под шаблон позиции «<stem>_<NN>_ready.png»
и подключается ровно тем же существующим механизмом, каким работает «Вернуть готовые файлы»
(studio_auto_clipart_flow.recover_results): прежняя картинка позиции переносится в
«Историю версий» (studio_clipart_versions.keep_version), метка ставится «Не проверено»
(review_mark="ok", review_checked=False), новые позиции не создаются — SET-0 не нарушается
(«Ок» владелец ставит сама), платных запросов нет.

Правила приёмки одного дропа (таблица «Откуда принимаем» макета): только PNG
(расширение + сигнатура, как _safe_png), не симлинки/ярлыки, ≤ 64 МБ, ≤ 8 файлов за раз,
папки — отказ; каждый отказ возвращается конкретной причиной, тексты — ровно из макета.

Выбор позиции — одно правило на все экраны (README): явная цель (строка/миниатюра)
сильнее имени файла; «мимо» — цифру подсказывает имя «_NN_ready» (файлы, названные
приложением); чужое имя — диалог «Куда поставить …?».
"""
from __future__ import annotations

import re
import shutil
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from output_naming import _budgeted_filename
from studio_clipart_recovery import PNG_SIGNATURE, READY_NUMBER
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QImageReader, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QListView,
    QPushButton,
    QVBoxLayout,
)

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


@dataclass(frozen=True)
class PlannedAttachment:
    """Одна запись плана подключения: источник → позиция запуска (номер 1-based)."""

    source: Path
    number: int
    busy: bool = False  # позиция уже показывает другую картинку — нужен вопрос «Прежняя станет версией»


@dataclass(frozen=True)
class PositionOption:
    """Миниатюра одной позиции для диалога «Куда поставить …?»."""

    number: int
    path: str = ""  # текущая картинка позиции; пусто — позиция свободна
    excluded: bool = False  # картинка исключена из наборов (макет отмечает её «исключена»)


@dataclass
class DropOutcome:
    """Итог дропа для плашки экрана (макет: зелёная «успех», красная «отказ»)."""

    error: bool = False
    headline: str = ""
    detail: str = ""
    reasons: list[str] = field(default_factory=list)


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


def suggest_position(name: str, count: int) -> int | None:
    """Цифра NN из «_NN_ready» в имени файла → позиция (0-based), только внутри набора.

    Чужое имя (и номер вне диапазона) не угадываем — вернётся None, и экран
    спросит позицию диалогом «Куда поставить …?» (макет «проверка-выбор-позиции»).
    """
    match = READY_NUMBER.search(name)
    if match is None:
        return None
    position = int(match.group(1)) - 1
    return position if 0 <= position < count else None


def resolve_position(source: Path, items: Sequence, *, target_index: int | None) -> int | None:
    """Позиция (0-based) одного файла: явная цель-строка/миниатюра сильнее имени файла."""
    if target_index is not None:
        return target_index if 0 <= target_index < len(items) else None
    return suggest_position(Path(source).name, len(items))


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


def _item_output(item) -> str:
    return str(getattr(item, "output_path", "") or "")


def plan_attachments(
    sources: Sequence[Path],
    items: Sequence,
    numbers: dict[Path, int],
    *,
    same_file: Callable[[Path, Path], bool] = same_file_content,
) -> tuple[list[PlannedAttachment], list[str]]:
    """Спланировать подключение принятых файлов к СУЩЕСТВУЮЩИМ позициям запуска.

    numbers — цель каждого источника (1-based номер): всё, что дошло до планирования
    после явного дропа на миниатюру, подсказки имени «_NN_ready» и диалога выбора.
    Порядок источников сохраняется («файлы обрабатываются по порядку»). Дубликат —
    «позиция уже показывает этот самый файл» — отказ с текстом из макета. Файл на
    занятую позицию планируется с busy=True: экран спросит «Прежняя станет версией».
    Новые позиции не создаются (позиция = промпт): номер вне набора — противоречие вызова.
    """
    count = len(items)
    planned: list[PlannedAttachment] = []
    rejects: list[str] = []
    for source in sources:
        source = Path(source)
        number = numbers.get(source)
        if number is None:
            continue  # позицию так и не выбрали — файл не подключается
        if not 1 <= number <= count:
            raise ValueError(f"Позиция {number} не существует — новые позиции не создаются")
        current = _item_output(items[number - 1])
        if current and same_file(source, Path(current)):
            rejects.append(f"Эта картинка уже стоит на позиции {number}")
            continue
        planned.append(PlannedAttachment(source=source, number=number, busy=bool(current)))
    return planned, rejects


def position_options(
    items: Sequence, *, is_excluded: Callable[[str], bool] | None = None
) -> list[PositionOption]:
    """Миниатюры всех позиций запуска для диалога «Куда поставить …?» (новых не создаём)."""
    options: list[PositionOption] = []
    for number, item in enumerate(items, start=1):
        current = _item_output(item)
        excluded = bool(current) and is_excluded is not None and is_excluded(current)
        options.append(PositionOption(number=number, path=current, excluded=excluded))
    return options


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


def position_copy_name(source_name: str, number: int) -> str:
    """Имя копии в папке результата: «<stem>_<NN>_ready.png» (бюджет длины — output_naming)."""
    return _budgeted_filename(_position_stem(source_name), f"_{max(1, int(number)):02d}_ready.png")


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


def _scaled_pixmap(path: str, bound: int) -> QPixmap:
        """Миниатюра bounded-размера без полной загрузки больших PNG в память."""
        reader = QImageReader(path)
        source = reader.size()
        if source.isValid() and source.width() > 0 and source.height() > 0:
            reader.setScaledSize(source.scaled(
                QSize(bound, bound), Qt.AspectRatioMode.KeepAspectRatio))
        image = reader.read()
        return QPixmap.fromImage(image) if not image.isNull() else QPixmap()


class PositionPickerDialog(QDialog):
    """Диалог «Куда поставить …?» (макет «проверка-выбор-позиции»).

    Миниатюры всех существующих позиций с номерами; на позиции с картинкой она видна,
    исключённая из наборов помечена «исключена»; выбор — «Поставить», отмена — «Отмена».
    """

    THUMB = 72

    def __init__(self, source_name: str, options: Sequence[PositionOption], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Куда поставить {source_name}?")
        self.setModal(True)
        self.setObjectName("positionPickerDialog")
        layout = QVBoxLayout(self)
        note = QLabel(
            "Имя файла не подсказывает номер (шаблон _NN_ready) — выберите позицию. "
            "Если на позиции уже есть картинка, она станет версией.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.grid = QListWidget()
        self.grid.setObjectName("positionPickerGrid")
        self.grid.setViewMode(QListView.ViewMode.IconMode)
        self.grid.setIconSize(QSize(self.THUMB, self.THUMB))
        self.grid.setGridSize(QSize(self.THUMB + 26, self.THUMB + 40))
        self.grid.setMovement(QListView.Movement.Static)
        self.grid.setResizeMode(QListView.ResizeMode.Adjust)
        self.grid.setWordWrap(True)
        self.grid.setSpacing(8)
        self.grid.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.grid.setStyleSheet(
            'QListWidget { background: transparent; } '
            'QListWidget::item { background: #1b2636; border: 1px solid #223045; '
            'border-radius: 6px; } '
            'QListWidget::item:selected { border: 2px dashed #24d8c5; background: #15243a; }'
        )
        for option in options:
            row = QListWidgetItem(self._option_label(option))
            row.setData(Qt.ItemDataRole.UserRole, option.number)
            row.setIcon(self._option_icon(option))
            row.setToolTip(self._option_tooltip(option))
            self.grid.addItem(row)
        layout.addWidget(self.grid, 1)
        actions = QHBoxLayout()
        actions.addStretch(1)
        self.cancel_button = QPushButton("Отмена")
        self.cancel_button.setProperty("v3Button", True)
        self.cancel_button.setProperty("variant", "secondary")
        self.cancel_button.clicked.connect(self.reject)
        actions.addWidget(self.cancel_button)
        self.apply_button = QPushButton("Поставить")
        self.apply_button.setObjectName("positionPickerApply")
        self.apply_button.setProperty("v3Button", True)
        self.apply_button.setProperty("variant", "primary")
        self.apply_button.setDefault(True)
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.accept)
        actions.addWidget(self.apply_button)
        layout.addLayout(actions)
        self.grid.currentRowChanged.connect(
            lambda current: self.apply_button.setEnabled(current >= 0))

    def chosen_number(self) -> int | None:
        """Выбранный номер позиции (1-based) или None, когда ничего не выбрано."""
        item = self.grid.currentItem()
        if item is None:
            return None
        number = item.data(Qt.ItemDataRole.UserRole)
        return int(number) if number is not None else None

    def select_position(self) -> int | None:
        """Показать диалог и вернуть выбранный номер позиции (None — «Отмена»)."""
        if self.exec() != int(QDialog.DialogCode.Accepted):
            return None
        return self.chosen_number()

    @classmethod
    def ask(cls, source_name: str, options: Sequence[PositionOption], parent=None) -> int | None:
        """Собрать диалог «Куда поставить …?» и вернуть выбор (макет «проверка-выбор-позиции»)."""
        return cls(source_name, options, parent).select_position()

    def accept(self) -> None:  # noqa: D102 — QDialog.accept; без выбора кнопка «Поставить» мертва
        if self.chosen_number() is None:
            return
        super().accept()

    @staticmethod
    def _option_label(option: PositionOption) -> str:
        if option.excluded:
            return f"{option.number} · исключена"
        if not option.path:
            return f"{option.number} · пусто"
        return str(option.number)

    @staticmethod
    def _option_tooltip(option: PositionOption) -> str:
        if option.excluded:
            return f"Позиция {option.number}: картинка исключена из наборов, позиция остаётся"
        if not option.path:
            return f"Позиция {option.number}: свободна (картинки нет после прерванного запуска)"
        return f"Позиция {option.number}: {Path(option.path).name}"

    def _option_icon(self, option: PositionOption) -> QIcon:
        side = self.THUMB
        canvas = QPixmap(QSize(side, side))
        canvas.fill(QColor("#1b2636"))
        painter = QPainter(canvas)
        inset = 4
        for y in range(inset, side - inset, 12):
            for x in range(inset, side - inset, 12):
                if x + 12 > side - inset or y + 12 > side - inset:
                    continue  # клетка видна целиком, как на шахматке проверки PNG
                painter.fillRect(x, y, 12, 12, QColor(
                    "#d6dce4" if ((x - inset) // 12 + (y - inset) // 12) % 2 else "#ffffff"))
        if option.path:
            picture = _scaled_pixmap(option.path, side - inset * 2)
            if not picture.isNull():
                painter.drawPixmap((side - picture.width()) // 2, (side - picture.height()) // 2, picture)
        if option.excluded:
            painter.setPen(QPen(QColor("#8ea3b8"), 2))
            painter.setBrush(QColor("#2b3340"))
            painter.drawEllipse(3, 3, 18, 18)
            painter.drawLine(6, 18, 18, 6)
        painter.end()
        return QIcon(canvas)
