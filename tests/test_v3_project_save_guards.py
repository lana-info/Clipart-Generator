"""Signed workflow state survives failed autosave and legacy preference migration."""
import json
import os
import sys
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from tests.test_studio_existing_module_launch import authorization, installed_delivery
from v3_mode_selection import V3ApplicationView
from v3_project_state import ProjectMode, PromptEntry, migrate_v2_config


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def signed_view(app, tmp_path, monkeypatch, request):
    mode = request.param
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr("v3_mode_selection.default_work_directory", lambda: work)
    gate = Mock()
    gate.current_authorization = authorization(mode.value)
    gate.authorize_run.return_value = gate.current_authorization
    delivery = installed_delivery(tmp_path, gate, mode.value)
    factory = Mock(side_effect=AssertionError("State changes must not start work"))
    options = dict(draft_path=tmp_path / "data" / "draft.json", license_gate=gate,
                   module_delivery=delivery, worker_factory=factory)
    view = V3ApplicationView(**options)
    view._handle_mode_selected(mode.value)
    assert view.shell.workflow_controller(mode.value) is not None
    assert view._active_project_id is None  # untouched projects are not saved
    view.project_state.common.project_name = "Initial content"
    view.shell.mark_dirty()
    assert view._active_project_id is not None
    yield view, options, factory
    view.close()
    view.deleteLater()
    app.processEvents()
    factory.assert_not_called()


@pytest.mark.parametrize("signed_view", tuple(ProjectMode), indirect=True)
def test_close_retries_failed_autosave_and_reopen_preserves_edits(app, signed_view):
    view, options, _ = signed_view
    project_id = view._active_project_id
    view.project_state.common.project_name = "Important edit after autosave failure"
    with patch.object(view._project_store, "save", side_effect=OSError("disk")):
        view.shell.mark_dirty()
    assert not view.shell.save_error_label.isHidden()
    assert view.close()
    restored = V3ApplicationView(**options)
    try:
        assert restored.continue_saved_project(project_id)
        assert restored.project_state.common.project_name == "Important edit after autosave failure"
        assert restored._project_store.load(project_id).module_id == view.shell.state.mode.value
    finally:
        restored.close()
        restored.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("signed_view", tuple(ProjectMode), indirect=True)
@pytest.mark.parametrize("failure", ("project", "draft", "preferences"))
def test_persistent_failure_blocks_close_and_every_project_transition(signed_view, failure):
    view, _, _ = signed_view
    source, project_id = view.shell, view._active_project_id
    source.state.common.project_name = "Keep this unsaved edit"
    target = {
        "project": patch.object(view._project_store, "save", side_effect=OSError("disk")),
        "draft": patch("v3_mode_selection.save_project_draft", side_effect=OSError("disk")),
        "preferences": patch("v3_mode_selection.save_preferences_atomic", side_effect=OSError("disk")),
    }[failure]
    with target:
        source.mark_dirty()
        assert not view.close()
        view.show_new_project()
        assert view.stack.currentWidget() is source
        view.show_mode_switcher()
        assert view.stack.currentWidget() is source
        view._handle_mode_selected(source.state.mode.value)
        assert view.shell is source
        assert not view.continue_saved_project(project_id)
        assert not view.continue_last_project()
        view._open_composer()
        assert view._composer_page_handle is None
        assert view._active_project_id == project_id
        assert source.state.common.project_name == "Keep this unsaved edit"
        assert not source.save_error_label.isHidden()
    view.show_new_project()
    assert view.stack.currentWidget() is view.mode_selection
    assert view._project_store.load(project_id).state["common"]["project_name"] == "Keep this unsaved edit"


@pytest.mark.parametrize("signed_view", tuple(ProjectMode), indirect=True)
@pytest.mark.parametrize("busy_kind", ("run", "controller"))
def test_busy_workflow_blocks_close_and_new_project(signed_view, busy_kind):
    view, _, _ = signed_view
    source, project_id = view.shell, view._active_project_id
    controller = source.workflow_controller(source.state.mode.value)
    busy = (patch.object(source, "active_run_controller", return_value=controller)
            if busy_kind == "run" else patch.object(controller, "is_busy", return_value=True, create=True))
    with busy, patch.object(view._project_store, "save") as save:
        assert not view.close()
        view.show_new_project()
        view._handle_mode_selected(source.state.mode.value)
        assert not view.continue_saved_project(project_id)
        assert not view.continue_last_project()
        assert view.shell is source
        assert view.stack.currentWidget() is source
        assert view._active_project_id == project_id
        save.assert_not_called()


LEGACY_CONFIG = {
    "text_generation_model": "flux-2/pro-text-to-image",
    "text_generation_ratio": "16:9", "text_generation_resolution": "2K",
    "reference_generation_model": "flux-2/pro-image-to-image",
    "reference_generation_ratio": "4:3", "reference_generation_resolution": "2K",
    "retries": 7, "timeout": 123, "generation_wait_timeout": 456,
    "status_poll_interval": 15, "kie_upload_path": "legacy-fixture",
}


def signed_generation_plan(view):
    controller = view.shell.workflow_controller("clipart")
    payload = sys.modules[type(controller).__module__]
    view.project_state.clipart.prompts = [PromptEntry("Offline fixture")]
    # The same signed workflow function builds the real run request. No worker.
    return payload.build_clipart_run_request(view.project_state).settings


def assert_legacy_plan(plan):
    for key, value in LEGACY_CONFIG.items():
        assert plan[key] == value


def test_actual_startup_migrates_legacy_plan_and_persists_new_project_settings(app, tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "legacy-data"))
    import main
    gate = Mock()
    gate.current_authorization = authorization("clipart")
    gate.authorize_run.return_value = gate.current_authorization
    delivery = installed_delivery(tmp_path, gate, "clipart")
    work = tmp_path / "work"
    work.mkdir()
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"last_work_dir": str(work), **LEGACY_CONFIG}), encoding="utf-8")
    credentials = Mock()
    credentials.load.return_value = {}
    with patch("main.CONFIG_FILE", str(config)), \
            patch.object(main.QStandardPaths, "writableLocation", return_value=str(tmp_path / "data")), \
            patch("main.ProviderCredentialStore", return_value=credentials), \
            patch("v3_license.OnlineLicenseGate", return_value=gate), \
            patch("studio_module_delivery.StudioModuleDelivery", return_value=delivery):
        view = main.create_v3_application_window()
    try:
        view._handle_mode_selected("clipart")
        assert_legacy_plan(signed_generation_plan(view))
        view.show_new_project()
        view._handle_mode_selected("clipart")
        assert_legacy_plan(signed_generation_plan(view))
        view.project_state.runtime.timeout = 234
        view.project_state.clipart.generation.ratio = "4:3"
        view.shell.mark_dirty()
        assert view.close()
        prefs = json.loads((tmp_path / "data" / "preferences.json").read_text(encoding="utf-8"))
        assert prefs["clipart"]["runtime"]["timeout"] == 234
        assert prefs["clipart"]["generation"]["ratio"] == "4:3"
        # Restart without a legacy config: disk preferences are authoritative.
        restored = V3ApplicationView(draft_path=tmp_path / "data" / "project_state.json",
                                     license_gate=gate, module_delivery=delivery)
        try:
            restored._handle_mode_selected("clipart")
            plan = signed_generation_plan(restored)
            assert plan["timeout"] == 234
            assert plan["text_generation_ratio"] == "4:3"
            assert plan["text_generation_model"] == LEGACY_CONFIG["text_generation_model"]
            assert plan["retries"] == 7
        finally:
            restored.close()
            restored.deleteLater()
    finally:
        view.close()
        view.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("signed_view", tuple(ProjectMode), indirect=True)
def test_explicit_saved_runtime_and_generation_override_legacy(signed_view):
    view, _, _ = signed_view
    mode = view.project_state.mode
    view.project_state.runtime.timeout = 234
    view.project_state.runtime.retries = 2
    if mode is not ProjectMode.PROCESSING:
        getattr(view.project_state, mode.value).generation.ratio = "4:3"
    view.shell.mark_dirty()
    view._legacy_project = migrate_v2_config(LEGACY_CONFIG)
    view.show_new_project()
    view._handle_mode_selected(mode.value)
    assert view.project_state.runtime.timeout == 234
    assert view.project_state.runtime.retries == 2
    if mode is not ProjectMode.PROCESSING:
        assert getattr(view.project_state, mode.value).generation.ratio == "4:3"
