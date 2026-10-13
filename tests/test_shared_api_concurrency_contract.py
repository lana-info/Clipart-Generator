"""Offline worker-limit and compact-control regression checks, no Qt installed."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def _remote_limit_method():
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    worker = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "WorkerThread")
    method = next(node for node in worker.body if isinstance(node, ast.FunctionDef) and node.name == "_remote_worker_limit")
    namespace = {"MAX_REMOTE_CONCURRENCY": 6}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), str(ROOT / "main.py"), "exec"), namespace)
    return namespace["_remote_worker_limit"]


class SharedApiConcurrencyTests(unittest.TestCase):
    def test_global_cap_counts_all_providers_together(self):
        method = _remote_limit_method()
        for requested in range(1, 6):
            with self.subTest(requested=requested):
                worker = SimpleNamespace(
                    api_concurrency=requested, kie_concurrency=requested,
                    photoroom_concurrency=requested, fal_concurrency=requested,
                    _uses_kie_generation=lambda: True, _uses_fal_generation=lambda: True,
                    _uses_atlascloud_generation=lambda: True, _uses_piapi_generation=lambda: True,
                    _uses_any_kie_upscale=lambda: False, _uses_kie_remove_bg=lambda: False,
                    _uses_photoroom_remove_bg=lambda: True,
                    _uses_any_fal_upscale=lambda: False, _uses_fal_remove_bg=lambda: False,
                )
                self.assertEqual(method(worker, include_generation=True, include_processing=True), requested)
                self.assertEqual(method(worker, include_generation=False, include_processing=True), requested)

    def test_old_projects_with_independent_limits_still_run(self):
        method = _remote_limit_method()
        worker = SimpleNamespace(
            api_concurrency=None, kie_concurrency=1, photoroom_concurrency=2, fal_concurrency=3,
            _uses_kie_generation=lambda: False, _uses_fal_generation=lambda: True,
            _uses_atlascloud_generation=lambda: False, _uses_piapi_generation=lambda: False,
            _uses_any_kie_upscale=lambda: False, _uses_kie_remove_bg=lambda: False,
            _uses_photoroom_remove_bg=lambda: True,
            _uses_any_fal_upscale=lambda: False, _uses_fal_remove_bg=lambda: False,
        )
        self.assertEqual(method(worker, include_generation=True, include_processing=True), 5)

    def test_compact_object_counts_remain_numeric_spinboxes_without_buttons(self):
        tree = ast.parse((ROOT / "studio_clipart_builder_ui.py").read_text(encoding="utf-8"))
        builder = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ClipartBuilderDialog")
        structure = next(n for n in builder.body if isinstance(n, ast.FunctionDef) and n.name == "_structure")
        body = ast.unparse(structure)
        self.assertIn("spin = PlainNumberSpinBox()", body)
        self.assertIn("def wheelEvent", (ROOT / "studio_clipart_builder_ui.py").read_text(encoding="utf-8"))
        self.assertIn("setFixedWidth(104)", body)
        self.assertIn("setMaximumWidth(540)", body)
        self.assertIn("self.counts[key] = spin", body)


if __name__ == "__main__":
    unittest.main()
