"""Offline packaged workflow check. Never creates a provider worker."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QCoreApplication, QEvent

from license_client import LicenseAuthorization, ModuleEntitlement
from v3_mode_selection import V3ApplicationView
from v3_project_state import StepId


def check_automatic_clipart(evidence_dir=None):
    now = datetime.now(timezone.utc)
    authorization = LicenseAuthorization(
        "fixture", "clipart-generator", "fixture", now, now + timedelta(minutes=5),
        module_entitlements=(ModuleEntitlement("auto-clipart", now, now + timedelta(minutes=5)),),
    )

    class FixtureGate:
        status_text = "Offline fixture"
        verification_text = "Offline fixture"
        current_authorization = authorization

        def authorize_run(self):
            return authorization

    def no_worker(**kwargs):
        raise AssertionError("Packaged smoke must not start generation")

    with TemporaryDirectory(prefix="vibix-auto-smoke-") as temporary:
        root = Path(temporary)
        view = V3ApplicationView(draft_path=root / "draft.json", license_gate=FixtureGate(),
            worker_factory=no_worker, runtime_settings_provider=lambda: {})
        try:
            view.resize(1120, 780)
            view._handle_module_action("auto-clipart", "open")
            controller = view.shell.workflow_controller("auto-clipart")
            controller.brief.directory.setText(str(root))
            controller.brief.theme.setText("Winter flowers")
            controller.brief.total.setValue(3)
            for _ in range(4):
                view.shell.go_next()
            for item in controller.brief.object_editor.items:
                item["name"] = f"Winter flower {item['ordinal']}"
            controller.brief.object_editor.refresh()
            view.shell.go_next()
            assert view.project_state.current_step is StepId.REVIEW_RUN
            assert len(view.project_state.clipart.prompts) == 3
            project_id = view._active_project_id
            controller.save_timer.stop()
            assert view.continue_saved_project(project_id)
            assert view.shell.module_id == "auto-clipart"
            assert view.project_state.current_step is StepId.REVIEW_RUN
            assert len(view.project_state.clipart.prompts) == 3
            if evidence_dir is not None:
                view.show()
                QApplication.processEvents()
                assert view.grab().save(str(Path(evidence_dir) / "automatic-clipart.png"))
            return True
        finally:
            if view.shell is not None:
                controller = view.shell.workflow_controller("auto-clipart")
                if controller is not None:
                    controller.save_timer.stop()
            view.close()
            view.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
