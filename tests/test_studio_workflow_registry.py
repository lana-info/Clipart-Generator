from __future__ import annotations

import ast
import tempfile
from pathlib import Path

import pytest

from studio_workflow_registry import WorkflowRegistryError, discover_workflows


def _fixture(root: Path, folder: str, module_id: str, body: str = "return module_id"):
    target = root / folder
    target.mkdir(parents=True)
    (target / "entry.py").write_text(
        f'MODULE_ID = {module_id!r}\n'
        'def install(shell, **kwargs):\n'
        f'    module_id = MODULE_ID\n    {body}\n',
        encoding="utf-8",
    )


def test_registry_discovers_arbitrary_fixture_without_module_specific_core_switch():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _fixture(root, "text_fixture", "text-probe")
        registry = discover_workflows(root)
        assert registry.module_ids == ("text-probe",)
        assert registry.require("text-probe").install(object()) == "text-probe"


def test_registry_rejects_duplicate_and_invalid_module_ids_fail_closed():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _fixture(root, "one", "same")
        _fixture(root, "two", "same")
        with pytest.raises(WorkflowRegistryError, match="Duplicate"):
            discover_workflows(root)
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _fixture(root, "bad", "../bad")
        with pytest.raises(WorkflowRegistryError, match="module id"):
            discover_workflows(root)


def test_core_mode_selection_does_not_import_concrete_flow_implementations():
    source = Path(__file__).resolve().parents[1] / "v3_mode_selection.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "v3_clipart_flow" not in imports
    assert "v3_pinterest_flow" not in imports
    assert "v3_processing_flow" not in imports


def test_registry_wraps_broken_entry_without_partial_registration():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        target = root / "broken"
        target.mkdir()
        (target / "entry.py").write_text(
            'MODULE_ID = "broken"\nraise RuntimeError("boom")\n',
            encoding="utf-8",
        )
        with pytest.raises(WorkflowRegistryError, match="could not be loaded"):
            discover_workflows(root)


def test_build_collects_builtin_workflow_adapters_generically():
    build = (Path(__file__).resolve().parents[1] / "build.ps1").read_text(encoding="utf-8")
    assert '--add-data "studio_builtin_workflows;studio_builtin_workflows"' in build
    assert '--collect-submodules "studio_builtin_workflows"' in build
