"""Eight-step automatic collections composed from existing planning and run services."""
from copy import deepcopy
import hashlib
import json
from datetime import datetime
from html import escape
from tempfile import TemporaryDirectory
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSizePolicy, QTabWidget, QVBoxLayout, QWidget,
)

from studio_clipart_builder_ui import ClipartBuilderDialog
from v3_components import ButtonVariant, V3Button
from studio_clipart_versions import restore_review, review_fields
from studio_clipart_objects import attach_reference_guidance, compile_objects, fill_recipe, validate_objects
from studio_clipart_recipe import ClipartRecipe, ROLES
from studio_bundle_planner import propose_bundle_plan
from studio_style_profiles import style_modifier_keys
from studio_workflow_host import workflow_host_for
from gpt25_recovery import expired_generation_retries
from v3_clipart_flow import (
    ClipartFlowController, ClipartGenerationPage, ClipartPromptReviewPage,
    ClipartReviewRunPage, estimate_clipart_cost,
    build_clipart_run_request,
)
from v3_project_state import ProjectMode, PromptEntry, PromptGeneratorData, StepId
from v3_provider_registry import (
    FAL_UPSCALE_MODEL_OPTIONS, KIE_MODEL_OPTIONS, processing_provider_options,
    CHROMA_KEY_COLOR_OPTIONS, CHROMA_SUBJECT_PROFILE_OPTIONS,
    upscale_model_preserves_alpha, normalize_fal_upscale_factor,
)


BRIEF_STEPS = (StepId.PROJECT, StepId.PROMPTS, StepId.PROMPT_REVIEW,
               StepId.GENERATION, StepId.PROCESSING_OPTIONS)


def _run_settings_fingerprint(request):
    return hashlib.sha256(json.dumps(
        {'work_dir': request.work_dir, 'settings': request.settings},
        sort_keys=True, ensure_ascii=False,
    ).encode('utf-8')).hexdigest()



def _plural_ru(count, one, few, many):
    count = abs(int(count))
    if count % 100 in range(11, 15):
        return many
    return one if count % 10 == 1 else few if count % 10 in (2, 3, 4) else many


PREVIOUS_RUNS_MAX_BYTES = 1024 * 1024


def launch_confirmation_html(*, object_count, models, cost, references=(), reference_model="",
                             expired_count=0, expired_providers=""):
    """Short, scannable confirmation text: one fact per line, key words in bold."""
    unit = _plural_ru(object_count, "объект", "объекта", "объектов")
    lines = [f"<b>Создать изображения: {object_count} {unit}?</b>", ""]
    lines.append(f"<b>{'Модель' if len(models) == 1 else 'Модели'}:</b> {escape(', '.join(models))}")
    requests = getattr(cost, "request_count", 0)
    lines.append(f"<b>Запросов:</b> {requests} (генерация {getattr(cost, 'generation_request_count', 0)}"
                 f", обработка {getattr(cost, 'processing_request_count', 0)})")
    if getattr(cost, "complete", False):
        lines.append(f"<b>Цена:</b> ориентировочно ${cost.estimated_usd:.3f}")
    else:
        from v3_flow_runtime import PROVIDER_DISPLAY_LABELS
        providers = ", ".join(PROVIDER_DISPLAY_LABELS.get(name, name)
                              for name in getattr(cost, "incomplete_providers", ())) or "выбранные провайдеры"
        lines.append(f"<b>Цена:</b> заранее неизвестна, платите по факту использования ({escape(providers)})")
    if references:
        lines.append("")
        lines.append(f"<b>Референсы ({len(references)}):</b> получит модель {escape(reference_model)}")
        lines.extend("• " + escape(Path(path).name) for path in sorted(references))
    if expired_count:
        lines.append("")
        lines.append(f"<b>Внимание:</b> прежние результаты для {expired_count} "
                     f"{_plural_ru(expired_count, 'объекта', 'объектов', 'объектов')} ({escape(expired_providers)}) "
                     "больше недоступны.")
        lines.append("Запуск = согласие на новую платную генерацию по текущему тарифу. "
                     "Успешные изображения заново не создаются.")
    return "<br>".join(lines)


class _TransparencyDialog(QDialog):
    """Esc and the window cross never throw away mask edits: with unsaved edits the window stays open."""

    editor = None

    def reject(self):
        editor = self.editor
        if editor is not None and editor._has_unsaved_changes():
            editor._show_contour_status("Есть несохранённые изменения: сохраните PNG или выйдите кнопкой «К результатам».")
            return
        super().reject()

class AutoClipartGenerationPage(ClipartGenerationPage):
    """Show only model controls that affect the current collection prompts."""
    show_primary_scope = True

    def __init__(self, state, changed):
        super().__init__(state, changed)
        self.primary_model_label = self.primary_controls_container.layout().labelForField(self.model_combo)
        self.reference_model_label = self.reference_controls_container.layout().labelForField(self.reference_model_combo)
        self.refresh_from_state()

    def refresh_from_state(self):
        super().refresh_from_state()
        text_count = sum(not entry.references for entry in self.data.prompts)
        reference_count = len(self.data.prompts) - text_count
        primary_form = self.primary_controls_container.layout()
        for control in (self.model_combo, self.ratio_combo, self.resolution_combo):
            control.setVisible(text_count > 0)
            primary_form.labelForField(control).setVisible(text_count > 0)
        self.primary_scope_label.setVisible(text_count > 0)
        self.model_capability_label.setVisible(text_count > 0)
        if self.show_ratio_preview:
            self.ratio_preview.setVisible(text_count > 0)
        self.primary_model_label.setText(f"Модель без референсов ({text_count})")
        self.reference_model_label.setText(f"Модель с референсами ({reference_count})")


class CollectionBrief(ClipartBuilderDialog):
    def __init__(self, state, changed, navigate):
        self.workflow_state = state
        self.changed = changed
        self.navigate_to = navigate
        super().__init__(state.data)
        self.setWindowFlags(Qt.WindowType.Widget)
        self.setMinimumSize(0, 0)
        self.heading.hide()
        self.back.hide()
        self.next.hide()
        self.layout().itemAt(self.layout().count() - 1).layout().itemAt(0).widget().hide()
        self.make_prompts.hide()
        self.planning.configure_automatic()
        self.reference_editor.set_compact_mode()
        self.palette_reference_button.hide()
        self.planning.send_references.show()
        self.planning.reference_images = lambda: tuple(
            ref['path'] for ref in self.reference_editor.value() if ref.get('enabled', True)
        ) if self.planning.send_references.isChecked() else ()
        self.planning.clear_reference_images = lambda: self.planning.send_references.setChecked(False)
        # One page, no scrolling: ideas list and fields are always visible (owner request 2026-10-20).
        self.object_editor.set_compact_mode()
        from v3_components import make_icon_button
        make_icon_button(self.planning.one_button, 'update', 'Заменить эту идею')
        self.object_editor.add_action(self.planning.one_button)
        self.planning.one_button.show()

        def fit_tabs(index):
            # The taller "Модель текста" page must not stretch the ideas page.
            tabs = self.planning.tabs
            for number in range(tabs.count()):
                # QTabWidget sizes itself to its tallest page; clamp the hidden pages to 0.
                tabs.widget(number).setMaximumHeight(16777215 if number == index else 0)
            tabs.updateGeometry()
            # Ideas tab: only as tall as its content (+ room for a wrapped status line).
            tabs.setMaximumHeight(
                tabs.tabBar().sizeHint().height() + tabs.widget(0).sizeHint().height() + 10
                if index == 0 else 16777215)
            self.object_editor.setVisible(index == 0)

        self.planning.tabs.currentChanged.connect(fit_tabs)
        fit_tabs(0)
        page_layout = self.pages.widget(4).widget().layout()
        page_layout.setSpacing(8)
        page_layout.setContentsMargins(2, 2, 2, 2)
        self.planning.layout().setContentsMargins(0, 0, 0, 0)
        self.planning.ideas_layout.setContentsMargins(6, 4, 6, 4)
        self.object_editor.layout().setContentsMargins(0, 0, 0, 0)
        self.pages.widget(4).setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.planning.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        # With the ideas list hidden ("Модель текста" tab) a bounded panel would be centred in the free height.
        page_layout.setAlignment(self.planning, Qt.AlignmentFlag.AlignTop)
        # No «Пропустить референсы» button (owner 2026-10-26): «Далее» moves on without references.
        reference_layout = self.pages.widget(2).widget().layout()
        reference_layout.insertWidget(0, QLabel("Референсы необязательны. Выбранные стиль и палитра сохраняются."))
        form = QFormLayout()
        self.project_name = QLineEdit(state.common.project_name)
        self.project_name.setMaxLength(200)
        self.directory = QLineEdit(state.common.work_dir)
        self.directory.setMaxLength(4000)
        choose = QPushButton("Выбрать папку")
        choose.clicked.connect(self._choose_directory)
        form.addRow("Название проекта", self.project_name)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.directory, 1)
        folder_row.addWidget(choose)
        form.addRow("Рабочая папка", folder_row)
        self.project_name.setPlaceholderText("Автоматический клипарт · " + datetime.now().strftime("%d.%m.%Y %H:%M"))
        self.pages.widget(0).widget().layout().insertLayout(0, form)
        self._applied_counts = dict(self.recipe.counts)
        # Total changes must affect the actual slots, including an existing plan.
        self.total.valueChanged.connect(self._suggest)

    def _reconcile_objects(self, counts):
        current = self.object_editor.value()
        inactive = deepcopy(self.workflow_state.data.automatic.get('inactive_objects', []))
        # New manually added objects use the editor's active ordinals. Preserve
        # both records if an inactive idea already used that number.
        ordinals = {item['ordinal'] for item in current}
        next_number = max([item['ordinal'] for item in current + inactive], default=0) + 1
        for item in inactive:
            if item['ordinal'] in ordinals:
                item['ordinal'] = next_number
                next_number += 1
            ordinals.add(item['ordinal'])
        candidates = validate_objects(current + inactive)
        remaining = dict(counts)
        active, unused = [], []
        for item in candidates:
            if remaining[item['role']] > 0:
                active.append(item)
                remaining[item['role']] -= 1
            else:
                unused.append(item)
        # Allocate new ordinals above inactive ideas as well, avoiding collisions
        # when those ideas are restored after a later increase.
        filled = fill_recipe(candidates, counts)
        existing_ids = {item['id'] for item in candidates}
        active.extend(item for item in filled if item['id'] not in existing_ids)
        active.sort(key=lambda item: item['ordinal'])
        if len(active) + len(unused) > 1000:
            raise ValueError('Допускается до 1000 объектов')
        if unused:
            self.workflow_state.data.automatic['inactive_objects'] = unused
        else:
            self.workflow_state.data.automatic.pop('inactive_objects', None)
        if current != active:
            self.object_editor.items = active
            self.object_editor.refresh()
        return active

    def _choose_directory(self):
        path = QFileDialog.getExistingDirectory(self, "Рабочая папка", self.directory.text())
        if path:
            self.directory.setText(path)

    def _go_to_references(self):
        self.navigate_to(StepId.PROMPT_REVIEW)

    def refresh_from_state(self):
        if self.workflow_state.current_step in BRIEF_STEPS:
            self.pages.setCurrentIndex(BRIEF_STEPS.index(self.workflow_state.current_step))

    def snapshot(self):
        if len(style_modifier_keys(self.mood.currentText())) > 2:
            raise ValueError('Выберите не более двух характеристик стиля')
        recipe = deepcopy(self.recipe)
        recipe.theme = self.theme.text().strip()
        recipe.context = self.context.currentText().strip()
        recipe.motifs = [value.strip() for value in self.motifs.text().split(",") if value.strip()]
        recipe.visual = self._visual_values()
        recipe.references = self.reference_editor.value()
        recipe.assistant = self.planning.selection()
        counts = {role: spin.value() for role, spin in self.counts.items()}
        objects = self.object_editor.value()
        object_counts = {role: sum(item['role'] == role for item in objects) for role in ROLES}
        if objects and counts == self._applied_counts and object_counts != counts:
            # Explicit manual add/remove/role edits still define the active plan.
            counts = object_counts
            for role, spin in self.counts.items():
                spin.blockSignals(True)
                spin.setValue(counts[role])
                spin.blockSignals(False)
            self._show_total()
            self.total.blockSignals(True)
            self.total.setValue(len(objects))
            self.total.blockSignals(False)
        recipe.edit_counts(counts)
        self.total.blockSignals(True)
        self.total.setValue(recipe.total)
        self.total.blockSignals(False)
        recipe.objects = self._reconcile_objects(counts) if self.object_editor.items else []
        self._applied_counts = dict(counts)
        if recipe.objects:
            recipe.bundle_plan = propose_bundle_plan(recipe.objects, existing=recipe.bundle_plan)
        recipe.validate()
        generator = PromptGeneratorData.from_dict(self.data.prompt_generator.to_dict())
        generator.style, generator.palette = self._effective_visual(recipe.references)
        generator.chroma_key_enabled = True
        if len(generator.style) > 4000:
            raise ValueError("Описание стиля слишком длинное: сократите его до 4000 символов")
        generator = PromptGeneratorData.from_dict(generator.to_dict())
        return recipe, generator


class AutoClipartFlowController(ClipartFlowController):
    module_id = "auto-clipart"
    collections_enabled = True

    def _ensure_delivery_operations(self):
        operations = self.shell.state.data.operations
        operations.trim = True
        operations.trim_mode = "alpha"
        operations.trim_padding_percent = 1
        operations.export_300_dpi = True

    def _install_pages(self):
        self._ensure_delivery_operations()
        self._flushing = False
        self.brief = CollectionBrief(self.shell.state, self.shell.mark_dirty, self._select_step)
        self.brief.planning.authorize = self.shell.authorize_run
        self.brief.planning.busy_changed.connect(self.shell.refresh)
        for step in BRIEF_STEPS:
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(0, 0, 0, 0)
            def refresh_brief(page=page):
                page.layout().addWidget(self.brief)
                self.brief.show()
                self.brief.refresh_from_state()
            page.refresh_from_state = refresh_brief
            self.pages.register_instance(step, page)

        self.launch_page = QTabWidget()
        self.prompt_page = ClipartPromptReviewPage(self.shell.state, self.shell.mark_dirty)
        self.prompt_page.progress_label.hide()
        self.generation_page = AutoClipartGenerationPage(self.shell.state, self.shell.mark_dirty)
        self._review_page = ClipartReviewRunPage(self.shell.state, fal_cost_refresh=self._refresh_fal_cost)
        self.launch_page.addTab(self.prompt_page, "Промпты")
        self.launch_page.addTab(self.generation_page, "Модель")
        self._review_page.setParent(self.launch_page)
        self._review_page.hide()
        self._install_upscale_controls()
        self._install_background_controls()
        self.launch_page.refresh_from_state = self._refresh_launch
        self.pages.register_instance(StepId.REVIEW_RUN, self.launch_page)
        self.pages.register_instance(StepId.RESULTS, self.run_queue.page)
        from studio_clipart_review_ui import ImageReview, review_supported
        self.review = ImageReview(self) if review_supported() else None
        if self.review is not None:
            self.review.install_results_page()
        self._install_recovery()
        # The separate export step owns collection delivery, not the result toolbar.
        self.run_queue.page.results_extension.export_action_label = ""
        # Here the toolbar button opens the PNG check before export (from it a file can be opened in
        # the transparency editor); the shared button keeps its editor-only meaning in other modules.
        check_button = self.run_queue.page.check_transparency_button
        check_button.clicked.disconnect()
        check_button.clicked.connect(self._open_png_check)
        check_button.setText("Проверка PNG")
        check_button.setToolTip("Просмотреть готовые PNG перед экспортом и при необходимости открыть проверку прозрачности")
        self.run_queue.page.refresh_from_state()
        self.export_page = QWidget()
        layout = QVBoxLayout(self.export_page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.export_panel = None
        self.export_empty = QLabel('Нет готовых PNG. Вернитесь к проверке результатов.')
        layout.addWidget(self.export_empty)
        self.export_page.refresh_from_state = self._refresh_export
        self.pages.register_instance(StepId.TRANSPARENCY, self.export_page)
        self.save_timer = QTimer(self.brief)
        self.save_timer.setInterval(800)
        self.save_timer.timeout.connect(self._autosave)
        self.save_timer.start()
        self._start_errors = None
        self.error.connect(self._collect_start_error)
        self._last_snapshot = None
        self._restore_prompt_references()
        self._restore_run()
        self.pages[self.shell.state.current_step].refresh_from_state()
        self.shell.refresh()

    @property
    def review_page(self):
        return self._review_page

    def is_busy(self):
        session = self.run_queue.session
        return bool((session and session.running) or self.brief.planning.pending is not None
                    or (self.export_panel is not None and self.export_panel.worker is not None))

    def _collect_start_error(self, message):
        if self._start_errors is not None:
            self._start_errors.append(message)

    def _autosave(self):
        try:
            active = self.shell.state.is_active
        except RuntimeError:
            # The workflow capability is gone (host shell released): nothing
            # left to save, and a live timer would raise on every tick.
            self.save_timer.stop()
            return
        if not active or self.is_busy():
            return
        try:
            before = self._last_snapshot
            self.flush()
            snapshot = (deepcopy(self.shell.state.data.to_dict()),
                        self.shell.state.common.project_name, self.shell.state.common.work_dir)
            if before != snapshot:
                self._last_snapshot = snapshot
                self.shell.mark_dirty()
        except (ValueError, OSError) as error:
            self.brief.error.setText(str(error)[:300])

    def flush(self):
        if getattr(self, "review", None) is not None:
            self.review.flush_save()
        if self._flushing or self.is_busy():
            return
        self._flushing = True
        try:
            recipe, generator = self.brief.snapshot()
            self.shell.state.data.recipe = recipe.to_dict()
            self.brief.recipe = recipe
            self.shell.state.data.prompt_generator = generator
            name = self.brief.project_name.text().strip()
            if not name:
                name = "Автоматический клипарт · " + datetime.now().strftime("%d.%m.%Y %H:%M")
                self.brief.project_name.setText(name)
            self.shell.state.common.project_name = name
            self.shell.state.common.work_dir = self.brief.directory.text().strip()
            self.shell.state.common.output_dir = str(Path(self.shell.state.common.work_dir) / "output")
        finally:
            self._flushing = False

    def _select_step(self, step):
        if self.is_busy():
            return
        self.flush()
        self.shell.state.set_step(step)
        self.shell.step_changed.emit(ProjectMode.CLIPART.value, step.value)
        self.shell.mark_dirty()

    def _refresh_launch(self):
        self._restore_prompt_references()
        self._refresh_upscale_controls()
        self._refresh_background_controls()
        for page in (self.prompt_page, self.generation_page, self._review_page):
            page.refresh_from_state()
        self._refresh_preflight()

    def _restore_prompt_references(self):
        # Older compiled plans kept attachments in the recipe only. The recipe
        # owns reference participation; manual prompt text remains untouched.
        references = list(self.brief.reference_editor.active_generation_paths())
        object_ids = {item['id'] for item in self.brief.object_editor.items}
        for prompt in self.shell.state.data.prompts:
            if prompt.object_id in object_ids:
                prompt.references = list(references)

    def _install_upscale_controls(self):
        panel = QWidget()
        form = QFormLayout(panel)
        self.upscale_provider = QComboBox()
        self.upscale_model = QComboBox()
        self.upscale_scale = QComboBox()
        for label, value in processing_provider_options("upscale_after_provider"):
            self.upscale_provider.addItem(label, value)
        form.addRow("Апскейл PNG", self.upscale_provider)
        form.addRow("Модель апскейла", self.upscale_model)
        form.addRow("Масштаб", self.upscale_scale)
        self.generation_page.add_widget(panel)
        self._refresh_upscale_controls()
        self.upscale_provider.currentIndexChanged.connect(self._upscale_provider_changed)
        self.upscale_model.currentIndexChanged.connect(self._upscale_model_changed)
        self.upscale_scale.currentIndexChanged.connect(self._upscale_scale_changed)

    def _install_background_controls(self):
        panel = QGroupBox("Прозрачный фон готового клипарта")
        form = QFormLayout(panel)
        self.background_color = QComboBox()
        self.background_color.setMaximumWidth(240)
        self.background_color.setAccessibleName("Цвет фона")
        for label, value in (("Авто", "auto"),) + CHROMA_KEY_COLOR_OPTIONS:
            self.background_color.addItem(label, value)
        self.subject_profile = QComboBox()
        self.subject_profile.setMaximumWidth(300)
        self.subject_profile.setAccessibleName("Тип изображения")
        for label, value in CHROMA_SUBJECT_PROFILE_OPTIONS:
            self.subject_profile.addItem(label, value)
        form.addRow("Цвет фона", self.background_color)
        form.addRow("Тип изображения", self.subject_profile)
        note = QLabel(
            "Для тюля и других полупрозрачных материалов выбирайте второй режим. "
            "Проверьте готовый PNG на разных подложках."
        )
        note.setWordWrap(True)
        note.setProperty("v3Subtitle", True)
        form.addRow("", note)
        self.generation_page.add_widget(panel)
        self._refresh_background_controls()
        self.background_color.currentIndexChanged.connect(self._background_control_changed)
        self.background_color.activated.connect(self._background_color_activated)
        self.subject_profile.currentIndexChanged.connect(self._background_control_changed)

    def _refresh_background_controls(self):
        operations = self.shell.state.data.operations
        for control, value in (
            (self.background_color, operations.chroma_key_color),
            (self.subject_profile, operations.chroma_subject_profile),
        ):
            blocked = control.blockSignals(True)
            control.setCurrentIndex(control.findData(value))
            control.blockSignals(blocked)

    def _background_control_changed(self):
        operations = self.shell.state.data.operations
        operations.chroma_key_color = self.background_color.currentData()
        operations.chroma_subject_profile = self.subject_profile.currentData()
        self.shell.mark_dirty()
        self._refresh_preflight()

    def _background_color_activated(self, *_):
        self.shell.state.data.operations.chroma_key_color_override = (
            self.background_color.currentData() != "auto"
        )
        self.shell.mark_dirty()
        self._refresh_preflight()

    def _upscale_fields(self):
        provider = self.shell.state.data.operations.upscale_after_provider
        return {
            "fal": ("fal_upscale_after_model", "fal_upscale_after_scale"),
            "kie": ("kie_upscale_after_model", "upscale_factor"),
            "local_realesrgan": ("local_realesrgan_profile", "local_realesrgan_after_scale"),
        }[provider]

    def _refresh_upscale_controls(self):
        operations = self.shell.state.data.operations
        provider = operations.upscale_after_provider
        model_field, scale_field = self._upscale_fields()
        options = (FAL_UPSCALE_MODEL_OPTIONS if provider == "fal" else
                   KIE_MODEL_OPTIONS if provider == "kie" else
                   (("Клипарт", "clipart"), ("Фото", "photo")))
        controls = (self.upscale_provider, self.upscale_model, self.upscale_scale)
        blocked = [control.blockSignals(True) for control in controls]
        try:
            self.upscale_provider.setCurrentIndex(self.upscale_provider.findData(provider))
            self.upscale_model.clear()
            for label, value in options:
                if upscale_model_preserves_alpha(provider, value):
                    self.upscale_model.addItem(label, value)
            model = getattr(operations, model_field)
            self.upscale_model.setCurrentIndex(self.upscale_model.findData(model))
            scales = sorted({normalize_fal_upscale_factor(model, scale) for scale in (2, 4)}) if provider == "fal" else (2, 4)
            self.upscale_scale.clear()
            for scale in scales:
                self.upscale_scale.addItem(f"{scale}x", scale)
            self.upscale_scale.setCurrentIndex(self.upscale_scale.findData(getattr(operations, scale_field)))
            self.upscale_scale.setEnabled(len(scales) > 1)
        finally:
            for control, previous in zip(controls, blocked):
                control.blockSignals(previous)

    def _upscale_provider_changed(self):
        if self.is_busy():
            self._refresh_upscale_controls()
            return
        self.shell.state.data.operations.upscale_after_provider = self.upscale_provider.currentData()
        self._upscale_changed()

    def _upscale_model_changed(self):
        if self.is_busy():
            self._refresh_upscale_controls()
            return
        operations = self.shell.state.data.operations
        model_field, scale_field = self._upscale_fields()
        model = self.upscale_model.currentData()
        if model is None:
            return
        setattr(operations, model_field, model)
        if operations.upscale_after_provider == "fal":
            setattr(operations, scale_field, normalize_fal_upscale_factor(model, getattr(operations, scale_field)))
        self._upscale_changed()

    def _upscale_scale_changed(self):
        if self.is_busy():
            self._refresh_upscale_controls()
            return
        scale = self.upscale_scale.currentData()
        if scale is None:
            return
        setattr(self.shell.state.data.operations, self._upscale_fields()[1], scale)
        self._upscale_changed()

    def _upscale_changed(self):
        self.shell.mark_dirty()
        self._refresh_launch()

    def _refresh_export(self):
        page = self.run_queue.page
        paths = page._export_paths()
        page._seed_bundle_membership()
        membership = self.shell.state.data.export_membership
        existing = self.export_panel
        if existing is not None and existing.worker is not None:
            return
        # An editor publishes new PNG bytes at the same path. Reusing the panel
        # must not also reuse a QC decision about the previous file.
        file_versions = []
        for path in paths:
            try:
                stat = Path(path).stat()
                file_versions.append((stat.st_ino, stat.st_size, stat.st_mtime_ns))
            except OSError:
                file_versions.append(None)
        review_issues = page._bundle_export_issues()
        if existing is not None and existing.paths == list(paths) \
                and existing.saved_membership == membership \
                and getattr(existing, '_file_versions', None) == file_versions \
                and getattr(existing, '_review_issues', None) == review_issues:
            return
        if existing is not None:
            existing._stop_png_check()
            existing.hide()
            self.export_page.layout().removeWidget(existing)
            existing.deleteLater()
            self.export_panel = None
        self.export_empty.hide()
        extension = page.results_extension
        if extension is None:
            return
        session = self.run_queue.session
        panel = extension.create_export_view(
            self.export_page, self.shell.state, paths,
            review_issues=review_issues,
            quality_reports=(),
            workspace=session.workspace_root if session is not None else None,
            embedded=True,
            quality_loader=lambda path: next(iter(page._alpha_qc_reports([path])), None),
            on_membership_saved=page._save_export_membership,
            on_fix_requested=page._request_quality_fix,
        )
        if panel is None:
            return
        panel._file_versions = file_versions
        panel._review_issues = review_issues
        self.export_page.layout().addWidget(panel, 1)
        self.export_panel = panel
        panel.busy_changed.connect(self.shell.refresh)
        panel.export_availability_changed.connect(lambda _enabled: self.shell.refresh())
        panel.review_requested.connect(lambda: self._select_step(StepId.RESULTS))
        if self.review is not None:
            panel.enable_marks(self.review.marks_by_path())
            panel.mark_requested.connect(self.review.mark_output)

    def navigate(self, direction):
        if self.is_busy():
            return
        step = self.shell.state.current_step
        route = (*BRIEF_STEPS, StepId.REVIEW_RUN, StepId.RESULTS, StepId.TRANSPARENCY)
        index = route.index(step)
        try:
            if direction < 0:
                if index == 6 and self.run_queue.session is not None:
                    if QMessageBox.question(self.run_queue.page, "Настройки набора",
                        "Вернуться к настройкам набора? Готовые результаты сохранятся в проекте.",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                        return
                if index:
                    self._select_step(route[index - 1])
                return
            if index == 0:
                if not self.brief.theme.text().strip():
                    raise ValueError("Укажите основную тему набора")
                if not Path(self.brief.directory.text()).is_dir():
                    raise ValueError("Выберите существующую рабочую папку")
                if self.brief.total.value() != self.brief.recipe.total:
                    self.brief._suggest()
            if index == 3:
                counts = {role: spin.value() for role, spin in self.brief.counts.items()}
                self.brief.recipe.edit_counts(counts)
                self.brief._reconcile_objects(counts)
            if index == 4:
                previous_session = None
                recipe, generator = self.brief.snapshot()
                if not recipe.objects or any(not item['name'].strip() for item in recipe.objects):
                    self.brief.planning.start(False)
                    return
                prompts = attach_reference_guidance(
                    compile_objects(recipe, generator),
                    self.brief.reference_editor.active_references(),
                )
                # Re-entering launch without editing the brief preserves manual prompt edits.
                fingerprint = hashlib.sha256(json.dumps(
                    [recipe.to_dict(), generator.to_dict()], sort_keys=True,
                    ensure_ascii=False).encode("utf-8")).hexdigest()
                if fingerprint != self.shell.state.data.automatic.get("compiled"):
                    if self.run_queue.session is not None:
                        if QMessageBox.question(self.brief, "Изменение набора",
                            "Состав изменён. Начать новый запуск? Предыдущие результаты сохранятся в проекте.",
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                            QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                            return
                        self._archive_run()
                        previous_session = self.run_queue.session
                        self.run_queue.reset_for_new_workflow()
                        self.shell.state.data.automatic.pop("run", None)
                        self.shell.state.data.automatic.pop('run_settings_fingerprint', None)
                    self.shell.state.data.prompts = prompts
                    self.shell.state.data.automatic["compiled"] = fingerprint
                operations = self.shell.state.data.operations
                operations.upscale_before = False
                operations.upscale_after = True
                operations.remove_background = True
                operations.remove_background_provider = "local_chroma_key"
                self._ensure_delivery_operations()
                if previous_session is not None:
                    if self._reuse_completed_run(previous_session):
                        self._select_step(StepId.RESULTS)
                        return
            if index == 5:
                self.flush()
                self._refresh_launch()
                cost = estimate_clipart_cost(self.shell.state)
                prepared = build_clipart_run_request(self.shell.state)
                references = {path for entry in prepared.generated_prompts for path in entry['references']}
                snapshots = self.brief.reference_editor.generation_reference_snapshot(references)
                models = sorted({prepared.settings.get(
                    'reference_generation_model' if entry['references'] else 'text_generation_model', ''
                ) for entry in prepared.generated_prompts})
                expired_retries: tuple[str, ...] = ()
                try:
                    expired_retries = expired_generation_retries(
                        prepared.work_dir, prepared.settings, prepared.generated_prompts,
                        project_id=getattr(self.shell, 'project_id', None),
                    )
                except (OSError, ValueError):
                    expired_retries = ()
                provider_names = ''
                if expired_retries:
                    from v3_flow_runtime import PROVIDER_DISPLAY_LABELS
                    provider_names = ', '.join(sorted(
                        PROVIDER_DISPLAY_LABELS.get(exhausted.split(':', 1)[0], exhausted.split(':', 1)[0])
                        for exhausted in expired_retries))
                message = launch_confirmation_html(
                    object_count=len(self.shell.state.data.prompts), models=models, cost=cost,
                    references=references, reference_model=self.shell.state.data.generation.reference_model,
                    expired_count=len(expired_retries), expired_providers=provider_names)
                if QMessageBox.question(self.launch_page, "Подтвердить запуск", message,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                    self._reference_consent = (deepcopy(prepared), snapshots)
                    self._pre_approved_retries = expired_retries
                    self._start_errors = []
                    try:
                        request = self.start()
                    finally:
                        self._reference_consent = None
                        self._pre_approved_retries = None
                        failures, self._start_errors = self._start_errors, None
                    if request is None:
                        # The launch status label lives on a hidden page, so a refused
                        # start must be reported here or it looks like nothing happened.
                        QMessageBox.warning(self.launch_page, "Запуск не выполнен",
                            (failures[-1] if failures else "Запуск не начался. Проверьте настройки и повторите.")[:500])
                return
            if index == 7:
                if self.export_panel is not None:
                    self.export_panel._export()
                self.shell.mark_dirty()
                return
            self._select_step(route[index + 1])
        except (ValueError, OSError, RuntimeError) as error:
            QMessageBox.warning(self.brief, "Clipart", str(error)[:500])

    def _open_png_check(self):
        if self.is_busy() or self.run_queue.session is None or self.run_queue.session.running:
            return
        self._select_step(StepId.TRANSPARENCY)
        if self.export_panel is not None:
            self.export_panel._show_quality_review()

    def _open_transparency_editor(self, item_index):
        # Editing is a local dialog, not the eighth (export) workflow page.
        from v3_clipart_flow import ClipartTransparencyEditorPage
        from v3_run_queue import transparency_candidate_paths
        session = self.run_queue.session
        if session is None or session.running:
            return
        paths = transparency_candidate_paths(session)
        if not paths:
            return
        dialog = _TransparencyDialog(self.run_queue.page)
        dialog.setWindowTitle("Проверка PNG")
        dialog.setWindowFlags(
            dialog.windowFlags()
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        dialog.resize(1080, 720)
        layout = QVBoxLayout(dialog)
        editor = ClipartTransparencyEditorPage()
        dialog.editor = editor
        layout.addWidget(editor)
        selected = 0
        if 0 <= item_index < len(session.items):
            path = Path(session.items[item_index].output_path or "")
            if path in paths:
                selected = paths.index(path)
        editor.set_files(paths, selected_index=selected)
        if self.review is not None:
            self.review.attach_editor(editor, paths)
        editor.copy_saved.connect(self.run_queue.page.use_edited_output)
        editor.back_requested.connect(dialog.accept)
        try:
            dialog.exec()
        finally:
            if self.review is not None:
                self.review.detach_editor()
            dialog.deleteLater()

    def before_replace_outputs(self, indices, kind):
        """Run queue hook: keep current pictures as versions before re-creation."""
        if self.review is not None:
            self.review.before_replace_outputs(indices, kind)

    def start_processing_again(self):
        self.shell.state.data.automatic.pop("run", None)
        self._select_step(StepId.PROJECT)

    def create_worker_for_request(self, request):
        consent = getattr(self, '_reference_consent', None)
        self._reference_consent = None
        if consent is not None and request != consent[0]:
            raise ValueError('Настройки изменились. Подтвердите запуск заново')
        references = {path for entry in request.generated_prompts for path in entry['references']}
        if not references:
            run = deepcopy(request)
            run.settings['auto_clipart_sharp_fallback'] = True
            return super().create_worker_for_request(run)
        if consent is None:
            raise ValueError('Подтвердите запуск с выбранными референсами заново')
        directory = TemporaryDirectory(prefix='vibix-reference-')
        try:
            copies = {}
            for index, path in enumerate(sorted(references)):
                with open(path, 'rb') as source:
                    data = source.read(10 * 1024 * 1024 + 1)
                if len(data) > 10 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != consent[1][path]:
                    raise ValueError('Референс изменился. Подтвердите запуск заново')
                target = Path(directory.name) / f'{index}{Path(path).suffix.lower()}'
                target.write_bytes(data)
                copies[path] = str(target)
            run = deepcopy(request)
            run.settings['auto_clipart_sharp_fallback'] = True
            for entry in run.generated_prompts:
                entry['references'] = [copies[path] for path in entry['references']]
            worker = super().create_worker_for_request(run)
            worker.completed.connect(lambda *_: directory.cleanup())
            self._reference_run_directory = directory
            return worker
        except Exception:
            directory.cleanup()
            raise

    def _request_cost_line(self, request):
        """Estimate for exactly the prompts of this request, never the whole set."""
        fallback = 'Стоимость не рассчитана; запросы оплачиваются отдельно.'
        try:
            import copy
            ids = {entry.get('object_id') for entry in request.generated_prompts}
            data = copy.copy(self.shell.state.data)
            data.prompts = [entry for entry in self.shell.state.data.prompts if entry.object_id in ids]
            if not ids or None in ids or not data.prompts:
                return fallback
            from v3_image_generation_runtime import estimate_image_generation_cost
            return estimate_image_generation_cost(data).summary
        except Exception:
            return fallback

    def confirm_retry_request(self, request, *, regenerate=False, summary=None):
        self._reference_consent = None
        approved = deepcopy(request)
        if approved.mode == "mode2_process" and approved.selected_files:
            settings = approved.settings
            paid = any(settings.get(flag) and settings.get(provider, "kie") in {"kie", "fal", "photoroom"}
                       for flag, provider in (("upscale", "upscale_provider"),
                                              ("upscale_after", "upscale_after_provider"),
                                              ("remove_bg", "remove_bg_provider")))
            message = f"Продолжить обработку сохранённых PNG: {len(approved.selected_files)}?\n"
            message += "Повторной генерации изображений не будет.\n"
            message += ("Оставшиеся внешние этапы могут потребовать оплаты; стоимость не рассчитана."
                        if paid else "Обработка выполняется локально.")
            return (QMessageBox.question(self.run_queue.page, 'Продолжить обработку', message,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes
                    and request == approved)
        references = {path for entry in approved.generated_prompts for path in entry['references']}
        try:
            snapshots = self.brief.reference_editor.generation_reference_snapshot(references)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self.run_queue.page, 'Повтор запуска', str(error)[:500])
            return False
        models = {approved.settings.get('reference_generation_model' if entry['references']
                                       else 'text_generation_model', '')
                  for entry in approved.generated_prompts}
        session = self.run_queue.session
        continuing = bool(session and any(item.status.value == 'cancelled' for item in session.items))
        action = 'Продолжить незавершённые запросы' if continuing else 'Повторить неудачные запросы'
        if regenerate:
            action = 'Сгенерировать заново выбранные изображения'
        replaced = ('Текущие версии выбранных изображений сохранятся в истории версий.\n'
                    if callable(getattr(self, 'before_replace_outputs', None))
                    else 'Текущие версии выбранных изображений будут заменены новыми.\n')
        message = (
            f'{action}: {len(approved.generated_prompts)}?\n'
            + (replaced if regenerate else 'Успешные изображения не будут созданы заново.\n')
            + self._request_cost_line(approved) + '\n'
            'Модель: ' + ', '.join(sorted(models))
        )
        if summary is not None:
            message = (f'Пересоздать помеченные. Брак генерации — {len(approved.generated_prompts)}: '
                       'новая генерация, платно.\n' + self._request_cost_line(approved) + '\n'
                       'Модель: ' + ', '.join(sorted(models)) + '\n' + '\n'.join(summary))
        if references:
            message += '\nМодели будут переданы референсы:\n' + '\n'.join(
                Path(path).name for path in sorted(references))
        if QMessageBox.question(self.run_queue.page, 'Подтвердить повтор', message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return False
        try:
            if request != approved:
                raise ValueError('Настройки изменились. Подтвердите повтор заново')
            if self.brief.reference_editor.generation_reference_snapshot(references) != snapshots:
                raise ValueError('Референс изменился. Подтвердите повтор заново')
        except (OSError, ValueError) as error:
            QMessageBox.warning(self.run_queue.page, 'Повтор запуска', str(error)[:500])
            return False
        self._reference_consent = (approved, snapshots)
        return True

    def start(self):
        data = self.shell.state.data
        if not data.prompts or any(entry.result_kind != "clipart" or not entry.object_id for entry in data.prompts):
            self.review_page.set_run_status("Соберите промпты объектов на предыдущем шаге.", error=True)
            return None
        data.operations.upscale_before = False
        data.operations.upscale_after = True
        data.operations.remove_background = True
        data.operations.remove_background_provider = "local_chroma_key"
        self._ensure_delivery_operations()
        if self.run_queue.session is not None and not self.run_queue.session.running:
            self._archive_run()
        request = super().start()
        if request is not None:
            self.run_queue.session.changed.connect(self._save_run)
            self._save_run()
        return request

    def _archive_run(self):
        """Keep recorded outputs and paid-stage evidence before an explicit new run."""
        data = self.shell.state.data
        saved = data.automatic.get('run')
        if not saved:
            return
        history = deepcopy(data.automatic.get('previous_runs', []))
        session = self.run_queue.session
        recorded_prompts = (
            [PromptEntry.from_value(item.payload).to_dict() for item in session.items]
            if session is not None else [prompt.to_dict() for prompt in data.prompts]
        )
        entry = {'prompts': recorded_prompts, 'run': deepcopy(saved)}
        if data.automatic.get('run_settings_fingerprint'):
            entry['settings_fingerprint'] = data.automatic['run_settings_fingerprint']
        if history and history[-1] == entry:
            return
        history.append(entry)
        # The history is write-only evidence inside a size-limited project file: the
        # oldest archives yield first, otherwise every later save would be refused.
        while len(history) > 1 and (
                len(history) > 100
                or len(json.dumps(history, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
                > PREVIOUS_RUNS_MAX_BYTES):
            history.pop(0)
        data.automatic['previous_runs'] = history

    def _reuse_completed_run(self, previous):
        """Reuse only verified unchanged local results, without submitting work."""
        from v3_run_queue import RunQueueSession, RunItemStatus
        request = build_clipart_run_request(self.shell.state)
        fingerprint = _run_settings_fingerprint(request)
        if getattr(previous, '_settings_fingerprint', None) != fingerprint:
            return
        session = RunQueueSession(request, ProjectMode.CLIPART)
        ready = set()
        # Apply the queue's existing final-output provenance/path checks.
        page = self.run_queue.page
        current = page.session
        try:
            page.session = previous
            ready = set(page._export_paths())
        finally:
            page.session = current
        reused = False
        for index, item in enumerate(session.items):
            candidates = [old for old in previous.items if old.payload == item.payload]
            if len(candidates) == 1:
                old = candidates[0]
                if old.status in {RunItemStatus.SUCCEEDED, RunItemStatus.FAILED, RunItemStatus.CANCELLED}:
                    retained = deepcopy(old)
                    retained.index, retained.display_name = item.index, item.display_name
                    if old.status is RunItemStatus.SUCCEEDED:
                        if not old.output_path or Path(old.output_path).resolve() not in ready:
                            retained.status = RunItemStatus.FAILED
                            retained.short_message = 'Сохранённый PNG недоступен. Проверьте файл результата.'
                        else:
                            reused = True
                    session.items[index] = retained
                    continue
            # New or changed ideas have not been submitted by this replan.
            item.status = RunItemStatus.CANCELLED
            item.attempts = 0
        if not reused:
            return
        session._settings_fingerprint = fingerprint
        session.handle_finished()
        self.run_queue.session = session
        page.set_session(session)
        session.changed.connect(self._save_run)
        self._save_run()
        return True

    def _save_run(self):
        session = self.run_queue.session
        if session is None:
            return
        if not hasattr(session, '_settings_fingerprint'):
            session._settings_fingerprint = _run_settings_fingerprint(session.request)
        if session._settings_fingerprint:
            self.shell.state.data.automatic['run_settings_fingerprint'] = session._settings_fingerprint
        else:
            self.shell.state.data.automatic.pop('run_settings_fingerprint', None)
        self.shell.state.data.automatic["run"] = [
            {"status": item.status.value, "output_path": item.output_path or "", "attempts": item.attempts,
             "editor_output_path": item.editor_output_path or "",
             "paid_completed_stages": list(item.paid_history_stages()),
             "stage_statuses": item.saved_stages(), "source_path": item.source_path or "",
             **review_fields(item)}
            for item in session.items
        ]
        self.shell.state_changed.emit()
        self.shell.refresh()

    # --- reconnect finished pictures that lie in the result folder (owner 2026-10-25) -------------------

    def _install_recovery(self):
        page = self.run_queue.page
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        self.recover_button = V3Button("Вернуть готовые файлы", ButtonVariant.PRIMARY)
        self.recover_button.setToolTip(
            "Подключить PNG, которые уже лежат в папке результата, к этому набору. "
            "Новая генерация не запускается, платных запросов нет.")
        self.recover_button.clicked.connect(self.recover_results)
        row_layout.addWidget(self.recover_button)
        row_layout.addStretch(1)
        row.hide()
        page.action_bar.layout().insertWidget(0, row)
        self.recover_row = row
        previous = getattr(page, "review_refresh", None)

        def refresh():
            if previous is not None:
                previous()
            self._refresh_recovery()
        page.review_refresh = refresh

    def _recoverable_outputs(self):
        from studio_clipart_recovery import recoverable
        from v3_run_queue import RunItemStatus
        session = self.run_queue.session
        if session is None or session.running:
            return {}
        prompts = [PromptEntry.from_value(item.payload).to_dict() for item in session.items]
        return recoverable(
            session.items, prompts, self.shell.state.data.automatic.get("previous_runs", []),
            session.output_dir, is_done=lambda item: item.status is RunItemStatus.SUCCEEDED and bool(item.output_path))

    def _refresh_recovery(self):
        found = self._recoverable_outputs() if hasattr(self, "recover_row") else {}
        self.recover_row.setVisible(bool(found))
        if found:
            self.recover_button.setText(f"Вернуть готовые файлы ({len(found)})")

    def recover_results(self):
        session = self.run_queue.session
        found = self._recoverable_outputs()
        if session is None or not found or self.is_busy():
            return
        page = self.run_queue.page
        if QMessageBox.question(
                page, "Вернуть готовые файлы",
                f"В папке результата найдено готовых PNG: {len(found)}.\n\nПодключить их к набору? "
                "Новая генерация не запускается, платных запросов нет, файлы не изменяются.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes) != QMessageBox.StandardButton.Yes:
            return
        from v3_run_queue import RunItemStatus
        for index, path in found.items():
            item = session.items[index]
            item.status = RunItemStatus.SUCCEEDED
            item.output_path = str(path)
            item.editor_output_path = ""
            item.attempts = max(1, item.attempts)
            item.short_message = "Файл найден в папке результата."
            item.review_mark, item.review_checked = "ok", False
        session.changed.emit()
        self._save_run()
        page.refresh_from_state()

    def _restore_run(self):
        self._ensure_delivery_operations()
        saved = self.shell.state.data.automatic.get("run")
        if not saved:
            return
        from v3_run_queue import RunQueueSession, RunItemStatus
        session = RunQueueSession(build_clipart_run_request(self.shell.state), ProjectMode.CLIPART)
        # Legacy runs did not record their settings. Rebuilding a request from
        # today's settings cannot prove that an older paid result used them.
        session._settings_fingerprint = self.shell.state.data.automatic.get('run_settings_fingerprint')
        if len(saved) != len(session.items):
            raise ValueError("Сохранённые результаты не соответствуют составу набора")
        for item, row in zip(session.items, saved):
            status = RunItemStatus(row["status"])
            item.status = status if status in {RunItemStatus.SUCCEEDED, RunItemStatus.CANCELLED} else RunItemStatus.FAILED
            item.output_path = row["output_path"] or None
            item.editor_output_path = row.get("editor_output_path", "")
            item.source_path = row.get("source_path", "")
            item.attempts = row["attempts"]
            item.stage_statuses = dict(row.get("stage_statuses", {}))
            item.paid_completed_stages = tuple(row.get("paid_completed_stages", ()))
            restore_review(item, row)
            if item.status is RunItemStatus.FAILED:
                item.short_message = (
                    "Файл сохранён для коррекции. Обработка не завершена; файл не готов к экспорту."
                    if item.output_path or item.source_path else
                    "Запуск был прерван. Повтор может потребовать оплаты."
                )
            elif item.status is RunItemStatus.CANCELLED:
                item.short_message = (
                    'Операция прервана пользователем.'
                    if item.output_path or item.source_path or item.paid_completed_stages
                    else 'Не выполнялся после остановки.'
                )
        session.handle_finished()
        self.run_queue.session = session
        self.run_queue.page.set_session(session)
        session.changed.connect(self._save_run)


def install_auto_clipart_flow(host):
    host = workflow_host_for(host, "auto-clipart")
    existing = host.workflow_controller("auto-clipart")
    if existing is not None:
        return existing
    controller = AutoClipartFlowController(host)
    host.register_workflow_controller("auto-clipart", controller)
    return controller
