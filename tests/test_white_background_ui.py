"""Actual Qt contracts for the owner-approved local white-background method."""
import builtins
import importlib.util
import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from studio_workflow_host import WorkflowHost
from v3_processing_flow import ProcessingPipelinePage, install_processing_flow
from v3_project_state import ProjectMode, ProjectState, StepId
from v3_wizard import AppShell


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def white_state():
    state = ProjectState(mode=ProjectMode.PROCESSING)
    state.processing.operations.remove_background = True
    state.processing.operations.upscale_before = False
    state.processing.operations.remove_background_provider = "local_white_background"
    state.set_step(StepId.PIPELINE)
    return ProjectState.from_dict(state.to_dict())


@pytest.mark.parametrize("available", [True, False])
def test_restoration_keeps_method_and_hides_other_provider_controls(app, available):
    state = white_state()
    with patch("white_background.white_background_available", return_value=available):
        page = ProcessingPipelinePage(state, lambda: None)
        combo = page.operation_widgets["remove_background_provider"]
        assert combo.currentData() == "local_white_background"
        assert combo.model().item(combo.currentIndex()).isEnabled() == available
        assert state.processing.operations.remove_background_provider == "local_white_background"
        assert not page.white_background_note.isHidden()
        for name in page._BACKGROUND_INTERNAL_CONTROLS:
            if name != "remove_background_provider":
                assert page.operation_widgets[name].isHidden(), name
        if available:
            assert page.validation_issues() == ()
            assert page.white_background_note.text() == "Чёткий контур без мягких теней. Обработка локально."
        else:
            assert page.validation_issues() == ("white_background_unavailable",)
            assert "U2Net" in page.white_background_note.text()
            assert "U2Net" in combo.itemData(combo.currentIndex(), Qt.ItemDataRole.ToolTipRole)
        page.close()


def test_combo_signals_toggle_note_and_preserve_method_when_disabled(app):
    state = white_state()
    changed = []
    with patch("white_background.white_background_available", return_value=True) as availability:
        page = ProcessingPipelinePage(state, lambda: changed.append(True))
        combo = page.operation_widgets["remove_background_provider"]
        combo.setCurrentIndex(combo.findData("local_chroma_key"))
        assert state.processing.operations.remove_background_provider == "local_chroma_key"
        assert page.white_background_note.isHidden()
        assert not page.operation_widgets["chroma_key_color"].isHidden()
        combo.setCurrentIndex(combo.findData("local_white_background"))
        assert changed
        assert not page.white_background_note.isHidden()
        availability.return_value = False
        page.refresh_from_state()
        assert combo.currentData() == "local_white_background"
        assert not combo.model().item(combo.currentIndex()).isEnabled()
        assert page.validation_issues() == ("white_background_unavailable",)
        page.operation_widgets["remove_background"].setChecked(False)
        assert page.white_background_note.isHidden()
        assert page.validation_issues() == ("processing_operation_required",)
        page.operation_widgets["remove_background"].setChecked(True)
        availability.return_value = True
        page.refresh_from_state()
        assert combo.model().item(combo.currentIndex()).isEnabled()
        assert page.validation_issues() == ()
        assert "недоступен" not in combo.toolTip()
        page.close()


def test_actual_shell_blocks_next_for_restored_unavailable_method(app):
    state = white_state()
    with patch("white_background.white_background_available", return_value=False):
        shell = AppShell(state)
        controller = install_processing_flow(WorkflowHost(shell, "processing"))
        assert not shell.next_button.isEnabled()
        assert "U2Net" in shell.next_button.toolTip()
        shell.next_button.click()
        assert state.current_step is StepId.PIPELINE
        assert not shell.validation_label.text()
        shell.go_next()
        assert state.current_step is StepId.PIPELINE
        assert "U2Net" in shell.validation_label.text()
        assert "rembg/onnxruntime" in shell.validation_label.text()
        combo = controller.pipeline_page.operation_widgets["remove_background_provider"]
        combo.setCurrentIndex(combo.findData("local_chroma_key"))
        assert shell.next_button.isEnabled()
        assert not shell.next_button.toolTip()
        shell.close()


def test_constructing_editor_never_loads_model_session_or_uses_network(app, tmp_path):
    original_import = builtins.__import__
    original_find_spec = importlib.util.find_spec
    cached_model = tmp_path / "u2net.onnx"
    cached_model.write_bytes(b"dummy readiness fixture")

    def installed_runtime(name, *args, **kwargs):
        if name in {"rembg", "onnxruntime"}:
            return object()
        return original_find_spec(name, *args, **kwargs)

    def safe_import(name, *args, **kwargs):
        if name.split(".")[0] in {"rembg", "onnxruntime"}:
            raise AssertionError("UI attempted to load the segmentation runtime")
        return original_import(name, *args, **kwargs)

    with patch("white_background.cached_u2net_model_path", return_value=cached_model), \
            patch("importlib.util.find_spec", side_effect=installed_runtime), \
            patch("builtins.__import__", side_effect=safe_import), \
            patch("socket.socket", side_effect=AssertionError("UI attempted network access")):
        page = ProcessingPipelinePage(white_state(), lambda: None)
        assert page.operation_widgets["remove_background_provider"].currentData() == "local_white_background"
        page.close()
