from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from v3_mode_selection import V3ApplicationView


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Clipart Generator")
    app.setApplicationDisplayName("Clipart Generator 3.0")

    window = V3ApplicationView()
    window.setWindowTitle("Clipart Generator 3.0")
    window.resize(1120, 780)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
