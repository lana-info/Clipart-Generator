"""Prompt Composer page. All persistence and paid work belongs to the host."""

from __future__ import annotations

from copy import deepcopy
import json
import random

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QMessageBox, QPushButton, QScrollArea, QSplitter,
    QTextEdit, QVBoxLayout, QWidget,
)


FIELDS = {
    "subject": "Герой или предмет", "appearance": "Внешность / особенности",
    "wardrobe": "Одежда / аксессуары", "material": "Материал",
    "color": "Цвет", "location": "Место", "surface": "Поверхность",
    "style": "Стиль", "lighting": "Освещение", "time": "Время",
    "camera": "Камера / движение", "shot": "Крупность", "angle": "Ракурс",
    "action": "Действие", "duration": "Длительность", "aspect": "Формат кадра",
    "exclusions": "Что исключить",
}
STEPS = ("Начало", "Кто / что в кадре", "Детали", "Сцена", "Готовые промпты")
TYPES = ("person", "character", "animal", "product", "object", "place")
TYPE_NAMES = ("Человек", "Персонаж", "Животное", "Товар", "Предмет", "Место")
IDENTITY_FIELDS = frozenset({"subject", "appearance", "wardrobe", "material", "color"})


def _button(label, slot, name=""):
    widget = QPushButton(label)
    if name:
        widget.setObjectName(name)
    widget.clicked.connect(slot)
    return widget


def _label(value):
    widget = QLabel(str(value))
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    return widget


def _text_error(exc):
    """Host errors may include URLs, tokens, or paths; show a safe local message."""
    if any(word in type(exc).__name__.lower() for word in ("conflict", "revision")):
        return "Запись уже изменена. Откройте её заново и сохраните отдельную копию."
    return "Действие не выполнено. Проверьте настройки и повторите вручную."


class PromptComposerPage(QWidget):
    back_requested = pyqtSignal()
    settings_requested = pyqtSignal()

    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self.setObjectName("promptComposerPage")
        self.setMinimumSize(750, 560)
        self._catalog = host.catalogue()
        self.draft = deepcopy(host.new_draft())
        self.draft.setdefault("fields", {})
        self.draft.setdefault("locks", [])
        self.draft.setdefault("references", [])
        self.draft.setdefault("revision", 1)
        self._saved_record = None
        self._favorite = False
        self._dirty = False
        self._step = 0
        self._tab = "composer"
        self._template_category = "people"
        self._template_placeholder = None
        self._reset_start_path()
        self._variants = []
        self._variant_index = 0
        self._variant_edits = {}
        self._proposal = None
        self._proposal_index = 0
        self._language = "en"
        self._ai_ticket = None
        self._ai_serial = 0
        self._library_rows = []
        self._build_shell()
        self._render()

    def _build_shell(self):
        self.setStyleSheet("""
            QWidget#promptComposerPage { background: #111b29; color: #e8f1f4; font-size: 13px; }
            QWidget#promptComposerPage QLabel { color: #e8f1f4; }
            QWidget#promptComposerPage QFrame[panel="true"] { background: #1d2b3b; border: 1px solid #35485c; border-radius: 9px; }
            QWidget#promptComposerPage QPushButton { background: #25394a; color: #e8f1f4; border: 1px solid #496175; border-radius: 6px; padding: 7px 11px; }
            QWidget#promptComposerPage QPushButton:hover { border-color: #27c4b1; }
            QWidget#promptComposerPage QPushButton[primary="true"] { background: #20ae9e; color: #071b22; border-color: #20ae9e; font-weight: bold; }
            QWidget#promptComposerPage QLineEdit, QWidget#promptComposerPage QTextEdit, QWidget#promptComposerPage QComboBox, QWidget#promptComposerPage QListWidget { background: #152332; color: #f3f8f9; border: 1px solid #486077; border-radius: 5px; padding: 5px; selection-background-color: #247e79; }
            QWidget#promptComposerPage QScrollArea { border: 0; background: transparent; }
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 12)
        outer.setSpacing(10)
        top = QHBoxLayout()
        brand = QLabel("VIBIX Studio  /  Конструктор промптов")
        brand.setStyleSheet("font-weight:bold;color:#29c9ba;font-size:15px")
        top.addWidget(brand)
        top.addStretch()
        top.addWidget(_button("Каталог Studio", self._request_back, "backButton"))
        top.addWidget(_button("Настройки AI", self.settings_requested.emit, "settingsButton"))
        outer.addLayout(top)
        title = QLabel("Конструктор промптов")
        title.setStyleSheet("font-size:23px;font-weight:bold")
        outer.addWidget(title)
        outer.addWidget(QLabel("От идеи до готового текста. Сохраняйте удачные варианты и меняйте детали."))
        tabs = QHBoxLayout()
        tabs.setSpacing(8)
        self.composer_tab = _button("Конструктор", lambda: self._show_tab("composer"), "composerTab")
        self.library_tab = _button("Сохранённые промпты", lambda: self._show_tab("library"), "libraryTab")
        for button in (self.composer_tab, self.library_tab):
            button.setFixedSize(190, 38)
        tabs.addStretch()
        tabs.addWidget(self.composer_tab)
        tabs.addWidget(self.library_tab)
        tabs.addStretch()
        outer.addLayout(tabs)
        self.steps_row = QHBoxLayout()
        self.step_buttons = []
        for index, name in enumerate(STEPS):
            btn = _button(f"{index + 1}  {name}", lambda checked=False, i=index: self.goto_step(i), f"step{index}")
            self.step_buttons.append(btn)
            self.steps_row.addWidget(btn)
        outer.addLayout(self.steps_row)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        outer.addWidget(self.scroll, 1)
        self.footer = QHBoxLayout()
        outer.addLayout(self.footer)
        self.status = QLabel("")
        self.status.setObjectName("composerStatus")
        self.status.setStyleSheet("color:#a8c9c8")
        outer.addWidget(self.status)

    def _show_message(self, message, title="Конструктор промптов"):
        self.status.setText(message)
        QMessageBox.information(self, title, message)

    def _error(self, exc):
        # Async core returns an already sanitized message; exceptions stay opaque.
        self._show_message(exc if isinstance(exc, str) else _text_error(exc), "Ошибка")

    def _set_dirty(self):
        self._dirty = True
        if self._proposal:
            self._proposal["stale"] = True
        self.draft["revision"] = int(self.draft.get("revision", 0)) + 1

    def _fingerprint(self, draft=None):
        return json.dumps(draft or self.draft, ensure_ascii=False, sort_keys=True, default=str)

    def _field_pair(self, key):
        raw = self.draft.get("fields", {}).get(key, {})
        return raw if isinstance(raw, dict) else {"ru": str(raw), "en": ""}

    def _set_field(self, key, ru, en):
        pair = {"ru": ru.strip(), "en": en.strip()}
        if self._field_pair(key) != pair:
            if not self._guard_manual_rebuild():
                return
            self.draft.setdefault("fields", {})[key] = pair
            if key in IDENTITY_FIELDS:
                self._template_placeholder = None
            if not self.draft.get("manual_en") and not self.draft.get("manual_ru"):
                self.draft["base_en"] = self.draft["base_ru"] = ""
            self.draft["selection_seed"] = 0
            self._set_dirty()

    def _set_property(self, key, value):
        if self.draft.get(key) != value:
            if key in ("mode", "subject_type") and not self._guard_manual_rebuild():
                return
            self.draft[key] = value
            if key == "subject_type":
                self._template_placeholder = None
            if key in ("mode", "subject_type", "locks"):
                self.draft["selection_seed"] = 0
            self._set_dirty()

    def _set_mode(self, mode):
        if mode != self.draft.get("mode"):
            if not self._guard_manual_rebuild():
                # Checkable buttons toggle before clicked; restore the draft's mode.
                self._render()
                return
            self._set_property("mode", mode)
            self._pending_template_id = self._applied_template_id = None
            self._template_direction = None
            if mode == "reels" and "aspect" not in self.draft.get("locks", []):
                self._set_field("aspect", "9:16", "9:16")
            self._render()

    def _request_back(self):
        if self.confirm_close():
            self.back_requested.emit()

    def confirm_close(self):
        if not self._guard_dirty("Закрыть конструктор?"):
            return False
        self.cancel_ai()
        try:
            self.host.close()
        except Exception as exc:
            self._error(exc)
            return False
        return True

    def _ask_save_discard(self, question):
        box = QMessageBox(self)
        box.setWindowTitle("Несохранённые изменения")
        box.setText(question)
        save = box.addButton("Сохранить изменения", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("Не сохранять", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is save:
            return "save"
        if box.clickedButton() is discard:
            return "discard"
        return "cancel"

    def _guard_dirty(self, question="Сохранить текущие изменения?"):
        if not self._dirty:
            return True
        choice = self._ask_save_discard(question)
        return choice == "discard" or (choice == "save" and self._save_before_leave())

    def _save_before_leave(self):
        # Snapshot all edits before saving the selected card changes draft state.
        selected = self._selected_draft()
        def content(value):
            return {k: v for k, v in value.items() if k not in ("revision", "selection_seed")}
        others = [(value, source) for value, source in self._manual_snapshots()
                  if content(value) != content(selected)]
        if not self.save_current():
            return False
        if not self._save_manual_copies(others):
            self._dirty = True
            return False
        self._variant_edits.clear()
        self._dirty = False
        return True

    def _guard_manual_rebuild(self, clear=True):
        if not self._manual_snapshots():
            return True
        box = QMessageBox(self)
        box.setWindowTitle("Ручная правка текста")
        box.setText("Ручной текст может отличаться от параметров. Как продолжить сборку?")
        save = box.addButton("Сохранить копии правок", QMessageBox.ButtonRole.AcceptRole)
        replace = box.addButton("Заменить новой сборкой", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is save and not self._save_manual_copies():
            return False
        if box.clickedButton() not in (save, replace):
            return False
        if clear:
            self.draft["manual_en"] = None
            self.draft["manual_ru"] = None
            self.draft["translation_stale"] = False
            self._variant_edits.clear()
            for variant in self._variants:
                variant.get("draft", {}).update(manual_en=None, manual_ru=None, translation_stale=False)
            self._set_dirty()
        return True

    def _manual_snapshots(self):
        snapshots = []
        seen = set()
        candidates = [(self.draft, "local")]
        for index, variant in enumerate(self._variants):
            value = deepcopy(variant.get("draft") or self.draft)
            value.update(base_en=variant.get("en", ""), base_ru=variant.get("ru", ""))
            value.update(self._variant_edits.get(index, {}))
            candidates.append((value, variant.get("source", "local")))
        for value, source in candidates:
            if value.get("manual_en") is None and value.get("manual_ru") is None:
                continue
            key = json.dumps({k: v for k, v in value.items() if k not in ("revision", "selection_seed")}, ensure_ascii=False, sort_keys=True)
            if key not in seen:
                snapshots.append((deepcopy(value), source))
                seen.add(key)
        return snapshots

    def _save_manual_copies(self, snapshots=None):
        try:
            for index, (snapshot, source) in enumerate(self._manual_snapshots() if snapshots is None else snapshots, 1):
                name = (snapshot.get("name") or "Промпт")[:90] + f" · ручная правка {index}"
                self.host.save(snapshot, {"name": name, "kind": "prompt", "source": source,
                                         "tags": [], "favorite": False})
        except Exception as exc:
            self._error(exc)
            return False
        return True

    def _show_tab(self, tab):
        if tab == self._tab:
            return
        if tab == "library" and not self._guard_dirty():
            return
        self._tab = tab
        self._render()

    def goto_step(self, index):
        if self._step == 0 and index != 0 and self._start_path == "template" and self._pending_template_id:
            identifier = self._pending_template_id
            templates = self._catalog.get("templates", [])
            if isinstance(templates, dict):
                templates = templates.values()
            template = next((item for item in templates
                             if item.get("id") == identifier and item["draft"]["mode"] == self.draft.get("mode")), None)
            self._pending_template_id = None
            if template is not None and not self.apply_template(template):
                self._pending_template_id = identifier
                return False
            if template is not None and index == 1:
                return True
        if self._step == 4 and index != 4 and not self._proposal and self._active_variant():
            cursor = self.draft.get("selection_seed", 0)
            self.draft = self._selected_draft()
            self.draft["selection_seed"] = cursor
        if index == 4 and self._step != 4:
            return self.generate_local()
        self._tab = "composer"
        self._step = index
        self._render()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _render(self):
        self._clear_layout(self.footer)
        self.steps_row.setEnabled(self._tab == "composer")
        for index, btn in enumerate(self.step_buttons):
            btn.setVisible(self._tab == "composer")
            btn.setStyleSheet("background:#146e70" if index == self._step and self._tab == "composer" else "")
        self.composer_tab.setStyleSheet("background:#146e70" if self._tab == "composer" else "")
        self.library_tab.setStyleSheet("background:#146e70" if self._tab == "library" else "")
        body = QWidget()
        body.setObjectName("composerBody")
        body.setStyleSheet("QWidget#composerBody { background: #111b29; color: #e8f1f4; }")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(1, 5, 1, 5)
        layout.setSpacing(10)
        if self._tab == "library":
            self._render_library(layout)
            self.footer.addWidget(_button("Новый промпт", self.new_draft, "newDraftButton"))
        else:
            (self._render_templates, self._render_subject, self._render_details,
             self._render_scene, self._render_results)[self._step](layout)
            if self._step == 4:
                self.footer.addWidget(_button("Ещё 7 вариантов", self.generate_local, "moreVariantsButton"))
                self.footer.addWidget(_button("Предложить с AI…", self.request_ai_variants, "aiButton"))
            else:
                if self._step:
                    self.footer.addWidget(_button("Назад", self._previous_step, "previousButton"))
                self.footer.addStretch()
                next_label = "Получить 7 вариантов" if self._step == 3 else "Далее"
                next_btn = _button(next_label, self._next_step, "nextButton")
                next_btn.setProperty("primary", True)
                self.footer.addWidget(next_btn)
        layout.addStretch()
        # setWidget deletes the previous body immediately. A selection signal
        # can arrive inside that body's mouse/key handler; keep its widgets
        # alive until Qt finishes dispatching the current event.
        previous_body = self.scroll.takeWidget()
        if previous_body is not None:
            previous_body.hide()
            previous_body.deleteLater()
        self.scroll.setWidget(body)

    def _previous_step(self):
        if self._step == 0:
            self._show_tab("library")
        else:
            self.goto_step(self._step - 1)

    def _next_step(self):
        self.goto_step(self._step + 1)

    def _panel(self, parent_layout, title):
        frame = QFrame()
        frame.setProperty("panel", True)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 15, 16, 15)
        heading = QLabel(title)
        heading.setStyleSheet("font-size:17px;font-weight:bold")
        layout.addWidget(heading)
        parent_layout.addWidget(frame)
        return layout

    def _render_templates(self, outer):
        outer.setSpacing(8)
        paths = QHBoxLayout()
        paths.addStretch()
        for key, label in (("template", "По шаблону"), ("custom", "Самостоятельно")):
            selected = self._start_path == key
            button = _button(("✓  " if selected else "") + label,
                             lambda checked=False, path=key: self._set_start_path(path), "start_" + key)
            button.setFixedWidth(190)
            button.setMinimumHeight(38)
            button.setCheckable(True)
            button.setChecked(selected)
            if selected:
                button.setStyleSheet("background:#146e70;border-color:#29c9ba;font-weight:bold;")
            paths.addWidget(button)
        paths.addStretch()
        outer.addLayout(paths)
        self._mode_selector(outer)
        if self._start_path == "custom":
            panel = self._panel(outer, "Самостоятельная настройка")
            panel.addWidget(QLabel("Героя, детали и сцену можно задать на следующих шагах."))
            return
        categories = self._catalog.get("categories", [])
        if categories:
            heading = QLabel("Тип")
            heading.setObjectName("templateTypeHeading")
            heading.setStyleSheet("font-size:14px;font-weight:bold;color:#a8c9c8;")
            outer.addWidget(heading)
            ids = {item["id"] for item in categories}
            if self._template_category not in ids:
                self._template_category = categories[0]["id"]
            category_grid = QGridLayout()
            category_grid.setSpacing(8)
            for index, category in enumerate(categories):
                selected = category["id"] == self._template_category
                button = _button(("✓  " if selected else "") + category["label"],
                    lambda checked=False, key=category["id"]: self._select_template_category(key),
                    "category_" + category["id"])
                button.setCheckable(True)
                button.setChecked(selected)
                button.setMinimumHeight(38)
                if selected:
                    button.setStyleSheet("background:#146e70;border-color:#29c9ba;font-weight:bold;")
                category_grid.addWidget(button, index // 3, index % 3)
            outer.addLayout(category_grid)
            outer.addSpacing(4)
            divider = QFrame()
            divider.setObjectName("templateGroupsDivider")
            divider.setFixedHeight(1)
            divider.setStyleSheet("background:#3b5062;")
            outer.addWidget(divider)
        templates = self._catalog.get("templates", [])
        if isinstance(templates, dict):
            templates = list(templates.values())
        templates = [t for t in templates if isinstance(t, dict) and t.get("mode", t.get("draft", {}).get("mode", self.draft.get("mode"))) == self.draft.get("mode")]
        if categories:
            templates = [t for t in templates if not t.get("legacy") and t.get("category") == self._template_category]
        directions = [item for item in self._catalog.get("directions", [])
                      if item.get("category") == self._template_category]
        direction = next((item for item in directions if item["id"] == self._template_direction), None)
        header = QHBoxLayout()
        showing_directions = bool(directions) and direction is None
        if showing_directions:
            templates = directions
            heading = QLabel("Направление")
            heading.setObjectName("templateDirectionHeading")
        else:
            if direction:
                back = _button("← Направления", lambda: self._select_template_direction(None), "directionsBack")
                back.setFixedSize(150, 30)
                header.addWidget(back)
                templates = [t for t in templates if t.get("direction") == direction["id"]]
            heading = QLabel("Сценарий" + (" · " + direction["label"] if direction else ""))
            heading.setObjectName("templateScenarioHeading")
        heading.setStyleSheet("font-size:14px;font-weight:bold;color:#a8c9c8;")
        header.addWidget(heading)
        header.addStretch()
        outer.addLayout(header)
        grid = QGridLayout()
        grid.setSpacing(10)
        for index, template in enumerate(templates):
            selected = not showing_directions and template.get("id") == (self._pending_template_id or self._applied_template_id)
            name = f"direction{index}" if showing_directions else f"template{index}"
            callback = (lambda checked=False, key=template["id"]: self._select_template_direction(key)) if showing_directions else (
                lambda checked=False, t=template: self._select_start_template(t))
            btn = _button("", callback, name)
            if selected:
                btn.setStyleSheet(f"QPushButton#{name} {{border:2px solid #29c9ba;background:#1b3d46;}}")
            btn.setAccessibleName(template.get("label", "Шаблон"))
            btn.setProperty("directionId" if showing_directions else "templateId", template.get("id", ""))
            btn.setMinimumHeight(108)
            card = QVBoxLayout(btn)
            card.setContentsMargins(14, 12, 14, 12)
            title = _label(("✓  " if selected else "") + template.get("label", template.get("id", "Шаблон")))
            title.setStyleSheet("font-weight:bold;font-size:14px;background:transparent;")
            description = _label(template.get("description", ""))
            description.setStyleSheet("color:#b5c8d7;background:transparent;")
            for label in (title, description):
                label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                card.addWidget(label)
            grid.addWidget(btn, index // 3, index % 3)
        outer.addLayout(grid)

    def _select_template_category(self, category):
        if category != self._template_category:
            self._pending_template_id = None
            self._template_direction = None
        self._template_category = category
        self._render()

    def _reset_start_path(self, path="template"):
        self._start_path = path
        self._pending_template_id = self._applied_template_id = None
        self._template_direction = None

    def _set_start_path(self, path):
        self._start_path = path
        if path == "custom":
            self._pending_template_id = None
            self._template_direction = None
        self._render()

    def _select_template_direction(self, direction):
        if direction is not None and not any(item.get("category") == self._template_category and item.get("id") == direction
                                             for item in self._catalog.get("directions", [])):
            return False
        self._template_direction = direction
        self._pending_template_id = None
        self._render()
        return True

    def _select_start_template(self, template):
        self._pending_template_id = template["id"]
        self._render()

    def apply_template(self, template):
        replacement = deepcopy(template.get("draft", {}))
        locked = set(self.draft.get("locks", []))
        custom_subject = True
        if template.get("reusable"):
            fields = self.draft.get("fields", {})
            subject = fields.get("subject", {})
            # A fresh draft's neutral placeholder is not a user-selected hero.
            default_subject = {"ru": "предмет", "en": "object"}
            current_type = self.draft.get("subject_type")
            generated_placeholder = self._template_placeholder == (current_type, subject)
            custom_subject = (subject != default_subject and not generated_placeholder and any(subject.get(lang, "").strip() for lang in ("ru", "en"))) or "subject" in locked or bool(self.draft.get("references"))
            target_type = replacement.get("subject_type")
            groups = ({"person", "character"}, {"product", "object"}, {"animal"}, {"place"})
            if custom_subject and not any(current_type in group and target_type in group for group in groups):
                self._show_message("Этот сценарий рассчитан на другой тип героя. Выберите подходящий раздел или начните новый промпт.")
                return False
            incoming = replacement.setdefault("fields", {})
            for key in {"appearance", "wardrobe", "material", "color", "exclusions"} | locked | ({"subject"} if custom_subject else set()):
                pair = fields.get(key)
                if pair is not None and (key in locked or any(pair.get(lang, "").strip() for lang in ("ru", "en"))):
                    incoming[key] = deepcopy(pair)
            if custom_subject:
                replacement["subject_type"] = current_type
            replacement["profile_id"] = self.draft.get("profile_id")
        clashes = [key for key in locked if replacement.get("fields", {}).get(key) not in (None, self.draft.get("fields", {}).get(key))]
        if clashes:
            self._show_message("Шаблон конфликтует с закреплениями: " + ", ".join(FIELDS.get(k, k) for k in clashes))
            return False
        if not self._guard_manual_rebuild():
            return False
        retained_fields = {key: deepcopy(self.draft.get("fields", {}).get(key)) for key in locked}
        incoming_fields = deepcopy(replacement.get("fields", {}))
        incoming_fields.update({key: value for key, value in retained_fields.items() if value is not None})
        replacement["fields"] = incoming_fields
        replacement["locks"] = sorted(locked | set(replacement.get("locks", [])))
        replacement["references"] = deepcopy(self.draft.get("references", []))
        for key, value in replacement.items():
            if key not in ("revision", "schema_version", "catalog_version"):
                self.draft[key] = value
        self._template_placeholder = (self.draft.get("subject_type"), deepcopy(self.draft.get("fields", {}).get("subject", {}))) if template.get("reusable") and not custom_subject else None
        self._pending_template_id = None
        self._applied_template_id = template.get("id")
        self._set_dirty()
        self.goto_step(1)
        return True

    def _render_subject(self, outer):
        panel = self._panel(outer, "Кто или что в кадре")
        row = QHBoxLayout()
        combo = QComboBox()
        combo.setObjectName("subjectTypeCombo")
        types = self._catalog.get("subject_types", [])
        if not types:
            types = [{"id": key, "label": label} for key, label in zip(TYPES, TYPE_NAMES)]
        for item in types:
            combo.addItem(item.get("label", item["id"]), item["id"])
        current = combo.findData(self.draft.get("subject_type"))
        combo.setCurrentIndex(max(current, 0))
        combo.currentIndexChanged.connect(lambda: self._change_subject_type(combo.currentData()))
        row.addWidget(QLabel("Тип"))
        row.addWidget(combo, 1)
        row.addWidget(_button("Выбрать профиль", self.choose_profile, "chooseProfileButton"))
        row.addWidget(_button("Сохранить профиль", self.save_profile, "saveProfileButton"))
        panel.addLayout(row)
        subject_type = self.draft.get("subject_type")
        fields = ["subject", "appearance", "wardrobe"] if subject_type in ("person", "character", "animal") else ["subject", "material", "color", "appearance"]
        for key in fields:
            self._field_editor(panel, key)
        panel.addWidget(_button("Добавить референс", self.import_reference, "addReferenceButton"))
        for handle in self.draft.get("references", []):
            try:
                available = self.host.reference_available(handle)
            except Exception:
                available = False
            line = QHBoxLayout()
            line.addWidget(QLabel("Референс: " + ("доступен" if available else "файл недоступен")))
            line.addWidget(_button("Удалить", lambda checked=False, h=handle: self._remove_reference(h)))
            panel.addLayout(line)

    def _change_subject_type(self, kind):
        if kind != self.draft.get("subject_type"):
            self._set_property("subject_type", kind)
            self._render()

    def _field_editor(self, panel, key):
        row = QHBoxLayout()
        label = QLabel(FIELDS[key])
        label.setMinimumWidth(150)
        row.addWidget(label)
        pair = self._field_pair(key)
        combo = QComboBox()
        combo.setObjectName(f"field_{key}")
        combo.addItem("Выберите или введите своё…", None)
        for option in self._catalog.get("options", {}).get(key, []):
            combo.addItem(option.get("ru", option.get("id", "")), option)
        selected = -1
        for i in range(1, combo.count()):
            if combo.itemData(i).get("ru") == pair.get("ru") and combo.itemData(i).get("en") == pair.get("en"):
                selected = i
                break
        if selected >= 0:
            combo.setCurrentIndex(selected)
        else:
            combo.setEditable(True)
            combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            combo.setCurrentIndex(-1)
            combo.lineEdit().setPlaceholderText("Выберите или введите своё…")
            combo.setEditText(pair.get("ru", ""))
        combo.currentIndexChanged.connect(lambda _=0, c=combo, k=key: self._select_option(k, c))
        if combo.isEditable():
            combo.lineEdit().editingFinished.connect(lambda c=combo, k=key: self._custom_field(k, c.currentText()))
        row.addWidget(combo, 1)
        custom = _button("Своё RU/EN", lambda checked=False, k=key: self._edit_custom_pair(k), f"custom_{key}")
        row.addWidget(custom)
        lock = _button("Закреплено" if key in self.draft.get("locks", []) else "Закрепить",
                       lambda checked=False, k=key: self._toggle_lock(k), f"lock_{key}")
        row.addWidget(lock)
        panel.addLayout(row)

    def _select_option(self, key, combo):
        option = combo.currentData()
        if option:
            self._set_field(key, option.get("ru", ""), option.get("en", ""))

    def _custom_field(self, key, text):
        if text != self._field_pair(key).get("ru", ""):
            self._set_field(key, text, "")

    def _edit_custom_pair(self, key):
        dialog = QDialog(self)
        dialog.setWindowTitle("Своё значение: " + FIELDS[key])
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        pair = self._field_pair(key)
        ru = QLineEdit(pair.get("ru", ""))
        en = QLineEdit(pair.get("en", ""))
        form.addRow("Русский", ru)
        form.addRow("English", en)
        dialog.composer_ru = ru
        dialog.composer_en = en
        layout.addLayout(form)
        layout.addWidget(QLabel("Неполную пару можно сохранить как черновик. Для готового EN нужен перевод."))
        translate = _button("Перевести с AI…", lambda: self.request_translation(ru.text(), "en", key, dialog))
        layout.addWidget(translate)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._set_field(key, ru.text(), en.text())
            self._render()

    def _toggle_lock(self, key):
        locks = list(self.draft.get("locks", []))
        if key in locks:
            locks.remove(key)
        else:
            locks.append(key)
        self._set_property("locks", locks)
        self._render()

    def _render_details(self, outer):
        panel = self._panel(outer, "Детали и атмосфера")
        actions = QHBoxLayout()
        actions.addStretch()
        randomize = _button("Случайные параметры", self.randomize_unlocked, "randomizeButton")
        randomize.setFixedWidth(320)
        randomize.setMinimumHeight(40)
        randomize.setStyleSheet(
            "QPushButton { background:#20ae9e; color:#071b20; "
            "border:1px solid #6df5e2; border-radius:6px; font-weight:700; }"
            "QPushButton:hover { background:#36c4b3; }"
            "QPushButton:pressed { background:#178f83; }"
        )
        actions.addWidget(randomize)
        actions.addStretch()
        panel.addLayout(actions)
        for key in ("location", "surface", "style", "lighting", "time"):
            self._field_editor(panel, key)

    def randomize_unlocked(self):
        if not self._guard_manual_rebuild():
            return
        keys = ("location", "surface", "style", "lighting", "time")
        keys += ("action", "camera", "duration", "aspect") if self.draft.get("mode") == "reels" else ("shot", "angle", "aspect")
        for key in keys:
            options = self._catalog.get("options", {}).get(key, [])
            if key in self.draft.get("locks", []) or not options:
                continue
            current = self._field_pair(key)
            alternatives = [o for o in options if (o.get("ru"), o.get("en")) != (current.get("ru"), current.get("en"))]
            if alternatives:
                option = random.choice(alternatives)
                self._set_field(key, option.get("ru", ""), option.get("en", ""))
        self._render()

    def _mode_selector(self, outer):
        modes = QHBoxLayout()
        modes.addStretch()
        for mode, label in (("image", "Изображение"), ("reels", "Рилс")):
            button = _button(("✓  " if self.draft.get("mode") == mode else "") + label,
                             lambda checked=False, m=mode: self._set_mode(m), f"mode_{mode}")
            button.setFixedWidth(190)
            button.setMinimumHeight(38)
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setChecked(self.draft.get("mode") == mode)
            button.setStyleSheet(
                "QPushButton { background:#25394a; color:#9aaebb; border:1px solid #496175; }"
                "QPushButton:checked { background:#20ae9e; color:#071b22; border:1px solid #6df5e2; font-weight:bold; }"
                "QPushButton:hover { border-color:#6df5e2; }"
            )
            modes.addWidget(button)
        modes.addStretch()
        outer.addLayout(modes)

    def _render_scene(self, outer):
        panel = self._panel(outer, "Сцена")
        keys = ("action", "camera", "duration", "aspect", "exclusions") if self.draft.get("mode") == "reels" else ("shot", "angle", "aspect", "exclusions")
        for key in keys:
            self._field_editor(panel, key)

    def _missing_translation(self):
        return [FIELDS.get(key, key) for key, pair in self.draft.get("fields", {}).items()
                if isinstance(pair, dict) and pair.get("ru", "").strip() and not pair.get("en", "").strip()]

    def generate_local(self):
        if not self._guard_manual_rebuild(clear=False):
            return False
        missing = self._missing_translation()
        if missing:
            self._show_message("Для английского промпта заполните перевод: " + ", ".join(missing))
            return False
        try:
            candidate = deepcopy(self.draft)
            candidate.update(manual_en=None, manual_ru=None, translation_stale=False)
            result = self.host.generate(candidate)
        except Exception as exc:
            self._error(exc)
            return False
        incoming = deepcopy(result.get("variants", []))
        if result.get("status") == "insufficient":
            self._show_message(result.get("reason") or "Закрепления допускают меньше семи разных вариантов.")
        if not incoming:
            return False
        self.draft.update(manual_en=None, manual_ru=None, translation_stale=False)
        self._variants = incoming
        self._variant_edits.clear()
        self._variant_index = 0
        self._set_dirty()
        if "next_seed" in result:
            self.draft["selection_seed"] = result["next_seed"]
        self._step = 4
        self._tab = "composer"
        self._render()
        return True

    def _active_variants(self):
        return self._proposal["variants"] if self._proposal else self._variants

    def _active_variant(self):
        variants = self._active_variants()
        index = self._proposal_index if self._proposal else self._variant_index
        return variants[index] if variants and 0 <= index < len(variants) else None

    def _render_results(self, outer):
        if self._proposal:
            label = "AI · предложения для просмотра"
        else:
            label = "Локальные варианты"
        outer.addWidget(QLabel(label))
        if self._proposal and self._proposal.get("status") == "insufficient":
            outer.addWidget(QLabel("Неполная подборка: " + str(self._proposal.get("reason") or "Модель предложила меньше семи вариантов.")))
        splitter = QSplitter(Qt.Orientation.Horizontal)
        list_widget = QListWidget()
        list_widget.setObjectName("variantList")
        list_widget.setWordWrap(True)
        list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for i, variant in enumerate(self._active_variants()):
            list_widget.addItem(f"{i + 1}. {variant.get('label', 'Вариант')}")
        selected = self._proposal_index if self._proposal else self._variant_index
        if list_widget.count():
            list_widget.setCurrentRow(selected)
        list_widget.currentRowChanged.connect(self._select_variant)
        splitter.addWidget(list_widget)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        variant = self._active_variant()
        if variant:
            heading = _label(variant.get("label", "Вариант"))
            heading.setStyleSheet("font-size:17px;font-weight:bold")
            right_layout.addWidget(heading)
            if not self._proposal:
                right_layout.addWidget(_button("★ В избранном" if self._favorite else "☆ В избранное",
                                               self._toggle_favorite, "favoriteButton"))
            source = "AI · предложение" if self._proposal else "Локально / сохранено"
            locked = ", ".join(FIELDS.get(k, k) for k in self.draft.get("locks", [])) or "нет"
            right_layout.addWidget(_label(f"{source}  ·  Закреплено: {locked}"))
            if self._proposal and self._proposal.get("stale"):
                right_layout.addWidget(QLabel("Черновик изменился после запроса. Откройте предложение отдельно."))
            warnings = variant.get("warnings") or []
            for warning in warnings:
                right_layout.addWidget(_label("Проверьте: " + str(warning)))
            langs = QHBoxLayout()
            langs.addWidget(_button("English · для генератора", lambda: self._change_language("en"), "languageEnButton"))
            langs.addWidget(_button("Русский вариант", lambda: self._change_language("ru"), "languageRuButton"))
            langs.addStretch()
            right_layout.addLayout(langs)
            text = QTextEdit()
            text.setObjectName("promptText")
            text.setReadOnly(True)
            text.setPlainText(self._variant_text(variant, self._language))
            right_layout.addWidget(text, 1)
            edit = self._variant_edits.get(self._variant_index, {})
            if (edit.get("translation_stale", variant.get("draft", {}).get("translation_stale")) and not self._proposal):
                right_layout.addWidget(QLabel("Другой язык требует обновления после ручной правки."))
            actions = QHBoxLayout()
            actions.addWidget(_button("Скопировать EN", lambda: self.copy_variant("en"), "copyEnButton"))
            actions.addWidget(_button("Скопировать RU", lambda: self.copy_variant("ru"), "copyRuButton"))
            if self._proposal:
                if self._proposal.get("stale"):
                    actions.addWidget(_button("Открыть отдельным черновиком", self.open_stale_proposal, "openStaleButton"))
                else:
                    actions.addWidget(_button("Принять вариант", self.accept_proposal, "acceptProposalButton"))
                actions.addWidget(_button("Отбросить", self.discard_proposal, "discardProposalButton"))
            else:
                actions.addWidget(_button("Изменить текст", self.edit_variant_text, "editTextButton"))
                actions.addWidget(_button("Обновить перевод с AI…", self.translate_active_text, "translateButton"))
                actions.addWidget(_button("Сохранить", self.save_current, "saveButton"))
                actions.addWidget(_button("Открыть в конструкторе", lambda: self.goto_step(2), "editParametersButton"))
            right_layout.addLayout(actions)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 2)
        outer.addWidget(splitter, 1)
        outer.addWidget(QLabel("Для референсов приложите файлы отдельно. Передача в генератор недоступна в текущем маршруте."))

    def _variant_text(self, variant, language):
        if self._proposal:
            return str(variant.get(language, ""))
        edit = self._variant_edits.get(self._variant_index, {})
        if edit.get(f"manual_{language}") is not None:
            return str(edit[f"manual_{language}"])
        snapshot = variant.get("draft", {})
        if snapshot.get(f"manual_{language}") is not None:
            return str(snapshot[f"manual_{language}"])
        return str(variant.get(language, ""))

    def _select_variant(self, index):
        if index < 0:
            return
        listing = self.scroll.widget().findChild(QListWidget, "variantList")
        restore_focus = listing is not None and listing.hasFocus()
        if self._proposal:
            self._proposal_index = index
        else:
            if self._variant_index != index:
                self._variant_index = index
                self._set_dirty()
        self._render()
        if restore_focus:
            self.scroll.widget().findChild(QListWidget, "variantList").setFocus()

    def _change_language(self, language):
        self._language = language
        self._render()

    def _toggle_favorite(self):
        self._favorite = not self._favorite
        self._set_dirty()
        self._render()

    def copy_variant(self, language="en"):
        variant = self._active_variant()
        if not variant:
            return False
        value = self._variant_text(variant, language)
        if not value:
            self._show_message("Текст на этом языке пока пуст.")
            return False
        QGuiApplication.clipboard().setText(value)
        self.status.setText("Текст скопирован. Референсы приложите отдельно.")
        return True

    def edit_variant_text(self):
        variant = self._active_variant()
        if not variant or self._proposal:
            return
        current = self._variant_text(variant, self._language)
        dialog = QDialog(self)
        dialog.setWindowTitle("Ручная правка текста")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Ручной текст может отличаться от сохранённых параметров."))
        editor = QTextEdit()
        editor.setPlainText(current)
        editor.setObjectName("manualPromptEditor")
        layout.addWidget(editor)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            edit = self._variant_edits.setdefault(self._variant_index, {})
            edit[f"manual_{self._language}"] = editor.toPlainText()
            edit["translation_stale"] = True
            self._set_dirty()
            self._render()

    def translate_active_text(self):
        variant = self._active_variant()
        if not variant or self._proposal:
            return False
        target = "ru" if self._language == "en" else "en"
        return self.request_translation(self._variant_text(variant, self._language), target)

    def _selected_draft(self):
        variant = self._variants[self._variant_index] if 0 <= self._variant_index < len(self._variants) else None
        if not variant or self._step < 4:
            return deepcopy(self.draft)
        selected = deepcopy(variant.get("draft") or self.draft)
        edit = self._variant_edits.get(self._variant_index, {})
        selected["base_en"] = variant.get("en", "")
        selected["base_ru"] = variant.get("ru", "")
        selected["manual_en"] = edit.get("manual_en", selected.get("manual_en"))
        selected["manual_ru"] = edit.get("manual_ru", selected.get("manual_ru"))
        selected["translation_stale"] = bool(edit.get("translation_stale", selected.get("translation_stale")))
        selected["references"] = deepcopy(self.draft.get("references", []))
        selected["profile_id"] = self.draft.get("profile_id")
        selected["revision"] = self.draft.get("revision", selected.get("revision", 1))
        return selected

    def save_current(self):
        draft = self._selected_draft()
        save_variant = self._active_variant()
        save_proposal = self._proposal
        save_record = self._saved_record
        save_step = self._step
        dialog = QDialog(self)
        dialog.setWindowTitle("Сохранить промпт")
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        default_label = (self._active_variant() or {}).get("label", "Новый промпт") if not self._proposal else "Новый промпт"
        name = QLineEdit(draft.get("name") or default_label)
        tags = QLineEdit(", ".join(self._saved_record.get("tags", [])) if self._saved_record else "")
        favorite = QCheckBox("Избранное")
        favorite.setChecked(self._favorite)
        form.addRow("Название", name)
        form.addRow("Теги", tags)
        form.addRow("", favorite)
        layout.addLayout(form)
        layout.addWidget(QLabel("Новая запись сохранит выбранный вариант, настройки и оба языка."))
        buttons = QDialogButtonBox()
        create = buttons.addButton("Сохранить как новый", QDialogButtonBox.ButtonRole.AcceptRole)
        replace = None
        if self._saved_record:
            replace = buttons.addButton("Заменить исходный…", QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        buttons.clicked.connect(lambda btn: dialog.done(2 if btn is replace else 1 if btn is create else 0))
        layout.addWidget(buttons)
        choice = dialog.exec()
        if choice == 0:
            return False
        if not name.text().strip():
            self._show_message("Введите название промпта.")
            return False
        metadata = {"name": name.text().strip(), "tags": [x.strip() for x in tags.text().split(",") if x.strip()],
                    "favorite": favorite.isChecked(), "kind": "prompt"}
        if self._saved_record and choice == 1:
            metadata["parent_id"] = self._saved_record["id"]
        try:
            if choice == 2 and self._saved_record:
                answer = QMessageBox.question(self, "Подтвердить замену", "Заменить сохранённую запись текущим вариантом?",
                                              QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:
                    return False
            if (self._step != save_step or self._active_variant() is not save_variant
                    or self._proposal is not save_proposal or self._saved_record is not save_record):
                self._show_message("Выбранный вариант изменился. Повторите сохранение.")
                return False
            # Modal dialogs dispatch AI callbacks. Take the content snapshot
            # after both dialogs so a newly received translation is saved too.
            draft = self._selected_draft()
            working_draft = deepcopy(self.draft)
            variant = self._active_variant() if not self._proposal and self._step == 4 else None
            metadata["source"] = variant.get("source", "local") if variant else "local"
            draft["name"] = metadata["name"]
            if choice == 2 and self._saved_record:
                record = self.host.save(draft, metadata, entry_id=self._saved_record["id"],
                                        expected_revision=self._saved_record["revision"])
            else:
                record = self.host.save(draft, metadata)
        except Exception as exc:
            self._error(exc)
            return False
        self._saved_record = deepcopy(record)
        self._favorite = bool(record.get("favorite"))
        self.draft = deepcopy(record.get("payload", draft))
        if self._step == 4 and not self._proposal and self._active_variant():
            self._variants[self._variant_index]["draft"] = deepcopy(self.draft)
            # The saved card is resolved; More 7 must continue the original
            # choice order and cursor rather than restart from that card.
            self.draft = working_draft
            self.draft["name"] = draft["name"]
            self._variant_edits.pop(self._variant_index, None)
        self._dirty = bool(self._variant_edits)
        self.status.setText("Промпт сохранён.")
        self._render()
        return True

    def new_draft(self):
        if not self._guard_dirty():
            return False
        self.cancel_ai()
        self.draft = deepcopy(self.host.new_draft())
        self._template_placeholder = None
        self._reset_start_path()
        self._saved_record = None
        self._favorite = False
        self._variants = []
        self._variant_edits.clear()
        self._proposal = None
        self._dirty = False
        self._step = 0
        self._tab = "composer"
        self._render()
        return True

    def _render_library(self, outer):
        try:
            self._library_rows = list(self.host.list_entries(kind="prompt"))
        except Exception as exc:
            self._error(exc)
            self._library_rows = []
        filters = QHBoxLayout()
        search = QLineEdit()
        search.setObjectName("librarySearch")
        search.setPlaceholderText("Поиск по названию, тегам и тексту")
        mode = QComboBox()
        mode.setObjectName("libraryModeFilter")
        mode.addItems(["Все типы", "Изображения", "Reels"])
        tag = QComboBox()
        tag.setObjectName("libraryTagFilter")
        tag.addItem("Все теги")
        for value in sorted({str(t) for row in self._library_rows for t in row.get("tags", [])}):
            tag.addItem(value)
        fav = QCheckBox("Избранное")
        fav.setObjectName("libraryFavoritesFilter")
        filters.addWidget(search, 3)
        filters.addWidget(mode)
        filters.addWidget(tag)
        filters.addWidget(fav)
        outer.addLayout(filters)
        results = QWidget()
        results.setObjectName("libraryResults")
        result_layout = QGridLayout(results)
        outer.addWidget(results)

        def refresh():
            self._clear_layout(result_layout)
            query = search.text().casefold().strip()
            count = 0
            for row in self._library_rows:
                payload = row.get("payload", {})
                if mode.currentIndex() == 1 and payload.get("mode") != "image":
                    continue
                if mode.currentIndex() == 2 and payload.get("mode") != "reels":
                    continue
                if tag.currentIndex() > 0 and tag.currentText() not in row.get("tags", []):
                    continue
                if fav.isChecked() and not row.get("favorite"):
                    continue
                haystack = " ".join((str(row.get("name", "")), str(row.get("description", "")), " ".join(row.get("tags", [])),
                                     str(payload.get("base_en", "")), str(payload.get("base_ru", "")),
                                     str(payload.get("manual_en", "")), str(payload.get("manual_ru", "")))).casefold()
                if query not in haystack:
                    continue
                card = QFrame()
                card.setProperty("panel", True)
                box = QVBoxLayout(card)
                box.addWidget(_label(("★ " if row.get("favorite") else "") + str(row.get("name", "Без названия"))))
                box.addWidget(QLabel("Reels" if payload.get("mode") == "reels" else "Изображение"))
                if row.get("description"):
                    box.addWidget(_label(row["description"]))
                box.addWidget(_label(", ".join(row.get("tags", []))))
                box.addWidget(_label(row.get("updated_at", "")))
                if row.get("error"):
                    box.addWidget(_label(row["error"]))
                actions = QHBoxLayout()
                open_button = _button("Открыть", lambda checked=False, r=row: self.open_entry(r["id"]))
                open_button.setEnabled(not bool(row.get("error")))
                actions.addWidget(open_button)
                actions.addWidget(_button("Переименовать", lambda checked=False, r=row: self.rename_entry(r)))
                actions.addWidget(_button("Удалить", lambda checked=False, r=row: self.delete_entry(r)))
                box.addLayout(actions)
                result_layout.addWidget(card, count // 2, count % 2)
                count += 1
            if not count:
                result_layout.addWidget(QLabel("Пока ничего не найдено. Создайте промпт или измените фильтры."), 0, 0)
        search.textChanged.connect(refresh)
        mode.currentIndexChanged.connect(refresh)
        tag.currentIndexChanged.connect(refresh)
        fav.toggled.connect(refresh)
        refresh()

    def open_entry(self, entry_id):
        if not self._guard_dirty():
            return False
        try:
            record = self.host.load(entry_id)
        except Exception as exc:
            self._error(exc)
            return False
        self.cancel_ai()
        self.draft = deepcopy(record["payload"])
        self._template_placeholder = None
        self._reset_start_path("custom")
        self._saved_record = deepcopy(record)
        self._favorite = bool(record.get("favorite"))
        self._dirty = False
        self._variants = [{"label": record.get("name", "Сохранённый промпт"), "draft": deepcopy(self.draft),
                           "en": self.draft.get("base_en", ""), "ru": self.draft.get("base_ru", ""), "source": record.get("source", "saved"), "warnings": []}]
        self._variant_index = 0
        self._variant_edits.clear()
        self._proposal = None
        self._step = 4
        self._tab = "composer"
        self._render()
        return True

    def rename_entry(self, row):
        name, accepted = QInputDialog.getText(self, "Переименовать", "Название", text=row.get("name", ""))
        if not accepted or not name.strip():
            return False
        try:
            record = self.host.load(row["id"])
            metadata = {"name": name.strip(), "tags": record.get("tags", []),
                        "favorite": record.get("favorite", False), "kind": "prompt",
                        "source": record.get("source", "saved")}
            payload = deepcopy(record["payload"])
            payload["name"] = name.strip()
            self.host.save(payload, metadata, entry_id=row["id"], expected_revision=row["revision"])
        except Exception as exc:
            self._error(exc)
            return False
        self._render()
        return True

    def delete_entry(self, row):
        answer = QMessageBox.question(self, "Удалить промпт?", f"Удалить «{row.get('name', '')}» из библиотеки?",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return False
        try:
            self.host.delete(row["id"], row["revision"])
        except Exception as exc:
            self._error(exc)
            return False
        self._render()
        return True

    def import_reference(self):
        if len(self.draft.get("references", [])) >= 5:
            self._show_message("Можно добавить до 5 референсов.")
            return False
        path, _ = QFileDialog.getOpenFileName(self, "Добавить референс", "", "Изображения (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return False
        try:
            asset = self.host.import_reference(path)
            from studio_asset_api import AssetHandle
            handle = AssetHandle.from_dict(asset).to_dict()
            if handle not in self.draft.setdefault("references", []):
                self.draft["references"].append(handle)
            self._set_dirty()
        except Exception as exc:
            self._error(exc)
            return False
        self._render()
        return True

    def _remove_reference(self, handle):
        refs = list(self.draft.get("references", []))
        if handle in refs:
            refs.remove(handle)
            self._set_property("references", refs)
            self._render()

    def choose_profile(self):
        try:
            profiles = self.host.list_entries(kind="profile")
        except Exception as exc:
            self._error(exc)
            return False
        if not profiles:
            self._show_message("Профилей пока нет.")
            return False
        labels = [p.get("name", p["id"]) for p in profiles]
        if len(set(labels)) != len(labels):
            labels = [f"{index + 1}. {label}" for index, label in enumerate(labels)]
        label, accepted = QInputDialog.getItem(self, "Выбрать профиль", "Профиль", labels, 0, False)
        if not accepted:
            return False
        selected = profiles[labels.index(label)]
        try:
            record = self.host.load(selected["id"])
        except Exception as exc:
            self._error(exc)
            return False
        snapshot = record.get("payload", {})
        profile_fields = {key: deepcopy(value) for key, value in snapshot.get("fields", {}).items()
                          if key in ("subject", "appearance", "wardrobe", "material", "color")}
        clashes = [key for key in self.draft.get("locks", []) if key in profile_fields
                   and profile_fields[key] != self.draft.get("fields", {}).get(key)]
        if clashes:
            self._show_message("Профиль конфликтует с закреплениями: " + ", ".join(FIELDS.get(k, k) for k in clashes))
            return False
        if not self._guard_manual_rebuild():
            return False
        self.draft["profile_id"] = record["id"]
        self._template_placeholder = None
        self.draft["fields"].update(profile_fields)
        if snapshot.get("subject_type"):
            self.draft["subject_type"] = snapshot["subject_type"]
        self.draft["references"] = deepcopy(snapshot.get("references", []))
        self.draft["selection_seed"] = 0
        self._set_dirty()
        self._render()
        return True

    def save_profile(self):
        name, accepted = QInputDialog.getText(self, "Сохранить профиль", "Название профиля")
        if not accepted or not name.strip():
            return False
        snapshot = deepcopy(self.draft)
        try:
            self.host.save(snapshot, {"name": name.strip(), "tags": [], "favorite": False, "kind": "profile"})
        except Exception as exc:
            self._error(exc)
            return False
        self.status.setText("Профиль сохранён.")
        return True

    def _ai_model(self):
        try:
            options = self.host.ai_options()
        except Exception as exc:
            self._error(exc)
            return None
        configured = [o for o in options if o.get("configured")]
        if not configured:
            self._show_message("AI не подключён. Локальные варианты доступны. Откройте настройки AI.")
            self.settings_requested.emit()
            return None
        labels = [o.get("label") or f"{o.get('provider')} / {o.get('model')}" for o in configured]
        if len(configured) == 1:
            return configured[0]
        label, accepted = QInputDialog.getItem(self, "Модель AI", "Провайдер и модель", labels, 0, False)
        return configured[labels.index(label)] if accepted else None

    def _quote_consent(self, quote, operation):
        price = quote.get("price")
        cost = "Стоимость неизвестна" if price is None else f"Оценка стоимости: ${price:.4f}. Это не предел списания."
        provider = quote.get("provider") or "AI"
        model = quote.get("model") or "модель"
        text = f"{operation}\n{provider} / {model}\n{cost}\nОтправить один платный запрос?"
        return QMessageBox.question(self, "Подтверждение AI", text,
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    def request_ai_variants(self):
        return self._request_ai("variants")

    def request_translation(self, text, target="en", key=None, parent_dialog=None):
        if not text.strip():
            self._show_message("Введите текст для перевода.")
            return False
        return self._request_ai("translation", text=text, target=target, field_key=key, parent_dialog=parent_dialog)

    def _show_unapplied_translation(self, translated, message):
        dialog = QDialog(self)
        dialog.setWindowTitle("Перевод прежнего черновика")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(message))
        editor = QTextEdit()
        editor.setPlainText(translated)
        editor.setReadOnly(True)
        layout.addWidget(editor)
        layout.addWidget(_button("Закрыть", dialog.accept))
        dialog.resize(620, 360)
        dialog.exec()

    def _request_ai(self, operation, text="", target="ru", field_key=None, parent_dialog=None):
        if self._ai_ticket is not None:
            self._show_message("AI-запрос уже выполняется.")
            return False
        if operation == "variants":
            missing = self._missing_translation()
            if missing:
                self._show_message("Заполните английский перевод: " + ", ".join(missing))
                return False
        model = self._ai_model()
        if not model:
            return False
        snapshot = self._selected_draft() if self._step == 4 and not self._proposal else deepcopy(self.draft)
        translation_index = self._variant_index
        field_target_text = None
        if field_key and parent_dialog is not None:
            try:
                target_editor = parent_dialog.composer_en if target == "en" else parent_dialog.composer_ru
                field_target_text = target_editor.text()
            except RuntimeError:
                return False
        if field_key:
            source_language = "ru" if target == "en" else "en"
            snapshot.setdefault("fields", {}).setdefault(field_key, {"ru": "", "en": ""})[source_language] = text
        fingerprint = self._fingerprint()
        self._ai_serial += 1
        serial = self._ai_serial
        self._ai_ticket = "quoting"
        self.status.setText("Получаем оценку AI-запроса…")

        def error(exc):
            if serial != self._ai_serial:
                return
            self._ai_ticket = None
            self._error(exc)

        def quoted(quote):
            if serial != self._ai_serial:
                return
            self._ai_ticket = "confirming"
            if not quote.get("configured", True):
                self._ai_ticket = None
                self._show_message("Выбранная модель не подключена. Проверьте настройки AI.")
                self.settings_requested.emit()
                return
            consent = self._quote_consent(quote, "Семь вариантов" if operation == "variants" else "Перевод текста")
            if serial != self._ai_serial:
                return
            if not consent:
                self._ai_ticket = None
                self.status.setText("AI-запрос отменён до отправки.")
                return
            if fingerprint != self._fingerprint():
                self._ai_ticket = None
                self._show_message("Черновик изменился до отправки. Повторите запрос для новых настроек.")
                return
            self._ai_ticket = "submitting"
            self.status.setText("AI-запрос выполняется…")

            def done(response):
                if serial != self._ai_serial:
                    return
                self._ai_ticket = None
                stale = fingerprint != self._fingerprint() or (operation == "translation" and not field_key and translation_index != self._variant_index)
                if operation == "variants":
                    if not response.get("variants"):
                        self._show_message(response.get("reason") or "AI не предложил вариантов.")
                        return
                    suggestions = deepcopy(response["variants"])
                    for suggestion in suggestions:
                        suggestion["source"] = "ai"
                    self._proposal = {"variants": suggestions,
                                      "status": response.get("status", "complete"),
                                      "reason": response.get("reason", ""),
                                      "snapshot": snapshot, "stale": stale}
                    self._proposal_index = 0
                    self._step = 4
                    self._tab = "composer"
                    self._render()
                elif stale:
                    self._show_unapplied_translation(str(response.get("text", "")),
                        "Черновик изменён. Можно скопировать полученный перевод; он не применён.")
                else:
                    translated = str(response.get("text", ""))
                    if field_key:
                        pair = snapshot["fields"][field_key]
                        if parent_dialog is not None:
                            try:
                                source_editor = parent_dialog.composer_ru if target == "en" else parent_dialog.composer_en
                                target_editor = parent_dialog.composer_en if target == "en" else parent_dialog.composer_ru
                                if (parent_dialog.isVisible() and source_editor.text() == text
                                        and target_editor.text() == field_target_text):
                                    target_editor.setText(translated)
                                else:
                                    self._show_unapplied_translation(translated,
                                        "Поле изменилось или окно закрыто. Можно скопировать перевод; он не применён.")
                            except RuntimeError:
                                self._show_unapplied_translation(translated,
                                    "Окно закрыто. Можно скопировать перевод; он не применён.")
                        else:
                            self._set_field(field_key, pair.get("ru", "") if target == "en" else translated,
                                            translated if target == "en" else pair.get("en", ""))
                    else:
                        edit = self._variant_edits.setdefault(self._variant_index, {})
                        edit[f"manual_{target}"] = translated
                        edit["translation_stale"] = False
                        self._set_dirty()
                    self._render()

            try:
                ticket = self.host.submit_ai(quote, done, error)
                if self._ai_ticket == "submitting":
                    self._ai_ticket = ticket
            except Exception as exc:
                error(exc)

        try:
            ticket = self.host.quote_ai(snapshot, quoted, error, operation=operation,
                                        provider=model.get("provider"), model=model.get("model"),
                                        text=text, target=target)
            if self._ai_ticket == "quoting":
                self._ai_ticket = ticket
        except Exception as exc:
            error(exc)
            return False
        return True

    def cancel_ai(self):
        ticket = self._ai_ticket
        self._ai_serial += 1
        self._ai_ticket = None
        if ticket is not None and hasattr(ticket, "cancel"):
            ticket.cancel()
        if ticket is not None:
            self.status.setText("AI-запрос отменён. Уже отправленный запрос мог быть оплачен.")
        else:
            self.status.clear()

    def accept_proposal(self):
        if not self._proposal or self._proposal.get("stale"):
            return False
        if not self._guard_manual_rebuild(clear=False):
            return False
        variant = self._active_variant()
        if not variant:
            return False
        self.draft = deepcopy(variant.get("draft") or self._proposal["snapshot"])
        self._template_placeholder = None
        self._reset_start_path("custom")
        self.draft["base_en"] = variant.get("en", "")
        self.draft["base_ru"] = variant.get("ru", "")
        self.draft["manual_en"] = None
        self.draft["manual_ru"] = None
        self._variants = [deepcopy(variant)]
        self._variant_edits.clear()
        self._variant_index = 0
        self._proposal = None
        self._saved_record = None
        self._favorite = False
        self._set_dirty()
        self._render()
        return True

    def open_stale_proposal(self):
        if not self._proposal or not self._proposal.get("stale"):
            return False
        if not self._guard_dirty("Сохранить текущие изменения перед открытием отдельного черновика?"):
            return False
        variant = self._active_variant()
        self.draft = deepcopy(variant.get("draft") or self._proposal["snapshot"])
        self._template_placeholder = None
        self._reset_start_path("custom")
        self.draft["base_en"] = variant.get("en", "")
        self.draft["base_ru"] = variant.get("ru", "")
        self.draft["manual_en"] = None
        self.draft["manual_ru"] = None
        self._variants = [deepcopy(variant)]
        self._variant_edits.clear()
        self._variant_index = 0
        self._saved_record = None
        self._favorite = False
        self._proposal = None
        self._set_dirty()
        self._render()
        return True

    def discard_proposal(self):
        self._proposal = None
        self._render()
