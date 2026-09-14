from __future__ import annotations

import ast
import tempfile
from pathlib import Path

import pytest

from studio_module_api import ModuleRegistration
from studio_workflow_registry import WorkflowRegistryError, discover_workflows


def _fixture(root: Path, module_id: str, body: str = "return context.module_id"):
    target = root / module_id
    target.mkdir(parents=True)
    (target / "entry.py").write_text(
        'from studio_module_api import ModuleRegistration\n'
        'def register(context):\n'
        '    return ModuleRegistration(context.module_id, context.version)\n'
        'def install(shell, **kwargs):\n'
        '    context = type("C", (), {"module_id": shell})()\n'
        f'    {body}\n',
        encoding="utf-8",
    )


def test_registry_discovers_public_module_registration_without_core_switch():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _fixture(root, "text-probe")
        registry = discover_workflows(root)
        assert registry.module_ids == ("text-probe",)
        registration = registry.require("text-probe")
        assert isinstance(registration.module, ModuleRegistration)
        assert registration.module.entitlement_id == "text-probe"
        assert registration.install("text-probe") == "text-probe"


def test_registry_rejects_invalid_folder_and_registration_identity_fail_closed():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        _fixture(root, "Bad")
        with pytest.raises(WorkflowRegistryError, match="module|registration"):
            discover_workflows(root)
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        target = root / "one"
        target.mkdir()
        (target / "entry.py").write_text(
            'from studio_module_api import ModuleRegistration\n'
            'def register(context): return ModuleRegistration("other", context.version)\n'
            'def install(shell, **kwargs): return None\n', encoding="utf-8",
        )
        with pytest.raises(WorkflowRegistryError, match="identity"):
            discover_workflows(root)


def test_core_mode_selection_does_not_import_concrete_flow_implementations():
    source = Path(__file__).resolve().parents[1] / "v3_mode_selection.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imports = {
        node.module for node in ast.walk(tree)
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
        (target / "entry.py").write_text('raise RuntimeError("boom")\n', encoding="utf-8")
        with pytest.raises(WorkflowRegistryError, match="could not be loaded"):
            discover_workflows(root)


def test_builtin_entries_author_metadata_through_public_module_api():
    root = Path(__file__).resolve().parents[1] / "studio_builtin_workflows"
    for module_id in ("clipart", "pinterest", "processing"):
        source = (root / module_id / "entry.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {
            node.module for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert "studio_module_api" in imports
        assert "studio_module_runtime" not in imports
        assert any(isinstance(node, ast.FunctionDef) and node.name == "register" for node in tree.body)


def test_build_collects_builtin_workflow_adapters_generically():
    build = (Path(__file__).resolve().parents[1] / "build.ps1").read_text(encoding="utf-8")
    assert '--add-data "studio_builtin_workflows;studio_builtin_workflows"' in build
    assert '--collect-submodules "studio_builtin_workflows"' in build
