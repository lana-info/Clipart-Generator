"""Non-production Qt mockups. Synthetic data, no license/network operations."""
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout
from v3_components import build_v3_stylesheet, V3Button, ButtonVariant
from v3_mode_selection import V3ApplicationView


def render():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(build_v3_stylesheet())
    output = Path(__file__).parent
    with tempfile.TemporaryDirectory() as temp:
        view = V3ApplicationView(draft_path=Path(temp) / "draft.json")
        view.resize(1120, 780)
        view.show()
        view.mode_selection.set_license_status("Лицензия активна", "Доступ: генерация изображений, обработка, Pinterest")
        app.processEvents()
        view.grab().save(str(output / "before.png"))
        entry = V3Button("Обновления модулей", variant=ButtonVariant.SECONDARY, parent=view)
        entry.setGeometry(822, 95, 274, 34)
        entry.show()
        for state in ("available", "checking", "downloading", "verifying", "busy", "error", "no-access"):
            in_progress = state in {"checking", "downloading", "verifying"}
            overlay = QFrame(view)
            overlay.setGeometry(110, 125, 900, 530)
            overlay.setObjectName("moduleProposal")
            overlay.setStyleSheet("QFrame#moduleProposal {background:#17212b;border:1px solid #405363;border-radius:8px;}"
                                 "QLabel {background:transparent;border:0;color:#f3f6fa;font-size:14px;}"
                                 "QPushButton {min-height:34px;padding:0 12px;}")
            layout = QVBoxLayout(overlay)
            layout.setContentsMargins(28, 24, 28, 24)
            layout.setSpacing(20)
            heading = QHBoxLayout()
            title = QLabel("Модули Studio")
            title.setStyleSheet("font-size:24px;font-weight:600;")
            heading.addWidget(title)
            heading.addStretch()
            check = V3Button("Проверить обновления", variant=ButtonVariant.SECONDARY)
            check.setEnabled(not in_progress)
            heading.addWidget(check)
            layout.addLayout(heading)
            table = QGridLayout()
            table.setHorizontalSpacing(20)
            table.setVerticalSpacing(18)
            headers = ("Модуль", "Установлено", "Доступно", "")
            for col, label in enumerate(headers):
                item = QLabel(label)
                item.setStyleSheet("color:#aab9c7;font-size:12px;")
                table.addWidget(item, 0, col)
            rows = [
                ("Генерация изображений", "1.0.0", "1.1.0", "Обновить"),
                ("Обработка изображений", "1.0.0", "1.0.0", "Установлено"),
                ("Pinterest", "Не установлен", "1.0.0", "Скачать"),
            ]
            for row, (name, installed, available, action) in enumerate(rows, 1):
                if state == "no-access":
                    available, action = "Нет доступа", "Недоступно"
                elif state == "downloading" and row == 1:
                    action = "Скачивание"
                elif state == "verifying" and row == 1:
                    action = "Проверка пакета"
                elif state == "busy" and row == 1:
                    action = "Проект открыт"
                elif state == "error" and row == 1:
                    action = "Повторить"
                for col, label in enumerate((name, installed, available)):
                    table.addWidget(QLabel(label), row, col)
                button = V3Button(action, variant=ButtonVariant.PRIMARY if action in {"Скачать", "Обновить", "Повторить"} else ButtonVariant.SECONDARY)
                button.setFixedWidth(158)
                button.setEnabled(action in {"Скачать", "Обновить", "Повторить"} and not in_progress)
                table.addWidget(button, row, 3)
            table.setColumnStretch(0, 1)
            layout.addLayout(table)
            note = {
                "available": "Проверено только что",
                "checking": "Проверяем обновления модулей…",
                "downloading": "Генерация изображений: скачано 8,4 из 20 МБ",
                "verifying": "Проверяем скачанный пакет генерации изображений…",
                "busy": "Обновление готово. Закройте проект генерации, чтобы установить его.",
                "error": "Не удалось проверить пакет. Установленная версия 1.0.0 сохранена.",
                "no-access": "В лицензии нет доступа к этим модулям.",
            }[state]
            status = QLabel(note)
            status.setWordWrap(True)
            status.setStyleSheet("color:" + ("#f0b65a" if state in {"error", "busy"} else "#aab9c7") + ";")
            layout.addWidget(status)
            if in_progress:
                progress = QProgressBar()
                progress.setFixedHeight(24)
                progress.setStyleSheet(
                    "QProgressBar {background:#243443;border:1px solid #405363;"
                    "border-radius:4px;color:#f3f6fa;text-align:center;font-weight:600;}"
                    "QProgressBar::chunk {background:#168b7d;border-radius:3px;}"
                )
                if state == "downloading":
                    progress.setRange(0, 100)
                    progress.setValue(42)
                    progress.setFormat("%p%")
                else:
                    progress.setRange(0, 0)
                    progress.setTextVisible(False)
                layout.addWidget(progress)
            layout.addStretch()
            footer = QHBoxLayout()
            footer.addWidget(QLabel("Studio 3.2.0"))
            footer.addStretch()
            footer.addWidget(V3Button("Закрыть", variant=ButtonVariant.SECONDARY))
            layout.addLayout(footer)
            overlay.show()
            overlay.raise_()
            app.processEvents()
            assert overlay.geometry().right() <= view.width()
            if in_progress:
                assert progress.width() > 600
                assert overlay.rect().contains(progress.geometry())
                assert progress.maximum() == (100 if state == "downloading" else 0)
                if state == "downloading":
                    assert progress.value() == 42
            view.grab().save(str(output / f"proposal-{state}.png"))
            overlay.hide()
            overlay.deleteLater()
            app.processEvents()
        view.close()


if __name__ == "__main__":
    render()
