"""Module update dialog: serialized background transfers, owner-thread activation."""
from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QDialog, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout

from v3_components import V3Button, ButtonVariant


MODULE_TITLES = {
    "clipart": "Генерация изображений",
    "processing": "Обработка изображений",
    "pinterest": "Pinterest",
    "auto-clipart": "Автоматический Clipart",
}


class ModuleUpdateWorker(QThread):
    progress = pyqtSignal(int, int)
    phase = pyqtSignal(str)

    def __init__(self, delivery, release=None, parent=None):
        super().__init__(parent)
        self.delivery = delivery
        self.release = release
        self.result = None
        self.failed = False

    def run(self):
        try:
            if self.release is not None:
                # Download grants expire. Refresh once on explicit user action,
                # but never substitute a different version for the selected one.
                fresh = self.delivery.check(self.release.module_id)
                identity = ("version", "sha256", "size", "studio_min", "studio_max_exclusive")
                if fresh is None or any(getattr(fresh, name) != getattr(self.release, name) for name in identity):
                    raise ValueError("Selected release changed")
                if fresh.version in self.delivery.store.installed_versions(fresh.module_id):
                    # A previous attempt may have staged successfully but failed
                    # activation. Runtime will reverify the installed signature.
                    self.phase.emit("verifying")
                    self.result = {"module_id": fresh.module_id, "version": fresh.version}
                    return
                self.result = self.delivery.install(
                    fresh, cancelled=self.isInterruptionRequested,
                    progress=self.progress.emit, phase=self.phase.emit,
                )
                return
            authorization = self.delivery.updates.license_client.validate()
            rows = {}
            for module in MODULE_TITLES:
                if self.isInterruptionRequested():
                    return
                if not authorization.allows_module(module):
                    rows[module] = ("denied", None)
                    continue
                try:
                    rows[module] = ("ready", self.delivery.check(module))
                except Exception:
                    rows[module] = ("error", None)
            self.result = rows
        except Exception:
            # Neither provider details, filesystem paths nor tokens enter UI text.
            self.failed = True


class ModuleUpdatesDialog(QDialog):
    def __init__(self, delivery, *, busy_module=lambda _module: False, parent=None):
        super().__init__(parent)
        self.delivery = delivery
        self.busy_module = busy_module
        self.worker = None
        self.releases = {}
        self._shutting_down = False
        self.setWindowTitle("Модули Studio")
        self.setObjectName("moduleUpdatesDialog")
        self.setStyleSheet(
            "QDialog#moduleUpdatesDialog {background:#17212b;border:1px solid #405363;border-radius:8px;}"
            "QDialog#moduleUpdatesDialog QLabel {background:transparent;border:0;color:#f3f6fa;font-size:14px;}"
        )
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.resize(900, 530)
        self.setMinimumSize(820, 480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(20)
        heading = QHBoxLayout()
        title = QLabel("Модули Studio")
        title.setStyleSheet("font-size:24px;font-weight:600;")
        heading.addWidget(title)
        heading.addStretch()
        self.check_button = V3Button("Проверить обновления", ButtonVariant.SECONDARY)
        self.check_button.clicked.connect(self.check)
        heading.addWidget(self.check_button)
        layout.addLayout(heading)
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(18)
        for column, text in enumerate(("Модуль", "Установлено", "Доступно", "")):
            label = QLabel(text)
            label.setProperty("v3Description", True)
            grid.addWidget(label, 0, column)
        self.rows = {}
        for index, (module, title) in enumerate(MODULE_TITLES.items(), 1):
            installed = QLabel()
            available = QLabel("Не проверено")
            button = V3Button("Недоступно", ButtonVariant.SECONDARY)
            button.setFixedWidth(158)
            button.setEnabled(False)
            button.clicked.connect(lambda _checked=False, name=module: self.download(name))
            for column, widget in enumerate((QLabel(title), installed, available, button)):
                grid.addWidget(widget, index, column)
            self.rows[module] = (installed, available, button)
        grid.setColumnStretch(0, 1)
        layout.addLayout(grid)
        self.status = QLabel("Обновления ещё не проверены.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setFixedHeight(24)
        self.progress.setFormat("%p%")
        self.progress.setStyleSheet(
            "QProgressBar {background:#243443;border:1px solid #405363;border-radius:4px;"
            "color:#f3f6fa;text-align:center;font-weight:600;}"
            "QProgressBar::chunk {background:#168b7d;border-radius:3px;}"
        )
        self.progress.hide()
        layout.addWidget(self.progress)
        layout.addStretch()
        footer = QHBoxLayout()
        footer.addWidget(QLabel(f"Studio {delivery.updates.current_version}"))
        footer.addStretch()
        self.close_button = V3Button("Закрыть", ButtonVariant.SECONDARY)
        self.close_button.clicked.connect(self.reject)
        footer.addWidget(self.close_button)
        layout.addLayout(footer)
        self._refresh_installed()
        if not delivery.store.trusted_keys:
            self.check_button.setEnabled(False)
            self.status.setText("Обновления модулей пока недоступны в этой версии Studio.")
        QApplication.instance().aboutToQuit.connect(self._shutdown)

    @property
    def busy(self):
        return self.worker is not None

    def _refresh_installed(self):
        for module, (installed, _available, _button) in self.rows.items():
            try:
                state = self.delivery.store.state(module)
                installed.setText(state["active"] if state["enabled"] and state["active"] else "В составе Studio")
            except Exception:
                installed.setText("Ошибка версии")

    def _start(self, release=None):
        if self.busy:
            return
        self.worker = ModuleUpdateWorker(self.delivery, release, self)
        self.check_button.setEnabled(False)
        self.close_button.setEnabled(False)
        for _installed, _available, button in self.rows.values():
            button.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.show()
        self.worker.progress.connect(self._progress)
        self.worker.phase.connect(self._phase)
        self.worker.finished.connect(self._finished)
        self.worker.start()

    def check(self):
        if self.busy or not self.delivery.store.trusted_keys:
            return
        self.releases.clear()
        self.status.setText("Проверяем обновления модулей…")
        self._start()

    def download(self, module):
        if self.busy or module not in self.releases:
            return
        if self.busy_module(module):
            self.status.setText("Проект открыт. Завершите работу и перезапустите Studio перед обновлением модуля.")
            return
        self.status.setText(f"{MODULE_TITLES[module]}: подготовка загрузки…")
        self.rows[module][2].setText("Скачивание")
        self._start(self.releases[module])

    def _progress(self, received, total):
        if not self.busy or self.worker.release is None or total <= 0:
            return
        self.progress.setRange(0, 100)
        self.progress.setValue(min(100, int(received * 100 / total)))
        self.progress.setTextVisible(True)
        title = MODULE_TITLES[self.worker.release.module_id]
        amount = f"{received / 1048576:.1f} из {total / 1048576:.1f}".replace(".", ",")
        self.status.setText(f"{title}: скачано {amount} МБ")

    def _phase(self, phase):
        if phase == "verifying":
            self.progress.setRange(0, 0)
            self.progress.setTextVisible(False)
            self.status.setText("Проверяем скачанный пакет…")

    def _finished(self):
        worker = self.worker
        try:
            if self._shutting_down:
                return
            if worker.failed:
                if worker.release is None:
                    for _installed, available, _button in self.rows.values():
                        available.setText("Ошибка проверки")
                self.status.setText("Не удалось проверить или скачать обновление. Текущая версия сохранена.")
            elif worker.release is None:
                for module, (state, release) in (worker.result or {}).items():
                    installed, available, button = self.rows[module]
                    available.setText({"denied": "Нет доступа", "error": "Ошибка проверки"}.get(
                        state, release.version if release else "Нет обновлений"))
                    button.setText("Нет обновлений" if state == "ready" else "Недоступно")
                    if release is not None:
                        self.releases[module] = release
                self.status.setText("Не все модули удалось проверить. Повторите проверку." if any(
                    state == "error" for state, _release in (worker.result or {}).values()) else "Проверено только что")
            else:
                module = worker.release.module_id
                if self.busy_module(module):
                    self.status.setText("Пакет проверен. Завершите работу и перезапустите Studio перед обновлением модуля.")
                else:
                    self.delivery.activate(module, worker.release.version)
                    self.releases.pop(module, None)
                    self.rows[module][2].setText("Установлено")
                    self.status.setText(f"{MODULE_TITLES[module]}: обновление установлено.")
        except Exception:
            self.status.setText("Не удалось активировать обновление. Текущая версия сохранена.")
        finally:
            self.worker = None
            worker.deleteLater()
            self.progress.hide()
            self.close_button.setEnabled(True)
            self.check_button.setEnabled(bool(self.delivery.store.trusted_keys))
            self._refresh_installed()
            for module, (_installed, _available, button) in self.rows.items():
                button.setEnabled(module in self.releases)
                button.set_variant(ButtonVariant.PRIMARY if module in self.releases else ButtonVariant.SECONDARY)
                if module in self.releases:
                    button.setText("Обновить")

    def reject(self):
        if not self.busy:
            super().reject()

    def closeEvent(self, event):
        if self.busy:
            event.ignore()
        else:
            super().closeEvent(event)

    def _shutdown(self):
        self._shutting_down = True
        if self.worker is not None:
            self.worker.requestInterruption()
            self.worker.wait()
