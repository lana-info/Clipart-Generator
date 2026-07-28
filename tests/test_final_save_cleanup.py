import json
import os
import shutil
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, PngImagePlugin


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import main
from metadata_cleanup import MetadataCleanupError, cleanup_image_metadata
from metadata_inspector import inspect_image_metadata
from tests.test_c2pa_inspector import add_png_chunk_after_ihdr, c2pa_jumbf


SECRET_METADATA_VALUE = "metadata-value-must-never-reach-progress-log"
XMP_PACKET = """<x:xmpmeta xmlns:x="adobe:ns:meta/"
    xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    xmlns:custom="https://example.invalid/final-save/">
  <rdf:RDF><rdf:Description custom:Keep="safe-fixture-value" /></rdf:RDF>
</x:xmpmeta>"""


def worker_settings(**overrides):
    settings = {
        "kie_api_key": "",
        "upscale": False,
        "upscale_after": False,
        "unsharp_enabled": False,
        "remove_bg": False,
        "trim_enabled": False,
        "edge_shrink_enabled": False,
        "cleanup_remove_exif": False,
        "cleanup_remove_xmp": False,
        "cleanup_remove_iptc": False,
        "cleanup_remove_comments_text": False,
        "cleanup_remove_embedded_thumbnail": False,
        "cleanup_remove_generator_fields": False,
        "cleanup_remove_embedded_c2pa": False,
        "cleanup_preserve_icc": True,
        "cleanup_preserve_dpi": True,
    }
    settings.update(overrides)
    return settings


def create_source(path, *, metadata=False, bordered=False, dpi=(300, 300)):
    if bordered:
        image = Image.new("RGBA", (18, 14), (0, 0, 0, 0))
        image.paste((30, 90, 150, 255), (3, 2, 15, 12))
    else:
        image = Image.new("RGBA", (18, 14), (30, 90, 150, 175))
    if not metadata:
        image.save(path, format="PNG")
        return
    pnginfo = PngImagePlugin.PngInfo()
    pnginfo.add_text("Comment", SECRET_METADATA_VALUE)
    pnginfo.add_itxt("XML:com.adobe.xmp", XMP_PACKET)
    image.save(
        path,
        format="PNG",
        pnginfo=pnginfo,
        icc_profile=b"fixture-icc-profile",
        dpi=dpi,
    )


def image_signature(path):
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        return rgba.size, rgba.tobytes()


class FinalSaveCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = main.QApplication.instance() or main.QApplication([])

    def test_selected_cleanup_is_atomic_and_logs_value_safe_summary(self):
        with tempfile.TemporaryDirectory(prefix="clipart-final-cleanup-") as temp_dir:
            temp_path = Path(temp_dir)
            stage_path = temp_path / "stage.png"
            output_path = temp_path / "output.png"
            create_source(stage_path, metadata=True)
            source_signature = image_signature(stage_path)

            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                worker_settings(cleanup_remove_comments_text=True),
            )
            progress = []
            worker.progress.connect(progress.append)
            result = worker._publish_final_output(str(stage_path), str(output_path))

            self.assertEqual(result["status"], "ok")
            self.assertEqual(image_signature(output_path), source_signature)
            inspection = inspect_image_metadata(output_path)
            self.assertFalse(inspection["categories"]["comments_text"]["present"])
            self.assertTrue(inspection["categories"]["xmp"]["present"])
            self.assertTrue(inspection["categories"]["icc_profile"]["present"])
            self.assertTrue(inspection["categories"]["dpi"]["present"])

            joined_log = "\n".join(progress)
            for heading in ("найдено", "удалено", "сохранено", "не поддерживается", "не выполнено"):
                self.assertIn(f"Очистка файла: {heading}", joined_log)
            self.assertNotIn(SECRET_METADATA_VALUE, joined_log)

    def test_cleanup_failure_preserves_previous_output_and_removes_stage(self):
        with tempfile.TemporaryDirectory(prefix="clipart-final-cleanup-failure-") as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.png"
            output_dir = temp_path / "output"
            raw_dir = temp_path / "raw"
            output_dir.mkdir()
            raw_dir.mkdir()
            output_path = output_dir / "result.png"
            create_source(source_path)
            previous_output = b"previous-output-must-survive"
            output_path.write_bytes(previous_output)

            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                worker_settings(cleanup_remove_exif=True),
            )
            progress = []
            worker.progress.connect(progress.append)
            with patch.object(
                main,
                "cleanup_image_metadata",
                side_effect=MetadataCleanupError("simulated cleanup failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "Очистка файла не выполнена"):
                    worker._save_final_output(
                        None,
                        str(source_path),
                        str(output_path),
                        str(raw_dir),
                        1,
                        "file",
                    )

            self.assertEqual(output_path.read_bytes(), previous_output)
            self.assertFalse(list(output_dir.glob(".clipart-final-*.stage.png")))
            self.assertIn("итог не опубликован", "\n".join(progress))

    def test_process_only_cleanup_preserves_unselected_source_metadata(self):
        with tempfile.TemporaryDirectory(prefix="clipart-final-cleanup-process-only-") as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.png"
            create_source(source_path, metadata=True)
            source_bytes = source_path.read_bytes()
            source_signature = image_signature(source_path)

            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                worker_settings(cleanup_remove_comments_text=True),
                selected_files=[str(source_path)],
            )
            worker._mode2_process_files(emit_final=False)

            outputs = list((temp_path / "output").glob("*.png"))
            self.assertEqual(len(outputs), 1)
            self.assertEqual(image_signature(outputs[0]), source_signature)
            inspection = inspect_image_metadata(outputs[0])
            self.assertFalse(inspection["categories"]["comments_text"]["present"])
            self.assertTrue(inspection["categories"]["xmp"]["present"])
            self.assertTrue(inspection["categories"]["icc_profile"]["present"])
            self.assertTrue(inspection["categories"]["dpi"]["present"])
            self.assertEqual(source_path.read_bytes(), source_bytes)
            self.assertFalse(list((temp_path / "raw").glob("*")))

    def test_trim_runs_before_cleanup_and_carries_supported_metadata(self):
        with tempfile.TemporaryDirectory(prefix="clipart-final-cleanup-trim-") as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.png"
            create_source(source_path, metadata=True, bordered=True)

            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                worker_settings(
                    trim_enabled=True,
                    cleanup_remove_comments_text=True,
                ),
                selected_files=[str(source_path)],
            )
            worker._mode2_process_files(emit_final=False)

            output_path = next((temp_path / "output").glob("*.png"))
            with Image.open(output_path) as output:
                self.assertEqual(output.size, (12, 10))
            inspection = inspect_image_metadata(output_path)
            self.assertFalse(inspection["categories"]["comments_text"]["present"])
            self.assertTrue(inspection["categories"]["xmp"]["present"])
            self.assertTrue(inspection["categories"]["icc_profile"]["present"])
            self.assertTrue(inspection["categories"]["dpi"]["present"])

    def test_print_export_keeps_300_dpi_as_final_authority(self):
        with tempfile.TemporaryDirectory(prefix="clipart-final-cleanup-dpi-") as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.png"
            create_source(source_path, metadata=True, dpi=(144, 144))

            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                worker_settings(
                    export_300_dpi=True,
                    cleanup_remove_comments_text=True,
                    cleanup_preserve_dpi=False,
                ),
                selected_files=[str(source_path)],
            )
            self.assertTrue(worker.metadata_cleanup_options.preserve_dpi)
            worker._mode2_process_files(emit_final=False)

            output_path = next((temp_path / "output").glob("*.png"))
            with Image.open(output_path) as output:
                self.assertAlmostEqual(output.info["dpi"][0], 300, delta=0.1)
                self.assertAlmostEqual(output.info["dpi"][1], 300, delta=0.1)
            inspection = inspect_image_metadata(output_path)
            self.assertFalse(inspection["categories"]["comments_text"]["present"])
            self.assertTrue(inspection["categories"]["xmp"]["present"])
            self.assertTrue(inspection["categories"]["icc_profile"]["present"])

    def test_trim_cannot_hide_c2pa_before_explicit_cleanup(self):
        with tempfile.TemporaryDirectory(prefix="clipart-final-cleanup-c2pa-") as temp_dir:
            root = Path(temp_dir)
            source_path = root / "source.png"
            create_source(source_path, bordered=True)
            add_png_chunk_after_ihdr(source_path, b"caBX", c2pa_jumbf())

            rejected_dir = root / "rejected"
            rejected_dir.mkdir()
            rejected_source = rejected_dir / "source.png"
            shutil.copyfile(source_path, rejected_source)
            rejected_worker = main.WorkerThread(
                "mode2_process",
                str(rejected_dir),
                worker_settings(
                    trim_enabled=True,
                    cleanup_remove_comments_text=True,
                ),
                selected_files=[str(rejected_source)],
            )
            rejected_progress = []
            rejected_worker.progress.connect(rejected_progress.append)
            rejected_worker._mode2_process_files(emit_final=False)
            rejected_log = "\n".join(rejected_progress)
            self.assertIn("C2PA input requires explicit C2PA cleanup", rejected_log)
            self.assertIn("итог не опубликован", rejected_log)
            self.assertFalse(list((rejected_dir / "output").glob("*.png")))

            accepted_dir = root / "accepted"
            accepted_dir.mkdir()
            accepted_source = accepted_dir / "source.png"
            shutil.copyfile(source_path, accepted_source)
            accepted_worker = main.WorkerThread(
                "mode2_process",
                str(accepted_dir),
                worker_settings(
                    trim_enabled=True,
                    cleanup_remove_embedded_c2pa=True,
                ),
                selected_files=[str(accepted_source)],
            )
            accepted_progress = []
            accepted_worker.progress.connect(accepted_progress.append)
            accepted_worker._mode2_process_files(emit_final=False)

            output_path = next((accepted_dir / "output").glob("*.png"))
            inspection = inspect_image_metadata(output_path)
            self.assertEqual(inspection["c2pa"]["presence"], "not_present")
            self.assertIn("удалено — встроенный C2PA", "\n".join(accepted_progress))

    def test_palette_transparency_survives_trim_and_cleanup_staging(self):
        with tempfile.TemporaryDirectory(prefix="clipart-final-cleanup-palette-") as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.png"
            palette = Image.new("P", (8, 8), 0)
            palette.putpalette([0, 0, 0, 220, 60, 120] + [0, 0, 0] * 254)
            for y in range(2, 6):
                for x in range(2, 6):
                    palette.putpixel((x, y), 1)
            pnginfo = PngImagePlugin.PngInfo()
            pnginfo.add_text("Comment", SECRET_METADATA_VALUE)
            palette.save(source_path, format="PNG", transparency=0, pnginfo=pnginfo)

            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                worker_settings(
                    trim_enabled=True,
                    cleanup_remove_comments_text=True,
                ),
                selected_files=[str(source_path)],
            )
            worker._mode2_process_files(emit_final=False)

            output_path = next((temp_path / "output").glob("*.png"))
            with Image.open(output_path) as output:
                self.assertEqual(output.size, (4, 4))
                self.assertEqual(output.mode, "RGBA")
                self.assertEqual(output.getchannel("A").getextrema(), (255, 255))

    def test_disabled_cleanup_matches_legacy_writer_and_skips_inspection(self):
        with tempfile.TemporaryDirectory(prefix="clipart-final-cleanup-disabled-") as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.png"
            output_dir = temp_path / "output"
            raw_dir = temp_path / "raw"
            output_dir.mkdir()
            raw_dir.mkdir()
            expected_path = temp_path / "expected.png"
            output_path = output_dir / "result.png"
            create_source(source_path)

            worker = main.WorkerThread("mode2_process", temp_dir, worker_settings())
            worker._save_image_as_png(str(source_path), str(expected_path))
            with (
                patch.object(main, "inspect_image_metadata") as inspect_mock,
                patch.object(main, "cleanup_image_metadata") as cleanup_mock,
            ):
                worker._save_final_output(
                    None,
                    str(source_path),
                    str(output_path),
                    str(raw_dir),
                    1,
                    "file",
                )

            inspect_mock.assert_not_called()
            cleanup_mock.assert_not_called()
            self.assertEqual(output_path.read_bytes(), expected_path.read_bytes())
            self.assertFalse(list(output_dir.glob(".clipart-final-*.stage.png")))

    def test_generate_process_local_and_mixed_outputs_use_shared_cleanup(self):
        with tempfile.TemporaryDirectory(prefix="clipart-final-cleanup-routes-") as temp_dir:
            root = Path(temp_dir)
            fixture = root / "fixture.png"
            create_source(fixture, metadata=True)

            with patch.object(main, "cleanup_image_metadata", wraps=cleanup_image_metadata) as cleanup_mock:
                for process_generated in (False, True):
                    case_dir = root / f"generate-{process_generated}"
                    case_dir.mkdir()
                    worker = main.WorkerThread(
                        "mode1_generate_only",
                        str(case_dir),
                        worker_settings(
                            kie_api_key="test-key",
                            cleanup_remove_comments_text=True,
                        ),
                        generated_prompts=["fixture prompt"],
                    )
                    worker._kie_generate_image = types.MethodType(
                        lambda worker_self, prompt, references=None: "mock://generated",
                        worker,
                    )
                    worker._download_file = types.MethodType(
                        lambda worker_self, url, output_path: shutil.copyfile(fixture, output_path),
                        worker,
                    )
                    before_calls = cleanup_mock.call_count
                    worker._mode1_generate(process_generated=process_generated, emit_final=False)
                    self.assertEqual(cleanup_mock.call_count, before_calls + 1)
                    self.assertEqual(len(list((case_dir / "output").glob("*.png"))), 1)

                local_dir = root / "process-local"
                local_dir.mkdir()
                local_source = local_dir / "source.png"
                shutil.copyfile(fixture, local_source)
                local_worker = main.WorkerThread(
                    "mode2_process",
                    str(local_dir),
                    worker_settings(
                        unsharp_enabled=True,
                        cleanup_remove_comments_text=True,
                    ),
                    selected_files=[str(local_source)],
                )
                before_calls = cleanup_mock.call_count
                local_worker._mode2_process_files(emit_final=False)
                self.assertEqual(cleanup_mock.call_count, before_calls + 1)

                mixed_dir = root / "process-mixed"
                mixed_dir.mkdir()
                mixed_source = mixed_dir / "source.png"
                shutil.copyfile(fixture, mixed_source)
                mixed_worker = main.WorkerThread(
                    "mode2_process",
                    str(mixed_dir),
                    worker_settings(
                        kie_api_key="test-key",
                        upscale=True,
                        upscale_provider="local_realesrgan",
                        remove_bg=True,
                        remove_bg_provider="kie",
                        cleanup_remove_comments_text=True,
                    ),
                    selected_files=[str(mixed_source)],
                )
                mixed_worker._run_processing_pipeline = types.MethodType(
                    lambda worker_self, *args, **kwargs: "mock://mixed-result",
                    mixed_worker,
                )
                mixed_worker._download_file = types.MethodType(
                    lambda worker_self, url, output_path: shutil.copyfile(fixture, output_path),
                    mixed_worker,
                )
                before_calls = cleanup_mock.call_count
                mixed_worker._mode2_process_files(emit_final=False)
                self.assertEqual(cleanup_mock.call_count, before_calls + 1)

            self.assertEqual(cleanup_mock.call_count, 4)

    def test_process_only_cleanup_can_start_without_kie_or_other_steps(self):
        with tempfile.TemporaryDirectory(prefix="clipart-final-cleanup-ui-") as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.png"
            create_source(source_path)
            config_path = temp_path / "config.json"
            config_path.write_text(json.dumps({"upscale": False}), encoding="utf-8")

            with (
                patch.object(main, "CONFIG_FILE", str(config_path)),
                patch.object(main, "ENV_FILE", str(temp_path / ".env")),
                patch.object(main, "PROMPTS_STORAGE_FILE", str(temp_path / "prompts.json")),
                patch.object(main, "LICENSE_CACHE_FILE", str(temp_path / "license.json")),
                patch.object(main.MainWindow, "_migrate_legacy_local_files", return_value=None),
                patch.object(main.QTimer, "singleShot"),
                patch.object(main.WorkerThread, "start", autospec=True) as start_mock,
                patch.object(main.QMessageBox, "warning") as warning_mock,
            ):
                window = main.MainWindow()
                window.work_dir = temp_dir
                window.selected_files = [str(source_path)]
                window.radio_run_process.setChecked(True)
                window.chk_upscale.setChecked(False)
                window.chk_upscale_after.setChecked(False)
                window.chk_unsharp.setChecked(False)
                window.chk_remove_bg.setChecked(False)
                window.chk_edge_shrink.setChecked(False)
                window.chk_trim.setChecked(False)
                window.chk_export_300_dpi.setChecked(True)
                self.assertFalse(window._cleanup_requested_from_ui())
                window.chk_export_300_dpi.setChecked(False)
                window.chk_cleanup_all.setChecked(True)
                window.kie_api_key_input.setText("")

                window.start_work()

                warning_mock.assert_not_called()
                start_mock.assert_called_once()
                self.assertTrue(window.worker.metadata_cleanup_options.remove_exif)
                self.assertFalse(window.worker.kie_api_key)
                window.settings_save_timer.stop()
                window.api_key_mask_timer.stop()
                window.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
