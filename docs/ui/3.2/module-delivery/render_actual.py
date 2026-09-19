"""Render production Qt controls with synthetic releases and controlled workers."""
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
from studio_module_update_ui import ModuleUpdatesDialog
from studio_module_updates import ModuleRelease
from v3_components import build_v3_stylesheet
from v3_mode_selection import V3ApplicationView


def main():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(build_v3_stylesheet())
    output = Path(__file__).parent
    phase = threading.Event()
    finish = threading.Event()
    release = ModuleRelease("1.1.0", "fixture.zip", 20971520, "a" * 64,
                            "https://fixture.invalid/downloads/x", module_id="clipart",
                            studio_min="3.2.0", studio_max_exclusive="4.0.0")
    active = {"clipart": "1.0.0", "processing": "1.0.0"}
    allow = {"clipart", "processing", "pinterest"}
    delivery = SimpleNamespace(
        store=SimpleNamespace(trusted_keys={"fixture": b"public"},
                              state=lambda module: {"active": active.get(module), "enabled": True},
                              installed_versions=lambda module: ()),
        updates=SimpleNamespace(current_version="3.2.0", license_client=SimpleNamespace(
            validate=lambda: SimpleNamespace(allows_module=lambda module: module in allow))),
        check=lambda module: release if module == "clipart" else None,
        activate=lambda module, version: active.update({module: version}),
    )

    def install(selected, **callbacks):
        callbacks["progress"](8808039, selected.size)
        if not phase.wait(10):
            raise RuntimeError("preview timed out")
        callbacks["phase"]("verifying")
        if not finish.wait(10):
            raise RuntimeError("preview timed out")
        return {"module_id": selected.module_id, "version": selected.version}

    delivery.install = install

    def wait(predicate):
        for _ in range(500):
            app.processEvents()
            if predicate():
                return
            QTest.qWait(10)
        raise RuntimeError("preview state timed out")

    with tempfile.TemporaryDirectory() as temp:
        view = V3ApplicationView(draft_path=Path(temp) / "draft.json", module_delivery=delivery)
        view.resize(1120, 780)
        view.mode_selection.set_license_status("Лицензия активна", "Доступ: генерация изображений, обработка, Pinterest")
        view.show()
        dialog = ModuleUpdatesDialog(delivery, parent=view)
        # Embed the real dialog only for a single full-window capture offscreen.
        dialog.setWindowFlags(Qt.WindowType.Widget)
        dialog.setGeometry(110, 125, 900, 530)
        dialog.show()

        def capture(name):
            app.processEvents()
            assert dialog.geometry().right() < view.width()
            for _installed, _available, button in dialog.rows.values():
                assert button.width() == 158
                assert button.fontMetrics().horizontalAdvance(button.text()) < button.width()
            assert view.grab().save(str(output / f"actual-{name}.png"))

        try:
            dialog.check_button.click()
            wait(lambda: not dialog.busy)
            capture("available")
            dialog.rows["clipart"][2].click()
            wait(lambda: dialog.progress.maximum() == 100)
            capture("downloading")
            phase.set()
            wait(lambda: dialog.progress.maximum() == 0)
            first = dialog.progress.grab().toImage()
            before = first.bits().asstring(first.sizeInBytes())
            QTest.qWait(250)
            second = dialog.progress.grab().toImage()
            assert before != second.bits().asstring(second.sizeInBytes()), "busy indicator must animate"
            capture("verifying")
            finish.set()
            wait(lambda: not dialog.busy)
            capture("installed")
            allow.clear()
            dialog.check()
            wait(lambda: not dialog.busy)
            capture("no-access")
            delivery.updates.license_client.validate = lambda: (_ for _ in ()).throw(ValueError("fixture"))
            dialog.check()
            wait(lambda: not dialog.busy)
            capture("error")
        finally:
            phase.set()
            finish.set()
            dialog._shutdown()
            view.close()


if __name__ == "__main__":
    main()
