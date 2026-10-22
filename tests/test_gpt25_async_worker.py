"""Exercise the actual WorkerThread paid-job logic offline without Qt on the VDS.

Extracting just the class methods via AST allows deterministic provider and
journal tests on a server that intentionally has no PyQt6 or OpenCV installed.
No live network or paid requests are performed.
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import json
import os
from urllib.parse import urlparse
import re
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

from fal_provider import FalProviderError, FalTaskJournal
from gpt25_provider import (
    failure_reason, generation_payload, prepare_reference_inputs, provider_for_model,
    request_headers, status_url, submit_url, submitted_task_id, task_result,
    piapi_edit_multipart_body, result_retention_elapsed,
)
from model_catalog import validate_generation_contract


SOURCE = Path(__file__).resolve().parent.parent / "main.py"
tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
worker_class = next(
    node for node in tree.body
    if isinstance(node, ast.ClassDef) and node.name == "WorkerThread"
)
picked = [
    node for node in worker_class.body
    if isinstance(node, ast.FunctionDef)
    and node.name in {"_gpt25_generate_image", "_claim_pending_task", "_task_operation_key"}
]
namespace = {
    "gpt25_provider_for_model": provider_for_model,
    "gpt25_generation_payload": generation_payload,
    "gpt25_prepare_reference_inputs": prepare_reference_inputs,
    "split_references": lambda refs: list(refs),
    "os": os, "urlparse": urlparse,
    "gpt25_request_headers": request_headers,
    "gpt25_submit_url": submit_url,
    "gpt25_status_url": status_url,
    "gpt25_submitted_task_id": submitted_task_id,
    "gpt25_task_result": task_result,
    "gpt25_failure_reason": failure_reason,
    "gpt25_piapi_edit_multipart_body": piapi_edit_multipart_body,
    "gpt25_result_retention_elapsed": result_retention_elapsed,
    "validate_generation_contract": validate_generation_contract,
    "ProcessingCancelled": type("ProcessingCancelled", (RuntimeError,), {}),
    "FalProviderError": FalProviderError,
    "uuid": uuid, "time": time, "re": re,
}
module = ast.fix_missing_locations(ast.Module(body=picked, type_ignores=[]))
exec(compile(module, str(SOURCE), "exec"), namespace)


class OfflineWorker:
    _gpt25_generate_image = namespace["_gpt25_generate_image"]
    _claim_pending_task = namespace["_claim_pending_task"]
    _task_operation_key = namespace["_task_operation_key"]

    def _note_provider_failure(self):
        """Streak accounting is covered in test_auto_clipart_skip_failed_file."""

    def __init__(self, directory, provider):
        self.settings = {"gpt25_cost_confirmed": True}
        self.atlascloud_api_key = "TEST_ATLAS_KEY"
        self.piapi_api_key = "TEST_PIAPI_KEY"
        self.gpt25_task_journals = {
            "atlascloud": FalTaskJournal(str(Path(directory) / "atlas.json")),
            "piapi": FalTaskJournal(str(Path(directory) / "piapi.json")),
        }
        self._claimed_gpt25_task_ids = {"atlascloud": set(), "piapi": set()}
        self._shared_state_lock = threading.Lock()
        self._diagnostic_context = SimpleNamespace(stage="generation", item_index=1)
        self._item_context = SimpleNamespace(gpt25_completion=None)
        self._task_item_indices = ()
        self.timeout = 30
        self.status_poll_interval = 0.001
        self.generation_wait_timeout = 3
        self.progress = SimpleNamespace(emit=lambda _text: None)
        self.calls = []
        self.responses = []
        self.provider = provider
        self.diagnostics = []

    def _request_json(self, url, method="GET", payload=None, headers=None, timeout=None):
        if method == "POST":
            self._diagnostic_context.gpt25_post_started = True
        self.calls.append((method, url, payload, headers))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def _get_generation_profile(self, _references):
        return ("1:1", "1K")

    def _paid_task_fingerprint(self, payload):
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def _set_provider_diagnostic_context(self, stage, _provider, _model):
        self._diagnostic_context.stage = stage

    def _provider_lease(self, _provider):
        return contextlib.nullcontext()

    def _wait_for_generation_launch_slot(self):
        pass

    def request_stop_after_current(self):
        self.batch_stop_requested = True

    def _ensure_provider_submission_allowed(self):
        pass

    def _ensure_running(self):
        pass

    def _emit_diagnostic(self, *args, **kwargs):
        self.diagnostics.append((args, kwargs))

    def _safe_error_text(self, error):
        return str(error)


class AsyncWorkerSafetyTests(unittest.TestCase):
    def test_all_five_routes_use_real_worker_with_matching_payload(self):
        from gpt25_provider import MODEL_TO_PROVIDER, MODEL_ENDPOINT_IDS, BUDGET_MODEL_ID
        for model, provider in MODEL_TO_PROVIDER.items():
            with self.subTest(model=model), tempfile.TemporaryDirectory() as temp:
                worker = OfflineWorker(temp, provider)
                if model == BUDGET_MODEL_ID:
                    worker._get_generation_profile = lambda _: ("auto", "auto")
                if provider == "atlascloud":
                    worker.responses = [{"data":{"id":"render1"}},
                        {"data":{"status":"completed","outputs":["https://images.example.org/a.png"]}}]
                else:
                    worker.responses = [{"task_id":"render1"},
                        {"status":"completed","output":{"data":[{"url":"https://images.example.org/a.png"}]}}]
                self.assertEqual(worker._gpt25_generate_image("A ceramic cup",model),
                                 "https://images.example.org/a.png")
                self.assertEqual([call[0] for call in worker.calls], ["POST","GET"])
                self.assertEqual(worker.calls[0][2]["model"],MODEL_ENDPOINT_IDS[model])

    def test_piapi_submit_and_poll_identify_application_to_gateway(self):
        from app_identity import APP_USER_AGENT
        with tempfile.TemporaryDirectory() as temp:
            worker = OfflineWorker(temp, "piapi")
            worker.responses = [
                {"task_id": "render1"},
                {"status": "completed", "output": {"data": [
                    {"url": "https://images.example.org/a.png"}
                ]}},
            ]
            worker._gpt25_generate_image("A cup", "piapi/gpt-image-2.5-flare")
            self.assertEqual([call[0] for call in worker.calls], ["POST", "GET"])
            for call in worker.calls:
                self.assertEqual(call[3].get("User-Agent"), APP_USER_AGENT)

    def test_reference_edits_use_paid_job_journal_and_provider_edit_route(self):
        for provider in ("piapi", "atlascloud"):
            for variant in ("flare", "sunburst"):
                with self.subTest(provider=provider, variant=variant), tempfile.TemporaryDirectory() as temp:
                    worker = OfflineWorker(temp, provider)
                    files = [Path(temp) / f"private-reference-{index}.png" for index in range(3)]
                    for index, file in enumerate(files):
                        file.write_bytes(b"\x89PNG\r\n\x1a\n" + f"image-content-{index}".encode())
                    model = f"{provider}/gpt-image-2.5-{variant}"
                    if provider == "atlascloud":
                        worker.responses = [{"data":{"id":"edit1"}},
                            {"data":{"status":"completed","outputs":["https://images.example.org/edit.png"]}}]
                    else:
                        worker.responses = [{"task_id":"edit1"},
                            {"status":"completed","output":{"data":[{"url":"https://images.example.org/edit.png"}]}}]
                    worker._get_generation_profile = lambda refs: ("1:1", "1K") if refs else ("auto", "auto")
                    self.assertEqual(worker._gpt25_generate_image("Make it blue", model, [str(file) for file in files]),
                                     "https://images.example.org/edit.png")
                    self.assertEqual([entry[0] for entry in worker.calls], ["POST", "GET"])
                    if provider == "piapi":
                        from app_identity import APP_USER_AGENT
                        for call in worker.calls:
                            self.assertEqual(call[3].get("User-Agent"), APP_USER_AGENT)
                        self.assertTrue(worker.calls[0][1].endswith("/images/edits/async"))
                        self.assertTrue(worker.calls[0][2].startswith(b"--VibixPiAPI"))
                        self.assertEqual(worker.calls[0][2].count(b'name="image[]"; filename='), 3)
                        self.assertIn("multipart/form-data; boundary=VibixPiAPI", worker.calls[0][3]["Content-Type"])
                        self.assertIn(b"\x89PNG\r\n\x1a\nimage-content-0", worker.calls[0][2])
                        self.assertIn(b"\x89PNG\r\n\x1a\nimage-content-1", worker.calls[0][2])
                        self.assertIn(b"\x89PNG\r\n\x1a\nimage-content-2", worker.calls[0][2])
                    else:
                        self.assertIn("data:image/png;base64,", str(worker.calls[0][2]))
                        self.assertNotIn(str(file), str(worker.calls[0][2]))
                        self.assertTrue(worker.calls[0][2]["model"].endswith("/edit"))

    def test_atlas_submit_and_poll(self):
        with tempfile.TemporaryDirectory() as temp:
            worker = OfflineWorker(temp, "atlascloud")
            worker.responses = [
                {"data": {"id": "pred_atlas", "status": "processing"}},
                {"data": {"status": "processing"}},
                {"data": {"status": "completed", "outputs": ["https://images.example.org/a.png"]}},
            ]
            url = worker._gpt25_generate_image("Blue butterfly clipart", "atlascloud/gpt-image-2.5-flare")
            self.assertEqual(url, "https://images.example.org/a.png")
            self.assertEqual([entry[0] for entry in worker.calls], ["POST", "GET", "GET"])
            self.assertEqual(worker.calls[0][2]["model"], "openai/gpt-image-2.5-flare/text-to-image")

    def test_piapi_recovers_polled_paid_job_without_second_post(self):
        with tempfile.TemporaryDirectory() as temp:
            worker = OfflineWorker(temp, "piapi")
            worker.responses = [{"task_id": "piapi_task_1"}, TimeoutError("Temporary gateway error")]
            with self.assertRaisesRegex(RuntimeError, "без новой оплаты"):
                worker._gpt25_generate_image("A tulip", "piapi/gpt-image-2.5-flare")
            worker.responses = [
                {"status": "completed", "output": {"data": [{"url": "https://images.example.org/piapi.png"}]}}
            ]
            url = worker._gpt25_generate_image("A tulip", "piapi/gpt-image-2.5-flare")
            self.assertEqual(url, "https://images.example.org/piapi.png")
            self.assertEqual(len([entry for entry in worker.calls if entry[0] == "POST"]), 1)

    def test_piapi_not_yet_visible_record_keeps_polling(self):
        # A fresh async record can answer with an error envelope or a status
        # word we do not know — neither ends the paid task.
        with tempfile.TemporaryDirectory() as temp:
            worker = OfflineWorker(temp, "piapi")
            worker.responses = [
                {"task_id": "piapi_task_9"},
                {"error": "task not found"},
                {"status": "waiting"},
                {"status": "completed", "output": {"data": [{"url": "https://images.example.org/ok.png"}]}},
            ]
            url = worker._gpt25_generate_image("A cup", "piapi/gpt-image-2.5-flare")
            self.assertEqual(url, "https://images.example.org/ok.png")
            self.assertEqual([call[0] for call in worker.calls], ["POST", "GET", "GET", "GET"])
            states = [d[1].get("provider_state") for d in worker.diagnostics if d[0][0] == "provider_task_polled"]
            self.assertEqual(states, ["pending", "pending", "completed"])

    def test_piapi_failed_poll_surfaces_provider_reason(self):
        with tempfile.TemporaryDirectory() as temp:
            worker = OfflineWorker(temp, "piapi")
            worker.responses = [
                {"task_id": "piapi_task_10"},
                {"status": "failed", "error": {"code": 10000, "message": "Internal error."},
                 "output": {"error_body": {"error": {
                     "message": "response handler failed: Our servers are currently overloaded.\nTry later.",
                     "type": "upstream_error", "upstream_status": 500}}}},
            ]
            with self.assertRaisesRegex(RuntimeError, "overloaded"):
                worker._gpt25_generate_image("A cup", "piapi/gpt-image-2.5-flare")
            failure = [d for d in worker.diagnostics if d[0][0] == "provider_task_failed"]
            self.assertTrue(failure)
            self.assertIn("overloaded", failure[0][1]["error_message"])
            self.assertIn("upstream 500", failure[0][1]["error_message"])
            # The failed task is terminal: nothing stays pending on the journal.
            self.assertEqual(worker.gpt25_task_journals["piapi"].pending(), ())
            self.assertNotIn("TEST_PIAPI_KEY", repr(worker.diagnostics))

    def test_piapi_poll_http400_preserves_get_only_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            worker = OfflineWorker(temp, "piapi")

            def gone(url, method="GET", payload=None, headers=None, timeout=None):
                worker.calls.append((method, url, payload, headers))
                if method == "POST":
                    worker._diagnostic_context.gpt25_post_started = True
                    return {"task_id": "piapi_task_11"}
                worker._diagnostic_context.last_http_status = 400
                raise RuntimeError("Ошибка HTTP-запроса: HTTP status=400")

            worker._request_json = gone
            with self.assertRaisesRegex(RuntimeError, "без новой оплаты"):
                worker._gpt25_generate_image("A cup", "piapi/gpt-image-2.5-flare")
            self.assertEqual(worker.gpt25_task_journals["piapi"].pending()[0].status, "poll_deferred")
            restarted = OfflineWorker(temp, "piapi")
            restarted.responses = [{"status": "completed", "output": {"data": [{"url": "https://images.example.org/recovered.png"}]}}]
            self.assertEqual(restarted._gpt25_generate_image("A cup", "piapi/gpt-image-2.5-flare"), "https://images.example.org/recovered.png")
            self.assertEqual([c[0] for c in worker.calls], ["POST", "GET"])
            self.assertEqual([c[0] for c in restarted.calls], ["GET"])

    def test_completed_job_stays_recoverable_until_image_is_saved(self):
        with tempfile.TemporaryDirectory() as temp:
            worker = OfflineWorker(temp, "atlascloud")
            response = {"data": {"status": "completed", "outputs": ["https://images.example.org/a.png"]}}
            worker.responses = [{"data": {"id": "pred_once"}}, response]
            worker._gpt25_generate_image("A daisy", "atlascloud/gpt-image-2.5-flare")
            self.assertEqual(len(worker.gpt25_task_journals["atlascloud"].pending()), 1)
            worker.responses = [response]
            worker._gpt25_generate_image("A daisy", "atlascloud/gpt-image-2.5-flare")
            self.assertEqual(len([call for call in worker.calls if call[0] == "POST"]), 1)
            worker.gpt25_task_journals["atlascloud"].update_status("pred_once", "completed")
            self.assertEqual(worker.gpt25_task_journals["atlascloud"].pending(), ())

    def test_unknown_paid_post_not_repeated_automatically(self):
        with tempfile.TemporaryDirectory() as temp:
            worker = OfflineWorker(temp, "atlascloud")
            worker._diagnostic_context.last_http_status = 401  # stale earlier request
            worker.responses = [TimeoutError("Ambiguous response to paid POST")]
            with self.assertRaisesRegex(RuntimeError, "Проверьте историю задач"):
                worker._gpt25_generate_image("A tulip", "atlascloud/gpt-image-2.5-flare")
            with self.assertRaisesRegex(RuntimeError, "двойного списания"):
                worker._gpt25_generate_image("A tulip", "atlascloud/gpt-image-2.5-flare")
            self.assertEqual(len([entry for entry in worker.calls if entry[0] == "POST"]), 1)

    def test_rejected_piapi_submit_exposes_safe_http_reason_and_diagnostic(self):
        with tempfile.TemporaryDirectory() as temp:
            worker = OfflineWorker(temp, "piapi")

            def reject_submit(*_args, **_kwargs):
                worker._diagnostic_context.gpt25_post_started = True
                worker._diagnostic_context.last_http_status = 401
                raise RuntimeError("HTTP status=401")

            worker._request_json = reject_submit
            with self.assertRaisesRegex(RuntimeError, "API-ключ или права доступа.*401"):
                worker._gpt25_generate_image("A tulip", "piapi/gpt-image-2.5-flare")
            failure = next(item for item in worker.diagnostics if item[0][0] == "provider_task_failed")
            self.assertEqual(failure[1]["http_status"], 401)
            self.assertNotIn("TEST_PIAPI_KEY", repr(failure))
            self.assertEqual(worker.gpt25_task_journals["piapi"].pending(), ())

    def test_cannot_start_paid_job_without_confirmation(self):
        with tempfile.TemporaryDirectory() as temp:
            worker = OfflineWorker(temp, "piapi")
            worker.settings["gpt25_cost_confirmed"] = False
            with self.assertRaisesRegex(RuntimeError, "подтвердите"):
                worker._gpt25_generate_image("A tulip", "piapi/gpt-image-2.5-flare")
            self.assertFalse(worker.calls)


if __name__ == "__main__":
    unittest.main()
