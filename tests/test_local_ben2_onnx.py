import hashlib
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from local_ben2 import (
    LocalBen2OnnxModel,
    load_local_ben2_onnx_model,
    validate_cached_model,
)


class _Input:
    name = "input"


class _FakeSession:
    def __init__(self):
        self.feed = None

    def get_inputs(self):
        return [_Input()]

    def run(self, _outputs, feed):
        self.feed = feed
        mask = np.linspace(0.0, 1.0, 16, dtype=np.float32).reshape(1, 1, 4, 4)
        return [mask]


class LocalBen2OnnxTests(unittest.TestCase):
    def test_inference_matches_source_size_and_produces_alpha(self):
        session = _FakeSession()
        model = LocalBen2OnnxModel(session)
        source = Image.new("RGB", (6, 4), (40, 80, 120))

        result = model.inference(source)

        self.assertEqual(result.mode, "RGBA")
        self.assertEqual(result.size, source.size)
        self.assertLess(result.getchannel("A").getextrema()[0], 255)
        tensor = session.feed["input"]
        self.assertEqual(tensor.shape, (1, 3, 1024, 1024))
        self.assertEqual(tensor.dtype, np.float32)
        self.assertGreaterEqual(float(tensor.min()), 0.0)
        self.assertLessEqual(float(tensor.max()), 1.0)

    def test_cached_model_requires_exact_size_and_sha256(self):
        payload = b"owned-ben2-fixture"
        expected_sha256 = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory(prefix="vibix-ben2-cache-") as temp:
            model_path = Path(temp) / "BEN2_Base.onnx"
            model_path.write_bytes(payload)

            self.assertEqual(
                validate_cached_model(
                    model_path,
                    expected_size=len(payload),
                    expected_sha256=expected_sha256,
                ),
                model_path,
            )
            with self.assertRaisesRegex(RuntimeError, "размер"):
                validate_cached_model(
                    model_path,
                    expected_size=len(payload) + 1,
                    expected_sha256=expected_sha256,
                )

    def test_refine_foreground_keeps_rgba_contract(self):
        model = LocalBen2OnnxModel(_FakeSession())

        result = model.inference(
            Image.new("RGB", (6, 4), (40, 80, 120)),
            refine_foreground=True,
        )

        self.assertEqual(result.mode, "RGBA")
        self.assertEqual(result.size, (6, 4))

    def test_loader_uses_bounded_cpu_memory_session_options(self):
        options = types.SimpleNamespace()
        fake_runtime = types.SimpleNamespace(
            SessionOptions=lambda: options,
            ExecutionMode=types.SimpleNamespace(ORT_SEQUENTIAL="sequential"),
            GraphOptimizationLevel=types.SimpleNamespace(ORT_ENABLE_BASIC="basic"),
            InferenceSession=lambda *_args, **_kwargs: _FakeSession(),
        )

        with (
            patch.dict("sys.modules", {"onnxruntime": fake_runtime}),
            patch("local_ben2.ensure_ben2_model", return_value=Path("model.onnx")),
        ):
            model = load_local_ben2_onnx_model("cache")

        self.assertIsInstance(model, LocalBen2OnnxModel)
        self.assertFalse(options.enable_cpu_mem_arena)
        self.assertFalse(options.enable_mem_pattern)
        self.assertEqual(options.execution_mode, "sequential")
        self.assertEqual(options.graph_optimization_level, "basic")
        self.assertEqual(options.intra_op_num_threads, 1)
        self.assertEqual(options.inter_op_num_threads, 1)


if __name__ == "__main__":
    unittest.main()
