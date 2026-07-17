import base64
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from decimal import Decimal
from pathlib import Path
from unittest import mock

from PIL import Image

from scripts import run_managed_fidelity_benchmark as benchmark


class ManagedFidelityBenchmarkTests(unittest.TestCase):
    def _image(self, path: Path, *, mode: str = "RGBA") -> bytes:
        color = (20, 30, 40, 255) if mode == "RGBA" else (20, 30, 40)
        Image.new(mode, (16, 16), color).save(path, format="PNG")
        return path.read_bytes()

    def test_candidate_suite_targets_editors_and_fits_total_budget(self):
        models = {candidate["model"] for candidate in benchmark.CANDIDATES.values()}
        providers = {candidate["provider"] for candidate in benchmark.CANDIDATES.values()}
        reserved = sum(
            (candidate["reservation_cost_usd"] for candidate in benchmark.CANDIDATES.values()),
            benchmark.TASK40_REPORTED_SPEND_USD,
        )

        self.assertEqual(
            models,
            {
                "bytedance-seed/seedream-4.5",
                "sourceful/riverflow-v2.5-pro",
            },
        )
        self.assertNotIn("google", providers)
        self.assertNotIn("openai", providers)
        self.assertEqual(reserved, Decimal("0.245"))
        self.assertLessEqual(reserved, benchmark.TOTAL_TEST_BUDGET_USD)

    def test_payload_pins_provider_and_requests_minimal_visible_change(self):
        with tempfile.TemporaryDirectory(prefix="clipart-task41-payload-") as temp_dir:
            source = Path(temp_dir) / "source.png"
            self._image(source)

            payload = benchmark.build_request_payload("seedream-4.5", source)

        self.assertEqual(payload["model"], "bytedance-seed/seedream-4.5")
        self.assertEqual(payload["provider"], {"only": ["seed"], "allow_fallbacks": False})
        self.assertEqual(payload["n"], 1)
        self.assertEqual(payload["resolution"], "1K")
        self.assertIn("smallest perceptible change", payload["prompt"])
        self.assertIn("exact same subject identity and face", payload["prompt"])
        self.assertTrue(
            payload["input_references"][0]["image_url"]["url"].startswith(
                "data:image/png;base64,"
            )
        )

    def test_rgb_default_retry_removes_alpha_and_optional_parameters(self):
        with tempfile.TemporaryDirectory(prefix="clipart-task41-rgb-payload-") as temp_dir:
            source = Path(temp_dir) / "source.png"
            self._image(source)

            payload = benchmark.build_request_payload(
                "seedream-4.5-rgb-defaults",
                source,
            )

        encoded = payload["input_references"][0]["image_url"]["url"].split(",", 1)[1]
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as image:
            mode = image.mode
        self.assertEqual(mode, "RGB")
        self.assertNotIn("resolution", payload)
        self.assertNotIn("aspect_ratio", payload)

    def test_closed_gate_performs_no_preflight_or_paid_request(self):
        with tempfile.TemporaryDirectory(prefix="clipart-task41-closed-") as temp_dir:
            root = Path(temp_dir)
            source = root / "source.png"
            output = root / "output.provider"
            state = root / "state.json"
            self._image(source)
            with mock.patch.dict(
                os.environ, {"OPENROUTER_API_KEY": "test-secret"}
            ), mock.patch.object(
                benchmark, "fetch_endpoint_snapshot"
            ) as preflight, mock.patch.object(benchmark, "_request_image") as request_image:
                with self.assertRaisesRegex(
                    benchmark.ManagedFidelityBenchmarkError, "closed for this candidate"
                ):
                    benchmark.run_live_generation(
                        "seedream-4.5",
                        source,
                        output,
                        state_path=state,
                        authorized_candidates=(),
                    )

        self.assertFalse(state.exists())
        self.assertFalse(output.exists())
        preflight.assert_not_called()
        request_image.assert_not_called()

    def test_missing_key_does_not_consume_budget_or_run_preflight(self):
        with tempfile.TemporaryDirectory(prefix="clipart-task41-no-key-") as temp_dir:
            root = Path(temp_dir)
            source = root / "source.png"
            output = root / "output.provider"
            state = root / "state.json"
            self._image(source)
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
                benchmark, "fetch_endpoint_snapshot"
            ) as preflight:
                with self.assertRaisesRegex(
                    benchmark.ManagedFidelityBenchmarkError, "OPENROUTER_API_KEY"
                ):
                    benchmark.run_live_generation(
                        "seedream-4.5",
                        source,
                        output,
                        state_path=state,
                        authorized_candidates=("seedream-4.5",),
                    )

        self.assertFalse(state.exists())
        preflight.assert_not_called()

    def test_reservations_are_one_shot_and_budget_bounded(self):
        authorized = tuple(benchmark.CANDIDATES)
        with tempfile.TemporaryDirectory(prefix="clipart-task41-state-") as temp_dir:
            state = Path(temp_dir) / "state.json"
            self.assertEqual(
                benchmark.reserve_candidate(
                    "seedream-4.5", state, authorized_candidates=authorized
                ),
                1,
            )
            with self.assertRaisesRegex(
                benchmark.ManagedFidelityBenchmarkError, "already consumed"
            ):
                benchmark.reserve_candidate(
                    "seedream-4.5", state, authorized_candidates=authorized
                )

            with mock.patch.dict(
                benchmark.CANDIDATES["riverflow-v2.5-pro"],
                {"reservation_cost_usd": Decimal("0.300")},
            ):
                with self.assertRaisesRegex(
                    benchmark.ManagedFidelityBenchmarkError, "budget is exhausted"
                ):
                    benchmark.reserve_candidate(
                        "riverflow-v2.5-pro",
                        state,
                        authorized_candidates=authorized,
                    )

            snapshot = benchmark.budget_snapshot(state)

        self.assertEqual(snapshot["counted_spend_usd"], "0.075")
        self.assertEqual(snapshot["attempted_candidates"], ["seedream-4.5"])

    def test_tampered_reservation_amount_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="clipart-task41-tampered-state-") as temp_dir:
            state = Path(temp_dir) / "state.json"
            payload = benchmark._empty_budget_state()
            payload["reservations"]["seedream-4.5"] = {
                "attempt_number": 1,
                "reserved_usd": "0.001",
                "actual_usd": None,
                "status": "reserved",
            }
            state.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(
                benchmark.ManagedFidelityBenchmarkError, "budget state is invalid"
            ):
                benchmark.budget_snapshot(state)

    def test_concurrent_processes_allow_only_one_reservation(self):
        with tempfile.TemporaryDirectory(prefix="clipart-task41-process-lock-") as temp_dir:
            state = Path(temp_dir) / "state.json"
            code = (
                "import sys\n"
                "from pathlib import Path\n"
                "from scripts import run_managed_fidelity_benchmark as b\n"
                "try:\n"
                "    b.reserve_candidate('seedream-4.5', Path(sys.argv[1]), "
                "authorized_candidates=('seedream-4.5',))\n"
                "    print('reserved')\n"
                "except b.ManagedFidelityBenchmarkError as error:\n"
                "    print(str(error))\n"
            )
            processes = [
                subprocess.Popen(
                    [sys.executable, "-c", code, str(state)],
                    cwd=Path(__file__).resolve().parent.parent,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for _ in range(2)
            ]
            results = [process.communicate(timeout=30) for process in processes]

        self.assertEqual([process.returncode for process in processes], [0, 0])
        stdout = [result[0].strip() for result in results]
        self.assertEqual(stdout.count("reserved"), 1)
        self.assertEqual(
            stdout.count("Task 41 candidate request was already consumed"), 1
        )
        self.assertEqual([result[1] for result in results], ["", ""])

    def test_endpoint_preflight_accepts_only_matching_provider_price_and_options(self):
        payload = {
            "id": "sourceful/riverflow-v2.5-pro",
            "endpoints": [
                {
                    "provider_slug": "sourceful",
                    "provider_tag": "sourceful",
                    "supported_parameters": {
                        "resolution": {"type": "enum", "values": ["1K", "2K"]},
                        "output_format": {
                            "type": "enum",
                            "values": ["png", "jpeg"],
                        },
                        "n": {"type": "range", "min": 1, "max": 1},
                        "input_references": {"type": "range", "min": 0, "max": 10},
                    },
                    "pricing": [
                        {"billable": "output_image", "unit": "image", "cost_usd": 0.13},
                        {
                            "billable": "output_image",
                            "unit": "image",
                            "cost_usd": 0.15,
                            "variant": "2k",
                        },
                    ],
                }
            ],
        }

        parsed = benchmark.parse_endpoint_snapshot("riverflow-v2.5-pro", payload)

        self.assertEqual(parsed["provider"], "sourceful")
        self.assertEqual(parsed["cost_usd"], "0.130")
        self.assertTrue(parsed["required_options_supported"])

    def test_endpoint_preflight_rejects_price_increase_before_paid_request(self):
        payload = {
            "id": "bytedance-seed/seedream-4.5",
            "endpoints": [
                {
                    "provider_slug": "seed",
                    "provider_tag": "seed",
                    "supported_parameters": {
                        "resolution": {"type": "enum", "values": ["1K"]},
                        "aspect_ratio": {"type": "enum", "values": ["1:1"]},
                        "n": {"type": "range", "min": 1, "max": 10},
                        "input_references": {"type": "range", "min": 0, "max": 14},
                    },
                    "pricing": [
                        {"billable": "output_image", "unit": "image", "cost_usd": 0.05}
                    ],
                }
            ],
        }

        with self.assertRaisesRegex(
            benchmark.ManagedFidelityBenchmarkError, "exceeds the reservation"
        ):
            benchmark.parse_endpoint_snapshot("seedream-4.5", payload)

    def test_endpoint_preflight_rejects_nonfunctional_image_input_and_option_values(self):
        payload = {
            "id": "bytedance-seed/seedream-4.5",
            "endpoints": [
                {
                    "provider_slug": "seed",
                    "provider_tag": "seed",
                    "supported_parameters": {
                        "resolution": {"type": "enum", "values": ["2K"]},
                        "aspect_ratio": {"type": "enum", "values": ["16:9"]},
                        "n": {"type": "range", "min": 1, "max": 1},
                        "input_references": {"type": "range", "min": 0, "max": 0},
                    },
                    "pricing": [
                        {"billable": "output_image", "unit": "image", "cost_usd": 0.04}
                    ],
                }
            ],
        }

        with self.assertRaisesRegex(
            benchmark.ManagedFidelityBenchmarkError, "no longer accepts image input"
        ):
            benchmark.parse_endpoint_snapshot("seedream-4.5", payload)

        payload["endpoints"][0]["supported_parameters"]["input_references"]["max"] = 1
        with self.assertRaisesRegex(
            benchmark.ManagedFidelityBenchmarkError, "required option"
        ):
            benchmark.parse_endpoint_snapshot("seedream-4.5", payload)

    def test_price_preflight_failure_happens_before_reservation_or_paid_request(self):
        with tempfile.TemporaryDirectory(prefix="clipart-task41-price-gate-") as temp_dir:
            root = Path(temp_dir)
            source = root / "source.png"
            output = root / "output.provider"
            state = root / "state.json"
            self._image(source)
            with mock.patch.dict(
                os.environ, {"OPENROUTER_API_KEY": "test-secret"}
            ), mock.patch.object(
                benchmark,
                "fetch_endpoint_snapshot",
                side_effect=benchmark.ManagedFidelityBenchmarkError(
                    "Pinned provider price exceeds the reservation"
                ),
            ), mock.patch.object(
                benchmark, "fetch_key_budget_snapshot"
            ) as key_budget, mock.patch.object(
                benchmark, "_request_image"
            ) as request_image:
                with self.assertRaisesRegex(
                    benchmark.ManagedFidelityBenchmarkError, "exceeds the reservation"
                ):
                    benchmark.run_live_generation(
                        "seedream-4.5",
                        source,
                        output,
                        state_path=state,
                        authorized_candidates=("seedream-4.5",),
                    )

            self.assertFalse(state.exists())
            self.assertFalse(output.exists())
            key_budget.assert_not_called()
            request_image.assert_not_called()

    def test_key_budget_requires_external_hard_limit_with_sufficient_remaining(self):
        accepted = benchmark.parse_key_budget_snapshot(
            "seedream-4.5",
            {"data": {"limit": 0.3, "limit_remaining": 0.265}},
        )
        self.assertEqual(accepted["hard_limit_usd"], "0.300")
        self.assertEqual(accepted["remaining_before_request_usd"], "0.265")
        self.assertFalse(accepted["local_budget_only"])

        for payload, message in (
            ({"data": {"limit": None, "limit_remaining": None}}, "hard spending limit"),
            ({"data": {"limit": 1.0, "limit_remaining": 1.0}}, "exceeds"),
            ({"data": {"limit": 0.3, "limit_remaining": 0.01}}, "insufficient"),
        ):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(
                    benchmark.ManagedFidelityBenchmarkError, message
                ):
                    benchmark.parse_key_budget_snapshot("seedream-4.5", payload)

    def test_unlimited_key_without_override_stops_before_reservation_and_post(self):
        with tempfile.TemporaryDirectory(prefix="clipart-task41-unlimited-key-") as temp_dir:
            root = Path(temp_dir)
            source = root / "source.png"
            output = root / "output.provider"
            state = root / "state.json"
            self._image(source)
            with mock.patch.dict(
                os.environ, {"OPENROUTER_API_KEY": "test-secret"}
            ), mock.patch.object(
                benchmark,
                "fetch_endpoint_snapshot",
                return_value={"cost_usd": "0.040"},
            ), mock.patch.object(
                benchmark,
                "fetch_key_budget_snapshot",
                side_effect=benchmark.ManagedFidelityBenchmarkError(
                    "OpenRouter key must have a hard spending limit"
                ),
            ), mock.patch.object(benchmark, "_request_image") as request_image:
                with self.assertRaisesRegex(
                    benchmark.ManagedFidelityBenchmarkError, "hard spending limit"
                ):
                    benchmark.run_live_generation(
                        "seedream-4.5",
                        source,
                        output,
                        state_path=state,
                        authorized_candidates=("seedream-4.5",),
                    )

        self.assertFalse(state.exists())
        self.assertFalse(output.exists())
        request_image.assert_not_called()

    def test_endpoint_preflight_rejects_input_minimum_above_one(self):
        payload = {
            "id": "bytedance-seed/seedream-4.5",
            "endpoints": [
                {
                    "provider_slug": "seed",
                    "provider_tag": "seed",
                    "supported_parameters": {
                        "resolution": {"type": "enum", "values": ["1K"]},
                        "aspect_ratio": {"type": "enum", "values": ["1:1"]},
                        "n": {"type": "range", "min": 1, "max": 1},
                        "input_references": {"type": "range", "min": 2, "max": 14},
                    },
                    "pricing": [
                        {"billable": "output_image", "unit": "image", "cost_usd": 0.04}
                    ],
                }
            ],
        }

        with self.assertRaisesRegex(
            benchmark.ManagedFidelityBenchmarkError, "no longer accepts image input"
        ):
            benchmark.parse_endpoint_snapshot("seedream-4.5", payload)

    def test_endpoint_preflight_rejects_ambiguous_provider_tag(self):
        endpoint = {
            "provider_slug": "seed",
            "provider_tag": "seed",
            "supported_parameters": {
                "resolution": {"type": "enum", "values": ["1K"]},
                "aspect_ratio": {"type": "enum", "values": ["1:1"]},
                "n": {"type": "range", "min": 1, "max": 1},
                "input_references": {"type": "range", "min": 0, "max": 14},
            },
            "pricing": [
                {"billable": "output_image", "unit": "image", "cost_usd": 0.04}
            ],
        }
        payload = {
            "id": "bytedance-seed/seedream-4.5",
            "endpoints": [
                endpoint,
                {
                    **endpoint,
                    "pricing": [
                        {
                            "billable": "output_image",
                            "unit": "image",
                            "cost_usd": 0.05,
                        }
                    ],
                },
            ],
        }

        with self.assertRaisesRegex(
            benchmark.ManagedFidelityBenchmarkError, "endpoint is ambiguous"
        ):
            benchmark.parse_endpoint_snapshot("seedream-4.5", payload)

    def test_openrouter_transport_pins_https_host_and_rejects_redirects(self):
        request = urllib.request.Request("https://example.com/api/v1/images")
        with mock.patch.object(urllib.request, "build_opener") as build_opener:
            with self.assertRaisesRegex(
                benchmark.ManagedFidelityBenchmarkError, "target is not allowed"
            ):
                benchmark._open_pinned_openrouter_request(request, timeout=1)
        build_opener.assert_not_called()

        handler = benchmark._RejectRedirectHandler()
        self.assertIsNone(
            handler.redirect_request(
                urllib.request.Request("https://openrouter.ai/api/v1/images"),
                None,
                302,
                "Found",
                {},
                "https://attacker.example/collect",
            )
        )

    def test_provider_error_message_is_bounded_and_redacts_sensitive_values(self):
        response = {
            "error": {
                "message": (
                    "invalid reference data:image/png;base64,QUJDRA== "
                    "for sk-secretvalue123456"
                )
            }
        }
        error = urllib.error.HTTPError(
            "https://openrouter.ai/api/v1/images",
            400,
            "Bad Request",
            {},
            io.BytesIO(json.dumps(response).encode("utf-8")),
        )

        message = benchmark._safe_provider_error(error)

        self.assertEqual(
            message,
            "invalid reference [image-data] for [redacted-key]",
        )

    def test_actual_cost_violation_is_recorded_and_cannot_be_retried(self):
        with tempfile.TemporaryDirectory(prefix="clipart-task41-cost-violation-") as temp_dir:
            state = Path(temp_dir) / "state.json"
            benchmark.reserve_candidate(
                "seedream-4.5",
                state,
                authorized_candidates=("seedream-4.5",),
            )
            with self.assertRaisesRegex(
                benchmark.ManagedFidelityBenchmarkError, "exceeded"
            ):
                benchmark.mark_candidate_result(
                    "seedream-4.5",
                    actual_cost_usd=Decimal("0.0404"),
                    status="completed",
                    state_path=state,
                )
            saved = json.loads(state.read_text(encoding="utf-8"))
            with self.assertRaisesRegex(
                benchmark.ManagedFidelityBenchmarkError, "already consumed"
            ):
                benchmark.reserve_candidate(
                    "seedream-4.5",
                    state,
                    authorized_candidates=("seedream-4.5",),
                )

        self.assertEqual(
            saved["reservations"]["seedream-4.5"],
            {
                "attempt_number": 1,
                "reserved_usd": "0.040",
                "actual_usd": "0.0404",
                "status": "completed",
            },
        )

    def test_image_validator_rejects_small_compressed_file_with_too_many_pixels(self):
        with tempfile.TemporaryDirectory(prefix="clipart-task41-pixels-") as temp_dir:
            source = Path(temp_dir) / "large.png"
            Image.new("1", (5000, 5000), 0).save(source, format="PNG")

            with self.assertRaisesRegex(
                benchmark.ManagedFidelityBenchmarkError, "pixel limit"
            ):
                benchmark._read_validated_image(source)

    def test_provider_parser_rejects_compressed_image_with_too_many_pixels(self):
        with tempfile.TemporaryDirectory(prefix="clipart-task41-provider-pixels-") as temp_dir:
            source = Path(temp_dir) / "large.png"
            Image.new("1", (5000, 5000), 0).save(source, format="PNG")
            payload = {
                "data": [
                    {
                        "b64_json": base64.b64encode(source.read_bytes()).decode(
                            "ascii"
                        ),
                        "media_type": "image/png",
                    }
                ]
            }

            with self.assertRaisesRegex(
                benchmark.ManagedFidelityBenchmarkError, "pixel limit"
            ):
                benchmark.parse_provider_response(payload)

    def test_windows_permission_error_is_normalized_as_locked_state(self):
        with tempfile.TemporaryDirectory(prefix="clipart-task41-lock-") as temp_dir:
            state = Path(temp_dir) / "state.json"
            with mock.patch.object(
                benchmark.os, "open", side_effect=PermissionError("busy")
            ):
                with self.assertRaisesRegex(
                    benchmark.ManagedFidelityBenchmarkError, "state is locked"
                ):
                    benchmark.reserve_candidate(
                        "seedream-4.5",
                        state,
                        authorized_candidates=("seedream-4.5",),
                    )

    def test_lock_release_permission_error_is_normalized(self):
        lock_path = Path("unused.lock")
        with mock.patch.object(Path, "unlink", side_effect=PermissionError("busy")):
            with self.assertRaisesRegex(
                benchmark.ManagedFidelityBenchmarkError, "could not be released"
            ):
                benchmark._release_state_lock(
                    lock_path,
                    preserve_active_error=False,
                )
            benchmark._release_state_lock(lock_path, preserve_active_error=True)

    def test_successful_request_records_actual_cost_and_atomic_output(self):
        with tempfile.TemporaryDirectory(prefix="clipart-task41-success-") as temp_dir:
            root = Path(temp_dir)
            source = root / "source.png"
            provider_image = root / "provider.png"
            output = root / "output.provider"
            state = root / "state.json"
            self._image(source)
            provider_bytes = self._image(provider_image, mode="RGB")
            parsed = {
                "provider_bytes": provider_bytes,
                "media_type": "image/png",
                "billed_cost_usd": 0.039,
            }
            with mock.patch.dict(
                os.environ, {"OPENROUTER_API_KEY": "test-secret"}
            ), mock.patch.object(
                benchmark,
                "fetch_endpoint_snapshot",
                return_value={"cost_usd": "0.040"},
            ), mock.patch.object(
                benchmark,
                "fetch_key_budget_snapshot",
                return_value={
                    "hard_limit_usd": "0.300",
                    "remaining_before_request_usd": "0.265",
                },
            ), mock.patch.object(
                benchmark, "_request_image", return_value=(parsed, 1.25)
            ):
                result = benchmark.run_live_generation(
                    "seedream-4.5",
                    source,
                    output,
                    state_path=state,
                    authorized_candidates=("seedream-4.5",),
                )

            saved_state = json.loads(state.read_text(encoding="utf-8"))
            saved_output = output.read_bytes()

        self.assertEqual(result[:4], (1, 1.25, 0.039, "image/png"))
        self.assertEqual(saved_output, provider_bytes)
        self.assertEqual(
            saved_state["reservations"]["seedream-4.5"]["actual_usd"], "0.039"
        )
        self.assertEqual(
            saved_state["reservations"]["seedream-4.5"]["status"], "completed"
        )

    def test_failed_paid_request_remains_counted_and_cannot_retry(self):
        with tempfile.TemporaryDirectory(prefix="clipart-task41-failure-") as temp_dir:
            root = Path(temp_dir)
            source = root / "source.png"
            output = root / "output.provider"
            state = root / "state.json"
            self._image(source)
            with mock.patch.dict(
                os.environ, {"OPENROUTER_API_KEY": "test-secret"}
            ), mock.patch.object(
                benchmark,
                "fetch_endpoint_snapshot",
                return_value={"cost_usd": "0.040"},
            ), mock.patch.object(
                benchmark,
                "fetch_key_budget_snapshot",
                return_value={
                    "hard_limit_usd": "0.300",
                    "remaining_before_request_usd": "0.265",
                },
            ), mock.patch.object(
                benchmark,
                "_request_image",
                side_effect=benchmark.ManagedFidelityBenchmarkError("provider failed"),
            ):
                with self.assertRaisesRegex(
                    benchmark.ManagedFidelityBenchmarkError, "provider failed"
                ):
                    benchmark.run_live_generation(
                        "seedream-4.5",
                        source,
                        output,
                        state_path=state,
                        authorized_candidates=("seedream-4.5",),
                    )

            saved_state = json.loads(state.read_text(encoding="utf-8"))
            snapshot = benchmark.budget_snapshot(state)
            with self.assertRaisesRegex(
                benchmark.ManagedFidelityBenchmarkError, "already consumed"
            ):
                benchmark.reserve_candidate(
                    "seedream-4.5",
                    state,
                    authorized_candidates=("seedream-4.5",),
                )

        self.assertEqual(
            saved_state["reservations"]["seedream-4.5"]["status"], "failed"
        )
        self.assertEqual(snapshot["counted_spend_usd"], "0.075")
        self.assertFalse(output.exists())

    def test_output_failure_records_known_actual_cost_and_preserves_error(self):
        with tempfile.TemporaryDirectory(prefix="clipart-task41-output-failure-") as temp_dir:
            root = Path(temp_dir)
            source = root / "source.png"
            provider_image = root / "provider.png"
            output = root / "output.provider"
            state = root / "state.json"
            self._image(source)
            parsed = {
                "provider_bytes": self._image(provider_image, mode="RGB"),
                "media_type": "image/png",
                "billed_cost_usd": 0.039,
            }
            with mock.patch.dict(
                os.environ, {"OPENROUTER_API_KEY": "test-secret"}
            ), mock.patch.object(
                benchmark,
                "fetch_endpoint_snapshot",
                return_value={"cost_usd": "0.040"},
            ), mock.patch.object(
                benchmark,
                "fetch_key_budget_snapshot",
                return_value={
                    "hard_limit_usd": "0.300",
                    "remaining_before_request_usd": "0.265",
                    "local_budget_only": False,
                },
            ), mock.patch.object(
                benchmark, "_request_image", return_value=(parsed, 1.25)
            ), mock.patch.object(
                Path, "write_bytes", side_effect=OSError("disk full")
            ):
                with self.assertRaisesRegex(OSError, "disk full"):
                    benchmark.run_live_generation(
                        "seedream-4.5",
                        source,
                        output,
                        state_path=state,
                        authorized_candidates=("seedream-4.5",),
                    )

            saved_state = json.loads(state.read_text(encoding="utf-8"))

        self.assertEqual(
            saved_state["reservations"]["seedream-4.5"]["actual_usd"], "0.039"
        )
        self.assertEqual(
            saved_state["reservations"]["seedream-4.5"]["status"], "failed"
        )
        self.assertFalse(output.exists())

    def test_existing_result_analysis_cannot_claim_watermark_removal(self):
        with tempfile.TemporaryDirectory(prefix="clipart-task41-analysis-") as temp_dir:
            root = Path(temp_dir)
            photo = root / "photo.png"
            face = root / "face.png"
            source = root / "source.png"
            result = root / "result.png"
            comparison = root / "comparison.png"
            Image.new("RGB", (480, 320), (80, 130, 170)).save(photo)
            Image.new("RGB", (320, 480), (210, 165, 145)).save(face)
            board, fixture = benchmark.common.build_fixture_board(photo, face)
            board.save(source)
            board.convert("RGB").save(result)

            metrics = benchmark.common.analyze_result(source, result, fixture, comparison)
            comparison_exists = comparison.is_file()

        synthid = metrics["pixel_watermark_status"]["synthid"]
        self.assertEqual(synthid["pixel_evidence"]["status"], "not_verified")
        self.assertEqual(synthid["pixel_evidence"]["removal_claim"], "not_claimed")
        self.assertTrue(comparison_exists)

    def test_report_serializer_rejects_secret_leak(self):
        secret = "openrouter-test-secret"
        with self.assertRaisesRegex(
            benchmark.ManagedFidelityBenchmarkError, "reached the Task 41 report"
        ):
            benchmark.serialize_report({"unexpected": secret}, api_key=secret)


if __name__ == "__main__":
    unittest.main()
