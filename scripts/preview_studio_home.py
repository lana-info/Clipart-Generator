"""Render the real Qt home with synthetic projects, without provider calls."""
from pathlib import Path
import sys
import tempfile
from dataclasses import replace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtWidgets import QApplication
from studio_projects import ProjectStore
from v3_project_state import ProjectState, ProjectMode
from v3_mode_selection import V3ApplicationView
from studio_catalog import ModuleAvailability
from studio_catalog_ui import BUILTIN_CATALOG


def main():
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix="studio-home-preview-") as temporary:
        root = Path(temporary)
        store = ProjectStore(root / "projects")
        for name, mode in [
            ("Весенние цветы", ProjectMode.CLIPART),
            ("Летние пины", ProjectMode.PINTEREST),
            ("Лесные персонажи", ProjectMode.CLIPART),
        ]:
            state = ProjectState(mode=mode)
            state.common.project_name = name
            store.create(mode.value, name, state.to_dict())
        view = V3ApplicationView(draft_path=root / "project_state.json")
        view.resize(1120, 780)
        view.show()
        app.processEvents()
        button = view.mode_selection.all_projects_button
        assert button.isVisible() and button.isEnabled() and button.width() > 0
        assert view.grab().save(str(output / "recent-projects-1120x780.png"))
        screen = view.mode_selection
        screen.set_saved_projects([])
        app.processEvents()
        assert view.grab().save(str(output / "catalog-empty-1120x780.png"))
        screen.set_saved_projects(store.recent())
        screen.set_license_status("Тестовые состояния каталога", "Синтетические данные, без покупки и скачивания")
        released = [replace(entry, released=True) for entry in BUILTIN_CATALOG]
        screen.set_module_catalog(released, {
            "auto-clipart": ModuleAvailability(entitled=True, download_supported=True),
            "patterns": ModuleAvailability(purchase_supported=True),
            "mockups": ModuleAvailability(compatible=False),
        })
        app.processEvents()
        assert view.grab().save(str(output / "catalog-actions-fixture-1120x780.png"))
        view.resize(980, 700)
        app.processEvents()
        screen.catalog_scroll.verticalScrollBar().setValue(
            screen.catalog_scroll.verticalScrollBar().maximum())
        app.processEvents()
        assert view.grab().save(str(output / "catalog-actions-fixture-980x700.png"))
        view.close()
        view.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    main()
