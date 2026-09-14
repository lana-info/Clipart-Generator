from __future__ import annotations

import ast
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from studio_workflow_host import WorkflowHost, workflow_host_for
from v3_clipart_flow import install_clipart_flow
from v3_pinterest_flow import install_pinterest_flow
from v3_processing_flow import install_processing_flow
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
    assert host.state.mode is ProjectMode.CLIPART
    assert host.state.current_step is shell.state.current_step_by_mode[ProjectMode.CLIPART]
    assert host.state.common.work_dir == shell.state.common.work_dir
    assert not hasattr(host.state.common, "output_dirs")
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


def test_workflow_host_for_requires_existing_host_and_validates_scope():
    shell = AppShell(ProjectState(mode=ProjectMode.CLIPART))
    host = WorkflowHost(shell, "clipart")
    assert workflow_host_for(host, "clipart") is host
    with pytest.raises(TypeError, match="WorkflowHost"):
        workflow_host_for(shell, "clipart")
    with pytest.raises(ValueError, match="scope"):
        workflow_host_for(host, "processing")
    shell.close()



def test_workflow_facades_store_no_raw_shell_or_project_state_reference():
    shell = AppShell(ProjectState(mode=ProjectMode.CLIPART))
    host = WorkflowHost(shell, "clipart")
    forbidden = (
        "_WorkflowHost__shell_ref",
        "_WorkflowStateView__state_ref",
        "_WorkflowCommonView__state_ref",
    )
    objects = (host, host.state, host.state.common)
    for obj, name in zip(objects, forbidden):
        assert not hasattr(obj, name), name
    import gc
    for obj in objects:
        referents = gc.get_referents(obj)
        assert shell not in referents
        assert shell.state not in referents
    shell.close()

def test_workflow_host_has_no_qobject_parent_escape():
    shell = AppShell(ProjectState(mode=ProjectMode.CLIPART))
    host = WorkflowHost(shell, "clipart")
    assert not hasattr(host, "parent")
    controller = install_clipart_flow(host)
    assert controller.parent() is None
    shell.close()


def test_builtin_installers_reject_raw_app_shell():
    for module_id, installer in (
        ("clipart", install_clipart_flow),
        ("pinterest", install_pinterest_flow),
        ("processing", install_processing_flow),
    ):
        shell = AppShell(ProjectState(mode=ProjectMode(module_id)))
        with pytest.raises(TypeError, match="WorkflowHost"):
            installer(shell)
        shell.close()


def test_common_and_current_step_are_mode_scoped():
    state = ProjectState(mode=ProjectMode.CLIPART)
    state.set_output_dir_for_mode("/clipart", ProjectMode.CLIPART)
    state.set_output_dir_for_mode("/processing", ProjectMode.PROCESSING)
    state.current_step_by_mode[ProjectMode.CLIPART] = StepId.PROMPTS
    state.current_step_by_mode[ProjectMode.PROCESSING] = StepId.FILES
    shell = AppShell(state)
    host = WorkflowHost(shell, "clipart")
    assert host.state.common.output_dir == "/clipart"
    host.state.common.output_dir = "/clipart-new"
    assert state.output_dir_for_mode(ProjectMode.CLIPART) == "/clipart-new"
    assert state.output_dir_for_mode(ProjectMode.PROCESSING) == "/processing"
    state.mode = ProjectMode.PROCESSING
    assert host.state.mode is ProjectMode.CLIPART
    assert host.state.current_step is StepId.PROMPTS
    shell.close()




def test_core_capability_registry_does_not_keep_shell_alive_via_bound_callbacks():
    import gc
    import weakref
    from _studio_workflow_core import _CAPABILITIES

    class SignalStub:
        def connect(self, _callback): pass
        def disconnect(self, _callback=None): pass
        def emit(self, *_args): pass

    class ShellStub:
        def __init__(self):
            self.state = ProjectState(mode=ProjectMode.CLIPART)
            self.tokens = object()
            self.step_changed = SignalStub()
            self.run_requested = SignalStub()
            self.state_changed = SignalStub()
            self.finish_requested = SignalStub()
        def workflow_definition(self, _mode): return object()
        def set_step_page(self, *_args): pass
        def ensure_step_page(self, *_args): return object()
        def register_workflow_controller(self, *_args): pass
        def workflow_controller(self, *_args): return None

    class Owner:
        def __init__(self, shell): self.shell = shell
        def settings(self): return {}

    shell = ShellStub()
    owner = Owner(shell)
    shell_ref = weakref.ref(shell)
    host = WorkflowHost(shell, "clipart", runtime_settings_provider=owner.settings)
    token = host._capability_id
    assert token in _CAPABILITIES
    del owner
    del shell
    gc.collect()
    assert shell_ref() is None
    assert token not in _CAPABILITIES

def test_builtin_controller_stores_no_core_service_callbacks():
    shell = AppShell(ProjectState(mode=ProjectMode.CLIPART))
    host = WorkflowHost(
        shell,
        "clipart",
        runtime_settings_provider=lambda: {},
        worker_factory=lambda **_kwargs: object(),
        authorization_provider=lambda: None,
    )
    controller = install_clipart_flow(host)
    for name in (
        "runtime_settings_provider", "worker_factory", "authorization_provider",
    ):
        assert not hasattr(controller, name), name
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


def test_processing_recipe_applies_through_scoped_host():
    shell = AppShell(ProjectState(mode=ProjectMode.PROCESSING))
    host = WorkflowHost(shell, "processing")
    controller = install_processing_flow(host)
    page = controller.pages[StepId.GOAL]
    page._select("basic_enhancement", True)
    assert shell.state.processing.recipe == "basic_enhancement"
    assert shell.state.processing.operations.unsharp is True
    shell.close()


def test_clipart_builder_opens_through_scoped_host(monkeypatch):
    from PyQt6.QtWidgets import QDialog
    from studio_clipart_builder_ui import ClipartBuilderDialog

    shell = AppShell(ProjectState(mode=ProjectMode.CLIPART))
    host = WorkflowHost(shell, "clipart")
    controller = install_clipart_flow(host)
    page = controller.pages[StepId.PROJECT]
    monkeypatch.setattr(
        ClipartBuilderDialog, "exec", lambda self: QDialog.DialogCode.Rejected
    )
    page._open_builder()
    shell.close()
