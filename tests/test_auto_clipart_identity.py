from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from studio_project_documents import ProjectDocumentService
from studio_projects import ProjectStore, ProjectStoreError
from studio_workflow_host import WorkflowHost, workflow_host_for
from v3_project_state import (
    ProjectMode, ProjectState, ProjectStateError, V3ProjectDocumentAdapter,
)
from v3_wizard import AppShell


@pytest.fixture(scope="module", autouse=True)
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()


def test_auto_host_keeps_module_identity_when_reusing_clipart_data():
    shell = AppShell(ProjectState())
    try:
        host = WorkflowHost(shell, "auto-clipart")
        assert host.module_id == "auto-clipart"
        assert host.state.scope is ProjectMode.CLIPART
        assert host.state.data is shell.state.clipart
        assert workflow_host_for(host, "auto-clipart") is host
        with pytest.raises(ValueError, match="scope"):
            workflow_host_for(host, "clipart")
        controller = object()
        host.register_workflow_controller("auto-clipart", controller)
        assert host.workflow_controller("auto-clipart") is controller
        assert shell.workflow_controller("auto-clipart") is controller
        assert shell.workflow_controller("clipart") is None
        with pytest.raises(ValueError, match="scope"):
            host.workflow_controller("clipart")
    finally:
        shell.close()


@pytest.mark.parametrize("first,second", [
    ("clipart", "auto-clipart"), ("auto-clipart", "clipart"),
])
def test_two_module_identities_cannot_share_one_shell_state(first, second):
    shell = AppShell(ProjectState())
    try:
        WorkflowHost(shell, first)
        before = shell.state.to_dict()
        with pytest.raises(ValueError, match="already bound"):
            WorkflowHost(shell, second)
        assert shell.state.to_dict() == before
        # Unrelated legacy scopes remain available for ordinary mode switching.
        assert WorkflowHost(shell, "processing").state.scope is ProjectMode.PROCESSING
    finally:
        shell.close()


def test_separate_shells_keep_automatic_and_legacy_data_independent():
    legacy = AppShell(ProjectState())
    automatic = AppShell(ProjectState())
    try:
        old = WorkflowHost(legacy, "clipart")
        new = WorkflowHost(automatic, "auto-clipart")
        new.state.common.project_name = "New collection"
        new.state.common.output_dir = "/automatic/output"
        assert old.state.common.project_name != "New collection"
        assert old.state.common.output_dir != "/automatic/output"
        assert old.state.data is not new.state.data
    finally:
        legacy.close()
        automatic.close()


def test_auto_document_roundtrip_does_not_rename_or_change_legacy_project(tmp_path):
    from clipart_project_state import ClipartProjectStateExtension
    from studio_clipart_recipe import ClipartRecipe

    store = ProjectStore(tmp_path / "projects")
    extension = ClipartProjectStateExtension()
    service = ProjectDocumentService(store, (
        V3ProjectDocumentAdapter("clipart", extensions=(extension,)),
        V3ProjectDocumentAdapter("auto-clipart", extensions=(extension,)),
    ))
    state = ProjectState().to_dict()
    legacy = service.create("clipart", "project", "Legacy", state)
    original = store.project_path(legacy.project_id).read_bytes()
    state["clipart"]["recipe"] = ClipartRecipe(theme="Winter flowers").to_dict()
    automatic = service.create("auto-clipart", "project", "Collection", state)
    session = service.open(automatic.project_id)
    assert session.editable
    session.state["common"]["project_name"] = "Edited collection"
    service.save(automatic.project_id, "Edited collection", session.state)
    reopened = service.open(automatic.project_id)
    assert reopened.record.module_id == "auto-clipart"
    assert reopened.state["common"]["project_name"] == "Edited collection"
    assert reopened.state["clipart"]["recipe"]["theme"] == "Winter flowers"
    assert store.project_path(legacy.project_id).read_bytes() == original
    # Without its own adapter this project stays read-only, never legacy fallback.
    legacy_only = ProjectDocumentService(store, (V3ProjectDocumentAdapter("clipart"),))
    assert not legacy_only.open(automatic.project_id).editable


@pytest.mark.parametrize("source,target", [
    ("clipart", "auto-clipart"), ("auto-clipart", "clipart"),
    ("auto-clipart", "processing"), ("processing", "auto-clipart"),
    ("clipart", "unknown-workflow"),
])
def test_project_store_refuses_cross_module_relabeling(tmp_path, source, target):
    store = ProjectStore(tmp_path / "projects")
    record = store.create(source, "Original", ProjectState().to_dict())
    path = store.project_path(record.project_id)
    original = path.read_bytes()
    with pytest.raises(ProjectStoreError, match="identity"):
        store.save(record.project_id, target, "Replaced", ProjectState().to_dict())
    assert path.read_bytes() == original


@pytest.mark.parametrize("mode", [ProjectMode.PROCESSING, ProjectMode.PINTEREST])
def test_auto_adapter_refuses_other_legacy_modes(mode):
    adapter = V3ProjectDocumentAdapter("auto-clipart")
    state = ProjectState(mode=mode).to_dict()
    with pytest.raises(ProjectStateError, match="scope"):
        adapter.open_state(state, adapter.current_version)
    with pytest.raises(ProjectStateError, match="scope"):
        adapter.prepare_save(state, None)


def test_unknown_module_cannot_acquire_legacy_state():
    shell = AppShell(ProjectState())
    try:
        with pytest.raises(ValueError):
            WorkflowHost(shell, "made-up-workflow")
        with pytest.raises(ProjectStateError):
            V3ProjectDocumentAdapter("made-up-workflow")
    finally:
        shell.close()


def test_ordinary_generator_has_no_collection_actions_and_keeps_old_recipe():
    from studio_clipart_recipe import ClipartRecipe
    from v3_clipart_flow import install_clipart_flow
    from v3_project_state import StepId

    state = ProjectState()
    state.clipart.recipe = ClipartRecipe(theme="Saved collection").to_dict()
    before = state.to_dict()
    shell = AppShell(state)
    try:
        host = WorkflowHost(shell, "clipart")
        controller = install_clipart_flow(host)
        project_page = shell.ensure_step_page(ProjectMode.CLIPART, StepId.PROJECT)
        assert not hasattr(project_page, "builder_button")
        assert not controller.run_queue.page.results_extension.collections_enabled
        assert controller.run_queue.page.export_sets_button.isHidden()
        assert shell.mode_label.text() == "Генерация изображений"
        assert state.to_dict() == before
    finally:
        shell.close()


def test_automatic_launch_requires_its_own_right_and_rechecks_revocation():
    from license_client import LicenseAuthorization, ModuleEntitlement
    from studio_image_run_services import ImageRunGatewayError
    from studio_module_access import authorize_module_run
    from v3_flow_runtime import FlowRunRequest

    def authorization(module):
        now = datetime.now(timezone.utc)
        return LicenseAuthorization(
            license_id="fixture", product_id="clipart-generator", device_key="fixture",
            issued_at=now, expires_at=now + timedelta(minutes=5),
            module_entitlements=(ModuleEntitlement(module, now, now + timedelta(days=1)),),
        )

    shell = AppShell(ProjectState())
    gate, prepare, factory = Mock(), Mock(return_value="project"), Mock()
    gate.authorize_run.return_value = authorization("clipart")
    host = WorkflowHost(
        shell, "auto-clipart",
        authorization_provider=lambda: authorize_module_run(gate, "auto-clipart"),
        runtime_settings_provider=lambda: {"kie_api_key": "fixture-only"},
        run_preparer=prepare, worker_factory=factory,
    )
    request = FlowRunRequest("mode1_generate_only", ".",
        {"text_generation_model": "gpt-image-2"},
        generated_prompts=[{"prompt": "fixture", "references": []}])
    try:
        with pytest.raises(ImageRunGatewayError, match="Нет доступа"):
            host.image_run_launch(request)
        prepare.assert_not_called()
        factory.assert_not_called()
        gate.authorize_run.return_value = authorization("auto-clipart")
        host.image_run_launch(request)
        assert prepare.call_count == factory.call_count == 1
        gate.authorize_run.return_value = authorization("clipart")
        with pytest.raises(ImageRunGatewayError, match="Нет доступа"):
            host.image_run_launch(request)
        assert prepare.call_count == factory.call_count == 1
    finally:
        shell.close()


def test_ordinary_result_hooks_never_open_or_plan_collections(monkeypatch):
    from clipart_run_results import ClipartRunResultsExtension
    from studio_clipart_recipe import ClipartRecipe

    state = ProjectState()
    state.clipart.recipe = ClipartRecipe(theme="Saved collection").to_dict()
    before = state.to_dict()
    dialog = Mock()
    monkeypatch.setattr("clipart_run_results.SetExportDialog", dialog)
    extension = ClipartRunResultsExtension(collections_enabled=False)
    assert not extension.seed_membership(state, None, [])
    assert extension.export_issues(state, None, []) == []
    extension.save_membership(state, {"unexpected": "ignored"})
    extension.open_export_dialog(None, state, [], review_issues=[], quality_reports=[],
        on_membership_saved=Mock(), on_fix_requested=Mock())
    dialog.assert_not_called()
    assert state.to_dict() == before
