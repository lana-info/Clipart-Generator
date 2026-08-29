import copy
import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from chroma_benchmark import (
    BenchmarkManifestError,
    evaluate_candidate,
    generate_fixture,
    load_golden_fixture,
    load_manifest,
    run_benchmark,
    score_result,
)
from chroma_key import remove_chroma_key


def benchmark_gates():
    return {
        "minimum_mean_alpha_mae_improvement": 0.2,
        "minimum_improved_cases": 1,
        "maximum_clean_iou_regression": 0.02,
        "maximum_opaque_subject_loss_regression": 0.005,
        "maximum_opaque_rgb_mae_regression": 0.005,
        "maximum_partial_rgb_mae_regression": 0.01,
        "maximum_background_leakage_regression": 0.005,
        "maximum_runtime_multiplier": 1.25,
        "maximum_runtime_seconds": 30.0,
        "maximum_peak_memory_mib": 384.0,
        "maximum_improvement_cycles": 2,
    }


def decision_case(case_id, kind, alpha_iou, alpha_mae, *, key_color="blue"):
    return {
        "id": case_id,
        "kind": kind,
        "key_color": key_color,
        "alpha_iou": alpha_iou,
        "alpha_mae": alpha_mae,
        "opaque_subject_loss": 0.0,
        "opaque_rgb_mae": 0.01,
        "partial_rgb_mae": 0.20,
        "background_leakage": 0.01,
    }


def decision_report(cases, *, elapsed_seconds=24.0, peak_memory_mib=250.0):
    summary_keys = (
        "alpha_mae",
        "alpha_iou",
        "opaque_subject_loss",
        "opaque_rgb_mae",
        "partial_rgb_mae",
        "background_leakage",
    )
    return {
        "schema_version": 1,
        "fixture_size": 256,
        "summary": {
            key: sum(case[key] for case in cases) / len(cases)
            for key in summary_keys
        },
        "performance": {
            "size": 2048,
            "elapsed_seconds": elapsed_seconds,
            "peak_memory_mib": peak_memory_mib,
        },
        "cases": cases,
    }


class ChromaBenchmarkTests(unittest.TestCase):
    def test_score_result_uses_hand_checked_alpha_mae_and_iou(self):
        expected_mask = Image.new("L", (2, 1))
        expected_mask.putdata((0, 255))
        expected_foreground = Image.new("RGB", (2, 1), (10, 20, 30))
        result = Image.new("RGBA", (2, 1))
        result.putdata(((0, 0, 255, 0), (10, 20, 30, 127)))

        metrics = score_result(result, expected_mask, expected_foreground)

        self.assertAlmostEqual(metrics["alpha_mae"], 128 / 510)
        self.assertEqual(metrics["alpha_iou"], 0.0)
        self.assertEqual(metrics["opaque_rgb_mae"], 0.0)

    def test_generate_fixture_has_exact_mask_for_internal_openings(self):
        fixture = generate_fixture(
            {
                "id": "openings",
                "kind": "openings",
                "key_color": "blue",
                "risk": "background remains inside holes",
            },
            size=96,
        )

        self.assertEqual(fixture.input_image.size, (96, 96))
        self.assertEqual(fixture.expected_mask.getextrema(), (0, 255))
        self.assertEqual(fixture.expected_mask.getpixel((48, 48)), 0)
        self.assertEqual(fixture.input_image.getpixel((48, 48))[:3], (0, 0, 255))

    def test_color_spill_keeps_clean_expected_rgb_and_contaminates_only_input_edge(self):
        common = {"key_color": "green", "risk": "edge spill"}
        spill = generate_fixture(
            {"id": "spill", "kind": "color_spill", **common},
            size=128,
        )
        clean = generate_fixture(
            {"id": "clean", "kind": "soft_edge", **common},
            size=128,
        )

        self.assertEqual(
            spill.expected_foreground.tobytes(),
            clean.expected_foreground.tobytes(),
        )
        self.assertEqual(
            spill.input_image.getpixel((64, 64))[:3],
            spill.expected_foreground.getpixel((64, 64)),
        )
        edge_pixels = [
            (x, y)
            for y in range(128)
            for x in range(128)
            if 180 <= spill.expected_mask.getpixel((x, y)) <= 250
        ]
        self.assertTrue(edge_pixels)
        self.assertTrue(
            any(
                spill.input_image.getpixel(point)[:3]
                != clean.input_image.getpixel(point)[:3]
                for point in edge_pixels
            )
        )

    def test_manifest_rejects_duplicate_case_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "quality_gates": benchmark_gates(),
                        "cases": [
                            {
                                "id": "same",
                                "kind": "clean_edge",
                                "key_color": "blue",
                                "risk": "first",
                            },
                            {
                                "id": "same",
                                "kind": "soft_edge",
                                "key_color": "green",
                                "risk": "second",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(BenchmarkManifestError):
                load_manifest(path)

    def test_manifest_rejects_path_traversal_case_id(self):
        payload = {
            "schema_version": 1,
            "quality_gates": benchmark_gates(),
            "cases": [
                {
                    "id": "../../outside",
                    "kind": "clean_edge",
                    "key_color": "blue",
                    "risk": "unsafe path",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(BenchmarkManifestError):
                load_manifest(path)

    def test_manifest_rejects_missing_or_unknown_quality_gate(self):
        payload = {
            "schema_version": 1,
            "quality_gates": benchmark_gates(),
            "cases": [
                {
                    "id": "safe-id",
                    "kind": "clean_edge",
                    "key_color": "blue",
                    "risk": "edge damage",
                }
            ],
        }
        del payload["quality_gates"]["maximum_peak_memory_mib"]
        payload["quality_gates"]["maximum_memory_typo"] = 384
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(BenchmarkManifestError):
                load_manifest(path)

            payload["quality_gates"] = [{"not": "a mapping"}]
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(BenchmarkManifestError):
                load_manifest(path)

    def test_committed_golden_fixture_is_hash_checked_and_not_regenerated(self):
        case = {
            "id": "fixed-golden",
            "kind": "soft_edge",
            "key_color": "red",
            "risk": "soft edge regression",
        }
        fixture = generate_fixture(case, size=64)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            golden = root / "golden"
            paths = {
                "input": golden / "input" / "fixed-golden.png",
                "expected_mask": golden / "expected-mask" / "fixed-golden.png",
                "expected_foreground": golden
                / "expected-foreground"
                / "fixed-golden.png",
            }
            for path in paths.values():
                path.parent.mkdir(parents=True, exist_ok=True)
            fixture.input_image.save(paths["input"])
            fixture.expected_mask.save(paths["expected_mask"])
            fixture.expected_foreground.save(paths["expected_foreground"])
            hashes = {
                name: hashlib.sha256(path.read_bytes()).hexdigest()
                for name, path in paths.items()
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "fixture_size": 64,
                        "performance_size": 96,
                        "quality_gates": benchmark_gates(),
                        "golden_sha256": {"fixed-golden": hashes},
                        "cases": [case],
                    }
                ),
                encoding="utf-8",
            )
            manifest = load_manifest(manifest_path)

            with patch(
                "chroma_benchmark.generate_fixture",
                side_effect=AssertionError("golden must not be regenerated"),
            ):
                loaded = load_golden_fixture(manifest, case)
            self.assertEqual(loaded.input_image.tobytes(), fixture.input_image.tobytes())

            original_generator = generate_fixture

            def performance_only(raw_case, *, size):
                self.assertEqual(size, 96)
                return original_generator(raw_case, size=size)

            with patch("chroma_benchmark.generate_fixture", side_effect=performance_only):
                report = run_benchmark(
                    manifest_path,
                    remove_chroma_key,
                    root / "report",
                    algorithm_name="rgb-distance-baseline",
                )
            self.assertEqual(report["cases"][0]["id"], "fixed-golden")

            paths["expected_mask"].write_bytes(b"changed")
            with self.assertRaises(BenchmarkManifestError):
                load_golden_fixture(manifest, case)

    def test_runner_writes_reproducible_metrics_fixtures_and_contact_sheet(self):
        manifest = {
            "schema_version": 1,
            "fixture_size": 96,
            "performance_size": 128,
            "quality_gates": benchmark_gates(),
            "cases": [
                {
                    "id": "clean",
                    "kind": "clean_edge",
                    "key_color": "blue",
                    "risk": "opaque edge damage",
                },
                {
                    "id": "thin",
                    "kind": "thin_lines",
                    "key_color": "green",
                    "risk": "thin details disappear",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)

            report = run_benchmark(
                manifest,
                remove_chroma_key,
                output,
                algorithm_name="rgb-distance-baseline",
            )

            self.assertEqual(report["schema_version"], 1)
            self.assertEqual([case["id"] for case in report["cases"]], ["clean", "thin"])
            self.assertIn("alpha_mae", report["summary"])
            self.assertGreater(report["performance"]["peak_memory_mib"], 0)
            self.assertIn(
                report["performance"]["memory_measurement"],
                {
                    "isolated_process_peak_rss",
                    "isolated_windows_peak_working_set",
                    "isolated_python_tracemalloc_fallback",
                },
            )
            self.assertEqual(report["performance"]["sample_count"], 3)
            self.assertEqual(len(report["performance"]["elapsed_samples_seconds"]), 3)
            self.assertEqual(report["performance"]["warmup_count"], 1)
            self.assertIn("platform", report["environment"])
            self.assertIn("python", report["environment"])
            self.assertIn("pillow", report["environment"])
            self.assertIn("numpy", report["environment"])
            self.assertIn("git_commit", report["environment"])
            self.assertTrue((output / "baseline_metrics.json").is_file())
            self.assertTrue((output / "baseline-contact-sheet.png").is_file())
            self.assertTrue((output / "fixtures" / "input" / "clean.png").is_file())
            self.assertTrue(
                (output / "fixtures" / "expected-mask" / "thin.png").is_file()
            )

            first_quality = [case["alpha_mae"] for case in report["cases"]]
            repeated = run_benchmark(
                manifest,
                remove_chroma_key,
                output,
                algorithm_name="rgb-distance-baseline",
            )
            self.assertEqual(
                [case["alpha_mae"] for case in repeated["cases"]],
                first_quality,
            )

    def test_cli_runs_real_baseline_and_reports_artifact_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "manifest.json"
            output = root / "report"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "quality_gates": benchmark_gates(),
                        "fixture_size": 64,
                        "performance_size": 64,
                        "cases": [
                            {
                                "id": "soft",
                                "kind": "soft_edge",
                                "key_color": "red",
                                "risk": "soft alpha becomes a hard edge",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                (
                    sys.executable,
                    "scripts/run_chroma_benchmark.py",
                    "--manifest",
                    str(manifest_path),
                    "--output-dir",
                    str(output),
                ),
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("baseline_metrics.json", completed.stdout)
            self.assertIn("baseline-contact-sheet.png", completed.stdout)
            self.assertTrue((output / "baseline_metrics.json").is_file())

    def test_contact_sheet_expected_column_uses_uncontaminated_foreground(self):
        case = {
            "id": "partial",
            "kind": "partial_alpha",
            "key_color": "red",
            "risk": "partial alpha is lost",
        }
        manifest = {
            "schema_version": 1,
            "fixture_size": 64,
            "performance_size": 64,
            "quality_gates": benchmark_gates(),
            "cases": [case],
        }
        fixture = generate_fixture(case, size=64)
        expected = Image.new("RGB", (64, 64), "#c8ced4")
        expected.paste(fixture.expected_foreground, mask=fixture.expected_mask)

        with tempfile.TemporaryDirectory() as directory:
            run_benchmark(
                manifest,
                remove_chroma_key,
                directory,
                algorithm_name="rgb-distance-baseline",
            )
            with Image.open(Path(directory) / "baseline-contact-sheet.png") as sheet:
                expected_column_center = sheet.getpixel((64 + 32, 22 + 32))

        self.assertEqual(expected_column_center, expected.getpixel((32, 32)))

    def test_cli_rejects_invalid_manifest_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "invalid.json"
            manifest_path.write_text('{"schema_version": 99, "cases": []}', encoding="utf-8")

            completed = subprocess.run(
                (
                    sys.executable,
                    "scripts/run_chroma_benchmark.py",
                    "--manifest",
                    str(manifest_path),
                    "--output-dir",
                    str(root / "report"),
                ),
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("schema_version", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)

    def test_golden_update_requires_explicit_confirmation_and_records_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "fixture_size": 64,
                        "performance_size": 64,
                        "quality_gates": benchmark_gates(),
                        "cases": [
                            {
                                "id": "fixed-case",
                                "kind": "soft_edge",
                                "key_color": "blue",
                                "risk": "soft edge regression",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            command = (
                sys.executable,
                "scripts/update_chroma_golden.py",
                "--manifest",
                str(manifest_path),
            )

            refused = subprocess.run(
                command,
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(refused.returncode, 2)
            self.assertFalse((root / "golden").exists())

            updated = subprocess.run(
                (*command, "--yes-update-golden"),
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            self.assertEqual(updated.returncode, 0, updated.stderr)
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            hashes = payload["golden_sha256"]["fixed-case"]
            self.assertEqual(
                set(hashes),
                {"input", "expected_mask", "expected_foreground"},
            )
            self.assertTrue((root / "golden" / "input" / "fixed-case.png").is_file())

    def test_candidate_decision_requires_quality_speed_memory_and_cycle_gates(self):
        baseline = decision_report([
            decision_case("clean", "clean_edge", 1.0, 0.0),
            decision_case("a", "soft_edge", 0.8, 0.2),
            decision_case("b", "thin_lines", 0.8, 0.2),
            decision_case("c", "openings", 0.8, 0.1),
            decision_case("d", "partial_alpha", 0.8, 0.1),
        ])
        candidate = decision_report(
            [
                decision_case("clean", "clean_edge", 0.99, 0.0),
                decision_case("a", "soft_edge", 0.9, 0.1),
                decision_case("b", "thin_lines", 0.9, 0.1),
                decision_case("c", "openings", 0.9, 0.05),
                decision_case("d", "partial_alpha", 0.9, 0.05),
            ],
            elapsed_seconds=20.0,
            peak_memory_mib=300.0,
        )
        gates = benchmark_gates()
        gates["minimum_improved_cases"] = 4

        decision = evaluate_candidate(baseline, candidate, gates, cycle_number=1)

        self.assertTrue(decision["continue"])
        self.assertTrue(all(check["passed"] for check in decision["checks"].values()))

        candidate["performance"]["elapsed_seconds"] = 31.0
        rejected = evaluate_candidate(baseline, candidate, gates, cycle_number=1)
        self.assertFalse(rejected["continue"])
        self.assertFalse(rejected["checks"]["runtime_absolute"]["passed"])

        candidate["performance"]["elapsed_seconds"] = 20.0
        for case in candidate["cases"]:
            case["partial_rgb_mae"] = 1.0
        candidate["summary"]["partial_rgb_mae"] = 1.0
        color_damaged = evaluate_candidate(baseline, candidate, gates, cycle_number=1)
        self.assertFalse(color_damaged["continue"])
        self.assertFalse(color_damaged["checks"]["partial_rgb_mae_regression"]["passed"])

    def test_candidate_rejects_incompatible_or_forged_reports(self):
        baseline = decision_report([
            decision_case("clean", "clean_edge", 1.0, 0.0),
            decision_case("soft", "soft_edge", 0.8, 0.2),
        ])
        candidate = copy.deepcopy(baseline)

        incompatible_reports = []
        wrong_schema = copy.deepcopy(candidate)
        wrong_schema["schema_version"] = 2
        incompatible_reports.append(wrong_schema)
        wrong_fixture_size = copy.deepcopy(candidate)
        wrong_fixture_size["fixture_size"] = 128
        incompatible_reports.append(wrong_fixture_size)
        wrong_performance_size = copy.deepcopy(candidate)
        wrong_performance_size["performance"]["size"] = 1024
        incompatible_reports.append(wrong_performance_size)
        wrong_case_kind = copy.deepcopy(candidate)
        wrong_case_kind["cases"][1]["kind"] = "thin_lines"
        incompatible_reports.append(wrong_case_kind)
        wrong_key_color = copy.deepcopy(candidate)
        wrong_key_color["cases"][1]["key_color"] = "green"
        incompatible_reports.append(wrong_key_color)
        forged_summary = copy.deepcopy(candidate)
        forged_summary["summary"]["alpha_mae"] = 0.001
        incompatible_reports.append(forged_summary)

        for report in incompatible_reports:
            with self.subTest(report=report):
                with self.assertRaises(BenchmarkManifestError):
                    evaluate_candidate(
                        baseline,
                        report,
                        benchmark_gates(),
                        cycle_number=1,
                    )


if __name__ == "__main__":
    unittest.main()
