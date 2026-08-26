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

from PyQt6.QtCore import QItemSelectionModel, QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QCheckBox, QDialog, QMessageBox
from PIL import Image

import v3_clipart_flow
from v3_clipart_flow import (
    MAX_CLIPART_REQUESTS,
    ClipartFlowError,
    ClipartProcessingPage,
    ClipartProjectPage,
    ClipartPromptInputPage,
    ClipartPromptReviewPage,
    ClipartReviewRunPage,
    build_clipart_run_request,
    clipart_pipeline_steps,
    estimate_clipart_cost,
    install_clipart_flow,
    missing_runtime_requirements,
    parse_prompt_csv,
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
        state.clipart.generation.variants = 2
        return state

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
        self.assertTrue(generation_page.reference_advanced.is_expanded)
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
            },
        )
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
        self.assertEqual(estimate.estimated_usd, Decimal("0.900"))
        self.assertTrue(estimate.complete)

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
        self.assertIn("3 запросов", estimate.summary)
        self.assertIn("изображений 1", review.summary_label.text())

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
