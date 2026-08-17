from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QStandardPaths
from PyQt6.QtWidgets import QApplication

from v3_mode_selection import V3ApplicationView
from app_identity import APP_NAME


def _draft_path() -> Path:
    app_data = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation
    )
    return Path(app_data) / "project_state.json"


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(f"{APP_NAME} 3.0")

    window = V3ApplicationView(draft_path=_draft_path())
    window.setWindowTitle(f"{APP_NAME} 3.0")
    window.resize(1120, 780)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
