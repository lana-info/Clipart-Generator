import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, PngImagePlugin
from PyQt6.QtWidgets import QApplication

from v3_evidence_center import (
    GEMINI_VERIFY_URL,
    OPENAI_VERIFY_URL,
    EvidenceCenterError,
    EvidenceCenterPage,
    build_evidence_report,
    cleanup_options_from_operations,
    export_evidence_report,
    format_evidence_log,
    set_verification_result,
)
from v3_processing_flow import install_processing_flow
from v3_project_state import (
    ProjectMode,
    ProjectState,
    ProjectStateError,
    StepId,
)
from v3_wizard import AppShell


SECRET_METADATA = "secret-metadata-value"
SECRET_PROMPT = "private prompt must not leak"
SECRET_KEY = "secret-api-key"


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def create_metadata_png(path):
    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", SECRET_METADATA)
    info.add_text("parameters", SECRET_PROMPT)
    exif = Image.Exif()
    exif[305] = "FixtureGenerator"
    Image.new("RGBA", (10, 8), (20, 40, 60, 255)).save(
        path,
        pnginfo=info,
        exif=exif,
    )


class V3EvidenceCenterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_state(self, directory):
        source = Path(directory) / "source.png"
        create_metadata_png(source)
        state = ProjectState(mode=ProjectMode.PROCESSING)
        state.common.work_dir = str(directory)
        state.processing.selected_files = [str(source)]
        return state, source

    def test_processing_route_installs_three_independent_evidence_cards(self):
        with tempfile.TemporaryDirectory(prefix="evidence-route-") as temp:
            state, _ = self.make_state(temp)
            shell = AppShell(state)
            controller = install_processing_flow(shell)
            page = controller.pages[StepId.EVIDENCE]

            self.assertIsInstance(page, EvidenceCenterPage)
            self.assertIsNot(page.file_card, page.c2pa_card)
            self.assertIsNot(page.file_card, page.pixel_card)
            self.assertIsNot(page.c2pa_card, page.pixel_card)
            self.assertEqual(page.file_card.title(), "Данные файла")
            self.assertEqual(page.c2pa_card.title(), "Content Credentials")
            self.assertEqual(page.pixel_card.title(), "Пиксельные маркеры")

    def test_local_inspection_shows_counts_without_metadata_values(self):
        with tempfile.TemporaryDirectory(prefix="evidence-inspect-") as temp:
            state, source = self.make_state(temp)
            page = EvidenceCenterPage(
                state,
                lambda: None,
            )
            before = file_hash(source)

            report = build_evidence_report(
                state,
                str(source),
                rights_confirmed=True,
            )
            serialized = json.dumps(report, ensure_ascii=False)

            self.assertEqual(before, file_hash(source))
            self.assertEqual(report["file_hints"]["metadata"], "present")
            self.assertTrue(
                report["file_hints"]["categories"]["generator_fields"]["present"]
            )
            self.assertFalse(report["file_hints"]["affects_pixel_evidence"])
            self.assertNotIn(SECRET_METADATA, serialized)
            self.assertNotIn(SECRET_PROMPT, serialized)
            self.assertIn("generator_fields", page.file_card.status_label.text())

    def test_cleanup_plan_never_changes_pixel_evidence(self):
        with tempfile.TemporaryDirectory(prefix="evidence-independent-") as temp:
            state, source = self.make_state(temp)
            set_verification_result(
                state,
                str(source),
                "synthid",
                "not_detected",
                "input",
            )
            before = build_evidence_report(
                state,
                str(source),
                rights_confirmed=True,
            )

            state.processing.operations.remove_exif = True
            state.processing.operations.remove_xmp = True
            state.processing.operations.remove_generator_fields = True
            after = build_evidence_report(
                state,
                str(source),
                rights_confirmed=True,
            )

            self.assertEqual(
                before["pixel_evidence"],
                after["pixel_evidence"],
            )
            self.assertNotEqual(
                before["cleanup_plan"],
                after["cleanup_plan"],
            )
            self.assertFalse(after["file_hints"]["affects_pixel_evidence"])

    def test_not_detected_never_becomes_human_origin_claim(self):
        with tempfile.TemporaryDirectory(prefix="evidence-claims-") as temp:
            state, source = self.make_state(temp)
            set_verification_result(
                state,
                str(source),
                "synthid",
                "not_detected",
                "output",
            )
            set_verification_result(
                state,
                str(source),
                "openai",
                "not_detected",
                "output",
            )

            report = build_evidence_report(
                state,
                str(source),
                rights_confirmed=True,
            )

            evidence = report["pixel_evidence"]["synthid"]
            self.assertEqual(evidence["status"], "not_detected")
            self.assertEqual(evidence["human_origin_claim"], "not_inferred")
            self.assertEqual(evidence["removal_claim"], "not_claimed")
            openai = report["verification_handoff"]["openai"]
            self.assertEqual(openai["recorded_status"], "not_detected")
            self.assertEqual(openai["signal_type"], "not_inferred")
            self.assertEqual(openai["human_origin_claim"], "not_inferred")
            self.assertEqual(openai["removal_claim"], "not_claimed")
            self.assertNotIn(
                "создано человеком",
                json.dumps(report, ensure_ascii=False).casefold(),
            )

    def test_inspector_is_available_without_a_manual_c1_gate(self):
        with tempfile.TemporaryDirectory(prefix="evidence-rights-") as temp:
            state, source = self.make_state(temp)
            shell = AppShell(state)
            with patch(
                "v3_evidence_center.inspect_image_metadata",
                return_value={"status": "invalid", "categories": {}, "c2pa": {}},
            ) as inspector:
                controller = install_processing_flow(shell)
                self.assertNotIn(
                    "file_rights_confirmation_required",
                    controller.files_page.validation_issues(),
                )
                build_evidence_report(
                    state,
                    str(source),
                    rights_confirmed=False,
                )
                state.current_step_by_mode[ProjectMode.PROCESSING] = StepId.EVIDENCE
                controller._step_changed(
                    ProjectMode.PROCESSING.value,
                    StepId.EVIDENCE.value,
                )
                self.assertGreaterEqual(inspector.call_count, 1)

    def test_openai_generic_result_is_not_rendered_as_pixel_evidence(self):
        with tempfile.TemporaryDirectory(prefix="evidence-openai-ui-") as temp:
            state, source = self.make_state(temp)
            set_verification_result(
                state,
                str(source),
                "openai",
                "detected",
                "input",
            )
            page = EvidenceCenterPage(
                state,
                lambda: None,
            )

            self.assertNotIn("OpenAI", page.pixel_card.status_label.text())
            self.assertNotIn("detected", page.pixel_card.status_label.text())
            self.assertIn("не pixel evidence", page.openai_status_label.text())
            self.assertIn("signal_type=not_inferred", page.openai_status_label.text())
    def test_official_handoff_opens_url_only_and_never_uploads(self):
        with tempfile.TemporaryDirectory(prefix="evidence-handoff-") as temp:
            state, source = self.make_state(temp)
            opened = []
            page = EvidenceCenterPage(
                state,
                lambda: None,
                url_opener=lambda url: opened.append(url) or True,
            )
            before = file_hash(source)

            page._open_official_service(GEMINI_VERIFY_URL)
            page._open_official_service(OPENAI_VERIFY_URL)

            self.assertEqual(opened, [GEMINI_VERIFY_URL, OPENAI_VERIFY_URL])
            self.assertTrue(all(str(source) not in value for value in opened))
            self.assertEqual(before, file_hash(source))
            self.assertIn("Файл не передан", page.action_status.text())

    def test_normalized_results_survive_project_draft_round_trip(self):
        with tempfile.TemporaryDirectory(prefix="evidence-state-") as temp:
            state, source = self.make_state(temp)
            set_verification_result(
                state,
                str(source),
                "synthid",
                "detected",
                "input",
            )
            set_verification_result(
                state,
                str(source),
                "openai",
                "unsupported",
                "output",
            )

            restored = ProjectState.from_dict(state.to_dict())
            record = restored.processing.verification_records[0]

            self.assertEqual(record.synthid_status, "detected")
            self.assertEqual(record.synthid_stage, "input")
            self.assertEqual(record.openai_status, "unsupported")
            self.assertEqual(record.openai_stage, "not_checked")

    def test_invalid_draft_evidence_fails_closed(self):
        state = ProjectState(mode=ProjectMode.PROCESSING)
        state.processing.selected_files = ["C:/image.png"]
        payload = state.to_dict()
        payload["processing"]["verification_records"] = [
            {
                "file_path": "C:/image.png",
                "synthid_status": "human",
                "synthid_stage": "input",
                "openai_status": "not_verified",
                "openai_stage": "not_checked",
            }
        ]

        with self.assertRaises(ProjectStateError):
            ProjectState.from_dict(payload)

    def test_viewing_does_not_create_dirty_records_and_clear_removes_records(self):
        with tempfile.TemporaryDirectory(prefix="evidence-lifecycle-") as temp:
            state, source = self.make_state(temp)
            shell = AppShell(state)
            controller = install_processing_flow(shell)
            self.assertEqual(state.processing.verification_records, [])

            controller.pages[StepId.EVIDENCE].refresh_from_state()
            self.assertEqual(state.processing.verification_records, [])

            set_verification_result(
                state,
                str(source),
                "synthid",
                "detected",
                "input",
            )
            self.assertEqual(len(state.processing.verification_records), 1)
            controller.files_page.clear_files()
            self.assertEqual(state.processing.verification_records, [])

    def test_old_v3_draft_without_evidence_records_still_loads(self):
        state = ProjectState(mode=ProjectMode.PROCESSING)
        payload = state.to_dict()
        del payload["processing"]["verification_records"]

        restored = ProjectState.from_dict(payload)

        self.assertEqual(restored.processing.verification_records, [])
    def test_export_is_atomic_value_safe_and_path_safe_in_logs(self):
        with tempfile.TemporaryDirectory(prefix="evidence-export-") as temp:
            state, source = self.make_state(temp)
            set_verification_result(
                state,
                str(source),
                "synthid",
                "detected",
                "input",
            )
            state.runtime.kie_upload_path = SECRET_KEY
            destination = Path(temp) / "report.json"

            report = export_evidence_report(
                state,
                str(source),
                destination,
                rights_confirmed=True,
            )
            serialized = destination.read_text(encoding="utf-8")
            log_line = format_evidence_log(report)

            self.assertTrue(destination.is_file())
            self.assertNotIn(str(Path(temp)), serialized)
            self.assertNotIn(SECRET_METADATA, serialized)
            self.assertNotIn(SECRET_PROMPT, serialized)
            self.assertNotIn(SECRET_KEY, serialized)
            self.assertNotIn(str(source), log_line)
            self.assertNotIn(SECRET_METADATA, log_line)
            self.assertIn("human_origin=not_inferred", log_line)
            self.assertIn("removal=not_claimed", log_line)
            self.assertFalse(
                report["verification_handoff"]["gemini"]["auto_upload"]
            )
            self.assertFalse(
                report["verification_handoff"]["openai"]["auto_upload"]
            )

    def test_report_extension_and_unknown_manual_values_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="evidence-invalid-") as temp:
            state, source = self.make_state(temp)
            with self.assertRaises(EvidenceCenterError):
                set_verification_result(
                    state,
                    str(source),
                    "unknown-provider",
                    "detected",
                )
            with self.assertRaises(EvidenceCenterError):
                set_verification_result(
                    state,
                    str(source),
                    "synthid",
                    "human",
                )
            with self.assertRaises(EvidenceCenterError):
                export_evidence_report(
                    state,
                    str(source),
                    Path(temp) / "report.txt",
                    rights_confirmed=True,
                )

    def test_cleanup_options_are_the_existing_pipeline_contract(self):
        state = ProjectState(mode=ProjectMode.PROCESSING)
        operations = state.processing.operations
        operations.remove_exif = True
        operations.remove_embedded_c2pa = True
        operations.preserve_dpi = False

        options = cleanup_options_from_operations(operations)

        self.assertTrue(options.remove_exif)
        self.assertTrue(options.remove_embedded_c2pa)
        self.assertFalse(options.preserve_dpi)


if __name__ == "__main__":
    unittest.main()
