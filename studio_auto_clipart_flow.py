"""Eight-step automatic collections composed from existing planning and run services."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFormLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from studio_clipart_builder_ui import ClipartBuilderDialog
from studio_clipart_objects import compile_objects, fill_recipe
from studio_clipart_recipe import ClipartRecipe, ROLES
from studio_bundle_planner import propose_bundle_plan
from studio_style_profiles import style_prompt_text
from studio_workflow_host import workflow_host_for
from v3_clipart_flow import (
    ClipartFlowController, ClipartGenerationPage, ClipartPromptReviewPage,
    ClipartReviewRunPage, estimate_clipart_cost,
    build_clipart_run_request,
)
from v3_project_state import ProjectMode, PromptGeneratorData, StepId
from v3_provider_registry import (
    FAL_UPSCALE_MODEL_OPTIONS, KIE_MODEL_OPTIONS, processing_provider_options,
    upscale_model_preserves_alpha, normalize_fal_upscale_factor,
)


BRIEF_STEPS = (StepId.PROJECT, StepId.PROMPTS, StepId.PROMPT_REVIEW,
               StepId.GENERATION, StepId.PROCESSING_OPTIONS)


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
        form = QFormLayout()
        self.project_name = QLineEdit(state.common.project_name)
        self.project_name.setMaxLength(200)
        self.directory = QLineEdit(state.common.work_dir)
        self.directory.setMaxLength(4000)
        choose = QPushButton("Выбрать папку")
        choose.clicked.connect(self._choose_directory)
        form.addRow("Название проекта", self.project_name)
        form.addRow("Рабочая папка", self.directory)
        form.addRow("", choose)
        self.pages.widget(0).widget().layout().insertLayout(0, form)

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
        recipe = deepcopy(self.recipe)
        recipe.theme = self.theme.text().strip()
        recipe.context = self.context.currentText().strip()
        recipe.motifs = [value.strip() for value in self.motifs.text().split(",") if value.strip()]
        recipe.visual = {key: widget.currentText().strip() for key, widget in self.visual_fields.items()}
        recipe.references = self.reference_editor.value()
        recipe.objects = self.object_editor.value()
        recipe.assistant = self.planning.selection()
        counts = {role: spin.value() for role, spin in self.counts.items()}
        if recipe.objects:
            counts = {role: sum(item["role"] == role for item in recipe.objects) for role in ROLES}
        recipe.edit_counts(counts)
        if recipe.objects:
            recipe.bundle_plan = propose_bundle_plan(recipe.objects, existing=recipe.bundle_plan)
        recipe.validate()
        generator = PromptGeneratorData.from_dict(self.data.prompt_generator.to_dict())
        generator.style = "; ".join(filter(None, (
            style_prompt_text(self.technique.currentText(), self.mood.currentText()),
            self.line.currentText().strip(), self.material.currentText().strip(),
            self.detail.currentText().strip(),
        )))
        generator.palette = self.palette.text().strip()
        generator.chroma_key_enabled = True
        if len(generator.style) > 4000:
            raise ValueError("Описание стиля слишком длинное: сократите его до 4000 символов")
        generator = PromptGeneratorData.from_dict(generator.to_dict())
        return recipe, generator


class AutoClipartFlowController(ClipartFlowController):
    module_id = "auto-clipart"
    collections_enabled = True

    def _install_pages(self):
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
        self.generation_page = ClipartGenerationPage(self.shell.state, self.shell.mark_dirty)
        self._review_page = ClipartReviewRunPage(self.shell.state, fal_cost_refresh=self._refresh_fal_cost)
        self.launch_page.addTab(self.prompt_page, "Промпты")
        self.launch_page.addTab(self.generation_page, "Модель")
        self.launch_page.addTab(self._review_page, "Проверка и стоимость")
        self._install_upscale_controls()
        self.launch_page.refresh_from_state = self._refresh_launch
        self.pages.register_instance(StepId.REVIEW_RUN, self.launch_page)
        self.pages.register_instance(StepId.RESULTS, self.run_queue.page)
        # The separate export step owns collection delivery, not the result toolbar.
        self.run_queue.page.results_extension.export_action_label = ""
        self.run_queue.page.refresh_from_state()
        self.export_page = QWidget()
        layout = QVBoxLayout(self.export_page)
        self.export_summary = QLabel()
        self.export_summary.setWordWrap(True)
        layout.addWidget(self.export_summary)
        self.export_sets = QTreeWidget()
        self.export_sets.setHeaderLabels(["Набор / изображение", "PNG"])
        self.export_sets.setColumnWidth(0, 540)
        layout.addWidget(self.export_sets, 1)
        self.export_page.refresh_from_state = self._refresh_export
        self.pages.register_instance(StepId.TRANSPARENCY, self.export_page)
        self.save_timer = QTimer(self.brief)
        self.save_timer.setInterval(800)
        self.save_timer.timeout.connect(self._autosave)
        self.save_timer.start()
        self._last_snapshot = None
        self._restore_run()
        self.pages[self.shell.state.current_step].refresh_from_state()
        self.shell.refresh()

    @property
    def review_page(self):
        return self._review_page

    def is_busy(self):
        session = self.run_queue.session
        return bool((session and session.running) or self.brief.planning.pending is not None)

    def _autosave(self):
        if not self.shell.state.is_active or self.is_busy():
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
        if self._flushing or self.is_busy():
            return
        self._flushing = True
        try:
            recipe, generator = self.brief.snapshot()
            self.shell.state.data.recipe = recipe.to_dict()
            self.brief.recipe = recipe
            self.shell.state.data.prompt_generator = generator
            self.shell.state.common.project_name = self.brief.project_name.text().strip()
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
        self._refresh_upscale_controls()
        for page in (self.prompt_page, self.generation_page, self._review_page):
            page.refresh_from_state()
        self._refresh_preflight()

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
        self.export_sets.clear()
        groups = {}
        membership = self.shell.state.data.export_membership
        for path in paths:
            for link in membership.get(str(path.resolve()), {}).get("memberships", []):
                if link["included"]:
                    group = groups.setdefault(link["set_id"], {"title": link["title"], "paths": []})
                    group["paths"].append(path)
        for group in groups.values():
            row = QTreeWidgetItem([group["title"], str(len(group["paths"]))])
            self.export_sets.addTopLevelItem(row)
            for path in group["paths"]:
                row.addChild(QTreeWidgetItem([path.name, "1"]))
        self.export_summary.setText(
            f"Готовых изображений: {len(paths)}\nPNG, обзорный лист, PDF Letter и ZIP для каждого набора."
            if paths else "Нет готовых изображений для экспорта. Вернитесь к проверке результатов."
        )

    def navigate(self, direction):
        if self.is_busy():
            return
        step = self.shell.state.current_step
        route = (*BRIEF_STEPS, StepId.REVIEW_RUN, StepId.RESULTS, StepId.TRANSPARENCY)
        index = route.index(step)
        try:
            if direction < 0:
                if index == 6 and self.run_queue.session is not None:
                    if QMessageBox.question(self.run_queue.page, "Новый запуск",
                        "Вернуться к настройке нового запуска? Текущие результаты останутся на диске; экспортируйте набор перед продолжением.",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                        return
                    self.run_queue.reset_for_new_workflow()
                    self.shell.state.data.automatic.pop("run", None)
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
                self.brief.object_editor.items = fill_recipe(self.brief.object_editor.value(), counts)
                self.brief.object_editor.refresh()
            if index == 4:
                recipe, generator = self.brief.snapshot()
                prompts = compile_objects(recipe, generator)
                # Re-entering launch without editing the brief preserves manual prompt edits.
                fingerprint = hashlib.sha256(json.dumps(
                    [recipe.to_dict(), generator.to_dict()], sort_keys=True,
                    ensure_ascii=False).encode("utf-8")).hexdigest()
                if fingerprint != self.shell.state.data.automatic.get("compiled"):
                    if self.run_queue.session is not None:
                        if QMessageBox.question(self.brief, "Изменение набора",
                            "Состав изменён. Начать новый запуск? Старые файлы останутся на диске.",
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                            QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                            return
                        self.run_queue.reset_for_new_workflow()
                        self.shell.state.data.automatic.pop("run", None)
                    self.shell.state.data.prompts = prompts
                    self.shell.state.data.automatic["compiled"] = fingerprint
                operations = self.shell.state.data.operations
                operations.upscale_before = False
                operations.upscale_after = True
                operations.remove_background = True
                operations.remove_background_provider = "local_chroma_key"
            if index == 5:
                self.flush()
                self._refresh_launch()
                cost = estimate_clipart_cost(self.shell.state)
                message = f"Создать изображения для {len(self.shell.state.data.prompts)} объектов?\n{cost.summary}"
                if QMessageBox.question(self.launch_page, "Подтвердить запуск", message,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                    self.start()
                return
            if index == 7:
                self.run_queue.page._export_sets()
                self._refresh_export()
                self.shell.mark_dirty()
                return
            self._select_step(route[index + 1])
        except (ValueError, OSError, RuntimeError) as error:
            QMessageBox.warning(self.brief, "Clipart", str(error)[:500])

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
        dialog = QDialog(self.run_queue.page)
        dialog.setWindowTitle("Проверка PNG")
        dialog.resize(1080, 720)
        layout = QVBoxLayout(dialog)
        editor = ClipartTransparencyEditorPage()
        layout.addWidget(editor)
        selected = 0
        if 0 <= item_index < len(session.items):
            path = Path(session.items[item_index].output_path or "")
            if path in paths:
                selected = paths.index(path)
        editor.set_files(paths, selected_index=selected)
        editor.copy_saved.connect(self.run_queue.page.use_edited_output)
        editor.back_requested.connect(dialog.accept)
        dialog.exec()
        dialog.deleteLater()

    def start_processing_again(self):
        self.shell.state.data.automatic.pop("run", None)
        self._select_step(StepId.PROJECT)

    def start(self):
        data = self.shell.state.data
        if not data.prompts or any(entry.result_kind != "clipart" or not entry.object_id for entry in data.prompts):
            self.review_page.set_run_status("Соберите промпты объектов на предыдущем шаге.", error=True)
            return None
        data.operations.upscale_before = False
        data.operations.upscale_after = True
        data.operations.remove_background = True
        data.operations.remove_background_provider = "local_chroma_key"
        request = super().start()
        if request is not None:
            self.run_queue.session.changed.connect(self._save_run)
            self._save_run()
        return request

    def _save_run(self):
        session = self.run_queue.session
        if session is None:
            return
        self.shell.state.data.automatic["run"] = [
            {"status": item.status.value, "output_path": item.output_path or "", "attempts": item.attempts,
             "editor_output_path": item.editor_output_path or ""}
            for item in session.items
        ]
        self.shell.state_changed.emit()
        self.shell.refresh()

    def _restore_run(self):
        saved = self.shell.state.data.automatic.get("run")
        if not saved:
            return
        from v3_run_queue import RunQueueSession, RunItemStatus
        session = RunQueueSession(build_clipart_run_request(self.shell.state), ProjectMode.CLIPART)
        if len(saved) != len(session.items):
            raise ValueError("Сохранённые результаты не соответствуют составу набора")
        for item, row in zip(session.items, saved):
            status = RunItemStatus(row["status"])
            item.status = status if status is RunItemStatus.SUCCEEDED else RunItemStatus.FAILED
            item.output_path = row["output_path"] or None
            item.editor_output_path = row.get("editor_output_path", "")
            item.attempts = row["attempts"]
            if item.status is RunItemStatus.FAILED:
                item.short_message = "Запуск был прерван. Повтор может потребовать оплаты."
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
