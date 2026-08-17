import json
import tempfile
import unittest
import pytest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

from scripts import run_reverse_synthid_pilot as pilot


class ReverseSynthIdPilotTests(unittest.TestCase):
    def test_constants_pin_research_license_code_and_safe_model(self):
        self.assertEqual(
            pilot.UPSTREAM_COMMIT,
            "b11083676fd3ee3ff97ce9d03c0e409e46905902",
        )
        self.assertFalse(
            {
                "diffusion_pytorch_model.bin",
                "pytorch_model.bin",
            }
            & set(pilot.VAE_FILE_HASHES)
        )
        self.assertIn(
            "diffusion_pytorch_model.safetensors",
            pilot.VAE_FILE_HASHES,
        )
        self.assertEqual(pilot.PROFILES, ("final", "nuke"))
        self.assertIn(
            "src/extraction/synthid_bypass.py", pilot.UPSTREAM_FILE_HASHES
        )
        self.assertEqual(len(pilot.INPUT_SPECS), 3)

    def test_execution_requires_license_and_ownership_confirmation(self):
        with self.assertRaisesRegex(pilot.PilotError, "license acknowledgement"):
            pilot.build_report(
                upstream=Path("."),
                model_dir=Path("."),
                codebook_path=Path("."),
                input_root=Path("."),
                output_dir=Path("output"),
                execute=True,
                research_license_acknowledged=False,
                ownership_confirmed=True,
            )
        with self.assertRaisesRegex(pilot.PilotError, "ownership"):
            pilot.build_report(
                upstream=Path("."),
                model_dir=Path("."),
                codebook_path=Path("."),
                input_root=Path("."),
                output_dir=Path("output"),
                execute=True,
                research_license_acknowledged=True,
                ownership_confirmed=False,
            )

    def test_upstream_audit_rejects_wrong_revision_before_file_use(self):
        with tempfile.TemporaryDirectory(prefix="m1-upstream-") as temp:
            with mock.patch.object(
                pilot,
                "_run_git",
                return_value="wrong",
            ):
                with self.assertRaisesRegex(pilot.PilotError, "revision"):
                    pilot.audit_upstream(Path(temp))

    @pytest.mark.network
    def test_offline_guard_blocks_connections_and_restores_socket(self):
        original_connect = pilot.socket.socket.connect

        @pilot._offline_only
        def attempt_connection():
            connection = pilot.socket.socket()
            try:
                connection.connect(("127.0.0.1", 9))
            finally:
                connection.close()

        with self.assertRaisesRegex(pilot.PilotError, "Network access is blocked"):
            attempt_connection()
        self.assertIs(pilot.socket.socket.connect, original_connect)
    def test_runtime_audit_rejects_unpinned_dependency(self):
        def version(name):
            if name == "torch":
                return "changed"
            return pilot.RUNTIME_VERSIONS[name]

        with mock.patch.object(pilot.importlib.metadata, "version", side_effect=version):
            with self.assertRaisesRegex(pilot.PilotError, "versions"):
                pilot.audit_runtime()

    def test_validate_inputs_rejects_hash_mismatch(self):
        with tempfile.TemporaryDirectory(prefix="m1-input-") as temp:
            root = Path(temp)
            source = root / pilot.INPUT_SPECS[0]["relative_path"]
            source.parent.mkdir(parents=True)
            Image.new("RGBA", (2, 2), "white").save(source)
            with mock.patch.object(pilot, "INPUT_SPECS", (pilot.INPUT_SPECS[0],)):
                with self.assertRaisesRegex(pilot.PilotError, "manifest"):
                    pilot.validate_inputs(root)

    def test_atomic_copy_removes_temp_file_when_source_open_fails(self):
        with tempfile.TemporaryDirectory(prefix="m1-copy-") as temp:
            root = Path(temp)
            destination = root / "input.png"
            with self.assertRaises(FileNotFoundError):
                pilot._atomic_copy(root / "missing.png", destination, "a" * 64)
            self.assertEqual(list(root.iterdir()), [])

    def test_exact_path_loader_ignores_preloaded_module(self):
        with tempfile.TemporaryDirectory(prefix="m1-module-") as temp:
            module_path = Path(temp) / "pinned_test_module.py"
            module_path.write_text("VALUE = 'pinned'\n", encoding="utf-8")
            previous = pilot.sys.modules.get("pinned_test_module")
            pilot.sys.modules["pinned_test_module"] = mock.Mock(VALUE="wrong")
            try:
                loaded = pilot._module_from_exact_path(
                    "pinned_test_module", module_path
                )
                self.assertEqual(loaded.VALUE, "pinned")
                self.assertEqual(Path(loaded.__file__).resolve(), module_path.resolve())
            finally:
                if previous is None:
                    pilot.sys.modules.pop("pinned_test_module", None)
                else:
                    pilot.sys.modules["pinned_test_module"] = previous

    def test_upstream_context_restores_modules_and_path(self):
        with tempfile.TemporaryDirectory(prefix="m1-context-") as temp:
            upstream = Path(temp) / "upstream"
            extraction = upstream / "src" / "extraction"
            extraction.mkdir(parents=True)
            (extraction / "synthid_bypass.py").write_text(
                "class BypassResult: pass\nclass SpectralCodebook: pass\n",
                encoding="utf-8",
            )
            (extraction / "vae_regen.py").write_text(
                "def load_vae(*args, **kwargs): return object(), 'cpu'\n",
                encoding="utf-8",
            )
            (extraction / "synthid_bypass_v4.py").write_text(
                "import os, sys, numpy as np\n"
                "sys.path.insert(0, os.path.dirname(__file__))\n"
                "from synthid_bypass import BypassResult, SpectralCodebook\n"
                "class SpectralCodebookV4:\n"
                "    def load(self, path): self.path = path\n"
                "class SynthIDBypassV4: pass\n",
                encoding="utf-8",
            )
            codebook = Path(temp) / "safe.npz"
            np.savez(codebook, keys=np.array(["safe"]))
            names = ("synthid_bypass", "vae_regen", "synthid_bypass_v4")
            previous = {name: pilot.sys.modules.get(name) for name in names}
            sentinels = {name: mock.Mock(name=name) for name in names}
            pilot.sys.modules.update(sentinels)
            path_before = list(pilot.sys.path)
            try:
                with pilot._load_upstream(
                    upstream, Path(temp) / "model", codebook
                ) as (bypass, loaded_codebook):
                    self.assertEqual(
                        Path(loaded_codebook.path).resolve(), codebook.resolve()
                    )
                    self.assertEqual(type(bypass).__name__, "SynthIDBypassV4")
                    self.assertIsNot(
                        pilot.sys.modules["synthid_bypass_v4"],
                        sentinels["synthid_bypass_v4"],
                    )
                self.assertEqual(pilot.sys.path, path_before)
                for name in names:
                    self.assertIs(pilot.sys.modules[name], sentinels[name])
            finally:
                for name, module in previous.items():
                    if module is None:
                        pilot.sys.modules.pop(name, None)
                    else:
                        pilot.sys.modules[name] = module
    def test_safe_codebook_rejects_object_arrays_without_unpickling(self):
        with tempfile.TemporaryDirectory(prefix="m1-codebook-") as temp:
            codebook = Path(temp) / "unsafe.npz"
            np.savez(
                codebook,
                format_version=np.array(4),
                keys=np.array(["profile"], dtype=object),
            )
            with (
                mock.patch.object(pilot, "SAFE_CODEBOOK_SHA256", pilot.sha256_file(codebook)),
                mock.patch.object(pilot, "SAFE_CODEBOOK_BYTES", codebook.stat().st_size),
            ):
                with self.assertRaisesRegex(pilot.PilotError, "safe loading"):
                    pilot.audit_safe_codebook(codebook)
    def test_output_directory_must_be_empty(self):
        with tempfile.TemporaryDirectory(prefix="m1-output-") as temp:
            output = Path(temp)
            (output / "existing.txt").write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(pilot.PilotError, "new or empty"):
                pilot.prepare_run_directory(output, [])
            self.assertEqual(
                (output / "existing.txt").read_text(encoding="utf-8"),
                "keep",
            )

    def test_analyze_output_separates_alpha_and_fidelity_metrics(self):
        with tempfile.TemporaryDirectory(prefix="m1-metrics-") as temp:
            root = Path(temp)
            source = root / "source.png"
            output = root / "output.png"
            source_pixels = np.zeros((4, 4, 4), dtype=np.uint8)
            source_pixels[:, :, :3] = 100
            source_pixels[:, :, 3] = 0
            source_pixels[1:3, 1:3, 3] = 255
            Image.fromarray(source_pixels, "RGBA").save(source)
            Image.new("RGB", (4, 4), (101, 101, 101)).save(output)

            metrics = pilot.analyze_output(source, output)

            self.assertEqual(metrics["source_mode"], "RGBA")
            self.assertEqual(metrics["output_mode"], "RGB")
            self.assertGreater(metrics["alpha_changed_pixel_ratio"], 0)
            self.assertEqual(metrics["output_transparent_pixels"], 0)
            self.assertAlmostEqual(metrics["alpha_iou"], 0.25)
            self.assertIn("global_ssim_luma", metrics)
            self.assertIn("output_sha256", metrics)

    def test_secure_repeat_report_compares_pinned_output_and_preserves_source(self):
        source_record = {
            "id": "O1",
            "source_path": Path("private/source.png"),
            "sha256": "a" * 64,
            "bytes": 1,
            "size": [1, 1],
            "mode": "RGB",
            "ownership": "user_owned_documented",
            "independent_scene": True,
        }
        copied_record = {**source_record, "copied_path": Path("private/copy.png")}
        run = {
            "input_id": "O1",
            "input_sha256": "a" * 64,
            "output_sha256": pilot.RECORDED_O1_FINAL["output_sha256"],
            "metrics": {
                "psnr_rgb_db": pilot.RECORDED_O1_FINAL["psnr_rgb_db"],
                "global_ssim_luma": pilot.RECORDED_O1_FINAL["global_ssim_luma"],
            },
            "processing": {"status": "succeeded"},
            "pixel_evidence": {"output": "not_verified"},
        }
        with (
            mock.patch.object(pilot, "audit_upstream", return_value={"commit": "pinned"}),
            mock.patch.object(pilot, "audit_model", return_value={"revision": "pinned"}),
            mock.patch.object(pilot, "audit_safe_codebook", return_value={"sha256": "safe"}),
            mock.patch.object(pilot, "audit_runtime", return_value={"environment": "venv"}),
            mock.patch.object(pilot, "validate_inputs", return_value=[source_record]),
            mock.patch.object(pilot, "prepare_run_directory", return_value=[copied_record]),
            mock.patch.object(pilot, "execute_secure_repeat", return_value=run),
            mock.patch.object(pilot, "sha256_file", return_value="a" * 64),
        ):
            report = pilot.build_secure_repeat_report(
                upstream=Path("."),
                model_dir=Path("."),
                codebook_path=Path("."),
                input_root=Path("."),
                output_dir=Path("output"),
                research_license_acknowledged=True,
                ownership_confirmed=True,
            )

        self.assertTrue(report["comparison"]["comparable"])
        self.assertTrue(report["comparison"]["output_sha256_equal"])
        self.assertTrue(report["source_hash_unchanged"])
        self.assertEqual(report["processing"], "succeeded")
        self.assertEqual(report["pixel_evidence"], "not_verified")
        self.assertFalse(report["execution_trust_boundary"]["pickle_allowed"])
        self.assertFalse(report["execution_trust_boundary"]["os_filesystem_sandbox"])
        self.assertNotIn("source_path", json.dumps(report))
        self.assertNotIn("copied_path", json.dumps(report))

    def test_secure_repeat_requires_both_execution_acknowledgements(self):
        arguments = {
            "upstream": Path("."),
            "model_dir": Path("."),
            "codebook_path": Path("."),
            "input_root": Path("."),
            "output_dir": Path("output"),
        }
        with self.assertRaisesRegex(pilot.PilotError, "license acknowledgement"):
            pilot.build_secure_repeat_report(
                **arguments,
                research_license_acknowledged=False,
                ownership_confirmed=True,
            )
        with self.assertRaisesRegex(pilot.PilotError, "ownership"):
            pilot.build_secure_repeat_report(
                **arguments,
                research_license_acknowledged=True,
                ownership_confirmed=False,
            )
    def test_report_keeps_processing_and_pixel_evidence_separate(self):
        source_records = [
            {
                "id": "O1",
                "source_path": Path("private/source.png"),
                "sha256": "a" * 64,
                "bytes": 1,
                "size": [1, 1],
                "mode": "RGB",
                "ownership": "user_owned_documented",
                "independent_scene": True,
            }
        ]
        copied_records = [
            {
                **source_records[0],
                "copied_path": Path("private/copy.png"),
            }
        ]
        with (
            mock.patch.object(pilot, "audit_upstream", return_value={"commit": "pinned"}),
            mock.patch.object(pilot, "audit_model", return_value={"revision": "pinned"}),
            mock.patch.object(
                pilot, "audit_safe_codebook", return_value={"sha256": "pinned"}
            ),
            mock.patch.object(pilot, "audit_runtime", return_value={"environment": "venv"}),
            mock.patch.object(pilot, "validate_inputs", return_value=source_records),
            mock.patch.object(
                pilot,
                "prepare_run_directory",
                return_value=copied_records,
            ),
            mock.patch.object(pilot, "sha256_file", return_value="a" * 64),
        ):
            report = pilot.build_report(
                upstream=Path("."),
                model_dir=Path("."),
                codebook_path=Path("."),
                input_root=Path("."),
                output_dir=Path("output"),
                execute=False,
                research_license_acknowledged=False,
                ownership_confirmed=False,
            )

        self.assertEqual(report["processing"], "not_run")
        self.assertEqual(report["pixel_evidence"], "not_verified")
        self.assertFalse(report["production_integration_allowed"])
        self.assertNotIn("source_path", json.dumps(report))
        self.assertNotIn("copied_path", json.dumps(report))

    def test_committed_report_is_linked_and_path_safe(self):
        report_path = Path(__file__).resolve().parents[1] / "benchmark_synthid_m1.pilot.json"
        report_text = report_path.read_text(encoding="utf-8")
        report = json.loads(report_text)

        inputs = {item["id"]: item for item in report["inputs"]}
        self.assertEqual(len(report["runs"]), pilot.MAX_RUNS)
        self.assertTrue(report["source_hashes_unchanged"])
        self.assertEqual(report["processing"], "succeeded")
        self.assertEqual(report["pixel_evidence"], "not_verified")
        self.assertFalse(report["production_integration_allowed"])
        self.assertIn(
            "src/extraction/synthid_bypass.py",
            report["upstream"]["audited_files"],
        )
        self.assertTrue(
            report["recorded_run_trust_boundary"]["original_codebook_used_allow_pickle"]
        )
        self.assertFalse(report["post_review_hardening"]["used_for_recorded_runs"])
        for run in report["runs"]:
            self.assertEqual(run["input_sha256"], inputs[run["input_id"]]["sha256"])
            self.assertEqual(len(run["output_sha256"]), 64)
            self.assertTrue(run["parameters"])
            self.assertIn("profile_key", run["upstream_result"]["details"])
            self.assertIn("exact_match", run["upstream_result"]["details"])
            self.assertIn("n_vae_passes", run["upstream_result"]["details"])
            self.assertTrue(run["upstream_result"]["stages_applied"])
            self.assertEqual(run["processing"]["status"], "succeeded")
            self.assertEqual(run["pixel_evidence"]["output"], "not_verified")
        self.assertNotIn("D:\\", report_text)
        self.assertNotIn("C:\\Users", report_text)

    def test_gemini_handoff_is_complete_but_closed_without_consent(self):
        root = Path(__file__).resolve().parents[1]
        handoff_path = root / "benchmark_synthid_m1.gemini_handoff.json"
        handoff_text = handoff_path.read_text(encoding="utf-8")
        handoff = json.loads(handoff_text)

        self.assertEqual(handoff["status"], "prepared_explicit_consent_pending")
        self.assertFalse(handoff["external_transfer_performed"])
        self.assertFalse(handoff["explicit_user_consent"])
        self.assertEqual(handoff["scope"]["files"], 9)
        self.assertEqual(len(handoff["items"]), 9)
        self.assertTrue(handoff["scope"]["one_file_per_check"])
        self.assertTrue(handoff["scope"]["collages_forbidden"])
        self.assertEqual(
            handoff["capture_policy"]["allowed_statuses"],
            ["detected", "not_detected", "unsupported"],
        )
        self.assertTrue(all(item["pixel_evidence"] == "not_verified" for item in handoff["items"]))
        self.assertEqual(len({item["id"] for item in handoff["items"]}), 9)
        self.assertTrue(all(len(item["sha256"]) == 64 for item in handoff["items"]))
        self.assertNotIn("D:\\", handoff_text)
        self.assertNotIn("C:\\Users", handoff_text)
    def test_task11_documents_have_no_hidden_control_characters(self):
        root = Path(__file__).resolve().parents[1]
        for name in (
            "M1_REVERSE_SYNTHID_PILOT_2026-07-26.md",
            "M1_GEMINI_HANDOFF.ru.md",
            "SYNTHID_3_METHOD_BENCHMARK.ru.md",
            "benchmark_synthid_m1.gemini_handoff.json",
        ):
            text = (root / name).read_text(encoding="utf-8-sig")
            hidden = [char for char in text if ord(char) < 32 and char not in "\n\r\t"]
            self.assertEqual(hidden, [], name)
    def test_atomic_json_replaces_complete_document(self):
        with tempfile.TemporaryDirectory(prefix="m1-json-") as temp:
            path = Path(temp) / "manifest.json"
            pilot._atomic_json(path, {"schema": 1, "value": "first"})
            pilot._atomic_json(path, {"schema": 1, "value": "second"})
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["value"],
                "second",
            )
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_pilot_has_hard_run_limit(self):
        self.assertEqual(
            len(pilot.INPUT_SPECS) * len(pilot.PROFILES) + 1,
            pilot.MAX_RUNS,
        )


if __name__ == "__main__":
    unittest.main()
