"""Auto Clipart owner review UI: marks, notes, versions and re-creation.

Approved mockups: docs/ui/3.2/autoclipart-image-marks/. The shared transparency
editor and results page only expose small hooks; all review behaviour lives here.
Paid generation is started only from "Пересоздать помеченные" with the existing
price confirmation; a cut-out redo uses the saved raw generation, never a new one.
"""
from __future__ import annotations

import re
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMenu, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from chroma_provenance import receipt_path
from studio_clipart_versions import (
    MAX_NOTE, discard_last_version, empty_trash, keep_version, restore_version, trash_paths,
)
from v3_components import ButtonVariant, V3Button
from v3_provider_registry import provider_requires_cost

KEY_HEX = re.compile(r"#(?:0000FF|00FF00|FF0000)\b", re.IGNORECASE)
OK, GEN, CUT, DEL = "#24cabb", "#f0c38a", "#b9a3f5", "#8a97a8"
MARKS = (
    ("ok", "Ок", OK),
    ("bad_generation", "Брак генерации", GEN),
    ("bad_cutout", "Брак вырезания", CUT),
    ("deleted", "Удалить", DEL),
)
MARK_BACKGROUND = {"ok": "#1d3a40", "bad_generation": "#3a3326", "bad_cutout": "#2e2a45", "deleted": "#2b3340"}
MARK_LABEL = {key: label for key, label, _ in MARKS}
LIST_LABEL = dict(MARK_LABEL, deleted="Удалено")
MARK_COLOR = {key: colour for key, _, colour in MARKS}
FILTERS = (("all", "Все"), ("unchecked", "Не проверено"), ("marked", "Помеченные"), ("deleted", "Удалённые"))
UNCHECKED = "#8393a7"
MARK_COLOR["unchecked"] = UNCHECKED
LIST_LABEL["unchecked"] = "Не проверено"


def mark_state(item) -> str:
    """The mark as the owner sees it: «Ок» only once she has looked; otherwise «Не проверено»."""
    mark = item.review_mark
    if mark == "ok" and not getattr(item, "review_checked", False):
        return "unchecked"
    return mark

# (key, label, worker setting overrides). Paid status comes from the provider registry.
CUTOUT_METHODS = (
    ("chroma_gentle", "Хромакей, бережный режим",
     {"remove_bg_provider": "local_chroma_key", "chroma_subject_profile": "legacy"}),
    ("local_ai_soft", "ИИ на компьютере, мягкий край",
     {"remove_bg_provider": "local_rembg", "local_rembg_edge_quality": "soft"}),
    ("local_ai_normal", "ИИ на компьютере, обычный край",
     {"remove_bg_provider": "local_rembg", "local_rembg_edge_quality": "normal"}),
    ("local_ai_sharp", "ИИ на компьютере, резкий край",
     {"remove_bg_provider": "local_rembg", "local_rembg_edge_quality": "sharp"}),
    ("kie", "ИИ онлайн KIE", {"remove_bg_provider": "kie"}),
    ("fal", "ИИ онлайн fal", {"remove_bg_provider": "fal"}),
)
DEFAULT_CUTOUT = CUTOUT_METHODS[0]

_FINISHED = {"succeeded", "failed"}


def review_supported() -> bool:
    """The review needs Studio core hooks; an older Studio shell simply has no marks."""
    from v3_run_queue import RunItem, RunQueueSession, RunQueueSupport
    from v3_transparency_preview import ClipartTransparencyEditorPage
    return ("review_mark" in getattr(RunItem, "__dataclass_fields__", {})
            and "review_checked" in getattr(RunItem, "__dataclass_fields__", {})
            and hasattr(RunQueueSession, "preview_reprocess")
            and hasattr(RunQueueSupport, "reprocess_selected")
            and hasattr(ClipartTransparencyEditorPage, "add_canvas_footer"))


def method_is_paid(overrides) -> bool:
    return provider_requires_cost(overrides["remove_bg_provider"])


def mark_counts(items) -> dict[str, int]:
    counts = {key: 0 for key, _, _ in MARKS}
    counts["unchecked"] = 0
    for item in items:
        state = mark_state(item)
        counts[state] = counts.get(state, 0) + 1
    return counts


def annotation(item):
    """(colour, text, dimmed) for a finished item, None while it is not finished."""
    if item.status.value not in _FINISHED:
        return None
    state = mark_state(item)
    text = LIST_LABEL[state]
    if item.review_note:
        text += f" · ✎ {item.review_note[:60]}"
    if getattr(item, "prompt_edited", False):
        text += " · промпт исправлен"
    return MARK_COLOR[state], text, item.review_mark == "deleted"


def visible(item, mode: str) -> bool:
    if mode == "marked":
        return mark_state(item) in {"bad_generation", "bad_cutout", "deleted"}
    if mode == "unchecked":
        return mark_state(item) == "unchecked"
    if mode == "deleted":
        return item.review_mark == "deleted"
    return True


def _small(text, colour="#a6b5c8", bold=False):
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(f"color:{colour}; background:transparent;"
                        + (" font-weight:bold;" if bold else ""))
    return label


def _thumb(path, size):
    label = QLabel()
    label.setFixedSize(size, size)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet("background:#e9edf2; border-radius:6px;")
    pixmap = QPixmap(str(path))
    if not pixmap.isNull():
        label.setPixmap(pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation))
    else:
        label.setText("Файл недоступен")
    return label


class ReviewStrip(QFrame):
    """The "Оценка" bar under the picture in the transparency check window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("reviewStrip")
        self.setStyleSheet(
            "QFrame#reviewStrip {background:#172131; border-top:1px solid #354154;}"
            " QPushButton[reviewMark=\"true\"] {border:1px solid #3b4b60; border-radius:6px;"
            " background:#263548; color:#e4edf6; padding:0 10px; min-height:28px;}"
            + "".join(
                f" QPushButton[reviewMark=\"true\"][markKey=\"{key}\"]:checked {{border-color:{colour};"
                f" color:{colour}; background:{MARK_BACKGROUND[key]};}}"
                for key, _label, colour in MARKS))
        box = QVBoxLayout(self)
        box.setContentsMargins(12, 10, 12, 10)
        box.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.mark_group = QButtonGroup(self)
        self.mark_group.setExclusive(True)
        self.mark_buttons = {}
        for key, label, _ in MARKS:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("reviewMark", True)
            button.setProperty("markKey", key)
            button.setAccessibleName(f"Метка: {label}")
            self.mark_group.addButton(button)
            self.mark_buttons[key] = button
            row.addWidget(button)
        row.addStretch(1)
        self.history = QPushButton("История версий")
        self.history.setCursor(Qt.CursorShape.PointingHandCursor)
        self.history.setStyleSheet("QPushButton {border:none; color:#24cabb; background:transparent;"
                                   " text-decoration:underline;} QPushButton:disabled {color:#74869a;}")
        row.addWidget(self.history)
        box.addLayout(row)
        self.note = QLineEdit()
        self.note.setMaxLength(MAX_NOTE)
        self.note.setPlaceholderText("Заметка: что не так (необязательно)")
        self.note.setAccessibleName("Заметка к картинке")
        box.addWidget(self.note)
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.status = _small("")
        bottom.addWidget(self.status, 1)
        self.method_label = _small("Способ:", "#e4edf6")
        self.method_label.setWordWrap(False)
        self.method = QComboBox()
        self.method.setMinimumWidth(300)
        self.method.setAccessibleName("Способ вырезания")
        for key, label, overrides in CUTOUT_METHODS:
            self.method.addItem(f"{label} — {'платно' if method_is_paid(overrides) else 'бесплатно'}", key)
        self.try_button = V3Button("Попробовать", ButtonVariant.PRIMARY)
        self.prompt_button = V3Button("Изменить промпт…", ButtonVariant.SECONDARY)
        self.brush_button = V3Button("Исправить кистью", ButtonVariant.SECONDARY)
        self.to_generation_button = V3Button("Отметить как брак генерации", ButtonVariant.PRIMARY)
        self.cancel_button = V3Button("Отменить", ButtonVariant.SECONDARY)
        self.compare_button = V3Button("Сравнить с прежним", ButtonVariant.SECONDARY)
        self.keep_button = V3Button("Оставить новый вариант", ButtonVariant.PRIMARY)
        self.restore_button = V3Button("Восстановить", ButtonVariant.PRIMARY)
        self.restore_button.setMinimumWidth(180)
        # Owner 2026-10-28: redoing this very picture is possible whatever its mark (the buttons stay on screen).
        self.regenerate_button = V3Button("Перегенерировать", ButtonVariant.SECONDARY)
        self.regenerate_button.setToolTip("Новая платная генерация этой картинки; цена и модель — в подтверждении")
        self.autocut_button = V3Button("Убрать фон", ButtonVariant.SECONDARY)
        self.autocut_button.setToolTip("Заново вырезать фон автоматически: бесплатно, прежняя картинка сохранится как версия")
        self.upscale_button = V3Button("Апскейл заново", ButtonVariant.SECONDARY)
        self.upscale_button.setToolTip(
            "Повторный апскейл вырезанной картинки, затем очистка края → резкость → обрезка → сохранение PNG")
        self.persistent_actions = (self.regenerate_button, self.autocut_button, self.upscale_button)
        self.actions = (self.method_label, self.method, self.try_button, self.prompt_button,
                        self.brush_button, self.to_generation_button, self.cancel_button,
                        self.compare_button, self.keep_button, self.restore_button)
        for widget in self.actions + self.persistent_actions:
            bottom.addWidget(widget)
        box.addLayout(bottom)

    def show_state(self, mark, *, actions=(), status="", history=0, enabled=True):
        # An exclusive group refuses to uncheck its checked button, so a state without a mark would keep the old one lit.
        self.mark_group.setExclusive(False)
        for key, button in self.mark_buttons.items():
            button.blockSignals(True)
            button.setChecked(key == mark)
            button.setEnabled(enabled)
            button.blockSignals(False)
            # The look follows :checked in the strip's stylesheet, so no stale per-button style can stay lit;
            # the explicit repolish covers styles that Qt does not refresh by itself.
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()
        self.mark_group.setExclusive(True)
        for widget in self.actions:
            widget.setVisible(widget in actions)
        for widget in self.persistent_actions:
            widget.setVisible(enabled)
        self.status.setText(status)
        self.status.setVisible(False)  # no caption under the panel (owner 2026-10-27); the text stays as a tooltip
        self.setToolTip(status)
        self.note.setEnabled(enabled)
        self.history.setText(f"История версий ({history})")
        self.history.setEnabled(enabled and history > 0)

    def set_note(self, text):
        self.note.blockSignals(True)
        self.note.setText(text)
        self.note.blockSignals(False)


def _check_reference_file(path):
    """A replacement reference must be a readable PNG/JPEG/WebP of sane size (the same limits as the set's references)."""
    from PIL import Image
    try:
        size = Path(path).stat().st_size
        if size > 25 * 1024 * 1024:
            raise ValueError("Референс превышает 25 МБ")
        with Image.open(path) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"}:
                raise ValueError("Поддерживаются PNG, JPEG и WebP")
            if image.width * image.height > 40_000_000:
                raise ValueError("Референс превышает 40 мегапикселей")
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError("Референс недоступен или повреждён") from error


GUIDANCE_LINE = re.compile(r"^Reference image (\d+):")


def drop_reference_guidance(prompt, removed):
    """Remove the «Reference image N:» line of a removed reference and renumber the later ones."""
    lines = []
    for line in prompt.split("\n"):
        match = GUIDANCE_LINE.match(line)
        if match:
            number = int(match.group(1))
            if number == removed:
                continue
            if number > removed:
                line = f"Reference image {number - 1}:" + line[match.end():]
        lines.append(line)
    return "\n".join(lines)


class PromptDialog(QDialog):
    def __init__(self, parent, *, path, title, note, prompt, original, references=()):
        super().__init__(parent)
        self.setWindowTitle("Изменить промпт")
        self.original = original
        self._references = [str(item) for item in references]
        self._original_references = list(self._references)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)
        heading = _small("Изменить промпт картинки", "#e4edf6", bold=True)
        heading.setStyleSheet(heading.styleSheet() + " font-size:18px;")
        root.addWidget(heading)
        top = QHBoxLayout()
        top.setSpacing(16)
        top.addWidget(_thumb(path, 220), 0, Qt.AlignmentFlag.AlignTop)
        side = QVBoxLayout()
        side.setSpacing(6)
        side.addWidget(_small(title, GEN, bold=True))
        if note:
            side.addWidget(_small(f"Заметка: {note}"))
        side.addWidget(_small("Было", "#e4edf6", bold=True))
        was = QPlainTextEdit(original)
        was.setReadOnly(True)
        was.setFixedHeight(80)
        side.addWidget(was)
        side.addWidget(_small("Новый промпт", "#e4edf6", bold=True))
        self.editor = QPlainTextEdit(prompt)
        self.editor.setFixedHeight(96)
        self.editor.setAccessibleName("Новый промпт")
        side.addWidget(self.editor)
        top.addLayout(side, 1)
        root.addLayout(top)
        self.references_box = QVBoxLayout()
        self.references_box.setSpacing(6)
        root.addLayout(self.references_box)
        self._show_references()
        root.addWidget(_small("Промпт сохранится в объекте набора. Генерация не запускается здесь: картинка будет "
                              "создана заново по кнопке «Пересоздать помеченные», с ценой и подтверждением."))
        root.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        reset = V3Button("Вернуть исходный", ButtonVariant.GHOST)
        reset.clicked.connect(self.reset_to_original)
        cancel = V3Button("Отмена", ButtonVariant.SECONDARY)
        cancel.clicked.connect(self.reject)
        save = V3Button("Сохранить промпт", ButtonVariant.PRIMARY)
        save.clicked.connect(self._save)
        for button in (reset, cancel, save):
            row.addWidget(button)
        root.addLayout(row)
        self.resize(760, 520)

    def reset_to_original(self):
        self.editor.setPlainText(self.original)
        self._references = list(self._original_references)
        self._show_references()

    def references(self):
        """Reference files for this picture only; the set and the other pictures keep theirs."""
        return list(self._references)

    def choose_reference(self):
        path, _ = QFileDialog.getOpenFileName(self, "Заменить референс", "", "Изображения (*.png *.jpg *.jpeg *.webp)")
        return path

    def _show_references(self):
        while self.references_box.count():
            item = self.references_box.takeAt(0)
            if item.layout() is not None:
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget() is not None:
                        child.widget().deleteLater()
            elif item.widget() is not None:
                item.widget().deleteLater()
        if not self._references:
            return
        self.references_box.addWidget(_small("Референсы этой картинки", "#e4edf6", bold=True))
        for index, reference in enumerate(self._references):
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(_thumb(reference, 44))
            name = _small(Path(reference).name)
            name.setToolTip(reference)
            row.addWidget(name, 1)
            replace = V3Button("Заменить…", ButtonVariant.SECONDARY)
            replace.setAccessibleName(f"Заменить референс {index + 1}")
            replace.clicked.connect(lambda _=False, at=index: self.replace_reference(at))
            remove = V3Button("Убрать", ButtonVariant.SECONDARY)
            remove.setAccessibleName(f"Убрать референс {index + 1}")
            remove.clicked.connect(lambda _=False, at=index: self.remove_reference(at))
            row.addWidget(replace)
            row.addWidget(remove)
            self.references_box.addLayout(row)

    def replace_reference(self, index):
        path = self.choose_reference()
        if not path:
            return
        try:
            _check_reference_file(path)
        except ValueError as error:
            QMessageBox.warning(self, "Референс", str(error))
            return
        self._references[index] = str(path)
        self._show_references()

    def remove_reference(self, index):
        del self._references[index]
        self.editor.setPlainText(drop_reference_guidance(self.editor.toPlainText(), index + 1))
        self._show_references()

    def _lost_background_sentences(self):
        """Sentences of the original that name a chroma-key colour, when the new text no longer names it.

        The key colour is written into the prompt itself; without it the model draws any background and the
        cut-out finds no key to remove (a regenerated picture came back on black)."""
        new_text = self.editor.toPlainText().lower()
        lost = []
        for sentence in re.split(r"(?<=[.!?])\s+", self.original):
            colours = {code.lower() for code in KEY_HEX.findall(sentence)}
            if colours and not any(code in new_text for code in colours):
                lost.append(sentence.strip())
        return lost

    def ask_background(self, sentences):
        """'add' puts the lost sentences back, 'keep' saves as written, anything else returns to editing."""
        box = QMessageBox(QMessageBox.Icon.Warning, "Фон хромакея",
                          "В новом тексте нет фразы про однотонный фон нужного цвета:\n\n" + "\n".join(sentences),
                          QMessageBox.StandardButton.NoButton, self)
        add = box.addButton("Вернуть фразу", QMessageBox.ButtonRole.AcceptRole)
        keep = box.addButton("Сохранить как есть", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Назад", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(add)
        box.exec()
        return "add" if box.clickedButton() is add else "keep" if box.clickedButton() is keep else "back"

    def _save(self):
        if not self.editor.toPlainText().strip():
            QMessageBox.warning(self, "Промпт", "Промпт не может быть пустым.")
            return
        lost = self._lost_background_sentences()
        if lost:
            answer = self.ask_background(lost)
            if answer == "add":
                self.editor.setPlainText(self.editor.toPlainText().rstrip() + " " + " ".join(lost))
            elif answer != "keep":
                return
        self.accept()

    def prompt(self):
        return self.editor.toPlainText().strip()


class VersionsDialog(QDialog):
    def __init__(self, parent, *, name, item):
        super().__init__(parent)
        self.setWindowTitle("История версий")
        self.chosen = None
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)
        heading = _small(f"История версий · {name}", "#e4edf6", bold=True)
        heading.setStyleSheet(heading.styleSheet() + " font-size:18px;")
        root.addWidget(heading)
        root.addWidget(_small("В наборы и экспорт идёт только текущая версия. Старые лежат в папке versions набора."))
        cards = QHBoxLayout()
        cards.setSpacing(16)
        entries = [(Path(entry["path"]), f"Версия {number}", entry, False)
                   for number, entry in enumerate(item.versions, 1)]
        if item.output_path:
            entries.append((Path(item.output_path), f"Версия {len(entries) + 1} · текущая", None, True))
        for index, (path, title, entry, current) in enumerate(entries[-4:], max(0, len(entries) - 4)):
            card = QFrame()
            card.setObjectName("versionCard")
            card.setStyleSheet(
                f"QFrame#versionCard {{border:{2 if current else 1}px solid {OK if current else '#354154'};"
                " border-radius:12px; background:#1f2937;}")
            inner = QVBoxLayout(card)
            inner.setSpacing(6)
            inner.addWidget(_thumb(path, 200), 0, Qt.AlignmentFlag.AlignHCenter)
            inner.addWidget(_small(title, "#e4edf6", bold=True))
            if entry is not None:
                reason = entry["reason"]
                if reason != "ok":
                    inner.addWidget(_small(LIST_LABEL[reason], MARK_COLOR[reason]))
                if entry["note"]:
                    inner.addWidget(_small(f"«{entry['note']}»"))
                if entry["prompt"]:
                    prompt = _small(f"Прежний промпт: {entry['prompt'][:90]}…" if len(entry["prompt"]) > 90
                                    else f"Прежний промпт: {entry['prompt']}")
                    prompt.setToolTip(entry["prompt"])
                    inner.addWidget(prompt)
                inner.addWidget(_small(entry["created"].replace("T", " ")[:16]))
                restore = V3Button("Сделать текущей", ButtonVariant.SECONDARY)
                restore.clicked.connect(lambda _=False, chosen=index: self._choose(chosen))
                inner.addWidget(restore)
            else:
                inner.addWidget(_small("Используется в наборе", OK, bold=True))
            inner.addStretch(1)
            cards.addWidget(card)
        cards.addStretch(1)
        root.addLayout(cards)
        if len(entries) > 4:
            root.addWidget(_small(f"Показаны последние 4 из {len(entries)}."))
        root.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        close = V3Button("Закрыть", ButtonVariant.PRIMARY)
        close.clicked.connect(self.reject)
        row.addWidget(close)
        root.addLayout(row)
        self.resize(min(1060, 280 * min(4, len(entries)) + 80), 600)

    def _choose(self, index):
        self.chosen = index
        self.accept()


def compare_dialog(parent, before, after):
    dialog = QDialog(parent)
    dialog.setWindowTitle("Сравнить с прежним")
    root = QVBoxLayout(dialog)
    row = QHBoxLayout()
    for path, title in ((before, "Прежний вариант"), (after, "Новый вариант")):
        column = QVBoxLayout()
        column.addWidget(_small(title, "#e4edf6", bold=True))
        column.addWidget(_thumb(path, 460))
        row.addLayout(column)
    root.addLayout(row)
    close = V3Button("Закрыть", ButtonVariant.PRIMARY)
    close.clicked.connect(dialog.accept)
    root.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
    dialog.exec()
    dialog.deleteLater()


class ImageReview:
    """Connects marks to the Auto Clipart run: results page, editor, re-creation."""

    def __init__(self, flow):
        self.flow = flow
        self.filter_mode = "all"
        self._pending_cutout: list[int] = []
        self._chain_started = False
        self._origin_prompts: dict[int, str] = {}
        self._name_targets: dict[int, Path] = {}
        self._run_seen = False
        self._editor = None
        self._job = None  # (row, item index, previous output) while a cut-out redo runs from the editor
        self._job_started = False
        self._preview_row = None
        self._installed = False
        self.marks_listeners = []  # called with no arguments the moment any mark or note changes

    # --- shared state --------------------------------------------------------

    @property
    def session(self):
        return self.flow.run_queue.session

    def _output_dir(self):
        return self.session.output_dir

    SAVE_DELAY_MS = 350

    def _save(self):
        """Persist soon, not on every click: each save writes the whole project twice and rebuilds the pages,
        which made a mark lag by seconds on a big run. Clicks inside the delay share one save."""
        self._save_pending = True
        self._show_marks_now()
        timer = getattr(self, "_save_timer", None)
        if timer is None:
            timer = self._save_timer = QTimer()
            timer.setSingleShot(True)
            timer.setInterval(self.SAVE_DELAY_MS)
            timer.timeout.connect(self.flush_save)
        timer.start()

    def _show_marks_now(self):
        """Marks must show everywhere at once: the saved copy lags by SAVE_DELAY_MS, the screens must not."""
        session = self.session
        page = self.flow.run_queue.page
        if session is not None and self._installed:
            page.queue.refresh_items(session.items)
            self.refresh_results()
        if session is not None and self._editor is not None:
            self.refresh_editor()
        for listener in self.marks_listeners:
            listener()

    def flush_save(self):
        """Run the pending save now (also on close and before anything reads the saved run)."""
        if not getattr(self, "_save_pending", False):
            return
        self._save_pending = False
        timer = getattr(self, "_save_timer", None)
        if timer is not None:
            timer.stop()
        self.flow.shell.mark_dirty()
        self.flow._save_run()
        self.flow.run_queue.page.refresh_from_state()

    def _prompt_entry(self, item):
        object_id = str((item.payload or {}).get("object_id") or "") if isinstance(item.payload, dict) else ""
        for entry in self.flow.shell.state.data.prompts:
            if object_id and entry.object_id == object_id:
                return entry
        return None

    def _prompt(self, item):
        return str(item.payload.get("prompt") or "") if isinstance(item.payload, dict) else ""

    def before_replace_outputs(self, indices, kind):
        """Copy each current picture into versions before a re-creation replaces it."""
        for index in indices:
            item = self.session.items[index]
            # Only an edited prompt is worth recording; the project file is size-limited.
            origin = self._origin_prompts.pop(index, None)
            if keep_version(item, self._output_dir(), origin if origin != self._prompt(item) else ""):
                self._name_targets[index] = Path(item.output_path).resolve()
        self.flow._save_run()

    def _keep_previous_names(self):
        """Put each new picture at the replaced picture's path (its copy is a version).

        The worker names a redo after the raw file and a regeneration "_2"; the set,
        its membership and the result folder keep the familiar name instead.
        """
        targets, self._name_targets = self._name_targets, {}
        changed = False
        output = Path(self._output_dir()).resolve()
        for index, target in targets.items():
            item = self.session.items[index]
            if not item.output_path or item.status.value != "succeeded":
                continue
            new = Path(item.output_path)
            if (new.resolve() == target or target.parent != output or new.is_symlink()
                    or not new.is_file() or new.resolve().parent != output):
                continue
            new.replace(target)
            # The hash-bound chroma receipt follows its picture; the old one no longer matches.
            receipt, old_receipt = receipt_path(new), receipt_path(target)
            if receipt.is_file() and not receipt.is_symlink():
                receipt.replace(old_receipt)
            elif old_receipt.is_file() and not old_receipt.is_symlink():
                old_receipt.unlink()
            item.output_path = str(target)
            item.editor_output_path = ""
            changed = True
        if changed:
            self.flow._save_run()

    # --- results page ----------------------------------------------------------

    def install_results_page(self):
        if self._installed:
            return
        self._installed = True
        page = self.flow.run_queue.page
        page.queue.annotate = annotation
        page.queue.row_visible = self._row_visible
        bar = QWidget()
        top = QHBoxLayout(bar)
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(_small("Показать:", "#e4edf6"))
        self.results_filter = QComboBox()
        self.results_filter.setAccessibleName("Фильтр по меткам")
        self.results_filter.setFixedWidth(190)
        self.results_filter.currentIndexChanged.connect(self._results_filter_changed)
        top.addWidget(self.results_filter)
        legend = QLabel("  ".join(f"<span style='color:{MARK_COLOR[key]}'>●</span> {LIST_LABEL[key]}"
                                  for key, _, _ in MARKS))
        legend.setTextFormat(Qt.TextFormat.RichText)
        legend.setStyleSheet("color:#a6b5c8;")
        top.addSpacing(12)
        top.addWidget(legend)
        top.addStretch(1)
        layout = page.queue.parentWidget().layout()
        layout.insertWidget(layout.indexOf(page.queue), bar)
        self.results_bar = bar
        actions = QWidget()
        row = QVBoxLayout(actions)
        row.setContentsMargins(0, 0, 0, 0)
        self.results_summary = _small("")
        row.addWidget(self.results_summary)
        buttons = QHBoxLayout()
        self.recreate_button = V3Button("Пересоздать помеченные", ButtonVariant.PRIMARY)
        self.recreate_button.setToolTip(
            "Брак генерации — новая платная генерация (цена в подтверждении); брак вырезания — "
            "повторное вырезание из исходной картинки. Прежние картинки сохраняются как версии.")
        self.recreate_button.clicked.connect(self.recreate_marked)
        self.trash_button = V3Button("Корзина", ButtonVariant.SECONDARY)
        self.trash_button.setToolTip("Окончательно стереть удалённые картинки и старые версии")
        self.trash_button.clicked.connect(self.empty_trash)
        # Owner 2026-10-28: first row = everything that redoes pictures (marked, selected, failed); the second row
        # (the toolbar below) = the PNG check as the main button and «Ещё».
        self.redo_selected_button = V3Button("Переделать выбранные", ButtonVariant.SECONDARY)
        self.redo_selected_button.setToolTip("Выделите строки в списке (Ctrl или Shift для нескольких)")
        redo_menu = QMenu(self.redo_selected_button)
        # Owner 2026-10-30: short labels; the full path each action repeats lives in the hover tip.
        self.redo_generate_action = redo_menu.addAction("Перегенерировать")
        self.redo_generate_action.setToolTip(
            "Новая генерация картинки, затем весь путь обработки: удаление фона → апскейл → очистка края → "
            "резкость → обрезка → сохранение PNG.\nПрежняя картинка станет версией.")
        self.redo_generate_action.triggered.connect(self.regenerate_selected_rows)
        self.redo_cutout_action = redo_menu.addAction("Удалить фон заново")
        self.redo_cutout_action.setToolTip(
            "Повторное вырезание из сгенерированной картинки, затем апскейл → очистка края → резкость → "
            "обрезка → сохранение PNG.")
        self.redo_cutout_action.triggered.connect(self.cutout_selected_rows)
        self.redo_upscale_action = redo_menu.addAction("Апскейл заново")
        self.redo_upscale_action.setToolTip(
            "Повторный апскейл вырезанной картинки, затем очистка края → резкость → обрезка → сохранение PNG.")
        self.redo_upscale_action.triggered.connect(self.upscale_redo_selected_rows)
        self.redo_selected_button.setMenu(redo_menu)
        buttons.addWidget(self.recreate_button)
        buttons.addWidget(self.redo_selected_button)
        buttons.addWidget(page.retry_button)
        buttons.addStretch(1)
        buttons.addWidget(self.trash_button)
        row.addLayout(buttons)
        page.action_bar.layout().insertWidget(0, actions)
        self.results_actions = actions
        page.review_refresh = self.refresh_results
        page.queue.itemSelectionChanged.connect(
            lambda: self.redo_selected_button.setEnabled(
                bool(page.queue.selected_rows()) and not self.flow.is_busy()))

    def _row_visible(self, item):
        """While a run is going every row stays in the list: a regenerated picture loses its mark the moment it is
        replaced, and with the «Помеченные» filter the whole list would melt away under the owner's eyes."""
        session = self.session
        if session is not None and session.running:
            return True
        return visible(item, self.filter_mode)

    def _results_filter_changed(self, _index):
        mode = self.results_filter.currentData()
        if mode and mode != self.filter_mode:
            self.filter_mode = mode
            self.flow.run_queue.page.refresh_from_state()

    def _filter_labels(self, items):
        counts = mark_counts(items)
        marked = counts["bad_generation"] + counts["bad_cutout"] + counts["deleted"]
        return {"all": f"Все ({len(items)})", "unchecked": f"Не проверено ({counts['unchecked']})",
                "marked": f"Помеченные ({marked})", "deleted": f"Удалённые ({counts['deleted']})"}

    def refresh_results(self):
        self.session_changed()
        session = self.session
        idle = session is not None and not session.running
        # The filter stays on screen during a run (it is only switched off), so it never «disappears».
        self.results_bar.setVisible(session is not None)
        self.results_actions.setVisible(idle)
        if session is None:
            return
        items = session.items
        labels = self._filter_labels(items)
        self.results_filter.blockSignals(True)
        self.results_filter.clear()
        for key, _ in FILTERS:
            self.results_filter.addItem(labels[key], key)
        self.results_filter.setCurrentIndex(self.results_filter.findData(self.filter_mode))
        self.results_filter.blockSignals(False)
        self.results_filter.setEnabled(idle)
        self.results_filter.setToolTip("" if idle else "Во время запуска показываются все картинки")
        if not idle:
            return
        counts = mark_counts(items)
        marked = counts["bad_generation"] + counts["bad_cutout"]
        self.results_summary.setText(
            f"Помечено: брак генерации {counts['bad_generation']}, брак вырезания {counts['bad_cutout']}, "
            f"удалено {counts['deleted']}." if (marked or counts["deleted"]) else
            (f"Не проверено: {counts['unchecked']}. Двойной щелчок по строке открывает проверку PNG: "
             "там ставятся «Ок», метки и заметки.") if counts["unchecked"] else
            "Все картинки проверены.")
        self.recreate_button.setText(f"Пересоздать помеченные ({marked})")
        # Paid regeneration is the main action only when something is marked; otherwise it must not compete with
        # the transparency check.
        self.recreate_button.set_variant(ButtonVariant.SECONDARY)  # the PNG check is the main button
        self.redo_selected_button.setEnabled(bool(self.flow.run_queue.page.queue.selected_rows())
                                             and not self.flow.is_busy())
        self.recreate_button.setEnabled(bool(marked) and not self.flow.is_busy())
        deleted, versions = trash_paths(items, session.output_dir)
        self.trash_button.setText(f"Корзина ({len(deleted) + len(versions)})")
        self.trash_button.setEnabled(bool(deleted or versions))

    # --- re-creation ---------------------------------------------------------------

    def recreate_marked(self):
        session = self.session
        if session is None or session.running or self.flow.is_busy():
            return
        generation = [i for i, item in enumerate(session.items) if item.review_mark == "bad_generation"]
        cutout = [i for i, item in enumerate(session.items) if item.review_mark == "bad_cutout"]
        generation = session.regenerable_indices(generation)
        ready_cutout = session.reprocessable_indices(cutout)
        missing = len(cutout) - len(ready_cutout)
        page = self.flow.run_queue.page
        if not generation and not ready_cutout:
            QMessageBox.information(page, "Пересоздать помеченные",
                "Нечего пересоздать. Для брака вырезания исходная картинка уже удалена очисткой рабочих "
                "файлов — отметьте такие картинки как брак генерации." if missing else "Нет помеченных картинок.")
            return
        lines = []
        if ready_cutout:
            lines.append(f"Брак вырезания — {len(ready_cutout)}: повторное вырезание бережным режимом, "
                         "без новой генерации.")
        if missing:
            lines.append(f"Брак вырезания без исходной картинки — {missing}: пропущены.")
        lines.append("Текущие картинки не удаляются: они станут версиями и их можно вернуть.")
        self._pending_cutout = ready_cutout
        if generation:
            # The existing paid confirmation adds price, model and references.
            started = self.flow.run_queue.regenerate_selected(generation, summary=lines)
            self._chain_started = started is not None
            if started is None:
                self._pending_cutout = []
            return
        message = f"Вырезать заново: {len(ready_cutout)}?\n" + "\n".join(lines)
        if self._paid_upscale():
            message += "\nАпскейл после вырезания платный; стоимость не рассчитана."
        if QMessageBox.question(page, "Пересоздать помеченные", message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            self._pending_cutout = []
            return
        self._run_pending_cutout()

    def regenerate_selected_rows(self):
        session = self.session
        page = self.flow.run_queue.page
        if session is None or session.running or self.flow.is_busy():
            return
        rows = session.regenerable_indices(page.queue.selected_rows())
        if not rows:
            QMessageBox.information(page, "Перегенерировать", "Выделите готовые картинки в списке.")
            return
        self._pending_cutout = []
        started = self.flow.run_queue.regenerate_selected(rows)
        self._chain_started = False
        return started

    def cutout_selected_rows(self):
        session = self.session
        page = self.flow.run_queue.page
        if session is None or session.running or self.flow.is_busy():
            return
        chosen = page.queue.selected_rows()
        rows = session.reprocessable_indices(chosen)
        if not rows:
            QMessageBox.information(page, "Вырезать фон заново",
                "Выделите картинки в списке. Для вырезания нужна сохранённая исходная картинка генерации: "
                "у добавленных вручную файлов или после очистки рабочих файлов её нет.")
            return
        skipped = len(chosen) - len(rows)
        message = f"Вырезать фон заново: {len(rows)}?" + (f"\nБез исходной картинки, пропущены: {skipped}." if skipped else "")
        message += "\nТекущие картинки станут версиями и их можно вернуть."
        if self._paid_upscale():
            message += "\nАпскейл после вырезания платный; стоимость не рассчитана."
        if QMessageBox.question(page, "Вырезать фон заново", message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self._pending_cutout = []
        self._chain_started = False
        self.flow.run_queue.reprocess_selected(rows, DEFAULT_CUTOUT[2])

    def upscale_redo_selected_rows(self):
        """«Апскейл заново»: repeat the upscale stage from the picture that entered it (owner 2026-10-30)."""
        session = self.session
        page = self.flow.run_queue.page
        if session is None or session.running or self.flow.is_busy():
            return
        chosen = page.queue.selected_rows()
        rows = session.upscale_redoable_indices(chosen)
        if not rows:
            QMessageBox.information(page, "Апскейл заново",
                "Выделите картинки в списке. Нужна сохранённая картинка до апскейла: её нет у добавленных "
                "вручную файлов, а также если она уже удалена очисткой рабочих файлов.\n"
                "В этом случае перегенерируйте картинку или удалите фон заново — апскейл выполнится вновь.")
            return
        skipped = len(chosen) - len(rows)
        message = f"Апскейл заново: {len(rows)}?" + (f"\nБез картинки до апскейла, пропущены: {skipped}." if skipped else "")
        message += "\nГенерация и удаление фона не выполняются. Текущие картинки станут версиями и их можно вернуть."
        if self._paid_upscale():
            message += "\nАпскейл платный; стоимость не рассчитана."
        if QMessageBox.question(page, "Апскейл заново", message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self._pending_cutout = []
        self._chain_started = False
        self.flow.run_queue.upscale_redo_selected(rows)

    def _paid_upscale(self):
        settings = self.session.request.settings
        return bool(settings.get("upscale_after")) and provider_requires_cost(
            settings.get("upscale_after_provider") or "local_realesrgan")

    def _run_pending_cutout(self):
        pending, self._pending_cutout = self._pending_cutout, []
        if pending:
            self.flow.run_queue.reprocess_selected(pending, DEFAULT_CUTOUT[2])

    def session_changed(self):
        """After a run that really started has finished: names, chained redo, editor job.

        Confirmation dialogs and saves also refresh the page while nothing runs yet.
        """
        session = self.session
        if session is None:
            return
        if session.running:
            self._run_seen = True
            return
        if not self._run_seen:
            return
        self._run_seen = False
        if self._name_targets:
            try:
                self._keep_previous_names()
            except OSError:
                pass  # the new picture keeps the worker's name; nothing is lost
        # Only after the started run has finished: confirmation dialogs also refresh the page.
        if self._chain_started:
            self._chain_started = False
            QTimer.singleShot(0, self._run_pending_cutout)
        if self._job_started:
            self._job_started = False
            QTimer.singleShot(0, self._finish_editor_job)

    def empty_trash(self):
        session = self.session
        if session is None or session.running:
            return
        deleted, versions = trash_paths(session.items, session.output_dir)
        if not deleted and not versions:
            return
        names = ", ".join(path.stem for path in deleted[:5])
        message = ("Будут окончательно стёрты с диска:\n"
                   f"• удалённые картинки — {len(deleted)}" + (f" ({names})" if names else "") + ";\n"
                   f"• старые версии — {len(versions)} (их нельзя будет вернуть).\n"
                   "Текущие картинки наборов не затрагиваются.")
        box = QMessageBox(QMessageBox.Icon.Warning, "Очистить корзину?", message,
                          QMessageBox.StandardButton.NoButton, self.flow.run_queue.page)
        erase = box.addButton(f"Стереть файлов: {len(deleted) + len(versions)}",
                              QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not erase:
            return
        empty_trash(session.items, session.output_dir)
        self._save()

    # --- transparency check window ------------------------------------------------

    def attach_editor(self, editor, paths):
        """Add the review strip to an opened editor; paths are its file rows."""
        session = self.session
        by_output = {}
        for index, item in enumerate(session.items):
            if item.output_path:
                by_output[str(Path(item.output_path).resolve())] = index
        self._rows = [by_output.get(str(Path(path).resolve())) for path in paths]
        self._editor = editor
        self._preview_row = None
        self.editor_filter = QComboBox()
        self.editor_filter.setAccessibleName("Фильтр файлов по меткам")
        self.editor_filter.currentIndexChanged.connect(self._editor_filter_changed)
        editor.insert_file_filter(self.editor_filter)
        strip = self.strip = ReviewStrip()
        editor.add_canvas_footer(strip)
        for key, button in strip.mark_buttons.items():
            button.clicked.connect(lambda _=False, mark=key: self._set_mark(mark))
        self._note_timer = QTimer(strip)
        self._note_timer.setSingleShot(True)
        self._note_timer.setInterval(600)
        self._note_timer.timeout.connect(self._save_note)
        strip.note.textEdited.connect(lambda _text: self._note_timer.start())
        strip.note.editingFinished.connect(self._save_note)
        strip.history.clicked.connect(self._show_versions)
        strip.prompt_button.clicked.connect(self._edit_prompt)
        strip.try_button.clicked.connect(self._try_cutout)
        strip.brush_button.clicked.connect(self._use_brush)
        strip.to_generation_button.clicked.connect(lambda: self._set_mark("bad_generation"))
        strip.regenerate_button.clicked.connect(lambda: self._redo_from_editor("regenerate"))
        strip.autocut_button.clicked.connect(lambda: self._redo_from_editor("cutout"))
        strip.upscale_button.clicked.connect(lambda: self._redo_from_editor("upscale"))
        strip.cancel_button.clicked.connect(self._cancel_preview)
        strip.compare_button.clicked.connect(self._compare)
        strip.keep_button.clicked.connect(self._keep_preview)
        strip.restore_button.clicked.connect(lambda: self._set_mark("ok"))
        editor.file_list.currentRowChanged.connect(lambda _row: self.refresh_editor())
        self.refresh_editor()

    def detach_editor(self):
        self.flush_save()
        self._editor = None
        self._preview_row = None

    def _redo_from_editor(self, kind):
        """«Перегенерировать» / «Убрать фон» for the open picture; progress is on the results step, so the editor closes."""
        row, index = self._current()
        if index is None or self._job is not None or self._preview_row is not None:
            return
        path = self.session.items[index].output_path
        if not path:
            return
        editor = self._editor
        if kind == "regenerate":
            self.flow._regenerate_from_png_check(path)
        elif kind == "upscale":
            self.flow._upscale_redo_from_png_check(path)
        else:
            self.flow._cutout_from_png_check(path)
        if self.flow.is_busy() and editor is not None:
            editor.back_requested.emit()

    def _current(self):
        editor = self._editor
        if editor is None:
            return None, None
        row = editor.file_list.currentRow()
        index = self._rows[row] if 0 <= row < len(self._rows) else None
        if index is None or self.session is None or index >= len(self.session.items):
            return row, None
        return row, index

    def _editor_filter_changed(self, _index):
        mode = self.editor_filter.currentData()
        if mode:
            self.filter_mode = mode
            self.refresh_editor()

    def refresh_editor(self):
        editor = self._editor
        if editor is None or self.session is None:
            return
        items = self.session.items
        known = [items[index] for index in self._rows if index is not None]
        labels = self._filter_labels(known)
        self.editor_filter.blockSignals(True)
        self.editor_filter.clear()
        for key, _ in FILTERS:
            self.editor_filter.addItem(labels[key], key)
        self.editor_filter.setCurrentIndex(self.editor_filter.findData(self.filter_mode))
        self.editor_filter.blockSignals(False)
        rows = []
        for index in self._rows:
            if index is None:
                rows.append(None)
                continue
            item = items[index]
            state = mark_state(item)
            edited = bool(getattr(item, "prompt_edited", False))
            text = (LIST_LABEL[state] + (" · ✎ заметка" if item.review_note else "")
                    + (" · промпт исправлен" if edited else ""))
            rows.append((MARK_COLOR[state], text, item.review_mark == "deleted",
                         not visible(item, self.filter_mode), edited))
        editor.set_file_annotations(rows)
        self._refresh_strip()

    def _refresh_strip(self):
        strip, editor = self.strip, self._editor
        row, index = self._current()
        if index is None:
            editor.set_canvas_notice(None)
            strip.set_note("")
            strip.show_state(None, status="Файл не из этого запуска: метки недоступны. Нажмите «Ещё» → «Вернуть готовые файлы», чтобы подключить его.",
                             enabled=False)
            return
        item = self.session.items[index]
        strip.set_note(item.review_note)
        history = len(item.versions)
        if self._job is not None:
            strip.show_state(item.review_mark, status="Вырезаю заново из исходной картинки…",
                             history=history, enabled=False)
            return
        editor.set_canvas_notice(
            "Удалено из набора" if item.review_mark == "deleted" else None,
            "Не попадёт в обзорный лист, PDF и ZIP. Файл не стёрт — можно восстановить.")
        if self._preview_row == row:
            method = strip.method.currentText().split(" — ")[0]
            strip.show_state("bad_cutout", history=history, actions=(
                strip.cancel_button, strip.compare_button, strip.keep_button),
                status=f"Новый вариант: {method.lower()}. Прежний сохранён как версия {history}.")
            return
        mark = item.review_mark
        state = mark_state(item)
        if mark == "bad_generation":
            strip.show_state(mark, history=history, actions=(strip.prompt_button,), status=(
                "Будет создана заново кнопкой «Пересоздать помеченные» на странице результатов. "
                f"Текущая картинка сохранится как версия {history + 1}."))
        elif mark == "bad_cutout":
            if self.session.reprocessable_indices([index]):
                strip.show_state(mark, history=history,
                                 actions=(strip.method_label, strip.method, strip.try_button),
                                 status="Вырезать заново из исходной картинки, без новой генерации.")
            else:
                strip.show_state(mark, history=history,
                                 actions=(),
                                 status="⚠ Исходная картинка до вырезания уже удалена очисткой рабочих файлов. "
                                        "Вырезать заново не из чего: исправьте край кистью или пересоздайте "
                                        "картинку.")
        elif mark == "deleted":
            strip.show_state(mark, history=history, actions=(strip.restore_button,),
                             status="Удалено из набора.")
        elif state == "unchecked":
            strip.show_state(None, history=history, status=(
                "Не проверено. Поставьте «Ок», если всё хорошо, или метку брака."))
        else:
            strip.show_state(mark, history=history, status=(
                "Картинка в порядке. Поставьте метку, если что-то не так — менять ничего не нужно."))

    def edited_paths(self):
        """Resolved output paths of pictures whose prompt the owner corrected."""
        if self.session is None:
            return set()
        return {str(Path(item.output_path).resolve()) for item in self.session.items
                if item.output_path and getattr(item, "prompt_edited", False)}

    def marks_by_path(self):
        """{resolved output path: review mark} for the PNG-check screen of the export step."""
        if self.session is None:
            return {}
        return {str(Path(item.output_path).resolve()): mark_state(item)
                for item in self.session.items if item.output_path}

    def notes_by_path(self):
        """{resolved output path: note} so the gallery can badge a picture that carries a note."""
        if self.session is None:
            return {}
        return {str(Path(item.output_path).resolve()): item.review_note
                for item in self.session.items
                if item.output_path and getattr(item, "review_note", "")}

    def mark_output(self, path, mark):
        """Mark a picture by its file (used from the PNG-check screen); same data as the marks on the results step."""
        if self.session is None or mark not in (*MARK_LABEL, "unchecked") or self._job is not None:
            return
        target = str(Path(path).resolve())
        for item in self.session.items:
            if item.output_path and str(Path(item.output_path).resolve()) == target:
                if mark == "unchecked":  # the mark was taken off: back to «не проверено»
                    item.review_mark, item.review_checked = "ok", False
                else:
                    item.review_mark = mark
                    item.review_checked = True
                self._save()
                return

    def _set_mark(self, mark):
        row, index = self._current()
        if index is None or self._job is not None:
            return
        if self._preview_row == row:
            self._keep_preview()
        self.session.items[index].review_mark = mark
        self.session.items[index].review_checked = True
        self._save()
        self.refresh_editor()

    def _save_note(self):
        row, index = self._current()
        if index is None:
            return
        item = self.session.items[index]
        text = self.strip.note.text().strip()[:MAX_NOTE]
        if text != item.review_note:
            item.review_note = text
            self._save()
            self.refresh_editor()

    def _show_versions(self):
        row, index = self._current()
        if index is None:
            return
        item = self.session.items[index]
        dialog = VersionsDialog(self._editor, name=Path(item.output_path or "").name, item=item)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        chosen = dialog.chosen
        dialog.deleteLater()
        if accepted and chosen is not None:
            self._restore(index, chosen)

    def _restore(self, index, version):
        item = self.session.items[index]
        old = item.output_path
        try:
            restore_version(item, version, self._output_dir())
        except (OSError, ValueError) as error:
            QMessageBox.warning(self._editor, "История версий", str(error)[:500])
            return
        from v3_run_queue import RunItemStatus
        item.status = RunItemStatus.SUCCEEDED
        item.short_message = "Возвращена прежняя версия."
        item.editor_output_path = ""
        self._save()
        if self._editor is not None and old:
            self._editor.reload_file(old, item.output_path)
        self.refresh_editor()

    def regenerate_path(self, path):
        """«Перегенерировать» from the PNG-check screen: one picture through the same paid, confirmed re-creation."""
        session = self.session
        if session is None or session.running or self._job is not None or self.flow.is_busy():
            return None
        target = str(Path(path).resolve())
        for index, item in enumerate(session.items):
            if item.output_path and str(Path(item.output_path).resolve()) == target:
                self._pending_cutout = []
                started = self.flow.run_queue.regenerate_selected([index])
                self._chain_started = False
                return started
        return None

    def cutout_unavailable_reason(self, path):
        """Why «Убрать фон» cannot start for this picture (empty when it can)."""
        session = self.session
        if session is None:
            return "Нет открытого проекта."
        if session.running or self._job is not None or self.flow.is_busy():
            return "Дождитесь окончания текущей работы и повторите."
        target = str(Path(path).resolve())
        for index, item in enumerate(session.items):
            if item.output_path and str(Path(item.output_path).resolve()) == target:
                if not session.reprocessable_indices([index]):
                    return ("Не найдена сохранённая исходная картинка генерации (например, файл был добавлен "
                            "вручную или рабочие файлы удалены), поэтому вырезать фон заново нельзя.")
                return ""
        return "Картинка не найдена в проекте."

    def cutout_path(self, path):
        """«Убрать фон» from the PNG-check screen: one picture through the free local re-cutout (a white or
        leftover background after a regeneration); the old picture is kept as a version."""
        session = self.session
        if session is None or session.running or self._job is not None or self.flow.is_busy():
            return None
        target = str(Path(path).resolve())
        for index, item in enumerate(session.items):
            if item.output_path and str(Path(item.output_path).resolve()) == target:
                self._pending_cutout = []
                started = self.flow.run_queue.reprocess_selected([index], CUTOUT_METHODS[2][2])
                self._chain_started = False
                return started
        return None

    def upscale_redo_unavailable_reason(self, path):
        """Why «Апскейл заново» cannot start for this picture (empty when it can)."""
        session = self.session
        if session is None:
            return "Нет открытого проекта."
        if session.running or self._job is not None or self.flow.is_busy():
            return "Дождитесь окончания текущей работы и повторите."
        target = str(Path(path).resolve())
        for index, item in enumerate(session.items):
            if item.output_path and str(Path(item.output_path).resolve()) == target:
                if not session.upscale_redoable_indices([index]):
                    return ("Не найдена сохранённая картинка до апскейла (у добавленных вручную файлов её нет, "
                            "или она удалена очисткой рабочих файлов). Перегенерируйте картинку или удалите фон "
                            "заново — апскейл выполнится вновь.")
                return ""
        return "Картинка не найдена в проекте."

    def upscale_redo_path(self, path):
        """«Апскейл заново» for one picture: repeat the upscale stage from the saved picture before it."""
        session = self.session
        if session is None or session.running or self._job is not None or self.flow.is_busy():
            return None
        target = str(Path(path).resolve())
        for index, item in enumerate(session.items):
            if item.output_path and str(Path(item.output_path).resolve()) == target:
                self._pending_cutout = []
                started = self.flow.run_queue.upscale_redo_selected([index])
                self._chain_started = False
                return started
        return None

    def edit_prompt_for(self, path, parent):
        """«Изменить промпт» from the PNG-check screen: the same dialog as in the transparency window."""
        if self.session is None or self._job is not None:
            return
        target = str(Path(path).resolve())
        for index, item in enumerate(self.session.items):
            if item.output_path and str(Path(item.output_path).resolve()) == target:
                self._edit_prompt_of(index, parent)
                return

    def _edit_prompt(self):
        row, index = self._current()
        if index is None:
            return
        self._edit_prompt_of(index, self._editor)

    def _edit_prompt_of(self, index, parent):
        item = self.session.items[index]
        current = self._prompt(item)
        original = self._origin_prompts.get(index, current)
        current_references = ([str(path) for path in (item.payload or {}).get("references") or []]
                              if isinstance(item.payload, dict) else [])
        dialog = PromptDialog(parent, path=item.output_path,
                              title=f"{Path(item.output_path or '').name} · Брак генерации",
                              note=item.review_note, prompt=current, original=original,
                              references=current_references)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        prompt = dialog.prompt()
        references = dialog.references() if hasattr(dialog, "references") else current_references
        dialog.deleteLater()
        if not accepted or (prompt == current and references == current_references):
            return
        if references != current_references:
            # Only this picture: its own request entry and prompt record, never the set's reference list.
            item.payload["references"] = list(references)
            entry = self._prompt_entry(item)
            if entry is not None:
                entry.references = list(references)
        if prompt == current:
            self._save()
            return
        self._origin_prompts.setdefault(index, current)
        item.payload["prompt"] = prompt
        # Back to the very first text clears the badge; any other change sets it.
        item.prompt_edited = prompt != self._origin_prompts[index]
        entry = self._prompt_entry(item)
        if entry is not None:
            entry.prompt = prompt
        self._save()

    def _use_brush(self):
        editor = self._editor
        button = getattr(editor, "tool_buttons", {}).get("brush")
        if button is not None:
            button.click()
        editor.canvas.setFocus()

    def _try_cutout(self):
        row, index = self._current()
        if index is None or self._job is not None:
            return
        key = self.strip.method.currentData()
        overrides = next(method[2] for method in CUTOUT_METHODS if method[0] == key)

        def confirm(_request):
            paid = method_is_paid(overrides) or self._paid_upscale()
            if not paid:
                return True
            return QMessageBox.question(
                self._editor, "Вырезать заново",
                "Выбранный способ или апскейл после вырезания платный; стоимость не рассчитана.\n"
                "Новой генерации не будет. Продолжить?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

        old = self.session.items[index].output_path
        self._job = (row, index, old)
        self._editor.setEnabled(False)
        self.strip.setEnabled(True)
        request = self.flow.run_queue.reprocess_selected([index], overrides, confirm=confirm)
        if request is None:
            self._job = None
            self._editor.setEnabled(True)
        else:
            self._job_started = True
        self.refresh_editor()

    def _finish_editor_job(self):
        if self._job is None or self.session is None or self.session.running:
            return
        row, index, old = self._job
        self._job = None
        item = self.session.items[index]
        editor = self._editor
        from v3_run_queue import RunItemStatus
        succeeded = item.status is RunItemStatus.SUCCEEDED and bool(item.output_path)
        if editor is None:
            # The window was closed during the redo: keep a good result, otherwise go back.
            if not succeeded and item.versions:
                note = item.versions[-1]["note"]
                self._restore(index, len(item.versions) - 1)
                item.review_mark, item.review_note = "bad_cutout", note
            self._save()
            return
        editor.setEnabled(True)
        if succeeded:
            # Shown until the owner keeps or cancels the preview.
            item.review_mark = "bad_cutout"
            item.review_note = item.versions[-1]["note"] if item.versions else ""
            self._preview_row = row
            editor.reload_file(old, item.output_path)
        else:
            QMessageBox.warning(editor, "Вырезать заново",
                                "Не получилось вырезать заново. Возвращаю прежний вариант.\n"
                                + (item.short_message or "")[:300])
            if item.versions:
                note = item.versions[-1]["note"]
                self._restore(index, len(item.versions) - 1)
                item.review_mark, item.review_note = "bad_cutout", note
        self._save()
        self.refresh_editor()

    def _keep_preview(self):
        row, index = self._current()
        if self._preview_row is None or index is None:
            return
        self._preview_row = None
        item = self.session.items[index]
        item.review_mark, item.review_note = "ok", ""
        item.review_checked = True
        self._save()
        self.refresh_editor()

    def _cancel_preview(self):
        row, index = self._current()
        if self._preview_row is None or index is None:
            return
        self._preview_row = None
        item = self.session.items[index]
        if item.versions:
            note = item.versions[-1]["note"]
            self._restore(index, len(item.versions) - 1)
            # The rejected attempt is not a version worth keeping.
            discard_last_version(item, self._output_dir())
            item.review_mark, item.review_note = "bad_cutout", note
            self._save()
        self.refresh_editor()

    def _compare(self):
        row, index = self._current()
        if index is None:
            return
        item = self.session.items[index]
        if item.versions and item.output_path:
            compare_dialog(self._editor, item.versions[-1]["path"], item.output_path)
