from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from PIL import Image

from license_client import LicenseError
from tests.test_v3_clipart_flow import WorkerFactory as ClipartFactory
from tests.test_v3_pinterest_flow import WorkerFactory as PinterestFactory
from tests.test_v3_processing_flow import WorkerFactory as ProcessingFactory
from v3_clipart_flow import install_clipart_flow
from v3_pinterest_flow import install_pinterest_flow
from v3_processing_flow import apply_processing_recipe, install_processing_flow
from v3_project_state import ProjectMode, ProjectState, PromptEntry, StepId
from v3_wizard import AppShell


class LicenseFlowGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def denied():
        raise LicenseError("Не удалось связаться с сервером лицензий")

    def test_clipart_worker_is_not_created_when_online_authorization_fails(self):
        with tempfile.TemporaryDirectory(prefix="clipart-license-gate-") as temp:
            state = ProjectState(mode=ProjectMode.CLIPART)
            state.common.work_dir = temp
            state.clipart.prompts = [PromptEntry("Test clipart")]
            state.set_step(StepId.REVIEW_RUN)
            factory = ClipartFactory()
            authorize = Mock(side_effect=self.denied)
            controller = install_clipart_flow(
                AppShell(state),
                runtime_settings_provider=lambda: {"kie_api_key": "test-key"},
                worker_factory=factory,
                authorization_provider=authorize,
            )
            result = controller.start()

        self.assertIsNone(result)
        authorize.assert_called_once_with()
        self.assertEqual(factory.workers, [])

    def test_pinterest_worker_is_not_created_when_online_authorization_fails(self):
        with tempfile.TemporaryDirectory(prefix="pinterest-license-gate-") as temp:
            state = ProjectState(mode=ProjectMode.PINTEREST)
            state.common.work_dir = temp
            state.pinterest.prompts = [PromptEntry("Test Pinterest pin")]
            state.set_step(StepId.REVIEW_RUN)
            factory = PinterestFactory()
            authorize = Mock(side_effect=self.denied)
            controller = install_pinterest_flow(
                AppShell(state),
                runtime_settings_provider=lambda: {"kie_api_key": "test-key"},
                worker_factory=factory,
                authorization_provider=authorize,
            )
            result = controller.start()

        self.assertIsNone(result)
        authorize.assert_called_once_with()
        self.assertEqual(factory.workers, [])

    def test_processing_worker_is_not_created_when_online_authorization_fails(self):
        with tempfile.TemporaryDirectory(prefix="processing-license-gate-") as temp:
            source = os.path.join(temp, "source.png")
            Image.new("RGB", (12, 8), (120, 80, 30)).save(source)
            state = ProjectState(mode=ProjectMode.PROCESSING)
            state.common.work_dir = temp
            state.processing.selected_files = [source]
            apply_processing_recipe(state, "basic_enhancement")
            state.set_step(StepId.REVIEW_RUN)
            factory = ProcessingFactory()
            authorize = Mock(side_effect=self.denied)
            controller = install_processing_flow(
                AppShell(state),
                runtime_settings_provider=lambda: {},
                worker_factory=factory,
                authorization_provider=authorize,
            )
            result = controller.start()

        self.assertIsNone(result)
        authorize.assert_called_once_with()
        self.assertEqual(factory.workers, [])


if __name__ == "__main__":
    unittest.main()
