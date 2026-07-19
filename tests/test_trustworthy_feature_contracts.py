import os
import json
import tempfile
import types
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import main
from PIL import Image


def worker_settings(**overrides):
    settings = {
        "kie_api_key": "test-generation-key",
        "text_generation_ratio": "1:1",
        "text_generation_resolution": "2K",
        "reference_generation_ratio": "3:2",
        "reference_generation_resolution": "4K",
        "timeout": 10,
        "retries": 0,
        "upscale": False,
        "remove_bg": False,
        "trim_enabled": False,
        "export_300_dpi": False,
    }
    settings.update(overrides)
    return settings


class TrustworthyGenerationContractsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = main.QApplication.instance() or main.QApplication([])

    def test_documented_generation_payload_preserves_prompt_references_and_png_contract(self):
        worker = main.WorkerThread(
            "mode1_generate_only",
            ".",
            worker_settings(reference_generation_ratio="16:9"),
        )

        text_payload = worker._build_documented_model_input(
            "nano-banana-2",
            "two blue birds",
            [],
        )
        reference_payload = worker._build_documented_model_input(
            "gpt-image-2",
            "keep the subject unchanged",
            ["https://example.test/reference.png"],
        )

        self.assertEqual(text_payload["prompt"], "two blue birds")
        self.assertEqual(text_payload["resolution"], "2K")
        self.assertEqual(text_payload["output_format"], "png")
        self.assertNotIn("image_input", text_payload)
        self.assertEqual(reference_payload["input_urls"], ["https://example.test/reference.png"])
        self.assertEqual(reference_payload["aspect_ratio"], "16:9")
        self.assertEqual(reference_payload["resolution"], "4K")

    def test_generation_routes_model_creates_task_and_returns_polled_result(self):
        worker = main.WorkerThread("mode1_generate_only", ".", worker_settings())
        calls = []

        def fake_create_task(worker_self, model, payload):
            calls.append((model, payload))
            return "task-123"

        worker._kie_create_task = types.MethodType(fake_create_task, worker)
        worker._kie_wait_result = types.MethodType(
            lambda worker_self, task_id: f"https://cdn.example/{task_id}.png", worker
        )

        result = worker._kie_generate_generic_model(
            "gpt-image-2",
            "preserve this image",
            ["https://example.test/reference.png"],
        )

        self.assertEqual(result, "https://cdn.example/task-123.png")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "gpt-image-2-image-to-image")
        self.assertEqual(calls[0][1]["input_urls"], ["https://example.test/reference.png"])

    def test_generation_polling_accepts_processing_then_success_and_extracts_url(self):
        worker = main.WorkerThread("mode1_generate_only", ".", worker_settings())
        worker.status_poll_interval = 0
        responses = [
            {"code": 200, "data": {"state": "processing"}},
            {
                "code": 200,
                "data": {
                    "state": "success",
                    "resultJson": {"output": {"mediaUrl": "https://cdn.example/result.png"}},
                },
            },
        ]
        requests = []

        def fake_request_json(worker_self, url, method="GET", headers=None, timeout=None, payload=None):
            requests.append((url, method))
            return responses.pop(0)

        worker._request_json = types.MethodType(fake_request_json, worker)
        with patch.object(main.time, "sleep") as sleep_mock:
            result = worker._kie_wait_result("task-123")

        self.assertEqual(result, "https://cdn.example/result.png")
        self.assertEqual(len(requests), 2)
        self.assertTrue(all(method == "GET" for _, method in requests))
        sleep_mock.assert_called_once_with(0)

    def test_generation_polling_rejects_failed_task_without_publishing_url(self):
        worker = main.WorkerThread("mode1_generate_only", ".", worker_settings())
        worker._request_json = types.MethodType(
            lambda worker_self, *args, **kwargs: {
                "code": 200,
                "data": {"state": "failed", "failMsg": "provider rejected task"},
            },
            worker,
        )

        with self.assertRaisesRegex(RuntimeError, "provider rejected task"):
            worker._kie_wait_result("task-failed")

    def test_generation_flow_posts_polls_downloads_and_publishes_one_png_without_network(self):
        with tempfile.TemporaryDirectory(prefix="clipart-trustworthy-generation-") as temp_dir:
            worker = main.WorkerThread(
                "mode1_generate_only",
                temp_dir,
                worker_settings(
                    text_generation_model="nano-banana-2",
                    text_generation_ratio="1:1",
                    text_generation_resolution="2K",
                ),
                generated_prompts=[{
                    "prompt": "a blue bird on a branch",
                    "references": [],
                }],
            )
            request_log = []
            poll_states = iter(["processing", "success"])

            png_buffer = BytesIO()
            Image.new("RGBA", (3, 2), (30, 90, 180, 255)).save(png_buffer, format="PNG")
            png_bytes = png_buffer.getvalue()
            png_buffer.close()

            def fake_request_with_retries(worker_self, req, timeout=None):
                del worker_self, timeout
                request_log.append((req.full_url, req.get_method(), req.data))
                if req.full_url.endswith("/jobs/createTask"):
                    return json.dumps({"code": 200, "data": {"taskId": "task-123"}}).encode("utf-8")
                if "/jobs/recordInfo?" in req.full_url:
                    state = next(poll_states)
                    data = {"state": state}
                    if state == "success":
                        data["resultJson"] = {
                            "resultUrls": ["https://cdn.example/generated.png"]
                        }
                    return json.dumps({"code": 200, "data": data}).encode("utf-8")
                if req.full_url == "https://cdn.example/generated.png":
                    return png_bytes
                raise AssertionError(f"Unexpected request URL: {req.full_url}")

            worker._request_with_retries = types.MethodType(fake_request_with_retries, worker)
            worker.status_poll_interval = 0
            with patch.object(main.time, "sleep"):
                worker._mode1_generate(process_generated=False, emit_final=False)

            output_files = list((Path(temp_dir) / "output").glob("*.png"))
            self.assertEqual(len(output_files), 1)
            with Image.open(output_files[0]) as output_image:
                self.assertEqual(output_image.format, "PNG")
                self.assertEqual(output_image.size, (3, 2))

            create_calls = [entry for entry in request_log if entry[0].endswith("/jobs/createTask")]
            self.assertEqual(len(create_calls), 1)
            posted = json.loads(create_calls[0][2].decode("utf-8"))
            self.assertEqual(posted["model"], "nano-banana-2")
            self.assertEqual(posted["input"]["prompt"], "a blue bird on a branch")
            self.assertEqual(posted["input"]["output_format"], "png")
            self.assertEqual(
                len([entry for entry in request_log if "/jobs/recordInfo?" in entry[0]]),
                2,
            )


class TrustworthyPreparationContractsTests(unittest.TestCase):
    def test_csv_import_preserves_bom_quoted_commas_and_reference_values(self):
        with tempfile.TemporaryDirectory(prefix="clipart-trustworthy-csv-") as temp_dir:
            csv_path = Path(temp_dir) / "prompts.csv"
            csv_path.write_text(
                'prompt,references\n"bird, blue","ref-a.png | https://example.test/ref.png"\n',
                encoding="utf-8-sig",
                newline="",
            )
            dialog = main.CsvImportDialog.__new__(main.CsvImportDialog)
            dialog.file_path = str(csv_path)
            dialog.delimiter_combo = types.SimpleNamespace(currentData=lambda: "auto")

            text = dialog._read_csv_text()
            delimiter = dialog._detect_delimiter(text)
            rows = dialog._parse_rows(text, delimiter)
            dialog._rows = rows[1:]

            entries = dialog._build_entries(0, 1)

        self.assertEqual(delimiter, ",")
        self.assertEqual(entries, [{
            "prompt": "bird, blue",
            "references": ["ref-a.png", "https://example.test/ref.png"],
        }])

    def test_csv_import_rejects_empty_data_and_skips_blank_prompt_rows(self):
        dialog = main.CsvImportDialog.__new__(main.CsvImportDialog)
        with self.assertRaisesRegex(RuntimeError, "пуст"):
            dialog._parse_rows("\n,\n", ",")

        dialog._rows = [["", "ref-a.png"], ["  ", ""], ["usable", ""]]
        entries = dialog._build_entries(0, 1)
        self.assertEqual(entries, [
            {"prompt": "", "references": ["ref-a.png"]},
            {"prompt": "usable", "references": []},
        ])

    def test_prompt_entry_normalization_supports_json_and_caps_references(self):
        window = main.MainWindow.__new__(main.MainWindow)
        raw_entry = '{"prompt": "  keep subject  ", "references": "a | b | c | d | e | f"}'

        normalized = window._normalize_prompt_entry(raw_entry)

        self.assertEqual(normalized["prompt"], "keep subject")
        self.assertEqual(normalized["references"], ["a", "b", "c", "d", "e"])

    def test_reference_limit_is_enforced_before_resolution(self):
        worker = main.WorkerThread("mode1_generate_only", ".", worker_settings())
        references = [f"https://example.test/{index}.png" for index in range(main.MAX_REFERENCES_PER_PROMPT + 1)]

        with self.assertRaisesRegex(RuntimeError, "Максимум"):
            worker._resolve_reference_urls(references)


class TrustworthyResultContractsTests(unittest.TestCase):
    def test_result_url_extraction_accepts_supported_provider_shapes_only(self):
        worker = main.WorkerThread("mode1_generate_only", ".", worker_settings())

        self.assertEqual(
            worker._extract_result_url({"resultUrls": ["https://cdn.example/a.png"]}),
            "https://cdn.example/a.png",
        )
        self.assertEqual(
            worker._extract_result_url({"output": {"mediaUrl": "https://cdn.example/b.png"}}),
            "https://cdn.example/b.png",
        )
        with self.assertRaisesRegex(RuntimeError, "извлечь URL"):
            worker._extract_result_url({"output": {}})


if __name__ == "__main__":
    unittest.main()
