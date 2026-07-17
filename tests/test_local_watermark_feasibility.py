import ast
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import run_local_watermark_feasibility as feasibility


class LocalWatermarkFeasibilityTests(unittest.TestCase):
    def _model_payload(self, component_name):
        component = feasibility.MODEL_COMPONENTS[component_name]
        return {
            "id": component["model_id"],
            "sha": component["revision"],
            "cardData": {"license": component["api_license"]},
            "siblings": [
                {"rfilename": filename, "size": size}
                for filename, size in component["required_files"].items()
            ],
        }

    def test_manifest_pins_all_upstream_models_and_licenses(self):
        self.assertEqual(
            feasibility.UPSTREAM_COMMIT,
            "190dc89d234fd7e3a61ff755f01251c9c0b87ef0",
        )
        self.assertEqual(
            feasibility.MODEL_COMPONENTS["sdxl"]["license"],
            "CreativeML Open RAIL++-M",
        )
        self.assertEqual(
            feasibility.MODEL_COMPONENTS["controlnet"]["license"], "Apache-2.0"
        )
        self.assertEqual(feasibility.MODEL_COMPONENTS["qwen"]["license"], "Apache-2.0")
        self.assertEqual(feasibility.MODEL_COMPONENTS["fp16_vae"]["license"], "MIT")
        self.assertIn(
            "Open RAIL++-M",
            feasibility.MODEL_COMPONENTS["controlnet"]["combined_pipeline_obligation"],
        )
        self.assertIn(
            "does not resolve inherited SDXL obligations",
            feasibility.MODEL_COMPONENTS["fp16_vae"]["license_caveat"],
        )
        for component in feasibility.MODEL_COMPONENTS.values():
            self.assertEqual(
                sum(component["required_files"].values()),
                component["serialized_weight_bytes"],
            )

    def test_cpu_only_machine_is_a_no_download_production_no_go(self):
        hardware = {
            "total_physical_bytes": 19_275_145_216,
            "available_physical_bytes": 5_222_981_632,
        }
        runtime = {
            "cuda_available": False,
            "xpu_available": False,
            "mps_available": False,
        }

        result = feasibility.assess_feasibility(hardware, runtime)

        self.assertEqual(result["decision"], "local_production_hardware_no_go")
        self.assertFalse(result["production_candidate"])
        self.assertFalse(result["model_downloads_performed"])
        self.assertFalse(result["paid_requests_performed"])
        for pipeline in result["pipelines"].values():
            self.assertEqual(pipeline["status"], "not_run_local_production_no_go")
            self.assertIn("no_supported_accelerator", pipeline["reasons"])
            self.assertEqual(pipeline["model_download_bytes"], 0)
            self.assertEqual(pipeline["detector_result"], "not_verified")
        self.assertEqual(
            result["pipelines"]["sdxl"]["cpu_diagnostic_status"],
            "not_run_resource_risk",
        )
        self.assertEqual(
            result["pipelines"]["qwen"]["cpu_diagnostic_status"],
            "not_run_weights_exceed_total_ram",
        )

    def test_qwen_accepts_the_upstream_xpu_path(self):
        hardware = {
            "total_physical_bytes": 128 * feasibility.GIB,
            "available_physical_bytes": 120 * feasibility.GIB,
        }
        runtime = {
            "cuda_available": False,
            "xpu_available": True,
            "mps_available": False,
        }

        result = feasibility.assess_feasibility(hardware, runtime)

        self.assertEqual(
            result["pipelines"]["sdxl"]["status"],
            "eligible_for_isolated_gpu_benchmark",
        )
        self.assertEqual(
            result["pipelines"]["controlnet"]["status"],
            "eligible_for_isolated_gpu_benchmark",
        )
        self.assertEqual(
            result["pipelines"]["qwen"]["status"],
            "eligible_for_isolated_gpu_benchmark",
        )

    def test_official_model_metadata_verifies_revisions_licenses_and_files(self):
        responses = [
            (self._model_payload(component_name), 1024)
            for component_name in feasibility.MODEL_COMPONENTS
        ]
        with mock.patch.object(
            feasibility, "_fetch_model_metadata", side_effect=responses
        ):
            result = feasibility.verify_model_metadata()

        self.assertEqual(result["status"], "verified")
        self.assertFalse(result["model_weight_downloads_performed"])
        self.assertEqual(set(result["components"]), set(feasibility.MODEL_COMPONENTS))

    def test_official_model_metadata_mismatch_is_rejected(self):
        first = self._model_payload("sdxl")
        first["sha"] = "changed"
        with mock.patch.object(
            feasibility, "_fetch_model_metadata", return_value=(first, 1024)
        ):
            with self.assertRaisesRegex(
                feasibility.FeasibilityError, "does not match Task 42"
            ):
                feasibility.verify_model_metadata()

    def test_model_metadata_url_is_pinned_to_official_https_host(self):
        self.assertEqual(
            feasibility._model_api_url("Qwen/Qwen-Image", "pinned-sha"),
            "https://huggingface.co/api/models/Qwen/Qwen-Image/revision/pinned-sha?blobs=true",
        )

    def test_upstream_model_constants_are_read_with_ast(self):
        with tempfile.TemporaryDirectory(prefix="clipart-task42-ast-") as temp_dir:
            source = Path(temp_dir) / "constants.py"
            source.write_text(
                'DEFAULT_MODEL_ID = "model/base"\nCOMPUTED = str(123)\n',
                encoding="utf-8",
            )

            values = feasibility._literal_assignments(source)

        self.assertEqual(values, {"DEFAULT_MODEL_ID": "model/base"})

    def test_revision_mismatch_is_rejected_before_hardware_probe(self):
        with tempfile.TemporaryDirectory(prefix="clipart-task42-revision-") as temp_dir:
            upstream = Path(temp_dir)
            completed = mock.Mock(returncode=0, stdout="wrong-revision\n")
            with mock.patch.object(
                feasibility.subprocess, "run", return_value=completed
            ):
                with self.assertRaisesRegex(
                    feasibility.FeasibilityError, "revision does not match"
                ):
                    feasibility.verify_upstream(upstream)

    def test_verified_upstream_records_unpinned_model_loader(self):
        with tempfile.TemporaryDirectory(
            prefix="clipart-task42-model-pin-"
        ) as temp_dir:
            upstream = Path(temp_dir)
            source_root = upstream / "src" / "remove_ai_watermarks" / "noai"
            source_root.mkdir(parents=True)
            profile_values = {
                name: value
                for name, value in feasibility.EXPECTED_UPSTREAM_MODEL_CONSTANTS.items()
                if name != "_SDXL_FP16_VAE_ID"
            }
            (source_root / "watermark_profiles.py").write_text(
                "\n".join(
                    f"{name} = {value!r}" for name, value in profile_values.items()
                ),
                encoding="utf-8",
            )
            (source_root / "watermark_remover.py").write_text(
                f"_SDXL_FP16_VAE_ID = {feasibility.EXPECTED_UPSTREAM_MODEL_CONSTANTS['_SDXL_FP16_VAE_ID']!r}\n",
                encoding="utf-8",
            )
            completed = mock.Mock(
                returncode=0, stdout=feasibility.UPSTREAM_COMMIT + "\n"
            )
            clean = mock.Mock(returncode=0, stdout="")
            with mock.patch.object(
                feasibility.subprocess, "run", side_effect=[completed, clean]
            ):
                result = feasibility.verify_upstream(upstream)

        self.assertFalse(result["model_revisions_pinned_by_loader"])
        self.assertTrue(result["working_tree_clean"])

    def test_dirty_upstream_checkout_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="clipart-task42-dirty-") as temp_dir:
            upstream = Path(temp_dir)
            revision = mock.Mock(
                returncode=0, stdout=feasibility.UPSTREAM_COMMIT + "\n"
            )
            dirty = mock.Mock(returncode=0, stdout=" M changed.py\n")
            with mock.patch.object(
                feasibility.subprocess, "run", side_effect=[revision, dirty]
            ):
                with self.assertRaisesRegex(
                    feasibility.FeasibilityError, "checkout is not clean"
                ):
                    feasibility.verify_upstream(upstream)

    def test_cli_writes_report_atomically(self):
        report = {
            "schema": 1,
            "task": 42,
            "assessment": {"decision": "local_production_hardware_no_go"},
        }
        with tempfile.TemporaryDirectory(prefix="clipart-task42-cli-") as temp_dir:
            root = Path(temp_dir)
            output = root / "result.json"
            with mock.patch.object(
                feasibility, "build_report", return_value=report
            ) as build_report:
                with contextlib.redirect_stdout(io.StringIO()):
                    exit_code = feasibility.main(
                        ["--upstream-dir", str(root), "--output", str(output)]
                    )
            saved = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(saved, report)
        build_report.assert_called_once_with(root, verify_remote_models=False)

    def test_default_report_does_not_call_remote_model_verification(self):
        hardware = {
            "total_physical_bytes": 19_275_145_216,
            "available_physical_bytes": 5_222_981_632,
        }
        runtime = {
            "cuda_available": False,
            "xpu_available": False,
            "mps_available": False,
        }
        with (
            mock.patch.object(
                feasibility, "verify_upstream", return_value={"commit": "pinned"}
            ),
            mock.patch.object(
                feasibility, "collect_runtime_snapshot", return_value=runtime
            ),
            mock.patch.object(
                feasibility, "collect_hardware_snapshot", return_value=hardware
            ),
            mock.patch.object(feasibility, "verify_model_metadata") as remote,
        ):
            report = feasibility.build_report(Path("."), verify_remote_models=False)

        remote.assert_not_called()
        self.assertEqual(
            report["model_metadata_verification"]["status"], "not_requested"
        )

    def test_preflight_module_has_no_model_loading_dependencies(self):
        source_path = Path(feasibility.__file__)
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])

        self.assertTrue({"requests", "httpx", "huggingface_hub"}.isdisjoint(imported))
        self.assertNotIn("from_pretrained", source_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
