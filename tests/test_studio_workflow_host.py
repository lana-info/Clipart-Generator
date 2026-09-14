from __future__ import annotations

import ast
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from studio_workflow_host import WorkflowHost, workflow_host_for
from v3_project_state import ProjectMode, ProjectState, StepId
from v3_wizard import AppShell


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module", autouse=True)
def _qt_app():
    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()


def test_workflow_host_exposes_scoped_state_not_full_shell():
    shell = AppShell(ProjectState(mode=ProjectMode.CLIPART))
    host = WorkflowHost(shell, "clipart")
    assert host.state.data is shell.state.clipart
    assert host.state.common is shell.state.common
    assert not hasattr(host.state, "processing")
    assert not hasattr(host.state, "pinterest")
    assert not hasattr(host, "main_window")
    assert not hasattr(host, "worker")
    assert not hasattr(host, "services")
    shell.close()


def test_scoped_state_rejects_cross_mode_mutation():
    shell = AppShell(ProjectState(mode=ProjectMode.CLIPART))
    host = WorkflowHost(shell, "clipart")
    with pytest.raises(ValueError, match="scope"):
        host.state.set_output_dir_for_mode("/tmp/no", ProjectMode.PROCESSING)
    host.state.set_step(StepId.PROMPTS)
    assert shell.state.current_step is StepId.PROMPTS
    shell.close()


def test_workflow_host_for_reuses_existing_host_and_validates_scope():
    shell = AppShell(ProjectState(mode=ProjectMode.CLIPART))
    host = workflow_host_for(shell, "clipart")
    assert workflow_host_for(host, "clipart") is host
    with pytest.raises(ValueError, match="scope"):
        workflow_host_for(host, "processing")
    shell.close()


def test_builtin_flows_do_not_import_app_shell_implementation():
    for filename in (
        "v3_clipart_flow.py", "v3_pinterest_flow.py", "v3_processing_flow.py",
    ):
        tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert "v3_wizard" not in imported
