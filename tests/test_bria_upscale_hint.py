"""Owner-approved UX guard for Fal Bria upscales after background removal.

Facts behind the fix (TASKS.md «Аудит краёв 2026-10-30», artifacts
ac-c1-owner-20261030): Fal Bria x4 after the background removal washes
semi-transparent clipart (internal alpha holes 26.78% -> 31.24%, grey smudges),
while Local Real-ESRGAN stays clean (0.07%/0.66%). The approved mitigation:
an unobtrusive hint when a Bria upscale model is selected for the stage after
the cut; the default provider for that stage stays Local Real-ESRGAN.
"""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from provider_upscale_contract import (
    FAL_BRIA_INCREASE_RESOLUTION_MODEL_ID,
    FAL_BRIA_UPSCALE_MODEL_ID,
    FAL_TOPAZ_TRANSPARENT_MODEL_ID,
)
from v3_mode_selection import V3ApplicationView
from v3_processing_flow import ProcessingPipelinePage
from v3_project_state import ImageOperationData, ProjectMode, ProjectState

# Verbatim owner-approved hint text (2026-10-30). The single source of truth
# lives in v3_image_processing_ui.BRIA_HINT_TEXT; this literal keeps the
# contract checked even if the constant is refactored away.
BRIA_HINT_TEXT = (
    "Bria ×4 — модель для фотографий: на клипарте с мягкими краями "
    "(акварель, пух, тонкие штрихи) может „вымывать“ полупрозрачные места "
    "и оставлять серые разводы. Для клипарта рекомендуем Local Real-ESRGAN."
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def after_cut_state(provider: str, model: str) -> ProjectState:
    state = ProjectState(mode=ProjectMode.PROCESSING)
    operations = state.processing.operations
    operations.remove_background = True
    operations.upscale_after = True
    operations.upscale_after_provider = provider
    operations.fal_upscale_after_model = model
    if provider == "fal":
        operations.fal_upscale_after_scale = 4
    return ProjectState.from_dict(state.to_dict())


def test_pipeline_hint_follows_bria_model_selection(app):
    state = after_cut_state("fal", FAL_BRIA_INCREASE_RESOLUTION_MODEL_ID)
    page = ProcessingPipelinePage(state, lambda: None)
    try:
        assert not page.bria_upscale_note.isHidden()
        assert page.bria_upscale_note.text() == BRIA_HINT_TEXT
        assert "Local Real-ESRGAN" in page.bria_upscale_note.text()
        model = page.operation_widgets["fal_upscale_after_model"]
        model.setCurrentIndex(model.findData(FAL_TOPAZ_TRANSPARENT_MODEL_ID))
        assert page.bria_upscale_note.isHidden()
        model.setCurrentIndex(model.findData(FAL_BRIA_UPSCALE_MODEL_ID))
        assert not page.bria_upscale_note.isHidden()
        model.setCurrentIndex(model.findData(FAL_TOPAZ_TRANSPARENT_MODEL_ID))
        assert page.bria_upscale_note.isHidden()
    finally:
        page.close()


def test_pipeline_hint_hidden_for_non_fal_providers_and_other_stages(app):
    page = ProcessingPipelinePage(
        after_cut_state("local_realesrgan", FAL_BRIA_INCREASE_RESOLUTION_MODEL_ID),
        lambda: None,
    )
    try:
        assert page.bria_upscale_note.isHidden()
        provider = page.operation_widgets["upscale_after_provider"]
        provider.setCurrentIndex(provider.findData("fal"))
        assert not page.bria_upscale_note.isHidden()
        provider.setCurrentIndex(provider.findData("kie"))
        assert page.bria_upscale_note.isHidden()
    finally:
        page.close()
    before_state = ProjectState(mode=ProjectMode.PROCESSING)
    before_operations = before_state.processing.operations
    before_operations.upscale_before = True
    before_operations.upscale = False
    before_operations.upscale_before_provider = "fal"
    before_operations.fal_upscale_model = FAL_BRIA_INCREASE_RESOLUTION_MODEL_ID
    before_operations.upscale_after = True
    before_operations.upscale_after_provider = "local_realesrgan"
    page = ProcessingPipelinePage(
        ProjectState.from_dict(before_state.to_dict()), lambda: None
    )
    try:
        assert page.bria_upscale_note.isHidden()
    finally:
        page.close()


def test_saved_project_settings_roundtrip_without_rewrite(app):
    state = after_cut_state("fal", FAL_BRIA_INCREASE_RESOLUTION_MODEL_ID)
    state.processing.operations.fal_upscale_after_scale = 4
    payload = state.to_dict()
    restored = ProjectState.from_dict(payload)
    operations = restored.processing.operations
    assert operations.upscale_after_provider == "fal"
    assert operations.fal_upscale_after_model == FAL_BRIA_INCREASE_RESOLUTION_MODEL_ID
    assert operations.fal_upscale_after_scale == 4
    restored_local = ProjectState.from_dict(
        after_cut_state("local_realesrgan", FAL_BRIA_UPSCALE_MODEL_ID).to_dict()
    )
    assert restored_local.processing.operations.upscale_after_provider == "local_realesrgan"


def test_new_project_defaults_keep_local_realesrgan_after_cut():
    fresh = ImageOperationData()
    assert fresh.upscale_after_provider == "local_realesrgan"
    assert fresh.upscale_before_provider == "kie"
    for mode in (ProjectMode.PROCESSING, ProjectMode.CLIPART):
        state = ProjectState(mode=mode)
        data = state.processing if mode is ProjectMode.PROCESSING else state.clipart
        assert data.operations.upscale_after_provider == "local_realesrgan"
        assert data.operations.upscale_before_provider == "kie"
        assert data.operations.fal_upscale_after_model == FAL_BRIA_UPSCALE_MODEL_ID


def _fixture_authorization():
    now = datetime.now(timezone.utc)
    from license_client import LicenseAuthorization, ModuleEntitlement

    return LicenseAuthorization(
        "fixture", "clipart-generator", "device", now, now + timedelta(minutes=5),
        module_entitlements=(
            ModuleEntitlement("auto-clipart", now, now + timedelta(days=1)),
        ),
    )


@pytest.fixture
def auto_clipart(tmp_path):
    gate = Mock(status_text="Test", verification_text="Test")
    gate.current_authorization = _fixture_authorization()
    gate.authorize_run.return_value = gate.current_authorization
    worker = Mock()
    view = V3ApplicationView(
        draft_path=tmp_path / "draft.json", license_gate=gate,
        worker_factory=worker,
        runtime_settings_provider=lambda: {"kie_api_key": "fixture-only"},
    )
    view._handle_module_action("auto-clipart", "open")
    controller = view.shell.workflow_controller("auto-clipart")
    controller.save_timer.stop()
    yield controller
    if controller.run_queue.session:
        controller.run_queue.session.running = False
    QApplication.processEvents()
    view.close()
    view.deleteLater()
    QApplication.processEvents()


def test_auto_clipart_hint_follows_bria_model_selection(auto_clipart):
    controller = auto_clipart
    operations = controller.shell.state.data.operations
    assert controller.bria_upscale_note.isHidden()
    controller.upscale_provider.setCurrentIndex(
        controller.upscale_provider.findData("fal")
    )
    assert not controller.bria_upscale_note.isHidden()
    controller.upscale_model.setCurrentIndex(
        controller.upscale_model.findData(FAL_BRIA_INCREASE_RESOLUTION_MODEL_ID)
    )
    controller.upscale_scale.setCurrentIndex(controller.upscale_scale.findData(4))
    assert not controller.bria_upscale_note.isHidden()
    assert controller.bria_upscale_note.text() == BRIA_HINT_TEXT
    assert operations.upscale_after_provider == "fal"
    controller.upscale_model.setCurrentIndex(
        controller.upscale_model.findData(FAL_TOPAZ_TRANSPARENT_MODEL_ID)
    )
    assert controller.bria_upscale_note.isHidden()
    controller.upscale_provider.setCurrentIndex(
        controller.upscale_provider.findData("local_realesrgan")
    )
    assert controller.bria_upscale_note.isHidden()


class MainWindowUpscaleSettingsTests(unittest.TestCase):
    """Default and saved-config contract of the desktop app settings."""

    @classmethod
    def setUpClass(cls):
        import main

        cls.main = main
        cls.app_qt = main.QApplication.instance() or main.QApplication([])

    def _close(self, window):
        window.settings_save_timer.stop()
        window.api_key_mask_timer.stop()
        window.deleteLater()
        self.app_qt.processEvents()

    def test_fresh_config_defaults_to_local_realesrgan_after_cut(self):
        with tempfile.TemporaryDirectory(prefix="bria-hint-default-") as temp_dir:
            with patch.multiple(
                self.main,
                CONFIG_FILE=str(Path(temp_dir) / "config.json"),
                USER_DATA_DIR=str(temp_dir),
            ), \
                patch.object(self.main, "ENV_FILE", str(Path(temp_dir) / ".env")), \
                patch.object(
                    self.main, "PROMPTS_STORAGE_FILE", str(Path(temp_dir) / "prompts.json")
                ), \
                patch.object(
                    self.main, "LICENSE_CACHE_FILE", str(Path(temp_dir) / "license.json")
                ), \
                patch.object(
                    self.main.MainWindow, "_migrate_legacy_local_files", return_value=None
                ), \
                patch.object(self.main.QTimer, "singleShot"):
                window = self.main.MainWindow()
                try:
                    self.assertEqual(
                        window.upscale_after_provider_combo.currentData(),
                        "local_realesrgan",
                    )
                    self.assertEqual(
                        window.config.get("upscale_after_provider"), "local_realesrgan"
                    )
                    self.assertTrue(window.upscale_after_note.text())
                finally:
                    self._close(window)

    def test_saved_fal_bria_settings_survive_reload(self):
        with tempfile.TemporaryDirectory(prefix="bria-hint-saved-") as temp_dir:
            (Path(temp_dir) / "config.json").write_text(
                json.dumps(
                    {
                        "upscale_after": True,
                        "upscale_after_provider": "fal",
                        "fal_upscale_after_model": FAL_BRIA_INCREASE_RESOLUTION_MODEL_ID,
                    }
                ),
                encoding="utf-8",
            )
            with patch.multiple(
                self.main,
                CONFIG_FILE=str(Path(temp_dir) / "config.json"),
                USER_DATA_DIR=str(temp_dir),
            ), \
                patch.object(self.main, "ENV_FILE", str(Path(temp_dir) / ".env")), \
                patch.object(
                    self.main, "PROMPTS_STORAGE_FILE", str(Path(temp_dir) / "prompts.json")
                ), \
                patch.object(
                    self.main, "LICENSE_CACHE_FILE", str(Path(temp_dir) / "license.json")
                ), \
                patch.object(
                    self.main.MainWindow, "_migrate_legacy_local_files", return_value=None
                ), \
                patch.object(self.main.QTimer, "singleShot"):
                window = self.main.MainWindow()
                try:
                    self.assertEqual(
                        window.upscale_after_provider_combo.currentData(), "fal"
                    )
                    self.assertEqual(
                        window.config.get("fal_upscale_after_model"),
                        FAL_BRIA_INCREASE_RESOLUTION_MODEL_ID,
                    )
                    window.persist_ui_settings()
                finally:
                    self._close(window)
                persisted = json.loads((Path(temp_dir) / "config.json").read_text("utf-8"))
                self.assertEqual(persisted["upscale_after_provider"], "fal")
                self.assertEqual(
                    persisted["fal_upscale_after_model"],
                    FAL_BRIA_INCREASE_RESOLUTION_MODEL_ID,
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
