"""Exercise real home/controller composition without providers or real licenses."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from PyQt6.QtWidgets import QApplication

from license_client import LicenseAuthorization, LicenseError, ModuleEntitlement
from studio_image_run_services import ImageRunGatewayError
from v3_flow_runtime import FlowRunRequest
from v3_mode_selection import V3ApplicationView
from v3_project_state import PinterestPinData, ProjectMode


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def authorization(*modules):
    now = datetime.now(timezone.utc)
    return LicenseAuthorization(
        license_id="fixture", product_id="clipart-generator", device_key="fixture",
        issued_at=now, expires_at=now + timedelta(minutes=5),
        module_entitlements=tuple(
            ModuleEntitlement(module, now, now + timedelta(days=1))
            for module in modules
        ),
    )


def request_for(mode):
    if mode is ProjectMode.PROCESSING:
        return FlowRunRequest("mode2_process", ".", {"remove_bg": False},
                              selected_files=["fixture.png"])
    return FlowRunRequest("mode1_generate_only", ".",
                          {"text_generation_model": "gpt-image-2"},
                          generated_prompts=[{"prompt": "fixture", "references": []}])


@pytest.mark.parametrize("mode", tuple(ProjectMode))
def test_existing_card_launch_rechecks_exact_right_and_revocation(app, tmp_path, mode):
    gate = Mock()
    # Give every *other* module, so product access cannot accidentally suffice.
    gate.authorize_run.return_value = authorization(
        *(other.value for other in ProjectMode if other is not mode)
    )
    worker = Mock()
    factory = Mock(return_value=worker)
    view = V3ApplicationView(
        draft_path=tmp_path / "draft.json", license_gate=gate,
        runtime_settings_provider=lambda: {"kie_api_key": "fixture-only"},
        worker_factory=factory,
    )
    try:
        view.mode_selection.mode_cards[mode].start_button.click()
        assert view.project_state.mode is mode
        assert view.stack.currentWidget() is view.shell
        controller = view.shell.workflow_controller(mode.value)
        assert controller is not None
        factory.assert_not_called()
        request = request_for(mode)

        with patch.object(view, "_prepare_project_run", wraps=view._prepare_project_run) as prepare:
            with pytest.raises(ImageRunGatewayError, match="Нет доступа"):
                controller.shell.image_run_launch(request)
            prepare.assert_not_called()
            factory.assert_not_called()

            gate.authorize_run.return_value = authorization(mode.value)
            controller.shell.image_run_launch(request)
            assert factory.call_count == 1
            assert factory.call_args.kwargs["project_id"] == view._active_project_id
            # Creating a run handle alone must not start a paid worker.
            worker.start.assert_not_called()
            prepare.reset_mock()

            gate.authorize_run.return_value = authorization()
            with pytest.raises(ImageRunGatewayError, match="Нет доступа"):
                controller.shell.image_run_launch(request)
            assert factory.call_count == 1
            prepare.assert_not_called()
            assert gate.authorize_run.call_count == 3
    finally:
        view.close()
        view.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("mode", tuple(ProjectMode))
def test_existing_project_resume_preserves_mode_without_automatic_run(app, tmp_path, mode):
    factory = Mock(side_effect=AssertionError("Opening a project must not run work"))
    path = tmp_path / "draft.json"
    first = V3ApplicationView(draft_path=path, worker_factory=factory)
    try:
        first.mode_selection.mode_cards[mode].start_button.click()
        first.project_state.common.project_name = "Saved fixture"
        first.shell.mark_dirty()
        project_id = first._active_project_id
        expected = first.project_state.to_dict()
    finally:
        first.close()
        first.deleteLater()
        app.processEvents()
    restored = V3ApplicationView(draft_path=path, worker_factory=factory)
    try:
        assert restored.continue_saved_project(project_id)
        assert restored.project_state.to_dict() == expected
        assert restored.shell.workflow_controller(mode.value) is not None
        factory.assert_not_called()
    finally:
        restored.close()
        restored.deleteLater()
        app.processEvents()


def test_pinterest_local_worker_uses_its_own_right_and_saves_before_creation(app, tmp_path):
    from v3_pinterest_flow import PinterestPinRunRequest

    gate = Mock()
    gate.authorize_run.return_value = authorization("clipart", "processing")
    view = V3ApplicationView(draft_path=tmp_path / "draft.json", license_gate=gate)
    request = PinterestPinRunRequest(
        work_dir=str(tmp_path), product_path="fixture.png", pin=PinterestPinData(),
        settings={}, queue_items=(),
    )
    try:
        view.mode_selection.mode_cards[ProjectMode.PINTEREST].start_button.click()
        controller = view.shell.workflow_controller("pinterest")
        with patch("v3_pinterest_flow.PinterestPinWorkerAdapter") as worker:
            with pytest.raises(LicenseError, match="Нет доступа"):
                controller.create_worker_for_request(request)
            worker.assert_not_called()

            gate.authorize_run.return_value = authorization("pinterest")
            with patch.object(view._project_store, "save", side_effect=OSError("disk")):
                with pytest.raises(OSError, match="Не удалось сохранить"):
                    controller.create_worker_for_request(request)
            worker.assert_not_called()

            assert controller.create_worker_for_request(request) is worker.return_value
            worker.assert_called_once_with(request)
            worker.return_value.start.assert_not_called()
    finally:
        view.close()
        view.deleteLater()
        app.processEvents()
