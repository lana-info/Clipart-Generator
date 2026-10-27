"""Core shell composition for the separate automatic collection workflow."""
from v3_project_state import StepId
from v3_wizard import AppShell
from v3_components import V3Button, ButtonVariant
from PyQt6.QtWidgets import QLabel


AUTO_STEPS = (
    (StepId.PROJECT, "Идея"),
    (StepId.PROMPTS, "Визуальное направление"),
    (StepId.PROMPT_REVIEW, "Референсы"),
    (StepId.GENERATION, "Структура набора"),
    (StepId.PROCESSING_OPTIONS, "Объекты"),
    (StepId.REVIEW_RUN, "Промпты и запуск"),
    (StepId.RESULTS, "Проверка"),
    (StepId.TRANSPARENCY, "Экспорт"),
)


class AutoClipartShell(AppShell):
    module_id = "auto-clipart"

    def refresh(self):
        super().refresh()
        self.mode_label.setText("Автоматический клипарт")
        self.mode_label.setAccessibleName(self.mode_label.text())

    def _refresh_stepper(self):
        super()._refresh_stepper()
        index = self.state.route.index(self.state.current_step)
        for position, (label, (_step, title)) in enumerate(zip(self.step_labels, AUTO_STEPS)):
            marker = "●" if position == index else "✓" if position < index else "○"
            label.setText(f"{marker} {position + 1}. {title}")
            label.setAccessibleName(title)

    def _refresh_footer(self):
        index = self.state.route.index(self.state.current_step)
        controller = self.workflow_controller(self.module_id)
        busy = bool(controller and controller.is_busy())
        if not hasattr(self, 'save_project_button'):
            self.save_project_button = V3Button('Сохранить проект', ButtonVariant.SECONDARY)
            self.save_project_button.clicked.connect(self._save_export_project)
            self.footer.layout().insertWidget(self.footer.layout().indexOf(self.next_button), self.save_project_button)
            self.project_save_label = QLabel('')
            self.project_save_label.setProperty('v3Small', True)
            self.footer.layout().insertWidget(0, self.project_save_label)
        if not hasattr(self, 'sets_back_button'):
            self.sets_back_button = V3Button('← К наборам', ButtonVariant.SECONDARY)
            self.sets_back_button.clicked.connect(self._back_to_sets)
            self.footer.layout().insertWidget(0, self.sets_back_button)
        panel_now = getattr(controller, 'export_panel', None)
        self.sets_back_button.setVisible(
            index == 7 and panel_now is not None and panel_now.stack.currentWidget() is panel_now.quality_page)
        self.sets_back_button.setEnabled(not busy)
        self.save_project_button.setVisible(index == 7)
        self.save_project_button.setEnabled(bool(controller) and not busy)
        self.project_save_label.setVisible(index == 7)
        saved = not self.save_error_label.text() and self.receivers(self.state_changed) > 0
        self.project_save_label.setText('Проект сохранён' if saved else '')
        self.back_button.show()
        self.next_button.show()
        self.back_button.setEnabled(index > 0 and not busy)
        has_exports = bool(controller and controller.run_queue.page._export_paths()) if index == 7 else True
        panel = getattr(controller, 'export_panel', None)
        if index == 7 and panel is not None:
            has_exports = panel.export_button.isEnabled()
        self.next_button.setEnabled(not busy and has_exports)
        self.next_button.setText({5: "Создать изображения", 6: "К экспорту", 7: "Создать ZIP-наборы"}.get(index, "Далее"))
        self.next_button.setAccessibleName(self.next_button.text())
        self.change_mode_button.setEnabled(not busy)

    def _back_to_sets(self):
        controller = self.workflow_controller(self.module_id)
        panel = getattr(controller, 'export_panel', None)
        if panel is not None and not controller.is_busy():
            panel._show_summary()
            self.refresh()

    def _save_export_project(self):
        controller = self.workflow_controller(self.module_id)
        if controller is None or controller.is_busy():
            return
        # The existing project-save handler flushes and reports persistence errors.
        self.mark_dirty()

    def go_next(self):
        controller = self.workflow_controller(self.module_id)
        if controller:
            reviewing = self.state.current_step is StepId.REVIEW_RUN
            save_timer = getattr(controller, "save_timer", None)
            resume_autosave = bool(reviewing and save_timer is not None and save_timer.isActive())
            if resume_autosave:
                save_timer.stop()
            if reviewing:
                self._run_request_key = (self.state.mode, StepId.REVIEW_RUN)
            try:
                controller.navigate(1)
            finally:
                self._run_request_key = None
                if resume_autosave:
                    save_timer.start()
        return self.state.current_step

    def go_back(self):
        controller = self.workflow_controller(self.module_id)
        if controller:
            controller.navigate(-1)
        return self.state.current_step
