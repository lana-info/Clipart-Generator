import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import main
from result_background_policy import SURFACE_KINDS, keeps_background
from tests.test_local_processing_acceptance import worker_settings
from v3_project_state import PromptEntry
from v3_prompt_generator import normalize_prompt_entries


class ResultBackgroundPolicyTests(unittest.TestCase):
    def test_mixed_batch_cost_excludes_surface_removal(self):
        from v3_project_state import ProjectState
        from v3_clipart_flow import estimate_clipart_cost, fal_endpoint_quantities

        state = ProjectState()
        state.clipart.prompts = [PromptEntry(prompt="flower"), PromptEntry(prompt="tile", result_kind="pattern")]
        state.clipart.generation.variants = 2
        operations = state.clipart.operations
        operations.upscale_before = operations.upscale_after = False
        operations.remove_background = True
        operations.remove_background_provider = "photoroom"
        cost = estimate_clipart_cost(state)
        self.assertEqual(cost.processing_request_count, 2)
        self.assertEqual(str(cost.processing_usd), "0.04")
        operations.remove_background_provider = "fal"
        operations.fal_remove_bg_model = "fal-ai/birefnet/v2"
        self.assertEqual(fal_endpoint_quantities(state)["fal-ai/birefnet/v2"], 2)

    def test_project_file_and_editor_preserve_result_kind(self):
        from PyQt6.QtWidgets import QApplication
        from v3_project_state import ProjectState, save_project_draft, load_project_draft
        from v3_clipart_flow import PromptReferenceEditorDialog

        app = QApplication.instance() or QApplication([])
        state = ProjectState()
        state.clipart.prompts = [PromptEntry(prompt="a tile", result_kind="pattern")]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "project.json"
            save_project_draft(state, path)
            restored = load_project_draft(path)
            entry = restored.clipart.prompts[0]
            self.assertEqual(entry.result_kind, "pattern")
            dialog = PromptReferenceEditorDialog(entry)
            dialog._prompt_edit.setPlainText("revised tile")
            self.assertEqual(dialog.prompt_entry().result_kind, "pattern")
            dialog.close()
        self.assertIsNotNone(app)

    def test_explicit_types_roundtrip_without_inference_from_prompt(self):
        for kind in sorted(SURFACE_KINDS):
            entry = PromptEntry(prompt="a flower", result_kind=kind)
            restored = PromptEntry.from_value(entry.to_dict())
            self.assertEqual(restored.result_kind, kind)
            self.assertEqual(normalize_prompt_entries([restored])[0].result_kind, kind)
            self.assertTrue(keeps_background(kind))
        self.assertEqual(PromptEntry.from_value("seamless pattern").result_kind, "legacy")
        self.assertNotIn("result_kind", PromptEntry(prompt="flower").to_dict())
        with self.assertRaises(ValueError):
            PromptEntry(prompt="flower", result_kind="unknown")

    def test_surface_bypasses_remover_and_edge_cleanup_without_mutating_worker(self):
        for kind in sorted(SURFACE_KINDS):
            for provider in ("local_chroma_key", "kie", "fal", "photoroom", "local_rembg", "local_ben2"):
                with self.subTest(kind=kind, provider=provider), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    source = root / "source.png"
                    Image.new("RGBA", (16, 16), (30, 80, 200, 128)).save(source)
                    original = source.read_bytes()
                    worker = main.WorkerThread("mode2_process", temp, worker_settings(
                        remove_bg=True, remove_bg_provider=provider, edge_shrink_enabled=True,
                        trim_enabled=True,
                    ))
                    with patch.object(worker, "_run_kie_processing_pipeline", side_effect=AssertionError("legacy route")), \
                         patch.object(worker, "_request_with_retries", side_effect=AssertionError("network")), \
                         patch.object(worker, "_edge_shrink_pipeline_step", side_effect=AssertionError("edge")), \
                         patch.object(main, "remove_chroma_key_automatic", side_effect=AssertionError("keyer")):
                        result = worker._run_processing_pipeline(str(source), None, temp, 1, "file", result_kind=kind)
                    self.assertIn(result, (None, str(source)))
                    self.assertEqual(source.read_bytes(), original)
                    self.assertTrue(worker.remove_bg)
                    self.assertTrue(worker.edge_shrink_enabled)
                    target = root / "export.png"
                    worker._save_final_output(result, str(source), str(target), temp, 1, "file")
                    with Image.open(target) as exported, Image.open(source) as original_image:
                        self.assertEqual(exported.size, original_image.size)
                        self.assertEqual(exported.convert("RGBA").tobytes(), original_image.tobytes())

    def test_conflicting_surface_key_fails_before_paid_generation(self):
        with tempfile.TemporaryDirectory() as temp:
            worker = main.WorkerThread("mode1_generate_only", temp, worker_settings())
            entry = {"prompt": "a pattern", "result_kind": "pattern", "chroma_key_color": "green"}
            with patch.object(worker, "_kie_generate_image") as generate:
                with self.assertRaises(ValueError):
                    worker._generate_entry(1, 1, entry, temp, str(Path(temp) / "out.png"), True)
                generate.assert_not_called()

    def test_worker_normalization_preserves_type_and_rejects_unknown(self):
        with tempfile.TemporaryDirectory() as temp:
            worker = main.WorkerThread("mode1_generate_only", temp, worker_settings())
            entry = {"prompt": "a pattern", "result_kind": "pattern"}
            self.assertEqual(worker._normalize_prompt_entries([entry])[0]["result_kind"], "pattern")
            with self.assertRaises(ValueError):
                worker._normalize_prompt_entries([dict(entry, result_kind="future")])
