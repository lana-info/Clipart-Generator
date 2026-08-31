import ast
import csv
import os
import tempfile
import unittest
from dataclasses import fields as dataclass_fields
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QItemSelectionModel, QMimeData, QObject, QUrl, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QLabel,
    QMessageBox,
    QRadioButton,
)
from PIL import Image

import v3_clipart_flow
from chroma_key import chroma_key_prompt_block
from v3_clipart_flow import (
    MAX_CLIPART_REQUESTS,
    ClipartFlowError,
    ClipartProcessingPage,
    ClipartGenerationPage,
    ClipartProjectPage,
    ClipartPromptInputPage,
    ClipartPromptReviewPage,
    ClipartReviewRunPage,
    build_clipart_run_request,
    clipart_pipeline_steps,
    estimate_clipart_cost,
    export_prompt_csv,
    fal_endpoint_quantities,
    generation_model_options,
    install_clipart_flow,
    missing_runtime_requirements,
    parse_prompt_csv,
    _safe_runtime_error,
    apply_prompt_text_edit,
)
from v3_mode_selection import V3ApplicationView
from v3_project_state import (
    MAX_PROMPT_ENTRIES,
    ImageOperationData,
    ProjectMode,
    ProjectState,
    PromptEntry,
    StepId,
)
from v3_wizard import AppShell


class FakeWorker(QObject):
    progress = pyqtSignal(str)
    progress_value = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, **kwargs):
        super().__init__()
        self.kwargs = kwargs
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True
        self.started = False

    def isRunning(self):
        return self.started


class WorkerFactory:
    def __init__(self):
        self.workers = []

    def __call__(self, **kwargs):
        worker = FakeWorker(**kwargs)
        self.workers.append(worker)
        return worker


class FakeCsvDropEvent:
    def __init__(self, paths):
        self._mime = QMimeData()
        self._mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
        self.accepted = False

    def mimeData(self):
        return self._mime

    def acceptProposedAction(self):
        self.accepted = True

    def ignore(self):
        self.accepted = False


class V3ClipartFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_state(self, work_dir):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.common.project_name = "Ocean pack"
        state.common.work_dir = str(work_dir)
        reference_path = Path(work_dir) / "reference.png"
        Image.new("RGBA", (2, 2), (255, 255, 255, 255)).save(reference_path)
        state.clipart.prompts = [
            PromptEntry("Baby whale"),
            PromptEntry("Baby turtle", [str(reference_path)]),
        ]
        state.clipart.generation.model = "gpt-image-2"
        state.clipart.generation.variants = 2
        return state

    def test_batch_prompt_text_edits_preserve_references_and_order(self):
        entries = [
            PromptEntry("blue fox", ["one.png"]),
            PromptEntry("red fox", ["two.png"]),
        ]
        changed, matches = apply_prompt_text_edit(
            entries, rows=(0,), action="replace", find_text="fox", new_text="wolf"
        )
        self.assertEqual(matches, 1)
        self.assertEqual([entry.prompt for entry in changed], ["blue wolf", "red fox"])
        self.assertEqual([entry.references for entry in changed], [["one.png"], ["two.png"]])
        appended, matches = apply_prompt_text_edit(
            changed, rows=(0, 1), action="append", find_text="", new_text="isolated"
        )
        self.assertEqual(matches, 2)
        self.assertEqual(
            [entry.prompt for entry in appended],
            ["blue wolf\nisolated", "red fox\nisolated"],
        )

    def test_batch_prompt_text_edit_changes_only_noncontiguous_selected_rows(self):
        entries = [
            PromptEntry(f"Акварельный цветок {index}", [f"ref-{index}.png"])
            for index in range(20)
        ]
        rows = tuple(index for index in range(20) if index not in {1, 5, 12, 18, 19})

        changed, matches = apply_prompt_text_edit(
            entries,
            rows=rows,
            action="replace",
            find_text="цветок",
            new_text="букет",
        )

        self.assertEqual(matches, 15)
        self.assertEqual(changed[0].prompt, "Акварельный букет 0")
        self.assertEqual(changed[1].prompt, "Акварельный цветок 1")
        self.assertEqual(
            [entry.references for entry in changed],
            [[f"ref-{index}.png"] for index in range(20)],
        )

    def test_batch_prompt_text_edit_preserves_generated_chroma_suffix(self):
        chroma_suffix = chroma_key_prompt_block("blue", materials=("watercolor",))
        entries = [
            PromptEntry(
                "Blue flower on a clean background\n" + chroma_suffix,
                ["flower.png"],
            )
        ]

        changed, matches = apply_prompt_text_edit(
            entries,
            rows=(0,),
            action="replace",
            find_text="background",
            new_text="backdrop",
        )
        appended, appended_count = apply_prompt_text_edit(
            changed,
            rows=(0,),
            action="append",
            find_text="",
            new_text="Centered composition",
        )

        self.assertEqual(matches, 1)
        self.assertEqual(appended_count, 1)
        self.assertEqual(
            appended[0].prompt,
            "Blue flower on a clean backdrop\nCentered composition\n" + chroma_suffix,
        )
        self.assertEqual(appended[0].references, ["flower.png"])

    def test_batch_prompt_text_edit_reports_no_match_without_changing_entries(self):
        entries = [PromptEntry("Лиса"), PromptEntry("Заяц")]

        changed, matches = apply_prompt_text_edit(
            entries,
            rows=(0, 1),
            action="replace",
            find_text="медведь",
            new_text="волк",
        )

        self.assertEqual(matches, 0)
        self.assertEqual([entry.to_dict() for entry in changed], [entry.to_dict() for entry in entries])

    def test_application_view_installs_full_clipart_route_with_results(self):
        factory = WorkerFactory()
        view = V3ApplicationView(
            runtime_settings_provider=lambda: {"kie_api_key": "test-key"},
            worker_factory=factory,
        )
        view.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()
        self.app.processEvents()

        controller = view.shell.clipart_flow_controller
        self.assertEqual(set(controller.pages), set(view.shell.state.route))
        self.assertIsInstance(controller.pages[StepId.PROJECT], ClipartProjectPage)
        self.assertFalse(
            hasattr(controller.pages[StepId.PROJECT], "project_name_edit")
        )
        self.assertIsInstance(
            controller.pages[StepId.PROMPTS],
            ClipartPromptInputPage,
        )
        self.assertIsInstance(
            controller.pages[StepId.PROMPT_REVIEW],
            ClipartPromptReviewPage,
        )
        self.assertIsInstance(
            controller.pages[StepId.PROCESSING_OPTIONS],
            ClipartProcessingPage,
        )
        self.assertIsInstance(
            controller.pages[StepId.REVIEW_RUN],
            ClipartReviewRunPage,
        )

    def test_process_more_starts_clean_clipart_workflow_at_first_step(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompts = [PromptEntry("old prompt")]
        state.set_step(StepId.RESULTS)
        shell = AppShell(state)
        controller = install_clipart_flow(shell)

        controller.run_queue.process_more()
        self.app.processEvents()

        self.assertEqual(state.current_step, StepId.PROJECT)
        self.assertEqual(state.clipart.prompts, [])
        self.assertIs(shell.current_page, controller.pages[StepId.PROJECT])

    def test_project_and_prompt_data_survive_forward_and_back_navigation(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-flow-") as temp:
            state = ProjectState(mode=ProjectMode.CLIPART)
            shell = AppShell(state)
            controller = install_clipart_flow(
                shell,
                runtime_settings_provider=lambda: {"kie_api_key": "test-key"},
                worker_factory=WorkerFactory(),
            )
            project_page = controller.pages[StepId.PROJECT]
            project_page.work_dir_edit.setText(temp)
            self.assertEqual(shell.go_next(), StepId.PROMPTS)

            prompt_page = controller.pages[StepId.PROMPTS]
            prompt_page.paste_edit.setPlainText("Fox")
            prompt_page.add_prompt_button.click()
            prompt_page.paste_edit.setPlainText("Bear")
            prompt_page.add_prompt_button.click()
            self.assertEqual(shell.go_next(), StepId.PROMPT_REVIEW)

            review_page = controller.pages[StepId.PROMPT_REVIEW]
            review_page.table.item(0, 0).setText("Red fox")
            state.clipart.prompts[0].references = ["D:/fox.png"]
            review_page.refresh_from_state()
            self.assertEqual(shell.go_next(), StepId.GENERATION)
            self.assertEqual(shell.go_back(), StepId.PROMPT_REVIEW)
            self.assertEqual(shell.go_back(), StepId.PROMPTS)
            self.assertEqual(shell.go_back(), StepId.PROJECT)

            self.assertEqual(state.common.project_name, "")
            self.assertEqual(state.common.work_dir, temp)
            self.assertEqual(
                [entry.prompt for entry in state.clipart.prompts],
                ["Red fox", "Bear"],
            )
            self.assertEqual(
                state.clipart.prompts[0].references,
                ["D:/fox.png"],
            )

    def test_prompt_input_presents_three_clear_source_choices(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        shell = AppShell(state)
        controller = install_clipart_flow(shell, worker_factory=WorkerFactory())
        page = controller.pages[StepId.PROMPTS]

        self.assertEqual(
            [button.text() for button in page.source_buttons],
            [
                "Сгенерировать серию",
                "Вставить готовый промпт",
                "Импортировать CSV",
            ],
        )
        self.assertTrue(page.source_buttons[1].isChecked())
        self.assertEqual(page.source_stack.currentIndex(), 1)
        self.assertEqual(page.progress_label.text(), "Шаг 1 из 2 · Добавление промптов")

    def test_append_reports_prompt_limit_instead_of_silently_dropping_rows(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompts = [
            PromptEntry(f"Prompt {index}") for index in range(MAX_PROMPT_ENTRIES)
        ]
        page = ClipartPromptInputPage(state, lambda: None)
        page.paste_edit.setPlainText("One more prompt")

        page.add_prompt_button.click()

        self.assertEqual(len(state.clipart.prompts), MAX_PROMPT_ENTRIES)
        self.assertIn("Максимум", page.card.status_label.text())

    def test_prompt_review_uses_compact_icon_actions_with_tooltips(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompts = [PromptEntry("Fox")]
        page = ClipartPromptReviewPage(state, lambda: None)

        self.assertEqual(page.table.horizontalHeaderItem(1).text(), "Референсы")
        actions = (
            (page.add_button, "Добавить промпт"),
            (page.duplicate_button, "Дублировать выбранные промпты"),
            (page.delete_button, "Удалить выбранные промпты"),
            (page.delete_all_button, "Удалить все промпты"),
            (page.add_refs_button, "Добавить референсы"),
            (page.replace_refs_button, "Заменить референсы"),
            (page.delete_refs_button, "Удалить референсы"),
        )
        for button, label in actions:
            self.assertEqual(button.text(), "")
            self.assertEqual(button.toolTip(), label)
            self.assertEqual(button.accessibleName(), label)
            self.assertFalse(button.icon().isNull())
            self.assertLessEqual(button.maximumWidth(), 64)
        self.assertEqual(page.progress_label.text(), "Шаг 2 из 2 · Проверка серии")

    def test_prompt_review_separates_a_visible_csv_export_action(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompts = [PromptEntry("Fox")]
        page = ClipartPromptReviewPage(state, lambda: None)

        self.assertEqual(page.export_actions_label.text(), "Экспорт:")
        self.assertEqual(page.export_csv_button.text(), "CSV")
        self.assertEqual(page.export_csv_button.property("variant"), "primary")
        self.assertEqual(
            page.export_csv_button.toolTip(),
            "Экспортировать все строки в CSV",
        )
        self.assertEqual(
            page.export_csv_button.accessibleName(),
            "Экспортировать все строки в CSV",
        )

    def test_prompt_review_exposes_one_batch_editor_and_one_step_undo(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompts = [PromptEntry("Fox"), PromptEntry("Bear")]
        page = ClipartPromptReviewPage(state, lambda: None)

        self.assertTrue(hasattr(page, "batch_edit_button"))
        self.assertEqual(page.batch_edit_button.text(), "Найти и заменить")
        self.assertTrue(hasattr(page, "undo_batch_button"))
        self.assertFalse(page.undo_batch_button.isEnabled())

        page._apply_batch_result(
            [PromptEntry("Red fox"), PromptEntry("Brown bear")],
            affected_count=2,
        )
        self.assertEqual(
            [entry.prompt for entry in state.clipart.prompts],
            ["Red fox", "Brown bear"],
        )
        self.assertTrue(page.undo_batch_button.isEnabled())

        page.undo_batch_button.click()

        self.assertEqual(
            [entry.prompt for entry in state.clipart.prompts],
            ["Fox", "Bear"],
        )
        self.assertFalse(page.undo_batch_button.isEnabled())

    def test_prompt_review_drops_stale_batch_undo_after_a_later_manual_edit(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompts = [PromptEntry("Fox"), PromptEntry("Bear")]
        page = ClipartPromptReviewPage(state, lambda: None)
        page._apply_batch_result(
            [PromptEntry("Red fox"), PromptEntry("Bear")],
            affected_count=1,
        )

        page.table.item(1, 0).setText("Brown bear")

        self.assertEqual(
            [entry.prompt for entry in state.clipart.prompts],
            ["Red fox", "Brown bear"],
        )
        self.assertFalse(page.undo_batch_button.isEnabled())

    def test_batch_prompt_dialog_previews_selected_or_all_rows(self):
        if not hasattr(v3_clipart_flow, "PromptBatchEditDialog"):
            self.fail("Окно массового редактирования промптов не создано")
        entries = [PromptEntry(f"Blue flower {index}") for index in range(20)]
        selected_rows = tuple(range(0, 20, 2))
        dialog = v3_clipart_flow.PromptBatchEditDialog(
            entries,
            selected_rows=selected_rows,
        )

        self.assertTrue(dialog.selected_radio.isChecked())
        self.assertEqual(dialog.selected_radio.text(), "Выбранные (10)")
        self.assertEqual(dialog.all_radio.text(), "Все (20)")
        self.assertEqual(dialog.replace_radio.text(), "Заменить")
        self.assertEqual(dialog.prepend_radio.text(), "В начало")
        self.assertEqual(dialog.append_radio.text(), "В конец")
        self.assertNotIn(
            "Вставить после",
            [button.text() for button in dialog.findChildren(QRadioButton)],
        )

        dialog.find_edit.setText("flower")
        dialog.new_text_edit.setPlainText("bouquet")
        self.app.processEvents()

        self.assertEqual(dialog.affected_count(), 10)
        self.assertEqual(dialog.rows(), selected_rows)
        self.assertIn("Будет изменено: 10 из 10", dialog.summary_label.text())
        self.assertGreater(dialog.preview_list.count(), 0)
        self.assertLessEqual(dialog.preview_list.count(), 3)
        self.assertTrue(dialog.apply_button.isEnabled())

        dialog.all_radio.setChecked(True)
        self.app.processEvents()

        self.assertEqual(dialog.affected_count(), 20)
        self.assertEqual(dialog.rows(), tuple(range(20)))
        self.assertIn("Будет изменено: 20 из 20", dialog.summary_label.text())

    def test_batch_prompt_dialog_disables_apply_when_replace_has_no_matches(self):
        if not hasattr(v3_clipart_flow, "PromptBatchEditDialog"):
            self.fail("Окно массового редактирования промптов не создано")
        dialog = v3_clipart_flow.PromptBatchEditDialog(
            [PromptEntry("Fox"), PromptEntry("Bear")],
            selected_rows=(),
        )

        dialog.find_edit.setText("Rabbit")
        dialog.new_text_edit.setPlainText("Wolf")
        self.app.processEvents()

        self.assertTrue(dialog.all_radio.isChecked())
        self.assertEqual(dialog.affected_count(), 0)
        self.assertIn("Совпадений не найдено", dialog.summary_label.text())
        self.assertIn("строки: 1, 2", dialog.summary_label.text())
        self.assertFalse(dialog.apply_button.isEnabled())

    def test_batch_prompt_dialog_treats_replacing_text_with_itself_as_no_change(self):
        dialog = v3_clipart_flow.PromptBatchEditDialog(
            [PromptEntry("Blue flower")],
            selected_rows=(),
        )

        dialog.find_edit.setText("flower")
        dialog.new_text_edit.setPlainText("flower")
        self.app.processEvents()

        edited, affected = dialog.edited_entries()
        self.assertEqual(affected, 0)
        self.assertEqual(edited[0].prompt, "Blue flower")
        self.assertEqual(dialog.preview_list.count(), 0)
        self.assertFalse(dialog.apply_button.isEnabled())

    def test_batch_prompt_dialog_requires_text_for_start_or_end_actions(self):
        dialog = v3_clipart_flow.PromptBatchEditDialog(
            [PromptEntry("Fox")],
            selected_rows=(),
        )

        dialog.prepend_radio.setChecked(True)
        self.app.processEvents()

        self.assertTrue(dialog.find_edit.isHidden())
        self.assertIn("Введите текст", dialog.summary_label.text())
        self.assertFalse(dialog.apply_button.isEnabled())

        dialog.new_text_edit.setPlainText("Watercolor")
        self.app.processEvents()

        edited, affected = dialog.edited_entries()
        self.assertEqual(affected, 1)
        self.assertEqual(edited[0].prompt, "Watercolor\nFox")
        self.assertTrue(dialog.apply_button.isEnabled())

    def test_editing_prompt_text_preserves_reference_paths(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompts = [
            PromptEntry("Fox", ["D:/one.png", "D:/two.png"]),
        ]
        page = ClipartPromptReviewPage(state, lambda: None)

        page.table.item(0, 0).setText("Red fox")

        self.assertEqual(state.clipart.prompts[0].prompt, "Red fox")
        self.assertEqual(
            state.clipart.prompts[0].references,
            ["D:/one.png", "D:/two.png"],
        )

    def test_prompt_review_deletes_selected_rows_and_never_touches_reference_files(self):
        with tempfile.TemporaryDirectory(prefix="vibix-delete-prompts-") as temp:
            reference = Path(temp) / "reference.png"
            Image.new("RGBA", (2, 2), (255, 255, 255, 255)).save(reference)
            state = ProjectState(mode=ProjectMode.CLIPART)
            state.clipart.prompts = [
                PromptEntry("Fox", [str(reference)]),
                PromptEntry("Bear"),
                PromptEntry("Rabbit"),
            ]
            page = ClipartPromptReviewPage(state, lambda: None)
            selection = page.table.selectionModel()
            for row in (0, 2):
                selection.select(
                    page.table.model().index(row, 0),
                    QItemSelectionModel.SelectionFlag.Select
                    | QItemSelectionModel.SelectionFlag.Rows,
                )

            page.delete_button.click()

            self.assertEqual(
                [entry.prompt for entry in state.clipart.prompts],
                ["Bear"],
            )
            self.assertTrue(reference.is_file())

    def test_prompt_review_delete_all_requires_confirmation(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompts = [PromptEntry("Fox"), PromptEntry("Bear")]
        page = ClipartPromptReviewPage(state, lambda: None)

        self.assertEqual(page.delete_all_button.text(), "")
        self.assertEqual(page.delete_all_button.toolTip(), "Удалить все промпты")
        with patch.object(
            v3_clipart_flow.QMessageBox,
            "question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            page.delete_all_button.click()

        self.assertEqual(state.clipart.prompts, [])

    def test_review_keeps_two_thirds_prompt_and_one_third_references(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompts = [
            PromptEntry("Fox", ["D:/a-very-long-reference-file-name.png"]),
        ]
        page = ClipartPromptReviewPage(state, lambda: None)
        page.resize(632, 480)
        page.show()
        self.app.processEvents()

        total_width = page.table.columnWidth(0) + page.table.columnWidth(1)
        prompt_share = page.table.columnWidth(0) / total_width
        self.assertAlmostEqual(prompt_share, 2 / 3, delta=0.04)

        page.resize(1100, 600)
        self.app.processEvents()
        total_width = page.table.columnWidth(0) + page.table.columnWidth(1)
        prompt_share = page.table.columnWidth(0) / total_width
        self.assertAlmostEqual(prompt_share, 2 / 3, delta=0.04)

    def test_generator_page_creates_editable_prompt_entries(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        shell = AppShell(state)
        controller = install_clipart_flow(shell, worker_factory=WorkerFactory())
        page = controller.pages[StepId.PROMPTS]
        page.theme_edit.setText("Children's watercolor illustration")
        page.subjects_edit.setPlainText("Fox\nBear")
        page.variations_edit.setPlainText("Sitting with flowers\nSleeping")
        page.style_edit.setText("Soft watercolor")

        self.assertEqual(
            state.clipart.prompt_generator.theme,
            "Children's watercolor illustration",
        )
        self.assertEqual(state.clipart.prompt_generator.subjects, ["Fox", "Bear"])
        restored = ProjectState.from_dict(state.to_dict())
        self.assertEqual(
            restored.clipart.prompt_generator.variations,
            ["Sitting with flowers", "Sleeping"],
        )

        page.create_series_button.click()
        state.clipart.prompts[0].references = ["D:/fox.png"]
        generation_page = controller.pages[StepId.GENERATION]
        generation_page.refresh_from_state()
        self.assertFalse(hasattr(generation_page, "reference_advanced"))
        self.assertEqual(len(state.clipart.prompts), 4)
        self.assertNotIn("Series item", state.clipart.prompts[0].prompt)
        self.assertNotIn("Output intent", state.clipart.prompts[0].prompt)
        self.assertTrue(all(isinstance(item, PromptEntry) for item in state.clipart.prompts))
        state.clipart.prompts[0].prompt = "Manual edit"
        self.assertEqual(state.clipart.prompts[0].prompt, "Manual edit")

    def test_prompt_source_page_has_no_prompt_table_and_paste_adds_one_multiline_prompt(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        page = ClipartPromptInputPage(state, lambda: None)

        self.assertFalse(hasattr(page, "current_prompts_table"))
        self.assertEqual(
            [button.text() for button in page.source_buttons],
            ["Сгенерировать серию", "Вставить готовый промпт", "Импортировать CSV"],
        )
        page.paste_edit.setPlainText("First line\nSecond line\nThird line")
        page.add_prompt_button.click()

        self.assertEqual(len(state.clipart.prompts), 1)
        self.assertEqual(
            state.clipart.prompts[0].prompt,
            "First line Second line Third line",
        )
        self.assertIn("следующем шаге", page.paste_status_label.text())
        self.assertFalse(hasattr(page, "paste_button"))

    def test_series_chroma_controls_offer_only_approved_materials(self):
        page = ClipartPromptInputPage(ProjectState(mode=ProjectMode.CLIPART), lambda: None)

        self.assertEqual(
            [button.text() for button in page.chroma_material_buttons],
            [
                "Акварель",
                "Тонкие листья",
                "Хвоя",
                "Металл",
                "Лента / сатин",
                "Прозрачные детали",
                "Снег / лёд",
            ],
        )
        self.assertFalse(hasattr(page, "chroma_key_custom_color"))

    def test_clipart_chroma_sources_use_three_visible_color_buttons(self):
        page = ClipartPromptInputPage(ProjectState(mode=ProjectMode.CLIPART), lambda: None)

        self.assertEqual(
            tuple(page.chroma_key_color_buttons),
            ("blue", "red", "green"),
        )
        self.assertEqual(
            tuple(page.paste_chroma_color_buttons),
            ("blue", "red", "green"),
        )
        self.assertTrue(page.chroma_key_color.isHidden())
        self.assertTrue(page.paste_chroma_color.isHidden())

        page.paste_chroma_color_buttons["red"].click()

        self.assertEqual(page.paste_chroma_color.currentData(), "red")
        self.assertTrue(page.paste_chroma_color_buttons["red"].isChecked())

    def test_series_color_buttons_restore_and_update_draft_and_prompt(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompt_generator.theme = "Watercolor fox"
        state.clipart.prompt_generator.subjects = ["Fox"]
        state.clipart.prompt_generator.chroma_key_enabled = True
        state.clipart.prompt_generator.chroma_key_color = "red"
        page = ClipartPromptInputPage(state, lambda: None)

        self.assertTrue(page.chroma_key_color_buttons["red"].isChecked())

        page.chroma_key_color_buttons["green"].click()

        self.assertEqual(page.chroma_key_color.currentData(), "green")
        self.assertEqual(state.clipart.prompt_generator.chroma_key_color, "green")
        self.assertIn("#00FF00", page.preview_label.text())

    def test_series_chroma_controls_default_to_blue_and_limit_materials_to_three(self):
        page = ClipartPromptInputPage(ProjectState(mode=ProjectMode.CLIPART), lambda: None)

        self.assertEqual(page.chroma_key_color.currentData(), "blue")
        watercolor, leaves, needles, metal = page.chroma_material_buttons[:4]
        watercolor.click()
        leaves.click()
        needles.click()

        self.assertTrue(watercolor.isChecked())
        self.assertTrue(leaves.isChecked())
        self.assertTrue(needles.isChecked())
        self.assertFalse(metal.isEnabled())

        watercolor.click()

        self.assertTrue(metal.isEnabled())

    def test_series_chroma_selected_materials_use_dedicated_readable_style(self):
        page = ClipartPromptInputPage(ProjectState(mode=ProjectMode.CLIPART), lambda: None)

        self.assertTrue(page.chroma_material_buttons[0].property("v3ChromaMaterial"))

    def test_clipart_chroma_sources_show_approved_clean_background_advisor(self):
        page = ClipartPromptInputPage(ProjectState(mode=ProjectMode.CLIPART), lambda: None)

        copy = " ".join(
            label.text() for label in page.chroma_advisor.findChildren(QLabel)
        )
        self.assertTrue(page.chroma_advisor.is_expanded)
        self.assertEqual(
            page.chroma_advisor.toggle_button.text().replace("\n", " "),
            "Помощник чистого фона",
        )
        self.assertIn("Синий подходит", copy)
        self.assertIn("Выберите красный фон", copy)
        self.assertIn("выберите зелёный фон", copy)
        self.assertIn("выбираются слева", copy)
        self.assertTrue(
            page.chroma_advisor.content_layout.alignment()
            & Qt.AlignmentFlag.AlignTop
        )
        self.assertFalse(page.chroma_advisor.isHidden())

        page._select_source(0)
        self.assertFalse(page.chroma_advisor.isHidden())

        page._select_source(2)
        self.assertTrue(page.chroma_advisor.isHidden())

    def test_chroma_material_controls_wrap_without_widening_the_prompt_page(self):
        page = ClipartPromptInputPage(ProjectState(mode=ProjectMode.CLIPART), lambda: None)

        generator_layout = page.chroma_material_buttons[0].parentWidget().layout()
        paste_layout = next(iter(page.paste_chroma_material_buttons.values())).parentWidget().layout()

        self.assertEqual(generator_layout.columnCount(), 2)
        self.assertEqual(paste_layout.columnCount(), 2)

    def test_chroma_advisor_fits_the_normal_window_without_horizontal_scroll(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.set_step(StepId.PROMPTS)
        shell = AppShell(state)
        controller = install_clipart_flow(shell, worker_factory=WorkerFactory())
        page = controller.pages[StepId.PROMPTS]
        page._select_source(1)
        shell.resize(1120, 780)
        shell.show()
        self.app.processEvents()

        self.assertEqual(page.horizontalScrollBar().maximum(), 0)

        shell.close()

    def test_paste_can_append_selected_chroma_material_clause(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        page = ClipartPromptInputPage(state, lambda: None)
        page.paste_chroma_enabled.setChecked(True)
        page.paste_chroma_material_buttons["metal"].setChecked(True)
        page.paste_edit.setPlainText("gold ornament")

        page._apply_paste()

        self.assertIn("matte brushed metal", state.clipart.prompts[0].prompt)

    def test_paste_chroma_controls_limit_materials_to_three(self):
        page = ClipartPromptInputPage(ProjectState(mode=ProjectMode.CLIPART), lambda: None)

        buttons = page.paste_chroma_material_buttons
        buttons["watercolor"].click()
        buttons["thin_leaves"].click()
        buttons["conifer_needles"].click()

        self.assertTrue(buttons["conifer_needles"].isChecked())
        self.assertFalse(buttons["metal"].isEnabled())

    def test_csv_import_has_no_chroma_controls(self):
        page = ClipartPromptInputPage(ProjectState(mode=ProjectMode.CLIPART), lambda: None)

        self.assertFalse(hasattr(page, "csv_chroma_enabled"))
        self.assertFalse(hasattr(page, "csv_chroma_material_buttons"))

    def test_csv_source_has_primary_button_and_accepts_csv_drop(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-csv-drop-") as temp:
            csv_path = Path(temp) / "prompts.csv"
            csv_path.write_text("prompt\nfox\n", encoding="utf-8")
            image_path = Path(temp) / "image.png"
            Image.new("RGB", (2, 2), "white").save(image_path)
            page = ClipartPromptInputPage(ProjectState(mode=ProjectMode.CLIPART), lambda: None)
            dropped = []
            page.csv_drop_zone.file_dropped.connect(dropped.append)

            valid_event = FakeCsvDropEvent([csv_path])
            page.csv_drop_zone.dragEnterEvent(valid_event)
            self.assertTrue(valid_event.accepted)
            with patch.object(
                v3_clipart_flow.PromptCsvImportDialog,
                "exec",
                return_value=QDialog.DialogCode.Rejected,
            ):
                page.csv_drop_zone.dropEvent(valid_event)

            invalid_event = FakeCsvDropEvent([image_path])
            page.csv_drop_zone.dragEnterEvent(invalid_event)

        self.assertEqual(page.csv_button.property("variant"), "primary")
        self.assertEqual(dropped, [str(csv_path)])
        self.assertFalse(invalid_event.accepted)

    def test_paste_keeps_duplicate_prompt_as_a_separate_entry_with_its_references(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompts = [PromptEntry("Same prompt", ["old.png"])]
        page = ClipartPromptInputPage(state, lambda: None)
        page._paste_references = ["new.png"]
        page.paste_edit.setPlainText("Same prompt")

        page.add_prompt_button.click()

        self.assertEqual(len(state.clipart.prompts), 2)
        self.assertEqual(state.clipart.prompts[1].references, ["new.png"])
        self.assertIn("добавлен", page.paste_status_label.text())

    def test_paste_prompt_keeps_up_to_five_reference_paths(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-paste-refs-") as temp:
            paths = []
            for index in range(6):
                path = Path(temp) / f"very-long-reference-file-name-{index}.png"
                Image.new("RGB", (2, 2), "white").save(path)
                paths.append(str(path))
            state = ProjectState(mode=ProjectMode.CLIPART)
            page = ClipartPromptInputPage(state, lambda: None)
            page._add_paste_references(paths)
            self.assertIn("…", page.paste_references_label.text())
            page.paste_edit.setPlainText("One prompt")
            page.add_prompt_button.click()

        self.assertEqual(state.clipart.prompts[0].references, paths[:5])

    def test_csv_import_appends_and_opens_prompt_review(self):
        class AcceptedImport:
            def __init__(self, *_):
                pass

            def exec(self):
                return QDialog.DialogCode.Accepted

            def get_entries(self):
                return [{"prompt": "Imported fox", "references": ["fox.png"]}]

        advanced = []
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompts = [PromptEntry("Existing")]
        page = ClipartPromptInputPage(
            state,
            lambda: None,
            advance=lambda: advanced.append(True),
        )
        with (
            patch.object(
                v3_clipart_flow.QFileDialog,
                "getOpenFileName",
                return_value=("prompts.csv", "CSV files (*.csv)"),
            ),
            patch.object(
                v3_clipart_flow,
                "PromptCsvImportDialog",
                AcceptedImport,
            ),
        ):
            page._choose_csv()

        self.assertEqual(
            [entry.prompt for entry in state.clipart.prompts],
            ["Existing", "Imported fox"],
        )
        self.assertEqual(advanced, [True])

    def test_exported_prompt_csv_round_trips_prompts_and_references(self):
        entries = [
            PromptEntry("Акварельный лис", ["fox.png", "texture.webp"]),
            PromptEntry("A winter branch", []),
        ]
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "prompts.csv"
            export_prompt_csv(entries, destination)

            self.assertTrue(destination.read_bytes().startswith(b"\xef\xbb\xbf"))
            self.assertEqual(
                list(csv.DictReader(destination.read_text(encoding="utf-8-sig").splitlines())),
                [
                    {"Prompt": "Акварельный лис", "References": "fox.png|texture.webp"},
                    {"Prompt": "A winter branch", "References": ""},
                ],
            )
            restored = parse_prompt_csv(destination)

        self.assertEqual(restored, entries)

    def test_prompt_review_exports_all_rows_to_csv(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.common.work_dir = tempfile.gettempdir()
        state.clipart.prompts = [
            PromptEntry("First", ["first.png"]),
            PromptEntry("Second", ["second.png"]),
        ]
        page = ClipartPromptReviewPage(state, lambda: None)
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "export.csv"
            with patch.object(
                v3_clipart_flow.QFileDialog,
                "getSaveFileName",
                return_value=(str(destination), "CSV files (*.csv)"),
            ):
                page.export_csv_button.click()

            self.assertEqual(parse_prompt_csv(destination), state.clipart.prompts)

    def test_review_search_filters_large_prompt_table_without_changing_data(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompts = [
            PromptEntry("Watercolor fox"),
            PromptEntry("Studio photo of a bear"),
            PromptEntry("Watercolor rabbit"),
        ]
        page = ClipartPromptReviewPage(state, lambda: None)
        page.search_edit.setText("watercolor")

        self.assertFalse(page.table.isRowHidden(0))
        self.assertTrue(page.table.isRowHidden(1))
        self.assertFalse(page.table.isRowHidden(2))
        self.assertIn("2 из 3", page.search_result_label.text())
        self.assertEqual(len(state.clipart.prompts), 3)

        page.table.item(0, 0).setText("Studio photo of a fox")
        self.assertTrue(page.table.isRowHidden(0))
        self.assertIn("1 из 3", page.search_result_label.text())

    def test_two_consecutive_row_moves_keep_visible_and_saved_order_in_sync(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompts = [PromptEntry("A"), PromptEntry("B"), PromptEntry("C")]
        page = ClipartPromptReviewPage(state, lambda: None)

        page._updating = True
        for row, source in enumerate((1, 2, 0)):
            page.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, source)
        page._updating = False
        page._rows_moved()
        self.assertEqual([entry.prompt for entry in state.clipart.prompts], ["B", "C", "A"])
        self.assertEqual(
            [page.table.item(row, 0).data(Qt.ItemDataRole.UserRole) for row in range(3)],
            [0, 1, 2],
        )

        page._updating = True
        for row, source in enumerate((2, 0, 1)):
            page.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, source)
        page._updating = False
        page._rows_moved()
        self.assertEqual([entry.prompt for entry in state.clipart.prompts], ["A", "B", "C"])

    def test_csv_import_preserves_quoted_text_and_bounded_references(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-csv-") as temp:
            path = Path(temp) / "prompts.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Prompt", "References"])
                writer.writerow(["Whale, watercolor", "one.png | two.png"])

            entries = parse_prompt_csv(path)

        self.assertEqual(entries[0].prompt, "Whale, watercolor")
        self.assertEqual(entries[0].references, ["one.png", "two.png"])

    def test_invalid_folder_and_malformed_csv_fail_closed(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        shell = AppShell(state)
        controller = install_clipart_flow(shell, worker_factory=WorkerFactory())
        page = controller.pages[StepId.PROJECT]
        page.work_dir_edit.setText("Z:/definitely/missing/clipart-folder")

        self.assertEqual(shell.go_next(), StepId.PROJECT)
        self.assertIn("недоступна", shell.validation_label.text())

        with tempfile.TemporaryDirectory(prefix="clipart-v3-bad-csv-") as temp:
            path = Path(temp) / "broken.csv"
            path.write_text('Prompt\n"' + ("x" * 200_000), encoding="utf-8")
            with self.assertRaises(ClipartFlowError):
                parse_prompt_csv(path)
    def test_paste_add_and_duplicate_enforce_prompt_entry_limit(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        shell = AppShell(state)
        controller = install_clipart_flow(shell, worker_factory=WorkerFactory())
        input_page = controller.pages[StepId.PROMPTS]
        state.clipart.prompts = [
            PromptEntry(f"Prompt {index}") for index in range(MAX_PROMPT_ENTRIES)
        ]
        input_page.paste_edit.setPlainText("One more prompt")
        input_page.add_prompt_button.click()
        self.assertEqual(len(state.clipart.prompts), MAX_PROMPT_ENTRIES)
        self.assertIn(
            "Максимум",
            input_page.card.status_label.text(),
        )

        state.clipart.prompts = [PromptEntry("First")]
        review_page = controller.pages[StepId.PROMPT_REVIEW]
        review_page.refresh_from_state()
        review_page.table.setCurrentCell(0, 0)
        state.clipart.prompts = [PromptEntry(f"Prompt {index}") for index in range(MAX_PROMPT_ENTRIES)]
        review_page._add()
        review_page._duplicate()
        self.assertEqual(len(state.clipart.prompts), MAX_PROMPT_ENTRIES)
        self.assertIn("Максимум", review_page.card.status_label.text())
    def test_processing_page_exposes_every_supported_operation_setting(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        shell = AppShell(state)
        controller = install_clipart_flow(shell, worker_factory=WorkerFactory())
        page = controller.pages[StepId.PROCESSING_OPTIONS]
        field_names = {definition.name for definition in dataclass_fields(ImageOperationData)}

        self.assertEqual(
            set(page.operation_widgets)
            | {"visible_mark_cleanup_mode", "upscale_factor"},
            field_names - {
                "remove_exif",
                "remove_xmp",
                "remove_iptc",
                "remove_comments_text",
                "remove_embedded_thumbnail",
                "remove_generator_fields",
                "remove_embedded_c2pa",
                "preserve_icc",
                "preserve_dpi",
                "chroma_key_custom_color",
                "chroma_key_tolerance",
                "chroma_key_softness",
            },
        )
        self.assertNotIn("chroma_key_tolerance", page.operation_widgets)
        self.assertNotIn("chroma_key_softness", page.operation_widgets)
        self.assertIsInstance(
            page.operation_widgets["remove_background"],
            QCheckBox,
        )
        self.assertIsNotNone(page.cleanup_checkbox)
        page.operation_widgets["trim"].setChecked(True)
        self.assertTrue(state.clipart.operations.trim)
        self.assertIn("Trim", page.pipeline_label.text())
        page.cleanup_checkbox.setChecked(True)
        self.assertTrue(state.clipart.operations.remove_exif)
        self.assertTrue(state.clipart.operations.preserve_icc)

    def test_pipeline_summary_matches_real_worker_order(self):
        operations = ImageOperationData(
            visible_mark_cleanup=True,
            upscale_before=True,
            unsharp=True,
            remove_background=True,
            upscale_after=True,
            edge_shrink=True,
            trim=True,
            remove_xmp=True,
            export_300_dpi=True,
        )

        self.assertEqual(
            clipart_pipeline_steps(operations),
            (
                "Генерация изображения",
                "Удаление видимой метки",
                "Апскейл до удаления фона",
                "Unsharp Mask",
                "Удаление фона",
                "Апскейл после удаления фона",
                "Очистка края alpha",
                "Trim",
                "Очистка данных файла",
                "Экспорт 300 DPI",
                "Экспорт PNG",
            ),
        )

    def test_cost_and_worker_request_include_variants_references_and_operations(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-run-") as temp:
            state = self.make_state(temp)
            state.runtime.timeout = 42
            request = build_clipart_run_request(
                state,
                {"kie_api_key": "test-key", "timeout": 999999},
            )
            estimate = estimate_clipart_cost(state)

        self.assertEqual(request.mode, "mode_both")
        self.assertEqual(len(request.generated_prompts), 4)
        self.assertEqual(request.generated_prompts[2]["references"], [str(Path(temp) / "reference.png")])
        self.assertEqual(request.settings["text_generation_model"], state.clipart.generation.model)
        self.assertEqual(request.settings["remove_bg"], True)
        self.assertEqual(request.settings["timeout"], 42)
        self.assertEqual(estimate.request_count, 12)
        self.assertEqual(estimate.estimated_usd, Decimal("0.920"))
        self.assertTrue(estimate.complete)

    def test_reference_prompts_use_their_own_generation_profile(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-reference-profile-") as temp:
            state = self.make_state(temp)
            state.clipart.generation.model = "gpt-image-2"
            state.clipart.generation.ratio = "16:9"
            state.clipart.generation.resolution = "2K"
            state.clipart.generation.reference_model = "gpt-image/1.5-image-to-image"
            state.clipart.generation.reference_ratio = "2:3"
            state.clipart.generation.reference_resolution = "1K"
            state.clipart.operations.upscale_before = False
            state.clipart.operations.remove_background = False

            request = build_clipart_run_request(state, {"kie_api_key": "test-key"})
            estimate = estimate_clipart_cost(state)

        self.assertEqual(request.settings["text_generation_model"], "gpt-image-2")
        self.assertEqual(request.settings["text_generation_ratio"], "16:9")
        self.assertEqual(request.settings["text_generation_resolution"], "2K")
        self.assertEqual(
            request.settings["reference_generation_model"],
            "gpt-image/1.5-image-to-image",
        )
        self.assertEqual(request.settings["reference_generation_ratio"], "2:3")
        self.assertEqual(request.settings["reference_generation_resolution"], "1K")
        self.assertEqual(estimate.generation_usd, Decimal("0.140"))

    def test_clipart_chroma_request_omits_legacy_numeric_and_custom_fields(self):
        with tempfile.TemporaryDirectory(prefix="clipart-chroma-request-") as temp:
            state = self.make_state(temp)
            operations = state.clipart.operations
            operations.remove_background = True
            operations.remove_background_provider = "local_chroma_key"
            operations.chroma_key_color = "green"
            operations.chroma_key_custom_color = "#123456"
            operations.chroma_key_tolerance = 255
            operations.chroma_key_softness = 255

            request = build_clipart_run_request(state, {"kie_api_key": "test-key"})

        self.assertEqual(request.settings["chroma_key_color"], "green")
        self.assertNotIn("chroma_key_custom_color", request.settings)
        self.assertNotIn("chroma_key_tolerance", request.settings)
        self.assertNotIn("chroma_key_softness", request.settings)

    def test_generation_options_use_mode_specific_qwen_ratios(self):
        primary = next(
            option
            for option in generation_model_options(references=False)
            if option.model_id == "qwen-image-2"
        )
        reference = next(
            option
            for option in generation_model_options(references=True)
            if option.model_id == "qwen-image-2"
        )
        self.assertEqual(primary.ratios, ("1:1", "3:4", "4:3", "9:16", "16:9"))
        self.assertEqual(
            reference.ratios,
            ("1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"),
        )

    def test_fal_endpoint_quantities_count_generation_and_processing(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompts = [PromptEntry(prompt="one"), PromptEntry(prompt="two")]
        state.clipart.generation.model = "fal-ai/flux/schnell"
        state.clipart.generation.variants = 2
        operations = state.clipart.operations
        operations.upscale_before = True
        operations.upscale_before_provider = "fal"
        operations.fal_upscale_model = "fal-ai/recraft/upscale/crisp"
        operations.remove_background = True
        operations.remove_background_provider = "fal"
        operations.fal_remove_bg_model = "fal-ai/birefnet/v2"
        operations.upscale_after = True
        operations.upscale_after_provider = "fal"

        assert fal_endpoint_quantities(state) == {
            "fal-ai/flux/schnell": 4,
            "fal-ai/recraft/upscale/crisp": 4,
            "fal-ai/birefnet/v2": 4,
        }

    def test_gpt_image_two_exposes_all_documented_ratios(self):
        primary = next(
            option
            for option in generation_model_options(references=False)
            if option.model_id == "gpt-image-2"
        )
        self.assertEqual(
            set(primary.ratios),
            {
                "auto", "1:1", "3:2", "2:3", "4:3", "3:4", "5:4", "4:5",
                "16:9", "9:16", "2:1", "1:2", "3:1", "1:3", "21:9", "9:21",
            },
        )

    def test_qwen_reference_limits_fail_before_worker_creation(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-qwen-contract-") as temp:
            state = self.make_state(temp)
            reference_path = str(Path(temp) / "reference.png")
            state.clipart.prompts = [
                PromptEntry("Baby turtle", [reference_path] * 2),
            ]
            state.clipart.generation.model = "qwen-image-2"
            state.clipart.generation.ratio = "1:1"
            state.clipart.generation.reference_model = "qwen-image-2"
            state.clipart.generation.reference_ratio = "1:1"

            with self.assertRaisesRegex(ClipartFlowError, "1 референс"):
                build_clipart_run_request(state, {"kie_api_key": "test-key"})

    def test_reference_file_size_limit_fails_before_worker_creation(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-reference-size-") as temp:
            state = self.make_state(temp)
            reference_path = Path(temp) / "reference.png"
            reference_path.write_bytes(
                reference_path.read_bytes()
                + b"\0" * (10 * 1024 * 1024 + 1)
            )
            state.clipart.prompts = [PromptEntry("Baby turtle", [str(reference_path)])]
            state.clipart.generation.model = "qwen-image-2"
            state.clipart.generation.ratio = "1:1"
            state.clipart.generation.reference_model = "qwen-image-2"
            state.clipart.generation.reference_ratio = "1:1"

            with self.assertRaisesRegex(ClipartFlowError, "10 МБ"):
                build_clipart_run_request(state, {"kie_api_key": "test-key"})

    def test_alpha_safe_upscale_rejects_non_alpha_preserving_provider_after_bg_removal(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-alpha-safe-") as temp:
            state = self.make_state(temp)
            state.clipart.operations.remove_background = True
            state.clipart.operations.upscale_after = True
            state.clipart.operations.upscale_after_provider = "local_realesrgan"

            with patch("v3_clipart_flow.upscale_model_preserves_alpha", return_value=False):
                with self.assertRaisesRegex(ClipartFlowError, "прозрачность"):
                    build_clipart_run_request(
                        state,
                        {"kie_api_key": "test-key"},
                    )

    def test_alpha_safe_upscale_rejects_recraft_after_bg_removal(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-recraft-alpha-safe-") as temp:
            state = self.make_state(temp)
            state.clipart.operations.remove_background = True
            state.clipart.operations.upscale_after = True
            state.clipart.operations.upscale_after_provider = "kie"
            state.clipart.operations.kie_upscale_after_model = "recraft/crisp-upscale"

            with self.assertRaisesRegex(ClipartFlowError, "Recraft Crisp|прозрач"):
                build_clipart_run_request(
                    state,
                    {"kie_api_key": "test-key"},
                )

    def test_request_is_accepted_by_real_worker_constructor(self):
        from main import WorkerThread

        with tempfile.TemporaryDirectory(prefix="clipart-v3-real-worker-") as temp:
            state = self.make_state(temp)
            state.runtime.timeout = 42
            state.clipart.operations.remove_xmp = True
            request = build_clipart_run_request(
                state,
                {"kie_api_key": "test-key", "timeout": 999999},
            )
            worker = WorkerThread(**request.worker_kwargs())

        self.assertEqual(worker.mode, "mode_both")
        self.assertEqual(len(worker.generated_prompts), 4)
        self.assertEqual(worker.text_generation_model, state.clipart.generation.model)
        self.assertTrue(worker.remove_bg)
        self.assertTrue(worker.metadata_cleanup_options.remove_xmp)
        self.assertEqual(worker.timeout, 42)
        self.assertNotIn("test-key", repr(request))
    def test_wizard_run_uses_injected_legacy_worker_without_network(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-launch-") as temp:
            state = self.make_state(temp)
            state.set_step(StepId.REVIEW_RUN)
            factory = WorkerFactory()
            shell = AppShell(state)
            controller = install_clipart_flow(
                shell,
                runtime_settings_provider=lambda: {"kie_api_key": "test-key"},
                worker_factory=factory,
                authorization_provider=lambda: None,
            )
            started = []
            controller.started.connect(started.append)

            shell.go_next()

        self.assertEqual(len(factory.workers), 1)
        self.assertTrue(factory.workers[0].started)
        self.assertEqual(factory.workers[0].kwargs["mode"], "mode_both")
        self.assertEqual(len(started), 1)

    def test_missing_key_and_excessive_request_count_fail_before_worker(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-guard-") as temp:
            state = self.make_state(temp)
            request = build_clipart_run_request(state, {})
            self.assertEqual(missing_runtime_requirements(request), ("KIE API Key",))

            state.set_step(StepId.REVIEW_RUN)
            shell = AppShell(state)
            controller = install_clipart_flow(
                shell,
                runtime_settings_provider=lambda: {},
                worker_factory=WorkerFactory(),
            )
            self.assertIn("KIE API Key", controller.review_page.requirements_label.text())

            state.clipart.prompts = [
                PromptEntry(f"Prompt {index}")
                for index in range((MAX_CLIPART_REQUESTS // 100) + 1)
            ]
            state.clipart.generation.variants = 100
            with self.assertRaisesRegex(ClipartFlowError, "Максимум"):
                build_clipart_run_request(state, {"kie_api_key": "test-key"})

    def test_fal_model_requires_fal_key_instead_of_kie_key(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-fal-guard-") as temp:
            state = self.make_state(temp)
            state.clipart.prompts = [PromptEntry("Baby whale")]
            state.clipart.generation.model = "fal-ai/flux/schnell"
            request = build_clipart_run_request(state, {"kie_api_key": "test-key"})

        self.assertEqual(missing_runtime_requirements(request), ("Fal.ai API Key",))

    def test_fal_review_keeps_price_refresh_optional_without_confirmation(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-fal-review-") as temp:
            state = self.make_state(temp)
            state.clipart.prompts = [PromptEntry("Baby whale")]
            state.clipart.generation.model = "fal-ai/flux/schnell"
            review = ClipartReviewRunPage(state)

        self.assertFalse(review.findChildren(QCheckBox))
        self.assertEqual(review.validation_issues(), ())
        self.assertFalse(review.fal_cost_refresh_button.isHidden())
        self.assertTrue(review.requirements_label.isHidden())

    def test_oversized_local_reference_is_rejected_when_attached(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-reference-size-") as temp:
            reference_path = Path(temp) / "too-large.png"
            with reference_path.open("wb") as handle:
                handle.seek(10 * 1024 * 1024)
                handle.write(b"x")
            state = ProjectState(mode=ProjectMode.CLIPART)
            page = ClipartPromptInputPage(state, lambda: None)

            page._add_paste_references([str(reference_path)])

            self.assertEqual(page._paste_references, [])
            self.assertIn("не добавлен", page.card.status_label.text())
            self.assertIn("10 МБ", page.card.status_label.text())
            self.assertIn("10,0 МБ", page.card.status_label.text())

    def test_oversized_saved_reference_has_specific_preflight_error(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-reference-preflight-") as temp:
            reference_path = Path(temp) / "too-large.png"
            with reference_path.open("wb") as handle:
                handle.seek(10 * 1024 * 1024)
                handle.write(b"x")
            state = ProjectState(mode=ProjectMode.CLIPART)
            state.common.work_dir = temp
            state.clipart.prompts = [PromptEntry("Fox", [str(reference_path)])]

            with self.assertRaisesRegex(
                ClipartFlowError,
                "Референс .* превышает 10 МБ",
            ):
                build_clipart_run_request(state, {"kie_api_key": "test-key"})

    def test_runtime_errors_explain_kie_balance_and_reference_size(self):
        balance = _safe_runtime_error(
            "KIE createTask rejected [errorCode=402; message=Insufficient Credits]"
        )
        oversized = _safe_runtime_error(
            "KIE task failed [errorCode=413; message=reference image exceeds 10MB]"
        )

        self.assertIn("Недостаточно средств", balance)
        self.assertIn("Пополните баланс KIE", balance)
        self.assertIn("Референс превышает", oversized)
        self.assertIn("10 МБ", oversized)

    def test_runtime_settings_are_allowlisted_and_project_bounds_win(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-runtime-") as temp:
            state = self.make_state(temp)
            state.runtime.timeout = 600
            state.runtime.retries = 10
            request = build_clipart_run_request(
                state,
                {
                    "kie_api_key": "secret-key",
                    "timeout": 10**30,
                    "retries": 10**30,
                    "unexpected": "ignored",
                },
            )

        self.assertEqual(request.settings["timeout"], 600)
        self.assertEqual(request.settings["retries"], 10)
        self.assertNotIn("unexpected", request.settings)
        self.assertNotIn("secret-key", repr(request))

    def test_unknown_processing_model_fails_and_never_shows_partial_price(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-model-") as temp:
            state = self.make_state(temp)
            state.clipart.operations.kie_upscale_model = "unknown/upscale"
            estimate = estimate_clipart_cost(state)

            self.assertFalse(estimate.complete)
            self.assertNotIn("$", estimate.summary)
            with self.assertRaisesRegex(ClipartFlowError, "не поддерживается"):
                build_clipart_run_request(state, {"kie_api_key": "test-key"})

    def test_missing_local_reference_is_reported_before_run(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-reference-") as temp:
            state = self.make_state(temp)
            Path(state.clipart.prompts[1].references[0]).unlink()
            state.set_step(StepId.REVIEW_RUN)
            shell = AppShell(state)
            controller = install_clipart_flow(
                shell,
                runtime_settings_provider=lambda: {"kie_api_key": "test-key"},
                worker_factory=WorkerFactory(),
            )

            status = controller.review_page.requirements_label.text()
            self.assertIn("reference.png", status)
            self.assertIn("не найден", status)

    def test_processing_page_hides_irrelevant_provider_parameters(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        shell = AppShell(state)
        controller = install_clipart_flow(shell, worker_factory=WorkerFactory())
        page = controller.pages[StepId.PROCESSING_OPTIONS]
        widgets = page.operation_widgets

        self.assertTrue(widgets["local_ben2_alpha_threshold"].isHidden())
        widgets["remove_background_provider"].setCurrentIndex(
            widgets["remove_background_provider"].findData("local_rembg")
        )
        self.assertTrue(widgets["local_ben2_alpha_threshold"].isHidden())
        self.assertFalse(widgets["local_rembg_model"].isHidden())
        self.assertTrue(widgets["kie_remove_bg_model"].isHidden())
        widgets["unsharp"].setChecked(True)
        self.assertFalse(widgets["unsharp_amount"].isHidden())
        widgets["remove_background"].setChecked(False)
        self.assertTrue(widgets["remove_background_provider"].isHidden())

    def test_local_upscale_is_blocked_before_paid_generation_when_tool_is_missing(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-local-tool-") as temp:
            state = self.make_state(temp)
            state.clipart.operations.upscale_before_provider = "local_realesrgan"
            request = build_clipart_run_request(state, {"kie_api_key": "test-key"})

        missing = missing_runtime_requirements(request)
        self.assertTrue(any("Real-ESRGAN" in item for item in missing))

    def test_reference_preflight_rejects_malformed_url_and_non_image_file(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-ref-guard-") as temp:
            state = self.make_state(temp)
            state.clipart.prompts[1].references = ["https://"]
            with self.assertRaisesRegex(ClipartFlowError, "HTTPS"):
                build_clipart_run_request(state, {"kie_api_key": "test-key"})

            text_path = Path(temp) / "not-image.txt"
            text_path.write_text("not an image", encoding="utf-8")
            state.clipart.prompts[1].references = [str(text_path)]
            with self.assertRaisesRegex(ClipartFlowError, "изображением"):
                build_clipart_run_request(state, {"kie_api_key": "test-key"})

    def test_worker_factory_and_signal_errors_redact_runtime_secrets(self):
        secret = "TEST-SECRET-KEY"
        with tempfile.TemporaryDirectory(prefix="clipart-v3-redact-") as temp:
            state = self.make_state(temp)
            state.set_step(StepId.REVIEW_RUN)
            shell = AppShell(state)

            def failing_factory(**_):
                raise ValueError(f"provider rejected {secret}")

            controller = install_clipart_flow(
                shell,
                runtime_settings_provider=lambda: {"kie_api_key": secret},
                worker_factory=failing_factory,
                authorization_provider=lambda: None,
            )
            controller.start()
            self.assertNotIn(secret, controller.review_page.run_status_label.text())

            controller._runtime_settings = {"kie_api_key": secret}
            errors = []
            controller.error.connect(errors.append)
            controller._error(f"worker failed bearer abc and {secret}")
            self.assertNotIn(secret, errors[-1])
            self.assertNotIn("bearer abc", errors[-1].lower())

    def test_fal_runtime_secret_is_redacted_from_worker_error(self):
        secret = "FAL-TEST-SECRET"
        with tempfile.TemporaryDirectory(prefix="clipart-v3-fal-redact-") as temp:
            state = self.make_state(temp)
            state.set_step(StepId.REVIEW_RUN)
            shell = AppShell(state)
            controller = install_clipart_flow(
                shell,
                runtime_settings_provider=lambda: {"fal_api_key": secret},
                worker_factory=lambda **_kwargs: (_ for _ in ()).throw(
                    ValueError(f"Fal rejected {secret}")
                ),
                authorization_provider=lambda: None,
            )

            controller.start()
            errors = []
            controller.error.connect(errors.append)
            controller._error(f"worker failed with {secret}")

            self.assertNotIn(secret, errors[-1])

    def test_csv_and_table_reject_oversized_input_without_truncation(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-limits-") as temp:
            csv_path = Path(temp) / "too-many.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Prompt"])
                for index in range(MAX_PROMPT_ENTRIES + 1):
                    writer.writerow([f"Prompt {index}"])
            with self.assertRaisesRegex(ClipartFlowError, "Максимум"):
                parse_prompt_csv(csv_path)

        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompts = [PromptEntry("Original")]
        shell = AppShell(state)
        controller = install_clipart_flow(shell, worker_factory=WorkerFactory())
        page = controller.pages[StepId.PROMPT_REVIEW]
        page.table.item(0, 0).setText("x" * (20_000 + 1))
        self.assertEqual(state.clipart.prompts[0].prompt, "Original")
        self.assertEqual(page.table.item(0, 0).text(), "Original")
        self.assertIn("длину", page.card.status_label.text())

    def test_cost_distinguishes_images_from_paid_provider_calls(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-cost-count-") as temp:
            state = ProjectState(mode=ProjectMode.CLIPART)
            state.common.work_dir = temp
            state.clipart.prompts = [PromptEntry("One image")]
            estimate = estimate_clipart_cost(state)
            review = ClipartReviewRunPage(state)

        self.assertEqual(estimate.request_count, 3)
        self.assertEqual(estimate.generation_request_count, 1)
        self.assertEqual(estimate.processing_request_count, 2)
        self.assertIn("3 запросов", estimate.summary)
        self.assertIn("изображений 1", review.summary_label.text())

    def test_generation_page_does_not_show_intermediate_cost(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        page = ClipartGenerationPage(state, lambda: None)

        visible_copy = " ".join(
            label.text() for label in page.findChildren(QLabel)
        ).lower()
        self.assertNotIn("ориентировочно", visible_copy)
        self.assertNotIn("стоимость", visible_copy)

    def test_generation_page_hides_reference_settings_without_references(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompts = [PromptEntry("Fox"), PromptEntry("Bear")]

        page = ClipartGenerationPage(state, lambda: None)

        self.assertFalse(page.reference_controls_container.isVisible())
        self.assertFalse(hasattr(page, "reference_advanced"))

    def test_generation_page_exposes_independent_reference_settings(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompts = [
            PromptEntry("Fox"),
            PromptEntry("Bear", ["D:/references/bear.png"]),
            PromptEntry("Rabbit", ["D:/references/rabbit.png"]),
        ]

        page = ClipartGenerationPage(state, lambda: None)

        self.assertFalse(page.reference_controls_container.isHidden())
        self.assertFalse(hasattr(page, "reference_advanced"))
        self.assertGreaterEqual(page.model_combo.findData("gpt-image-2"), 0)
        self.assertGreaterEqual(page.model_combo.findData("fal-ai/ideogram/v3"), 0)
        self.assertGreaterEqual(page.model_combo.findData("gpt-image/1.5-text-to-image"), 0)
        self.assertGreaterEqual(
            page.reference_model_combo.findData("gpt-image/1.5-image-to-image"),
            0,
        )
        self.assertEqual(page.reference_model_combo.findData("fal-ai/ideogram/v3"), -1)
        page.reference_model_combo.setCurrentIndex(
            page.reference_model_combo.findData("gpt-image/1.5-image-to-image")
        )
        page.reference_ratio_combo.setCurrentText("2:3")
        self.assertEqual(
            state.clipart.generation.reference_model,
            "gpt-image/1.5-image-to-image",
        )
        self.assertEqual(state.clipart.generation.reference_ratio, "2:3")

    def test_nonprefixed_fal_generation_model_requires_fal_key(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompts = [PromptEntry("Fox")]
        state.clipart.generation.model = "ideogram/v4/fast"
        state.clipart.operations.upscale_before = False
        state.clipart.operations.remove_background = False

        request = build_clipart_run_request(state)

        self.assertEqual(missing_runtime_requirements(request), ("Fal.ai API Key",))

    def test_review_summary_is_compact_and_left_aligned(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompts = [PromptEntry("Fox")]
        review = ClipartReviewRunPage(state)
        review.resize(980, 700)
        review.show()
        self.app.processEvents()

        self.assertTrue(
            review.card.layout().alignment() & Qt.AlignmentFlag.AlignTop
        )
        self.assertTrue(
            review.card.content_layout.alignment() & Qt.AlignmentFlag.AlignTop
        )
        for label in (
            review.output_label,
            review.summary_label,
            review.requests_label,
            review.cost_breakdown_label,
            review.pipeline_label,
        ):
            self.assertTrue(label.alignment() & Qt.AlignmentFlag.AlignLeft)
            self.assertTrue(label.alignment() & Qt.AlignmentFlag.AlignTop)
        self.assertLess(review.output_label.geometry().top(), 90)
        section_copy = " ".join(
            label.text() for label in review.findChildren(QLabel)
        )
        self.assertIn("Файлы и результат", section_copy)
        self.assertIn("Порядок", section_copy)
        self.assertIn("API-вызовы и стоимость", section_copy)
        self.assertLess(review.files_section_label.geometry().top(), 40)

    def test_final_review_separates_request_counts_and_provider_costs(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompts = [PromptEntry(f"Prompt {index}") for index in range(80)]
        operations = state.clipart.operations
        operations.upscale_before = True
        operations.remove_background = False
        operations.upscale_after = False
        operations.unsharp = False
        operations.edge_shrink = False
        operations.trim = False
        operations.export_300_dpi = False
        review = ClipartReviewRunPage(state)
        estimate = estimate_clipart_cost(state)

        self.assertEqual(estimate.generation_request_count, 80)
        self.assertEqual(estimate.processing_request_count, 80)
        self.assertEqual(estimate.request_count, 160)
        self.assertIn("генерация 80", review.requests_label.text())
        self.assertIn("обработка 80", review.requests_label.text())
        self.assertIn("всего 160", review.requests_label.text())
        self.assertIn("KIE — 17.600 USD", review.cost_breakdown_label.text())
        self.assertIn("Итого — 17.600 USD", review.cost_breakdown_label.text())
        self.assertNotIn("Fal.ai", review.cost_breakdown_label.text())
        review_copy = " ".join(
            label.text() for label in review.findChildren(QLabel)
        )
        self.assertNotIn("API-ключи не сохраняются", review_copy)

        review.set_preflight_status("Обязательные поля заполнены; запуск готов.", ready=True)
        self.assertFalse(review.requirements_label.isHidden())
        self.assertEqual(review.requirements_label.text(), "✓ Готово к запуску.")

    def test_mixed_provider_cost_refresh_keeps_kie_and_marks_total_complete(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompts = [PromptEntry("Fox")]
        operations = state.clipart.operations
        operations.upscale_before = False
        operations.remove_background = True
        operations.remove_background_provider = "fal"
        operations.upscale_after = False
        operations.unsharp = False
        operations.edge_shrink = False
        operations.trim = False
        operations.export_300_dpi = False
        review = ClipartReviewRunPage(
            state,
            fal_cost_refresh=lambda: (0.033, "USD"),
        )

        before = review.cost_breakdown_label.text()
        self.assertIn("KIE — 0.020 USD", before)
        self.assertIn("Fal.ai — требуется обновить", before)
        self.assertIn("Итого — не рассчитано полностью", before)

        review.refresh_fal_cost()

        after = review.cost_breakdown_label.text()
        self.assertIn("KIE — 0.020 USD", after)
        self.assertIn("Fal.ai — 0.033 USD", after)
        self.assertIn("Итого — 0.053 USD", after)

    def test_fal_cost_refresh_error_keeps_known_kie_cost_visible(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompts = [PromptEntry("Fox")]
        operations = state.clipart.operations
        operations.upscale_before = False
        operations.remove_background = True
        operations.remove_background_provider = "fal"
        review = ClipartReviewRunPage(
            state,
            fal_cost_refresh=lambda: (_ for _ in ()).throw(RuntimeError("timeout")),
        )

        review.refresh_fal_cost()

        text = review.cost_breakdown_label.text()
        self.assertIn("KIE — 0.020 USD", text)
        self.assertIn("Fal.ai — не удалось обновить: timeout", text)
        self.assertIn("Итого — не рассчитано полностью", text)

    def test_supported_fal_upscale_before_is_counted_but_after_is_not(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompts = [PromptEntry("Fox")]
        operations = state.clipart.operations
        operations.upscale_before = True
        operations.upscale_before_provider = "fal"
        operations.upscale_after = True
        operations.upscale_after_provider = "fal"
        operations.remove_background = False

        estimate = estimate_clipart_cost(state)

        self.assertEqual(estimate.processing_request_count, 1)
        self.assertIn("fal", estimate.provider_usd)
        self.assertIn("fal", estimate.incomplete_providers)

    def test_fal_cost_error_is_cleared_when_endpoint_selection_changes(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompts = [PromptEntry("Fox")]
        state.clipart.generation.model = "fal-ai/flux/schnell"
        review = ClipartReviewRunPage(
            state,
            fal_cost_refresh=lambda: (0.011, "USD"),
        )
        review.refresh_fal_cost()
        self.assertIn("Fal.ai — 0.011 USD", review.cost_breakdown_label.text())

        state.clipart.generation.model = "ideogram/v4/fast"
        review.refresh_from_state()
        review.fal_cost_refresh = lambda: (_ for _ in ()).throw(
            RuntimeError("endpoint unavailable")
        )
        review.refresh_fal_cost()
        self.assertIn("endpoint unavailable", review.cost_breakdown_label.text())

        state.clipart.generation.model = "fal-ai/flux/schnell"
        review.refresh_from_state()

        text = review.cost_breakdown_label.text()
        self.assertIn("Fal.ai — требуется обновить", text)
        self.assertNotIn("endpoint unavailable", text)

    def test_fal_refresh_button_uses_actual_per_row_generation_routes(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.generation.model = "fal-ai/flux/schnell"
        state.clipart.generation.reference_model = "gpt-image/1.5-image-to-image"
        state.clipart.prompts = [PromptEntry("Fox", references=("fox.png",))]

        review = ClipartReviewRunPage(state, fal_cost_refresh=lambda: (0.01, "USD"))

        self.assertEqual(fal_endpoint_quantities(state), {})
        self.assertTrue(review.fal_cost_refresh_button.isHidden())
        self.assertNotIn("Fal.ai", review.cost_breakdown_label.text())

    def test_upscale_after_is_hidden_and_disabled_without_affecting_upscale_before(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        operations = state.clipart.operations
        operations.upscale_before = True
        operations.upscale_after = True

        page = ClipartProcessingPage(state, lambda: None)

        self.assertFalse(operations.upscale_after)
        self.assertTrue(page.operation_widgets["upscale_after"].isHidden())
        self.assertTrue(
            page.operation_widgets["upscale_after_provider"].isHidden()
        )
        self.assertFalse(page.operation_widgets["upscale_before"].isHidden())
        self.assertTrue(operations.upscale_before)

    def test_clipart_processing_can_be_skipped(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        operations = state.clipart.operations
        operations.upscale_before = False
        operations.remove_background = False
        page = ClipartProcessingPage(state, lambda: None)

        self.assertNotIn("processing_operation_required", page.validation_issues())

    def test_offscreen_layout_keeps_navigation_visible_at_minimum_size(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-ui-") as temp:
            state = self.make_state(temp)
            shell = AppShell(state)
            controller = install_clipart_flow(shell, worker_factory=WorkerFactory())
            shell.resize(980, 700)
            shell.show()
            self.app.processEvents()

            self.assertTrue(shell.next_button.isVisible())
            self.assertTrue(shell.back_button.isVisible())
            for step, page in controller.pages.items():
                state.set_step(step)
                page.refresh_from_state()
                shell.refresh()
                self.app.processEvents()
                self.assertTrue(page.isVisible())
                self.assertTrue(page.accessibleName())
                if step is StepId.PROMPTS:
                    page._select_source(0)
                    self.app.processEvents()
                    self.assertGreater(page.verticalScrollBar().maximum(), 0)
            shell.close()

    def test_large_prompt_generator_scrolls_vertically_and_horizontally_when_needed(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        page = ClipartPromptInputPage(state, lambda: None)
        page._select_source(0)
        page.resize(500, 350)
        page.show()
        self.app.processEvents()

        self.assertEqual(
            page.verticalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        )
        self.assertEqual(
            page.horizontalScrollBarPolicy(),
            Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        )
        self.assertGreater(page.verticalScrollBar().maximum(), 0)
        self.assertGreater(page.horizontalScrollBar().maximum(), 0)

    def test_module_does_not_duplicate_worker_or_network_transport(self):
        source = Path(v3_clipart_flow.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        class_names = {
            node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        }
        imported_roots = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertNotIn("WorkerThread", class_names)
        self.assertTrue(
            imported_roots.isdisjoint(
                {"requests", "urllib", "httpx", "aiohttp", "socket"}
            )
        )


if __name__ == "__main__":
    unittest.main()
