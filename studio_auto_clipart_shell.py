"""Core shell composition for the separate automatic collection workflow."""
from v3_project_state import StepId
from v3_wizard import AppShell


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
        self.mode_label.setText("Автоматический Clipart")
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
        self.back_button.show()
        self.next_button.show()
        self.back_button.setEnabled(index > 0 and not busy)
        has_exports = bool(controller and controller.run_queue.page._export_paths()) if index == 7 else True
        self.next_button.setEnabled(not busy and has_exports)
        self.next_button.setText({5: "Создать изображения", 6: "К экспорту", 7: "Экспортировать"}.get(index, "Далее"))
        self.next_button.setAccessibleName(self.next_button.text())
        self.change_mode_button.setEnabled(not busy)

    def go_next(self):
        controller = self.workflow_controller(self.module_id)
        if controller:
            if self.state.current_step is StepId.REVIEW_RUN:
                self._run_request_key = (self.state.mode, StepId.REVIEW_RUN)
            try:
                controller.navigate(1)
            finally:
                self._run_request_key = None
        return self.state.current_step

    def go_back(self):
        controller = self.workflow_controller(self.module_id)
        if controller:
            controller.navigate(-1)
        return self.state.current_step
